"""Response envelope helpers used by every handler.

Every tool handler returns an envelope of the shape::

    {
      "status":               "success" | "warning" | "error",
      "payload":              <tool-specific dict>,
      "data":                 alias for payload (back-compat; slated for removal),
      "audit_findings":       [<finding>, ...],
      "next_recommended_call": "tool_X(args=...)" | None,
      "tier_transition":      "tier_a -> tier_b" | None,
      "tokens_estimate":      int,
      "ro_version":           "<package version>",
      "error":                str | None   (only when status == "error"),
    }

Handler authors call ``_success(data, …)`` or ``_error(message, …)`` /
``_error(what=…, why=…, next_action=…)``.  The ``_text(envelope)`` helper
wraps the dict in the MCP ``TextContent`` shape that the dispatcher
returns to clients.

Backwards compatibility: ``payload`` and ``data`` reference the SAME
object, so older callers that read ``envelope["data"]`` keep working.
The ``data`` alias is slated for removal in the next major; the
migration table in ``docs/MIGRATION_v2_0_to_v2_1.md`` names callers that
should switch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from research_os import __version__ as _RO_VERSION


try:
    from mcp.types import TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

    @dataclass
    class TextContent:  # type: ignore[no-redef]
        type: str
        text: str


# Envelope fields beyond {status, payload, data, error}.
# Each handler may override any of these via kwargs to _success / _error.
_DEFAULT_AUDIT_FINDINGS: list = []
_DEFAULT_NEXT_CALL: str | None = None
_DEFAULT_TIER_TRANSITION: str | None = None
_DEFAULT_TOKENS_ESTIMATE: int = 0


def _envelope_base(
    *,
    audit_findings: list | None = None,
    next_recommended_call: str | None = None,
    tier_transition: str | None = None,
    tokens_estimate: int | None = None,
) -> dict:
    """Common envelope fields added to every success/error response."""
    return {
        "audit_findings": list(audit_findings) if audit_findings else list(_DEFAULT_AUDIT_FINDINGS),
        "next_recommended_call": next_recommended_call if next_recommended_call is not None else _DEFAULT_NEXT_CALL,
        "tier_transition": tier_transition if tier_transition is not None else _DEFAULT_TIER_TRANSITION,
        "tokens_estimate": int(tokens_estimate) if tokens_estimate is not None else _DEFAULT_TOKENS_ESTIMATE,
        "ro_version": _RO_VERSION,
    }


def _stringify_tier_transition(value: Any) -> str | None:
    """Normalize tier_transition to the contract's `"tier_a -> tier_b"` form.

    Accepts None (returns None), a string (passes through), or a
    `{"from": ..., "to": ...}` dict (serializes). Other shapes return None
    rather than leaking a non-stringified blob into the envelope.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        f = value.get("from")
        t = value.get("to")
        if f and t:
            return f"{f} -> {t}"
        if t and not f:
            return f"-> {t}"
        if f and not t:
            return f"{f} ->"
    return None


def _payload_lift(payload: Any) -> dict[str, Any]:
    """Lift envelope-level fields from a payload dict.

    Bridges the legacy handler convention (handlers tuck `recommended_action`,
    `tier_transition`, `audit_findings` into the success payload) with the
    current envelope contract that surfaces those fields at envelope level.
    Handlers don't need to be rewritten — `_success` reads the payload and
    promotes whatever's there. Explicit kwargs to `_success` still win.
    """
    out: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return out
    if "recommended_action" in payload and payload["recommended_action"]:
        out["next_recommended_call"] = payload["recommended_action"]
    if "tier_transition" in payload:
        s = _stringify_tier_transition(payload["tier_transition"])
        if s is not None:
            out["tier_transition"] = s
    if "audit_findings" in payload and isinstance(payload["audit_findings"], list):
        out["audit_findings"] = list(payload["audit_findings"])
    return out


def _success(
    data: Any = None,
    *,
    audit_findings: list | None = None,
    next_recommended_call: str | None = None,
    tier_transition: str | None = None,
    tokens_estimate: int | None = None,
) -> dict:
    """Build a success envelope.

    ``data`` becomes ``envelope["payload"]`` AND ``envelope["data"]`` —
    both names reference the same object while the ``data`` alias is
    still supported.  Callers that don't pass ``data`` get an empty dict.

    Envelope fields auto-populate from common payload keys when
    not passed explicitly:
      * `payload["recommended_action"]` → envelope `next_recommended_call`
      * `payload["tier_transition"]`    → envelope `tier_transition` (serialized to string)
      * `payload["audit_findings"]`     → envelope `audit_findings`
    Explicit kwargs always win.
    """
    payload = data if data is not None else {}
    lifted = _payload_lift(payload)
    # Normalize tier_transition passed explicitly to the canonical string shape.
    if tier_transition is not None and not isinstance(tier_transition, str):
        tier_transition = _stringify_tier_transition(tier_transition)
    env = {
        "status": "success",
        "payload": payload,
        "data": payload,
    }
    env.update(_envelope_base(
        audit_findings=audit_findings if audit_findings is not None else lifted.get("audit_findings"),
        next_recommended_call=next_recommended_call if next_recommended_call is not None else lifted.get("next_recommended_call"),
        tier_transition=tier_transition if tier_transition is not None else lifted.get("tier_transition"),
        tokens_estimate=tokens_estimate if tokens_estimate is not None else _tokens_heuristic(payload),
    ))
    return env


def _tokens_heuristic(payload: Any) -> int:
    """Cheap len(json.dumps(payload))//4 heuristic for envelope `tokens_estimate`.

    Lets clients cost-route on every response without per-handler instrumentation.
    """
    try:
        return max(0, len(json.dumps(payload, default=str)) // 4)
    except Exception:
        return 0


def _error(
    message: str | None = None,
    *,
    what: str | None = None,
    why: str | None = None,
    next_action: str | None = None,
    audit_findings: list | None = None,
    next_recommended_call: str | None = None,
    tier_transition: str | None = None,
    tokens_estimate: int | None = None,
) -> dict:
    """Build an error envelope.

    Two call styles are supported:

    * Positional / single-message (legacy compat)::

          return _error("path not found")

    * WHAT/WHY/NEXT keyword form (standard)::

          return _error(
              what="path not found",
              why="the protocol was renamed",
              next_action="try `sys_protocol_list` to find the new name",
          )

    With kwargs, ``message`` becomes a composed sentence and the original
    parts land in ``payload`` so a structured client can render them
    independently.  ``next_action`` ALSO promotes to envelope-level
    ``next_recommended_call`` unless the caller overrides explicitly.
    """
    if what or why or next_action:
        parts = []
        if what:
            parts.append(what.rstrip("."))
        if why:
            parts.append(f"because {why.rstrip('.')}")
        if next_action:
            parts.append(f"— next: {next_action.rstrip('.')}")
        composed = ". ".join(parts)
        msg = message or composed
        payload_fields = {
            "what": what,
            "why": why,
            "next_action": next_action,
        }
        env_next = next_recommended_call if next_recommended_call is not None else next_action
    else:
        msg = message or "unknown error"
        payload_fields = {"what": msg, "why": None, "next_action": None}
        env_next = next_recommended_call

    env = {
        "status": "error",
        "error": msg,
        "payload": payload_fields,
        "data": payload_fields,
    }
    env.update(_envelope_base(
        audit_findings=audit_findings,
        next_recommended_call=env_next,
        tier_transition=tier_transition,
        tokens_estimate=tokens_estimate,
    ))
    return env


def _text(payload: Any) -> list[TextContent]:
    """Wrap any payload in the MCP TextContent[] shape expected by clients."""
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]
