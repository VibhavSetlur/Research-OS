"""Package-native workspace operations for clean Research Copilot projects."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - PyYAML is a package dependency.
    yaml = None

from research_copilot.utils.common import find_project_root, now_iso


def _resolve_root(root: Path | None = None) -> Path:
    r = find_project_root(root)
    if not r:
        raise ValueError("Could not find project root containing .research/")
    return r


EXPERIMENT_SUBDIRS = [
    "scripts",
    "outputs",
    "outputs/figures",
    "outputs/tables",
    "outputs/artifacts",
    "outputs/analysis",
]


def slugify(value: str, fallback: str = "branch") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def state_path(root: Path) -> Path:
    return root / "03_synthesis" / "state_ledger.json"


def manifest_path(root: Path) -> Path:
    return root / "03_synthesis" / "manifest.json"


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def default_state() -> dict:
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "current_branch": "exp_001_baseline",
        "branches": {
            "exp_001_baseline": {
                "branch_id": "exp_001_baseline",
                "parent_branch": None,
                "status": "active",
                "hypothesis": "Baseline research workflow",
                "experiment_dir": "02_experiments/exp_001_baseline",
                "created_at": now_iso(),
                "input_data_hashes": {},
            }
        },
    }


def load_state(root: Path | None = None) -> dict:
    root = _resolve_root(root)
    state = read_json(state_path(root), default_state())
    state.setdefault("current_branch", "exp_001_baseline")
    state.setdefault("branches", {})
    return cast(dict, state)


def save_state(root: Path, state: dict) -> dict:
    state["updated_at"] = now_iso()
    write_json(state_path(root), state)
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
    for base in (root / "00_inputs" / "raw_data", root / "00_inputs" / "literature"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith(".") and path.name not in {"README.md", ".gitkeep"}:
                hashes[path.relative_to(root).as_posix()] = compute_file_hash(path)
    return hashes


def next_experiment_id(root: Path | None, slug: str) -> str:
    root = _resolve_root(root)
    experiments = root / "02_experiments"
    max_seen = 1
    if experiments.exists():
        for path in experiments.iterdir():
            match = re.match(r"exp_(\d+)_", path.name)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
    return f"exp_{max_seen + 1:03d}_{slugify(slug)}"


def write_readme(path: Path, title: str, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {title}\n\n{body.strip()}\n")


def scaffold_minimal_workspace(root: Path, project_name: str) -> None:
    """Create the four top-level clean workspace directories and .research/config.yaml."""
    root.mkdir(parents=True, exist_ok=True)
    directories = {
        "00_inputs": "Immutable canonical inputs after ingest.",
        "00_inputs/raw_data": "Raw data files. Do not modify these after hashing.",
        "00_inputs/literature": "Original literature files and extracted indexes.",
        "01_workspace": "Human-AI working notes and scratch material.",
        "01_workspace/scratchpad": "Queued ideas, links, and informal notes.",
        "02_experiments": "Isolated hypothesis branches with local scripts and outputs.",
        "02_experiments/exp_001_baseline": "Baseline experiment branch.",
        "02_experiments/exp_001_baseline/scripts": "Numbered scripts for the baseline experiment.",
        "02_experiments/exp_001_baseline/outputs": "Baseline generated outputs.",
        "02_experiments/exp_001_baseline/outputs/figures": "Figures with sidecar metadata.",
        "02_experiments/exp_001_baseline/outputs/tables": "Tables with sidecar metadata.",
        "02_experiments/exp_001_baseline/outputs/artifacts": "Serialized models and processed artifacts.",
        "02_experiments/exp_001_baseline/outputs/analysis": "Analysis plans, diagnostics, and result summaries.",
        "03_synthesis": "Final synthesis, manifests, manuscript, and audit outputs.",
        "03_synthesis/manuscript": "Manuscript drafts generated from ledgers and artifact metadata.",
        "03_synthesis/final_figures": "Promoted final figures.",
        "03_synthesis/quality_gates": "Recorded quality gate results.",
        "03_synthesis/audit": "Adversarial and compliance review outputs.",
    }
    for rel, body in directories.items():
        write_readme(root / rel, Path(rel).name.replace("_", " ").title(), body)

    # Create .research/config.yaml
    research_dir = root / ".research"
    research_dir.mkdir(parents=True, exist_ok=True)
    config_path = research_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            f"# Research Copilot — Project Configuration\n"
            f'project_id: "{project_name}"\n'
            f'schema_version: "9.0.0"\n'
            f'default_workflow: "quick_exploratory"\n'
            f"intent_routing:\n"
            f"  enabled: true\n"
            f'  default_depth: "academic"\n'
            f"branching:\n"
            f"  enabled: true\n"
            f"knowledge_graph:\n"
            f"  enabled: true\n"
            f"semantic_filesystem:\n"
            f"  enabled: true\n"
            f"interpretative_coupling:\n"
            f"  enabled: true\n"
            f"data_scale_thresholds:\n"
            f"  medium_mb: 100\n"
            f"  large_gb: 1\n"
            f"  massive_gb: 10\n"
            f"execution:\n"
            f"  supported_runtimes: [python, r, bash]\n"
            f"dependency_management:\n"
            f"  auto_detect: true\n"
            f'  requirements_file: "environment/requirements.txt"\n'
            f"quality_gates_enabled: true\n"
            f"pin_dependency_versions: true\n"
        )

    intake = root / "00_inputs" / "intake.md"
    if not intake.exists():
        intake.write_text(
            f"# {project_name} Intake\n\n"
            "## Project\n\n"
            "- Title:\n- Researcher:\n- Institution:\n\n"
            "## Research Questions\n\n"
            "1. \n\n"
            "## Data\n\n"
            "- Place raw files in `00_inputs/raw_data/`.\n"
        )

    notebook = root / "01_workspace" / "lab_notebook.md"
    if not notebook.exists():
        notebook.write_text(
            f"# Lab Notebook - {project_name}\n\n"
            "> Append-only chronological record of research thoughts and AI actions.\n\n"
            f"## {datetime.now(timezone.utc).date().isoformat()}\n"
            "- Initialized clean Research Copilot workspace.\n"
        )

    baseline_decisions = root / "02_experiments" / "exp_001_baseline" / "decisions.yaml"
    if not baseline_decisions.exists():
        baseline_decisions.write_text(
            "schema_version: '1.0'\n"
            "experiment_id: exp_001_baseline\n"
            "parent_experiment: null\n"
            f"created: {now_iso()}\n"
            "input_data_hashes: {}\n"
            "decisions:\n"
            "  decision_001:\n"
            f"    date: {datetime.now(timezone.utc).date().isoformat()}\n"
            "    context: Clean workspace initialized from packaged Research Copilot assets.\n"
            "    selected: Use experiment-driven directory structure.\n"
            "    rationale: Keeps user workspace minimal while preserving provenance.\n"
            "    linked_literature: []\n"
        )

    manifest = {
        "schema_version": "1.0",
        "project": {"title": project_name},
        "created_at": now_iso(),
        "architecture": "package_assets_clean_workspace",
        "top_level_directories": ["00_inputs", "01_workspace", "02_experiments", "03_synthesis"],
        "active_experiment": "exp_001_baseline",
        "branches": {"exp_001_baseline": {"status": "active"}},
    }
    write_json(manifest_path(root), manifest)

    state = default_state()
    state["branches"]["exp_001_baseline"]["input_data_hashes"] = compute_input_hashes(root)
    save_state(root, state)

    _copy_ai_rules_to_project(root)
    _copy_environment_to_project(root)
    _setup_mcp_configs(root)
    _setup_gitignore(root)
    _initialize_git(root)
    _run_preflight_checks()

def _initialize_git(root: Path) -> None:
    import subprocess
    if not (root / ".git").exists():
        try:
            subprocess.run(["git", "init"], cwd=root, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "chore: initial research copilot scaffold"], cwd=root, capture_output=True)
        except Exception:
            pass

def _run_preflight_checks() -> None:
    print("=" * 60)
    print("ENVIRONMENT PREFLIGHT CHECKS")
    print("=" * 60)
    import subprocess
    import sys
    print(f"  [✓] Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    try:
        docker = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if docker.returncode == 0:
            print(f"  [✓] Docker: {docker.stdout.strip()}")
        else:
            print("  [ ] Docker not found.")
    except Exception:
        print("  [ ] Docker not found.")

    try:
        conda = subprocess.run(["conda", "--version"], capture_output=True, text=True)
        if conda.returncode == 0:
            print(f"  [✓] Conda: {conda.stdout.strip()}")
        else:
            print("  [ ] Conda not found.")
    except Exception:
        print("  [ ] Conda not found.")

    try:
        ollama = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if ollama.returncode == 0:
            print(f"  [✓] Ollama: {ollama.stdout.strip()}")
        else:
            print("  [ ] Ollama not found.")
    except Exception:
        print("  [ ] Ollama not found.")
    print("=" * 60)


def _setup_gitignore(root: Path) -> None:
    """Generate default .gitignore for the research project."""
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# Research Copilot — Git Ignore Rules\n\n"
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
            "# Research Copilot Runtime Cache\n"
            ".research/cache/\n"
            ".research/state/\n"
            ".research/workflow_dag.json\n"
            ".research/workflow_dag.mermaid\n\n"
            "# Raw Data (Do not commit massive datasets)\n"
            "00_inputs/raw_data/*\n"
            "!00_inputs/raw_data/.gitkeep\n"
        )


def _setup_mcp_configs(root: Path) -> None:
    """Generate default MCP configuration for popular AI IDEs."""
    cursor_dir = root / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    cursor_mcp = cursor_dir / "mcp.json"
    if not cursor_mcp.exists():
        cursor_mcp.write_text(
            json.dumps({"mcpServers": {"research-copilot": {"command": "research-copilot-mcp", "args": []}}}, indent=2)
            + "\n"
        )

    opencode_json = root / "opencode.json"
    if not opencode_json.exists():
        opencode_json.write_text(
            json.dumps({"mcp": {"research-copilot": {"command": "research-copilot-mcp", "args": []}}}, indent=2) + "\n"
        )


def _copy_ai_rules_to_project(root: Path) -> None:
    """Copy AI agent rules files from package assets to the project root."""
    try:
        import importlib.resources as importlib_resources
    except ImportError:
        import importlib_resources  # type: ignore[no-redef]

    assets = ["AGENTS.md", ".cursorrules", ".clinerules", ".windsurfrules", "copilot-instructions.md"]
    for asset_name in assets:
        try:
            asset_path = importlib_resources.files("research_copilot.assets") / asset_name
            dest = root / asset_name
            if not dest.exists():
                dest.write_text(asset_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass


def _copy_environment_to_project(root: Path) -> None:
    """Copy environment configuration files from package assets to the project."""
    try:
        import importlib.resources as importlib_resources
    except ImportError:
        import importlib_resources  # type: ignore[no-redef]

    env_dir = root / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)

    files = ["setup.sh", "setup_conda.sh", "requirements.txt", "README.md"]
    for filename in files:
        try:
            asset_path = importlib_resources.files("research_copilot.assets.environment") / filename
            dest = env_dir / filename
            if not dest.exists():
                dest.write_text(asset_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass


def create_experiment_branch(
    name: str,
    hypothesis: str = "",
    parent: str | None = None,
    root: Path | None = None,
) -> dict:
    """Create an isolated experiment branch and update state/manifest."""
    root = _resolve_root(root)
    state = load_state(root)
    parent = parent or state.get("current_branch", "exp_001_baseline")
    branch_id = name if name.startswith("exp_") else next_experiment_id(root, name)
    if branch_id in state.get("branches", {}):
        raise ValueError(f"Branch '{branch_id}' already exists.")

    experiment_dir = root / "02_experiments" / branch_id
    data_hashes = compute_input_hashes(root)
    for subdir in EXPERIMENT_SUBDIRS:
        write_readme(
            experiment_dir / subdir,
            f"{branch_id} {subdir}",
            f"Branch-specific `{subdir}` files for hypothesis: {hypothesis or name}.",
        )

    decisions_path = experiment_dir / "decisions.yaml"
    decisions_path.write_text(
        "schema_version: '1.0'\n"
        f"experiment_id: {branch_id}\n"
        f"parent_experiment: {parent}\n"
        f"created: {now_iso()}\n"
        "input_data_hashes:\n" + _yaml_mapping(data_hashes, indent=2) + "decisions:\n"
        "  decision_001:\n"
        f"    date: {datetime.now(timezone.utc).date().isoformat()}\n"
        "    context: Alternate hypothesis branch created.\n"
        "    selected: Create isolated experiment branch.\n"
        f"    rationale: {hypothesis or name}\n"
        "    linked_literature: []\n"
    )

    state["branches"][branch_id] = {
        "branch_id": branch_id,
        "parent_branch": parent,
        "status": "active",
        "hypothesis": hypothesis or name,
        "experiment_dir": f"02_experiments/{branch_id}",
        "created_at": now_iso(),
        "input_data_hashes": data_hashes,
    }
    state["current_branch"] = branch_id
    save_state(root, state)

    manifest = read_json(manifest_path(root), {})
    manifest.setdefault("branches", {})[branch_id] = {
        "status": "active",
        "parent_branch": parent,
        "hypothesis": hypothesis or name,
        "created_at": now_iso(),
    }
    manifest["active_experiment"] = branch_id
    write_json(manifest_path(root), manifest)

    return {
        "branch_id": branch_id,
        "parent_branch": parent,
        "experiment_dir": f"02_experiments/{branch_id}",
        "data_hashes": data_hashes,
        "decisions": decisions_path.relative_to(root).as_posix(),
    }


def current_branch(root: Path | None = None) -> str:
    return cast(str, load_state(root).get("current_branch", "exp_001_baseline"))


def branch_decisions_path(root: Path, branch_id: str | None = None) -> Path:
    branch_id = branch_id or current_branch(root)
    return root / "02_experiments" / branch_id / "decisions.yaml"


def log_decision(
    context: str,
    selected: str,
    rationale: str,
    *,
    options_considered: list[str] | None = None,
    linked_literature: list[str] | None = None,
    branch_id: str | None = None,
    root: Path | None = None,
) -> dict:
    """Append a methodological decision to the active experiment ledger."""
    root = _resolve_root(root)
    path = branch_decisions_path(root, branch_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    if yaml is not None and path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    else:
        data = {}

    decisions = data.setdefault("decisions", {})
    next_idx = len(decisions) + 1
    decision_id = f"decision_{next_idx:03d}"
    decisions[decision_id] = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "context": context,
        "options_considered": options_considered or [],
        "selected": selected,
        "rationale": rationale,
        "linked_literature": linked_literature or [],
    }
    data.setdefault("schema_version", "1.0")
    data.setdefault("experiment_id", branch_id or current_branch(root))
    data.setdefault("created", now_iso())

    if yaml is not None:
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    else:
        with open(path, "a") as f:
            f.write(
                f"\n  {decision_id}:\n    context: {context}\n    selected: {selected}\n    rationale: {rationale}\n"
            )

    return {"decision_id": decision_id, "path": path.relative_to(root).as_posix()}


def save_artifact(
    filename: str,
    content: str,
    *,
    artifact_type: str = "artifact",
    generated_by: str = "mcp",
    source_script: str = "",
    input_files: list[str] | None = None,
    decisions_applied: list[str] | None = None,
    branch_id: str | None = None,
    root: Path | None = None,
) -> dict:
    """Save a text artifact with required sibling provenance metadata."""
    root = _resolve_root(root)
    branch_id = branch_id or current_branch(root)
    folder = {
        "figure": "figures",
        "table": "tables",
        "analysis": "analysis",
        "artifact": "artifacts",
    }.get(artifact_type, "artifacts")
    safe_name = Path(filename).name
    output_path = root / "02_experiments" / branch_id / "outputs" / folder / safe_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    input_files = input_files or []
    data_hashes = {}
    for item in input_files:
        path = root / item if not Path(item).is_absolute() else Path(item)
        if path.exists() and path.is_file():
            data_hashes[item] = compute_file_hash(path)

    script_hash = ""
    if source_script:
        script_path = root / source_script if not Path(source_script).is_absolute() else Path(source_script)
        if script_path.exists():
            script_hash = compute_file_hash(script_path)

    meta = {
        "generated_by": generated_by,
        "timestamp": now_iso(),
        "source_script": source_script,
        "script_hash": script_hash,
        "data_hashes": data_hashes,
        "decisions_applied": decisions_applied or [],
        "branch_id": branch_id,
    }
    meta_path = output_path.with_name(f"{output_path.stem}.meta.yaml")
    if yaml is not None:
        meta_path.write_text(yaml.safe_dump(meta, sort_keys=False))
    else:
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    return {
        "artifact": output_path.relative_to(root).as_posix(),
        "metadata": meta_path.relative_to(root).as_posix(),
        "branch_id": branch_id,
    }


def _yaml_mapping(values: dict, indent: int = 0) -> str:
    prefix = " " * indent
    if not values:
        return f"{prefix}{{}}\n"
    return "".join(f'{prefix}"{k}": "{v}"\n' for k, v in values.items())
