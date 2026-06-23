"""Endpoint tests for the daemon HTTP server (Phase 1, read-only API).

Skipped automatically when the optional [daemon] web stack isn't installed,
so the suite still passes on a core-only install.
"""
from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from research_os.daemon import Daemon  # noqa: E402
from research_os.daemon.server import build_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    (tmp_path / ".os_state").mkdir()
    daemon = Daemon.for_root(tmp_path)
    return TestClient(build_app(daemon)), daemon


def test_healthz(client):
    c, _ = client
    r = c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "research-os-daemon"
    assert "version" in body
    assert body["serving"] is False  # TestClient doesn't flip serving


def test_state_multi_root(client, tmp_path):
    c, _ = client
    r = c.get("/v1/state")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["roots"][0]["initialized"] is True


def test_state_single_root_filter(client, tmp_path):
    c, _ = client
    r = c.get("/v1/state", params={"root": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()["root"]["initialized"] is True


def test_state_unknown_root_registers_and_returns(client, tmp_path):
    c, _ = client
    other = tmp_path.parent / "not_a_project_xyz"
    r = c.get("/v1/state", params={"root": str(other)})
    assert r.status_code == 200
    assert r.json()["root"]["initialized"] is False


def test_jobs_empty(client):
    c, _ = client
    r = c.get("/v1/jobs")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_jobs_reflects_submitted_job(client):
    c, daemon = client
    daemon.tasks.start()
    try:
        daemon.tasks.submit(lambda: 1, name="probe")
        r = c.get("/v1/jobs")
        assert r.status_code == 200
        assert r.json()["total"] == 1
    finally:
        daemon.tasks.shutdown()


def test_job_not_found(client):
    c, _ = client
    r = c.get("/v1/jobs/nope")
    assert r.status_code == 404


def test_jobs_bad_limit(client):
    c, _ = client
    r = c.get("/v1/jobs", params={"limit": "abc"})
    assert r.status_code == 400


def test_require_web_stack_message():
    # The install hint must name the [daemon] extra.
    from research_os.daemon.server import _INSTALL_HINT

    assert "research-os[daemon]" in _INSTALL_HINT
