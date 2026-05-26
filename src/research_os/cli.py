#!/usr/bin/env python3
"""Research OS CLI.

Two commands only:
    init   — Scaffold a new Research OS workspace in a directory.
    start  — Start the MCP server (all AI tooling goes through MCP, not CLI).

Everything else — analysis, literature search, experiment creation,
synthesis — is done by the AI via MCP tools. The researcher just talks to
the AI in their IDE.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.utils.asset_manager import AssetManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_tree(path: Path, prefix: str = "", is_root: bool = True) -> None:
    """Print a user-friendly directory tree."""
    EXPLANATIONS = {
        "inputs": "Your original, immutable research data (never modified by tools)",
        "raw_data": "Original data files — CSV, Excel, PDF, etc.",
        "literature": "Downloaded papers",
        "context": "Background notes and prior results",
        "workspace": "Active analysis area — experiments live here",
        "synthesis": "Final paper and consolidated outputs",
        "docs": "Research question and overview documents",
        "environment": "Dependency snapshots for reproducibility",
        ".os_state": "Research OS internal state (do not edit manually)",
    }
    entries = sorted(path.iterdir()) if path.exists() else []
    for i, entry in enumerate(entries):
        if entry.name.startswith(".") and entry.name not in (".os_state", ".cursor", ".antigravity"):
            continue
        if entry.name in ("__pycache__", ".git"):
            continue
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        name_display = entry.name + "/" if entry.is_dir() else entry.name
        explanation = EXPLANATIONS.get(entry.name)
        if explanation:
            print(f"{prefix}{connector}{name_display}  ← {explanation}")
        else:
            print(f"{prefix}{connector}{name_display}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _print_tree(entry, prefix + extension, is_root=False)


def _interactive_questionnaire(target_dir: Path) -> dict:
    print("  Let's set up your research project.")
    print("  (Press Enter to accept defaults.)")
    print()
    project_name = input(f"  Project name [{target_dir.name}]: ").strip() or target_dir.name
    research_question = input("  Research question (optional): ").strip()
    print("  Domain:")
    print("    1. General / Social Sciences")
    print("    2. Clinical / Medical Research")
    print("    3. Environmental / Epidemiology")
    print("    4. Machine Learning / AI")
    print("    5. Other")
    domain_map = {
        "1": "general", "2": "clinical", "3": "environmental",
        "4": "machine_learning", "5": "other",
    }
    domain_choice = input("  Domain [1]: ").strip() or "1"
    domain = domain_map.get(domain_choice, "general")
    depth_choice = input("  Analysis depth — quick/standard/deep [standard]: ").strip() or "standard"
    return {
        "project_name": project_name,
        "research_question": research_question,
        "domain": domain,
        "depth": depth_choice,
    }


def _print_mcp_snippet(project_root: Path, ide: str) -> None:
    """Print the MCP JSON snippet for the chosen IDE."""
    snippet = {
        "research-os": {
            "command": "research-os",
            "args": ["start"],
            "env": {"RESEARCH_OS_WORKSPACE": str(project_root)},
        }
    }
    ide_labels = {
        "cursor":      "Cursor → paste into .cursor/mcp.json",
        "claude":      "Claude → paste into claude_desktop_config.json",
        "vscode":      "VS Code → paste into .vscode/mcp.json",
        "antigravity": "Antigravity → paste into .antigravity/mcp.json",
        "opencode":    "OpenCode → paste into opencode.json",
    }
    label = ide_labels.get(ide, "IDE → paste into your MCP config")
    print(f"\n  ┌─ {label} {'─' * max(0, 68 - len(label))}┐")
    for line in json.dumps({"mcpServers": snippet}, indent=2).splitlines():
        print(f"  │ {line:<70} │")
    print(f"  └{'─' * 72}┘\n")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold a Research OS workspace."""
    # Resolve target directory
    if args.name and args.directory is None:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", args.name.replace(" ", "-")).lower()
        target_dir = (Path.cwd() / slug).resolve()
        created_new_folder = not target_dir.exists()
    elif args.directory:
        target_dir = Path(args.directory).resolve()
        created_new_folder = not target_dir.exists()
    else:
        target_dir = Path.cwd().resolve()
        created_new_folder = False

    already_initialized = (target_dir / ".os_state").exists()
    if already_initialized and not args.force:
        print(f"  Workspace already exists at '{target_dir}'.")
        print("  Use --force to re-scaffold (preserves your data).")
        print()

    # Gather config
    if args.interactive:
        answers = _interactive_questionnaire(target_dir)
        project_name = answers.pop("project_name")
    else:
        project_name = args.name or target_dir.name
        answers = {"domain": "general", "depth": "standard"}

    # Map --ide to flags
    ide_map = {
        "cursor": ["cursor"], "claude": ["claude"], "vscode": ["vscode"],
        "antigravity": ["antigravity"], "opencode": ["opencode"],
        "all": ["cursor", "claude", "vscode", "antigravity", "opencode"],
    }
    ide_flags = ide_map.get(args.ide, ["cursor"])

    # Detect and symlink existing data
    linked: list[str] = []
    raw_data_sources: list[Path] = []
    if target_dir.exists() and not args.force:
        for pattern in ("*.csv", "*.json", "*.xlsx", "*.xls", "*.txt", "*.pdf"):
            raw_data_sources.extend(list(target_dir.glob(pattern))[:5])

    scaffold_minimal_workspace(
        target_dir,
        project_name,
        config_overrides=answers,
        ide_flags=ide_flags,
        copy_agents=args.rules,
    )

    # Symlink any pre-existing data files into inputs/raw_data/
    if raw_data_sources:
        inputs_raw = target_dir / "inputs" / "raw_data"
        inputs_raw.mkdir(parents=True, exist_ok=True)
        for src in raw_data_sources:
            link = inputs_raw / src.name
            if not link.exists():
                try:
                    link.symlink_to(src.absolute())
                    linked.append(src.name)
                except OSError:
                    try:
                        shutil.copy2(src, link)
                        linked.append(src.name)
                    except OSError as exc:
                        print(f"  ⚠  Could not link {src.name}: {exc}")

    # Ledger record
    if linked:
        try:
            from research_os.project_ops import load_state, save_state
            state = load_state(target_dir)
            state.setdefault("linked_external_data", [])
            for name in linked:
                if name not in state["linked_external_data"]:
                    state["linked_external_data"].append(name)
            save_state(target_dir, state)
        except Exception:
            pass

    # Print result
    print()
    print("=" * 60)
    print("  RESEARCH OS — WORKSPACE READY")
    print("=" * 60)
    print(f"  Project  : {project_name}")
    print(f"  Location : {target_dir}")
    if linked:
        print(f"  Linked   : {', '.join(linked)}")
    print()

    file_count = len([f for f in target_dir.rglob("*") if f.is_file()])
    if created_new_folder or file_count < 25:
        _print_tree(target_dir)

    print()
    print("  Next steps:")
    n = 1
    if created_new_folder:
        print(f"  {n}. cd {target_dir}")
        n += 1
    print(f"  {n}. Paste the MCP config into your IDE:")
    _print_mcp_snippet(target_dir, args.ide)
    n += 1
    print(f"  {n}. Open your IDE, point it at this folder, and just start talking.")
    print(f"     The AI will read your data and guide you through the research.")
    print()
    print(f"  Config   : {target_dir / 'inputs' / 'researcher_config.yaml'}")
    print()


def cmd_start(args: argparse.Namespace) -> None:
    """Start the Research OS MCP server.

    The server is what the AI IDE connects to via MCP. It exposes all
    research tools — data sampling, literature search, experiment creation,
    synthesis, etc. The researcher never calls these tools directly.
    """
    workspace = Path(getattr(args, "workspace", None) or ".").resolve()
    if not getattr(args, "workspace", None):
        try:
            workspace = AssetManager.find_project_root()
        except Exception:
            workspace = Path.cwd()

    if not (workspace / ".os_state").exists():
        print(f"  ✗ Not a Research OS workspace: {workspace}")
        print("  Run 'research-os init' first.")
        sys.exit(1)

    from research_os.server import main as server_main
    sys.argv = [sys.argv[0], "--transport", getattr(args, "transport", "stdio")]
    if args.workspace:
        sys.argv.extend(["--workspace", args.workspace])
    server_main()


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description=(
            "Research OS — MCP-native research assistant.\n\n"
            "Two commands: 'init' to set up a workspace, 'start' to run the MCP server.\n"
            "All research work (analysis, literature, writing) is done by AI via MCP."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # ── init ──────────────────────────────────────────────────────────────────
    p_init = sub.add_parser(
        "init",
        help="Initialize a Research OS workspace",
        description="Scaffold a workspace directory ready for AI-driven research.",
    )
    p_init.add_argument(
        "directory", nargs="?", default=None,
        help="Target directory (default: current directory)",
    )
    p_init.add_argument("--name", help="Project name (default: directory name)")
    p_init.add_argument(
        "--interactive", "-i", action="store_true",
        help="Interactive questionnaire to set research question and domain",
    )
    p_init.add_argument(
        "--rules", action="store_true",
        help="Copy AGENTS.md into the workspace for AI rules",
    )
    p_init.add_argument(
        "--force", action="store_true",
        help="Re-scaffold even if workspace already exists",
    )
    p_init.add_argument(
        "--ide",
        choices=["cursor", "claude", "vscode", "antigravity", "opencode", "all"],
        default="cursor",
        help="IDE to show MCP config snippet for (default: cursor)",
    )

    # ── start ─────────────────────────────────────────────────────────────────
    p_start = sub.add_parser(
        "start",
        help="Start the Research OS MCP server",
        description=(
            "Start the MCP server. Connect your AI IDE to this server to enable\n"
            "all research tools. You never run research commands directly — the AI does."
        ),
    )
    p_start.add_argument(
        "--workspace", type=str, default=None,
        help="Path to Research OS workspace (default: auto-detect from current directory)",
    )
    p_start.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="MCP transport (default: stdio, which most IDEs use)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "start":
        cmd_start(args)
    else:
        parser.print_help()
        print()
        print("  Tip: Run 'research-os init' to create a workspace, then open")
        print("  your AI IDE and just start talking — no Research OS commands needed.")
