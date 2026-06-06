"""Research / reasoning tools — help the AI ground its choices in sources.

These tools collect evidence from the web + literature for a specific decision,
then return a structured report the AI uses to commit a decision (and log it).
They do NOT make the decision for the AI — they ensure the AI never picks a
method or library from training memory alone.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.research")


def _write_report(root: Path, kind: str, slug: str, body: str) -> str:
    """Write a research report into the current step (or workspace/logs)."""
    from research_os.tools.actions.audit.audit import get_current_path

    current = get_current_path(root)
    if current:
        out = root / "workspace" / current / "outputs" / "reports" / f"{kind}_{slug}.md"
    else:
        out = root / "workspace" / "logs" / f"{kind}_{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    return str(out.relative_to(root))


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")[:40] or "item"


# ---------------------------------------------------------------------------
# Research a method
# ---------------------------------------------------------------------------


def research_method(query: str, root: Path, limit: int = 5) -> dict[str, Any]:
    """Deep-dive a statistical / computational method.

    Pulls 5-10 sources across multiple providers, extracts assumptions,
    typical sample-size requirements, common pitfalls, and recommended
    implementations. Writes a structured markdown report and returns the
    parsed evidence so the AI can choose.
    """
    try:
        from research_os.tools.actions.search.search import (
            search_crossref,
            search_pubmed,
            search_semantic_scholar,
            search_web,
        )

        sources: list[dict[str, Any]] = []

        # 1. Academic providers (always free; cached).
        try:
            for paper in search_semantic_scholar(query, limit=limit)[:limit]:
                sources.append({**paper, "provider": "semantic_scholar"})
        except Exception as e:
            logger.warning(f"s2 lookup failed: {e}")

        try:
            for paper in search_crossref(query, limit=limit)[:limit]:
                sources.append({**paper, "provider": "crossref"})
        except Exception as e:
            logger.warning(f"crossref lookup failed: {e}")

        try:
            for paper in search_pubmed(query, limit=limit)[:limit]:
                sources.append({**paper, "provider": "pubmed"})
        except Exception as e:
            logger.warning(f"pubmed lookup failed: {e}")

        # 2. Best-practice / docs (web).
        web_results = []
        try:
            web = search_web(f"{query} best practices assumptions", limit=limit)
            web_results = web.get("results", [])[:limit]
        except Exception as e:
            logger.warning(f"web lookup failed: {e}")

        # 3. Dedupe academic by DOI / title.
        seen: set[str] = set()
        unique_academic: list[dict[str, Any]] = []
        for src in sources:
            key = (src.get("doi") or src.get("url") or src.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_academic.append(src)

        # 4. Build the report.
        lines = [
            f"# Method research — {query}",
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
            "",
            "## Sources (academic, deduplicated)",
            "",
        ]
        if not unique_academic:
            lines.append("- (no academic sources found — falling back to web only)")
        for src in unique_academic[:10]:
            title = (src.get("title") or "")[:140]
            year = src.get("year") or ""
            authors = ", ".join((src.get("authors") or [])[:3])
            url = src.get("url") or src.get("doi") or ""
            lines.append(f"- **{title}** · {authors} ({year}) · `{src.get('provider')}`")
            if url:
                lines.append(f"  {url}")
            abstract = (src.get("abstract") or "").strip()
            if abstract:
                lines.append(f"  > {abstract[:400]}{'…' if len(abstract) > 400 else ''}")

        lines.extend(["", "## Best-practice / web sources", ""])
        if not web_results:
            lines.append("- (no web sources retrieved — provider may be unconfigured)")
        for r in web_results:
            t = (r.get("title") or "")[:140]
            u = r.get("url") or ""
            d = (r.get("description") or "")[:300]
            lines.append(f"- **{t}** {u}\n  > {d}")

        lines.extend(
            [
                "",
                "## What the AI must extract next",
                "Read each abstract / page and synthesise:",
                "1. Core assumptions (each must be testable).",
                "2. Typical sample-size requirements / power.",
                "3. Common pitfalls and how the literature mitigates them.",
                "4. Recommended implementations (library + version, language).",
                "5. Alternatives if assumptions fail.",
                "",
                "Then call `mem_log(kind='methods', ...)` to commit the chosen method and",
                "`mem_log(kind='decision', context=..., selected=..., rationale=...)`.",
            ]
        )
        report_path = _write_report(root, "method_research", _slug(query), "\n".join(lines) + "\n")

        return {
            "status": "success",
            "query": query,
            "academic_count": len(unique_academic),
            "web_count": len(web_results),
            "academic": unique_academic[:10],
            "web": web_results,
            "report_path": report_path,
            "next_action": (
                "Synthesise the evidence into mem_log(kind='methods') + "
                "mem_log(kind='decision') before writing any analysis script."
            ),
        }
    except Exception as e:
        logger.exception("research_method failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Research a tool / library / website
# ---------------------------------------------------------------------------


def research_tool(task: str, root: Path, language: str = "any") -> dict[str, Any]:
    """Find candidate tools for a task — libraries, CLIs, websites, services.

    Returns a structured evaluation report. Includes external/web tools that
    the AI cannot run directly — in that case the AI should write a
    WORKSHEET.md for the researcher (see tool_external_tool_instructions).
    """
    try:
        from research_os.tools.actions.search.search import search_web

        queries = [task]
        if language and language != "any":
            queries.append(f"{task} {language} library")
        else:
            queries.append(f"{task} Python library")
            queries.append(f"{task} R package")
        queries.append(f"{task} open source tool")
        queries.append(f"{task} online service")

        all_results: list[dict[str, Any]] = []
        for q in queries:
            try:
                hits = search_web(q, limit=5).get("results", [])
                for h in hits:
                    h["_query"] = q
                    all_results.append(h)
            except Exception as e:
                logger.warning(f"web lookup '{q}' failed: {e}")

        # Dedupe by URL.
        seen: set[str] = set()
        candidates: list[dict[str, Any]] = []
        for r in all_results:
            u = (r.get("url") or "").lower()
            if not u or u in seen:
                continue
            seen.add(u)
            candidates.append(r)

        # Heuristically tag accessibility.
        for c in candidates:
            url = (c.get("url") or "").lower()
            desc = (c.get("description") or "").lower() + " " + (c.get("title") or "").lower()
            tags: list[str] = []
            if any(x in url for x in ("github.com", "gitlab.com", "bitbucket.org")):
                tags.append("source_code")
            if any(x in url for x in ("pypi.org", "anaconda.org", "cran.r-project.org", "juliahub.com")):
                tags.append("installable")
                tags.append("installable_via_package_manager")
            if any(x in desc for x in ("api", "rest", "endpoint")):
                tags.append("api_available")
            if any(x in desc for x in ("web app", "online tool", "browser")):
                tags.append("requires_browser")
                tags.append("external_tool")
            if any(x in desc for x in ("paid", "subscription", "license", "commercial")):
                tags.append("paid_or_licensed")
            c["accessibility_tags"] = tags

        lines = [
            f"# Tool research — {task}",
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
            "",
            f"## Candidates ({len(candidates)})",
            "",
        ]
        for c in candidates[:12]:
            title = (c.get("title") or "")[:140]
            url = c.get("url") or ""
            desc = (c.get("description") or "")[:300]
            tags = ", ".join(c.get("accessibility_tags") or []) or "uncategorised"
            lines.append(f"- **{title}** · `{tags}`\n  {url}\n  > {desc}")

        lines.extend(
            [
                "",
                "## How the AI should choose",
                "1. Prefer `installable_via_package_manager` for reproducibility.",
                "2. If the best option is `external_tool` or `requires_browser` —",
                "   call `tool_external_tool_instructions` to write a WORKSHEET.md",
                "   for the researcher (the AI cannot drive a browser).",
                "3. If the best option is `paid_or_licensed` — flag this to the",
                "   researcher and propose a free alternative ranked second.",
                "4. Check the GitHub repo (if any) for last-commit-date < 12mo and",
                "   star count via `tool_search(source='web')` follow-ups.",
                "5. Commit the decision with `mem_log(kind='decision', ...)`.",
            ]
        )
        report_path = _write_report(root, "tool_research", _slug(task), "\n".join(lines) + "\n")
        return {
            "status": "success",
            "task": task,
            "language": language,
            "count": len(candidates),
            "candidates": candidates[:12],
            "report_path": report_path,
        }
    except Exception as e:
        logger.exception("research_tool failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# External tool instructions — when the AI can't run it
# ---------------------------------------------------------------------------


def external_tool_instructions(
    tool_name: str,
    purpose: str,
    url: str,
    root: Path,
    steps: list[str] | None = None,
) -> dict[str, Any]:
    """Write a WORKSHEET.md telling the researcher how to use an external tool.

    Use when the chosen tool is a website, paid service, GUI app, or anything
    the AI cannot exec in the workspace. The worksheet records inputs the
    researcher must provide, the steps, the expected outputs, and where to
    drop the results back into the workspace.
    """
    try:
        from research_os.tools.actions.audit.audit import get_current_path

        current = get_current_path(root)
        target_dir = (
            root / "workspace" / current if current else root / "workspace" / "logs"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        worksheet = target_dir / f"WORKSHEET_{_slug(tool_name)}.md"

        body_steps = steps or [
            f"1. Open {url}",
            "2. Upload the inputs listed below.",
            "3. Run the tool with the parameters listed below.",
            "4. Download outputs and place them in `data/output/` of this step.",
            "5. Reply to the AI: \"worksheet done, outputs in data/output/\".",
        ]

        body = (
            f"# Worksheet — {tool_name}\n"
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*\n\n"
            f"## Purpose\n{purpose}\n\n"
            f"## Tool URL\n{url}\n\n"
            f"## What the researcher must do\n"
            + "\n".join(body_steps)
            + "\n\n"
            "## Inputs to provide\n*(AI fills this when the worksheet is created)*\n\n"
            "## Parameters\n*(AI fills this)*\n\n"
            "## Expected outputs\n*(AI fills this)*\n\n"
            "## After the researcher signals completion\n"
            "- AI runs `tool_data_profile` on the placed outputs.\n"
            "- AI logs the run via `mem_log(kind='methods', ...)` (method = the external tool name).\n"
            "- AI proceeds with the next step.\n"
        )
        worksheet.write_text(body)
        return {
            "status": "success",
            "worksheet_path": str(worksheet.relative_to(root)),
            "message": (
                f"Worksheet written. Tell the researcher: 'Please follow the steps in "
                f"`{worksheet.relative_to(root)}` and reply when done.'"
            ),
        }
    except Exception as e:
        logger.exception("external_tool_instructions failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Plan a complex step (force breakdown)
# ---------------------------------------------------------------------------


def plan_step(goal: str, root: Path, max_substeps: int = 6) -> dict[str, Any]:
    """Force the AI to break a complex step into atomic sub-tasks before coding.

    Writes a plan markdown into the current step's outputs/reports/ and
    returns it. The AI is then expected to execute the sub-tasks one at a
    time, with version-numbered scripts.
    """
    try:
        from research_os.project_ops import load_state
        from research_os.tools.actions.audit.audit import get_current_path

        state = load_state(root)
        profile = state.get("model_profile") or "medium"
        runtime = (
            (state.get("runtime") if isinstance(state.get("runtime"), dict) else None)
            or {}
        )

        suggested_batches = {"small": 1, "medium": 2, "large": 3}.get(profile, 2)

        body = (
            f"# Plan — {goal}\n"
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*\n\n"
            f"Model profile: `{profile}` · Suggested sub-tasks per turn: `{suggested_batches}`\n\n"
            "## Sub-tasks (atomic)\n"
            "Fill each as a single concrete script with one purpose. Number them.\n"
            "Use version suffixes (_v1, _v2) when iterating on the same sub-task.\n\n"
            "1. [ ] *(sub-task 1: e.g. load data, validate schema → outputs/reports/data_validation.md)*\n"
            "2. [ ] *(sub-task 2: e.g. exploratory plots → outputs/figures/eda_distributions.png)*\n"
            "3. [ ] *(sub-task 3: e.g. fit baseline model)*\n"
            "...\n\n"
            f"Up to {max_substeps} sub-tasks. If you need more, that's a sign the\n"
            "step itself should be split into multiple experiments (`sys_path(operation='create')`).\n\n"
            "## Dependencies\n*(any sub-task that requires an earlier output — list them)*\n\n"
            "## Decisions still pending\n*(things to confirm with the researcher before coding)*\n\n"
            "## Long-running sub-tasks\n"
            f"Anything > {runtime.get('long_running_threshold_seconds', 60)}s should run via\n"
            "`tool_task_run` (background subprocess). Poll with `tool_task_status`.\n"
        )

        current = get_current_path(root)
        out_dir = (
            root / "workspace" / current / "outputs" / "reports"
            if current
            else root / "workspace" / "logs"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"plan_{_slug(goal)}.md"
        out.write_text(body)

        return {
            "status": "success",
            "plan_path": str(out.relative_to(root)),
            "model_profile": profile,
            "suggested_substeps_per_turn": suggested_batches,
            "next_action": (
                "Fill the plan, then execute sub-task 1 (versioned script). "
                "Stop and report after each batch of sub-tasks."
            ),
        }
    except Exception as e:
        logger.exception("plan_step failed")
        return {"status": "error", "message": str(e)}


def plan_step_grounded(
    goal: str,
    root: Path,
    *,
    inputs_to_consult: list[str] | None = None,
    context_to_consult: list[str] | None = None,
    literature_queries: list[str] | None = None,
    max_substeps: int = 6,
) -> dict[str, Any]:
    """Plan a step where every sub-task carries a Thought / Required-Grounding
    / Action / Verification structure (ReAct + CoVe schema).

    Unlike ``plan_step`` (which writes a free-form checklist), this writer
    surfaces the inputs / context / literature the AI is supposed to consult
    and gives each sub-task a slot for the grounding source + the
    verification question. The output is the canonical pre-coding artefact
    for hardcore research: every action is preceded by stated evidence and
    followed by a check.

    Lists the project's available context up front (intake.md,
    inputs/context/*, prior step conclusions) so the AI cannot claim
    "nothing to consult".

    Use this for substantive analyses; ``plan_step`` is fine for routine
    sub-task chunking.
    """
    try:
        from research_os.project_ops import load_state
        from research_os.tools.actions.audit.audit import get_current_path

        state = load_state(root)
        profile = state.get("model_profile") or "medium"

        # Auto-inventory potential evidence the AI should consult.
        inputs_dir = root / "inputs"
        ctx_dir = inputs_dir / "context"
        lit_dir = inputs_dir / "literature"
        intake = inputs_dir / "intake.md"
        rq = root / "docs" / "research_overview.md"

        available_inputs: list[str] = []
        if intake.exists():
            available_inputs.append("inputs/intake.md (research question + input inventory)")
        if rq.exists():
            available_inputs.append("docs/research_overview.md")
        for sub in (inputs_dir / "raw_data",):
            if sub.exists() and any(p for p in sub.iterdir() if p.name != ".gitkeep"):
                available_inputs.append(f"{sub.relative_to(root)}/ (raw data)")
        available_context: list[str] = []
        if ctx_dir.exists():
            for p in sorted(ctx_dir.iterdir()):
                if p.is_file() and p.name not in {"README.md", ".gitkeep"}:
                    available_context.append(str(p.relative_to(root)))
        available_literature: list[str] = []
        if lit_dir.exists():
            for p in sorted(lit_dir.iterdir()):
                if p.suffix.lower() == ".pdf":
                    available_literature.append(str(p.relative_to(root)))
        # Also surface the most recent active step's conclusions for chain.
        prior_conclusions: list[str] = []
        ws = root / "workspace"
        if ws.exists():
            import re as _re

            for d in sorted(ws.iterdir()):
                if d.is_dir() and _re.match(r"^\d{2,3}_", d.name) \
                        and not d.name.endswith("__DEAD_END"):
                    c = d / "conclusions.md"
                    if c.exists() and c.stat().st_size > 200:
                        prior_conclusions.append(str(c.relative_to(root)))
        prior_conclusions = prior_conclusions[-3:]  # last 3

        # Build the plan body.
        def _fmt_list(items: list[str], default: str = "(none)") -> str:
            return "\n".join(f"  - `{x}`" for x in items) if items else f"  - {default}"

        body_parts: list[str] = []
        body_parts.append(f"# Grounded plan — {goal}")
        body_parts.append(f"*Generated: {datetime.now(timezone.utc).isoformat()}*  "
                          f"·  Model profile: `{profile}`")
        body_parts.append("")
        body_parts.append("## Available evidence (consult BEFORE acting)")
        body_parts.append("")
        body_parts.append("### Project inputs")
        body_parts.append(_fmt_list(available_inputs))
        body_parts.append("")
        body_parts.append("### Researcher context (prose notes)")
        body_parts.append(_fmt_list(available_context, "(none — researcher provided no narrative context)"))
        body_parts.append("")
        body_parts.append("### Literature on hand")
        body_parts.append(_fmt_list(available_literature, "(none — call tool_literature_search_and_save to add)"))
        body_parts.append("")
        body_parts.append("### Prior step conclusions")
        body_parts.append(_fmt_list(prior_conclusions, "(this is the first step)"))
        body_parts.append("")
        if inputs_to_consult or context_to_consult or literature_queries:
            body_parts.append("### Explicitly required for this step")
            if inputs_to_consult:
                body_parts.append("Inputs:")
                body_parts.append(_fmt_list(inputs_to_consult))
            if context_to_consult:
                body_parts.append("Context files:")
                body_parts.append(_fmt_list(context_to_consult))
            if literature_queries:
                body_parts.append("Literature queries to run:")
                body_parts.append(
                    "\n".join(f"  - `tool_literature_search_and_save query=\"{q}\"`"
                               for q in literature_queries)
                )
            body_parts.append("")

        body_parts.append("## Sub-tasks (ReAct + CoVe schema)")
        body_parts.append("")
        body_parts.append(
            "Each sub-task carries the structure below. Fill every slot — "
            "an unfilled grounding or verification means the sub-task is "
            "**not** ready to execute."
        )
        body_parts.append("")
        for i in range(1, max_substeps + 1):
            body_parts.extend([
                f"### {i}. _(sub-task title)_",
                "",
                "- **Thought**: _why this sub-task; what hypothesis it tests._",
                "- **Required grounding**: _which inputs / context files / "
                "literature entries the action will consult._",
                "  - e.g. `inputs/context/protocol_v2.md` (researcher's spec)",
                "  - e.g. `literature/smith2023.pdf` (canonical reference for the method)",
                "- **Action**: _the tool call(s) — `tool_step_pipeline_run`, "
                "`tool_python_exec` / `tool_r_exec` for AI-authored scripts, "
                "`tool_search_*` for literature, etc._",
                "- **Expected outputs**: _files this sub-task should produce."
                " Provenance sidecars auto-emit._",
                "- **Verification** (CoVe): _the question that would falsify "
                "this sub-task's output; how it gets checked._",
                "- **Lessons consulted**: _from `tool_lessons(operation='consult', task=\"<goal>\")` — list lesson_ids referenced._",
                "",
            ])

        body_parts.extend([
            "## Pre-commit checklist (before running ANY sub-task)",
            "",
            "- [ ] Researcher context (inputs/intake.md + inputs/context/) read end-to-end.",
            "- [ ] Prior step conclusions skimmed.",
            "- [ ] `tool_lessons(operation='consult', task=\"" + goal[:80] + "\")` called — "
            "prior lessons noted.",
            "- [ ] Every sub-task above has filled grounding + verification slots.",
            "- [ ] `tool_thought(operation='log', kind='plan', content=<this plan summary>)` recorded.",
            "",
            "## After execution",
            "",
            "- For each completed sub-task: `tool_ground(mode='explicit', ...)` with the evidence consulted + `tool_verify(scope='claim', ...)` with the CoVe question.",
            "- `tool_lessons(operation='record', outcome=<...>, reflection=<one paragraph>)` for the step as a whole.",
            "- `tool_audit_quality_full` before synthesis.",
        ])

        current = get_current_path(root)
        out_dir = (
            root / "workspace" / current / "outputs" / "reports"
            if current
            else root / "workspace" / "logs"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"plan_grounded_{_slug(goal)}.md"
        out.write_text("\n".join(body_parts) + "\n")

        return {
            "status": "success",
            "plan_path": str(out.relative_to(root)),
            "available_inputs": available_inputs,
            "available_context": available_context,
            "available_literature": available_literature,
            "prior_conclusions": prior_conclusions,
            "advice": (
                "Grounded plan written. Every sub-task has explicit "
                "Thought / Required grounding / Action / Verification "
                "slots — fill them ALL before executing the first action. "
                "Call tool_lessons(operation='consult') and "
                "tool_thought(operation='log') first."
            ),
        }
    except Exception as e:
        logger.exception("plan_step_grounded failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Alternative-path proposal — surface a potentially-better methodology
# ---------------------------------------------------------------------------


def _next_branch_suffix(workspace: Path) -> int:
    """Compute the next `_path_<k>` suffix available across the workspace."""
    import re as _re

    pat = _re.compile(r"_path_(\d+)(?:__DEAD_END)?$")
    best = 0
    if not workspace.exists():
        return 1
    for p in workspace.iterdir():
        if not p.is_dir() or not _re.match(r"^\d{2,3}_", p.name):
            continue
        m = pat.search(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best + 1


def alternative_path_propose(
    task: str,
    user_method: str,
    root: Path,
    *,
    data_summary: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """Surface an alternative pipeline ONLY when literature evidence is strong.

    Behaviour
    ---------
    1. Pulls literature on both the user's method AND alternatives
       framed against the same task + data shape.
    2. Writes a structured ``alternative_path_<slug>.md`` report into the
       active step's ``outputs/reports/`` (or ``workspace/logs/``).
    3. Returns a structured proposal the AI surfaces to the researcher
       before committing — confidence-gated so quiet runs stay quiet.

    The tool DOES NOT create the branch. The AI surfaces the proposal,
    asks the researcher, and only on confirmation calls
    ``sys_path(operation='create', branch_of=<current_path>)`` with ``suggested_branch_name``.

    Confidence policy
    -----------------
    Only flag an alternative when the literature retrieval surfaces ≥3
    sources framing the alternative as a meaningful improvement for the
    SPECIFIC data shape described (paired samples, sparse counts,
    hierarchical structure, etc.). Otherwise return
    ``recommendation = "commit_user_method"`` — silent acceptance.
    """
    try:
        from research_os.project_ops import load_state
        from research_os.tools.actions.audit.audit import get_current_path
        from research_os.tools.actions.search.search import (
            search_semantic_scholar,
            search_web,
        )

        workspace = root / "workspace"
        current = get_current_path(root) or ""
        state = load_state(root)
        # The researcher's autonomy level shapes how loudly we surface the
        # alternative — autopilot still asks, but supervised invites the
        # researcher to weigh in directly.
        interaction = (
            (state.get("interaction") if isinstance(state.get("interaction"), dict) else None)
            or {}
        )
        autonomy = interaction.get("autonomy_level") or "supervised"

        primary_q = f"{task} {user_method}"
        alt_q = f"{task} alternative to {user_method}"
        data_q = (
            f"{task} {user_method} {data_summary}"
            if data_summary else
            f"{task} {user_method} method comparison"
        )

        academic: list[dict[str, Any]] = []
        for q in (primary_q, alt_q, data_q):
            try:
                for paper in search_semantic_scholar(q, limit=limit):
                    academic.append({**paper, "_query": q})
            except Exception as e:
                logger.warning(f"alt_path s2 lookup '{q}' failed: {e}")

        web: list[dict[str, Any]] = []
        for q in (f"{task} {user_method} vs", f"best practice {task}"):
            try:
                hits = search_web(q, limit=limit).get("results", []) or []
                for h in hits:
                    h["_query"] = q
                    web.append(h)
            except Exception as e:
                logger.warning(f"alt_path web lookup '{q}' failed: {e}")

        # Dedupe academic by title.
        seen_titles: set[str] = set()
        unique_academic: list[dict[str, Any]] = []
        for src in academic:
            key = (src.get("title") or "").strip().lower()
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            unique_academic.append(src)

        # Crude confidence signal: how many academic hits referenced
        # "alternative" / "compared with" / "better" / "outperforms" in
        # title or abstract. The AI does the final judging; this just
        # gates silent runs.
        signals = 0
        keywords = ("alternative", "outperform", "compared with", "better than",
                    "preferable", "robust to", "more accurate", "more powerful")
        for src in unique_academic:
            blob = ((src.get("title") or "") + " " + (src.get("abstract") or "")).lower()
            if any(k in blob for k in keywords):
                signals += 1

        recommendation = "commit_user_method"
        if signals >= 3:
            recommendation = "branch_to_alternative"

        suggested_branch_name = ""
        if current:
            # Strip lineage tag from the parent slug — the new branch
            # gets its own lineage from sys_path(operation='create').
            import re as _re

            slug = _re.sub(r"^\d{2,3}_", "", current)
            slug = _re.sub(r"_path_\d+(?:__DEAD_END)?$", "", slug)
            slug = _re.sub(r"__DEAD_END$", "", slug)
            suggested_branch_name = f"{slug}_alt"

        # Build the report.
        lines = [
            f"# Alternative-path scan — {task}",
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
            "",
            f"## User's proposed method\n`{user_method}`",
            "",
        ]
        if data_summary:
            lines.extend([f"## Data context\n{data_summary}", ""])
        lines.extend([
            "## Literature signals",
            f"- Academic sources surfaced: **{len(unique_academic)}**",
            f"- Web/best-practice sources: **{len(web)}**",
            f"- Comparative-evidence signals (titles/abstracts hinting at "
            f"alternative-being-better): **{signals}**",
            "",
            f"## Recommendation: `{recommendation}`",
            "",
        ])
        if recommendation == "commit_user_method":
            lines.append(
                "The literature scan did not surface strong evidence that an "
                "alternative pipeline would meaningfully outperform the user's "
                "method on this data shape. Proceed with the user's choice.\n"
            )
        else:
            lines.append(
                "Literature surfaces ≥3 comparative signals. The AI should "
                "synthesise the evidence below into ONE candidate alternative "
                "and surface it to the researcher BEFORE branching — phrased "
                "as 'I noticed the literature on X often prefers Y for data "
                "like ours because Z. Would you like to run that as "
                f"`{suggested_branch_name or '<slug>_alt'}` alongside the "
                "primary?'.\n"
            )
        lines.extend(["", "## Top academic sources", ""])
        for src in unique_academic[:8]:
            title = (src.get("title") or "")[:160]
            year = src.get("year") or ""
            authors = ", ".join((src.get("authors") or [])[:3])
            url = src.get("url") or src.get("doi") or ""
            lines.append(f"- **{title}** · {authors} ({year})")
            if url:
                lines.append(f"  {url}")
            abstract = (src.get("abstract") or "").strip()
            if abstract:
                lines.append(f"  > {abstract[:280]}{'…' if len(abstract) > 280 else ''}")

        lines.extend(["", "## Best-practice / web", ""])
        for r in web[:6]:
            t = (r.get("title") or "")[:160]
            u = r.get("url") or ""
            d = (r.get("description") or "")[:240]
            lines.append(f"- **{t}** {u}\n  > {d}")

        lines.extend([
            "",
            "## How to act on this",
            "1. The AI reads the evidence above and decides which ONE alternative is best supported.",
            "2. If `commit_user_method`: tell the researcher you considered alternatives and stuck with their choice (one-line note in analysis.md is enough).",
            (
                "3. If `branch_to_alternative`: phrase the proposal to the researcher exactly once. "
                "On confirmation, call "
                f"`sys_path(operation='create', name=\"<slug>_alt\", branch_of=\"{current or '<current>'}\")` "
                "— that produces an `NN_<slug>_alt_path_<k>` folder that runs alongside the primary without disturbing it."
            ),
            "4. Log the decision with `mem_log(kind='decision', ...)`.",
        ])

        out_dir = (
            workspace / current / "outputs" / "reports"
            if current and (workspace / current).is_dir()
            else workspace / "logs"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"alternative_path_{_slug(task)}.md"
        report_path.write_text("\n".join(lines) + "\n")

        return {
            "status": "success",
            "task": task,
            "user_method": user_method,
            "current_path": current,
            "academic_count": len(unique_academic),
            "web_count": len(web),
            "comparative_signals": signals,
            "recommendation": recommendation,
            "suggested_branch_name": suggested_branch_name,
            "suggested_branch_suffix_hint": _next_branch_suffix(workspace),
            "autonomy_level": autonomy,
            "report_path": str(report_path.relative_to(root)),
            "academic": unique_academic[:8],
            "web": web[:6],
            "advice": (
                "Surface the proposal to the researcher ONCE if recommendation "
                "= 'branch_to_alternative'. Stay silent (just commit) "
                "otherwise — proposing weak alternatives erodes the "
                "researcher's trust."
            ),
        }
    except Exception as e:
        logger.exception("alternative_path_propose failed")
        return {"status": "error", "message": str(e)}
