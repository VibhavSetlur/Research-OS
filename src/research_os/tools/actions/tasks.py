"""Real background tasks — subprocess.Popen with persisted PID and tail logs.

Designed for shared-server workflows: a long-running script gets backgrounded
so the conversation doesn't block. The AI polls `tool_task_status` instead of
waiting. State persists to ``.os_state/tasks/`` so tasks survive a server
restart (you can still query status by PID).
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.tasks")

TASKS_DIR_NAME = "tasks"


def _tasks_dir(root: Path) -> Path:
    d = root / ".os_state" / TASKS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(task_path: Path, data: dict[str, Any]) -> None:
    task_path.write_text(json.dumps(data, indent=2, default=str))


def _load(task_path: Path) -> dict[str, Any] | None:
    if not task_path.exists():
        return None
    try:
        return json.loads(task_path.read_text())
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def task_run(command: str | list[str], root: Path, *, cwd: str | None = None,
             description: str = "") -> dict[str, Any]:
    """Spawn a real background subprocess and return its task_id immediately.

    ``command`` can be a string (shell-tokenised) or a list of argv items.
    stdout + stderr are tee'd to ``.os_state/tasks/<id>.log``.
    """
    try:
        task_id = f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        tasks_dir = _tasks_dir(root)
        log_path = tasks_dir / f"{task_id}.log"
        meta_path = tasks_dir / f"{task_id}.json"

        if isinstance(command, str):
            argv = shlex.split(command)
        else:
            argv = list(command)

        # Resolve cwd against root if relative.
        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute():
                cwd_path = root / cwd_path
            cwd_str = str(cwd_path)
        else:
            cwd_str = str(root)

        log_file = open(log_path, "w")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd_str,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as e:
            log_file.close()
            return {"status": "error", "message": f"Command not found: {e}"}

        meta = {
            "task_id": task_id,
            "command": " ".join(shlex.quote(a) for a in argv),
            "argv": argv,
            "cwd": cwd_str,
            "description": description,
            "pid": proc.pid,
            "started_at": _now(),
            "status": "running",
            "log_path": str(log_path.relative_to(root)),
        }
        _save(meta_path, meta)
        # Don't wait — return immediately. The file handle stays open in the
        # subprocess; the parent reference is fine to drop.
        return {
            "status": "success",
            "task_id": task_id,
            "pid": proc.pid,
            "log_path": meta["log_path"],
            "message": f"Started background task {task_id} (pid {proc.pid}).",
        }
    except Exception as e:
        logger.exception("task_run failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Status / list / kill
# ---------------------------------------------------------------------------


def task_status(task_id: str, root: Path, *, tail_lines: int = 50) -> dict[str, Any]:
    """Return current status + tail of log for a task."""
    try:
        meta_path = _tasks_dir(root) / f"{task_id}.json"
        meta = _load(meta_path)
        if not meta:
            return {"status": "error", "message": f"Unknown task {task_id}"}

        pid = meta.get("pid", 0)
        alive = _pid_alive(pid)
        log_path = root / meta.get("log_path", f".os_state/tasks/{task_id}.log")

        tail = ""
        if log_path.exists():
            try:
                with open(log_path) as f:
                    lines = f.readlines()
                tail = "".join(lines[-tail_lines:])
            except Exception:
                tail = ""

        current_status = "running" if alive else "finished"
        if meta.get("status") != current_status:
            meta["status"] = current_status
            if not alive:
                meta["finished_at"] = _now()
            _save(meta_path, meta)

        return {
            "status": "success",
            "task_id": task_id,
            "task_status": current_status,
            "pid": pid,
            "started_at": meta.get("started_at"),
            "finished_at": meta.get("finished_at"),
            "command": meta.get("command"),
            "description": meta.get("description"),
            "log_path": meta.get("log_path"),
            "log_tail": tail,
        }
    except Exception as e:
        logger.exception("task_status failed")
        return {"status": "error", "message": str(e)}


def task_list(root: Path) -> dict[str, Any]:
    """List every known task with a live-status check."""
    try:
        out: list[dict[str, Any]] = []
        for meta_path in sorted(_tasks_dir(root).glob("task_*.json")):
            meta = _load(meta_path)
            if not meta:
                continue
            pid = meta.get("pid", 0)
            alive = _pid_alive(pid)
            meta["task_status"] = "running" if alive else "finished"
            out.append(
                {
                    "task_id": meta["task_id"],
                    "pid": pid,
                    "task_status": meta["task_status"],
                    "started_at": meta.get("started_at"),
                    "description": meta.get("description"),
                    "command": meta.get("command"),
                }
            )
        return {"status": "success", "count": len(out), "tasks": out}
    except Exception as e:
        logger.exception("task_list failed")
        return {"status": "error", "message": str(e)}


def task_kill(task_id: str, root: Path, *, signal_name: str = "TERM") -> dict[str, Any]:
    """Kill a background task (SIGTERM by default; pass signal_name='KILL' for hard)."""
    try:
        meta_path = _tasks_dir(root) / f"{task_id}.json"
        meta = _load(meta_path)
        if not meta:
            return {"status": "error", "message": f"Unknown task {task_id}"}

        pid = meta.get("pid", 0)
        if not pid:
            return {"status": "error", "message": "No PID recorded for task"}
        if not _pid_alive(pid):
            meta["status"] = "finished"
            _save(meta_path, meta)
            return {"status": "success", "message": "Task already finished."}

        sig = getattr(signal, f"SIG{signal_name.upper()}", signal.SIGTERM)
        try:
            os.killpg(os.getpgid(pid), sig)
        except (PermissionError, ProcessLookupError, OSError):
            try:
                os.kill(pid, sig)
            except (PermissionError, ProcessLookupError, OSError) as e:
                return {"status": "error", "message": f"Could not kill {pid}: {e}"}

        # Give it a moment to exit gracefully.
        time.sleep(0.4)
        meta["status"] = "killed" if not _pid_alive(pid) else "kill_requested"
        meta["finished_at"] = _now()
        _save(meta_path, meta)
        return {"status": "success", "task_id": task_id, "task_status": meta["status"]}
    except Exception as e:
        logger.exception("task_kill failed")
        return {"status": "error", "message": str(e)}
