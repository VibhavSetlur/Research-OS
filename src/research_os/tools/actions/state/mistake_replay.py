"""Coaching-mode replay: surface recurring patterns from local logs.

Reads workspace/.os_state/reliability.jsonl (telemetry-free local event
log) + workspace/logs/override_log.md (audit-gate bypass log). Groups
events by protocol + event_type. Returns the top patterns the
researcher keeps tripping — the AI can use this in coaching mode to
build the researcher's mental model of their own failure modes.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.mistake_replay")


_OVERRIDE_HEADER_PAT = re.compile(r"^##\s+", re.MULTILINE)


def _read_reliability(root: Path) -> list[dict]:
    path = root / "workspace" / ".os_state" / "reliability.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_overrides(root: Path) -> list[str]:
    path = root / "workspace" / "logs" / "override_log.md"
    if not path.exists():
        return []
    text = path.read_text()
    # Split on top-level '## ' headers; each block is one override entry.
    parts = _OVERRIDE_HEADER_PAT.split(text)
    return [p.strip() for p in parts if p.strip()]


def mistake_replay(root: Path, *, limit: int = 5) -> dict[str, Any]:
    """Return the top recurring patterns across reliability + override logs."""
    try:
        events = _read_reliability(root)
        overrides = _read_overrides(root)
        if not events and not overrides:
            return {
                "status": "success",
                "patterns": [],
                "message": (
                    "No reliability events or overrides logged yet — "
                    "nothing to coach against."
                ),
            }
        # Group reliability events by (protocol, event_type).
        gate_keys = ("gate_fire", "gate_abandon", "tool_error", "override_used")
        counter: Counter[tuple[str, str]] = Counter()
        examples: dict[tuple[str, str], list[str]] = {}
        for ev in events:
            t = ev.get("event_type", "")
            if t not in gate_keys:
                continue
            protocol = ev.get("protocol_name") or "(unknown)"
            key = (protocol, t)
            counter[key] += 1
            payload = ev.get("payload") or {}
            label = payload.get("gate") or payload.get("tool") or payload.get("step_id") or ""
            if label and key not in examples:
                examples[key] = [str(label)]
            elif label and len(examples.get(key, [])) < 3:
                examples[key].append(str(label))
        patterns: list[dict] = []
        for (protocol, ev_type), count in counter.most_common(limit):
            patterns.append({
                "protocol": protocol,
                "event_type": ev_type,
                "count": count,
                "examples": examples.get((protocol, ev_type), []),
            })
        return {
            "status": "success",
            "patterns": patterns,
            "total_events": len(events),
            "total_overrides": len(overrides),
            "advice": (
                "Coaching: surface these to the researcher BEFORE the next "
                "step that touches the same protocol — ask whether they "
                "want to fix the underlying habit or override again."
            ),
        }
    except Exception as e:
        logger.exception("mistake_replay failed")
        return {"status": "error", "message": str(e)}
