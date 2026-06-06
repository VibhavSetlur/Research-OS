"""v2.1.0 envelope-shape regression tests.

Asserts the v2.1.0 envelope shape (`status`, `payload`, `data`,
`audit_findings`, `next_recommended_call`, `tier_transition`,
`tokens_estimate`, `ro_version`) on a representative tool call from
each handler module. If any handler bypasses the central
`_success` / `_error` helpers, these tests catch it.
"""
from __future__ import annotations

import json

import pytest

from research_os.server import _handle_tool_call


REQUIRED_ENVELOPE_KEYS = {
    "status", "payload", "data",
    "audit_findings", "next_recommended_call",
    "tier_transition", "tokens_estimate", "ro_version",
}


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "logs").mkdir()
    return tmp_path


def _envelope(result):
    """Parse the TextContent[] -> JSON envelope dict."""
    if isinstance(result, list) and result:
        return json.loads(result[0].text)
    if isinstance(result, dict):
        return result
    raise AssertionError(f"unexpected handler return shape: {type(result)}")


# Representative handler per handler module. Each call uses safe defaults
# that don't require external state beyond the empty workspace fixture.
REPRESENTATIVE_CALLS = [
    # meta_routing
    ("tool_route",      {"request": "I want to start a new project"}),
    ("sys_boot",        {}),
    # meta_sys
    ("sys_path",        {"operation": "list"}),
    ("sys_packs_installed", {}),
    # meta_workspace
    ("sys_protocols_list", {}),
    # meta_help
    ("sys_help",        {"topic": "boot"}),
    # research_search consolidated (we don't network out — `source=auto`
    # with a query that no provider can answer still returns an envelope).
    ("tool_search",     {"query": "qx", "source": "auto", "limit": 1}),
    # methodology + grounding sample
    ("tool_plan",       {"operation": "show"}),
    # memory + scratch
    ("mem_log",         {"kind": "methods", "method": "regression"}),
]


@pytest.mark.parametrize("tool_name,args", REPRESENTATIVE_CALLS)
def test_envelope_shape_present(tool_name, args, project_root):
    """Each representative handler returns the v2.1.0 envelope shape."""
    result = _handle_tool_call(tool_name, args, project_root)
    env = _envelope(result)

    missing = REQUIRED_ENVELOPE_KEYS - set(env)
    assert not missing, f"{tool_name} envelope missing keys: {missing}"

    # Status is canonical
    assert env["status"] in {"success", "warning", "error"}, (
        f"{tool_name} status={env['status']!r}"
    )
    # payload + data are aliases (same object)
    assert env["payload"] == env["data"], (
        f"{tool_name} payload/data drift: payload={env['payload']!r} data={env['data']!r}"
    )
    # ro_version is the bumped semver string
    assert isinstance(env["ro_version"], str)
    assert env["ro_version"].count(".") >= 2
    # tier_transition is None or a "tier_a -> tier_b" string
    assert env["tier_transition"] is None or "->" in env["tier_transition"] or " " in env["tier_transition"]
    # tokens_estimate is a non-negative int
    assert isinstance(env["tokens_estimate"], int) and env["tokens_estimate"] >= 0
    # audit_findings is a list (may be empty)
    assert isinstance(env["audit_findings"], list)


def test_error_envelope_carries_what_why_next(project_root):
    """An intentionally-failing call produces a structured error envelope."""
    # tool_search with an unknown source intentionally returns an error
    result = _handle_tool_call(
        "tool_search", {"query": "q", "source": "scihub"}, project_root
    )
    env = _envelope(result)
    assert env["status"] == "error"
    assert "error" in env, "error envelope missing 'error' message"
    # Both payload + data carry the WHAT/WHY/NEXT subfields (None ok for v2.0-style raises)
    p = env["payload"]
    assert "what" in p
    assert "why" in p
    assert "next_action" in p
