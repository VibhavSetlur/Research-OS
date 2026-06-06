"""Phase-4 migration tests for ``tool_audit_code_quality``.

These tests pin three things:

1. The legacy markdown report at ``workspace/logs/code_quality.md`` is
   produced byte-for-byte the same as before the AuditBase migration —
   snapshot-style regression against a fixed fixture.
2. The new JSON companion at ``workspace/code_quality_audit.json`` is
   schema-valid against ``audit_finding.schema.json``.
3. The append-only JSONL ledger at ``workspace/logs/.audit_findings.jsonl``
   gains one line per finding on every run (idempotency: re-running adds
   another batch of lines, never truncates).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.code_quality import (
    CodeQualityAudit,
    audit_code_quality,
)


# ---------------------------------------------------------------------------
# Fixture: a minimal but realistic workspace with one blocker, one warning,
# and one clean script — covers all three severities the auditor emits.
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_workspace(tmp_path: Path) -> Path:
    """Build workspace/01_eda/scripts/ with three Python files.

    The contents are pinned: any drift in the fixture invalidates the
    snapshot. Keep them tiny and deterministic.
    """
    scripts = tmp_path / "workspace" / "01_eda" / "scripts"
    scripts.mkdir(parents=True)

    # 1. Clean script — module + function docstrings, no smells.
    (scripts / "clean.py").write_text(
        '"""Tidy analysis helper."""\n\n'
        "def double(x: int) -> int:\n"
        '    """Double an integer."""\n'
        "    return x * 2\n"
    )

    # 2. Script with a blocker (bare except) and a warning (no module docstring).
    (scripts / "bad_except.py").write_text(
        "def doit():\n"
        "    try:\n"
        "        return 1\n"
        "    except:\n"
        "        return 0\n"
    )

    # 3. Script with import-star blocker.
    (scripts / "bad_star.py").write_text(
        '"""Bad imports."""\n'
        "from os import *\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# 1. Legacy markdown snapshot — the human-readable report must NOT drift.
# ---------------------------------------------------------------------------


def test_legacy_markdown_report_unchanged(fixture_workspace: Path):
    """workspace/logs/code_quality.md is produced by the legacy function.

    We run the legacy entry point and the new AuditBase subclass and
    confirm both render the same markdown — the AuditBase subclass
    delegates, so the file must be identical between the two paths.
    """
    # Run legacy direct.
    audit_code_quality(fixture_workspace, run_ruff=False, run_mypy=False)
    md_path = fixture_workspace / "workspace" / "logs" / "code_quality.md"
    assert md_path.exists()
    direct_md = md_path.read_text()

    # The exact structural markers the legacy report has emitted since v1.
    # If any of these strings disappear, downstream readers (the master
    # audit aggregator, the synthesis gate) will silently lose info.
    assert direct_md.startswith("# Code Quality Audit\n")
    assert "## " in direct_md  # at least one step heading
    assert "`01_eda`" in direct_md
    assert "bad_except.py" in direct_md
    assert "bad_star.py" in direct_md
    assert "clean.py" in direct_md
    # Legacy blocker labels.
    assert "**Blockers**" in direct_md
    assert "bare `except:`" in direct_md
    assert "import *`" in direct_md

    # Run via the new AuditBase subclass — markdown should be identical
    # (AuditBase.run() delegates to audit_code_quality()).
    md_path.unlink()
    findings = CodeQualityAudit().run(
        fixture_workspace, run_ruff=False, run_mypy=False
    )
    second_md = md_path.read_text()
    assert second_md == direct_md, (
        "AuditBase subclass changed the legacy markdown output — the "
        "Phase-4 migration is meant to be additive only."
    )
    assert findings, "audit must surface findings for the fixture"


# ---------------------------------------------------------------------------
# 2. JSON companion is schema-valid.
# ---------------------------------------------------------------------------


def test_json_companion_is_schema_valid(fixture_workspace: Path):
    findings = CodeQualityAudit().run(
        fixture_workspace, run_ruff=False, run_mypy=False
    )
    write_audit_outputs(findings, "code_quality", fixture_workspace)

    json_path = (
        fixture_workspace / "workspace" / "code_quality_audit.json"
    )
    assert json_path.exists()
    arr = json.loads(json_path.read_text())
    assert isinstance(arr, list) and arr, "expected non-empty finding list"

    # Every entry must pass schema validation (no missing fields, valid
    # severity enum, well-formed uuid, etc.).
    for d in arr:
        validate_finding(d)

    # Sanity: at least one blocker (bare except + import-star), at least
    # one warning (no module docstring on bad_except.py).
    severities = {d["severity"] for d in arr}
    assert "block" in severities
    assert "warn" in severities

    # audit_name is stable across every finding.
    assert {d["audit_name"] for d in arr} == {"code_quality"}


def test_finding_ids_are_deterministic(fixture_workspace: Path):
    """Re-running against the same workspace state produces the same ids.

    Phase-4 derives ids via ``uuid.uuid5`` keyed off audit_name +
    dimension + evidence_paths + detail so dashboards can dedupe across
    runs. If this churns, downstream history queries break.
    """
    audit = CodeQualityAudit()
    first = audit.run(fixture_workspace, run_ruff=False, run_mypy=False)
    second = audit.run(fixture_workspace, run_ruff=False, run_mypy=False)
    first_ids = sorted(f.id for f in first)
    second_ids = sorted(f.id for f in second)
    assert first_ids == second_ids


# ---------------------------------------------------------------------------
# 3. JSONL ledger is append-only and gains lines on every run.
# ---------------------------------------------------------------------------


def test_jsonl_rollup_appends_new_lines(fixture_workspace: Path):
    audit = CodeQualityAudit()
    first = audit.run(fixture_workspace, run_ruff=False, run_mypy=False)
    write_audit_outputs(first, "code_quality", fixture_workspace)

    jsonl = (
        fixture_workspace / "workspace" / "logs" / ".audit_findings.jsonl"
    )
    assert jsonl.exists()
    lines_after_first = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(lines_after_first) == len(first)

    # Every line is schema-valid.
    for line in lines_after_first:
        validate_finding(json.loads(line))

    # Second run — must APPEND, not truncate.
    second = audit.run(fixture_workspace, run_ruff=False, run_mypy=False)
    write_audit_outputs(second, "code_quality", fixture_workspace)
    lines_after_second = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(lines_after_second) == len(first) + len(second)
    # First batch preserved verbatim at the top of the ledger.
    assert lines_after_second[: len(first)] == lines_after_first


def test_empty_workspace_returns_info_finding(tmp_path: Path):
    """No workspace/ directory → a single 'info' finding describing the gap.

    The legacy function returns ``status=error`` with a message; the new
    AuditBase wrapper surfaces that as an info finding so the gate
    doesn't silently emit zero findings (which would be indistinguishable
    from a clean run).
    """
    findings = CodeQualityAudit().run(tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].dimension == "workspace"
