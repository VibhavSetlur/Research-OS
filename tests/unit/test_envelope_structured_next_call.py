"""Tests for envelope ``next_recommended_call_structured`` (W16).

The string form ``"sys_protocol_get(protocol_name='X', format='summary')"``
forces small models to parse free-form text. The structured form
``{"tool": "sys_protocol_get", "arguments": {"protocol_name": "X", "format": "summary"}}``
lets strict tool-loop clients (ai-qwen, ai-deepseek, etc.) dispatch directly
without an extra parse hop.

This module covers:

* ``_envelope_base`` adds the field with a None default.
* When a parseable next_recommended_call string is set, the structured form
  is auto-derived (no per-handler change required).
* Explicit ``next_recommended_call_structured`` kwarg always wins over
  auto-derivation.
* The legacy upgrader fills the field with None for back-compat.
* ``_payload_lift`` promotes ``payload["recommended_action_structured"]``.
* The field appears in REQUIRED_ENVELOPE_KEYS so envelope-shape gates
  catch handlers that drop it.
"""
from __future__ import annotations

from research_os.server.envelopes import (
    REQUIRED_ENVELOPE_KEYS,
    _envelope_base,
    _error,
    _parse_next_call_string,
    _success,
    _upgrade_legacy_envelope,
)


# ---------------------------------------------------------------------------
# REQUIRED_ENVELOPE_KEYS includes the new field
# ---------------------------------------------------------------------------


def test_required_envelope_keys_include_structured_next_call():
    """The envelope-shape gate now requires next_recommended_call_structured."""
    assert "next_recommended_call_structured" in REQUIRED_ENVELOPE_KEYS


# ---------------------------------------------------------------------------
# _parse_next_call_string covers the realistic hint shapes
# ---------------------------------------------------------------------------


def test_parse_string_simple_kwargs():
    """Quoted kwargs from _recommended_action_for_route parse cleanly."""
    parsed = _parse_next_call_string(
        "sys_protocol_get(protocol_name='guidance/project_startup', format='summary')"
    )
    assert parsed == {
        "tool": "sys_protocol_get",
        "arguments": {
            "protocol_name": "guidance/project_startup",
            "format": "summary",
        },
    }


def test_parse_string_no_args():
    """Bare-paren calls (sys_boot()) parse to an empty arguments dict."""
    parsed = _parse_next_call_string("sys_boot()")
    assert parsed == {"tool": "sys_boot", "arguments": {}}


def test_parse_string_typed_values():
    """Bool / int / None literals coerce, not strings."""
    parsed = _parse_next_call_string(
        "tool_route(prompt='hi', persist_plan=true, limit=5, owner=none)"
    )
    assert parsed == {
        "tool": "tool_route",
        "arguments": {
            "prompt": "hi",
            "persist_plan": True,
            "limit": 5,
            "owner": None,
        },
    }


def test_parse_string_returns_none_for_freeform():
    """Free-form next_action strings (ask_user: ..., 'try sys_protocol_list')
    don't masquerade as tool calls."""
    assert _parse_next_call_string("ask_user: which protocol did you mean?") is None
    assert _parse_next_call_string("try sys_protocol_list or one of: a, b") is None
    assert _parse_next_call_string("") is None
    assert _parse_next_call_string(None) is None


# ---------------------------------------------------------------------------
# _envelope_base auto-derives the structured form from a parseable string
# ---------------------------------------------------------------------------


def test_envelope_base_auto_derives_structured_from_string():
    """When only the string form is set, the dict form is auto-filled."""
    env = _envelope_base(
        next_recommended_call="sys_protocol_get(protocol_name='guidance/x', format='summary')"
    )
    assert env["next_recommended_call_structured"] == {
        "tool": "sys_protocol_get",
        "arguments": {"protocol_name": "guidance/x", "format": "summary"},
    }


def test_envelope_base_structured_is_none_when_string_unparseable():
    """Free-form next_action (ask_user: ...) leaves the structured form at None."""
    env = _envelope_base(next_recommended_call="ask_user: which one?")
    assert env["next_recommended_call_structured"] is None


def test_envelope_base_explicit_structured_wins():
    """Caller can pass the dict explicitly; auto-derivation does not overwrite."""
    explicit = {"tool": "sys_help", "arguments": {"topic": "boot"}}
    env = _envelope_base(
        next_recommended_call="sys_protocol_get(protocol_name='x', format='summary')",
        next_recommended_call_structured=explicit,
    )
    assert env["next_recommended_call_structured"] == explicit


def test_envelope_base_defaults_to_none():
    """No hint passed -> field present but None."""
    env = _envelope_base()
    assert env["next_recommended_call"] is None
    assert env["next_recommended_call_structured"] is None


# ---------------------------------------------------------------------------
# _success / _error emit both forms
# ---------------------------------------------------------------------------


def test_success_emits_both_forms():
    """_success populates both string and structured next-call fields."""
    env = _success(
        {"hello": "world"},
        next_recommended_call="sys_active_tools(protocol_name='guidance/x')",
    )
    assert env["next_recommended_call"] == "sys_active_tools(protocol_name='guidance/x')"
    assert env["next_recommended_call_structured"] == {
        "tool": "sys_active_tools",
        "arguments": {"protocol_name": "guidance/x"},
    }


def test_success_lifts_structured_from_payload():
    """payload['recommended_action_structured'] promotes to envelope level."""
    payload = {
        "primary_protocol": "guidance/project_startup",
        "recommended_action": "sys_protocol_get(protocol_name='guidance/project_startup', format='summary')",
        "recommended_action_structured": {
            "tool": "sys_protocol_get",
            "arguments": {
                "protocol_name": "guidance/project_startup",
                "format": "summary",
            },
        },
    }
    env = _success(payload)
    assert env["next_recommended_call_structured"] == payload[
        "recommended_action_structured"
    ]


def test_error_emits_both_forms_from_parseable_next_action():
    """An error with a parseable next_action sets both fields."""
    env = _error(
        what="protocol not found",
        why="typo in name",
        next_action="sys_protocol_list()",
    )
    assert env["status"] == "error"
    assert env["next_recommended_call"] == "sys_protocol_list()"
    assert env["next_recommended_call_structured"] == {
        "tool": "sys_protocol_list",
        "arguments": {},
    }


def test_error_with_freeform_next_action_has_none_structured():
    """Free-form NEXT hints don't masquerade as tool calls."""
    env = _error(
        what="not found",
        why="bad name",
        next_action="try sys_protocol_list or one of: a, b",
    )
    assert env["next_recommended_call"] == "try sys_protocol_list or one of: a, b"
    assert env["next_recommended_call_structured"] is None


# ---------------------------------------------------------------------------
# Legacy upgrader keeps the field present
# ---------------------------------------------------------------------------


def test_legacy_envelope_upgrade_includes_structured_field():
    """Old {status, data} envelopes get the new field with None for back-compat."""
    legacy = {"status": "success", "data": {"foo": "bar"}}
    upgraded = _upgrade_legacy_envelope(legacy)
    assert "next_recommended_call_structured" in upgraded
    assert upgraded["next_recommended_call_structured"] is None


# ---------------------------------------------------------------------------
# Both forms always present on every envelope
# ---------------------------------------------------------------------------


def test_both_forms_always_present_in_success():
    """Even bare-minimum _success() carries the structured field."""
    env = _success()
    assert "next_recommended_call" in env
    assert "next_recommended_call_structured" in env


def test_both_forms_always_present_in_error():
    """Bare-message _error() also carries both fields."""
    env = _error("oops")
    assert "next_recommended_call" in env
    assert "next_recommended_call_structured" in env
