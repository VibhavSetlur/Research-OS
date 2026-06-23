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


# ── lineage / staleness / rebuild-plan endpoints (Phase 1.17) ─────────
@pytest.fixture
def chain_client(tmp_path):
    """A daemon whose journal holds a real 2-run chain A -> B.

    A produces model.txt (hash H1); B records model.txt (H1) as an input
    and produces result.txt. The content-addressed link falls out of the
    matching hash, exactly as in production.
    """
    from research_os.daemon.runstore import build_manifest

    (tmp_path / ".os_state").mkdir()
    daemon = Daemon.for_root(tmp_path)
    store = daemon.runstore
    assert store is not None

    h1 = "sha256:" + "a" * 64  # A's output == B's input
    a = build_manifest(
        run_id="aaaa1111", name="buildA", kind="subprocess",
        status="succeeded", root=str(tmp_path),
        provenance={"inputs": {"data.csv": "sha256:" + "d" * 64}},
        artifacts=[{"path": "model.txt", "sha256": h1, "change": "created"}],
        submitted_at=100.0,
    )
    b = build_manifest(
        run_id="bbbb2222", name="buildB", kind="subprocess",
        status="succeeded", root=str(tmp_path),
        provenance={"inputs": {"model.txt": h1}},
        artifacts=[{"path": "result.txt",
                    "sha256": "sha256:" + "c" * 64, "change": "created"}],
        submitted_at=200.0,
    )
    store.write_manifest("aaaa1111", a)
    store.write_manifest("bbbb2222", b)
    return TestClient(build_app(daemon)), daemon, tmp_path


def test_lineage_endpoint_builds_graph(chain_client):
    c, _, _ = chain_client
    r = c.get("/v1/lineage")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["counts"]["runs"] == 2
    assert body["counts"]["edges"] == 1
    assert body["counts"]["linked"] == 2


def test_lineage_focus_returns_ancestors(chain_client):
    c, _, _ = chain_client
    r = c.get("/v1/lineage", params={"run_id": "bbbb2222"})
    assert r.status_code == 200
    focus = r.json()["focus"]
    assert focus["run_id"] == "bbbb2222"
    assert "aaaa1111" in focus["ancestors"]


def test_staleness_endpoint_flags_changed_input(chain_client):
    c, _, tmp_path = chain_client
    # data.csv doesn't exist on disk -> A is input-stale (recorded hash,
    # missing file) -> B is transitive-stale.
    r = c.get("/v1/staleness")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["counts"]["total"] == 2
    assert set(body["stale"]) == {"aaaa1111", "bbbb2222"}


def test_rebuild_plan_orders_producers_first(chain_client):
    c, _, _ = chain_client
    r = c.get("/v1/rebuild/plan")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    # producer (A) must precede consumer (B).
    assert body["plan"] == ["aaaa1111", "bbbb2222"]
    assert body["counts"]["planned"] == 2
    assert "dry-run" in body["note"]


def test_lineage_bad_limit_is_400(chain_client):
    c, _, _ = chain_client
    r = c.get("/v1/lineage", params={"limit": "xyz"})
    assert r.status_code == 400


def test_endpoints_unavailable_without_runstore(tmp_path):
    # A daemon with no resolved root has no runstore -> graceful "available: False".
    daemon = Daemon.for_root(None)
    if daemon.runstore is not None:
        pytest.skip("daemon resolved a runstore; not the no-root case")
    c = TestClient(build_app(daemon))
    for path in ("/v1/lineage", "/v1/staleness", "/v1/rebuild/plan"):
        body = c.get(path).json()
        assert body["available"] is False

