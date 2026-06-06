"""Tool aliases, deprecated-alias telemetry, alias-param injection, removed tools.

Two flavours of alias:
* non-deprecated nickname aliases (old typos / colloquial names) — silent.
* this-release consolidation aliases — flagged in _DEPRECATED_ALIASES;
  hits log to .os_state/deprecations.log so projects can audit usage
  before the next major (when aliases hard-remove).
"""
from __future__ import annotations

from typing import Any


_ALIASES = {
    # Dot notation is handled generically by the dispatcher's dot→underscore
    # rewrite, no need to list here.
    "sys_state_summary": "sys_state_get",
    # Silent nickname mapping directly to mem_log with kind=decision injection.
    "tool_log_decision": "mem_log",
    "view_workspace_tree": "sys_workspace_tree",

    # ── consolidation aliases ─────────────────────────
    # The first-wave consolidation aliases (tool_search_*, tool_plan_*,
    # tool_ground[ing]_*, tool_claim_verify, tool_grounding_verify,
    # tool_lessons_record/consult, sys_path_*, mem_methods_append,
    # mem_decision_log, mem_hypothesis_update, mem_analysis_log) are
    # hard-removed. Callers using those names now get a friendly
    # _REMOVED_TOOLS message naming the canonical entry point.
    # Lessons + failure-memory + dead-end + mistake-replay (8 → 1).
    "tool_failure_record":   "tool_lessons",
    "tool_failure_check":    "tool_lessons",
    "tool_failure_list":     "tool_lessons",
    "tool_dead_end_lessons": "tool_lessons",
    "tool_mistake_replay":   "tool_lessons",
    # Reliability log (2 → 1).
    "tool_reliability_log_event": "tool_reliability",
    "tool_reliability_report":    "tool_reliability",

    # ── audit cluster ───────────────────────────────────
    # Per-step audits.
    "tool_audit_assumptions": "tool_audit",
    "tool_audit_code_quality": "tool_audit",
    "tool_audit_evalue": "tool_audit",
    "tool_audit_figure": "tool_audit",
    "tool_audit_figure_full": "tool_audit",
    "tool_audit_figure_interactivity": "tool_audit",
    "tool_audit_power": "tool_audit",
    "tool_audit_reproducibility": "tool_audit",
    "tool_audit_step_completeness": "tool_audit",
    "tool_audit_step_literature": "tool_audit",
    # Project-wide audits.
    "tool_audit_citations": "tool_audit",
    "tool_audit_claims": "tool_audit",
    "tool_audit_cliches": "tool_audit",
    "tool_audit_coherence": "tool_audit",
    "tool_audit_cross_deliverable_consistency": "tool_audit",
    "tool_audit_prose": "tool_audit",
    "tool_audit_version_coherence": "tool_audit",
    # Synthesis-side audits.
    "tool_audit_synthesis": "tool_audit",
    "tool_audit_dashboard_content": "tool_audit",
    "tool_audit_figure_coverage": "tool_audit",
    "tool_audit_reviewer_responses": "tool_audit",
    # Findings ledger (2 → 1).
    "tool_audit_findings_query": "tool_audit_findings",
    "tool_audit_findings_diff": "tool_audit_findings",
    # Legacy nickname aliases — chain through the consolidated entry point.
    "tool_audit_figure_quality": "tool_audit",
    "tool_audit_statistical_power": "tool_audit",

    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create":            "tool_dashboard",
    "tool_dashboard_story_generate":    "tool_dashboard",
    "tool_dashboard_story_edit":        "tool_dashboard",
    "tool_dashboard_story_quality_bar": "tool_dashboard",
    "tool_dashboard_reviewer_sim":      "tool_dashboard",
    "tool_dashboard_test_generate":     "tool_dashboard",
    "tool_dashboard_test_run":          "tool_dashboard",

    # ── step cluster (8 → 2) ──────────────────────────
    # tool_step_complete stays standalone (top-level end-of-step bundle).
    # tool_step_literature_list lives with the literature/search family
    # and is owned by that cluster — NOT consolidated here.
    "tool_step_iterate":           "tool_step",
    "tool_step_iterations_list":   "tool_step",
    "tool_step_revision_options":  "tool_step",
    "tool_step_env_lock":          "tool_step",
    "tool_step_pipeline_define":   "tool_step_pipeline",
    "tool_step_pipeline_run":      "tool_step_pipeline",
    "tool_step_pipeline_status":   "tool_step_pipeline",
    "tool_step_pipeline_diagram":  "tool_step_pipeline",

    # ── sensitivity cluster (2 → 1) ──────
    "tool_sensitivity_define":     "tool_sensitivity",
    "tool_sensitivity_run":        "tool_sensitivity",
    # ── preregister cluster (2 → 1) ──────
    "tool_preregister_freeze":     "tool_preregister",
    "tool_preregister_diff":       "tool_preregister",
    # ── reviewer cluster (4 → 1) ─────────
    "tool_reviewer_simulate":          "tool_reviewer",
    "tool_response_to_reviewers":      "tool_reviewer",
    "tool_rebuttal_draft":             "tool_reviewer",
    "tool_reviewer_response_compile":  "tool_reviewer",
    # ── data cluster (3 → 1) ─────────────
    "tool_data_sample":                "tool_data",
    "tool_data_profile":               "tool_data",
    "tool_data_convert":               "tool_data",
    # ── figure cluster (4 → 1) ───────────
    "tool_figure_palette":             "tool_figure",
    "tool_figure_caption_synthesise":  "tool_figure",
    "tool_figure_interactive_autogen": "tool_figure",
    "tool_paper_figures_autoembed":    "tool_figure",
    # ── thought cluster (2 → 1) ──────────
    "tool_thought_log":                "tool_thought",
    "tool_thought_trace":              "tool_thought",
    # ── scratch cluster (4 → 1) ──────────
    "tool_scratch_write":              "tool_scratch",
    "tool_scratch_run":                "tool_scratch",
    "tool_scratch_list":               "tool_scratch",
    "tool_scratch_clear":              "tool_scratch",
    # ── task cluster (4 → 1) ─────────────
    "tool_task_run":                   "tool_task",
    "tool_task_status":                "tool_task",
    "tool_task_list":                  "tool_task",
    "tool_task_kill":                  "tool_task",
    # ── sys_config cluster (3 → 1) ──────
    "sys_config_get":                  "sys_config",
    "sys_config_set":                  "sys_config",
    "sys_config_validate":             "sys_config",
    # ── sys_env cluster (2 → 1) ──────────
    "sys_env_snapshot":                "sys_env",
    "sys_env_docker_generate":         "sys_env",
}

# Aliases that should fire deprecation telemetry when invoked. Every name
# here MUST resolve through _ALIASES to a real handler — preflight enforces.
#
# The first-wave consolidation aliases (tool_search_*, tool_plan_*,
# tool_ground[ing]_*, tool_claim_verify, tool_grounding_verify,
# tool_lessons_record/consult, sys_path_*, mem_methods_append,
# mem_decision_log, mem_hypothesis_update, mem_analysis_log) are
# hard-removed and now live in _REMOVED_TOOLS, not here.
_DEPRECATED_ALIASES = {
    # tool_log_decision is a silent nickname that needs param injection to
    # reach the canonical mem_log handler. Listed here so the dispatcher
    # invokes _inject_consolidation_param on every call.
    "tool_log_decision",
    # ── lessons + failure + reliability cluster (10 → 2) ──
    "tool_failure_record",
    "tool_failure_check",
    "tool_failure_list",
    "tool_dead_end_lessons",
    "tool_mistake_replay",
    "tool_reliability_log_event",
    "tool_reliability_report",
    # ── audit cluster ───────────────────────────────────
    "tool_audit_assumptions",
    "tool_audit_code_quality",
    "tool_audit_evalue",
    "tool_audit_figure",
    "tool_audit_figure_full",
    "tool_audit_figure_interactivity",
    "tool_audit_power",
    "tool_audit_reproducibility",
    "tool_audit_step_completeness",
    "tool_audit_step_literature",
    "tool_audit_citations",
    "tool_audit_claims",
    "tool_audit_cliches",
    "tool_audit_coherence",
    "tool_audit_cross_deliverable_consistency",
    "tool_audit_prose",
    "tool_audit_version_coherence",
    "tool_audit_synthesis",
    "tool_audit_dashboard_content",
    "tool_audit_figure_coverage",
    "tool_audit_reviewer_responses",
    "tool_audit_findings_query",
    "tool_audit_findings_diff",
    # Legacy nickname aliases that flow through the consolidated
    # tool_audit dispatcher and need param injection. They map to
    # tool_audit_figure_full / tool_audit_power respectively.
    "tool_audit_figure_quality",
    "tool_audit_statistical_power",
    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create",
    "tool_dashboard_story_generate",
    "tool_dashboard_story_edit",
    "tool_dashboard_story_quality_bar",
    "tool_dashboard_reviewer_sim",
    "tool_dashboard_test_generate",
    "tool_dashboard_test_run",
    # ── step cluster (8 → 2) ──────────────────────────
    "tool_step_iterate",
    "tool_step_iterations_list",
    "tool_step_revision_options",
    "tool_step_env_lock",
    "tool_step_pipeline_define",
    "tool_step_pipeline_run",
    "tool_step_pipeline_status",
    "tool_step_pipeline_diagram",
    # ── sensitivity cluster (2 → 1) ──────
    "tool_sensitivity_define",
    "tool_sensitivity_run",
    # ── preregister cluster (2 → 1) ──────
    "tool_preregister_freeze",
    "tool_preregister_diff",
    # ── reviewer cluster (4 → 1) ─────────
    "tool_reviewer_simulate",
    "tool_response_to_reviewers",
    "tool_rebuttal_draft",
    "tool_reviewer_response_compile",
    # ── data cluster (3 → 1) ─────────────
    "tool_data_sample",
    "tool_data_profile",
    "tool_data_convert",
    # ── figure cluster (4 → 1) ───────────
    "tool_figure_palette",
    "tool_figure_caption_synthesise",
    "tool_figure_interactive_autogen",
    "tool_paper_figures_autoembed",
    # ── thought cluster (2 → 1) ──────────
    "tool_thought_log",
    "tool_thought_trace",
    # ── scratch cluster (4 → 1) ──────────
    "tool_scratch_write",
    "tool_scratch_run",
    "tool_scratch_list",
    "tool_scratch_clear",
    # ── task cluster (4 → 1) ─────────────
    "tool_task_run",
    "tool_task_status",
    "tool_task_list",
    "tool_task_kill",
    # ── sys_config cluster (3 → 1) ──────
    "sys_config_get",
    "sys_config_set",
    "sys_config_validate",
    # ── sys_env cluster (2 → 1) ──────────
    "sys_env_snapshot",
    "sys_env_docker_generate",
}


# Maps legacy alias → kwarg(s) to inject. Lets the consolidated handler
# infer operation/kind/source/mode/scope from the caller's name so an
# old-style `tool_search_pubmed(query=...)` keeps working without the
# caller supplying `source='pubmed'`.
#
# Two value shapes are accepted:
#   * (key, value) tuple — single-kwarg injection (most clusters).
#   * tuple of (key, value) tuples — multi-kwarg injection (audit cluster
#     needs both scope and dimension).
_ALIAS_PARAM_INJECTION: dict[str, Any] = {
    # Silent nickname — chains to mem_log with kind=decision injection.
    "tool_log_decision":            ("kind", "decision"),
    # ── lessons + failure + reliability cluster ──
    "tool_failure_record":          ("operation", "failure_record"),
    "tool_failure_check":           ("operation", "failure_check"),
    "tool_failure_list":            ("operation", "failure_list"),
    "tool_dead_end_lessons":        ("operation", "dead_end"),
    "tool_mistake_replay":          ("operation", "mistake_replay"),
    "tool_reliability_log_event":   ("operation", "log_event"),
    "tool_reliability_report":      ("operation", "report"),
    # ── audit cluster ──
    # Per-step audits.
    "tool_audit_assumptions":             (("scope", "step"), ("dimension", "assumptions")),
    "tool_audit_code_quality":            (("scope", "step"), ("dimension", "code_quality")),
    "tool_audit_evalue":                  (("scope", "step"), ("dimension", "evalue")),
    "tool_audit_figure":                  (("scope", "step"), ("dimension", "figure")),
    "tool_audit_figure_full":             (("scope", "step"), ("dimension", "figure_full")),
    "tool_audit_figure_interactivity":    (("scope", "step"), ("dimension", "figure_interactivity")),
    "tool_audit_power":                   (("scope", "step"), ("dimension", "power")),
    "tool_audit_reproducibility":         (("scope", "step"), ("dimension", "reproducibility")),
    "tool_audit_step_completeness":       (("scope", "step"), ("dimension", "completeness")),
    "tool_audit_step_literature":         (("scope", "step"), ("dimension", "literature")),
    # Project-wide audits.
    "tool_audit_citations":               (("scope", "project"), ("dimension", "citations")),
    "tool_audit_claims":                  (("scope", "project"), ("dimension", "claims")),
    "tool_audit_cliches":                 (("scope", "project"), ("dimension", "cliches")),
    "tool_audit_coherence":               (("scope", "project"), ("dimension", "coherence")),
    "tool_audit_cross_deliverable_consistency": (("scope", "project"), ("dimension", "cross_deliverable")),
    "tool_audit_prose":                   (("scope", "project"), ("dimension", "prose")),
    "tool_audit_version_coherence":       (("scope", "project"), ("dimension", "version_coherence")),
    # Synthesis-side audits.
    "tool_audit_synthesis":               (("scope", "synthesis"), ("dimension", "all")),
    "tool_audit_dashboard_content":       (("scope", "synthesis"), ("dimension", "dashboard_content")),
    "tool_audit_figure_coverage":         (("scope", "synthesis"), ("dimension", "figure_coverage")),
    "tool_audit_reviewer_responses":      (("scope", "synthesis"), ("dimension", "reviewer_responses")),
    # Findings ledger (2 → 1).
    "tool_audit_findings_query":          ("operation", "query"),
    "tool_audit_findings_diff":           ("operation", "diff"),
    # Legacy nickname aliases.
    "tool_audit_figure_quality":          (("scope", "step"), ("dimension", "figure_full")),
    "tool_audit_statistical_power":       (("scope", "step"), ("dimension", "power")),
    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create":              ("operation", "create"),
    "tool_dashboard_story_generate":      ("operation", "story_generate"),
    "tool_dashboard_story_edit":          ("operation", "story_edit"),
    "tool_dashboard_story_quality_bar":   ("operation", "story_quality_bar"),
    "tool_dashboard_reviewer_sim":        ("operation", "reviewer_sim"),
    "tool_dashboard_test_generate":       ("operation", "test_generate"),
    "tool_dashboard_test_run":            ("operation", "test_run"),
    # ── step cluster (8 → 2) ──────────────────────────
    "tool_step_iterate":                  ("operation", "iterate"),
    "tool_step_iterations_list":          ("operation", "iterations_list"),
    "tool_step_revision_options":         ("operation", "revision_options"),
    "tool_step_env_lock":                 ("operation", "env_lock"),
    "tool_step_pipeline_define":          ("operation", "define"),
    "tool_step_pipeline_run":             ("operation", "run"),
    "tool_step_pipeline_status":          ("operation", "status"),
    "tool_step_pipeline_diagram":         ("operation", "diagram"),
    # ── sensitivity cluster (2 → 1) ──────
    "tool_sensitivity_define":            ("operation", "define"),
    "tool_sensitivity_run":               ("operation", "run"),
    # ── preregister cluster (2 → 1) ──────
    "tool_preregister_freeze":            ("operation", "freeze"),
    "tool_preregister_diff":              ("operation", "diff"),
    # ── reviewer cluster (4 → 1) ─────────
    "tool_reviewer_simulate":             ("operation", "simulate"),
    "tool_response_to_reviewers":         ("operation", "response"),
    "tool_rebuttal_draft":                ("operation", "rebuttal"),
    "tool_reviewer_response_compile":     ("operation", "compile"),
    # ── data cluster (3 → 1) ─────────────
    "tool_data_sample":                   ("operation", "sample"),
    "tool_data_profile":                  ("operation", "profile"),
    "tool_data_convert":                  ("operation", "convert"),
    # ── figure cluster (4 → 1) ───────────
    "tool_figure_palette":                ("operation", "palette"),
    "tool_figure_caption_synthesise":     ("operation", "caption_synthesise"),
    "tool_figure_interactive_autogen":    ("operation", "interactive_autogen"),
    "tool_paper_figures_autoembed":       ("operation", "paper_autoembed"),
    # ── thought cluster (2 → 1) ──────────
    "tool_thought_log":                   ("operation", "log"),
    "tool_thought_trace":                 ("operation", "trace"),
    # ── scratch cluster (4 → 1) ──────────
    "tool_scratch_write":                 ("operation", "write"),
    "tool_scratch_run":                   ("operation", "run"),
    "tool_scratch_list":                  ("operation", "list"),
    "tool_scratch_clear":                 ("operation", "clear"),
    # ── task cluster (4 → 1) ─────────────
    "tool_task_run":                      ("operation", "run"),
    "tool_task_status":                   ("operation", "status"),
    "tool_task_list":                     ("operation", "list"),
    "tool_task_kill":                     ("operation", "kill"),
    # ── sys_config cluster (3 → 1) ──────
    "sys_config_get":                     ("operation", "get"),
    "sys_config_set":                     ("operation", "set"),
    "sys_config_validate":                ("operation", "validate"),
    # ── sys_env cluster (2 → 1) ──────────
    "sys_env_snapshot":                   ("operation", "snapshot"),
    "sys_env_docker_generate":            ("operation", "docker_generate"),
}


# Tools removed in earlier releases — friendly error pointing the AI at the new path.
# Old plans, scripts, or third-party callers that still name these get a
# clear message instead of a generic "unknown tool" dead end.
_REMOVED_TOOLS = {
    "tool_figure_create": (
        "tool_figure_create was removed. Research-OS no longer ships "
        "premade chart code — write your own matplotlib / ggplot2 / Altair / "
        "plotnine / Vega-Lite / d3 script tailored to the data. Load the "
        "guidance with sys_protocol_get(protocol_name='visualization/figure_guidelines', "
        "format='summary'); call tool_research_method or tool_search_web first if "
        "you're unsure which plotting library is canonical for this data type. "
        "tool_figure(operation='palette') + tool_audit(scope='step', dimension='figure_full') are unchanged."
    ),
    # First-wave consolidation aliases hard-removed after their
    # deprecation runway expired (see CHANGELOG for the
    # introduction → removal version pair).
    # Search cluster (5 → 1).
    "tool_search_semantic_scholar": (
        "tool_search_semantic_scholar: renamed to tool_search in v1.6.1, removed in v2.0.0; "
        "call tool_search(query='...', source='semantic_scholar') instead."
    ),
    "tool_search_pubmed": (
        "tool_search_pubmed: renamed to tool_search in v1.6.1, removed in v2.0.0; "
        "call tool_search(query='...', source='pubmed') instead."
    ),
    "tool_search_crossref": (
        "tool_search_crossref: renamed to tool_search in v1.6.1, removed in v2.0.0; "
        "call tool_search(query='...', source='crossref') instead."
    ),
    "tool_search_arxiv": (
        "tool_search_arxiv: renamed to tool_search in v1.6.1, removed in v2.0.0; "
        "call tool_search(query='...', source='arxiv') instead."
    ),
    "tool_search_web": (
        "tool_search_web: renamed to tool_search in v1.6.1, removed in v2.0.0; "
        "call tool_search(query='...', source='web') instead."
    ),
    # Plan cluster (3 → 1).
    "tool_plan_turn": (
        "tool_plan_turn: renamed to tool_plan in v1.6.1, removed in v2.0.0; "
        "call tool_plan(operation='turn') instead."
    ),
    "tool_plan_advance": (
        "tool_plan_advance: renamed to tool_plan in v1.6.1, removed in v2.0.0; "
        "call tool_plan(operation='advance') instead."
    ),
    "tool_plan_clear": (
        "tool_plan_clear: renamed to tool_plan in v1.6.1, removed in v2.0.0; "
        "call tool_plan(operation='clear') instead."
    ),
    # Grounding cluster (4 → 2).
    "tool_grounding_register": (
        "tool_grounding_register: renamed to tool_ground in v1.6.1, removed in v2.0.0; "
        "call tool_ground(mode='explicit', ...) instead."
    ),
    "tool_ground_from_context": (
        "tool_ground_from_context: renamed to tool_ground in v1.6.1, removed in v2.0.0; "
        "call tool_ground(mode='from_context', ...) instead."
    ),
    "tool_claim_verify": (
        "tool_claim_verify: renamed to tool_verify in v1.6.1, removed in v2.0.0; "
        "call tool_verify(scope='claim', ...) instead."
    ),
    "tool_grounding_verify": (
        "tool_grounding_verify: renamed to tool_verify in v1.6.1, removed in v2.0.0; "
        "call tool_verify(scope='project', ...) instead."
    ),
    # Lessons cluster (record/consult slice; the rest of the lessons
    # family is still aliased — see CHANGELOG).
    "tool_lessons_record": (
        "tool_lessons_record: renamed to tool_lessons in v1.6.1, removed in v2.0.0; "
        "call tool_lessons(operation='record', ...) instead."
    ),
    "tool_lessons_consult": (
        "tool_lessons_consult: renamed to tool_lessons in v1.6.1, removed in v2.0.0; "
        "call tool_lessons(operation='consult', ...) instead."
    ),
    # Path cluster (3 → 1).
    "sys_path_create": (
        "sys_path_create: renamed to sys_path in v1.6.1, removed in v2.0.0; "
        "call sys_path(operation='create', ...) instead."
    ),
    "sys_path_abandon": (
        "sys_path_abandon: renamed to sys_path in v1.6.1, removed in v2.0.0; "
        "call sys_path(operation='abandon', ...) instead."
    ),
    "sys_path_list": (
        "sys_path_list: renamed to sys_path in v1.6.1, removed in v2.0.0; "
        "call sys_path(operation='list') instead."
    ),
    # Memory cluster (4 → 1).
    "mem_methods_append": (
        "mem_methods_append: renamed to mem_log in v1.6.1, removed in v2.0.0; "
        "call mem_log(kind='methods', method='...') instead."
    ),
    "mem_decision_log": (
        "mem_decision_log: renamed to mem_log in v1.6.1, removed in v2.0.0; "
        "call mem_log(kind='decision', context='...', selected='...', rationale='...') instead."
    ),
    "mem_hypothesis_update": (
        "mem_hypothesis_update: renamed to mem_log in v1.6.1, removed in v2.0.0; "
        "call mem_log(kind='hypothesis', hypothesis_id='...', status='...') instead."
    ),
    "mem_analysis_log": (
        "mem_analysis_log: renamed to mem_log in v1.6.1, removed in v2.0.0; "
        "call mem_log(kind='analysis', entry='...') instead."
    ),
    # Tikzposter LaTeX poster path is hard-removed. tool_poster_create
    # still exists but the engine='latex' branch, create_poster() under
    # synthesis/latex.py, and the layout/audience kwargs are gone.
    # Callers that referenced the old tool name nicknames get a clear
    # migration message.
    "tool_poster_create_latex": (
        "tool_poster_create_latex was never a real tool name. The legacy "
        "tikzposter LaTeX poster path was reachable through tool_poster_create "
        "with engine='latex' (or researcher_config.synthesis.poster_engine='latex'); "
        "it was removed in v2.0.0 (phase-14b). Call tool_poster_create with no "
        "engine kwarg — the Typst renderer is the only supported path."
    ),
    "tool_poster_compile_latex": (
        "tool_poster_compile_latex was never a real tool name. The legacy "
        "tikzposter LaTeX poster path was removed in v2.0.0 (phase-14b). "
        "Call tool_poster_create() — Typst is the only supported renderer."
    ),
}
