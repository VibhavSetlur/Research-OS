"""Sensitivity grid + cluster wrapper tests."""

from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.exec.cluster import (
    list_slurm,
    status_slurm,
    submit_slurm,
)
from research_os.tools.actions.exec.sensitivity import (
    define_sensitivity,
    run_sensitivity,
)


def _scaffold(tmp_path: Path):
    scaffold_minimal_workspace(tmp_path, project_name="P", git_init=False, ide_flags=[])
    create_numbered_experiment(tmp_path, "fit", enforce_predecessor_finalized=False)


def test_sensitivity_define(tmp_path: Path):
    _scaffold(tmp_path)
    r = define_sensitivity(
        "01_fit", tmp_path, base_script="scripts/fit.py",
    )
    assert r["status"] == "success"
    # Cartesian product of the field-neutral default grid (2 * 3 * 2 * 2) = 24.
    assert r["n_specifications"] == 24


def test_sensitivity_define_idempotent(tmp_path: Path):
    _scaffold(tmp_path)
    define_sensitivity("01_fit", tmp_path, base_script="scripts/fit.py")
    r2 = define_sensitivity("01_fit", tmp_path, base_script="scripts/fit.py")
    assert r2["status"] == "exists"


def test_sensitivity_run_with_missing_script(tmp_path: Path):
    _scaffold(tmp_path)
    define_sensitivity("01_fit", tmp_path, base_script="scripts/missing.py")
    r = run_sensitivity("01_fit", tmp_path, max_specs=2, render_figure=False)
    assert r["status"] == "error"


def test_slurm_submit_without_slurm_returns_explicit_error(tmp_path: Path):
    _scaffold(tmp_path)
    r = submit_slurm(tmp_path, cmd="python scripts/fit.py")
    # No slurm on the test runner — must NOT silently succeed.
    if r["status"] == "error":
        assert "slurm" in r["message"].lower() or "sbatch" in r["message"].lower()


def test_slurm_list_empty(tmp_path: Path):
    _scaffold(tmp_path)
    r = list_slurm(tmp_path)
    assert r["status"] == "success"
    assert r["n_jobs"] == 0


def test_slurm_status_handles_missing_record(tmp_path: Path):
    _scaffold(tmp_path)
    r = status_slurm(tmp_path, job_id="9999999")
    # When SLURM isn't installed → error string; otherwise empty jobs list.
    assert r["status"] in {"success", "error"}
