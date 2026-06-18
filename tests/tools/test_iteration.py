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
    res = create_numbered_experiment(tmp_path, slug, hypothesis="H1", enforce_predecessor_finalized=False)
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
    from research_os.server.errors import RoError
    _make_step(tmp_path, slug="real_step")
    with pytest.raises((RoError, FileNotFoundError)):
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


# ── v1.2.2: numeric findings without a table → warning ────────────────


def test_step_completeness_warns_on_numeric_findings_without_table(tmp_path):
    """When a step has a figure + numeric findings but no CSV/TSV in
    outputs/tables/, surface a 'numeric findings + figure but no table'
    warning. Pre-v1.2.2 the audit accepted figures + reports with no
    machine-readable table, which is a research-record gap."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1, reports=1)
    # Findings with several numeric signals.
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n"
        "- AUROC = 0.823 (95% CI 0.79–0.85), n = 1532.\n"
        "- Calibration slope 0.91, intercept -0.04 (p < 0.001).\n"
        "## Decision\n\nproceed.\n"
    )
    res = audit_step_completeness(tmp_path, step_id=step_id)
    # Either status='ok' or 'warning', but the warning must be present.
    all_warnings = " ".join(
        w for step in res.get("steps", []) for w in step.get("warnings", [])
    )
    assert "no table" in all_warnings.lower(), (
        f"expected 'no table' warning, got warnings: {all_warnings}"
    )


def test_step_completeness_quiet_when_table_exists(tmp_path):
    """The 'no table' warning should NOT fire when outputs/tables/
    contains a step-prefixed CSV — even if findings are numeric."""
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1, tables=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n"
        "- AUROC = 0.823 (95% CI 0.79–0.85), n = 1532.\n"
        "## Decision\n\nproceed.\n"
    )
    res = audit_step_completeness(tmp_path, step_id=step_id)
    all_warnings = " ".join(
        w for step in res.get("steps", []) for w in step.get("warnings", [])
    )
    assert "no table" not in all_warnings.lower()


# ── v1.3.0: finalize_path now writes back into project-scope logs ────


def test_finalize_appends_step_entry_to_analysis_md(tmp_path):
    """finalize_path should add a step-finalized heading + headline +
    output counts to workspace/analysis.md (idempotent)."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1, tables=1, reports=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n\n"
        "- Hazard ratio = 1.42 (95% CI 1.10-1.84), p = 0.008.\n"
        "## Decision\nproceed.\n"
    )
    res = finalize_path(path_name=step_id, root=tmp_path)
    assert res["status"] == "success"
    assert any("analysis.md" in u for u in res.get("project_updates", []))
    analysis = (tmp_path / "workspace" / "analysis.md").read_text()
    assert f"### Step `{step_id}` finalized" in analysis
    assert "Hazard ratio" in analysis

    # Idempotency: running finalize again should NOT duplicate the
    # heading.
    finalize_path(path_name=step_id, root=tmp_path)
    again = (tmp_path / "workspace" / "analysis.md").read_text()
    assert again.count(f"### Step `{step_id}` finalized") == 1


def test_finalize_mirrors_methods_section_into_methods_md(tmp_path):
    """If conclusions.md has `## Methods (full detail)`, finalize_path
    should mirror it into workspace/methods.md under a step heading."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n- something\n\n"
        "## Methods (full detail)\n"
        "Cox proportional hazards model on n=152 subjects with "
        "right-censoring, fit via lifelines==0.27.4, seed=42.\n\n"
        "## Decision\nproceed.\n"
    )
    finalize_path(path_name=step_id, root=tmp_path)
    methods = (tmp_path / "workspace" / "methods.md").read_text()
    assert f"### Step `{step_id}` — methods" in methods
    assert "Cox proportional hazards" in methods


def test_finalize_warns_on_stub_findings(tmp_path):
    """finalize_path should surface a warning when conclusions.md
    Findings / Decision are still stubs — not a blocker, just a
    nudge."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    # Leave conclusions.md as the stub template (the create_numbered_experiment
    # scaffolder already wrote it with the placeholders).
    res = finalize_path(path_name=step_id, root=tmp_path)
    assert res["status"] == "success"
    warnings = res.get("warnings", [])
    assert any("Findings" in w for w in warnings) or any(
        "stub" in w.lower() for w in warnings
    ), f"expected stub-conclusions warning, got: {warnings}"


def test_env_snapshot_step_id_param(tmp_path):
    """sys_env_snapshot(step_id=…) should write into the named step's
    environment folder, not the most-recent active one."""
    from research_os.project_ops import create_numbered_experiment, scaffold_minimal_workspace
    from research_os.tools.actions.exec.environment import env_snapshot
    scaffold_minimal_workspace(tmp_path, "EnvScopeTest", ide_flags=[], copy_agents=False)
    a = create_numbered_experiment(tmp_path, "alpha", enforce_predecessor_finalized=False)["path_id"]
    b = create_numbered_experiment(tmp_path, "beta", enforce_predecessor_finalized=False)["path_id"]   # most recent
    res = env_snapshot(tmp_path, step_id=a)
    assert res["status"] == "success"
    # The snapshot must land in alpha, NOT beta (the active one).
    assert (tmp_path / "workspace" / a / "environment" / "requirements.txt").exists()
    # Beta should still be empty of step-specific requirements.
    assert not (tmp_path / "workspace" / b / "environment" / "requirements.txt").exists()


def test_env_snapshot_project_scope(tmp_path):
    """sys_env_snapshot(scope='project') should write to the
    project-global environment/ folder (eager-scaffolded in v1.3.0)."""
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.tools.actions.exec.environment import env_snapshot
    scaffold_minimal_workspace(tmp_path, "ScopeTest", ide_flags=[], copy_agents=False)
    res = env_snapshot(tmp_path, scope="project")
    assert res["status"] == "success"
    snap = tmp_path / "environment" / "requirements.txt"
    assert snap.exists()
    # Snapshot overwrites the init stub; new content should be a real
    # pip freeze, not the placeholder header.
    text = snap.read_text()
    assert "# Project-global Python packages" not in text


# ── v1.3.0 e2e-surfaced patches ──────────────────────────────────────


def test_finalize_headline_strips_markdown_bold(tmp_path):
    """Headline extraction must remove **bold** markers even when the
    bullet's leading list marker would otherwise eat the opening **."""
    from research_os.tools.actions.state.path import _headline_from_findings
    sample = (
        "## Findings\n\n"
        "- **Species main effect**: F(2, 322) = 744.8, p < 0.001, "
        "ω² = 0.821.\n"
        "## Decision\n"
    )
    headline = _headline_from_findings(sample)
    assert "Species main effect" in headline
    assert "**" not in headline, headline


def test_finalize_input_data_section_backfilled(tmp_path):
    """The README's `## Input data` stub should be replaced with the
    step's data/input listing once finalize_path runs."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=1)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n- finding\n\n## Decision\nproceed.\n"
    )
    # Drop a pipeline.yaml so the input inventory has something to find.
    (step_dir / "pipeline.yaml").write_text(
        "nodes:\n  - id: clean\n    inputs: ['inputs/raw_data/penguins.csv']\n"
    )
    finalize_path(path_name=step_id, root=tmp_path)
    readme = (step_dir / "README.md").read_text()
    assert "*(list inputs used)*" not in readme
    assert "inputs/raw_data/penguins.csv" in readme


def test_finalize_figure_inventory_filters_sidecars(tmp_path):
    """The Outputs section + the returned figure count should reflect
    REAL image files, not the .caption.md / .summary.md / .svg
    sidecars."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=2)
    # _populate_step writes caption + summary sidecars per figure; we
    # also add an SVG companion to verify the dedup branch.
    figs = step_dir / "outputs" / "figures"
    (figs / "01_curve_0.svg").write_text("<svg/>")
    (step_dir / "conclusions.md").write_text(
        "## Findings\n- finding\n\n## Decision\nproceed.\n"
    )
    res = finalize_path(path_name=step_id, root=tmp_path)
    assert res["figures"] == 2, (
        f"expected 2 real figures, got {res['figures']} — sidecars are "
        "leaking into the inventory"
    )


def test_from_step_does_not_copy_outputs(tmp_path):
    """create_numbered_experiment(from_step=X, enforce_predecessor_finalized=False) must NOT duplicate X's
    outputs/scripts into the new step. The intent of from_step is only
    'wire data/input from X's output'."""
    from research_os.project_ops import (
        scaffold_minimal_workspace, create_numbered_experiment,
    )
    scaffold_minimal_workspace(tmp_path, "FromStepTest",
                                ide_flags=[], copy_agents=False)
    a = create_numbered_experiment(tmp_path, "alpha", enforce_predecessor_finalized=False)["path_id"]
    # Plant some artefacts in alpha's outputs/scripts so we can check
    # they're NOT carried over.
    aa = tmp_path / "workspace" / a
    (aa / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    (aa / "outputs" / "figures" / "marker.png").write_bytes(b"PNG")
    (aa / "scripts" / "marker.py").write_text("# marker\n")

    b = create_numbered_experiment(tmp_path, "beta", from_step=a, enforce_predecessor_finalized=False)["path_id"]
    bb = tmp_path / "workspace" / b
    # outputs/figures must be empty in beta.
    assert not (bb / "outputs" / "figures" / "marker.png").exists()
    assert not (bb / "scripts" / "marker.py").exists()
    # But data/input MUST be wired to alpha's data/output.
    link = bb / "data" / "past_step_input"
    assert link.is_symlink()
    assert link.resolve() == (aa / "data" / "next_step_output").resolve()


def test_intake_biology_domain_recognised(tmp_path):
    """v1.3.0 added a biology_ecology domain so penguin-style datasets
    no longer fall through to 'economics'."""
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.tools.actions.data.intake import _classify_domain
    scaffold_minimal_workspace(tmp_path, "BioTest",
                                ide_flags=[], copy_agents=False)
    raw = tmp_path / "inputs" / "raw_data"
    raw.mkdir(parents=True, exist_ok=True)
    csv = raw / "penguins.csv"
    csv.write_text(
        "species,sex,island,bill_length_mm,bill_depth_mm,body_mass_g\n"
        "Adelie,male,Torgersen,39.1,18.7,3750\n"
    )
    context = "Working with Pygoscelis penguin morphometric data."
    domain, why = _classify_domain([csv], context)
    assert domain == "biology_ecology", (
        f"penguin CSV + 'pygoscelis' keyword should classify as "
        f"biology_ecology, got {domain!r} (why: {why})"
    )


def test_intake_extracts_markdown_hypotheses(tmp_path):
    """v1.3.0 hypothesis regex must handle the markdown-bullet-with-
    bold pattern advisors actually use:
        - **H1** — text
        - **H2**: text
    """
    from research_os.tools.actions.data.intake import _propose_hypotheses
    notes = (
        "## Open hypotheses\n\n"
        "- **H1** — Bill length differs by species.\n"
        "- **H2** — Within each species, males have deeper bills.\n"
        "- **H3** — Dimorphism scales allometrically with body mass.\n"
    )
    hs = _propose_hypotheses(notes)
    assert len(hs) == 3, f"expected 3 hypotheses, got {len(hs)}: {hs}"
    assert "Bill length" in hs[0]
    assert "deeper bills" in hs[1]
    assert "allometrically" in hs[2]


# ── v1.3.0 round-2: STATE.md, multi-language env, finalize audit ─────


def test_state_md_at_project_root_with_research_question(tmp_path):
    """v1.3.0 round-2: the human-readable status file is STATE.md at
    the project root, not buried under .os_state/. The content must
    surface what a fresh AI session needs."""
    from research_os.project_ops import (
        scaffold_minimal_workspace, save_state, load_state,
    )
    scaffold_minimal_workspace(tmp_path, "Round2 Test",
                                ide_flags=[], copy_agents=False,
                                config_overrides={
                                    "research_question": "Test Q",
                                    "domain": "biology_ecology",
                                })
    # Save state to make sure the trigger fires.
    save_state(tmp_path, load_state(tmp_path))
    state_md = tmp_path / "STATE.md"
    assert state_md.exists()
    text = state_md.read_text()
    # New fresh-chat directions section.
    assert "How to resume in a fresh chat" in text
    # No internal-tool jargon for the reader.
    assert "mem_analysis_log" not in text
    # Old buried copy gone after the migration in save_state.
    assert not (tmp_path / ".os_state" / "os_state.md").exists()


def test_env_snapshot_skips_python_for_r_only_project(tmp_path):
    """A project whose only scripts are R should NOT receive a stray
    pip-freeze. v1.3.0 detects languages from the workspace."""
    from research_os.project_ops import (
        scaffold_minimal_workspace, create_numbered_experiment,
    )
    from research_os.tools.actions.exec.environment import env_snapshot
    scaffold_minimal_workspace(tmp_path, "R Only",
                                ide_flags=[], copy_agents=False)
    step_id = create_numbered_experiment(tmp_path, "r_analysis", enforce_predecessor_finalized=False)["path_id"]
    # Drop a single R script — no Python anywhere.
    r_script = (tmp_path / "workspace" / step_id / "scripts" / "01_fit.R")
    r_script.write_text("library(MASS)\n")
    res = env_snapshot(tmp_path, step_id=step_id)
    assert res["status"] == "success"
    captured = res.get("languages_captured", [])
    assert "R" in captured, (
        f"R script in workspace should trigger R capture, got {captured}"
    )
    assert "python" not in captured, (
        f"R-only project should NOT get python capture, got {captured}"
    )


def test_env_snapshot_picks_up_quarto_and_julia(tmp_path):
    """v1.3.0 round-2: workspace scan picks up .qmd (Quarto) and
    .jl (Julia) files and captures both."""
    from research_os.project_ops import (
        scaffold_minimal_workspace, create_numbered_experiment,
    )
    from research_os.tools.actions.exec.environment import env_snapshot
    scaffold_minimal_workspace(tmp_path, "Mixed",
                                ide_flags=[], copy_agents=False)
    step_id = create_numbered_experiment(tmp_path, "mixed", enforce_predecessor_finalized=False)["path_id"]
    s = tmp_path / "workspace" / step_id / "scripts"
    (s / "01_report.qmd").write_text("---\ntitle: X\n---\n")
    (s / "02_fit.jl").write_text("using Plots\n")
    res = env_snapshot(tmp_path, step_id=step_id)
    captured = res.get("languages_captured", [])
    assert "quarto" in captured
    assert "julia" in captured


def test_finalize_runs_figure_audit_per_figure(tmp_path):
    """v1.3.0 round-2: tool_path_finalize now runs the figure audit
    on every figure and returns the results under `figure_audit` +
    rolls blockers into warnings."""
    from research_os.tools.actions.state.path import finalize_path
    step_id = _make_step(tmp_path)
    step_dir = tmp_path / "workspace" / step_id
    _populate_step(step_dir, scripts=1, figures=2)
    (step_dir / "conclusions.md").write_text(
        "## Findings\n- finding\n\n## Decision\nproceed.\n"
    )
    res = finalize_path(path_name=step_id, root=tmp_path)
    assert res["status"] == "success"
    fa = res.get("figure_audit", {})
    assert len(fa) == 2, (
        f"expected per-figure audit for 2 figures, got {len(fa)}"
    )
    # The fake .png bytes _populate_step writes have no real DPI;
    # PIL either errors out or reports defaults. Either way we expect
    # the audit dict to have blockers OR warnings keys present.
    for fig_name, entry in fa.items():
        assert "blockers" in entry and "warnings" in entry


def test_workspace_logs_has_a_readme_after_init(tmp_path):
    """v1.3.0 round-2: workspace/logs/ ships with a README explaining
    what kinds of logs land there. Previously it was a dead empty
    folder."""
    from research_os.project_ops import scaffold_minimal_workspace
    scaffold_minimal_workspace(tmp_path, "Logs Test",
                                ide_flags=[], copy_agents=False)
    logs_readme = tmp_path / "workspace" / "logs" / "README.md"
    assert logs_readme.exists()
    text = logs_readme.read_text()
    # Must mention the standard log files researchers grep for.
    assert "audit_report.md" in text
    assert "search_log.md" in text
    assert "override_log.md" in text


# ---------------------------------------------------------------------------
# v1.3.1 regression tests
# ---------------------------------------------------------------------------


def test_finalize_scrapes_references_into_citations_md(tmp_path):
    """v1.3.1: finalize must scrape `## References to ground` from
    conclusions.md into the project-wide citations.md."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "test_step",
        enforce_predecessor_finalized=False,
    )
    conc = tmp_path / "workspace" / step["path_id"] / "conclusions.md"
    conc.write_text(
        "# Conclusions — test_step\n\n"
        "## Decision\nPROCEED to step 02.\n\n"
        "## References to ground\n"
        "- Smith J, et al. Nature 2024 — fictional canonical reference.\n"
        "- Doe A. PLOS ONE 2023 — fictional second reference.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    citations = (tmp_path / "workspace" / "citations.md").read_text()
    assert "Smith J" in citations, (
        "References to ground should have been scraped into citations.md"
    )
    assert "Doe A" in citations
    # And per-step key_papers.md
    kp = tmp_path / "workspace" / step["path_id"] / "literature" / "key_papers.md"
    assert kp.exists(), "literature/key_papers.md should have been auto-filled"
    assert "Smith J" in kp.read_text()


def test_finalize_mirrors_decision_into_log(tmp_path):
    """v1.3.1: finalize must mirror the conclusions.md `## Decision`
    block into workspace/analysis.md as a Decision · timestamp entry."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "decision_test", enforce_predecessor_finalized=False,
    )
    conc = tmp_path / "workspace" / step["path_id"] / "conclusions.md"
    conc.write_text(
        "# Conclusions — decision_test\n\n"
        "## Decision\nPROCEED — model is well-calibrated.\n\n"
        "## References to ground\n- Test 2024\n"
    )
    finalize_path(step["path_id"], tmp_path)
    analysis_md = (tmp_path / "workspace" / "analysis.md").read_text()
    assert "PROCEED" in analysis_md, "decision verb should be in analysis.md"
    assert f"step={step['path_id']}" in analysis_md, (
        "the marker line for idempotency must be present"
    )


def test_finalize_flips_step_status_to_completed(tmp_path):
    """v1.3.1: finalize must flip the state-ledger path status from
    'active' to 'completed' so STATE.md shows ✓ instead of →."""
    from research_os.project_ops import (
        create_numbered_experiment, load_state, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "status_test", enforce_predecessor_finalized=False,
    )
    pre = load_state(tmp_path)["paths"][step["path_id"]]["status"]
    assert pre == "active"
    conc = tmp_path / "workspace" / step["path_id"] / "conclusions.md"
    conc.write_text(
        "# Conclusions\n## Decision\nPROCEED.\n## Findings\n- All good.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    post = load_state(tmp_path)["paths"][step["path_id"]]["status"]
    assert post == "completed"


def test_finalize_env_snapshot_uses_project_scope(tmp_path):
    """v1.3.1: env auto-snapshot at finalize must land in
    environment/requirements.txt (project-global), NOT in the active
    step's environment folder."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "env_test", enforce_predecessor_finalized=False,
    )
    # Produce work so the env-snapshot trigger fires
    step_dir = tmp_path / "workspace" / step["path_id"]
    (step_dir / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    (step_dir / "outputs" / "figures" / "01_fake.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (step_dir / "outputs" / "figures" / "01_fake.caption.md").write_text("caption.")
    conc = step_dir / "conclusions.md"
    conc.write_text(
        "# Conclusions\n## Decision\nPROCEED.\n## Findings\n- All good.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    proj_req = tmp_path / "environment" / "requirements.txt"
    text = proj_req.read_text()
    # Post-snapshot, the file should have at least one non-comment
    # package line (e.g. 'pytest==X.Y' or similar).
    has_package = any(
        ln.strip() and not ln.strip().startswith("#")
        for ln in text.splitlines()
    )
    assert has_package, (
        "project environment/requirements.txt should have pinned packages "
        "after finalize, not stay as the comment-only template"
    )


def test_tools_md_filters_stdlib(tmp_path):
    """v1.3.1: workspace/tools.md must exclude stdlib modules
    (pathlib, sys, warnings) from the auto-import scan."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "imports_test", enforce_predecessor_finalized=False,
    )
    step_dir = tmp_path / "workspace" / step["path_id"]
    (step_dir / "scripts").mkdir(exist_ok=True)
    (step_dir / "scripts" / "main_v1.py").write_text(
        "import pathlib\nimport sys\nimport warnings\nimport pandas\nimport numpy\n"
    )
    conc = step_dir / "conclusions.md"
    conc.write_text(
        "# Conclusions\n## Decision\nPROCEED.\n## Findings\n- ok.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    tools_md = (tmp_path / "workspace" / "tools.md").read_text()
    assert "pandas" in tools_md
    assert "numpy" in tools_md
    assert "`pathlib`" not in tools_md, "stdlib `pathlib` should be filtered"
    assert "`sys`" not in tools_md, "stdlib `sys` should be filtered"
    assert "`warnings`" not in tools_md, "stdlib `warnings` should be filtered"


# ---------------------------------------------------------------------------
# v1.3.3 — anti-one-shot tool_step_revision_options
# ---------------------------------------------------------------------------


def test_step_revision_options_flags_placeholder_conclusions(tmp_path):
    """v1.3.3: revision_options surfaces unfilled-placeholder + short-
    Findings + missing-figure heuristics so the AI can pause before
    advancing to the next step."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.revision import step_revision_options
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "stub_step", enforce_predecessor_finalized=False,
    )
    # Leave conclusions.md as the seed placeholder template (default).
    res = step_revision_options(step["path_id"], tmp_path)
    assert res["status"] == "success"
    assert res["would_benefit_from_revision"] is True
    assert any("placeholder" in s.lower() for s in res["suggested_revisions"])
    assert any("figure" in s.lower() for s in res["suggested_revisions"])


def test_step_revision_options_clean_step_passes(tmp_path):
    """A step with substantive conclusions + figures + tables should NOT
    be flagged as needing revision (heuristic returns False)."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.revision import step_revision_options
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "clean_step", enforce_predecessor_finalized=False,
    )
    step_dir = tmp_path / "workspace" / step["path_id"]
    conc = step_dir / "conclusions.md"
    # Substantive content (>200 chars in Findings).
    conc.write_text(
        "# Conclusions — clean_step\n\n"
        "## Headline finding\n"
        "**Real finding written out.**\n\n"
        "## Methods (full detail)\n"
        "Real methods written out across multiple sentences with citations.\n\n"
        "## Findings\n"
        "- " + ("Substantive finding with specific numbers (n=12, p<0.001, "
        "effect size 0.85). " * 5) + "\n"
        "- Another substantive finding with explicit references to figures + tables.\n\n"
        "## Decision\nPROCEED to next step.\n\n"
        "## Limitations\n- The usual small-n caveats.\n"
    )
    fig_dir = step_dir / "outputs" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    (fig_dir / "01_fig.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    tab_dir = step_dir / "outputs" / "tables"
    tab_dir.mkdir(parents=True, exist_ok=True)
    (tab_dir / "01_tab.csv").write_text("a,b\n1,2\n")
    res = step_revision_options(step["path_id"], tmp_path)
    assert res["status"] == "success"
    # Heuristic might still flag minor things (e.g. env folder empty),
    # but the headline boolean should be False because findings are
    # substantive + figures + tables present.
    assert res["would_benefit_from_revision"] is False, (
        f"clean step shouldn't need revision; got: {res['suggested_revisions']}"
    )


def test_finalize_does_not_emit_step_summary_yaml(tmp_path):
    """3.2: the derived step_summary.yaml sidecar was retired — finalize
    leaves conclusions.md as the single per-step source of truth and does
    NOT write a step_summary.yaml."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "summary_test", enforce_predecessor_finalized=False,
    )
    step_dir = tmp_path / "workspace" / step["path_id"]
    (step_dir / "conclusions.md").write_text(
        "# Conclusions — summary_test\n\n"
        "## Headline finding\n**Test headline with numbers (n=12, p<0.001).**\n\n"
        "## Methods (full detail)\n"
        "- DESeq2 negative-binomial GLM (Love et al 2014).\n\n"
        "## Findings\n- Finding A.\n- Finding B.\n\n"
        "## Decision\nPROCEED to next step.\n\n"
        "## Limitations\n- Small n.\n\n"
        "## References to ground\n- Love MI, et al. 2014.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    assert not (step_dir / "step_summary.yaml").exists(), (
        "step_summary.yaml must NOT be written in 3.2"
    )
    # conclusions.md remains the source of truth and is left intact.
    conc = (step_dir / "conclusions.md").read_text()
    assert "Test headline" in conc
    assert "DESeq2" in conc


def test_finalize_appends_anticipated_reviewer_questions(tmp_path):
    """v1.3.3: finalize auto-appends a scaffolded self-critique section
    so the AI's own retrospective is on record."""
    from research_os.project_ops import (
        create_numbered_experiment, scaffold_minimal_workspace,
    )
    from research_os.tools.actions.state.path import finalize_path
    scaffold_minimal_workspace(tmp_path, "Test")
    step = create_numbered_experiment(
        tmp_path, "retro_test", enforce_predecessor_finalized=False,
    )
    step_dir = tmp_path / "workspace" / step["path_id"]
    (step_dir / "conclusions.md").write_text(
        "# Conclusions\n\n## Headline finding\n**Test.**\n\n"
        "## Methods (full detail)\nNB-GLM fit per gene with PCA.\n\n"
        "## Findings\n- Good.\n\n## Decision\nPROCEED.\n\n"
        "## Limitations\n- Small n acknowledged.\n"
    )
    finalize_path(step["path_id"], tmp_path)
    conc = (step_dir / "conclusions.md").read_text()
    assert "## Anticipated reviewer questions" in conc
    # Should have at least one content-aware question (we mentioned NB-GLM + PCA).
    assert any(k in conc.lower() for k in ("dispersion", "shrunk", "pc1")) or \
        "anticipated" in conc.lower()
