"""Autonomous continuation — after a long result lands, optionally re-prompt
the researcher's AI to CONTINUE the work toward a goal, unattended.

docs/AUTONOMOUS_CONTINUATION.md.

The "I kicked off hours of compute and walked away — when it finishes, keep
going" feature. STRICTLY OPT-IN: nothing auto-continues unless the researcher
sets ``daemon.continue_command`` (a shell command wired to their agent — Hermes
/ CC / any). The daemon never decides on its own to spend the researcher's
compute or tokens.

How it works when enabled:
  1. A long job reaches a terminal state.
  2. The daemon builds a CONTINUATION PAYLOAD: the finished run's outcome, the
     project goal, the current hop count, and a compact "what to do next"
     pointer (orient's recommendation). Written to .os_state/continuation/.
  3. The daemon runs ``continue_command`` with that payload on stdin. The
     researcher's command hands it to their agent, which continues the work.
  4. A hard ``continue_max_hops`` ceiling per goal prevents an infinite loop;
     when the agent declares the goal MET (or the ceiling is hit), the loop
     stops and a notification fires.

Safety:
  * Opt-in only (empty continue_command → no-op).
  * Hop-limited (a goal can't loop forever).
  * The continued agent still passes through every enforcement gate (consent,
    staleness) — autonomy never bypasses the kernel.
  * Fail-open: a continuation failure is logged + notified, never crashes the
    daemon or the job.

stdlib only. Never raises into the caller.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

_CONT_DIR = "continuation"
_STATE_FILE = "state.json"   # per-goal hop tracking


def _cont_dir(root: Path) -> Path:
    return Path(root) / ".os_state" / _CONT_DIR


def _read_loop_state(root: Path) -> dict[str, Any]:
    try:
        path = _cont_dir(root) / _STATE_FILE
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"goal": None, "hops": 0, "active": False}


def _write_loop_state(root: Path, state: dict[str, Any]) -> None:
    try:
        d = _cont_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        (d / _STATE_FILE).write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def start_goal_loop(root: str | Path, goal: str) -> dict[str, Any]:
    """Begin an autonomous goal loop. Resets the hop counter for a new goal."""
    root = Path(root)
    state = {"goal": goal, "hops": 0, "active": True, "started_at": time.time()}
    _write_loop_state(root, state)
    return state


def stop_goal_loop(root: str | Path, *, reason: str = "goal_met") -> dict[str, Any]:
    """End the active goal loop (goal met, or the agent/researcher stopped it)."""
    root = Path(root)
    state = _read_loop_state(root)
    state["active"] = False
    state["stopped_reason"] = reason
    state["stopped_at"] = time.time()
    _write_loop_state(root, state)
    return state


def build_continuation_payload(
    root: str | Path,
    *,
    finished_run: dict[str, Any] | None,
    goal: str | None,
    hops: int,
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON the continue_command receives on stdin.

    Compact + self-contained: a fresh agent session reads ONLY this + sys_boot
    and knows what just finished, the goal, where it is in the loop, and the
    recommended next move.
    """
    return {
        "schema": 1,
        "kind": "autonomous_continuation",
        "root": str(root),
        "goal": goal,
        "hop": hops,
        "finished_run": {
            "id": (finished_run or {}).get("id"),
            "name": (finished_run or {}).get("name"),
            "status": (finished_run or {}).get("status"),
            "returncode": (finished_run or {}).get("returncode"),
        } if finished_run else None,
        "next_action": next_action,
        "instruction": (
            "A background result just landed. Continue the research toward the "
            "goal above: call sys_boot, read the daemon_notes, act on the "
            "recommended next action, and either advance one step or — if the "
            "goal is met — call the daemon to stop the loop. You are running "
            "unattended; respect every gate (do not self-approve)."
        ),
    }


def maybe_continue(
    root: str | Path,
    *,
    config: Any,
    finished_run: dict[str, Any] | None,
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one autonomous-continuation hop IF opted in and within the ceiling.

    Called by the daemon when a long job reaches a terminal state. Returns a
    result dict describing what happened (``ran`` / ``skipped`` / ``stopped``).
    Never raises — a continuation failure must not break the job or the daemon.

    Gating (all must hold to run a hop):
      * ``config.continue_command`` is set (opt-in).
      * a goal loop is active.
      * hops < ``config.continue_max_hops`` (the hard ceiling).
    """
    root = Path(root)
    cmd = (getattr(config, "continue_command", "") or "").strip()
    if not cmd:
        return {"ran": False, "reason": "not_opted_in"}

    state = _read_loop_state(root)
    if not state.get("active"):
        return {"ran": False, "reason": "no_active_goal"}

    max_hops = int(getattr(config, "continue_max_hops", 25) or 25)
    hops = int(state.get("hops", 0))
    if hops >= max_hops:
        stop_goal_loop(root, reason="max_hops_reached")
        _notify(
            root, config, level="action_required",
            title="Autonomous loop stopped",
            body=(
                f"The autonomous continuation loop hit its ceiling "
                f"({max_hops} hops) without the goal being declared met. "
                "Review progress and decide whether to continue."
            ),
        )
        return {"ran": False, "reason": "max_hops_reached", "hops": hops}

    # Advance the hop counter BEFORE running, so a crash mid-hop still counts
    # (fail toward stopping, never toward an unbounded loop).
    hops += 1
    state["hops"] = hops
    state["last_hop_at"] = time.time()
    _write_loop_state(root, state)

    payload = build_continuation_payload(
        root,
        finished_run=finished_run,
        goal=state.get("goal"),
        hops=hops,
        next_action=next_action,
    )
    # Persist the payload for inspection / the agent to read by-shape.
    try:
        d = _cont_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"hop_{hops:04d}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass

    # Run the researcher's continuation command with the payload on stdin.
    # Best-effort + bounded: a hung agent command must not wedge the daemon.
    try:
        subprocess.run(
            cmd,
            shell=True,
            input=json.dumps(payload),
            text=True,
            timeout=30,
            capture_output=True,
            check=False,
        )
        return {"ran": True, "hop": hops, "goal": state.get("goal")}
    except subprocess.TimeoutExpired:
        return {"ran": True, "hop": hops, "warning": "continue_command timed out (fire-and-forget)"}
    except Exception as exc:  # noqa: BLE001 - never raise into the daemon
        _notify(
            root, config, level="warn",
            title="Autonomous continuation failed",
            body=f"continue_command failed on hop {hops}: {exc}",
        )
        return {"ran": False, "reason": f"command_error: {exc}", "hop": hops}


def _notify(root: Path, config: Any, *, level: str, title: str, body: str) -> None:
    """Best-effort notification via the spine (never raises)."""
    try:
        from . import notifications as _ntfy

        _ntfy.emit(
            root,
            kind="autonomous_continuation",
            title=title,
            body=body,
            level=level,
            notify_command=getattr(config, "notify_command", "") or "",
        )
    except Exception:  # noqa: BLE001
        pass
