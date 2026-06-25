"""Staleness floor gate: don't ship a deliverable built on changed data.

docs/STALENESS_GATE.md. The daemon detects when a run's recorded inputs
changed on disk and persists a verdict to .os_state/staleness/verdict.json;
server/staleness_state.py reads it by shape (no daemon import) and the
gate (declared in guidance/autopilot.yaml as a world_state predicate)
fires on tool_typst_compile when the project is currently stale.

These tests drive the reader + the gate_spec world_state predicate + the
full enforce path directly, plus the daemon-side verdict writer.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from research_os.server import gate_spec as gs
from research_os.server import staleness_state as ss


def _write_verdict(root: Path, status: str, *, assessed_at: str | None = None,
                   stale_runs=None, stale_outputs=None) -> None:
    d = root / ".os_state" / "staleness"
    d.mkdir(parents=True, exist_ok=True)
    v = {
        "schema": 1,
        "status": status,
        "counts": {"total": 1, "stale": 1 if status == "stale" else 0,
                   "fresh": 0, "unknown": 0},
        "stale_runs": stale_runs or (["run_01"] if status == "stale" else []),
        "stale_outputs": stale_outputs or (["data.csv"] if status == "stale" else []),
    }
    if assessed_at is not None:
        v["assessed_at"] = assessed_at
    (d / "verdict.json").write_text(json.dumps(v))


def _write_run(root: Path, rid: str = "run_01") -> None:
    rd = root / ".os_state" / "runs" / rid
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "run.json").write_text(json.dumps({"id": rid, "status": "completed"}))


# --- reader: fail-safe direction ------------------------------------------

def test_no_verdict_is_not_stale(tmp_path):
    assert ss.is_currently_stale(tmp_path) is False
    assert ss.current_stale_verdict(tmp_path) is None


def test_fresh_verdict_is_not_stale(tmp_path):
    _write_verdict(tmp_path, "fresh")
    assert ss.is_currently_stale(tmp_path) is False


def test_stale_verdict_is_stale(tmp_path):
    _write_verdict(tmp_path, "stale")
    assert ss.is_currently_stale(tmp_path) is True
    v = ss.current_stale_verdict(tmp_path)
    assert v is not None and v["stale_outputs"] == ["data.csv"]


def test_garbage_verdict_is_not_stale(tmp_path):
    d = tmp_path / ".os_state" / "staleness"
    d.mkdir(parents=True)
    (d / "verdict.json").write_text("{ not json")
    assert ss.is_currently_stale(tmp_path) is False


def test_wrong_schema_verdict_is_not_stale(tmp_path):
    d = tmp_path / ".os_state" / "staleness"
    d.mkdir(parents=True)
    (d / "verdict.json").write_text(json.dumps({"schema": 99, "status": "stale"}))
    assert ss.is_currently_stale(tmp_path) is False


def test_stale_verdict_older_than_newest_run_is_ignored(tmp_path):
    # A verdict assessed in the distant past, then a run written now → the
    # verdict predates current state → treated as no-claim.
    _write_verdict(tmp_path, "stale", assessed_at="2000-01-01T00:00:00Z")
    time.sleep(0.01)
    _write_run(tmp_path)  # newer than the verdict
    assert ss.is_currently_stale(tmp_path) is False


def test_recent_stale_verdict_with_old_run_still_stale(tmp_path):
    _write_run(tmp_path)
    time.sleep(0.01)
    # verdict assessed now (newer than the run) → still a valid claim
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_verdict(tmp_path, "stale", assessed_at=now)
    assert ss.is_currently_stale(tmp_path) is True


# --- gate_spec world_state predicate --------------------------------------

def test_world_state_predicate_fires_when_stale(tmp_path):
    _write_verdict(tmp_path, "stale")
    assert gs._match_predicate({"world_state": "no_stale_inputs"}, {}, tmp_path) is True


def test_world_state_predicate_silent_when_fresh(tmp_path):
    _write_verdict(tmp_path, "fresh")
    assert gs._match_predicate({"world_state": "no_stale_inputs"}, {}, tmp_path) is False


def test_world_state_predicate_no_root_does_not_fire():
    assert gs._match_predicate({"world_state": "no_stale_inputs"}, {}, None) is False


def test_unknown_world_state_kind_fails_closed(tmp_path):
    _write_verdict(tmp_path, "stale")
    assert gs._match_predicate({"world_state": "bogus_kind"}, {}, tmp_path) is False


# --- most-specific gate resolution ----------------------------------------

def test_stale_inputs_gate_wins_over_unconditional_compile_gate(tmp_path):
    """When inputs are stale, tool_typst_compile resolves to the staleness
    gate (specific) not the unconditional one — so the firing reason is
    the real risk."""
    _write_verdict(tmp_path, "stale")
    g = gs.resolve_declared_gate("tool_typst_compile", {}, tmp_path)
    assert g is not None and g["key"] == "tool_typst_compile:stale_inputs"


def test_fresh_resolves_to_unconditional_compile_gate(tmp_path):
    _write_verdict(tmp_path, "fresh")
    g = gs.resolve_declared_gate("tool_typst_compile", {}, tmp_path)
    assert g is not None and g["key"] == "tool_typst_compile"


# --- full enforce path -----------------------------------------------------

def test_compile_blocked_when_stale_with_daemon(tmp_path):
    """Under a daemon + stale verdict, the compile is gated; with no token
    it refuses (the un-skippable layer applies to the staleness gate too)."""
    import os

    import yaml

    from research_os.server.autopilot_gate import enforce_autopilot_gate
    from research_os.server.errors import RoError

    (tmp_path / "inputs").mkdir(parents=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"interaction": {"autonomy_level": "autopilot"}})
    )
    st = tmp_path / ".os_state"
    st.mkdir(exist_ok=True)
    (st / "daemon.json").write_text(json.dumps({"pid": os.getpid(), "port": 8787}))
    _write_verdict(tmp_path, "stale")

    with pytest.raises(RoError) as exc:
        enforce_autopilot_gate("tool_typst_compile", {}, tmp_path)
    assert exc.value.what == "consent_required"


def test_compile_stale_gate_degrades_without_daemon(tmp_path):
    """No daemon → staleness gate degrades to confirmed=true (today's flow).

    The unconditional compile gate still fires, but confirmed=true clears
    it — proving the staleness addition didn't change the no-daemon path.
    """
    import yaml

    from research_os.server.autopilot_gate import enforce_autopilot_gate

    (tmp_path / "inputs").mkdir(parents=True)
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump({"interaction": {"autonomy_level": "autopilot"}})
    )
    _write_verdict(tmp_path, "stale")  # stale, but NO daemon descriptor
    # No RoError: confirmed=true clears the gate in the degrade path.
    enforce_autopilot_gate("tool_typst_compile", {"confirmed": True}, tmp_path)


# --- daemon-side verdict writer -------------------------------------------

def test_write_verdict_round_trips():
    from research_os.daemon import staleness as dstale

    report = {
        "runs": {"r1": {"status": "input-stale", "changed": [{"path": "x.csv"}],
                        "missing": []}},
        "stale": ["r1"], "fresh": [], "unknown": [],
        "counts": {"total": 1, "stale": 1, "fresh": 0, "unknown": 0},
    }
    import tempfile
    root = Path(tempfile.mkdtemp())
    path = dstale.write_verdict(root, report)
    assert path.exists()
    v = json.loads(path.read_text())
    assert v["status"] == "stale"
    assert v["stale_outputs"] == ["x.csv"]
    assert "assessed_at" in v
    # the reader agrees
    assert ss.is_currently_stale(root) is True


def test_write_verdict_fresh_when_no_stale_runs():
    from research_os.daemon import staleness as dstale

    report = {"runs": {}, "stale": [], "fresh": [], "unknown": [],
              "counts": {"total": 0, "stale": 0, "fresh": 0, "unknown": 0}}
    import tempfile
    root = Path(tempfile.mkdtemp())
    dstale.write_verdict(root, report)
    assert ss.is_currently_stale(root) is False
