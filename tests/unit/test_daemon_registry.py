"""Unit tests for the daemon workspace registry (Phase 1)."""
from __future__ import annotations

from research_os.daemon.registry import Workspace, WorkspaceRegistry


def test_uninitialized_workspace_state(tmp_path):
    ws = Workspace(tmp_path)
    state = ws.state()
    assert state["initialized"] is False
    assert state["root"] == str(tmp_path.resolve())
    assert state["active_protocol"] is None
    assert any("no .os_state" in n for n in state["notes"])


def test_initialized_workspace_reads_state(tmp_path):
    (tmp_path / ".os_state").mkdir()
    ws = Workspace(tmp_path)
    state = ws.state()
    assert state["initialized"] is True
    # active_protocol/progress/ledger are best-effort; just ensure shape.
    assert "progress" in state
    assert "ledger" in state
    assert "notes" in state


def test_state_is_cached_within_ttl(tmp_path):
    ws = Workspace(tmp_path, cache_ttl=100.0)
    first = ws.state()
    second = ws.state()
    # Same cached object returned within TTL.
    assert first is second
    forced = ws.state(force=True)
    assert forced is not first


def test_registry_register_is_idempotent(tmp_path):
    reg = WorkspaceRegistry()
    a = reg.register(tmp_path)
    b = reg.register(tmp_path)
    assert a is b
    assert reg.roots() == [str(tmp_path.resolve())]


def test_registry_get_resolves_path(tmp_path):
    reg = WorkspaceRegistry()
    reg.register(tmp_path)
    assert reg.get(tmp_path) is not None
    assert reg.get(str(tmp_path)) is not None
    assert reg.get(tmp_path / "nope") is None


def test_registry_snapshot_multi_root(tmp_path):
    reg = WorkspaceRegistry()
    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir()
    p2.mkdir()
    reg.register(p1)
    reg.register(p2)
    snap = reg.snapshot()
    assert snap["count"] == 2
    roots = {r["root"] for r in snap["roots"]}
    assert roots == {str(p1.resolve()), str(p2.resolve())}


def test_state_never_raises_on_broken_os_state(tmp_path):
    # .os_state exists but is empty/garbage — reads must degrade to notes.
    (tmp_path / ".os_state").mkdir()
    (tmp_path / ".os_state" / "state_ledger.json").write_text("{ not json")
    ws = Workspace(tmp_path)
    state = ws.state()  # must not raise
    assert state["initialized"] is True
