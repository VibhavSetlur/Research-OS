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


# ── regression tests for the hardening pass ───────────────────────────


def test_mega_script_ignores_stray_figures_without_step_prefix(tmp_path):
    """Bug: stray figure files (no step_num prefix) forced a BLOCKER.

    A step that legitimately produces only a CSV table must not get
    blocked when an unrelated comparison panel.png lands in
    outputs/figures/.
    """
    step_id = _make_step(tmp_path, slug="fit")
    step_dir = tmp_path / "workspace" / step_id
    step_num = step_id.split("_", 1)[0]
    # Legit: one CSV table from this step.
    _populate_step(step_dir, scripts=1, tables=1)
    # Stray: a figure with NO step-number prefix (someone dropped it).
    stray = step_dir / "outputs" / "figures" / "panel.png"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    stray.with_name("panel.caption.md").write_text("c")
    stray.with_name("panel.summary.md").write_text("s")
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n- finding\n\n## Decision\n\nproceed.\n"
    )

    res = audit_step_completeness(tmp_path, step_id=step_id)
    # The mega-script blocker must NOT fire — the stray figure has no
    # step_num prefix so it isn't an artefact of this step.
    assert not any("mega-script" in b for b in res["blockers"]), (
        f"stray figure should not trigger blocker; got {res['blockers']}"
    )
    # Categories actually attributable to this step's scripts: tables only.
    assert res["steps"][0]["output_categories"] == 1
    _ = step_num  # silence the unused warning if numbering changes


def test_version_coherence_does_not_falsely_flag_sibling_prefix(tmp_path):
    """Bug: unrelated scripts sharing a prefix produced false drift.

    Step has scripts/01_fit_v2.py (used by the figure) AND an unrelated
    scripts/01_fit_extended_v3.py. The audit must report drift_count=0,
    not blame `_extended_v3` for `_v2`'s figure.
    """
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    (step_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (step_dir / "scripts" / "01_fit_v2.py").write_text("# fit v2\n")
    (step_dir / "scripts" / "01_fit_extended_v3.py").write_text("# unrelated\n")
    (step_dir / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    fig = step_dir / "outputs" / "figures" / "01_curve.png"
    fig.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    fig.with_name("01_curve.prov.json").write_text(json.dumps({
        "produced_by": {"script": "scripts/01_fit_v2.py"},
    }))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["drift_count"] == 0, res["steps"][0]["drift"]


def test_version_coherence_catches_unsuffixed_to_versioned_drift(tmp_path):
    """Bug: prov pointing at unsuffixed script + newer _v2 on disk was missed."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    (step_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (step_dir / "scripts" / "02_clean.py").write_text("# original\n")
    (step_dir / "scripts" / "02_clean_v2.py").write_text("# replacement\n")
    (step_dir / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    fig = step_dir / "outputs" / "figures" / "02_overview.png"
    fig.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    fig.with_name("02_overview.prov.json").write_text(json.dumps({
        "produced_by": {"script": "scripts/02_clean.py"},
    }))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["drift_count"] == 1, res
    assert "02_clean_v2.py" in res["steps"][0]["drift"][0]


def test_bump_script_suffix_skips_existing_versions(tmp_path):
    """Bug: rename advice clobbered existing _v(n+1) files."""
    from research_os.tools.actions.state.iteration import _bump_script_suffix
    step_id = _make_step(tmp_path)
    scripts = tmp_path / "workspace" / step_id / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "fit_v1.py").write_text("v1")
    (scripts / "fit_v2.py").write_text("v2")  # already on disk!
    advised = _bump_script_suffix(scripts / "fit_v1.py")
    # Must skip v2 (and v1) to the first free slot — v3.
    assert advised.name == "fit_v3.py"


def test_iterate_step_picks_unused_archive_dir(tmp_path):
    """Refuses to overwrite an existing .versions/v<n>/ on disk."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    # Pre-create v1 to simulate a stale/orphan archive.
    (step_dir / ".versions" / "v1" / "stale.txt").parent.mkdir(parents=True)
    (step_dir / ".versions" / "v1" / "stale.txt").write_text("do not clobber")
    res = iterate_step(tmp_path, step_id=step_id, rationale="r")
    assert res["iteration"] >= 2
    assert (step_dir / ".versions" / "v1" / "stale.txt").read_text() == "do not clobber"


def test_audit_version_coherence_rejects_unknown_step_id(tmp_path):
    """Typo'd step_id must surface, not silently return success."""
    _make_step(tmp_path, slug="real_step")
    with pytest.raises(FileNotFoundError):
        audit_version_coherence(tmp_path, step_id="not_a_real_step")


def test_audit_version_coherence_rejects_traversal(tmp_path):
    _make_step(tmp_path)
    with pytest.raises(ValueError):
        audit_version_coherence(tmp_path, step_id="../inputs")


def test_audit_version_coherence_escalates_status_on_warnings(tmp_path):
    """Bug: warning-only steps left top-level status='success'."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    # Caption older than figure → warning, no drift.
    fig = step_dir / "outputs" / "figures" / "01_curve_0.png"
    cap = fig.with_name("01_curve_0.caption.md")
    import os
    import time
    old = time.time() - 3600
    os.utime(cap, (old, old))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["status"] == "warning"
    assert res["warning_count"] >= 1


def test_audit_version_coherence_warns_on_empty_snapshot_dir(tmp_path):
    """Bug: empty snapshot_dir collapsed to step → integrity check silent."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    # Hand-write a ledger entry with a missing snapshot_dir.
    (step_dir / "iterations.yaml").write_text(yaml.safe_dump({
        "step_id": step_dir.name,
        "iterations": [{"iteration": 1, "snapshot_dir": ""}],
    }))
    res = audit_version_coherence(tmp_path, step_id=step_id)
    assert res["status"] == "warning"
    assert any("malformed" in w or "scrubbed" in w
               for w in res["steps"][0]["warnings"])
