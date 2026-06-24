"""Declared-gate spec: protocols author hard gates, the engine enforces.

This is the HYBRID layer (docs/v4/HYBRID_ARCHITECTURE.md). Floor gates —
the actions that MUST stop and ask even in hands-off mode — used to live
twice: as prose in ``guidance/autopilot.yaml`` and as hand-maintained
Python in ``autopilot_gate.py``. Two sources of truth drift. Now a
protocol DECLARES its gates in a machine-readable ``enforcement.gates``
block, a build step compiles every protocol's block into one sidecar
(``protocols/_gate_meta.json``), and this module reads that sidecar and
evaluates a gate's arg-match predicate.

Seam (DESIGN_V4 #1, preflight-enforced): this module lives on the
reasoning side (``server/``) and MUST NOT import ``research_os.daemon``.
It only reads the compiled sidecar shipped in the package. The daemon's
role (UNSKIPPABLE_GATES.md) is orthogonal: it makes a fired gate
un-skippable by minting consent; THIS module decides which gates fire.

Fail-safe: every loader path falls back to ``[]`` (and the caller keeps
its built-in legacy tables) so a missing/garbage sidecar never drops a
floor — the engine keeps enforcing, it just can't be EXTENDED by a
protocol until the sidecar is rebuilt.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The compiled sidecar ships next to the protocols, exactly like
# _route_meta.json sits next to _router_index.yaml.
_GATE_META_PATH = (
    Path(__file__).resolve().parent.parent / "protocols" / "_gate_meta.json"
)

_GATE_META_SCHEMA = 1


def _load_gate_meta(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the compiled gate list from the sidecar. Fail SAFE to [].

    A missing, unreadable, malformed, or wrong-schema sidecar yields an
    empty list; the caller then relies on its built-in legacy tables so
    the floor never silently drops. Only a well-formed, current-schema
    file contributes declared gates.
    """
    p = path or _GATE_META_PATH
    try:
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    if data.get("schema") != _GATE_META_SCHEMA:
        return []
    gates = data.get("gates")
    if not isinstance(gates, list):
        return []
    out: list[dict[str, Any]] = []
    for g in gates:
        if not isinstance(g, dict):
            continue
        key = g.get("key")
        tool = g.get("tool")
        floor = g.get("floor")
        when = g.get("when")
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(tool, str) or not tool:
            continue
        if floor not in {"light", "normal", "strict"}:
            continue
        if not isinstance(when, dict):
            continue
        out.append(
            {
                "key": key,
                "tool": tool,
                "floor": floor,
                "when": when,
                "reason": g.get("reason") or "",
                "source_protocol": g.get("source_protocol") or "",
            }
        )
    return out


def _match_predicate(
    when: dict[str, Any], args: dict[str, Any], root: Path | None
) -> bool:
    """Evaluate a gate's ``when`` predicate against a tool call's args.

    The predicate vocabulary is deliberately tiny — it is a DECLARATION
    of which arg combos are dangerous, not a general expression language.
    ALL clauses must hold (logical AND). An empty ``when`` ({}) always
    matches (the tool is a gate regardless of arguments).

    Supported clause forms (value side):
      * scalar           → str(args.get(k)) == str(value)
      * list             → str(args.get(k)) in {str(v) for v in value}
      * {"truthy": true} → bool(args.get(k)) is True
      * {"path_prefix": P, "exists": E, "when_arg": A}
            → the synthesis-force-write special case. Fires when:
              args[A] is truthy AND the target path (args['filepath'])
              resolves under prefix P AND (if E is true and root given)
              the target already exists. Mirrors the legacy
              _is_synthesis_force_write logic exactly.
      * {"any_of": [<sub-predicate>, ...]} → OR: the clause holds if any
            sub-predicate matches. Used for one dangerous action that has
            two distinct argument signatures (e.g. paid tool via
            source='paid' OR paid=true).

    Any unrecognised clause shape fails CLOSED for THIS clause (returns
    False → the gate does not fire on a predicate the engine can't read),
    which is the safe default: we never invent a gate from a malformed
    rule, and the legacy tables remain the backstop for known gates.
    """
    args = args or {}
    if not when:
        return True
    for k, expected in when.items():
        if k == "any_of":
            # ``any_of`` is a list of sub-predicates; the clause holds if
            # ANY sub-predicate matches (logical OR). Lets a single gate
            # express "source in {paid,...} OR paid==true" without needing
            # two gate keys for one dangerous action.
            if not isinstance(expected, list):
                return False
            if not any(
                isinstance(sub, dict) and _match_predicate(sub, args, root)
                for sub in expected
            ):
                return False
            continue
        if isinstance(expected, dict):
            if "path_prefix" in expected:
                if not _match_path_clause(expected, args, root):
                    return False
                continue
            if expected.get("truthy") is True:
                if args.get(k) is not True and not bool(args.get(k)):
                    return False
                continue
            # Unknown dict clause → fail closed for this clause.
            return False
        if isinstance(expected, list):
            allowed = {str(v) for v in expected}
            if str(args.get(k) if args.get(k) is not None else "") not in allowed:
                return False
            continue
        # Scalar equality (string-normalised, matching the legacy checks
        # which compared str(args.get(...)) == "...").
        if str(args.get(k) if args.get(k) is not None else "") != str(expected):
            return False
    return True


def _match_path_clause(
    clause: dict[str, Any], args: dict[str, Any], root: Path | None
) -> bool:
    """The synthesis-force-write predicate (needs args + optional root).

    Fires when the gating arg is truthy AND the target path is under the
    declared prefix AND (when ``exists`` is set and a root is available)
    the file actually exists — a force-write to a non-existent path
    destroys nothing, so it is not a floor gate. With no root, fall back
    to path-shape only (fail toward gating on any resolution error).
    """
    when_arg = clause.get("when_arg")
    prefix = str(clause.get("path_prefix") or "")
    needs_exists = bool(clause.get("exists"))

    if when_arg is not None and not bool(args.get(when_arg)):
        return False

    filepath = str(args.get("filepath") or "")
    if root is not None:
        try:
            root_r = Path(root).resolve()
            target = Path(filepath)
            cand = target if target.is_absolute() else (root_r / target)
            cand_r = cand.resolve()
            rel = cand_r.relative_to(root_r).as_posix()
        except (ValueError, OSError):
            return True  # fail-safe: any resolution error → gate
        if not rel.startswith(prefix):
            return False
        if needs_exists:
            return cand_r.exists()
        return True
    # No root: path-shape only (cannot check existence).
    norm = filepath
    for p in ("./", "/"):
        while norm.startswith(p):
            norm = norm[len(p):]
    return norm.startswith(prefix)


def resolve_declared_gate(
    tool_name: str,
    args: dict[str, Any],
    root: Path | None = None,
    *,
    gates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the declared gate matching this call, or None.

    Iterates the compiled gates for ``tool_name`` and returns the first
    whose ``when`` predicate matches. Returns the gate dict (carrying
    ``key`` and ``floor``) so the caller can apply adaptive-floor logic.
    None when no declared gate matches (the caller then consults its
    legacy tables for fail-safe coverage).
    """
    pool = gates if gates is not None else _load_gate_meta()
    for g in pool:
        if g["tool"] != tool_name:
            continue
        if _match_predicate(g["when"], args, root):
            return g
    return None


def declared_floor_map(
    gates: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """key → floor for every declared gate (mirrors legacy _GATE_FLOOR)."""
    pool = gates if gates is not None else _load_gate_meta()
    return {g["key"]: g["floor"] for g in pool}
