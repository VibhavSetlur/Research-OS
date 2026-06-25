"""Audit-judge scoring — a durable, structured self-assessment of work quality.

docs/AUDIT_JUDGE.md.

Deep + autonomous research needs a HONEST scorecard: how good is this result,
what are its limitations, what would improve it? Without one, an autonomous loop
either stops too early ("looks done") or spins forever ("never satisfied").

DOCTRINE: the tool does NOT score the science — the AI (the brain) authors the
judgment. This module provides the RUBRIC + records the verdict durably so the
loop, the researcher, and the synthesis gate can all act on the same scorecard.
It validates the shape (every dimension scored + justified), it does not invent
numbers.

A scorecard scores work along dimensions (the AI picks the relevant ones for
the work — analysis, a tool build, a draft), each 0–5 with a written
justification, plus explicit ``limitations`` and ``improvements``. The overall
verdict is one of: ``ship`` (good enough for the goal), ``iterate`` (close,
specific improvements named), ``redo`` (fundamentally flawed). The loop uses
the verdict: ``iterate``/``redo`` → keep going; ``ship`` → the goal may be met.

stdlib only. Pure validation + durable record. Never raises.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_JUDGE_DIR = "judge"
_VALID_VERDICTS = ("ship", "iterate", "redo")


def _judge_dir(root: Path) -> Path:
    return Path(root) / ".os_state" / _JUDGE_DIR


def score_work(
    root: str | Path,
    *,
    subject: str,
    dimensions: list[dict[str, Any]],
    limitations: list[str],
    improvements: list[str],
    verdict: str,
    goal: str | None = None,
) -> dict[str, Any]:
    """Record an AI-authored scorecard for a piece of work. Validates shape.

    Args:
      subject: what's being judged (e.g. "step 03 survival analysis", "the
               peak-caller tool v2", "the discussion draft").
      dimensions: list of {name, score (0-5 int), justification (str)}. The AI
               picks the dimensions that matter for THIS work — there is no
               fixed menu (doctrine: the brain decides what to judge).
      limitations: explicit, honest limitations of the work as it stands.
      improvements: specific, actionable changes that would raise the score.
      verdict: one of ship | iterate | redo.
      goal: the goal this work serves (for the autonomous loop).

    Returns the persisted scorecard, or {"status":"error",...} when the shape
    is invalid (so the AI is forced to produce a real, complete judgment — a
    half-filled scorecard is rejected, not silently accepted).
    """
    root = Path(root)

    if verdict not in _VALID_VERDICTS:
        return {
            "status": "error",
            "message": f"verdict must be one of {_VALID_VERDICTS}, got {verdict!r}",
        }
    if not isinstance(dimensions, list) or not dimensions:
        return {
            "status": "error",
            "message": "at least one scored dimension is required",
        }
    norm_dims: list[dict[str, Any]] = []
    for d in dimensions:
        if not isinstance(d, dict):
            return {"status": "error", "message": "each dimension must be an object"}
        name = str(d.get("name", "")).strip()
        just = str(d.get("justification", "")).strip()
        try:
            score = int(d.get("score"))
        except (TypeError, ValueError):
            return {"status": "error", "message": f"dimension '{name}' has no integer score"}
        if not name:
            return {"status": "error", "message": "a dimension is missing its name"}
        if not (0 <= score <= 5):
            return {"status": "error", "message": f"dimension '{name}' score {score} out of 0..5"}
        if len(just) < 10:
            return {
                "status": "error",
                "message": (
                    f"dimension '{name}' needs a real justification (>=10 chars) "
                    "— a score without a reason is not a judgment"
                ),
            }
        norm_dims.append({"name": name, "score": score, "justification": just})

    # iterate/redo MUST name improvements (otherwise the loop has nothing to
    # act on); ship MAY still list limitations (honest shipping).
    if verdict in ("iterate", "redo") and not improvements:
        return {
            "status": "error",
            "message": (
                f"verdict '{verdict}' requires at least one concrete improvement "
                "— the loop needs to know what to change next"
            ),
        }

    scores = [d["score"] for d in norm_dims]
    scorecard = {
        "schema": 1,
        "subject": subject,
        "goal": goal,
        "scored_at": time.time(),
        "dimensions": norm_dims,
        "mean_score": round(sum(scores) / len(scores), 2),
        "min_score": min(scores),
        "limitations": [str(x) for x in (limitations or [])],
        "improvements": [str(x) for x in (improvements or [])],
        "verdict": verdict,
    }

    # Persist: a timestamped record + a "latest" pointer for the loop to read.
    try:
        d = _judge_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        slug = "".join(c if c.isalnum() else "_" for c in subject)[:40]
        (d / f"{stamp}__{slug}.json").write_text(
            json.dumps(scorecard, indent=2, default=str), encoding="utf-8"
        )
        (d / "latest.json").write_text(
            json.dumps(scorecard, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass

    scorecard["status"] = "success"
    scorecard["loop_signal"] = (
        "goal may be met — verify, then stop the loop"
        if verdict == "ship" else
        "keep iterating — act on the named improvements"
    )
    return scorecard


def latest_scorecard(root: str | Path) -> dict[str, Any] | None:
    """Read the most recent scorecard (for the loop / a returning session)."""
    try:
        path = _judge_dir(Path(root)) / "latest.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
