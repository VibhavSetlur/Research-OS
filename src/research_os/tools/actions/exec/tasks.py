"""Real background tasks — subprocess.Popen with persisted PID and tail logs.

Designed for shared-server workflows: a long-running script gets backgrounded
so the conversation doesn't block. The AI polls `tool_task_status` instead of
waiting. State persists to ``.os_state/tasks/`` so tasks survive a server
restart (you can still query status by PID).

Security model (configurable via researcher_config.runtime):
  command_allowlist     list of allowed argv[0] binaries (basename match).
                        Default = common interpreters + git + a small set.
  allow_arbitrary       bool. When true, allowlist check is skipped.
  max_cpu_seconds       per-process CPU time cap (setrlimit RLIMIT_CPU).
  max_memory_mb         per-process RSS cap (setrlimit RLIMIT_AS).
  max_file_size_mb      per-process file-size cap (setrlimit RLIMIT_FSIZE).

A potentially dangerous shell metachar (`;`, `|`, `>`, `<`, `&&`, `||`,
`$(`, backtick) in the raw command string warns or refuses based on the
``allow_shell_meta`` flag.

Every accepted task is logged to ``workspace/logs/task_audit.log``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import resource
import shlex
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("research_os.tools.tasks")

TASKS_DIR_NAME = "tasks"

# Default allowlist — common research interpreters + a small set of helpers.
# Add to / override with `runtime.command_allowlist` in researcher_config.
_DEFAULT_ALLOWLIST = {
    # Interpreters
    "python", "python3", "python3.10", "python3.11", "python3.12",
    "Rscript", "R",
    "julia",
    "bash", "sh",
    "jupyter", "jupyter-nbconvert", "quarto",
    "ipython",
    # Dev + research helpers
    "git",
    "make",
    "node", "npm",
    "snakemake", "nextflow",
    "pytest", "tox", "nox",
    "rmarkdown", "knitr",
    "stata", "mlr",
    # Safe coreutils (used in test scaffolding + benign placeholders).
    # These don't write outside cwd by default and have no destructive
    # behaviour that isn't already obvious from the argv.
    "sleep", "true", "false", "echo",
}

# Shell metachars that warrant scrutiny (might still be legitimate).
_DANGEROUS_META = re.compile(r"[;|&]{2}|[;|&<>`]|\$\(")


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


def _read_runtime_config(root: Path) -> dict:
    cfg_path = root / "inputs" / "researcher_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        return (cfg.get("runtime") or {})
    except Exception:
        return {}


def _check_command_safety(
    raw_command: str | None,
    argv: list[str],
    runtime_cfg: dict,
) -> tuple[bool, str]:
    """Return (ok, reason). When not ok, reason is the refusal text."""
    if not argv:
        return False, "Empty argv."

    if not runtime_cfg.get("allow_arbitrary"):
        allowlist = set(_DEFAULT_ALLOWLIST)
        extra = runtime_cfg.get("command_allowlist") or []
        if isinstance(extra, list):
            allowlist.update(str(x) for x in extra)
        binary = Path(argv[0]).name
        if binary not in allowlist:
            return False, (
                f"Refused: `{binary}` not on the command_allowlist. "
                f"Either add it via researcher_config "
                f"(runtime.command_allowlist) or set "
                f"runtime.allow_arbitrary=true for this workspace."
            )

    if raw_command and not runtime_cfg.get("allow_shell_meta", False):
        if _DANGEROUS_META.search(raw_command):
            return False, (
                "Refused: command contains shell metacharacters "
                "(`;`, `|`, `&&`, `||`, `>`, `<`, `$(...)`, backtick). "
                "Wrap the work in an actual script and re-invoke, or set "
                "runtime.allow_shell_meta=true if you know what you're doing."
            )
    return True, ""


def _audit_log(
    root: Path,
    *,
    task_id: str,
    argv: list[str],
    cwd: str,
    description: str,
    pid: int | None,
    accepted: bool,
    reason: str = "",
) -> None:
    log_path = root / "workspace" / "logs" / "task_audit.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now(),
        "task_id": task_id,
        "argv": argv,
        "cwd": cwd,
        "description": description,
        "pid": pid,
        "accepted": accepted,
        "reason": reason,
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        logger.warning(f"task_audit write failed: {e}")


def _make_preexec(runtime_cfg: dict):
    """Return a preexec_fn that applies resource limits in the child.

    Returns None if no limits configured (avoids fork-time overhead).
    """
    max_cpu = runtime_cfg.get("max_cpu_seconds")
    max_mem_mb = runtime_cfg.get("max_memory_mb")
    max_fsize_mb = runtime_cfg.get("max_file_size_mb")
    if not any((max_cpu, max_mem_mb, max_fsize_mb)):
        return None

    def _preexec() -> None:
        # Detach from controlling terminal (already done by start_new_session,
        # but harmless to repeat).
        try:
            os.setsid()
        except OSError:
            pass
        if max_cpu:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (int(max_cpu), int(max_cpu)))
            except (ValueError, OSError):
                pass
        if max_mem_mb:
            try:
                cap = int(max_mem_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            except (ValueError, OSError):
                pass
        if max_fsize_mb:
            try:
                cap = int(max_fsize_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
            except (ValueError, OSError):
                pass

    return _preexec


def _reap_pid(pid: int) -> tuple[bool, int | None]:
    """Return ``(alive, exit_code)`` for ``pid``.

    Background tasks are spawned via ``subprocess.Popen`` and the parent
    drops the handle. When the child exits it becomes a zombie until
    reaped. ``os.kill(pid, 0)`` still succeeds for zombies, so naïve
    liveness checks report ``running`` long after the process finished.
    Reap with ``waitpid(WNOHANG)`` when we are the parent; fall back to
    ``/proc/<pid>/status`` (Linux) when we are not.

    The status word returned by ``waitpid`` carries the exit code (or the
    terminating signal). It is available EXACTLY ONCE — the child is
    reaped on the first successful ``waitpid``, after which subsequent
    calls raise ``ChildProcessError``. Callers MUST persist a returned
    non-None ``exit_code`` immediately, or the success/failure verdict is
    lost. ``exit_code`` is None when the process is still alive or when
    we are not the parent and can't recover the status word (in that case
    success vs. failure is unknown — reported as ``finished``).

    Exit-code convention (``os.waitstatus_to_exitcode``): 0 = success,
    >0 = the process's own non-zero exit, <0 = killed by signal N
    (value is ``-N``).
    """
    if not pid:
        return False, None
    # Try non-blocking reap — succeeds when we are the parent and child
    # has already exited. Capture the status word so the exit code isn't
    # discarded (a crashed task must not look identical to a clean one).
    try:
        reaped, wstatus = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            try:
                exit_code = os.waitstatus_to_exitcode(wstatus)
            except (ValueError, ChildProcessError):
                exit_code = None
            return False, exit_code
    except (ChildProcessError, OSError):
        # Already reaped by someone else, or we are not the parent —
        # fall through to the /proc liveness probe; exit code is
        # unrecoverable here.
        pass
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False, None
    # Process exists in the table — distinguish running from zombie.
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("State:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].upper().startswith("Z"):
                        return False, None
                    return True, None
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return True, None


def _pid_alive(pid: int) -> bool:
    """Back-compat liveness check. Prefer :func:`_reap_pid` when the exit
    code matters (it reaps the child exactly once)."""
    alive, _ = _reap_pid(pid)
    return alive


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def task_run(command: str | list[str], root: Path, *, cwd: str | None = None,
             description: str = "") -> dict[str, Any]:
    """Spawn a real background subprocess and return its task_id immediately.

    ``command`` can be a string (shell-tokenised) or a list of argv items.
    stdout + stderr are tee'd to ``.os_state/tasks/<id>.log``.

    Safety: argv[0] is checked against ``runtime.command_allowlist`` (set
    ``allow_arbitrary=true`` to skip). Shell metacharacters in a string
    command are refused unless ``allow_shell_meta=true``. Resource limits
    (CPU / memory / file size) are applied via ``setrlimit`` when
    configured. Every accepted task is audited to
    ``workspace/logs/task_audit.log``.
    """
    try:
        task_id = (
            f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            f"_{uuid.uuid4().hex[:6]}"
        )
        tasks_dir = _tasks_dir(root)
        log_path = tasks_dir / f"{task_id}.log"
        meta_path = tasks_dir / f"{task_id}.json"

        raw_command = command if isinstance(command, str) else None
        argv = shlex.split(command) if isinstance(command, str) else list(command)

        # Resolve cwd against root if relative.
        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute():
                cwd_path = root / cwd_path
            cwd_str = str(cwd_path)
        else:
            cwd_str = str(root)

        # Safety check FIRST — refuse early, never spawn.
        runtime_cfg = _read_runtime_config(root)
        ok, reason = _check_command_safety(raw_command, argv, runtime_cfg)
        if not ok:
            _audit_log(
                root,
                task_id=task_id,
                argv=argv,
                cwd=cwd_str,
                description=description,
                pid=None,
                accepted=False,
                reason=reason,
            )
            return {"status": "error", "message": reason}

        preexec_fn = _make_preexec(runtime_cfg)

        log_file = open(log_path, "w")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd_str,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=preexec_fn,
            )
        except FileNotFoundError as e:
            _audit_log(
                root,
                task_id=task_id,
                argv=argv,
                cwd=cwd_str,
                description=description,
                pid=None,
                accepted=False,
                reason=f"Command not found: {e}",
            )
            return {"status": "error", "message": f"Command not found: {e}"}
        finally:
            # Close the parent's copy on every path (success,
            # FileNotFoundError return, and any other Popen/preexec
            # exception). The child retains its own dup'd descriptor, so
            # log output is unaffected.
            log_file.close()

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
            "limits": {
                k: runtime_cfg.get(k)
                for k in ("max_cpu_seconds", "max_memory_mb", "max_file_size_mb")
                if runtime_cfg.get(k)
            },
        }
        _save(meta_path, meta)
        _audit_log(
            root,
            task_id=task_id,
            argv=argv,
            cwd=cwd_str,
            description=description,
            pid=proc.pid,
            accepted=True,
        )
        # Don't wait — return immediately. The child holds its own dup'd fd;
        # the parent's copy was closed deterministically above.
        return {
            "status": "success",
            "task_id": task_id,
            "pid": proc.pid,
            "log_path": meta["log_path"],
            "limits": meta["limits"],
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
        # If we already reaped this task on a prior poll the exit code is
        # recorded in meta — don't waitpid() again (the child is gone and
        # the status word can't be recovered a second time).
        already_terminal = meta.get("status") in {"finished", "failed", "killed"}
        if already_terminal:
            alive = False
            exit_code = meta.get("exit_code")
        else:
            alive, exit_code = _reap_pid(pid)
        log_path = root / meta.get("log_path", f".os_state/tasks/{task_id}.log")

        tail = ""
        if log_path.exists():
            try:
                with open(log_path) as f:
                    lines = f.readlines()
                tail = "".join(lines[-tail_lines:])
            except Exception:
                tail = ""

        # Distinguish a crashed task from a clean one. 'finished' is kept as
        # a back-compat superset for the unknown-exit-code case (we weren't
        # the parent / couldn't recover the status word); a known non-zero
        # exit (or a terminating signal, encoded as a negative code) is
        # surfaced as 'failed'.
        if alive:
            current_status = "running"
        elif exit_code is None:
            current_status = "finished"
        elif exit_code == 0:
            current_status = "finished"
        else:
            current_status = "failed"

        if meta.get("status") != current_status or (
            not alive and exit_code is not None and "exit_code" not in meta
        ):
            meta["status"] = current_status
            if not alive:
                meta.setdefault("finished_at", _now())
                if exit_code is not None:
                    meta["exit_code"] = exit_code
            _save(meta_path, meta)

        succeeded: bool | None
        if alive:
            succeeded = None
        elif exit_code is None:
            succeeded = None  # terminal but exit code unknown
        else:
            succeeded = exit_code == 0

        return {
            "status": "success",
            "task_id": task_id,
            "task_status": current_status,
            "exit_code": meta.get("exit_code", exit_code),
            "succeeded": succeeded,
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
            # Don't re-reap a task already recorded as terminal — the exit
            # code (if any) is persisted in meta from the first observation.
            already_terminal = meta.get("status") in {"finished", "failed", "killed"}
            if already_terminal:
                alive = False
                exit_code = meta.get("exit_code")
            else:
                alive, exit_code = _reap_pid(pid)
            if alive:
                live_status = "running"
            elif exit_code is None:
                live_status = "finished"
            elif exit_code == 0:
                live_status = "finished"
            else:
                live_status = "failed"
            # Persist the verdict (and exit code) so a later poll doesn't
            # need to re-reap a child that's already gone.
            if meta.get("status") != live_status or (
                not alive and exit_code is not None and "exit_code" not in meta
            ):
                meta["status"] = live_status
                if not alive:
                    meta.setdefault("finished_at", _now())
                    if exit_code is not None:
                        meta["exit_code"] = exit_code
                _save(meta_path, meta)
            out.append(
                {
                    "task_id": meta["task_id"],
                    "pid": pid,
                    "task_status": live_status,
                    "exit_code": meta.get("exit_code", exit_code),
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
