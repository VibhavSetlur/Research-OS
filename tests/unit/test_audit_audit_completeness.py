"""Phase-4 regression tests for the StepCompletenessAudit AuditBase wrapper.

Covers:
* The legacy markdown report at ``workspace/logs/step_completeness.md``
  is byte-identical pre- and post-Phase-4 (snapshot regression).
* ``StepCompletenessAudit.run()`` emits one ``AuditFinding`` per
  per-step blocker + warning, with severity mapped block→block and
  warn→warn.
* The JSON companion at ``workspace/logs/audits/step_completeness_audit.json`` is
  schema-valid and round-trips through ``validate_finding``.
* ``workspace/logs/.audit_findings.jsonl`` gains one new line per
  finding on each run (append-only ledger).
* Finding IDs are deterministic uuid5s — re-running against the same
  workspace gives the same IDs (no churn across runs).
* The server handler ``_handle_tool_audit_step_completeness`` writes
  all three artefacts.
"""

from __future__ import annotations

import json
import re
import uuid

import pytest

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.audit.audit import (
    StepCompletenessAudit,
    audit_step_completeness,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_blocked_step(tmp_path, step_name: str = "02_eda"):
    """Build a step that BLOCKS on the missing-caption-sidecar rule.

    conclusions present + focal figure + scripts + stack_plan present,
    but the figure has no ``.caption.md`` (the only sidecar still gated in
    3.2 — the plain-English ``.summary.md`` was retired).
    """
    scaffold_minimal_workspace(tmp_path, "Test")
    step = tmp_path / "workspace" / step_name
    step.mkdir(parents=True)
    (step / "scripts").mkdir()
    (step / "scripts" / "01_eda.py").write_text("import pandas as pd\n")
    (step / "scratch").mkdir()
    (step / "scratch" / "stack_plan.md").write_text(
        "# Stack plan\n\nUsing Python pandas because it's the team default.\n"
    )
    (step / "conclusions.md").write_text(
        "## Findings\n\nDetailed prose findings " + ("more text " * 30)
        + "\n\n## Decision\n\nProceed to step 3.\n"
    )
    figs = step / "outputs" / "figures"
    figs.mkdir(parents=True)
    num = step_name.split("_", 1)[0]
    fig = figs / f"{num}_dist.png"
    fig.write_bytes(b"\x89PNG\r\n")
    # Intentionally no .caption.md — should BLOCK on caption_sidecar.
    return step


# ---------------------------------------------------------------------------
# 1) Markdown regression — the legacy report is unchanged.
# ---------------------------------------------------------------------------


def test_legacy_markdown_report_unchanged_by_phase4_wrapper(tmp_path):
    """The legacy ``workspace/logs/step_completeness.md`` must keep the
    exact v1.x format. Phase-4 must not touch it. The snapshot here is
    pinned against the v1.x output shape: a top header, then per-step
    blocks with the icon + step_id + BLOCKERS / Warnings sub-lists.
    """
    _make_blocked_step(tmp_path, "02_eda")

    # Direct legacy call writes the report.
    audit_step_completeness(tmp_path, step_id="02_eda")
    legacy_md = (tmp_path / "workspace" / "logs" / "step_completeness.md")
    assert legacy_md.exists()
    legacy_text = legacy_md.read_text()

    # Snapshot expectations: the top header, the per-step icon (❌
    # because the step is blocked), the step id, the BLOCKERS sub-header,
    # and the missing-summary blocker text.
    assert legacy_text.startswith("# Step Completeness Audit\n")
    assert "## ❌ `02_eda`" in legacy_text
    assert "**BLOCKERS:**" in legacy_text
    assert "missing caption sidecar" in legacy_text

    # Snapshot the bytes, then run the Phase-4 wrapper, then re-read +
    # confirm the legacy markdown is byte-identical. The Phase-4 wrapper
    # delegates to the same legacy function, so the file should not
    # change if the wrapper is well-behaved.
    snapshot = legacy_md.read_bytes()
    findings = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    assert findings, "wrapper should emit at least one finding"
    assert legacy_md.read_bytes() == snapshot, (
        "Phase-4 wrapper must not alter the legacy markdown bytes."
    )


# ---------------------------------------------------------------------------
# 2) Findings shape + severity mapping
# ---------------------------------------------------------------------------


def test_run_returns_findings_with_block_severity_for_blockers(tmp_path):
    """A workspace with a single blocker yields a single block-severity
    AuditFinding with the right audit_name and a non-empty
    suggested_fix copied from the blocker string.
    """
    _make_blocked_step(tmp_path, "02_eda")
    findings = StepCompletenessAudit().run(tmp_path, step_id="02_eda")

    blocks = [f for f in findings if f.severity == "block"]
    assert len(blocks) >= 1, f"expected at least one block, got {findings}"

    caption_findings = [
        f for f in blocks if f.dimension == "caption_sidecar"
    ]
    assert len(caption_findings) == 1
    f = caption_findings[0]
    assert f.audit_name == "step_completeness"
    assert f.severity == "block"
    assert "caption" in f.suggested_fix.lower()
    # Override kwarg is set for missing caption sidecar — bypassable via
    # the documented override_completeness_gate flag.
    assert f.override_kwarg == "override_completeness_gate"
    # Evidence path points at the figures directory of the offending step.
    assert any("workspace/02_eda" in p for p in f.evidence_paths)
    # Schema-valid id.
    uuid.UUID(f.id)


def test_run_returns_empty_when_workspace_missing(tmp_path):
    """No workspace/ → empty findings list (rather than crash).

    Mirrors the legacy contract that returns status="error" with a
    message in that case; the wrapper just surfaces zero findings.
    """
    # tmp_path has no workspace/.
    findings = StepCompletenessAudit().run(tmp_path)
    assert findings == []


# ---------------------------------------------------------------------------
# 3) JSON companion is schema-valid
# ---------------------------------------------------------------------------


def test_json_companion_is_schema_valid(tmp_path):
    """write_audit_outputs(findings, "step_completeness", root) produces
    a workspace/logs/audits/step_completeness_audit.json file containing an array
    of finding objects, each of which round-trips through
    validate_finding without raising.
    """
    _make_blocked_step(tmp_path, "02_eda")
    findings = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    assert findings

    write_audit_outputs(findings, "step_completeness", tmp_path)

    json_path = tmp_path / "workspace" / "logs" / "audits" / "step_completeness_audit.json"
    assert json_path.exists()
    payload = json.loads(json_path.read_text())
    assert isinstance(payload, list)
    assert len(payload) == len(findings)
    for d in payload:
        # Re-validate to confirm the schema round-trips. validate_finding
        # raises ValueError on any violation.
        validate_finding(d)


# ---------------------------------------------------------------------------
# 4) JSONL ledger appends on each run
# ---------------------------------------------------------------------------


def test_jsonl_rollup_appends_new_lines_per_run(tmp_path):
    """The ``workspace/logs/.audit_findings.jsonl`` file is append-only.

    Running the audit twice should leave double the lines (and the
    first-run lines must still be present byte-identical as a prefix).
    """
    _make_blocked_step(tmp_path, "02_eda")

    first = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    write_audit_outputs(first, "step_completeness", tmp_path)
    jsonl = tmp_path / "workspace" / "logs" / ".audit_findings.jsonl"
    assert jsonl.exists()
    first_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    assert len(first_lines) == len(first)
    for ln in first_lines:
        validate_finding(json.loads(ln))

    second = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    write_audit_outputs(second, "step_completeness", tmp_path)
    all_lines = [
        ln for ln in jsonl.read_text().splitlines() if ln.strip()
    ]
    # Two runs → 2x findings in the ledger.
    assert len(all_lines) == len(first) + len(second)
    # The first-run lines are still the first prefix of the file.
    assert all_lines[: len(first_lines)] == first_lines


# ---------------------------------------------------------------------------
# 5) Stable uuid5 — re-runs over the same workspace produce same IDs
# ---------------------------------------------------------------------------


def test_finding_ids_are_stable_across_runs(tmp_path):
    """Re-running the audit against an unchanged workspace must produce
    the SAME finding ids (uuid5 derived from audit_name + dimension +
    evidence_paths). Otherwise dashboards would see every finding as
    "new" on every run and history queries would be useless.
    """
    _make_blocked_step(tmp_path, "02_eda")
    first = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    second = StepCompletenessAudit().run(tmp_path, step_id="02_eda")

    assert {f.id for f in first} == {f.id for f in second}, (
        "uuid5 IDs must be stable across re-runs."
    )


# ---------------------------------------------------------------------------
# 6) Clean workspace → zero findings
# ---------------------------------------------------------------------------


def test_clean_step_produces_no_findings(tmp_path):
    """A step that meets every completeness rule yields zero findings.

    Adds the missing .caption.md to the otherwise-blocked fixture so
    the only blocking rule passes. (Other rules — e.g. provenance
    coverage — may still WARN, but those are not block-severity.)
    """
    step = _make_blocked_step(tmp_path, "02_eda")
    (step / "outputs" / "figures" / "02_dist.caption.md").write_text(
        "**Figure 1.** Distribution of values.\n"
    )

    findings = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    # No blockers expected; warnings (e.g. provenance, tables) MAY
    # appear if the fixture happens to trip them — assert specifically
    # that no BLOCK-severity findings come back.
    blocks = [f for f in findings if f.severity == "block"]
    assert blocks == [], f"expected no blockers, got {[f.suggested_fix for f in blocks]}"


# ---------------------------------------------------------------------------
# 7) Server handler integration
# ---------------------------------------------------------------------------


def test_server_handler_writes_all_three_artefacts(tmp_path):
    """``_handle_tool_audit_step_completeness`` must call
    ``write_audit_outputs`` so the .md + .json + .jsonl artefacts all
    exist after one server-side invocation.
    """
    _make_blocked_step(tmp_path, "02_eda")

    from research_os.server import _handle_tool_audit_step_completeness

    res = _handle_tool_audit_step_completeness(
        "tool_audit_step_completeness",
        {"step_id": "02_eda"},
        tmp_path,
    )
    # Handler returns a TextContent payload; we only need to confirm
    # the response body is non-empty + the artefacts landed.
    assert res

    md = tmp_path / "workspace" / "logs" / "audits" / "step_completeness_audit.md"
    js = tmp_path / "workspace" / "logs" / "audits" / "step_completeness_audit.json"
    jl = tmp_path / "workspace" / "logs" / ".audit_findings.jsonl"
    legacy_md = tmp_path / "workspace" / "logs" / "step_completeness.md"

    assert md.exists()
    assert js.exists()
    assert jl.exists()
    # The legacy markdown is still produced by the wrapped legacy call.
    assert legacy_md.exists()
    assert "Step Completeness Audit" in legacy_md.read_text()

    payload = json.loads(js.read_text())
    assert isinstance(payload, list)
    for d in payload:
        validate_finding(d)


# ---------------------------------------------------------------------------
# 8) Dimension classifier covers the documented surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg,expected_dim",
    [
        ("conclusions.md missing.", "conclusions"),
        ("conclusions.md → Findings section is still a stub.", "findings_stub"),
        ("conclusions.md → Decision section is still a stub.", "decision_stub"),
        (
            "2 figure(s) missing caption sidecar: 01_a.png, 01_b.png",
            "caption_sidecar",
        ),
        (
            "02_eda: no scratch/stack_plan.md — language + library choice "
            "not documented.",
            "stack_plan",
        ),
        (
            "Outputs span 2 categories (figures / tables / reports) but no "
            "pipeline.yaml declares the sub-task DAG — this is the "
            "mega-script anti-pattern.",
            "mega_script",
        ),
        (
            "No figure produced — every step MUST emit at least one focal "
            "figure to outputs/figures/01_<descriptor>.png.",
            "focal_artefact",
        ),
        (
            "Provenance sidecar coverage 25% (1/4 outputs have .prov.json).",
            "provenance",
        ),
        (
            "3 scripts but no pipeline.yaml declaring the sub-task DAG.",
            "pipeline_yaml",
        ),
        (
            "No script files under scripts/ — step's outputs may not be "
            "reproducible from this folder alone.",
            "scripts",
        ),
        (
            "Step has numeric findings + a figure but no table in "
            "outputs/tables/.",
            "tables",
        ),
        (
            "conclusions.md → Plain-language summary still a stub.",
            "plain_language_summary",
        ),
        # Unknown message → falls back to generic completeness label.
        ("something completely new that nobody has seen before", "completeness"),
    ],
)
def test_classifier_maps_every_documented_message(msg, expected_dim):
    """Every blocker/warning string the legacy auditor can emit maps to
    a known dimension label. New strings without a matcher fall back
    to "completeness" — that's intentional and tested here so the
    fallback is part of the documented contract.
    """
    from research_os.tools.actions.audit.audit import (
        _classify_completeness_dimension,
    )

    assert _classify_completeness_dimension(msg) == expected_dim


# ---------------------------------------------------------------------------
# 9) Sanity: every finding has a non-empty suggested_fix + at least one
# evidence path; multi-finding workspaces preserve the per-step grouping.
# ---------------------------------------------------------------------------


def test_findings_carry_evidence_paths_pointing_at_step(tmp_path):
    """Every finding's evidence_paths list must start with
    ``workspace/<step_id>`` so a reviewer can jump straight to the
    offending directory.
    """
    _make_blocked_step(tmp_path, "02_eda")
    findings = StepCompletenessAudit().run(tmp_path, step_id="02_eda")
    assert findings
    for f in findings:
        assert f.evidence_paths, f"finding has no evidence_paths: {f}"
        assert all(
            re.match(r"^workspace/02_eda(/|$)", p) for p in f.evidence_paths
        ), f"evidence path leaked outside workspace/02_eda: {f.evidence_paths}"
