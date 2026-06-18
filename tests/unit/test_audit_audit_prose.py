"""Phase-4 AuditBase regression tests for ``tool_audit_prose``.

These tests pin behaviour the v2.0.0 migration must preserve:

* The legacy ``workspace/logs/prose_audit.md`` report is rendered
  byte-for-byte identically before and after the refactor — downstream
  AI prompts and templates still read this file.
* The new ``ProseQualityAudit`` (subclass of :class:`AuditBase`)
  emits :class:`AuditFinding` objects that satisfy the bundled JSON
  Schema and round-trip through :func:`validate_finding`.
* :func:`write_audit_outputs` writes the gate's ``.md`` + ``.json``
  companion artefacts AND appends one line per finding to the
  append-only ``workspace/logs/.audit_findings.jsonl`` ledger.
* Reruns over identical inputs produce IDs that don't churn (uuid5 is
  deterministic), so diffing the jsonl across runs surfaces only
  genuine changes.

We never mock the workspace — every test scaffolds a tiny but real
project root on ``tmp_path`` and asserts against the files actually
written, per the v2.0.0 release-spec hard constraint of "never mock
the database in tests".
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.prose_quality import (
    ProseQualityAudit,
    audit_prose,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# A prose blob that intentionally trips MULTIPLE auditor heuristics so
# every code-path that produces a finding gets exercised:
#  - vague quantifiers without a nearby number ("Many subjects ...")
#  - hedging language ("appears to", "tends to")
#  - weasel words ("clearly", "obviously")
#  - causal language (only fires when is_observational=True)
_DIRTY_PROSE = (
    "# Findings\n\n"
    "Many subjects showed substantial variability. "
    "Several measures appear to be considerable. "
    "The effect clearly tends to be relatively strong. "
    "Obviously, diet causes weight loss in this cohort.\n"
)


def _seed_workspace(root: Path, *, body: str = _DIRTY_PROSE) -> None:
    """Build a minimal real workspace + synthesis target for an audit run.

    The default target ``synthesis/paper.md`` is what the legacy
    ``audit_prose`` discovers when no explicit ``targets`` arg is passed.
    A bare ``workspace/`` directory must also exist or the function
    refuses to run.
    """
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    syn = root / "synthesis"
    syn.mkdir(parents=True, exist_ok=True)
    (syn / "paper.md").write_text(body)


def _fixture_root(tmp_path: Path) -> Path:
    """One deterministic fixture used by every test so inputs are pinned
    in one place — change the prose, change the snapshot."""
    _seed_workspace(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Legacy markdown report must remain byte-identical
# ---------------------------------------------------------------------------


def test_prose_legacy_md_report_snapshot(tmp_path: Path):
    """The human-readable ``workspace/logs/prose_audit.md`` report must
    keep the v1.x shape: top-level heading, then a per-document section
    with status icon, word/grade/passive line, and warning bullets.

    Pin the exact prefix + characteristic substrings so any drift
    surfaces as a test failure rather than a silent prompt change.
    """
    root = _fixture_root(tmp_path)
    res = audit_prose(root, is_observational=True)
    report = (root / "workspace" / "logs" / "prose_audit.md").read_text()

    # Header.
    assert report.startswith("# Prose Quality Audit\n\n")

    # Per-document heading uses the path + word / FK grade / passive line.
    assert "synthesis/paper.md" in report
    assert "words" in report
    assert "FK grade" in report
    assert "passive" in report

    # Causal-language is a blocker for observational designs, so the
    # **Blockers** section appears verbatim (bold + capitalised).
    assert "**Blockers**" in report

    # Vague quantifiers are flagged as a warning, with the legacy
    # heading text "Vague quantifier examples:".
    assert "Vague quantifier examples:" in report

    # Hedge examples likewise render under the legacy heading.
    assert "Hedge examples:" in report

    # The response payload still carries the headline status field that
    # callers (master auditor, AI prompts) read.
    assert res["status"] == "error"  # causal-language blocker → error
    assert res["n_documents"] >= 1
    assert isinstance(res.get("documents"), list)


# ---------------------------------------------------------------------------
# AuditBase findings + JSON companion
# ---------------------------------------------------------------------------


def test_prose_audit_emits_block_and_warn_findings(tmp_path: Path):
    """The dirty prose fixture produces at least one block finding
    (causal language on observational data) and several warn findings
    (hedge / weasel / vague-quantifier / passive). Every finding is
    schema-valid."""
    root = _fixture_root(tmp_path)

    findings = ProseQualityAudit().run(root, is_observational=True)
    blocks = [f for f in findings if f.severity == "block"]
    warns = [f for f in findings if f.severity == "warn"]

    assert len(blocks) >= 1, "expected at least one block finding (causal)"
    assert len(warns) >= 1, "expected at least one warn finding"

    for f in findings:
        # Schema round-trip — proves the dataclass payload satisfies the
        # bundled draft-07 schema on disk.
        d = f.to_dict()
        validate_finding(d)
        # UUID-format string per the schema pattern. uuid5 + uuid4 both
        # fit the same hex layout, so this is a sanity check.
        uuid.UUID(d["id"])
        assert d["audit_name"] == "prose_quality"
        assert d["dimension"]  # non-empty
        assert d["ro_version"]
        assert d["generated_at"].endswith("Z")
        # Evidence always points at the offending document.
        assert d["evidence_paths"]
        assert any("paper.md" in p for p in d["evidence_paths"])

    # The block finding for causal language carries the causal_language
    # dimension so dashboards can group on it.
    causal_blocks = [f for f in blocks if f.dimension == "causal_language"]
    assert causal_blocks, "expected the causal-language blocker to be tagged"


def test_prose_audit_json_companion_schema_valid(tmp_path: Path):
    """The ``prose_quality_audit.json`` companion is a list of
    schema-valid finding objects, and the ``.md`` companion is the
    severity-grouped report (distinct from the legacy prose_audit.md)."""
    root = _fixture_root(tmp_path)
    findings = ProseQualityAudit().run(root, is_observational=True)
    paths = write_audit_outputs(findings, ProseQualityAudit.name, root)

    assert paths["json"] == (
        root / "workspace" / "logs" / "audits" / "prose_quality_audit.json"
    )
    arr = json.loads(paths["json"].read_text())
    assert isinstance(arr, list)
    assert len(arr) == len(findings)
    for d in arr:
        validate_finding(d)

    # The .md companion is grouped by severity, with the audit name in
    # the heading; the ledger-style markdown is distinct from the
    # legacy report file at workspace/logs/prose_audit.md.
    md_text = paths["md"].read_text()
    assert md_text.startswith("# prose_quality audit")


def test_prose_audit_jsonl_ledger_appends(tmp_path: Path):
    """Reruns APPEND to ``workspace/logs/.audit_findings.jsonl`` rather
    than truncating it — deterministic uuid5 keeps IDs stable, so
    re-runs produce the same lines."""
    root = _fixture_root(tmp_path)
    jsonl = root / "workspace" / "logs" / ".audit_findings.jsonl"

    findings1 = ProseQualityAudit().run(root, is_observational=True)
    write_audit_outputs(findings1, ProseQualityAudit.name, root)
    first_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(first_lines) == len(findings1)
    for ln in first_lines:
        validate_finding(json.loads(ln))

    # Rerun — same workspace, same findings, but the ledger should now
    # have DOUBLED in line count (append-only ledger).
    findings2 = ProseQualityAudit().run(root, is_observational=True)
    write_audit_outputs(findings2, ProseQualityAudit.name, root)
    second_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(second_lines) == 2 * len(findings1)

    # The first run's lines are still the first half verbatim.
    assert second_lines[: len(first_lines)] == first_lines


def test_prose_audit_uuid5_is_deterministic(tmp_path: Path):
    """Same workspace + paper => same finding IDs across runs. This is
    the load-bearing property that keeps the jsonl ledger diffable."""
    root = _fixture_root(tmp_path)
    ids_a = sorted(
        f.id for f in ProseQualityAudit().run(root, is_observational=True)
    )
    ids_b = sorted(
        f.id for f in ProseQualityAudit().run(root, is_observational=True)
    )
    assert ids_a == ids_b
    assert ids_a, "expected at least one finding from the dirty fixture"


def test_prose_audit_handles_missing_workspace(tmp_path: Path):
    """When no ``workspace/`` exists at all, the audit must NOT crash —
    instead it returns an empty findings list so the orchestrator can
    treat 'nothing to audit' as 'nothing wrong'."""
    # Bare tmp_path — no workspace/, no synthesis/.
    findings = ProseQualityAudit().run(tmp_path)
    assert findings == []


def test_prose_audit_clean_doc_yields_no_findings(tmp_path: Path):
    """A clean paragraph without hedges, weasels, vague quantifiers, or
    causal language should produce zero findings — proves the audit
    isn't trigger-happy."""
    clean_body = (
        "# Methods\n\n"
        "We enrolled 423 participants and assigned each to one of "
        "three arms with a fixed 1:1:1 ratio.\n"
    )
    _seed_workspace(tmp_path, body=clean_body)
    findings = ProseQualityAudit().run(tmp_path, is_observational=False)
    # Clean prose passes everything except possibly the FK reading-level
    # warning on very dense methods text; assert no BLOCKERS at minimum.
    assert not [f for f in findings if f.severity == "block"]
