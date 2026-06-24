"""Notification-outbox sink for sys_notify (reasoning side).

When a daemon is running, ``sys_notify`` should reach the researcher
through the daemon's notification spine (which knows the configured
delivery channel) instead of only appending to a log file nobody tails.
The reasoning layer MUST NOT import ``research_os.daemon`` (the
preflight-enforced seam), so this writes the SAME outbox file by SHAPE —
exactly like ``server/consent.py`` writes/reads the consent ledger.

The daemon owns delivery: it watches the outbox (or the live emit path
does delivery directly). This sink's job is only to durably record the
notification where the daemon's spine can see it. With no daemon present,
the caller keeps its existing log-file behaviour and this sink is a no-op.

stdlib only; fail-safe (any error → silently skip the outbox write, the
log-file path in interaction.notify_researcher still runs).
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

_OUTBOX_SCHEMA = 1


def _outbox_path(root: Path) -> Path:
    from . import daemon_bridge as _bridge

    return _bridge.state_path(root, _bridge.NOTIFICATIONS_OUTBOX)


def _daemon_present(root: Path) -> bool:
    """True iff a daemon is running for this project (descriptor + live PID).

    Delegates to the canonical daemon_bridge.daemon_present — no daemon
    import. Any error → False (degrade: the log-file path still runs).
    """
    from . import daemon_bridge as _bridge

    return _bridge.daemon_present(root)


def sink_notification(
    root: Path,
    message: str,
    level: str,
    *,
    kind: str = "sys_notify",
) -> bool:
    """Append a sys_notify message to the daemon outbox, IF a daemon is up.

    Returns True if the record was written (daemon present + write ok),
    False otherwise (no daemon, or any error). Never raises — the caller's
    log-file notification is the durable fallback.

    The record is marked ``delivered=False`` / delivery not attempted: the
    daemon's spine is responsible for pushing it through the configured
    channel. The reasoning side cannot run the delivery command (it doesn't
    know the daemon config and must not shell out on the agent's behalf).
    """
    try:
        if not _daemon_present(Path(root)):
            return False
        rec = {
            "schema": _OUTBOX_SCHEMA,
            "id": "ntfy_" + secrets.token_hex(4),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "kind": kind,
            "level": level if level in {"info", "action_required", "warn"} else "info",
            "title": message[:120],
            "body": message,
            "context": {"source": "sys_notify"},
            "delivered": False,
            "delivery": {"attempted": False, "ok": None,
                         "detail": "queued by sys_notify; daemon delivers"},
        }
        path = _outbox_path(Path(root))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, separators=(",", ":")) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except (OSError, ValueError):
        return False
