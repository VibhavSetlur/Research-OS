"""3.2 project-end meta-review — workspace/audit.md.

The single human-facing audit artefact, generated at the ship gate from
the cross-audit findings ledger: per-step concerns + evidence hashes +
suggested fixes. The per-gate machine detail stays in logs/audits/.
"""
from __future__ import annotations

from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.audit._base import (
    AuditFinding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.ship_gate import (
    finalize_project,
    write_final_audit,
)


def _seed_finding(root: Path) -> None:
    finding = AuditFinding(
        audit_name="step_completeness",
        severity="warn",
        dimension="caption_sidecar",
        id="11111111-1111-5111-8111-111111111111",
        evidence_paths=["workspace/02_eda/outputs/figures/"],
        suggested_fix="Write 02_dist.caption.md next to the figure.",
    )
    write_audit_outputs([finding], "step_completeness", root)


def test_write_final_audit_groups_by_step(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    _seed_finding(tmp_path)
    rel = write_final_audit(tmp_path)
    assert rel == "workspace/audit.md"
    text = (tmp_path / "workspace" / "audit.md").read_text()
    assert text.startswith("# Project audit — meta-review")
    assert "## `02_eda`" in text
    assert "caption_sidecar" in text
    assert "sha256" in text  # evidence hash line present
    assert "Write 02_dist.caption.md" in text


def test_final_audit_handles_empty_ledger(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    rel = write_final_audit(tmp_path)
    assert rel == "workspace/audit.md"
    text = (tmp_path / "workspace" / "audit.md").read_text()
    assert "No outstanding audit findings" in text


def test_finalize_project_emits_audit_md(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    _seed_finding(tmp_path)
    res = finalize_project(tmp_path, operation="check")
    assert res.get("audit_md") == "workspace/audit.md"
    assert (tmp_path / "workspace" / "audit.md").exists()
