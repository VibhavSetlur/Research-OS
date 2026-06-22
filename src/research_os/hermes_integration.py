"""Make Research-OS a first-class citizen inside Hermes Agent.

Hermes (https://hermes-agent.nousresearch.com) is a general agent with a
global config at ``~/.hermes/config.yaml``. Two integration points let a
Hermes user drive a Research-OS project end to end:

1. **MCP server** — Research-OS ships an MCP server (``research-os start``
   / ``research_os.server``). Registering it under the top-level
   ``mcp_servers:`` block exposes every RO tool (the protocol router,
   audits, synthesis, the self-improving skill registry, ...) to Hermes.

2. **Skills dir** — Research-OS ships a canonical Hermes SKILL.md that
   teaches the agent how to use the RO workflow. Adding its directory to
   ``skills.external_dirs`` makes the agent load it automatically.

This module edits the Hermes config **non-destructively** (ruamel
round-trip preserves the user's comments and ordering) and is fully
idempotent: re-running ``research-os hermes add`` never duplicates an
entry. Everything is reversible via ``research-os hermes remove``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locating the Hermes config.
# ---------------------------------------------------------------------------

#: Name under which the RO server is registered in mcp_servers.
SERVER_KEY = "research-os"

#: Directory (under the Hermes home) where we drop the RO skill.
_SKILL_DIRNAME = "research-os"


def hermes_home() -> Path:
    """Return the Hermes home dir, honouring HERMES_HOME then default."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hermes"


def hermes_config_path() -> Path:
    """Return the Hermes config path, honouring HERMES_CONFIG then default."""
    env = os.environ.get("HERMES_CONFIG")
    if env:
        return Path(env).expanduser()
    return hermes_home() / "config.yaml"


# ---------------------------------------------------------------------------
# YAML round-trip (comment-preserving).
# ---------------------------------------------------------------------------

def _yaml():
    from ruamel.yaml import YAML

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _load(path: Path):
    if not path.exists():
        return {}
    y = _yaml()
    with path.open("r", encoding="utf-8") as fh:
        data = y.load(fh)
    return data if data is not None else {}


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = _yaml()
    with path.open("w", encoding="utf-8") as fh:
        y.dump(data, fh)


# ---------------------------------------------------------------------------
# The MCP server entry we register.
# ---------------------------------------------------------------------------

def _server_entry(command: str, args: list[str], url: str | None) -> dict:
    """Build the mcp_servers entry. Hermes accepts {command,args} (stdio)
    or {url} (HTTP/SSE). We only set the keys that are actually used so the
    config stays clean."""
    entry: dict = {}
    if url:
        entry["url"] = url
    else:
        entry["command"] = command
        entry["args"] = list(args)
    return entry


def default_command() -> tuple[str, list[str]]:
    """The default stdio launch for the RO server.

    Prefer the installed console-script if it is on PATH; otherwise fall
    back to ``python -m research_os.server`` using the *current*
    interpreter so the entry keeps working inside the active env.
    """
    import shutil

    exe = shutil.which("research-os")
    if exe:
        return exe, ["start", "--transport", "stdio"]
    return sys.executable, ["-m", "research_os.server.entry"]


# ---------------------------------------------------------------------------
# Skill installation.
# ---------------------------------------------------------------------------

def _skill_source() -> Path:
    """Path to the packaged Hermes SKILL.md template inside the wheel."""
    return Path(__file__).resolve().parent / "templates" / "hermes" / "SKILL.md"


def skill_install_dir() -> Path:
    """Where the RO skill is installed for Hermes to discover."""
    return hermes_home() / "skills" / _SKILL_DIRNAME


def install_skill() -> Path:
    """Copy the packaged SKILL.md into the Hermes skills tree.

    Returns the installed SKILL.md path. Idempotent: overwrites in place so
    upgrades pick up the latest copy.
    """
    src = _skill_source()
    dst_dir = skill_install_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "SKILL.md"
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:  # pragma: no cover — defensive; template ships in the wheel
        dst.write_text(_FALLBACK_SKILL, encoding="utf-8")
    return dst


# ---------------------------------------------------------------------------
# Public ops: add / remove / status.
# ---------------------------------------------------------------------------

def add(
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    config_path: Path | None = None,
) -> dict:
    """Register the RO MCP server + skill dir in the Hermes config.

    Idempotent. Returns a summary dict describing what changed.
    """
    path = config_path or hermes_config_path()
    data = _load(path)

    if command is None and not url:
        command, args = default_command()
    args = args or []

    # 1. mcp_servers entry
    servers = data.setdefault("mcp_servers", {})
    if not hasattr(servers, "setdefault"):  # corrupt/non-mapping → reset
        servers = {}
        data["mcp_servers"] = servers
    existed = SERVER_KEY in servers
    servers[SERVER_KEY] = _server_entry(command or "", args, url)

    # 2. skills.external_dirs
    skill_dst = install_skill()
    skills_block = data.setdefault("skills", {})
    if not hasattr(skills_block, "setdefault"):
        skills_block = {}
        data["skills"] = skills_block
    ext = skills_block.get("external_dirs")
    if not isinstance(ext, list):
        ext = []
        skills_block["external_dirs"] = ext
    skill_parent = str(skill_dst.parent.parent)  # the skills/ root we added
    skill_dir = str(skill_dst.parent)            # skills/research-os
    dir_added = False
    # Hermes scans each external_dir for */SKILL.md, so register the parent
    # ("skills/") only if it is not already the built-in tree; otherwise add
    # the specific skill dir. The built-in ~/.hermes/skills is always scanned,
    # so when we install there we need NO external_dir entry at all.
    builtin = str(hermes_home() / "skills")
    if skill_parent != builtin and skill_dir not in ext and skill_parent not in ext:
        ext.append(skill_dir)
        dir_added = True

    _dump(path, data)
    return {
        "config_path": str(path),
        "server_key": SERVER_KEY,
        "server_action": "updated" if existed else "added",
        "command": command,
        "args": args,
        "url": url,
        "skill_path": str(skill_dst),
        "external_dir_added": dir_added,
        "external_dir_needed": skill_parent != builtin,
    }


def remove(config_path: Path | None = None) -> dict:
    """Unregister the RO server + external_dir from the Hermes config.

    Leaves the installed SKILL.md on disk (cheap, harmless); only unwires
    the config so Hermes stops loading it. Idempotent.
    """
    path = config_path or hermes_config_path()
    data = _load(path)

    server_removed = False
    servers = data.get("mcp_servers")
    if isinstance(servers, dict) and SERVER_KEY in servers:
        del servers[SERVER_KEY]
        server_removed = True

    dir_removed = False
    skills_block = data.get("skills")
    if isinstance(skills_block, dict):
        ext = skills_block.get("external_dirs")
        if isinstance(ext, list):
            skill_dir = str(skill_install_dir())
            for cand in (skill_dir,):
                while cand in ext:
                    ext.remove(cand)
                    dir_removed = True

    _dump(path, data)
    return {
        "config_path": str(path),
        "server_removed": server_removed,
        "external_dir_removed": dir_removed,
    }


def status(config_path: Path | None = None) -> dict:
    """Report whether RO is currently wired into the Hermes config."""
    path = config_path or hermes_config_path()
    data = _load(path)
    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    entry = servers.get(SERVER_KEY) if isinstance(servers, dict) else None
    skills_block = data.get("skills") if isinstance(data, dict) else None
    ext = skills_block.get("external_dirs") if isinstance(skills_block, dict) else None
    skill_dst = skill_install_dir() / "SKILL.md"
    return {
        "config_path": str(path),
        "config_exists": path.exists(),
        "server_registered": bool(entry),
        "server_entry": dict(entry) if isinstance(entry, dict) else None,
        "skill_installed": skill_dst.exists(),
        "skill_path": str(skill_dst),
        "external_dirs": list(ext) if isinstance(ext, list) else [],
    }


# A minimal in-code fallback so `add` never crashes even if the packaged
# template is somehow missing from the install. The real, richer skill
# ships at templates/hermes/SKILL.md.
_FALLBACK_SKILL = """\
---
name: research-os
description: Drive a Research-OS project — rigorous, reproducible research
  with adaptive autonomy and a self-improving skill registry. Use whenever
  the user does computational research, literature review, data analysis,
  or writes a scientific paper/report.
---

# Research-OS

Research-OS is an MCP server that turns an agent into a disciplined
research collaborator. When this skill is active and the RO MCP server is
connected, prefer RO tools over ad-hoc shell work:

- Start every task by routing it through the protocol router (the RO
  server exposes a routing tool that maps the request to the right
  protocol and decomposition).
- Respect the workspace contract: `inputs/` is the immutable source of
  truth, `synthesis/` holds deliverables, `.os_state/` is RO-managed.
- Autonomy is **adaptive** by default: RO flows on cheap, reversible
  actions and pauses only on irreversible / expensive / external-cost
  moves, tightening as the project earns rigor. Do not ask the user to
  pick a mode.
- After milestones, run the self-improving skill registry (distill, then
  promote) so recurring lessons crystallize into reusable skills.

If the RO MCP server is not connected, tell the user to run
`research-os hermes add` and restart Hermes.
"""
