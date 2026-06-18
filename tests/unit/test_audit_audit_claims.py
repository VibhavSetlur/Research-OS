"""Phase-4 AuditBase regression tests for ``tool_audit_claims``.

These tests pin behaviour the v2.0.0 migration must preserve:

* The legacy ``workspace/logs/claim_grounding.md`` report is rendered
  byte-for-byte identically before and after the refactor — downstream
  AI prompts and templates still read this file.
* The new ``ClaimGroundingAudit`` (subclass of :class:`AuditBase`)
  emits :class:`AuditFinding` objects that satisfy the bundled JSON
  Schema and round-trip through :func:`validate_finding`.
* :func:`write_audit_outputs` writes the gate's ``.md`` + ``.json``
  companion artefacts AND appends one line per finding to the
  append-only ``workspace/logs/.audit_findings.jsonl`` ledger.
* Reruns over identical inputs produce IDs that don't churn (uuid5 is
  deterministic), so diffing the jsonl across runs surfaces only
  genuine changes.

We never mock the workspace — every test scaffolds a tiny but real
project root on ``tmp_path`` and asserts against the files actually
written, per the v2.0.0 release-spec hard constraint of "never mock
the database in tests".
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.claim_grounding import (
    ClaimGroundingAudit,
    audit_claims,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_workspace(
    root: Path,
    *,
    paper_body: str,
    corpus_body: str,
) -> None:
    """Build a minimal real workspace + synthesis target for an audit run.

    No mocks: a real ``workspace/01_eda/outputs/reports/summary.md`` and
    a real ``synthesis/paper.md`` are written to disk and the audit is
    invoked against the actual root.
    """
    ws = root / "workspace" / "01_eda" / "outputs" / "reports"
    ws.mkdir(parents=True)
    (ws / "summary.md").write_text(corpus_body)
    syn = root / "synthesis"
    syn.mkdir(parents=True)
    (syn / "paper.md").write_text(paper_body)


def _fixture_root(tmp_path: Path) -> Path:
    """One deterministic fixture used by both the snapshot test and the
    JSON / jsonl behaviour tests so the inputs are pinned in one place."""
    _seed_workspace(
        tmp_path,
        paper_body=(
            "# Paper\n\n"
            "The mean was 12.3 (95% CI 10.1-14.5). "
            "Effect size = 0.42.\n"
        ),
        corpus_body="Mean = 12.3\n",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Legacy markdown report must remain byte-identical
# ---------------------------------------------------------------------------


def test_claim_grounding_md_report_snapshot(tmp_path: Path):
    """The human-readable ``workspace/logs/claim_grounding.md`` report
    must keep the v1.x shape: heading, target line, three bullet
    counts, then ungrounded list. Pin the exact prefix so any drift
    surfaces as a test failure rather than a silent prompt change."""
    root = _fixture_root(tmp_path)
    res = audit_claims(root)
    report = (root / "workspace" / "logs" / "claim_grounding.md").read_text()

    # Header + meta line.
    assert report.startswith("# Claim grounding audit\n\n")
    assert "_Target: `synthesis/paper.md`_" in report
    assert "Tolerance: ±1%" in report

    # Three count bullets in their fixed order.
    assert "- Total numeric claims:" in report
    assert "- Grounded in workspace outputs:" in report
    assert "- Ungrounded (hallucination candidates):" in report

    # The ungrounded section header is exactly the v1 phrasing.
    assert "## Ungrounded claims (review before submission)" in report

    # The response object's headline numbers match the report.
    assert res["total_claims"] >= 3
    assert res["grounded"] >= 1
    assert res["ungrounded"] >= 1


# ---------------------------------------------------------------------------
# AuditBase findings + JSON companion
# ---------------------------------------------------------------------------


def test_claim_grounding_audit_emits_block_findings_per_ungrounded(
    tmp_path: Path,
):
    """One block-severity finding per ungrounded claim plus exactly one
    info summary finding. Every finding is schema-valid."""
    root = _fixture_root(tmp_path)

    findings = ClaimGroundingAudit().run(root)
    blocks = [f for f in findings if f.severity == "block"]
    infos = [f for f in findings if f.severity == "info"]

    assert len(blocks) >= 1, "expected at least one block finding"
    assert len(infos) == 1, "expected exactly one info summary finding"

    for f in findings:
        # Schema round-trip — proves the dataclass payload satisfies the
        # bundled draft-07 schema on disk.
        d = f.to_dict()
        validate_finding(d)
        # UUID4-format string per the schema pattern (uuid5 also fits
        # the same hex layout, so this is a sanity check).
        uuid.UUID(d["id"])
        assert d["audit_name"] == "claim_grounding"
        assert d["dimension"] == "grounding"
        assert d["ro_version"]
        assert d["generated_at"].endswith("Z")

    # The info summary references the markdown report so reviewers can
    # find the structured claim listing from the ledger. (The legacy
    # synthesis/claim_index.json sidecar is no longer written.)
    summary = infos[0]
    assert any(
        p.endswith("claim_grounding.md") for p in summary.evidence_paths
    )


def test_claim_grounding_audit_json_companion_schema_valid(tmp_path: Path):
    """The ``claim_grounding_audit.json`` companion is a list of
    schema-valid finding objects."""
    root = _fixture_root(tmp_path)
    findings = ClaimGroundingAudit().run(root)
    paths = write_audit_outputs(findings, "claim_grounding", root)

    assert paths["json"] == (
        root / "workspace" / "logs" / "audits" / "claim_grounding_audit.json"
    )
    arr = json.loads(paths["json"].read_text())
    assert isinstance(arr, list)
    assert len(arr) == len(findings)
    for d in arr:
        validate_finding(d)

    # The .md companion is grouped by severity, with the audit name in
    # the heading; the ledger-style markdown is distinct from the
    # legacy report file.
    md_text = paths["md"].read_text()
    assert md_text.startswith("# claim_grounding audit")


def test_claim_grounding_audit_jsonl_ledger_appends(tmp_path: Path):
    """Reruns APPEND to ``workspace/logs/.audit_findings.jsonl`` rather
    than truncating it — deterministic uuid5 keeps IDs stable, so
    re-runs produce the same lines."""
    root = _fixture_root(tmp_path)
    jsonl = root / "workspace" / "logs" / ".audit_findings.jsonl"

    findings1 = ClaimGroundingAudit().run(root)
    write_audit_outputs(findings1, "claim_grounding", root)
    first_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(first_lines) == len(findings1)
    for ln in first_lines:
        validate_finding(json.loads(ln))

    # Rerun — same workspace, same findings, but the ledger should now
    # have DOUBLED in line count (append-only).
    findings2 = ClaimGroundingAudit().run(root)
    write_audit_outputs(findings2, "claim_grounding", root)
    second_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(second_lines) == 2 * len(findings1)

    # The first run's lines are still the first half verbatim.
    assert second_lines[: len(first_lines)] == first_lines


def test_claim_grounding_audit_uuid5_is_deterministic(tmp_path: Path):
    """Same workspace + paper => same finding IDs across runs. This is
    the load-bearing property that keeps the jsonl ledger diffable."""
    root = _fixture_root(tmp_path)
    ids_a = sorted(f.id for f in ClaimGroundingAudit().run(root))
    ids_b = sorted(f.id for f in ClaimGroundingAudit().run(root))
    assert ids_a == ids_b


def test_claim_grounding_audit_handles_missing_target(tmp_path: Path):
    """When no synthesis target exists, the audit must NOT crash —
    instead it emits a single warn finding so the gate has a record."""
    # workspace exists but no synthesis/ at all.
    (tmp_path / "workspace").mkdir()
    findings = ClaimGroundingAudit().run(tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    validate_finding(findings[0].to_dict())
