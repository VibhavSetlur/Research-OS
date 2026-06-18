"""Phase-4 v2 migration tests for tool_audit_step_literature.

The audit's free-form blocker / warning strings are preserved (the
legacy `workspace/logs/step_literature_audit.md` is byte-identical to
the v1 output); these tests cover the NEW structured Phase-4 artefacts
the migrated audit also produces:

* the markdown report at ``workspace/logs/step_literature_audit.md``
  is preserved exactly (regression snapshot)
* :func:`StepLiteratureAudit.run` returns a list of valid
  ``AuditFinding`` objects
* :func:`audit_step_literature` writes the JSON companion
  ``workspace/logs/audits/step_literature_audit.json`` and it is schema-valid
* the append-only ``workspace/logs/.audit_findings.jsonl`` ledger
  gains new lines on each run (one per finding)
* finding ids are deterministic across re-runs against the same inputs
"""

from __future__ import annotations

import json

import pytest

from research_os.tools.actions.audit._base import (
    AuditFinding,
    validate_finding,
)
from research_os.tools.actions.audit.step_literature import (
    StepLiteratureAudit,
    audit_step_literature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_step_missing_fvl(root, step_name: str = "03_run_deseq2") -> None:
    """Step with a real Findings section but no findings_vs_literature.md."""
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(root, "Test")
    step_dir = root / "workspace" / step_name
    step_dir.mkdir(parents=True, exist_ok=True)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n"
        "- APOE significantly down-regulated in AD vs CTRL "
        "(log2FC=-1.4, padj=2e-5).\n"
        "- 247 DE genes pass FDR<0.05.\n"
    )


def _seed_step_passing(root, step_name: str = "05_hub_genes") -> None:
    """Complete literature loop — should pass cleanly with no blockers."""
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(root, "Test")
    step_dir = root / "workspace" / step_name
    step_dir.mkdir(parents=True, exist_ok=True)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- APOE up-regulated 1.4-fold, padj=1e-6.\n"
    )
    lit_dir = step_dir / "literature"
    lit_dir.mkdir(exist_ok=True)
    (lit_dir / "findings_vs_literature.md").write_text(
        "## Claim: APOE up-regulated in AD hippocampus\n\n"
        "**Our finding:** log2FC=1.4, padj=1e-6.\n\n"
        "**Literature says:** Smith 2024 reports the same direction.\n\n"
        "**Verdict:** AGREES\n\n"
        "**Evidence:**\n- [@smith2024] (2024) - confirms direction.\n\n"
        "**Discussion implication:** anchor the discussion paragraph.\n"
    )
    (step_dir / "step_summary.yaml").write_text(
        "literature:\n"
        "  claims_grounded: 1\n"
        "  claims_deferred: 0\n"
        "  papers_downloaded: 1\n"
        "  verdicts: {agrees: 1, disagrees: 0, extends: 0}\n"
    )


# ---------------------------------------------------------------------------
# Markdown regression snapshot — legacy report MUST be byte-identical
# ---------------------------------------------------------------------------


def test_legacy_markdown_report_unchanged_for_missing_fvl(tmp_path):
    """The migrated audit must keep producing the same workspace/logs/
    step_literature_audit.md content the v1 implementation produced."""
    _seed_step_missing_fvl(tmp_path)
    res = audit_step_literature(tmp_path, step_id="03_run_deseq2")

    log_path = tmp_path / "workspace" / "logs" / "step_literature_audit.md"
    assert log_path.exists()
    expected = (
        "# Per-step literature loop audit\n"
        "\n"
        "- Steps audited (non-skipped): **1**\n"
        "- Steps with findings_vs_literature.md: **0**\n"
        "- Steps skipped (no conclusions / data-eng): **0**\n"
        "- Verdict roll-up: AGREES=0, DISAGREES=0, EXTENDS=0, DEFERRED=0\n"
        "\n"
        "## Blockers (1)\n"
        "\n"
        "- 03_run_deseq2: missing workspace/03_run_deseq2/literature/"
        "findings_vs_literature.md. Run research/literature_per_step before "
        "path_finalize, OR pass override_literature_gate=true with "
        "override_rationale.\n"
        "\n"
        "## Warnings (0)\n"
        "\n"
        "_None_\n"
    )
    assert log_path.read_text() == expected
    assert res["status"] == "error"
    assert res["log_path"] == "workspace/logs/step_literature_audit.md"


def test_legacy_markdown_report_unchanged_for_passing(tmp_path):
    _seed_step_passing(tmp_path)
    audit_step_literature(tmp_path, step_id="05_hub_genes")
    log_path = tmp_path / "workspace" / "logs" / "step_literature_audit.md"
    text = log_path.read_text()
    # Verdict roll-up reflects the AGREES verdict.
    assert "AGREES=1" in text
    assert "DISAGREES=0" in text
    # Header + section labels preserved verbatim.
    assert text.startswith("# Per-step literature loop audit")
    assert "## Blockers (0)" in text
    assert "## Warnings (0)" in text


# ---------------------------------------------------------------------------
# AuditBase subclass surface
# ---------------------------------------------------------------------------


def test_step_literature_audit_subclasses_auditbase(tmp_path):
    """Class name + ``name`` attribute + return type contract."""
    from research_os.tools.actions.audit._base import AuditBase

    assert issubclass(StepLiteratureAudit, AuditBase)
    assert StepLiteratureAudit.name == "step_literature"

    _seed_step_missing_fvl(tmp_path)
    audit = StepLiteratureAudit()
    findings = audit.run(tmp_path, step_id="03_run_deseq2")
    assert isinstance(findings, list)
    assert findings, "missing findings_vs_literature.md must emit a finding"
    assert all(isinstance(f, AuditFinding) for f in findings)
    assert all(f.audit_name == "step_literature" for f in findings)


def test_findings_have_block_severity_for_missing_fvl(tmp_path):
    _seed_step_missing_fvl(tmp_path)
    findings = StepLiteratureAudit().run(tmp_path, step_id="03_run_deseq2")
    severities = {f.severity for f in findings}
    assert "block" in severities
    # Dimension surfaces the specific failure axis.
    assert any(f.dimension == "findings_vs_lit_md" for f in findings)


def test_passing_step_emits_zero_findings(tmp_path):
    _seed_step_passing(tmp_path)
    findings = StepLiteratureAudit().run(tmp_path, step_id="05_hub_genes")
    # No blockers AND no warnings for a fully-grounded step.
    assert findings == []


# ---------------------------------------------------------------------------
# JSON companion + .audit_findings.jsonl roll-up
# ---------------------------------------------------------------------------


def test_json_companion_written_and_schema_valid(tmp_path):
    _seed_step_missing_fvl(tmp_path)
    audit_step_literature(tmp_path, step_id="03_run_deseq2")

    json_path = tmp_path / "workspace" / "logs" / "audits" / "step_literature_audit.json"
    assert json_path.exists()
    arr = json.loads(json_path.read_text())
    assert isinstance(arr, list)
    assert len(arr) >= 1
    # Every emitted finding satisfies the schema.
    for d in arr:
        validate_finding(d)
        assert d["audit_name"] == "step_literature"


def test_jsonl_ledger_appends_on_each_run(tmp_path):
    _seed_step_missing_fvl(tmp_path)
    audit_step_literature(tmp_path, step_id="03_run_deseq2")

    jl = tmp_path / "workspace" / "logs" / ".audit_findings.jsonl"
    assert jl.exists()
    first_lines = [ln for ln in jl.read_text().splitlines() if ln.strip()]
    assert first_lines, "first run must write at least one finding line"
    for line in first_lines:
        d = json.loads(line)
        validate_finding(d)
        assert d["audit_name"] == "step_literature"

    # Re-run — same inputs, so the ledger appends MORE lines (one per
    # finding) but the structured ids should be identical (deterministic).
    audit_step_literature(tmp_path, step_id="03_run_deseq2")
    second_lines = [ln for ln in jl.read_text().splitlines() if ln.strip()]
    assert len(second_lines) == 2 * len(first_lines), (
        "jsonl ledger is APPEND-only: re-run must add a new line per finding"
    )
    # The earliest lines still match verbatim.
    assert second_lines[: len(first_lines)] == first_lines


def test_finding_ids_are_deterministic(tmp_path):
    _seed_step_missing_fvl(tmp_path)
    ids_first = {
        f.id for f in StepLiteratureAudit().run(tmp_path, step_id="03_run_deseq2")
    }
    ids_second = {
        f.id for f in StepLiteratureAudit().run(tmp_path, step_id="03_run_deseq2")
    }
    assert ids_first == ids_second, (
        "uuid5 derivation must yield identical ids across re-runs"
    )


# ---------------------------------------------------------------------------
# Public function still returns the legacy dict shape unchanged
# ---------------------------------------------------------------------------


def test_public_function_legacy_keys_preserved(tmp_path):
    _seed_step_passing(tmp_path)
    res = audit_step_literature(tmp_path, step_id="05_hub_genes")
    # All keys callers (tool_path_finalize, audit_quality_full) rely on:
    for key in (
        "status",
        "steps_audited",
        "steps_grounded",
        "steps_skipped",
        "verdict_roll_up",
        "blockers",
        "warnings",
        "per_step",
        "log_path",
    ):
        assert key in res, f"legacy key {key!r} missing from return dict"
    # New key (additive, won't break older callers).
    assert "findings" in res
    assert isinstance(res["findings"], list)


def test_unknown_step_returns_error_dict(tmp_path):
    """Public function must still surface 'error' for a missing step id."""
    from research_os.project_ops import scaffold_minimal_workspace

    scaffold_minimal_workspace(tmp_path, "Test")
    res = audit_step_literature(tmp_path, step_id="99_nope")
    assert res["status"] == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
