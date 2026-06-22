"""Multi-hypothesis tracking helpers that mutate state.active_hypotheses.

Used by mem_hypothesis_add / mem_hypothesis_list (and the consolidated
mem_log(kind='hypothesis') dispatcher, which calls _handle_mem_hypothesis_update
internally; the legacy mem_hypothesis_update tool name was hard-removed in
phase-14a — see CHANGELOG).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.memory")


def hypothesis_add(
    statement: str, root: Path, *, hypothesis_id: str | None = None,
    direction: str | None = None, status: str = "testing",
) -> dict[str, Any]:
    """Add a new hypothesis to state.active_hypotheses[]."""
    try:
        from research_os.project_ops import mutate_state

        # Allocate the id AND append inside the locked mutator so two
        # concurrent adds serialise and mint distinct H{n} (the previous
        # unguarded load→mutate→save let both sessions mint the same id and
        # one clobbered the other).
        captured: dict[str, Any] = {}

        def _add(state: dict) -> None:
            existing = state.setdefault("active_hypotheses", [])
            used = {h.get("id") for h in existing if isinstance(h, dict)}
            hid = hypothesis_id
            if not hid:
                n = len(existing) + 1
                while f"H{n}" in used:
                    n += 1
                hid = f"H{n}"
            entry = {
                "id": hid,
                "statement": statement,
                "status": status,
                "direction": direction,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "evidence": [],
            }
            existing.append(entry)
            captured["entry"] = entry

        mutate_state(root, _add)
        entry = captured["entry"]
        hypothesis_id = entry["id"]

        # Also log a line to analysis.md so the workflow narrative captures it.
        from research_os.project_ops import now_iso

        log = root / "workspace" / "analysis.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as f:
            f.write(
                f"\n[{now_iso()}] **HYPOTHESIS {hypothesis_id} added** "
                f"({status}): {statement}\n"
            )
        return {"status": "success", "hypothesis": entry}
    except Exception as e:
        logger.exception("hypothesis_add failed")
        return {"status": "error", "message": str(e)}


def hypothesis_update(
    hypothesis_id: str, root: Path, *, status: str | None = None,
    evidence: str | None = None, step: str | None = None,
) -> dict[str, Any]:
    """Update a hypothesis: status (supported|refuted|inconclusive|testing) + add evidence."""
    try:
        from research_os.project_ops import mutate_state, now_iso

        # Look up + mutate the target inside the lock so a concurrent add /
        # update can't clobber the change (was an unguarded RMW).
        captured: dict[str, Any] = {}

        def _update(state: dict) -> None:
            hypotheses = state.get("active_hypotheses", []) or []
            target = next(
                (h for h in hypotheses
                 if isinstance(h, dict) and h.get("id") == hypothesis_id),
                None,
            )
            if not target:
                return
            if status:
                target["status"] = status
            if evidence:
                target.setdefault("evidence", []).append(
                    {"step": step or "", "note": evidence, "logged_at": now_iso()}
                )
            target["updated_at"] = now_iso()
            captured["target"] = target

        mutate_state(root, _update)
        target = captured.get("target")
        if not target:
            return {
                "status": "error",
                "message": f"No hypothesis {hypothesis_id}. Use mem_hypothesis_list.",
            }

        log = root / "workspace" / "analysis.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as f:
            f.write(
                f"\n[{now_iso()}] **HYPOTHESIS {hypothesis_id} updated** "
                f"status={target['status']}"
                + (f" evidence={evidence}" if evidence else "")
                + (f" step={step}" if step else "")
                + "\n"
            )
        return {"status": "success", "hypothesis": target}
    except Exception as e:
        logger.exception("hypothesis_update failed")
        return {"status": "error", "message": str(e)}


def hypothesis_list(root: Path) -> dict[str, Any]:
    """Return every tracked hypothesis."""
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        return {
            "status": "success",
            "count": len(state.get("active_hypotheses", []) or []),
            "hypotheses": state.get("active_hypotheses", []) or [],
        }
    except Exception as e:
        logger.exception("hypothesis_list failed")
        return {"status": "error", "message": str(e)}
