"""Handlers — audit_core sub-domain.

Carved out of handlers/audit.py to stay under the 600-line ceiling.
"""
from __future__ import annotations

from .._handlers_runtime import *  # noqa: F401,F403

__all__ = [
    "_handle_tool_audit",
    "_handle_tool_audit_findings",
    "_handle_tool_audit_synthesis",
    "_handle_tool_audit_power",
    "_handle_tool_audit_assumptions",
    "_handle_tool_audit_figure",
    "_handle_tool_audit_citations",
    "_handle_tool_audit_reproducibility",
    "_handle_tool_audit_figure_interactivity",
    "_handle_tool_audit_dashboard_content",
    "_handle_tool_audit_cliches",
    "_handle_tool_audit_figure_coverage",
    "_handle_tool_audit_cross_deliverable_consistency",
    "_handle_tool_audit_reviewer_responses",
    "_handle_tool_audit_step_completeness",
    "_handle_tool_audit_step_literature",
    "_handle_tool_audit_findings_query",
    "_handle_tool_audit_findings_diff",
    "_handle_tool_audit_version_coherence",
    "_handle_tool_audit_figure_full",
    "_handle_tool_audit_code_quality",
    "_handle_tool_audit_prose",
    "_handle_tool_audit_claims",
    "_handle_tool_audit_evalue",
    "_handle_tool_audit_quality_full",
    "_handle_tool_audit_coherence",
]

def _handle_tool_audit(name, arguments, root):
    """Unified audit dispatcher.

    Routes (scope, dimension) → the matching per-dimension handler.
    Every legacy ``tool_audit_*`` name is aliased to this entry point and
    has its scope+dimension injected via ``_ALIAS_PARAM_INJECTION``, so
    callers (researchers, scripts, protocols) using the older per-
    dimension names keep working unchanged.
    """
    scope = arguments.get("scope")
    dimension = arguments.get("dimension")
    if not scope or not dimension:
        return _text(_error(
            "tool_audit requires scope= and dimension=. "
            "Valid scopes: step | project | synthesis. "
            "See docs/V2_MIGRATION_TABLE.md for the full dimension list."
        ))
    handler_name = _AUDIT_DISPATCH.get((scope, dimension))
    if not handler_name:
        return _text(_error(
            f"tool_audit: unknown (scope='{scope}', dimension='{dimension}'). "
            "See docs/V2_MIGRATION_TABLE.md for valid combinations."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_audit: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


def _handle_tool_audit_findings(name, arguments, root):
    """Unified findings-ledger dispatcher (query | diff).

    Replaces the two per-operation tools (tool_audit_findings_query +
    tool_audit_findings_diff). Operation defaults to 'query' when the
    diff-specific timestamps are absent and the caller did not specify
    operation explicitly.
    """
    op = arguments.get("operation")
    if not op:
        # Infer: diff if both timestamps are present, else query.
        if arguments.get("timestamp_a") and arguments.get("timestamp_b"):
            op = "diff"
        else:
            op = "query"
    if op == "query":
        return _handle_tool_audit_findings_query(name, arguments, root)
    if op == "diff":
        return _handle_tool_audit_findings_diff(name, arguments, root)
    return _text(_error(
        f"tool_audit_findings: unknown operation '{op}'. "
        "Use operation='query' or operation='diff'."
    ))


def _handle_tool_audit_synthesis(name, arguments, root):
    from research_os.tools.actions.audit import audit_synthesis
    from research_os.project_ops import log_override

    res = audit_synthesis(
        arguments.get("paper_path", "synthesis/paper.md"),
        root,
        override_no_pdfs=bool(arguments.get("override_no_pdfs", False)),
        override_rationale=str(arguments.get("override_rationale", "")),
    )
    # Mirror the other six override gates in this file: when the bypass
    # is actually honoured by audit_synthesis (reflected in the result
    # via report["override_no_pdfs"]=True), append it to override_log.md
    # so pre_submission_checklist can surface the bypass.
    if res.get("override_no_pdfs"):
        try:
            log_override(
                root,
                tool="tool_audit_synthesis",
                gate="audit_synthesis_no_pdfs",
                rationale=str(arguments.get("override_rationale", "")),
            )
        except Exception as exc:  # pragma: no cover - logging best effort
            logger.debug("log_override(audit_synthesis_no_pdfs) failed: %s", exc)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_power(name, arguments, root):
    from research_os.tools.actions.audit import audit_power

    res = audit_power(
        arguments["filepath"],
        arguments.get("effect_size", 0.5),
        arguments["alpha"],
        arguments["n"],
        root,
    )
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_assumptions(name, arguments, root):
    from research_os.tools.actions.audit import audit_assumptions

    res = audit_assumptions(arguments["filepath"], root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_figure(name, arguments, root):
    from research_os.tools.actions.audit import audit_figure

    res = audit_figure(arguments["filepath"], root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_citations(name, arguments, root):
    from research_os.tools.actions.audit import audit_citations

    res = audit_citations(root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_reproducibility(name, arguments, root):
    from research_os.tools.actions.audit import audit_reproducibility_full

    res = audit_reproducibility_full(root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_figure_interactivity(name, arguments, root):
    from research_os.tools.actions.audit.figure_interactivity import (
        audit_figure_interactivity,
    )

    res = audit_figure_interactivity(
        root,
        strictness=arguments.get("strictness"),
        autogen=arguments.get("autogen"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_figure_interactivity failed")))
    return _text(_success(res))


def _handle_tool_audit_dashboard_content(name, arguments, root):
    from research_os.tools.actions.audit.dashboard_content import audit_dashboard_content
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_dashboard_content_gate", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_dashboard_content_gate=true requires override_rationale."
        ))
    res = audit_dashboard_content(
        root,
        dashboard_path=arguments.get("dashboard_path", "synthesis/dashboard.html"),
    )
    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_audit_dashboard_content",
            gate="dashboard_content",
            rationale=rationale,
            extra={"blocker_count": len(res["blockers"])},
        )
        res["override_applied"] = True
        res["status"] = "success"
    return _text(_success(res))


def _handle_tool_audit_cliches(name, arguments, root):
    from research_os.tools.actions.audit.content_depth import audit_cliches

    return _text(_success(audit_cliches(
        arguments.get("paper_path", "synthesis/paper.md"),
        root,
    )))


def _handle_tool_audit_figure_coverage(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.synthesis.figure_auto_embed import (
        FigureCoverageAudit,
    )

    root_path = Path(root)
    audit = FigureCoverageAudit()
    # Run the audit to get structured findings, then fan them
    # out to workspace/figure_coverage_audit.{md,json} +
    # workspace/logs/.audit_findings.jsonl. Best-effort writes — if the
    # workspace dir is read-only we still want to return the audit verdict.
    findings: list = []
    try:
        findings = audit.run(root_path)
        write_audit_outputs(findings, "figure_coverage", root_path)
    except Exception:  # noqa: BLE001 — best-effort artefact write
        pass
    # Legacy dict surface preserved for back-compat callers (tests,
    # protocols that key on `status`/`blockers`/`checked`/`embedded`).
    res = audit.to_legacy_dict(root_path, findings)
    if res.get("status") == "error" and "blockers" in res:
        # Return as success-with-blockers so the audit aggregator can
        # surface them rather than treating the audit as a tool error.
        return _text(_success(res))
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_figure_coverage failed")))
    return _text(_success(res))


def _handle_tool_audit_cross_deliverable_consistency(name, arguments, root):
    """Cross-deliverable consistency audit: 5 dimensions, override-aware."""
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.cross_deliverable import (
        CrossDeliverableConsistencyAudit,
        audit_cross_deliverable_consistency,
    )
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_cross_deliverable", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (
        policy == "enforce"
        and override_requested
        and (not rationale or not str(rationale).strip())
    ):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_cross_deliverable=true requires override_rationale."
        ))

    res = audit_cross_deliverable_consistency(root)

    # AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = CrossDeliverableConsistencyAudit().run(Path(root))
        write_audit_outputs(
            findings, "cross_deliverable_consistency", Path(root)
        )
    except Exception:  # pragma: no cover - defensive guard
        pass

    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_audit_cross_deliverable_consistency",
            gate="cross_deliverable_consistency",
            rationale=rationale,
            extra={
                "blocker_count": len(res["blockers"]),
                "deliverables_found": res.get("deliverables_found", []),
            },
        )
        res["override_applied"] = True
        res["status"] = "success"

    return _text(_success(res))


def _handle_tool_audit_reviewer_responses(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import (
        audit_reviewer_responses,
    )
    res = audit_reviewer_responses(root)
    return _text(_success(res))


def _handle_tool_audit_step_completeness(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.audit import (
        StepCompletenessAudit,
        audit_step_completeness,
    )

    step_id = arguments.get("step_id")
    # Legacy procedural call produces workspace/logs/step_completeness.md
    # and is the source of truth for the response body that callers
    # (tool_synthesize, tool_path_finalize, tool_dashboard_create) consume.
    result = audit_step_completeness(root, step_id=step_id)

    # AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = StepCompletenessAudit().run(root, step_id=step_id)
        write_audit_outputs(findings, "step_completeness", root)
    except Exception:  # pragma: no cover - defensive guard
        pass

    return _text(_success(result))


def _handle_tool_audit_step_literature(name, arguments, root):
    from research_os.tools.actions.audit.step_literature import audit_step_literature

    return _text(_success(audit_step_literature(
        root, step_id=arguments.get("step_id"),
    )))


def _handle_tool_audit_findings_query(name, arguments, root):
    """Filter the cross-audit findings ledger.

    Reads ``workspace/logs/.audit_findings.jsonl`` (latest snapshot per
    stable finding id), then filters by severity / dimension / step /
    since. Returns the list — does NOT mutate the ledger.
    """
    from research_os.tools.actions.audit.findings_query import (
        audit_findings_query,
    )

    res = audit_findings_query(
        Path(root),
        severity=arguments.get("severity"),
        dimension=arguments.get("dimension"),
        step=arguments.get("step"),
        since=arguments.get("since"),
    )
    return _text(_success(res))


def _handle_tool_audit_findings_diff(name, arguments, root):
    """Diff two snapshots of the findings ledger by stable id.

    Snapshots the ledger as of ``timestamp_a`` and ``timestamp_b`` (both
    ISO-8601), then reports findings added / resolved / changed between
    them. The structural diff ignores re-emission churn (generated_at +
    ro_version) so a finding that simply reruns is NOT reported as
    changed.
    """
    from research_os.tools.actions.audit.findings_query import (
        audit_findings_diff,
    )

    ts_a = arguments.get("timestamp_a")
    ts_b = arguments.get("timestamp_b")
    if not ts_a or not ts_b:
        return _text(_error(
            "tool_audit_findings_diff requires both timestamp_a and "
            "timestamp_b (ISO-8601 strings, e.g. '2026-06-05T12:00:00Z')."
        ))
    res = audit_findings_diff(Path(root), timestamp_a=ts_a, timestamp_b=ts_b)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_findings_diff failed")))
    return _text(_success(res))


def _handle_tool_audit_version_coherence(name, arguments, root):
    from research_os.tools.actions.state.iteration import audit_version_coherence

    return _text(_success(audit_version_coherence(
        root, step_id=arguments.get("step_id"),
    )))


def _handle_tool_audit_figure_full(name, arguments, root):
    from research_os.tools.actions.viz import audit_figure_quality

    return _text(_success(audit_figure_quality(
        arguments["figure_path"], root,
    )))


def _handle_tool_audit_code_quality(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.code_quality import (
        CodeQualityAudit,
        audit_code_quality,
    )

    # Legacy report (preserves workspace/logs/code_quality.md byte-for-byte).
    legacy = audit_code_quality(
        root,
        step_id=arguments.get("step_id"),
        run_ruff=bool(arguments.get("run_ruff", True)),
        run_mypy=bool(arguments.get("run_mypy", False)),
    )

    # Structured artefacts (JSON + JSONL ledger) alongside the
    # legacy markdown. Re-running audit_code_quality is cheap and keeps
    # the two output paths trivially consistent; if that ever shows up
    # in a profile, lift the per_step walk out into a shared helper.
    findings = CodeQualityAudit().run(
        root,
        step_id=arguments.get("step_id"),
        run_ruff=bool(arguments.get("run_ruff", True)),
        run_mypy=bool(arguments.get("run_mypy", False)),
    )
    written = write_audit_outputs(findings, "code_quality", root)
    legacy["audit_findings"] = {
        "count": len(findings),
        "block": sum(1 for f in findings if f.severity == "block"),
        "warn": sum(1 for f in findings if f.severity == "warn"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "json_path": str(written["json"].relative_to(root)),
        "jsonl_path": str(written["jsonl"].relative_to(root)),
    }
    return _text(_success(legacy))


def _handle_tool_audit_prose(name, arguments, root):
    from research_os.tools.actions.audit.prose_quality import audit_prose

    return _text(_success(audit_prose(
        root,
        targets=arguments.get("targets"),
        is_observational=arguments.get("is_observational"),
    )))


def _handle_tool_audit_claims(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.claim_grounding import (
        ClaimGroundingAudit,
        audit_claims,
    )

    target_path = arguments.get("target_path")
    tolerance = float(arguments.get("tolerance", 0.01))

    # Legacy procedural call produces synthesis/claim_index.json and
    # workspace/logs/claim_grounding.md and is the source of truth for
    # the response body that callers consume.
    result = audit_claims(root, target_path=target_path, tolerance=tolerance)

    # AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = ClaimGroundingAudit().run(
            root, target_path=target_path, tolerance=tolerance
        )
        write_audit_outputs(findings, "claim_grounding", root)
    except Exception:  # pragma: no cover - defensive guard
        pass

    return _text(_success(result))


def _handle_tool_audit_evalue(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_evalue

    return _text(_success(audit_evalue(
        float(arguments["risk_ratio"]), root,
        ci_lower=arguments.get("ci_lower"),
        ci_upper=arguments.get("ci_upper"),
    )))


def _handle_tool_audit_quality_full(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.audit import (
        AuditMaster,
        audit_quality_full,
    )

    # 1) Legacy aggregator — writes workspace/logs/audit_master.md and
    # returns the dict shape MCP clients (and tool_synthesize) already
    # know how to read. The markdown format is pinned by snapshot test
    # and must stay byte-for-byte stable.
    legacy = audit_quality_full(
        root,
        target_path=arguments.get("target_path"),
        skip=arguments.get("skip"),
    )

    # 2) Structured findings — fan out to the writer so the
    # JSON companion + the cross-audit .audit_findings.jsonl ledger
    # pick up this run. Failures here must NEVER take the legacy
    # result down with them; the structured writer is best-effort and
    # supplementary.
    try:
        audit = AuditMaster()
        findings = audit.run(root, legacy_result=legacy)
        paths = write_audit_outputs(findings, audit.name, root)
        legacy["audit_master_v2"] = {
            "finding_count": len(findings),
            "json_path": str(paths["json"].relative_to(root)),
            "jsonl_path": str(paths["jsonl"].relative_to(root)),
            "md_path": str(paths["md"].relative_to(root)),
        }
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("audit_master v2 writer failed")
        legacy["audit_master_v2_error"] = str(exc)

    # 3) Phase 8 — attach a tier-based progress summary so the AI can
    # see where the project sits in the lifecycle without re-routing.
    try:
        legacy["tier_progress"] = _build_tier_progress(root)
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("tier_progress build failed: %s", exc)

    return _text(_success(legacy))


def _handle_tool_audit_coherence(name, arguments, root):
    from research_os.tools.actions.audit.coherence import audit_coherence
    return _text(audit_coherence(
        root,
        paper_path=str(arguments.get("paper_path") or "synthesis/paper.md"),
    ))


HANDLERS = {
    "tool_audit": _handle_tool_audit,
    "tool_audit_findings": _handle_tool_audit_findings,
    "tool_audit_quality_full": _handle_tool_audit_quality_full,
}
