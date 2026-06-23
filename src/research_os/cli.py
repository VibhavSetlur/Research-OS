#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""Research OS CLI.

Four commands, by design:

    research-os init [dir] [--name X] [--ide all|cursor|claude|...]
        Scaffold a Research OS workspace. Interactive by default; pass
        ``--yes`` (or pipe stdin) for a non-interactive one-shot.

    research-os ide add|remove|list <name>
        Wire / unwire / inspect AI IDE MCP configs without re-running
        ``init`` (so existing data + state is never touched).

    research-os start [--workspace .]
        Run the MCP server. Your AI IDE connects to this.

    research-os doctor [--verbose|--workspace-only|--json]
        Diagnose install + workspace health (python version, conda env,
        version consistency, pack registration, embeddings freshness,
        IDE wiring, disk usage, git cleanliness, etc.). Returns exit
        code 0 (clean), 1 (warnings), or 2 (failures).

    research-os completion bash|zsh|fish
        Print a sourceable shell-completion script. Install with
        ``eval "$(research-os completion zsh)"`` (or your shell's
        equivalent) in your shell rc file.

All real research work happens by talking to the AI in the IDE.
"""

from __future__ import annotations

import argparse
import json
import os
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

# Shell-completion choice list for the `init --ide` flag.
# Includes the two sentinels ("all", "none") so argcomplete can suggest them.
IDE_CHOICES_FOR_COMPLETION = (*VALID_IDES, "all", "none")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _supports_utf8() -> bool:
    """True when stdout encoding looks like UTF-* (else ASCII fallback)."""
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


def _glyph(unicode_char: str, ascii_fallback: str) -> str:
    """Return the unicode glyph when stdout is UTF-*, else the ASCII fallback.

    Used so messages render correctly on terminals whose encoding doesn't
    cover ✓/✗/⚠ (e.g. C locale, Windows cp1252, some piped contexts).
    """
    return unicode_char if _supports_utf8() else ascii_fallback


def _check() -> str:
    return _glyph("✓", "[+]")


def _cross() -> str:
    return _glyph("✗", "[x]")


def _warn_glyph() -> str:
    return _glyph("⚠", "[!]")


def _ide_choice(args_ide: str | None) -> list[str]:
    if not args_ide or args_ide == "all":
        return list(VALID_IDES)
    if args_ide.strip().lower() == "none":
        # Explicit opt-out: skip all IDE wiring. Caller passes the empty
        # list, which downstream code treats as "no MCP config, no .ide
        # files, no IDE-specific docs".
        return []
    parts = [p.strip() for p in args_ide.split(",") if p.strip()]
    invalid = [p for p in parts if p not in VALID_IDES]
    if invalid:
        valid_names = ", ".join(VALID_IDES)
        print(
            f"  {_cross()} Unknown IDE(s): {', '.join(invalid)}.\n"
            f"    Valid choices: {valid_names}, all, none.\n"
            f"    Use --ide none to skip IDE wiring entirely."
        )
        sys.exit(2)
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
                print(f"  {_warn_glyph()}  Could not link {src.name}: {exc}")
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
            print(f"  {_warn_glyph()}  Could not copy {src.name}: {exc}")
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
        try:
            result = wizard.run_wizard(args)
            if not wizard.show_summary_and_confirm(result):
                print()
                print(f"  {wizard._C.YELLOW}Cancelled — no changes made.{wizard._C.RESET}")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C / Ctrl+D mid-wizard → clean exit, never a raw traceback.
            print()
            print(f"  {wizard._C.YELLOW}Cancelled — no changes made.{wizard._C.RESET}")
            sys.exit(0)
        _execute(result, run_preflight_repo=args.preflight)
        return

    # ── Non-interactive path (legacy / scripted) ────────────────────────
    if args.name and args.directory is None:
        from research_os.wizard import slugify

        slug = slugify(args.name)
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
        print(f"  {_cross()} Workspace already exists at: {target_dir}")
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
        workspace_mode=getattr(args, "workspace_mode", None) or "analysis",
        mcp_scope=getattr(args, "mcp_scope", None) or "workspace",
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
    researcher_block = {
        "name": getattr(r, "researcher_name", "") or "",
        "email": getattr(r, "researcher_email", "") or "",
        "institution": getattr(r, "researcher_institution", "") or "",
        "orcid": getattr(r, "researcher_orcid", "") or "",
    }
    config_overrides = {
        "project_name": r.project_name,
        "domain": r.domain,
        "research_question": r.question,
        "research_questions": list(getattr(r, "questions", []) or []),
        "authors": [author.as_dict()],
        "api_keys": dict(getattr(r, "api_keys", {}) or {}),
        "model_profile": getattr(r, "model_profile", "medium"),
        "researcher": researcher_block,
    }
    # Workspace mode (analysis | tool_build | exploration). Threaded into
    # config_overrides so init_config stamps it AND the scaffold selects
    # the matching profile. Default analysis keeps the classic surface.
    workspace_mode = getattr(r, "workspace_mode", "analysis") or "analysis"
    if workspace_mode != "analysis":
        config_overrides["workspace"] = {"mode": workspace_mode}
    scaffold_minimal_workspace(
        target_dir,
        r.project_name,
        config_overrides=config_overrides,
        ide_flags=r.ides,
        copy_agents=True,
        mode=workspace_mode,
    )
    wizard.ok("Workspace scaffolded", str(target_dir))

    # 2a. Opt-in cross-project profile save.
    if getattr(r, "save_as_profile", False) and any(researcher_block.values()):
        try:
            from research_os.tools.actions.state.config import (
                load_profile, save_profile,
            )
            profile = load_profile()
            existing_r = profile.get("researcher") if isinstance(profile.get("researcher"), dict) else {}
            existing_r.update({k: v for k, v in researcher_block.items() if v})
            profile["researcher"] = existing_r
            # Persist non-empty api_keys + model_profile too.
            api_keys = config_overrides.get("api_keys") or {}
            if api_keys:
                profile.setdefault("api_keys", {}).update(
                    {k: v for k, v in api_keys.items() if v}
                )
            if config_overrides.get("model_profile"):
                profile["model_profile"] = config_overrides["model_profile"]
            res = save_profile(profile)
            wizard.ok("Saved cross-project profile",
                      f"→ {res.get('profile_path')}")
        except Exception as e:
            wizard.warn("Cross-project profile save failed", str(e))

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

    # NOTE: `CONTRIBUTORS.md` is not created automatically at init time.
    # It only gets written when an action explicitly logs to it (e.g.
    # `research-os ide add ...`, which is a deliberate change to project
    # wiring).

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
            print(f"  {_warn_glyph()}  --workspace points at a non-RO directory: {workspace}")
            print("  Run 'research-os init' there first, or omit --workspace.")
            # Launching the server against an un-scaffolded path leaves the AI
            # with no state to boot from — fail fast rather than start broken.
            sys.exit(1)
        sys.argv = [sys.argv[0], "--transport", args.transport,
                    "--workspace", str(workspace)]
    else:
        sys.argv = [sys.argv[0], "--transport", args.transport]

    server_main()


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run / inspect the v4 multi-protocol gateway daemon.

    ``status`` reports daemon + active-project state (read-only). ``start``
    runs the persistent daemon: a background task queue plus read-only HTTP
    endpoints (/healthz, /v1/state, /v1/jobs) on localhost. The HTTP stack
    needs the optional ``research-os[daemon]`` extra. See docs/v4/ROADMAP.md.
    """
    from research_os.daemon import Daemon

    sub = getattr(args, "daemon_command", None)
    if sub is None:
        print("  Research OS daemon (v4 multi-protocol gateway)")
        print()
        print("  research-os daemon status   show daemon + project state")
        print("  research-os daemon start    run the daemon (localhost, read-only API)")
        print("  research-os daemon run      run a command as a tracked job")
        print("  research-os daemon runs     list recorded runs (durable history)")
        print("  research-os daemon logs ID  show a run's details + output")
        print("  research-os daemon reproduce ID  re-run + verify outputs match")
        print("  research-os daemon submit SCRIPT  submit to HPC scheduler (SLURM)")
        print()
        print("  Architecture + roadmap: docs/v4/ROADMAP.md")
        return 0

    overrides: dict = {}
    if getattr(args, "host", None):
        overrides["host"] = args.host
    if getattr(args, "port", None):
        overrides["port"] = args.port

    workspace = getattr(args, "workspace", None)
    if workspace:
        root = Path(workspace).expanduser().resolve()
        daemon = Daemon.for_root(root, **overrides)
    else:
        daemon = Daemon.autoresolve(**overrides)

    if sub == "status":
        status = daemon.status()
        if getattr(args, "as_json", False):
            print(json.dumps(status.to_dict(), indent=2, default=str))
            return 0
        _print_daemon_status(status)
        return 0

    if sub == "start":
        print(f"  Research OS daemon starting on {daemon.config.base_url}")
        print(f"  root: {daemon.root or '(none resolved)'}")
        print("  endpoints: GET /healthz  /v1/state  /v1/jobs   (read-only)")
        print("  Ctrl-C to stop.")
        try:
            daemon.serve()
        except RuntimeError as exc:
            # Missing [daemon] extra (or other startup failure) — clear hint.
            print(f"  {_warn_glyph()}  {exc}")
            return 1
        except KeyboardInterrupt:
            print("\n  daemon stopped.")
            return 0
        return 0

    if sub == "run":
        return _daemon_run(daemon, args)

    if sub == "runs":
        return _daemon_runs(daemon, args)

    if sub == "logs":
        return _daemon_logs(daemon, args)

    if sub == "reproduce":
        return _daemon_reproduce(daemon, args)

    if sub == "submit":
        return _daemon_submit(daemon, args)

    print(f"  {_warn_glyph()}  Unknown daemon command: {sub!r}")
    return 2


def _daemon_run(daemon, args) -> int:
    """Execute a command as a tracked, provenance-recording run (blocking)."""
    import time as _time

    cmd = list(getattr(args, "cmd", []) or [])
    # argparse.REMAINDER keeps a leading "--"; strip it.
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print(f"  {_warn_glyph()}  No command given. Use: research-os daemon run -- <cmd>")
        return 2
    if daemon.runstore is None:
        print(f"  {_warn_glyph()}  No workspace resolved — runs need a project root.")
        print("  Run inside a research-os project, or pass --workspace <path>.")
        return 2

    daemon.tasks.start()
    daemon._start_journal()
    jid = daemon.run_command(
        cmd,
        name=getattr(args, "name", None),
        cwd=getattr(args, "cwd", None),
        track_artifacts=not getattr(args, "no_artifacts", False),
    )

    if not getattr(args, "as_json", False):
        print(f"  run {jid} started: {' '.join(cmd)}")
    # Stream log lines as they land by polling the live log file.
    last = 0
    while True:
        job = daemon.tasks.get(jid)
        if not getattr(args, "as_json", False):
            lines = daemon.runstore.read_log(jid)
            for ln in lines[last:]:
                print(f"    {ln}")
            last = len(lines)
        if job and job.status.value in ("succeeded", "failed", "cancelled"):
            break
        _time.sleep(0.15)

    # Give the journal a beat to flush the terminal manifest.
    _time.sleep(0.3)
    manifest = daemon.runstore.read_manifest(jid) or {}
    daemon.tasks.shutdown(wait=False)

    if getattr(args, "as_json", False):
        print(json.dumps(manifest, indent=2, default=str))
        return 0 if manifest.get("status") == "succeeded" else 1

    status = manifest.get("status", "?")
    result = manifest.get("result") or {}
    rc = result.get("returncode")
    arts = manifest.get("artifacts") or []
    glyph = "✓" if status == "succeeded" else "✗"
    print(f"  {glyph} run {jid}: {status}" + (f" (exit {rc})" if rc is not None else ""))
    if arts:
        print(f"  artifacts ({len(arts)}):")
        for a in arts[:20]:
            h = (a.get("sha256") or "")[:19]
            print(f"    {a.get('change','?'):8} {a.get('path')}  {a.get('size')}b  {h}")
        if len(arts) > 20:
            print(f"    … and {len(arts) - 20} more")
    print(f"  record: {daemon.runstore._run_dir(jid)}")
    return 0 if status == "succeeded" else 1


def _daemon_runs(daemon, args) -> int:
    """List the durable run history for the workspace."""
    if daemon.runstore is None:
        print("  no workspace resolved — nothing to list.")
        return 0
    runs = daemon.runstore.list_runs(limit=getattr(args, "limit", 20))
    if getattr(args, "as_json", False):
        print(json.dumps(runs, indent=2, default=str))
        return 0
    if not runs:
        print("  no recorded runs yet.")
        print(f"  (looked in {daemon.runstore.runs_dir})")
        return 0
    print(f"  {len(runs)} run(s) in {daemon.runstore.runs_dir}:")
    for r in runs:
        rid = r.get("id") or "?"
        status = r.get("status", "?")
        name = r.get("name") or ""
        nart = r.get("artifact_count") or 0
        rc = r.get("returncode")
        glyph = {"succeeded": "✓", "failed": "✗", "cancelled": "⊘"}.get(status, "·")
        extra = f"  exit={rc}" if rc is not None else ""
        artx = f"  {nart} artifact(s)" if nart else ""
        print(f"  {glyph} {rid}  {status:10}{extra}{artx}  {name}")
    return 0


def _daemon_logs(daemon, args) -> int:
    """Show one run's manifest + captured log."""
    if daemon.runstore is None:
        print(f"  {_warn_glyph()}  No workspace resolved — no runs to read.")
        return 1
    rid = args.run_id
    manifest = daemon.runstore.read_manifest(rid)
    if manifest is None:
        print(f"  {_warn_glyph()}  No run found: {rid}")
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(manifest, indent=2, default=str))
        return 0
    print(f"  run {rid}")
    print(f"  status:   {manifest.get('status','?')}")
    spec = manifest.get("spec") or {}
    cmd_val = spec.get("cmd") or spec.get("command")
    if cmd_val:
        print(f"  command:  {cmd_val}")
    prov = manifest.get("provenance") or {}
    git = prov.get("git") or {}
    commit = git.get("commit")
    if commit:
        dirty = " (dirty)" if git.get("dirty") else ""
        print(f"  commit:   {commit[:12]}{dirty} [{git.get('branch','?')}]")
    env = prov.get("env") or {}
    if env.get("conda_env"):
        print(f"  env:      {env.get('conda_env')} / python {env.get('python_version','?')}")
    arts = manifest.get("artifacts") or []
    if arts:
        print(f"  artifacts ({len(arts)}):")
        for a in arts[:20]:
            print(f"    {a.get('change','?'):8} {a.get('path')}  {a.get('size')}b")
    tail = getattr(args, "tail", 0) or None
    lines = daemon.runstore.read_log(rid, tail=tail)
    if lines:
        label = f"last {len(lines)}" if tail else f"{len(lines)}"
        print(f"  log ({label} lines):")
        for ln in lines:
            print(f"    {ln}")
    else:
        print("  (no log captured)")
    return 0


def _daemon_reproduce(daemon, args) -> int:
    """Re-run a recorded run and report whether its outputs still match."""
    from research_os.daemon import reproduce as _repro

    if daemon.runstore is None:
        print(f"  {_warn_glyph()}  No workspace resolved — no runs to reproduce.")
        return 2
    timeout = getattr(args, "timeout", 0) or None
    try:
        daemon.tasks.start()
        daemon._start_journal()
        report = daemon.reproduce_run(
            args.run_id,
            cwd=getattr(args, "cwd", None),
            timeout=timeout,
        )
    except ValueError as exc:
        print(f"  {_warn_glyph()}  {exc}")
        return 2
    finally:
        daemon.tasks.shutdown(wait=False)

    if getattr(args, "as_json", False):
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["verdict"] == _repro.REPRODUCED else 1

    comp = report["comparison"]
    verdict = report["verdict"]
    glyph = _repro.verdict_glyph(verdict)
    print(f"  reproducing {report['original_id']} → run {report['repro_id']}")
    print(f"  command:  {report['command']}")
    print(f"  re-run:   {report['repro_status']}")
    c = comp["counts"]
    print(
        f"  outputs:  {c['matched']} matched, {c['changed']} changed, "
        f"{c['missing']} missing, {c['added']} new"
    )
    for ch in comp["changed"][:20]:
        r = (ch.get("recorded_sha256") or "?")[:19]
        f = (ch.get("fresh_sha256") or "?")[:19]
        print(f"    changed  {ch['path']}")
        print(f"             was {r}  now {f}")
    for p in comp["missing"][:20]:
        print(f"    missing  {p}")
    for p in comp["added"][:20]:
        print(f"    new      {p}")
    if comp["unhashed"]:
        print(f"  ({len(comp['unhashed'])} output(s) compared by size only — too large to hash)")
    label = {
        _repro.REPRODUCED: "REPRODUCED — every recorded output came back identical",
        _repro.DIVERGED: "DIVERGED — at least one output changed",
        _repro.INCOMPLETE: "INCOMPLETE — an output was not regenerated",
    }.get(verdict, verdict)
    print(f"  {glyph} {label}")
    return 0 if verdict == _repro.REPRODUCED else 1


def _daemon_submit(daemon, args) -> int:
    """Submit a job to an HPC scheduler and report the handle.

    Non-blocking: the cluster job may run for hours. We wait only long
    enough to confirm the submission itself succeeded (or failed cleanly),
    then print the daemon job id + scheduler job id and return — the daemon
    worker owns the poll-wait, and 'daemon runs/logs' track it from there.
    """
    import time as _time

    if daemon.runstore is None:
        print(f"  {_warn_glyph()}  No workspace resolved — cannot record a submission.")
        return 2
    daemon.tasks.start()
    daemon._start_journal()
    jid = daemon.submit_job(
        args.script,
        scheduler=getattr(args, "scheduler", "slurm"),
        name=getattr(args, "name", None),
        cwd=getattr(args, "cwd", None),
        poll_interval=getattr(args, "poll", 5.0),
    )

    # Briefly poll the job to surface an immediate submission failure (bad
    # scheduler, sbatch error) without blocking on the cluster run itself.
    scheduler_job_id = None
    submit_error = None
    deadline = _time.time() + 8.0
    while _time.time() < deadline:
        job = daemon.tasks.get(jid)
        if job is None:
            break
        res = job.result if isinstance(job.result, dict) else {}
        if res.get("scheduler_job_id"):
            scheduler_job_id = res["scheduler_job_id"]
            break
        if job.status.value == "failed" or res.get("error"):
            submit_error = res.get("error") or job.error
            break
        # A terminal status with no scheduler id but no error = very fast job.
        if job.status.value in ("succeeded", "cancelled"):
            scheduler_job_id = res.get("scheduler_job_id")
            break
        _time.sleep(0.25)

    if getattr(args, "as_json", False):
        print(json.dumps({
            "job_id": jid,
            "scheduler": getattr(args, "scheduler", "slurm"),
            "scheduler_job_id": scheduler_job_id,
            "error": submit_error,
        }, default=str))
        return 1 if submit_error else 0

    if submit_error:
        print(f"  {_warn_glyph()}  submission failed: {submit_error}")
        print(f"  daemon run id: {jid}  (see 'daemon logs {jid}')")
        return 1
    print(f"  submitted to {getattr(args, 'scheduler', 'slurm')}")
    print(f"  daemon run id:   {jid}")
    if scheduler_job_id:
        print(f"  scheduler job:   {scheduler_job_id}")
    print(f"  the daemon is now tracking it — 'daemon runs' / 'daemon logs {jid}'")
    return 0


def _print_daemon_status(status) -> None:
    """Pretty-print a DaemonStatus for the terminal."""
    serving = "yes" if status.serving else "no"
    print(f"  Research OS daemon v{status.version}")
    print(f"  serving:     {serving}")
    print(f"  bind:        {status.config.get('base_url')}")
    print(f"  gateway:     {'on' if status.config.get('enable_gateway') else 'off'}")
    print(f"  dashboard:   {'on' if status.config.get('enable_dashboard') else 'off'}")
    print(f"  sandbox:     {status.config.get('sandbox_mode')}")
    print(f"  workers:     {status.config.get('task_workers')}")
    print(f"  root:        {status.root or '(none resolved)'}")
    print(f"  initialized: {'yes' if status.project_initialized else 'no'}")
    if status.active_protocol:
        print(f"  protocol:    {status.active_protocol}")
    if status.progress:
        done = status.progress.get("completed") or status.progress.get("steps_done")
        total = status.progress.get("total") or status.progress.get("steps_total")
        if done is not None and total is not None:
            print(f"  progress:    {done}/{total} steps")
    jobs = status.jobs or {}
    if jobs.get("total"):
        counts = jobs.get("counts", {})
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        print(f"  jobs:        {jobs['total']} ({summary})")
    if len(status.roots) > 1:
        print(f"  roots:       {len(status.roots)} registered")
    for note in status.notes:
        print(f"  {_warn_glyph()}  {note}")


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

    if action == "config-path":
        names = args.names or []
        if not names:
            wizard.fail("`research-os ide config-path` needs at least one IDE name",
                        "e.g. `research-os ide config-path cursor`")
            sys.exit(1)
        unknown = [n for n in names if n not in collab.IDE_FILES]
        if unknown:
            wizard.fail(f"Unknown IDE(s): {', '.join(unknown)}",
                        f"Choose from: {', '.join(sorted(collab.IDE_FILES))}")
            sys.exit(1)
        for ide in names:
            print(collab.IDE_FILES[ide][0])
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
# mcp subcommand — compose OTHER MCP servers (Slack, GitHub, Postgres, ...)
# into the IDE configs RO already manages.
#
# This is additive: `research-os ide add` still wires the RO server itself
# into an IDE. `research-os mcp add` wires extra third-party MCP servers
# into the same mcpServers block so the IDE picks them up alongside RO.
# ---------------------------------------------------------------------------


def cmd_mcp(args: argparse.Namespace) -> int:
    """Add / list / remove / template third-party MCP servers."""
    from research_os import collab, wizard
    if getattr(args, "no_color", False):
        wizard.disable_color()

    root = _find_workspace_root()
    if not root:
        wizard.fail("Not inside a Research OS workspace",
                    "Run `research-os init` first, or cd into a project.")
        return 1

    action = args.action

    if action == "list":
        servers_by_ide = collab.mcp_list_servers(root)
        if not servers_by_ide:
            wizard.warn("No IDE configs with composable mcpServers found",
                        "Run `research-os ide add <name>` to wire an IDE first.")
            return 0
        print()
        print(f"  {wizard._C.BOLD}MCP servers in {root}{wizard._C.RESET}")
        print(f"  {wizard._C.GREY}{wizard._hr()}{wizard._C.RESET}")
        for ide, servers in servers_by_ide.items():
            relpath = collab.IDES_WITH_MCP_JSON[ide][0]
            print(f"  {wizard._C.BOLD}{ide}{wizard._C.RESET} "
                  f"{wizard._C.GREY}({relpath}){wizard._C.RESET}")
            if not servers:
                print(f"    {wizard._C.GREY}(no servers configured){wizard._C.RESET}")
                continue
            for name, entry in sorted(servers.items()):
                cmd = entry.get("command", "?") if isinstance(entry, dict) else "?"
                print(f"    {wizard._C.GREEN}·{wizard._C.RESET} "
                      f"{name:<24}{wizard._C.GREY}{cmd}{wizard._C.RESET}")
        print()
        return 0

    if action == "template":
        name = (args.name or "").strip().lower()
        if not name:
            wizard.fail("`research-os mcp template` needs --name",
                        f"Known: {', '.join(sorted(collab.MCP_TEMPLATES))}")
            return 2
        entry = collab.MCP_TEMPLATES.get(name)
        if not entry:
            wizard.fail(f"Unknown template: {name!r}",
                        f"Known: {', '.join(sorted(collab.MCP_TEMPLATES))}")
            return 2
        ides = _parse_ide_list_for_mcp(args.ide, collab)
        results = collab.mcp_add_server(root, args.as_name or name, entry, ides=ides)
        _print_mcp_results(results, args.as_name or name, action="added", wizard=wizard)
        author = collab.whoami(root)
        collab.log_action(root, author, f"Added MCP server template: {args.as_name or name}")
        return 0

    if action == "add":
        if not args.name:
            wizard.fail("`research-os mcp add` needs --name", "")
            return 2
        if not args.mcp_command:
            wizard.fail("`research-os mcp add` needs --command",
                        "e.g. `--command npx --args -y,@scope/server`")
            return 2
        entry: dict = {"command": args.mcp_command}
        if args.mcp_args:
            # Accept comma- or space-separated lists (commas are simpler in shells).
            arg_list = [a for a in args.mcp_args.replace(",", " ").split() if a]
            if arg_list:
                entry["args"] = arg_list
        ides = _parse_ide_list_for_mcp(args.ide, collab)
        results = collab.mcp_add_server(root, args.name, entry, ides=ides)
        _print_mcp_results(results, args.name, action="added", wizard=wizard)
        author = collab.whoami(root)
        collab.log_action(root, author, f"Added MCP server: {args.name}")
        return 0

    if action == "remove":
        if not args.name:
            wizard.fail("`research-os mcp remove` needs --name", "")
            return 2
        ides = _parse_ide_list_for_mcp(args.ide, collab)
        results = collab.mcp_remove_server(root, args.name, ides=ides)
        _print_mcp_results(results, args.name, action="removed", wizard=wizard)
        author = collab.whoami(root)
        collab.log_action(root, author, f"Removed MCP server: {args.name}")
        return 0

    wizard.fail(f"Unknown mcp action: {action}", "")
    return 2


def _parse_ide_list_for_mcp(value: str | None, collab_mod) -> list[str] | None:
    """Parse the --ide flag for `mcp` subcommands. None / 'all' / 'wired'
    → return None (delegate to mcp_add_server's default).
    Comma-separated → return the explicit list, validated against the
    set of IDEs that DO support composable mcpServers blocks."""
    if not value or value.lower() in ("all", "wired"):
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    valid = collab_mod.IDES_WITH_MCP_JSON
    invalid = [p for p in parts if p not in valid]
    if invalid:
        print(f"  {_cross()} Unknown IDE(s) for mcp: {', '.join(invalid)}. "
              f"Choose from: {', '.join(sorted(valid))}.")
        sys.exit(2)
    return parts


def _print_mcp_results(results: dict[str, str], name: str, action: str, wizard) -> None:
    if not results:
        wizard.warn(f"No IDEs to {action.rstrip('ed')} {name!r}",
                    "Wire one with `research-os ide add <name>` first.")
        return
    for ide, status in results.items():
        if status in ("added", "updated", "removed"):
            wizard.ok(f"{ide}: {status} {name}")
        else:
            wizard.warn(f"{ide}", status)


# ---------------------------------------------------------------------------
# hermes subcommand — wire Research-OS into Hermes Agent (~/.hermes/config.yaml)
# ---------------------------------------------------------------------------


def cmd_hermes(args: argparse.Namespace) -> int:
    """Wire / unwire / inspect Research-OS inside Hermes Agent."""
    from research_os import hermes_integration as hi
    from research_os import wizard
    if getattr(args, "no_color", False):
        wizard.disable_color()

    action = args.action
    cfg = Path(args.config).expanduser() if getattr(args, "config", None) else None

    if action == "status":
        st = hi.status(config_path=cfg)
        print()
        print(f"  {wizard._C.BOLD}Research-OS in Hermes{wizard._C.RESET}")
        print(f"  {wizard._C.GREY}{wizard._hr()}{wizard._C.RESET}")
        print(f"  config        {st['config_path']}"
              f"  {'(exists)' if st['config_exists'] else '(missing)'}")
        if st["server_registered"]:
            wizard.ok("MCP server registered", repr(st["server_entry"]))
        else:
            wizard.warn("MCP server not registered",
                        "run `research-os hermes add`")
        if st["skill_installed"]:
            wizard.ok("Skill installed", st["skill_path"])
        else:
            wizard.warn("Skill not installed", "run `research-os hermes add`")
        if st["external_dirs"]:
            print(f"  external_dirs {st['external_dirs']}")
        return 0

    if action == "add":
        raw = getattr(args, "mcp_args", None)
        mcp_args = [a for a in raw.replace(",", " ").split() if a] if raw else None
        res = hi.add(
            command=getattr(args, "hermes_command", None),
            args=mcp_args,
            url=getattr(args, "url", None),
            config_path=cfg,
        )
        wizard.ok(f"MCP server {res['server_action']}",
                  f"{res['server_key']} → {res['config_path']}")
        if res["url"]:
            print(f"  url     {res['url']}")
        else:
            print(f"  command {res['command']} {' '.join(res['args'])}")
        wizard.ok("Skill installed", res["skill_path"])
        if res["external_dir_added"]:
            wizard.ok("Registered skills dir in external_dirs")
        elif not res["external_dir_needed"]:
            print("  (skill lives in the built-in Hermes skills tree; "
                  "no external_dir needed)")
        print()
        print("  Restart Hermes to pick up the new MCP server and skill.")
        return 0

    if action == "remove":
        res = hi.remove(config_path=cfg)
        if res["server_removed"]:
            wizard.ok("MCP server unregistered", res["config_path"])
        else:
            wizard.warn("MCP server was not registered", "no changes")
        if res["external_dir_removed"]:
            wizard.ok("Removed skills dir from external_dirs")
        return 0

    wizard.fail(f"Unknown hermes action: {action!r}",
                "Choose from: add, remove, status")
    return 2


# ---------------------------------------------------------------------------
# route subcommand — preview the protocol router from the terminal
# ---------------------------------------------------------------------------


def cmd_route(args: argparse.Namespace) -> int:
    """Run the runtime protocol router on a prompt and print the decision.

    This is the same ``route_request`` the MCP ``tool_route`` calls, exposed
    so a researcher (or a non-MCP agent) can preview what Research-OS would
    do for a given request without loading an IDE. Read-only: never persists
    an active plan.
    """
    import json as _json

    from research_os import wizard
    from research_os.tools.actions.router import route_request

    if getattr(args, "no_color", False):
        wizard.disable_color()

    prompt = (args.prompt or "").strip()
    if not prompt:
        wizard.fail("Empty prompt", 'Usage: research-os route "<your request>"')
        return 2

    root = _find_workspace_root() or Path.cwd()

    result = route_request(prompt, root, persist_plan=False)

    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "success" else 1

    if result.get("status") != "success":
        wizard.fail("Routing failed", result.get("message", "unknown error"))
        return 1

    C = wizard._C
    level = result.get("resolved_level")
    intent = result.get("intent_class") or "—"
    sub = result.get("sub_intent") or "—"
    primary = result.get("primary_protocol")
    shortcut = result.get("shortcut_tool")
    complexity = result.get("complexity") or "—"
    tier = result.get("tier")
    why = result.get("why_matched") or result.get("why") or ""
    ask = result.get("ask_user")
    decomposition = result.get("decomposition") or []
    alternatives = result.get("alternatives") or []
    triggers = result.get("matched_triggers") or []

    print()
    print(f"  {C.BOLD}Route for:{C.RESET} {prompt}")
    print(f"  {C.GREY}{wizard._hr()}{C.RESET}")
    print(f"  {C.BOLD}intent{C.RESET}        {intent} / {sub}")
    if primary:
        print(f"  {C.BOLD}protocol{C.RESET}      {C.GREEN}{primary}{C.RESET}")
    if shortcut:
        print(f"  {C.BOLD}shortcut{C.RESET}      {C.GREEN}{shortcut}{C.RESET}")
    print(f"  {C.BOLD}level{C.RESET}         L{level}   "
          f"complexity={complexity}" + (f"   tier={tier}" if tier else ""))
    if triggers:
        print(f"  {C.BOLD}triggers{C.RESET}      {', '.join(str(t) for t in triggers)}")
    if why:
        print(f"  {C.BOLD}why{C.RESET}           {C.GREY}{why}{C.RESET}")
    if ask:
        print(f"  {C.BOLD}{C.YELLOW}ask first{C.RESET}     {ask}")

    if decomposition:
        print()
        print(f"  {C.BOLD}planned tool sequence{C.RESET}")
        for i, step in enumerate(decomposition, 1):
            tool = step.get("tool") if isinstance(step, dict) else str(step)
            note = step.get("why", "") if isinstance(step, dict) else ""
            line = f"    {i:>2}. {tool}"
            if note:
                line += f"   {C.GREY}{note}{C.RESET}"
            print(line)

    if alternatives:
        print()
        print(f"  {C.BOLD}alternatives{C.RESET}")
        for alt in alternatives[:4]:
            if isinstance(alt, dict):
                aid = alt.get("name") or alt.get("protocol") or alt.get("primary_protocol") or "—"
                ascore = alt.get("score")
            else:
                aid, ascore = str(alt), None
            sc = f"  ({ascore})" if ascore is not None else ""
            print(f"    - {aid}{C.GREY}{sc}{C.RESET}")
    print()
    return 0


# ---------------------------------------------------------------------------
# api-key subcommand — manage api_keys in inputs/researcher_config.yaml
# ---------------------------------------------------------------------------


def cmd_api_key(args: argparse.Namespace) -> int:
    """Add / list / rotate / remove / test an API key in researcher_config.yaml."""
    from research_os import collab, wizard
    from research_os.tools.actions.state.config import (
        add_api_key, check_api_key, list_api_keys, remove_api_key,
    )
    if getattr(args, "no_color", False):
        wizard.disable_color()

    root = _find_workspace_root()
    if not root:
        wizard.fail("Not inside a Research OS workspace",
                    "Run `research-os init` first, or cd into a project.")
        return 1

    action = args.action

    if action == "list":
        res = list_api_keys(root)
        if res.get("status") != "success":
            wizard.fail("Could not list API keys", res.get("message", ""))
            return 1
        api_keys = res.get("api_keys") or {}
        print()
        print(f"  {wizard._C.BOLD}API keys in {root / 'inputs' / 'researcher_config.yaml'}{wizard._C.RESET}")
        print(f"  {wizard._C.GREY}{wizard._hr()}{wizard._C.RESET}")
        if not api_keys:
            print(f"  {wizard._C.GREY}(no keys configured){wizard._C.RESET}")
        for provider, masked_val in sorted(api_keys.items()):
            mark = (f"{wizard._C.GREEN}·{wizard._C.RESET}" if masked_val
                    else f"{wizard._C.GREY}·{wizard._C.RESET}")
            display = masked_val or f"{wizard._C.GREY}(blank){wizard._C.RESET}"
            print(f"  {mark} {provider:<22}{display}")
        print()
        return 0

    if action in ("add", "rotate"):
        provider = args.provider
        if not provider:
            wizard.fail(f"`research-os api-key {action}` needs a provider",
                        f"e.g. `research-os api-key {action} semantic_scholar`")
            return 2
        value = _read_secret_value(args, provider, wizard)
        if not value:
            return 2
        res = add_api_key(root, provider, value)
        if res.get("status") != "success":
            wizard.fail(f"Could not store key for {provider}",
                        res.get("message", ""))
            return 1
        verb = "Rotated" if res.get("rotated") or action == "rotate" else "Added"
        wizard.ok(f"{verb} key for {provider}", "chmod 600 applied")
        author = collab.whoami(root)
        collab.log_action(root, author, f"{verb} API key: {provider}")
        return 0

    if action == "remove":
        provider = args.provider
        if not provider:
            wizard.fail("`research-os api-key remove` needs a provider", "")
            return 2
        res = remove_api_key(root, provider)
        if res.get("status") == "success":
            wizard.ok(f"Removed key for {provider}")
            author = collab.whoami(root)
            collab.log_action(root, author, f"Removed API key: {provider}")
            return 0
        if res.get("status") == "noop":
            wizard.warn(res.get("message", "no-op"))
            return 0
        wizard.fail("Could not remove key", res.get("message", ""))
        return 1

    if action == "test":
        provider = args.provider
        if not provider:
            wizard.fail("`research-os api-key test` needs a provider",
                        "e.g. `research-os api-key test pubmed`")
            return 2
        res = check_api_key(root, provider)
        if res.get("status") == "ok":
            wizard.ok(f"{provider}: OK", res.get("detail", ""))
            return 0
        wizard.fail(f"{provider}: FAIL", res.get("detail", ""))
        return 1

    wizard.fail(f"Unknown api-key action: {action}", "")
    return 2


def _read_secret_value(args: argparse.Namespace, provider: str, wizard) -> str:
    """Return the secret to store, prompting via getpass if not in --from-env."""
    if getattr(args, "from_env", None):
        env_name = args.from_env
        val = os.environ.get(env_name, "").strip()
        if not val:
            wizard.fail(f"Environment variable {env_name} not set or empty", "")
            return ""
        return val
    # Interactive: hidden prompt.
    import getpass as _getpass
    try:
        val = _getpass.getpass(f"Paste {provider} API key (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        wizard.warn("Cancelled — no key stored")
        return ""
    if not val:
        wizard.warn("Empty input — no key stored")
        return ""
    return val


# ---------------------------------------------------------------------------
# refresh — update project copies of templates from the bundled source
# ---------------------------------------------------------------------------


# Files that the wizard copies into a new project from
# `templates/`. The refresh command compares each project copy against
# the bundled source and (optionally) overwrites when they diverge.
# Path is relative to the project root; the bundled source lives at the
# same relative path under `templates/`. Order matches the wizard.
_REFRESHABLE_TEMPLATES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/rules/research-os.md",
    ".cursor/rules/research-os.mdc",
    ".antigravity/rules/research-os.md",
    ".windsurfrules",
    ".continuerules",
    ".aider.conf.yml",
)


def _bundled_templates_dir() -> Path:
    """Path to the bundled templates directory shipped with the package."""
    return Path(__file__).resolve().parent.parent.parent / "templates"


def _diff_template(bundled: Path, project: Path) -> tuple[str, str]:
    """Return ``(status, message)`` for one project copy vs the bundled source.

    Status values:
      * ``fresh``    — project copy missing OR identical to bundled source.
      * ``drift``    — both exist but content differs.
      * ``absent``   — neither exists (file isn't applicable to this project,
                       e.g. .cursor/ rules in a project wired only for Claude).
      * ``error``    — couldn't read one of the files.
    """
    bundled_exists = bundled.exists()
    project_exists = project.exists()
    if not bundled_exists and not project_exists:
        return ("absent", "neither source nor project copy present")
    if not project_exists:
        return ("absent", "project copy missing (file is opt-in per IDE)")
    if not bundled_exists:
        return ("error", "bundled source missing — package install corrupt?")
    try:
        b_text = bundled.read_text()
        p_text = project.read_text()
    except OSError as e:
        return ("error", f"read failed: {e}")
    if b_text == p_text:
        return ("fresh", "identical to bundled template")
    # Cheap line-level diff stats so the report is meaningful without
    # running a full diff library.
    b_lines = b_text.splitlines()
    p_lines = p_text.splitlines()
    delta = len(b_lines) - len(p_lines)
    sign = "+" if delta > 0 else ""
    return (
        "drift",
        f"differs from bundled (project has {len(p_lines)} lines, "
        f"bundled has {len(b_lines)}, {sign}{delta} after refresh)",
    )


def cmd_refresh(args: argparse.Namespace) -> int:
    """Detect drift between project template copies and bundled sources;
    optionally overwrite.

    Read-only by default (``--check`` is the only mode that exits non-zero
    on drift). Pass ``--write`` to overwrite drifted files; pass ``--yes``
    to skip the confirmation prompt for each file.
    """
    from research_os import wizard

    if getattr(args, "no_color", False):
        wizard.disable_color()

    workspace = (
        Path(args.workspace).resolve() if getattr(args, "workspace", None)
        else _find_workspace_root()
    )
    if not workspace:
        wizard.fail(
            "Not inside a Research OS workspace",
            "cd into a project directory or pass --workspace <path>.",
        )
        return 1

    bundled_dir = _bundled_templates_dir()
    if not bundled_dir.exists():
        wizard.fail(
            "Bundled templates directory not found",
            f"expected at {bundled_dir} — package install may be corrupt.",
        )
        return 1

    results: list[tuple[str, str, str, Path, Path]] = []
    for rel in _REFRESHABLE_TEMPLATES:
        bundled = bundled_dir / rel
        project = workspace / rel
        status, message = _diff_template(bundled, project)
        results.append((rel, status, message, bundled, project))

    drift_count = sum(1 for _, status, *_ in results if status == "drift")
    error_count = sum(1 for _, status, *_ in results if status == "error")
    fresh_count = sum(1 for _, status, *_ in results if status == "fresh")
    absent_count = sum(1 for _, status, *_ in results if status == "absent")

    # ── JSON mode ───────────────────────────────────────────────────────
    if getattr(args, "json", False):
        out = {
            "workspace": str(workspace),
            "bundled_dir": str(bundled_dir),
            "drift_count": drift_count,
            "error_count": error_count,
            "fresh_count": fresh_count,
            "absent_count": absent_count,
            "files": [
                {
                    "relative_path": rel,
                    "status": status,
                    "message": msg,
                    "bundled_source": str(bundled),
                    "project_copy": str(project),
                }
                for rel, status, msg, bundled, project in results
            ],
        }
        print(json.dumps(out, indent=2))
        if getattr(args, "check", False):
            return 0 if drift_count == 0 and error_count == 0 else 1
        return 0

    # ── Human-readable report ───────────────────────────────────────────
    print(f"\nWorkspace: {workspace}")
    print(f"Templates: {bundled_dir}\n")
    for rel, status, msg, _bundled, _project in results:
        if status == "fresh":
            wizard.ok(f"  {rel}", msg)
        elif status == "drift":
            wizard.warn(f"  {rel}", msg)
        elif status == "absent":
            # Quiet success — file not applicable.
            print(f"  · {rel}: not applicable (no project copy)")
        else:
            wizard.fail(f"  {rel}", msg)
    print()

    if drift_count == 0 and error_count == 0:
        wizard.ok(
            "All template copies fresh",
            f"{fresh_count} match, {absent_count} not applicable.",
        )
        return 0

    # ── Check mode: report only, exit non-zero on drift ─────────────────
    if getattr(args, "check", False):
        wizard.warn(
            f"{drift_count} drifted, {error_count} error(s)",
            "re-run without --check (and with --write to apply) to upgrade.",
        )
        return 1

    # ── Write mode: overwrite drifted files ─────────────────────────────
    if not getattr(args, "write", False):
        wizard.warn(
            f"{drift_count} drifted file(s)",
            "Re-run with --write to overwrite the project copy with the "
            "bundled template (use --yes to skip per-file confirmation).",
        )
        return 1

    auto_yes = bool(getattr(args, "yes", False))
    written = 0
    for rel, status, _msg, bundled, project in results:
        if status != "drift":
            continue
        if not auto_yes:
            try:
                resp = input(f"Overwrite {rel}? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                wizard.warn("Cancelled by user — partial refresh", "")
                return 1
            if resp not in ("y", "yes"):
                print(f"  skipped: {rel}")
                continue
        try:
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(bundled.read_text())
            wizard.ok(f"  wrote: {rel}", "")
            written += 1
        except OSError as e:
            wizard.fail(f"  failed: {rel}", str(e))
            return 1

    if written:
        wizard.ok(
            f"Refreshed {written} file(s)",
            "Diff against your prior version with `git diff` to spot any "
            "project-specific tweaks you want to re-apply on top.",
        )
    else:
        wizard.warn(
            "No files written",
            "Every drifted file was skipped — re-run with --yes to apply "
            "without per-file prompting.",
        )

    # Optional: regenerate the project-root README with a "Project
    # status" section reflecting current step inventory + synthesis
    # deliverables. Idempotent; safe to run repeatedly.
    if getattr(args, "regen_readme", False):
        from research_os.project_ops import regenerate_root_readme

        try:
            res = regenerate_root_readme(workspace)
            wizard.ok(
                f"Regenerated {res['path']}",
                f"{res['step_count']} step(s) + "
                f"{len(res['deliverables'])} synthesis deliverable(s) listed.",
            )
        except Exception as e:  # noqa: BLE001
            wizard.fail("README regeneration failed", str(e))
            return 1

    return 0


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------


# Top-level subcommand names recognized by the CLI. Kept in one place so
# the fish completion script and the argparse subparser registry stay in
# sync (the test suite cross-checks these).
SUBCOMMANDS_FOR_COMPLETION = (
    "init", "ide", "mcp", "hermes", "route", "api-key", "start", "daemon",
    "doctor", "refresh", "completion",
)


_FISH_COMPLETION_TEMPLATE = """\
# research-os fish completion
# Generated by `research-os completion fish`.
# Source via: research-os completion fish | source

complete -c research-os -f

# Top-level subcommands.
function __research_os_no_subcommand
    set -l cmd (commandline -opc)
    set -l subs {sub_list}
    if test (count $cmd) -le 1
        return 0
    end
    for token in $cmd[2..-1]
        for s in $subs
            if test "$token" = "$s"
                return 1
            end
        end
    end
    return 0
end

{sub_complete_block}

# init flags
complete -c research-os -n '__fish_seen_subcommand_from init' -l name -d 'Project name'
complete -c research-os -n '__fish_seen_subcommand_from init' -l domain -d 'Domain hint'
complete -c research-os -n '__fish_seen_subcommand_from init' -l question -d 'Initial research question'
complete -c research-os -n '__fish_seen_subcommand_from init' -l ide -d 'IDE(s) to wire' -xa "{ide_choices}"
complete -c research-os -n '__fish_seen_subcommand_from init' -l force -d 'Re-scaffold even if workspace exists'
complete -c research-os -n '__fish_seen_subcommand_from init' -s y -l yes -d 'Skip the wizard'
complete -c research-os -n '__fish_seen_subcommand_from init' -l no-color -d 'Disable ANSI styling'
complete -c research-os -n '__fish_seen_subcommand_from init' -l preflight -d 'Run repo preflight after scaffold'

# ide subcommand
complete -c research-os -n '__fish_seen_subcommand_from ide' -xa 'list add remove config-path'

# start flags
complete -c research-os -n '__fish_seen_subcommand_from start' -l workspace -d 'Pin to a workspace path' -r
complete -c research-os -n '__fish_seen_subcommand_from start' -l transport -d 'MCP transport' -xa 'stdio sse'

# doctor flags
complete -c research-os -n '__fish_seen_subcommand_from doctor' -l verbose -d 'Show fix hints for passing checks'
complete -c research-os -n '__fish_seen_subcommand_from doctor' -l workspace-only -d 'Skip install checks'
complete -c research-os -n '__fish_seen_subcommand_from doctor' -l workspace -d 'Explicit workspace path' -r
complete -c research-os -n '__fish_seen_subcommand_from doctor' -l json -d 'Emit JSON report'
complete -c research-os -n '__fish_seen_subcommand_from doctor' -l no-color -d 'Disable ANSI styling'

# refresh flags
complete -c research-os -n '__fish_seen_subcommand_from refresh' -l check -d 'Report only; exit 1 on drift'
complete -c research-os -n '__fish_seen_subcommand_from refresh' -l write -d 'Overwrite drifted files'
complete -c research-os -n '__fish_seen_subcommand_from refresh' -s y -l yes -d 'Skip per-file confirmation'
complete -c research-os -n '__fish_seen_subcommand_from refresh' -l workspace -d 'Explicit workspace path' -r
complete -c research-os -n '__fish_seen_subcommand_from refresh' -l json -d 'Emit JSON report'
complete -c research-os -n '__fish_seen_subcommand_from refresh' -l no-color -d 'Disable ANSI styling'

# completion subcommand
complete -c research-os -n '__fish_seen_subcommand_from completion' -xa 'bash zsh fish'
"""


def _build_fish_completion() -> str:
    """Hand-rolled fish completion script for the research-os CLI."""
    sub_list = " ".join(SUBCOMMANDS_FOR_COMPLETION)
    # Per-subcommand top-level entries with short descriptions.
    sub_descriptions = {
        "init": "Scaffold a Research OS workspace",
        "ide": "Add / remove / list AI IDE MCP configs",
        "start": "Run the MCP server",
        "doctor": "Diagnose install + workspace health",
        "refresh": "Refresh project template copies from bundled sources",
        "completion": "Print shell completion script",
    }
    lines = []
    for name in SUBCOMMANDS_FOR_COMPLETION:
        desc = sub_descriptions.get(name, "")
        lines.append(
            f"complete -c research-os -n '__research_os_no_subcommand' "
            f"-xa '{name}' -d '{desc}'"
        )
    return _FISH_COMPLETION_TEMPLATE.format(
        sub_list=sub_list,
        sub_complete_block="\n".join(lines),
        ide_choices=" ".join(IDE_CHOICES_FOR_COMPLETION),
    )


def _build_bash_zsh_completion(shell: str) -> str:
    """Use argcomplete to emit a bash/zsh completion script when available.

    Falls back to a minimal hand-rolled script when argcomplete isn't
    installed so the subcommand still works without the optional extra.
    """
    try:
        import shlex
        import subprocess as _sub
        # argcomplete ships a console script `register-python-argcomplete`.
        # It emits a sh-eval'able snippet. For zsh, it auto-detects via
        # `-s zsh`; for bash, the default mode works.
        cmd = ["register-python-argcomplete"]
        if shell == "zsh":
            cmd += ["-s", "zsh"]
        cmd += ["research-os"]
        try:
            out = _sub.check_output(cmd, text=True, stderr=_sub.DEVNULL)
            return out
        except (OSError, _sub.CalledProcessError):
            # Fall through to fallback below.
            pass
        # Try the python module form.
        cmd = [sys.executable, "-m", "argcomplete.scripts.register_python_argcomplete"]
        if shell == "zsh":
            cmd += ["-s", "zsh"]
        cmd += ["research-os"]
        try:
            out = _sub.check_output(cmd, text=True, stderr=_sub.DEVNULL)
            return out
        except (OSError, _sub.CalledProcessError):
            pass
        _ = shlex  # keep import side-effect free for linters
    except Exception:
        pass
    # Fallback: minimal hand-rolled completion covering subcommands +
    # --ide values. Works without argcomplete.
    subs = " ".join(SUBCOMMANDS_FOR_COMPLETION)
    ides = " ".join(IDE_CHOICES_FOR_COMPLETION)
    if shell == "zsh":
        return (
            "#compdef research-os\n"
            "# Minimal fallback completion (argcomplete not installed).\n"
            "_research_os() {\n"
            "  local -a subs ides\n"
            f"  subs=({subs})\n"
            f"  ides=({ides})\n"
            "  if (( CURRENT == 2 )); then\n"
            "    compadd -- $subs\n"
            "    return\n"
            "  fi\n"
            "  if [[ $words[2] == init && $words[CURRENT-1] == --ide ]]; then\n"
            "    compadd -- $ides\n"
            "    return\n"
            "  fi\n"
            "}\n"
            "compdef _research_os research-os\n"
        )
    # bash
    return (
        "# Minimal fallback completion (argcomplete not installed).\n"
        "_research_os() {\n"
        '  local cur prev words cword\n'
        '  _init_completion 2>/dev/null || {\n'
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '    prev="${COMP_WORDS[COMP_CWORD-1]}"\n'
        "  }\n"
        f'  local subs="{subs}"\n'
        f'  local ides="{ides}"\n'
        '  if [[ $COMP_CWORD -eq 1 ]]; then\n'
        '    COMPREPLY=( $(compgen -W "$subs" -- "$cur") )\n'
        "    return 0\n"
        "  fi\n"
        '  if [[ "$prev" == "--ide" ]]; then\n'
        '    COMPREPLY=( $(compgen -W "$ides" -- "$cur") )\n'
        "    return 0\n"
        "  fi\n"
        "}\n"
        "complete -F _research_os research-os\n"
    )


def cmd_completion(args: argparse.Namespace) -> int:
    """Print a sourceable shell completion script."""
    shell = args.shell
    if shell == "fish":
        sys.stdout.write(_build_fish_completion())
    elif shell in ("bash", "zsh"):
        sys.stdout.write(_build_bash_zsh_completion(shell))
    else:
        # Should never hit — argparse `choices=` enforces this.
        print(
            f"  {_cross()} Unsupported shell: {shell}. "
            "Choose one of: bash, zsh, fish.",
            file=sys.stderr,
        )
        return 2
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os",
        description=(
            "Research OS — an MCP-native research operating system.\n\n"
            "Four commands:\n"
            "  research-os init    scaffold a workspace ready for any AI IDE\n"
            "  research-os ide     add / remove / list AI IDE MCP configs\n"
            "  research-os start   run the MCP server (your IDE auto-launches it)\n"
            "  research-os doctor  diagnose install + workspace health\n\n"
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
    p_init.add_argument("--workspace-mode", dest="workspace_mode",
                        choices=["analysis", "tool_build", "exploration",
                                 "notebook", "multi_study", "hybrid"],
                        default=None,
                        help="What kind of work this is. "
                             "analysis (default) = linear analysis steps; "
                             "tool_build = governed software build; "
                             "exploration = scratch-first probes; "
                             "notebook = Jupyter-first notebook project; "
                             "multi_study = multi-study program (portfolio "
                             "+ cross-study meta-analysis); "
                             "hybrid = research + software (analysis steps "
                             "plus an inner software component).")
    p_init.add_argument("--mcp-scope", dest="mcp_scope",
                        choices=["workspace", "global"], default="workspace",
                        help="Where to register the MCP server. workspace "
                             "(default) = per-project config files. global = "
                             "also print the user-scope install command so "
                             "research-os is available in every project. "
                             "Either way, RESTART your IDE afterwards.")
    _ide_arg = p_init.add_argument(
        "--ide", default="all",
        help="IDE(s) to wire up: 'all' or a comma-separated list. "
             "Valid names: " + ", ".join(VALID_IDES)
             + " (plus 'all' and 'none').",
    )
    # Attach argcomplete completer hook (no-op when argcomplete absent).
    _ide_arg.completer = lambda **kw: list(IDE_CHOICES_FOR_COMPLETION)
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
    p_ide.add_argument("action", choices=["list", "add", "remove", "config-path"],
                       help="What to do. `config-path <name>` prints the expected MCP config path for one IDE.")
    p_ide.add_argument("names", nargs="*",
                       help="IDE names (required for add / remove / config-path).")
    p_ide.add_argument("--no-color", action="store_true",
                       help="Disable ANSI styling.")

    # ── mcp ─────────────────────────────────────────────────────────────
    p_mcp = sub.add_parser(
        "mcp",
        help="Compose third-party MCP servers (Slack, GitHub, Postgres, ...) into IDE configs.",
        description=(
            "Manage OTHER MCP servers wired into your IDE configs. Additive to\n"
            "`research-os ide add`, which wires the Research-OS server itself.\n\n"
            "Examples:\n"
            "  research-os mcp list\n"
            "  research-os mcp template --name slack\n"
            "  research-os mcp add my-server --command npx --args -y,@scope/server\n"
            "  research-os mcp remove my-server\n"
            "  research-os mcp add foo --command npx --args -y,@x --ide cursor,claude"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mcp.add_argument("action", choices=["list", "add", "remove", "template"],
                       help="What to do.")
    p_mcp.add_argument("name", nargs="?", default=None,
                       help="Server name (for add/remove) or template key (for template).")
    p_mcp.add_argument("--name", dest="name_flag",
                       help="Alternate way to supply --name; positional 'name' takes precedence.")
    p_mcp.add_argument("--command", dest="mcp_command",
                       help="Command to run the MCP server (e.g. 'npx').")
    p_mcp.add_argument("--args", dest="mcp_args",
                       help="Comma- or space-separated args list for the command "
                            "(e.g. '-y,@scope/server-name').")
    p_mcp.add_argument("--ide", default="wired",
                       help="Which IDE config(s) to update. 'wired' (default) = "
                            "every wired IDE that supports mcpServers; 'all' is an "
                            "alias; or pass a comma-separated list (cursor,claude,...).")
    p_mcp.add_argument("--as-name", dest="as_name",
                       help="Override the name a template is registered under "
                            "(default: the template's own key).")
    p_mcp.add_argument("--no-color", action="store_true",
                       help="Disable ANSI styling.")

    # ── hermes ──────────────────────────────────────────────────────────
    p_hermes = sub.add_parser(
        "hermes",
        help="Wire Research-OS into Hermes Agent (~/.hermes/config.yaml).",
        description=(
            "Make Research-OS a first-class citizen inside Hermes Agent.\n"
            "Registers the RO MCP server under mcp_servers: and installs the\n"
            "canonical RO skill so the agent loads it automatically. The edit\n"
            "is comment-preserving, idempotent, and reversible.\n\n"
            "Examples:\n"
            "  research-os hermes add        # auto-detect launch command\n"
            "  research-os hermes status\n"
            "  research-os hermes remove\n"
            "  research-os hermes add --url http://127.0.0.1:8765/mcp\n"
            "  research-os hermes add --command research-os --args start"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_hermes.add_argument("action", choices=["add", "remove", "status"],
                          help="What to do.")
    p_hermes.add_argument("--command", dest="hermes_command",
                          help="Command to launch the RO MCP server (stdio). "
                               "Defaults to the installed `research-os` script "
                               "or `python -m research_os.server`.")
    p_hermes.add_argument("--args", dest="mcp_args",
                          help="Comma- or space-separated args for --command.")
    p_hermes.add_argument("--url", dest="url",
                          help="Register an HTTP/SSE endpoint instead of a "
                               "stdio command.")
    p_hermes.add_argument("--config", dest="config",
                          help="Path to the Hermes config (default: "
                               "$HERMES_CONFIG or ~/.hermes/config.yaml).")
    p_hermes.add_argument("--no-color", action="store_true",
                          help="Disable ANSI styling.")

    # ── route ───────────────────────────────────────────────────────────
    p_route = sub.add_parser(
        "route",
        help="Preview the protocol router for a prompt (no IDE needed).",
        description=(
            "Run the same hierarchical router the MCP `tool_route` uses and\n"
            "print the routing decision: matched protocol, intent class,\n"
            "planned tool sequence, and alternatives. Read-only — never\n"
            "persists an active plan. Run inside a workspace for state-aware\n"
            "routing, or anywhere for a stateless preview.\n\n"
            "Examples:\n"
            '  research-os route "fit a mixed-effects model to my data"\n'
            '  research-os route "draft the methods section" --json'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_route.add_argument("prompt", help="The request to route.")
    p_route.add_argument("--json", action="store_true",
                         help="Emit the raw routing decision as JSON.")
    p_route.add_argument("--no-color", action="store_true",
                         help="Disable ANSI styling.")

    # ── api-key ─────────────────────────────────────────────────────────
    p_api = sub.add_parser(
        "api-key",
        help="Manage api_keys in inputs/researcher_config.yaml (chmod 600 + hidden prompts).",
        description=(
            "Add / rotate / list / remove / test API keys for free-tier research\n"
            "providers (Semantic Scholar, PubMed, Crossref, OpenAlex, ...).\n"
            "Stored in inputs/researcher_config.yaml under api_keys:; every write\n"
            "re-applies chmod 600. Hidden input via getpass for add and rotate.\n\n"
            "Examples:\n"
            "  research-os api-key list\n"
            "  research-os api-key add semantic_scholar          # prompts via getpass\n"
            "  research-os api-key add openai --from-env OPENAI_API_KEY  # for CI\n"
            "  research-os api-key rotate pubmed                 # prompts via getpass\n"
            "  research-os api-key test pubmed                   # 1-token round-trip\n"
            "  research-os api-key remove crossref"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_api.add_argument("action", choices=["add", "list", "rotate", "remove", "test"],
                       help="What to do.")
    p_api.add_argument("provider", nargs="?", default=None,
                       help="Provider name (e.g. semantic_scholar, pubmed, crossref). "
                            "Required for add/rotate/remove/test; ignored for list.")
    p_api.add_argument("--from-env", dest="from_env", default=None,
                       help="Read the key from this environment variable instead of "
                            "prompting (used in CI).")
    p_api.add_argument("--no-color", action="store_true",
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

    # ── daemon ──────────────────────────────────────────────────────────
    # v4 multi-protocol gateway daemon. Phase 0: skeleton + status only.
    # See docs/v4/ROADMAP.md for the full architecture + phase plan.
    p_daemon = sub.add_parser(
        "daemon",
        help="Run / inspect the v4 multi-protocol gateway daemon (preview).",
        description=(
            "The Research OS daemon is a persistent, headless, localhost\n"
            "service that owns the master execution state machine and (in\n"
            "later phases) exposes an OpenAI-compatible gateway, a read-only\n"
            "MCP telemetry sidecar, a sandbox, and a web dashboard.\n\n"
            "PREVIEW: Phase 0 ships the skeleton. 'daemon status' works now;\n"
            "'daemon start' is not serving yet. Track docs/v4/ROADMAP.md.\n\n"
            "Examples:\n"
            "  research-os daemon status            # show daemon + project state\n"
            "  research-os daemon status --json     # machine-readable\n"
            "  research-os daemon start             # (preview) not serving yet"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    daemon_sub = p_daemon.add_subparsers(dest="daemon_command")
    pd_status = daemon_sub.add_parser(
        "status", help="Show daemon + active-project state (read-only)."
    )
    pd_status.add_argument("--json", dest="as_json", action="store_true",
                           help="Emit machine-readable JSON.")
    pd_status.add_argument("--workspace", default=None,
                           help="Explicit workspace path (else auto-resolved).")
    pd_start = daemon_sub.add_parser(
        "start", help="Start the daemon serving loop (localhost HTTP, read-only API)."
    )
    pd_start.add_argument("--workspace", default=None,
                          help="Explicit workspace path (else auto-resolved).")
    pd_start.add_argument("--host", default=None, help="Bind host (default 127.0.0.1).")
    pd_start.add_argument("--port", default=None, type=int, help="Bind port (default 8787).")

    # run: execute any command as a tracked, provenance-recording run.
    pd_run = daemon_sub.add_parser(
        "run",
        help="Run a command as a tracked job (provenance + artifacts recorded).",
        description=(
            "Execute any shell command as a Research OS run. The command's\n"
            "output streams to your terminal; on completion a durable record\n"
            "(command, environment, git commit, input/output artifact hashes,\n"
            "timestamps) is written to .os_state/runs/<id>/. This is the\n"
            "human door to the same durable-run machinery the daemon API uses.\n\n"
            "Examples:\n"
            "  research-os daemon run -- python analyze.py --in data.csv\n"
            "  research-os daemon run --name fig3 -- Rscript plot.R\n"
            "  research-os daemon run --json -- snakemake -j4"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pd_run.add_argument("--workspace", default=None,
                        help="Explicit workspace path (else auto-resolved).")
    pd_run.add_argument("--name", default=None, help="Human label for the run.")
    pd_run.add_argument("--cwd", default=None,
                        help="Working directory for the command (default: workspace root).")
    pd_run.add_argument("--no-artifacts", dest="no_artifacts", action="store_true",
                        help="Skip output-artifact detection for this run.")
    pd_run.add_argument("--json", dest="as_json", action="store_true",
                        help="Emit the run manifest as JSON on completion.")
    pd_run.add_argument("cmd", nargs=argparse.REMAINDER,
                        help="The command to run (use -- to separate it from flags).")

    # runs: list the durable run history.
    pd_runs = daemon_sub.add_parser(
        "runs", help="List recorded runs (durable history) for the workspace."
    )
    pd_runs.add_argument("--workspace", default=None,
                         help="Explicit workspace path (else auto-resolved).")
    pd_runs.add_argument("--limit", default=20, type=int, help="Max runs to show.")
    pd_runs.add_argument("--json", dest="as_json", action="store_true",
                         help="Emit machine-readable JSON.")

    # logs: show one run's manifest + captured log.
    pd_logs = daemon_sub.add_parser(
        "logs", help="Show a recorded run's details + captured output."
    )
    pd_logs.add_argument("run_id", help="The run id (from 'daemon runs').")
    pd_logs.add_argument("--workspace", default=None,
                         help="Explicit workspace path (else auto-resolved).")
    pd_logs.add_argument("--tail", default=0, type=int,
                         help="Show only the last N log lines (0 = full log).")
    pd_logs.add_argument("--json", dest="as_json", action="store_true",
                         help="Emit the full manifest as JSON.")

    # reproduce: re-run a recorded run and compare its outputs.
    pd_repro = daemon_sub.add_parser(
        "reproduce",
        help="Re-run a recorded run and check its outputs still match.",
    )
    pd_repro.add_argument("run_id", help="The run id to reproduce (from 'daemon runs').")
    pd_repro.add_argument("--workspace", default=None,
                          help="Explicit workspace path (else auto-resolved).")
    pd_repro.add_argument("--cwd", default=None,
                          help="Override the working directory for the re-run.")
    pd_repro.add_argument("--timeout", default=0, type=float,
                          help="Max seconds to wait for the re-run (0 = no limit).")
    pd_repro.add_argument("--json", dest="as_json", action="store_true",
                          help="Emit the full reproduction report as JSON.")

    # submit: hand a job to an HPC scheduler (SLURM, …).
    pd_submit = daemon_sub.add_parser(
        "submit",
        help="Submit a job to an HPC scheduler (SLURM) with full provenance.",
    )
    pd_submit.add_argument("script",
                           help="Batch script path, or inline command string.")
    pd_submit.add_argument("--scheduler", default="slurm",
                           help="Scheduler backend (default: slurm).")
    pd_submit.add_argument("--workspace", default=None,
                           help="Explicit workspace path (else auto-resolved).")
    pd_submit.add_argument("--cwd", default=None,
                           help="Working directory for the job (default: workspace).")
    pd_submit.add_argument("--name", default=None, help="Human-friendly job name.")
    pd_submit.add_argument("--poll", default=5.0, type=float,
                           help="Scheduler poll interval in seconds (default: 5).")
    pd_submit.add_argument("--json", dest="as_json", action="store_true",
                           help="Emit the submitted job id as JSON.")

    # ── doctor ──────────────────────────────────────────────────────────
    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnose install + workspace health (returns exit code 0/1/2).",
        description=(
            "Run a battery of health checks against the install and (if "
            "invoked inside a workspace) the workspace itself. Prints a\n"
            "coloured summary, exits 0 (all pass), 1 (warnings only), or\n"
            "2 (failures present).\n\n"
            "Checks include: python version, conda env, version consistency,\n"
            "pack registration, embeddings freshness, typst / chromium on\n"
            "PATH, IDE MCP wiring, orphan figures, stale step_summary,\n"
            "unresolved BLOCK gates, disk usage, git cleanliness, and\n"
            ".gitignore coverage.\n\n"
            "Examples:\n"
            "  research-os doctor                    # full report\n"
            "  research-os doctor --json             # machine-readable\n"
            "  research-os doctor --verbose          # show fix hints for passing checks\n"
            "  research-os doctor --workspace-only   # skip install checks\n"
            "  research-os doctor --workspace .      # explicit workspace path"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_doctor.add_argument("--verbose", action="store_true",
                          help="Show fix hints even for passing checks.")
    p_doctor.add_argument("--workspace-only", dest="workspace_only",
                          action="store_true",
                          help="Skip install checks; only run workspace checks.")
    p_doctor.add_argument("--workspace", default=None,
                          help="Explicit workspace path (default: walk up from CWD).")
    p_doctor.add_argument("--json", action="store_true",
                          help="Emit JSON instead of the human-readable report.")
    p_doctor.add_argument("--no-color", action="store_true",
                          help="Disable ANSI styling. Auto-disabled when NO_COLOR is set.")

    # ── refresh ─────────────────────────────────────────────────────────
    p_refresh = sub.add_parser(
        "refresh",
        help="Refresh project copies of AGENTS.md / CLAUDE.md / IDE rules from the bundled templates.",
        description=(
            "Detect drift between a project's copies of bundled templates\n"
            "(AGENTS.md, CLAUDE.md, .claude/rules/research-os.md, IDE rule\n"
            "files) and the version shipped with this `research-os` install.\n\n"
            "Templates evolve across releases; the wizard only copies them\n"
            "once at init, so a project that's been around for a few\n"
            "releases can be teaching the AI a stale tool surface or\n"
            "out-of-date hard rules. `refresh` shows the gap and (with\n"
            "--write) overwrites the project copies in place.\n\n"
            "Read-only by default. --check exits non-zero on drift so CI\n"
            "can fail if the project gets out of sync.\n\n"
            "Examples:\n"
            "  research-os refresh             # report drift (default)\n"
            "  research-os refresh --check     # report + exit 1 if drift\n"
            "  research-os refresh --write     # prompt per-file, overwrite\n"
            "  research-os refresh --write --yes  # overwrite every drifted file\n"
            "  research-os refresh --json      # machine-readable report"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_refresh.add_argument(
        "--check", action="store_true",
        help="Report only; exit non-zero if any project copy has drifted.",
    )
    p_refresh.add_argument(
        "--write", action="store_true",
        help="Overwrite drifted project copies with the bundled template.",
    )
    p_refresh.add_argument(
        "-y", "--yes", action="store_true",
        help="With --write, skip the per-file confirmation prompt.",
    )
    p_refresh.add_argument(
        "--regen-readme", action="store_true",
        help="Also regenerate the project-root README.md with the current "
             "step inventory + synthesis deliverable list (use at project "
             "finalize to refresh the GitHub front page).",
    )
    p_refresh.add_argument(
        "--workspace", default=None,
        help="Explicit workspace path (default: walk up from CWD).",
    )
    p_refresh.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of the human-readable report.",
    )
    p_refresh.add_argument(
        "--no-color", action="store_true",
        help="Disable ANSI styling. Auto-disabled when NO_COLOR is set.",
    )

    # ── completion ──────────────────────────────────────────────────────
    p_completion = sub.add_parser(
        "completion",
        help="Print a sourceable shell completion script (bash | zsh | fish).",
        description=(
            "Emit a shell-completion script for `research-os` to stdout.\n\n"
            "Install (zsh): eval \"$(research-os completion zsh)\"\n"
            "Install (bash): eval \"$(research-os completion bash)\"\n"
            "Install (fish): research-os completion fish | source\n\n"
            "Tab-completes subcommand names and --ide values."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_completion.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to emit completion script for.",
    )

    return parser


def main() -> None:
    parser = build_parser()

    # Activate argcomplete if the optional dep is installed; otherwise this
    # is a no-op. argcomplete short-circuits the process when invoked by the
    # shell-completion machinery.
    try:
        import argcomplete  # type: ignore
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "ide":
        cmd_ide(args)
    elif args.command == "mcp":
        # Positional `name` wins over `--name`; argparse stores --name as name_flag.
        if not getattr(args, "name", None) and getattr(args, "name_flag", None):
            args.name = args.name_flag
        sys.exit(cmd_mcp(args))
    elif args.command == "hermes":
        sys.exit(cmd_hermes(args))
    elif args.command == "route":
        sys.exit(cmd_route(args))
    elif args.command == "api-key":
        sys.exit(cmd_api_key(args))
    elif args.command == "start":
        cmd_start(args)
    elif args.command == "daemon":
        sys.exit(cmd_daemon(args))
    elif args.command == "doctor":
        from research_os.cli_doctor import cmd_doctor
        sys.exit(cmd_doctor(args))
    elif args.command == "refresh":
        sys.exit(cmd_refresh(args))
    elif args.command == "completion":
        sys.exit(cmd_completion(args))
    else:
        parser.print_help()
        print()
        print("  Tip: 'research-os init' to scaffold, then open your IDE and chat with the AI.")


if __name__ == "__main__":
    main()
