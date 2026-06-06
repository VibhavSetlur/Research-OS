"""Phase-4c: tool_audit_findings_diff — diff two snapshots of the ledger.

Covers:
* added (in B not A) / resolved (in A not B) / changed (same id, different
  structural fields) are bucketed correctly
* same id, different generated_at / ro_version only → NOT changed
* bad timestamp → status='error'
* timestamp_b < timestamp_a → status='error'
* empty ledger → all buckets empty, status='success'
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import AuditFinding
from research_os.tools.actions.audit.findings_query import (
    FINDINGS_JSONL_RELPATH,
    audit_findings_diff,
)


def _stamp(
    *,
    audit_name: str,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    generated_at: str,
    finding_id: str | None = None,
    suggested_fix: str = "fix it",
    ro_version: str = "2.0.0-dev",
) -> AuditFinding:
    return AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=finding_id or str(uuid.uuid4()),
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
        generated_at=generated_at,
        ro_version=ro_version,
    )


def _write_ledger(root: Path, findings: list[AuditFinding]) -> Path:
    jsonl = root / FINDINGS_JSONL_RELPATH
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_dict(), sort_keys=True) + "\n")
    return jsonl


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_diff_empty_ledger_returns_empty_buckets(tmp_path):
    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-01T00:00:00Z",
        timestamp_b="2026-06-05T00:00:00Z",
    )
    assert res["status"] == "success"
    assert res["added"] == []
    assert res["resolved"] == []
    assert res["changed"] == []
    assert res["summary"] == {"added": 0, "resolved": 0, "changed": 0}


def test_diff_rejects_bad_timestamp(tmp_path):
    res = audit_findings_diff(
        tmp_path, timestamp_a="not-a-date", timestamp_b="2026-06-05T00:00:00Z",
    )
    assert res["status"] == "error"
    assert "ISO-8601" in res["message"]


def test_diff_rejects_b_before_a(tmp_path):
    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-05T00:00:00Z",
        timestamp_b="2026-06-01T00:00:00Z",
    )
    assert res["status"] == "error"
    assert "on/after" in res["message"]


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def test_diff_buckets_added_resolved_changed(tmp_path):
    # Stable ids so we can engineer the buckets deterministically.
    id_persistent = str(uuid.uuid4())
    id_resolved = str(uuid.uuid4())
    id_added = str(uuid.uuid4())

    # Snapshot A (=== before): persistent + resolved.
    # Snapshot B (=== after):  persistent (CHANGED) + added.
    # Resolution semantics: audit "Y" must RERUN in (A, B] without
    # re-emitting id_resolved for it to count as resolved. Same for
    # the persistent change — audit "X" must rerun in (A, B] and
    # re-emit id_persistent with the new content.
    _write_ledger(
        tmp_path,
        [
            # both present at A (different audits)
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=id_persistent,
                suggested_fix="too much hedging",
            ),
            _stamp(
                audit_name="Y", severity="warn", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=id_resolved,
                suggested_fix="cite this claim",
            ),
            # later: audit X reruns at B-1 and re-emits id_persistent
            # with NEW suggested_fix (CHANGED)
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=id_persistent,
                suggested_fix="now also: passive voice",
            ),
            # later: audit Y reruns at B-1 but emits NO row for
            # id_resolved (the fix worked) — instead emits a different
            # id, which proves the audit ran. id_resolved is then RESOLVED.
            _stamp(
                audit_name="Y", severity="info", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=str(uuid.uuid4()),
                suggested_fix="claims audit clean now",
            ),
            # later: audit Z runs for the first time and emits a new
            # blocker (ADDED)
            _stamp(
                audit_name="Z", severity="block", dimension="completeness",
                evidence_paths=["workspace/03_eval/conclusions.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=id_added,
            ),
        ],
    )

    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-01T12:00:00Z",
        timestamp_b="2026-06-05T12:00:00Z",
    )
    assert res["status"] == "success"
    # added = id_added (Z block) + the new Y-info row added to prove Y reran
    assert res["summary"]["added"] == 2
    assert res["summary"]["resolved"] == 1
    assert res["summary"]["changed"] == 1

    added_ids = {r["id"] for r in res["added"]}
    resolved_ids = {r["id"] for r in res["resolved"]}
    changed_ids = {c["id"] for c in res["changed"]}
    assert id_added in added_ids
    assert resolved_ids == {id_resolved}
    assert changed_ids == {id_persistent}

    # `changed` carries both before + after.
    change = res["changed"][0]
    assert change["before"]["suggested_fix"] == "too much hedging"
    assert change["after"]["suggested_fix"] == "now also: passive voice"


def test_diff_ignores_pure_rerun_with_unchanged_structure(tmp_path):
    """Same id, same structural fields, different generated_at +
    ro_version → NOT in `changed`."""
    fid = str(uuid.uuid4())
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid, suggested_fix="reduce hedging",
                ro_version="1.11.0",
            ),
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=fid, suggested_fix="reduce hedging",
                ro_version="2.0.0",
            ),
        ],
    )
    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-01T12:00:00Z",
        timestamp_b="2026-06-05T12:00:00Z",
    )
    assert res["status"] == "success"
    assert res["summary"]["added"] == 0
    assert res["summary"]["resolved"] == 0
    assert res["summary"]["changed"] == 0, (
        "pure rerun must NOT show as changed"
    )


def test_diff_detects_severity_change(tmp_path):
    fid = str(uuid.uuid4())
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="X", severity="warn", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid,
            ),
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=fid,
            ),
        ],
    )
    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-01T12:00:00Z",
        timestamp_b="2026-06-05T12:00:00Z",
    )
    assert res["summary"]["changed"] == 1
    change = res["changed"][0]
    assert change["before"]["severity"] == "warn"
    assert change["after"]["severity"] == "block"


def test_diff_resolved_finding_no_longer_in_latest_snapshot(tmp_path):
    """A BLOCK finding emitted at A, then its audit reruns in (A, B]
    without re-emitting it, is resolved."""
    fid_a = str(uuid.uuid4())
    fid_b = str(uuid.uuid4())
    # Audit "X" emits fid_a at A. Audit "X" reruns at B-1 and emits a
    # DIFFERENT id — proving the audit ran and chose not to re-emit
    # fid_a (the fix worked).
    _write_ledger(
        tmp_path,
        [
            _stamp(
                audit_name="X", severity="block", dimension="prose",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-01T00:00:00Z",
                finding_id=fid_a, suggested_fix="reduce hedging",
            ),
            # X rerun — emits fid_b as a fresh finding; fid_a not
            # re-emitted so it's RESOLVED.
            _stamp(
                audit_name="X", severity="block", dimension="claims",
                evidence_paths=["synthesis/paper.md"],
                generated_at="2026-06-05T00:00:00Z",
                finding_id=fid_b, suggested_fix="cite this",
            ),
        ],
    )
    res = audit_findings_diff(
        tmp_path,
        timestamp_a="2026-06-02T00:00:00Z",
        timestamp_b="2026-06-06T00:00:00Z",
    )
    assert res["summary"]["resolved"] == 1
    assert res["resolved"][0]["id"] == fid_a
    assert res["summary"]["added"] == 1
    assert res["added"][0]["id"] == fid_b
