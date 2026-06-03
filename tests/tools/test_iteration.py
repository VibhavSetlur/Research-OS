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
    a = create_numbered_experiment(tmp_path, "alpha")["path_id"]
    b = create_numbered_experiment(tmp_path, "beta")["path_id"]   # most recent
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
    """create_numbered_experiment(from_step=X) must NOT duplicate X's
    outputs/scripts into the new step. The intent of from_step is only
    'wire data/input from X's output'."""
    from research_os.project_ops import (
        scaffold_minimal_workspace, create_numbered_experiment,
    )
    scaffold_minimal_workspace(tmp_path, "FromStepTest",
                                ide_flags=[], copy_agents=False)
    a = create_numbered_experiment(tmp_path, "alpha")["path_id"]
    # Plant some artefacts in alpha's outputs/scripts so we can check
    # they're NOT carried over.
    aa = tmp_path / "workspace" / a
    (aa / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    (aa / "outputs" / "figures" / "marker.png").write_bytes(b"PNG")
    (aa / "scripts" / "marker.py").write_text("# marker\n")

    b = create_numbered_experiment(tmp_path, "beta", from_step=a)["path_id"]
    bb = tmp_path / "workspace" / b
    # outputs/figures must be empty in beta.
    assert not (bb / "outputs" / "figures" / "marker.png").exists()
    assert not (bb / "scripts" / "marker.py").exists()
    # But data/input MUST be wired to alpha's data/output.
    link = bb / "data" / "input"
    assert link.is_symlink()
    assert link.resolve() == (aa / "data" / "output").resolve()


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
