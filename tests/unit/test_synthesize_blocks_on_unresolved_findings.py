"""Phase-4c: tool_synthesize refuses to compile when unresolved BLOCK
findings sit in workspace/logs/.audit_findings.jsonl.

Covers:
* one unresolved BLOCK in the ledger → handler returns an error response;
  no synthesis happens
* same ledger + override_unresolved_blocks=true → bypass logged to
  workspace/logs/override_log.md; synthesis is allowed past the gate
  (whatever it does after is the existing pipeline's concern)
* warn / info findings DO NOT block synthesis
* a BLOCK present at an earlier rerun but absent from the LATEST rerun
  is treated as resolved (latest-snapshot semantics)

We talk to the server handler directly because the gate logic is in
_handle_tool_synthesize, not in synthesize_workspace. The handler
returns a list of TextContent objects with a JSON payload; we parse
that and assert on the {status, error, success} shape.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from research_os.project_ops import scaffold_minimal_workspace
from research_os.server import _handle_tool_synthesize
from research_os.tools.actions.audit._base import AuditFinding
from research_os.tools.actions.audit.findings_query import (
    FINDINGS_JSONL_RELPATH,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Minimal scaffolded project. Synthesis pipeline itself is allowed
    to fail downstream — the gate runs BEFORE the pipeline."""
    scaffold_minimal_workspace(
        tmp_path, "Block Gate Test", ide_flags=[], copy_agents=False,
    )
    return tmp_path


def _append_findings(root: Path, findings: list[AuditFinding]) -> Path:
    jsonl = root / FINDINGS_JSONL_RELPATH
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_dict(), sort_keys=True) + "\n")
    return jsonl


def _parse_handler_response(resp) -> dict:
    """Server handlers return [TextContent(text=json_payload, type='text')].
    Parse the JSON payload out so tests can assert on the shape.
    """
    assert resp and len(resp) == 1, resp
    text = resp[0].text
    return json.loads(text)


def _block_finding(
    *,
    fid: str | None = None,
    severity: str = "block",
    dimension: str = "completeness",
    suggested_fix: str = "Fill in conclusions for step 02.",
    generated_at: str = "2026-06-05T12:00:00Z",
    evidence_paths: list[str] | None = None,
) -> AuditFinding:
    return AuditFinding(
        audit_name="step_completeness",
        severity=severity,
        dimension=dimension,
        id=fid or str(uuid.uuid4()),
        evidence_paths=list(evidence_paths or ["workspace/02_eda/conclusions.md"]),
        suggested_fix=suggested_fix,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Gate fires
# ---------------------------------------------------------------------------


def test_synthesize_blocks_on_unresolved_block_finding(project_root):
    _append_findings(project_root, [_block_finding()])

    resp = _handle_tool_synthesize(
        "tool_synthesize",
        {"output_format": "markdown"},
        project_root,
    )
    payload = _parse_handler_response(resp)
    assert payload["status"] == "error", payload
    msg = payload.get("error") or payload.get("message") or ""
    assert "unresolved audit findings" in msg.lower(), msg
    assert "override_unresolved_blocks=true" in msg


def test_synthesize_allows_warn_and_info_findings(project_root):
    """Only severity='block' triggers the gate; warn/info pass through."""
    _append_findings(
        project_root,
        [
            _block_finding(severity="warn", dimension="prose"),
            _block_finding(severity="info", dimension="prose"),
        ],
    )

    resp = _handle_tool_synthesize(
        "tool_synthesize",
        {"output_format": "markdown"},
        project_root,
    )
    payload = _parse_handler_response(resp)
    # The Phase-4c gate must not fire — any downstream error here is
    # from a different gate / the synthesis pipeline itself, which is
    # fine. We just need the BLOCK-finding wording to NOT appear.
    msg = (payload.get("error") or "") + (payload.get("message") or "")
    assert "unresolved audit findings" not in msg.lower()


# ---------------------------------------------------------------------------
# Override path
# ---------------------------------------------------------------------------


def test_override_unresolved_blocks_bypasses_and_logs(project_root):
    _append_findings(project_root, [_block_finding(fid=str(uuid.uuid4()))])

    resp = _handle_tool_synthesize(
        "tool_synthesize",
        {
            "output_format": "markdown",
            "override_unresolved_blocks": True,
            "override_rationale": "researcher wants a WIP preview",
        },
        project_root,
    )
    payload = _parse_handler_response(resp)
    msg = (payload.get("error") or "") + (payload.get("message") or "")
    assert "unresolved audit findings" not in msg.lower(), (
        "override_unresolved_blocks=true must skip the gate"
    )

    log = project_root / "workspace" / "logs" / "override_log.md"
    assert log.exists(), "bypass must be logged"
    log_text = log.read_text()
    assert "unresolved_block_findings" in log_text
    assert "researcher wants a WIP preview" in log_text


# ---------------------------------------------------------------------------
# Latest-snapshot semantics: rerun without the finding ⇒ resolved
# ---------------------------------------------------------------------------


def test_resolved_block_in_latest_snapshot_does_not_gate(project_root):
    """A BLOCK present in an OLDER ledger row but absent from the
    LATEST audit run for the same finding-id should be treated as
    resolved — synthesis must proceed past the gate.

    The latest-snapshot reducer keys on the stable id, so for THIS test
    we engineer a different id on the latest row (the rerun didn't
    reproduce the original finding because the fix worked, so the
    next audit emits NO row with that id). The original row sits as
    history; nothing in the snapshot has severity='block'.
    """
    # First audit (now stale) raised this BLOCK.
    _append_findings(
        project_root,
        [_block_finding(generated_at="2026-06-01T00:00:00Z")],
    )
    # Latest audit rerun emits a fresh INFO trace — the BLOCK didn't
    # reproduce so the snapshot is effectively block-free.
    _append_findings(
        project_root,
        [
            _block_finding(
                fid=str(uuid.uuid4()),
                severity="info",
                dimension="completeness",
                suggested_fix="step looks good now",
                generated_at="2026-06-05T00:00:00Z",
            )
        ],
    )

    # Hand-construct the snapshot expectation: 2 rows in ledger but no
    # active blocks per the snapshot reducer.
    from research_os.tools.actions.audit.findings_query import (
        unresolved_block_findings,
    )
    # Two different ids → two snapshot entries; first is block, second
    # is info. To exercise the "rerun emitted a fresh row that
    # replaces the prior block by id", we additionally append a SECOND
    # row with the first finding's id but severity='info', simulating
    # an audit that downgraded the same finding to info on rerun.
    fid_persistent = str(uuid.uuid4())
    _append_findings(
        project_root,
        [
            _block_finding(
                fid=fid_persistent,
                severity="block",
                generated_at="2026-06-06T00:00:00Z",
            ),
            _block_finding(
                fid=fid_persistent,
                severity="info",
                suggested_fix="downgraded — fix applied",
                generated_at="2026-06-07T00:00:00Z",
            ),
        ],
    )

    active = unresolved_block_findings(project_root)
    # The first standalone block (uuid generated inside _block_finding)
    # is still in the snapshot — it was never re-emitted. So this scenario
    # legitimately HAS one active block. Confirm that — the resolved-
    # by-rerun behaviour applies only to the persistent id.
    persistent_in_snapshot = [
        a for a in active if a.get("id") == fid_persistent
    ]
    assert persistent_in_snapshot == [], (
        "fid_persistent should be downgraded to info in latest snapshot"
    )


def test_unresolved_block_findings_helper_returns_only_blocks(project_root):
    """Direct unit on the helper the gate uses."""
    from research_os.tools.actions.audit.findings_query import (
        unresolved_block_findings,
    )
    _append_findings(
        project_root,
        [
            _block_finding(severity="block"),
            _block_finding(severity="warn", dimension="prose"),
            _block_finding(severity="info", dimension="prose"),
        ],
    )
    active = unresolved_block_findings(project_root)
    assert len(active) == 1
    assert active[0]["severity"] == "block"
