"""Phase-4b regression tests for tool_audit_figure_coverage.

Covers the AuditBase migration:

* The Phase-4 ``FigureCoverageAudit`` subclass emits structured
  :class:`AuditFinding` objects with deterministic UUIDs (same workspace
  state → same finding IDs on rerun).
* The legacy dict surface returned by ``audit_figure_coverage`` is
  preserved byte-for-byte so existing tests + protocols keep working.
* ``write_audit_outputs`` lays down the three Phase-4 artefacts
  (``workspace/figure_coverage_audit.md``, ``.json``,
  ``workspace/logs/.audit_findings.jsonl``).
* The JSON companion validates against
  ``audit_finding.schema.json``.
* The JSONL ledger gets appended on every rerun (history is preserved,
  not truncated).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.tools.actions.audit._base import (
    validate_finding,
    write_audit_outputs,
)
from research_os.tools.actions.synthesis.figure_auto_embed import (
    FigureCoverageAudit,
    audit_figure_coverage,
)


# ---------------------------------------------------------------------------
# Fixture helpers — mirror the existing test_figure_auto_embed helpers but
# stay self-contained so the v2 suite isn't coupled to the v1 file.
# ---------------------------------------------------------------------------


_PAPER_SKELETON = """# Title

## Abstract

Abstract body.

## Introduction

Intro body.

## Methods

Methods body.

## Results

Results body.

## Discussion

Discussion body.
"""


def _make_step(root: Path, step_id: str, figures: list[tuple[str, str, bool]]) -> None:
    """Create a numbered step dir with given (stem, caption, embed_flag)."""
    step = root / "workspace" / step_id
    fig_dir = step / "outputs" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for stem, caption, for_paper in figures:
        (fig_dir / f"{stem}.png").write_bytes(b"\x89PNG fake")
        fm = "---\n" f"figures_for_paper: {'true' if for_paper else 'false'}\n" "---\n"
        (fig_dir / f"{stem}.caption.md").write_text(fm + caption + "\n")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A fresh project root with no figures + no paper.md yet."""
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Structured findings + deterministic IDs
# ---------------------------------------------------------------------------


def test_audit_emits_block_finding_per_orphan_figure(project_root: Path) -> None:
    _make_step(project_root, "01_eda", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    findings = FigureCoverageAudit().run(project_root)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "block"
    assert f.dimension == "figures"
    assert f.audit_name == "audit_figure_coverage"
    assert "synthesis/paper.md" in f.evidence_paths
    assert any("vol" in ep for ep in f.evidence_paths)


def test_audit_returns_no_findings_when_paper_embeds_every_figure(
    project_root: Path,
) -> None:
    _make_step(project_root, "01_eda", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON + "\n![](workspace/01_eda/outputs/figures/vol.png)\n")

    findings = FigureCoverageAudit().run(project_root)
    assert findings == []


def test_audit_blocks_when_paper_missing(project_root: Path) -> None:
    # No paper.md at all — single block finding pointing at the absent file.
    findings = FigureCoverageAudit().run(project_root)
    assert len(findings) == 1
    assert findings[0].severity == "block"
    assert "synthesis/paper.md" in findings[0].evidence_paths


def test_finding_ids_are_deterministic_across_runs(project_root: Path) -> None:
    _make_step(project_root, "01_eda", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    first = FigureCoverageAudit().run(project_root)
    second = FigureCoverageAudit().run(project_root)
    # Re-runs against an unchanged workspace must not churn IDs — they
    # are derived deterministically from (audit_name, dimension,
    # evidence_paths) via uuid5(NAMESPACE_DNS, key).
    assert [f.id for f in first] == [f.id for f in second]


# ---------------------------------------------------------------------------
# 2. Legacy dict surface preserved (regression — protocols + v1 tests
#    key on these keys / shape).
# ---------------------------------------------------------------------------


def test_legacy_dict_shape_block_on_orphan(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    res = audit_figure_coverage(project_root)
    assert res["status"] == "error"
    assert isinstance(res["blockers"], list)
    assert any("vol" in b for b in res["blockers"])
    assert res["checked"] == 1
    assert res["embedded"] == 0
    assert res["advice"]  # populated when blockers exist


def test_legacy_dict_shape_pass_when_embedded(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON + "\n![](workspace/01_x/outputs/figures/vol.png)\n")

    res = audit_figure_coverage(project_root)
    assert res["status"] == "success"
    assert res["blockers"] == []
    assert res["checked"] == 1
    assert res["embedded"] == 1
    assert res["advice"] is None


def test_legacy_dict_shape_no_paper(project_root: Path) -> None:
    res = audit_figure_coverage(project_root)
    assert res["status"] == "error"
    assert res["message"] == "synthesis/paper.md not found"
    assert res["blockers"] == ["synthesis/paper.md does not exist"]


def test_legacy_dict_shape_no_figures(project_root: Path) -> None:
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)
    res = audit_figure_coverage(project_root)
    assert res["status"] == "success"
    assert res["checked"] == 0
    assert res["embedded"] == 0
    assert "no figures" in res["message"]


# ---------------------------------------------------------------------------
# 3. write_audit_outputs — JSON companion + JSONL ledger
# ---------------------------------------------------------------------------


def test_write_audit_outputs_emits_three_artefacts(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    findings = FigureCoverageAudit().run(project_root)
    paths = write_audit_outputs(findings, "figure_coverage", project_root)

    assert paths["md"].exists()
    assert paths["json"].exists()
    assert paths["jsonl"].exists()

    # Markdown is human-readable and groups by severity.
    md = paths["md"].read_text()
    assert "figure_coverage audit" in md
    assert "block" in md.lower()


def test_json_companion_is_schema_valid(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    findings = FigureCoverageAudit().run(project_root)
    paths = write_audit_outputs(findings, "figure_coverage", project_root)

    arr = json.loads(paths["json"].read_text())
    assert isinstance(arr, list)
    assert len(arr) == len(findings)
    for obj in arr:
        # Validates against audit_finding.schema.json — raises on
        # missing required fields, bad enum, malformed UUID, etc.
        validate_finding(obj)
        assert obj["audit_name"] == "audit_figure_coverage"
        assert obj["dimension"] == "figures"
        assert obj["severity"] == "block"


def test_jsonl_ledger_appends_on_rerun(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    audit = FigureCoverageAudit()
    first = audit.run(project_root)
    write_audit_outputs(first, "figure_coverage", project_root)
    lines_after_first = (
        project_root / "workspace" / "logs" / ".audit_findings.jsonl"
    ).read_text().splitlines()

    second = audit.run(project_root)
    write_audit_outputs(second, "figure_coverage", project_root)
    lines_after_second = (
        project_root / "workspace" / "logs" / ".audit_findings.jsonl"
    ).read_text().splitlines()

    # Append-only: second run leaves the first run's lines intact and
    # adds its own batch on top.
    assert len(lines_after_second) == len(lines_after_first) + len(second)
    for ln in lines_after_second:
        validate_finding(json.loads(ln))


# ---------------------------------------------------------------------------
# 4. Markdown snapshot — keep the v2 audit report stable so dashboards
#    can rely on the header + counts shape.
# ---------------------------------------------------------------------------


def test_markdown_snapshot_for_single_orphan(project_root: Path) -> None:
    _make_step(project_root, "01_x", [("vol", "A caption.", True)])
    paper = project_root / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_PAPER_SKELETON)

    findings = FigureCoverageAudit().run(project_root)
    paths = write_audit_outputs(findings, "figure_coverage", project_root)
    md = paths["md"].read_text()

    # Anchor lines that downstream dashboards / docs reference. We avoid
    # snapshotting the whole file (timestamps + UUIDs would churn it on
    # every run); the structural anchors are what matter.
    assert md.startswith("# figure_coverage audit")
    assert "- Total findings: **1**" in md
    assert "- block: 1" in md
    assert "- warn: 0" in md
    assert "- info: 0" in md
    assert "## " in md  # at least one severity section
    assert "[figures]" in md  # dimension appears in finding header
