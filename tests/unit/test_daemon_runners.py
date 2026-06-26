"""Unit tests for the daemon execution runners (Phase 1.6 — any language)."""
from __future__ import annotations

import sys
import threading
import time

from research_os.daemon.runners import RunResult, SubprocessRunner


def test_runresult_ok_and_to_dict():
    r = RunResult(returncode=0, cmd=["x"], cwd=None, duration_s=1.234)
    assert r.ok is True
    d = r.to_dict()
    assert d["returncode"] == 0
    assert d["ok"] is True
    assert d["duration_s"] == 1.234
    r2 = RunResult(returncode=1, cmd=["x"], cwd=None, duration_s=0)
    assert r2.ok is False
    r3 = RunResult(returncode=0, cmd=["x"], cwd=None, duration_s=0, cancelled=True)
    assert r3.ok is False  # cancelled is never ok


def test_subprocess_success_captures_output():
    runner = SubprocessRunner([sys.executable, "-c", "print('hi'); print('there')"])
    out = runner()
    assert out["returncode"] == 0
    assert out["ok"] is True
    assert "hi" in out["stdout_tail"]
    assert "there" in out["stdout_tail"]


def test_subprocess_captures_stderr_and_exit_code():
    runner = SubprocessRunner(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"]
    )
    out = runner()
    assert out["returncode"] == 3
    assert out["ok"] is False
    assert "boom" in out["stderr_tail"]


def test_subprocess_emits_log_events():
    runner = SubprocessRunner([sys.executable, "-c", "print('a'); print('b')"])
    events: list[tuple[str, str]] = []

    def emit(kind, data):
        events.append((data["channel"], data["line"]))

    runner(emit=emit)
    lines = [line for _ch, line in events]
    assert "a" in lines and "b" in lines


def test_subprocess_string_cmd_is_split():
    runner = SubprocessRunner(f"{sys.executable} -c print(1)")
    assert runner.cmd[0] == sys.executable
    assert "-c" in runner.cmd


def test_subprocess_tail_is_bounded():
    runner = SubprocessRunner(
        [sys.executable, "-c", "[print(i) for i in range(100)]"],
        tail_lines=10,
    )
    out = runner()
    assert len(out["stdout_tail"]) == 10
    assert out["truncated"] is True
    # keeps the LAST lines
    assert "99" in out["stdout_tail"]
    assert "0" not in out["stdout_tail"]


def test_subprocess_cancel_terminates_quickly():
    runner = SubprocessRunner(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        kill_grace_s=2.0,
    )
    cancel = threading.Event()
    result: dict = {}

    def run():
        result.update(runner(cancel_event=cancel))

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.5)
    start = time.time()
    cancel.set()
    t.join(timeout=8)
    elapsed = time.time() - start
    assert not t.is_alive(), "runner did not stop after cancel"
    assert elapsed < 5, f"cancel took too long: {elapsed}s"
    assert result.get("cancelled") is True


def test_subprocess_env_is_passed():
    runner = SubprocessRunner(
        [sys.executable, "-c", "import os; print(os.environ.get('RO_TEST_VAR'))"],
        env={"RO_TEST_VAR": "spice"},
    )
    out = runner()
    assert "spice" in out["stdout_tail"]
