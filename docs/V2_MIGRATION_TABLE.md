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

## Reviewer family (4 → 1) — phase-9-c6

The four reviewer-response scaffold tools collapse into a single
`tool_reviewer(operation=simulate|response|rebuttal|compile)` entry
point. `simulate` builds the 7-persona pre-submission brief against
`synthesis/paper.md`; `response` writes the response-to-reviewers
template paired with the latest red-team report; `rebuttal` scaffolds a
single rebuttal markdown with auto-discovered evidence inventory; and
`compile` assembles every rebuttal under `workspace/reviewer/rebuttals/`
into `response_to_reviewers.md` (+ best-effort Typst PDF). Every legacy
name remains callable via `_ALIASES` + `_ALIAS_PARAM_INJECTION`; the
dispatcher forwards to the matching private per-operation worker.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_reviewer_simulate | tool_reviewer | operation | simulate | aliased v2.0.x, removed v2.1.0 |
| tool_response_to_reviewers | tool_reviewer | operation | response | aliased v2.0.x, removed v2.1.0 |
| tool_rebuttal_draft | tool_reviewer | operation | rebuttal | aliased v2.0.x, removed v2.1.0 |
| tool_reviewer_response_compile | tool_reviewer | operation | compile | aliased v2.0.x, removed v2.1.0 |

## Data + figure + thought families (9 → 3) — phase-9-c7

Three small dispatch-style families collapse in one cluster:

* **Data (3 → 1)** — the three per-operation `tool_data_*` tools
  (`sample` returns N rows via head|random|tail, `profile` returns
  schema + dtypes + missingness + descriptive stats, `convert` swaps a
  dataset between CSV / Parquet / Feather / RDS) collapse into a single
  `tool_data(operation=sample|profile|convert)` entry point.
* **Figure (4 → 1)** — the four figure helpers (`palette` returns
  CVD-safe palettes; `caption_synthesise` drafts a plain-English
  `<name>.summary.md` sidecar; `interactive_autogen` writes an
  offline-capable Vega-Lite / vis-network HTML companion next to a
  static figure; `paper_autoembed` walks every step's `outputs/figures/`
  and embeds them into the right `synthesis/paper.md` section) collapse
  into a single `tool_figure(operation=palette|caption_synthesise|interactive_autogen|paper_autoembed)`
  entry point.
* **Thought (2 → 1)** — the two ReAct trace tools (`log` appends one
  trace entry to `workspace/.thoughts/thoughts.jsonl`; `trace` returns
  the recent tail filterable by step / decision) collapse into a single
  `tool_thought(operation=log|trace)` entry point.

Every legacy name remains callable via `_ALIASES` +
`_ALIAS_PARAM_INJECTION`; the dispatcher forwards to the matching
private per-operation worker so existing scripts, protocols, and
researcher commands produce identical output.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_data_sample | tool_data | operation | sample | aliased v2.0.x, removed v2.1.0 |
| tool_data_profile | tool_data | operation | profile | aliased v2.0.x, removed v2.1.0 |
| tool_data_convert | tool_data | operation | convert | aliased v2.0.x, removed v2.1.0 |
| tool_figure_palette | tool_figure | operation | palette | aliased v2.0.x, removed v2.1.0 |
| tool_figure_caption_synthesise | tool_figure | operation | caption_synthesise | aliased v2.0.x, removed v2.1.0 |
| tool_figure_interactive_autogen | tool_figure | operation | interactive_autogen | aliased v2.0.x, removed v2.1.0 |
| tool_paper_figures_autoembed | tool_figure | operation | paper_autoembed | aliased v2.0.x, removed v2.1.0 |
| tool_thought_log | tool_thought | operation | log | aliased v2.0.x, removed v2.1.0 |
| tool_thought_trace | tool_thought | operation | trace | aliased v2.0.x, removed v2.1.0 |

## Misc families: scratch + task (8 → 2) — phase-9-c8

The audit of remaining `tool_<verb>_*` families found two natural
sub-systems still expressed as per-operation surface:

* **Scratch (4 → 1)** — the four scratch-sandbox tools (`write` stages
  a quick-test file under `workspace/scratch/`; `run` executes one with
  language inferred from extension; `list` reports the current files;
  `clear` wipes the sandbox while preserving `.gitignore` and README)
  collapse into a single `tool_scratch(operation=write|run|list|clear)`
  entry point.
* **Task (4 → 1)** — the four background-task tools (`run` spawns a
  real background subprocess and returns a `task_id`; `status` checks
  status + tail of log; `list` enumerates all known background tasks;
  `kill` signal-terminates a running task) collapse into a single
  `tool_task(operation=run|status|list|kill)` entry point.

The two `tool_quick_*` tools (`tool_quick_review` stages a paper-review
markdown; `tool_quick_route` is the throwaway-intent classifier used to
short-circuit protocol load) share a *prefix* only — no functional
overlap — and are NOT consolidated here. They are kept standalone for
the same reason `tool_search_*` was already consolidated per-provider
and a hypothetical `tool_search_anything_else` would not have been
folded in: the rule is "natural family with a shared concept", not
"shared name prefix".

Every legacy name remains callable via `_ALIASES` +
`_ALIAS_PARAM_INJECTION`; the dispatcher forwards to the matching
private per-operation worker so existing scripts, protocols, and
researcher commands produce identical output.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_scratch_write | tool_scratch | operation | write | aliased v2.0.x, removed v2.1.0 |
| tool_scratch_run | tool_scratch | operation | run | aliased v2.0.x, removed v2.1.0 |
| tool_scratch_list | tool_scratch | operation | list | aliased v2.0.x, removed v2.1.0 |
| tool_scratch_clear | tool_scratch | operation | clear | aliased v2.0.x, removed v2.1.0 |
| tool_task_run | tool_task | operation | run | aliased v2.0.x, removed v2.1.0 |
| tool_task_status | tool_task | operation | status | aliased v2.0.x, removed v2.1.0 |
| tool_task_list | tool_task | operation | list | aliased v2.0.x, removed v2.1.0 |
| tool_task_kill | tool_task | operation | kill | aliased v2.0.x, removed v2.1.0 |

## SYS_* families: sys_config + sys_env (5 → 2) — phase-9-c9

C9 was a judgment pass over every `sys_*` family. Most are kept
separate because they are top-of-funnel discovery primitives or
single-purpose tools the AI needs to find by name (`sys_boot`,
`sys_tool_describe`, `sys_help`, `sys_active_tools`, `sys_state_get`,
`sys_protocol_*` (six), `sys_workspace_scaffold` / `sys_workspace_tree`,
`sys_file_*` (five), `sys_checkpoint_*` (three), `sys_session_handoff`,
`sys_export_share_archive`, `sys_notify`, etc.). Hiding any of those
behind an `operation=` dispatcher would force AIs to discover an extra
indirection layer for tools they already invoke fluently — net friction
goes UP, not down. Per the C9 rules: "If consolidation would hide a
primitive the AI needs to find, LEAVE IT."

Two families were genuinely over-fragmented and DO consolidate cleanly:

* **`sys_config` (3 → 1)** — `get` / `set` / `validate` all operate on
  the same `inputs/researcher_config.yaml` file and form the canonical
  read / write / validate trio. Mirrors the proven `sys_path` (3 → 1)
  pattern already shipped.
* **`sys_env` (2 → 1)** — `snapshot` then `docker_generate` are paired
  in every protocol that mentions them ("Use sys_env(operation='docker_generate')
  after sys_env(operation='snapshot')"). Single conceptual surface (the
  environment), two sequential operations.

Other candidate families that were considered and **rejected**:

* **`sys_file_*` (5 tools)** — read / write / list / delete /
  validate_md. File I/O is the highest-frequency MCP surface; every
  filesystem-style MCP server keeps these split. Consolidating fights
  AI muscle memory and increases per-call schema parsing.
* **`sys_workspace_*` (2 tools)** — scaffold is destructive directory
  creation (rare); tree is a high-frequency read-only orientation
  tool. Different intents, no shared semantics.
* **`sys_checkpoint_*` (3 tools)** — the task explicitly carves
  `sys_checkpoint_rollback` out as KEEP-separate; leaving the other
  two as a 2 → 1 dispatcher would create an asymmetric API where
  create/list dispatch but rollback doesn't (worse than status quo).

Every legacy name remains callable via `_ALIASES` +
`_ALIAS_PARAM_INJECTION`; the dispatcher forwards to the existing
private per-operation worker so existing scripts, protocols, and
researcher commands produce identical output.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| sys_config_get | sys_config | operation | get | aliased v2.0.x, removed v2.1.0 |
| sys_config_set | sys_config | operation | set | aliased v2.0.x, removed v2.1.0 |
| sys_config_validate | sys_config | operation | validate | aliased v2.0.x, removed v2.1.0 |
| sys_env_snapshot | sys_env | operation | snapshot | aliased v2.0.x, removed v2.1.0 |
| sys_env_docker_generate | sys_env | operation | docker_generate | aliased v2.0.x, removed v2.1.0 |
