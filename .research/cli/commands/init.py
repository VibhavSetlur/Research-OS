"""Init commands: init-dirs."""
import shutil
from datetime import datetime
from pathlib import Path

from core.utils import (
    find_project_root, load_json, load_markdown, save_json, get_config,
    get_research_map, require_project_root,
)

# Re-export shared commands from project module
from cli.commands.project import cmd_setup, cmd_preflight


def cmd_init_dirs(args):
    root = require_project_root()

    config = get_config(root)
    research_map = get_research_map(root, config)
    intake = load_markdown(root / config["intake_path"])

    project_title = research_map.get("project", {}).get("title", "Untitled")
    questions = research_map.get("questions", [])
    domain = research_map.get("domain", {}).get("name", "Unknown")
    data_files = research_map.get("data", {}).get("files", [])
    q_count = len(questions)
    file_count = len(data_files)
    today = datetime.now().strftime("%Y-%m-%d")

    researcher = "Unknown"
    institution = "Unknown"
    for line in intake.split("\n"):
        stripped = line.strip()
        if stripped.startswith("**Researcher**"):
            researcher = stripped.split(":", 1)[-1].strip().strip("[]")
        elif stripped.startswith("**Institution**"):
            institution = stripped.split(":", 1)[-1].strip().strip("[]")

    active_exp = config.get("active_experiment", "exp_001_baseline")
    dirs = {
        "00_inputs": f"# Inputs — {project_title}\n\nImmutable research inputs. After ingest, AI agents must not modify files here.",
        "00_inputs/raw_data": f"# Raw Data — {project_title}\n\nCanonical immutable raw data. Record SHA-256 hashes before downstream use.",
        "00_inputs/literature": f"# Literature — {project_title}\n\nOriginal papers, extracted method cache indexes, evidence matrices, and bibliography files.",
        "01_workspace": f"# Workspace — {project_title}\n\nHuman-AI working area for notes, triage, and lab notebook entries.",
        "01_workspace/scratchpad": f"# Scratchpad — {project_title}\n\nDrop zone for random ideas, links, notes, and half-baked files. Items are triaged before execution.",
        "02_experiments": f"# Experiments — {project_title}\n\nSelf-contained hypothesis branches. Each experiment owns scripts, outputs, artifacts, and decisions.",
        f"02_experiments/{active_exp}": f"# Experiment {active_exp} — {project_title}\n\nBaseline experiment branch created by research_init.",
        f"02_experiments/{active_exp}/scripts": f"# Scripts — {active_exp}\n\nNumbered reproducible scripts for this experiment only.",
        f"02_experiments/{active_exp}/outputs": f"# Outputs — {active_exp}\n\nGenerated outputs for this experiment. Every output requires a sibling `.meta.yaml` file.",
        f"02_experiments/{active_exp}/outputs/figures": f"# Figures — {active_exp}\n\nGenerated figures with sidecar provenance metadata.",
        f"02_experiments/{active_exp}/outputs/tables": f"# Tables — {active_exp}\n\nGenerated tables with sidecar provenance metadata.",
        f"02_experiments/{active_exp}/outputs/artifacts": f"# Artifacts — {active_exp}\n\nSerialized models, clean data chunks, and other reproducible artifacts.",
        f"02_experiments/{active_exp}/outputs/analysis": f"# Analysis — {active_exp}\n\nResearch maps, plans, diagnostics, and result JSON for this experiment.",
        "03_synthesis": f"# Synthesis — {project_title}\n\nFinal manuscript destination, global methods synthesized from experiment decisions, and winning outputs.",
        "03_synthesis/manuscript": f"# Manuscript — {project_title}\n\nPaper and write-up drafts assembled from experiment outputs.",
        "03_synthesis/final_figures": f"# Final Figures — {project_title}\n\nSymlinks or copies of selected experiment figures.",
        "03_synthesis/audit": f"# Audit — {project_title}\n\nFinal adversarial reviews, claim tracing, and quality gate results.",
        "03_synthesis/dashboards": f"# Dashboards — {project_title}\n\nInteractive final summaries.",
    }

    created = []
    for dir_path, readme_content in dirs.items():
        full_path = root / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        readme_path = full_path / "README.md"
        with open(readme_path, "w") as f:
            f.write(readme_content)
        created.append(dir_path)

    manifest = {
        "schema_version": "10.0.0",
        "project": {"title": project_title, "researcher": researcher, "institution": institution, "domain": domain},
        "created": today,
        "last_updated": today,
        "structure": {path: "Created by research_init" for path in dirs.keys()},
        "architecture": "experiment_driven",
        "active_experiment": active_exp,
        "iterations": [{"id": "001", "type": "initial_setup", "trigger": "research_init agent executed", "date": today, "status": "complete", "summary": "Full directory structure created, intake parsed, data scanned"}],
        "current_phase": "research_init",
        "total_iterations": 1,
        "research_questions": q_count,
        "data_files": file_count,
    }
    manifest_path = root / config.get("manifest", "docs/manifest.json")
    save_json(manifest_path, manifest)

    log_path = root / config.get("lab_notebook", "01_workspace/lab_notebook.md")
    with open(log_path, "w") as f:
        f.write(f"# Lab Notebook — {project_title}\n\n> Append-only chronological record of research thoughts, AI actions, and triage decisions.\n\n## Log\n\n### {today} — Initial Setup\n- **Agent**: research_init\n- **Action**: Parsed intake, scanned data, created experiment-driven project structure\n- **Active experiment**: {active_exp}\n- **Questions**: {q_count} research questions identified\n- **Data**: {file_count} files found in inputs/data/raw/\n- **Feasibility**: {research_map.get('feasibility', {}).get('verdict', 'unknown')}\n- **Next step**: Continue through the pipeline\n")

    method_path = root / config.get("global_methods", "03_synthesis/global_methods.md")
    with open(method_path, "w") as f:
        f.write(f"# Global Methods — {project_title}\n\n> Generated from experiment-level `decisions.yaml` ledgers during synthesis.\n\n## Current Methods\nMethods will be selected based on question types during method_route phase.\n")

    decisions_path = root / f"02_experiments/{active_exp}/decisions.yaml"
    with open(decisions_path, "w") as f:
        f.write(f"schema_version: '1.0'\nexperiment_id: {active_exp}\nparent_experiment: null\ncreated: {today}\ndecisions:\n  decision_001:\n    date: {today}\n    context: Initial baseline experiment scaffold.\n    options_considered:\n      - Create type-based docs/reports/data/scripts structure\n      - Create experiment-driven branch with local scripts, outputs, artifacts, and decisions\n    selected: Create experiment-driven branch with local scripts, outputs, artifacts, and decisions\n    rationale: Keeps provenance and branch-specific methodological choices attached to each hypothesis test.\n    linked_literature: []\n")

    registry_path = root / config.get("iteration_registry", "docs/iterations/registry.json")
    save_json(registry_path, {
        "schema_version": "10.0.0",
        "project": project_title,
        "iterations": [{"id": "001", "type": "initial_setup", "trigger": "research_init agent", "date": today, "status": "complete", "summary": "Initial project structure created, intake parsed, data scanned"}],
        "total": 1,
        "current_iteration": "001"
    })

    cache_map = root / config["cache_research_map"]
    if cache_map.exists():
        dest = root / config["research_map"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_map, dest)

    print("=" * 60)
    print("DIRECTORY STRUCTURE CREATED")
    print("=" * 60)
    print()
    print(f"  Project: {project_title}")
    print(f"  Directories created: {len(created)}")
    for d in created:
        print(f"    ✓ {d}/")
    print()
    print(f"  Files created:")
    print(f"    ✓ 03_synthesis/manifest.json")
    print(f"    ✓ 01_workspace/lab_notebook.md")
    print(f"    ✓ 03_synthesis/global_methods.md")
    print(f"    ✓ 03_synthesis/iteration_registry.json")
    print(f"    ✓ 02_experiments/{active_exp}/decisions.yaml")
    print(f"    ✓ 02_experiments/{active_exp}/outputs/analysis/research_map.json (copied from cache)")
    print()
    print(f"  Next: Continue with the pipeline agents.")
    print()
