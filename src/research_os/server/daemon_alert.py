"""Per-turn daemon-findings backstop — the AI's constant 'did the daemon flag me?' check.

The daemon writes its self-check to `.os_state/daemon_notes.json` at startup AND
on a periodic tick (so the file stays fresh mid-session). But the AI only read
that file at `sys_boot` (session start) — so a problem the daemon detected an
hour into a long session never reached the AI until the next reboot. This closes
that loop: on EVERY tool call, cheaply check whether the daemon's notes carry
block/warn findings the AI hasn't seen yet, and if so surface them on the same
envelope the AI is already reading (audit_findings). The AI doesn't have to
remember to poll — the check rides every turn.

Acknowledgment is tracked by the notes' `checked_at` timestamp: we persist the
last value the AI was shown to `.os_state/.daemon_ack.json`, and only re-surface
when the daemon has run a NEWER self-check with actionable findings. So the AI
is nudged once per fresh daemon finding, not on every single turn.

Seam-safe: reads `.os_state` by shape, never imports research_os.daemon, fails
open (any error → no alert). Non-blocking: only appends to audit_findings.
"""
from __future__ import annotations

import json
from pathlib import Path

_ACK_FILE = ".daemon_ack.json"


def _ack_path(root: Path) -> Path:
    return root / ".os_state" / _ACK_FILE


def _read_ack(root: Path) -> float:
    try:
        p = _ack_path(root)
        if p.is_file():
            return float(json.loads(p.read_text(encoding="utf-8")).get("checked_at", 0))
    except Exception:
        pass
    return 0.0


def _write_ack(root: Path, checked_at: float) -> None:
    try:
        p = _ack_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"checked_at": checked_at}), encoding="utf-8")
    except Exception:
        pass


def daemon_alert(root: Path) -> dict | None:
    """Return a single consolidated alert finding if the daemon flagged NEW
    actionable (block/warn) problems since the AI last saw the notes.

    Returns None when: no daemon notes, no actionable findings, or the AI has
    already been shown this self-check run. Marks the run acknowledged so the
    same findings don't nag every turn (a fresher daemon tick re-arms it).
    """
    try:
        root = Path(root)
        from research_os.server.daemon_bridge import read_daemon_notes

        notes = read_daemon_notes(root)
        if not isinstance(notes, dict):
            return None
        checked_at = float(notes.get("checked_at", 0) or 0)
        if checked_at <= 0:
            return None
        if checked_at <= _read_ack(root):
            return None  # already shown this self-check run

        findings = notes.get("findings") or []
        actionable = [
            f for f in findings
            if isinstance(f, dict) and f.get("severity") in ("block", "warn")
        ]
        # Mark seen regardless, so a self-check with only info-level findings
        # doesn't re-trigger every turn.
        _write_ack(root, checked_at)
        if not actionable:
            return None

        blocks = [f for f in actionable if f.get("severity") == "block"]
        worst = "block" if blocks else "warn"
        # Compact summary the AI can act on; full detail is in daemon_notes.
        lines = []
        for f in actionable[:5]:
            code = f.get("code") or f.get("source") or "issue"
            lines.append(f"  - [{f.get('severity')}] {code}: {f.get('message', '')}")
        more = f"\n  (+{len(actionable) - 5} more)" if len(actionable) > 5 else ""
        return {
            "severity": worst,
            "code": "daemon_flagged_issue",
            "message": (
                f"The daemon's watch found {len(actionable)} issue(s) you should "
                "address (it re-checks the project in the background):\n"
                + "\n".join(lines) + more
                + "\nReview `sys_boot.daemon_notes` / call `sys_daemon` for full "
                "detail, fix the BLOCK items before building further."
            ),
            "next_recommended_call": "sys_daemon(operation='notes')",
        }
    except Exception:
        return None
