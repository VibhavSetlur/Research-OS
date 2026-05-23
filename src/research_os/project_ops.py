"""Package-native workspace operations for clean Research OS projects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - PyYAML is a package dependency.
    yaml = None

from research_os.utils.common import find_project_root, now_iso
from research_os.state.state_ledger import ResearchLedger


def _resolve_root(root: Path | None = None) -> Path:
    r = find_project_root(root)
    if not r:
        raise ValueError("Could not find project root containing .os_state/")
    return r


def slugify(value: str, fallback: str = "path") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


# ── State ledger paths ──────────────────────────────────────────────


def state_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.yaml"


def state_json_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.json"


def manifest_path(root: Path) -> Path:
    return root / ".os_state" / "manifest.json"


def state_diff_log_path(root: Path) -> Path:
    return root / "workspace" / "logs" / "state_changes.log"


# ── YAML helpers ────────────────────────────────────────────────────


def read_yaml(path: Path) -> dict | None:
    if not yaml:
        raise RuntimeError(
            "PyYAML is required but not installed. Run: pip install pyyaml"
        )
    try:
        with open(path) as f:
            return cast(dict, yaml.safe_load(f))
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return None


def write_yaml(path: Path, data: dict) -> None:
    if not yaml:
        raise RuntimeError(
            "PyYAML is required but not installed. Run: pip install pyyaml"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(
                data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
            )
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
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


# ── State diff logging ──────────────────────────────────────────────


def _compute_state_diff(before: dict, after: dict) -> list[str]:
    """Return human-readable diff lines between two state dicts."""
    lines: list[str] = []
    before_paths = set(before.get("paths", {}).keys())
    after_paths = set(after.get("paths", {}).keys())

    added = after_paths - before_paths
    removed = before_paths - after_paths
    if before.get("current_path") != after.get("current_path"):
        lines.append(
            f"  path switch: {before.get('current_path')} → {after.get('current_path')}"
        )

    if before.get("pipeline_stage") != after.get("pipeline_stage"):
        lines.append(
            f"  stage: {before.get('pipeline_stage')} → {after.get('pipeline_stage')}"
        )

    if before.get("step") != after.get("step"):
        lines.append(f"  step: {before.get('step')} → {after.get('step')}")

    for b in added:
        s = after["paths"][b].get("status", "active")
        lines.append(f"  path +{b} ({s})")
    for b in removed:
        lines.append(f"  path -{b}")

    # checkpoint history diff
    before_cp = before.get("checkpoint_history", [])
    after_cp = after.get("checkpoint_history", [])
    new_cps = after_cp[len(before_cp) :]
    for cp in new_cps:
        lines.append(
            f"  checkpoint: {cp.get('id', '?')} = {cp.get('step', '?')} @ {cp.get('timestamp', '?')}"
        )

    return lines


def write_state_diff(root: Path, before: dict | None, after: dict) -> None:
    """Atomically append a diff entry to workspace/logs/state_changes.log."""
    if before is None:
        return
    log_path = state_diff_log_path(root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    diffs = _compute_state_diff(before, after)
    if not diffs:
        return
    entry = f"--- {ts}\n" + "\n".join(diffs) + "\n"
    with open(log_path, "a") as f:
        f.write(entry)


# ── Primary state functions ─────────────────────────────────────────


def default_state() -> dict:
    return {
        "schema_version": "2.0",  # Internal state format version (independent of package version)
        "project_id": str(uuid.uuid4()),
        "project_name": "Research Project",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "step": 0,
        "pipeline_stage": "init",
        "current_path": "main",
        "checkpoint_history": [],
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
    ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
    # _load handles default state correctly
    return ledger._load()


def save_state(root: Path, state: dict) -> dict:
    """Atomically save state using ResearchLedger, logging diff."""
    root = _resolve_root(root)
    ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
    before = ledger._load()
    state["updated_at"] = now_iso()
    ledger._save(state)
    write_state_diff(root, before, state)
    return state


def compute_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
    except (FileNotFoundError, PermissionError, OSError):
        return "error"
    return sha256.hexdigest()


def compute_input_hashes(root: Path | None = None) -> dict[str, str]:
    root = _resolve_root(root)
    hashes: dict[str, str] = {}
    for base in (
        root / "inputs" / "raw_data",
        root / "inputs" / "literature",
    ):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path.name not in {"README.md", ".gitkeep"}
            ):
                hashes[path.relative_to(root).as_posix()] = compute_file_hash(path)
    # Also hash inputs/context files
    context_dir = root / "inputs" / "context"
    if context_dir.exists():
        for path in sorted(context_dir.rglob("*")):
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path.name not in {"README.md", ".gitkeep"}
            ):
                hashes[path.relative_to(root).as_posix()] = compute_file_hash(path)
    return hashes


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
    ide: str = "all",
) -> None:
    """Create the unified workspace directory structure and .os_state config.

    Args:
        root: Target directory path.
        project_name: Display name for the project.
        config_overrides: Optional dict with keys: project_name, research_question,
                         domain, depth, provider. These populate the config.yaml
                         and intake.md.
    """
    config_overrides = config_overrides or {}
    root.mkdir(parents=True, exist_ok=True)

    # ── Publication-grade directory taxonomy (§2.1 of TODO.md) ─────
    (root / ".os_state").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    for doc_file, content in [
        (
            "research_question.md",
            f"# Research Question\n\n## Main Question\n\n*({project_name})*\n\n## Sub-Questions\n\n1. \n2. \n3. \n\n## Last Updated\n\n{now_iso()}\n",
        ),
        (
            "hypotheses.md",
            f"# Hypotheses\n\n## H1\n\n- **Statement**:\n- **Test**:\n- **Outcome**:\n\n## H2\n\n- **Statement**:\n- **Test**:\n- **Outcome**:\n\n*Auto-generated: {now_iso()}*\n",
        ),
        (
            "glossary.md",
            f"# Glossary\n\n| Term | Definition |\n|------|------------|\n| | |\n\n*Auto-generated: {now_iso()}*\n",
        ),
    ]:
        p = root / "docs" / doc_file
        if not p.exists():
            p.write_text(content)
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "raw_data").mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "literature").mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "context").mkdir(parents=True, exist_ok=True)

    directories = {
        "workspace": "Active experimentation area — iterative research lives here",
        "workspace/logs": "Execution logs and provenance records",
        "synthesis": "Final consolidated outputs — paper, abstract, bibliography",
        "environment": "Reproducible environments (requirements.txt, Dockerfile)",
    }
    for rel, body in directories.items():
        write_readme(root / rel, Path(rel).name.replace("_", " ").title(), body or "")

    # Initialize workspace state files with structured headers (§2.3)
    methods_path = root / "workspace" / "methods.md"
    if not methods_path.exists():
        methods_path.write_text(
            f"# Methods Log\n\n"
            f"*Append-only record of every method used.*\n\n"
            f"## {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"- **Init**: Workspace initialized\n\n"
        )

    analysis_path = root / "workspace" / "analysis.md"
    if not analysis_path.exists():
        analysis_path.write_text(
            f"# Analysis Log\n\n"
            f"*Chronological workflow log.*\n\n"
            f"```mermaid\n"
            f"graph TD\n"
            f"    init[Initialized]:::complete\n"
            f"    classDef complete fill:#d4edda,stroke:#28a745\n"
            f"```\n\n"
            f"[{now_iso()}] init: Workspace scaffolded\n\n"
        )

    citations_path = root / "workspace" / "citations.md"
    if not citations_path.exists():
        citations_path.write_text(
            "# Running Bibliography\n\n"
            "*Each entry has a `verified` flag for the citation_verifier.*\n\n"
        )

    # ── Auto-generate researcher_config.yaml via init_config ──
    from research_os.tools.actions.config import init_config
    init_config(root)

    # Symlink .os_state into workspace for easier access by scripts
    workspace_os_state = root / "workspace" / ".os_state"
    if not workspace_os_state.exists():
        try:
            workspace_os_state.symlink_to(root / ".os_state", target_is_directory=True)
        except OSError:
            pass  # Handle OS limitations (e.g. Windows without admin rights)

    intake = root / "inputs" / "intake.md"
    if not intake.exists():
        rq = config_overrides.get("research_question", "")
        domain = config_overrides.get("domain", "general")
        depth = config_overrides.get("depth", "academic")
        intake.write_text(
            f"# {project_name} — Research Intake\n\n"
            "## Project\n\n"
            f"- Title: {project_name}\n"
            f"- Domain: {domain}\n"
            f"- Depth: {depth}\n\n"
            "## Research Question\n\n"
            f"{rq if rq else '(Set your research question in inputs/researcher_config.yaml)'}\n\n"
            "## Input Files\n\n"
            "- Place raw data in `inputs/raw_data/`\n"
            "- Place literature PDFs in `inputs/literature/`\n"
            "- Place context notes in `inputs/context/`\n\n"
            "## Auto-generated\n"
            f"- Date: {datetime.now(timezone.utc).date().isoformat()}\n"
        )

    # ── Initialize workflow.mermaid ──
    workflow_mermaid = root / "workspace" / "workflow.mermaid"
    if not workflow_mermaid.exists():
        workflow_mermaid.write_text(
            "graph TD\n"
            "    init[Initialize Project]:::complete\n"
            "    classDef complete fill:#d4edda,stroke:#28a745\n"
        )



    manifest = {
        "schema_version": "1.0",
        "project": {"title": project_name},
        "created_at": now_iso(),
        "architecture": "unified_workspace",
        "top_level_directories": ["workspace", ".os_state"],
        "active_path": "main",
        "paths": {"main": {"status": "active"}},
    }
    write_json(manifest_path(root), manifest)

    state = default_state()
    state["paths"]["main"]["input_data_hashes"] = compute_input_hashes(root)
    state["project_name"] = project_name
    save_state(root, state)

    # Regenerate intake with current file hashes
    regenerate_intake(root, project_name, config_overrides)

    _copy_environment_to_project(root)
    _copy_agents_md(root)
    _setup_mcp_configs(root, ide)
    _setup_gitignore(root)
    if git_init:
        _initialize_git(root)


def _initialize_git(root: Path) -> None:
    import subprocess

    if not (root / ".git").exists():
        try:
            subprocess.run(["git", "init"], cwd=root, capture_output=True)
        except Exception:
            pass


def _copy_agents_md(root: Path) -> None:
    """Copy AGENTS.md template to project root."""
    dest = root / "AGENTS.md"
    if dest.exists():
        return
    
    # Try to find it in the repository structure if running from source
    try:
        src_path = Path(__file__).resolve().parent.parent.parent / "templates" / "AGENTS.md"
        if src_path.exists():
            import shutil
            shutil.copy2(src_path, dest)
            return
    except Exception:
        pass

    # Try looking in package assets if packaged
    try:
        try:
            import importlib.resources as importlib_resources
        except ImportError:
            import importlib_resources  # type: ignore[no-redef]
        
        asset_path = importlib_resources.files("research_os.assets") / "AGENTS.md"
        if asset_path.exists(): # type: ignore
            dest.write_text(asset_path.read_text(encoding="utf-8"), encoding="utf-8") # type: ignore
    except Exception:
        pass


def _setup_gitignore(root: Path) -> None:
    """Generate default .gitignore for the research project."""
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# Research OS — Git Ignore Rules\n\n"
            "# Python\n"
            "__pycache__/\n"
            "*.pyc\n"
            "*.pyo\n"
            "*.pyd\n"
            "*.egg-info/\n"
            ".venv/\n"
            "venv/\n"
            "env/\n"
            "environment/venv/\n\n"
            "# System\n"
            ".DS_Store\n\n"
            "# Research OS Runtime Cache\n"
            ".os_state/cache/\n"
            ".os_state/checkpoints/\n"
            "# Researcher config (contains API keys)\n"
            "inputs/researcher_config.yaml\n"
        )


def _setup_mcp_configs(root: Path, ide: str = "all") -> None:
    """Generate default MCP configuration for popular AI IDEs."""
    import sys as _sys

    mcp_entry = {
        "command": _sys.executable,
        "args": ["-m", "research_os.server", "--transport", "stdio"],
    }

    ide = ide.lower()

    # Cursor
    if ide in ("all", "cursor"):
        cursor_dir = root / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_mcp = cursor_dir / "mcp.json"
        if not cursor_mcp.exists():
            cursor_mcp.write_text(
                json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n"
            )

    # Claude Desktop
    if ide in ("all", "claude"):
        claude_dir = root / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        claude_mcp = claude_dir / "mcp.json"
        if not claude_mcp.exists():
            try:
                claude_mcp.write_text(
                    json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n"
                )
            except Exception:
                pass

    # OpenCode
    if ide in ("all", "opencode"):
        opencode_json = root / "opencode.json"
        if not opencode_json.exists():
            opencode_json.write_text(
                json.dumps({"mcp": {"research-os": mcp_entry}}, indent=2) + "\n"
            )

    # VS Code OS
    if ide in ("all", "vscode"):
        vscode_dir = root / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_mcp = vscode_dir / "mcp.json"
    if not vscode_mcp.exists():
        vscode_mcp.write_text(
            json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n"
        )


def _copy_environment_to_project(root: Path) -> None:
    """Copy environment configuration files from package assets to the project."""
    try:
        import importlib.resources as importlib_resources
    except ImportError:
        import importlib_resources  # type: ignore[no-redef]

    env_dir = root / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)

    try:
        env_assets = importlib_resources.files("research_os.assets.environment")
        if not list(env_assets.iterdir()):
            print("assets/environment directory is empty or missing. Skipping environment copy.")
            return
    except Exception as e:
        print(f"assets/environment directory is missing. Skipping environment copy: {e}")
        return

    files = [
        "setup.sh",
        "setup_conda.sh",
        "requirements.txt",
        "README.md",
        "Dockerfile",
    ]
    for filename in files:
        try:
            asset_path = env_assets / filename
            dest = env_dir / filename
            if not dest.exists():
                dest.write_text(
                    asset_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
        except Exception:
            pass


def _update_workspace_readme_manifest(root: Path) -> None:
    readme_path = root / "workspace" / "README.md"

    # Gather numbered experiment paths
    import re
    experiment_dirs = sorted(
        p for p in (root / "workspace").iterdir()
        if p.is_dir() and re.match(r"^\d{2}_", p.name)
    )

    lines = [
        "# Workspace Manifest",
        "",
        "This directory is actively managed by Research OS.",
        "",
    ]
    if experiment_dirs:
        lines.append("## Experiment Paths")
        for exp_dir in experiment_dirs:
            lines.append(f"- `{exp_dir.name}/`")
        lines.append("")

    readme_path.write_text("\n".join(lines) + "\n")


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
        f"\n\n### Decision\n"
        f"- **Date**: {ts}\n"
        f"- **Context**: {context}\n"
        f"- **Selected**: {selected}\n"
        f"- **Rationale**: {rationale}\n"
    )
    if options_considered:
        entry += f"- **Options Considered**: {', '.join(options_considered)}\n"
    if linked_literature:
        entry += f"- **Linked Literature**: {', '.join(linked_literature)}\n"

    with open(analysis_path, "a") as f:
        f.write(entry)

    return {"logged": True, "path": "workspace/analysis.md"}


def save_artifact(
    filename: str,
    content: str,
    *,
    artifact_type: str = "artifact",
    generated_by: str = "mcp",
    source_script: str = "",
    input_files: list[str] | None = None,
    decisions_applied: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Save a text artifact with required sibling provenance metadata."""
    root = _resolve_root(root)
    from research_os.state import ResearchLedger
    ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
    active_step = ledger.get_current_path()
    
    if active_step:
        folder = {
            "figure": f"{active_step}/outputs/figures",
            "table": f"{active_step}/outputs/tables",
            "analysis": f"{active_step}/data",
            "artifact": f"{active_step}/data",
        }.get(artifact_type, f"{active_step}/data")
    else:
        folder = {
            "figure": "outputs/figures",
            "table": "outputs/tables",
            "analysis": "data",
            "artifact": "data",
        }.get(artifact_type, "data")

    safe_name = Path(filename).name
    output_path = root / "workspace" / folder / safe_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    # Update README
    _update_workspace_readme_manifest(root)

    input_files = input_files or []
    data_hashes = {}
    for item in input_files:
        path = root / item if not Path(item).is_absolute() else Path(item)
        if path.exists() and path.is_file():
            data_hashes[item] = compute_file_hash(path)

    script_hash = ""
    if source_script:
        script_path = (
            root / source_script
            if not Path(source_script).is_absolute()
            else Path(source_script)
        )
        if script_path.exists():
            script_hash = compute_file_hash(script_path)

    meta = {
        "generated_by": generated_by,
        "timestamp": now_iso(),
        "source_script": source_script,
        "script_hash": script_hash,
        "data_hashes": data_hashes,
        "decisions_applied": decisions_applied or [],
    }
    meta_path = output_path.with_name(f"{output_path.stem}.meta.yaml")
    if yaml is not None:
        meta_path.write_text(yaml.safe_dump(meta, sort_keys=False))
    else:
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    return {
        "artifact": output_path.relative_to(root).as_posix(),
        "metadata": meta_path.relative_to(root).as_posix(),
    }


def _yaml_mapping(values: dict, indent: int = 0) -> str:
    prefix = " " * indent
    if not values:
        return f"{prefix}{{}}\n"
    return "".join(f'{prefix}"{k}": "{v}"\n' for k, v in values.items())


# ------------------------------------------------------------------
# §2.2 — intake.md auto-regeneration (with SHA-256 hashes)
# ------------------------------------------------------------------


def regenerate_intake(
    root: Path, project_name: str | None = None, config_overrides: dict | None = None
) -> str:
    """Regenerate inputs/intake.md with current file hashes, domain, depth, and keywords.

    Call this after init and after every major research prompt.
    Returns the path to the written file as a string.
    """
    config_overrides = config_overrides or {}
    state = load_state(root)
    project_name = project_name or state.get("project_name", "Research OS Project")

    # Determine domain and depth from config
    config_path = root / "inputs" / "researcher_config.yaml"
    domain = config_overrides.get("domain", "general")
    depth = config_overrides.get("depth", "academic")
    if config_path.exists() and yaml:
        try:
            cfg = yaml.safe_load(config_path.read_text()) or {}
            domain = config_overrides.get("domain", cfg.get("domain", "general"))
            depth = config_overrides.get("depth", cfg.get("default_depth", "academic"))
        except Exception:
            pass

    # Scan input files
    input_files = []
    for subdir in ("raw_data", "literature", "context"):
        d = root / "inputs" / subdir
        if d.exists():
            for f in sorted(d.rglob("*")):
                if (
                    f.is_file()
                    and not f.name.startswith(".")
                    and f.name not in (".gitkeep",)
                ):
                    sha = compute_file_hash(f)
                    rel = f.relative_to(root).as_posix()
                    input_files.append(
                        {"path": rel, "sha256": sha, "size_kb": f.stat().st_size / 1024}
                    )

    # Write intake.md
    intake_path = root / "inputs" / "intake.md"
    lines = [
        f"# {project_name} — Research Intake",
        "",
        f"*Auto-generated: {now_iso()}*",
        "",
        "## Project",
        "",
        f"- Title: {project_name}",
        f"- Domain: {domain}",
        f"- Depth: {depth}",
        "",
        "## Research Question",
        "",
        f"{config_overrides.get('research_question', '(Set in inputs/researcher_config.yaml)')}",
        "",
        "## Keywords",
        "",
        f"{', '.join(config_overrides.get('keywords', []))}",
        "",
        "## Input Files",
        "",
    ]
    if input_files:
        lines.append("| File | SHA-256 | Size |")
        lines.append("|------|---------|------|")
        for f in input_files:
            lines.append(
                f"| {f['path']} | `{f['sha256'][:12]}...` | {f['size_kb']:.1f} KB |"
            )
    else:
        lines.append("*(No input files found. Place data in `inputs/raw_data/`.)*")
    lines.append("")

    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text("\n".join(lines) + "\n")
    return str(intake_path.absolute())


# ------------------------------------------------------------------
# §2.2 — literature_index.yaml sidecar
# ------------------------------------------------------------------


def update_literature_index(root: Path) -> dict:
    """Scan inputs/literature/ and build/refresh literature_index.yaml.

    Each PDF in inputs/literature/ gets a sidecar entry mapping
    filename → citation key (auto-generated from stem).

    Returns the index dict.
    """
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
            if f.is_file() and f.suffix.lower() in (".pdf", ".epub", ".ps", ".djvu"):
                name = f.name
                citation_key = (
                    f.stem.replace(" ", "_")
                    .replace("-", "_")
                    .replace("__", "_")
                    .lower()
                )
                sha = compute_file_hash(f)
                if name not in index["entries"]:
                    index["entries"][name] = {
                        "citation_key": citation_key,
                        "sha256": sha,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "verified": False,
                    }
                else:
                    index["entries"][name]["sha256"] = sha

    if yaml:
        index_path.write_text(yaml.safe_dump(index, sort_keys=False))
    else:
        index_path.write_text(json.dumps(index, indent=2) + "\n")

    return index


# ------------------------------------------------------------------
# §2.3 — Numbered experiment folder creation with README.md
# ------------------------------------------------------------------

EXPERIMENT_SUBDIRS = [
    "data",
    "scripts",
    "outputs/reports",
    "outputs/figures",
    "outputs/tables",
    "outputs/dashboards",
    "environment",
]


def create_numbered_experiment(
    root: Path,
    name: str,
    hypothesis: str = "",
    parent: str | None = None,
    from_step: str | None = None,
) -> dict:
    """Create a numbered experiment folder under workspace/ with full subdirectory tree.

    Creates:
      workspace/01_<name>/
        README.md       (goal, methods, expected/actual outcomes)
        data/
        scripts/
        outputs/
          reports/
          figures/
          dashboards/
        .meta/
        conclusions.md

    Args:
        root: Project root.
        name: Short slug for the experiment (e.g. 'baseline', 'causal_model').
        hypothesis: Research hypothesis for this branch.
        parent: Parent branch name.
        from_step: Copy contents from an existing step folder (e.g. '01_exploration').

    Returns:
        Dict with branch_id, experiment_dir, and paths created.
    """
    import shutil
    from research_os.errors import check_write_permitted

    state = load_state(root)

    # Determine next number
    workspace_dir = root / "workspace"
    max_num = 0
    if workspace_dir.exists():
        for p in workspace_dir.iterdir():
            if p.is_dir() and re.match(r"^\d{2}_", p.name):
                try:
                    num = int(p.name[:2])
                    max_num = max(max_num, num)
                except ValueError:
                    pass

    next_num = max_num + 1
    slug = (
        re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_") or "experiment"
    )
    branch_id = f"{next_num:02d}_{slug}"
    experiment_dir = workspace_dir / branch_id

    if experiment_dir.exists():
        raise ValueError(
            f"Experiment folder '{branch_id}' already exists at {experiment_dir}"
        )

    # Optionally copy from a source step
    if from_step:
        src_dir = workspace_dir / from_step
        if not src_dir.exists():
            raise ValueError(f"Source step '{from_step}' not found at {src_dir}")
        check_write_permitted(experiment_dir)
        shutil.copytree(src_dir, experiment_dir, symlinks=True, dirs_exist_ok=True)
        paths_created = [str(src_dir.absolute()), str(experiment_dir.absolute())]
        paths_created += [
            str(p.absolute()) for p in experiment_dir.rglob("*") if p.is_dir()
        ]
    else:
        # Create fresh subdirectory tree
        check_write_permitted(experiment_dir)
        experiment_dir.mkdir(parents=True, exist_ok=True)
        for sub in EXPERIMENT_SUBDIRS:
            d = experiment_dir / sub
            d.mkdir(parents=True, exist_ok=True)
        paths_created = [str(experiment_dir.absolute())]

    status = state.get("pipeline_stage", "planned")
    if status == "init":
        status = "planned"

    # Write conclusions.md
    conclusions = experiment_dir / "conclusions.md"
    conclusions.write_text(
        f"# {branch_id} — Conclusions\n\n"
        f"*Created: {now_iso()}*\n\n"
        "## Summary\n\n"
        "*(Summarize key findings here after analysis.)*\n\n"
        "## Next Steps\n\n"
        "*(Describe what to do next — proceed, branch, or dead-end.)*\n"
    )

    # Write README.md
    readme = experiment_dir / "README.md"
    readme.write_text(
        f"# Experiment: {branch_id}\n\n"
        f"*Created: {now_iso()}*\n\n"
        "## Goal\n\n"
        f"{hypothesis or name}\n\n"
        "## Input Data\n\n"
        "- *(List input files used)*\n\n"
        "## Methods Used\n\n"
        "- *(List statistical methods, transforms, models)*\n\n"
        "## Expected Output\n\n"
        "- *(Describe expected outputs)*\n\n"
        "## Actual Output\n\n"
        "- *(Describe actual results after execution)*\n\n"
        "## Next-Step Decision\n\n"
        "- *(proceed / branch / dead-end)*\n"
    )
    if not from_step:
        paths_created += [str(readme.absolute()), str(conclusions.absolute())]

    # Update state ledger
    state["paths"][branch_id] = {
        "path_id": branch_id,
        "experiment_number": next_num,
        "status": status,
        "hypothesis": hypothesis or name,
        "experiment_dir": f"workspace/{branch_id}",
        "created_at": now_iso(),
    }
    state["current_path"] = branch_id
    state["pipeline_stage"] = status
    save_state(root, state)

    return {
        "path_id": branch_id,
        "experiment_number": next_num,
        "experiment_dir": str(experiment_dir.absolute()),
        "from_step": from_step,
        "paths_created": paths_created,
    }


# ------------------------------------------------------------------
# §2.4 — synthesis helpers
# ------------------------------------------------------------------


def scaffold_synthesis(root: Path, project_name: str = "Research Project") -> dict:
    """Populate synthesis/ directory with template files.

    Creates:
      synthesis/abstract.md     -- structured 250-word abstract template
      synthesis/paper.tex       -- LaTeX skeleton (generic, not template-specific)
      synthesis/references.bib  -- empty BibTeX file
      synthesis/supplementary/  -- directory for supplementary materials

    Returns dict of paths created.
    """
    from research_os.errors import check_write_permitted

    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)
    supplementary_dir = synthesis_dir / "supplementary"
    supplementary_dir.mkdir(parents=True, exist_ok=True)

    created = []

    # workflow_diagram.png auto-generation
    import shutil

    workflow_png_path = root / "workspace" / "workflow.png"
    synthesis_diagram_path = synthesis_dir / "workflow_diagram.png"
    if workflow_png_path.exists():
        check_write_permitted(synthesis_diagram_path)
        shutil.copy2(workflow_png_path, synthesis_diagram_path)
        created.append(str(synthesis_diagram_path.absolute()))

    # abstract.md
    abstract_path = synthesis_dir / "abstract.md"
    if not abstract_path.exists():
        check_write_permitted(abstract_path)
        abstract_path.write_text(
            f"# Abstract — {project_name}\n\n"
            "*Auto-generated template. Fill in each section with ~50 words.*\n\n"
            "## Background\n\n"
            "*(Context and motivation for this research)*\n\n"
            "## Objective\n\n"
            f"*({project_name} — the core research question)*\n\n"
            "## Methods\n\n"
            "*(Study design, data sources, analytical approach)*\n\n"
            "## Results\n\n"
            "*(Key findings with quantitative summary)*\n\n"
            "## Conclusion\n\n"
            "*(Implications, limitations, future work)*\n\n"
            "---\n"
            f"*Drafted: {now_iso()}* | *Status: draft*\n"
        )
        created.append(str(abstract_path.absolute()))

    # paper.tex
    tex_path = synthesis_dir / "paper.tex"
    if not tex_path.exists():
        check_write_permitted(tex_path)
        tex_path.write_text(
            r"""\documentclass[11pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{geometry}
\usepackage{natbib}
\usepackage{hyperref}

\title{"""
            + project_name
            + r"""}
\author{Research OS}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
(Abstract to be filled from synthesis/abstract.md)
\end{abstract}

\section{Introduction}

\section{Methods}

\section{Results}

\section{Discussion}

\bibliographystyle{plainnat}
\bibliography{references}

\end{document}
"""
        )
        created.append(str(tex_path.absolute()))

    # references.bib
    bib_path = synthesis_dir / "references.bib"
    if not bib_path.exists():
        check_write_permitted(bib_path)
        bib_path.write_text(
            "% References will be auto-populated from workspace/citations.md\n"
        )
        created.append(str(bib_path.absolute()))

    return {"paths_created": created, "synthesis_dir": str(synthesis_dir.absolute())}


# ------------------------------------------------------------------
# §3.4 — Workflow diagram rendering
# ------------------------------------------------------------------


def render_workflow_diagram(root: Path) -> dict:
    """Render workspace/workflow.mermaid → workspace/workflow.png via mmdc.

    If mmdc (mermaid-cli) is not installed, returns a warning.
    Returns dict with 'png_path', 'rendered' (bool), and optional 'warning'.
    """
    mermaid_path = root / "workspace" / "workflow.mermaid"
    png_path = root / "workspace" / "workflow.png"

    if not mermaid_path.exists():
        return {
            "png_path": None,
            "rendered": False,
            "warning": "No workflow.mermaid found to render",
        }

    import shutil

    mmdc = shutil.which("mmdc")
    if not mmdc:
        return {
            "png_path": None,
            "rendered": False,
            "warning": (
                "mmdc (mermaid-cli) is not installed. "
                "Install it with: npm install -g @mermaid-js/mermaid-cli\n"
                "To automatically install it, rerun setup or run: pip install -e '.[dev]'"
            ),
        }

    import subprocess

    try:
        result = subprocess.run(
            [mmdc, "-i", str(mermaid_path), "-o", str(png_path), "-b", "white"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {
                "png_path": None,
                "rendered": False,
                "warning": f"mmdc failed: {result.stderr.strip()}",
            }
        return {"png_path": str(png_path.absolute()), "rendered": True, "warning": None}
    except subprocess.TimeoutExpired:
        return {
            "png_path": None,
            "rendered": False,
            "warning": "mmdc timed out after 60s",
        }
    except Exception as e:
        return {"png_path": None, "rendered": False, "warning": f"mmdc error: {e}"}


def generate_citations_md(root: Path) -> str:
    """Generate workspace/citations.md from the literature index.

    Each entry includes a `verified: false` flag for the citation_verifier.
    Returns the path to the written file.
    """
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

    lines = ["# Running Bibliography", "", "*Auto-generated from literature index*", ""]
    if entries:
        for filename, meta in sorted(entries.items()):
            key = meta.get("citation_key", filename)
            verified = meta.get("verified", False)
            status = "✅ Verified" if verified else "⏳ Pending verification"
            sha = meta.get("sha256", "")[:12]
            lines.append(f"### `{key}`")
            lines.append(f"  - **File**: {filename}")
            lines.append(f"  - **SHA-256**: `{sha}`")
            lines.append(f"  - **Status**: {status}")
            lines.append("")
    else:
        lines.append("*(No citations yet. Add PDFs to `inputs/literature/`.)*")
        lines.append("")

    citations_path.write_text("\n".join(lines) + "\n")
    return str(citations_path.absolute())
