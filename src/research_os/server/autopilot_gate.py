"""Server-side enforcement of autopilot floor gates.

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

Only triggered when ``interaction.autonomy_level == 'autopilot'``;
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
        return normalize_autonomy_level(raw)
    except Exception:
        return "supervised"


# Tools that ALWAYS require confirmation in autopilot mode, regardless
# of arguments.
_ALWAYS_GATED: set[str] = {
    "tool_package_install",
    "sys_checkpoint_rollback",
}


def _requires_confirmation(tool_name: str, arguments: dict) -> bool:
    """Decide whether this (tool_name, arguments) combo is a floor gate.

    Returns ``True`` only for the combinations enumerated in
    ``guidance/autopilot.yaml`` step ``mandatory_gates``.
    """
    if tool_name in _ALWAYS_GATED:
        return True
    args = arguments or {}
    if tool_name == "sys_file_write":
        filepath = str(args.get("filepath") or "")
        force = bool(args.get("force"))
        # Only gate writes that overwrite (force=true) inside synthesis/.
        # Normalize leading "./" and treat both relative + absolute paths.
        norm = filepath.lstrip("./").lstrip("/")
        return force and norm.startswith("synthesis/")
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
    """Raise ``RoError`` if this call hits an autopilot floor gate.

    No-op when:
      * autonomy != 'autopilot'
      * tool is not in the gated set for these arguments
      * caller passed ``confirmed=true``

    The error includes the exact next-action call the AI must make
    after the researcher consents.
    """
    if not _requires_confirmation(tool_name, arguments):
        return
    level = _read_autonomy_level(root)
    if level != "autopilot":
        return
    args = arguments or {}
    if args.get("confirmed") is True:
        return
    raise RoError(
        what="autopilot_gate_blocked",
        why=(
            f"autopilot autonomy requires explicit confirmation for {tool_name} — "
            "this is one of 8 mandatory floor gates declared in "
            "guidance/autopilot.yaml and enforced server-side"
        ),
        next_action=(
            f"researcher must confirm — call {tool_name}(confirmed=true, ...) "
            "only if researcher authorized"
        ),
    )
