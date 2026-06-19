"""3.2.6 — router drift guards + step dispatch coverage.

Two whole router gates silently died because their tool sets drifted to
names later removed (``tool_synthesize`` / ``tool_dashboard_create`` /
``tool_poster_create`` are all in ``_REMOVED_TOOLS``), so the anti-one-shot
deliverable gate + heavy-step weighting never fired for Typst deliverables.
And ``tool_step(operation='env_lock')`` always failed because the dispatcher
resolved the handler via globals() that didn't contain it. These guards lock
both fixes.
"""
from __future__ import annotations

import json

import pytest


def test_deliverable_tools_have_no_removed_drift():
    from research_os.server.aliases import _REMOVED_TOOLS
    from research_os.tools.actions.router import DELIVERABLE_TOOLS
    drifted = set(DELIVERABLE_TOOLS) & set(_REMOVED_TOOLS)
    assert not drifted, f"DELIVERABLE_TOOLS names a removed tool: {drifted}"


def test_heavy_tools_have_no_removed_drift():
    from research_os.server.aliases import _REMOVED_TOOLS
    from research_os.tools.actions.router import _HEAVY_TOOLS
    drifted = set(_HEAVY_TOOLS) & set(_REMOVED_TOOLS)
    assert not drifted, f"_HEAVY_TOOLS names a removed tool: {drifted}"


def test_deliverable_tools_all_registered():
    """Every deliverable-gate tool must be a live registered tool."""
    import research_os.server as srv
    from research_os.tools.actions.router import DELIVERABLE_TOOLS
    missing = [t for t in DELIVERABLE_TOOLS if t not in srv.TOOL_DEFINITIONS]
    assert not missing, f"DELIVERABLE_TOOLS references unregistered tools: {missing}"


def test_step_env_lock_dispatches(tmp_path):
    """tool_step(operation='env_lock') must reach its handler (was a dead path:
    the handler lives in meta_routing but the dispatcher resolves via globals)."""
    import research_os.server as srv
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    out = srv._handle_tool_call(
        "tool_step", {"operation": "env_lock", "step_id": "01_x"}, tmp_path
    )
    env = json.loads(out[0].text)
    # No real step on disk -> a clean error, NOT "handler not callable".
    assert env["status"] in {"success", "error"}
    assert "not callable" not in (env.get("error") or "")


def test_step_env_lock_alias_dispatches(tmp_path):
    import research_os.server as srv
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    out = srv._handle_tool_call("tool_step_env_lock", {"step_id": "01_x"}, tmp_path)
    env = json.loads(out[0].text)
    assert "not callable" not in (env.get("error") or "")


@pytest.mark.parametrize("profile,key", [("small", "ai"), ("large", "ai")])
def test_model_profile_read_from_ai_section(tmp_path, profile, key):
    """_read_model_profile must honour the canonical ai.model_profile location."""
    import yaml
    from research_os.project_ops import scaffold_minimal_workspace
    from research_os.tools.actions.router import _read_model_profile
    scaffold_minimal_workspace(tmp_path, "MP")
    cfg_path = tmp_path / "inputs" / "researcher_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    cfg.setdefault("ai", {})["model_profile"] = profile
    cfg_path.write_text(yaml.dump(cfg, sort_keys=False))
    assert _read_model_profile(tmp_path) == profile
