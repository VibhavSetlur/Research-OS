"""First-class workspace-mode transitions (B1/B2).

Before this, flipping workspace.mode via config left the scaffold missing and
config/state disagreeing — a silent half-change. These lock the additive,
synced, recorded transition behaviour.
"""
from __future__ import annotations

from research_os.project_ops import scaffold_minimal_workspace, load_state
from research_os.tools.actions.state.config import get_workspace_mode
from research_os.tools.actions.state.mode_transition import (
    transition_workspace_mode,
    workspace_mode_status,
)
from research_os.tools.actions.router import mode_transition_spec


def test_status_reports_mode_and_moves(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    s = workspace_mode_status(tmp_path)
    assert s["config_mode"] == "analysis"
    assert s["drift"] is False
    tos = {m["to"] for m in s["available_transitions"]}
    assert {"hybrid", "multi_study", "exploration"} <= tos


def test_transition_creates_surface_and_syncs(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="exploration")
    res = transition_workspace_mode(tmp_path, "tool_build", plan_only=False, rationale="graduated")
    assert res["status"] == "applied"
    # additive surface created
    assert (tmp_path / "spec").exists() and (tmp_path / "eval").exists()
    # config AND state synced — no drift (the B1 bug)
    assert get_workspace_mode(tmp_path) == "tool_build"
    assert load_state(tmp_path)["workspace_mode"] == "tool_build"
    # recorded
    assert (tmp_path / ".os_state" / "mode_history.jsonl").exists()


def test_transition_is_additive_keeps_prior_work(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="analysis")
    (tmp_path / "workspace" / "01_baseline").mkdir(parents=True)
    (tmp_path / "workspace" / "01_baseline" / "marker.txt").write_text("keep me")
    transition_workspace_mode(tmp_path, "hybrid", plan_only=False)
    # prior analysis work survives the move
    assert (tmp_path / "workspace" / "01_baseline" / "marker.txt").read_text() == "keep me"


def test_unsupported_transition_refused(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="hybrid")
    res = transition_workspace_mode(tmp_path, "multi_study", plan_only=True)
    assert res["status"] == "error"


def test_plan_does_not_mutate(tmp_path):
    scaffold_minimal_workspace(tmp_path, "T", mode="exploration")
    transition_workspace_mode(tmp_path, "tool_build", plan_only=True)
    assert get_workspace_mode(tmp_path) == "exploration"  # unchanged
    assert not (tmp_path / "spec").exists()


def test_transition_matrix_specs_resolve():
    # every declared transition names a real (or empty) protocol + a kind
    assert mode_transition_spec("exploration", "analysis")["kind"] == "promote"
    assert mode_transition_spec("analysis", "analysis") is None  # same-mode noop
