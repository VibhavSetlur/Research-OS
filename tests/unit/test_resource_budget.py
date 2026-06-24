"""Resource budget — researcher-declared ceiling the daemon enforces.

docs/v4/RESOURCE_BUDGET.md. A resource_budget: block in
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
