"""Phase-4c downstream consumers for the cross-audit findings ledger.

Every Phase-4 audit appends one JSON-per-line entry to
``workspace/logs/.audit_findings.jsonl`` via
:func:`research_os.tools.actions.audit._base.write_audit_outputs`. The
ledger is append-only so a project rerun preserves the full historical
trail — every finding ever raised, in chronological order.

This module gives downstream tools (and the AI) two read paths on top
of that ledger:

* :func:`audit_findings_query` — filter the latest snapshot by
  ``severity`` / ``dimension`` / ``step`` / ``since``. "Latest
  snapshot" = the most recent occurrence of each stable ``id`` in the
  ledger (so a finding that was emitted on three reruns counts once).
* :func:`audit_findings_diff` — snapshot the ledger as of two
  timestamps and report ``added`` / ``resolved`` / ``changed`` between
  them, keyed by the stable ``id``.

Both functions read the same file and never mutate it; callers can run
them safely from any tool without risking the audit trail.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.audit.findings_query")


# Public path constant — every downstream consumer (this module,
# tool_synthesize gating, the dashboard) reads from here. Keeping it
# centralised means a future relocation only edits one constant.
FINDINGS_JSONL_RELPATH = Path("workspace") / "logs" / ".audit_findings.jsonl"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _findings_jsonl_path(root: Path) -> Path:
    """Return the absolute path to the cross-audit findings ledger."""
    return root / FINDINGS_JSONL_RELPATH


def _load_jsonl_lines(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load every well-formed JSON object from the ledger, in file order.

    Malformed lines are skipped with a debug log — the ledger is
    append-only so a corrupt tail (rare, but possible from a partial
    write) should not block downstream readers.
    """
    if not jsonl_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in jsonl_path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.debug("skipping malformed line in %s: %s", jsonl_path, exc)
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp; tolerate trailing 'Z' (UTC)."""
    if not ts:
        return None
    try:
        # Python's fromisoformat accepts 'Z' as of 3.11; swap for safety on
        # the 3.12 baseline and any older callers still in flight.
        normalised = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _latest_snapshot(
    findings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reduce the append-only ledger to {id: most-recent-occurrence}.

    The ledger appends a fresh row each time an audit reruns. Most
    audits derive stable uuids (uuid5) so the same logical finding
    keeps the same id across reruns — taking the LAST entry per id
    gives the current state. Findings without an id are tagged by
    their full row hash so they don't collide.
    """
    snap: dict[str, dict[str, Any]] = {}
    for row in findings:
        key = row.get("id") or json.dumps(row, sort_keys=True)
        snap[key] = row
    return snap


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def audit_findings_query(
    root: Path,
    *,
    severity: str | None = None,
    dimension: str | None = None,
    step: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Return the latest snapshot, optionally filtered.

    Parameters
    ----------
    root:
        Project root (parent of ``workspace/``).
    severity:
        Filter to one of ``"block"`` / ``"warn"`` / ``"info"``. ``None``
        returns every severity.
    dimension:
        Filter to one dimension label (e.g. ``"completeness"``). ``None``
        returns every dimension.
    step:
        Filter to findings whose ``evidence_paths`` reference the given
        step folder (matched against ``workspace/<step>/`` prefix or any
        path containing ``/<step>/``). ``None`` returns every step.
    since:
        Filter to findings whose ``generated_at`` is on/after the given
        ISO-8601 timestamp. ``None`` returns every timestamp.

    Returns a dict::

        {
            "status": "success",
            "findings": [<finding-dict>, ...],
            "count": <int>,
            "filters": {"severity": ..., "dimension": ..., ...},
        }

    On a missing ledger the result is ``{"findings": [], "count": 0,
    "status": "success", ...}`` — an empty ledger is a valid state
    (the project simply hasn't run any audits yet).
    """
    jsonl = _findings_jsonl_path(root)
    rows = _load_jsonl_lines(jsonl)
    snapshot = list(_latest_snapshot(rows).values())

    # Build filter predicates once so the loop stays tight.
    since_dt = _parse_iso(since) if since else None
    step_token = step.strip("/") if step else None

    def _matches(row: dict[str, Any]) -> bool:
        if severity is not None and row.get("severity") != severity:
            return False
        if dimension is not None and row.get("dimension") != dimension:
            return False
        if step_token is not None:
            paths = row.get("evidence_paths") or []
            # Match either an exact ``workspace/<step>/...`` prefix or a
            # substring of the form ``/<step>/`` — the second form lets
            # callers pass just the numbered folder name.
            target = f"workspace/{step_token}/"
            mid = f"/{step_token}/"
            if not any(
                isinstance(p, str)
                and (p.startswith(target) or mid in p or p == f"workspace/{step_token}")
                for p in paths
            ):
                return False
        if since_dt is not None:
            row_dt = _parse_iso(row.get("generated_at"))
            if row_dt is None or row_dt < since_dt:
                return False
        return True

    matched = [r for r in snapshot if _matches(r)]

    return {
        "status": "success",
        "findings": matched,
        "count": len(matched),
        "filters": {
            "severity": severity,
            "dimension": dimension,
            "step": step,
            "since": since,
        },
        "ledger_path": str(FINDINGS_JSONL_RELPATH),
    }


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _snapshot_as_of(
    rows: list[dict[str, Any]],
    timestamp: datetime | None,
    *,
    audits_rerun_after: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``{id: row}`` for every finding "active" at the snapshot
    timestamp.

    Semantics:

    * The latest row (by file position) for each id whose ``generated_at``
      is ≤ ``timestamp`` is a candidate.
    * If ``audits_rerun_after`` is provided, a candidate is DROPPED
      when its audit (``audit_name``) re-ran in the window
      ``(audits_rerun_after, timestamp]`` but did NOT re-emit this id.
      That is: the audit got another chance and chose not to report
      this finding — it has been resolved.

    Callers that want the simple "state at t" snapshot pass
    ``audits_rerun_after=None``. Callers diffing two timestamps pass
    ``audits_rerun_after=A`` when building snapshot B so a finding
    that was active at A and never re-emitted by any audit run in
    (A, B] is correctly classified as resolved.

    Rows without a parseable ``generated_at`` are kept (defensive: a
    stripped fixture finding should not silently disappear). Within
    the cutoff window the latest row per id wins.
    """
    # Pass 1: collect candidate latest emission per id, bounded by ``timestamp``.
    candidates: dict[str, dict[str, Any]] = {}
    audit_rerun_in_window: dict[str, bool] = {}
    ids_seen_in_window: set[str] = set()
    for row in rows:
        row_dt = _parse_iso(row.get("generated_at"))
        in_bound = (
            timestamp is None
            or row_dt is None
            or row_dt <= timestamp
        )
        if not in_bound:
            continue
        key = row.get("id") or json.dumps(row, sort_keys=True)
        candidates[key] = row
        # Track which audits emitted at least one row in the resolution
        # window (audits_rerun_after, timestamp].
        if audits_rerun_after is not None and row_dt is not None:
            if row_dt > audits_rerun_after and (
                timestamp is None or row_dt <= timestamp
            ):
                an = row.get("audit_name")
                if an:
                    audit_rerun_in_window[an] = True
                ids_seen_in_window.add(key)

    if audits_rerun_after is None:
        return candidates

    # Pass 2: drop a candidate when its audit reran in the window but
    # did NOT re-emit this id. That id has been resolved.
    snap: dict[str, dict[str, Any]] = {}
    for key, row in candidates.items():
        an = row.get("audit_name")
        if an and audit_rerun_in_window.get(an) and key not in ids_seen_in_window:
            # Audit reran and chose not to re-emit → resolved.
            continue
        snap[key] = row
    return snap


def audit_findings_diff(
    root: Path,
    *,
    timestamp_a: str,
    timestamp_b: str,
) -> dict[str, Any]:
    """Diff two snapshots of the findings ledger by stable id.

    Resolution semantics: snapshot_a is the latest emission per id at
    or before timestamp_a. snapshot_b is the latest emission per id at
    or before timestamp_b, EXCLUDING any id whose audit re-ran in the
    window ``(timestamp_a, timestamp_b]`` but did NOT re-emit that id
    (the audit got another chance and didn't reproduce the finding, so
    we call it resolved). "Audit re-ran" is detected by the presence of
    any row with the same ``audit_name`` and ``generated_at`` in the
    resolution window.

    Parameters
    ----------
    root:
        Project root (parent of ``workspace/``).
    timestamp_a:
        ISO-8601 timestamp for the EARLIER snapshot ("before").
    timestamp_b:
        ISO-8601 timestamp for the LATER snapshot ("after"). Must be
        chronologically on/after ``timestamp_a`` — the function does not
        flip them automatically because the asymmetric naming
        (added vs resolved) only reads correctly with the documented
        order.

    Returns::

        {
            "status": "success",
            "added":    [<finding-dict>, ...],  # in B but not A
            "resolved": [<finding-dict>, ...],  # in A but not B
            "changed":  [{"id": ..., "before": {...}, "after": {...}}, ...],
            "summary": {"added": N, "resolved": M, "changed": K},
            "timestamps": {"a": ..., "b": ...},
        }

    Both timestamps must parse — an unparseable string yields
    ``status="error"`` so the caller knows the diff is unreliable.
    """
    dt_a = _parse_iso(timestamp_a)
    dt_b = _parse_iso(timestamp_b)
    if dt_a is None or dt_b is None:
        return {
            "status": "error",
            "message": (
                "audit_findings_diff: both timestamp_a and timestamp_b must "
                "be parseable ISO-8601 strings (e.g. '2026-06-05T12:00:00Z')."
            ),
        }
    if dt_b < dt_a:
        return {
            "status": "error",
            "message": (
                "audit_findings_diff: timestamp_b must be on/after "
                "timestamp_a (got b < a). Pass the EARLIER timestamp as "
                "timestamp_a and the LATER as timestamp_b."
            ),
        }

    rows = _load_jsonl_lines(_findings_jsonl_path(root))
    snap_a = _snapshot_as_of(rows, dt_a)
    # Snapshot B uses resolution semantics: a finding that was active
    # at A and whose audit reran in (A, B] without re-emitting it is
    # considered resolved and excluded from snap_b.
    snap_b = _snapshot_as_of(rows, dt_b, audits_rerun_after=dt_a)

    ids_a = set(snap_a)
    ids_b = set(snap_b)

    added_ids = ids_b - ids_a
    resolved_ids = ids_a - ids_b
    shared_ids = ids_a & ids_b

    # "changed" = same id, different content. Compare structural fields
    # (severity / dimension / evidence_paths / suggested_fix) because
    # generated_at + ro_version always shift on rerun and would create
    # spurious churn.
    _STRUCT_KEYS = ("severity", "dimension", "evidence_paths", "suggested_fix")

    def _struct(row: dict[str, Any]) -> tuple:
        return tuple(
            (
                tuple(row.get(k) or ())
                if k == "evidence_paths"
                else row.get(k)
            )
            for k in _STRUCT_KEYS
        )

    changed: list[dict[str, Any]] = []
    for fid in sorted(shared_ids):
        before = snap_a[fid]
        after = snap_b[fid]
        if _struct(before) != _struct(after):
            changed.append({"id": fid, "before": before, "after": after})

    added = [snap_b[i] for i in sorted(added_ids)]
    resolved = [snap_a[i] for i in sorted(resolved_ids)]

    return {
        "status": "success",
        "added": added,
        "resolved": resolved,
        "changed": changed,
        "summary": {
            "added": len(added),
            "resolved": len(resolved),
            "changed": len(changed),
        },
        "timestamps": {"a": timestamp_a, "b": timestamp_b},
        "ledger_path": str(FINDINGS_JSONL_RELPATH),
    }


# ---------------------------------------------------------------------------
# Helper used by tool_synthesize's BLOCK-gate (Phase-4c task 3)
# ---------------------------------------------------------------------------


def unresolved_block_findings(root: Path) -> list[dict[str, Any]]:
    """Return every BLOCK finding currently present in the latest snapshot.

    Helper used by :func:`tool_synthesize` to refuse compilation when
    any unresolved BLOCK finding sits in the ledger. The snapshot
    semantics mean a BLOCK finding emitted on an earlier run but absent
    from the most recent run for the same gate is considered resolved
    (the audit reran and didn't reproduce it).
    """
    rows = _load_jsonl_lines(_findings_jsonl_path(root))
    snap = _latest_snapshot(rows)
    return [r for r in snap.values() if r.get("severity") == "block"]
