#!/usr/bin/env python3
"""Research OS package CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]


from research_os.tools.actions.path import create_path, list_paths
from research_os.project_ops import (
    compute_input_hashes,
    load_state,
    log_decision,
    save_artifact,
    scaffold_minimal_workspace,
)
from research_os.utils.asset_manager import AssetManager

def cmd_compile(args) -> None:
    print("Compile command is deprecated or missing manuscript_compiler.")

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


def _print_tree(path: Path, prefix: str = "", is_root: bool = True) -> None:
    """Print a user-friendly directory tree with plain-English explanations."""
    EXPLANATIONS = {
        "inputs": "Your original, immutable research data and literature (never modified by tools)",
        "raw_data": "Original data files — CSV, JSON, Excel, etc.",
        "literature": "Downloaded papers and PDFs",
        "context": "Background context, notes, prior results",
        "workspace": "Active experimentation area — iterative research lives here",
        "data": "Derived and processed datasets",
        "derived": "Cleaned, transformed, and processed data files",
        "figures": "300-DPI publication-ready figures and visualizations",
        "reports": "Markdown analysis reports per experiment step",
        "dashboards": "Interactive HTML dashboards",
        "logs": "Execution logs and provenance records",
        "scripts": "Numbered analysis scripts (01_load.py, 02_eda.py, ...)",
        "outputs": "All experiment outputs — reports, figures, artifacts",
        "synthesis": "Final consolidated outputs — paper, abstract, bibliography",
        "environment": "Reproducible environments (requirements.txt, Dockerfile)",
        ".os_state": "OS internal state — checkpoints, manifest, ledger",
        "docs": "Project documentation and guides",
    }

    entries = sorted(path.iterdir()) if path.exists() else []

    for i, entry in enumerate(entries):
        if entry.name.startswith(".") and entry.name not in (
            ".os_state",
            ".os_state",
            ".cursor",
        ):
            continue
        if entry.name in ("__pycache__", ".git"):
            continue

        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        name_display = entry.name + "/" if entry.is_dir() else entry.name

        explanation = EXPLANATIONS.get(entry.name)
        if explanation:
            line = f"{prefix}{connector}{name_display}  ← {explanation}"
        else:
            line = f"{prefix}{connector}{name_display}"

        print(line)

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _print_tree(entry, prefix + extension, is_root=False)


def _interactive_questionnaire(target_dir: Path) -> dict:
    """Ask the user interactive questions to populate config.yaml."""
    print()
    print("Let's set up your Research OS project with a few quick questions.")
    print("(Press Enter to accept defaults in brackets.)")
    print()

    project_name = (
        input(f"  Project name [{target_dir.name}]: ").strip() or target_dir.name
    )

    default_question = f"Research question for '{project_name}'"
    research_question = input(f"  {default_question} []: ").strip()

    print("  Domain:")
    print("    1. General / Social Sciences")
    print("    2. Natural Sciences")
    print("    3. Biomedical / Health")
    print("    4. Engineering / CS")
    print("    5. Economics / Business")
    domain_choice = input("  Choose domain [1]: ").strip() or "1"
    domain_map = {
        "1": "general",
        "2": "natural_sciences",
        "3": "biomedical",
        "4": "engineering",
        "5": "economics",
    }
    domain = domain_map.get(domain_choice, "general")

    print("  Research depth:")
    print("    1. Quick exploratory (fast, simple stats)")
    print("    2. Academic (balanced, method checks)")
    print("    3. Publication (full rigor, adversarial critique)")
    depth_choice = input("  Choose depth [2]: ").strip() or "2"
    depth_map = {"1": "exploratory", "2": "academic", "3": "publication"}
    depth = depth_map.get(depth_choice, "academic")

    provider = input("  LLM provider [openai]: ").strip() or "openai"

    return {
        "project_name": project_name,
        "research_question": research_question,
        "domain": domain,
        "depth": depth,
        "provider": provider,
    }


def _print_mcp_snippet(project_root: Path) -> None:
    """Print the MCP JSON snippet that users paste into their IDE."""
    import sys as _sys

    snippet = {
        "research-os": {
            "command": "research-os",
            "args": ["start", "--transport", "stdio"],
        }
    }
    print("  ┌─ Cursor — paste into .cursor/mcp.json ─────────────────────────────┐")
    for line in json.dumps({"mcpServers": snippet}, indent=2).splitlines():
        print(f"  │ {line:<73} │")
    print("  └────────────────────────────────────────────────────────────────────┘")
    print()
    print(
        f"  Or run: echo '{json.dumps({'mcpServers': snippet})}' > {project_root / '.cursor' / 'mcp.json'}"
    )


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a Research OS workspace in the given target directory.

    Usage:
        research-os init /home/user/my-project/
        research-os init /home/user/existing-project/ --interactive
    """
    if args.directory is None:
        if args.name:
            import re
            slug = re.sub(r"[^a-zA-Z0-9_-]", "-", args.name.replace(" ", "-")).lower()
            target_dir = (Path.cwd() / slug).resolve()
        else:
            target_dir = Path.cwd()
    else:
        target_dir = Path(args.directory).resolve()

    project_name = args.name or target_dir.name

    has_existing_data = False
    existing_data_sources = []

    if target_dir.exists():
        # Check if there's existing data to preserve
        for pattern in (
            "*.csv",
            "*.json",
            "*.xlsx",
            "*.txt",
            "*.r",
            "*.py",
            "*.ipynb",
            "*.pdf",
        ):
            existing = list(target_dir.glob(pattern))
            if existing:
                has_existing_data = True
                existing_data_sources.extend(existing[:5])  # Show at most 5 per pattern
                break

        # Also check common subdirectories
        for sub in ("data", "raw_data", "inputs", "csv", "json", "notebooks"):
            if (target_dir / sub).exists():
                has_existing_data = True

        if has_existing_data and not args.force:
            print(f"Found existing files in '{target_dir}'.")
            print("Research OS will NOT overwrite your data.")
            print("Existing data will be symlinked into the workspace.")
            print()

    if has_existing_data and not args.force:
        confirm = input("Proceed with initialization? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    if args.interactive:
        answers = _interactive_questionnaire(target_dir)
        project_name = answers["project_name"]
    else:
        answers = {
            "project_name": project_name,
            "research_question": "",
            "domain": "general",
            "depth": "academic",
            "provider": "openai",
        }

    ide_flags = []
    if args.cursor: ide_flags.append("cursor")
    if args.claude: ide_flags.append("claude")
    if args.antigravity: ide_flags.append("antigravity")
    if args.opencode: ide_flags.append("opencode")
    if args.vscode: ide_flags.append("vscode")
    if args.all_ide: ide_flags.append("all-ide")

    scaffold_minimal_workspace(target_dir, project_name, config_overrides=answers, ide_flags=ide_flags, copy_agents=args.rules)

    # If there's existing data, symlink it into inputs/raw_data/
    if has_existing_data and not args.force:
        inputs_raw = target_dir / "inputs" / "raw_data"
        inputs_raw.mkdir(parents=True, exist_ok=True)
        for src in existing_data_sources:
            link = inputs_raw / src.name
            if not link.exists():
                try:
                    link.symlink_to(src.absolute())
                except OSError:
                    import shutil

                    shutil.copy2(src, link)

    print()
    print("=" * 60)
    print("RESEARCH OS — WORKSPACE CREATED")
    print("=" * 60)
    print(f"  Project: {project_name}")
    print(f"  Location: {target_dir}")
    print()

    _print_tree(target_dir)

    print()
    print("Next steps:")
    print(f"  1. cd {target_dir}")
    print("  2. research-os doctor    # Verify everything is ready")
    print("  3. Open in your AI IDE and paste the MCP config:")
    print()
    _print_mcp_snippet(target_dir)
    print()
    print("  4. Type in the IDE: 'Explore my data'")
    print()

    print(f"Project config: {target_dir / 'inputs' / 'researcher_config.yaml'}")


def cmd_preflight(args: argparse.Namespace) -> None:
    try:
        root = _project_root()
        log_dir = root / "workspace" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "preflight.log"
        
        with open(log_file, "a") as f:
            f.write("=" * 60 + "\n")
            f.write("ENVIRONMENT PREFLIGHT CHECKS\n")
            f.write("=" * 60 + "\n")
            f.write(f"Python Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n")
            f.write(f"Workspace:      {root}\n")
            f.write(f"Config Folder:  {'.os_state/' if (root / '.os_state').exists() else 'MISSING'}\n")
            f.write(f"Inputs Folder:  {'inputs/' if (root / 'inputs').exists() else 'MISSING'}\n")
            f.write("Status:         OK\n")
            
        print(f"Preflight checks logged to {log_file.relative_to(root)}")
    except Exception as e:
        print(f"Preflight error: {e}")
        sys.exit(1)


def cmd_scan(args: argparse.Namespace) -> None:
    try:
        from research_os.utils.data_scale_detector import DataScaleDetector

        root = _project_root()
        inputs_dir = root / "inputs" / "raw_data"
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
    print(
        f"Local overrides: {len([r for r in local_overrides if r.source == 'local_override'])}"
    )
    print("Status: READY")


def cmd_status(args: argparse.Namespace) -> None:
    root = _project_root()
    state = load_state(root)
    hashes = compute_input_hashes(root)
    import re
    workspace_dir = root / "workspace"
    experiments = (
        sorted(p.name for p in workspace_dir.iterdir() if p.is_dir() and re.match(r"^\d{2}_", p.name))
        if workspace_dir.exists()
        else []
    )
    manifest_exists = (root / ".os_state" / "manifest.json").exists()

    print("=" * 60)
    print("RESEARCH PROJECT STATUS")
    print("=" * 60)
    print(f"Workspace: {root}")
    print(f"Current path: {state.get('current_path', 'main')}")
    print(f"Experiment paths: {len(experiments)}")
    for exp in experiments[:8]:
        marker = "*" if exp == state.get("current_path") else "-"
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


def cmd_run(args: argparse.Namespace) -> None:
    print("The `run` command (autonomous execution engine) has been removed.")
    print("Research OS is an MCP-native server — the IDE provides the intelligence.")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run comprehensive pre-flight checks and output READY / NOT READY status."""
    import os
    from research_os.config import settings

    print("=" * 60)
    print("RESEARCH OS — DOCTOR (Pre-Flight Check)")
    print("=" * 60)

    checks: list[dict] = []
    all_ok = True

    def _check(name: str, ok: bool, message: str) -> None:
        nonlocal all_ok
        if not ok:
            all_ok = False
        checks.append({"name": name, "ok": ok, "message": message})

    # ── 1. Python Version ──────────────────────────────────────────
    py_ver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    py_ok = sys.version_info >= (3, 10)
    _check(
        "Python version",
        py_ok,
        f"Python {py_ver} {'✓ (>= 3.10)' if py_ok else '✗ (need 3.10+)'}",
    )

    # ── 2. MCP SDK ─────────────────────────────────────────────────
    try:
        import mcp

        mcp_version = getattr(mcp, "__version__", "unknown")
        _check("MCP SDK", True, f"MCP SDK {mcp_version} found")
    except ImportError:
        _check("MCP SDK", False, "MCP SDK not installed (pip install mcp)")

    # ── 3. Docker ──────────────────────────────────────────────────
    docker_path = shutil.which("docker")
    docker_ok = docker_path is not None
    _check(
        "Docker",
        docker_ok,
        "Docker found"
        if docker_ok
        else "Docker not found (optional for containerized runs)",
    )

    # ── 4. Disk Space ──────────────────────────────────────────────
    try:
        root = _project_root()
        stat = os.statvfs(root)
        free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
        space_ok = free_gb >= 1.0
        _check(
            "Disk space",
            space_ok,
            f"{free_gb:.1f} GB free {'✓' if space_ok else '✗ (need ≥ 1 GB)'}",
        )
    except Exception:
        _check("Disk space", False, "Could not determine free disk space")

    # ── 5. Write Permissions ────────────────────────────────────────
    try:
        test_dir = (root if "root" in dir() else Path.cwd()) / ".doctor_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_write"
        test_file.write_text("ok")
        test_file.unlink()
        test_dir.rmdir()
        _check("Write permissions", True, "Workspace directory is writable")
    except Exception:
        _check("Write permissions", False, "Workspace directory is NOT writable")

    # ── 6. API Keys ─────────────────────────────────────────────────
    llm_ok = bool(settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY)
    _check(
        "LLM API key",
        llm_ok,
        "LLM API key configured"
        if llm_ok
        else "No OPENAI_API_KEY or ANTHROPIC_API_KEY found",
    )

    semantic_ok = bool(settings.SEMANTIC_SCHOLAR_API_KEY)
    _check(
        "Semantic Scholar API key",
        True,
        "Semantic Scholar API key configured"
        if semantic_ok
        else "No key (will use public endpoints)",
    )

    # ── 7. Validate API Keys (lightweight test call) ───────────────
    if llm_ok:
        key_source = "OPENAI" if settings.OPENAI_API_KEY else "ANTHROPIC"
        try:
            if settings.OPENAI_API_KEY:
                import httpx

                r = httpx.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    timeout=10,
                )
                key_valid = r.status_code == 200
            elif settings.ANTHROPIC_API_KEY:
                import httpx

                r = httpx.get(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=10,
                )
                key_valid = r.status_code in (
                    200,
                    400,
                )  # 400 means auth passed but body format may differ
            else:
                key_valid = False
            _check(
                f"API key test ({key_source})",
                key_valid,
                f"{key_source} API key validated"
                if key_valid
                else f"{key_source} API key rejected",
            )
        except Exception as e:
            _check(
                f"API key test ({key_source})",
                False,
                f"Could not validate {key_source} key: {e}",
            )

    # ── 8. Input Files ─────────────────────────────────────────────
    try:
        inputs_dir = root / "inputs"
        if inputs_dir.exists():
            data_files = list(inputs_dir.rglob("*"))
            data_files = [
                f for f in data_files if f.is_file() and not f.name.startswith(".")
            ]
            has_inputs = len(data_files) > 0
            _check(
                "Input files",
                has_inputs,
                f"{len(data_files)} file(s) in inputs/"
                if has_inputs
                else "inputs/ is empty — add data",
            )
        else:
            _check(
                "Input files",
                False,
                "inputs/ directory not found — run 'research-os init'",
            )
    except Exception:
        _check("Input files", False, "Could not check inputs/")

    # ── 9. LaTeX / Pandoc ──────────────────────────────────────────
    latex_ok = shutil.which("pdflatex") is not None
    _check(
        "pdflatex",
        latex_ok,
        "pdflatex found (PDF compilation)"
        if latex_ok
        else "pdflatex not found (Markdown only)",
    )

    pandoc_ok = shutil.which("pandoc") is not None
    _check(
        "pandoc",
        pandoc_ok,
        "pandoc found"
        if pandoc_ok
        else "pandoc not found (manuscript compilation may fail)",
    )

    # ── Print Results ──────────────────────────────────────────────
    print()
    for c in checks:
        icon = "✅" if c["ok"] else "❌"
        print(f"  {icon}  {c['name']:<30} {c['message']}")

    print()
    print("─" * 60)
    if all_ok:
        print("  ✅  STATUS: READY — All checks passed.")
    else:
        n_fail = sum(1 for c in checks if not c["ok"])
        print(f"  ❌  STATUS: NOT READY — {n_fail} check(s) failed.")
        print()
        print("  Action items:")
        for c in checks:
            if not c["ok"]:
                print(f"    • {c['message']}")
    print("─" * 60)
    print()

    if not all_ok:
        sys.exit(1)


def cmd_path_create(args: argparse.Namespace) -> None:
    result = create_path(args.name, root=_project_root())
    if result["status"] == "success":
        print(f"Created path: {result['path_id']}")
        print(f"Directory: {result['experiment_dir']}")
        print(f"Sub-directories created: {len(result.get('paths_created', []))}")
    else:
        print(f"Error: {result['message']}")


def cmd_paths(args: argparse.Namespace) -> None:
    result = list_paths(_project_root())
    if result["status"] == "success":
        print(f"{'Path':<32} {'#':<4} {'Status':<12}")
        print("-" * 54)
        for p in result["paths"]:
            print(
                f"{p['path_id']:<32} "
                f"{p['number']:<4} "
                f"{p['status']:<12}"
            )
    else:
        print(f"Error: {result['message']}")


def cmd_log_decision(args: argparse.Namespace) -> None:
    result = log_decision(
        context=args.context,
        selected=args.selected,
        rationale=args.rationale,
        root=_project_root(),
    )
    print(f"Logged to {result['path']}")


def cmd_save_artifact(args: argparse.Namespace) -> None:
    result = save_artifact(
        args.filename,
        args.content,
        artifact_type=args.artifact_type,
        generated_by=args.generated_by,
        source_script=args.source_script or "",
        root=_project_root(),
    )
    print(f"Saved {result['artifact']}")
    print(f"Metadata {result['metadata']}")


def cmd_trace(args: argparse.Namespace) -> None:
    from research_os.utils.auto_debug import trace_node

    trace_node(args.node_id, _project_root())


def cmd_continue(args: argparse.Namespace) -> None:
    root = _project_root()
    from research_os.state.state_ledger import ResearchLedger

    ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
    state = ledger.get()

    if state.get("phase") != "WAITING_ON_USER":
        print("No plan pending approval.")
        return

    pending = state.get("hitl_pending", {})
    if not args.approve and not args.reject:
        print("=" * 60)
        print("PENDING APPROVAL")
        print("=" * 60)
        print(f"Query : {pending.get('query', '')}")
        print(f"Intent: {pending.get('intent', '')}")
        steps = pending.get("proposed_plan", [])
        if steps:
            print("Proposed plan:")
            for i, step in enumerate(steps, 1):
                print(f"  {i}. {step}")
        choice = input("Approve this workflow? [y/N]: ").strip().lower()
        if choice in {"y", "yes"}:
            args.approve = True
        else:
            args.reject = True

    if args.reject:
        ledger.update(phase="user_rejected", hitl_pending=None)
        print("Plan rejected.")
        return

    if args.approve:
        ledger.update(phase="running", hitl_pending=None)
        print("Plan approved. Resuming workflow...")
        print("The autonomous execution engine has been removed.")
        print(
            "Research OS is an MCP-native server — the IDE provides the intelligence."
        )


def cmd_ingest(args: argparse.Namespace) -> None:
    from research_os.utils.cache_manager import cmd_ingest as _ingest

    _ingest(args)


def cmd_compress(args: argparse.Namespace) -> None:
    """Compress the state ledger using a local LLM to free context window space."""
    try:
        from research_os.state.state_ledger import ResearchLedger

        root = _project_root()
        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
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


def cmd_audit(args: argparse.Namespace) -> None:
    try:
        from research_os.state.state_ledger import ResearchLedger
        from research_os.utils.provenance_mapper import ProvenanceMapper

        root = _project_root()
        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
        mapper = ProvenanceMapper(ledger)

        lineage = mapper.build_lineage(args.result_file)
        print("=" * 60)
        print("PROVENANCE AUDIT TRAIL")
        print("=" * 60)
        print(mapper.format_human_readable(lineage))
    except Exception as e:
        print(f"Audit error: {e}")
        sys.exit(1)


def cmd_start(args: argparse.Namespace) -> None:
    if getattr(args, "daemon", False):
        import subprocess
        import sys

        cmd = [sys.executable, "-m", "research_os.server"]
        if getattr(args, "transport", None):
            cmd.extend(["--transport", args.transport])
        if getattr(args, "workspace", None):
            cmd.extend(["--workspace", args.workspace])
        subprocess.Popen(cmd, start_new_session=True)
        print(f"Started MCP server daemon (transport: {getattr(args, 'transport', 'stdio')})")
        return

    from research_os.server import main as server_main
    import sys

    # Reconstruct sys.argv for server_main() parsing
    sys.argv = [sys.argv[0], "--transport", getattr(args, "transport", "stdio")]
    if getattr(args, "workspace", None):
        sys.argv.extend(["--workspace", args.workspace])

    server_main()


def cmd_env(args: argparse.Namespace) -> None:
    import subprocess

    root = _project_root()
    step_dir = root / "workspace" / args.step
    if not step_dir.exists():
        print(f"Error: Step directory {step_dir} does not exist.")
        sys.exit(1)

    env_dir = step_dir / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    req_file = env_dir / "requirements.txt"

    if args.env_cmd == "freeze":
        print(f"Freezing environment to {req_file}...")
        with open(req_file, "w") as f:
            subprocess.run(
                [sys.executable, "-m", "pip", "freeze"], stdout=f, check=True
            )
        print("Environment frozen successfully.")
    elif args.env_cmd == "restore":
        if not req_file.exists():
            print(f"Error: {req_file} not found. Cannot restore.")
            sys.exit(1)
        print(f"Restoring environment from {req_file}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=True
        )
        print("Environment restored successfully.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description="Research OS - clean workspace CLI",
    )
    parser.add_argument(
        "--depth",
        dest="global_depth",
        choices=DEPTH_CHOICES,
        default="academic",
        help="Default routing depth for commands that use intent context",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser(
        "init", help="Initialize a Research OS workspace in a directory"
    )
    p_init.add_argument(
        "directory", nargs="?", default=None, help="Target directory path (e.g. /home/user/my-project/)"
    )
    p_init.add_argument("--name", help="Project name (defaults to directory name)")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing directory and ignore existing data",
    )
    p_init.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run interactive questionnaire for config",
    )

    p_init.add_argument("--cursor", action="store_true", help="Copy Cursor IDE rules")
    p_init.add_argument("--claude", action="store_true", help="Copy Claude IDE rules")
    p_init.add_argument("--antigravity", action="store_true", help="Copy Antigravity IDE rules")
    p_init.add_argument("--opencode", action="store_true", help="Copy OpenCode IDE rules")
    p_init.add_argument("--vscode", action="store_true", help="Copy VSCode IDE rules")
    p_init.add_argument("--all-ide", action="store_true", help="Copy all IDE rules")
    p_init.add_argument("--rules", action="store_true", help="Copy general AGENTS.md rules")

    sub.add_parser("preflight", help="Run environment preflight checks")
    sub.add_parser("scan", help="Scan inputs and build research map")
    sub.add_parser("setup", help="Verify package assets and local overrides")
    sub.add_parser("status", help="Show clean workspace status")

    p_run = sub.add_parser(
        "run", help="Run the Research OS on a natural language query"
    )
    p_run.add_argument("query", help="The research task to execute")
    p_run.add_argument(
        "--plan-only",
        action="store_true",
        help="Generate the research plan and exit without executing loops.",
    )

    sub.add_parser(
        "doctor", help="Pre-flight check for API keys, LaTeX, and permissions"
    )

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

    p_audit = sub.add_parser(
        "audit", help="Trace the provenance of a result file back to its inputs"
    )
    p_audit.add_argument("result_file", help="Path to the output result file to audit")

    p_compile = sub.add_parser(
        "compile", help="Map-reduce manuscript sections into PDF/HTML via Pandoc"
    )
    p_compile.add_argument(
        "--formats", default="pdf,html", help="Comma-separated formats (e.g., pdf,html)"
    )

    p_trace = sub.add_parser("trace", help="Trace node execution sequence")
    p_trace.add_argument("node_id", help="Node ID to trace")

    p_continue = sub.add_parser("continue", help="Continue a paused workflow")
    p_continue.add_argument(
        "--approve", action="store_true", help="Approve the workflow"
    )
    p_continue.add_argument("--reject", action="store_true", help="Reject the workflow")

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

    p_intent = sub.add_parser(
        "intent", help="Route a query through depth-aware intent routing"
    )
    p_intent.add_argument("query")
    p_intent.add_argument("--depth", choices=DEPTH_CHOICES, default=None)

    p_path_create = sub.add_parser("path-create", help="Create a numbered experiment path in workspace/")
    p_path_create.add_argument("name")
    sub.add_parser("paths", help="List experiment paths")

    p_decision = sub.add_parser(
        "log-decision", help="Append to the active experiment decisions.yaml"
    )
    p_decision.add_argument("--context", required=True)
    p_decision.add_argument("--selected", required=True)
    p_decision.add_argument("--rationale", required=True)
    p_artifact = sub.add_parser(
        "save-artifact", help="Save artifact with sibling .meta.yaml"
    )
    p_artifact.add_argument("filename")
    p_artifact.add_argument("--content", required=True)
    p_artifact.add_argument(
        "--artifact-type",
        choices=["artifact", "analysis", "figure", "table"],
        default="artifact",
    )
    p_artifact.add_argument("--generated-by", default="cli")
    p_artifact.add_argument("--source-script")
    p_start = sub.add_parser("start", help="Boot the MCP server")
    p_start.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p_start.add_argument("--port", type=int, default=8080)
    p_start.add_argument(
        "--daemon", action="store_true", help="Run server in the background"
    )
    p_start.add_argument("--workspace", type=str, help="Workspace directory to start the server in")

    p_env = sub.add_parser("env", help="Manage reproducible environments per step")
    env_sub = p_env.add_subparsers(dest="env_cmd", required=True)

    p_env_freeze = env_sub.add_parser("freeze", help="Snapshot current environment")
    p_env_freeze.add_argument(
        "step", help="Experiment step folder name (e.g., 01_baseline)"
    )

    p_env_restore = env_sub.add_parser(
        "restore", help="Restore environment from a step"
    )
    p_env_restore.add_argument(
        "step", help="Experiment step folder name (e.g., 01_baseline)"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        args.command = "chat"

    args.depth = getattr(args, "depth", None) or args.global_depth

    commands = {
        "chat": lambda a: __import__("research_os.chat").chat.start_chat_loop(),
        "init": cmd_init,
        "run": cmd_run,
        "doctor": cmd_doctor,
        "preflight": cmd_preflight,
        "scan": cmd_scan,
        "setup": cmd_setup,
        "status": cmd_status,
        "compress": cmd_compress,
        "audit": cmd_audit,
        "agent": cmd_agents,
        "agents": lambda a: cmd_agents(argparse.Namespace(name=None)),
        "skill": cmd_skills,
        "skills": lambda a: cmd_skills(argparse.Namespace(name=None)),
        "workflow": cmd_workflow,
        "continue": cmd_continue,
        "trace": cmd_trace,
        "compile": cmd_compile,
        "ingest": cmd_ingest,
        "path-create": cmd_path_create,
        "paths": cmd_paths,
        "log-decision": cmd_log_decision,
        "save-artifact": cmd_save_artifact,
        "start": cmd_start,
        "env": cmd_env,
    }
    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
