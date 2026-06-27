"""Daemon startup self-check + AI-facing notes.

docs/DAEMON.md (§ Startup self-check).

When the daemon spins up it should LOOK at the project, notice anything wrong
or worth flagging (structure drift, interrupted runs, stale results, an empty
intake), and leave a short, plain-language note the AI will read at the start
of its next turn — so problems get surfaced to the researcher (or fixed in an
autonomous loop) instead of silently festering.

The note is written to ``.os_state/daemon_notes.md`` (human-readable) plus a
machine sibling ``.os_state/daemon_notes.json``. ``server/daemon_bridge.py``
exposes the JSON by-shape and ``sys_boot`` / ``sys_daemon`` surface it, so the
agent inherits the daemon's findings without importing the daemon (seam intact).

Design rules:
  * READ-ONLY assessment — this notices, it does not fix (fixing is the AI's
    job via tool_workspace_repair / the structure protocols, or an explicit
    autonomous loop).
  * Fail-OPEN — any error writing notes is swallowed; a self-check failure
    must never stop the daemon from serving.
  * Bounded + deduped — the note is regenerated each startup (not appended
    forever), so it always reflects current reality, never a stale pile.

stdlib only. Never raises.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections.abc import Sequence
from typing import Any

_NOTES_MD = "daemon_notes.md"
_NOTES_JSON = "daemon_notes.json"

_SEVERITY_ICON = {"block": "🔴", "warn": "🟡", "info": "🔵"}


def _notes_dir(root: Path) -> Path:
    return Path(root) / ".os_state"


def run_self_check(root: str | Path) -> dict[str, Any]:
    """Assess the project at daemon startup. Read-only. Never raises.

    Aggregates findings from the structure-integrity audit, the run journal
    (interrupted runs), and a couple of cheap project-health signals into one
    note payload the AI can act on. Returns the payload (also persisted by
    :func:`write_notes`).
    """
    root = Path(root)
    findings: list[dict[str, Any]] = []

    # 1. Structural integrity (reuse the read-only audit — same engine the AI
    #    can call as tool_structure_audit, so the daemon and the agent agree).
    try:
        from research_os.tools.actions.state.structure_audit import audit_structure

        audit = audit_structure(root)
        for f in audit.get("findings", []):
            findings.append({
                "severity": f.get("severity", "info"),
                "source": "structure",
                "message": f.get("message", ""),
                "code": f.get("code"),
            })
    except Exception:  # noqa: BLE001 - self-check must not raise
        pass

    # 2. Interrupted runs (the "walked away, box rebooted" signal).
    try:
        from .runstore import RunStore

        store = RunStore(root)
        interrupted = [
            r for r in store.list_runs(limit=200)
            if (r.get("status") or "").lower() == "interrupted"
        ]
        if interrupted:
            findings.append({
                "severity": "warn",
                "source": "runs",
                "message": (
                    f"{len(interrupted)} run(s) were interrupted and never "
                    "finished — resume or re-run them (sys_daemon / "
                    "POST /v1/runs/<id>/resume)."
                ),
                "code": "interrupted_runs",
            })
    except Exception:  # noqa: BLE001
        pass

    # 3. Empty/unfilled intake — a project the AI should help frame.
    try:
        overview = root / "docs" / "research_overview.md"
        state_json = root / ".os_state" / "state.json"
        question_set = False
        if state_json.exists():
            data = json.loads(state_json.read_text(encoding="utf-8"))
            q = (data.get("research_question") or "").strip()
            question_set = bool(q) and "not yet set" not in q.lower()
        if not question_set and not overview.exists():
            findings.append({
                "severity": "info",
                "source": "intake",
                "message": (
                    "No research question set yet — help the researcher frame "
                    "the project (they can just describe it in chat)."
                ),
                "code": "intake_unframed",
            })
    except Exception:  # noqa: BLE001
        pass

    # 4. Agent-compliance watch (G): is the AI actually FOLLOWING protocols, or
    #    repeatedly failing / abandoning them? Scan the protocol execution log for
    #    a run of failures or steps started-but-never-completed. The daemon flags
    #    this for the AI to self-correct, and (on repeated failure) for the
    #    researcher — RO's promise is "protocols get followed, nothing is lost".
    try:
        log_path = root / ".os_state" / "protocol_execution_log.jsonl"
        if log_path.exists():
            entries: list[dict[str, Any]] = []
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
            recent = entries[-30:]
            failed = [e for e in recent if (e.get("status") or "").lower() == "failed"]
            # started protocols with no matching completed entry afterwards
            started = [e for e in recent if (e.get("status") or "").lower() == "started"]
            completed_protocols = {
                (e.get("protocol") or "") for e in recent
                if (e.get("status") or "").lower() == "completed"
            }
            abandoned = [
                e for e in started
                if (e.get("protocol") or "") not in completed_protocols
            ]
            if len(failed) >= 3:
                findings.append({
                    "severity": "warn",
                    "source": "agent_compliance",
                    "message": (
                        f"{len(failed)} protocol step(s) FAILED recently — the AI "
                        "may be stuck or not following the protocol. Review the "
                        "blockers and correct course; if this persists, the "
                        "researcher should step in."
                    ),
                    "code": "repeated_protocol_failure",
                })
            if len(abandoned) >= 2:
                findings.append({
                    "severity": "warn",
                    "source": "agent_compliance",
                    "message": (
                        f"{len(abandoned)} protocol(s) were started but never "
                        "completed (no completion logged) — work may have been "
                        "abandoned mid-protocol. Resume and finish, or log the "
                        "outcome so nothing is lost."
                    ),
                    "code": "abandoned_protocols",
                })
    except Exception:  # noqa: BLE001 - compliance watch must not raise
        pass

    counts = {"block": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f.get("severity", "info")] = counts.get(f.get("severity", "info"), 0) + 1

    return {
        "schema": 1,
        "checked_at": time.time(),
        "root": str(root),
        "ok": counts["block"] == 0,
        "counts": counts,
        "findings": findings,
    }


def render_notes_md(payload: dict[str, Any]) -> str:
    """Render the self-check payload as a short, plain-language markdown note."""
    findings = payload.get("findings", [])
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(payload.get("checked_at")))
    lines = [
        "# Daemon notes for the AI",
        "",
        f"_The daemon checked this project at {when}. Read this at the start "
        "of your turn and address anything below before building on the project._",
        "",
    ]
    if not findings:
        lines.append("✅ No problems found — the project looks structurally sound.")
        lines.append("")
        return "\n".join(lines)
    # Prioritize: BLOCK first, then WARN, then INFO — the AI/researcher should
    # see the must-fix items at the top, not buried under info notes.
    _order = {"block": 0, "warn": 1, "info": 2}
    ordered = sorted(findings, key=lambda f: _order.get(f.get("severity", "info"), 3))
    for f in ordered:
        icon = _SEVERITY_ICON.get(f.get("severity", "info"), "•")
        lines.append(f"- {icon} **{f.get('source', '?')}** — {f.get('message', '')}")
    lines.append("")
    if payload.get("counts", {}).get("block"):
        lines.append(
            "🔴 There are BLOCK-level integrity issues — fix them (e.g. "
            "tool_workspace_repair, tool_structure_audit) before relying on "
            "this project's results."
        )
        lines.append("")
    return "\n".join(lines)


def write_notes(root: str | Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the self-check (if no payload given) and persist the AI-facing notes.

    Writes both ``daemon_notes.md`` (human) and ``daemon_notes.json``
    (machine, read by-shape via daemon_bridge). Fail-open: returns the payload
    even if the write fails. Regenerates (overwrites), never appends, so the
    note always reflects current reality.
    """
    root = Path(root)
    payload = payload if payload is not None else run_self_check(root)
    try:
        d = _notes_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        (d / _NOTES_MD).write_text(render_notes_md(payload), encoding="utf-8")
        (d / _NOTES_JSON).write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass
    # Escalation: if a BLOCK-level finding persists across consecutive
    # self-checks (the AI keeps not addressing it), page the researcher once —
    # RO's promise is "nothing is lost". Best-effort, never raises.
    try:
        _escalate_persistent_blocks(root, payload)
    except Exception:  # noqa: BLE001
        pass
    return payload


_STREAK_FILE = ".daemon_finding_streak.json"
_ESCALATE_AFTER = 3  # consecutive self-checks a block must persist before paging


def _escalate_persistent_blocks(root: Path, payload: dict[str, Any]) -> None:
    """Track per-code block streaks; page the researcher when one sticks.

    A block finding the AI fixes disappears next check (streak resets). One that
    persists ``_ESCALATE_AFTER`` checks means the AI isn't resolving it — emit a
    single notification so a human can step in, then mark it escalated so we
    don't page again until it clears + recurs.
    """
    streak_path = root / ".os_state" / _STREAK_FILE
    try:
        prev = json.loads(streak_path.read_text(encoding="utf-8")) if streak_path.exists() else {}
    except Exception:
        prev = {}
    if not isinstance(prev, dict):
        prev = {}

    current_blocks = {
        f.get("code") or f.get("source") or "issue": f
        for f in payload.get("findings", [])
        if isinstance(f, dict) and f.get("severity") == "block"
    }
    new_state: dict[str, Any] = {}
    for code, finding in current_blocks.items():
        prior = prev.get(code) or {}
        count = int(prior.get("count", 0) or 0) + 1
        escalated = bool(prior.get("escalated", False))
        if count >= _ESCALATE_AFTER and not escalated:
            try:
                from .notifications import emit
                emit(
                    root,
                    kind="persistent_block",
                    level="warning",
                    title="Research OS: a problem isn't getting fixed",
                    body=(
                        f"The daemon has flagged '{code}' for {count} checks "
                        f"and it's still unresolved: {finding.get('message', '')} "
                        "The AI may be stuck — you might want to step in."
                    ),
                    context={"code": code, "count": count},
                )
                escalated = True
            except Exception:  # noqa: BLE001
                pass
        new_state[code] = {"count": count, "escalated": escalated}
    # Codes that cleared this check drop out (streak resets implicitly).
    try:
        streak_path.parent.mkdir(parents=True, exist_ok=True)
        streak_path.write_text(json.dumps(new_state), encoding="utf-8")
    except OSError:
        pass


def read_notes(root: str | Path) -> dict[str, Any] | None:
    """Read the persisted machine notes (for the agent side, by shape)."""
    try:
        path = _notes_dir(Path(root)) / _NOTES_JSON
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_self_check_all(roots: "Sequence[str | Path]") -> dict[str, Any]:
    """Aggregate self-check across many projects — the supervisor (PI) roll-up.

    Returns {projects: {root: {counts, ok, worst}}, totals: {block,warn,info},
    needs_attention: [roots with any block/warn]} so one call answers "are ALL
    my students' projects healthy?" without opening each. Read-only, fail-open.
    """
    projects: dict[str, Any] = {}
    totals = {"block": 0, "warn": 0, "info": 0}
    needs_attention: list[str] = []
    for root in roots:
        try:
            payload = run_self_check(root)
        except Exception:  # noqa: BLE001
            continue
        counts = payload.get("counts", {}) or {}
        for k in totals:
            totals[k] += int(counts.get(k, 0) or 0)
        findings = payload.get("findings", []) or []
        worst = sorted(
            (f for f in findings if f.get("severity") in ("block", "warn")),
            key=lambda f: {"block": 0, "warn": 1}.get(f.get("severity"), 2),
        )[:3]
        projects[str(root)] = {
            "ok": bool(payload.get("ok", True)),
            "counts": counts,
            "worst": [
                {"severity": f.get("severity"), "code": f.get("code"),
                 "message": f.get("message")}
                for f in worst
            ],
        }
        if counts.get("block") or counts.get("warn"):
            needs_attention.append(str(root))
    return {
        "schema": 1,
        "checked_at": time.time(),
        "projects": projects,
        "totals": totals,
        "needs_attention": needs_attention,
    }

