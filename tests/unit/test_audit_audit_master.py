"""Phase-4 tests for the ``AuditMaster`` AuditBase wrapper.

These tests pin three guarantees the v2 migration must hold:

1. **Markdown regression** — the legacy ``workspace/logs/audit_master.md``
   output of ``audit_quality_full`` is byte-for-byte stable across the
   refactor. The whole point of keeping the legacy function intact is
   that ``tool_synthesis_check`` parses this file; any drift would
   silently break that caller.
2. **JSON companion is schema-valid** — every ``AuditFinding`` written
   to ``workspace/logs/audits/audit_master_audit.json`` round-trips through the
   audit_finding JSON Schema.
3. **JSONL roll-up gets new lines** — ``write_audit_outputs`` APPENDS
   to ``workspace/logs/.audit_findings.jsonl`` on each run so the
   historical ledger across reruns survives. Re-running on the same
   fixture must add exactly as many lines as findings emitted, leaving
   the prior lines untouched.

Stable-uuid sanity is also checked: re-running over an unchanged
fixture yields the same finding ids, so downstream deduplicators
keyed on id behave.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.audit import (
    AuditMaster,
    audit_quality_full,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def passing_root(tmp_path: Path) -> Path:
    """Minimal valid project where every gate passes cleanly.

    Bare ``workspace/`` with no active steps + no synthesis target is
    the canonical "fresh project, just initialised" state. Every
    quality gate either passes (no steps to fail) or returns a
    warning (no preregistration yet) — but no blockers.
    """
    (tmp_path / "workspace").mkdir()
    return tmp_path


@pytest.fixture
def blocking_root(tmp_path: Path) -> Path:
    """Project with a step that's missing pieces — triggers blockers.

    Designed to exercise BOTH the block-finding and info-finding
    branches of ``AuditMaster.run``: step_completeness fails (no
    figure, stub conclusions) while code_quality + prose + grounding
    pass cleanly. ``preregistration_diff`` produces a warning the
    aggregator silently records.
    """
    ws = tmp_path / "workspace"
    step = ws / "01_eda"
    (step / "outputs" / "figures").mkdir(parents=True)
    (step / "scripts").mkdir(parents=True)
    (step / "conclusions.md").write_text("# Notes\n\n_TBD_\n")
    return tmp_path


# ---------------------------------------------------------------------------
# 1) Markdown regression — legacy aggregator output must stay byte-stable.
# ---------------------------------------------------------------------------


def test_legacy_markdown_path_and_format_preserved(passing_root: Path) -> None:
    """The aggregator must still write the legacy md to the legacy path."""
    res = audit_quality_full(passing_root, skip=["claims"])
    md_path = passing_root / "workspace" / "logs" / "audit_master.md"
    assert md_path.exists(), "legacy md path moved"

    body = md_path.read_text()
    # Header is exactly what tool_synthesis_check parses for.
    assert body.startswith("# Master quality audit"), body[:80]
    # Each known component shows up as a level-2 section.
    for comp in (
        "## ✅ step_completeness",
        "## ✅ code_quality",
        "## ✅ prose_quality",
        "## ⚠️ preregistration_diff",
        "## ✅ grounding",
    ):
        assert comp in body, f"missing legacy section {comp!r}"

    # And the API shape the handler returns is unchanged.
    assert res["status"] == "success"
    assert res["report_path"] == "workspace/logs/audit_master.md"
    assert isinstance(res["components"], dict)
    assert isinstance(res["blockers"], list)


def test_legacy_markdown_byte_identical_with_and_without_v2(
    passing_root: Path,
) -> None:
    """Running ``AuditMaster`` on top must not perturb the legacy md file."""
    legacy = audit_quality_full(passing_root, skip=["claims"])
    md_path = passing_root / "workspace" / "logs" / "audit_master.md"
    snapshot_before = md_path.read_text()

    # Fan out structured findings via the v2 writer — using the
    # already-computed legacy_result so the aggregator does NOT rerun.
    AuditMaster().run(passing_root, legacy_result=legacy)

    # Legacy file is untouched; v2 writes go to workspace/audit_master_audit.*.
    assert md_path.read_text() == snapshot_before


# ---------------------------------------------------------------------------
# 2) JSON companion is schema-valid.
# ---------------------------------------------------------------------------


def test_v2_json_companion_round_trips_through_schema(
    blocking_root: Path,
) -> None:
    """Every written finding must validate against the audit_finding schema."""
    legacy = audit_quality_full(blocking_root, skip=["claims"])
    audit = AuditMaster()
    findings = audit.run(blocking_root, legacy_result=legacy)
    assert findings, "blocking_root must produce findings"

    paths = write_audit_outputs(findings, audit.name, blocking_root)
    json_path = paths["json"]
    assert json_path == blocking_root / "workspace" / "logs" / "audits" / "audit_master_audit.json"

    arr = json.loads(json_path.read_text())
    assert isinstance(arr, list) and len(arr) == len(findings)
    for d in arr:
        # Round-trip through the schema; raises if any field is bad.
        validate_finding(d)
        assert d["audit_name"] == "audit_master"
        assert d["severity"] in ("block", "warn", "info")
        assert d["override_kwarg"] == "override_completeness_gate"


def test_v2_md_companion_has_severity_grouping(
    blocking_root: Path,
) -> None:
    """The v2 markdown groups by severity with block first."""
    legacy = audit_quality_full(blocking_root, skip=["claims"])
    audit = AuditMaster()
    findings = audit.run(blocking_root, legacy_result=legacy)
    paths = write_audit_outputs(findings, audit.name, blocking_root)

    md = paths["md"].read_text()
    assert md.startswith("# audit_master audit")
    # blocking_root produces ≥1 block finding from step_completeness.
    assert "block (" in md
    # Info findings cover the gates that passed.
    assert "info (" in md
    # Block section appears before info section.
    assert md.index("block (") < md.index("info (")


# ---------------------------------------------------------------------------
# 3) JSONL roll-up gets new lines on each run.
# ---------------------------------------------------------------------------


def test_jsonl_rollup_appends_on_each_run(blocking_root: Path) -> None:
    """``.audit_findings.jsonl`` must grow on every rerun, never truncate."""
    legacy = audit_quality_full(blocking_root, skip=["claims"])
    audit = AuditMaster()
    findings_first = audit.run(blocking_root, legacy_result=legacy)
    write_audit_outputs(findings_first, audit.name, blocking_root)

    jsonl_path = blocking_root / "workspace" / "logs" / ".audit_findings.jsonl"
    first_lines = [
        ln for ln in jsonl_path.read_text().splitlines() if ln.strip()
    ]
    assert len(first_lines) == len(findings_first)
    # Every line is schema-valid JSON.
    for ln in first_lines:
        validate_finding(json.loads(ln))

    # Second run on the same fixture. Aggregator output is identical, so
    # the stable-uuid finding ids match the first run — but the JSONL
    # writer still APPENDS, preserving the historical record.
    legacy2 = audit_quality_full(blocking_root, skip=["claims"])
    findings_second = audit.run(blocking_root, legacy_result=legacy2)
    write_audit_outputs(findings_second, audit.name, blocking_root)

    second_lines = [
        ln for ln in jsonl_path.read_text().splitlines() if ln.strip()
    ]
    assert len(second_lines) == len(first_lines) + len(findings_second)
    # The first N lines are byte-identical to the first run.
    assert second_lines[: len(first_lines)] == first_lines


# ---------------------------------------------------------------------------
# Stable uuid invariants.
# ---------------------------------------------------------------------------


def test_finding_ids_are_stable_across_reruns(blocking_root: Path) -> None:
    """uuid5(NAMESPACE_DNS, audit_name|dimension|paths|extra) → same on rerun."""
    legacy_a = audit_quality_full(blocking_root, skip=["claims"])
    a = AuditMaster().run(blocking_root, legacy_result=legacy_a)
    legacy_b = audit_quality_full(blocking_root, skip=["claims"])
    b = AuditMaster().run(blocking_root, legacy_result=legacy_b)

    assert [f.id for f in a] == [f.id for f in b], (
        "stable-uuid contract broken — reruns must produce the same finding ids"
    )


def test_passing_project_emits_only_info_findings(passing_root: Path) -> None:
    """A fresh project with no failures emits info findings only (no blockers)."""
    legacy = audit_quality_full(passing_root, skip=["claims"])
    findings = AuditMaster().run(passing_root, legacy_result=legacy)
    assert findings, "every active component should emit an info finding"
    severities = {f.severity for f in findings}
    assert severities <= {"info", "warn"}, severities
    assert "block" not in severities
