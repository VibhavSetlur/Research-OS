"""Phase 8 — ``tool_step_complete`` advances current_tier.json across tiers.

When the step's owning protocol (read from the active plan or the
protocol-execution log) maps onto a different tier than the workspace's
current tier, the bundle promotes the workspace forward (or backward)
and surfaces the transition.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.protocol import log_protocol_execution
from research_os.tools.actions.router import _clear_tier_cache
from research_os.tools.actions.state.tier_state import (
    get_current_tier,
    set_current_tier,
)


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(tmp_path, "Tier Advance Test")
    return tmp_path


def _scaffold_step(root: Path, step_id: str = "01_baseline") -> str:
    """Create the minimal workspace files tool_step_complete needs."""
    step_dir = root / "workspace" / step_id
    (step_dir / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    (step_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (step_dir / "scripts" / "run.py").write_text("print('ok')\n")
    return step_id


def test_step_complete_advances_tier_from_active_plan(tmp_path):
    """When active_plan.primary_protocol resolves to a new tier, advance."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "intake")

    # Active plan pointing at a synthesize-tier protocol.
    plan_path = root / ".os_state" / "active_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({
        "created_at": "2026-06-05T12:00:00+00:00",
        "user_prompt": "draft the paper",
        "primary_protocol": "synthesis/synthesis_paper",
        "shortcut_tool": None,
        "decomposition": [{"tool": "tool_synthesize_plan", "purpose": "."}],
        "current_step": 1,
        "status": "in_progress",
    }))

    step_id = _scaffold_step(root)

    from research_os.server import _handle_tool_step_complete

    res = _handle_tool_step_complete(
        "tool_step_complete", {"step_id": step_id}, root,
    )
    env = json.loads(res[0].text)
    # tool_step_complete now returns a conformant envelope; the bundle (incl.
    # the tier_transition dict) lives under payload.
    payload = env["payload"]
    assert "tier_transition" in payload, env
    assert payload["tier_transition"]["from"] == "intake"
    assert payload["tier_transition"]["to"] == "synthesize"
    assert get_current_tier(root) == "synthesize"


def test_step_complete_falls_back_to_execution_log(tmp_path):
    """With no active_plan, use the latest protocol_execution_log entry."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "intake")
    log_protocol_execution(
        root, "synthesis/synthesis_paper", "completed", "step done",
        override_completeness_gate=True,
    )
    step_id = _scaffold_step(root)

    from research_os.server import _handle_tool_step_complete

    res = _handle_tool_step_complete(
        "tool_step_complete", {"step_id": step_id}, root,
    )
    env = json.loads(res[0].text)
    assert env["payload"].get("tier_transition", {}).get("to") == "synthesize"
    assert get_current_tier(root) == "synthesize"


def test_step_complete_no_advance_when_tier_unchanged(tmp_path):
    """Same-tier moves write wrote=False and don't push a history entry."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "synthesize")
    log_protocol_execution(
        root, "synthesis/synthesis_paper", "completed", "still synthesize",
        override_completeness_gate=True,
    )
    step_id = _scaffold_step(root)

    from research_os.server import _handle_tool_step_complete

    res = _handle_tool_step_complete(
        "tool_step_complete", {"step_id": step_id}, root,
    )
    env = json.loads(res[0].text)
    trans = env["payload"].get("tier_transition") or {}
    assert trans.get("from") == "synthesize"
    assert trans.get("to") == "synthesize"
    assert trans.get("wrote") is False


def test_step_complete_silent_when_no_protocol_context(tmp_path):
    """Without active_plan AND without log entries, no tier work happens."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    # No prior tier, no plan, no log.
    step_id = _scaffold_step(root)

    from research_os.server import _handle_tool_step_complete

    res = _handle_tool_step_complete(
        "tool_step_complete", {"step_id": step_id}, root,
    )
    payload = json.loads(res[0].text)
    # tier_transition either absent or carries no usable target.
    assert payload.get("tier_transition") in (None, {})
    assert get_current_tier(root) is None


def test_audit_master_reports_tier_progress(tmp_path):
    """``tool_audit_master`` surfaces the per-tier protocol counts."""
    _clear_tier_cache()
    root = _scaffold(tmp_path)
    set_current_tier(root, "synthesize")
    log_protocol_execution(root, "guidance/project_startup", "completed", "", override_completeness_gate=True)
    log_protocol_execution(root, "writing/writing_methods", "completed", "", override_completeness_gate=True)
    log_protocol_execution(root, "synthesis/synthesis_paper", "completed", "", override_completeness_gate=True)

    from research_os.server import _handle_tool_audit_quality_full

    res = _handle_tool_audit_quality_full(
        "tool_audit_quality_full", {}, root,
    )
    payload = json.loads(res[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert "tier_progress" in data, data
    tp = data["tier_progress"]
    assert tp["current_tier"] == "synthesize"
    # Each per-tier entry has the schema fields the writer needs.
    by_tier = {entry["tier"]: entry for entry in tp["per_tier"]}
    assert by_tier["synthesize"]["n_protocols_fired"] >= 2
    assert by_tier["intake"]["n_protocols_fired"] >= 1
    # n_tiers_visited counts distinct tiers seen.
    assert tp["n_tiers_visited"] >= 2
