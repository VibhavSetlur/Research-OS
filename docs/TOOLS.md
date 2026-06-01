# Tool Catalog

**140 MCP tools** across three namespaces (`sys_*` / `tool_*` / `mem_*`).
Names use underscores; dot notation (`sys.state.get`) and a small set
of legacy aliases (e.g. `tool_audit_statistical_power` →
`tool_audit_power`) auto-rewrite. `sys_tool_describe(name)` returns the
long-form description of any tool without re-listing the whole catalog.

For most users this is a quick lookup. For *when* to use a tool, see
[PROTOCOLS.md](PROTOCOLS.md) — protocols string tools together to do
real work. For *which* protocol to load, the AI calls `tool_route` and
the router picks one for you.

---

## Routing layer — call these FIRST every session

| Tool | Purpose |
|---|---|
| `sys_boot` | **One call** returns state + config + history + dep inventory + recommended next protocol + pause classification + any active plan. Replaces 4-5 separate calls per session boot. |
| `tool_route` | Hierarchical L1 → L2 → L3 picker. Takes the researcher's raw prompt, returns `primary_protocol`, `shortcut_tool`, `decomposition`, `complexity`, `ask_user`. ~250 tokens out. |
| `tool_plan_turn` | Slices the active plan into a `this_turn` batch + `next_turn` queue sized to the researcher's `model_profile`. Returns `chat_split_recommended` when the plan won't fit in one chat. |
| `tool_plan_advance` | Mark current step done; get next step. Called after every executed step. |
| `tool_plan_clear` | Discard the active plan (researcher pivoted away). |
| `sys_tool_describe` | Return the full description for one tool (cheaper than re-listing every tool). |
| `sys_dep_inventory` | Report which optional dependencies failed to import this session. |

---

## `sys_*` — workspace, state, files, paths, checkpoints

| Tool | Purpose |
|---|---|
| `sys_boot` | (Listed above — call first.) |
| `sys_tool_describe` | (Listed above — full description on demand.) |
| `sys_dep_inventory` | (Listed above — missing-extras report.) |
| `sys_active_tools` | Given a protocol name, returns the tight ~10-15 tool shortlist (essentials + decomposition tools) the AI should prefer while executing it. |
| `tool_workflow_dag` | Build a DAG of numbered steps + data dependencies; write `docs/workflow_dag.mermaid` (+ PNG if `mmdc` present). Auto-refreshed on path create/abandon. |
| `sys_protocol_get` | Load a protocol YAML. Supports `format='summary'` (~300 tokens), `format='step' step_id='<id>'`, or `format='full'`. |
| `sys_protocol_list` | List every protocol + one-line summary. |
| `sys_protocol_next` | Recommend the next protocol from state + on-disk artifacts. |
| `sys_protocol_validate` | Check whether a protocol's expected_outputs exist. |
| `sys_protocol_log` | Record a protocol execution (started / completed / failed / skipped). |
| `sys_protocol_history` | Show recent execution log entries. |
| `sys_state_get` | Full / minimal / markdown state snapshot. (Prefer `sys_boot` at session start.) |
| `sys_workspace_scaffold` | Re-create the directory tree. |
| `sys_workspace_tree` | Structured workspace listing. |
| `sys_file_read` / `_write` / `_list` / `_delete` / `_validate_md` | File I/O. Writes to `inputs/raw_data` + `inputs/literature` blocked. |
| `sys_path_create` | Create the next numbered experiment folder. |
| `sys_path_abandon` | Mark a path as `__DEAD_END` (preserved, never deleted). |
| `sys_path_list` | List numbered experiment paths + status. |
| `sys_checkpoint_create` / `_rollback` / `_list` | Workspace snapshots. |
| `sys_config_get` / `_set` / `_validate` | researcher_config.yaml. (Prefer `sys_boot` at session start.) |
| `sys_notify` | Append to workspace/logs/notifications.log. |
| `sys_session_handoff` | Generate a structured handoff doc + a fresh checkpoint. |
| `sys_env_snapshot` / `_docker_generate` | Capture + containerise the environment. |

---

## `tool_*` — search, exec, audit, synthesis, research, intake, scratch, tasks, repair

### Routing + planning

| Tool | Purpose |
|---|---|
| `tool_route` | Hierarchical L1→L2→L3 protocol picker. |
| `tool_plan_turn` | Per-turn batching sized to model_profile. |
| `tool_plan_advance` | Walk the active plan. |
| `tool_plan_clear` | Discard the active plan. |

### Session continuity

| Tool | Purpose |
|---|---|
| `tool_session_resume` | Reconstruct intent + status from logs after any pause / handoff / new chat. |
| `tool_progress_digest` | One-page summary of experiments / hypotheses / outputs / citations. |
| `tool_dead_end_lessons` | Pull reusable lessons from every `__DEAD_END` folder. |
| `tool_quick_review` | Stage a critical-appraisal skeleton for someone else's paper. |

### Search + literature

| Tool | Purpose |
|---|---|
| `tool_search_semantic_scholar` | Semantic Scholar Graph API. |
| `tool_search_pubmed` | PubMed (NCBI eutils). |
| `tool_search_crossref` | Crossref. |
| `tool_search_arxiv` | arXiv (no key needed). |
| `tool_search_web` | Firecrawl → SerpAPI fallback. |
| `tool_web_scrape` | Scrape a URL to markdown. |
| `tool_literature_download` | Save a paper PDF. Pass `step_id='NN_<slug>'` to scope to a step. |
| `tool_literature_search_and_save` | Search + download top-N PDFs in one shot. |
| `tool_step_literature_list` | List PDFs in one step's literature/ (or across all steps). |
| `tool_cache_clear` | Wipe cached search results (per-provider or older-than-N-days). Cache TTL defaults to 24h (configurable via `runtime.cache_ttl_seconds`). |

### Script execution

| Tool | File types |
|---|---|
| `tool_python_exec` | `.py` |
| `tool_r_exec` | `.R` (requires Rscript on PATH) |
| `tool_julia_exec` | `.jl` (requires julia on PATH) |
| `tool_bash_exec` | `.sh` (returncode-aware) |
| `tool_notebook_exec` | `.ipynb` (jupyter nbconvert --execute --inplace) |
| `tool_rmarkdown_render` | `.Rmd` / `.qmd` (rmarkdown::render OR quarto render) |
| `tool_package_install` | pip install + append to environment/requirements.txt |
| `tool_step_env_lock` | Pin per-step `requirements.txt` + `python_version.txt` (+ optional `conda.yaml` / `Dockerfile`). Use for any step you intend to publish. |

### Long-running background work

| Tool | Purpose |
|---|---|
| `tool_task_run` | Spawn a real subprocess (Popen) and return immediately with a task_id. |
| `tool_task_status` | Check status + tail log; zombie-aware (waitpid + /proc fallback). |
| `tool_task_list` | List every known background task. |
| `tool_task_kill` | SIGTERM (default) or SIGKILL a task. |

### Data

| Tool | Purpose |
|---|---|
| `tool_data_sample` | Head / random / tail sample. |
| `tool_data_profile` | Schema + dtypes + missingness + descriptive stats + suggestions. |
| `tool_data_convert` | CSV ↔ Parquet ↔ Feather ↔ RDS. |
| `tool_intake_autofill` | Read inputs/, infer domain + question + hypotheses, fill researcher_config blanks. |
| `tool_context_intake` | Route mid-flow file drops into the right `inputs/` subfolder. Skips scaffold files. |

### Audit

| Tool | Purpose |
|---|---|
| `tool_audit_synthesis` | Audit a manuscript: claim grounding, citation coverage, causal language. |
| `tool_audit_power` | Post-hoc statistical power. |
| `tool_audit_assumptions` | Normality + homoscedasticity + independence on residuals. |
| `tool_audit_figure` | DPI / colorblind palette / axis labels / error bars. |
| `tool_audit_citations` | Verify every workspace/citations.md entry against Crossref. |
| `tool_audit_reproducibility` | Re-run every script in a clean env and compare hashes. (Slow.) |

### Synthesis

| Tool | Purpose |
|---|---|
| `tool_synthesize_plan` | Inspect available sources; propose section order. |
| `tool_synthesize` | Compile workspace into paper / abstract / poster / dashboard / grant / report. Verified citations only. |
| `tool_latex_compile` | pdflatex + bibtex on synthesis/paper.tex. |
| `tool_poster_create` | Tikzposter LaTeX poster. |
| `tool_dashboard_create` | Single-file offline HTML dashboard. |
| `tool_citations_verify` | Re-verify every citation_key in workspace/citations.md. |

### Research / grounding

| Tool | Purpose |
|---|---|
| `tool_research_method` | 5-10 academic + web sources on a method; structured report. Required BEFORE choosing any method. |
| `tool_research_tool` | Find candidate libraries / CLIs / websites; tagged as installable / api / external / paid. |
| `tool_external_tool_instructions` | Writes a WORKSHEET.md when the chosen tool is external (website / paid / GUI). |
| `tool_plan_step` | Force a complex step into atomic sub-tasks BEFORE coding. |
| `tool_plan_next_step` | Survey state + search + propose 2-3 options for "what should I do next?". |
| `tool_branch_recommendation` | Branch into a new parallel experiment vs extend the current one. |

### Scratch sandbox

| Tool | Purpose |
|---|---|
| `tool_scratch_write` | Write a file into `workspace/scratch/` (gitignored). |
| `tool_scratch_run` | Execute by extension (`.py` / `.R` / `.jl` / `.sh`). |
| `tool_scratch_list` | List scratch files. (Excludes `.gitkeep`.) |
| `tool_scratch_clear` | Wipe scratch contents (keeps README + .gitignore + .gitkeep). |

### Workspace robustness

| Tool | Purpose |
|---|---|
| `tool_workspace_repair` | Detect missing dirs / corrupted state / stale paths and (optionally) heal. NEVER deletes. |

---

## `mem_*` — append-only ledgers

| Tool | Purpose |
|---|---|
| `mem_analysis_log` | Append a chronological narrative entry to workspace/analysis.md. |
| `mem_methods_append` | Append a structured method entry (step / dataset / params / justification / assumptions) to workspace/methods.md. |
| `mem_citations_generate` | Refresh workspace/citations.md from project + per-step literature sidecars. |
| `mem_intake_regenerate` | Regenerate inputs/intake.md with fresh hashes. |
| `mem_decision_log` | Append a structured decision (context / selected / rationale). |
| `mem_hypothesis_add` | Register a new hypothesis (state.active_hypotheses + analysis.md). |
| `mem_hypothesis_update` | Update a hypothesis (status + evidence). |
| `mem_hypothesis_list` | List every tracked hypothesis. |

---

## Token-cost reference

| Pattern | Tokens | When to use |
|---|---|---|
| `sys_boot` | ~800 | EVERY session start. |
| `tool_route(prompt)` | ~250 | Before loading any protocol. |
| `sys_protocol_get format='summary'` | ~300 | To see step headings + quality_bar. |
| `sys_protocol_get format='step' step_id='...'` | ~150-500 | When executing one step. |
| `sys_protocol_get format='full'` | ~1.5-3K | Only when you need every step at once. |
| `sys_tool_describe(name)` | ~200 | Full description for one tool. |
| `tool_synthesize output_type='paper'` | ~2-5K | One-shot — actual paper draft. |

**Default `list_tools` payload is ~1K tokens** (down from ~3K) — each
tool ships its `short` field, full description available on demand.

---

## What's new in 2.0 — quick reference

**Sub-task pipelines** (replaces "one mega-script per step")
* `tool_step_pipeline_define / _run / _status / _diagram` — declare a
  multi-node `pipeline.yaml`; runner topologically orders + content-hash
  caches; emits a per-output `.prov.json` sidecar.

**Provenance + grounding**
* `tool_thought_log` / `tool_thought_trace` — ReAct trace.
* `tool_grounding_register` / `tool_ground_from_context` /
  `tool_grounding_verify` — PROV-O decision-to-evidence binding +
  audit gate.
* `tool_claim_verify` — Chain-of-Verification per claim.
* `tool_lessons_record` / `tool_lessons_consult` — Reflexion-style
  lessons across sessions.

**Visualisation (25 chart kinds)**
* `tool_figure_create kind=<roc|pr|calibration|qq|residual_diagnostics|
  partial_dependence|dot_whisker|ridgeline|raincloud|hexbin|slope|
  posterior|var_importance|funnel|alluvial|hierarchical_heatmap|
  consort_flow|...>` — auto colour-blind palette, ≥300 DPI, dual
  PNG + SVG, four sidecars (caption, summary, prov, optional HTML).
* `tool_figure_caption_synthesise` — plain-English `.summary.md`.
* `tool_audit_figure_full` — strict figure audit (DPI, caption,
  summary, SVG companion, aspect ratio).
* `tool_figure_palette` — Okabe-Ito / viridis / PuOr palettes.

**Quality auditors**
* `tool_audit_quality_full` — runs every gate in one call.
* `tool_audit_code_quality` — ruff + AST complexity + smells.
* `tool_audit_prose` — hedging + vague quantifiers + reporting
  standards.
* `tool_audit_claims` — every paper number traces to outputs.
* `tool_audit_evalue` — VanderWeele E-value sensitivity.
* `tool_audit_step_completeness` — focal figure + sidecars +
  conclusions per step + **BLOCKS** a step whose outputs span
  figures + tables + reports without a `pipeline.yaml`.
* `tool_audit_version_coherence` — flags drift between scripts,
  outputs, and provenance: a v2 figure produced by a v1 script,
  a caption older than its figure, a missing iteration snapshot.

**Iteration versioning** (collective change application)
* `tool_step_iterate(step_id, rationale=…)` — snapshot scripts +
  outputs + caption / summary / prov sidecars + conclusion into
  `.versions/v<n>/` BEFORE editing. Live filenames stay stable so
  cross-step references in conclusions / dashboards don't rot.
* `tool_step_iterations_list(step_id)` — return `iterations.yaml`
  ledger so the AI can show the iteration history before the next
  edit.

**Researcher-authorised overrides** (every bypass is logged)
* `tool_synthesize(override_completeness_gate=true, override_rationale=…)`
* `tool_dashboard_create(override_completeness_gate=true, override_rationale=…)`
* `tool_plan_advance(override_gate=true, override_rationale=…)`

Bypasses append to `workspace/logs/override_log.md`;
`audit/pre_submission_checklist` resurfaces them at publish time.

**Pre-registration, multi-verse, red-team, null findings**
* `tool_preregister_freeze` / `tool_preregister_diff`
* `tool_sensitivity_define` / `tool_sensitivity_run` (specification curve)
* `tool_redteam_review` / `tool_response_to_reviewers`
* `tool_null_findings_report`

**HPC / SLURM**
* `tool_slurm_submit / _status / _fetch / _list`

**Self-tested dashboards (Playwright)**
* `tool_dashboard_test_generate` / `tool_dashboard_test_run`

**Plan creation**
* `tool_plan_step_grounded` — every sub-task has explicit
  Thought / Required-grounding / Action / Verification slots.

---

## Adding a new tool

See [CONTRIBUTING.md § Adding a new tool](../CONTRIBUTING.md). Key
steps:

1. Implement in `src/research_os/tools/actions/<category>/<file>.py`.
2. Add `TOOL_DEFINITIONS` entry in `server.py` with `short` +
   `description` + `category` + `inputSchema`.
3. Add a handler + register in `_HANDLERS`.
4. Add to `_router_index.yaml` (either as a `decomposition` entry in a
   protocol or as a `shortcut_intents` entry).
5. Reference from at least one protocol or shortcut — preflight
   complains about orphans.
6. Add a test in `tests/tools/test_<area>.py`.
