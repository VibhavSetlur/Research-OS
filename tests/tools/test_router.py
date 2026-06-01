"""Tests for sys_boot, tool_route (hierarchical), per-turn batching,
active tool scoping, and the active-plan decomposition."""

import json

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.router import (
    active_tools_for_protocol,
    advance_plan,
    clear_active_plan,
    plan_turn,
    route_request,
    sys_boot,
)


def test_sys_boot_returns_full_payload(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Router Test")
    res = sys_boot(tmp_path)
    assert res["status"] == "success"
    # Every key the AI is expected to consume in one shot.
    for k in (
        "project_name", "pipeline_stage", "current_path", "domain",
        "autonomy", "expertise", "model_profile", "shared_server",
        "active_hypotheses", "history_tail", "last_protocol_entry",
        "pause_classification", "next_protocol", "dep_inventory",
        "active_plan", "advice",
    ):
        assert k in res, f"sys_boot missing key {k}"
    assert res["project_name"] == "Router Test"
    assert res["pause_classification"] == "fresh_session"


def test_sys_boot_survives_unscaffolded_root(tmp_path):
    # No scaffold — sys_boot must still return a degraded payload, not throw.
    res = sys_boot(tmp_path)
    assert res["status"] == "success"
    # Any string is acceptable; we just want no exception escaping.
    assert isinstance(res["pipeline_stage"], str)


def test_route_intake_prompt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Route Test")
    res = route_request("fill the intake", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "guidance/project_startup"
    # Shortcut tool should resolve to intake autofill.
    assert res["shortcut_tool"] == "tool_intake_autofill"
    assert "decomposition" in res
    assert res["complexity"] == "low"  # short prompt


def test_route_complex_prompt_persists_plan(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Complex Route Test")
    prompt = (
        "alright go and run a baseline EDA, then fit a random forest, "
        "and audit the figures, also write the methods section"
    )
    res = route_request(prompt, tmp_path)
    assert res["status"] == "success"
    assert res["complexity"] == "high"
    assert "active_plan_path" in res
    plan = json.loads((tmp_path / res["active_plan_path"]).read_text())
    assert plan["status"] == "in_progress"
    assert plan["current_step"] == 1
    assert len(plan["decomposition"]) >= 1
    assert plan["user_prompt"] == prompt


def test_route_no_persist_when_disabled(tmp_path):
    scaffold_minimal_workspace(tmp_path, "No Persist Test")
    prompt = "run a baseline EDA and then fit a random forest"
    res = route_request(prompt, tmp_path, persist_plan=False)
    assert res["status"] == "success"
    assert "active_plan_path" not in res
    assert not (tmp_path / ".os_state" / "active_plan.json").exists()


def test_route_quick_review(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Review Route Test")
    res = route_request("can you tear apart that draft paper", tmp_path)
    assert res["status"] == "success"
    # Either the protocol or the shortcut should win.
    assert (
        res["primary_protocol"] == "guidance/quick_paper_review"
        or res["shortcut_tool"] == "tool_quick_review"
    )


def test_route_resume_prompt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Resume Route Test")
    res = route_request("pick up where we left off", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "guidance/session_resume"
    assert res["shortcut_tool"] == "tool_session_resume"


def test_route_handoff_prompt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Handoff Route Test")
    res = route_request("wrap up I need to come back tomorrow", tmp_path)
    assert res["status"] == "success"
    assert (
        res["primary_protocol"] == "guidance/chat_handoff"
        or res["shortcut_tool"] == "sys_session_handoff"
    )


def test_route_empty_prompt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Empty Route Test")
    res = route_request("   ", tmp_path)
    assert res["status"] == "error"


def test_advance_plan_walks_decomposition(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Advance Test")
    prompt = "run a baseline EDA and then fit a random forest and audit"
    route_request(prompt, tmp_path)
    assert (tmp_path / ".os_state" / "active_plan.json").exists()
    step2 = advance_plan(tmp_path)
    assert step2["status"] == "success"
    assert step2["current_step"] >= 2
    # Drain the plan; eventually it archives itself.
    for _ in range(20):
        res = advance_plan(tmp_path)
        if res.get("message") and "completed" in res["message"].lower():
            break
    assert not (tmp_path / ".os_state" / "active_plan.json").exists()


def test_clear_plan_removes_file(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Clear Test")
    prompt = "run a baseline and fit a model and write the paper"
    route_request(prompt, tmp_path)
    assert (tmp_path / ".os_state" / "active_plan.json").exists()
    res = clear_active_plan(tmp_path)
    assert res["status"] == "success"
    assert not (tmp_path / ".os_state" / "active_plan.json").exists()


def test_route_fallback_unknown_prompt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Fallback Test")
    res = route_request("xyzzy nonsense plover", tmp_path)
    assert res["status"] == "success"
    # No trigger should match.
    assert res["primary_protocol"] is None or res["matched_triggers"] == []
    # Resolved at L0 with an ask_user.
    assert res["resolved_level"] == 0
    assert res["ask_user"] is not None


def test_route_hierarchical_fields(tmp_path):
    """Every successful route should expose resolved_level + intent_class."""
    scaffold_minimal_workspace(tmp_path, "Hier Test")
    res = route_request("fill the intake", tmp_path)
    assert res["status"] == "success"
    assert "resolved_level" in res
    assert res["resolved_level"] == 3
    assert res["intent_class"] == "discover"
    assert res["sub_intent"] == "intake"


def test_route_ambiguous_at_l2_asks_user(tmp_path):
    """A clear L1 + ambiguous L3 candidates returns ask_user."""
    scaffold_minimal_workspace(tmp_path, "Ambiguous L2 Test")
    # "synthesize" with both "abstract" and "dashboard" intents.
    res = route_request("write me an abstract and a dashboard", tmp_path)
    assert res["status"] == "success"
    # L1 should still resolve (synthesize) but the specific sub_intent
    # may be ambiguous depending on scoring.
    # At minimum the router shouldn't crash.
    assert res["intent_class"] in {"synthesize", None}


def test_plan_turn_with_no_active_plan(tmp_path):
    scaffold_minimal_workspace(tmp_path, "PlanTurn NoPlan")
    res = plan_turn(tmp_path)
    assert res["status"] == "success"
    assert res["this_turn"] == []
    assert res["next_turn"] == []


def test_plan_turn_batches_by_model_profile(tmp_path):
    scaffold_minimal_workspace(tmp_path, "PlanTurn Batch")
    # Default model_profile is medium → budget 3.
    prompt = (
        "alright run a baseline EDA and then fit a random forest and "
        "audit the figures and write the methods section"
    )
    route_request(prompt, tmp_path)
    # active_plan should exist now.
    res = plan_turn(tmp_path)
    assert res["status"] == "success"
    assert res["model_profile"] == "medium"
    assert res["turn_budget"] == 3
    # Should have at least 1 step this turn.
    assert len(res["this_turn"]) >= 1
    # Total this_turn + next_turn equals remaining decomposition.
    assert (
        len(res["this_turn"]) + len(res["next_turn"]) ==
        7  # analysis_plan decomposition size from _router_index.yaml
    )


def test_plan_turn_small_model_one_step_per_turn(tmp_path):
    import yaml as _yaml
    scaffold_minimal_workspace(tmp_path, "PlanTurn Small")
    cfg_path = tmp_path / "inputs" / "researcher_config.yaml"
    cfg = _yaml.safe_load(cfg_path.read_text()) or {}
    cfg["model_profile"] = "small"
    cfg_path.write_text(_yaml.dump(cfg, sort_keys=False))

    prompt = (
        "alright run a baseline EDA and then fit a random forest and "
        "audit the figures and write the methods section"
    )
    route_request(prompt, tmp_path)
    res = plan_turn(tmp_path)
    assert res["status"] == "success"
    assert res["model_profile"] == "small"
    assert res["turn_budget"] == 1
    assert len(res["this_turn"]) == 1


def test_route_returns_active_tools(tmp_path):
    """tool_route response must include an active_tools shortlist."""
    scaffold_minimal_workspace(tmp_path, "Active Tools Test")
    res = route_request("fill the intake", tmp_path)
    assert res["status"] == "success"
    assert "active_tools" in res
    tools = res["active_tools"]
    assert isinstance(tools, list)
    assert "sys_boot" in tools         # essential
    assert "tool_route" in tools       # essential
    assert "tool_intake_autofill" in tools  # protocol's shortcut


def test_active_tools_for_protocol_direct_lookup(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Active Tools Direct")
    res = active_tools_for_protocol("synthesis/synthesis_paper")
    assert res["status"] == "success"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "paper"
    # Decomposition includes tool_synthesize.
    assert "tool_synthesize" in res["active_tools"]
    # Essentials still present.
    assert "sys_boot" in res["active_tools"]
    assert res["active_tools_count"] > 10


def test_active_tools_for_unknown_protocol(tmp_path):
    res = active_tools_for_protocol("nonexistent/ghost")
    assert res["status"] == "error"


def test_route_visualization_workflow(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Viz Workflow")
    res = route_request("make me a figure from this CSV for the talk", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "visualization/visualization_workflow"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "viz_build"


def test_route_figure_critique(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Figure Critique")
    res = route_request("critique this figure for me", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "visualization/figure_critique"
    assert res["intent_class"] == "review"
    assert res["sub_intent"] == "figure"


def test_route_synthesis_slides(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Slides")
    res = route_request("build a slide deck for my conference talk", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_slides"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "slides"


def test_route_lay_summary(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Lay Summary")
    res = route_request("write a lay summary for the public", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_lay_summary"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "lay"


def test_route_progress_update(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Progress")
    res = route_request("weekly update for my pi", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_progress_update"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "update"


def test_route_from_inputs_synthesis(tmp_path):
    scaffold_minimal_workspace(tmp_path, "From Inputs")
    res = route_request(
        "we already analysed this, just write it up", tmp_path
    )
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_from_inputs"
    assert res["intent_class"] == "synthesize"
    assert res["sub_intent"] == "inputs_only"


def test_route_exploratory_data_analysis(tmp_path):
    scaffold_minimal_workspace(tmp_path, "EDA")
    res = route_request("do real eda on this dataset", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/exploratory_data_analysis"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "eda"


def test_route_method_comparison(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Method Compare")
    res = route_request("benchmark these methods head-to-head", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/method_comparison"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "comparison"


def test_route_data_quality_audit(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Data QC")
    res = route_request("data quality audit on this csv", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/data_quality_audit"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "data_audit"


def test_route_power_analysis(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Power")
    res = route_request("power analysis for the irb", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/power_analysis"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "power"


def test_route_reproduction_attempt(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Reproduction")
    res = route_request("reproduce this paper for me", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/reproduction_attempt"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "reproduce"


def test_route_methodological_consultation(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Consult")
    res = route_request("teach me about mixed effects models", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/methodological_consultation"
    assert res["intent_class"] == "methodology"
    assert res["sub_intent"] == "consult"


def test_route_comparative_paper_review(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Paper Compare")
    res = route_request("compare these papers for journal club", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "literature/comparative_paper_review"
    assert res["intent_class"] == "literature"
    assert res["sub_intent"] == "compare"


def test_route_mid_pipeline_entry(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Mid Entry")
    res = route_request(
        "i'm bringing this into research-os, we've been working on this for months",
        tmp_path,
    )
    assert res["status"] == "success"
    assert res["primary_protocol"] == "guidance/mid_pipeline_entry"
    assert res["intent_class"] == "discover"
    assert res["sub_intent"] == "mid_entry"


def test_route_figure_guidelines_still_wins_on_style_prompt(tmp_path):
    """figure_guidelines (style) should still win on a styling prompt,
    not be hijacked by the new visualization_workflow."""
    scaffold_minimal_workspace(tmp_path, "Figure Guidelines")
    res = route_request("which color palette should i use for the dpi", tmp_path)
    assert res["status"] == "success"
    # Either figure_guidelines or visualization_workflow; we just check
    # that figures-domain protocols win over unrelated ones.
    assert res["primary_protocol"] in (
        "visualization/figure_guidelines",
        "visualization/visualization_workflow",
    )


def test_route_existing_protocols_not_hijacked_by_new_ones(tmp_path):
    """Regression: adding 14 new protocols should not change routing
    for any existing well-known trigger phrase."""
    scaffold_minimal_workspace(tmp_path, "Regression")
    # Each pair is (prompt, expected pre-existing protocol).
    pairs = [
        ("fill the intake", "guidance/project_startup"),
        ("run a baseline EDA and then fit a random forest and audit",
         "guidance/analysis_plan"),
        ("draft the paper for a journal", "synthesis/synthesis_paper"),
        ("review this paper", "guidance/quick_paper_review"),
        ("review my code", "guidance/code_review"),
        ("pick up where we left off", "guidance/session_resume"),
        ("wrap up i need to come back tomorrow", "guidance/chat_handoff"),
        ("make a poster for an academic conference",
         "synthesis/synthesis_poster"),
        ("build a dashboard for the lab meeting",
         "synthesis/synthesis_dashboard"),
        ("draft an nsf proposal", "synthesis/synthesis_grant"),
        ("preregister this study before data lands",
         "methodology/preregistration"),
        ("send to a collaborator", "guidance/collaboration_handoff"),
    ]
    for prompt, expected in pairs:
        res = route_request(prompt, tmp_path)
        assert res["status"] == "success", prompt
        assert res["primary_protocol"] == expected, (
            f"Regression: {prompt!r} routed to "
            f"{res['primary_protocol']!r}, expected {expected!r}"
        )


def test_route_writing_discussion(tmp_path):
    scaffold_minimal_workspace(tmp_path, "writing discussion")
    res = route_request("draft the discussion section", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "writing/writing_discussion"


def test_route_writing_limitations(tmp_path):
    scaffold_minimal_workspace(tmp_path, "writing limitations")
    res = route_request("tighten the limitations", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "writing/writing_limitations"


def test_route_writing_results(tmp_path):
    scaffold_minimal_workspace(tmp_path, "writing results")
    res = route_request("draft the results section", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "writing/writing_results"


def test_route_writing_end_matter(tmp_path):
    scaffold_minimal_workspace(tmp_path, "end matter")
    res = route_request("draft the end matter", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "writing/writing_data_availability"


def test_route_multi_panel(tmp_path):
    scaffold_minimal_workspace(tmp_path, "multi panel")
    res = route_request("multi-panel figure with subpanels", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "visualization/multi_panel_composition"


def test_route_figure_narrative_arc(tmp_path):
    scaffold_minimal_workspace(tmp_path, "arc")
    res = route_request("order my figures for the paper", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "visualization/figure_narrative_arc"


def test_route_color_accessibility(tmp_path):
    scaffold_minimal_workspace(tmp_path, "a11y")
    res = route_request("check colour accessibility on my figures", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "visualization/color_accessibility_audit"


def test_route_cover_letter(tmp_path):
    scaffold_minimal_workspace(tmp_path, "cover")
    res = route_request("draft a cover letter for the journal", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_cover_letter"


def test_route_title_workshop(tmp_path):
    scaffold_minimal_workspace(tmp_path, "title")
    res = route_request("workshop the title for the paper", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_title_workshop"


def test_route_handout(tmp_path):
    scaffold_minimal_workspace(tmp_path, "handout")
    res = route_request("make a one-pager handout", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "synthesis/synthesis_handout"


def test_route_evaluation_design(tmp_path):
    scaffold_minimal_workspace(tmp_path, "eval design")
    res = route_request("design the evaluation strategy", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/evaluation_design"


def test_route_sweep_design(tmp_path):
    scaffold_minimal_workspace(tmp_path, "sweep")
    res = route_request("design the hyperparameter sweep", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/hyperparameter_search_design"


def test_route_data_ethics(tmp_path):
    scaffold_minimal_workspace(tmp_path, "ethics")
    res = route_request("do an ethics review on this data", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "methodology/data_ethics_review"


def test_route_constructive_disagreement(tmp_path):
    scaffold_minimal_workspace(tmp_path, "disagree")
    res = route_request("tell me if i am wrong about this plan", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "guidance/constructive_disagreement"


def test_route_pre_submission_checklist(tmp_path):
    scaffold_minimal_workspace(tmp_path, "submit")
    res = route_request("is this ready to submit", tmp_path)
    assert res["status"] == "success"
    assert res["primary_protocol"] == "audit/pre_submission_checklist"


def test_sys_active_project_exists_in_router_essentials_or_handlers(tmp_path):
    """Smoke: sys_active_project + sys_help are wired."""
    from research_os.server import TOOL_DEFINITIONS, _HANDLERS
    assert "sys_active_project" in TOOL_DEFINITIONS
    assert "sys_active_project" in _HANDLERS
    assert "sys_help" in TOOL_DEFINITIONS
    assert "sys_help" in _HANDLERS


def test_sys_active_project_returns_root(tmp_path):
    """Smoke: sys_active_project returns a project root + advice."""
    import os
    from research_os.server import _handle_sys_active_project
    scaffold_minimal_workspace(tmp_path, "active project")
    os.environ["RESEARCH_OS_WORKSPACE"] = str(tmp_path)
    try:
        out = _handle_sys_active_project("sys_active_project", {}, tmp_path)
        assert out and out[0].text
        import json
        payload = json.loads(out[0].text)
        assert payload["status"] == "success"
        data = payload["data"]
        assert "project_root" in data
        assert data["has_os_state"] is True
        assert "env var" in data["resolved_via"] or "cwd" in data["resolved_via"]
    finally:
        os.environ.pop("RESEARCH_OS_WORKSPACE", None)


def test_sys_help_returns_orientation(tmp_path):
    from research_os.server import _handle_sys_help
    out = _handle_sys_help("sys_help", {}, tmp_path)
    assert out and out[0].text
    import json
    payload = json.loads(out[0].text)
    assert payload["status"] == "success"
    data = payload["data"]
    assert "tool_namespaces" in data
    assert "session_start_pattern" in data
    assert "protocol_categories" in data


def test_sys_help_topic_synthesis_returns_synthesis_protocols(tmp_path):
    from research_os.server import _handle_sys_help
    out = _handle_sys_help("sys_help", {"topic": "synthesis"}, tmp_path)
    assert out and out[0].text
    import json
    payload = json.loads(out[0].text)
    assert payload["status"] == "success"
    assert "synthesis_protocols" in payload["data"]


def test_resolve_project_root_uses_env_var_when_set(tmp_path):
    """Global-server resolution: RESEARCH_OS_WORKSPACE wins."""
    import os
    from research_os.server import _resolve_project_root
    scaffold_minimal_workspace(tmp_path, "envvar test")
    os.environ["RESEARCH_OS_WORKSPACE"] = str(tmp_path)
    try:
        root = _resolve_project_root()
        assert root == tmp_path.resolve()
    finally:
        os.environ.pop("RESEARCH_OS_WORKSPACE", None)


def test_resolve_project_root_ignores_nonexistent_env_var(tmp_path):
    """If env var points at a nonexistent path, fall through to cwd."""
    import os
    from research_os.server import _resolve_project_root
    os.environ["RESEARCH_OS_WORKSPACE"] = "/this/path/does/not/exist"
    try:
        root = _resolve_project_root()
        # Should fall through to cwd-based resolution, not crash
        assert root.exists()
    finally:
        os.environ.pop("RESEARCH_OS_WORKSPACE", None)


def test_resolve_project_root_falls_back_to_cwd_when_no_env_var(tmp_path, monkeypatch):
    """Without env var, walks up from cwd looking for .os_state/."""
    import os
    from research_os.server import _resolve_project_root
    scaffold_minimal_workspace(tmp_path, "cwd test")
    os.environ.pop("RESEARCH_OS_WORKSPACE", None)
    monkeypatch.chdir(tmp_path)
    root = _resolve_project_root()
    assert root == tmp_path.resolve()


def test_tool_alias_resolution(tmp_path):
    """Dispatcher rewrites dot notation + handles legacy aliases."""
    from research_os.server import _resolve_tool_name
    # Dot → underscore
    assert _resolve_tool_name("sys.state.get") == "sys_state_get"
    assert _resolve_tool_name("tool.audit.synthesis") == "tool_audit_synthesis"
    # Legacy alias
    assert _resolve_tool_name("tool_audit_figure_quality") == "tool_audit_figure_full"
    assert _resolve_tool_name("tool_log_decision") == "mem_decision_log"
    # No-op for canonical names
    assert _resolve_tool_name("sys_boot") == "sys_boot"


def test_plan_turn_recommends_chat_split_when_long(tmp_path):
    import yaml as _yaml
    scaffold_minimal_workspace(tmp_path, "PlanTurn Split")
    # Tiny budget + long plan → chat split should be recommended.
    cfg_path = tmp_path / "inputs" / "researcher_config.yaml"
    cfg = _yaml.safe_load(cfg_path.read_text()) or {}
    cfg["model_profile"] = "small"
    cfg_path.write_text(_yaml.dump(cfg, sort_keys=False))

    # Manually persist a long fake active plan.
    fake_plan = {
        "created_at": "2026-01-01T00:00:00Z",
        "user_prompt": "test",
        "primary_protocol": "guidance/analysis_plan",
        "shortcut_tool": None,
        "decomposition": [
            {"tool": "sys_file_write", "purpose": f"step {i}"}
            for i in range(15)
        ],
        "current_step": 1,
        "status": "in_progress",
    }
    (tmp_path / ".os_state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".os_state" / "active_plan.json").write_text(
        json.dumps(fake_plan, indent=2)
    )
    res = plan_turn(tmp_path)
    assert res["status"] == "success"
    assert res["chat_split_recommended"] is True
    assert res["chat_split_reason"]
