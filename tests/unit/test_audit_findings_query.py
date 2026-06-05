"""Phase-4c: tool_audit_findings_query — filter the cross-audit ledger.

Covers:
* empty ledger → empty result, status='success'
* severity / dimension / step / since filters compose
* latest-snapshot semantics: a finding emitted N times appears once
* malformed lines in the jsonl are skipped, not fatal
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import (
    AuditFinding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.findings_query import (
    FINDINGS_JSONL_RELPATH,
    audit_findings_query,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stamp_finding(
    *,
    audit_name: str,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    generated_at: str,
    finding_id: str | None = None,
    suggested_fix: str = "fix it",
) -> AuditFinding:
    """Build a finding with a stamped generated_at (factory default uses 'now')."""
    f = AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=finding_id or str(uuid.uuid4()),
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
        generated_at=generated_at,
    )
    return f


def _write_ledger(root: Path, findings: list[AuditFinding]) -> Path:
    """Append findings to the cross-audit ledger by hand (bypassing the
    {gate}_audit.md + .json side-effects so the test stays focused).
    """
    jsonl = root / FINDINGS_JSONL_RELPATH
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_dict(), sort_keys=True) + "\n")
    return jsonl


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------


def test_query_empty_ledger_returns_empty_success(tmp_path):
    res = audit_findings_query(tmp_path)
    assert res["status"] == "success"
    assert res["findings"] == []
    assert res["count"] == 0
    assert res["filters"] == {
        "severity": None,
        "dimension": None,
        "step": None,
        "since": None,
    }


# ---------------------------------------------------------------------------
# Severity / dimension / step / since filters
# ---------------------------------------------------------------------------


def test_query_filters_by_severity(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="A", severity="block", dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="B", severity="warn", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="C", severity="info", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-03T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_query(tmp_path, severity="block")
    assert res["count"] == 1
    assert res["findings"][0]["severity"] == "block"

    res = audit_findings_query(tmp_path, severity="warn")
    assert res["count"] == 1
    assert res["findings"][0]["audit_name"] == "B"


def test_query_filters_by_dimension(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="A", severity="block", dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="B", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_query(tmp_path, dimension="prose")
    assert res["count"] == 1
    assert res["findings"][0]["dimension"] == "prose"


def test_query_filters_by_step(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="A", severity="block", dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="B", severity="block", dimension="completeness",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="C", severity="warn", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-03T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_query(tmp_path, step="02_model")
    assert res["count"] == 1
    assert "02_model" in res["findings"][0]["evidence_paths"][0]


def test_query_filters_by_since(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="A", severity="block", dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="B", severity="warn", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_query(tmp_path, since="2026-06-03T00:00:00Z")
    assert res["count"] == 1
    assert res["findings"][0]["audit_name"] == "B"


def test_query_combines_multiple_filters(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="A", severity="block", dimension="prose",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="B", severity="warn", dimension="prose",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="C", severity="block", dimension="prose",
                evidence_paths=["workspace/03_eval/conclusions.md"],
                generated_at="2026-06-03T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_query(
        tmp_path, severity="block", dimension="prose", step="02_model",
    )
    assert res["count"] == 1
    assert res["findings"][0]["audit_name"] == "A"


# ---------------------------------------------------------------------------
# Latest-snapshot semantics + malformed lines
# ---------------------------------------------------------------------------


def test_query_returns_latest_snapshot_per_id(tmp_path):
    fid = str(uuid.uuid4())
    # Same id appears 3 times — 2nd and 3rd reruns mutate suggested_fix.
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="X", severity="block", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid, suggested_fix="initial fix",
            ),
            _stamp_finding(
                audit_name="X", severity="block", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-02T00:00:00Z",
                finding_id=fid, suggested_fix="middle fix",
            ),
            _stamp_finding(
                audit_name="X", severity="block", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-03T00:00:00Z",
                finding_id=fid, suggested_fix="latest fix",
            ),
        ],
    )
    res = audit_findings_query(tmp_path)
    assert res["count"] == 1, "deduped by id"
    assert res["findings"][0]["suggested_fix"] == "latest fix"


def test_query_skips_malformed_jsonl_lines(tmp_path):
    jsonl = tmp_path / FINDINGS_JSONL_RELPATH
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    good = _stamp_finding(
        audit_name="A", severity="block", dimension="prose",
        evidence_paths=["synthesis/paper.md"],
        generated_at="2026-06-01T00:00:00Z",
    )
    jsonl.write_text(
        json.dumps(good.to_dict(), sort_keys=True) + "\n"
        + "not-valid-json\n"
        + "{partial json,\n"
        + "\n"  # blank line
    )
    res = audit_findings_query(tmp_path)
    assert res["count"] == 1
    assert res["findings"][0]["audit_name"] == "A"


# ---------------------------------------------------------------------------
# Integration with write_audit_outputs
# ---------------------------------------------------------------------------


def test_query_reads_ledger_written_by_writer(tmp_path):
    """End-to-end: write findings via write_audit_outputs, then query."""
    findings = [
        AuditFinding.new(
            audit_name="step_completeness",
            severity="block",
            dimension="completeness",
            evidence_paths=["workspace/01_eda/conclusions.md"],
            suggested_fix="Fill in Findings section.",
        ),
        AuditFinding.new(
            audit_name="step_completeness",
            severity="info",
            dimension="completeness",
            evidence_paths=["workspace/02_eda/conclusions.md"],
            suggested_fix="step looks good",
        ),
    ]
    write_audit_outputs(findings, "step_completeness", tmp_path)
    res = audit_findings_query(tmp_path)
    assert res["count"] == 2
    res = audit_findings_query(tmp_path, severity="block")
    assert res["count"] == 1
    res = audit_findings_query(tmp_path, severity="info")
    assert res["count"] == 1
