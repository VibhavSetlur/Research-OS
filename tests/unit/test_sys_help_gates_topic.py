"""W10: sys_help(topic='gates') — gate discoverability.

Closes the gap where researchers learn gate names only from BLOCKED
errors. The 'gates' topic returns:
  * full gate vocabulary (every (scope, dimension) the dispatcher routes
    to, with a 1-line role per gate)
  * autopilot 8-gate floor list with bypass shapes per gate
  * override_log location for quality-gate (non-floor) bypasses
  * pointers to discoverability tools (tool_audit(scope='active_gates'),
    tool_audit_findings(operation='timeline'))
"""

from __future__ import annotations

import json

import pytest

from research_os.server import _handle_tool_call


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "logs").mkdir()
    return tmp_path


def _payload(result):
    """Parse a sys_help response → the inner data dict."""
    assert isinstance(result, list) and result, f"unexpected: {result!r}"
    env = json.loads(result[0].text)
    assert env["status"] == "success", env
    return env["data"]


def test_gates_topic_returns_full_vocabulary(project_root):
    res = _handle_tool_call("sys_help", {"topic": "gates"}, project_root)
    data = _payload(res)

    # Top-level keys we promised to return.
    for key in (
        "all_audit_gates",
        "autopilot_floor_gates",
        "quality_gate_overrides",
        "bypass_log_location",
        "discoverability_tools",
        "gate_count_total",
    ):
        assert key in data, f"sys_help(topic='gates') missing {key!r}"

    # The gate vocabulary has three scopes and adds up.
    scopes = data["all_audit_gates"]
    assert set(scopes) == {"step", "project", "synthesis"}
    total_dims = sum(len(v) for v in scopes.values())
    # 10 step + 7 project + 4 synthesis = 21 in current dispatch table.
    assert total_dims >= 20, (
        f"expected >=20 gate dimensions, got {total_dims}"
    )

    # Every gate body is a 1-line role string (non-empty).
    for scope_name, dims in scopes.items():
        for dim_name, role in dims.items():
            assert isinstance(role, str) and role.strip(), (
                f"{scope_name}.{dim_name} role is empty"
            )


def test_gates_topic_lists_autopilot_floor(project_root):
    res = _handle_tool_call("sys_help", {"topic": "gates"}, project_root)
    data = _payload(res)
    floor = data["autopilot_floor_gates"]

    assert floor["count"] == 8
    assert len(floor["list"]) == 8

    # Each floor entry has the tool name + a bypass call shape including
    # confirmed=true. Closes the "what flag do I pass?" gap.
    for entry in floor["list"]:
        assert "tool" in entry and entry["tool"]
        assert "bypass" in entry and "confirmed=true" in entry["bypass"]

    # The well-known floor tools must all be enumerated.
    tools_joined = " ".join(e["tool"] for e in floor["list"])
    for required in (
        "tool_typst_compile",
        "tool_audit",  # reproducibility
        "tool_research_tool",
        "sys_path",
        "sys_file_write",
        "tool_package_install",
        "sys_checkpoint_rollback",
    ):
        assert required in tools_joined, (
            f"autopilot floor missing entry for {required}"
        )


def test_gates_topic_provides_override_log_location(project_root):
    res = _handle_tool_call("sys_help", {"topic": "gates"}, project_root)
    data = _payload(res)
    assert data["bypass_log_location"] == "workspace/logs/override_log.md"


def test_gates_topic_lists_discoverability_tools(project_root):
    """Both new tools (tool_audit(scope='active_gates') and
    tool_audit_findings(operation='timeline')) must be advertised so the
    AI can find them without grepping the codebase.
    """
    res = _handle_tool_call("sys_help", {"topic": "gates"}, project_root)
    data = _payload(res)
    discov = data["discoverability_tools"]

    discov_keys = " ".join(discov.keys())
    assert "active_gates" in discov_keys
    assert "timeline" in discov_keys


def test_gates_topic_listed_in_topics_index(project_root):
    """sys_help with no topic returns the topics index — 'gates' must
    appear so the AI can find it on the way in."""
    res = _handle_tool_call("sys_help", {}, project_root)
    data = _payload(res)
    assert "gates" in data["topics"]


def test_active_gates_returns_armed_state(project_root):
    """tool_audit(scope='active_gates') returns live gate state."""
    res = _handle_tool_call(
        "tool_audit", {"scope": "active_gates"}, project_root
    )
    env = json.loads(res[0].text)
    assert env["status"] == "success", env
    data = env["data"]
    # Empty ledger → no armed gates, but vocabulary is always populated.
    assert data["armed_gate_count"] == 0
    assert isinstance(data["gates"], list) and data["gates"] == []
    assert data["vocabulary_count"] >= 20
    # Each vocabulary entry has scope + dimension + handler.
    for v in data["known_gate_vocabulary"]:
        assert "scope" in v and "dimension" in v and "handler" in v
