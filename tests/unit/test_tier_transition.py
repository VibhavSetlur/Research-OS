"""Phase 8 — ``tool_route`` emits ``tier_transition: {from, to}``.

The transition is computed against ``workspace/.os_state/current_tier.json``
which tracks the project's most recently committed tier.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.protocols._tiers import TIERS
from research_os.tools.actions.router import _clear_tier_cache, route_request
from research_os.tools.actions.state.tier_state import (
    compute_transition,
    get_current_tier,
    set_current_tier,
)


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "Tier Transition Test")
    return tmp_path


def test_fresh_workspace_has_no_current_tier(tmp_path):
    """Before any tier write, ``get_current_tier`` returns None."""
    root = _scaffold(tmp_path)
    assert get_current_tier(root) is None


def test_compute_transition_from_unset_workspace(tmp_path):
    """First-route transition is ``{from: None, to: <new>}``."""
    root = _scaffold(tmp_path)
    trans = compute_transition(root, "plan")
    assert trans == {"from": None, "to": "plan"}


def test_set_current_tier_persists_and_records_history(tmp_path):
    """Writing a tier creates current_tier.json with a history entry."""
    root = _scaffold(tmp_path)
    res = set_current_tier(root, "intake", source_protocol="guidance/project_startup")
    assert res["wrote"] is True
    assert res["from"] is None
    assert res["to"] == "intake"
    state_file = root / ".os_state" / "current_tier.json"
    assert state_file.exists()
    payload = json.loads(state_file.read_text())
    assert payload["current_tier"] == "intake"
    assert payload["history"][-1]["from"] is None
    assert payload["history"][-1]["to"] == "intake"
    assert payload["history"][-1]["source_protocol"] == "guidance/project_startup"


def test_set_current_tier_rejects_invalid_tier(tmp_path):
    """An unknown tier is a no-op (no file write)."""
    root = _scaffold(tmp_path)
    res = set_current_tier(root, "not_a_real_tier")
    assert res["wrote"] is False
    assert res["to"] is None
    assert not (root / ".os_state" / "current_tier.json").exists()


def test_set_current_tier_same_tier_does_not_record_transition(tmp_path):
    """Re-writing the same tier returns wrote=False but doesn't error."""
    root = _scaffold(tmp_path)
    set_current_tier(root, "execute")
    again = set_current_tier(root, "execute")
    assert again["wrote"] is False
    assert again["from"] == "execute"
    assert again["to"] == "execute"


def test_route_transition_reflects_persisted_tier(tmp_path):
    """When current_tier=intake and we route to a synthesize protocol,
    the router reports ``{from: 'intake', to: 'synthesize'}``."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "intake")
    res = route_request("draft the paper", root, persist_plan=False)
    assert res["status"] == "success"
    assert res["tier"] == "synthesize"
    assert res["tier_transition"] == {"from": "intake", "to": "synthesize"}


def test_route_transition_when_tier_matches_persisted(tmp_path):
    """When the route's tier matches current_tier the transition is
    ``{from: X, to: X}`` (not None — callers may still want to log it)."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "synthesize")
    res = route_request("draft the paper", root, persist_plan=False)
    assert res["tier"] == "synthesize"
    assert res["tier_transition"] == {"from": "synthesize", "to": "synthesize"}


def test_history_capped(tmp_path):
    """The history list is capped at TIER_HISTORY_LIMIT entries."""
    from research_os.tools.actions.state.tier_state import TIER_HISTORY_LIMIT

    root = _scaffold(tmp_path)
    # Toggle between two tiers many times so each write transitions.
    for i in range(TIER_HISTORY_LIMIT + 10):
        set_current_tier(root, TIERS[i % 2])
    payload = json.loads((root / ".os_state" / "current_tier.json").read_text())
    assert len(payload["history"]) <= TIER_HISTORY_LIMIT


def test_route_handler_emits_tier_transition_via_json(tmp_path):
    """The MCP handler must round-trip tier_transition through JSON."""
    from research_os.server import _handle_tool_route

    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "intake")
    res = _handle_tool_route(
        "tool_route",
        {"prompt": "draft the paper", "persist_plan": False},
        root,
    )
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert data["tier"] == "synthesize"
    assert data["tier_transition"]["from"] == "intake"
    assert data["tier_transition"]["to"] == "synthesize"
