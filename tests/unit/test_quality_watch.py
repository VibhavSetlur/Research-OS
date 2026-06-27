"""Per-turn quality watchers (A2/A3/A4) — daemon/server watching AI more closely."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.server.quality_watch import quality_hints


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def _codes(hints):
    return [h["code"] for h in hints]


def test_ungrounded_synthesis_is_flagged():
    root = _proj()
    (root / "synthesis").mkdir(exist_ok=True)
    (root / "synthesis" / "paper.md").write_text(
        "The effect was 0.42 (p=0.03), a 25% reduction across 1200 patients."
    )
    hints = quality_hints("sys_file_write", {"filepath": "synthesis/paper.md"}, root)
    assert "ungrounded_synthesis_unverified" in _codes(hints)
    h = next(x for x in hints if x["code"] == "ungrounded_synthesis_unverified")
    assert "claim_grounding" in h["next_recommended_call"]


def test_synthesis_with_no_numbers_is_not_flagged():
    root = _proj()
    (root / "synthesis").mkdir(exist_ok=True)
    (root / "synthesis" / "intro.md").write_text("This paper studies a phenomenon.")
    hints = quality_hints("sys_file_write", {"filepath": "synthesis/intro.md"}, root)
    assert "ungrounded_synthesis_unverified" not in _codes(hints)


def test_conclusions_without_audit_is_flagged():
    root = _proj()
    sd = root / "workspace" / "01_x"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "conclusions.md").write_text("We conclude the model works.")
    hints = quality_hints(
        "sys_file_write", {"filepath": "workspace/01_x/conclusions.md"}, root)
    assert "wrote_conclusions_no_audit" in _codes(hints)


def test_stuck_protocol_loop_is_flagged():
    root = _proj()
    log = root / ".os_state" / "protocol_execution_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    import json
    log.write_text("\n".join(
        json.dumps({"status": "failed", "protocol": "x"}) for _ in range(4)
    ) + "\n")
    hints = quality_hints("tool_route", {"prompt": "retry"}, root)
    assert "stuck_protocol_loop" in _codes(hints)


def test_unwatched_tool_returns_nothing():
    root = _proj()
    assert quality_hints("sys_help", {}, root) == []


def test_debounce_suppresses_repeat():
    root = _proj()
    (root / "synthesis").mkdir(exist_ok=True)
    (root / "synthesis" / "paper.md").write_text("Effect 0.42 across 1200 cases.")
    first = quality_hints("sys_file_write", {"filepath": "synthesis/paper.md"}, root)
    second = quality_hints("sys_file_write", {"filepath": "synthesis/paper.md"}, root)
    assert any(h["code"] == "ungrounded_synthesis_unverified" for h in first)
    assert not any(h["code"] == "ungrounded_synthesis_unverified" for h in second)


def test_next_action_hint_for_high_traffic_tools():
    from research_os.server.quality_watch import next_action_hint
    root = _proj()
    assert "completeness" in next_action_hint("tool_step_complete", root)
    assert "claim_grounding" in next_action_hint("tool_synthesis_scaffold", root)
    assert next_action_hint("sys_help", root) is None  # not high-traffic


def test_next_action_route_advances_when_plan_persisted():
    import json as _json
    from research_os.server.quality_watch import next_action_hint
    root = _proj()
    (root / ".os_state").mkdir(exist_ok=True)
    (root / ".os_state" / "active_plan.json").write_text(_json.dumps({"protocol": "x"}))
    assert "tool_plan" in next_action_hint("tool_route", root)
