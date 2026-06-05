"""Tool failure memory — paywall + permanent 404 cache (v1.5.0 — Theme 12).

Persists per-tool failures to ``workspace/.os_state/tool_failures.jsonl``
so subsequent attempts skip known-bad URLs and DOIs. Designed for
``tool_literature_download`` + ``tool_literature_search_and_save`` but
generic enough for any HTTP-shaped tool.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.paywall_memory")


_PERMANENT_REASONS = {
    "paywall",
    "permanent_404",
    "permanent_403",
    "no_pdf_found",
    "permanent_error",
}


def _failures_path(root: Path) -> Path:
    p = root / "workspace" / ".os_state" / "tool_failures.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _normalise_target(target: str) -> str:
    """Normalise URL / DOI so cache hits work across casing + trailing slashes."""
    if not target:
        return ""
    t = target.strip().rstrip("/").lower()
    m = re.search(r"(10\.\d{4,9}/[-._;()/:a-z0-9]+)", t)
    if m:
        return f"doi:{m.group(1)}"
    return t


def record_failure(
    root: Path,
    *,
    tool: str,
    target: str,
    reason: str,
    error_text: str = "",
    permanent: bool = False,
) -> dict[str, Any]:
    """Append a failure record. ``permanent=True`` short-circuits future retries."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "target": target,
            "target_key": _normalise_target(target),
            "reason": reason,
            "error_text": (error_text or "")[:200],
            "permanent": bool(permanent or reason in _PERMANENT_REASONS),
        }
        path = _failures_path(root)
        with open(path, "a") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
        return {"status": "success", "record": record}
    except Exception as e:
        logger.exception("record_failure failed")
        return {"status": "error", "message": str(e)}


def _load_failures(root: Path) -> list[dict[str, Any]]:
    path = _failures_path(root)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def is_known_bad(root: Path, target: str) -> dict[str, Any]:
    """Return {known_bad, reason, last_attempt_ts} for a URL / DOI."""
    try:
        key = _normalise_target(target)
        if not key:
            return {"known_bad": False}
        records = _load_failures(root)
        permanent_hit = None
        for rec in records:
            if rec.get("target_key") == key and rec.get("permanent"):
                permanent_hit = rec
        if permanent_hit:
            return {
                "known_bad": True,
                "reason": permanent_hit.get("reason"),
                "last_attempt_ts": permanent_hit.get("ts"),
                "tool": permanent_hit.get("tool"),
            }
        recent = [r for r in records if r.get("target_key") == key]
        if len(recent) >= 3:
            return {
                "known_bad": True,
                "reason": "max_retries",
                "attempts": len(recent),
                "last_attempt_ts": recent[-1].get("ts"),
                "tool": recent[-1].get("tool"),
            }
        return {"known_bad": False, "prior_attempts": len(recent)}
    except Exception as e:
        logger.exception("is_known_bad failed")
        return {"known_bad": False, "error": str(e)}


def step_summary_failures(root: Path, step_id: str) -> list[dict[str, Any]]:
    """Return the failure list a step's summary should embed.

    Pulled into ``step_summary.yaml.tool_failures`` by the literature
    download tools so the per-step audit shows what was tried.
    """
    try:
        records = _load_failures(root)
        return [
            {
                "tool": r.get("tool"),
                "target": r.get("target"),
                "reason": r.get("reason"),
                "ts": r.get("ts"),
                "permanent": r.get("permanent", False),
            }
            for r in records
            if step_id in str(r.get("error_text", ""))
            or step_id in str(r.get("target", ""))
        ][-20:]
    except Exception:
        logger.exception("step_summary_failures failed")
        return []


def list_failures(root: Path, *, limit: int = 50) -> dict[str, Any]:
    """List recent failures (for audit / debugging)."""
    try:
        records = _load_failures(root)
        permanent = [r for r in records if r.get("permanent")]
        return {
            "status": "success",
            "total": len(records),
            "permanent_count": len(permanent),
            "recent": records[-limit:],
            "permanent_targets": sorted({r.get("target_key", "") for r in permanent}),
        }
    except Exception as e:
        logger.exception("list_failures failed")
        return {"status": "error", "message": str(e)}
