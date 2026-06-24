"""Staleness-verdict reader for the world-state floor gate.

The READER half of the staleness gate (docs/v4/STALENESS_GATE.md). Lives
on the reasoning side (``server/``) and MUST NOT import
``research_os.daemon`` — the preflight-enforced seam (DESIGN_V4 #1). It
reads the daemon-owned verdict sidecar by SHAPE, exactly like
``server/consent.py`` reads the consent ledger and
``handlers/meta_workspace.py`` reads daemon discovery.

Why this exists
---------------
The daemon detects when a run's recorded inputs have changed on disk
(``daemon/staleness.py``) and persists a compact verdict to
``.os_state/staleness/verdict.json``. The floor gate consults this verdict
so the AI cannot compile the final deliverable while results are built on
data that changed — failure mode #4 (silent corner-cutting) in its purest
form.

Fail-safe DIRECTION (deliberate, see the design doc)
----------------------------------------------------
Unlike consent (fail CLOSED — no token, refuse), staleness fails toward
NOT blocking when there is no affirmative, CURRENT staleness claim:

  * verdict ABSENT / unreadable / malformed → no claim → gate does NOT
    fire (most projects never run a daemon; a freshness gate that fired on
    every project without a verdict would brick the default flow).
  * verdict says ``status == "stale"`` AND is at least as new as the
    freshest run → a daemon currently determined results are stale → gate
    FIRES.
  * verdict OLDER than the freshest run manifest → it predates current
    state and can't be trusted → treated as absent (no claim). This is the
    freshness-of-the-freshness-check: re-running the affected steps and
    not re-assessing must not leave a stale *verdict* blocking forever.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_VERDICT_SCHEMA = 1


def _verdict_path(root: Path) -> Path:
    """Path to the daemon-owned staleness verdict sidecar for this project."""
    return Path(root) / ".os_state" / "staleness" / "verdict.json"


def _runs_dir(root: Path) -> Path:
    return Path(root) / ".os_state" / "runs"


def _parse_iso(ts: str) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _newest_run_mtime(root: Path) -> float:
    """Largest mtime among run manifests (0.0 if none). Cheap, fail-safe.

    Used to decide whether a verdict predates current state. We compare the
    verdict's ``assessed_at`` against the freshest run.json mtime: if a run
    was written AFTER the verdict, the verdict is out of date and we ignore
    it (no claim) rather than block on a stale assessment.
    """
    newest = 0.0
    runs = _runs_dir(root)
    try:
        if not runs.is_dir():
            return 0.0
        for run_dir in runs.iterdir():
            manifest = run_dir / "run.json"
            try:
                m = manifest.stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest = m
    except OSError:
        return 0.0
    return newest


def _load_verdict(root: Path) -> dict | None:
    """Read + validate the verdict sidecar. None on any miss (fail-safe)."""
    path = _verdict_path(root)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema") != _VERDICT_SCHEMA:
        return None
    if data.get("status") not in {"stale", "fresh"}:
        return None
    return data


def current_stale_verdict(root: Path) -> dict | None:
    """Return the verdict IFF it currently asserts staleness, else None.

    Returns the verdict dict only when ALL hold:
      * a well-formed, current-schema verdict exists,
      * its ``status`` is ``"stale"``,
      * it is not older than the freshest run (a verdict written before the
        newest run is out of date → ignored).

    None in every other case (absent, fresh, malformed, or out-of-date) —
    meaning "no current staleness claim", so the gate does not fire.
    """
    verdict = _load_verdict(root)
    if verdict is None:
        return None
    if verdict.get("status") != "stale":
        return None
    # Age check: ignore a verdict older than the freshest run.
    assessed = _parse_iso(verdict.get("assessed_at", ""))
    newest = _newest_run_mtime(Path(root))
    if assessed is not None and newest > 0.0:
        if assessed.timestamp() < newest:
            return None
    return verdict


def is_currently_stale(root: Path) -> bool:
    """True iff there is a current daemon verdict asserting staleness."""
    return current_stale_verdict(root) is not None
