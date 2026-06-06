# Tool Catalog

**212 MCP tools** across three namespaces (`sys_*` / `tool_*` / `mem_*`).
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
| `tool_plan` | Unified plan dispatcher. `operation='turn'` slices the active plan into a `this_turn` batch + `next_turn` queue sized to the researcher's `model_profile`. `operation='advance'` marks the current step done + returns the next. `operation='clear'` discards the active plan (researcher pivoted away). |
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
| `sys_path` | Unified path-lifecycle dispatcher. `operation='create'` creates the next numbered experiment folder; `operation='abandon'` marks a path as `__DEAD_END` (preserved, never deleted); `operation='list'` lists numbered experiment paths + status. |
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
| `tool_plan` | Unified plan dispatcher (`operation='turn'|'advance'|'clear'`). |

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
| `tool_search` | Unified search dispatcher. `source='semantic_scholar'` (Semantic Scholar Graph API), `'pubmed'` (NCBI eutils), `'crossref'`, `'arxiv'` (no key needed), `'web'` (Firecrawl → SerpAPI fallback), or `'auto'` to let the heuristic pick. |
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
| `tool_intake_autofill` | Read inputs/, infer domain + question + hypotheses, write to `inputs/intake.md` + `docs/research_overview.md` + `.os_state/state.json`. |
| `tool_context_intake` | Route mid-flow file drops into the right `inputs/` subfolder. Skips scaffold files. |

### Audit

| Tool | Purpose |
|---|---|
| `tool_audit_synthesis` | Audit a manuscript: claim grounding, citation coverage, causal language. v1.3.4+ aggregates per-step `step_summary.yaml` warnings and BLOCKs on pending-verification citations; v1.4.0+ BLOCKs on per-step `literature_deferred` + `literature.claims_grounded == 0`. |
| `tool_audit_step_completeness` | Per-step gate: focal figure + caption + summary sidecars + non-stub conclusions + no mega-script. v1.4.0+ BLOCKs on missing `.summary.md` (was WARN) + WARNs on missing `scratch/stack_plan.md`. |
| `tool_audit_step_literature` | **v1.4.0.** Per-step literature-loop gate. BLOCKs if `workspace/<step>/literature/findings_vs_literature.md` missing, any claim lacks a Verdict (AGREES \| DISAGREES \| EXTENDS \| DEFERRED), any DISAGREES verdict lacks a Discussion implication block, all-DEFERRED with no PDFs, or stub `## Findings`. Override: `override_literature_gate=true` + rationale. Writes `workspace/logs/step_literature_audit.md`. |
| `tool_audit_findings_query` | **v2.0.0 (Phase-4c).** Read the cross-audit findings ledger (`workspace/logs/.audit_findings.jsonl`). Filters by `severity` (`block`\|`warn`\|`info`), `dimension`, `step` (matches `evidence_paths` containing `/<step>/`), and `since` (ISO-8601). Returns the latest snapshot per stable finding id — a finding that was emitted, then re-emitted unchanged on rerun, appears once. Read-only; never mutates the ledger. |
| `tool_audit_findings_diff` | **v2.0.0 (Phase-4c).** Diff two snapshots of `workspace/logs/.audit_findings.jsonl` by stable finding id. Required: `timestamp_a` (earlier) + `timestamp_b` (later), both ISO-8601. Returns `{added, resolved, changed}` where `changed` compares structural fields only (`severity`, `dimension`, `evidence_paths`, `suggested_fix`) — a pure rerun with no content change is NOT reported as changed. Use to confirm a fix actually resolved a BLOCK finding between two audit runs. |
| `tool_audit_power` | Post-hoc statistical power. |
| `tool_audit_assumptions` | Normality + homoscedasticity + independence on residuals. |
| `tool_audit_figure` | DPI / colorblind palette / axis labels / error bars. |
| `tool_audit_citations` | Verify every workspace/citations.md entry against Crossref. |
| `tool_audit_reproducibility` | Re-run every script in a clean env and compare hashes. (Slow.) |
| `tool_audit_dashboard_content` | Content gates for synthesis/dashboard.html: numeric grounding, figure-to-text proximity, per-section substantiveness, WCAG 2.2 AA accessibility, print stylesheet sanity, color-palette consistency, 5-minute-reviewer simulator. |
| `tool_dashboard_reviewer_sim` | Standalone: would a 5-minute skimmer extract the headline finding from the dashboard? |
| `tool_section_substantiveness` | Per-IMRAD-section content depth: abstract ≥ 1 number, intro ≥ 3 citations + "in this study" pivot, methods covers ≥ 80% of workspace steps, results has stats, discussion has limitations + future work, refs sync with citations. |
| `tool_audit_cliches` | Scan synthesis/paper.md for AI-cliché phrases ("in this study, we investigate", "future work should explore", …) with per-cliché replacement hints. |

### Synthesis

| Tool | Purpose |
|---|---|
| `tool_synthesize_plan` | Inspect available sources; propose section order. |
| `tool_synthesize` | Compile workspace into paper / abstract / poster / dashboard / grant / report. Verified citations only. **v2.0.0:** also refuses to compile when any unresolved BLOCK finding sits in `workspace/logs/.audit_findings.jsonl` (latest-snapshot semantics). Override: `override_unresolved_blocks=true` + `override_rationale='<why>'`; logged to `workspace/logs/override_log.md`. |
| `tool_synthesis_preview` | Cheap deterministic dry-run before `tool_synthesize` — predicts word counts, page count, figures, citations, gaps. `mode='diff'` compares against the existing deliverable. |
| `tool_paper_compile_typst` | synthesis/paper.md → paper.typ → paper.pdf via Typst with a venue template (nature / science / nejm / cell / ieee_conf / neurips / acl / plos / generic_two_column / generic_thesis). Recommended PDF path. **v2.0.0:** wrapped in a review-rewrite loop (presentation_critic + scope_creep_critic + methodology_skeptic). Each iteration writes `workspace/logs/drafter_loops/paper_iter_<N>.{md,json}` and the cumulative `workspace/logs/drafter_loops/quality_progression.md` table. Disable per call with `drafter_loop=false`; tune via `synthesis.drafter_loop_*` in `researcher_config.yaml`. |
| `tool_latex_compile` | pdflatex + bibtex on synthesis/paper.tex. Use when a venue requires .tex submission. |
| `tool_poster_create` | Typst poster (academic_36x48 / academic_48x36 / academic_a0_portrait / academic_a1_landscape / public_24x36; light/dark/branded themes; optional QR + handout PDF). **v2.0.0:** wrapped in a review-rewrite loop (presentation_critic + novelty_critic, max 2 iterations). The legacy tikzposter LaTeX engine was removed in v2.0.0 (phase-14b). |
| `tool_dashboard_create` | Single-file offline HTML dashboard. `mode=` parameter selects the renderer's framing: `explore` (default, sidebar TOC + verdicts grid for self-service browsing), `story` (linear top-to-bottom walk-through driven by `synthesis/dashboard_story.md`), `executive` (collapsed everything-but-the-headline + verdicts; for stakeholders who need 5 minutes), `teaching` (defers jargon, leads with plain-English summaries, surfaces the glossary). Pair with the `audience=` parameter (academic / executive / technical / teaching) for section ordering. |
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

### Step completion

| Tool | Purpose |
|---|---|
| `tool_step_complete` | One-call gate for "this step is done." Runs `tool_audit_step_completeness` + `tool_audit_step_literature` + the per-step pieces of `tool_audit_quality_full` in sequence, then calls `tool_path_finalize` if every gate passes. Use this at the end of each numbered experiment step before moving on. Returns `passed: bool` + `blockers: [...]` + the same `next_steps` hint the per-gate tools return. Functionally an alias-superset of `tool_path_finalize` for callers who want a single entrypoint. |

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
| `mem_log` | Unified memory append. `kind='methods' \| 'decision' \| 'hypothesis' \| 'analysis'`. Replaces `mem_{methods_append, decision_log, hypothesis_update, analysis_log}`. |

---

## Infrastructure + power-user tools

The tables above cover the protocol-facing surface. The block below is
the **ground-truth roster** of every other `sys_*` / `tool_*` defined
in `TOOL_DEFINITIONS` — boot helpers, semantic search, unified
dispatchers, adapter framework, reliability / freshness probes, the
domain-pack tools (qualitative / humanities / engineering / wet-lab /
theory-math), and the SLURM / Snakemake / Nextflow / Synapse / REDCap
infrastructure adapters. Most are router-internal or pack-internal;
researchers rarely call them directly.

### Routing + dispatch helpers (mostly internal)

| Tool | Purpose |
|---|---|
| `sys_active_project` | Return the project root the server resolved for THIS request (global-server mode). |
| `sys_help` | AI orientation — how to use Research-OS efficiently (protocols + tools + routing). |
| `sys_packs_installed` | List installed protocol packs (name, version, tool count, router entries, errors). |
| `sys_adapters_installed` | List installed infrastructure adapters (SLURM / Snakemake / Nextflow / Cytoscape / REDCap / Synapse / external). |
| `sys_semantic_tool_search` | Find tools by what they do — semantic search over tool descriptions. |
| `tool_quick_route` | Detect throwaway / sanity-check / exploratory intent and short-circuit protocol load. |
| `tool_semantic_route` | Direct semantic search over protocol embeddings. Returns top-k candidates with scores. |
| `tool_search` | Unified literature/web search. Replaces `tool_search_{semantic_scholar,pubmed,crossref,arxiv,web}` via `source=…` or `auto`. |
| `tool_plan` | Unified plan dispatcher. `operation='turn'|'advance'|'clear'`. Replaces `tool_plan_{turn,advance,clear}`. |
| `tool_verify` | Verify a claim or the whole project's grounded claims. `scope='claim'|'project'`. Replaces `tool_claim_verify + tool_grounding_verify`. |
| `tool_lessons` | Unified lessons store. `operation='record'|'consult'`. Replaces `tool_lessons_record + tool_lessons_consult`. |
| `tool_dry_run` | Preview a protocol's tool-call sequence without executing — for supervised review. |
| `tool_deprecations_summary` | Aggregate counts from `.os_state/deprecations.log` — which deprecated aliases / redirects this project is still hitting. |

### State / config / files / checkpoints

| Tool | Purpose |
|---|---|
| `sys_config_set` | Set a single config value (dot notation, e.g. `researcher.expertise_level=advanced`). |
| `sys_config_validate` | Validate the config schema and report which API keys are present. |
| `sys_file_write` | Write a file. Refuses to write into `inputs/raw_data/` or `inputs/literature/` (immutable). `force=true` to overwrite in `synthesis/`. |
| `sys_file_list` | List files in a workspace directory (recursive). |
| `sys_file_delete` | Delete a workspace file or empty directory. |
| `sys_file_validate_md` | Validate a markdown file against the headings/sections expected by a writing protocol. |
| `sys_checkpoint_list` | List all checkpoints with descriptions and timestamps. |
| `sys_checkpoint_rollback` | Restore the workspace to a checkpoint. Current state is backed up first. |
| `sys_path` | Unified path dispatcher. `operation='create'|'abandon'|'list'`. Replaces `sys_path_{create,abandon,list}`. |
| `sys_env_docker_generate` | Generate a Dockerfile from the environment snapshot for full reproducibility. |
| `sys_export_share_archive` | Build a share-safe zip of the project (excludes AI-internal files). |

### Reliability / freshness / coaching

| Tool | Purpose |
|---|---|
| `tool_reliability_log_event` | Append a structural event (gate fire, tool error, recovery) to `workspace/.os_state/reliability.jsonl`. |
| `tool_reliability_report` | Redacted markdown summary of `reliability.jsonl`. |
| `tool_failure_record` | Record a tool failure (paywall / 404 / etc.) to `workspace/.os_state/tool_failures.jsonl`. |
| `tool_failure_check` | Is this URL/DOI known-bad (paywall, prior failure)? |
| `tool_failure_list` | List recent tool failures. |
| `tool_state_freshness_check` | Detect stale workspace state (state.json > 30d, citations older than newest PDF, orphan provenance). |
| `tool_intake_freshness` | Recommended intake depth (full / refresh-only / skip) based on intake.md freshness + step count. |
| `tool_rigor_signals_scan` | Score project rigor 0-100 from methods.md, citations, git, preregistration, scripts, prior step summaries. |
| `tool_project_tier_strictness` | Map `researcher_config.project_tier` (throwaway / sketch / production) → default `gate_strictness`. |
| `tool_resolve_gate_strictness` | Resolve effective gate strictness (light / normal / strict) from config + trust_score. |
| `tool_self_certify` | Persist a researcher self-certification (domain + scope + rationale). |
| `tool_list_certifications` | List active researcher self-certifications. |
| `tool_mistake_replay` | Surface recurring patterns from reliability log + override log — coaching-mode learning artifact. |
| `tool_promote_to_step` | Retroactively wrap a scratch result in proper provenance (new numbered step + sidecar + summary). |
| `tool_step_revision_options` | After a step finalize, surface the pause-and-revise heuristic + alternative paths + handoff hint. |
| `tool_alternative_path_propose` | Confidence-gated scan that pulls literature on the chosen method AND alternatives framed for the specific data shape. |

### Sub-task step pipelines (Theme 17)

| Tool | Purpose |
|---|---|
| `tool_step_pipeline_run` | Execute the step's sub-task DAG with content-hash caching. |
| `tool_step_pipeline_status` | Per-node staleness report — what's fresh, stale, or never run. |
| `tool_step_pipeline_diagram` | Render the step's sub-task DAG as Mermaid + (optional) PNG. |

### Audit extensions (beyond the master quality gate)

| Tool | Purpose |
|---|---|
| `tool_audit_coherence` | Verify every Discussion / Results / Intro paragraph in `synthesis/paper.md` maps back to a step's `conclusions.md`. |
| `tool_audit_figure_interactivity` | Per-figure interactive-companion gate (Theme 20). Scatter / volcano / UMAP > 200 marks, heatmaps > 50×50, networks, > 1k-point time-series need a sibling `<stem>.html`. Auto-generates Vega-Lite / vis-network fallbacks. |
| `tool_discussion_coverage_audit` | BLOCK gate: every non-AGREES literature verdict must have a Discussion paragraph. |
| `tool_redteam_review` | Adversarial review of a deliverable BEFORE peer review sees it. Stages a structured critique skeleton: assumptions / claims / threats-to-validity / alternative explanations / weakest step. Takes `focus='manuscript' \| 'proof' \| 'figure' \| 'methods'`. Distinct from `guidance/quick_paper_review` (critique of someone ELSE'S paper) and from `guidance/peer_review_response` (responding to reviews received). Referenced by `theory_math/proof/proof_verification_workflow` (focus='proof') and `writing/writing_limitations` (focus='manuscript'). |

### Synthesis extensions

| Tool | Purpose |
|---|---|
| `tool_synthesis_curate_figures` | Collect each step's focal figure into `synthesis/figures/` with stable, ordered names (`fig01_<slug>.png`, …). |
| `tool_writing_discussion_from_verdicts` | Append one Discussion paragraph per non-AGREES verdict in any step's `findings_vs_literature.md`. |
| `tool_dashboard_story_generate` | Build `synthesis/dashboard_story.md` (Theme 21 story-mode source) from workspace state. |
| `tool_dashboard_story_edit` | Read or patch `synthesis/dashboard_story.md`. |
| `tool_dashboard_story_quality_bar` | Quality bar for `dashboard_story.md`: 5-20 min read, figure in first 1000 words, ≥1 DISAGREES / EXTENDS callout. |
| `tool_figure_interactive_autogen` | Write an interactive HTML companion (Vega-Lite / vis-network) next to a static figure. Offline-capable. |

### Visualization adapters

| Tool | Purpose |
|---|---|
| `tool_cytoscape_export_static` | Render a static PNG / SVG snapshot of one or every network embedded in a `.cys` archive. |

### SLURM (deeper than `tool_slurm_submit`)

| Tool | Purpose |
|---|---|
| `tool_slurm_status` | Live status via `squeue` + finished status via `sacct` for one or all project jobs. |
| `tool_slurm_fetch` | Block until a SLURM job finishes; return stdout / stderr paths. |
| `tool_slurm_list` | List every SLURM job submitted from this project. |
| `tool_slurm_job_status` | Adapter-level: query Slurm (`squeue --json`) or PBS (`qstat -f`) for a job's status. Parsed JSON when supported, otherwise raw tail. |
| `tool_slurm_estimate_cost` | Estimate compute cost from `#SBATCH walltime + nodes × $/node-hour`. Real bills depend on queue priority + GPU surcharges. |

### Workflow-engine adapters

| Tool | Purpose |
|---|---|
| `tool_snakemake_dryrun` | `snakemake --dry-run -s <snakefile>`; status=warning with install hint if missing. |
| `tool_snakemake_dag_render` | Render the workflow DAG to PNG via `snakemake --dag | dot -Tpng`. Falls back to regex-derived Mermaid. |
| `tool_nextflow_validate` | `nextflow run <main.nf> --help`. Surfaces parse / config / DSL syntax issues. |

### Data-repo + clinical-data adapters

| Tool | Purpose |
|---|---|
| `tool_synapse_entity_info` | Opt-in live query of a Synapse entity's metadata via `synapseclient` using the project's `.synapseConfig`. |
| `tool_redcap_schema_describe` | Render the detected REDCap schema (events, instruments, fields, PHI warnings) as Markdown into `workspace/<step>/data/redcap_schema.md`. |

### Adapter framework

| Tool | Purpose |
|---|---|
| `tool_adapters_list` | List adapters + detection status on the current project (e.g. `slurm: detected_in_project=true`). |
| `tool_adapter_extract` | Run one adapter's `extract()` + write provenance YAML to `workspace/<step>/provenance/<adapter>.yaml`. |
| `tool_adapters_run_all` | Run every detected adapter's `extract()` and write per-adapter provenance YAMLs. |

### Qualitative pack

| Tool | Purpose |
|---|---|
| `tool_qualitative_codebook_diff` | Diff two versions of a qualitative codebook + optional per-code Cohen's κ from two rounds of applied coding. |
| `tool_qualitative_quote_provenance` | Register a participant quote in `workspace/quotes/registry.jsonl` with full provenance (participant_id, transcript path, line range, optional timestamp). |

### Humanities pack

| Tool | Purpose |
|---|---|
| `tool_humanities_archive_lookup` | Query digital archives (Internet Archive / HathiTrust / DPLA / Europeana / Gallica / Library of Congress) for primary sources. Writes a structured lookup plan. |
| `tool_humanities_citation_chain` | Build a chain-of-custody for a quotation: original ms → critical edition → translation → secondary citation. |
| `tool_humanities_transcribe` | Scaffold an OCR + manual-correction workflow for an archival image. Side-by-side transcription template. |

### Engineering pack

| Tool | Purpose |
|---|---|
| `tool_engineering_fault_tree_render` | Render a fault tree as Mermaid + (optional) SVG. Top event + AND/OR gates + basic events. |
| `tool_engineering_fmea_render` | Render an FMEA (Failure Mode & Effects Analysis) table from YAML to CSV + Markdown (+ optional `.xlsx`). Computes RPN = severity × occurrence × detection. |
| `tool_engineering_requirements_matrix` | Bidirectional requirements traceability matrix: requirements ↔ design elements ↔ test cases ↔ test results. Markdown + optional Excel. Cross-referenced from `methodology/method_comparison`'s engineering / systems-benchmark addendum — bind each measured property (wall-clock, throughput, memory) back to a stated requirement when the comparison feeds an engineering deliverable (release decision, contract milestone, internal RFC). |

### Wet-lab pack

| Tool | Purpose |
|---|---|
| `tool_wet_lab_plate_map_render` | Render a 96- or 384-well plate layout as PNG / SVG from a YAML spec. Visual sanity check for control placement. |
| `tool_wet_lab_reagent_query` | Structured query plan + write-into-`reagents.yaml` stub for one reagent. No live supplier API calls. |
| `tool_wet_lab_sample_lineage_export` | Render the parent → split → aliquot → readout tree as JSON + Mermaid. |

### Theory + math pack

| Tool | Purpose |
|---|---|
| `tool_theory_math_lean_check` | `lean --make` on a `.lean` file with structured error parsing. Writes an install hint when Lean is missing. |
| `tool_theory_math_coq_check` | `coqc` on a `.v` file with structured error parsing. Same install-detection behaviour as `_lean_check`. |
| `tool_theory_math_dep_graph` | Parse every `.lean` and `.v` under `source_dir`, extract named theorems / lemmas / definitions + module imports, write Mermaid + JSON dependency graph. |

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

**Visualisation (AI writes the script; tools support audit + sidecars)**

Research-OS does not ship a parametric chart-builder. The AI writes its
own matplotlib / ggplot2 / Altair / plotnine / d3 / plotly script per
the `visualization/figure_guidelines` protocol. The tools below support
that workflow:

* `tool_figure_palette` — Okabe-Ito (qualitative, CVD-safe), viridis
  (sequential), PuOr (diverging), or the dashboard accent set.
* `tool_figure_caption_synthesise` — drafts a plain-English
  `<name>.summary.md` sidecar from the figure's existing
  `.caption.md` + the step's Findings (W3C two-part guidance).
* `tool_audit_figure_full` — strict figure audit: DPI ≥ 300, sidecar
  presence (caption + summary), SVG companion, aspect-ratio sanity for
  time-series-named figures, AND an SVG text-overlap heuristic for the
  "stacked labels" pitfall.

> **Removed in v1.3.0:** `tool_figure_create` and the 30+ `_render_*`
> chart-kind dispatchers. The AI writes its own plotting code now.
> Old callers receive a deprecation message pointing at
> `visualization/figure_guidelines`.

**Quality auditors**
* `tool_audit_quality_full` — runs every gate in one call. Bundles
  `tool_audit_step_completeness` + `tool_audit_code_quality` +
  `tool_audit_prose` + `tool_audit_claims` + `tool_preregister_diff`
  + `tool_ground`. **Does NOT run the per-step literature gate** —
  call `tool_audit_step_literature` per step (or rely on
  `tool_step_complete` to catch it). Skipping it surfaces as a blocker
  later in `tool_audit_synthesis` / `tool_path_finalize`.
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

## Return-shape examples (what these tools actually hand back)

Most `tool_*` handlers return a dict the AI parses to decide the next
step. The examples below cover the four tools most often called on a
fresh project — `tool_intake_autofill`, `tool_dashboard_create`,
`tool_step_complete`, `tool_audit_quality_full` — so the AI doesn't
have to guess the shape from the description alone.

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
  "wrote": ["inputs/intake.md", "docs/research_overview.md", ".os_state/state.json"],
  "next_steps": "Run methodology/qualitative_research to enter the COREQ/SRQR loop, or methodology/qualitative_pii_redaction first if transcripts contain PHI."
}
```

### `tool_dashboard_create`

```json
{
  "status": "ok",
  "wrote": "synthesis/dashboard.html",
  "size_kb": 612,
  "audience": "academic",
  "mode": "explore",
  "embedded_figures": 7,
  "verdicts_rendered": 3,
  "blockers_surfaced": 0,
  "warnings": [
    "Two figures lack an interactive companion; gate auto-generated Vega-Lite fallbacks."
  ],
  "next_steps": "Open synthesis/dashboard.html in any browser. To share, the file is self-contained — email or upload as-is."
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
  "gates_run": [
    "tool_audit_step_completeness",
    "tool_audit_code_quality",
    "tool_audit_prose",
    "tool_audit_claims",
    "tool_preregister_diff",
    "tool_ground"
  ],
  "blockers": 0,
  "warnings": 3,
  "per_gate": {
    "tool_audit_step_completeness": {"status": "ok", "summary": "5/5 steps pass"},
    "tool_audit_claims": {"status": "warning", "summary": "1 paragraph in Discussion lacks a numeric source"}
  },
  "note": "Does NOT run the per-step literature gate; call tool_audit_step_literature per step (or tool_step_complete) before synthesis.",
  "next_steps": "Address the 3 warnings or proceed to synthesis if scope is provisional."
}
```

The exact keys may evolve; the AI should treat unknown keys as
forward-compatible (read what it understands, log+ignore the rest).
When a tool returns `next_steps` or `advice`, the AI should surface
that hint verbatim to the researcher rather than re-paraphrasing.

---

---

## Per-step audit overrides

Quality gates BLOCK by default. The researcher can authorise a bypass
for a single call by passing the right `override_<gate>=true` kwarg
**plus** an `override_rationale="<one-line why>"`. Every honoured
bypass appends a line to `workspace/logs/override_log.md` so the
pre-submission audit can resurface it before publication.

Under the default `interaction.quality_gate_policy=enforce`, the
rationale is **mandatory** — a bypass kwarg without a rationale is
rejected before the gate is even consulted. Under `allow_override`
the AI may bypass on request with the rationale logged. Under
`warn_only` (sandbox only) blockers degrade to warnings and no
explicit override is needed.

### Override kwargs by tool

| Tool | Gate kwarg | Pairs with | Blocks what |
|---|---|---|---|
| `tool_synthesize` | `override_completeness_gate` | `override_rationale` | Master quality gate (full doc) / step-completeness (section-only) |
| `tool_dashboard_create` | `override_completeness_gate` | `override_rationale` | Step-completeness warnings panel on the rendered dashboard |
| `tool_dashboard_create` | `override_dashboard_content_gate` | `override_rationale` | `tool_audit_dashboard_content` BLOCKERs (placeholder text, stub captions, etc.) |
| `tool_audit_dashboard_content` | `override_dashboard_content_gate` | `override_rationale` | Same gate when called directly (returns `override_applied: true`) |
| `tool_plan_advance` / `sys_plan_op operation='advance'` | `override_gate` | `override_rationale` | Deliverable-step quality gate before advancing the plan |
| `tool_path_finalize` | `override_literature_gate` | `override_rationale` | Per-step literature loop check (missing `findings_vs_literature.md`, uncovered DISAGREES verdicts) |
| `tool_audit_step_literature` | `override_literature_gate` | `override_rationale` | Same gate when called directly |
| `tool_discussion_coverage_audit` / `tool_writing_discussion` validate step | `override_discussion_coverage` | `override_rationale` | Discussion-coverage BLOCK (non-AGREES verdict missing from `synthesis/discussion.md`) |
| `tool_audit_synthesis` | `override_no_pdfs` | `override_rationale` | Zero-PDF default-deny on literature-required steps |
| `tool_paper_figures_autoembed` | `override_xref_rewrite` | n/a (local flip) | Skip the auto rewrite of figure cross-references when `synthesis.figure_xref_rewrite=true` in `researcher_config.yaml`. Use when `paper.md` already carries hand-tuned Pandoc cross-refs the AI must not touch. |
| `tool_audit_cross_deliverable_consistency` | `override_cross_deliverable` | `override_rationale` | 5-dimension cross-deliverable audit (numeric / figures / citations / top-line findings / reproducibility footer). Use when an outward-facing deliverable intentionally diverges from the paper (e.g. a poster simplification reviewed by the supervisor). |
| `sys_path_create` | `allow_unfinalized_predecessor` | `override_rationale` | Refusal to create the next numbered step before the previous one is finalised |

### Example calls

Synthesize a partial paper preview before the final figures land:

```python
tool_synthesize(
    output_type="paper",
    override_completeness_gate=True,
    override_rationale="reviewer wants a preview of the discussion before Fig 3 is final",
)
```

Render the executive dashboard for a status meeting even though three
step captions are still stubs:

```python
tool_dashboard_create(
    audience="executive",
    override_completeness_gate=True,
    override_rationale="board update at 16:00, finals land tomorrow",
)
```

Walk the plan past a deliverable step the researcher already produced
outside the workspace:

```python
tool_plan_advance(
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
tool_audit_synthesis(
    paper_path="synthesis/paper.md",
    override_no_pdfs=True,
    override_rationale="theory_math project — no empirical PDFs needed",
)
```

Create the next numbered path before the previous one is sealed (the
researcher is branching exploratory work):

```python
sys_path_create(
    name="04_alt_grouping",
    branch_of="03_pilot_grouping",
    allow_unfinalized_predecessor=True,
    override_rationale="branching to explore an alternative cutoff while 03 finishes",
)
```

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
- 2026-06-05T17:42:11Z · `tool_synthesize` · gate=quality_full · reviewer wants a preview · {"output_type": "paper", "section": null, "blocker_count": 4}
```

Fields in order:

1. UTC timestamp (ISO 8601)
2. Tool name (backticked)
3. `gate=<gate-id>` — internal name of the gate that was bypassed
   (e.g. `quality_full`, `step_completeness`, `dashboard_content`,
   `audit_synthesis_no_pdfs`, `enforce_predecessor_finalized`)
4. The rationale string verbatim (or
   `<no rationale provided — flag in audit>` if the policy allowed an
   empty one)
5. Optional JSON extras — for `tool_synthesize` this includes
   `output_type`, `section`, and `blocker_count`; other tools attach
   tool-specific context

The file header is written once on first append:

```markdown
# Quality-gate bypass log

Every entry here represents a moment the researcher explicitly
authorised the AI to bypass a quality gate. The pre-submission audit
surfaces this list — confirm each bypass was intentional before
submission.
```

`audit/pre_submission_checklist` reads this log at publish time and
asks the researcher to confirm each entry. Don't hand-edit the log —
re-running the override creates a fresh entry, which is what the
audit trail expects.

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
