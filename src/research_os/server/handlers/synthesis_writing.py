"""Handlers — synthesis_writing sub-domain.

Carved out of handlers/synthesis.py to stay under the 600-line ceiling.
"""
from __future__ import annotations

from .._handlers_runtime import *  # noqa: F401,F403

__all__ = [
    "_handle_tool_synthesize_plan",
    "_handle_tool_synthesize",
    "_handle_tool_latex_compile",
    "_handle_tool_paper_compile_typst",
    "_handle_tool_synthesis_preview",
    "_handle_tool_section_substantiveness",
    "_handle_tool_humanities_essay_scaffold",
    "_handle_tool_paper_figures_autoembed",
    "_handle_tool_writing_discussion_from_verdicts",
    "_handle_tool_discussion_coverage_audit",
]

def _handle_tool_synthesize_plan(name, arguments, root):
    from research_os.tools.actions.synthesis.synthesize import synthesize_plan

    return _text(_success(synthesize_plan(root)))


def _handle_tool_synthesize(name, arguments, root):
    from research_os.tools.actions.audit.audit import (
        audit_quality_full, audit_step_completeness,
    )
    from research_os.tools.actions.audit.findings_query import (
        unresolved_block_findings,
    )
    from research_os.tools.actions.synthesis.synthesize import synthesize_workspace
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    # Server-enforced quality gate. Single-section synthesis (e.g. just
    # the abstract) clears with a lightweight check; full-document
    # synthesis must pass the master quality auditor.
    #
    # We log override_completeness_gate=true to override_log.md ONLY
    # when the gate it would have run actually returned blockers — a
    # bypass that didn't bypass anything (gate would have passed, or
    # didn't apply to the section call) is a phantom entry that
    # confuses the pre-submission audit.
    override_requested = bool(arguments.get("override_completeness_gate", False))
    rationale = arguments.get("override_rationale")
    full_doc = not arguments.get("section")
    bypass_logged = False
    policy = get_interaction_policy(root)["quality_gate_policy"]

    # Phase-4c gate: if any unresolved BLOCK finding sits in the
    # cross-audit ledger (workspace/logs/.audit_findings.jsonl), refuse
    # to compile. The latest-snapshot semantics mean a BLOCK finding
    # emitted on an earlier audit run but absent from the most recent
    # rerun is treated as resolved — only currently-active BLOCKs
    # stop synthesis. Override path: pass
    # override_unresolved_blocks=true with a rationale; the override is
    # recorded to workspace/logs/override_log.md so the pre-submission
    # audit can flag it.
    override_unresolved_blocks = bool(
        arguments.get("override_unresolved_blocks", False)
    )
    try:
        active_blocks = unresolved_block_findings(Path(root))
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.debug("unresolved_block_findings scan failed: %s", exc)
        active_blocks = []
    if active_blocks and not override_unresolved_blocks and not (
        policy == "warn_only"
    ):
        if (
            policy == "enforce"
            and override_requested
            and (not rationale or not str(rationale).strip())
        ):
            # Fall through to the existing enforce check below — it
            # rejects with the same shape and we don't want two errors
            # racing for the response slot.
            pass
        else:
            top = active_blocks[:10]
            lines = [
                f"- [{b.get('dimension','?')}] "
                f"{b.get('audit_name','?')}: "
                f"{(b.get('suggested_fix') or '').strip()[:160]}"
                for b in top
            ]
            extra = (
                f"\n  … and {len(active_blocks) - 10} more"
                if len(active_blocks) > 10
                else ""
            )
            return _text(_error(
                "BLOCKED by unresolved audit findings ledger "
                f"({len(active_blocks)} BLOCK finding(s) in "
                "workspace/logs/.audit_findings.jsonl). Resolve them "
                "(re-run the originating audit so the latest snapshot "
                "no longer surfaces them) before tool_synthesize.\n\n"
                + "\n".join(lines)
                + extra
                + "\n\nTo bypass for a partial / WIP deliverable, call "
                "again with override_unresolved_blocks=true AND "
                "override_rationale='<one-line why>'."
            ))
    elif active_blocks and override_unresolved_blocks:
        # Record the bypass before we run anything else so the override
        # trail captures it even if synthesis fails later.
        log_override(
            Path(root),
            tool="tool_synthesize",
            gate="unresolved_block_findings",
            rationale=rationale,
            extra={
                "blocker_count": len(active_blocks),
                "blocker_ids": [b.get("id") for b in active_blocks[:20]],
                "output_type": arguments.get("output_type", "paper"),
                "section": arguments.get("section"),
            },
        )
    # warn_only ⇒ never block; the gate-blocker list is surfaced as
    # warnings on the response. Sandbox / exploratory use only.
    soft_gate = policy == "warn_only"
    # enforce ⇒ overrides demand an explicit researcher rationale; a
    # call asking for the bypass without supplying WHY is rejected.
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: override_completeness_gate=true "
            "requires a one-line override_rationale (recorded to "
            "workspace/logs/override_log.md). Pass override_rationale='…' or "
            "ask the researcher; or relax the policy to 'allow_override' in "
            "inputs/researcher_config.yaml."
        ))

    def _record_bypass(gate_name: str, blockers: list[str] | None) -> None:
        nonlocal bypass_logged
        if bypass_logged:
            return
        log_override(
            root,
            tool="tool_synthesize",
            gate=gate_name,
            rationale=rationale,
            extra={
                "output_type": arguments.get("output_type", "paper"),
                "section": arguments.get("section"),
                "blocker_count": len(blockers or []),
            },
        )
        bypass_logged = True

    if full_doc:
        gate = audit_quality_full(
            root,
            # Skip claims gate on the FIRST synthesis (paper.md doesn't
            # exist yet to extract claims from). Honour an explicit
            # empty list — researcher asked for ALL gates to run.
            skip=arguments["skip_gates"] if "skip_gates" in arguments else ["claims"],
        )
        if gate.get("status") == "error":
            if override_requested:
                _record_bypass("quality_full", gate.get("blockers"))
            elif soft_gate:
                # warn_only policy — record the override (researcher set
                # the policy that turns blockers into warnings) and let
                # synthesis proceed. Blockers attach as warnings below.
                _record_bypass("quality_full", gate.get("blockers"))
            else:
                return _text(_error(
                    "BLOCKED by master quality gate. "
                    + (gate.get("advice") or "")
                    + "\n\nBlockers:\n"
                    + "\n".join(f"- {b}" for b in (gate.get("blockers") or [])[:15])
                    + (f"\n  … and {len(gate.get('blockers') or []) - 15} more"
                       if len(gate.get("blockers") or []) > 15 else "")
                    + "\n\nReport: " + str(gate.get("report_path"))
                    + "\n\nTo bypass for a partial / WIP deliverable, call "
                    "again with override_completeness_gate=true."
                ))
    else:
        # Lightweight gate for single-section calls — still want focal
        # figure + caption coverage.
        sc = audit_step_completeness(root)
        if sc.get("status") == "error":
            if override_requested or soft_gate:
                _record_bypass("step_completeness", sc.get("blockers"))
            else:
                return _text(_error(
                    "BLOCKED by step-completeness gate (section-only synthesis). "
                    + sc.get("advice", "")
                ))

    res = synthesize_workspace(
        root,
        output_format=arguments.get("output_format", "markdown"),
        section=arguments.get("section"),
        output_type=arguments.get("output_type", "paper"),
        citation_style=arguments.get("citation_style", "vancouver"),
        auto_proceed=bool(arguments.get("auto_proceed", False)),
    )
    if "error" in res:
        return _text(_error(res["error"]))

    # After writing the full paper, run the claims audit as a second
    # pass so any AI hallucinations surface immediately. Skip when the
    # researcher already overrode the gate (the bypass log captures it).
    if full_doc and not override_requested and not soft_gate:
        try:
            from research_os.tools.actions.audit.claim_grounding import (
                audit_claims,
            )

            cl = audit_claims(root)
            res["claim_grounding"] = {
                "status": cl.get("status"),
                "ungrounded": cl.get("ungrounded"),
                "coverage_pct": cl.get("coverage_pct"),
                "report_path": cl.get("report_path"),
            }
            if cl.get("ungrounded"):
                res["advice"] = (
                    f"Paper written, but {cl['ungrounded']} numeric claim(s) "
                    "are NOT grounded in any workspace output. Review "
                    f"{cl.get('report_path')} before submitting."
                )
        except Exception as e:
            logger.debug("claims audit skipped: %s", e)

    return _text(_success(res))


def _handle_tool_latex_compile(name, arguments, root):
    from research_os.tools.actions.synthesis.latex import latex_compile

    return _text(_success(latex_compile(root)))


def _handle_tool_paper_compile_typst(name, arguments, root):
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.typst import paper_compile_typst
    from research_os.tools.actions.state.config import get_research_config

    paper_path = arguments.get("paper_path", "synthesis/paper.md")
    venue = arguments.get("venue")
    output = arguments.get("output", "synthesis/paper.pdf")

    # Phase-5 review-rewrite loop. Config knobs:
    #   synthesis.drafter_loop_enabled (bool, default True)
    #   synthesis.drafter_loop_max_iterations (int, default 3)
    #   synthesis.drafter_loop_quality_threshold (float, default 0.10)
    # Tier overrides:
    #   project_tier=throwaway → max_iter clamped to 1.
    #   interaction.autonomy_level=autopilot → respects config max_iter.
    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}
    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    max_iter = int(synth.get("drafter_loop_max_iterations", 3))
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    # Allow per-call disable for back-compat / debugging.
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    if not loop_enabled:
        return _text(_success(paper_compile_typst(
            root,
            paper_path=paper_path,
            venue=venue,
            output=output,
        )))

    def _drafter(prior_output=None, findings=None, root=root):
        return paper_compile_typst(
            root,
            paper_path=paper_path,
            venue=venue,
            output=output,
        )

    reviewer = persona_reviewer(
        ["presentation_critic", "scope_creep_critic", "methodology_skeptic"]
    )
    loop_res = draft_with_review_rewrite(
        _drafter,
        reviewer,
        drafter_name="paper",
        root=Path(root),
        max_iter=max_iter,
        improvement_threshold=threshold,
    )
    final = loop_res.get("final_output") or {}
    if isinstance(final, dict):
        final["drafter_loop"] = {
            "iterations": loop_res["iterations"],
            "converged": loop_res["converged"],
            "stop_reason": loop_res["stop_reason"],
            "quality_progression": loop_res["quality_progression"],
        }
    return _text(_success(final))


def _handle_tool_synthesis_preview(name, arguments, root):
    from research_os.tools.actions.synthesis.preview import synthesis_preview

    return _text(_success(synthesis_preview(
        root,
        target=arguments.get("target", "paper"),
        venue=arguments.get("venue"),
        mode=arguments.get("mode", "fresh"),
    )))


def _handle_tool_section_substantiveness(name, arguments, root):
    from research_os.tools.actions.audit.content_depth import section_substantiveness

    return _text(_success(section_substantiveness(
        root,
        paper_path=arguments.get("paper_path", "synthesis/paper.md"),
    )))


def _handle_tool_humanities_essay_scaffold(name, arguments, root):
    from research_os.tools.actions.synthesis.humanities_essay_scaffold import (
        scaffold_humanities_essay,
    )
    return _text(_success(scaffold_humanities_essay(root)))


def _handle_tool_paper_figures_autoembed(name, arguments, root):
    from research_os.tools.actions.synthesis.figure_auto_embed import (
        auto_embed_figures,
        rewrite_figure_xrefs,
    )
    from research_os.tools.actions.state.config import get_research_config

    root_path = Path(root)
    paper = root_path / "synthesis" / "paper.md"
    mode = arguments.get("mode", "append_to_section")
    section_map = arguments.get("section_map")

    embed_res = auto_embed_figures(
        paper, root_path, mode=mode, section_map=section_map,
    )
    if embed_res.get("status") == "error":
        return _text(_error(embed_res.get("message", "auto-embed failed")))

    # Honour config — researcher can disable rewrite.
    rewrite_res: dict = {"skipped": True}
    skip_xref_rewrite = bool(arguments.get("override_xref_rewrite", False))
    try:
        cfg = get_research_config(root_path) or {}
        rewrite_on = (
            (cfg.get("synthesis", {}) or {}).get("figure_xref_rewrite", True)
        )
    except Exception:
        rewrite_on = True
    if rewrite_on and not skip_xref_rewrite:
        rewrite_res = rewrite_figure_xrefs(paper)

    return _text(_success({
        "embed": embed_res,
        "xref_rewrite": rewrite_res,
        "paper_path": str(paper.relative_to(root_path)),
    }))


def _handle_tool_writing_discussion_from_verdicts(name, arguments, root):
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        emit_discussion_paragraphs,
    )
    return _text(emit_discussion_paragraphs(root))


def _handle_tool_discussion_coverage_audit(name, arguments, root):
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        discussion_coverage_audit,
    )
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_discussion_coverage", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_discussion_coverage=true requires override_rationale."
        ))
    res = discussion_coverage_audit(root)
    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_discussion_coverage_audit",
            gate="discussion_coverage",
            rationale=rationale or "",
            extra={"uncovered_count": res.get("uncovered_count", 0)},
        )
        res["override_applied"] = True
        res["status"] = "success"
    return _text(res)


# Adaptive-friction + quick-mode handlers.


HANDLERS = {
    "tool_synthesize_plan": _handle_tool_synthesize_plan,
    "tool_synthesize": _handle_tool_synthesize,
    "tool_latex_compile": _handle_tool_latex_compile,
    "tool_paper_compile_typst": _handle_tool_paper_compile_typst,
    "tool_synthesis_preview": _handle_tool_synthesis_preview,
    "tool_section_substantiveness": _handle_tool_section_substantiveness,
    "tool_humanities_essay_scaffold": _handle_tool_humanities_essay_scaffold,
    "tool_writing_discussion_from_verdicts": _handle_tool_writing_discussion_from_verdicts,
    "tool_discussion_coverage_audit": _handle_tool_discussion_coverage_audit,
}
