"""Tests for the v2 flat protocol lister + tool_protocols_list MCP tool."""

from __future__ import annotations

from research_os.tools.actions.listers import list_protocols_flat


def test_list_protocols_flat_returns_structured_entries():
    out = list_protocols_flat()
    assert isinstance(out, list)
    assert len(out) > 50, f"expected many protocols, got {len(out)}"
    # Every entry has the v2 schema.
    required = {
        "name", "category", "pack_or_core", "intent_class",
        "tier", "version", "description_short",
    }
    valid_tiers = {None, "intake", "plan", "execute", "ground",
                   "synthesize", "review", "finalize"}
    tier_populated_count = 0
    for entry in out:
        missing = required - set(entry.keys())
        assert not missing, f"entry {entry.get('name')} missing keys {missing}"
        # tier is now sourced from the YAML's `tier:` field (v2.1.0). May be
        # None for protocols that don't declare one, but most should.
        assert entry["tier"] in valid_tiers, (
            f"entry {entry.get('name')} tier={entry['tier']!r} not in enum"
        )
        if entry["tier"] is not None:
            tier_populated_count += 1
        # pack_or_core never blank.
        assert entry["pack_or_core"]
        # description_short is short (we cap at ~160 chars).
        assert len(entry["description_short"]) <= 200
    # v2.1.0: tier:null was Phase 8 placeholder; should now be populated on
    # the majority of protocols (the YAMLs carry `tier:` since v2.0.0).
    assert tier_populated_count > 100, (
        f"expected tier populated on >100 protocols, got {tier_populated_count}"
    )


def test_list_protocols_flat_filter_by_category():
    out = list_protocols_flat(category="guidance")
    assert out, "expected at least one guidance protocol"
    for entry in out:
        assert entry["category"] == "guidance"


def test_list_protocols_flat_filter_by_pack_core():
    out = list_protocols_flat(pack="core")
    assert out, "expected core protocols"
    for entry in out:
        assert entry["pack_or_core"] == "core"


def test_list_protocols_flat_exclude_packs():
    out = list_protocols_flat(include_pack_protocols=False)
    for entry in out:
        assert entry["pack_or_core"] == "core", entry


def test_list_protocols_flat_intent_class_populated_for_routed():
    """guidance/session_boot is in the router index — its intent_class
    must surface in the flat list."""
    out = list_protocols_flat()
    boot = next(
        (e for e in out if e["name"] == "guidance/session_boot"),
        None,
    )
    assert boot is not None, "guidance/session_boot missing from flat list"
    assert boot["intent_class"] == "session"
    assert boot["category"] == "guidance"
    assert boot["pack_or_core"] == "core"


def test_list_protocols_flat_unknown_category_empty():
    assert list_protocols_flat(category="not-a-real-category") == []


def test_tool_protocols_list_handler(tmp_path):
    from research_os.server import _handle_tool_protocols_list

    res = _handle_tool_protocols_list(
        "tool_protocols_list", {"category": "guidance"}, tmp_path,
    )
    assert isinstance(res, list) and res
    import json
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert "protocols" in data
    assert "count" in data
    assert data["count"] == len(data["protocols"])
    assert all(e["category"] == "guidance" for e in data["protocols"])
    assert data["filters"]["category"] == "guidance"


def test_tool_protocols_list_no_filters_dump_all(tmp_path):
    from research_os.server import _handle_tool_protocols_list

    res = _handle_tool_protocols_list("tool_protocols_list", {}, tmp_path)
    import json
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert data["count"] > 50
    # Default is include_pack_protocols=True.
    assert data["filters"]["include_pack_protocols"] is True
