# Research-OS v2 — Migration Table

Tracks every legacy tool name that has been folded into a consolidated v2
entry point. Old names continue to work via `_ALIASES`; callers see the
expected behaviour because `_ALIAS_PARAM_INJECTION` sets the dispatch
kwarg(s) automatically. Each row records the version this alias was
introduced (status `aliased v2.0.x`) and the version it will be removed
in (status `removed v2.1.0`).

## Audit family (26 → 3)  — phase-9-c1

The 23 per-dimension `tool_audit_*` tools collapse into `tool_audit`
(dispatched by `scope` + `dimension`). The 2 ledger tools collapse into
`tool_audit_findings` (dispatched by `operation`). `tool_audit_quality_full`
stays as the canonical aggregator.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_audit_assumptions | tool_audit | scope, dimension | step, assumptions | aliased v2.0.x, removed v2.1.0 |
| tool_audit_citations | tool_audit | scope, dimension | project, citations | aliased v2.0.x, removed v2.1.0 |
| tool_audit_claims | tool_audit | scope, dimension | project, claims | aliased v2.0.x, removed v2.1.0 |
| tool_audit_cliches | tool_audit | scope, dimension | project, cliches | aliased v2.0.x, removed v2.1.0 |
| tool_audit_code_quality | tool_audit | scope, dimension | step, code_quality | aliased v2.0.x, removed v2.1.0 |
| tool_audit_coherence | tool_audit | scope, dimension | project, coherence | aliased v2.0.x, removed v2.1.0 |
| tool_audit_cross_deliverable_consistency | tool_audit | scope, dimension | project, cross_deliverable | aliased v2.0.x, removed v2.1.0 |
| tool_audit_dashboard_content | tool_audit | scope, dimension | synthesis, dashboard_content | aliased v2.0.x, removed v2.1.0 |
| tool_audit_evalue | tool_audit | scope, dimension | step, evalue | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure | tool_audit | scope, dimension | step, figure | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_coverage | tool_audit | scope, dimension | synthesis, figure_coverage | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_full | tool_audit | scope, dimension | step, figure_full | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_interactivity | tool_audit | scope, dimension | step, figure_interactivity | aliased v2.0.x, removed v2.1.0 |
| tool_audit_figure_quality | tool_audit | scope, dimension | step, figure_full | aliased v2.0.x, removed v2.1.0 |
| tool_audit_power | tool_audit | scope, dimension | step, power | aliased v2.0.x, removed v2.1.0 |
| tool_audit_prose | tool_audit | scope, dimension | project, prose | aliased v2.0.x, removed v2.1.0 |
| tool_audit_reproducibility | tool_audit | scope, dimension | step, reproducibility | aliased v2.0.x, removed v2.1.0 |
| tool_audit_reviewer_responses | tool_audit | scope, dimension | synthesis, reviewer_responses | aliased v2.0.x, removed v2.1.0 |
| tool_audit_statistical_power | tool_audit | scope, dimension | step, power | aliased v2.0.x, removed v2.1.0 |
| tool_audit_step_completeness | tool_audit | scope, dimension | step, completeness | aliased v2.0.x, removed v2.1.0 |
| tool_audit_step_literature | tool_audit | scope, dimension | step, literature | aliased v2.0.x, removed v2.1.0 |
| tool_audit_synthesis | tool_audit | scope, dimension | synthesis, all | aliased v2.0.x, removed v2.1.0 |
| tool_audit_version_coherence | tool_audit | scope, dimension | project, version_coherence | aliased v2.0.x, removed v2.1.0 |
| tool_audit_findings_query | tool_audit_findings | operation | query | aliased v2.0.x, removed v2.1.0 |
| tool_audit_findings_diff | tool_audit_findings | operation | diff | aliased v2.0.x, removed v2.1.0 |

## Dashboard family (7 → 1)  — phase-9-c2

The seven per-operation `tool_dashboard_*` tools collapse into a single
`tool_dashboard(operation=...)` entry point. Every legacy name remains
callable via `_ALIASES` + `_ALIAS_PARAM_INJECTION`; the dispatcher
forwards to the matching private per-operation worker.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_dashboard_create | tool_dashboard | operation | create | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_generate | tool_dashboard | operation | story_generate | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_edit | tool_dashboard | operation | story_edit | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_quality_bar | tool_dashboard | operation | story_quality_bar | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_reviewer_sim | tool_dashboard | operation | reviewer_sim | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_test_generate | tool_dashboard | operation | test_generate | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_test_run | tool_dashboard | operation | test_run | aliased v2.0.x, removed v2.1.0 |

## Step family (8 → 2)  — phase-9-c3

The four step-lifecycle tools (`tool_step_iterate`,
`tool_step_iterations_list`, `tool_step_revision_options`,
`tool_step_env_lock`) collapse into `tool_step(operation=...)`. The four
step sub-task pipeline tools (`tool_step_pipeline_define`,
`tool_step_pipeline_run`, `tool_step_pipeline_status`,
`tool_step_pipeline_diagram`) collapse into
`tool_step_pipeline(operation=...)`. Every legacy name remains callable
via `_ALIASES` + `_ALIAS_PARAM_INJECTION`; the dispatchers forward to
the matching private per-operation worker. `tool_step_complete` stays
standalone as the top-level end-of-step bundle (it composes
`tool_path_finalize` + `tool_audit(scope='step', dimension='completeness')`
+ `tool_audit(scope='step', dimension='literature')` +
`tool_step(operation='revision_options')`). `tool_step_literature_list`
lives with the literature/search family and is owned by that cluster
(not consolidated here).

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_step_iterate | tool_step | operation | iterate | aliased v2.0.x, removed v2.1.0 |
| tool_step_iterations_list | tool_step | operation | iterations_list | aliased v2.0.x, removed v2.1.0 |
| tool_step_revision_options | tool_step | operation | revision_options | aliased v2.0.x, removed v2.1.0 |
| tool_step_env_lock | tool_step | operation | env_lock | aliased v2.0.x, removed v2.1.0 |
| tool_step_pipeline_define | tool_step_pipeline | operation | define | aliased v2.0.x, removed v2.1.0 |
| tool_step_pipeline_run | tool_step_pipeline | operation | run | aliased v2.0.x, removed v2.1.0 |
| tool_step_pipeline_status | tool_step_pipeline | operation | status | aliased v2.0.x, removed v2.1.0 |
| tool_step_pipeline_diagram | tool_step_pipeline | operation | diagram | aliased v2.0.x, removed v2.1.0 |

## Lessons + reliability family (10 → 2) — phase-9-c4

The pre-existing `tool_lessons` dispatcher (which already absorbed
`tool_lessons_record` + `tool_lessons_consult` in v1.x) is extended to
cover the entire "what went wrong / what did we learn" family. The
three paywall/permanent-error tools (`tool_failure_record`,
`tool_failure_check`, `tool_failure_list`), the dead-end summariser
(`tool_dead_end_lessons`), and the coaching-mode pattern surface
(`tool_mistake_replay`) all collapse into
`tool_lessons(operation=…)`. The two reliability-log tools
(`tool_reliability_log_event`, `tool_reliability_report`) collapse into
a separate `tool_reliability(operation=log_event|report)` entry point
(kept separate so log/report semantics stay sharply distinct from the
lessons-store). Every legacy name remains callable via `_ALIASES` +
`_ALIAS_PARAM_INJECTION`.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_lessons_record | tool_lessons | operation | record | aliased v2.0.x, removed v2.1.0 |
| tool_lessons_consult | tool_lessons | operation | consult | aliased v2.0.x, removed v2.1.0 |
| tool_failure_record | tool_lessons | operation | failure_record | aliased v2.0.x, removed v2.1.0 |
| tool_failure_check | tool_lessons | operation | failure_check | aliased v2.0.x, removed v2.1.0 |
| tool_failure_list | tool_lessons | operation | failure_list | aliased v2.0.x, removed v2.1.0 |
| tool_dead_end_lessons | tool_lessons | operation | dead_end | aliased v2.0.x, removed v2.1.0 |
| tool_mistake_replay | tool_lessons | operation | mistake_replay | aliased v2.0.x, removed v2.1.0 |
| tool_reliability_log_event | tool_reliability | operation | log_event | aliased v2.0.x, removed v2.1.0 |
| tool_reliability_report | tool_reliability | operation | report | aliased v2.0.x, removed v2.1.0 |

## Sensitivity family (2 → 1) — phase-9-c5

The two per-operation `tool_sensitivity_*` tools (`define` authors the
multiverse / specification-curve grid; `run` executes the Cartesian
product and renders the Steegen-style spec curve) collapse into a single
`tool_sensitivity(operation=define|run)` entry point. Every legacy name
remains callable via `_ALIASES` + `_ALIAS_PARAM_INJECTION`; the
dispatcher forwards to the matching private per-operation worker.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_sensitivity_define | tool_sensitivity | operation | define | aliased v2.0.x, removed v2.1.0 |
| tool_sensitivity_run | tool_sensitivity | operation | run | aliased v2.0.x, removed v2.1.0 |

## Preregister family (2 → 1) — phase-9-c5

The two per-operation `tool_preregister_*` tools (`freeze` snapshots the
SAP + hypotheses BEFORE data analysis, content-hashed; `diff` compares
the frozen SAP against the current state at synthesis time) collapse
into a single `tool_preregister(operation=freeze|diff)` entry point.
Every legacy name remains callable via `_ALIASES` +
`_ALIAS_PARAM_INJECTION`; the dispatcher forwards to the matching
private per-operation worker.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_preregister_freeze | tool_preregister | operation | freeze | aliased v2.0.x, removed v2.1.0 |
| tool_preregister_diff | tool_preregister | operation | diff | aliased v2.0.x, removed v2.1.0 |
