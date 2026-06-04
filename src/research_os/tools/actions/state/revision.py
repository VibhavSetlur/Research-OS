"""Step-level pause-and-revise heuristics.

v1.3.3 — surfaces after a step finalize: should the researcher revise
this step before proceeding? Branch into an alternative? Hand off to a
fresh chat? The AI presents these options verbatim; only the
researcher commits.

The anti-one-shot doctrine: AI agents tend to "complete" long plans as
fast as possible, which hurts quality because context fills, the AI
stops introspecting, and the researcher loses oversight. Forcing a
mandatory pause at well-defined checkpoints — with concrete revision
options — gives the researcher a moment to redirect.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.revision")


def step_revision_options(
    step_id: str, root: Path,
) -> dict[str, Any]:
    """Return revision + handoff options for a finalized step.

    Heuristics:
      - placeholder text still in conclusions → revise
      - no figures, or focal figure missing → revise
      - audit warnings logged for this step → revise
      - short conclusions (< 300 chars in Findings) → revise
      - zero tool_search_* calls logged → revise (grounding gap)
      - per-step env folder empty + step ran code → revise
      - conversation has spanned >5 finalized steps → handoff_recommended
    """
    workspace = root / "workspace"
    step_dir = workspace / step_id
    if not step_dir.is_dir():
        return {
            "status": "error",
            "message": f"Step `{step_id}` not found under workspace/",
        }

    conc = step_dir / "conclusions.md"
    suggested_revisions: list[str] = []
    risk_signals: list[str] = []

    conc_text = conc.read_text() if conc.exists() else ""

    # Placeholder still present?
    placeholders = [
        "*(2-3 sentences",
        "*(method name",
        "*(the single most important",
        "*(proceed | branch | dead-end)*",
        "*(list inputs used)*",
    ]
    found_placeholders = sum(1 for m in placeholders if m in conc_text)
    if found_placeholders:
        suggested_revisions.append(
            f"conclusions.md still has {found_placeholders} placeholder "
            "marker(s) — fill in Findings + Methods + Decision before "
            "moving on."
        )

    # Short Findings section?
    import re as _re
    findings_m = _re.search(
        r"##\s*Findings\s*\n(.+?)(?=^##|\Z)",
        conc_text, _re.MULTILINE | _re.DOTALL,
    )
    findings_body = findings_m.group(1).strip() if findings_m else ""
    if len(findings_body) < 200:
        suggested_revisions.append(
            f"Findings section is only {len(findings_body)} chars — a "
            "reviewer-readable Findings section should be ≥300 chars with "
            "specific numbers + references to the figures + tables produced."
        )

    # Figure presence?
    fig_dir = step_dir / "outputs" / "figures"
    if fig_dir.is_dir():
        n_fig = sum(
            1 for p in fig_dir.iterdir()
            if p.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
        )
        if n_fig == 0:
            suggested_revisions.append(
                "No figures in outputs/figures/. Every step should produce at "
                "least one focal figure named "
                f"`{step_id.split('_', 1)[0]}_<descriptor>.png` per "
                "visualization/figure_guidelines."
            )
    else:
        suggested_revisions.append("No outputs/figures/ folder — was the step run?")

    # Tables?
    tab_dir = step_dir / "outputs" / "tables"
    if tab_dir.is_dir() and not list(tab_dir.iterdir()):
        suggested_revisions.append(
            "outputs/tables/ is empty. Numerical findings should be "
            "reproducible from a CSV — even a one-row summary table."
        )

    # Search/grounding signals
    searches_log = root / "workspace" / "logs" / "searches.log"
    n_searches = 0
    if searches_log.exists():
        n_searches = sum(1 for ln in searches_log.read_text().splitlines() if ln.strip())
    references_block = _re.search(
        r"##\s*References?\s+to\s+ground\s*\n(.+?)(?=^##|\Z)",
        conc_text, _re.MULTILINE | _re.DOTALL,
    )
    refs_count = 0
    if references_block:
        refs_count = sum(
            1 for ln in references_block.group(1).splitlines()
            if ln.strip().startswith(("-", "*", "+"))
        )
    if refs_count > 0 and n_searches == 0:
        risk_signals.append(
            "conclusions.md cites references but zero `tool_search_*` "
            "calls have been logged. The citations may be coming from "
            "training memory rather than verifiable lookups."
        )
        suggested_revisions.append(
            "Ground each cited reference by running "
            "`tool_literature_search_and_save query=\"<canonical paper>\" "
            f"step_id=\"{step_id}\"` BEFORE moving on."
        )

    # Per-step env empty?
    env_dir = step_dir / "environment"
    env_files = [
        p for p in env_dir.iterdir()
        if env_dir.exists() and p.name != "README.md"
    ] if env_dir.exists() else []
    scripts_dir = step_dir / "scripts"
    has_scripts = scripts_dir.is_dir() and any(
        p.suffix.lower() in {".py", ".r", ".jl"} for p in scripts_dir.iterdir()
    )
    if has_scripts and not env_files:
        suggested_revisions.append(
            f"Step has scripts but per-step env is empty. If the step "
            f"uses different packages than the project default, call "
            f"`sys_env_snapshot step_id='{step_id}'` for a per-step capture."
        )

    # Audit warnings for THIS step in workspace/logs/audit_report.md?
    audit_log = root / "workspace" / "logs" / "audit_report.md"
    has_step_audit_warnings = False
    if audit_log.exists():
        if step_id in audit_log.read_text():
            has_step_audit_warnings = True
            risk_signals.append(
                f"`workspace/logs/audit_report.md` mentions {step_id} — "
                "check whether audit warnings remain unresolved."
            )

    # Alternative paths the researcher could consider.
    alternative_paths: list[str] = []
    # Stratified analysis suggestion if the step's findings mention groups.
    if any(g in conc_text.lower() for g in (" by sex", " by age", " by cohort", " by site")):
        alternative_paths.append(
            "Stratified analysis: re-run within each subgroup separately to "
            "check whether the headline holds, then branch via "
            f"`sys_path_create name='{step_id.split('_', 1)[1]}_stratified' "
            f"branch_of='{step_id}'`."
        )
    # Sensitivity analysis if any cutoff was named.
    if any(c in conc_text.lower() for c in ("fdr", "p < ", "p<0.", "log2fc")):
        alternative_paths.append(
            f"Sensitivity to cutoff: branch via `branch_of='{step_id}'` and "
            "re-run with a stricter/looser threshold to confirm robustness."
        )
    # Method-comparison if a single method dominates.
    if "we use" in conc_text.lower() or "we chose" in conc_text.lower():
        alternative_paths.append(
            "Alternative method: re-fit with a competing method "
            "(e.g. limma-voom vs DESeq2, Bayesian vs frequentist) to "
            "report concordance + divergence."
        )

    # Handoff hint: count finalized steps + total per-step finalize log
    # entries. If we're past 5 substantive steps, a fresh chat is the
    # right move before going further.
    n_finalized = 0
    if workspace.is_dir():
        for p in workspace.iterdir():
            if p.is_dir() and p.name[:2].isdigit() and (p / "conclusions.md").exists():
                txt = (p / "conclusions.md").read_text(errors="ignore")
                if "*(2-3 sentences" not in txt:
                    n_finalized += 1
    handoff_recommended = n_finalized >= 5

    would_benefit = bool(suggested_revisions or risk_signals or has_step_audit_warnings)

    return {
        "status": "success",
        "step_id": step_id,
        "would_benefit_from_revision": would_benefit,
        "risk_signals": risk_signals,
        "suggested_revisions": suggested_revisions,
        "alternative_paths": alternative_paths,
        "handoff_recommended": handoff_recommended,
        "n_finalized_steps_this_project": n_finalized,
        "message": (
            "Present these options VERBATIM to the researcher and WAIT for "
            "their choice (proceed | revise | branch | handoff). Do NOT "
            "auto-scaffold the next step unless researcher_config."
            "interaction.autonomy_level == 'autopilot' AND "
            "would_benefit_from_revision is False."
        ),
    }
