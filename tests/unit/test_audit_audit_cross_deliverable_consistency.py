"""Phase-4 AuditBase wrapper for cross-deliverable consistency.

Covers the v2 fan-out introduced when migrating
``audit_cross_deliverable_consistency`` to :class:`AuditBase`:

* the legacy procedural auditor's markdown log
  (``workspace/logs/cross_deliverable_audit.md``) is byte-identical
  before and after the AuditBase wrapper runs — the wrapper is purely
  additive and must not perturb the existing format;
* :func:`write_audit_outputs` emits a schema-valid JSON companion;
* the append-only ``.audit_findings.jsonl`` ledger gains a fresh line
  per finding on each run.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.cross_deliverable import (
    CrossDeliverableConsistencyAudit,
    audit_cross_deliverable_consistency,
)

# ---------------------------------------------------------------------------
# Fixture: a well-formed multi-deliverable project
# ---------------------------------------------------------------------------


_REF_FOOTER = (
    "\n\n---\n\n"
    "Research-OS version: v1.11.0  ·  commit: deadbeefcafe1234  ·  "
    "built: 2026-06-05T12:00:00Z\n"
)


def _make_paper(root: Path) -> Path:
    p = root / "synthesis" / "paper.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# A Study of Things\n\n"
        "## Abstract\n\n"
        "We analysed n = 423 subjects and report AUROC = 0.84 (p < 0.01).\n\n"
        "## Methods\n\n"
        "![Figure 1](outputs/fig1.png)\n\n"
        "We cite @smith2020 and @jones2021.\n\n"
        "## Findings\n\n"
        "Subjects with treatment showed a 42% improvement in outcomes "
        "compared to controls.\n"
        + _REF_FOOTER
    )
    return p


def _make_dashboard(root: Path) -> Path:
    p = root / "synthesis" / "dashboard.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "<html><body>"
        "<h2>Findings</h2>"
        "<p>Subjects with treatment showed a 42% improvement in outcomes.</p>"
        "<p>AUROC = 0.84 across n = 423 subjects.</p>"
        "<img src=\"outputs/fig1.png\" alt=\"Figure 1\">"
        "<p>Cited: @smith2020.</p>"
        "</body></html>"
        + "<footer>" + _REF_FOOTER + "</footer>"
    )
    return p


def _make_slides(root: Path) -> Path:
    p = root / "synthesis" / "slides.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Slides\n\n"
        "## Findings\n\n"
        "Treatment yielded a 42% improvement in outcomes for subjects.\n\n"
        "![](outputs/fig1.png)\n\n"
        "Cite: @smith2020.\n"
        + _REF_FOOTER
    )
    return p


@pytest.fixture
def good_project(tmp_path: Path) -> Path:
    """A project where every dimension passes."""
    _make_paper(tmp_path)
    _make_dashboard(tmp_path)
    _make_slides(tmp_path)
    return tmp_path


@pytest.fixture
def divergent_project(tmp_path: Path) -> Path:
    """A project where numeric_claims_consistent fails (AUROC mismatch)."""
    _make_paper(tmp_path)
    p = tmp_path / "synthesis" / "dashboard.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    # AUROC diverges from the paper's 0.84.
    p.write_text(
        "<html><body><h2>Findings</h2>"
        "<p>Subjects with treatment showed a 42% improvement.</p>"
        "<p>AUROC = 0.93 across n = 423 subjects.</p>"
        "</body></html>"
        + _REF_FOOTER
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Regression: legacy markdown is unchanged by the AuditBase fan-out
# ---------------------------------------------------------------------------


def test_legacy_markdown_unchanged_by_v2_wrapper(good_project: Path):
    """Calling the legacy auditor twice + the AuditBase wrapper once must
    produce a markdown log identical to a fresh legacy run.

    The wrapper internally re-invokes the legacy auditor, so we lock the
    output format by snapshotting the legacy markdown on first run and
    comparing it to a second legacy run after the wrapper has executed.
    """
    # Snapshot the legacy markdown produced by a clean run.
    audit_cross_deliverable_consistency(good_project)
    log_path = good_project / "workspace" / "logs" / "cross_deliverable_audit.md"
    assert log_path.is_file(), "legacy auditor must write its markdown log"
    # Strip the ISO timestamp on the second line so the snapshot is stable.
    first_text = _strip_timestamp(log_path.read_text())

    # Run the AuditBase wrapper.
    findings = CrossDeliverableConsistencyAudit().run(good_project)
    assert isinstance(findings, list)
    assert all(f.audit_name == "cross_deliverable_consistency" for f in findings)

    # Now run the legacy auditor again. Its markdown must match the
    # first snapshot byte-for-byte (modulo the timestamp).
    audit_cross_deliverable_consistency(good_project)
    second_text = _strip_timestamp(log_path.read_text())
    assert first_text == second_text, (
        "AuditBase fan-out must not perturb the legacy markdown format"
    )


def _strip_timestamp(text: str) -> str:
    """Drop the ``_Generated …_`` line so snapshots are time-stable."""
    out_lines = []
    for line in text.splitlines():
        if line.startswith("_Generated ") and line.endswith("_"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# AuditBase wrapper emits valid findings
# ---------------------------------------------------------------------------


def test_run_returns_audit_findings_for_passing_project(good_project: Path):
    """On a clean project, the wrapper still emits an info heartbeat."""
    findings = CrossDeliverableConsistencyAudit().run(good_project)
    assert len(findings) >= 1
    # Heartbeat finding is always present.
    summary = [f for f in findings if f.dimension == "cross_deliverable_summary"]
    assert len(summary) == 1
    assert summary[0].severity == "info"
    # No block-severity findings when every dimension passes.
    assert not [f for f in findings if f.severity == "block"]


def test_run_emits_block_finding_on_numeric_divergence(divergent_project: Path):
    """Numeric claim divergence produces a block-severity finding."""
    findings = CrossDeliverableConsistencyAudit().run(divergent_project)
    blocks = [f for f in findings if f.severity == "block"]
    assert blocks, "divergent numeric claims must produce a block finding"
    dims = {f.dimension for f in blocks}
    assert "numeric_claims_consistent" in dims


def test_run_handles_skipped_project_with_info_heartbeat(tmp_path: Path):
    """A project with only one deliverable skips, emitting an info finding."""
    _make_paper(tmp_path)
    findings = CrossDeliverableConsistencyAudit().run(tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].dimension == "cross_deliverable_skipped"


# ---------------------------------------------------------------------------
# write_audit_outputs companion (.json + .jsonl)
# ---------------------------------------------------------------------------


def test_json_companion_is_schema_valid(good_project: Path):
    """Every finding in {gate}_audit.json round-trips through the schema."""
    findings = CrossDeliverableConsistencyAudit().run(good_project)
    paths = write_audit_outputs(
        findings, "cross_deliverable_consistency", good_project
    )
    arr = json.loads(paths["json"].read_text())
    assert isinstance(arr, list) and len(arr) == len(findings)
    for d in arr:
        validate_finding(d)
    # Each id is a valid uuid4-shaped string.
    for d in arr:
        uuid.UUID(d["id"])


def test_jsonl_rollup_appends_on_each_run(divergent_project: Path):
    """Re-running the audit appends new lines to the .audit_findings.jsonl ledger."""
    jl = (
        divergent_project / "workspace" / "logs" / ".audit_findings.jsonl"
    )

    # First run.
    first = CrossDeliverableConsistencyAudit().run(divergent_project)
    write_audit_outputs(first, "cross_deliverable_consistency", divergent_project)
    first_lines = [ln for ln in jl.read_text().splitlines() if ln.strip()]
    assert len(first_lines) == len(first)

    # Second run (deterministic ids — same findings).
    second = CrossDeliverableConsistencyAudit().run(divergent_project)
    write_audit_outputs(second, "cross_deliverable_consistency", divergent_project)
    second_lines = [ln for ln in jl.read_text().splitlines() if ln.strip()]
    assert len(second_lines) == len(first_lines) + len(second)

    # Every line still validates.
    for ln in second_lines:
        validate_finding(json.loads(ln))


def test_finding_ids_are_deterministic_across_runs(divergent_project: Path):
    """Stable uuid5 ids: re-running on the same workspace yields the same ids."""
    a = CrossDeliverableConsistencyAudit().run(divergent_project)
    b = CrossDeliverableConsistencyAudit().run(divergent_project)
    a_ids = sorted(f.id for f in a)
    b_ids = sorted(f.id for f in b)
    assert a_ids == b_ids


def test_md_companion_groups_by_severity(divergent_project: Path):
    """The {gate}_audit.md report orders block findings before info."""
    findings = CrossDeliverableConsistencyAudit().run(divergent_project)
    paths = write_audit_outputs(
        findings, "cross_deliverable_consistency", divergent_project
    )
    text = paths["md"].read_text()
    assert "# cross_deliverable_consistency audit" in text
    # Block heading must precede info heading (severity order).
    if "block (" in text and "info (" in text:
        assert text.index("block (") < text.index("info (")
