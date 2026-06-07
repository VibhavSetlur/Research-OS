"""Multi-researcher collaboration helpers.

When two or more people share a Research OS workspace (typical for a lab
or a paired analyst + PI), it's useful to record *who did what when*
even if the workspace isn't under git. This module:

* Resolves the current researcher's identity from ``git config`` →
  ``$USER`` env var → ``"anonymous"``.
* Appends activity rows to ``CONTRIBUTORS.md`` at the project root.
* Merges the resolved author into ``inputs/researcher_config.yaml``
  under a deduplicated ``authors:`` list.

The activity log is plain Markdown so it's diff-friendly and readable
in any GitHub/Gitea/Forgejo viewer.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Author:
    name: str
    email: str = ""
    source: str = "fallback"   # "git" | "env" | "fallback"

    def display(self) -> str:
        if self.email:
            return f"{self.name} <{self.email}>"
        return self.name

    def as_dict(self) -> dict:
        d = {"name": self.name}
        if self.email:
            d["email"] = self.email
        return d


def whoami(root: Path | None = None) -> Author:
    """Resolve the current researcher's identity.

    Order of preference:
      1. ``git config user.name`` (+ ``user.email``) — local repo first,
         then global. This works even when the project isn't a git repo
         because the global config is consulted as a fallback.
      2. ``$USER`` env var + a stub ``user@hostname`` email.
      3. ``"anonymous"`` literal.
    """
    # 1. Try git, repo-local first, then global.
    for scope in (["--local"], ["--global"]):
        try:
            cwd = str(root) if root else None
            name = subprocess.run(
                ["git", "config", *scope, "user.name"],
                capture_output=True, text=True, timeout=3, cwd=cwd,
            )
            email = subprocess.run(
                ["git", "config", *scope, "user.email"],
                capture_output=True, text=True, timeout=3, cwd=cwd,
            )
            n = name.stdout.strip() if name.returncode == 0 else ""
            e = email.stdout.strip() if email.returncode == 0 else ""
            if n:
                return Author(name=n, email=e, source="git")
        except (OSError, subprocess.SubprocessError):
            continue
    # 2. Env.
    user = os.environ.get("USER") or os.environ.get("USERNAME")
    if user:
        try:
            host = socket.gethostname()
        except OSError:
            host = "local"
        return Author(name=user, email=f"{user}@{host}", source="env")
    # 3. Fallback.
    try:
        return Author(name=getpass.getuser(), source="env")
    except Exception:
        return Author(name="anonymous", source="fallback")


# ---------------------------------------------------------------------------
# CONTRIBUTORS.md
# ---------------------------------------------------------------------------


_CONTRIBUTORS_HEADER = """\
# Contributors

Activity log for this Research OS workspace. Updated automatically by
`research-os init`, `research-os ide add`, and other actions that change
the workspace's wiring. Hand-edit only to fix bad data.

| When (UTC) | Researcher | Action |
|---|---|---|
"""


def log_action(root: Path, author: Author, action: str) -> Path:
    """Append a row to ``CONTRIBUTORS.md``. Creates the file if missing."""
    path = root / "CONTRIBUTORS.md"
    if not path.exists():
        path.write_text(_CONTRIBUTORS_HEADER)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    row = f"| {when} | {_md_escape(author.display())} | {_md_escape(action)} |\n"
    with open(path, "a") as f:
        f.write(row)
    return path


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# IDE wiring/unwiring on an existing workspace
# ---------------------------------------------------------------------------

IDE_FILES: dict[str, list[str]] = {
    "claude":      [".claude/mcp.json", ".claude/rules", ".claude/commands", "CLAUDE.md"],
    "cursor":      [".cursor/mcp.json", ".cursor/rules"],
    "vscode":      [".vscode/mcp.json"],
    "antigravity": [".antigravity/mcp.json", ".antigravity/rules"],
    "opencode":    ["opencode.json"],
    "windsurf":    [".windsurfrules"],
    "continue":    [".continuerules"],
    "aider":       [".aider.conf.yml"],
}


def list_wired_ides(root: Path) -> dict[str, bool]:
    """Return a map of ide-key → bool indicating whether its primary
    config file currently exists in the workspace."""
    out: dict[str, bool] = {}
    for ide, files in IDE_FILES.items():
        primary = root / files[0]
        out[ide] = primary.exists()
    return out


def add_ide(root: Path, ide: str) -> list[str]:
    """Wire one IDE into an existing workspace. Returns the list of file
    paths created. Raises ``ValueError`` for an unknown IDE key.

    Idempotent — if a file already exists, it is not overwritten.
    """
    if ide not in IDE_FILES:
        raise ValueError(f"unknown ide: {ide!r}. Choose from: {', '.join(sorted(IDE_FILES))}")
    from research_os.project_ops import _setup_mcp_configs
    before = list_wired_ides(root)
    _setup_mcp_configs(root, [ide])
    after = list_wired_ides(root)
    created = []
    for fpath in IDE_FILES[ide]:
        if (root / fpath).exists():
            created.append(fpath)
    return created if not before.get(ide, False) or after.get(ide, False) else []


# ---------------------------------------------------------------------------
# Composable MCP servers (Postgres, Slack, GitHub, Filesystem, Memory, ...)
# ---------------------------------------------------------------------------
#
# `research-os ide add` wires the RO server into an IDE config. This block
# is the OTHER half: composing third-party MCP servers (Postgres, Slack,
# GitHub, Filesystem, Memory, Notion, ...) into the same mcpServers block
# RO already manages, so the researcher's IDE picks them up alongside.
#
# IDE config schemas vary slightly:
#   * cursor / claude / vscode / antigravity → top-level `mcpServers: {...}`
#   * opencode → top-level `mcp: {...}` (note the singular form)
#   * windsurf / continue / aider → not JSON, not currently composable here
#
# IDES_WITH_MCP_JSON below is the set we can merge into.

IDES_WITH_MCP_JSON: dict[str, tuple[str, str]] = {
    # ide_key: (config_file_relpath, top_level_block_key)
    "cursor":      (".cursor/mcp.json",      "mcpServers"),
    "claude":      (".claude/mcp.json",      "mcpServers"),
    "antigravity": (".antigravity/mcp.json", "mcpServers"),
    "vscode":      (".vscode/mcp.json",      "mcpServers"),
    "opencode":    ("opencode.json",         "mcp"),
}


# Vetted snippet templates for common third-party MCP servers. Placeholder
# tokens use the ${TOKEN} form so they're greppable and obvious in the
# resulting config.
MCP_TEMPLATES: dict[str, dict] = {
    "slack": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {
            "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
            "SLACK_TEAM_ID":   "${SLACK_TEAM_ID}",
        },
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres",
                 "${POSTGRES_CONNECTION_STRING}"],
    },
    "notion": {
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {"NOTION_API_KEY": "${NOTION_API_KEY}"},
    },
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem",
                 "${ALLOWED_DIRECTORY}"],
    },
    "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
    },
}


def _read_mcp_config(path: Path) -> dict:
    """Read an IDE's MCP config JSON, returning {} if missing/unreadable."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except (OSError, json.JSONDecodeError):
        return {}


def _write_mcp_config(path: Path, data: dict) -> None:
    """Write JSON with a trailing newline to keep diffs clean."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def mcp_add_server(
    root: Path,
    name: str,
    entry: dict,
    ides: list[str] | None = None,
) -> dict[str, str]:
    """Merge an MCP server `entry` under `name` into each IDE's config.

    `ides` defaults to the IDEs that are already wired in the workspace
    (i.e. the ones whose primary config file exists). Returns a map of
    ide → status ('added' | 'updated' | 'skipped: <reason>').
    """
    wired = list_wired_ides(root)
    if ides is None:
        ides = [ide for ide, present in wired.items()
                if present and ide in IDES_WITH_MCP_JSON]
    out: dict[str, str] = {}
    for ide in ides:
        if ide not in IDES_WITH_MCP_JSON:
            out[ide] = f"skipped: {ide!r} does not support composable mcpServers"
            continue
        relpath, block_key = IDES_WITH_MCP_JSON[ide]
        cfg_path = root / relpath
        config = _read_mcp_config(cfg_path)
        block = config.setdefault(block_key, {})
        existed = name in block
        block[name] = entry
        _write_mcp_config(cfg_path, config)
        out[ide] = "updated" if existed else "added"
    return out


def mcp_remove_server(
    root: Path,
    name: str,
    ides: list[str] | None = None,
) -> dict[str, str]:
    """Remove `name` from each IDE's mcpServers/mcp block. Returns ide→status."""
    wired = list_wired_ides(root)
    if ides is None:
        ides = [ide for ide, present in wired.items()
                if present and ide in IDES_WITH_MCP_JSON]
    out: dict[str, str] = {}
    for ide in ides:
        if ide not in IDES_WITH_MCP_JSON:
            out[ide] = f"skipped: {ide!r} does not support composable mcpServers"
            continue
        relpath, block_key = IDES_WITH_MCP_JSON[ide]
        cfg_path = root / relpath
        if not cfg_path.exists():
            out[ide] = "skipped: no config file"
            continue
        config = _read_mcp_config(cfg_path)
        block = config.get(block_key) or {}
        if name not in block:
            out[ide] = "skipped: not present"
            continue
        del block[name]
        config[block_key] = block
        _write_mcp_config(cfg_path, config)
        out[ide] = "removed"
    return out


def mcp_list_servers(root: Path) -> dict[str, dict[str, dict]]:
    """Return ide → {server_name → entry-dict} for every IDE we can read.

    Includes IDEs whose config file is present even if their mcpServers
    block is empty (so the caller can render an "(empty)" row).
    """
    out: dict[str, dict[str, dict]] = {}
    for ide, (relpath, block_key) in IDES_WITH_MCP_JSON.items():
        cfg_path = root / relpath
        if not cfg_path.exists():
            continue
        config = _read_mcp_config(cfg_path)
        block = config.get(block_key) or {}
        out[ide] = block if isinstance(block, dict) else {}
    return out


def remove_ide(root: Path, ide: str) -> list[str]:
    """Remove every artefact this IDE owns. Returns the list of files
    removed. Raises ``ValueError`` for an unknown IDE key."""
    import shutil
    if ide not in IDE_FILES:
        raise ValueError(f"unknown ide: {ide!r}. Choose from: {', '.join(sorted(IDE_FILES))}")
    removed: list[str] = []
    for rel in IDE_FILES[ide]:
        p = root / rel
        if not p.exists():
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed.append(rel)
        except OSError:
            pass
    return removed
