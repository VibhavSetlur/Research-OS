"""Mid-prompt off-protocol drift detector (4.0.4).

The AI sometimes FORGETS to use Research-OS: it writes analysis/step content
directly (sys_file_write / sys_path) without routing through tool_route or
opening a numbered step, and never logs to protocol_execution_log.jsonl. Before
4.0.4 nothing caught this *in the same turn* — the daemon's compliance watchdog
ran only at boot, via a sys_boot call the AI is told not to repeat.

This module returns a NON-BLOCKING "COURSE CORRECT" hint that rides home on the
SAME envelope the AI is already reading, so the AI sees it mid-prompt and can
self-correct and continue. The write/route already succeeded — we only append a
hint; we never block (hard gates live in autopilot_gate.py for irreversible
actions; drift is a nudge, not a gate).

Seam discipline: reasoning-side, stdlib-only. It reads `.os_state` BY SHAPE and
NEVER imports research_os.daemon (matching the preflight seam in
server/daemon_bridge.py), so it works identically with OR without a daemon
running — stdio-only users get the same self-correction.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# Tools that PRODUCE step / analysis / synthesis content. Only these trigger the
# (tiny) on-disk scan; every other tool short-circuits to None for ~zero cost.
STEP_PRODUCING_TOOLS = frozenset(
    {
        "sys_file_write",
        "sys_path",
        "sys_path_create",
        "tool_step_pipeline_run",
    }
)

# A path is "step-like" (should have been routed + scaffolded) when it is a
# numbered step's working content, a step conclusions file, or a synthesis
# deliverable. Scratch / inputs / context / logs are explicitly NOT step-like.
_STEP_LIKE_RE = re.compile(
    r"^workspace/\d{2,3}_[^/]+/.+|"          # workspace/NN_slug/<anything>
    r"^workspace/analysis\.md$|"
    r".*/conclusions\.md$|"
    r"^synthesis/(?!deliverables/README).+"  # synthesis content (a real deliverable)
)

# Debounce: nudge at most once per this many seconds per project, and never
# re-nag in the same short window after the AI has been told.
_NUDGE_DEBOUNCE_S = 90.0
_LOG_TAIL = 40


def _rel_target(tool: str, arguments: dict) -> str | None:
    """The project-relative path a step-producing call is writing to, if any."""
    if not isinstance(arguments, dict):
        return None
    for key in ("filepath", "path", "rel_path", "file", "filename", "target", "step_id", "name"):
        v = arguments.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lstrip("./")
    return None


def _has_active_plan(root: Path) -> bool:
    """True if tool_route persisted a plan this session (proxy for 'routed')."""
    p = root / ".os_state" / "active_plan.json"
    try:
        if not p.is_file():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        return bool(data)
    except Exception:
        return False


def _recent_protocol_started(root: Path) -> bool:
    """True if the protocol-execution log tail has a recent 'started' entry."""
    log = root / ".os_state" / "protocol_execution_log.jsonl"
    try:
        if not log.is_file():
            return False
        lines = log.read_text(encoding="utf-8").splitlines()[-_LOG_TAIL:]
        for ln in lines:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            if str(e.get("event") or e.get("status") or "").lower() in (
                "started", "step_started", "routed", "protocol_started"
            ):
                return True
        return False
    except Exception:
        return False


def _debounced(root: Path) -> bool:
    """True if we nudged recently (skip to avoid nagging). Records now if not."""
    marker = root / ".os_state" / "drift" / "last_nudge.json"
    now = time.time()
    try:
        if marker.is_file():
            last = json.loads(marker.read_text(encoding="utf-8")).get("at", 0)
            if now - float(last) < _NUDGE_DEBOUNCE_S:
                return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"at": now}), encoding="utf-8")
    except Exception:
        return False
    return False


def drift_hint(tool: str, arguments: dict, root: Path) -> dict | None:
    """Return a non-blocking course-correct hint, or None.

    Fires when a step-producing call writes step-like content while NO routing /
    open protocol exists for this session — i.e. the AI is freelancing past
    Research-OS. Fail-open: any error returns None (never breaks a tool call).
    """
    try:
        root = Path(root)
        if tool not in STEP_PRODUCING_TOOLS:
            return None
        rel = _rel_target(tool, arguments)
        if not rel:
            return None
        # sys_path/step_id values are bare slugs; treat a numbered slug as step-like.
        candidate = rel if "/" in rel or rel.endswith(".md") else f"workspace/{rel}/x"
        if not _STEP_LIKE_RE.match(candidate):
            return None
        # The AI is on-protocol if it routed (active_plan) OR a step is open
        # (recent 'started' in the log). Either one clears the nudge.
        if _has_active_plan(root) or _recent_protocol_started(root):
            return None
        if _debounced(root):
            return None
        return {
            "severity": "warn",
            "code": "off_protocol_freelancing",
            "message": (
                "COURSE CORRECT: you wrote step content without routing it "
                "through Research-OS — no tool_route ran and no protocol step is "
                "open this session. Don't keep freelancing: route the ask, open "
                "a numbered step, then continue the work inside it (and finish "
                "with tool_step_complete)."
            ),
            "next_recommended_call": (
                "tool_route(prompt='<the researcher ask you are working on>')"
            ),
        }
    except Exception:
        return None
