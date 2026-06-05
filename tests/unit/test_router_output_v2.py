"""Tests for v2 tool_route output fields: why_matched, tier, tier_transition,
alternatives-with-scores."""

from __future__ import annotations

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.router import route_request


V2_FIELDS = {"why_matched", "tier", "tier_transition", "alternatives"}


def _route(prompt, tmp_path):
    scaffold_minimal_workspace(tmp_path, "Router v2 Test")
    return route_request(prompt, tmp_path, persist_plan=False)


def test_route_response_includes_v2_fields(tmp_path):
    res = _route("fill the intake", tmp_path)
    assert res["status"] == "success"
    for f in V2_FIELDS:
        assert f in res, f"v2 field {f!r} missing from route response"


def test_route_tier_fields_populated_at_phase_8(tmp_path):
    """Phase 8: tier is resolved from the matched protocol's YAML.

    'fill the intake' routes into the intake bucket, so the tier is
    ``intake``. Since no current_tier.json exists yet for the fresh
    workspace, the transition is ``{from: None, to: "intake"}``.
    """
    from research_os.protocols._tiers import TIERS

    res = _route("fill the intake", tmp_path)
    assert res["tier"] in TIERS, res["tier"]
    trans = res["tier_transition"]
    assert isinstance(trans, dict)
    assert trans["from"] is None
    assert trans["to"] == res["tier"]


def test_route_why_matched_mentions_trigger_or_intent(tmp_path):
    res = _route("fill the intake", tmp_path)
    wm = res.get("why_matched") or ""
    # Either the literal trigger or the intent_class label must appear.
    assert "intake" in wm.lower() or "intent_class=" in wm, wm


def test_route_alternatives_are_objects_with_scores(tmp_path):
    """v1 returned alternatives as bare names; v2 returns objects."""
    # Use a prompt that pulls multiple candidates so alternatives is non-empty.
    res = _route("audit the figures and write the methods section", tmp_path)
    assert res["status"] == "success"
    alts = res.get("alternatives")
    assert isinstance(alts, list)
    # The prompt should land at least one alternative — defensive: when
    # the top pick is the only candidate, alternatives may be empty.
    if alts:
        for entry in alts:
            assert isinstance(entry, dict)
            assert set(entry.keys()) >= {"name", "score", "why_matched"}
            assert isinstance(entry["name"], str)
            assert isinstance(entry["score"], (int, float))


def test_route_alternatives_limited_to_three(tmp_path):
    res = _route(
        "run a baseline EDA and then fit a model and then write the paper "
        "and audit the figures and check power",
        tmp_path,
    )
    assert res["status"] == "success"
    alts = res.get("alternatives") or []
    assert len(alts) <= 3, f"alternatives exceeded 3: {len(alts)}"


def test_route_shortcut_response_has_v2_fields(tmp_path):
    """progress digest is a cross-intent shortcut — must still carry v2 fields.

    Phase 8: when the prompt also matches a protocol's trigger phrases,
    the router promotes that protocol as the primary, so ``tier`` mirrors
    the primary's tier rather than being null. The tier_transition then
    has ``to=<protocol tier>`` and ``from=None`` for a fresh workspace.
    """
    from research_os.protocols._tiers import TIERS

    res = _route("what's the progress so far", tmp_path)
    assert res["status"] == "success"
    for f in V2_FIELDS:
        assert f in res
    # tier may be a real tier (when a primary protocol won alongside the
    # shortcut) or None (pure shortcut path). Either is valid.
    if res["tier"] is not None:
        assert res["tier"] in TIERS


def test_route_unmatched_prompt_has_v2_fields(tmp_path):
    """Even the fallback (zero matches) must carry the v2 fields."""
    res = _route("xyzzy plugh frobnicate quux", tmp_path)
    assert res["status"] == "success"
    for f in V2_FIELDS:
        assert f in res
    assert res["tier"] is None
    assert res["tier_transition"] is None


def test_route_handler_serializes_v2_fields(tmp_path):
    """The MCP-facing handler must surface the v2 fields in its JSON."""
    import json

    from research_os.server import _handle_tool_route

    scaffold_minimal_workspace(tmp_path, "Router v2 Handler Test")
    res = _handle_tool_route(
        "tool_route",
        {"prompt": "fill the intake", "persist_plan": False},
        tmp_path,
    )
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    for f in V2_FIELDS:
        assert f in data, f"v2 field {f!r} missing from handler output"
