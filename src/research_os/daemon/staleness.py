"""Staleness detection — the freshness verdict (Phase 1.14).

DESIGN_V4.md feature #8. The lineage graph (1.13) is passive: it shows
which run fed which. Staleness makes it *active* — it answers the question
that keeps computational researchers up at night:

    "Is this figure still valid, or was it built from data that changed?"

A run is **input-stale** when a file it recorded as an input now has a
different content hash on disk than the hash captured at run time: the
result was computed from inputs that no longer exist in that form. A run
is **transitively stale** when any of its lineage ancestors is stale —
even if the run's own direct inputs are unchanged, an upstream result it
depends on is no longer trustworthy, so neither is this one.

The check is pure given an injected hash function, so it is trivially
testable and never depends on the daemon being up. The daemon/CLI inject
``provenance.hash_file`` to read current on-disk state.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import lineage as _lineage

# Status constants — stable strings for CLI, HTTP, and tests.
FRESH = "fresh"
INPUT_STALE = "input-stale"          # a direct input changed on disk
TRANSITIVE_STALE = "transitive-stale"  # an upstream run is stale
UNKNOWN = "unknown"                    # inputs unreadable / nothing to check


def _run_id(manifest: dict) -> str:
    return manifest.get("id") or manifest.get("run_id") or "?"


def _recorded_inputs(manifest: dict) -> dict[str, str]:
    prov = manifest.get("provenance") or {}
    inputs = prov.get("inputs") or {}
    return {p: h for p, h in inputs.items() if h}


def check_input_staleness(
    manifest: dict,
    hash_file: Callable[[str], str | None],
) -> dict[str, Any]:
    """Check one run's direct inputs against current on-disk hashes.

    Args:
        manifest: the run manifest (reads ``provenance.inputs``).
        hash_file: maps a path -> current 'sha256:...' (or None if gone).

    Returns ``{status, changed: [{path, recorded, current}], missing: [...],
    checked: int}``. Status is FRESH, INPUT_STALE, or UNKNOWN (no inputs
    recorded — can't make a claim either way).
    """
    recorded = _recorded_inputs(manifest)
    if not recorded:
        return {"status": UNKNOWN, "changed": [], "missing": [], "checked": 0}

    changed: list[dict] = []
    missing: list[str] = []
    for path, rec_hash in recorded.items():
        cur = hash_file(path)
        if cur is None:
            missing.append(path)
        elif cur != rec_hash:
            changed.append({"path": path, "recorded": rec_hash, "current": cur})

    status = INPUT_STALE if (changed or missing) else FRESH
    changed.sort(key=lambda c: c["path"])
    missing.sort()
    return {
        "status": status,
        "changed": changed,
        "missing": missing,
        "checked": len(recorded),
    }


def assess(
    manifests: list[dict],
    hash_file: Callable[[str], str | None],
) -> dict[str, Any]:
    """Whole-project freshness assessment over the lineage DAG.

    Each run is first checked for direct input staleness, then transitive
    staleness is propagated DOWN the lineage graph: every descendant of an
    input-stale run is transitive-stale (its provenance chain is no longer
    trustworthy), unless it is itself directly input-stale (the stronger
    label wins).

    Returns:
        {
          "runs": {run_id: {status, reason, changed, missing,
                            stale_ancestors}},
          "stale": [run_id, ...],      # any non-fresh, non-unknown run
          "fresh": [run_id, ...],
          "counts": {...},
        }
    """
    graph = _lineage.build_lineage(manifests)
    by_id = {_run_id(m): m for m in manifests}

    # Pass 1: direct input staleness.
    direct: dict[str, dict] = {}
    for rid, m in by_id.items():
        direct[rid] = check_input_staleness(m, hash_file)

    directly_stale = {rid for rid, d in direct.items() if d["status"] == INPUT_STALE}

    # Pass 2: transitive propagation down the DAG.
    runs: dict[str, dict] = {}
    for rid in by_id:
        d = direct[rid]
        anc = _lineage.ancestors(graph, rid)
        stale_anc = [a for a in anc if a in directly_stale]
        if d["status"] == INPUT_STALE:
            status, reason = INPUT_STALE, "a direct input changed on disk"
        elif stale_anc:
            status, reason = TRANSITIVE_STALE, "an upstream run is stale"
        elif d["status"] == UNKNOWN:
            status, reason = UNKNOWN, "no recorded inputs to verify"
        else:
            status, reason = FRESH, "all inputs unchanged; provenance intact"
        runs[rid] = {
            "status": status,
            "reason": reason,
            "changed": d["changed"],
            "missing": d["missing"],
            "stale_ancestors": stale_anc,
        }

    stale = sorted(r for r, v in runs.items()
                   if v["status"] in (INPUT_STALE, TRANSITIVE_STALE))
    fresh = sorted(r for r, v in runs.items() if v["status"] == FRESH)
    unknown = sorted(r for r, v in runs.items() if v["status"] == UNKNOWN)

    return {
        "runs": runs,
        "stale": stale,
        "fresh": fresh,
        "unknown": unknown,
        "counts": {
            "total": len(runs),
            "stale": len(stale),
            "fresh": len(fresh),
            "unknown": len(unknown),
            "directly_stale": len(directly_stale),
        },
    }


def status_glyph(status: str) -> str:
    """Single-char status glyph for terminal output."""
    return {
        FRESH: "✓",
        INPUT_STALE: "✗",
        TRANSITIVE_STALE: "≈",
        UNKNOWN: "·",
    }.get(status, "·")
