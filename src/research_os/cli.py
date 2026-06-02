#!/usr/bin/env python3
"""Research OS CLI.

Three commands, by design:

    research-os init [dir] [--name X] [--ide all|cursor|claude|...]
        Scaffold a Research OS workspace. Interactive by default; pass
        ``--yes`` (or pipe stdin) for a non-interactive one-shot.

    research-os ide add|remove|list <name>
        Wire / unwire / inspect AI IDE MCP configs without re-running
        ``init`` (so existing data + state is never touched).

    research-os start [--workspace .]
        Run the MCP server. Your AI IDE connects to this.

All real research work happens by talking to the AI in the IDE.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from research_os import __version__
from research_os.project_ops import scaffold_minimal_workspace
from research_os.utils.asset_manager import AssetManager  # noqa: F401  (re-export)

VALID_IDES = (
    "cursor", "claude", "antigravity", "opencode", "vscode",
    "windsurf", "continue", "aider",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ide_choice(args_ide: str | None) -> list[str]:
    if not args_ide or args_ide == "all":
        return list(VALID_IDES)
    parts = [p.strip() for p in args_ide.split(",") if p.strip()]
    invalid = [p for p in parts if p not in VALID_IDES]
    if invalid:
        print(f"  ⚠  Unknown IDE(s): {', '.join(invalid)}. Falling back to 'claude'.")
        return ["claude"]
    return parts


def _detect_existing_data(target_dir: Path) -> list[Path]:
    found: list[Path] = []
    if not target_dir.exists():
        return found
    for pattern in ("*.csv", "*.tsv", "*.json", "*.jsonl", "*.xlsx", "*.xls",
                    "*.parquet", "*.feather", "*.pdf"):
        found.extend(p for p in list(target_dir.glob(pattern))[:5]
                     if not p.is_symlink())
    return found


def _link_inputs(target_dir: Path, sources: list[Path]) -> list[str]:
    linked: list[str] = []
    inputs_raw = target_dir / "inputs" / "raw_data"
    inputs_raw.mkdir(parents=True, exist_ok=True)
    for src in sources:
        link = inputs_raw / src.name
        if link.exists():
            continue
        try:
            link.symlink_to(src.absolute())
            linked.append(src.name)
        except OSError:
            try:
                shutil.copy2(src, link)
                linked.append(src.name)
            except OSError as exc:
                print(f"  ⚠  Could not link {src.name}: {exc}")
    return linked


def _save_linked_meta(target_dir: Path, linked: list[str]) -> None:
    try:
        from research_os.project_ops import load_state, save_state
        state = load_state(target_dir)
        linked_meta = state.setdefault("linked_external_data", [])
        for name in linked:
            if name not in linked_meta:
                linked_meta.append(name)
        save_state(target_dir, state)
    except Exception:
        pass


def _count_scaffold(target_dir: Path) -> dict:
    files = 0
    dirs = 0
    for p in target_dir.rglob("*"):
        if p.is_dir():
            dirs += 1
        elif p.is_file():
            files += 1
    return {"files": files, "dirs": dirs}


def _copy_attachments(target_dir: Path, paths: list[Path]) -> list[Path]:
    """Copy attachments into inputs/. PDFs → literature/, anything else → context/.
    Returns the list of destination paths actually written.

    Refuses to copy symlinks whose target escapes the user's home directory —
    a paper.pdf → /etc/passwd trick would otherwise be silently dragged in.
    """
    from research_os import wizard  # local import to avoid cycle
    from research_os.wizard import IMAGE_EXTENSIONS  # noqa: F401

    lit_dir = target_dir / "inputs" / "literature"
    ctx_dir = target_dir / "inputs" / "context"
    lit_dir.mkdir(parents=True, exist_ok=True)
    ctx_dir.mkdir(parents=True, exist_ok=True)
    home = Path.home().resolve()
    written: list[Path] = []
    for src in paths:
        # Reject symlinks that point outside the user's home directory.
        if src.is_symlink():
            try:
                real_src = src.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                wizard.warn(f"Skipping {src.name}", f"unresolvable symlink: {exc}")
                continue
            if home != real_src and home not in real_src.parents:
                wizard.warn(
                    f"Skipping {src.name}",
                    f"symlink target escapes home directory ({real_src})",
                )
                continue

        suffix = src.suffix.lower()
        dest_dir = lit_dir if suffix == ".pdf" else ctx_dir
        dest = dest_dir / src.name
        # Don't clobber.
        if dest.exists() and dest.samefile(src):
            continue
        if dest.exists():
            stem, ext = dest.stem, dest.suffix
            i = 1
            while (dest_dir / f"{stem}_{i}{ext}").exists():
                i += 1
            dest = dest_dir / f"{stem}_{i}{ext}"
        try:
            shutil.copy2(src, dest)
            written.append(dest)
        except OSError as exc:
            print(f"  ⚠  Could not copy {src.name}: {exc}")
    return written


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold a Research OS workspace. Interactive by default."""
    from research_os import wizard
    if getattr(args, "no_color", False):
        wizard.disable_color()

    interactive = wizard.should_run_wizard(args)

    if interactive:
        result = wizard.run_wizard(args)
        if not wizard.show_summary_and_confirm(result):
            print()
            print(f"  {wizard._C.YELLOW}Cancelled — no changes made.{wizard._C.RESET}")
            sys.exit(0)
        _execute(result, run_preflight_repo=args.preflight)
        return

    # ── Non-interactive path (legacy / scripted) ────────────────────────
    if args.name and args.directory is None:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", args.name.replace(" ", "-")).lower()
        target_dir = (Path.cwd() / slug).resolve()
        created_new_folder = not target_dir.exists()
    elif args.directory:
        target_dir = Path(os.path.expanduser(args.directory)).resolve()
        created_new_folder = not target_dir.exists()
    else:
        target_dir = Path.cwd().resolve()
        created_new_folder = False

    project_name = args.name or target_dir.name
    already_initialized = (target_dir / ".os_state").exists()
    if already_initialized and not args.force:
        print(f"  ✗ Workspace already exists at: {target_dir}")
        print("  Pass --force to re-scaffold (preserves your data and config).")
        sys.exit(1)

    ide_flags = _ide_choice(args.ide)
    raw_data_sources = (_detect_existing_data(target_dir)
                        if (target_dir.exists() and not args.force) else [])

    # Multi-question support: take args.questions if given; else fall back
    # to the singular args.question.
    questions = list(getattr(args, "questions", None) or [])
    if args.question and args.question not in questions:
        questions.insert(0, args.question)

    result = wizard.WizardResult(
        target_dir=target_dir,
        project_name=project_name,
        domain=args.domain or "",
        question=questions[0] if questions else (args.question or ""),
        questions=questions,
        ides=ide_flags,
        force=args.force,
        run_verify=True,
        start_server=False,
        create_dir_needed=created_new_folder,
        detected_inputs=raw_data_sources,
    )
    _execute(result, run_preflight_repo=args.preflight, quiet_banner=True)


def _execute(r, run_preflight_repo: bool = False, quiet_banner: bool = False) -> None:
    """Actually scaffold + post-process. Shared by interactive + non-interactive."""
    from research_os import collab, wizard
    from research_os.verify import verify_workspace, summarize

    target_dir: Path = r.target_dir

    already_initialized = (target_dir / ".os_state").exists()
    if already_initialized and not r.force:
        wizard.fail(f"Workspace already exists: {target_dir}",
                    "Pass --force to re-scaffold (data is preserved).")
        sys.exit(1)

    if not quiet_banner:
        print()
        print(f"  {wizard._C.GREY}{wizard._hr('━')}{wizard._C.RESET}")
        print(f"  {wizard._C.BOLD}Scaffolding workspace…{wizard._C.RESET}")
        print(f"  {wizard._C.GREY}{wizard._hr('━')}{wizard._C.RESET}")
        print()

    # 1. Resolve author identity BEFORE scaffold so we can pass to config.
    author = collab.whoami(target_dir if target_dir.exists() else None)

    # 2. Scaffold.
    config_overrides = {
        "project_name": r.project_name,
        "domain": r.domain,
        "research_question": r.question,
        "research_questions": list(getattr(r, "questions", []) or []),
        "authors": [author.as_dict()],
        "api_keys": dict(getattr(r, "api_keys", {}) or {}),
        "model_profile": getattr(r, "model_profile", "medium"),
    }
    scaffold_minimal_workspace(
        target_dir,
        r.project_name,
        config_overrides=config_overrides,
        ide_flags=r.ides,
        copy_agents=True,
    )
    wizard.ok("Workspace scaffolded", str(target_dir))

    # 3. Link any pre-existing input files the user agreed to.
    linked: list[str] = []
    if r.detected_inputs:
        linked = _link_inputs(target_dir, r.detected_inputs)
        if linked:
            _save_linked_meta(target_dir, linked)
            wizard.ok(f"Linked {len(linked)} data file(s)",
                      f"→ inputs/raw_data/  ({', '.join(linked[:3])}{'…' if len(linked) > 3 else ''})")

    # 4. Copy attachments (images, screenshots, PDFs).
    attachment_results = []
    if getattr(r, "pending_attachments", None):
        attachment_results = _copy_attachments(target_dir, r.pending_attachments)
        if attachment_results:
            wizard.ok(f"Copied {len(attachment_results)} attachment(s)",
                      "→ inputs/context | inputs/literature")

    # 5. Save any pasted notes captured during Step 5.
    note_results = []
    if getattr(r, "pending_notes", None):
        from research_os.inputs.paste import save as save_note
        ctx_dir = target_dir / "inputs" / "context"
        for source_hint, blob in r.pending_notes:
            try:
                res = save_note(blob, ctx_dir, source_hint=source_hint)
                note_results.append(res)
            except Exception as e:
                wizard.warn(f"Could not save note ({source_hint})", str(e))
        if note_results:
            wizard.ok(f"Saved {len(note_results)} pasted note(s)", "→ inputs/context/")

    # 6. Download any pasted paper URLs / DOIs / arXiv IDs (with per-paper progress).
    paper_results = []
    if getattr(r, "pending_papers", None):
        from research_os.inputs.papers import fetch_one
        lit_dir = target_dir / "inputs" / "literature"
        total = len(r.pending_papers)
        wizard.info(f"Fetching {total} paper(s) — may take a moment…")
        for i, token in enumerate(r.pending_papers, 1):
            print(f"      {wizard._C.GREY}[{i}/{total}] {token[:60]}…{wizard._C.RESET}", end="", flush=True)
            res = fetch_one(token, lit_dir)
            paper_results.append(res)
            if res.ok:
                size_kb = res.bytes_written / 1024
                print(f"\r      {wizard._C.GREEN}✓{wizard._C.RESET} "
                      f"[{i}/{total}] {token[:60]}  "
                      f"{wizard._C.GREY}→ {res.path.name if res.path else ''} "
                      f"({size_kb:.0f} KB){wizard._C.RESET}")
            else:
                print(f"\r      {wizard._C.YELLOW}✗{wizard._C.RESET} "
                      f"[{i}/{total}] {token[:60]}  "
                      f"{wizard._C.GREY}— {res.error}{wizard._C.RESET}")

    # 7. Smoke check.
    verify_summary = None
    if r.run_verify:
        results = verify_workspace(target_dir, ides=r.ides)
        passed, failed, summary = summarize(results)
        if failed == 0:
            wizard.ok("Smoke check passed", summary)
            verify_summary = summary
        else:
            wizard.warn("Smoke check found issues", summary)
            for name, ok, detail in results:
                if not ok:
                    wizard.fail(f"  · {name}", detail)

    # 8. Optionally run the repo's preflight (dev mode only).
    if run_preflight_repo:
        _run_repo_preflight()

    # 9. Optional: kick off the MCP server in the background.
    if r.start_server:
        _try_start_server(target_dir)

    # 10. Record the contributor row.
    try:
        collab.log_action(target_dir, author,
                          "Initialized workspace" if not already_initialized
                          else "Re-scaffolded workspace (--force)")
    except OSError:
        pass

    # 11. Final report.
    stats = _count_scaffold(target_dir)
    wizard.show_done_card(r, stats, verify_summary,
                          note_results=note_results,
                          paper_results=paper_results,
                          attachment_results=attachment_results,
                          author=author)


def _run_repo_preflight() -> None:
    from research_os import wizard
    here = Path(__file__).resolve()
    for parent in (here.parent.parent.parent, *here.parents):
        candidate = parent / "scripts" / "preflight.py"
        if candidate.exists():
            print()
            wizard.info(f"Running repo preflight: {candidate.relative_to(parent)}")
            try:
                rc = subprocess.run(
                    [sys.executable, str(candidate)],
                    cwd=str(parent),
                    timeout=60,
                ).returncode
            except (OSError, subprocess.TimeoutExpired) as e:
                wizard.warn(f"Preflight didn't finish: {e}")
                return
            if rc == 0:
                wizard.ok("Repo preflight passed")
            else:
                wizard.warn(f"Repo preflight exited {rc}")
            return


def _try_start_server(target_dir: Path) -> None:
    from research_os import wizard

    binary = shutil.which("research-os")
    if not binary:
        wizard.warn("research-os not found on PATH",
                    "Skipping server start — open your IDE; it will launch the server.")
        return

    log_path = target_dir / ".os_state" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["RESEARCH_OS_WORKSPACE"] = str(target_dir)
    try:
        with open(log_path, "ab") as logf:
            proc = subprocess.Popen(
                [binary, "start"],
                stdout=logf,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        wizard.ok(f"MCP server started (PID {proc.pid})",
                  f"logs → {log_path.relative_to(target_dir)}")
    except OSError as e:
        wizard.warn(f"Could not start server: {e}",
                    "Run `research-os start` manually if your IDE doesn't auto-launch it.")


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def cmd_start(args: argparse.Namespace) -> None:
    from research_os.server import main as server_main

    if args.workspace:
        workspace = Path(args.workspace).resolve()
        if not (workspace / ".os_state").exists():
            print(f"  ⚠  --workspace points at a non-RO directory: {workspace}")
            print("  Run 'research-os init' there first, or omit --workspace.")
        sys.argv = [sys.argv[0], "--transport", args.transport,
                    "--workspace", str(workspace)]
    else:
        sys.argv = [sys.argv[0], "--transport", args.transport]

    server_main()


# ---------------------------------------------------------------------------
# ide subcommand
# ---------------------------------------------------------------------------


def _find_workspace_root(start: Path | None = None) -> Path | None:
    p = (start or Path.cwd()).resolve()
    for parent in (p, *p.parents):
        if (parent / ".os_state").exists():
            return parent
    return None


def cmd_ide(args: argparse.Namespace) -> None:
    """Inspect / add / remove AI IDE MCP configs in the current workspace."""
    from research_os import collab, wizard
    if getattr(args, "no_color", False):
        wizard.disable_color()

    root = _find_workspace_root()
    if not root:
        wizard.fail("Not inside a Research OS workspace",
                    "Run `research-os init` first, or cd into a project.")
        sys.exit(1)

    action = args.action

    if action == "list":
        wired = collab.list_wired_ides(root)
        print()
        print(f"  {wizard._C.BOLD}AI IDE configs in {root}{wizard._C.RESET}")
        print(f"  {wizard._C.GREY}{wizard._hr()}{wizard._C.RESET}")
        for ide, present in wired.items():
            mark = (f"{wizard._C.GREEN}✓{wizard._C.RESET}" if present
                    else f"{wizard._C.GREY}·{wizard._C.RESET}")
            primary = collab.IDE_FILES[ide][0]
            line = f"  {mark} {ide:<14}{wizard._C.GREY}{primary}{wizard._C.RESET}"
            if not present:
                line += f"  {wizard._C.DIM}(run `research-os ide add {ide}` to wire){wizard._C.RESET}"
            print(line)
        print()
        return

    if action in ("add", "remove"):
        names = args.names or []
        if not names:
            wizard.fail(f"`research-os ide {action}` needs at least one IDE name",
                        f"e.g. `research-os ide {action} cursor`")
            sys.exit(1)
        unknown = [n for n in names if n not in collab.IDE_FILES]
        if unknown:
            wizard.fail(f"Unknown IDE(s): {', '.join(unknown)}",
                        f"Choose from: {', '.join(sorted(collab.IDE_FILES))}")
            sys.exit(1)

        author = collab.whoami(root)
        for ide in names:
            if action == "add":
                created = collab.add_ide(root, ide)
                if created:
                    wizard.ok(f"Wired {ide}", f"{', '.join(created)}")
                    collab.log_action(root, author, f"Added IDE config: {ide}")
                else:
                    wizard.warn(f"{ide} already wired", "no changes made")
            else:  # remove
                removed = collab.remove_ide(root, ide)
                if removed:
                    wizard.ok(f"Removed {ide} config", ", ".join(removed))
                    collab.log_action(root, author, f"Removed IDE config: {ide}")
                else:
                    wizard.warn(f"{ide} was not wired", "no changes made")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description=(
            "Research OS — an MCP-native research operating system.\n\n"
            "Three commands:\n"
            "  research-os init    scaffold a workspace ready for any AI IDE\n"
            "  research-os ide     add / remove / list AI IDE MCP configs\n"
            "  research-os start   run the MCP server (your IDE auto-launches it)\n\n"
            "Research OS does NOT manage LLM provider keys. Your AI client\n"
            "(Claude Code, OpenCode, Antigravity, Cursor, Claude Desktop,\n"
            "VS Code, Windsurf, Continue, Aider, ...) owns model access.\n\n"
            "Documentation: docs/START.md · docs/RESEARCHER_GUIDE.md ·\n"
            "               docs/USE_CASES.md · docs/TOOLS.md · docs/PROTOCOLS.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version=f"research-os {__version__}")
    sub = parser.add_subparsers(dest="command")

    # ── init ────────────────────────────────────────────────────────────
    p_init = sub.add_parser(
        "init",
        help="Initialise a Research OS workspace (interactive by default).",
        description=(
            "Scaffold a workspace directory ready for AI-driven research.\n\n"
            "By default launches a 6-step interactive wizard with arrow-key\n"
            "navigation, multi-select IDE wiring, paper auto-download, and\n"
            "a paste-helper for notes / Slack threads / emails. Skip the\n"
            "wizard with --yes, or by piping stdin (CI / scripts).\n\n"
            "Examples:\n"
            "  research-os init                              # interactive wizard\n"
            "  research-os init my-project --yes             # one-shot, no prompts\n"
            "  research-os init my-project --name 'Cohort'   # explicit name\n"
            "  research-os init . --force                    # re-scaffold an existing folder\n"
            "  research-os init --ide cursor,claude          # only those two IDEs\n"
            "  research-os init --no-color                   # disable ANSI styling"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_init.add_argument("directory", nargs="?", default=None,
                        help="Target directory (default: current directory).")
    p_init.add_argument("--name", help="Project name (default: directory name).")
    p_init.add_argument("--domain",
                        help="Domain hint (clinical / nlp / genomics / ...). Optional.")
    p_init.add_argument("--question",
                        help="Initial research question. Refined later by the AI.")
    p_init.add_argument("--questions", action="append", default=None,
                        help="Add a research question (repeatable). Builds a list.")
    p_init.add_argument("--ide", default="all",
                        help="IDE(s) to wire up: 'all' or a comma-separated list.")
    p_init.add_argument("--force", action="store_true",
                        help="Re-scaffold even if the workspace already exists.")
    p_init.add_argument("-y", "--yes", action="store_true",
                        help="Skip the wizard and use defaults + provided flags.")
    p_init.add_argument("--non-interactive", dest="no_interactive", action="store_true",
                        help="Alias for --yes.")
    p_init.add_argument("--no-color", action="store_true",
                        help="Disable ANSI styling. Auto-disabled when NO_COLOR is set.")
    p_init.add_argument("--preflight", action="store_true",
                        help="After scaffolding, run the repo's preflight (dev only).")

    # ── ide ─────────────────────────────────────────────────────────────
    p_ide = sub.add_parser(
        "ide",
        help="Add / remove / list AI IDE MCP configs in this workspace.",
        description=(
            "Manage which AI IDEs are wired up in the current workspace —\n"
            "without re-running `research-os init` (which would re-scaffold\n"
            "the whole tree). Walks up the directory tree for `.os_state/`\n"
            "to find the workspace.\n\n"
            "Examples:\n"
            "  research-os ide list                # show which IDEs are wired\n"
            "  research-os ide add cursor          # add Cursor MCP config\n"
            "  research-os ide add windsurf aider  # add several at once\n"
            "  research-os ide remove opencode     # remove OpenCode config"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ide.add_argument("action", choices=["list", "add", "remove"],
                       help="What to do.")
    p_ide.add_argument("names", nargs="*",
                       help="IDE names (only required for add / remove).")
    p_ide.add_argument("--no-color", action="store_true",
                       help="Disable ANSI styling.")

    # ── start ───────────────────────────────────────────────────────────
    p_start = sub.add_parser(
        "start",
        help="Start the Research OS MCP server (global — one server, many projects).",
        description=(
            "Run the Research OS MCP server. Your AI IDE connects via stdio.\n"
            "Install once, share across all your projects. The active project\n"
            "is resolved per-request via $RESEARCH_OS_WORKSPACE, or by walking\n"
            "the CWD up to find `.os_state/`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_start.add_argument("--workspace", default=None,
                        help="(Back-compat) Pin this server to a specific workspace path.")
    p_start.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="MCP transport (default: stdio).")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "ide":
        cmd_ide(args)
    elif args.command == "start":
        cmd_start(args)
    else:
        parser.print_help()
        print()
        print("  Tip: 'research-os init' to scaffold, then open your IDE and chat with the AI.")


if __name__ == "__main__":
    main()
