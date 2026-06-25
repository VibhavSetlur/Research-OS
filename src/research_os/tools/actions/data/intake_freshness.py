"""Intake re-entry detection.

Decides whether ``project_startup`` should fully autofill intake or
skip / refresh-only:

- ``inputs/intake.md`` missing or stub → **full**
- ``inputs/intake.md`` exists with > 500 chars + edited in last 90 days → **skip**
- ``inputs/intake.md`` exists but older than 90 days → **refresh-only**

Also surfaces whether at least one numbered step has ``conclusions.md``
— the signal ``mid_pipeline_entry`` should become the default.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.data.intake_freshness")


_INTAKE_TEMPLATE_MARKERS = (
    "<replace with",
    "[fill in",
    "tbd",
    "todo",
    "ro:intake-template",  # the unfilled scaffold template (chat-or-files guide)
)


def _is_substantive(text: str, min_chars: int = 500) -> bool:
    if len(text) < min_chars:
        return False
    cleaned = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < min_chars:
        return False
    lower = cleaned.lower()
    if any(m in lower for m in _INTAKE_TEMPLATE_MARKERS):
        return False
    return True


def _count_completed_steps(workspace: Path) -> int:
    if not workspace.is_dir():
        return 0
    n = 0
    for d in workspace.iterdir():
        if (
            d.is_dir()
            and d.name[:2].isdigit()
            and not d.name.endswith("__DEAD_END")
            and (d / "conclusions.md").exists()
        ):
            n += 1
    return n


def intake_freshness(root: Path, *, fresh_window_days: int = 90) -> dict[str, Any]:
    """Return recommended intake depth + reasoning."""
    try:
        intake_path = root / "inputs" / "intake.md"
        workspace = root / "workspace"
        completed_steps = _count_completed_steps(workspace)

        details: dict[str, Any] = {
            "intake_exists": intake_path.exists(),
            "completed_steps": completed_steps,
            "fresh_window_days": fresh_window_days,
        }

        if not intake_path.exists():
            details["reason"] = "inputs/intake.md does not exist"
            return {
                "status": "success",
                "recommended_depth": "full",
                "mid_pipeline_entry_recommended": completed_steps >= 1,
                "details": details,
            }

        try:
            text = intake_path.read_text()
        except Exception as exc:
            details["reason"] = f"could not read intake: {exc}"
            return {
                "status": "success",
                "recommended_depth": "full",
                "mid_pipeline_entry_recommended": completed_steps >= 1,
                "details": details,
            }

        details["intake_chars"] = len(text)
        details["substantive"] = _is_substantive(text)

        age_days = (time.time() - intake_path.stat().st_mtime) / 86400
        details["age_days"] = round(age_days, 1)

        if not details["substantive"]:
            details["reason"] = (
                f"intake is {len(text)} chars or contains template markers — "
                "not substantive"
            )
            depth = "full"
        elif age_days <= fresh_window_days:
            details["reason"] = (
                f"intake is {int(age_days)} day(s) old (≤ "
                f"{fresh_window_days}) and substantive; safe to skip "
                "autofill"
            )
            depth = "skip"
        else:
            details["reason"] = (
                f"intake is {int(age_days)} day(s) old (> "
                f"{fresh_window_days}) but substantive; refresh-only "
                "(re-read but do not regenerate)"
            )
            depth = "refresh-only"

        return {
            "status": "success",
            "recommended_depth": depth,
            "mid_pipeline_entry_recommended": completed_steps >= 1,
            "details": details,
        }
    except Exception as e:
        logger.exception("intake_freshness failed")
        return {"status": "error", "message": str(e)}
