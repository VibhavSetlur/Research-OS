"""Tests for `research-os hermes` — wiring RO into Hermes Agent config.

Covers add / status / remove against an isolated temp config, idempotency,
the HTTP-url variant, and the built-in-skills-dir special case (no
external_dir entry needed when the skill lands in ~/.hermes/skills).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from research_os import hermes_integration as hi

yaml = pytest.importorskip("ruamel.yaml")


def _cfg(tmp_path) -> Path:
    return tmp_path / "config.yaml"


def test_add_creates_server_and_installs_skill(tmp_path, monkeypatch):
    # Keep the skill install inside the tmp tree so we don't touch the real home.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_home"))
    cfg = _cfg(tmp_path)
    res = hi.add(config_path=cfg)
    assert res["server_action"] == "added"
    assert res["command"]  # auto-detected stdio launch
    assert Path(res["skill_path"]).exists()
    assert "research-os" in Path(res["skill_path"]).read_text().lower()
    # Config persisted with the server entry.
    assert cfg.exists()
    text = cfg.read_text()
    assert "mcp_servers:" in text
    assert "research-os" in text


def test_add_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    hi.add(config_path=cfg)
    res2 = hi.add(config_path=cfg)
    assert res2["server_action"] == "updated"
    # Only one entry under mcp_servers.
    data = hi._load(cfg)
    assert list(data["mcp_servers"].keys()) == [hi.SERVER_KEY]


def test_status_reports_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    before = hi.status(config_path=cfg)
    assert before["server_registered"] is False
    hi.add(config_path=cfg)
    after = hi.status(config_path=cfg)
    assert after["server_registered"] is True
    assert after["skill_installed"] is True


def test_remove_unwires_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    hi.add(config_path=cfg)
    res = hi.remove(config_path=cfg)
    assert res["server_removed"] is True
    assert hi.status(config_path=cfg)["server_registered"] is False
    # Remove is idempotent.
    res2 = hi.remove(config_path=cfg)
    assert res2["server_removed"] is False


def test_url_variant_registers_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    res = hi.add(url="http://127.0.0.1:8765/mcp", config_path=cfg)
    assert res["url"] == "http://127.0.0.1:8765/mcp"
    data = hi._load(cfg)
    entry = data["mcp_servers"][hi.SERVER_KEY]
    assert entry["url"] == "http://127.0.0.1:8765/mcp"
    assert "command" not in entry


def test_builtin_skills_dir_needs_no_external_dir(tmp_path, monkeypatch):
    # Default HERMES_HOME → skill installs under ~/.hermes/skills, which
    # Hermes already scans, so external_dirs must stay empty.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    res = hi.add(config_path=cfg)
    assert res["external_dir_added"] is False
    assert res["external_dir_needed"] is False
    data = hi._load(cfg)
    assert data["skills"]["external_dirs"] == []


def test_preserves_existing_config_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    cfg = _cfg(tmp_path)
    cfg.write_text("model: claude\nskills:\n  external_dirs: []\n  write_approval: false\n")
    hi.add(config_path=cfg)
    data = hi._load(cfg)
    # Pre-existing keys survive the merge.
    assert data["model"] == "claude"
    assert data["skills"]["write_approval"] is False
    assert hi.SERVER_KEY in data["mcp_servers"]
