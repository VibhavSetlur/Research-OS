"""Research / reasoning tools — help the AI ground its choices in sources.

These tools collect evidence from the web + literature for a specific decision,
then return a structured report the AI uses to commit a decision (and log it).
They do NOT make the decision for the AI — they ensure the AI never picks a
method or library from training memory alone.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.research")


def _write_report(root: Path, kind: str, slug: str, body: str) -> str:
    """Write a research report into the current step (or workspace/logs)."""
    from research_os.tools.actions.audit import get_current_path

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
        from research_os.tools.actions.literature_retrieval import (
            search_crossref,
            search_pubmed,
            search_semantic_scholar,
        )
        from research_os.tools.actions.web_search import search_web

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
                "Then call `mem_methods_append` to commit the chosen method and",
                "`mem_decision_log` with context / selected / rationale.",
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
                "Synthesise the evidence into mem_methods_append + mem_decision_log "
                "before writing any analysis script."
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
        from research_os.tools.actions.web_search import search_web

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
                "   star count via `tool_search_web` follow-ups.",
                "5. Commit the decision with `mem_decision_log`.",
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
        from research_os.tools.actions.audit import get_current_path

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
            "- AI logs the run via `mem_methods_append` (method = the external tool name).\n"
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
        from research_os.tools.actions.audit import get_current_path

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
            "step itself should be split into multiple experiments (`sys_path_create`).\n\n"
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
