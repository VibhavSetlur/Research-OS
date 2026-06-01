# Changelog

All notable changes to Research OS are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) ·
versioning: [SemVer](https://semver.org).

## [2.2.0] — Partial-workflow + role-specific protocols

Coverage release. Audits the protocol surface against how researchers
actually USE Research OS — many enter mid-pipeline, want viz without
re-running analysis, need a talk deck instead of a paper, or want to
TEACH a method rather than commit to one. Adds 14 new protocols
covering visualization-only, role-specific synthesis (slides / lay
summary / progress update / from-inputs), and methodology workflows
that didn't have a home (real EDA + hypothesis generation, head-to-
head method comparison, standalone data quality, standalone power,
reproduction of published work, methodological consultation /
teaching, multi-paper compare, mid-pipeline entry). All scaffolds,
not scripts.

### New protocols — visualization
* `visualization/visualization_workflow` — full WORKFLOW counterpart of
  `figure_guidelines` (the existing rules-only doc). Scope → locate
  sources → enumerate figures → compute minimal inputs → build via
  `tool_figure_create` → sensitivity-check → audit → promote/curate.
  Routes from "make me a figure", "polish my figures", "build a
  figure deck".
* `visualization/figure_critique` — reviewer-style critique of a single
  figure. Chart-family / encoding / information-density / caption-
  alignment walk + one alternative-encoding sensitivity proposal.
  Routes from "critique this figure", "review this plot".

### New protocols — synthesis
* `synthesis/synthesis_slides` — presentation deck with six audience
  profiles (lab_meeting / conference_talk_short / conference_talk_long /
  defense / invited_seminar / teaching), four output formats
  (Beamer / Marp / Reveal.js / PowerPoint), mandatory speaker notes,
  mandatory Q&A anticipation + backup deck.
* `synthesis/synthesis_lay_summary` — non-expert summary with six
  audience profiles (general_public / press_release / funder_lay_section
  / patient_or_participant / social_thread / blog_post). Reading-grade
  cap; jargon-replacement glossary; anchor comparisons for every
  number; supportive recommendation for a human review pass on
  high-stakes outputs.
* `synthesis/synthesis_progress_update` — short PI / advisor / lab /
  collaborator / stand-up update sourced from the diff since the
  last update; blockers + ask explicit; one-per-day file naming so
  the chain of updates becomes a searchable project diary.
* `synthesis/synthesis_from_inputs` — synthesis when prior analyses
  ran OUTSIDE Research-OS. Creates a labelled SHADOW workspace step
  to anchor the synthesis (so audit + dashboard tooling still works),
  extracts findings from input artefacts with explicit citations,
  runs the chosen target synthesis on top, surfaces an honest
  PROVENANCE CEILING paragraph in the final deliverable.

### New protocols — methodology
* `methodology/exploratory_data_analysis` — real EDA + hypothesis
  generation (distinct from confirmatory EDA inside analysis_plan
  and from the lightweight `casual_exploration`). Pre-registers the
  SCOPE of exploration before outcomes are examined; caps subgroup
  splits; marks generated hypotheses with `status="exploratory"`;
  forbids confirmatory claims on the same data; audits for
  forking-paths, target leakage, and over-reach.
* `methodology/method_comparison` — head-to-head benchmark of N
  candidate methods on the same task. Same split + same featureset +
  same hyperparameter budget; tune-inside-folds; uncertainty (CIs
  + paired tests + correction) reported alongside the winner;
  baseline mandatory; honest generalisability ceiling.
* `methodology/data_quality_audit` — standalone data QC. Structural /
  completeness / distributional / duplicate / leakage / temporal /
  cross-source / representation checks. Verdict in one of four
  classes (usable / usable with conditions / usable for subset only /
  not usable) with reproducible-check evidence per blocker.
* `methodology/power_analysis` — standalone power / sample-size
  justification. Three shapes (prospective / post-hoc sensitivity /
  sequential). Explicitly refuses classical post-hoc power; replaces
  with detectable-effect-size analysis. Builds a power TABLE (not a
  single number) across an effect × alpha × allocation × attrition
  grid + a power-curve figure + a reviewer-facing justification
  paragraph.
* `methodology/reproduction_attempt` — attempt to reproduce a
  PUBLISHED analysis (distinct from `replication_study` which runs
  the analysis on new data, and from `reproducibility/reproducibility`
  which audits OUR OWN work). Honest verdict in one of six classes
  (regenerated / regenerated-with-deviations / partial /
  failed-mechanically / failed-substantively / blocked-by-
  unavailability). Numerical diff table; cause hierarchy walks
  mechanical → substantive; author engagement encouraged before
  publishing the failure.
* `methodology/methodological_consultation` — teach / explain / compare
  methods WITHOUT committing to a project. Layered explanation
  (intuition → mechanics → caveats → reading list); literature-
  grounded BEFORE the explanation so it reflects current consensus.
  Failure-mode layer matches the depth of the mechanics layer
  (half of methodological skill is knowing how to break what you're
  about to use). Optional save to `docs/consultations/`.

### New protocols — literature
* `literature/comparative_paper_review` — compare-and-contrast 2-N
  papers (distinct from `quick_paper_review` (single paper) and from
  the broader `systematic_review` / `evidence_synthesis`). Four
  audience profiles (journal_club / related_work_section /
  reviewer_response / foundational_reading). Comparison matrix with
  cells at parallel depth; common ground + disagreements both
  named; positioning paragraph for project audiences.

### New protocols — guidance
* `guidance/mid_pipeline_entry` — explicit entry for researchers
  arriving with work ALREADY DONE outside Research-OS (distinct from
  `session_boot` which fires every session, `session_resume` for
  paused RO projects, and `project_startup` for fresh data dumps).
  Classifies the entry into one of seven archetypes (DATA-READY /
  ANALYSES-READY / FIGURES-READY / SYNTHESIS-READY / PRIOR-RO-PROJECT
  / CONCEPTUAL / MIXED) and routes to the right downstream protocol
  without forcing redundant intake. Records the provenance ceiling
  so downstream audits know what was reasoned vs imported.

### Router hierarchy — new sub-intents
Added to `_router_index.yaml`:
* `discover.mid_entry` — enter an in-progress project
* `methodology.eda` / `comparison` / `data_audit` / `power` /
  `reproduce` / `consult`
* `literature.compare`
* `synthesize.slides` / `lay` / `update` / `inputs_only` / `viz_build`
* `review.figure`

### Docs
* `docs/USE_CASES.md` (new) — role × goal × output map. Picks the
  right protocol by researcher role (grad student / PI /
  methodologist / reviewer / communicator / teacher / presenter /
  starting-in-the-middle / viz-only / no-project-yet) and by output
  type (paper / poster / dashboard / slides / lay summary / report /
  grant / progress update / critique / reproduction report / power
  justification / consultation).
* `docs/RESEARCHER_GUIDE.md` — copy-paste prompts section expanded with
  categorised entries (starting / mid-flow analysis / reading +
  understanding / visualization / writing + synthesis / operations).
  Cross-references USE_CASES.
* `docs/PROTOCOLS.md` — protocol counts and per-category lists updated.
  Cross-references USE_CASES.
* `README.md` — top-line counts updated (66 protocols), feature
  description names the role / partial-workflow coverage explicitly,
  documentation table links USE_CASES.

### Existing protocols — cross-references added (no behaviour change)
* `visualization/figure_guidelines` (v6.0.0 → v6.1.0) — description
  cross-references `visualization_workflow` (workflow counterpart)
  and `figure_critique` (single-figure critique). No step changes.
* `guidance/casual_exploration` (v1.0.0 → v1.1.0) — description lists
  the related lightweight modes (`exploratory_data_analysis`,
  `data_quality_audit`, `methodological_consultation`,
  `visualization_workflow`, `quick_paper_review`, `code_review`) so
  the AI knows when to route to a more-specific protocol instead.
  No step changes.

### Tests
* `tests/tools/test_router.py` — 14 new tests, one per new protocol,
  asserting correct L1 / L2 / L3 routing for a representative
  trigger. Plus a regression test verifying that adding 14 new
  protocols does NOT change routing for any of 12 well-known
  pre-existing trigger phrases.
* `tests/integration/test_all_protocols_load.py` — path bug fix
  (the parametrize was silently empty because
  `tests/src/research_os/protocols/` did not exist; one more
  `.parent` was needed). Now correctly parametrizes over every
  protocol on disk + skips underscore-prefixed special files
  (router index). Coverage went from 0 to 67 protocols loaded.

### Preflight
67 protocols indexed, all router refs resolve, all tool refs resolve.
13 / 13 preflight checks pass.

### Test count
342 passed (was 259, +83 new). 1 skipped.

---

## [2.1.0] — Reasoning scaffolds, branch-aware paths, domain-agnostic deep research

Doctrine + capability release. Codifies the protocol-design principle
that should have been explicit from day one (**scaffolds, not
scripts**), prunes prescriptive content that violated it, adds a
literature-grounded **deep-domain-research** layer for subfields where
the analysis is a multi-stage canonical pipeline, ships
**branch-aware path naming** so alternative analytical paths live
side-by-side under explicit lineage tags, and adds a confidence-gated
**alternative-path proposal** tool. Backward-compatible — no breaking
changes to state schema or tool signatures; new behaviours are opt-in.

### Principle (new) — scaffold not script
A new doctrine doc at [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md)
states the operating principle: every protocol names the QUESTIONS
the AI must answer + the GROUNDING it must cite, never the answers.
Tools, thresholds, finite method menus, and canned step sequences are
prescription and out of scope. The doctrine names the patterns that
count as each, with concrete examples. `CONTRIBUTING.md` now links to
it as required reading before protocol edits.

### Methodology protocols — de-prescriptivized
All 14 methodology protocols re-audited against the doctrine.
Substantive rewrites:
* `methodology_selection.yaml` — removed the 14-row
  `(outcome × structure × dim) → method` lookup table. Replaced with
  a literature-grounded candidate-enumeration scaffold that demands
  the AI surface candidates via `tool_research_method` and never pick
  from memory or a fixed menu. The list-of-canned-assumption-tests is
  similarly replaced with a "name the falsifying diagnostic, cite
  the source" scaffold.
* `clinical_trials.yaml` — removed |SMD| > 0.10, MICE-as-default, the
  canned step sequence. Replaced with reasoning about randomisation,
  missingness mechanism, analysis population, and SAP alignment.
* `survey_psychometrics.yaml` — removed CFI ≥ 0.95, RMSEA ≤ 0.06,
  α-band thresholds. Replaced with field-cited reliability and
  factor-structure reasoning.
* `machine_learning.yaml` — removed 70/15/15, SHAP-as-default, named
  metrics. Replaced with a "split mirrors deployment" scaffold +
  leakage audit + cost-structure-driven metric reasoning.
* `causal_inference_deep.yaml` — removed dowhy/econml-as-default,
  identification-strategy table. Replaced with DAG-first reasoning +
  literature-grounded identification + sensitivity-to-unmeasured-
  confounding scaffold.
* `meta_analysis.yaml` — removed I² interpretation cutoffs and named
  estimators; effect-size scale + pooling-model choice now follow
  from the outcome family + field convention.
* `timeseries_analysis.yaml` — removed the method-family lookup table
  (`Univariate · stationary · short → ARMA`, etc.); replaced with
  reasoning about the dimensions that drive method choice +
  literature-grounded candidate enumeration.
* `qualitative_research.yaml` — removed the "aim for 30-100 codes /
  5-20 categories / 3-7 themes" prescriptions; counts now follow
  data + analytic tradition.

Light touches (added `editorial_voice` blocks anchoring the scaffold
tone; no content rewrites): `ablation_study`, `pilot_study`,
`mixed_methods`, `simulation_studies`, `replication_study`.

`bayesian_analysis` already met the doctrine — unchanged.

### New protocol — `methodology/deep_domain_research`
Domain-agnostic reasoning scaffold for entering an unfamiliar subfield.
Six steps: identify the specific subfield from project signals (not
from a list in the protocol), survey the literature for the field's
canonical pipeline with ≥3 cited sources, propose a per-stage
skeleton (tool × language × runtime — polyglot pipelines are
first-class), build an assumption matrix that names falsifying
diagnostics per stage, run a confidence-gated alternative-path
scan, commit. `domain_analysis` routes here when the subfield is
non-trivial; `methodology_selection` consults the committed
`docs/pipeline_plan.md` first when it exists. Contains zero
domain-specific defaults — the AI generates everything per project
from the literature.

### New tool — `tool_alternative_path_propose`
Confidence-gated alternative-pipeline scan. Pulls literature on the
user's chosen method AND on alternatives framed for the specific data
shape, counts comparative-evidence signals, and returns either
`recommendation: commit_user_method` (silent — default) or
`recommendation: branch_to_alternative` (surface ONE alternative
once, branch on confirmation). Anti-spam by design.

### Branch-aware path naming
`sys_path_create` gains a `branch_of` parameter. When set, the new
folder is named `NN_<slug>_path_<k>` (e.g. `05_glmm_path_1`) and its
`data/input` symlinks to the PARENT step's output rather than to the
previous numbered step. The branch lineage flows through every
subsequent step created with `branch_of` pointing back into the same
lineage — so a forked analytical path's steps share the `_path_<k>`
suffix. Dead-ends stack: `05_glmm_path_1` →
`05_glmm_path_1__DEAD_END`. State records `branch_of` +
`path_lineage` per path.

### Config presets — removed
The 10 modality-specific preset configs (`rct_config`, `genomics`,
`psychometric`, `epidemiology_observational`, `nlp_benchmark`,
`economic_panel`, `qualitative_research`, `geospatial`, `time_series`,
`survival_analysis`) are deleted. They violated the scaffold doctrine
by baking in canonical pipelines, expected columns, and "right"
reporting standards per modality. There is now ONE template:
`templates/researcher_config.yaml` (all fields blank). The AI fills it
per-project from intake signals + literature.

For *patterns* the AI can recognise without copying, see
[`docs/DOMAIN_HINT_EXAMPLES.md`](docs/DOMAIN_HINT_EXAMPLES.md) —
three cross-domain reasoning patterns, explicitly not a taxonomy.

### Wiring
* `_router_index.yaml` adds `subfield_pipeline` sub-intent and the
  `methodology/deep_domain_research` entry with cross-domain trigger
  phrases.
* `domain/domain_analysis.yaml` gains a `route_to_deep_domain_research`
  step and points to the new protocol when the subfield is non-trivial.
* `methodology/methodology_selection.yaml` gains a
  `load_pipeline_plan_if_present` first step so it operates on top of
  the committed pipeline rather than from a blank slate.

### Tests
* `tests/unit/test_branch_paths.py` — 9 tests covering branch naming,
  lineage inheritance through downstream steps, dead-end suffix
  stacking, data/input wiring to the parent's output.

### Validation
* 53 protocols load (13 preflight checks pass), 138 tools wired
* 259 tests pass, 1 skipped
* `ruff check src tests scripts` clean

## [2.0.0] — National-lab quality overhaul

Major release. 137 MCP tools (up from 98), 52 protocols (up from 47),
new grounded-reasoning layer, sub-task pipelines, per-output provenance,
Playwright dashboard self-tests, expanded visualisation library (25 chart
kinds), comprehensive quality auditors, pre-registration / SAP workflow,
HPC integration. State schema migrates automatically on first load.

See the [migration guide](docs/MIGRATION_2_0.md) for the few API names
that changed and the dropped legacy aliases.



### Sub-task pipelines (no more mega-scripts)
* **`tool_step_pipeline_define / _run / _status / _diagram`** — every
  numbered step can now declare a `pipeline.yaml` of small atomic
  scripts (ingest → validate → clean → fit → diagnose → visualize →
  report). The runner topologically orders nodes, content-hash
  caches inputs+params+script (only changed downstream chains
  re-run), and writes `.pipeline_run/run_<ts>.json` audit trails.
* Multi-script steps without a `pipeline.yaml` are flagged by
  `tool_audit_step_completeness`.

### Per-file provenance sidecars (PROV-O / RO-Crate compatible)
* **`write_output_provenance`** drops a `<file>.prov.json` next to
  every figure, table, CSV, pickle. Records: script + git SHA,
  input SHA-256s, params, RNG seed, library versions, wall time,
  host. `tool_figure_create`, the sub-task runner, `tool_sensitivity_run`,
  and Papermill-mode notebook exec all emit sidecars automatically.
* `step_provenance_inventory` gates synthesis on coverage <50%.

### 16 new publication-grade plot types
* ROC, PR, calibration, QQ, residual diagnostics (4-panel),
  partial dependence, dot-and-whisker (regression coefs),
  ridgeline, raincloud, hexbin, slope, Bayesian posterior (with HDI
  + ROPE), variable importance, funnel (publication bias),
  alluvial / Sankey, hierarchical heatmap with clustering, CONSORT
  flow diagram. `tool_figure_create` now supports 25 chart kinds.

### Quality auditors (every gate BLOCKS at synthesis)
* **`tool_audit_code_quality`** — ruff lint + AST-based cyclomatic
  complexity + function length + smell detection (bare except,
  `import *`, `eval`/`exec`, hardcoded absolute paths) per script.
  Blockers: complexity >20, length >150, sloppy smells.
* **`tool_audit_prose`** — flags 40+ hedge phrases, numbers-without-
  precision regex, passive-voice ratio, Flesch-Kincaid grade,
  causal language on observational designs, CONSORT / STROBE /
  PRISMA / ARRIVE section coverage by domain.
* **`tool_audit_claims`** — extracts every numeric claim from
  `synthesis/paper.md` and verifies each appears in some workspace
  output (CSV / JSON / MD / TXT) within 1% tolerance. Catches AI
  hallucination.
* **`tool_audit_evalue`** — VanderWeele & Ding 2017 E-value
  sensitivity to unmeasured confounding for observational designs.
* **`tool_audit_quality_full`** — runs every gate in one call,
  aggregates blockers. `tool_synthesize` calls this as its first
  step; if any blocker, synthesis is REFUSED.

### Extended statistical diagnostics
* `tool_audit_assumptions` now runs Breusch-Pagan,
  Durbin-Watson, Variance Inflation Factor (VIF), Cook's distance,
  Shapiro-Wilk, Levene — the full diagnostic battery a national-lab
  reviewer expects.

### Pre-registration / SAP
* **`tool_preregister_freeze`** — snapshots methods + hypotheses
  into a content-hashed, immutable SAP under
  `workspace/.preregistration/`. Follows the FDA E9 + SPIRIT 2025 +
  CONSORT 2010 field structure; suggests OSF upload.
* **`tool_preregister_diff`** — at synthesis, lists every deviation
  (added/removed hypotheses, methods drift, primary-outcome
  swap) so the Discussion can acknowledge them honestly.
* New protocol: `methodology/preregistration.yaml`.

### Multi-verse / specification-curve sensitivity
* **`tool_sensitivity_define / _run`** — author a Cartesian-product
  grid of analytic choices (covariate sets, exclusion rules, outlier
  handling, model families); the runner fans out the base script,
  collects estimate + CI per spec, and renders a Steegen-style
  specification curve. Distinguishes ROBUST from FRAGILE findings.

### Red-team peer-reviewer workflow
* **`tool_redteam_review`** — generates a hostile-reviewer scaffold
  (summary, M1-M5 major comments, m1-m5 minor, threats-to-validity,
  devil's-advocate questions) under three personas
  (methodological_skeptic, statistical_referee, sympathetic_peer).
* **`tool_response_to_reviewers`** — paired response template with
  one heading per reviewer comment.

### Null findings reporter
* **`tool_null_findings_report`** — assembles `synthesis/null_findings.md`
  from refuted hypotheses, underpowered tests (computed power <0.8),
  and abandoned dead-end paths. Fights the file-drawer problem.

### HPC / SLURM integration
* **`tool_slurm_submit / _status / _fetch / _list`** — generate
  sbatch scripts from `researcher_config.runtime.cluster_defaults`
  (cpus, mem, time, partition, GPUs, array, dependency, modules,
  conda env); record job_id; poll squeue/sacct; pull stdout/stderr
  back into the step folder.

### Apptainer / Docker / entrypoint per step
* `tool_step_env_lock` gains `write_apptainer` (emits HPC-friendly
  `step.def`) and `write_entrypoint` (default true — writes
  `entrypoint.sh` that reproduces every output by walking the
  sub-task DAG).

### Papermill-aware notebook execution
* `tool_notebook_exec` accepts a `parameters` dict (Papermill).
  Each parameter set lands at `notebooks/runs/<stem>_<hash>.ipynb`
  with a provenance sidecar. The executed notebook IS the provenance
  record. Falls back to nbconvert when papermill isn't installed.

### Visualisation toolkit (new module `tools/actions/viz/`)
* **`tool_figure_create`** — publication-grade figure builder. SciencePlots
  stylesheet (or built-in equivalent), Okabe-Ito / viridis / PuOr palettes,
  enforced ≥300 DPI, mandatory axis-with-units, inline n annotation,
  95% CI band on regression overlays, dual PNG + SVG emission, and both
  caption sidecars written in one call. Optional plotnine backend (grammar
  of graphics) and plotly companion (interactive HTML) when installed.
* **`tool_figure_caption_synthesise`** — W3C-style accessible
  `<name>.summary.md` next to every figure, drafted from the technical
  caption + the step's Findings.
* **`tool_figure_audit_quality`** — deeper figure audit (DPI + caption +
  summary + SVG + aspect ratio).
* **`tool_figure_palette`** — colour-blind-safe palettes by encoding.

### Per-step accessibility + completeness gates
* **New `context/` folder** in every step — narrative scratchpad with a
  `notes.md` template; plain-language summary auto-propagates to the
  step's README via `tool_path_finalize`.
* **Dual-file README + conclusions** convention: README is a 60-second
  overview for non-experts; conclusions is the full statistical record.
  Every figure now MUST have `.caption.md` (technical) AND `.summary.md`
  (plain-English) sidecars — auto-synthesised by `tool_path_finalize`
  if the analyst doesn't supply them.
* **`tool_audit_step_completeness`** — server-enforced gate validating
  that every active step has a focal figure + both sidecars + non-stub
  conclusions. BLOCKS `tool_synthesize` and `tool_plan_advance` to the
  final deliverable until cleared (override available for partial
  deliverables when explicitly authorised).
* **Tightened `_is_complex` classifier** — word-count threshold 25 → 18,
  verb threshold 3 → 2, explicit "do everything"-style phrases always
  trigger an active plan.

### Synthesis outputs
* **Unified `synthesis_spec.yaml`** (legacy `dashboard_spec.yaml` still
  read) — single editorial source consumed by paper + dashboard + poster.
  Adds `methods_summary`, `poster_headline`, `paper_url` fields.
* **Better paper LaTeX**: replaces line-by-line escape with a proper
  AST-aware renderer (pandoc when available, full markdown→LaTeX
  fallback with inline formatting, lists, tables, hyperlinks). Real
  Background/Methods/Results/Conclusion abstract derived from
  conclusions, not a stub.
* **Better dashboard**: audience-driven section ordering (academic,
  executive, technical, teaching), evidence-traceability matrix
  (hypothesis → step → figure), per-step appendix surfacing plain-
  language summaries + headline finding + figure with BOTH captions +
  decision, "Outstanding artefacts" panel embedding the latest
  completeness audit.
* **`tool_poster_create`** gains `layout` parameter — `billboard`
  (default, Mike Morrison Better Poster pattern: oversized plain-
  English headline + ammo bar + QR code) or `classic` (IMRAD two-
  column). `audience` profile (academic_conference, symposium, industry,
  teaching) gates copy density and call-to-action.

### Workflow diagram polish
* Hypothesis badges per node (which H's the step touched).
* Inline figure / table counts with ★ marker for a focal figure.
* Headline finding annotation under each step box.
* Chronological timeline bar at the top.
* "⚠ no focal figure yet" inline warning for incomplete steps.

### State schema v4.0 — streamlined for AI consumption
* **One canonical default** (`ResearchLedger._default_state`); drops
  the duplicate in `project_ops`.
* **Legacy field migration** runs on load: `phase` → `pipeline_stage`,
  `project` → `project_name`, `run_id` → `project_id`. Drops vestigial
  `token_budget`, `knowledge_graph_path`, `data_scale_profile`,
  `execution_dag_path`, and per-path `input_data_hashes` mirrors.
* **CTMs externalised** — full blobs in `.os_state/context_transfer_memos/<id>.json`;
  in-state list now stores 3-field stubs only.
* **Slimmer `sys_boot`** — returns short hypothesis statements,
  per-step focal-figure flags, and missing-caption counts so the AI
  spots outstanding artefacts in one call.

## [1.0.0] — Stable release

### Operational safety + ergonomics (post-routing finalization)

* **`tool_route` returns `active_tools`** — a tight 10-15 tool shortlist
  (essentials + the chosen protocol's decomposition tools) so the AI
  focuses its working set instead of triaging all 98 tools every turn.
  `sys_active_tools(protocol_name)` queries the same scope directly.
* **`tool_workflow_dag`** — walks each numbered step's `data/input`
  symlink, derives cross-step dependencies, writes
  `docs/workflow_dag.mermaid` (+ PNG via `mmdc` if available).
  Auto-refreshed on every `sys_path_create` / `sys_path_abandon`.
* **`tool_step_env_lock`** — pins `requirements.txt` +
  `python_version.txt` (+ optional `conda.yaml` + per-step `Dockerfile`)
  inside `workspace/<NN>/environment/`. Each step becomes
  self-contained and reproducible years later even if the global env
  drifts.
* **`tool_task_run` security** — argv[0] validated against
  `runtime.command_allowlist` (default = common interpreters + benign
  coreutils; bypass with `runtime.allow_arbitrary`); shell
  metacharacters refused unless `runtime.allow_shell_meta`; per-task
  CPU / RSS / file-size limits via `setrlimit`; every accepted task
  audited to `workspace/logs/task_audit.log`.
* **Search caching with TTL + 429 backoff** — file cache moved to
  `.os_state/cache/search/<provider>/<hash>.json` with timestamped
  envelopes; 24h default TTL (`runtime.cache_ttl_seconds` to override).
  All literature providers now use a shared `_fetch_json_with_backoff`
  helper that retries on 429 / 5xx and honours `Retry-After`.
  `tool_cache_clear` wipes per-provider or older-than-N-days.
* **Preflight protocol freshness check** — warns when a protocol
  hasn't been touched in 180+ days (uses explicit `last_reviewed` field
  or git mtime). Surfaces the 47-protocol maintenance burden early.

### Routing layer (token-efficient + anti-one-shot)

* **`sys_boot`** — one MCP call returns project state + researcher
  config + protocol history tail + dep inventory + recommended next
  protocol + pause classification + any active plan. Replaces 4-5
  separate calls per session boot; cuts a typical boot from ~5K tokens
  to ~1K.
* **`tool_route(prompt)`** — hierarchical L1 → L2 → L3 picker.
  L1 = `intent_class` (session / discover / plan / execute /
  methodology / literature / synthesize / audit_wrap / memory / review).
  L2 = `sub_intent` within class. L3 = specific protocol. Returns
  ambiguity-aware: if two L3 candidates tie, returns `resolved_level=2`
  + an `ask_user` line for the AI to disambiguate with one researcher
  follow-up.
* **`tool_plan_turn`** — slices the active plan into a `this_turn`
  batch + `next_turn` queue, sized to the researcher's `model_profile`
  (small: 1 step/turn, medium: 3, large: 6, weighted for heavy tools
  like `tool_synthesize` or `tool_audit_reproducibility`). Returns
  `chat_split_recommended` when the remaining plan exceeds what one
  chat should hold; AI then hands off + asks for a fresh chat.
* **`tool_plan_advance` / `tool_plan_clear`** — walk or discard the
  persistent active plan written to `.os_state/active_plan.json`.
* **`sys_tool_describe`** — full description of one tool on demand
  (paired with trimmed `list_tools` defaults, saving ~2K tokens
  permanently per message).
* **`sys_dep_inventory`** — reports which optional extras failed to
  import so the AI knows which tools will work this session.
* **`sys_protocol_get`** now supports `format='summary'` (~300 tokens,
  step headings only), `format='step' step_id='<id>'` (one step body),
  or `format='full'` (whole YAML, ~2-3K tokens).
* **`_router_index.yaml`** — single source of truth for trigger
  phrases, decompositions, intent classes, and sub-intents. Preflight
  validates every entry resolves.

### Resume / handoff / progress / quick review

* **`tool_session_resume`** — reconstructs intent + status after any
  pause (different chat, different AI model, next day) in one call.
* **`tool_progress_digest`** — one-page summary of experiments,
  hypotheses, outputs, citations.
* **`tool_dead_end_lessons`** — pulls reusable lessons from every
  `__DEAD_END` folder so future steps don't repeat past mistakes.
* **`tool_quick_review`** — stages the critical-appraisal skeleton for
  reviewing someone else's paper (orthogonal to the main project).
* **`sys_session_handoff`** now snapshots a checkpoint, captures
  running background tasks + open hypotheses + methods tail + dead-end
  lessons + a "Notes for the next AI" addendum. Fresh AI can pick up
  with just the handoff + AGENTS.md.

### Protocols (47 total)

10-stage main pipeline (`session_boot → project_startup →
domain_analysis → research_design → methodology_selection →
literature_search → analysis_plan → reproducibility →
audit_and_validation → synthesis_paper`) plus 37 on-demand protocols:

* **Guidance**: session_boot, session_resume, project_startup,
  analysis_plan, iterative_planning, dead_end_routing,
  hypothesis_tracking, writing_standards, glossary_update,
  casual_exploration, autopilot, chat_handoff, quick_paper_review.
* **Domain**: domain_analysis, research_design.
* **Methodology**: methodology_selection, research_methods,
  causal_inference_deep, machine_learning, clinical_trials,
  meta_analysis, survey_psychometrics, qualitative_research,
  simulation_studies, replication_study, ablation_study, pilot_study,
  mixed_methods, tool_discovery.
* **Literature**: literature_search, systematic_review,
  evidence_synthesis.
* **Synthesis**: synthesis_paper, synthesis_abstract, synthesis_poster,
  synthesis_dashboard, synthesis_grant, synthesis_report.
* **Writing**: writing_core, writing_methods, writing_citations,
  writing_analysis_log, writing_conclusions, writing_readme.
* **Visualization**: figure_guidelines.
* **Audit + reproducibility**: audit_and_validation, reproducibility.

Every protocol declares `quality_bar`, `expected_outputs`,
`next_protocol`, `on_failure`; ends with the auto-injected
`protocol_completion` step (logs + checkpoints + routes). All have
matching entries in `_router_index.yaml` for hierarchical routing.

### Domain presets (10)

`rct_config`, `epidemiology_observational`, `genomics`, `nlp_benchmark`,
`economic_panel`, `qualitative_research`, `geospatial`, `time_series`,
`survival_analysis`, `psychometric`. Each defines expected columns,
expected file extensions, biases to monitor, suggested protocols, and
reporting standard.

### Tools (94 total)

Three namespaces:

* `sys_*` — workspace, state, paths, checkpoints, config, files, env,
  notifications, session handoff, scratch sandbox, workspace repair,
  boot, dep inventory, tool describe.
* `tool_*` — routing (route, plan_turn, plan_advance, plan_clear),
  search (Crossref / Semantic Scholar / PubMed / arXiv / web),
  literature download, multi-language execution (py / R / julia / bash
  / ipynb / Rmd / qmd), background tasks (real `subprocess.Popen` for
  shared servers), data sample / profile / convert, audits, research
  grounding, intake autofill, mid-flow context injection, synthesis
  (paper / abstract / poster / dashboard / grant / report), citation
  verification, session resume, progress digest, dead-end lessons,
  quick review.
* `mem_*` — append-only methods / analysis / citations / decision /
  hypothesis ledgers (multi-hypothesis tracking).

Dot notation (`sys.state.get`) and legacy tool names auto-rewrite.

### Synthesis quality bars (no hallucinations)

* Every citation in every final output is pulled from real providers,
  verified online, and dropped if unverified.
* Per-output_type caps: abstract 3, poster 6, dashboard 12, report 25,
  paper 40.
* `synthesis_paper` / `_abstract` / `_poster` / `_dashboard` / `_grant` /
  `_report` each have venue-tailored quality minimums.
* `tool_citations_verify` re-verifies a workspace's bibliography on
  demand.

### Auto-intake + mid-flow context

* `tool_intake_autofill` classifies domain, extracts research question
  + hypotheses, rewrites `inputs/intake.md`, fills blank config fields,
  registers hypotheses.
* `tool_context_intake` routes mid-flow file drops into the right
  `inputs/` subfolder; skips scaffold files (AGENTS.md, CLAUDE.md,
  opencode.json, etc.) to avoid noise.

### Robustness

* `tool_workspace_repair` heals missing dirs / corrupted state —
  NEVER deletes.
* Background tasks survive zombies via `waitpid(WNOHANG)` +
  `/proc/<pid>/status` fallback.
* `execute_bash_script` / `_r` / `_julia` propagate non-zero exit
  codes (previously claimed success on every completed run).
* `scratch_list` excludes `.gitkeep` (previously over-counted).
* Scaffold prunes stale `.gitkeep` after populating dirs.

### Runtime awareness

* `runtime.shared_server` + `runtime.long_running_threshold_seconds`
  in `researcher_config`: protocols background long jobs via
  `tool_task_run`, poll with `tool_task_status`, warn before heavy
  compute.

### Multi-language scripts

`.py`, `.R`, `.jl`, `.sh`, `.ipynb`, `.Rmd`, `.qmd` — first-class.

### Codebase organisation

`src/research_os/tools/actions/` has eight domain subpackages
(`state/`, `data/`, `exec/`, `search/`, `research/`, `audit/`,
`synthesis/`, `memory/`) plus two cross-cutting modules flat at the
top (`protocol.py` — YAML loader; `router.py` — sys_boot + tool_route
+ plan_turn + active plan).

Tests live in `tests/{unit,integration,tools}/` — ~180 tests, ~3s
to run. Preflight at `scripts/preflight.py` runs 12 wiring checks
in ~2s.

### CI

GitHub Actions workflow runs ruff + preflight + unit tests on Python
3.11 (fast path), then integration + tools tests on Python 3.10 /
3.11 / 3.12. Lean `[ci]` extras keep installs fast; the build job
validates the wheel ships all 47 protocols + the router index.

### Docs

* `README.md` — 60-second pitch + cheat sheet.
* `docs/WALKTHROUGH.md` — exhaustive 10-day simulated project with
  messy/ranting researcher prompts, every protocol exercised.
* `docs/GUIDE.md` — full reference: routing, tools, protocols.
* `docs/QUICKSTART.md` — 5-minute walkthrough.
* `docs/SETUP.md` — install + per-IDE MCP wiring.
* `docs/RESEARCHER_GUIDE.md` — non-technical user guide.
* `docs/PROTOCOLS.md` — protocol catalog with trigger phrases.
* `docs/TOOLS.md` — tool catalog with example invocations.
* `docs/FAQ.md` — common questions.
* `docs/SETUP_PROMPT.md` — paste-into-any-AI installer prompt.
