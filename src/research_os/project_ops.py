"""Workspace scaffolding, state I/O, and shared filesystem helpers.

Conventions
-----------
* Single state file: ``.os_state/state_ledger.json`` (mirrored to
  ``.os_state/state_ledger.yaml`` for human reading).
* Append-only logs: ``workspace/methods.md``, ``analysis.md``, ``citations.md``.
* Immutable: ``inputs/raw_data/``, ``inputs/literature/``.
* All workspace writes go through MCP tools so provenance is captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - yaml is a hard dep
    yaml = None

from research_os.errors import check_write_permitted
from research_os.state.state_ledger import ResearchLedger
from research_os.utils.common import find_project_root, now_iso

EXPERIMENT_SUBDIRS = (
    "data/input",
    "data/output",
    "scripts",
    "outputs/reports",
    "outputs/figures",
    "outputs/tables",
    "outputs/dashboards",
    "environment",
)

TOP_LEVEL_DIRS = (
    ".os_state",
    "docs",
    "inputs",
    "inputs/raw_data",
    "inputs/literature",
    "inputs/context",
    "workspace",
    "workspace/logs",
    "synthesis",
    "environment",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    r = find_project_root()
    if not r:
        raise ValueError("Could not find project root containing .os_state/")
    return r


def slugify(value: str, fallback: str = "path") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def state_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.yaml"


def state_json_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.json"


def manifest_path(root: Path) -> Path:
    return root / ".os_state" / "manifest.json"


# ---------------------------------------------------------------------------
# Atomic JSON / YAML I/O
# ---------------------------------------------------------------------------


def read_yaml(path: Path) -> dict | None:
    if not yaml:
        raise RuntimeError("PyYAML is required (pip install pyyaml).")
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return None


def write_yaml(path: Path, data: dict) -> None:
    if not yaml:
        raise RuntimeError("PyYAML is required (pip install pyyaml).")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def compute_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return "error"


# ---------------------------------------------------------------------------
# State (single source of truth — ResearchLedger)
# ---------------------------------------------------------------------------


def default_state() -> dict:
    """Canonical default state. Used by ResearchLedger when no file exists."""
    return {
        "schema_version": "3.0",
        "project_id": str(uuid.uuid4()),
        "project_name": "Research Project",
        "project": "",  # legacy alias
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "phase": "init",  # legacy alias
        "pipeline_stage": "init",
        "step": 0,
        "current_path": "main",
        "checkpoints": {},
        "checkpoint_history": [],
        "active_hypotheses": [],
        "dead_ends": [],
        "loaded_data": [],
        "errors": [],
        "resumable_from": None,
        "context_transfer_memos": [],
        "linked_external_data": [],
        "paths": {
            "main": {
                "path_id": "main",
                "status": "active",
                "experiment_dir": "workspace",
                "created_at": now_iso(),
                "input_data_hashes": {},
            }
        },
    }


def load_state(root: Path | None = None) -> dict:
    root = _resolve_root(root)
    ledger = ResearchLedger(state_json_path(root))
    state = ledger._load()
    if not state or "paths" not in state:
        state = default_state()
        ledger._save(state)
    return state


def save_state(root: Path, state: dict) -> dict:
    root = _resolve_root(root)
    ledger = ResearchLedger(state_json_path(root))
    state["updated_at"] = now_iso()
    # Keep legacy + canonical fields in sync for older readers.
    if "pipeline_stage" in state:
        state.setdefault("phase", state["pipeline_stage"])
    if "project_name" in state and not state.get("project"):
        state["project"] = state["project_name"]
    ledger._save(state)
    _write_os_state_summary(root)
    return state


def _write_os_state_summary(root: Path) -> None:
    """Render ``.os_state/os_state.md`` — a human-readable status snapshot."""
    try:
        state = load_state(root)
    except Exception:
        return

    try:
        from research_os.tools.actions.path import list_paths

        paths = list_paths(root).get("paths", []) or []
    except Exception:
        paths = []

    name = state.get("project_name") or state.get("project") or "Research Project"
    stage = state.get("pipeline_stage", state.get("phase", "init"))
    current = state.get("current_path", "main")

    lines = [
        f"# OS State — {name}",
        f"*Last updated: {now_iso()}*",
        "",
        f"## Phase: `{stage}`",
        f"## Active path: `{current}`",
        "",
        "## Experiment paths",
    ]
    if not paths:
        lines.append("- (none yet)")
    for p in paths:
        icon = {
            "completed": "✅",
            "active": "🔄",
            "dead_end": "❌",
        }.get(p.get("status", "active"), "•")
        lines.append(f"- {icon} `{p.get('path_id')}` — {p.get('status')}")

    lines.extend(["", "## Key files"])
    for f in [
        "inputs/intake.md",
        "docs/research_question.md",
        "docs/domain_summary.md",
        "workspace/methods.md",
        "workspace/analysis.md",
        "workspace/citations.md",
        "workspace/logs/audit_report.md",
        "synthesis/paper.md",
    ]:
        exists = (root / f).exists()
        lines.append(f"- {'✅' if exists else '⚪'} `{f}`")

    out = root / ".os_state" / "os_state.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Manifest (workspace tree snapshot)
# ---------------------------------------------------------------------------


def _update_manifest(root: Path) -> None:
    """Sync ``.os_state/manifest.json`` with the current workspace tree."""
    workspace = root / "workspace"
    paths_info: dict[str, Any] = {}
    if workspace.exists():
        for p in sorted(workspace.iterdir()):
            if p.is_dir() and re.match(r"^\d{2,3}_", p.name):
                scripts: list[str] = []
                scripts_dir = p / "scripts"
                if scripts_dir.exists():
                    scripts = [f.name for f in sorted(scripts_dir.iterdir()) if f.is_file()]
                paths_info[p.name] = {
                    "status": "dead_end" if "__DEAD_END" in p.name else "active",
                    "has_readme": (p / "README.md").exists(),
                    "has_conclusions": (p / "conclusions.md").exists(),
                    "scripts": scripts,
                }
    manifest = read_json(manifest_path(root), {})
    manifest["paths"] = paths_info
    manifest["updated_at"] = now_iso()
    write_json(manifest_path(root), manifest)


# ---------------------------------------------------------------------------
# Hashing of input files
# ---------------------------------------------------------------------------


def compute_input_hashes(root: Path | None = None) -> dict[str, str]:
    root = _resolve_root(root)
    hashes: dict[str, str] = {}
    for base in (root / "inputs" / "raw_data", root / "inputs" / "literature", root / "inputs" / "context"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path.name not in {"README.md", ".gitkeep"}
            ):
                hashes[path.relative_to(root).as_posix()] = compute_file_hash(path)
    return hashes


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def write_readme(path: Path, title: str, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {title}\n\n{body.strip()}\n")


def scaffold_minimal_workspace(
    root: Path,
    project_name: str,
    config_overrides: dict | None = None,
    git_init: bool = False,
    ide_flags: list[str] | None = None,
    copy_agents: bool = True,
) -> None:
    """Create the workspace directory tree.

    Philosophy: scaffold creates ONLY the directories + the bare minimum files
    the AI / researcher need before the first session boot. We do NOT
    pre-create synthesis outputs (paper.md, abstract.md), per-experiment
    folders, or pre-filled docs. Those get written by the protocols that own
    them, when (and only when) they're needed.
    """
    config_overrides = config_overrides or {}
    ide_flags = ide_flags or list(("cursor", "claude", "antigravity", "opencode", "vscode"))
    root.mkdir(parents=True, exist_ok=True)

    # 1. Directory skeleton + .gitkeep so empty dirs survive git.
    for rel in TOP_LEVEL_DIRS:
        d = root / rel
        d.mkdir(parents=True, exist_ok=True)
        if not any(d.iterdir()):
            (d / ".gitkeep").touch()

    # 2. docs/glossary.md — empty table (the AI fills it).
    glossary = root / "docs" / "glossary.md"
    if not glossary.exists():
        glossary.write_text(
            "# Glossary\n\n| Term | Definition | Source |\n|---|---|---|\n"
        )

    # 3. docs/research_question.md — placeholder; intake autofill replaces it.
    rq = root / "docs" / "research_question.md"
    if not rq.exists():
        rq.write_text(
            "# Research Question\n\n"
            "*(blank — say to the AI 'fill out the intake' to populate from inputs/)*\n"
        )

    # 4. Append-only workspace logs — start EMPTY but with a header so the
    #    AI knows the file is initialised.
    for fname, header in [
        ("methods.md", "# Methods Log\n\n*Append-only via `mem_methods_append`.*\n"),
        ("analysis.md", "# Analysis Log\n\n*Append-only via `mem_analysis_log`.*\n"),
        ("citations.md", "# Citations\n\n*Auto-populated by `mem_citations_generate`.*\n"),
    ]:
        p = root / "workspace" / fname
        if not p.exists():
            p.write_text(header)

    # 5. workflow.mermaid — minimal diagram; expanded by _update_workflow_mermaid.
    wf = root / "workspace" / "workflow.mermaid"
    if not wf.exists():
        wf.write_text(
            "graph TD\n"
            "    init[Initialised]:::complete\n"
            "    classDef complete fill:#d4edda,stroke:#28a745\n"
        )

    # 6. researcher_config.yaml — source of truth for AI behaviour.
    from research_os.tools.actions.config import init_config

    init_config(root, overrides=config_overrides)

    # 7. .os_state symlink inside workspace/ for scripts that resolve relative.
    workspace_os_state = root / "workspace" / ".os_state"
    if not workspace_os_state.exists():
        try:
            workspace_os_state.symlink_to(root / ".os_state", target_is_directory=True)
        except OSError:
            pass

    # 8. inputs/intake.md — tiny placeholder; tool_intake_autofill rewrites it.
    intake = root / "inputs" / "intake.md"
    if not intake.exists():
        intake.write_text(
            "# Research Intake\n\n"
            "*(blank — drop your data/PDFs/notes into `inputs/`, then ask the AI to "
            "`fill out the intake`. It will run `tool_intake_autofill`.)*\n"
        )

    # 9. Manifest + state.
    manifest = {
        "schema_version": "2.0",
        "project": {"title": project_name},
        "created_at": now_iso(),
        "top_level_directories": list(TOP_LEVEL_DIRS),
        "active_path": "main",
        "paths": {"main": {"status": "active"}},
    }
    write_json(manifest_path(root), manifest)

    state = default_state()
    state["project_name"] = project_name
    state["project"] = project_name
    state["paths"]["main"]["input_data_hashes"] = compute_input_hashes(root)
    save_state(root, state)

    regenerate_intake(root, project_name, config_overrides)
    _copy_agents_md(root, copy_agents)
    _setup_mcp_configs(root, ide_flags)
    _setup_gitignore(root)
    _update_manifest(root)
    if git_init and not (root / ".git").exists():
        try:
            subprocess.run(["git", "init"], cwd=root, capture_output=True)
        except Exception:
            pass


def _copy_agents_md(root: Path, copy: bool) -> None:
    if not copy:
        return
    dest = root / "AGENTS.md"
    if dest.exists():
        return
    src = Path(__file__).resolve().parent.parent.parent / "templates" / "AGENTS.md"
    if src.exists():
        shutil.copy2(src, dest)


def _setup_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    if gi.exists():
        return
    gi.write_text(
        "# Research OS\n"
        "__pycache__/\n*.pyc\n*.pyo\n*.egg-info/\n"
        ".venv/\nvenv/\nenv/\n"
        ".DS_Store\n\n"
        ".os_state/cache/\n.os_state/checkpoints/\n.os_state/handoffs/\n\n"
        "# Secrets / machine-specific\n"
        "inputs/researcher_config.yaml\n"
        "inputs/literature_index.yaml\n"
        "inputs/raw_data/\n"
    )


def _setup_mcp_configs(root: Path, ide_flags: list[str]) -> None:
    """Drop a per-IDE MCP config + rule file so the AI auto-connects."""
    mcp_entry = {
        "command": "research-os",
        "args": ["start"],
        "env": {"RESEARCH_OS_WORKSPACE": str(root.resolve())},
    }
    templates_dir = Path(__file__).resolve().parent.parent.parent / "templates"

    def _copy_rule(src_rel: str, dest: Path) -> None:
        src = templates_dir / src_rel
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)

    if "cursor" in ide_flags:
        d = root / ".cursor"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".cursor/rules/research-os.mdc", d / "rules" / "research-os.mdc")

    if "claude" in ide_flags:
        d = root / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".claude/rules/research-os.md", d / "rules" / "research-os.md")
        _copy_rule(".claude/commands/start-session.md", d / "commands" / "start-session.md")

    if "antigravity" in ide_flags:
        d = root / ".antigravity"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".antigravity/rules/research-os.md", d / "rules" / "research-os.md")

    if "opencode" in ide_flags:
        f = root / "opencode.json"
        if not f.exists():
            f.write_text(
                json.dumps(
                    {
                        "mcp": {"research-os": mcp_entry},
                        "system_prompt": "Read AGENTS.md at the project root before any research request.",
                    },
                    indent=2,
                )
                + "\n"
            )

    if "vscode" in ide_flags:
        d = root / ".vscode"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Intake + literature index
# ---------------------------------------------------------------------------


def regenerate_intake(
    root: Path, project_name: str | None = None, config_overrides: dict | None = None
) -> str:
    """Rewrite ``inputs/intake.md`` with current file hashes + config."""
    config_overrides = config_overrides or {}
    try:
        state = load_state(root)
        project_name = project_name or state.get("project_name") or state.get("project") or "Research Project"
    except Exception:
        project_name = project_name or "Research Project"

    config_path = root / "inputs" / "researcher_config.yaml"
    domain = config_overrides.get("domain", "")
    research_question = config_overrides.get("research_question", "")
    keywords: list[str] = list(config_overrides.get("keywords", []) or [])

    if config_path.exists() and yaml:
        try:
            cfg = yaml.safe_load(config_path.read_text()) or {}
            domain = config_overrides.get("domain") or cfg.get("domain") or ""
            research_question = (
                config_overrides.get("research_question") or cfg.get("research_question") or ""
            )
            hints = (cfg.get("domain_hints") or {}).get("expected_columns") or []
            if hints and not keywords:
                keywords = hints
        except Exception:
            pass

    input_files: list[dict[str, Any]] = []
    for subdir in ("raw_data", "literature", "context"):
        d = root / "inputs" / subdir
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name.startswith(".") or f.name in {".gitkeep"}:
                continue
            input_files.append(
                {
                    "path": f.relative_to(root).as_posix(),
                    "sha256": compute_file_hash(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                }
            )

    lines = [
        f"# {project_name} — Research Intake",
        f"*Auto-generated: {now_iso()}*",
        "",
        "## Project",
        f"- Title: {project_name}",
        f"- Domain: {domain or '(not yet classified — domain_analysis will set this)'}",
        f"- Research question: {research_question or '(to be confirmed in project_startup)'}",
        f"- Keywords: {', '.join(keywords) if keywords else '(none)'}",
        "",
        "## Input files",
    ]
    if input_files:
        lines.extend(["", "| File | SHA-256 | Size |", "|---|---|---|"])
        for f in input_files:
            lines.append(
                f"| {f['path']} | `{f['sha256'][:12]}…` | {f['size_kb']:.1f} KB |"
            )
    else:
        lines.append("- (no inputs yet — drop files into `inputs/raw_data/` or `inputs/literature/`)")
    lines.append("")

    intake_path = root / "inputs" / "intake.md"
    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text("\n".join(lines) + "\n")
    return str(intake_path.absolute())


def update_literature_index(root: Path) -> dict:
    """Refresh ``inputs/literature_index.yaml`` from PDFs in ``inputs/literature/``."""
    lit_dir = root / "inputs" / "literature"
    index_path = root / "inputs" / "literature_index.yaml"

    index: dict = {"schema_version": "1.0", "last_updated": now_iso(), "entries": {}}
    if index_path.exists() and yaml:
        try:
            existing = yaml.safe_load(index_path.read_text()) or {}
            index["entries"] = existing.get("entries", {})
        except Exception:
            pass

    if lit_dir.exists():
        for f in sorted(lit_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in {".pdf", ".epub", ".ps", ".djvu"}:
                continue
            citation_key = re.sub(r"[\s-]+", "_", f.stem).lower()
            sha = compute_file_hash(f)
            entry = index["entries"].get(f.name, {})
            entry.update(
                {
                    "citation_key": citation_key,
                    "sha256": sha,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "verified": entry.get("verified", False),
                }
            )
            index["entries"][f.name] = entry

    if yaml:
        index_path.write_text(yaml.safe_dump(index, sort_keys=False))
    else:
        index_path.write_text(json.dumps(index, indent=2) + "\n")
    return index


# ---------------------------------------------------------------------------
# Numbered experiment creation
# ---------------------------------------------------------------------------


def _prune_old_checkpoints(root: Path, keep: int = 5) -> None:
    ckpt_dir = root / ".os_state" / "checkpoints"
    if not ckpt_dir.exists():
        return
    meta_files = sorted(ckpt_dir.glob("*.meta.json"), key=lambda f: f.stat().st_mtime)
    for meta in meta_files[: max(0, len(meta_files) - keep)]:
        try:
            data = json.loads(meta.read_text())
            cid = data.get("checkpoint_id")
        except Exception:
            cid = meta.stem
        meta.unlink(missing_ok=True)
        snapshot_dir = ckpt_dir / cid if cid else None
        if snapshot_dir and snapshot_dir.exists():
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def create_numbered_experiment(
    root: Path,
    name: str,
    hypothesis: str = "",
    from_step: str | None = None,
) -> dict:
    """Create the next numbered experiment folder + wire up its data link."""
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    max_num = 0
    for p in workspace.iterdir():
        if p.is_dir() and re.match(r"^\d{2,3}_", p.name):
            try:
                max_num = max(max_num, int(p.name.split("_", 1)[0]))
            except ValueError:
                pass
    next_num = max_num + 1
    slug = slugify(name, "experiment")
    branch_id = f"{next_num:02d}_{slug}"
    exp_dir = workspace / branch_id

    if exp_dir.exists():
        raise ValueError(f"Experiment '{branch_id}' already exists at {exp_dir}")

    check_write_permitted(exp_dir)

    if from_step:
        src_dir = workspace / from_step
        if not src_dir.exists():
            raise ValueError(f"Source step '{from_step}' not found")
        shutil.copytree(src_dir, exp_dir, symlinks=True, dirs_exist_ok=True)
    else:
        exp_dir.mkdir(parents=True, exist_ok=True)
        for sub in EXPERIMENT_SUBDIRS:
            (exp_dir / sub).mkdir(parents=True, exist_ok=True)

        # Wire data/input/
        data_input = exp_dir / "data" / "input"
        if next_num == 1:
            raw_dir = root / "inputs" / "raw_data"
            raw_dir.mkdir(parents=True, exist_ok=True)
            try:
                data_input.rmdir()
                data_input.symlink_to(raw_dir.absolute())
            except OSError:
                pass
        else:
            prev_num = next_num - 1
            prev_dirs = sorted(
                p for p in workspace.iterdir()
                if p.is_dir() and re.match(rf"^{prev_num:02d}_", p.name)
            )
            if prev_dirs:
                prev_output = prev_dirs[0] / "data" / "output"
                prev_output.mkdir(parents=True, exist_ok=True)
                try:
                    data_input.rmdir()
                    data_input.symlink_to(prev_output.absolute())
                except OSError:
                    pass

    # README + conclusions stubs
    (exp_dir / "README.md").write_text(
        f"# Experiment: {branch_id}\n*Created: {now_iso()}*\n\n"
        f"## Goal\n{hypothesis or name}\n\n"
        "## Input data\n- *(list inputs used)*\n\n"
        "## Methods\n- *(list methods/models)*\n\n"
        "## Outputs\n- *(describe expected outputs)*\n\n"
        "## Decision\n- *(proceed | branch | dead-end)*\n"
    )
    (exp_dir / "conclusions.md").write_text(
        f"# {branch_id} — Conclusions\n*Created: {now_iso()}*\n\n"
        "## Findings\n*(populate after analysis)*\n\n"
        "## Limitations\n*(assumption tests + their result)*\n\n"
        "## Decision\n*(proceed | branch | dead-end)*\n\n"
        "## Next steps\n*(2-3 candidates with rationale)*\n"
    )

    # State update
    state = load_state(root)
    state["paths"][branch_id] = {
        "path_id": branch_id,
        "experiment_number": next_num,
        "status": "active",
        "hypothesis": hypothesis or name,
        "experiment_dir": f"workspace/{branch_id}",
        "created_at": now_iso(),
    }
    state["current_path"] = branch_id
    state["step"] = next_num
    if state.get("pipeline_stage") in (None, "init", "planned"):
        state["pipeline_stage"] = "execution"
    save_state(root, state)
    _update_manifest(root)
    _update_workflow_mermaid(root)
    _prune_old_checkpoints(root, keep=5)

    return {
        "path_id": branch_id,
        "experiment_number": next_num,
        "experiment_dir": str(exp_dir.absolute()),
        "from_step": from_step,
        "paths_created": [str(exp_dir / sub) for sub in EXPERIMENT_SUBDIRS],
    }


# ---------------------------------------------------------------------------
# Workflow diagram + analysis.md helpers
# ---------------------------------------------------------------------------


def log_decision(
    context: str,
    selected: str,
    rationale: str,
    *,
    options_considered: list[str] | None = None,
    linked_literature: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Append a methodological decision to workspace/analysis.md."""
    root = _resolve_root(root)
    analysis_path = root / "workspace" / "analysis.md"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = (
        f"\n\n### Decision · {ts}\n"
        f"- **Context**: {context}\n"
        f"- **Selected**: {selected}\n"
        f"- **Rationale**: {rationale}\n"
    )
    if options_considered:
        entry += f"- **Options considered**: {', '.join(options_considered)}\n"
    if linked_literature:
        entry += f"- **Linked literature**: {', '.join(linked_literature)}\n"
    with open(analysis_path, "a") as f:
        f.write(entry)
    return {"logged": True, "path": "workspace/analysis.md"}


def _update_analysis_mermaid_block(root: Path, mermaid_content: str) -> None:
    analysis_path = root / "workspace" / "analysis.md"
    if not analysis_path.exists():
        return
    content = analysis_path.read_text()
    start = content.find("```mermaid")
    if start == -1:
        return
    end = content.find("```", start + 10)
    if end == -1:
        return
    end += 3
    new_block = f"```mermaid\n{mermaid_content}\n```"
    analysis_path.write_text(content[:start] + new_block + content[end:])


def _update_workflow_mermaid(root: Path) -> None:
    """Regenerate workspace/workflow.mermaid + analysis.md block + (optional) PNG."""
    try:
        from research_os.tools.actions.path import list_paths

        paths = list_paths(root).get("paths", []) or []
    except Exception:
        paths = []

    lines = ["graph TD", "    init[Initialise Project]:::complete"]
    for p in paths:
        pid = re.sub(r"[^a-zA-Z0-9_]", "_", p["path_id"])
        label = p.get("name") or p["path_id"]
        status = p.get("status", "active")
        css = {"completed": "complete", "active": "running", "dead_end": "failed"}.get(status, "planned")
        lines.append(f"    {pid}[{label}]:::{css}")
        lines.append(f"    init --> {pid}")
    lines.extend(
        [
            "    classDef complete fill:#d4edda,stroke:#28a745",
            "    classDef running  fill:#fff3cd,stroke:#ffc107",
            "    classDef failed   fill:#f8d7da,stroke:#dc3545,stroke-dasharray: 5 5",
            "    classDef planned  fill:#e2e3e5,stroke:#6c757d",
        ]
    )
    text = "\n".join(lines)
    mermaid_path = root / "workspace" / "workflow.mermaid"
    mermaid_path.write_text(text + "\n")
    _update_analysis_mermaid_block(root, text)

    mmdc = shutil.which("mmdc")
    if mmdc:
        try:
            subprocess.run(
                [mmdc, "-i", str(mermaid_path), "-o", str(root / "workspace" / "workflow.png"), "-b", "white"],
                capture_output=True,
                timeout=60,
            )
        except Exception:
            pass


def generate_citations_md(root: Path) -> str:
    """Regenerate workspace/citations.md from inputs/literature_index.yaml."""
    citations_path = root / "workspace" / "citations.md"
    citations_path.parent.mkdir(parents=True, exist_ok=True)

    index_path = root / "inputs" / "literature_index.yaml"
    entries: dict = {}
    if index_path.exists() and yaml:
        try:
            data = yaml.safe_load(index_path.read_text()) or {}
            entries = data.get("entries", {})
        except Exception:
            pass

    lines = ["# Running Bibliography", "", "*Auto-generated from inputs/literature_index.yaml*", ""]
    if entries:
        for filename, meta in sorted(entries.items()):
            key = meta.get("citation_key", filename)
            verified = meta.get("verified", False)
            sha = (meta.get("sha256") or "")[:12]
            badge = "✅ verified" if verified else "⏳ pending verification"
            lines.append(f"### `{key}`")
            lines.append(f"- File: {filename}")
            lines.append(f"- SHA-256: `{sha}`")
            lines.append(f"- Status: {badge}")
            lines.append("")
    else:
        lines.append("*(No PDFs in `inputs/literature/` yet — drop some in or use `tool_literature_download`.)*")
        lines.append("")

    citations_path.write_text("\n".join(lines) + "\n")
    return str(citations_path.absolute())


# ---------------------------------------------------------------------------
# Diff log (unused-but-kept hook for future state-diff watchers)
# ---------------------------------------------------------------------------


def state_diff_log_path(root: Path) -> Path:
    return root / "workspace" / "logs" / "state_changes.log"
