"""W10: tool_audit_findings(operation='timeline') — full append-only ledger.

Unlike operation='query' (latest snapshot per id), 'timeline' returns
every emission so long-context models can spot recurrence + override
loops.

Covers:
* empty ledger → empty snapshots, status='success'
* every emission preserved (no dedup by id)
* chronological order matches file order
* optional gate_name filter narrows to one audit
* optional scope filter narrows to one step / path token
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import AuditFinding
from research_os.tools.actions.audit.findings_query import (
    FINDINGS_JSONL_RELPATH,
    audit_findings_timeline,
)


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
    return AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=finding_id or str(uuid.uuid4()),
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
        generated_at=generated_at,
    )


def _write_ledger(root: Path, findings: list[AuditFinding]) -> Path:
    jsonl = root / FINDINGS_JSONL_RELPATH
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_dict(), sort_keys=True) + "\n")
    return jsonl


def test_timeline_empty_ledger_returns_empty_success(tmp_path):
    res = audit_findings_timeline(tmp_path)
    assert res["status"] == "success"
    assert res["snapshots"] == []
    assert res["snapshot_count"] == 0
    assert res["filters"] == {"gate_name": None, "scope": None}
    assert res["ledger_path"] == str(FINDINGS_JSONL_RELPATH)


def test_timeline_preserves_every_emission_no_dedup(tmp_path):
    """Same id appears 3 times — timeline keeps all 3; query keeps 1."""
    fid = str(uuid.uuid4())
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
    res = audit_findings_timeline(tmp_path)
    assert res["snapshot_count"] == 3, "timeline preserves every emission"
    # Chronological — file order matches generated_at order in this fixture.
    fixes = [s["suggested_fix"] for s in res["snapshots"]]
    assert fixes == ["initial fix", "middle fix", "latest fix"]


def test_timeline_filters_by_gate_name(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="cross_deliverable_consistency", severity="warn",
                dimension="cross_deliverable",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="step_completeness", severity="info",
                dimension="completeness",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-03T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_timeline(tmp_path, gate_name="step_completeness")
    assert res["snapshot_count"] == 2
    assert all(s["audit_name"] == "step_completeness" for s in res["snapshots"])


def test_timeline_filters_by_scope(tmp_path):
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
    res = audit_findings_timeline(tmp_path, scope="02_model")
    assert res["snapshot_count"] == 1
    assert "02_model" in res["snapshots"][0]["evidence_paths"][0]


def test_timeline_combines_gate_and_scope_filters(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp_finding(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="step_completeness", severity="warn",
                dimension="completeness",
                evidence_paths=["workspace/03_eval/conclusions.md"],
                generated_at="2026-06-02T00:00:00Z",
            ),
            _stamp_finding(
                audit_name="prose", severity="warn", dimension="prose",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-03T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_timeline(
        tmp_path, gate_name="step_completeness", scope="02_model",
    )
    assert res["snapshot_count"] == 1
    assert res["snapshots"][0]["audit_name"] == "step_completeness"
    assert "02_model" in res["snapshots"][0]["evidence_paths"][0]


def test_timeline_detects_recurrence_pattern(tmp_path):
    """A finding that keeps coming back after overrides — the use case."""
    fid = str(uuid.uuid4())
    # 5 emissions of the same id across 5 audit reruns. query() returns 1;
    # timeline() returns all 5 so a long-context model can flag the loop.
    for i in range(5):
        _write_ledger(
            tmp_path,
            [
                _stamp_finding(
                    audit_name="claim_grounding", severity="block",
                    dimension="claims",
                    evidence_paths=["synthesis/paper.md"],
                    generated_at=f"2026-06-{i+1:02d}T00:00:00Z",
                    finding_id=fid,
                    suggested_fix=f"attempt {i+1}: still ungrounded",
                ),
            ],
        )
    res = audit_findings_timeline(tmp_path, gate_name="claim_grounding")
    assert res["snapshot_count"] == 5, "every recurrence preserved"
    # All same id — the recurrence pattern.
    ids = {s["id"] for s in res["snapshots"]}
    assert ids == {fid}
