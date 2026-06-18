"""Phase-4 tests for the AuditBase migration of ``audit_reviewer_responses``.

Three invariants the migration must preserve:

1. The legacy markdown report at ``workspace/reviewer/audit_report.md``
   is byte-for-byte unchanged (modulo the run-time timestamp on line 2)
   so existing usability snapshots + the ``test_audit_writes_report``
   regression in ``test_reviewer.py`` keep passing.

2. The v2 JSON companion at
   ``workspace/logs/audits/audit_reviewer_responses_audit.json`` is schema-valid
   and re-parses into ``AuditFinding`` objects.

3. The ``.audit_findings.jsonl`` ledger at ``workspace/logs/`` grows
   on every run (append-only), and finding IDs are deterministic across
   re-runs on identical inputs (uuid5).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import validate_finding
from research_os.tools.actions.synthesis.reviewer import (
    ReviewerResponsesAudit,
    audit_reviewer_responses,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Bare project root — the audit creates its own workspace tree."""
    return tmp_path


def _write_rebuttal(project: Path, name: str, body: str) -> Path:
    out = project / "workspace" / "reviewer" / "rebuttals" / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out


# A rebuttal with one of each issue: hand-waving + no-evidence + scaffold-stale.
_PROBLEM_REBUTTAL = (
    "# Rebuttal — Statistician\n\n"
    "## Reviewer comment\n> Effect lacks CI.\n\n"
    "## Response\nWe believe the result is robust.\n\n"
    "## Evidence\nWARNING: paths do not exist on disk.\n"
)

# A clean rebuttal that should produce zero findings.
_CLEAN_REBUTTAL = (
    "# Rebuttal — Statistician\n\n"
    "## Reviewer comment\n> Effect lacks CI.\n\n"
    "## Response\nWe agree. Revised Results report 95% CI; see "
    "`workspace/methods.md`.\n\n"
    "## Evidence\n- `workspace/methods.md`\n"
)


# ---------------------------------------------------------------------------
# Invariant 1 — legacy markdown report shape unchanged
# ---------------------------------------------------------------------------


def _strip_timestamp(md: str) -> str:
    """Remove the ``_Audited <iso>_`` line so two runs compare equal."""
    return re.sub(r"^_Audited [^_]+_$", "_Audited <ts>_", md, flags=re.MULTILINE)


def test_legacy_markdown_report_format_preserved(project: Path) -> None:
    """The audit_report.md format must match the pre-migration v1 output exactly.

    The pre-migration writer produced a header, three counts, and an
    optional Findings section. This snapshot pins that contract.
    """
    _write_rebuttal(project, "stat_handwave", _PROBLEM_REBUTTAL)
    audit_reviewer_responses(project)

    report = (project / "workspace" / "reviewer" / "audit_report.md").read_text()

    # Header + counts (timestamps masked).
    expected_head = (
        "# Reviewer-response audit\n\n"
        "_Audited <ts>_\n\n"
        "- rebuttals audited: 1\n"
        "- passed: 0\n"
        "- failed: 1\n"
    )
    assert _strip_timestamp(report).startswith(expected_head)

    # Findings section present, listing the rebuttal + its issues.
    assert "## Findings" in report
    assert "### workspace/reviewer/rebuttals/stat_handwave.md" in report
    assert "hand-waving language detected" in report
    assert "no evidence path cited" in report
    assert "supplied evidence path missing" in report


def test_legacy_markdown_report_clean_run(project: Path) -> None:
    """A passing rebuttal still produces the header without a Findings section."""
    _write_rebuttal(project, "stat_clean", _CLEAN_REBUTTAL)
    audit_reviewer_responses(project)
    report = (project / "workspace" / "reviewer" / "audit_report.md").read_text()
    masked = _strip_timestamp(report)

    assert masked.startswith(
        "# Reviewer-response audit\n\n"
        "_Audited <ts>_\n\n"
        "- rebuttals audited: 1\n"
        "- passed: 1\n"
        "- failed: 0\n"
    )
    assert "## Findings" not in report


# ---------------------------------------------------------------------------
# Invariant 2 — v2 JSON companion is schema-valid
# ---------------------------------------------------------------------------


def test_v2_json_companion_is_schema_valid(project: Path) -> None:
    """Every entry in the audit JSON file round-trips through validate_finding."""
    _write_rebuttal(project, "stat_handwave", _PROBLEM_REBUTTAL)
    audit_reviewer_responses(project)

    json_path = project / "workspace" / "logs" / "audits" / "audit_reviewer_responses_audit.json"
    assert json_path.exists(), "v2 JSON companion not written"

    payload = json.loads(json_path.read_text())
    assert isinstance(payload, list)
    assert len(payload) >= 3  # hand-waving + no-evidence + stale-warning

    for entry in payload:
        # Re-validates against the audit_finding schema.
        f = validate_finding(entry)
        assert f.audit_name == "audit_reviewer_responses"
        assert f.severity in ("block", "warn", "info")
        assert f.evidence_paths  # every finding cites the rebuttal


def test_v2_md_companion_written(project: Path) -> None:
    """The v2 markdown companion is also written next to the JSON."""
    _write_rebuttal(project, "stat_clean", _CLEAN_REBUTTAL)
    audit_reviewer_responses(project)
    md_path = project / "workspace" / "logs" / "audits" / "audit_reviewer_responses_audit.md"
    assert md_path.exists()
    assert "audit_reviewer_responses audit" in md_path.read_text()


def test_v2_outputs_written_even_with_no_rebuttals(project: Path) -> None:
    """Empty-rebuttals case still writes the v2 artefacts (empty list)."""
    audit_reviewer_responses(project)
    json_path = project / "workspace" / "logs" / "audits" / "audit_reviewer_responses_audit.json"
    assert json_path.exists()
    assert json.loads(json_path.read_text()) == []


# ---------------------------------------------------------------------------
# Invariant 3 — .audit_findings.jsonl rolls up, IDs are deterministic
# ---------------------------------------------------------------------------


def test_jsonl_rollup_appends_new_lines(project: Path) -> None:
    """Each run appends a one-JSON-per-line entry to the ledger."""
    _write_rebuttal(project, "stat_handwave", _PROBLEM_REBUTTAL)

    audit_reviewer_responses(project)
    jsonl_path = project / "workspace" / "logs" / ".audit_findings.jsonl"
    first_run_lines = jsonl_path.read_text().splitlines()
    assert len(first_run_lines) >= 3

    # Re-run; the ledger should grow (append-only).
    audit_reviewer_responses(project)
    second_run_lines = jsonl_path.read_text().splitlines()
    assert len(second_run_lines) == 2 * len(first_run_lines)


def test_finding_ids_are_deterministic_across_runs(project: Path) -> None:
    """uuid5-based IDs mean re-runs on unchanged rebuttals yield the same IDs."""
    _write_rebuttal(project, "stat_handwave", _PROBLEM_REBUTTAL)

    a = ReviewerResponsesAudit().run(project)
    b = ReviewerResponsesAudit().run(project)

    ids_a = sorted(f.id for f in a)
    ids_b = sorted(f.id for f in b)
    assert ids_a == ids_b
    # And each id is a valid UUID hex string.
    for fid in ids_a:
        uuid.UUID(fid)  # raises on malformed


def test_finding_ids_differ_per_dimension(project: Path) -> None:
    """The same rebuttal triggering multiple checks yields distinct IDs per check."""
    _write_rebuttal(project, "stat_handwave", _PROBLEM_REBUTTAL)
    findings = ReviewerResponsesAudit().run(project)
    ids = [f.id for f in findings]
    assert len(ids) == len(set(ids)), "duplicate finding IDs across dimensions"
