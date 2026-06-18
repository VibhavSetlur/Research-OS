"""Tests for the audit-finding schema, dataclass, and writer.

Covers:
* schema validation accepts a well-formed finding + rejects bad ones
  (missing required field, bad severity enum, malformed uuid)
* write_audit_outputs writes the .md, .json, and .jsonl artefacts
* idempotent re-run rewrites .md + .json but APPENDS to the .jsonl
"""

from __future__ import annotations

import json
import uuid

import pytest

from research_os.tools.actions.audit._base import (
    AuditBase,
    AuditFinding,
    validate_finding,
    write_audit_outputs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path):
    """Bare project root with no preseeded workspace — writer creates dirs."""
    return tmp_path


def _good_finding_dict() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "audit_name": "step_completeness",
        "severity": "block",
        "dimension": "completeness",
        "evidence_paths": ["workspace/01_eda/conclusions.md"],
        "suggested_fix": "Fill in the Findings section with quantitative bullets.",
        "override_kwarg": "override_completeness_gate",
        "override_log_format": "OVERRIDE completeness by user — rationale: {rationale}",
        "generated_at": "2026-06-05T12:00:00Z",
        "ro_version": "2.0.0-dev",
    }


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_validate_finding_accepts_good_payload():
    d = _good_finding_dict()
    f = validate_finding(d)
    assert isinstance(f, AuditFinding)
    assert f.audit_name == "step_completeness"
    assert f.severity == "block"
    assert f.evidence_paths == ["workspace/01_eda/conclusions.md"]


def test_validate_finding_rejects_missing_required_field():
    d = _good_finding_dict()
    del d["dimension"]
    with pytest.raises(ValueError, match="dimension"):
        validate_finding(d)


def test_validate_finding_rejects_bad_severity():
    d = _good_finding_dict()
    d["severity"] = "critical"  # not in enum
    with pytest.raises(ValueError):
        validate_finding(d)


def test_validate_finding_rejects_malformed_uuid():
    d = _good_finding_dict()
    d["id"] = "not-a-uuid"
    with pytest.raises(ValueError):
        validate_finding(d)


def test_audit_finding_factory_validates():
    f = AuditFinding.new(
        audit_name="prose_quality",
        severity="warn",
        dimension="prose",
        evidence_paths=["synthesis/paper.md"],
        suggested_fix="Reduce hedging language.",
    )
    assert f.severity == "warn"
    # Auto-populated fields look sensible.
    uuid.UUID(f.id)
    assert f.ro_version
    assert f.generated_at.endswith("Z")


def test_audit_finding_factory_rejects_bad_severity():
    with pytest.raises(ValueError):
        AuditFinding.new(
            audit_name="x", severity="catastrophic", dimension="prose"
        )


# ---------------------------------------------------------------------------
# write_audit_outputs
# ---------------------------------------------------------------------------


def _findings_pair() -> list[AuditFinding]:
    return [
        AuditFinding.new(
            audit_name="step_completeness",
            severity="block",
            dimension="completeness",
            evidence_paths=["workspace/01_eda/conclusions.md"],
            suggested_fix="Fill in Findings.",
            override_kwarg="override_completeness_gate",
            override_log_format="override by {user}",
        ),
        AuditFinding.new(
            audit_name="step_completeness",
            severity="warn",
            dimension="completeness",
            evidence_paths=["workspace/02_eda/conclusions.md"],
            suggested_fix="Add plain-language summary.",
        ),
    ]


def test_write_audit_outputs_writes_all_three(project_root):
    findings = _findings_pair()
    paths = write_audit_outputs(findings, "completeness", project_root)

    md = paths["md"]
    js = paths["json"]
    jl = paths["jsonl"]
    assert md.exists() and js.exists() and jl.exists()
    assert md == project_root / "workspace" / "logs" / "audits" / "completeness_audit.md"
    assert js == project_root / "workspace" / "logs" / "audits" / "completeness_audit.json"
    assert jl == project_root / "workspace" / "logs" / ".audit_findings.jsonl"

    # Markdown is grouped by severity (block first).
    md_text = md.read_text()
    assert "# completeness audit" in md_text
    assert "block (1)" in md_text
    assert "warn (1)" in md_text
    # Block section appears before warn section.
    assert md_text.index("block (1)") < md_text.index("warn (1)")

    # JSON is schema-valid + round-trips.
    arr = json.loads(js.read_text())
    assert isinstance(arr, list) and len(arr) == 2
    for d in arr:
        validate_finding(d)

    # JSONL has one line per finding.
    lines = [ln for ln in jl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        validate_finding(json.loads(line))


def test_write_audit_outputs_empty_findings_still_writes(project_root):
    paths = write_audit_outputs([], "completeness", project_root)
    md_text = paths["md"].read_text()
    assert "No findings" in md_text
    assert json.loads(paths["json"].read_text()) == []
    # The jsonl file is created by mkdir + open('a'), and gets no content
    # for an empty findings list — but the file must exist for subsequent
    # appends. open('a') creates it implicitly when we enter the loop;
    # with zero findings the file may not be touched, which is fine —
    # writers append rather than truncate, so a missing file is created
    # on first non-empty write.
    # We only assert what we can: md + json are present.
    assert paths["md"].exists()
    assert paths["json"].exists()


def test_write_audit_outputs_idempotent_md_json_appending_jsonl(project_root):
    # First run.
    first = _findings_pair()
    write_audit_outputs(first, "completeness", project_root)
    jl = project_root / "workspace" / "logs" / ".audit_findings.jsonl"
    js = project_root / "workspace" / "logs" / "audits" / "completeness_audit.json"
    md = project_root / "workspace" / "logs" / "audits" / "completeness_audit.md"

    first_md = md.read_text()
    first_json = json.loads(js.read_text())
    first_jsonl_lines = [
        ln for ln in jl.read_text().splitlines() if ln.strip()
    ]
    assert len(first_jsonl_lines) == 2
    assert len(first_json) == 2

    # Second run with fresh findings (different ids).
    second = _findings_pair()
    assert {f.id for f in second}.isdisjoint({d["id"] for d in first_json})

    write_audit_outputs(second, "completeness", project_root)

    # md + json reflect ONLY the second run — they were rewritten.
    second_json = json.loads(js.read_text())
    assert len(second_json) == 2
    assert {d["id"] for d in second_json} == {f.id for f in second}
    second_md = md.read_text()
    assert second_md != first_md  # different ids in headings

    # jsonl APPENDED — now contains 4 lines (2 from first + 2 from second).
    second_jsonl_lines = [
        ln for ln in jl.read_text().splitlines() if ln.strip()
    ]
    assert len(second_jsonl_lines) == 4

    # The original two lines are still the first two lines verbatim.
    assert second_jsonl_lines[:2] == first_jsonl_lines

    # Every line still validates.
    for ln in second_jsonl_lines:
        validate_finding(json.loads(ln))


# ---------------------------------------------------------------------------
# AuditBase contract
# ---------------------------------------------------------------------------


def test_auditbase_is_abstract():
    # Direct instantiation should fail because `run` is abstract.
    with pytest.raises(TypeError):
        AuditBase()  # type: ignore[abstract]


def test_auditbase_subclass_can_run_and_writer_persists(project_root):
    class _SimpleAudit(AuditBase):
        name = "simple"

        def run(self, root, **kwargs):
            return [
                AuditFinding.new(
                    audit_name=self.name,
                    severity="info",
                    dimension="demo",
                    evidence_paths=["x.md"],
                    suggested_fix="nothing",
                )
            ]

    audit = _SimpleAudit()
    findings = audit.run(project_root)
    assert len(findings) == 1
    paths = write_audit_outputs(findings, "simple", project_root)
    arr = json.loads(paths["json"].read_text())
    assert arr[0]["audit_name"] == "simple"
    assert arr[0]["severity"] == "info"
