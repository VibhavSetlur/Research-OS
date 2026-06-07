"""W09: tool_audit_findings(operation='explain', id=...) — full history,
no truncation.

Covers:
* explain() returns every chronological snapshot of one finding id
* suggested_fix text is preserved verbatim (NO 160-char truncation)
* evidence_paths come through complete
* empty result when id is unknown (still status='success')
* error envelope when id is missing
* synthesize BLOCK error embeds next_recommended_call pointing at
  tool_audit_findings(operation='explain', id='<first blocker id>')
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import (
    AuditFinding,
)
from research_os.tools.actions.audit.findings_query import (
    FINDINGS_JSONL_RELPATH,
    audit_findings_explain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stamp(
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


# ---------------------------------------------------------------------------
# explain()
# ---------------------------------------------------------------------------


def test_explain_returns_all_snapshots_in_chronological_order(tmp_path):
    fid = str(uuid.uuid4())
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid,
                suggested_fix="first raise",
            ),
            # noise: different id, must not be returned
            _stamp(
                audit_name="prose_quality", severity="warn",
                dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-02T00:00:00Z",
                suggested_fix="ignored",
            ),
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-03T00:00:00Z",
                finding_id=fid,
                suggested_fix="re-raised after refactor",
            ),
        ],
    )

    res = audit_findings_explain(tmp_path, finding_id=fid)
    assert res["status"] == "success"
    assert res["id"] == fid
    assert res["snapshot_count"] == 2
    assert [s["suggested_fix"] for s in res["snapshots"]] == [
        "first raise",
        "re-raised after refactor",
    ]
    assert res["first_seen"] == "2026-06-01T00:00:00Z"
    assert res["last_seen"] == "2026-06-03T00:00:00Z"
    assert res["current"]["suggested_fix"] == "re-raised after refactor"


def test_explain_preserves_full_suggested_fix_no_truncation(tmp_path):
    """The BLOCK preview in synthesize truncates at 160 chars. explain()
    must NOT — the whole point of the operation is to recover the full
    remediation text."""
    fid = str(uuid.uuid4())
    # 600+ chars of remediation guidance to make truncation visible
    long_fix = (
        "Run tool_audit_step_completeness on the affected step. The gate "
        "needs both a conclusions.md (with a What / So-what / Next "
        "section), a step_summary.yaml that names the figures, and at "
        "least one figure in outputs/figures/ with a caption sidecar. "
        "If the step is genuinely a section-only deliverable, mark it "
        "literature_required=false in the per-step config and rerun the "
        "audit so the latest snapshot reflects the override."
    )
    assert len(long_fix) > 200
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/02_model/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid,
                suggested_fix=long_fix,
            ),
        ],
    )

    res = audit_findings_explain(tmp_path, finding_id=fid)
    assert res["snapshot_count"] == 1
    assert res["snapshots"][0]["suggested_fix"] == long_fix
    # Belt-and-braces: nothing was sliced to 160
    assert len(res["snapshots"][0]["suggested_fix"]) == len(long_fix)


def test_explain_returns_evidence_paths_intact(tmp_path):
    fid = str(uuid.uuid4())
    paths = [
        "workspace/02_model/conclusions.md",
        "workspace/02_model/outputs/figures/fig1.png",
        "workspace/02_model/step_summary.yaml",
    ]
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=paths,
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid,
            ),
        ],
    )
    res = audit_findings_explain(tmp_path, finding_id=fid)
    assert res["snapshots"][0]["evidence_paths"] == paths


def test_explain_unknown_id_returns_empty_success(tmp_path):
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="A", severity="block", dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
            ),
        ],
    )
    res = audit_findings_explain(tmp_path, finding_id=str(uuid.uuid4()))
    assert res["status"] == "success"
    assert res["snapshots"] == []
    assert res["snapshot_count"] == 0
    assert res["first_seen"] is None
    assert res["last_seen"] is None
    assert res["current"] is None


def test_explain_empty_ledger_returns_empty_success(tmp_path):
    res = audit_findings_explain(tmp_path, finding_id=str(uuid.uuid4()))
    assert res["status"] == "success"
    assert res["snapshots"] == []
    assert res["snapshot_count"] == 0


def test_explain_missing_id_returns_error(tmp_path):
    res = audit_findings_explain(tmp_path, finding_id="")
    assert res["status"] == "error"
    assert "finding_id" in res["message"]


# ---------------------------------------------------------------------------
# Dispatcher: operation='explain' routes through tool_audit_findings
# ---------------------------------------------------------------------------


def test_dispatcher_routes_explain_operation(tmp_path):
    """tool_audit_findings(operation='explain', id=...) reaches the
    explain handler and returns the snapshot list."""
    from research_os.server.handlers.audit_core import (
        _handle_tool_audit_findings,
    )

    fid = str(uuid.uuid4())
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid,
                suggested_fix="full text the AI needs",
            ),
        ],
    )

    out = _handle_tool_audit_findings(
        "tool_audit_findings",
        {"operation": "explain", "id": fid},
        str(tmp_path),
    )
    # _text returns a list of TextContent objects; parse the text body.
    body = json.loads(out[0].text)
    assert body["status"] == "success"
    assert body["payload"]["id"] == fid
    assert body["payload"]["snapshot_count"] == 1
    assert (
        body["payload"]["snapshots"][0]["suggested_fix"]
        == "full text the AI needs"
    )


def test_dispatcher_explain_without_id_errors(tmp_path):
    from research_os.server.handlers.audit_core import (
        _handle_tool_audit_findings,
    )

    out = _handle_tool_audit_findings(
        "tool_audit_findings",
        {"operation": "explain"},
        str(tmp_path),
    )
    body = json.loads(out[0].text)
    assert body["status"] == "error"
    assert "id=" in body["error"]


# ---------------------------------------------------------------------------
# Synthesize BLOCK envelope carries next_recommended_call
# ---------------------------------------------------------------------------


def test_synthesize_block_envelope_points_at_explain(tmp_path):
    """When tool_synthesize is BLOCKed by unresolved findings, the error
    envelope's next_recommended_call must steer the AI to
    tool_audit_findings(operation='explain', id='<first blocker id>')."""
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.server import _handle_tool_synthesize

    scaffold_minimal_workspace(
        tmp_path, "Block Gate Test", ide_flags=[], copy_agents=False,
    )
    # Need at least one numbered step under workspace/ for the
    # synthesize handler to proceed past its empty-workspace guard.
    (tmp_path / "workspace" / "01_eda").mkdir(parents=True, exist_ok=True)

    fid_a = str(uuid.uuid4())
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="step_completeness", severity="block",
                dimension="completeness",
                evidence_paths=["workspace/01_eda/conclusions.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid_a,
                suggested_fix="resolve the completeness gap",
            ),
        ],
    )

    out = _handle_tool_synthesize(
        "tool_synthesize",
        {"output_type": "paper"},
        str(tmp_path),
    )
    body = json.loads(out[0].text)
    assert body["status"] == "error"
    expected = (
        f'tool_audit_findings(operation="explain", id="{fid_a}")'
    )
    assert body["next_recommended_call"] == expected
    # The composed error text mentions the id + the next call so a
    # plaintext-only client still sees the steer.
    assert fid_a in body["error"]
    assert "explain" in body["error"]
