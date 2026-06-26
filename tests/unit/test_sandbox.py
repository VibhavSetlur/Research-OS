"""Unit tests for the tiered execution sandbox (Phase 4).

Covers tier detection/degradation logic (mocked so the suite is
host-independent), command wrapping per tier, and a genuine end-to-end
resource-tier test that proves an rlimit actually bites on this host —
the resource tier is the universal floor and is always exercisable.
"""
from __future__ import annotations

import os
import sys

import pytest

from research_os.daemon import sandbox as sb
from research_os.daemon.runners import SubprocessRunner


@pytest.fixture(autouse=True)
def _reset_sandbox_cache():
    """Clear the module-global detection cache around every test so a
    monkeypatched probe in one test never leaks into the next."""
    sb._CACHE = None
    yield
    sb._CACHE = None


# --------------------------------------------------------------------------
# Tier resolution: degrade DOWN to the strongest supported, never UP.
# --------------------------------------------------------------------------

def _caps(container=None, namespace=None, resource=True):
    return sb.SandboxCapabilities(
        best_tier="container" if container else ("namespace" if namespace else "resource"),
        container_runtime=container,
        namespace_tool=namespace,
        resource_limits=resource,
    )


def test_resolve_tier_degrades_down_not_up():
    # Host only has the resource tier; a container request degrades to it.
    caps = _caps(resource=True)
    assert caps.resolve_tier("container") == "resource"
    assert caps.resolve_tier("namespace") == "resource"
    assert caps.resolve_tier("resource") == "resource"
    assert caps.resolve_tier(None) == "resource"


def test_resolve_tier_honours_strongest_available():
    caps = _caps(container="docker", namespace="bwrap", resource=True)
    assert caps.resolve_tier(None) == "container"  # strongest-first
    # Requesting a weaker tier than available must NOT silently upgrade.
    assert caps.resolve_tier("resource") == "resource"
    assert caps.resolve_tier("namespace") == "namespace"


def test_resolve_tier_namespace_host_degrades_container():
    caps = _caps(namespace="unshare", resource=True)
    assert caps.resolve_tier("container") == "namespace"
    assert caps.resolve_tier(None) == "namespace"


def test_tiers_available_order_is_strongest_first():
    caps = _caps(container="podman", namespace="bwrap", resource=True)
    assert caps.tiers_available() == ["container", "namespace", "resource"]


def test_resolve_tier_none_when_nothing():
    caps = sb.SandboxCapabilities(
        best_tier="none", container_runtime=None, namespace_tool=None, resource_limits=False
    )
    assert caps.resolve_tier("resource") == "none"


# --------------------------------------------------------------------------
# detect_sandbox: probes are host-independent via monkeypatch.
# --------------------------------------------------------------------------

def test_detect_prefers_container_when_usable(monkeypatch):
    monkeypatch.setattr(sb, "_container_runtime_usable", lambda b: b == "docker")
    monkeypatch.setattr(sb, "_userns_usable", lambda: True)
    monkeypatch.setattr(sb, "_resource_available", lambda: True)
    monkeypatch.setattr(sb.shutil, "which", lambda b: "/usr/bin/" + b)
    caps = sb.detect_sandbox(refresh=True)
    assert caps.best_tier == "container"
    assert caps.container_runtime == "docker"


def test_detect_notes_unusable_container_daemon(monkeypatch):
    # docker installed but daemon dead -> NOT counted, note explains why.
    monkeypatch.setattr(sb, "_container_runtime_usable", lambda b: False)
    monkeypatch.setattr(sb, "_userns_usable", lambda: False)
    monkeypatch.setattr(sb, "_resource_available", lambda: True)
    monkeypatch.setattr(sb.shutil, "which", lambda b: "/usr/bin/docker" if b == "docker" else None)
    caps = sb.detect_sandbox(refresh=True)
    assert caps.container_runtime is None
    assert caps.best_tier == "resource"
    assert any("unreachable" in n or "permission" in n for n in caps.notes)


def test_detect_resource_floor_always_present_on_posix(monkeypatch):
    monkeypatch.setattr(sb, "_container_runtime_usable", lambda b: False)
    monkeypatch.setattr(sb, "_userns_usable", lambda: False)
    monkeypatch.setattr(sb, "_resource_available", lambda: True)
    monkeypatch.setattr(sb.shutil, "which", lambda b: None)
    caps = sb.detect_sandbox(refresh=True)
    assert caps.best_tier == "resource"
    assert "resource" in caps.tiers_available()


# --------------------------------------------------------------------------
# wrap_command: per-tier argv transforms.
# --------------------------------------------------------------------------

def test_wrap_container_isolates_network_and_memory():
    caps = _caps(container="docker")
    limits = sb.ResourceLimits(address_space_mb=512, wall_seconds=None)
    cmd = sb.wrap_command(["python", "x.py"], tier="container", caps=caps, limits=limits)
    assert cmd[0] == "docker" and "run" in cmd and "--rm" in cmd
    assert "--network" in cmd and "none" in cmd
    assert "--memory" in cmd and "512m" in cmd
    assert cmd[-2:] == ["python", "x.py"]


def test_wrap_container_image_override_via_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_OS_SANDBOX_IMAGE", "r-base:4.3")
    caps = _caps(container="docker")
    cmd = sb.wrap_command(["Rscript", "a.R"], tier="container", caps=caps,
                          limits=sb.ResourceLimits(wall_seconds=None))
    assert "r-base:4.3" in cmd


def test_wrap_resource_tier_adds_wall_timeout_only():
    import shutil as _sh
    caps = _caps(resource=True)
    limits = sb.ResourceLimits(wall_seconds=30)
    cmd = sb.wrap_command(["sleep", "100"], tier="resource", caps=caps, limits=limits)
    if _sh.which("timeout"):
        # argv unchanged except the wallclock guard prefix.
        assert cmd[:3] == ["timeout", "-k", "10"]
        assert cmd[-2:] == ["sleep", "100"]
    else:  # no GNU timeout: argv must be untouched
        assert cmd == ["sleep", "100"]


def test_make_preexec_returns_callable_on_posix():
    fn = sb.make_preexec(sb.ResourceLimits())
    assert callable(fn)


# --------------------------------------------------------------------------
# Runner integration + a REAL rlimit that bites (resource tier, this host).
# --------------------------------------------------------------------------

def test_runner_records_effective_tier():
    # On this host (no container/userns) a container request degrades.
    runner = SubprocessRunner([sys.executable, "-c", "print('ok')"], sandbox="resource")
    out = runner()
    assert out["returncode"] == 0
    meta = out["sandbox"]
    assert meta is not None
    assert meta["requested"] == "resource"
    assert meta["effective"] in ("container", "namespace", "resource")
    assert "limits" in meta


def test_runner_no_sandbox_leaves_meta_none():
    runner = SubprocessRunner([sys.executable, "-c", "print('x')"])
    out = runner()
    assert out["sandbox"] is None


@pytest.mark.skipif(os.name != "posix", reason="rlimits are POSIX-only")
def test_resource_tier_memory_limit_actually_bites():
    # Cap virtual memory hard, then try to allocate well past it. The child
    # must die (MemoryError / nonzero exit), proving the preexec rlimit is
    # enforced rather than cosmetic.
    limits = sb.ResourceLimits(
        address_space_mb=128, cpu_seconds=None, file_size_mb=None,
        open_files=None, processes=None, wall_seconds=20,
    )
    runner = SubprocessRunner(
        [sys.executable, "-c", "x = bytearray(512 * 1024 * 1024); print(len(x))"],
        sandbox="resource",
        sandbox_limits=limits,
    )
    out = runner()
    # A 512MB alloc under a 128MB cap cannot succeed.
    assert out["returncode"] != 0
    assert out["sandbox"]["limits"]["address_space_mb"] == 128
