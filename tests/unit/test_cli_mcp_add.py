"""W19 — `research-os mcp {add,list,remove,template}` subcommand.

Composes third-party MCP servers (Slack, GitHub, Postgres, Filesystem,
Memory, ...) into the IDE configs Research-OS already manages. Additive
to `research-os ide add`, which wires the RO server itself.

These tests poke the underlying ``collab.mcp_*`` helpers directly so we
exercise the merge logic without needing to spawn a subprocess for every
command. The CLI parser is also smoke-tested so we catch any future
``dest=`` collision that would silently make ``args.command`` None.
"""

from __future__ import annotations

import json

import pytest

from research_os import collab


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_with_cursor_claude(tmp_path):
    """A workspace with two IDE MCP configs already populated by RO."""
    root = tmp_path
    (root / ".os_state").mkdir()
    # Cursor.
    (root / ".cursor").mkdir(parents=True)
    (root / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"research-os": {"command": "research-os", "args": ["start"]}}}, indent=2)
    )
    # Claude.
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"research-os": {"command": "research-os", "args": ["start"]}}}, indent=2)
    )
    return root


# ---------------------------------------------------------------------------
# mcp_add_server
# ---------------------------------------------------------------------------


class TestMcpAddServer:
    def test_add_to_all_wired_ides_by_default(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        entry = {"command": "npx", "args": ["-y", "@scope/server-foo"]}
        result = collab.mcp_add_server(root, "foo", entry)
        # Both cursor + claude were wired → both should get the entry.
        assert result["cursor"] == "added"
        assert result["claude"] == "added"
        # Verify on disk.
        cursor_cfg = json.loads((root / ".cursor" / "mcp.json").read_text())
        assert cursor_cfg["mcpServers"]["foo"] == entry
        # Existing 'research-os' entry must survive the merge.
        assert "research-os" in cursor_cfg["mcpServers"]
        claude_cfg = json.loads((root / ".claude" / "mcp.json").read_text())
        assert claude_cfg["mcpServers"]["foo"] == entry
        assert "research-os" in claude_cfg["mcpServers"]

    def test_add_only_to_named_ides(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        entry = {"command": "npx", "args": ["-y", "@x/y"]}
        result = collab.mcp_add_server(root, "only-cursor", entry, ides=["cursor"])
        assert result == {"cursor": "added"}
        assert "claude" not in result
        # Claude config must NOT be modified.
        claude_cfg = json.loads((root / ".claude" / "mcp.json").read_text())
        assert "only-cursor" not in claude_cfg["mcpServers"]

    def test_re_add_reports_updated(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        entry1 = {"command": "npx", "args": ["-y", "@v/1"]}
        entry2 = {"command": "node", "args": ["/path/to/server.js"]}
        collab.mcp_add_server(root, "x", entry1, ides=["cursor"])
        result = collab.mcp_add_server(root, "x", entry2, ides=["cursor"])
        assert result["cursor"] == "updated"
        cfg = json.loads((root / ".cursor" / "mcp.json").read_text())
        assert cfg["mcpServers"]["x"] == entry2

    def test_opencode_uses_mcp_not_mcpservers(self, tmp_path):
        """OpenCode's config schema uses the singular `mcp` key."""
        root = tmp_path
        (root / ".os_state").mkdir()
        (root / "opencode.json").write_text(
            json.dumps({"mcp": {"research-os": {"command": "research-os"}},
                       "system_prompt": "x"}, indent=2)
        )
        result = collab.mcp_add_server(root, "slack",
                                       {"command": "npx", "args": ["-y", "x"]},
                                       ides=["opencode"])
        assert result["opencode"] == "added"
        cfg = json.loads((root / "opencode.json").read_text())
        assert "slack" in cfg["mcp"]
        # system_prompt MUST be preserved.
        assert cfg["system_prompt"] == "x"

    def test_unsupported_ide_is_skipped(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        # Windsurf doesn't have a JSON mcpServers block.
        result = collab.mcp_add_server(root, "x", {"command": "npx"},
                                       ides=["windsurf"])
        assert "skipped" in result["windsurf"]


# ---------------------------------------------------------------------------
# mcp_remove_server
# ---------------------------------------------------------------------------


class TestMcpRemoveServer:
    def test_remove_present_server(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        collab.mcp_add_server(root, "doomed", {"command": "npx"},
                              ides=["cursor", "claude"])
        result = collab.mcp_remove_server(root, "doomed",
                                          ides=["cursor", "claude"])
        assert result == {"cursor": "removed", "claude": "removed"}
        cursor_cfg = json.loads((root / ".cursor" / "mcp.json").read_text())
        assert "doomed" not in cursor_cfg["mcpServers"]
        # research-os entry must survive.
        assert "research-os" in cursor_cfg["mcpServers"]

    def test_remove_missing_is_skipped(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        result = collab.mcp_remove_server(root, "never-added",
                                          ides=["cursor"])
        assert "skipped" in result["cursor"]


# ---------------------------------------------------------------------------
# mcp_list_servers
# ---------------------------------------------------------------------------


class TestMcpListServers:
    def test_list_shows_all_configured(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        collab.mcp_add_server(root, "slack",
                              {"command": "npx", "args": ["-y", "slack"]},
                              ides=["cursor"])
        out = collab.mcp_list_servers(root)
        assert "cursor" in out
        assert "claude" in out
        assert "research-os" in out["cursor"]
        assert "slack" in out["cursor"]
        # Slack was only added to cursor → not in claude.
        assert "slack" not in out["claude"]

    def test_empty_workspace_returns_empty_dict(self, tmp_path):
        (tmp_path / ".os_state").mkdir()
        assert collab.mcp_list_servers(tmp_path) == {}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TestMcpTemplates:
    def test_known_templates_exist(self):
        # Done-when wording: {slack, github, postgres, notion, filesystem, memory}
        for name in ("slack", "github", "postgres", "notion",
                     "filesystem", "memory"):
            assert name in collab.MCP_TEMPLATES, f"missing template: {name}"
            entry = collab.MCP_TEMPLATES[name]
            assert "command" in entry, f"template {name} missing command"

    def test_template_drops_into_wired_ides(self, ws_with_cursor_claude):
        root = ws_with_cursor_claude
        entry = collab.MCP_TEMPLATES["slack"]
        result = collab.mcp_add_server(root, "slack", entry,
                                       ides=["cursor", "claude"])
        assert result["cursor"] == "added"
        assert result["claude"] == "added"
        cfg = json.loads((root / ".cursor" / "mcp.json").read_text())
        # Token placeholders must survive the round-trip — researchers
        # fill them in manually.
        assert "${SLACK_BOT_TOKEN}" in json.dumps(cfg)


# ---------------------------------------------------------------------------
# CLI parser smoke test (catches dest=collision regressions)
# ---------------------------------------------------------------------------


class TestMcpCliParserShape:
    def test_mcp_list_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(["mcp", "list"])
        assert args.command == "mcp"
        assert args.action == "list"

    def test_mcp_add_with_command_and_args_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args([
            "mcp", "add", "foo",
            "--command", "npx",
            "--args=-y,@scope/server",
        ])
        # Critical: --command must NOT clobber the subparsers' `command` dest.
        assert args.command == "mcp"
        assert args.action == "add"
        assert args.name == "foo"
        assert args.mcp_command == "npx"
        assert args.mcp_args == "-y,@scope/server"

    def test_mcp_template_parses(self):
        from research_os.cli import build_parser
        args = build_parser().parse_args(["mcp", "template", "slack"])
        assert args.command == "mcp"
        assert args.action == "template"
        assert args.name == "slack"
