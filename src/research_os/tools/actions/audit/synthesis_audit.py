""":class:`AuditBase` wrapper around :func:`audit_synthesis`.

Calls the procedural auditor (so its existing markdown report at
``<step>/outputs/reports/synthesis_audit.md`` continues to be written
byte-identically) and then translates its result dict into a list of
:class:`AuditFinding` objects:

* one ``severity="block"`` finding per ``gate_blockers`` entry — these
  halt the synthesis gate (quality bars, recurring step warnings,
  zero-PDF default-deny, unverified citations);
* one ``severity="warn"`` finding per causal-language hit + per missing
  IMRAD section + per missing figure file + bibliography absence;
* one ``severity="info"`` heartbeat summary finding per run, recording
  citation density + figure coverage even when the gate passes cleanly.
  This gives the append-only ``.audit_findings.jsonl`` ledger a record
  the audit actually executed.

Each finding's UUID is derived deterministically with ``uuid5`` over
``(audit_name, dimension, severity, sorted evidence_paths,
suggested_fix)`` so that re-running the audit against the same workspace
+ paper does NOT churn finding IDs — important for downstream diffing
of the jsonl ledger across runs.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding
from research_os.tools.actions.audit._paper import resolve_paper_path


_AUDIT_NAME = "synthesis"


class SynthesisAudit(AuditBase):
    """AuditBase wrapper around :func:`audit_synthesis`.

    After :meth:`run` returns, the underlying legacy result dict is
    accessible on ``self.last_result`` so handlers that need to return
    the full procedural report (existing API shape) don't have to
    re-invoke the auditor.
    """

    name = _AUDIT_NAME

    def __init__(self) -> None:
        self.last_result: dict[str, Any] | None = None

    def run(  # type: ignore[override]
        self,
        root: Path,
        paper_path: str | None = None,
        *,
        override_no_pdfs: bool = False,
        override_rationale: str = "",
        **_: Any,
    ) -> list[AuditFinding]:
        """Run the legacy audit and translate its dict into findings.

        Always returns a ``list[AuditFinding]`` — never raises for a
        missing paper or workspace; emits a ``warn`` finding instead so
        the gate ledger sees the no-op. ``paper_path`` defaults to the
        resolved synthesis paper (``synthesis/paper.typ`` if present,
        else the Markdown forms).
        """
        if paper_path is None:
            paper_path = resolve_paper_path(root)
        # Local import so audit/__init__.py's import of audit_synthesis
        # (legacy) + SynthesisAudit (this module) doesn't create an
        # import cycle when the legacy module pulls
        # `_findings_from_synthesis_result` from here.
        from research_os.tools.actions.audit.audit import audit_synthesis

        result = audit_synthesis(
            paper_path,
            root,
            override_no_pdfs=override_no_pdfs,
            override_rationale=override_rationale,
        )
        self.last_result = result
        return findings_from_synthesis_result(result, paper_path)


def findings_from_synthesis_result(
    result: dict[str, Any], paper_path: str
) -> list[AuditFinding]:
    """Translate the ``audit_synthesis`` result dict into findings.

    Pure function over the dict so callers can derive findings without
    re-running the audit. Used by both :class:`SynthesisAudit` and the
    procedural function itself (after it has computed the result) to
    write the companion .json + .jsonl artefacts via
    :func:`write_audit_outputs`.
    """
    findings: list[AuditFinding] = []

    # Hard error path (paper missing, etc.): emit a single warn
    # finding so the run is recorded.
    if result.get("status") == "error" and not result.get("report"):
        findings.append(
            _make_finding(
                severity="warn",
                dimension="synthesis",
                evidence_paths=[paper_path],
                suggested_fix=(
                    result.get("message")
                    or "tool_audit_synthesis could not run — see workspace state."
                ),
            )
        )
        return findings

    report = result.get("report") or {}
    report_path = result.get("report_path") or (
        "workspace/logs/synthesis_audit.md"
    )

    # 1. Gate blockers: each entry maps to a block-severity finding.
    for blocker in result.get("blockers") or []:
        is_default_deny = "DEFAULT-DENY" in blocker
        findings.append(
            _make_finding(
                severity="block",
                dimension="synthesis_quality_gate",
                evidence_paths=[paper_path, report_path],
                suggested_fix=blocker,
                override_kwarg="override_no_pdfs" if is_default_deny else None,
                override_log_format=(
                    "OVERRIDE audit_synthesis_no_pdfs — rationale: {rationale}"
                    if is_default_deny
                    else None
                ),
            )
        )

    # 2. Missing IMRAD sections: one warn each.
    for sec in report.get("missing_sections") or []:
        findings.append(
            _make_finding(
                severity="warn",
                dimension="structure",
                evidence_paths=[paper_path],
                suggested_fix=(
                    f"Paper is missing the `## {sec.title()}` IMRAD "
                    f"section. Add a top-level `## {sec.title()}` "
                    "header and fill it from the per-step "
                    "`conclusions.md` / `step_summary.yaml` material."
                ),
            )
        )

    # 3. Causal-language hits: one warn each.
    for hit in report.get("causal_language_hits") or []:
        term = hit.get("term") or "causal-language"
        ctx = (hit.get("context") or "").strip()
        findings.append(
            _make_finding(
                severity="warn",
                dimension="prose",
                evidence_paths=[paper_path],
                suggested_fix=(
                    f"Causal-language term `{term}` appears in observational "
                    "context. Replace with associative phrasing "
                    "(\"is associated with\", \"shows\", \"is consistent "
                    "with\") unless a causal-identification strategy is "
                    "actually invoked."
                    + (f' Context: "...{ctx}..."' if ctx else "")
                ),
            )
        )

    # 4. Missing figure files referenced by the paper: one warn each.
    for fig in report.get("figures_missing") or []:
        ref = fig.get("ref") if isinstance(fig, dict) else str(fig)
        findings.append(
            _make_finding(
                severity="warn",
                dimension="figures",
                evidence_paths=[paper_path, ref or ""],
                suggested_fix=(
                    f"Figure `{ref}` is referenced in {paper_path} but the "
                    "file is missing on disk. Either rebuild the figure or "
                    "fix the relative path."
                ),
            )
        )

    # 5. Bibliography missing: one warn.
    if not report.get("has_bibliography"):
        findings.append(
            _make_finding(
                severity="warn",
                dimension="structure",
                evidence_paths=[paper_path],
                suggested_fix=(
                    "No `## References` section or `\\bibliography` "
                    "directive found. Add one (workspace/citations.md "
                    "aggregates per-step references)."
                ),
            )
        )

    # 6. Heartbeat info: always emit a single summary so the
    # jsonl ledger records the run even on a clean pass.
    qg = report.get("quality_gates") or {}
    findings.append(
        _make_finding(
            severity="info",
            dimension="synthesis",
            evidence_paths=[paper_path, report_path],
            suggested_fix=(
                f"{report.get('citation_count', 0)} citation(s) "
                f"({report.get('citation_density_per_1000_words', 0)}/1000w); "
                f"{report.get('figures_referenced', 0)} figure(s) referenced; "
                f"figure_coverage_ratio="
                f"{qg.get('figure_coverage_ratio', 1.0)} "
                f"(target {qg.get('figure_coverage_target', 0.8)}); "
                f"total_words={qg.get('total_words', 0)}."
            ),
        )
    )

    return findings


def _make_finding(
    *,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    suggested_fix: str,
    override_kwarg: str | None = None,
    override_log_format: str | None = None,
) -> AuditFinding:
    """Build an :class:`AuditFinding` with a deterministic ``uuid5`` id.

    Keying off ``(audit_name, dimension, severity, sorted
    evidence_paths, suggested_fix)`` keeps the id stable across reruns
    where the audit finds the same problem in the same place, so the
    append-only ``.audit_findings.jsonl`` ledger can be diffed cleanly
    across runs.
    """
    key = "|".join([
        _AUDIT_NAME,
        dimension,
        severity,
        ",".join(sorted(evidence_paths)),
        suggested_fix,
    ])
    stable_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
    return AuditFinding(
        audit_name=_AUDIT_NAME,
        severity=severity,
        dimension=dimension,
        id=stable_id,
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
        override_kwarg=override_kwarg,
        override_log_format=override_log_format,
    )


__all__ = ["SynthesisAudit", "findings_from_synthesis_result"]
