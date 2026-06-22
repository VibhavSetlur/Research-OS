"""Server-side enforcement of autopilot / adaptive floor gates.

The ``guidance/autopilot.yaml`` protocol lists the mandatory
confirmation gates that must stop and ask the researcher before they
execute, even when the AI is otherwise hands-off. Before this module,
those gates were prose only — an AI could legally skip them. Now the
dispatcher refuses the call unless ``arguments['confirmed'] == True``.

The gates intercepted here:

  1. ``tool_typst_compile`` (final-deliverable PDF compile)
  2. ``tool_audit(scope='step', dimension='reproducibility')``
  3. ``tool_research_tool`` (paid candidates)
  4. ``sys_path(operation='abandon')`` — irreversible-ish path closure
  5. ``sys_file_write`` targeting ``synthesis/`` with ``force=true``
  6. ``tool_package_install``
  7. ``sys_checkpoint_rollback``
  8. ``tool_task(operation='run')`` — long-running background jobs

Two autonomy levels engage these gates:

  * ``autopilot`` — STATIC. All 8 gates always fire. The opt-in "be
    hands-off but stop on the big stuff" posture.
  * ``adaptive`` — DEFAULT, and the point of v3.3: the researcher never
    picks a mode. The gate SET flexes with the project's resolved
    ``gate_strictness`` (which is itself trust-score driven via
    ``rigor_signals.resolve_gate_strictness``):

        strict  → all 8 gates fire (same as autopilot). Low-trust /
                  young / messy projects get full protection.
        normal  → the irreversible + real-cost gates fire; reversible
                  ones (synthesis force-overwrite — auto-archived; long
                  background tasks — killable) flow.
        light   → only the genuinely irreversible / real-money gates
                  fire (path abandon, package install, paid tools,
                  rollback). A rigorous project earns flow.

``supervised`` / ``manual`` / ``coaching`` are untouched (their flows
already include an explicit ask elsewhere).
"""
from __future__ import annotations

import logging
from pathlib import Path

from .errors import RoError

logger = logging.getLogger("research-os.server.autopilot_gate")


def _read_autonomy_level(root: Path) -> str:
    """Return the normalized autonomy level for this project, or 'supervised'.

    Safe by default: any read error → 'supervised' so the gate does NOT
    fire (avoids breaking calls in projects without a config file).
    """
    try:
        from research_os.tools.actions.state.config import (
            _config_path,
            normalize_autonomy_level,
        )
        import yaml as _yaml

        cfg_path = _config_path(Path(root))
        if not cfg_path.exists():
            return "supervised"
        cfg = _yaml.safe_load(cfg_path.read_text()) or {}
        raw = (cfg.get("interaction") or {}).get("autonomy_level")
        # No explicit level set → the v3.3 default is adaptive.
        return normalize_autonomy_level(raw, default="adaptive")
    except Exception:
        return "supervised"


def _resolved_strictness(root: Path) -> str:
    """Resolve the project's gate_strictness (light|normal|strict).

    Defaults to 'strict' on any error so adaptive mode fails SAFE — an
    unreadable project keeps every floor gate active.
    """
    try:
        from research_os.tools.actions.state.rigor_signals import (
            resolve_gate_strictness,
        )

        res = resolve_gate_strictness(Path(root))
        val = res.get("resolved")
        return val if val in {"light", "normal", "strict"} else "strict"
    except Exception:
        return "strict"


# Tools that ALWAYS require confirmation in autopilot mode, regardless
# of arguments.
_ALWAYS_GATED: set[str] = {
    "tool_package_install",
    "sys_checkpoint_rollback",
}

# Adaptive-mode gate tiers. A gate fires in adaptive mode when the
# project's resolved strictness is at or above the gate's floor. Lower
# index = looser. ``light`` keeps only the truly irreversible / real-money
# gates; ``normal`` adds the reversible-but-weighty ones; ``strict`` is the
# full autopilot set.
#
# Classification rationale:
#   light  → irreversible OR spends real money (can't be undone / costs $):
#            package_install, rollback, path abandon, paid tools.
#   normal → + final-deliverable compile + reproducibility audit
#            (expensive, but re-runnable).
#   strict → + synthesis force-overwrite (auto-archived, fully reversible)
#            + long background tasks (killable) = every gate.
_GATE_FLOOR: dict[str, str] = {
    "tool_package_install": "light",
    "sys_checkpoint_rollback": "light",
    "sys_path:abandon": "light",
    "tool_research_tool:paid": "light",
    "tool_typst_compile": "normal",
    "tool_audit:reproducibility": "normal",
    "sys_file_write:synthesis_force": "strict",
    "tool_task:run": "strict",
}

_STRICTNESS_RANK = {"light": 0, "normal": 1, "strict": 2}


def _gate_key(tool_name: str, arguments: dict) -> str | None:
    """Return the canonical gate key for this (tool, args) combo, or None.

    The key is what ``_GATE_FLOOR`` is indexed by; it lets adaptive mode
    decide per-gate whether the current strictness clears the floor.
    """
    args = arguments or {}
    if tool_name == "tool_package_install":
        return "tool_package_install"
    if tool_name == "sys_checkpoint_rollback":
        return "sys_checkpoint_rollback"
    if tool_name == "sys_path":
        return "sys_path:abandon" if (args.get("operation") or "") == "abandon" else None
    if tool_name == "tool_research_tool":
        source = str(args.get("source") or "").lower()
        if source in {"paid", "paid_or_licensed"} or args.get("paid") is True:
            return "tool_research_tool:paid"
        return None
    if tool_name == "tool_typst_compile":
        return "tool_typst_compile"
    if tool_name == "tool_audit":
        scope = str(args.get("scope") or "")
        dimension = str(args.get("dimension") or "")
        if scope == "step" and dimension == "reproducibility":
            return "tool_audit:reproducibility"
        return None
    if tool_name == "tool_task":
        return "tool_task:run" if (args.get("operation") or "") == "run" else None
    if tool_name == "sys_file_write":
        return "sys_file_write:synthesis_force" if _is_synthesis_force_write(
            args, None
        ) else None
    return None


def _is_synthesis_force_write(args: dict, root: Path | None) -> bool:
    """True when this sys_file_write force-OVERWRITES an existing synthesis/ file.

    A force-write to a path that does not exist yet destroys nothing, so
    it is not a floor gate — only an actual overwrite of existing
    synthesis content is irreversible-ish (and even then auto-archived).
    """
    filepath = str(args.get("filepath") or "")
    force = bool(args.get("force"))
    if not force:
        return False
    if root is not None:
        try:
            root_r = Path(root).resolve()
            target = Path(filepath)
            cand = target if target.is_absolute() else (root_r / target)
            cand_r = cand.resolve()
            rel = cand_r.relative_to(root_r).as_posix()
        except (ValueError, OSError):
            return True  # fail-safe: any resolution error → gate
        if not rel.startswith("synthesis/"):
            return False
        # Only gate when we are actually clobbering existing content.
        return cand_r.exists()
    # No root to check existence against → fall back to path-shape only.
    norm = filepath
    for prefix in ("./", "/"):
        while norm.startswith(prefix):
            norm = norm[len(prefix):]
    return norm.startswith("synthesis/")


def _requires_confirmation(tool_name: str, arguments: dict,
                           root: Path | None = None) -> bool:
    """Decide whether this (tool_name, arguments) combo is a floor gate.

    Returns ``True`` only for the combinations enumerated in
    ``guidance/autopilot.yaml`` step ``mandatory_gates``. (autopilot-static
    set — adaptive mode further filters this by strictness.)
    """
    if tool_name in _ALWAYS_GATED:
        return True
    args = arguments or {}
    if tool_name == "sys_file_write":
        return _is_synthesis_force_write(args, root)
    if tool_name == "sys_path":
        return (args.get("operation") or "") == "abandon"
    if tool_name == "tool_task":
        # Expensive jobs: heuristic on the run operation. The protocol
        # spec says "> 1 GPU-hour OR > 10 GB memory OR > 50 GB disk I/O".
        # Without a cost estimator, treat every operation='run' as a
        # floor gate in autopilot — the researcher said "wake me on
        # background tasks", and they can confirm with one flag.
        return (args.get("operation") or "") == "run"
    if tool_name == "tool_research_tool":
        # Paid-source picks need explicit confirmation. The autopilot
        # protocol scopes this to candidates tagged paid_or_licensed —
        # callers signal that via source='paid' or paid=True.
        source = str(args.get("source") or "").lower()
        if source in {"paid", "paid_or_licensed"}:
            return True
        if args.get("paid") is True:
            return True
        return False
    if tool_name == "tool_typst_compile":
        # Final-deliverable PDF compile — gate every call.
        return True
    if tool_name == "tool_audit":
        # Reproducibility audits are slow + expensive.
        scope = str(args.get("scope") or "")
        dimension = str(args.get("dimension") or "")
        return scope == "step" and dimension == "reproducibility"
    return False


def enforce_autopilot_gate(
    tool_name: str, arguments: dict, root: Path
) -> None:
    """Raise ``RoError`` if this call hits a floor gate.

    No-op when:
      * autonomy is not gate-active (not 'autopilot' / 'adaptive')
      * tool is not in the gated set for these arguments
      * autonomy is 'adaptive' AND the project's strictness is below the
        gate's floor (a rigorous project flows through reversible gates)
      * caller passed ``confirmed=true``

    The error includes the exact next-action call the AI must make
    after the researcher consents.
    """
    if not _requires_confirmation(tool_name, arguments, root):
        return
    level = _read_autonomy_level(root)
    if level not in {"autopilot", "adaptive"}:
        return

    args = arguments or {}
    if args.get("confirmed") is True:
        return

    # Adaptive mode: only fire when the project's resolved strictness
    # clears this gate's floor. autopilot is always full-strictness.
    if level == "adaptive":
        gate_key = _gate_key(tool_name, args)
        if gate_key is not None:
            floor = _GATE_FLOOR.get(gate_key, "strict")
            strictness = _resolved_strictness(root)
            if _STRICTNESS_RANK[strictness] < _STRICTNESS_RANK[floor]:
                logger.debug(
                    "adaptive gate %s skipped: strictness=%s < floor=%s",
                    gate_key, strictness, floor,
                )
                return

    posture = (
        "adaptive autonomy paused here: this action is irreversible / "
        "expensive / external-cost at the project's current rigor level"
        if level == "adaptive"
        else "autopilot autonomy requires explicit confirmation"
    )
    raise RoError(
        what="autopilot_gate_blocked",
        why=(
            f"{posture} for {tool_name} — this is one of the mandatory "
            "floor gates declared in guidance/autopilot.yaml and enforced "
            "server-side"
        ),
        next_action=(
            f"researcher must confirm — call {tool_name}(confirmed=true, ...) "
            "only if researcher authorized"
        ),
    )
