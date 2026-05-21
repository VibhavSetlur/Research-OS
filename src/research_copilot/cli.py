#!/usr/bin/env python3
"""Research Copilot package CLI."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from research_copilot.intent_router import IntentRouter
from research_copilot.project_ops import (
    compute_input_hashes,
    create_experiment_branch,
    load_state,
    log_decision,
    save_artifact,
    scaffold_minimal_workspace,
)
from research_copilot.utils.asset_manager import AssetManager
from research_copilot.utils.manuscript_compiler import cmd_compile, ManuscriptCompiler

# All valid depth values — quick/standard/deep are user-facing aliases;

# exploratory/academic/publication are the canonical internal names.
DEPTH_CHOICES = ("quick", "exploratory", "standard", "academic", "deep", "publication")


def _project_root() -> Path:
    return AssetManager.find_project_root()


def _asset_by_name(manager: AssetManager, directory: str, name: str) -> str | None:
    exact = f"{directory}/{name}.md"
    if manager.exists(exact):
        return exact

    for ref in manager.iter_files(directory, "*.md"):
        stem = Path(ref.relative_path).stem
        normalized = stem.split("_", 1)[1] if "_" in stem else stem
        if stem == name or normalized == name:
            return ref.relative_path
    return None


def cmd_init(args: argparse.Namespace) -> None:
    project_name = args.name
    target_dir = Path(project_name)

    if target_dir.exists():
        if not args.force:
            print(f"Error: Directory '{project_name}' already exists.")
            print("Use --force to overwrite.")
            sys.exit(1)
        shutil.rmtree(target_dir)

    scaffold_minimal_workspace(target_dir, project_name)

    print("=" * 60)
    print("Research Copilot workspace created")
    print("=" * 60)
    print(f"Project: {project_name}")
    print(f"Location: {target_dir.resolve()}")
    print()
    print("Top-level directories:")
    for dirname in ("00_inputs", "01_workspace", "02_experiments", "03_synthesis"):
        print(f"  - {dirname}/")
    print()
    print("Next steps:")
    print(f"  cd {project_name}")
    print("  rcp setup          # Verify assets")
    print("  rcp status         # Check project state")
    print()
    print("System assets are loaded from the installed Python package.")
    print("Project config is in .research/config.yaml.")


def cmd_preflight(args: argparse.Namespace) -> None:
    try:
        root = _project_root()
        print("=" * 60)
        print("ENVIRONMENT PREFLIGHT CHECKS")
        print("=" * 60)
        print(f"Python Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        print(f"Workspace:      {root}")
        print(f"Config Folder:  {root / '.research' if (root / '.research').exists() else 'MISSING'}")
        print(f"Inputs Folder:  {root / '00_inputs' if (root / '00_inputs').exists() else 'MISSING'}")
        print("Status:         OK")
    except Exception as e:
        print(f"Preflight error: {e}")
        sys.exit(1)


def cmd_scan(args: argparse.Namespace) -> None:
    try:
        from research_copilot.utils.data_scale_detector import DataScaleDetector

        root = _project_root()
        inputs_dir = root / "00_inputs" / "raw_data"
        if not inputs_dir.exists():
            print(f"Error: Raw data directory not found at {inputs_dir}")
            sys.exit(1)

        print("=" * 60)
        print("SCANNING INPUT DATA")
        print("=" * 60)
        detector = DataScaleDetector(project_root=root)
        results = detector.scan()
        print(yaml.safe_dump(results, sort_keys=False))
    except Exception as e:
        print(f"Scan error: {e}")
        sys.exit(1)


def cmd_setup(args: argparse.Namespace) -> None:
    manager = AssetManager(_project_root())
    asset_counts = {
        "agents": len(list(manager.iter_files("agents", "*.md"))),
        "skills": len(list(manager.iter_files("skills", "*.md"))),
        "schemas": len(list(manager.iter_files("schemas", "*.py"))),
        "workflows": len(list(manager.iter_files("workflows", "*.yaml"))),
        "domains": len(list(manager.iter_files("domains", "*"))),
    }
    local_overrides: list = []
    if manager.override_root.exists():
        for root_name in ("agents", "skills", "schemas", "workflows", "domains"):
            local_overrides.extend(manager.iter_files(root_name, "*"))

    print("=" * 60)
    print("RESEARCH COPILOT SETUP")
    print("=" * 60)
    print(f"Workspace: {manager.project_root}")
    print("Bundled assets:")
    for name, count in asset_counts.items():
        print(f"  - {name}: {count}")
    print(f"Local overrides: {len([r for r in local_overrides if r.source == 'local_override'])}")
    print("Status: READY")


def cmd_status(args: argparse.Namespace) -> None:
    root = _project_root()
    state = load_state(root)
    hashes = compute_input_hashes(root)
    experiments_dir = root / "02_experiments"
    experiments = sorted(p.name for p in experiments_dir.iterdir() if p.is_dir()) if experiments_dir.exists() else []
    manifest_exists = (root / "03_synthesis" / "manifest.json").exists()

    print("=" * 60)
    print("RESEARCH PROJECT STATUS")
    print("=" * 60)
    print(f"Workspace: {root}")
    print(f"Current branch: {state.get('current_branch', 'exp_001_baseline')}")
    print(f"Experiments: {len(experiments)}")
    for exp in experiments[:8]:
        marker = "*" if exp == state.get("current_branch") else "-"
        print(f"  {marker} {exp}")
    if len(experiments) > 8:
        print(f"  ... and {len(experiments) - 8} more")
    print(f"Input files hashed: {len(hashes)}")
    print(f"Manifest: {'present' if manifest_exists else 'missing'}")
    print(f"Depth profile: {args.depth}")


def cmd_agents(args: argparse.Namespace) -> None:
    manager = AssetManager(_project_root())
    if args.name:
        rel = _asset_by_name(manager, "agents", args.name)
        if not rel:
            print(f"Agent '{args.name}' not found.")
            return
        print(f"--- {rel} ---")
        print(manager.read_text(rel))
        return

    print("=" * 60)
    print("AGENTS")
    print("=" * 60)
    for ref in manager.iter_files("agents", "*.md"):
        stem = Path(ref.relative_path).stem
        if stem.startswith("00_"):
            continue
        name = stem.split("_", 1)[1] if "_" in stem else stem
        source = " (override)" if ref.source == "local_override" else ""
        print(f"  - {name}{source}")


def cmd_skills(args: argparse.Namespace) -> None:
    manager = AssetManager(_project_root())
    if args.name:
        rel = _asset_by_name(manager, "skills", args.name)
        if not rel:
            print(f"Skill '{args.name}' not found.")
            return
        print(f"--- {rel} ---")
        print(manager.read_text(rel))
        return

    print("=" * 60)
    print("SKILLS")
    print("=" * 60)
    current_category = None
    for ref in manager.iter_files("skills", "*.md"):
        path = Path(ref.relative_path)
        if path.name == "SKILL_TEMPLATE.md":
            continue
        category = path.parts[1] if len(path.parts) > 2 else "root"
        if category != current_category:
            current_category = category
            print(f"\n  {category}/")
        source = " (override)" if ref.source == "local_override" else ""
        print(f"    - {path.stem}{source}")


def cmd_workflow(args: argparse.Namespace) -> None:
    manager = AssetManager(_project_root())
    config = yaml.safe_load(manager.read_text("config.yaml")) or {}
    workflow_id = args.name or config.get("default_workflow", "quick_exploratory")
    rel = f"workflows/{workflow_id}.yaml"
    if not manager.exists(rel):
        print(f"Workflow '{workflow_id}' not found.")
        return
    workflow = yaml.safe_load(manager.read_text(rel)) or {}
    print("=" * 60)
    print(f"WORKFLOW: {workflow.get('name', workflow_id)}")
    print("=" * 60)
    print(workflow.get("description", ""))
    print()
    for idx, agent in enumerate(workflow.get("agents", []), 1):
        print(f"  {idx}. {agent}")


def cmd_intent(args: argparse.Namespace) -> None:
    router = IntentRouter(_project_root())
    result = router.route(args.query, depth=args.depth)
    print(f"Intent: {result['classification']['primary_intent']}")
    print(f"Depth: {result['depth']}")
    print(f"Constraint: {result['depth_profile']['prompt_constraint']}")
    print(f"Null space excluded: {', '.join(result['null_space'])}")
    print(f"Estimated token savings: ~{result['excluded']['estimated_token_savings']} tokens")
    print("\nSkills to load:")
    for skill in result["context"]["skills"]:
        print(f"  - {skill}")
    print("\nAgents to invoke:")
    for agent in result["context"]["agents"]:
        print(f"  - {agent}")


def cmd_branch(args: argparse.Namespace) -> None:
    result = create_experiment_branch(args.name, hypothesis=args.hypothesis, parent=args.parent, root=_project_root())
    print(f"Created branch: {result['branch_id']}")
    print(f"Experiment: {result['experiment_dir']}")
    print(f"Input hashes inherited: {len(result['data_hashes'])}")


def cmd_branches(args: argparse.Namespace) -> None:
    state = load_state(_project_root())
    active = state.get("current_branch")
    print(f"{'Branch':<28} {'Parent':<24} {'Status':<12} Hypothesis")
    print("-" * 90)
    for branch_id, branch in sorted(state.get("branches", {}).items()):
        marker = "*" if branch_id == active else " "
        print(
            f"{marker} {branch_id:<26} "
            f"{str(branch.get('parent_branch') or ''):<24} "
            f"{branch.get('status', ''):<12} "
            f"{branch.get('hypothesis', '')}"
        )


def cmd_log_decision(args: argparse.Namespace) -> None:
    result = log_decision(
        context=args.context,
        selected=args.selected,
        rationale=args.rationale,
        branch_id=args.branch,
        root=_project_root(),
    )
    print(f"Logged {result['decision_id']} -> {result['path']}")


def cmd_save_artifact(args: argparse.Namespace) -> None:
    result = save_artifact(
        args.filename,
        args.content,
        artifact_type=args.artifact_type,
        generated_by=args.generated_by,
        source_script=args.source_script or "",
        branch_id=args.branch,
        root=_project_root(),
    )
    print(f"Saved {result['artifact']}")
    print(f"Metadata {result['metadata']}")


def cmd_trace(args: argparse.Namespace) -> None:
    from research_copilot.utils.auto_debug import trace_node
    trace_node(args.node_id, _project_root())

def cmd_ingest(args: argparse.Namespace) -> None:
    from research_copilot.utils.cache_manager import cmd_ingest as _ingest
    _ingest(args)

def cmd_compress(args: argparse.Namespace) -> None:
    """Compress the state ledger using a local LLM to free context window space."""
    try:
        from research_copilot.core.state_ledger import ResearchLedger

        root = _project_root()
        ledger = ResearchLedger(root / "03_synthesis" / "state_ledger.json")
        result = ledger.compress_ledger(model=args.model, dry_run=args.dry_run)

        print("=" * 60)
        print("LEDGER COMPRESSION SUMMARY")
        print("=" * 60)
        print(f"Nodes compressed : {result['compressed_nodes']}")
        print(f"Original chars   : {result['original_chars']:,}")
        print(f"Compressed chars : {result['compressed_chars']:,}")
        print(f"Context savings  : ~{result['savings_pct']}%")
        if args.dry_run:
            print("\n[DRY RUN] No changes written.")
    except Exception as e:
        print(f"Compress error: {e}")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rcp",
        description="Research Copilot - clean workspace CLI",
    )
    parser.add_argument(
        "--depth",
        dest="global_depth",
        choices=DEPTH_CHOICES,
        default="academic",
        help="Default routing depth for commands that use intent context",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize a clean Research Copilot project")
    p_init.add_argument("name", help="Project name or target directory")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing directory")

    sub.add_parser("preflight", help="Run environment preflight checks")
    sub.add_parser("scan", help="Scan inputs and build research map")
    sub.add_parser("setup", help="Verify package assets and local overrides")
    sub.add_parser("status", help="Show clean workspace status")

    p_compress = sub.add_parser(
        "compress",
        help="Compress state ledger via local LLM to reclaim context window space",
    )
    p_compress.add_argument(
        "--model",
        default="ollama/llama3",
        help="Local model to use (format: ollama/<model_name>). Default: ollama/llama3",
    )
    p_compress.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview compressed outputs without saving changes",
    )

    p_compile = sub.add_parser("compile", help="Map-reduce manuscript sections into PDF/HTML via Pandoc")
    p_compile.add_argument("--formats", default="pdf,html", help="Comma-separated formats (e.g., pdf,html)")

    p_trace = sub.add_parser("trace", help="Trace node execution sequence")
    p_trace.add_argument("node_id", help="Node ID to trace")

    p_ingest = sub.add_parser("ingest", help="Ingest a file into local vector database")
    p_ingest.add_argument("file", help="File to ingest (pdf/csv/txt)")

    p_agent = sub.add_parser("agent", help="Show a specific agent")
    p_agent.add_argument("name")
    sub.add_parser("agents", help="List agents")

    p_skill = sub.add_parser("skill", help="Show a specific skill")
    p_skill.add_argument("name")
    sub.add_parser("skills", help="List skills")

    p_workflow = sub.add_parser("workflow", help="Show workflow")
    p_workflow.add_argument("name", nargs="?")

    p_intent = sub.add_parser("intent", help="Route a query through depth-aware intent routing")
    p_intent.add_argument("query")
    p_intent.add_argument("--depth", choices=DEPTH_CHOICES, default=None)

    p_branch = sub.add_parser("branch", help="Create an isolated experiment branch")
    p_branch.add_argument("name")
    p_branch.add_argument("--hypothesis", default="")
    p_branch.add_argument("--from", dest="parent", default=None)
    sub.add_parser("branches", help="List experiment branches")

    p_decision = sub.add_parser("log-decision", help="Append to the active experiment decisions.yaml")
    p_decision.add_argument("--context", required=True)
    p_decision.add_argument("--selected", required=True)
    p_decision.add_argument("--rationale", required=True)
    p_decision.add_argument("--branch")

    p_artifact = sub.add_parser("save-artifact", help="Save artifact with sibling .meta.yaml")
    p_artifact.add_argument("filename")
    p_artifact.add_argument("--content", required=True)
    p_artifact.add_argument("--artifact-type", choices=["artifact", "analysis", "figure", "table"], default="artifact")
    p_artifact.add_argument("--generated-by", default="cli")
    p_artifact.add_argument("--source-script")
    p_artifact.add_argument("--branch")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.depth = getattr(args, "depth", None) or args.global_depth

    commands = {
        "init": cmd_init,
        "preflight": cmd_preflight,
        "scan": cmd_scan,
        "setup": cmd_setup,
        "status": cmd_status,
        "compress": cmd_compress,
        "agent": cmd_agents,
        "agents": lambda a: cmd_agents(argparse.Namespace(name=None)),
        "skill": cmd_skills,
        "skills": lambda a: cmd_skills(argparse.Namespace(name=None)),
        "workflow": cmd_workflow,
        "intent": cmd_intent,
        "trace": cmd_trace,
        "compile": cmd_compile,
        "trace": cmd_trace,
        "ingest": cmd_ingest,
        "branch": cmd_branch,
        "branches": cmd_branches,
        "log-decision": cmd_log_decision,
        "save-artifact": cmd_save_artifact,
    }
    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
