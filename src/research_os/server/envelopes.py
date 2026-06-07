"""Response envelope helpers used by every handler.

Every tool handler returns an envelope of the shape::

    {
      "status":               "success" | "warning" | "error",
      "payload":              <tool-specific dict>,
      "data":                 alias for payload (back-compat; removal slated for v3.0.0),
      "audit_findings":       [<finding>, ...],
      "next_recommended_call": "tool_X(args=...)" | None,
      "next_recommended_call_structured": {"tool": "tool_X", "arguments": {...}} | None,
      "tier_transition":      "tier_a -> tier_b" | None,
      "tokens_estimate":      int,
      "ro_version":           "<package version>",
      "error":                str | None   (only when status == "error"),
    }

The ``next_recommended_call`` string form keeps back-compat with clients
that parse the literal hint string. The ``next_recommended_call_structured``
dict form (``{tool, arguments}``) lets strict tool-loop clients dispatch
directly without re-parsing — ai-qwen and ai-deepseek both flagged the
string form as forcing small models to parse free-form text.

Handler authors call ``_success(data, …)`` or ``_error(message, …)`` /
``_error(what=…, why=…, next_action=…)``.  The ``_text(envelope)`` helper
wraps the dict in the MCP ``TextContent`` shape that the dispatcher
returns to clients.

Backwards compatibility: ``payload`` and ``data`` reference the SAME
object, so older callers that read ``envelope["data"]`` keep working.
The ``data`` alias is slated for removal in v3.0.0 (kept through every
2.x release); the migration table in ``docs/MIGRATION_v2_0_to_v2_1.md``
names callers that should switch.
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
_DEFAULT_NEXT_CALL_STRUCTURED: dict | None = None
_DEFAULT_TIER_TRANSITION: str | None = None
_DEFAULT_TOKENS_ESTIMATE: int = 0


def _parse_next_call_string(s: str | None) -> dict | None:
    """Best-effort parse of a hint string like ``tool_X(arg='v', n=1)`` -> ``{tool, arguments}``.

    Returns None when the string doesn't look like a tool-call hint
    (e.g. a free-form ``"ask the researcher ..."`` next_action). Strict
    tool-loop clients prefer the structured form; the parser is permissive
    rather than authoritative — callers may always pass an explicit
    ``next_recommended_call_structured`` to override.
    """
    if not isinstance(s, str):
        return None
    text = s.strip()
    if not text:
        return None
    # Find the first ( and the matching last )
    open_paren = text.find("(")
    if open_paren < 1 or not text.endswith(")"):
        return None
    tool = text[:open_paren].strip()
    # Tool names are word-ish (sys_X / tool_X / mem_X).
    if not tool or not all(c.isalnum() or c in {"_", "."} for c in tool):
        return None
    body = text[open_paren + 1 : -1].strip()
    args: dict[str, Any] = {}
    if body:
        # Split on commas not inside quotes / brackets.
        parts: list[str] = []
        depth = 0
        in_quote: str | None = None
        buf: list[str] = []
        for ch in body:
            if in_quote:
                buf.append(ch)
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in {"'", '"'}:
                in_quote = ch
                buf.append(ch)
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        if buf:
            parts.append("".join(buf).strip())
        for p in parts:
            if "=" not in p:
                continue
            k, _, v = p.partition("=")
            k = k.strip()
            v = v.strip()
            # Strip quotes
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]
            elif v.lower() in {"true", "false"}:
                v = v.lower() == "true"
            elif v == "none" or v == "None" or v == "null":
                v = None
            else:
                try:
                    v = int(v)
                except (ValueError, TypeError):
                    try:
                        v = float(v)
                    except (ValueError, TypeError):
                        pass
            if k:
                args[k] = v
    return {"tool": tool, "arguments": args}


def _envelope_base(
    *,
    audit_findings: list | None = None,
    next_recommended_call: str | None = None,
    next_recommended_call_structured: dict | None = None,
    tier_transition: str | None = None,
    tokens_estimate: int | None = None,
) -> dict:
    """Common envelope fields added to every success/error response.

    When ``next_recommended_call_structured`` is None but ``next_recommended_call``
    looks like a parseable tool-call hint, the structured form is auto-derived
    so strict tool-loop clients always have something to dispatch directly.
    """
    structured = next_recommended_call_structured
    if structured is None and next_recommended_call is not None:
        structured = _parse_next_call_string(next_recommended_call)
    return {
        "audit_findings": list(audit_findings) if audit_findings else list(_DEFAULT_AUDIT_FINDINGS),
        "next_recommended_call": next_recommended_call if next_recommended_call is not None else _DEFAULT_NEXT_CALL,
        "next_recommended_call_structured": structured if structured is not None else _DEFAULT_NEXT_CALL_STRUCTURED,
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
    if "recommended_action_structured" in payload and payload["recommended_action_structured"]:
        out["next_recommended_call_structured"] = payload["recommended_action_structured"]
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
    next_recommended_call_structured: dict | None = None,
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
      * `payload["recommended_action_structured"]` → envelope `next_recommended_call_structured`
      * `payload["tier_transition"]`    → envelope `tier_transition` (serialized to string)
      * `payload["audit_findings"]`     → envelope `audit_findings`
    Explicit kwargs always win. ``next_recommended_call_structured`` is auto-derived
    from the string form by ``_envelope_base`` when not passed and the string is parseable.
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
        next_recommended_call_structured=next_recommended_call_structured if next_recommended_call_structured is not None else lifted.get("next_recommended_call_structured"),
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
    next_recommended_call_structured: dict | None = None,
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
            parts.append(f"next: {next_action.rstrip('.')}")
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
        next_recommended_call_structured=next_recommended_call_structured,
        tier_transition=tier_transition,
        tokens_estimate=tokens_estimate,
    ))
    return env


def _text(payload: Any) -> list[TextContent]:
    """Wrap any payload in the MCP TextContent[] shape expected by clients."""
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Legacy → v2.1.0 envelope normalizer (FIX-7)
# ---------------------------------------------------------------------------
# Pack and adapter tools historically emit the legacy shape:
#   {"status": "success", "data": {...}}     or
#   {"status": "error",   "error": "..."}
# The dispatcher funnels every handler result through `_normalize_envelope`
# so MCP clients only ever see the v2.1.0 envelope shape, regardless of
# whether the handler came from in-tree code, a bundled pack, or a
# third-party adapter.

# Envelope fields every v2.1.0 response must carry (matches CONTRACT A.6.1
# and the REQUIRED_ENVELOPE_KEYS used by test_v210_envelope_shape).
REQUIRED_ENVELOPE_KEYS: frozenset[str] = frozenset({
    "status",
    "payload",
    "data",
    "audit_findings",
    "next_recommended_call",
    "next_recommended_call_structured",
    "tier_transition",
    "tokens_estimate",
    "ro_version",
})


def _is_legacy_envelope(env: dict) -> bool:
    """Detect the legacy `{status, data, [error]}` shape used by packs/adapters.

    A v2.1.0 envelope always carries `payload`; legacy envelopes do not.
    """
    if not isinstance(env, dict):
        return False
    if "payload" in env:
        return False
    return "status" in env and ("data" in env or "error" in env)


def _upgrade_legacy_envelope(env: dict) -> dict:
    """Promote a legacy `{status, data}` / `{status, error}` envelope to v2.1.0.

    Preserves the `data` alias for one minor cycle so downstream callers
    that still read `envelope["data"]` keep working.
    """
    status = env.get("status", "success")
    if status == "error":
        # Extract the error message; legacy form stores it on `error`.
        err_msg = env.get("error") or env.get("message") or "unknown error"
        payload = env.get("data")
        if not isinstance(payload, dict):
            payload = {"what": err_msg, "why": None, "next_action": None}
        upgraded = {
            "status": "error",
            "error": err_msg,
            "payload": payload,
            "data": payload,
        }
    else:
        payload = env.get("data")
        if payload is None:
            # Carry forward any non-status/data keys as the payload so legacy
            # responses that stuffed fields next to `status` aren't dropped.
            payload = {k: v for k, v in env.items() if k not in {"status", "data", "error"}}
        upgraded = {
            "status": status,
            "payload": payload,
            "data": payload,
        }
        # Surface a top-level `error` only when status indicates one.
    upgraded.update(_envelope_base(
        audit_findings=None,
        next_recommended_call=None,
        next_recommended_call_structured=None,
        tier_transition=None,
        tokens_estimate=_tokens_heuristic(payload),
    ))
    return upgraded


def _normalize_envelope(result: Any, tool_name: str) -> Any:
    """Wrap a handler result so the MCP client only sees v2.1.0 envelopes.

    Accepts whatever the dispatcher receives back from a handler:
    a `list[TextContent]` (the normal case — pack/adapter tools wrap
    their JSON in TextContent themselves), a dict envelope, or other
    pass-through values.

    The normalizer is a no-op when the envelope already carries
    `payload` (i.e. came through `_success` / `_error`). Otherwise it
    upgrades the legacy `{status, data}` / `{status, error}` shape to
    the v2.1.0 envelope, adding any missing fields with safe defaults.
    """
    # Common path: handler returned list[TextContent] containing JSON.
    if isinstance(result, list) and result:
        first = result[0]
        text = getattr(first, "text", None)
        if not isinstance(text, str):
            return result
        try:
            env = json.loads(text)
        except (ValueError, TypeError):
            return result
        if not isinstance(env, dict):
            return result
        if not _is_legacy_envelope(env):
            return result
        upgraded = _upgrade_legacy_envelope(env)
        return _text(upgraded)
    # Less common: handler returned a raw envelope dict.
    if isinstance(result, dict) and _is_legacy_envelope(result):
        return _upgrade_legacy_envelope(result)
    return result
