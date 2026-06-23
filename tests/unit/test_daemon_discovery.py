"""Tests for the daemon discovery handshake (Phase 3)."""
from __future__ import annotations

import json
import os

from research_os.daemon import discovery


def test_write_read_roundtrip(tmp_path):
    discovery.write_discovery(
        tmp_path,
        host="127.0.0.1",
        port=8787,
        version="9.9.9",
        started_at="2026-06-23T00:00:00+00:00",
    )
    p = discovery.discovery_path(tmp_path)
    assert p.exists()
    data = discovery.read_discovery(tmp_path)
    assert data is not None
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8787
    assert data["version"] == "9.9.9"
    assert data["pid"] == os.getpid()
    assert data["base_url"] == "http://127.0.0.1:8787"
    assert data["schema"] == discovery.DISCOVERY_SCHEMA


def test_write_is_atomic_no_tmp_left(tmp_path):
    discovery.write_discovery(
        tmp_path, host="h", port=1, version="v", started_at="t"
    )
    # The .json.tmp sibling must not linger after an atomic replace.
    tmp = discovery.discovery_path(tmp_path).with_suffix(".json.tmp")
    assert not tmp.exists()


def test_clear_is_idempotent(tmp_path):
    # Clearing when nothing exists must not raise.
    discovery.clear_discovery(tmp_path)
    discovery.write_discovery(
        tmp_path, host="h", port=1, version="v", started_at="t"
    )
    assert discovery.discovery_path(tmp_path).exists()
    discovery.clear_discovery(tmp_path)
    assert not discovery.discovery_path(tmp_path).exists()
    # Second clear is a no-op, still no raise.
    discovery.clear_discovery(tmp_path)


def test_read_missing_returns_none(tmp_path):
    assert discovery.read_discovery(tmp_path) is None


def test_read_corrupt_returns_none(tmp_path):
    p = discovery.discovery_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    assert discovery.read_discovery(tmp_path) is None


def test_read_non_dict_returns_none(tmp_path):
    p = discovery.discovery_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert discovery.read_discovery(tmp_path) is None


def test_pid_alive_self_true():
    assert discovery.pid_alive(os.getpid()) is True


def test_pid_alive_dead_false():
    # PID 0 / a very high unlikely pid -> not a live process we can signal.
    assert discovery.pid_alive(2**31 - 1) is False


def test_pid_alive_garbage_false():
    assert discovery.pid_alive("not-a-pid") is False  # type: ignore[arg-type]
