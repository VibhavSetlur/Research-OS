"""Resource-bounding of the reasoning-side exec surface (Wave1 CRITICAL fix).

The daemon run_command path was already bounded; these verify the DIRECT exec
tools (scripts/notebook/pipeline) also apply rlimits, and that shared_server
can't be silently overridden to unbounded.
"""
from __future__ import annotations

import sys

import pytest

from research_os.tools.actions.exec import _sandbox


def test_resolve_mem_cap_declared_only():
    rt = {"resource_budget": {"memory_mb": 512}, "dynamic_resources": {"enabled": False}}
    assert _sandbox.resolve_mem_cap_mb(rt) == 512


def test_resolve_mem_cap_unbounded_on_private_box_no_cap():
    rt = {"dynamic_resources": {"enabled": False}}  # no cap, not shared
    assert _sandbox.resolve_mem_cap_mb(rt) is None


def test_resolve_mem_cap_shared_server_never_unbounded():
    # shared_server + no declared cap + no dynamic signal → conservative cap, NOT None
    rt = {"shared_server": True, "dynamic_resources": {"enabled": False}}
    cap = _sandbox.resolve_mem_cap_mb(rt)
    assert cap is not None and cap > 0


def test_resolve_mem_cap_headroom_never_exceeds_declared(monkeypatch):
    monkeypatch.setattr(_sandbox, "_free_ram_mb", lambda: 100_000)
    rt = {"resource_budget": {"memory_mb": 1024},
          "dynamic_resources": {"enabled": True, "mem_fraction": 0.8, "mem_reserve_mb": 2048}}
    # headroom would be huge; declared cap (1024) must win
    assert _sandbox.resolve_mem_cap_mb(rt) == 1024


def test_resolve_mem_cap_shrinks_on_busy_box(monkeypatch):
    monkeypatch.setattr(_sandbox, "_free_ram_mb", lambda: 1000)  # only 1GB free
    rt = {"resource_budget": {"memory_mb": 100_000},  # declared 100GB
          "dynamic_resources": {"enabled": True, "mem_fraction": 0.8, "mem_reserve_mb": 256}}
    cap = _sandbox.resolve_mem_cap_mb(rt)
    # must shrink well below the declared 100GB toward live headroom
    assert cap < 100_000


@pytest.mark.skipif(sys.platform == "win32", reason="rlimits are POSIX-only")
def test_make_preexec_returns_callable_when_bounded():
    import tempfile
    import yaml
    from pathlib import Path
    from research_os.project_ops import scaffold_minimal_workspace

    d = Path(tempfile.mkdtemp())
    scaffold_minimal_workspace(d, "Sbx")
    cfgp = d / "inputs" / "researcher_config.yaml"
    cfg = yaml.safe_load(cfgp.read_text()) if cfgp.exists() else {}
    cfg.setdefault("runtime", {})["resource_budget"] = {"memory_mb": 256}
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    cfgp.write_text(yaml.safe_dump(cfg))
    pre = _sandbox.make_preexec(d)
    assert callable(pre)


@pytest.mark.skipif(sys.platform == "win32", reason="rlimits are POSIX-only")
def test_run_bounded_kills_runaway_allocation():
    """End-to-end: a >budget allocation through the exec surface is killed."""
    import tempfile
    import yaml
    from pathlib import Path
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.tools.actions.exec.scripts import execute_bash_script

    d = Path(tempfile.mkdtemp())
    scaffold_minimal_workspace(d, "Runaway")
    cfgp = d / "inputs" / "researcher_config.yaml"
    cfg = yaml.safe_load(cfgp.read_text()) if cfgp.exists() else {}
    cfg.setdefault("runtime", {})["resource_budget"] = {"memory_mb": 256}
    cfg["runtime"]["dynamic_resources"] = {"enabled": False}
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    cfgp.write_text(yaml.safe_dump(cfg))
    script = d / "big.sh"
    script.write_text(
        'python3 -c "x=bytearray(1024*1024*1024); x[-1]=1; print(\'OK1GB\')"\n'
    )
    res = execute_bash_script("big.sh", d, timeout=30)
    # the 1GB alloc under a 256MB cap must NOT succeed
    assert res.get("status") == "error"
    assert "OK1GB" not in (res.get("stdout") or "")


def test_shared_server_off_mode_still_bounds():
    """daemon resource_budget: sandbox_mode=off must NOT unbound a shared-server
    run (the project safety signal wins)."""
    import tempfile
    import yaml
    from pathlib import Path
    from research_os.daemon.resource_budget import resolve_sandbox_tier

    d = Path(tempfile.mkdtemp())
    (d / "inputs").mkdir(parents=True, exist_ok=True)
    (d / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"runtime": {"shared_server": True}})
    )
    # off on a shared server degrades to the resource floor, not None
    assert resolve_sandbox_tier(d, sandbox_mode="off") == "resource"
    # off on a private box still honours the opt-out
    d2 = Path(tempfile.mkdtemp())
    (d2 / "inputs").mkdir(parents=True, exist_ok=True)
    (d2 / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"runtime": {"shared_server": False}})
    )
    assert resolve_sandbox_tier(d2, sandbox_mode="off") is None
