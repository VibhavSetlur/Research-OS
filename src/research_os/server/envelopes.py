"""Response envelope helpers used by every handler.

Every tool handler returns a v2.1.0 envelope of the shape::

    {
      "status":               "success" | "warning" | "error",
      "payload":              <tool-specific dict>,
      "data":                 alias for payload (v2.0 back-compat; v2.2.0 removal),
      "audit_findings":       [<finding>, ...],
      "next_recommended_call": "tool_X(args=...)" | None,
      "tier_transition":      "tier_a -> tier_b" | None,
      "tokens_estimate":      int,
      "ro_version":           "2.1.0",
      "error":                str | None   (only when status == "error"),
    }

Handler authors call ``_success(data, …)`` or ``_error(message, …)`` /
``_error(what=…, why=…, next_action=…)``.  The ``_text(envelope)`` helper
wraps the dict in the MCP ``TextContent`` shape that the dispatcher
returns to clients.

Backwards compatibility: ``payload`` and ``data`` reference the SAME
object, so older callers that read ``envelope["data"]`` keep working
through the v2.1.x line.  The ``data`` alias is removed in v2.2.0; the
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


# Envelope fields beyond {status, payload, data, error} that v2.1.0 adds.
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


def _success(
    data: Any = None,
    *,
    audit_findings: list | None = None,
    next_recommended_call: str | None = None,
    tier_transition: str | None = None,
    tokens_estimate: int | None = None,
) -> dict:
    """Build a v2.1.0 success envelope.

    ``data`` becomes ``envelope["payload"]`` AND ``envelope["data"]`` —
    both names reference the same object for one minor cycle.  Callers
    that don't pass ``data`` get an empty dict (matches v2.0 behaviour).
    """
    payload = data if data is not None else {}
    env = {
        "status": "success",
        "payload": payload,
        "data": payload,
    }
    env.update(_envelope_base(
        audit_findings=audit_findings,
        next_recommended_call=next_recommended_call,
        tier_transition=tier_transition,
        tokens_estimate=tokens_estimate,
    ))
    return env


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
    """Build a v2.1.0 error envelope.

    Two call styles are supported during the v2.1.x cycle:

    * Positional / single-message (v2.0 compat)::

          return _error("path not found")

    * WHAT/WHY/NEXT keyword form (v2.1.0 standard)::

          return _error(
              what="path not found",
              why="the protocol was renamed during v2.1.0",
              next_action="try `sys_protocols_list` to find the new name",
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
