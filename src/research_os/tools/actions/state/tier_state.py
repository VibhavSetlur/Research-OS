"""Workspace ``current_tier.json`` — tier-aware routing state.

Lives at ``workspace/.os_state/current_tier.json``. Holds the project's
current tier (one of ``research_os.protocols._tiers.TIERS``), a small
trail of recent transitions for audit, and the timestamp of the last
write.

The router reads this to compute ``tier_transition`` on every
``tool_route`` call. ``tool_step_complete`` writes it forward when the
just-finished step's protocol crosses a tier boundary.

The file is always best-effort: missing file = "no tier yet" (returned
as None). Corrupt file = same. We never error out of the router on
tier-state failure — the router is hot-path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_os.protocols._tiers import TIER_INDEX, is_valid_tier, tier_position

logger = logging.getLogger("research_os.tools.state.tier")

# Public so tests / callers can refer to the file location consistently.
TIER_STATE_REL = (".os_state", "current_tier.json")
TIER_HISTORY_LIMIT = 50


def _tier_path(root: Path) -> Path:
    return root.joinpath(*TIER_STATE_REL)


def get_current_tier(root: Path) -> str | None:
    """Return the currently-active tier, or None if unset / unreadable."""
    p = _tier_path(root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except Exception as exc:
        logger.debug("current_tier.json unreadable: %s", exc)
        return None
    cur = data.get("current_tier")
    return cur if is_valid_tier(cur) else None


def read_tier_state(root: Path) -> dict[str, Any]:
    """Return the whole tier-state document (or a fresh empty one)."""
    p = _tier_path(root)
    if not p.exists():
        return {"current_tier": None, "history": []}
    try:
        data = json.loads(p.read_text())
    except Exception:
        return {"current_tier": None, "history": []}
    if not isinstance(data, dict):
        return {"current_tier": None, "history": []}
    data.setdefault("history", [])
    if not is_valid_tier(data.get("current_tier")):
        data["current_tier"] = None
    return data


def set_current_tier(
    root: Path,
    new_tier: str | None,
    *,
    source_protocol: str | None = None,
    via: str = "tool_route",
) -> dict[str, Any]:
    """Persist ``new_tier`` as the active tier; append a history entry.

    Returns the same dict shape as ``compute_transition`` so callers can
    surface ``from`` / ``to`` without re-reading the file.

    No-ops when ``new_tier`` is None or invalid (a protocol that didn't
    declare a tier shouldn't be allowed to overwrite the workspace's
    current tier).
    """
    if not is_valid_tier(new_tier):
        return {"from": get_current_tier(root), "to": None, "wrote": False}
    state = read_tier_state(root)
    prev = state.get("current_tier")
    if prev == new_tier:
        # No transition; still record a touch so debugging knows the
        # router agreed with the prior decision.
        return {"from": prev, "to": new_tier, "wrote": False}
    state["current_tier"] = new_tier
    history = list(state.get("history") or [])
    history.append({
        "from": prev,
        "to": new_tier,
        "via": via,
        "source_protocol": source_protocol,
        "at": datetime.now(tz=timezone.utc).isoformat(),
    })
    state["history"] = history[-TIER_HISTORY_LIMIT:]
    state["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    p = _tier_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(state, indent=2, default=str))
    except OSError as exc:
        logger.warning("current_tier.json write failed: %s", exc)
        return {"from": prev, "to": new_tier, "wrote": False}
    return {"from": prev, "to": new_tier, "wrote": True}


def compute_transition(root: Path, new_tier: str | None) -> dict[str, Any] | None:
    """Return ``{from, to}`` describing the transition the router would emit.

    Always returns a dict when ``new_tier`` is a valid tier (so callers
    can serialise it). The transition does NOT include direction info;
    callers can derive it from ``tier_position`` if needed.

    Returns None when ``new_tier`` isn't a valid tier — keeps the router
    output null when there's nothing to report.
    """
    if not is_valid_tier(new_tier):
        return None
    prev = get_current_tier(root)
    return {"from": prev, "to": new_tier}


def tier_direction(prev: str | None, new: str | None) -> str | None:
    """Return ``forward`` | ``backward`` | ``same`` | None.

    Used by ``tool_audit_master`` to characterise the project's overall
    movement through tiers.
    """
    if not is_valid_tier(new):
        return None
    if prev is None:
        return "forward"
    pp = tier_position(prev)
    pn = tier_position(new)
    if pp is None or pn is None:
        return None
    if pn > pp:
        return "forward"
    if pn < pp:
        return "backward"
    return "same"


__all__ = [
    "TIER_STATE_REL",
    "TIER_HISTORY_LIMIT",
    "TIER_INDEX",
    "get_current_tier",
    "read_tier_state",
    "set_current_tier",
    "compute_transition",
    "tier_direction",
]
