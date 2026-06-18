"""3.2.2 — one canonical MCP entry + Claude Code root .mcp.json + restart notice."""
from __future__ import annotations

from research_os.project_ops import (
    _setup_mcp_configs,
    mcp_global_install_hint,
    mcp_restart_notice,
    mcp_server_entry,
)


def test_entry_is_portable():
    e = mcp_server_entry()
    assert e["command"] == "research-os"
    assert e["args"] == ["start"]
    # Portable workspace hint — never an absolute path.
    assert e["env"]["RESEARCH_OS_WORKSPACE"] == "${workspaceFolder}"


def test_claude_writes_canonical_root_mcp_json(tmp_path):
    (tmp_path / ".os_state").mkdir()
    _setup_mcp_configs(tmp_path, ["claude"])
    import json

    root_mcp = tmp_path / ".mcp.json"
    claude_mcp = tmp_path / ".claude" / "mcp.json"
    assert root_mcp.exists(), "Claude Code reads ROOT .mcp.json — must be written"
    assert claude_mcp.exists()
    a = json.loads(root_mcp.read_text())["mcpServers"]["research-os"]
    b = json.loads(claude_mcp.read_text())["mcpServers"]["research-os"]
    # Both carry the identical canonical entry (no drift).
    assert a == b == mcp_server_entry()


def test_restart_notice_is_loud():
    n = mcp_restart_notice()
    assert "RESTART" in n.upper()


def test_global_hint_mentions_user_scope():
    hint = mcp_global_install_hint(["claude", "cursor"])
    assert "global" in hint.lower() or "user scope" in hint.lower()
    assert "claude mcp add" in hint
