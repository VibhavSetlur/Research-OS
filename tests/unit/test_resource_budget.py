"""Resource budget — researcher-declared ceiling the daemon enforces.

docs/RESOURCE_BUDGET.md. A resource_budget: block in
researcher_config.yaml resolves into the ResourceLimits applied to every
run, turning the autopilot protocol's "stay within budget" prose into a
hard rlimit. These tests drive load/coerce/fail-safe, the overlay
precedence (incl. null=uncapped), and the runner integration.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from research_os.daemon import resource_budget as rb
from research_os.daemon.sandbox import ResourceLimits


def _write_cfg(root: Path, budget: dict | None) -> None:
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    cfg = {"interaction": {"autonomy_level": "adaptive"}}
    if budget is not None:
        cfg["resource_budget"] = budget
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump(cfg))


# --- load_budget -----------------------------------------------------------

def test_no_config_is_empty_budget(tmp_path):
    assert rb.load_budget(tmp_path) == {}


def test_no_budget_block_is_empty(tmp_path):
    _write_cfg(tmp_path, None)
    assert rb.load_budget(tmp_path) == {}


def test_nested_under_runtime_is_read(tmp_path):
    """The DOCUMENTED home is runtime.resource_budget — must be read."""
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "runtime": {"resource_budget": {"memory_mb": 4096}},
    }))
    assert rb.load_budget(tmp_path)["address_space_mb"] == 4096


def test_nested_runtime_wins_over_top_level(tmp_path):
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "resource_budget": {"memory_mb": 1024},
        "runtime": {"resource_budget": {"memory_mb": 8192}},
    }))
    assert rb.load_budget(tmp_path)["address_space_mb"] == 8192


def test_memory_mb_aliases_address_space(tmp_path):
    _write_cfg(tmp_path, {"memory_mb": 16384})
    b = rb.load_budget(tmp_path)
    assert b["address_space_mb"] == 16384


def test_all_fields_load(tmp_path):
    _write_cfg(tmp_path, {
        "memory_mb": 8192, "cpu_seconds": 3600, "wall_seconds": 7200,
        "file_size_mb": 51200, "open_files": 4096, "processes": 256,
    })
    b = rb.load_budget(tmp_path)
    assert b == {
        "address_space_mb": 8192, "cpu_seconds": 3600, "wall_seconds": 7200,
        "file_size_mb": 51200, "open_files": 4096, "processes": 256,
    }


def test_null_means_uncapped(tmp_path):
    _write_cfg(tmp_path, {"cpu_seconds": None})
    b = rb.load_budget(tmp_path)
    assert b["cpu_seconds"] is rb._UNCAPPED


def test_zero_means_uncapped(tmp_path):
    _write_cfg(tmp_path, {"cpu_seconds": 0})
    assert rb.load_budget(tmp_path)["cpu_seconds"] is rb._UNCAPPED


def test_unparseable_value_ignored(tmp_path):
    _write_cfg(tmp_path, {"memory_mb": "lots"})
    assert "address_space_mb" not in rb.load_budget(tmp_path)


def test_unknown_key_ignored(tmp_path):
    _write_cfg(tmp_path, {"gpus": 4, "memory_mb": 1024})
    b = rb.load_budget(tmp_path)
    assert b == {"address_space_mb": 1024}


def test_garbage_yaml_fails_safe(tmp_path):
    (tmp_path / "inputs").mkdir(parents=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text("{ not: valid: yaml:")
    assert rb.load_budget(tmp_path) == {}


# --- apply_budget (overlay precedence) ------------------------------------

def test_apply_caps_dimension():
    base = ResourceLimits()
    out = rb.apply_budget(base, {"address_space_mb": 2048})
    assert out.address_space_mb == 2048
    assert out.cpu_seconds == base.cpu_seconds  # untouched


def test_apply_uncapped_sets_none():
    base = ResourceLimits(cpu_seconds=900)
    out = rb.apply_budget(base, {"cpu_seconds": rb._UNCAPPED})
    assert out.cpu_seconds is None


def test_apply_empty_budget_is_identity():
    base = ResourceLimits()
    assert rb.apply_budget(base, {}) is base


def test_apply_does_not_mutate_base():
    base = ResourceLimits(address_space_mb=4096)
    rb.apply_budget(base, {"address_space_mb": 1024})
    assert base.address_space_mb == 4096


# --- resolve_run_limits (precedence: explicit > budget > default) ---------

def test_resolve_uses_budget_over_default(tmp_path):
    _write_cfg(tmp_path, {"memory_mb": 16384})
    out = rb.resolve_run_limits(tmp_path)
    assert out.address_space_mb == 16384


def test_resolve_budget_overrides_explicit_for_that_dimension(tmp_path):
    # Budget declares memory; explicit base declares cpu. Both should hold.
    _write_cfg(tmp_path, {"memory_mb": 2048})
    base = ResourceLimits(address_space_mb=99999, cpu_seconds=120)
    out = rb.resolve_run_limits(tmp_path, base=base)
    assert out.address_space_mb == 2048  # budget wins on its dimension
    assert out.cpu_seconds == 120        # explicit base survives elsewhere


def test_resolve_no_budget_returns_base(tmp_path):
    base = ResourceLimits(address_space_mb=123)
    out = rb.resolve_run_limits(tmp_path, base=base)
    assert out.address_space_mb == 123


# --- budget_summary --------------------------------------------------------

def test_summary_not_configured(tmp_path):
    s = rb.budget_summary(tmp_path)
    assert s == {"configured": False, "limits": {}}


def test_summary_configured_with_uncapped(tmp_path):
    _write_cfg(tmp_path, {"memory_mb": 8192, "cpu_seconds": None})
    s = rb.budget_summary(tmp_path)
    assert s["configured"] is True
    assert s["limits"]["address_space_mb"] == 8192
    assert s["limits"]["cpu_seconds"] is None


# --- runner integration (the limits actually reach the run) ---------------

def test_runner_resolves_budget_into_effective_limits(tmp_path):
    """A SubprocessRunner under a budgeted root records the budgeted limits."""
    from research_os.daemon.runners import SubprocessRunner

    _write_cfg(tmp_path, {"memory_mb": 256})
    runner = SubprocessRunner("echo hi", cwd=str(tmp_path), sandbox="resource")
    result = runner()
    meta = result.get("sandbox") or {}
    # The effective limits recorded for the run reflect the budget.
    assert meta.get("limits", {}).get("address_space_mb") == 256


# --- resolve_sandbox_tier (the universal-floor decision) -------------------

def _write_runtime(root: Path, runtime: dict) -> None:
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"runtime": runtime})
    )


def test_tier_off_means_unbounded_opt_out(tmp_path):
    assert rb.resolve_sandbox_tier(tmp_path, sandbox_mode="off") is None


def test_tier_native_is_resource_floor(tmp_path):
    assert rb.resolve_sandbox_tier(tmp_path, sandbox_mode="native") == "resource"


def test_tier_auto_default_still_bounds(tmp_path):
    """Auto with no runtime hints must STILL return a bounding tier — a daemon
    background run is never left completely unbounded by default."""
    tier = rb.resolve_sandbox_tier(tmp_path, sandbox_mode="auto")
    assert tier is not None


def test_tier_shared_server_forces_resource(tmp_path):
    """shared_server=true => resource floor (no futile Docker/userns probe on a
    locked-down shared HPC node)."""
    _write_runtime(tmp_path, {"shared_server": True})
    assert rb.resolve_sandbox_tier(tmp_path, sandbox_mode="auto") == "resource"


def test_tier_conda_env_forces_resource(tmp_path):
    _write_runtime(tmp_path, {"compute_environment": "conda"})
    assert rb.resolve_sandbox_tier(tmp_path, sandbox_mode="auto") == "resource"


def test_load_runtime_reads_shared_server_bool(tmp_path):
    _write_runtime(tmp_path, {"shared_server": "true", "compute_environment": "Conda"})
    rt = rb.load_runtime(tmp_path)
    assert rt["shared_server"] is True
    assert rt["compute_environment"] == "conda"


def test_load_runtime_empty_on_missing(tmp_path):
    assert rb.load_runtime(tmp_path) == {}


def test_budget_root_looks_up_under_project_not_cwd(tmp_path):
    """The budget must bind from the PROJECT ROOT even when the run's cwd is a
    subdirectory (regression: budget was looked up under cwd)."""
    from research_os.daemon.runners import SubprocessRunner

    _write_cfg(tmp_path, {"memory_mb": 256})
    subdir = tmp_path / "workspace" / "01_step"
    subdir.mkdir(parents=True, exist_ok=True)
    runner = SubprocessRunner(
        "echo hi", cwd=str(subdir), sandbox="resource",
        budget_root=str(tmp_path),
    )
    result = runner()
    meta = result.get("sandbox") or {}
    assert meta.get("limits", {}).get("address_space_mb") == 256


def test_run_command_bounds_a_runaway_job(tmp_path):
    """End-to-end: a daemon run_command honoring a tight memory budget kills a
    runaway allocation instead of letting it take down a shared node."""
    import time as _time

    from research_os.daemon.core import Daemon
    from research_os.daemon.config import DaemonConfig

    _write_cfg(tmp_path, {"memory_mb": 256, "wall_seconds": 5})
    cfg = DaemonConfig.resolve(root=tmp_path)
    daemon = Daemon(tmp_path, cfg)
    # Allocate ~1GB then touch it — must be killed by RLIMIT_AS (256MB), not
    # run to a clean success.
    code = "x = bytearray(1024*1024*1024); x[-1] = 1; print(len(x))"
    job_id = daemon.run_command(["python", "-c", code], track_artifacts=False)
    deadline = _time.time() + 30
    job = None
    while _time.time() < deadline:
        job = daemon.tasks.get(job_id)
        if job and job.status.value in ("succeeded", "failed", "cancelled"):
            break
        _time.sleep(0.1)
    assert job is not None and job.status.value == "failed", (
        "runaway allocation should be killed by the resource budget "
        f"(got status={getattr(job, 'status', None)})"
    )
