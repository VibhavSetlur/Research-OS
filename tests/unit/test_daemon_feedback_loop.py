"""Daemon feedback loop: per-turn alert backstop + persistent-block escalation."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.server.daemon_alert import daemon_alert
from research_os.daemon.health_notes import write_notes
from research_os.daemon.notifications import _outbox_path


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def _notes(root: Path, findings, ok=False):
    (root / ".os_state" / "daemon_notes.json").write_text(json.dumps({
        "schema": 1, "checked_at": time.time(), "ok": ok, "findings": findings,
    }))


def test_daemon_alert_fires_once_per_fresh_run():
    root = _proj()
    _notes(root, [{"severity": "block", "code": "input_drift", "message": "stale"}])
    first = daemon_alert(root)
    assert first is not None and first["severity"] == "block"
    assert daemon_alert(root) is None  # same run → suppressed


def test_daemon_alert_rearms_on_newer_check():
    root = _proj()
    _notes(root, [{"severity": "warn", "code": "abandoned_protocols", "message": "x"}])
    assert daemon_alert(root) is not None
    assert daemon_alert(root) is None
    time.sleep(0.01)
    _notes(root, [{"severity": "warn", "code": "abandoned_protocols", "message": "x"}])
    assert daemon_alert(root) is not None  # newer checked_at re-arms


def test_daemon_alert_silent_with_no_notes():
    assert daemon_alert(_proj()) is None


def test_daemon_alert_ignores_info_only():
    root = _proj()
    _notes(root, [{"severity": "info", "code": "intake_unframed", "message": "x"}], ok=True)
    assert daemon_alert(root) is None


def test_persistent_block_escalates_once_then_rearms():
    root = _proj()

    def block():
        return [{"severity": "block", "code": "input_drift", "message": "stale"}]

    def n():
        p = _outbox_path(root)
        return len([x for x in p.read_text().splitlines() if x.strip()]) if p.exists() else 0

    for _ in range(2):
        write_notes(root, {"schema": 1, "checked_at": time.time(), "ok": False,
                           "findings": block()})
    assert n() == 0  # not yet
    write_notes(root, {"schema": 1, "checked_at": time.time(), "ok": False,
                       "findings": block()})
    assert n() == 1  # escalated at 3
    write_notes(root, {"schema": 1, "checked_at": time.time(), "ok": False,
                       "findings": block()})
    assert n() == 1  # no re-page
    # clear, then recur → re-escalates
    write_notes(root, {"schema": 1, "checked_at": time.time(), "ok": True, "findings": []})
    for _ in range(3):
        write_notes(root, {"schema": 1, "checked_at": time.time(), "ok": False,
                           "findings": block()})
    assert n() == 2
