"""Daemon stall watcher: flag RUNNING jobs whose log stopped advancing."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.daemon.runstore import RunStore
from research_os.daemon.health_notes import run_self_check


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def _running_run(rs: RunStore, rid: str, log_age_s: float):
    d = rs._run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    rs.write_manifest(rid, {"id": rid, "name": "job", "status": "running",
                            "submitted_at": time.time() - log_age_s,
                            "started_at": time.time() - log_age_s})
    log = d / "log.txt"
    log.write_text("...")
    t = time.time() - log_age_s
    os.utime(log, (t, t))


def test_stalled_run_detected():
    root = _proj()
    rs = RunStore(root)
    _running_run(rs, "run_stuck", log_age_s=3600)  # 1h idle
    stalled = rs.detect_stalled_runs(stall_seconds=1800)
    assert any(s["id"] == "run_stuck" for s in stalled)


def test_fresh_run_not_flagged():
    root = _proj()
    rs = RunStore(root)
    _running_run(rs, "run_fresh", log_age_s=10)  # just started
    assert rs.detect_stalled_runs(stall_seconds=1800) == []


def test_terminal_run_not_flagged():
    root = _proj()
    rs = RunStore(root)
    d = rs._run_dir("run_done")
    d.mkdir(parents=True, exist_ok=True)
    rs.write_manifest("run_done", {"id": "run_done", "status": "succeeded",
                                   "submitted_at": time.time() - 9999})
    assert rs.detect_stalled_runs(stall_seconds=1) == []


def test_self_check_surfaces_stalled():
    root = _proj()
    rs = RunStore(root)
    _running_run(rs, "run_stuck", log_age_s=3600)
    codes = [f["code"] for f in run_self_check(root)["findings"]]
    assert "stalled_runs" in codes
