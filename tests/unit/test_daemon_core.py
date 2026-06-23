"""Unit tests for the v4 daemon core (research_os.daemon.core).

Covers the Daemon holder, the DaemonStatus snapshot (uninitialized vs.
initialized project), the not-yet-implemented serve() contract, and the
lazy-import discipline (importing the package must not pull the heavy web
serving stack).
"""
from __future__ import annotations

import sys

import pytest

from research_os.daemon import Daemon, DaemonConfig, DaemonStatus


def test_package_import_does_not_pull_heavy_web_deps():
    """`import research_os.daemon` must stay cheap — no starlette/uvicorn.

    The serving stack lives in the optional [daemon] extra and is imported
    lazily by later phases. Importing the package at all must never require
    it (core-only installs must work).

    Run in a FRESH subprocess: a shared interpreter's sys.modules is
    polluted by other tests that legitimately import starlette, so the only
    robust way to test our import-time discipline is process isolation.
    """
    import subprocess

    code = (
        "import sys, research_os.daemon\n"
        "leaked = [m for m in ('starlette', 'uvicorn', 'sse_starlette') "
        "if m in sys.modules]\n"
        "print(','.join(leaked))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"import failed: {res.stderr}"
    leaked = res.stdout.strip()
    assert not leaked, f"daemon import leaked heavy web deps: {leaked}"


def test_for_root_builds_daemon_with_config(tmp_path):
    d = Daemon.for_root(tmp_path, port=4242)
    assert d.root == tmp_path
    assert isinstance(d.config, DaemonConfig)
    assert d.config.port == 4242
    assert d.serving is False


def test_status_uninitialized_project(tmp_path):
    d = Daemon.for_root(tmp_path)
    status = d.status()
    assert isinstance(status, DaemonStatus)
    assert status.serving is False
    assert status.project_initialized is False
    assert status.root == str(tmp_path)
    assert any("os_state" in n for n in status.notes)
    # serializable
    assert status.to_dict()["project_initialized"] is False


def test_status_with_none_root():
    d = Daemon(root=None, config=DaemonConfig())
    status = d.status()
    assert status.root is None
    assert status.project_initialized is False
    assert any("no project root" in n for n in status.notes)


def test_status_initialized_project_reads_state(tmp_path):
    """An initialized project (has .os_state) reports initialized + no
    spurious 'run init' note, and never raises while reading engine state."""
    (tmp_path / ".os_state").mkdir()
    d = Daemon.for_root(tmp_path)
    status = d.status()
    assert status.project_initialized is True
    assert not any("run 'research-os init'" in n for n in status.notes)
    # progress is always a dict; active_protocol is str|None
    assert isinstance(status.progress, dict)
    assert status.active_protocol is None or isinstance(status.active_protocol, str)


def test_status_includes_config_block(tmp_path):
    d = Daemon.for_root(tmp_path, host="127.0.0.1", port=8787)
    cfg = d.status().to_dict()["config"]
    assert cfg["base_url"] == "http://127.0.0.1:8787"
    assert cfg["sandbox_mode"] == "auto"
    assert cfg["enable_gateway"] is False


def test_serve_is_implemented(tmp_path):
    """Phase 1: serve() is real — it must NOT raise NotImplementedError.

    We don't actually bind a port here (that blocks); we assert the method
    exists, is wired to the lazy server module, and builds a valid ASGI app
    for this daemon. The real bind/serve loop is exercised via the HTTP
    endpoint tests (test_daemon_server.py) against a TestClient.
    """
    (tmp_path / ".os_state").mkdir()
    d = Daemon.for_root(tmp_path)
    # serve() must be callable and not the Phase-0 stub.
    import inspect

    src = inspect.getsource(d.serve)
    assert "NotImplementedError" not in src
    # The lazy server module builds a working app from this daemon.
    pytest.importorskip("starlette")
    from research_os.daemon.server import build_app

    app = build_app(d)
    assert app is not None


def test_autoresolve_returns_daemon(monkeypatch, tmp_path):
    """autoresolve uses the server's resolver; force it to tmp_path."""
    monkeypatch.setenv("RESEARCH_OS_WORKSPACE", str(tmp_path))
    d = Daemon.autoresolve()
    assert d.root == tmp_path.resolve()
