"""Tests for tool_step_iterate / tool_step_iterations_list /
tool_audit_version_coherence and the mega-script blocker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.audit.audit import audit_step_completeness
from research_os.tools.actions.state.iteration import (
    audit_version_coherence,
    iterate_step,
    list_iterations,
)


def _make_step(tmp_path: Path, slug: str = "baseline_eda") -> str:
    scaffold_minimal_workspace(tmp_path, "Test", ide_flags=[], copy_agents=False)
    res = create_numbered_experiment(tmp_path, slug, hypothesis="H1")
    return res["path_id"]


def _populate_step(step_dir: Path, *, scripts=1, figures=0, tables=0, reports=0):
    """Fill a step with synthetic artefacts so audits have something to chew."""
    for i in range(scripts):
        s = step_dir / "scripts" / f"01_fit_v{i + 1}.py"
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text(f"# version {i + 1}\nprint('hi')\n")
    for i in range(figures):
        f = step_dir / "outputs" / "figures" / f"01_curve_{i}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        (f.with_name(f.stem + ".caption.md")).write_text("caption")
        (f.with_name(f.stem + ".summary.md")).write_text("summary")
    for i in range(tables):
        t = step_dir / "outputs" / "tables" / f"01_table_{i}.csv"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("a,b\n1,2\n")
    for i in range(reports):
        r = step_dir / "outputs" / "reports" / f"01_report_{i}.md"
        r.parent.mkdir(parents=True, exist_ok=True)
        r.write_text("# report\n\nbody.\n")


# ── tool_step_iterate ─────────────────────────────────────────────────


def test_iterate_step_requires_rationale(tmp_path):
    step_id = _make_step(tmp_path)
    _populate_step(tmp_path / "workspace" / step_id, scripts=1, figures=1)
    with pytest.raises(ValueError):
        iterate_step(tmp_path, step_id=step_id, rationale="")


def test_iterate_step_snapshots_into_versions_dir(tmp_path):
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    # Write a non-stub conclusion so the snapshot picks it up.
    (step_dir / "conclusions.md").write_text("## Findings\n\n- finding 1\n")

    res = iterate_step(
        tmp_path,
        step_id=step_id,
        rationale="recolour the figure",
        scripts=None,
        figures=None,
    )
    assert res["status"] == "success"
    assert res["iteration"] == 1
    archive = step_dir / ".versions" / "v1"
    assert archive.is_dir()
    assert (archive / "scripts" / "01_fit_v1.py").exists()
    assert (archive / "outputs" / "figures" / "01_curve_0.png").exists()
    assert (archive / "outputs" / "figures" / "01_curve_0.caption.md").exists()
    assert (archive / "conclusions.md").exists()
    # Ledger written.
    ledger = yaml.safe_load((step_dir / "iterations.yaml").read_text())
    assert ledger["iterations"][0]["rationale"] == "recolour the figure"
    # Next-rename suggestion bumps the version suffix.
    assert res["next_script_paths"] == {"01_fit_v1.py": "01_fit_v2.py"}


def test_iterate_step_increments_iteration_number(tmp_path):
    step_id = _make_step(tmp_path)
    _populate_step(tmp_path / "workspace" / step_id, scripts=1, figures=1)
    a = iterate_step(tmp_path, step_id=step_id, rationale="first")
    b = iterate_step(tmp_path, step_id=step_id, rationale="second")
    assert a["iteration"] == 1
    assert b["iteration"] == 2
    ledger = list_iterations(tmp_path, step_id)
    assert len(ledger["iterations"]) == 2


# ── tool_audit_version_coherence ───────────────────────────────────────


def test_version_coherence_clean_when_no_provenance(tmp_path):
    step_id = _make_step(tmp_path)
    _populate_step(tmp_path / "workspace" / step_id, scripts=1, figures=1)
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["status"] == "success"
    assert res["drift_count"] == 0


def test_version_coherence_flags_stale_script_reference(tmp_path):
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=2, figures=1)
    # Write a .prov.json pointing at v1 while v2 is on disk.
    fig = step_dir / "outputs" / "figures" / "01_curve_0.png"
    prov = fig.with_name(fig.stem + ".prov.json")
    prov.write_text(json.dumps({
        "@id": str(fig.relative_to(tmp_path)),
        "produced_by": {"script": "scripts/01_fit_v1.py"},
        "inputs": {},
    }))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["status"] == "warning"
    assert res["drift_count"] == 1
    drift = res["steps"][0]["drift"][0]
    assert "01_fit_v1.py" in drift
    assert "v2" in drift


def test_version_coherence_flags_missing_script(tmp_path):
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    fig = step_dir / "outputs" / "figures" / "01_curve_0.png"
    prov = fig.with_name(fig.stem + ".prov.json")
    prov.write_text(json.dumps({
        "@id": str(fig.relative_to(tmp_path)),
        "produced_by": {"script": "scripts/01_fit_DELETED.py"},
        "inputs": {},
    }))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["status"] == "warning"
    assert "no longer in scripts/" in res["steps"][0]["drift"][0]


# ── mega-script blocker in tool_audit_step_completeness ────────────────


def test_step_completeness_blocks_multi_category_without_pipeline(tmp_path):
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    # Single mega-script producing outputs across 3 categories.
    _populate_step(step_dir, scripts=1, figures=1, tables=1, reports=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- finding\n\n## Decision\n\nproceed.\n"
    )

    res = audit_step_completeness(tmp_path, step_id=step_id)
    assert res["status"] == "error"
    assert any(
        "mega-script" in b or "categories" in b for b in res["blockers"]
    ), f"expected mega-script blocker, got {res['blockers']}"


def test_step_completeness_passes_with_pipeline_yaml(tmp_path):
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=2, figures=1, tables=1, reports=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- finding\n\n## Decision\n\nproceed.\n"
    )
    # Declare the DAG.
    (step_dir / "pipeline.yaml").write_text(
        "nodes:\n  - id: fit\n  - id: visualize\n  - id: report\n"
    )
    res = audit_step_completeness(tmp_path, step_id=step_id)
    # Mega-script blocker should not fire when pipeline.yaml exists.
    assert not any("mega-script" in b for b in res["blockers"])


def test_step_completeness_single_category_ok_without_pipeline(tmp_path):
    """A step with only figures (no tables / reports) is genuinely atomic."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- finding\n\n## Decision\n\nproceed.\n"
    )
    res = audit_step_completeness(tmp_path, step_id=step_id)
    assert not any("mega-script" in b for b in res["blockers"])
