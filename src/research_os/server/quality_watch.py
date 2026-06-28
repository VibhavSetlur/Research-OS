"""Per-turn quality watchers — the daemon/server watching the AI more closely.

Companion to ``server/drift_detect.py``. Where drift_detect catches the AI
working OUTSIDE Research OS (no route / no step), these watchers catch the AI
doing INCOMPLETE or unverified work INSIDE it, and return a non-blocking
COURSE-CORRECT hint on the same envelope the AI is reading this turn:

  * A2 ``wrote_conclusions_no_audit`` — a step's conclusions.md or a synthesis
    deliverable was written but no audit has run since.
  * A3 ``ungrounded_synthesis_unverified`` — a synthesis file now contains
    quantitative claims but no claim-grounding run recorded since it changed.
    (Attacks hallucinated numbers at the moment they are written.)
  * A4 ``stuck_protocol_loop`` — several recent protocol steps failed in a row.

Seam discipline (identical to drift_detect): reasoning-side, stdlib-only, reads
``.os_state`` / ``workspace/`` BY SHAPE, never imports ``research_os.daemon``,
so it behaves the same with or without a daemon. Every watcher is fail-open
(any error → no hint) and NON-blocking (only appends to ``audit_findings`` /
fills an empty ``next_recommended_call`` — never changes status). Hard gates
remain in autopilot_gate.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# Tools whose output is worth a quality check (writes + step/route lifecycle).
_WATCHED_TOOLS = frozenset(
    {"sys_file_write", "sys_path", "sys_path_create", "tool_step_complete",
     "tool_route", "sys_boot"}
)

_AUDIT_LEDGER = "workspace/logs/.audit_findings.jsonl"
_PROTOCOL_LOG = ".os_state/protocol_execution_log.jsonl"
_DEBOUNCE_S = 90.0
_FAIL_RUN = 3            # ≥ this many recent failures in a row → stuck
_LOG_TAIL = 30


def _rel_target(arguments: dict) -> str | None:
    if not isinstance(arguments, dict):
        return None
    for key in ("filepath", "path", "rel_path", "file", "filename", "target"):
        v = arguments.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lstrip("./")
    return None


def _ledger_has_entry_since(root: Path, mtime: float, kind: str | None = None) -> bool:
    """True if the audit ledger has an entry newer than ``mtime`` (optionally of
    a given kind/code substring)."""
    led = root / _AUDIT_LEDGER
    try:
        if not led.is_file():
            return False
        if led.stat().st_mtime < mtime:
            return False
        if kind is None:
            return True
        for ln in led.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            blob = json.dumps(e).lower()
            if kind.lower() in blob:
                return True
        return False
    except Exception:
        return False


def _debounced(root: Path, code: str) -> bool:
    marker = root / ".os_state" / "drift" / f"qw_{code}.json"
    now = time.time()
    try:
        if marker.is_file():
            last = json.loads(marker.read_text(encoding="utf-8")).get("at", 0)
            if now - float(last) < _DEBOUNCE_S:
                return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"at": now}), encoding="utf-8")
    except Exception:
        return False
    return False


def _recent_failure_run(root: Path) -> int:
    """Count consecutive recent 'failed' entries at the tail of the protocol log."""
    log = root / _PROTOCOL_LOG
    try:
        if not log.is_file():
            return 0
        lines = log.read_text(encoding="utf-8").splitlines()[-_LOG_TAIL:]
        run = 0
        for ln in reversed(lines):
            try:
                e = json.loads(ln)
            except Exception:
                continue
            status = str(e.get("status") or e.get("event") or "").lower()
            if "fail" in status:
                run += 1
            elif status in ("completed", "started", "step_complete", "routed"):
                break
        return run
    except Exception:
        return 0


def next_action_hint(tool: str, root: Path) -> str | None:
    """Derive a sensible 'do this next' call for high-traffic tools that didn't
    return one, so the AI always has a proactive next step (better user↔AI
    interaction). Only a hint — the dispatcher fills it ONLY when the handler
    left next_recommended_call empty. By-shape, fail-open.
    """
    try:
        # After finishing a step → audit it. After a synthesis-scaffold or
        # synthesis write → ground the claims. After routing → walk the plan.
        if tool == "tool_step_complete":
            return "tool_audit(scope='step', dimension='completeness')"
        if tool in ("tool_synthesis_scaffold",):
            return "tool_claim_grounding()"
        if tool == "tool_route":
            # If routing persisted a plan, advance it; else load the protocol.
            try:
                ap = Path(root) / ".os_state" / "active_plan.json"
                if ap.is_file() and json.loads(ap.read_text()):
                    return "tool_plan(operation='turn')"
            except Exception:
                pass
            return None
        return None
    except Exception:
        return None


def quality_hints(tool: str, arguments: dict, root: Path) -> list[dict]:
    """Return zero or more non-blocking quality course-correct hints."""
    hints: list[dict] = []
    try:
        root = Path(root)
        if tool not in _WATCHED_TOOLS:
            return hints
        rel = _rel_target(arguments)

        # A2/A3 — a conclusions / synthesis write with no audit / grounding since.
        if rel:
            is_conclusions = rel.endswith("conclusions.md")
            is_synth = rel.startswith("synthesis/") and not rel.endswith("/README.md")
            target = root / rel
            mtime = target.stat().st_mtime if target.exists() else time.time()
            if is_conclusions and not _ledger_has_entry_since(root, mtime):
                if not _debounced(root, "wrote_conclusions_no_audit"):
                    hints.append({
                        "severity": "warn",
                        "code": "wrote_conclusions_no_audit",
                        "message": (
                            "You wrote conclusions but no audit has run since. "
                            "Don't call the step done on unaudited conclusions — "
                            "run the completeness audit for this step."
                        ),
                        "next_recommended_call": (
                            "tool_audit(scope='step', dimension='completeness')"
                        ),
                    })
            if is_synth:
                # A3: does the just-written synthesis contain quantitative claims
                # with no grounding run since? (cheap regex on the one file.)
                try:
                    from research_os.tools.actions.audit.claim_grounding import (
                        extract_claims,
                    )
                    n_claims = len(extract_claims(target)) if target.exists() else 0
                except Exception:
                    n_claims = 0
                grounded = _ledger_has_entry_since(root, mtime, kind="grounding")
                if n_claims >= 1 and not grounded:
                    if not _debounced(root, "ungrounded_synthesis_unverified"):
                        hints.append({
                            "severity": "warn",
                            "code": "ungrounded_synthesis_unverified",
                            "message": (
                                f"This synthesis file now has ~{n_claims} numeric "
                                "claim(s) but no claim-grounding run since you "
                                "wrote it. Verify every number traces to a real "
                                "artifact before anyone reads it."
                            ),
                            "next_recommended_call": "tool_claim_grounding()",
                        })

        # A4 — stuck in a run of failed protocol steps (it's looping NOW).
        if _recent_failure_run(root) >= _FAIL_RUN:
            if not _debounced(root, "stuck_protocol_loop"):
                hints.append({
                    "severity": "warn",
                    "code": "stuck_protocol_loop",
                    "message": (
                        "Several protocol steps failed in a row. Stop repeating "
                        "the same approach — try a different decomposition, or ask "
                        "the researcher how to proceed."
                    ),
                    "next_recommended_call": (
                        "tool_route(prompt='<reframe the current step differently>')"
                    ),
                })
    except Exception:
        return hints
    return hints
