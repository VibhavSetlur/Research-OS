# Tool Catalog

**Live MCP tools** across three namespaces (`sys_*` / `tool_*` /
`mem_*`). Every legacy v1.x name still dispatches via `_ALIASES` +
`_ALIAS_PARAM_INJECTION` through the v2.0.x patch line. Deprecated
aliases (dispatch-but-flag) and hard-removed names (return a friendly
`_REMOVED_TOOLS` error naming the v2 entry point) round out the
back-compat surface. See `CHANGELOG.md [2.0.0]` for the full
old → new table. For live counts call `tool_tools_list`.

For *when* to use a tool, see [PROTOCOLS.md](PROTOCOLS.md) — protocols
string tools together to do real work. For *which* protocol to load,
the AI calls `tool_route` and the router picks one for you. At
runtime, the canonical introspection path is `sys_tool_describe(name)`
+ `sys_active_tools(protocol_name)` — both are cheaper than re-reading
this doc.

Every tool definition carries two metadata fields:

* `status` — `live` (visible in `list_tools`), `alias` (back-compat
  pointer), or `deprecated` (callable, telemetry to
  `.os_state/deprecations.log`). `list_tools` returns `status='live'`
  only.
* `pack` — `core` or one of `humanities`, `qualitative`,
  `theory_math`, `wet_lab`, `engineering`, `slurm`, `snakemake`,
  `nextflow`, `cytoscape`, `redcap`, `synapse`.

---

## Discovery + introspection (call these FIRST)

| Tool | Purpose |
|---|---|
| `sys_boot` | **Always your first call.** One envelope returns state + config + history + dep inventory + recommended next protocol + pause classification + active plan. Replaces 4-5 separate v1 calls per session boot. |
| `tool_route` | Hierarchical L1 → L2 → L3 + semantic picker. Returns `primary_protocol`, `recommended_action` (literal next-call string), `why_matched` (similarity score + matched triggers + tier), `tier`, `alternatives`, `decomposition`, `complexity`, `ask_user`, `shortcut_tool`. ~250 tokens. **Call after every researcher message.** |
| `sys_protocol_get` | Load a protocol. Defaults to `format='summary'` (~300 tokens; v2 change). Other formats: `step` (one step body), `lean` (small-model), `dryrun` (preview), `full` (entire YAML, 1.5-3K tokens). Response includes `_load_hint` guiding the AI to drill in. |
| `sys_active_tools` | Given a protocol name, returns the 13-18-tool scoped shortlist the AI should prefer while executing it. Shrinks the working surface ~10× per turn. |
| `sys_tool_describe` | Full description + schema + `status` + `pack` for one tool. Cheaper than re-listing every tool. |
| `tool_protocols_list` | **v2.0 new.** Flat protocol catalogue with structured metadata (name, category, pack, intent_class, tier, version, short description). Filter by `category`, `pack`, `intent_class`, or `tier`. The discovery counterpart of `sys_protocol_list`. |
| `tool_tools_list` | **v2.0 new.** Flat MCP tool catalogue with `scope` (core or pack), summary, required input fields, deprecation status, alias target. Filter by `scope`, `include_deprecated`, etc. |
| `sys_help` | Topic-based AI orientation. Topics: `routing`, `iteration`, `overrides`, `recovery`, `fields`, `depth`, plus any protocol category. |
| `sys_dep_inventory` | Which optional extras failed to import this session. |
| `sys_packs_installed` | List installed protocol packs (name, version, tool count, router entries, errors). |
| `sys_adapters_installed` | List installed infrastructure adapters (SLURM / Snakemake / Nextflow / Cytoscape / REDCap / Synapse / external). |
| `sys_active_project` | Resolved project root for THIS request + how it was resolved (env var / cwd walk / fallback). |
| `sys_semantic_tool_search` | Find tools by what they do — semantic search over tool descriptions. |
| `tool_semantic_route` | Direct semantic search over protocol embeddings. Returns top-k candidates with scores. |
| `tool_quick_route` | Throwaway / sanity-check / exploratory intent classifier — short-circuits protocol load. |
| `tool_dry_run` | Preview a protocol's tool-call sequence without executing (supervised review). |
| `tool_deprecations_summary` | Aggregate counts from `.os_state/deprecations.log` — which deprecated aliases this project still hits. |

---

## Catalogue, alphabetical by canonical name

Every live tool is below, alphabetised within namespace. Aliases (old
v1.x names that still dispatch) are listed as **cross-references**
under the new canonical tool. Hard-removed names (return
`_REMOVED_TOOLS` friendly errors) are noted in
`CHANGELOG.md [2.0.0]`, not here.

### `mem_*` — append-only ledgers

| Tool | Purpose |
|---|---|
| `mem_citations_generate` | Refresh `workspace/citations.md` from project + per-step literature sidecars. |
| `mem_hypothesis_add` | Register a new hypothesis (state.active_hypotheses + analysis.md). |
| `mem_hypothesis_list` | List every tracked hypothesis. |
| `mem_intake_regenerate` | Regenerate `inputs/intake.md` with fresh content hashes. |
| `mem_log` | **Unified memory append.** `kind='methods'\|'decision'\|'hypothesis'\|'analysis'`. Aliases: `mem_methods_append`, `mem_decision_log`, `mem_hypothesis_update`, `mem_analysis_log` (all hard-removed in v2.0.0 — call `mem_log` with the matching `kind`). The nickname `tool_log_decision` still works and resolves to `mem_log(kind='decision')`. |

### `sys_*` — system, workspace, state, files, paths, checkpoints

| Tool | Purpose |
|---|---|
| `sys_active_project` | Listed above (Discovery). |
| `sys_active_tools` | Listed above (Discovery). |
| `sys_adapters_installed` | Listed above (Discovery). |
| `sys_boot` | Listed above (Discovery). |
| `sys_checkpoint_create` | Workspace snapshot (hardlinked, fast). |
| `sys_checkpoint_list` | List checkpoints with descriptions + timestamps. |
| `sys_checkpoint_rollback` | Restore the workspace to a checkpoint. Files created after the checkpoint are removed (except large ref-only data extensions the snapshot skips) so it is a true restore-to, not an overlay; the current state is backed up to a pre-rollback checkpoint first and is recoverable. |
| `sys_config` | **Unified config dispatcher.** `operation='get'\|'set'\|'validate'\|'note'`. Aliases: `sys_config_get`, `sys_config_set`, `sys_config_validate` (still callable). Operates on `inputs/researcher_config.yaml`. `operation='note'` appends a learned researcher preference / correction to `interaction.agent_notes` (the learn-the-user loop — append-only, idempotent; surfaced at every boot). |
| `sys_dep_inventory` | Listed above (Discovery). |
| `sys_env` | **Unified environment dispatcher.** `operation='snapshot'\|'docker_generate'`. Aliases: `sys_env_snapshot`, `sys_env_docker_generate` (still callable). Capture + containerise the env. |
| `sys_export_ro_crate` | Emit `ro-crate-metadata.json` + `codemeta.json` at project root. FAIR-aligned discoverability for downstream tools (Zenodo, OSF). |
| `sys_export_share_archive` | Build a share-safe zip of the project (excludes AI-internal files). Bundles `ro-crate-metadata.json` + `codemeta.json` + `CITATION.cff` at archive root. |
| `sys_file_delete` | Delete a workspace file or empty directory. |
| `sys_file_list` | List files in a workspace directory (recursive). |
| `sys_file_read` | Read a project file. |
| `sys_file_validate_md` | Validate a markdown file against the headings/sections a writing protocol expects. |
| `sys_file_write` | Write a file. Refuses writes under `inputs/raw_data/` or `inputs/literature/` (immutable). `force=true` to overwrite under `synthesis/`. |
| `sys_help` | Listed above (Discovery). |
| `sys_notify` | Append to `workspace/logs/notifications.log`. |
| `sys_packs_installed` | Listed above (Discovery). |
| `sys_path` | **Unified path-lifecycle dispatcher.** `operation='create'\|'abandon'\|'list'`. Hard-removed aliases: `sys_path_create`, `sys_path_abandon`, `sys_path_list` — call `sys_path` with the matching `operation`. `create` adds the next numbered experiment folder; `abandon` marks a path `__DEAD_END` (never deleted); `list` lists paths + status. |
| `sys_protocol_get` | Listed above (Discovery). |
| `sys_protocol_history` | Show recent execution log entries. |
| `sys_protocol_list` | List every protocol + one-line summary. |
| `sys_protocol_log` | Record a protocol execution (`started`/`completed`/`failed`/`skipped`). |
| `sys_protocol_next` | Recommend the next protocol from state + on-disk artifacts. |
| `sys_protocol_validate` | Check whether a protocol's `expected_outputs` exist. |
| `sys_semantic_tool_search` | Listed above (Discovery). |
| `sys_session_handoff` | Generate a structured handoff doc + a fresh checkpoint. |
| `sys_state_get` | Full / minimal / markdown state snapshot. (Prefer `sys_boot` at session start.) |
| `sys_tool_describe` | Listed above (Discovery). |
| `sys_where` | ~30-token mid-session "where am I?" snapshot (root, tier, plan position, blocks, last protocol). Cheaper than `sys_boot`. |
| `sys_daemon` | Discover a running Research-OS daemon for this project and return its live telemetry (jobs, freshness, recommended next action) — the same continuity an HTTP agent gets from `/v1/orient`, inside MCP. Read-only; degrades cleanly when no daemon is running. |
| `sys_consent` | Request or check researcher consent for a daemon-gated action when a floor gate returns `consent_required`. Bridges the MCP session to the daemon's consent authority over localhost (request a one-shot, argument-bound token; check pending/granted; fetch a minted token to retry). The agent cannot self-grant — only an authorized human mints. Degrades to `available=false` when no daemon is enforcing. |
| `sys_workspace_scaffold` | Re-create the directory tree. |
| `sys_workspace_tree` | Structured workspace listing. |

### `tool_*` — research workflow

#### Consolidated v2 entry points (the names to learn)

The Phase 9 audit folded ~120 per-operation tools into ~14 dispatchers.
Every legacy name continues to dispatch through the v2.0.x runway via
`_ALIASES` + `_ALIAS_PARAM_INJECTION`; hard removal is scheduled for
v2.1.0. Aliases marked **(removed)** below have already been
hard-removed in v2.0.0 (Phase 14a) — they return a friendly
`_REMOVED_TOOLS` error naming the canonical entry point.

| v2 entry point | Dispatch by | Operations | v1.x aliases (callable unless **removed**) |
|---|---|---|---|
| `tool_audit` | `scope` + `dimension` | step/project/synthesis × completeness, code_quality, prose, claims, citations, coherence, cross_deliverable, dashboard_content, evalue, figure, figure_coverage, figure_full, figure_interactivity, power, reproducibility, reviewer_responses, step_literature, version_coherence, cliches, all | `tool_audit_assumptions`, `tool_audit_citations`, `tool_audit_claims`, `tool_audit_cliches`, `tool_audit_code_quality`, `tool_audit_coherence`, `tool_audit_cross_deliverable_consistency`, `tool_audit_dashboard_content`, `tool_audit_evalue`, `tool_audit_figure`, `tool_audit_figure_coverage`, `tool_audit_figure_full`, `tool_audit_figure_interactivity`, `tool_audit_figure_quality`, `tool_audit_power`, `tool_audit_prose`, `tool_audit_reproducibility`, `tool_audit_reviewer_responses`, `tool_audit_statistical_power`, `tool_audit_step_completeness`, `tool_audit_step_literature`, `tool_audit_synthesis`, `tool_audit_version_coherence` |
| `tool_audit_findings` | `operation` | `query` (filter the ledger), `diff` (compare two snapshots by stable id), `explain` (full chronological history + untruncated suggested_fix for one id — call after a synthesize BLOCK; the BLOCK envelope's `next_recommended_call` points at it) | `tool_audit_findings_query`, `tool_audit_findings_diff` |
| `tool_audit_quality_full` | — (aggregator) | (standalone) — runs every gate in one call and returns structured per-component verdicts | — |
| `tool_build` | `operation` | `build`, `test`, `lint` — shells the per-operation command declared in `researcher_config.yaml#workspace.commands.{build,test,lint}` with cwd = the `tool_build` inner repo. The build-mode counterpart of `tool_scratch`. | — |
| `tool_git` | `operation` | `init`, `status`, `commit`, `branch`, `tag`, `log`, `diff` — provenance-aware git hard-scoped to the `tool_build` inner project repo (`workspace.inner_repo`, default `project`). | — |
| `tool_data` | `operation` | `sample`, `profile`, `convert` (CSV ↔ Parquet ↔ Feather ↔ RDS) | `tool_data_sample`, `tool_data_profile`, `tool_data_convert` |
| `tool_ground` | `mode` | `explicit` (register a decision↔evidence binding), `from_context` (extract bindings from a step's conclusions) | **removed**: `tool_grounding_register`, `tool_ground_from_context` |
| `tool_lessons` | `operation` | `record`, `consult` (cross-session lesson store), `failure_record`, `failure_check`, `failure_list` (URL/DOI paywall / 404 memory), `dead_end` (dead-end summariser), `mistake_replay` (recurring-pattern coaching) | `tool_dead_end_lessons`, `tool_failure_record`, `tool_failure_check`, `tool_failure_list`, `tool_mistake_replay`; **removed**: `tool_lessons_record`, `tool_lessons_consult` |
| `tool_plan` | `operation` | `turn` (slice the active plan into `this_turn` + `next_turn`, sized to `model_profile`), `advance` (mark current step done), `clear` (discard the active plan) | **removed**: `tool_plan_turn`, `tool_plan_advance`, `tool_plan_clear` |
| `tool_preregister` | `operation` | `freeze` (snapshot SAP + hypotheses content-hashed BEFORE data), `diff` (compare frozen SAP vs current at synthesis) | `tool_preregister_freeze`, `tool_preregister_diff` |
| `tool_reliability` | `operation` | `log_event` (structural event → `reliability.jsonl`), `report` (redacted markdown summary) | `tool_reliability_log_event`, `tool_reliability_report` |
| `tool_reviewer` | `operation` | `response` (response-to-reviewers template + red-team), `rebuttal` (single rebuttal markdown + evidence inventory), `compile` (assemble every rebuttal under `workspace/reviewer/rebuttals/`) | `tool_response_to_reviewers`, `tool_rebuttal_draft`, `tool_reviewer_response_compile` |
| `tool_scratch` | `operation` | `write`, `run` (by extension), `list`, `clear` (workspace sandbox, gitignored) | `tool_scratch_write`, `tool_scratch_run`, `tool_scratch_list`, `tool_scratch_clear` |
| `tool_search` | `source` | `semantic_scholar`, `pubmed`, `crossref`, `arxiv`, `web` (Firecrawl → SerpAPI fallback), `auto` | **removed**: `tool_search_semantic_scholar`, `tool_search_pubmed`, `tool_search_crossref`, `tool_search_arxiv`, `tool_search_web` |
| `tool_sensitivity` | `operation` | `define` (multiverse / specification-curve grid), `run` (execute the Cartesian product + render the Steegen spec curve) | `tool_sensitivity_define`, `tool_sensitivity_run` |
| `tool_step` | `operation` | `iterate` (snapshot scripts + outputs + sidecars into `.versions/v<n>/` before edit), `iterations_list` (return `iterations.yaml`), `revision_options` (post-finalize pause-and-revise heuristic), `env_lock` (per-step `requirements.txt` + `python_version.txt` + optional `conda.yaml` / `Dockerfile`) | `tool_step_iterate`, `tool_step_iterations_list`, `tool_step_revision_options`, `tool_step_env_lock` |
| `tool_step_pipeline` | `operation` | `define`, `run` (content-hash-cached topological execution), `status` (per-node staleness report), `diagram` (Mermaid + optional PNG of the sub-task DAG) | `tool_step_pipeline_define`, `tool_step_pipeline_run`, `tool_step_pipeline_status`, `tool_step_pipeline_diagram` |
| `tool_task` | `operation` | `run` (spawn real subprocess via `subprocess.Popen`, returns `task_id`), `status` (check + tail log; zombie-aware), `list`, `kill` (SIGTERM default, SIGKILL on demand) | `tool_task_run`, `tool_task_status`, `tool_task_list`, `tool_task_kill` |
| `tool_thought` | `operation` | `log` (append a ReAct trace entry to `workspace/.thoughts/thoughts.jsonl`), `trace` (recent tail filterable by step / decision) | `tool_thought_log`, `tool_thought_trace` |
| `tool_verify` | `scope` | `claim` (Chain-of-Verification per claim), `project` (verify all grounded claims) | **removed**: `tool_claim_verify`, `tool_grounding_verify` |

#### Standalone `tool_*` (alphabetical)

| Tool | Purpose |
|---|---|
| `tool_adapter_extract` | Run one adapter's `extract()` + write provenance YAML to `workspace/<step>/provenance/<adapter>.yaml`. |
| `tool_adapters_list` | List adapters + detection status on the current project. |
| `tool_adapters_run_all` | Run every detected adapter's `extract()`; write per-adapter provenance YAMLs. |
| `tool_alternative_path_propose` | Confidence-gated scan: literature on the chosen method AND alternatives, framed for the specific data shape. |
| `tool_bash_exec` | Run `.sh`. Returncode-aware. |
| `tool_branch_recommendation` | Decide whether to branch into a new parallel path vs extend the current one. |
| `tool_cache_clear` | Wipe cached search results (per-provider or older-than-N-days). TTL default 24h (`runtime.cache_ttl_seconds`). |
| `tool_citations_verify` | Re-verify every `citation_key` in `workspace/citations.md`. |
| `tool_context_intake` | Route a mid-flow file drop into the right `inputs/` subfolder. Skips scaffold files. |
| `tool_cytoscape_export_static` | (adapter: `cytoscape`) Render a static PNG / SVG snapshot of one or every network embedded in a `.cys` archive. |
| `tool_deliverable_chooser` | "I'm done, what now?" — inspects project readiness (steps with conclusions, figures, citations) + `researcher_config.yaml#research_goal.output_types` and recommends which deliverable(s) to build (asks if none declared). Surfaces always-available interim artifacts (e.g. step reports) without forcing them. |
| `tool_deprecations_summary` | Listed above (Discovery). |
| `tool_discussion_coverage_audit` | BLOCK gate: every non-AGREES literature verdict must have a Discussion paragraph. |
| `tool_dry_run` | Listed above (Discovery). |
| `tool_engineering_fault_tree_render` | (pack: `engineering`) Render a fault tree as Mermaid + optional SVG. |
| `tool_engineering_fmea_render` | (pack: `engineering`) Render FMEA (Failure Mode & Effects Analysis) from YAML to CSV + Markdown (+ optional `.xlsx`). Computes RPN = severity × occurrence × detection. |
| `tool_engineering_requirements_matrix` | (pack: `engineering`) Bidirectional requirements ↔ design elements ↔ test cases ↔ test results matrix. |
| `tool_explain` | Plain-language tutor for any concept / method / topic. Returns a grounded, LAYERED explanation scaffold (intuition → mechanics → caveats), tuned to an optional `depth` — not a memorised answer. |
| `tool_external_tool_instructions` | Writes a `WORKSHEET.md` when the chosen tool is external (website / paid / GUI). |
| `tool_finalize_project` | Server-enforced ship gate. `operation='check'\|'finalize'` — the ONE gate that can actually REFUSE "done": aggregates BLOCK-severity findings (unresolved audit blockers, unverified citations, missing provenance) across the whole project. Every other gate is advisory. |
| `tool_humanities_archive_lookup` | (pack: `humanities`) Query digital archives (Internet Archive / HathiTrust / DPLA / Europeana / Gallica / Library of Congress). |
| `tool_humanities_citation_chain` | (pack: `humanities`) Chain-of-custody for a quotation: original ms → critical edition → translation → secondary citation. |
| `tool_humanities_transcribe` | (pack: `humanities`) Scaffold OCR + manual-correction for an archival image. Side-by-side transcription template. |
| `tool_intake_autofill` | Read `inputs/`, infer domain + question + hypotheses, write `inputs/intake.md` + `research_overview.md` (in the project's `docs/`) + `.os_state/state.json`. |
| `tool_intake_freshness` | Recommended intake depth (full / refresh-only / skip) based on intake.md freshness + step count. |
| `tool_julia_exec` | Run `.jl` (requires `julia` on PATH). |
| `tool_latex_compile` | `pdflatex` + `bibtex` on `synthesis/paper.tex`. Use when a venue requires `.tex` submission. |
| `tool_list_certifications` | List active researcher self-certifications. |
| `tool_literature_download` | Save a paper PDF. Pass `step_id='NN_<slug>'` to scope to a step. |
| `tool_literature_search_and_save` | Search + download top-N PDFs in one shot. |
| `tool_nextflow_validate` | (adapter: `nextflow`) `nextflow run <main.nf> --help`. Surfaces parse / config / DSL syntax issues. |
| `tool_notebook_exec` | Run `.ipynb` (`jupyter nbconvert --execute --inplace`). |
| `tool_null_findings_report` | Assemble a publishable companion document for findings that DIDN'T pan out (anti-file-drawer). |
| `tool_package_install` | `pip install` + append to per-step `environment/requirements.txt`. |
| `tool_typst_compile` | Generic Typst compiler. Renders any AI-authored `.typ` source (`synthesis/paper.typ`, `slides.typ`, `poster.typ`, `essay.typ`, `cover_letter.typ`, `response.typ`) to PDF. Auto-generates `synthesis/biblio.yml` from `workspace/citations.md` when missing; materialises bundled venue templates into `_typst_templates/` next to the source. Returns `pdf_path`, `page_count`, `citation_count`, `typst_warnings`, `typst_errors`. |
| `tool_path_finalize` | Seal a numbered experiment path. Runs the per-step literature loop check before sealing. |
| `tool_plan_next_step` | Survey state + search + propose 2-3 options for "what should I do next?". |
| `tool_plan_step` | Force a complex step into atomic sub-tasks BEFORE coding. |
| `tool_plan_step_grounded` | Every sub-task ships with Thought / Required-grounding / Action / Verification slots. |
| `tool_figure_palette` | Returns a colour-blind-safe palette (Okabe-Ito qualitative / viridis sequential / PuOr diverging / accent). Read-only; for the AI's plotting scripts. |
| `tool_progress_digest` | One-page summary of experiments / hypotheses / outputs / citations. |
| `tool_project_tier_strictness` | Map `researcher_config.project_tier` (throwaway/sketch/production) → default `gate_strictness`. |
| `tool_promote_to_step` | Retroactively wrap a scratch result in proper provenance (new numbered step + sidecar + summary). |
| `tool_protocols_list` | Listed above (Discovery). |
| `tool_python_exec` | Run `.py`. |
| `tool_qualitative_codebook_diff` | (pack: `qualitative`) Diff two versions of a qualitative codebook + optional per-code Cohen's κ from two rounds of applied coding. |
| `tool_qualitative_quote_provenance` | (pack: `qualitative`) Register a participant quote in `workspace/quotes/registry.jsonl` (participant_id, transcript path, line range, optional timestamp). |
| `tool_qualitative_select_standard` | (pack: `qualitative`) Select the reporting standard (COREQ / SRQR; `auto` picks COREQ for interview/focus-group studies, SRQR otherwise). |
| `tool_quick_review` | Stage a critical-appraisal skeleton for someone else's paper. |
| `tool_quick_route` | Listed above (Discovery). |
| `tool_r_exec` | Run `.R` (requires `Rscript` on PATH). |
| `tool_redcap_schema_describe` | (adapter: `redcap`) Render the detected REDCap schema (events, instruments, fields, PHI warnings) as Markdown into `workspace/<step>/data/redcap_schema.md`. |
| `tool_redteam_review` | Adversarial review of a deliverable BEFORE peer review. `focus='manuscript'\|'proof'\|'figure'\|'methods'`. |
| `tool_research_method` | 5-10 academic + web sources on a method; structured report. **Required BEFORE choosing any method.** |
| `tool_research_tool` | Find candidate libraries / CLIs / websites; tagged installable / api / external / paid. |
| `tool_resolve_gate_strictness` | Resolve effective gate strictness (light / normal / strict) from config + trust_score. |
| `tool_rigor_signals_scan` | Score project rigor 0-100 from methods.md, citations, git, preregistration, scripts, prior step summaries. |
| `tool_rmarkdown_render` | Run `.Rmd` / `.qmd` (`rmarkdown::render` or `quarto render`). |
| `tool_route` | Listed above (Discovery). |
| `tool_synthesis_check` | Quality audit for AI-authored synthesis files (`paper.typ` / `slides.typ` / `poster.typ` / `essay.typ` / `dashboard.html`). Auto-detects file type. Modes: `all` (default), `substantiveness` (per-IMRAD content depth), `structure` (sections + references), `accessibility` (alt-text, semantic HTML), `cliches`. For paper / essay: abstract >=1 number + method + conclusion verb; intro >=3 citations + pivot; methods covers >=80% of workspace steps; results has stats + figure refs; discussion has limitations + future-work + verdict coverage; refs sync. For slides: slide_count >=4, speaker notes present, <=12 citations. For poster: section_count >=3, <=8 citations. For dashboard: offline (no `http:` scripts), every `<img>` has alt, no placeholders / path leaks. |
| `tool_synthesis_scaffold` | Writes a `<=80`-line skeleton synthesis file (paper.typ / slides.typ / poster.typ / essay.typ / dashboard.html) with section headers + `// AI: author this` markers. Refuses to overwrite an existing file unless `overwrite=true`. |
| `tool_self_certify` | Persist a researcher self-certification (domain + scope + rationale). |
| `tool_semantic_route` | Listed above (Discovery). |
| `tool_session_resume` | Reconstruct intent + status from logs after any pause / handoff / new chat. |
| `tool_synthesize_plan` | Inspect workspace + return what's ready to draft (per-section source paths + gaps). Read-only; call before authoring synthesis files. |
| `tool_skills` | Self-improving skill registry. `operation='distill'\|'promote'\|'list'` — clusters this project's recorded lessons (`workspace/.lessons/lessons.jsonl`) by tag and crystallizes recurring patterns into reusable, Hermes-compatible `SKILL.md` cards. The self-improving loop on top of `tool_lessons`. |
| `tool_slurm_estimate_cost` | (adapter: `slurm`) Estimate compute cost from `#SBATCH walltime + nodes × $/node-hour`. |
| `tool_slurm_fetch` | (adapter: `slurm`) Block until a SLURM job finishes; return stdout / stderr paths. |
| `tool_slurm_job_status` | (adapter: `slurm`) Query Slurm (`squeue --json`) or PBS (`qstat -f`) for a job's status. |
| `tool_slurm_list` | (adapter: `slurm`) List every SLURM job submitted from this project. |
| `tool_slurm_status` | (adapter: `slurm`) Live status via `squeue` + finished status via `sacct` for one or all project jobs. |
| `tool_slurm_submit` | (adapter: `slurm`) Submit a `sbatch` script; return `job_id`. |
| `tool_snakemake_dag_render` | (adapter: `snakemake`) Render the workflow DAG to PNG via `snakemake --dag \| dot -Tpng`. Falls back to regex-derived Mermaid. |
| `tool_snakemake_dryrun` | (adapter: `snakemake`) `snakemake --dry-run -s <snakefile>`; status=warning with install hint if missing. |
| `tool_state_freshness_check` | Detect stale workspace state (state.json > 30d, citations older than newest PDF, orphan provenance). |
| `tool_step_complete` | One-call gate for "this step is done." Runs per-step completeness + literature + quality pieces and `tool_path_finalize` if every gate passes. Functionally an alias-superset of `tool_path_finalize` for callers who want a single entrypoint. |
| `tool_step_literature_list` | List PDFs in one step's `literature/` (or across all steps). |
| `tool_synapse_entity_info` | (adapter: `synapse`) Opt-in live query of a Synapse entity's metadata via `synapseclient` using the project's `.synapseConfig`. |
| `tool_synthesis_curate_figures` | Collect each step's focal figure into `synthesis/figures/` with stable ordered names (`fig01_<slug>.png`, …). |
| `tool_synthesis_preview` | Cheap deterministic dry-run before authoring — predicts word counts, page count, figures, citations, gaps. `mode='diff'` compares against the existing deliverable on disk. |
| `tool_synthesize_plan` | Inspect available sources; propose section order. |
| `tool_theory_math_coq_check` | (pack: `theory_math`) `coqc` on a `.v` file with structured error parsing. Install-hint when Coq is missing. |
| `tool_theory_math_dep_graph` | (pack: `theory_math`) Parse every `.lean` and `.v` under `source_dir`; write Mermaid + JSON dependency graph. |
| `tool_theory_math_lean_check` | (pack: `theory_math`) `lean --make` on a `.lean` file with structured error parsing. |
| `tool_tools_list` | Listed above (Discovery). |
| `tool_web_scrape` | Scrape a URL to markdown. |
| `tool_wet_lab_plate_map_render` | (pack: `wet_lab`) Render a 96- or 384-well plate layout as PNG / SVG from a YAML spec. |
| `tool_wet_lab_checksum_raw` | (pack: `wet_lab`) Compute the SHA-256 + size of a raw instrument output file (never trust an operator-typed checksum) and, given `run_log_path`, append the `{path, sha256, size_bytes}` entry to that run log. Streams the file for large sequencer/imaging output. |
| `tool_wet_lab_reagent_query` | (pack: `wet_lab`) Structured query plan + write-into-`reagents.yaml` stub for one reagent. |
| `tool_wet_lab_run_log_init` | (pack: `wet_lab`) Stub a structured instrument run-log YAML for an instrument family at `workspace/<step>/runs/<family>_<run_label>.yaml`. Pre-fills the family-appropriate parameter fields + capture timestamp with TODO placeholders. |
| `tool_wet_lab_sample_lineage_export` | (pack: `wet_lab`) Render the parent → split → aliquot → readout tree as JSON + Mermaid. |
| `tool_workflow_dag` | Build a DAG of numbered steps + data dependencies; write `docs/workflow_dag.mermaid` (+ PNG if `mmdc` present). Auto-refreshed on path create/abandon. |
| `tool_workspace_repair` | Detect missing dirs / corrupted state / stale paths and (optionally) heal. NEVER deletes. |
| `tool_writing_discussion_from_verdicts` | Append one Discussion paragraph per non-AGREES verdict in any step's `findings_vs_literature.md`. |

---

## Token-cost reference

| Pattern | Tokens | When to use |
|---|---|---|
| `sys_boot` | ~800 | EVERY session start. |
| `tool_route(prompt)` | ~250 | Before loading any protocol. |
| `sys_protocol_get format='summary'` (v2 default) | ~300 | To see step headings + quality_bar. |
| `sys_protocol_get format='step' step_id='...'` | ~150-500 | When executing one step. |
| `sys_protocol_get format='full'` | ~1.5-3K | Only when you need every step at once. |
| `sys_tool_describe(name)` | ~200 | Full description for one tool. |
| `tool_synthesis_check(file='synthesis/paper.typ')` | ~1-3K | Audit an AI-authored synthesis file before compiling. |

**Default `list_tools` payload is ~1K tokens** (vs ~3K pre-consolidation)
— each tool ships its `short` field, full description on demand via
`sys_tool_describe`.

---

## What's new in v2.0.0 — quick reference

**Tool surface consolidation** (~344 v1.x names → ~150 v2 live)

* Audit family 26 → 3 (`tool_audit`, `tool_audit_findings`,
  `tool_audit_quality_full`).
* Dashboard 7 → 1, Search 7 → 1, Figure 4 → 1, Reviewer 4 → 1, Step
  lifecycle 4 → 1, Step pipeline 4 → 1, Scratch 4 → 1, Task 4 → 1,
  Data 3 → 1, Sensitivity 2 → 1, Preregister 2 → 1, Thought 2 → 1,
  Lessons + reliability 10 → 2, `sys_config` 3 → 1, `sys_env` 2 → 1.
* 80 backward-compat aliases + 78 deprecated aliases preserve every
  v1 callsite. 24 hard-removed names (Phase 14a) return a friendly
  `_REMOVED_TOOLS` error.

**Discovery + introspection**

* New: `tool_protocols_list`, `tool_tools_list` — flat filterable
  catalogues.
* MCP `instructions` field shipped at handshake — names the canonical
  boot ritual.
* `tool_route` output gained `recommended_action` (literal next-call
  string) + `why_matched` (similarity score + matched triggers + tier).
* `sys_active_tools` returns a 13-18-tool scoped shortlist per
  protocol (down from 344 visible).
* `sys_protocol_get` default `format` flipped `full` → `summary`
  (5-10× cheaper per-turn load).

**Audit-as-data** *(phase-4)*

* Every audit emits a JSON companion alongside the Markdown report.
* `tool_audit_findings(operation='query'\|'diff'\|'explain')` reads the
  cross-audit ledger at `workspace/logs/.audit_findings.jsonl` with
  stable UUIDv5 ids. `query` filters by `severity`, `dimension`,
  `step`, `since`. `diff` compares two snapshots. `explain` (REQUIRES
  `id=...`) returns the full chronological history of one finding with
  the **untruncated** `suggested_fix` text — what to call when a
  synthesis-scope BLOCK preview cuts off the remediation guidance at
  160 chars.
* `tool_audit(scope='synthesis')` surfaces unresolved BLOCK findings
  in its error envelope so they can be triaged
  (`tool_audit_findings(operation='query', severity='block')`) and
  resolved before authoring or compiling the deliverable.
* `tool_audit_quality_full` returns structured per-component verdicts:
  `components: {step_completeness, code_quality, prose_quality,
  claims, preregistration_diff, grounding}` each with `{status,
  blockers, advice}`.

**Draft → review → rewrite loop**

* The AI authors the deliverable (`synthesis/paper.typ`,
  `poster.typ`, …) directly, then iterates draft → adversarial review
  (`tool_redteam_review`) → rewrite → `tool_synthesis_check` →
  `tool_typst_compile`. Drive the loop yourself rather than calling a
  one-shot generator.

**`research-os doctor`** *(phase-6)*

* 20+ install + workspace health checks. Exit policy: 0 = all-pass,
  1 = warn-only, 2 = fail. Run after every `pip install --upgrade
  research-os`. Flags: `--verbose`, `--workspace-only`, `--workspace
  <path>`, `--json`.

**`scope_tags` + `tier:` on every protocol** *(phase-7 + phase-8)*

* All protocols carry `scope_tags: {domain, audience,
  workflow_shape}` + a `tier:` annotation. Infrastructure shipped;
  the router does not yet filter on `scope_tags` (default-filter
  wiring is v2.1.0).

**`status` + `pack` on every tool definition**

* All tools annotated. `list_tools` filters to `status='live'`;
  no aliases / deprecated leak.

**Preflight checks expanded 22 → 24**

* New: "every tool definition has a handler" (all wired) +
  "no deprecated-alias tool refs in protocols" (clean across all
  deprecated names).

**Removed**

* Phase 14a — 21 v1.6.1 first-wave aliases hard-removed (`tool_search_*`,
  `tool_plan_*`, `tool_ground_*`, `tool_verify_*` legacy names,
  `sys_path_*`, `mem_*_log`/`mem_*_append`). Call the canonical entry
  point shown in the migration table.
* Phase 14b — `tool_poster_create(engine='latex')` (tikzposter) removed.
  Typst is the only supported poster renderer.
* `tool_figure_create` was removed (along with the 30+ `_render_*`
  chart-kind dispatchers, in v1.3.0). The AI writes its own
  matplotlib / ggplot2 / Altair / plotnine / d3 / plotly code per
  `visualization/figure_guidelines`.

---

## Return-shape examples

Most `tool_*` handlers return a dict the AI parses to decide the next
step. The examples below cover four tools called most often on a fresh
project.

### `tool_intake_autofill`

```json
{
  "status": "ok",
  "domain_inferred": "qualitative_interviews",
  "research_question": "How do early-career engineers narrate the moment they reframed a stuck design problem?",
  "hypotheses_drafted": [
    {"id": "H01", "text": "Reframing moments cluster around external prompts from peers, not from documentation."}
  ],
  "files_seen": {
    "raw_data": ["12 transcripts (.docx + .txt)"],
    "literature": ["3 PDFs"],
    "context": ["IRB approval letter"]
  },
  "wrote": ["inputs/intake.md", "research_overview.md", ".os_state/state.json"],
  "next_steps": "Run methodology/qualitative_research to enter the COREQ/SRQR loop."
}
```

`research_overview.md` is written into the project's `docs/` folder
(alongside any `domain_summary.md` / `glossary.md` later protocols add).

### `tool_synthesis_check`

```json
{
  "status": "warning",
  "file": "synthesis/dashboard.html",
  "mode": "all",
  "blockers": [],
  "warnings": [
    "Two <img> elements are missing alt text — add a plain-English description for each."
  ],
  "next_steps": "Add the missing alt text, then re-run tool_synthesis_check. The file is self-contained — open synthesis/dashboard.html in any browser to share."
}
```

### `tool_step_complete`

```json
{
  "status": "blocked",
  "step_id": "03_logistic_baseline",
  "passed": false,
  "gates_run": ["tool_audit_step_completeness", "tool_audit_step_literature", "tool_audit_code_quality"],
  "blockers": [
    {"gate": "tool_audit_step_literature", "issue": "findings_vs_literature.md missing — run literature/literature_per_step on this step's ## Findings"}
  ],
  "warnings": [
    {"gate": "tool_audit_step_completeness", "issue": "scratch/stack_plan.md missing"}
  ],
  "next_steps": "Resolve the one BLOCKER above, then re-run tool_step_complete. Override path: tool_step_complete(override_literature_gate=true, override_rationale='...') when justified."
}
```

### `tool_audit_quality_full`

```json
{
  "status": "warning",
  "wrote": "workspace/logs/audit_master.md",
  "components": {
    "step_completeness": {"status": "ok", "blockers": [], "advice": ["5/5 steps pass"]},
    "code_quality":      {"status": "ok", "blockers": [], "advice": []},
    "prose_quality":     {"status": "warning", "blockers": [], "advice": ["3 hedging phrases in Discussion"]},
    "claims":            {"status": "warning", "blockers": [], "advice": ["1 paragraph in Discussion lacks a numeric source"]},
    "preregistration_diff": {"status": "ok", "blockers": [], "advice": []},
    "grounding":         {"status": "warning", "blockers": [], "advice": ["2 decisions unbound"]}
  },
  "blockers": 0,
  "warnings": 3,
  "note": "Does NOT run the per-step literature gate; call tool_audit(scope='step', dimension='literature') per step (or tool_step_complete) before synthesis.",
  "next_steps": "Address the 3 warnings or proceed to synthesis if scope is provisional."
}
```

When a tool returns `next_steps` or `advice`, surface that hint
verbatim to the researcher rather than re-paraphrasing.

---

## Per-step audit overrides

Quality gates BLOCK by default. The researcher can authorise a bypass
for a single call by passing the right `override_<gate>=true` kwarg
**plus** an `override_rationale="<one-line why>"`. Every honoured
bypass appends a line to `workspace/logs/override_log.md` so the
pre-submission audit can resurface it before publication.

Under the default `interaction.quality_gate_policy=enforce`, the
rationale is **mandatory** — a bypass kwarg without a rationale is
rejected before the gate is even consulted. `allow_override` and
`warn_only` are **reserved** (not yet enforced): today they behave
exactly like `enforce`, and the per-tool `override_<gate>=true`
flags below already work regardless of the policy — so don't rely on
`warn_only` to soften gates.

### Override kwargs by tool

| Tool | Gate kwarg | Pairs with | Blocks what |
|---|---|---|---|
| `tool_audit(scope='synthesis', dimension='dashboard_content')` | `override_dashboard_content_gate` | `override_rationale` | Dashboard-content BLOCKERs (placeholder text, stub captions, etc.) |
| `tool_plan(operation='advance')` | `override_gate` | `override_rationale` | Deliverable-step quality gate before advancing the plan |
| `tool_step_complete` | `override_literature_gate` | `override_rationale` | Per-step literature loop check (missing `findings_vs_literature.md`, uncovered DISAGREES verdicts) |
| `tool_discussion_coverage_audit` | `override_discussion_coverage` | `override_rationale` | Discussion-coverage BLOCK (non-AGREES verdict missing from the Discussion) |
| `tool_audit(scope='synthesis', dimension='all')` | `override_no_pdfs` | `override_rationale` | Zero-PDF default-deny on literature-required steps |
| `tool_audit(scope='project', dimension='cross_deliverable')` | `override_cross_deliverable` | `override_rationale` | 5-dimension cross-deliverable audit |
| `sys_path(operation='create')` | `allow_unfinalized_predecessor` | `override_rationale` | Refusal to create the next numbered step before the previous one is finalised |

### Example calls

Walk the plan past a deliverable step the researcher already produced
outside the workspace:

```python
tool_plan(
    operation="advance",
    override_gate=True,
    override_rationale="poster v2 was rendered manually in Keynote",
)
```

Finalise the path before the literature loop has caught up:

```python
tool_path_finalize(
    path_name="03_pilot_grouping",
    override_literature_gate=True,
    override_rationale="pilot path — literature deferred to the v2 follow-up",
)
```

Audit a manuscript that intentionally has no PDFs (theory paper that
cites only earlier theorems):

```python
tool_audit(
    scope="synthesis",
    dimension="all",
    paper_path="synthesis/paper.md",
    override_no_pdfs=True,
    override_rationale="theory_math project — no empirical PDFs needed",
)
```

Use `tool_audit_findings(operation='query', severity='block')` to list
the current active blockers and
`tool_audit_findings(operation='diff', timestamp_a=..., timestamp_b=...)`
to confirm a fix actually resolved a finding between two audit runs.

### `override_rationale` is required, not advisory

Under `interaction.quality_gate_policy=enforce` (the default) every
override kwarg above MUST be paired with a non-empty
`override_rationale`. The server returns a hard error if the rationale
is missing or blank — the bypass never happens. This is deliberate:
silent bypasses are the failure mode this whole subsystem exists to
prevent.

### `workspace/logs/override_log.md` format

Every honoured bypass appends a single markdown bullet:

```
- 2026-06-06T17:42:11Z · `tool_audit` · gate=quality_full · reviewer wants a preview · {"output_type": "paper", "section": null, "blocker_count": 4}
```

Fields in order:

1. UTC timestamp (ISO 8601)
2. Tool name (backticked)
3. `gate=<gate-id>` — internal name of the gate that was bypassed
4. The rationale string verbatim (or
   `<no rationale provided — flag in audit>` if the policy allowed an
   empty one)
5. Optional JSON extras — for a synthesis-scope audit this includes
   `output_type`, `section`, and `blocker_count`; other tools attach
   tool-specific context

`audit/pre_submission_checklist` reads this log at publish time and
asks the researcher to confirm each entry. Don't hand-edit the log —
re-running the override creates a fresh entry, which is what the
audit trail expects.

---

## Adding a new tool

See [CONTRIBUTING.md § Adding a new tool](../CONTRIBUTING.md). Key
steps:

1. Implement in `src/research_os/tools/actions/<category>/<file>.py`.
2. Add `TOOL_DEFINITIONS` entry in
   `src/research_os/server/tool_definitions/<group>.py` with `short` +
   `description` + `category` + `pack` + `inputSchema`. Set
   `status='live'` (the default).
3. Add a handler + register in `_HANDLERS` (under
   `src/research_os/server/handlers/`).
4. Add to `_router_index.yaml` (either as a `decomposition` entry in
   a protocol or as a `shortcut_intents` entry).
5. Reference from at least one protocol or shortcut — preflight
   complains about orphans.
6. Add a test in `tests/tools/test_<area>.py`.

If the tool conceptually folds into an existing dispatcher
(`tool_audit`, `tool_search`, etc.), prefer adding an
`operation` / `dimension` value to the dispatcher over a fresh
top-level tool — the consolidation discipline is what keeps the
surface compact.
