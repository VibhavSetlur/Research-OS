"""Iterative planning — the AI repeatedly proposes the BEST next step.

Some researchers don't want to dictate every move ("now run X, now run Y").
They want the AI to assess the current state, search literature + tools, and
propose what's most worth doing next. This module supports that workflow.

Public functions
----------------
* ``plan_next_step``       — propose the best next step given current state.
* ``branch_recommendation`` — when to fork a parallel experiment vs continue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.research.planning")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_plan(root: Path, body: str) -> str:
    """Write a planning document into the active step (or workspace/logs)."""
    from research_os.tools.actions.audit.audit import get_current_path

    current = get_current_path(root)
    target_dir = (
        root / "workspace" / current / "outputs" / "reports"
        if current
        else root / "workspace" / "logs"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = target_dir / f"next_step_plan_{ts}.md"
    out.write_text(body)
    return str(out.relative_to(root))


def plan_next_step(root: Path, *, goal: str | None = None,
                   search_literature: bool = True,
                   search_tools: bool = True) -> dict[str, Any]:
    """Survey current state + search the world + propose the best next step.

    Pulls together:
      - active hypotheses (from state)
      - completed and active experiment paths
      - latest conclusions
      - audit warnings (if audit_report.md exists)
      - fresh literature on the open questions
      - tool candidates if a methodological question is open
    Returns a structured plan and writes it as a markdown into the active step.
    """
    try:
        from research_os.project_ops import load_state
        from research_os.tools.actions.search.search import search_semantic_scholar, search_web
        from research_os.tools.actions.state.path import list_paths

        state = load_state(root)
        paths_info = list_paths(root).get("paths", []) or []
        active = [p for p in paths_info if p.get("status") == "active"]
        completed = [p for p in paths_info if p.get("status") == "completed"]
        dead = [p for p in paths_info if p.get("status") == "dead_end"]
        hypotheses = state.get("active_hypotheses", []) or []

        # ── Pull recent conclusions ─────────────────────────────────────
        recent_conclusions: list[dict[str, str]] = []
        for p in (active + completed)[-3:]:
            conc_path = Path(p["experiment_dir"]) / "conclusions.md"
            if conc_path.exists():
                recent_conclusions.append(
                    {"path": p["path_id"], "text": conc_path.read_text()[:2000]}
                )

        # ── Pull audit warnings ────────────────────────────────────────
        audit_report = root / "workspace" / "logs" / "audit_report.md"
        audit_text = audit_report.read_text()[:2000] if audit_report.exists() else ""

        # ── Decide what to search ──────────────────────────────────────
        question = (
            goal
            or (
                state.get("research_question")
                or (hypotheses[0].get("statement") if hypotheses else "")
                or "next analytical step"
            )
        )

        lit_hits: list[dict[str, Any]] = []
        if search_literature:
            try:
                lit_hits = search_semantic_scholar(question, limit=5)
            except Exception as e:
                logger.warning(f"plan literature search failed: {e}")

        tool_hits: list[dict[str, Any]] = []
        if search_tools and goal:
            try:
                web = search_web(f"{goal} library tool", limit=5)
                tool_hits = web.get("results", [])
            except Exception as e:
                logger.warning(f"plan tool search failed: {e}")

        # ── Build the recommendation ───────────────────────────────────
        # Heuristics for what to do next:
        recommendations: list[str] = []
        untested = [h for h in hypotheses if h.get("status") == "testing"]
        refuted = [h for h in hypotheses if h.get("status") == "refuted"]

        if not hypotheses:
            recommendations.append(
                "No hypotheses tracked. Run `tool_intake_autofill` or register "
                "hypotheses with `mem_hypothesis_add` before more experiments."
            )
        elif untested:
            recommendations.append(
                f"Open hypotheses without conclusive evidence: "
                f"{', '.join(h['id'] for h in untested)}. Design a new experiment "
                "targeting one of them via `guidance/analysis_plan`."
            )
        elif refuted and not completed:
            recommendations.append(
                "All current hypotheses refuted. Either revise the research "
                "question (`docs/research_overview.md`) or branch to a different "
                "methodological angle via `guidance/dead_end_routing`."
            )
        if dead:
            recommendations.append(
                f"{len(dead)} dead-end path(s) on record. Review their "
                "`conclusions.md` before re-trying similar approaches."
            )
        if audit_text and "BLOCKER" in audit_text:
            recommendations.append(
                "Audit has BLOCKER warnings. Resolve those before any synthesis."
            )
        if state.get("pipeline_stage") in {"execution", "analysis"} and not active:
            recommendations.append(
                "No active experiment path. Create one via `sys_path(operation='create')` "
                "before writing scripts."
            )

        # ── Write the plan markdown ────────────────────────────────────
        lines = [
            f"# Next-step plan — {_now()}",
            "",
            "## Project state",
            f"- Stage: `{state.get('pipeline_stage', 'init')}`",
            f"- Active paths: {len(active)} · completed: {len(completed)} · dead: {len(dead)}",
            f"- Hypotheses tracked: {len(hypotheses)} "
            f"(testing: {len(untested)}, refuted: {len(refuted)})",
            "",
            "## Recent conclusions",
        ]
        if not recent_conclusions:
            lines.append("- (none yet)")
        for c in recent_conclusions:
            lines.append(f"### `{c['path']}`")
            lines.append("```")
            lines.append(c["text"])
            lines.append("```")

        if audit_text:
            lines.extend(["", "## Latest audit (head)", "```", audit_text, "```"])

        lines.extend(["", "## Fresh literature on the open question", ""])
        if not lit_hits:
            lines.append("- (no literature retrieved — provider may be down)")
        for paper in lit_hits[:5]:
            title = (paper.get("title") or "")[:140]
            year = paper.get("year") or ""
            url = paper.get("url") or ""
            lines.append(f"- **{title}** ({year}) {url}")

        if tool_hits:
            lines.extend(["", "## Tool / library candidates", ""])
            for t in tool_hits[:5]:
                lines.append(f"- **{t.get('title', '')[:120]}** — {t.get('url', '')}")

        lines.extend(["", "## Recommended next steps", ""])
        if not recommendations:
            recommendations.append(
                "Pipeline looks healthy. Suggested next: continue "
                "`guidance/analysis_plan` for the next hypothesis, OR move to "
                "`reproducibility/reproducibility` if all experiments are done."
            )
        for r in recommendations:
            lines.append(f"- {r}")

        lines.extend(
            [
                "",
                "## How to act",
                "1. Read the recommendations above + the fresh literature.",
                "2. Pick ONE next step. Tell the researcher what you chose and why.",
                "3. Log the decision: `mem_log(kind='decision', context='next-step plan', "
                "selected=<your-pick>, rationale=<short>)`",
                "4. Load the matching protocol (analysis_plan, dead_end_routing,",
                "   reproducibility, synthesis_paper, …) and proceed.",
            ]
        )

        plan_path = _write_plan(root, "\n".join(lines) + "\n")

        return {
            "status": "success",
            "plan_path": plan_path,
            "recommendations": recommendations,
            "open_hypotheses": [h["id"] for h in untested],
            "literature_hits": len(lit_hits),
            "tool_hits": len(tool_hits),
        }
    except Exception as e:
        logger.exception("plan_next_step failed")
        return {"status": "error", "message": str(e)}


def session_resume(root: Path) -> dict[str, Any]:
    """Reconstruct intent + status from logs so the AI can pick back up.

    Combines: state ledger summary, recent protocol-log entries, last few
    analysis/methods lines, hypothesis registry, live background tasks. The
    output is a structured "resume brief" the AI can hand the researcher in
    one message.
    """
    try:
        import json as _json

        from research_os.project_ops import load_state
        from research_os.tools.actions.exec.tasks import task_list
        from research_os.tools.actions.protocol import get_protocol_history
        from research_os.tools.actions.state.path import list_paths

        state = load_state(root)
        history = get_protocol_history(root, limit=10)
        paths = list_paths(root).get("paths", []) or []
        hypotheses = state.get("active_hypotheses", []) or []

        # Tail analysis + methods.
        def _tail(path: Path, lines: int = 30) -> list[str]:
            if not path.exists():
                return []
            try:
                return path.read_text(errors="replace").splitlines()[-lines:]
            except OSError:
                return []

        analysis_tail = _tail(root / "workspace" / "analysis.md", 30)
        methods_tail = _tail(root / "workspace" / "methods.md", 20)

        # Latest handoff doc, if any.
        handoffs_dir = root / ".os_state" / "handoffs"
        latest_handoff: str | None = None
        if handoffs_dir.exists():
            candidates = sorted(
                (p for p in handoffs_dir.iterdir() if p.suffix == ".md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                latest_handoff = str(candidates[0].relative_to(root))

        # Live tasks.
        tasks = task_list(root).get("tasks", []) or []
        running = [t for t in tasks if t.get("task_status") == "running"]
        finished = [t for t in tasks if t.get("task_status") == "finished"]

        # Classify pause reason from history.
        entries = history.get("entries", []) if isinstance(history, dict) else []
        last_entry = entries[-1] if entries else None
        pause_reason = "unknown"
        if not entries:
            pause_reason = "fresh_session"
        elif last_entry and last_entry.get("status") == "started":
            pause_reason = "mid_step"
        elif last_entry and (
            # The execution log writes the field as 'protocol'; tolerate the
            # legacy 'protocol_name' so dead-end detection actually fires.
            (last_entry.get("protocol") or last_entry.get("protocol_name") or "")
        ).endswith("dead_end_routing"):
            pause_reason = "dead_end"
        elif latest_handoff:
            pause_reason = "ctx_exhaustion"
        elif running:
            pause_reason = "long_running_job"
        elif last_entry and last_entry.get("status") == "completed":
            pause_reason = "completed_step"

        # Recommend a next protocol.
        from research_os.tools.actions.protocol import get_next_protocol

        next_proto = get_next_protocol(root)

        active = [p for p in paths if p.get("status") == "active"]
        completed = [p for p in paths if p.get("status") == "completed"]
        dead = [p for p in paths if p.get("status") == "dead_end"]

        brief = {
            "status": "success",
            "project_name": state.get("project_name")
            or state.get("project", "(unnamed)"),
            "pipeline_stage": state.get("pipeline_stage", state.get("phase", "init")),
            "current_path": state.get("current_path", "main"),
            "pause_reason": pause_reason,
            "last_protocol_entry": last_entry,
            "paths_counts": {
                "active": len(active),
                "completed": len(completed),
                "dead_end": len(dead),
            },
            "active_path_ids": [p.get("path_id") for p in active],
            "hypotheses": hypotheses,
            "background_tasks": {
                "running": [
                    {
                        "task_id": t.get("task_id"),
                        "pid": t.get("pid"),
                        "command": t.get("command"),
                        "started_at": t.get("started_at"),
                    }
                    for t in running
                ],
                "finished_count": len(finished),
            },
            "latest_handoff": latest_handoff,
            "analysis_tail": analysis_tail,
            "methods_tail": methods_tail,
            "recommended_next_protocol": next_proto,
            "resume_message": _format_resume_brief(
                project=state.get("project_name") or state.get("project", "Project"),
                stage=state.get("pipeline_stage", "init"),
                path=state.get("current_path", "main"),
                pause_reason=pause_reason,
                hypotheses=hypotheses,
                running=running,
                finished_count=len(finished),
                next_proto=next_proto,
            ),
        }
        # Persist a tiny resume record so future sessions know the trail.
        rec_dir = root / ".os_state" / "handoffs"
        rec_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rec_path = rec_dir / f"resume_{ts}.json"
        try:
            rec_path.write_text(_json.dumps(brief, indent=2, default=str))
            brief["resume_record"] = str(rec_path.relative_to(root))
        except OSError:
            pass
        return brief
    except Exception as e:
        logger.exception("session_resume failed")
        return {"status": "error", "message": str(e)}


def _format_resume_brief(
    *,
    project: str,
    stage: str,
    path: str,
    pause_reason: str,
    hypotheses: list,
    running: list,
    finished_count: int,
    next_proto: Any,
) -> str:
    """One-message brief the AI can paste back to the researcher verbatim."""
    h_str = (
        ", ".join(
            f"{h.get('id', '?')}={h.get('status', '?')}"
            for h in hypotheses
            if isinstance(h, dict)
        )
        or "(none)"
    )
    next_name = ""
    if isinstance(next_proto, dict):
        next_name = next_proto.get("protocol_name") or next_proto.get("name") or ""
    running_str = (
        f"{len(running)} running" if running else "none"
    ) + (f", {finished_count} finished" if finished_count else "")
    return (
        f"**Resume brief** — {project}\n"
        f"- Stage: `{stage}` · current path: `{path}`\n"
        f"- Why we stopped: `{pause_reason}`\n"
        f"- Hypotheses: {h_str}\n"
        f"- Background tasks: {running_str}\n"
        f"- Recommended next protocol: `{next_name or 'see sys_protocol_next'}`\n"
        "Continue the recommended next protocol, switch tracks, or start "
        "something new?"
    )


def progress_digest(root: Path) -> dict[str, Any]:
    """One-page digest of the project's state and accomplishments.

    Tallies: experiment steps (active / completed / dead-end), hypotheses
    by status, citations counted in workspace/citations.md, figures and
    tables produced across every step. Writes the digest to
    workspace/logs/progress_digest.md and also returns it as a string.
    """
    try:
        from research_os.project_ops import load_state
        from research_os.tools.actions.state.path import list_paths

        state = load_state(root)
        paths = list_paths(root).get("paths", []) or []
        hypotheses = state.get("active_hypotheses", []) or []

        active = [p for p in paths if p.get("status") == "active"]
        completed = [p for p in paths if p.get("status") == "completed"]
        dead = [p for p in paths if p.get("status") == "dead_end"]

        # Count outputs across all steps.
        figures = 0
        tables = 0
        reports = 0
        for p in paths:
            ed = Path(p.get("experiment_dir", root / "workspace" / p.get("path_id", "")))
            fig_dir = ed / "outputs" / "figures"
            tab_dir = ed / "outputs" / "tables"
            rep_dir = ed / "outputs" / "reports"
            if fig_dir.exists():
                figures += sum(
                    1 for f in fig_dir.iterdir() if f.suffix.lower() in
                    {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".tiff"}
                )
            if tab_dir.exists():
                tables += sum(
                    1 for f in tab_dir.iterdir() if f.suffix.lower() in
                    {".csv", ".tsv", ".md", ".html"}
                )
            if rep_dir.exists():
                reports += sum(1 for f in rep_dir.iterdir() if f.suffix == ".md")

        # Citations.
        citations_md = root / "workspace" / "citations.md"
        citation_count = 0
        if citations_md.exists():
            try:
                lines = citations_md.read_text().splitlines()
                # Heuristic: count lines that look like a citation entry.
                citation_count = sum(
                    1 for ln in lines if ln.strip().startswith(("- ", "* ", "["))
                )
            except OSError:
                citation_count = 0

        by_status = {"testing": 0, "supported": 0, "refuted": 0, "inconclusive": 0}
        for h in hypotheses:
            if isinstance(h, dict):
                by_status[h.get("status", "testing")] = (
                    by_status.get(h.get("status", "testing"), 0) + 1
                )

        digest_lines = [
            f"# Progress digest — {_now()}",
            "",
            f"**Project**: {state.get('project_name', '(unnamed)')}",
            f"**Stage**: `{state.get('pipeline_stage', 'init')}` "
            f"· **current path**: `{state.get('current_path', 'main')}`",
            "",
            "## Experiments",
            f"- Active: {len(active)}",
            f"- Completed: {len(completed)}",
            f"- Dead-end: {len(dead)}",
            "",
            "## Hypotheses",
        ]
        for status, count in by_status.items():
            digest_lines.append(f"- {status}: {count}")
        digest_lines.extend([
            "",
            "## Outputs",
            f"- Figures: {figures}",
            f"- Tables: {tables}",
            f"- Reports: {reports}",
            f"- Citations (workspace/citations.md): {citation_count}",
            "",
            "## What's next",
        ])
        if state.get("pipeline_stage", "init") == "init":
            digest_lines.append("- Run `tool_intake_autofill` to bootstrap.")
        elif by_status["testing"] > 0:
            digest_lines.append(
                f"- {by_status['testing']} hypothesis/es still under test — "
                "design the next experiment."
            )
        elif active:
            digest_lines.append(
                f"- Active path(s) {[p['path_id'] for p in active]} still need "
                "conclusions.md."
            )
        else:
            digest_lines.append(
                "- All experiments converged. Consider `tool_synthesize` for "
                "the writeup."
            )

        body = "\n".join(digest_lines) + "\n"
        out_path = root / "workspace" / "logs" / "progress_digest.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body)

        return {
            "status": "success",
            "digest_path": str(out_path.relative_to(root)),
            "experiments": {
                "active": len(active),
                "completed": len(completed),
                "dead_end": len(dead),
            },
            "hypotheses_by_status": by_status,
            "outputs": {
                "figures": figures,
                "tables": tables,
                "reports": reports,
                "citations": citation_count,
            },
            "digest_markdown": body,
        }
    except Exception as e:
        logger.exception("progress_digest failed")
        return {"status": "error", "message": str(e)}


def dead_end_lessons(root: Path) -> dict[str, Any]:
    """Extract reusable lessons from every abandoned experiment path.

    Reads each ``__DEAD_END`` folder's conclusions.md and pulls out the
    "Why this path failed" section (if present), the methods that were
    tried, and any explicit recommendation against repeating the pattern.
    """
    try:
        from research_os.tools.actions.state.path import list_paths

        paths = list_paths(root).get("paths", []) or []
        dead = [p for p in paths if p.get("status") == "dead_end"]
        lessons: list[dict[str, str]] = []
        for p in dead:
            ed = Path(p.get("experiment_dir", root / "workspace" / p.get("path_id", "")))
            conc = ed / "conclusions.md"
            if not conc.exists():
                lessons.append(
                    {
                        "path_id": p.get("path_id", ""),
                        "lesson": "(no conclusions.md — abandoned without rationale)",
                        "methods_tried": "",
                    }
                )
                continue
            text = conc.read_text(errors="replace")
            why = ""
            in_why = False
            why_lines: list[str] = []
            for line in text.splitlines():
                if line.lower().startswith(("## why", "### why")):
                    in_why = True
                    continue
                if in_why:
                    if line.startswith("#"):
                        break
                    why_lines.append(line)
            why = "\n".join(why_lines).strip() or "(no 'Why this path failed' section)"

            # Pull the methods that were tried — heuristic.
            scripts_dir = ed / "scripts"
            methods_tried = ""
            if scripts_dir.exists():
                methods_tried = ", ".join(
                    s.stem for s in scripts_dir.iterdir() if s.is_file()
                )
            lessons.append(
                {
                    "path_id": p.get("path_id", ""),
                    "lesson": why[:600],
                    "methods_tried": methods_tried,
                }
            )

        # Persist
        out_path = root / "workspace" / "logs" / "dead_end_lessons.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body = [f"# Dead-end lessons — {_now()}", ""]
        if not lessons:
            body.append("*(no dead-end paths recorded)*")
        for lesson in lessons:
            body.append(f"## `{lesson['path_id']}`")
            if lesson.get("methods_tried"):
                body.append(f"- Methods tried: {lesson['methods_tried']}")
            body.append("- Lesson:")
            body.append("```")
            body.append(lesson["lesson"])
            body.append("```")
            body.append("")
        out_path.write_text("\n".join(body) + "\n")

        return {
            "status": "success",
            "dead_end_count": len(lessons),
            "lessons": lessons,
            "report_path": str(out_path.relative_to(root)),
        }
    except Exception as e:
        logger.exception("dead_end_lessons failed")
        return {"status": "error", "message": str(e)}


def quick_review(
    root: Path,
    paper_path: str,
    *,
    lens: str = "claims_vs_evidence",
) -> dict[str, Any]:
    """Stage a quick-paper-review brief — fills the scaffold, AI populates.

    Writes a structured Markdown skeleton to workspace/reviews/<slug>.md so
    the AI fills it according to the ``guidance/quick_paper_review``
    protocol. The skeleton enforces the required headings (verdict,
    strengths, concerns, citations) so the AI cannot skip them.
    """
    try:
        p = root / paper_path
        if not p.exists() and not paper_path.startswith(("http://", "https://")):
            return {
                "status": "error",
                "message": f"Paper not found at {paper_path}",
            }

        slug = (
            p.stem.replace(" ", "_")
            if p.exists()
            else paper_path.rsplit("/", 1)[-1].split("?")[0]
        )
        slug = "".join(c if c.isalnum() or c in "_-" else "_" for c in slug)[:60]
        reviews_dir = root / "workspace" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        out_path = reviews_dir / f"{slug}.md"

        skeleton = (
            f"# Review: {slug}\n"
            f"**Lens**: {lens}\n"
            f"**Reviewer**: Research OS quick_paper_review · {_now()}\n"
            "**Verdict**: <accept | minor revise | major revise | reject>\n"
            "**One-line TLDR**: …\n\n"
            "## Three strengths\n"
            "1. …\n2. …\n3. …\n\n"
            "## Five concerns (most → least severe)\n"
            "1. **<concern>** — *(severity: critical|major|minor)* — evidence + why.\n"
            "2. …\n3. …\n4. …\n5. …\n\n"
            "## Suggested citations the authors should engage\n"
            "- <cite_key>: <one-line relevance>\n\n"
            "## Reviewer notes (private)\n"
            "- Method grounded against: …\n"
            "- Stats sniff-tested: …\n"
        )
        out_path.write_text(skeleton)
        return {
            "status": "success",
            "review_path": str(out_path.relative_to(root)),
            "lens": lens,
            "next_action": (
                "Follow `guidance/quick_paper_review`: read the paper, ground "
                "the method via `tool_research_method`, then fill in the "
                "skeleton at the path above."
            ),
        }
    except Exception as e:
        logger.exception("quick_review failed")
        return {"status": "error", "message": str(e)}


def branch_recommendation(root: Path, *, reason: str) -> dict[str, Any]:
    """Decide: branch into a new parallel experiment, or extend the current one.

    Use when you have a working pipeline but want to try an alternative
    methodology / model / preprocessing without abandoning the current path.
    """
    try:
        from research_os.tools.actions.state.path import list_paths

        paths = list_paths(root).get("paths", []) or []
        active = [p for p in paths if p.get("status") == "active"]
        recommendation = (
            "branch"
            if len(active) <= 2
            else "extend_current"
        )
        guidance = {
            "branch": (
                "Create a parallel experiment via `sys_path(operation='create')` with a NEW "
                "slug describing the alternative approach. The branched path "
                "becomes current_path; you can switch back later by referencing "
                "the old folder."
            ),
            "extend_current": (
                "You already have multiple active paths. Finish the current line "
                "of analysis (write conclusions.md, snapshot env) BEFORE forking "
                "again. Branching too aggressively makes synthesis harder."
            ),
        }[recommendation]
        return {
            "status": "success",
            "recommendation": recommendation,
            "reason": reason,
            "active_paths": [p["path_id"] for p in active],
            "guidance": guidance,
        }
    except Exception as e:
        logger.exception("branch_recommendation failed")
        return {"status": "error", "message": str(e)}
