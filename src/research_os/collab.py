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
import os
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


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
