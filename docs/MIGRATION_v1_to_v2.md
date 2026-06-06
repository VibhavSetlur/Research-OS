# Migrating from Research-OS v1.x to v2.0.0

Research-OS v2.0.0 is a MAJOR release. The headline shape change is a
**tool surface consolidation (~344 → ~146 live)** plus a flip of
`sys_protocol_get` to default `format="summary"`. Both are breaking
on paper but **every legacy tool name still dispatches via alias for the
v2.0.x runway** — most projects upgrade with zero call-site edits.

This guide is the one-stop-shop for the upgrade. Read the "Upgrade in
5 steps" recipe first, then jump to the per-surface sections you care
about. The companion validation report at
[`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md) measures the
actual upgrade impact across 20 independent agent runs (avg rating
6.35 → 7.70; HIGH-friction items 124 → 63; no regressions).

For the celebratory version of these notes, see
[`docs/V2_RELEASE_NOTES.md`](V2_RELEASE_NOTES.md).

---

## Upgrade in 5 steps

```bash
# 1. Bring the package up to v2.0.0.
pip install --upgrade research-os

# 2. Verify the install + workspace health. Surfaces any deprecation
#    warnings, broken tool refs, or stale config knobs.
research-os doctor

# 3. (Optional but recommended) Re-emit per-IDE MCP config so the new
#    'instructions' field on initialize is picked up by Cursor / Claude
#    Desktop / Windsurf / etc.
research-os ide config-path <your-ide>

# 4. Re-run your last project against the new surface. Every v1 tool
#    name still dispatches via _DEPRECATED_ALIASES with automatic
#    parameter injection — old plans and scripts should run unchanged.
#    Deprecation telemetry lands in .os_state/deprecations.log so you
#    can see which legacy names you still call.

# 5. Before v2.1.0 lands, sweep .os_state/deprecations.log and rename
#    every flagged call site to the v2 canonical name from the
#    migration table below. The aliases will be HARD-removed in v2.1.0.
```

If you wrote your own integration that called Research-OS tools by
name, the only file you need to read end-to-end is the
[Tool migration table](#tool-migration-table) section below.

---

## Breaking changes

### 1. `sys_protocol_get` default `format` is now `"summary"`

This is the single biggest token-cost win identified in the Phase 15a
baseline. Callers that did not pass a `format` argument used to receive
the full YAML body (~1.5-3K tokens per call); they now receive the
~300-token summary view.

**Old (v1.x)**

```yaml
- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop"}
  # returned the full body (~5K tokens)
```

**New (v2.0.0)**

```yaml
- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop"}
  # returns the summary (~500 tokens)

- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop", format: "full"}
  # opt back into the full body explicitly
```

The schema's `inputSchema` declares `"default": "summary"` so
well-behaved clients see the new default automatically. The response
payload still carries a `_load_hint` field guiding the AI to drill in
via `format="step"` or `format="full"` only when needed. Per-turn token
cost is 5-10x cheaper.

### 2. Tool surface consolidated (~344 live → ~146 live)

The Phase 9 audit folded 23 separate `tool_audit_*` per-dimension tools
into a single `tool_audit(scope, dimension)` dispatcher, plus seven
other family collapses (dashboard, step, lessons/reliability,
sensitivity, preregister, reviewer, data/figure/thought,
scratch/task, sys_config/sys_env). Every legacy name remains callable
via `_DEPRECATED_ALIASES` with automatic parameter injection — so
`tool_audit_step_completeness(...)` continues to do exactly what it did
in v1.x.

The deprecated names will be HARD-removed in v2.1.0. Before then,
update call sites to the new canonical names. The full mapping is in
the [Tool migration table](#tool-migration-table) section below.

### 3. Phase 14a — first-wave aliases hard-removed (no alias path)

The 21 legacy tool names introduced as consolidation aliases in
**v1.6.1** have expired their 4-minor-version deprecation runway and
are removed in v2.0.0. Calling any of them now returns a friendly
`_REMOVED_TOOLS` error envelope naming the canonical v2 entry point —
not a generic "unknown tool" error.

| v1.x cluster (removed in v2.0.0) | call this instead |
|---|---|
| `tool_search_semantic_scholar`, `tool_search_pubmed`, `tool_search_crossref`, `tool_search_arxiv`, `tool_search_web` | `tool_search(query=..., source='semantic_scholar'|'pubmed'|'crossref'|'arxiv'|'web')` |
| `tool_plan_turn`, `tool_plan_advance`, `tool_plan_clear` | `tool_plan(operation='turn'|'advance'|'clear')` |
| `tool_grounding_register`, `tool_ground_from_context` | `tool_ground(mode='explicit'|'from_context', ...)` |
| `tool_claim_verify`, `tool_grounding_verify` | `tool_verify(scope='claim'|'project', ...)` |
| `tool_lessons_record`, `tool_lessons_consult` | `tool_lessons(operation='record'|'consult', ...)` (other lessons aliases remain deprecated, not removed) |
| `sys_path_create`, `sys_path_abandon`, `sys_path_list` | `sys_path(operation='create'|'abandon'|'list', ...)` |
| `mem_methods_append`, `mem_decision_log`, `mem_hypothesis_update`, `mem_analysis_log` | `mem_log(kind='methods'|'decision'|'hypothesis'|'analysis', ...)` |

The pre-v1.6.1 silent nickname `tool_log_decision` still works — it
now resolves directly to `mem_log(kind='decision')`.

### 4. Phase 14b — tikzposter LaTeX poster path hard-removed

The legacy `create_poster()` + `_poster_tex_escape()` functions under
`src/research_os/tools/actions/synthesis/latex.py` (387 lines) are
deleted. `tool_poster_create` is unchanged on the surface — the Typst
engine has been the default since v1.11.0 — but the `engine='latex'`
branch now returns a structured error pointing callers at the Typst
surface.

The validator enum on `researcher_config.synthesis.poster_engine` now
rejects `"latex"`. Protocol `synthesis/printable` was updated:
`template: tikzposter` → `academic_36x48` / `academic_48x36` /
`public_24x36` per audience.

Calls to the nicknames `tool_poster_create_latex` /
`tool_poster_compile_latex` (which never were real tools but a
future caller might try) now return `_REMOVED_TOOLS` errors.

---

## Tool migration table

The full old → new mapping below is the canonical reference. Use it
when sweeping your call sites or reading
`.os_state/deprecations.log`. Sourced verbatim from
[`docs/V2_MIGRATION_TABLE.md`](V2_MIGRATION_TABLE.md).

### Audit family (26 → 3) — phase-9-c1

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

### Dashboard family (7 → 1) — phase-9-c2

The seven per-operation `tool_dashboard_*` tools collapse into a single
`tool_dashboard(operation=...)` entry point.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_dashboard_create | tool_dashboard | operation | create | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_generate | tool_dashboard | operation | story_generate | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_edit | tool_dashboard | operation | story_edit | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_story_quality_bar | tool_dashboard | operation | story_quality_bar | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_reviewer_sim | tool_dashboard | operation | reviewer_sim | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_test_generate | tool_dashboard | operation | test_generate | aliased v2.0.x, removed v2.1.0 |
| tool_dashboard_test_run | tool_dashboard | operation | test_run | aliased v2.0.x, removed v2.1.0 |

### Step family (8 → 2) — phase-9-c3

Four step-lifecycle tools collapse into `tool_step(operation=...)`.
Four step sub-task pipeline tools collapse into
`tool_step_pipeline(operation=...)`. `tool_step_complete` stays
standalone as the top-level end-of-step bundle; it composes
`tool_path_finalize` + `tool_audit(scope='step', dimension='completeness')`
+ `tool_audit(scope='step', dimension='literature')` +
`tool_step(operation='revision_options')`. `tool_step_literature_list`
lives with the literature/search family.

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

### Lessons + reliability family (10 → 2) — phase-9-c4

The pre-existing `tool_lessons` dispatcher is extended to cover the
entire "what went wrong / what did we learn" family. The two
reliability-log tools collapse into a separate `tool_reliability`
(kept distinct so log/report semantics stay sharp).

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

### Sensitivity family (2 → 1) — phase-9-c5

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_sensitivity_define | tool_sensitivity | operation | define | aliased v2.0.x, removed v2.1.0 |
| tool_sensitivity_run | tool_sensitivity | operation | run | aliased v2.0.x, removed v2.1.0 |

### Preregister family (2 → 1) — phase-9-c5

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_preregister_freeze | tool_preregister | operation | freeze | aliased v2.0.x, removed v2.1.0 |
| tool_preregister_diff | tool_preregister | operation | diff | aliased v2.0.x, removed v2.1.0 |

### Reviewer family (4 → 1) — phase-9-c6

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_reviewer_simulate | tool_reviewer | operation | simulate | aliased v2.0.x, removed v2.1.0 |
| tool_response_to_reviewers | tool_reviewer | operation | response | aliased v2.0.x, removed v2.1.0 |
| tool_rebuttal_draft | tool_reviewer | operation | rebuttal | aliased v2.0.x, removed v2.1.0 |
| tool_reviewer_response_compile | tool_reviewer | operation | compile | aliased v2.0.x, removed v2.1.0 |

### Data + figure + thought families (9 → 3) — phase-9-c7

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

### Misc families: scratch + task (8 → 2) — phase-9-c8

The two `tool_quick_*` tools (`tool_quick_review`, `tool_quick_route`)
share a prefix only and are NOT consolidated.

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

### SYS_* families: sys_config + sys_env (5 → 2) — phase-9-c9

Phase-9-c9 was a judgment pass over every `sys_*` family. Most are
intentionally kept separate — each is a distinct primitive AIs need to
find by name (`sys_boot`, `sys_active_tools`, `sys_protocol_*` ×6,
`sys_help`, `sys_tool_describe`, `sys_state_get`, `sys_file_*` ×5,
`sys_checkpoint_*` ×3, `sys_workspace_scaffold`/`_tree`, etc.). Hiding
any of those behind an `operation=` dispatcher forces AIs to discover
an extra indirection layer and net friction goes UP.

Two families were genuinely over-fragmented and consolidate cleanly:

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| sys_config_get | sys_config | operation | get | aliased v2.0.x, removed v2.1.0 |
| sys_config_set | sys_config | operation | set | aliased v2.0.x, removed v2.1.0 |
| sys_config_validate | sys_config | operation | validate | aliased v2.0.x, removed v2.1.0 |
| sys_env_snapshot | sys_env | operation | snapshot | aliased v2.0.x, removed v2.1.0 |
| sys_env_docker_generate | sys_env | operation | docker_generate | aliased v2.0.x, removed v2.1.0 |

### Phase 14a — first-wave consolidation aliases hard-removed in v2.0.0

These 21 names were introduced as aliases in v1.6.1, deprecated for 4
minor versions, and are now **fully removed** (not aliased). Calling
any of them returns a `_REMOVED_TOOLS` error envelope.

| old_name | new_name | dispatch_kwarg | value | status |
|---|---|---|---|---|
| tool_search_semantic_scholar | tool_search | source | semantic_scholar | removed v2.0.0 |
| tool_search_pubmed | tool_search | source | pubmed | removed v2.0.0 |
| tool_search_crossref | tool_search | source | crossref | removed v2.0.0 |
| tool_search_arxiv | tool_search | source | arxiv | removed v2.0.0 |
| tool_search_web | tool_search | source | web | removed v2.0.0 |
| tool_plan_turn | tool_plan | operation | turn | removed v2.0.0 |
| tool_plan_advance | tool_plan | operation | advance | removed v2.0.0 |
| tool_plan_clear | tool_plan | operation | clear | removed v2.0.0 |
| tool_grounding_register | tool_ground | mode | explicit | removed v2.0.0 |
| tool_ground_from_context | tool_ground | mode | from_context | removed v2.0.0 |
| tool_claim_verify | tool_verify | scope | claim | removed v2.0.0 |
| tool_grounding_verify | tool_verify | scope | project | removed v2.0.0 |
| tool_lessons_record | tool_lessons | operation | record | removed v2.0.0 |
| tool_lessons_consult | tool_lessons | operation | consult | removed v2.0.0 |
| sys_path_create | sys_path | operation | create | removed v2.0.0 |
| sys_path_abandon | sys_path | operation | abandon | removed v2.0.0 |
| sys_path_list | sys_path | operation | list | removed v2.0.0 |
| mem_methods_append | mem_log | kind | methods | removed v2.0.0 |
| mem_decision_log | mem_log | kind | decision | removed v2.0.0 |
| mem_hypothesis_update | mem_log | kind | hypothesis | removed v2.0.0 |
| mem_analysis_log | mem_log | kind | analysis | removed v2.0.0 |

---

## Per-pack notes

The five bundled domain packs (humanities, qualitative, theory_math,
wet_lab, engineering) ship 36 protocols total across their `protocols/`
directories. Per-pack call-site impact in v2.0.0 is small — the
consolidation work was concentrated in core tool names, and pack
authors generally call canonical core tools rather than maintaining
pack-specific tools that overlap. Pack-completeness is tracked in
[`docs/V2_PACK_COMPLETENESS_MATRIX.md`](V2_PACK_COMPLETENESS_MATRIX.md).

### humanities (8 protocols)

* **No required call-site edits.** All shipped humanities protocol
  YAMLs already reference the canonical consolidated names where
  applicable; the AUDIT-047 sweep in v1.11.0 cleaned out 21 deprecated
  alias names across 75 protocol YAMLs.
* **Affected publishing surfaces** (per pack-completeness matrix): the
  `dashboard_story`, `slides`, `poster`, `reviewer_scaffold`, and
  `drafter_loop` subsystems still treat humanities projects with a
  STEM-shaped lens. These are not breaking changes — they were already
  the v1.11.0 behaviour — but if your project depended on humanities
  output (an essay-shaped paper.md, monograph ISBN verifiers,
  apparatus-aware completeness rules), the v2.0.0 venue templates
  `humanities_essay.typ` and `chicago_thesis.typ` are unchanged and
  the `humanities_essay_structure` protocol still drives the
  six-section interpretive shape.
* **Deferred to v2.1.0:** humanities reviewer personas
  (philologist / literary_critic / intellectual_historian /
  manuscript_editor), `humanities_talk_20min` slide template, and
  pack-aware `drafter_loop` persona checks. See
  [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md) §4.

### qualitative (5 protocols)

* **One file flagged for cleanup, no behaviour change.**
  `src/research_os_qualitative/protocols/coding/coding_scheme_iteration.yaml`
  line 67 still references the deprecated alias name
  `tool_audit_step_completeness` in protocol DESCRIPTION prose. The
  call works (the dispatcher rewrites via `_DEPRECATED_ALIASES`) but
  the canonical form is
  `tool_audit(scope='step', dimension='completeness')`. Not a
  blocker for v2.0.0 — covered by the existing deprecation runway
  and slated for v2.0.1 cleanup along with similar drift in core
  audit recommendation strings.
* **Affected publishing surfaces:** 7 of 8 pack-completeness cells
  are STEM-shaped (paper_pdf, dashboard_story, slides, poster,
  reviewer_scaffold, drafter_loop, literature_gate). Same caveat as
  humanities — not breaking, but a qualitative project still gets
  generic IMRaD-shaped papers/posters/slides unless the v2.1.0
  pack-aware deliverable work lands.
* **Deferred to v2.1.0:** `tool_qualitative_pii_redact` as a
  first-class MCP tool (currently a `scripts/qual_pii_redact.py`
  workaround) and `tool_qualitative_quotes_bulk_register`.

### theory_math (8 protocols)

* **No required call-site edits.** All theory_math protocols reference
  the canonical core tools.
* **Known protocol naming drift (v2.0.1 fix):**
  `proof_verification_workflow.yaml` line 137 references
  `tool_theory_lean_check` / `tool_theory_coq_check`, but the
  registered names are `tool_theory_math_lean_check` /
  `tool_theory_math_coq_check`. Add aliases OR edit the protocol —
  tracked in [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md)
  §4 as a v2.0.1 patch item. Will not block v2.0.0.
* **`IMPORTED_AS_CITED` literature verdict landed in v1.9.4** as a
  first-class verdict for theorem-import work. Theory papers no longer
  hit the literature gate's empirical-shaped verdict enum.
* **Deferred to v3.0.0:** rename
  `tool_theory_math_{lean,coq,dep_graph}_*` →
  `tool_theory_{lean,coq,dep_graph}_*` (drop redundant `math` infix).
  This would be MAJOR-breaking; v2.0.0 keeps the full name.

### wet_lab (8 protocols)

* **No required call-site edits.** All wet_lab protocols reference
  canonical core tools. The AUDIT-047 sweep already migrated this
  pack from 21 deprecated aliases in v1.11.0.
* **Largest content gap in v2.0.0:** the pack ships **zero**
  sequencing-acquisition / DE / scRNA-seq protocols. A bio_omics pack
  (`methodology/rnaseq_de.yaml`, `methodology/scrnaseq_qc.yaml`,
  `methodology/geo_sra_ingest.yaml`,
  `synthesis/methods_section_bioinformatics.yaml`) is **slated for
  v2.1.0** along with explicit trigger phrases (GEO, GSE, SRA, fastq,
  DESeq2, edgeR, limma, voom, scanpy, Seurat, Bioconductor, salmon,
  kallisto, STAR, HISAT2, cellranger). A bio project on v2.0.0 will
  route through the generic methodology/quantitative_methods protocol
  and the AI is expected to write the DE-specific scaffolding by hand.

### engineering (7 protocols)

* **No required call-site edits.** All engineering protocols
  reference canonical core tools.
* **Largest content gap in v2.0.0:** no dedicated
  `engineering/test/algorithmic_benchmark` protocol. Today,
  engineering-benchmark work is routed through
  `methodology/method_comparison` step 10 of 11 as an addendum (added
  in v1.9.4 via F-010). A first-class `algorithmic_benchmark` protocol
  + `tool_engineering_benchmark_sweep` is **slated for v2.1.0**.
* **Pack-completeness gaps:** the dashboard_story / slides / poster /
  reviewer_scaffold / drafter_loop subsystems are IMRAD-shaped; an
  engineering project's paper.md sections (Background → Requirements
  → Design → V&V → Validation → Conclusions) reach the PDF correctly
  via `pack_paper_sections('engineering')`, but the downstream
  deliverables fall back to generic templates. Not breaking —
  pre-existing v1.11.0 behaviour.

---

## Config field changes

Phase 14d removed five `researcher_config.yaml` fields that the v1.9.2
Lens-7 audit identified as declared-but-never-read. None of these
fields had any consumer in `src/`, `tests/`, or shipped protocols —
the comments that claimed they were "Read by
`methodology/pick_tool_stack`" were inaccurate. The
`pick_tool_stack` protocol picks language + library purely from method
+ field-practice + literature signal; it never consulted these fields.

**Existing projects on prior versions that hand-set these keys are
unaffected.** The keys silently become unknown extras;
`validate_config` does not enforce key membership and will not raise.
If you want a clean config, delete the fields manually.

### Removed in v2.0.0

| field | block | reason |
|---|---|---|
| `runtime.default_n_for_sampling` | `runtime` | No caller anywhere. `tool_data(operation='sample')` takes its `n` argument from the tool call, not from config. |
| `tool_stack.preferred_languages` | `tool_stack` (entire block removed) | Never read. `methodology/pick_tool_stack` picks based on method + literature signal + env compatibility. |
| `tool_stack.allow_mixed_language_steps` | `tool_stack` | Never read. Same as above. |
| `tool_stack.field_practice_overrides_preference` | `tool_stack` | Never read. Same as above. |
| `tool_stack.cite_field_practice_when_choosing` | `tool_stack` | Never read. Same as above. |

### Added in v2.0.0

| field | default | purpose |
|---|---|---|
| `synthesis.drafter_loop_enabled` | `true` | Toggle the new draft → adversarial review → rewrite loop for paper/slides/poster. |
| `synthesis.drafter_loop_max_iterations` | `3` | Cap loop iterations to bound token cost. |
| `synthesis.drafter_loop_quality_threshold` | `0.10` | Exit early when iteration-over-iteration quality delta drops below this floor. |

(These three knobs were already shipped in v1.11.0's
`synthesis:` block but are listed here for completeness — Phase 14d's
config sweep also surfaced their declarative role.)

---

## New surface in v2.0.0 (additive — won't break)

The following landed in v2.0.0 alongside the consolidation work. None
of these change existing behaviour; they're available to call but
optional.

* `research-os doctor` — 18+ install + workspace health checks. Exit
  policy: 0=all-pass, 1=warn-only, 2=fail.
* `research-os ide config-path <name>` — print MCP config path for one
  IDE (Cursor, Claude Desktop, Windsurf, etc.).
* `tool_audit(scope, dimension, ...)` — unified per-dimension audit
  dispatcher (replaces 23 per-dimension tools via alias).
* `tool_audit_findings(operation=query|diff, ...)` — query the
  cross-audit ledger at `.audit_findings.jsonl` with severity /
  dimension / step / since filters.
* `tool_protocols_list`, `tool_tools_list` — flat AI-friendly
  discovery lists.
* `tool_dashboard`, `tool_step`, `tool_step_pipeline`, `tool_lessons`,
  `tool_reliability`, `tool_sensitivity`, `tool_preregister`,
  `tool_reviewer`, `tool_data`, `tool_figure`, `tool_thought`,
  `tool_scratch`, `tool_task`, `sys_config`, `sys_env` — consolidated
  family dispatchers (operation kwarg).
* `tool_route` output gains `recommended_action` (a literal next-call
  string), `tier`, `tier_transition`, and `why_matched` (the
  Semantic-similarity rationale used to pick the primary protocol).
* `sys_boot` consolidates 4-5 startup calls into one envelope
  (state + config + history + dep inventory + next protocol +
  freshness + pause_classification + active_plan).
* `sys_active_tools(protocol_name=...)` returns a 13-18-tool scoped
  shortlist per protocol (down from the full 146 visible). The
  naive-AI working surface shrinks ~10x per turn.
* MCP `instructions` field on initialize — names the boot sequence
  (`sys_boot → tool_route → sys_protocol_get(format=summary) →
  sys_active_tools`) so a fresh client sees the ritual instead of
  discovering it. **Pre-v2 IDEs will not see this field** — it is
  attached to the server's `Server(instructions=...)` constructor at
  initialize handshake time. Older clients silently ignore it.
* Every tool definition now carries `status: live|alias|deprecated`
  and `pack: core|<pack_name>` introspection fields. `sys_tool_describe`
  surfaces both.
* Every shipped protocol YAML (153 files across core + 5 packs)
  carries a `scope_tags` block — `domain` (e.g. `[biology, wet_lab]`),
  `audience` (e.g. `[researcher]`), and `workflow_shape` (e.g.
  `[experiment_pipeline]`). The router uses these as a soft filter.
* Per-protocol `tier:` annotation, supporting protocol-graph routing.
* `tool_synthesize` BLOCKED error now names the exact override flag
  (e.g. `override_unresolved_blocks` + required
  `override_rationale='<one-line why>'`).
* `tool_audit_quality_full` returns structured per-component verdicts:
  `components: {step_completeness, code_quality, prose_quality, claims,
  preregistration_diff, grounding}` each with
  `{status, blockers, advice}`.
* Audit findings ledger (`.audit_findings.jsonl`) populated by
  audit_master with structured rows (`id`, `severity`, `dimension`,
  `suggested_fix`, `evidence_paths`, `ro_version`, `generated_at`).
  Stable UUIDv5 ids.

---

## Validation

Phase 15b measured the upgrade impact via the same 20-agent
multi-perspective harness that produced the v1.11.0 baseline. Headline
numbers in [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md):

| metric | v1.11.0 baseline | v2.0.0 candidate | delta |
|---|---|---|---|
| Mean `final_rating` | 6.35 | 7.70 | **+1.35 (+21%)** |
| Total HIGH-friction items | 124 | 63 | **-49%** |
| First-5-turn HIGH-friction | 66 | 42 | **-36%** |
| Every-deliverable-produced runs | 11/20 | 14/20 | +3 |
| Regressions | — | 0 | none |

Every cell of the 4-perspective × 5-scenario matrix moved up by +0.7
to +1.9 points. The v3-grade release-gate targets in the Phase 15 plan
(avg ≥ 9.5; HIGH ≤ 5; first-5-turn HIGH = 0) are **not met** — the
recommendation is YELLOW: ship v2.0.0 with the documented caveat that
the deeper structural gaps (domain-pack coverage for bioinformatics +
systems benchmarks; envelope/dispatcher bugs; pack-aware audit gates)
carry over into the v2.0.x patch series and v2.1.0 minor.

For the full deferred-work backlog (v2.0.1 patch / v2.1.0 minor /
v3.0.0 major buckets), see
[`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md) §4.

---

## See also

* [`docs/V2_RELEASE_NOTES.md`](V2_RELEASE_NOTES.md) — celebratory
  version of these notes, with the 5 CRAFT-inspired additions and the
  full 4×5 perspective × scenario rating matrix.
* [`docs/V2_MIGRATION_TABLE.md`](V2_MIGRATION_TABLE.md) — canonical
  migration table source (this guide copies it for one-stop-shop
  reading).
* [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md) — full
  Phase 15b re-validation report with per-scenario breakdowns and
  deferred-work backlog.
* [`docs/V2_PACK_COMPLETENESS_MATRIX.md`](V2_PACK_COMPLETENESS_MATRIX.md)
  — per-pack × per-subsystem completeness verdicts.
* [`docs/CONTRACT.md`](CONTRACT.md) — the stable-surface promise; the
  things Research-OS is committed to MAJOR-bumping on change.
* [`CHANGELOG.md`](../CHANGELOG.md) — full per-version change log.
