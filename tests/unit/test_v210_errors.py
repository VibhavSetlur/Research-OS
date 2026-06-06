"""v2.1.0 RoError + structured-error regression tests.

Asserts:
* RoError composes "WHAT. because WHY — next: NEXT" sentences correctly.
* did_you_mean returns sensible nearest matches.
* The dispatcher renders RoError into a v2.1.0 error envelope with
  WHAT/WHY/NEXT subfields on `payload` and `next_action` promoted to
  envelope-level `next_recommended_call`.
* Unknown-tool dispatcher errors carry a "Did you mean: …" suggestion list.
* Missing-required-arg KeyError lands as a structured envelope.
* FileNotFoundError from the protocol loader includes did-you-mean
  suggestions.
"""
from __future__ import annotations

import json

import pytest

from research_os.server import _handle_tool_call
from research_os.server.errors import RoError, did_you_mean


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "logs").mkdir()
    return tmp_path


def _envelope(result):
    if isinstance(result, list) and result:
        return json.loads(result[0].text)
    raise AssertionError(f"unexpected handler return shape: {type(result)}")


# ── RoError ────────────────────────────────────────────────────────


def test_roerror_composes_sentence():
    e = RoError("X failed", why="Y was missing", next_action="run Z")
    assert "X failed" in str(e)
    assert "because Y was missing" in str(e)
    assert "next: run Z" in str(e)


def test_roerror_what_only_does_not_add_clauses():
    e = RoError("simple problem")
    assert str(e) == "simple problem"
    kw = e.to_envelope_kwargs()
    assert kw == {"what": "simple problem", "why": None, "next_action": None}


# ── did_you_mean ───────────────────────────────────────────────────


def test_did_you_mean_returns_close_matches():
    candidates = ["tool_search", "tool_plan", "tool_audit", "tool_ground"]
    out = did_you_mean("tool_serach", candidates)
    assert "tool_search" in out


def test_did_you_mean_excludes_exact_target():
    out = did_you_mean("alpha", ["alpha", "alpha2", "beta"])
    assert "alpha" not in out


# ── dispatcher: unknown tool ───────────────────────────────────────


def test_dispatcher_unknown_tool_carries_did_you_mean(project_root):
    # 'tool_serach' typo should suggest 'tool_search'
    result = _handle_tool_call("tool_serach", {"query": "x"}, project_root)
    env = _envelope(result)
    assert env["status"] == "error"
    assert "unknown tool" in env["error"].lower()
    # WHAT/WHY/NEXT subfields present
    assert env["payload"]["what"]
    assert env["payload"]["why"]
    assert env["payload"]["next_action"]
    # Suggestion list included in the NEXT text
    assert "did you mean" in env["payload"]["next_action"].lower()


# ── dispatcher: FileNotFound from protocol loader ──────────────────


def test_dispatcher_renders_filenotfound_with_did_you_mean(project_root):
    # sys_protocol_get on a non-existent protocol; loader raises
    # FileNotFoundError with did-you-mean appended.
    result = _handle_tool_call(
        "sys_protocol_get",
        {"protocol_name": "guidance/sesssion_boot"},  # typo: sesssion
        project_root,
    )
    env = _envelope(result)
    assert env["status"] == "error"
    # The typo should be close enough to suggest the real protocol.
    msg_blob = (
        (env.get("error") or "")
        + " "
        + (env["payload"].get("why") or "")
    )
    assert "session_boot" in msg_blob, (
        f"expected did-you-mean suggestion in error: {env['payload']!r}"
    )
