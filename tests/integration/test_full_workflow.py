"""End-to-end MCP workflow — scaffold, protocol load, path create, audit."""

import json

from research_os.server import _handle_tool_call


def test_full_workflow(tmp_path):
    # 1. Scaffold
    res = _handle_tool_call("sys_workspace_scaffold", {"project_name": "Test Project"}, tmp_path)
    assert "success" in res[0].text

    # 2. Load a real protocol (uses the installed protocols/ dir)
    res = _handle_tool_call(
        "sys_protocol_get", {"protocol_name": "guidance/session_boot"}, tmp_path
    )
    assert "success" in res[0].text

    # 3. Create a path — sys_path(operation='create') in v2.0.0
    res = _handle_tool_call(
        "sys_path",
        {"operation": "create", "name": "baseline", "hypothesis": "Test H"},
        tmp_path,
    )
    assert "success" in res[0].text

    # 4. Write a workspace file via MCP (synthesis paper)
    paper = (
        "# Title\n\n"
        "## Abstract\nbody\n\n## Introduction\nbody\n\n## Methods\nbody\n\n"
        "## Results\nThe sum is 21.\n\n## Discussion\nThis proves our hypothesis.\n\n"
        "## References\n[1] Smith et al.\n"
    )
    res = _handle_tool_call(
        "sys_file_write",
        {"filepath": "synthesis/paper.md", "content": paper, "force": True},
        tmp_path,
    )
    assert "success" in res[0].text

    # 5. Audit synthesis — should flag causal language
    res = _handle_tool_call(
        "tool_audit_synthesis", {"paper_path": "synthesis/paper.md"}, tmp_path
    )
    payload = json.loads(res[0].text)
    causal = payload["data"]["report"]["causal_language_hits"]
    assert len(causal) > 0


def test_dot_notation_routes_to_underscore(tmp_path):
    # Scaffold first
    _handle_tool_call("sys_workspace_scaffold", {"project_name": "Dot Test"}, tmp_path)

    # Dot notation
    res = _handle_tool_call(
        "sys.protocol.get", {"protocol_name": "guidance/session_boot"}, tmp_path
    )
    assert "success" in res[0].text


def test_legacy_tool_name_alias(tmp_path):
    _handle_tool_call("sys_workspace_scaffold", {"project_name": "Alias Test"}, tmp_path)

    # `tool_audit_statistical_power` is one of the live aliases retained
    # in the 2.0 alias table — it routes to `tool_audit_power`.
    res = _handle_tool_call(
        "tool_audit_statistical_power",
        {"filepath": "workspace/dummy.csv",
         "effect_size": 0.5, "alpha": 0.05, "n": 100},
        tmp_path,
    )
    # Should route the alias and reach the handler (which may then error
    # for missing file — that's fine; the alias resolved).
    assert "Unknown tool" not in res[0].text
