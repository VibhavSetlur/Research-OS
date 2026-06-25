"""Notification spine — the daemon's channel to reach the researcher.

docs/NOTIFICATION_SPINE.md. Every notification flows through one durable
append-only outbox (.os_state/notifications/outbox.jsonl) and is optionally
pushed via a researcher-configured notify_command (JSON on stdin). The
outbox is the source of truth; delivery is best-effort and recorded.

These tests drive the daemon-side emit/read + delivery, the job-terminal
helper, and the reasoning-side sys_notify sink (which writes the same
outbox by shape when a daemon is present).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from research_os.daemon import notifications as ntfy


def _outbox(root: Path) -> Path:
    return root / ".os_state" / "notifications" / "outbox.jsonl"


# --- emit + outbox ---------------------------------------------------------

def test_emit_writes_outbox_record(tmp_path):
    rec = ntfy.emit(tmp_path, kind="info", title="hello", body="world")
    assert rec["title"] == "hello"
    assert _outbox(tmp_path).exists()
    lines = _outbox(tmp_path).read_text().strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["kind"] == "info"
    assert stored["delivered"] is False  # no notify_command


def test_emit_normalises_bad_level(tmp_path):
    rec = ntfy.emit(tmp_path, kind="info", title="t", level="bogus")
    assert rec["level"] == "info"


def test_emit_appends_multiple(tmp_path):
    ntfy.emit(tmp_path, kind="info", title="a")
    ntfy.emit(tmp_path, kind="info", title="b")
    recs = ntfy.read_outbox(tmp_path)
    assert [r["title"] for r in recs] == ["a", "b"]


# --- delivery via notify_command ------------------------------------------

def test_delivery_runs_command_and_records_success(tmp_path):
    # A command that captures stdin to a file and exits 0.
    sink = tmp_path / "got.json"
    cmd = f"cat > {sink}"
    rec = ntfy.emit(tmp_path, kind="job.succeeded", title="done",
                    notify_command=cmd)
    assert rec["delivered"] is True
    assert rec["delivery"]["ok"] is True
    # The command received the notification JSON on stdin.
    delivered = json.loads(sink.read_text())
    assert delivered["title"] == "done"


def test_delivery_failure_is_recorded_not_raised(tmp_path):
    rec = ntfy.emit(tmp_path, kind="info", title="t",
                    notify_command="exit 3")
    assert rec["delivered"] is False
    assert rec["delivery"]["attempted"] is True
    assert rec["delivery"]["ok"] is False
    # Outbox record still persisted despite delivery failure.
    assert len(ntfy.read_outbox(tmp_path)) == 1


def test_missing_command_is_no_delivery(tmp_path):
    rec = ntfy.emit(tmp_path, kind="info", title="t", notify_command="")
    assert rec["delivery"]["attempted"] is False


# --- read_outbox -----------------------------------------------------------

def test_read_outbox_missing_is_empty(tmp_path):
    assert ntfy.read_outbox(tmp_path) == []


def test_read_outbox_skips_garbage_lines(tmp_path):
    p = _outbox(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text('{"id":"a","title":"ok","delivered":true}\n'
                 "{ not json\n"
                 '{"id":"b","title":"ok2","delivered":false}\n')
    recs = ntfy.read_outbox(tmp_path)
    assert [r["id"] for r in recs] == ["a", "b"]


def test_read_outbox_undelivered_filter(tmp_path):
    ntfy.emit(tmp_path, kind="info", title="x", notify_command="cat >/dev/null")
    ntfy.emit(tmp_path, kind="info", title="y")  # not delivered
    undel = ntfy.read_outbox(tmp_path, undelivered_only=True)
    assert [r["title"] for r in undel] == ["y"]


# --- job-terminal helper ---------------------------------------------------

def test_emit_job_terminal_succeeded(tmp_path):
    job = {"id": "j1", "name": "fit", "status": "succeeded",
           "started_at": 100.0, "finished_at": 100.0 + 95}
    rec = ntfy.emit_job_terminal(tmp_path, job)
    assert rec is not None
    assert rec["kind"] == "job.succeeded"
    assert "1m35s" in rec["body"]
    assert rec["level"] == "info"


def test_emit_job_terminal_failed_is_action_required(tmp_path):
    job = {"id": "j2", "name": "sweep", "status": "failed",
           "error": "boom"}
    rec = ntfy.emit_job_terminal(tmp_path, job)
    assert rec is not None
    assert rec["level"] == "action_required"
    assert "boom" in rec["body"]


def test_emit_job_terminal_ignores_nonterminal(tmp_path):
    assert ntfy.emit_job_terminal(tmp_path, {"status": "running"}) is None
    assert ntfy.emit_job_terminal(tmp_path, {"status": "queued"}) is None


# --- reasoning-side sink (sys_notify -> outbox when daemon present) --------

def _write_daemon_descriptor(root: Path):
    st = root / ".os_state"
    st.mkdir(parents=True, exist_ok=True)
    (st / "daemon.json").write_text(json.dumps({"pid": os.getpid(), "port": 8787}))


def test_sink_writes_outbox_when_daemon_present(tmp_path):
    from research_os.server.notify_sink import sink_notification

    _write_daemon_descriptor(tmp_path)
    assert sink_notification(tmp_path, "page me", "action_required") is True
    recs = ntfy.read_outbox(tmp_path)
    assert len(recs) == 1
    assert recs[0]["body"] == "page me"
    assert recs[0]["level"] == "action_required"
    assert recs[0]["delivered"] is False  # daemon delivers, not the sink


def test_sink_noop_when_no_daemon(tmp_path):
    from research_os.server.notify_sink import sink_notification

    assert sink_notification(tmp_path, "msg", "info") is False
    assert ntfy.read_outbox(tmp_path) == []


def test_sink_noop_when_dead_daemon_pid(tmp_path):
    from research_os.server.notify_sink import sink_notification

    st = tmp_path / ".os_state"
    st.mkdir(parents=True)
    # A PID that is almost certainly not alive.
    (st / "daemon.json").write_text(json.dumps({"pid": 2_000_000_000, "port": 1}))
    assert sink_notification(tmp_path, "msg", "info") is False


# --- end-to-end: notify_researcher feeds both log + spine -----------------

def test_notify_researcher_uses_spine_when_daemon_present(tmp_path):
    from research_os.tools.actions.state.interaction import notify_researcher

    _write_daemon_descriptor(tmp_path)
    res = notify_researcher("done", "info", tmp_path)
    assert res["status"] == "success"
    assert res["delivered_to_spine"] is True
    # Log file ALSO written (durable fallback preserved).
    log = tmp_path / "workspace" / "logs" / "notifications.log"
    assert log.exists() and "done" in log.read_text()
    # And the outbox carries it.
    assert len(ntfy.read_outbox(tmp_path)) == 1


def test_notify_researcher_log_only_without_daemon(tmp_path):
    from research_os.tools.actions.state.interaction import notify_researcher

    res = notify_researcher("hi", "info", tmp_path)
    assert res["status"] == "success"
    assert res["delivered_to_spine"] is False
    assert ntfy.read_outbox(tmp_path) == []


# --- interrupted-runs notification (the "walked away, box rebooted" case) ---

def test_emit_runs_interrupted_writes_action_required_record(tmp_path):
    rec = ntfy.emit_runs_interrupted(tmp_path, ["run_a", "run_b"])
    assert rec is not None
    assert rec["kind"] == "runs.interrupted"
    assert rec["level"] == "action_required"
    assert rec["context"]["count"] == 2
    assert rec["context"]["run_ids"] == ["run_a", "run_b"]
    # Persisted to the durable outbox.
    out = ntfy.read_outbox(tmp_path)
    assert len(out) == 1 and out[0]["kind"] == "runs.interrupted"


def test_emit_runs_interrupted_noop_on_empty(tmp_path):
    assert ntfy.emit_runs_interrupted(tmp_path, []) is None
    assert ntfy.read_outbox(tmp_path) == []
