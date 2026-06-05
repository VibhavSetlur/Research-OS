"""Synapse (Sage Bionetworks) data-sharing platform adapter.

Detects:
    * `.synapseConfig` file in the project root or workspace
    * `import synapseclient` / `from synapseclient` in any Python script
    * `syn\\d{6,}` entity-ID references (e.g. `syn.get("syn12345678")`)
      anywhere in scripts / notebooks / configs

Extracts per-project:
    * `config_file` — relative path to `.synapseConfig` if present
    * `project_id`  — top-level project synID parsed from `.synapseConfig`
    * `username`    — username (NOT password / auth token) parsed from `.synapseConfig`
    * `entities_referenced` — list of {id, source, line, note} pulled from
      every script that mentions a `synXXXXXXXX` literal, with the nearest
      preceding inline / line comment captured as the `note` field
    * `synapse_scripts` — list of scripts that import `synapseclient`

CRITICAL: extraction is filesystem-only. We never auto-query Synapse — that
would require an auth token AND would leak the project ID off-machine. The
optional `tool_synapse_entity_info` tool is the only path to a live query,
and it degrades to a warning if `synapseclient` is not installed.

Optional tools:
    * tool_synapse_entity_info(entity_id) — opt-in; tries `synapseclient`
      with the configured `.synapseConfig` and returns entity metadata.

Limitations (also surfaced under `_notes` in the returned payload):
    * `.synapseConfig` is parsed as INI; non-standard sections are ignored.
    * Entity-ID extraction is regex-based and does NOT resolve dynamically
      constructed IDs (e.g. `"syn" + str(n)`).
    * The `note` field captures the nearest preceding inline `#` comment on
      the same or prior line; it will miss block / docstring context.
"""
from __future__ import annotations

import configparser
import json
import re
from pathlib import Path
from typing import Any

from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    register_adapter,
)


__version__ = "1.8.0"


# ── detection ─────────────────────────────────────────────────────────


_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+synapseclient\b|from\s+synapseclient\b)", re.MULTILINE
)
_ENTITY_RE = re.compile(r"\b(syn\d{6,})\b")
_CONFIG_NAME = ".synapseConfig"


def _candidate_scripts(root: Path) -> list[Path]:
    """All scripts/notebooks/configs that could mention Synapse."""
    suffixes = {".py", ".ipynb", ".r", ".R", ".rmd", ".Rmd", ".sh", ".bash",
                ".yaml", ".yml", ".json", ".md", ".txt", ".cfg", ".ini"}
    scripts: list[Path] = []
    workspace = root / "workspace"
    for d in (workspace, root / "scripts", root):
        if not d.exists():
            continue
        # Only walk root non-recursively (avoid descending into venvs, .git, etc.)
        if d == root:
            for p in d.iterdir():
                if p.is_file() and p.suffix in suffixes:
                    scripts.append(p)
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in suffixes:
                scripts.append(p)
    return scripts


def _find_config(root: Path) -> Path | None:
    """Locate `.synapseConfig` in project root or workspace."""
    for candidate in (root / _CONFIG_NAME, root / "workspace" / _CONFIG_NAME):
        if candidate.is_file():
            return candidate
    # Also accept .synapseConfig nested under workspace/<step_id>/
    workspace = root / "workspace"
    if workspace.exists():
        for p in workspace.rglob(_CONFIG_NAME):
            if p.is_file():
                return p
    return None


def detect(root: Path) -> bool:
    if _find_config(root) is not None:
        return True
    for path in _candidate_scripts(root):
        try:
            head = path.read_text(errors="ignore")[:8192]
        except Exception:
            continue
        if _IMPORT_RE.search(head) or _ENTITY_RE.search(head):
            return True
    return False


# ── extraction ────────────────────────────────────────────────────────


def _parse_config(path: Path) -> dict[str, Any]:
    """Pull username + project_id out of an INI-shaped `.synapseConfig`.

    NEVER captures `authtoken` / `password` / `apikey` — we don't store secrets.
    """
    parser = configparser.ConfigParser()
    out: dict[str, Any] = {"username": None, "project_id": None}
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return out
    if parser.has_section("authentication"):
        username = parser["authentication"].get("username")
        if username:
            out["username"] = username.strip()
    if parser.has_section("project"):
        # Synapse projects are sometimes keyed as `id` or `project`
        pid = parser["project"].get("id") or parser["project"].get("project")
        if pid:
            pid = pid.strip()
            if _ENTITY_RE.match(pid):
                out["project_id"] = pid
    # Fall back: scan any section for a synXXXXXXXX value
    if out["project_id"] is None:
        for section in parser.sections():
            for _, value in parser.items(section):
                m = _ENTITY_RE.search(str(value))
                if m:
                    out["project_id"] = m.group(1)
                    break
            if out["project_id"]:
                break
    return out


def _comment_near(lines: list[str], idx: int) -> str | None:
    """Return the nearest `#` comment on the same line or the line just above."""
    line = lines[idx]
    # Inline `# ...` on the same line
    hash_pos = line.find("#")
    if hash_pos != -1:
        # Only treat it as a comment if it's not inside the matched entity itself
        return line[hash_pos + 1:].strip() or None
    # Otherwise look upwards for the most recent non-blank line that starts with #
    j = idx - 1
    while j >= 0:
        stripped = lines[j].strip()
        if not stripped:
            j -= 1
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
        break
    return None


def _scan_entities(path: Path, root: Path) -> tuple[list[dict], bool]:
    """Return (entity refs, imports_synapseclient?) for a single file."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return [], False
    has_import = bool(_IMPORT_RE.search(text))
    lines = text.splitlines()
    rel = str(path.relative_to(root))
    refs: list[dict] = []
    for i, line in enumerate(lines):
        for m in _ENTITY_RE.finditer(line):
            refs.append({
                "id": m.group(1),
                "source": rel,
                "line": i + 1,
                "note": _comment_near(lines, i),
            })
    return refs, has_import


def extract(root: Path, step_id: str | None = None) -> dict:
    scripts = _candidate_scripts(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        scripts = [s for s in scripts if str(s.resolve()).startswith(str(step_prefix))]

    config_path = _find_config(root)
    if step_id and config_path is not None:
        # Only surface the config when it is inside the requested step's tree
        step_prefix = (root / "workspace" / step_id).resolve()
        if not str(config_path.resolve()).startswith(str(step_prefix)):
            config_path = None

    config_info: dict[str, Any] = {"username": None, "project_id": None}
    if config_path is not None:
        config_info = _parse_config(config_path)

    entities: list[dict] = []
    synapse_scripts: list[str] = []
    seen_keys: set[tuple[str, str, int]] = set()
    for path in scripts:
        refs, has_import = _scan_entities(path, root)
        if has_import:
            synapse_scripts.append(str(path.relative_to(root)))
        for ref in refs:
            key = (ref["id"], ref["source"], ref["line"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entities.append(ref)

    return {
        "config_file": str(config_path.relative_to(root)) if config_path else None,
        "project_id": config_info["project_id"],
        "username": config_info["username"],
        "entities_referenced": entities,
        "synapse_scripts": synapse_scripts,
        "scripts_scanned": len(scripts),
        "_notes": [
            "Extraction is filesystem-only; no Synapse API calls are made at "
            "detect/extract time.",
            "Auth tokens / passwords are intentionally NOT parsed from "
            ".synapseConfig — only username + project_id.",
            "Entity IDs are regex-matched (syn\\d{6,}); dynamically built IDs "
            "(e.g. 'syn' + str(n)) are not resolved.",
            "The 'note' field captures the nearest inline or preceding-line '#' "
            "comment; block / docstring context is not captured.",
        ],
    }


def describe() -> dict:
    return {
        "name": "synapse",
        "version": __version__,
        "platform": "Sage Bionetworks Synapse",
        "queries_remote": False,
    }


# ── optional tools ────────────────────────────────────────────────────


def _ok(data: dict) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]


def _err(message: str) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]


def _handle_entity_info(name: str, arguments: dict, root: Path) -> Any:
    entity_id = (arguments.get("entity_id") or "").strip()
    if not entity_id:
        return _err("entity_id is required")
    if not _ENTITY_RE.fullmatch(entity_id):
        return _err(f"entity_id must match synXXXXXXXX, got {entity_id!r}")

    try:
        import synapseclient  # type: ignore
    except ImportError:
        return _ok({
            "status": "warning",
            "message": "synapseclient is not installed; "
                       "install it (`pip install synapseclient`) to enable live queries. "
                       "Refusing to make any network call.",
            "entity_id": entity_id,
        })

    config_path = _find_config(root)
    if config_path is None:
        return _ok({
            "status": "warning",
            "message": "No .synapseConfig found in project root or workspace; "
                       "Synapse auth requires either a .synapseConfig or an explicit "
                       "auth token. Refusing to query without configured credentials.",
            "entity_id": entity_id,
        })

    try:
        syn = synapseclient.Synapse(configPath=str(config_path), silent=True)
        syn.login()
    except Exception as exc:
        return _err(f"synapseclient login failed: {exc!r}")

    try:
        entity = syn.get(entity_id, downloadFile=False)
    except Exception as exc:
        return _err(f"syn.get({entity_id!r}) failed: {exc!r}")

    # Pull a safe subset of metadata — avoid serialising arbitrary attrs
    info: dict[str, Any] = {
        "id": getattr(entity, "id", entity_id),
        "name": getattr(entity, "name", None),
        "concreteType": getattr(entity, "concreteType", None),
        "parentId": getattr(entity, "parentId", None),
        "versionNumber": getattr(entity, "versionNumber", None),
        "createdOn": getattr(entity, "createdOn", None),
        "modifiedOn": getattr(entity, "modifiedOn", None),
        "createdBy": getattr(entity, "createdBy", None),
        "modifiedBy": getattr(entity, "modifiedBy", None),
    }
    return _ok({
        "entity_id": entity_id,
        "config_file": str(config_path.relative_to(root)),
        "metadata": info,
        "note": "Live query via synapseclient; downloadFile was disabled. "
                "This tool is opt-in and never auto-runs.",
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"synapseclient", "Synapse Python client"),
    (r"(syn\d{6,})", "Synapse entity: {0}"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="synapse",
        version=__version__,
        description="Sage Bionetworks Synapse data-platform provenance extractor "
                    "(.synapseConfig + synapseclient imports + synXXXXXXXX entity refs).",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_synapse_entity_info",
                handler=_handle_entity_info,
                schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Synapse entity ID, e.g. syn12345678.",
                        },
                    },
                    "required": ["entity_id"],
                    "description": "Opt-in live query of a Synapse entity's metadata via "
                                   "synapseclient using the project's .synapseConfig. "
                                   "Returns status=warning (no network call) if synapseclient "
                                   "is not installed OR no .synapseConfig is configured. "
                                   "Never auto-runs; never downloads file content.",
                },
            ),
        ),
    )
