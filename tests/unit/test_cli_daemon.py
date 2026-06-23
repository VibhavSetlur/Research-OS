"""Unit tests for `research-os daemon` (CLI subcommand wiring).

Covers parser wiring, the completion-tuple sync invariant, status output
(text + JSON) for an uninitialized vs. initialized project, the preview
'start' contract (non-zero exit, not serving), and bind overrides.
"""
from __future__ import annotations

import json

from research_os import cli


# ── parser + completion sync ─────────────────────────────────────────────


def test_daemon_in_completion_tuple():
    """The completion tuple must list 'daemon' (fish/argcomplete sync)."""
    assert "daemon" in cli.SUBCOMMANDS_FOR_COMPLETION


def test_parser_accepts_daemon_subcommands():
    parser = cli.build_parser()
    for argv in (["daemon"], ["daemon", "status"], ["daemon", "status", "--json"],
                 ["daemon", "start"]):
        args = parser.parse_args(argv)
        assert args.command == "daemon"


def test_fish_completion_mentions_daemon(capsys):
    parser = cli.build_parser()
    cli.cmd_completion(parser.parse_args(["completion", "fish"]))
    assert "daemon" in capsys.readouterr().out


# ── status command ───────────────────────────────────────────────────────


def _run(parser, argv):
    return cli.cmd_daemon(parser.parse_args(argv))


def test_daemon_no_subcommand_prints_help(capsys):
    parser = cli.build_parser()
    rc = _run(parser, ["daemon"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "daemon status" in out
    assert "ROADMAP" in out


def test_daemon_status_text_uninitialized(tmp_path, capsys):
    parser = cli.build_parser()
    rc = _run(parser, ["daemon", "status", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Research OS daemon" in out
    assert "initialized: no" in out
    assert "127.0.0.1:8787" in out


def test_daemon_status_json_is_valid(tmp_path, capsys):
    parser = cli.build_parser()
    rc = _run(parser, ["daemon", "status", "--workspace", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["serving"] is False
    assert payload["project_initialized"] is False
    assert payload["config"]["base_url"] == "http://127.0.0.1:8787"


def test_daemon_status_initialized(tmp_path, capsys):
    (tmp_path / ".os_state").mkdir()
    parser = cli.build_parser()
    rc = _run(parser, ["daemon", "status", "--workspace", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)["project_initialized"] is True


# ── start serving contract ───────────────────────────────────────────────


def test_daemon_start_serves(tmp_path, capsys, monkeypatch):
    """Phase 1: 'start' announces the bind + endpoints and calls serve().

    serve() blocks on a real bind, so we patch it to a no-op and assert the
    CLI drives it (announces base_url, exits 0).
    """
    served = {"called": False}

    def fake_serve(self):
        served["called"] = True

    monkeypatch.setattr("research_os.daemon.Daemon.serve", fake_serve)
    parser = cli.build_parser()
    rc = _run(parser, ["daemon", "start", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert served["called"] is True
    assert "starting on" in out.lower()
    assert "/healthz" in out


def test_daemon_start_missing_extra_hint(tmp_path, capsys, monkeypatch):
    """If the [daemon] extra is missing, serve() raises RuntimeError and the
    CLI surfaces a clear hint with exit code 1 (graceful degrade)."""

    def boom(self):
        raise RuntimeError("the 'research-os[daemon]' extra is required")

    monkeypatch.setattr("research_os.daemon.Daemon.serve", boom)
    parser = cli.build_parser()
    rc = _run(parser, ["daemon", "start", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "daemon" in out.lower() and "extra" in out.lower()


def test_daemon_start_bind_overrides(tmp_path):
    """--host/--port flow through to the resolved config (visible via status)."""
    # Confirm the override path is exercised via a direct Daemon build.
    from research_os.daemon import Daemon

    d = Daemon.for_root(tmp_path, host="0.0.0.0", port=9123)
    cfg = d.status().to_dict()["config"]
    assert cfg["host"] == "0.0.0.0"
    assert cfg["port"] == 9123
