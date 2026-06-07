"""W20 — AI-side knobs: researcher_config.ai.context_class + ai.model_profile.

Verifies:
  * `_read_profile` reads context_class + ai.model_profile from the new
    `ai:` block, with `ai.model_profile` overriding the legacy top-level
    `model_profile`.
  * Default values are `context_class="short"` and `model_profile="medium"`.
  * `sys_boot` returns both `model_profile` and `context_class` so the AI
    doesn't have to guess.
  * `sys_boot` returns `active_packs` (visibility for pack tools).
  * `sys_protocol_get` defaults to format='full' when context_class='long',
    'lean' when model_profile='small', otherwise 'summary'.
  * Explicit `format` argument always wins over the profile-derived
    default.
  * Validate config accepts the new ai.* enum values + rejects off-enum
    values.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


def _scaffold(tmp_path: Path, ai_block: dict | None = None,
              top_model_profile: str | None = None) -> Path:
    """Write a minimal inputs/researcher_config.yaml + .os_state/."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / ".os_state").mkdir()
    cfg: dict = {
        "project_name": "w20-test",
        "researcher": {"name": "test"},
        "interaction": {"autonomy_level": "supervised"},
        "research_goal": {"output_types": ["paper"]},
    }
    if top_model_profile is not None:
        cfg["model_profile"] = top_model_profile
    if ai_block is not None:
        cfg["ai"] = ai_block
    (tmp_path / "inputs" / "researcher_config.yaml").write_text(
        yaml.safe_dump(cfg)
    )
    return tmp_path


def _payload(resp):
    text = resp[0].text if hasattr(resp[0], "text") else resp[0]["text"]
    obj = json.loads(text)
    if "payload" in obj and isinstance(obj["payload"], dict):
        return obj["payload"]
    return obj


# ── _read_profile ──────────────────────────────────────────────────────


def test_read_profile_defaults_when_ai_block_absent(tmp_path):
    from research_os.server._helpers import _read_profile

    _scaffold(tmp_path)
    p = _read_profile(tmp_path)
    assert p["context_class"] == "short"
    assert p["model_profile"] == "medium"


def test_read_profile_picks_up_ai_block(tmp_path):
    from research_os.server._helpers import _read_profile

    _scaffold(tmp_path, ai_block={
        "context_class": "long",
        "model_profile": "small",
    })
    p = _read_profile(tmp_path)
    assert p["context_class"] == "long"
    assert p["model_profile"] == "small"


def test_ai_model_profile_overrides_top_level(tmp_path):
    from research_os.server._helpers import _read_profile

    _scaffold(tmp_path, top_model_profile="large",
              ai_block={"model_profile": "small"})
    p = _read_profile(tmp_path)
    assert p["model_profile"] == "small"


def test_top_level_model_profile_used_when_ai_block_missing(tmp_path):
    from research_os.server._helpers import _read_profile

    _scaffold(tmp_path, top_model_profile="large")
    p = _read_profile(tmp_path)
    assert p["model_profile"] == "large"
    assert p["context_class"] == "short"


# ── sys_boot exposes the AI-side knobs + active_packs ─────────────────


def test_sys_boot_returns_model_profile_and_context_class(tmp_path):
    from research_os.tools.actions.router import sys_boot

    _scaffold(tmp_path, ai_block={
        "context_class": "long",
        "model_profile": "small",
    })
    res = sys_boot(tmp_path)
    assert res["status"] == "success"
    assert res["model_profile"] == "small"
    assert res["context_class"] == "long"
    # active_packs visibility — even when empty, the key must exist so
    # the AI can answer "is tool_X real or hallucinated?".
    assert "active_packs" in res
    assert isinstance(res["active_packs"], list)


def test_sys_boot_lean_also_returns_active_packs(tmp_path):
    from research_os.tools.actions.router import sys_boot

    _scaffold(tmp_path)
    res = sys_boot(tmp_path, lean=True)
    assert res["status"] == "success"
    assert "active_packs" in res
    assert isinstance(res["active_packs"], list)


# ── sys_protocol_get format default driven by AI knobs ────────────────


def _make_protocol(tmp_path: Path):
    """Drop a minimal protocol YAML where load_protocol can find it."""
    # Just sanity-test the format-default selection logic in the handler.
    # We mock load_protocol so the test stays unit-scoped.
    pass


def test_protocol_get_default_format_small_model(tmp_path, monkeypatch):
    from research_os.server.handlers import meta_routing

    _scaffold(tmp_path, ai_block={"model_profile": "small"})

    captured = {}

    def fake_load(p_name, *, model_profile, format, step_id):
        captured["format"] = format
        captured["model_profile"] = model_profile
        return {"id": p_name, "summary": "x"}

    monkeypatch.setattr(meta_routing, "load_protocol", fake_load)
    meta_routing._handle_sys_protocol_get(
        "sys_protocol_get", {"protocol_name": "demo"}, tmp_path,
    )
    assert captured["format"] == "lean"
    assert captured["model_profile"] == "small"


def test_protocol_get_default_format_long_context(tmp_path, monkeypatch):
    from research_os.server.handlers import meta_routing

    _scaffold(tmp_path, ai_block={"context_class": "long"})

    captured = {}

    def fake_load(p_name, *, model_profile, format, step_id):
        captured["format"] = format
        return {"id": p_name, "content": "y"}

    monkeypatch.setattr(meta_routing, "load_protocol", fake_load)
    meta_routing._handle_sys_protocol_get(
        "sys_protocol_get", {"protocol_name": "demo"}, tmp_path,
    )
    assert captured["format"] == "full"


def test_protocol_get_default_format_summary_otherwise(tmp_path, monkeypatch):
    from research_os.server.handlers import meta_routing

    _scaffold(tmp_path)  # no ai block — short/medium defaults

    captured = {}

    def fake_load(p_name, *, model_profile, format, step_id):
        captured["format"] = format
        return {"id": p_name, "summary": "z"}

    monkeypatch.setattr(meta_routing, "load_protocol", fake_load)
    meta_routing._handle_sys_protocol_get(
        "sys_protocol_get", {"protocol_name": "demo"}, tmp_path,
    )
    assert captured["format"] == "summary"


def test_protocol_get_explicit_format_wins(tmp_path, monkeypatch):
    from research_os.server.handlers import meta_routing

    _scaffold(tmp_path, ai_block={"model_profile": "small"})

    captured = {}

    def fake_load(p_name, *, model_profile, format, step_id):
        captured["format"] = format
        return {"id": p_name, "summary": "explicit"}

    monkeypatch.setattr(meta_routing, "load_protocol", fake_load)
    # Even with model_profile=small, explicit format='summary' should
    # win — the AI knows what it wants.
    meta_routing._handle_sys_protocol_get(
        "sys_protocol_get",
        {"protocol_name": "demo", "format": "summary"},
        tmp_path,
    )
    assert captured["format"] == "summary"


# ── validate_config ────────────────────────────────────────────────────


def test_validate_accepts_valid_ai_values(tmp_path):
    from research_os.tools.actions.state.config import validate_config

    _scaffold(tmp_path, ai_block={
        "context_class": "long",
        "model_profile": "small",
    })
    res = validate_config(tmp_path)
    assert res["status"] == "success"
    # No enum violations for the ai.* block.
    bad = [v for v in res.get("enum_violations", [])
           if v["field"].startswith("ai.")]
    assert bad == []


def test_validate_rejects_off_enum_ai_values(tmp_path):
    from research_os.tools.actions.state.config import validate_config

    _scaffold(tmp_path, ai_block={
        "context_class": "ginormous",
        "model_profile": "xxl",
    })
    res = validate_config(tmp_path)
    bad_fields = {v["field"] for v in res.get("enum_violations", [])}
    assert "ai.context_class" in bad_fields
    assert "ai.model_profile" in bad_fields
