# Scenario 4 — Engineering Benchmark Study (Research-OS v1.9.4 usability trace)

**Scenario inputs**

- Hypothesis: "Variant A of quicksort outperforms variants B and C for input sizes >= 10^5 due to better cache locality."
- Data: 3 sorting variants x 5 input sizes (10^3, 10^4, 10^5, 10^6, 10^7) x 10 runs each (150 timing measurements per metric, plus optional cache-miss / instruction counts).
- Engineering pack active (`tool_engineering_*`).
- Expected deliverables: `synthesis/paper.pdf` via Typst venue `ieee_conf`, `synthesis/dashboard.html`, performance-vs-input-size plots with error bars (CIs across the 10 runs), sample-size justified (10 reps adequate? bootstrap / t-test?).

**Trace methodology**

- Fresh agent — no prior Research-OS knowledge.
- Doc-surface only: `README.md`, `docs/*.md`, `templates/*`, `src/research_os/protocols/**/*.yaml`, `CHANGELOG.md`.
- No `.py` reads. No MCP server. Every tool call is simulated using `docs/TOOLS.md` + the protocol's `expected_outputs`.
- Goal: trace empty-project → paper.pdf + dashboard.html and log friction at each turn.

---

## Part 1 — Project setup (turns 1–5)

### Turn 1
- **What I wanted to do.** Start the project; orient as a fresh AI.
- **Tool I called.** `sys_boot` (template `CLAUDE.md`: "first MCP call, regardless of what the researcher asked").
- **Simulated result.** Bundle of `state`, `config`, `protocol_history` (empty), `dep_inventory`, `next_protocol` recommendation, `pause_classification` (cold-start). On a freshly scaffolded project, `has_os_state` is False until `research-os init` runs.
- **Was the result format clear?** yes — `docs/AI_GUIDE.md` lines 24–34 enumerate every key returned.
- **Did I know what to do next?** yes — call `tool_route` next.
- **Friction.** FRICTION/LOW — `docs/START.md` shows `research-os init` as the very first action, but `AI_GUIDE.md` opens with "fire `sys_boot` first" without saying "the researcher must have already run `research-os init` in this folder, otherwise `sys_active_project` will say `has_os_state=False`." A reader-AI on an empty folder would learn this only by failing.
- **Doc gap.** none material — `AI_GUIDE.md` § "Resolving the active project" covers it, but the "first turn pattern" should cross-link there.
- **Time-to-clarity.** ~20s.

### Turn 2
- **What I wanted to do.** Have the researcher scaffold the project.
- **Tool called.** None from MCP — `research-os init` is the CLI command. Researcher runs `mkdir quicksort-bench && cd quicksort-bench && research-os init`.
- **Simulated result.** 7-step interactive wizard collects researcher name, project name, optional domain ("computer science / systems") + research question ("does quicksort variant A win on >=10^5 due to cache locality?"), IDE choice (Claude Code), drops `AGENTS.md`, `inputs/{raw_data,literature,context}/`, `workspace/`, `synthesis/`, `docs/`, `.os_state/`, `inputs/researcher_config.yaml`, MCP configs.
- **Was the result clear?** yes — `docs/START.md` § "Scaffold your first project" maps every drop.
- **Did I know what to do next?** yes — drop the data into `inputs/raw_data/`, write the hypothesis into `inputs/context/`, then say "fill out the intake".
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

### Turn 3
- **What I wanted to do.** Set `model_profile`, `target_venue`, `venue_template`, and `pdf_compile_engine` BEFORE intake so synthesis later picks the right Typst template (`ieee_conf`).
- **Tool called.** Edit `inputs/researcher_config.yaml` directly (`sys_config_set` would also work for single keys).
- **Simulated edit.**
  ```yaml
  research_goal:
    output_types: ["paper", "dashboard"]
    target_venue: "conference"
  writing_preferences:
    citation_style: "ieee"
    venue_template: "ieee_conf"
    pdf_compile_engine: "typst"
  model_profile: "large"      # Opus
  project_tier: "production"
  ```
- **Was the result format clear?** yes — `templates/researcher_config.yaml` is heavily commented; every legal venue value is listed.
- **Did I know what to do next?** yes.
- **Friction.** FRICTION/LOW — `templates/researcher_config.yaml` does NOT list `ieee` as a legal `citation_style` (the comment shows `apa | vancouver | acm | ieee | nature`, so it IS listed — actually fine). But `citation_style` and `venue_template` are decoupled, and the docs do not say which combinations are coherent (does `ieee_conf` Typst template expect `citation_style: ieee` or is APA fine?). Engineering / CS researchers will want this stated.
- **Doc gap.** Suggest a "venue_template × citation_style compatibility matrix" snippet in `docs/VENUE_TEMPLATES.md`.
- **Time-to-clarity.** ~45s.

### Turn 4
- **What I wanted to do.** Land the 150 timing measurements + the hypothesis context + relevant cache-locality literature (Hennessy & Patterson, McIlroy 1999, Sedgewick 1978, BLOG-Z TLBs).
- **Tool called.** Researcher action — `mv timings.csv inputs/raw_data/`, `cp quicksort_variants.{c,py} inputs/context/`, `cp hennessy_patterson.pdf sedgewick_quicksort.pdf inputs/literature/`, `printf '...' > inputs/context/hypothesis.md`.
- **Simulated result.** Inputs landed; `inputs/raw_data/` and `inputs/literature/` are immutable.
- **Was the result format clear?** yes — `docs/START.md` cheatsheet shows the directory contract.
- **Did I know what to do next?** yes — say "fill out the intake".
- **Friction.** FRICTION/LOW — the 3 sub-folders of `inputs/` are clear, but for a benchmark scenario the SOURCE CODE under benchmark (the C / Python implementations of variants A/B/C) is ambiguously placed. It is not "raw_data" (it is the artefact under study), not "literature", not "context" exactly. A small note in `inputs/context/` README about "code under study lives here" would help.
- **Doc gap.** `docs/RESEARCHER_GUIDE.md` does not name a recommended location for "engineering: the implementation under benchmark."
- **Time-to-clarity.** ~30s.

### Turn 5
- **What I wanted to do.** Run intake.
- **Tool called.** Researcher says "fill out the intake". AI calls `tool_route(prompt="fill out the intake")`.
- **Simulated result.** Router returns `intent_class=discover`, `sub_intent=intake`, `primary_protocol=discover/intake` (actual path: there is no `discover/` directory — protocols live under `domain/` and `guidance/`, with intake spread between `tool_intake_autofill` (shortcut) and `guidance/project_startup`). Likely `shortcut_tool=tool_intake_autofill`, `complexity=low`.
- **Was the result format clear?** PARTIALLY — `AI_GUIDE.md` lists `discover` as a top-level category, but the protocols/ folder has NO `discover/` directory. The intake mechanism is the `tool_intake_autofill` shortcut tool, not a YAML protocol.
- **Did I know what to do next?** yes — call `tool_intake_autofill`. Inferred from `docs/TOOLS.md` line 124.
- **Friction.** FRICTION/MEDIUM — Doc says "discover is a protocol category" but the FS has no folder for it. A fresh AI grepping `src/research_os/protocols/discover/` finds nothing and risks reading `src/` source to understand. **This is a doc-vs-implementation drift.**
- **Doc gap.** `docs/AI_GUIDE.md` § "Protocol categories" lists `discover` but the codebase ships intake-as-a-tool. Either add a `discover/` protocol or remove `discover` from the category table.
- **Time-to-clarity.** ~60s.

**Onboarding-friction count (first 5 turns):** 4 (1 LOW T1, 1 LOW T3, 1 LOW T4, 1 MEDIUM T5).

---

## Part 2 — Hypothesis + planning (turns 6–10)

### Turn 6
- **What I wanted to do.** Have the intake digest the 150-row timings CSV + the hypothesis note + the literature PDFs into `inputs/intake.md` and `docs/research_overview.md`.
- **Tool called.** `tool_intake_autofill()`.
- **Simulated result.** Writes `inputs/intake.md` (data shape, columns: `variant`, `n`, `replicate`, `wall_time_ns`; 150 rows; 3 variants x 5 sizes x 10 reps), `docs/research_overview.md` (domain: systems / algorithms; question; hypotheses), `.os_state/state.json` (active_hypotheses tracker). Engineering pack detector fires (signals: C source under `inputs/context/`, timing-heavy CSV columns, "cache locality" in hypothesis prose) and registers the `engineering` pack active.
- **Was the result format clear?** yes — outputs paths are deterministic.
- **Did I know what to do next?** yes — register hypothesis formally + route.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~15s.

### Turn 7
- **What I wanted to do.** Record the hypothesis with status `proposed` so downstream synthesis can group findings by hypothesis.
- **Tool called.** `mem_hypothesis_add(text="Variant A outperforms B/C at n>=1e5 due to better cache locality", status="proposed")` or `mem_log(kind="hypothesis", ...)`.
- **Simulated result.** Appends to `.os_state/state.json` `active_hypotheses[]` + `workspace/analysis.md`. Returns `hypothesis_id=H1`.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — call `tool_route` with the actual workflow ask.
- **Friction.** FRICTION/LOW — `mem_hypothesis_add` AND `mem_log(kind='hypothesis')` both exist. `TOOLS.md` line 197 says `mem_log` replaces `mem_{methods_append, decision_log, hypothesis_update, analysis_log}` but NOT `mem_hypothesis_add`. Slightly confusing.
- **Doc gap.** `mem_log`'s `kind` enum vs the older per-kind tools needs one canonical "use these, not those" table.
- **Time-to-clarity.** ~30s.

### Turn 8
- **What I wanted to do.** Route the actual research ask: "benchmark quicksort variants A vs B vs C across input sizes 10^3 … 10^7."
- **Tool called.** `tool_route(prompt="benchmark quicksort variants A vs B vs C head-to-head across input sizes; quantify when A wins")`.
- **Simulated result.** Per `_router_index.yaml` and the explicit `trigger` block in `methodology/method_comparison.yaml` ("benchmark these methods", "head-to-head", "bake-off", "which model is best") this resolves to `intent_class=methodology`, `sub_intent=comparison`, `primary_protocol=methodology/method_comparison`, `complexity=high` (multi-step + N methods + per-method literature pass + dashboard), `shortcut_tool=null`, `decomposition=[...]`, `active_plan` persisted to `.os_state/active_plan.json`.
- **Was the result format clear?** yes — `AI_GUIDE.md` § "Anti-patterns" explicitly tells me how to handle `complexity=high`.
- **Did I know what to do next?** yes — `tool_plan_turn` then iterate `tool_plan_advance`.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~20s.

### Turn 9
- **What I wanted to do.** Pull the first batch of plan steps sized to `model_profile=large` (6 steps/turn).
- **Tool called.** `tool_plan_turn()`.
- **Simulated result.** Returns `this_turn=[name_the_methods_and_the_task, ground_each_candidate, pre_register_the_comparison, implement_each_method, tune_within_folds_not_on_test, evaluate_with_uncertainty]`, `chat_split_recommended=false` (still within context budget for large), `next_batch=[build_the_comparison_dashboard, name_the_winner_honestly, capture_generalisability_ceiling]`.
- **Was the result format clear?** yes — `AI_GUIDE.md` § "session pattern" step 3.
- **Did I know what to do next?** yes — work through `this_turn` in order, `tool_plan_advance` between each.
- **Friction.** FRICTION/LOW — for an engineering benchmark, step `tune_within_folds_not_on_test` is a confusing fit. There is no train/val/test in a deterministic sorting microbenchmark; the "tuning" question is about JIT warmup, CPU governor, cache flushing between runs. The protocol is ML-flavoured even though `method_comparison` is named generically.
- **Doc gap.** `methodology/method_comparison.yaml` should have a "non-statistical benchmarks (latency, throughput, memory) — read these steps as: ensure equal warm-up, same governor, same RNG seed, same data ordering, same isolation" sub-section. Currently the editorial-voice rules speak entirely in ML / statistical-test vocabulary.
- **Time-to-clarity.** ~90s (longest in this batch — had to map "fold" → "warm-up run" by analogy).

### Turn 10
- **What I wanted to do.** Inspect the protocol's expected_outputs to ensure I know the artefact targets.
- **Tool called.** `sys_protocol_get(format='summary', protocol='methodology/method_comparison')`.
- **Simulated result.** ~300-token summary listing step headings + `quality_bar` keys: `same_split_same_features_same_budget`, `uncertainty_reported_alongside_winner`, `paired_statistical_test_named_and_cited`, `multiple_comparison_correction_when_n_gt_2`, `baseline_included`, `no_winner_overstated_beyond_dataset`. `next_protocol=guidance/analysis_plan`.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — start step 1.
- **Friction.** FRICTION/LOW — `quality_bar.baseline_included: true` for an engineering benchmark of 3 sorting variants is interpreted ambiguously. The "baseline" should obviously be `std::sort` / `qsort` / `numpy.sort`. The protocol doesn't say so for benchmark-of-implementations contexts.
- **Doc gap.** `methodology/method_comparison.yaml` step 1 (`name_the_methods_and_the_task`) names baselines for ML tasks (logistic regression, mean predictor) but no analogue for systems benchmarks (stdlib sort, single-threaded reference).
- **Time-to-clarity.** ~30s.

---

## Part 3 — Per-step execution (turns 11–25)

The 9 protocol steps map to numbered workspace steps. I'll trace the canonical inner loop for each (`step_pipeline_define → step_pipeline_run → tool_audit_step_completeness → tool_audit_step_literature → tool_step_complete`) but only narrate the first two fully — afterward I summarise.

### Turn 11 — Step 01: name_the_methods_and_the_task
- **What I wanted to do.** Lock in: TASK=wall-time-vs-input-size; METHODS={variant_A_tiled_blocked, variant_B_classic_lomuto, variant_C_introsort_yaroslavskiy}; BASELINE=`std::sort` (libstdc++); OUTCOME=`wall_time_ns` per (variant, n, replicate).
- **Tool called.** `sys_path(operation='create', name='01_methods_and_task')` then `sys_file_write('workspace/01_methods_and_task/methods.md', ...)`.
- **Simulated result.** New numbered workspace folder; `methods.md` lists 3 variants + baseline + outcome + RNG seed (input array generated via `numpy.random.default_rng(seed=42)`).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — call `tool_audit_step_completeness` and `tool_step_complete`.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~20s.

### Turn 12 — Step 01: completeness gate
- **Tool called.** `tool_audit_step_completeness(step_id='01_methods_and_task')`.
- **Simulated result.** Per `TOOLS.md` line 132: WARNs on missing focal figure (this step has no figure — it is a planning step). v1.4.0+ BLOCKs on missing `.summary.md`. So step 01 likely BLOCKS until I add a figure or a `.summary.md` that says "this is a non-figure planning step."
- **Was the result format clear?** PARTIALLY — `TOOLS.md` says "every active step needs a focal figure", but methods-spec steps don't naturally produce one.
- **Did I know what to do next?** YES but reluctantly — author a placeholder figure (e.g. an experimental-design diagram via `mermaid`).
- **Friction.** FRICTION/MEDIUM — fresh AI may assume completeness gates only apply to analytical steps, then get BLOCKED. Doc should distinguish "design/planning steps (waiver-eligible)" vs "analysis steps".
- **Doc gap.** `audit_step_completeness` should document its waiver path for non-figure steps (or auto-detect step type).
- **Time-to-clarity.** ~120s.

### Turn 13 — Step 02: ground_each_candidate (literature pass)
- **What I wanted to do.** Per `method_comparison` step 2: literature for each of {tiled, classic Lomuto, Yaroslavskiy/introsort, std::sort baseline} — surface canonical references, default hyperparameter ranges, pitfalls (branch prediction, TLB misses, prefetching).
- **Tool called.** `tool_research_method(query="tiled blocked quicksort cache locality")` then 3 more for each candidate; then `tool_literature_search_and_save` to drop PDFs into `workspace/02_ground/literature/`.
- **Simulated result.** 5–10 hits per query from Semantic Scholar / arXiv / ACM DL; saves McIlroy 1999, Bentley & McIlroy 1993, Yaroslavskiy 2009, Sedgewick 1978, Hennessy & Patterson Ch. 5.
- **Was the result format clear?** yes — `TOOLS.md` line 161 is explicit, AI_GUIDE.md anti-pattern "Pick a method from training memory" reinforces.
- **Did I know what to do next?** yes — write `findings_vs_literature.md`.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~30s.

### Turn 14 — Step 02: per-step literature gate
- **Tool called.** `tool_audit_step_literature(step_id='02_ground')`.
- **Simulated result.** Per `TOOLS.md` line 133: BLOCKs if `findings_vs_literature.md` missing, any claim lacks a Verdict, etc. Step 02 itself has no findings YET (it is literature grounding, not result generation). So this gate also blocks — unless I author a stub `findings_vs_literature.md` whose "Findings" section says "this step grounds the methods; findings come from steps 03–08."
- **Was the result format clear?** PARTIALLY — `TOOLS.md` says "BLOCKs on stub `## Findings`", which seems to be exactly what a grounding step needs.
- **Did I know what to do next?** YES, but I need to use `override_literature_gate=true + rationale="grounding step; no claims"`. Doc says this is the escape hatch.
- **Friction.** FRICTION/MEDIUM — second instance of "gate too strict for non-analysis steps." Pattern: per-step audits assume every step produces a figure + a claim + a literature contrast. Planning / grounding / scaffolding steps don't.
- **Doc gap.** Per-step gates should classify step intent (plan / ground / analyse / visualise / synthesise) and only apply the relevant gates.
- **Time-to-clarity.** ~90s.

### Turn 15 — Step 03: pre_register_the_comparison
- **What I wanted to do.** Author `workspace/03_prereg/comparison_plan.md` per the protocol's template: TASK, 4 METHODS (3 variants + baseline) with init hyperparam ranges, SPLIT (input sizes are deterministic; "split" = which sizes are train-style warmup vs measured), PRIMARY metric (median wall_time_ns), SECONDARY (cache-miss rate, instruction count), STATISTICAL TEST for differences (paired Wilcoxon across the 10 reps at each n, with Bonferroni across the 3 pairwise contrasts × 5 sizes = 15 tests), STOPPING RULE, BUDGET.
- **Tool called.** `sys_file_write('workspace/03_prereg/comparison_plan.md', ...)` then `tool_preregister_freeze` (high stakes is the user's call; for an internal benchmark, I'd skip the freeze).
- **Simulated result.** Plan file written; `.os_state/state.json.preregistration_locked=false` (not frozen).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** FRICTION/LOW — `tool_preregister_freeze` not in `TOOLS.md`'s main table; researcher might miss it.
- **Doc gap.** none material.
- **Time-to-clarity.** ~45s.

### Turn 16 — Step 04: implement_each_method
- **What I wanted to do.** One script per variant + baseline. Same data input, same preprocessing (input array generation), same RNG seed, same input-size sweep. The 150 measurements ALREADY exist in `inputs/raw_data/timings.csv` — so the "implementation" step here is REPLAYING the existing measurement rather than running fresh.
- **Tool called.** `tool_step_pipeline_define(step_id='04_implement', nodes=[ingest, validate, summarise_per_variant])` then `tool_step_pipeline_run(step_id='04_implement')`.
- **Simulated result.** Pipeline DAG: `ingest(timings.csv) → validate(150 rows, no nulls, expected schema) → summarise(group by variant×n, mean/median/p95/std/CI)`. Cached on content hash.
- **Was the result format clear?** yes — `TOOLS.md` lines 271–273 describe `tool_step_pipeline_*` cleanly.
- **Did I know what to do next?** yes.
- **Friction.** FRICTION/LOW — the protocol assumes you write the methods (you generate predictions); my scenario is "measurements already exist; replay and analyse." The doc doesn't acknowledge this archetype.
- **Doc gap.** `method_comparison.yaml` lacks a "imported measurements" archetype (`mid_pipeline_entry` covers this for the project as a whole but not for `method_comparison` per-step semantics).
- **Time-to-clarity.** ~60s.

### Turn 17 — Step 05: tune_within_folds_not_on_test
- **What I wanted to do.** N/A for deterministic sorts — there are no folds. Skip via `tool_plan_advance(skip_reason="non-statistical benchmark; no tuning loop")`.
- **Tool called.** `tool_plan_advance(skip_reason=...)`.
- **Simulated result.** Step 05 marked `skipped` in `active_plan.json`. Logged to `workspace/logs/plan_skips.md`.
- **Was the result format clear?** PARTIALLY — `tool_plan_advance` is described but its `skip_reason` parameter isn't called out in `TOOLS.md` table.
- **Did I know what to do next?** yes.
- **Friction.** FRICTION/LOW — skip-with-reason mechanic underdocumented.
- **Doc gap.** Add `skip_reason` to `tool_plan_advance` description in `TOOLS.md`.
- **Time-to-clarity.** ~60s.

### Turn 18 — Step 06: evaluate_with_uncertainty (the heart of the analysis)
- **What I wanted to do.** Per-variant per-n: median wall_time_ns + 95% CI (bootstrap with B=10000 over the 10 reps); pairwise A-vs-B, A-vs-C, B-vs-C paired differences at each n with bootstrap CI on the difference; paired Wilcoxon signed-rank p-values + Bonferroni-corrected (15 tests). Also: cache-miss-rate analysis (the hypothesis-mechanism check).
- **Tool called.** `tool_step_pipeline_define(step_id='06_evaluate', nodes=[per_variant_summary, pairwise_diff, bootstrap_ci, paired_wilcoxon, multiple_comp_correct, cache_miss_mechanism])`, then `tool_step_pipeline_run`.
- **Simulated result.** Produces per-method evaluation JSON + a 3x5 stats table + a mechanism summary linking variant-A's win at n>=10^5 to lower cache miss rate (if the hypothesis holds).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — build the figure.
- **Friction.** FRICTION/LOW — `method_comparison` editorial voice repeatedly says "Use the paired test the FIELD uses." For systems / micro-benchmarking the field convention is non-parametric (Mann-Whitney / Wilcoxon) + plots over parametric tests because timing distributions are heavy-tailed. The protocol leaves the AI to figure that out unaided.
- **Doc gap.** `uncertainty_visualization` and `method_comparison` could cross-link a one-paragraph "benchmarking measurement statistics" cheat-sheet.
- **Time-to-clarity.** ~30s.

### Turn 19 — Step 07: build_the_comparison_dashboard (the figures)
- **What I wanted to do.** Plot: (1) wall-time-vs-input-size on log-log axes, one line per variant, ribbon = bootstrap 95% CI from the 10 reps; (2) winner-summary dot-and-whisker at n=10^7 (the hypothesis target); (3) cache-miss-rate overlay tying the mechanism to the win.
- **Tool called.** AI writes a matplotlib script via `tool_python_exec`. Then `tool_figure_palette(scheme="okabe_ito")` to pick CVD-safe colours. Then `tool_audit_figure_full(figure_path=...)` to verify DPI / sidecars / SVG companion.
- **Simulated result.** 3 figures land in `workspace/07_figures/outputs/figures/` each with `.caption.md`, `.summary.md`, `.svg`. `tool_audit_figure_full` passes if DPI >= 300, both sidecars present, SVG present, no text-overlap heuristic flag.
- **Was the result format clear?** yes — `docs/TOOLS.md` § "What's new in 2.0 — visualization" explicitly tells me Research-OS does NOT ship a chart-builder and I write the plot script.
- **Did I know what to do next?** yes.
- **Friction.** FRICTION/LOW — `tool_figure_caption_synthesise` requires `.caption.md` to exist before it can write `.summary.md`. Order matters; no protocol step says "caption first, then summary."
- **Doc gap.** `visualization/figure_guidelines` could spell out the caption → summary order.
- **Time-to-clarity.** ~30s.

### Turn 20 — Step 07: per-step audits + completeness gate
- **Tool called.** `tool_audit_step_completeness(step_id='07_figures')` then `tool_audit_step_literature(step_id='07_figures')`.
- **Simulated result.** Both pass — focal figure present, captions + summaries present, `findings_vs_literature.md` written with verdicts AGREES (e.g., Sedgewick 1978 predicts A wins on locality-friendly inputs) / EXTENDS (we extend his result to n=10^7).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~15s.

### Turn 21 — Step 08: name_the_winner_honestly
- **What I wanted to do.** Author `workspace/08_winner/conclusions.md > Findings`: variant A wins at n>=10^5 by 12% (median, bootstrap CI [9%, 16%]) and the cache-miss differential explains it (Pearson r between speedup and miss-rate-reduction across input sizes = 0.92). Honesty: variant A LOSES at n<=10^4 (overhead of blocking dominates); the win is not universal.
- **Tool called.** `sys_file_write('workspace/08_winner/conclusions.md', ...)` + `mem_hypothesis_update(id='H1', status='supported_with_qualifications', evidence_step='08_winner')`.
- **Simulated result.** Hypothesis tracker updated; conclusions written.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~20s.

### Turn 22 — Step 09: capture_generalisability_ceiling
- **What I wanted to do.** Limitations paragraph: single CPU architecture (x86-64 Skylake), single input distribution (uniform random ints), single language runtime, GCC 13.2. Findings about cache locality may not transfer to AArch64 / Apple Silicon, to nearly-sorted inputs, to long string keys.
- **Tool called.** `sys_file_write('workspace/08_winner/conclusions.md', append=True, body="## Limitations\n...")`.
- **Simulated result.** Limitations appended.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — engineering pack tools (requirements matrix, FMEA, fault tree) are AVAILABLE but not required by the protocol. None of the per-step audits enforce them.
- **Friction.** FRICTION/MEDIUM — the "Engineering pack active" flag did fire on intake, but the `method_comparison` protocol never branches to use ANY engineering pack tool. The pack tools (`tool_engineering_fault_tree_render`, `_fmea_render`, `_requirements_matrix`) are visible but no protocol points to them in the benchmark workflow. They feel orphaned.
- **Doc gap.** `methodology/method_comparison.yaml` for engineering-pack-active projects could optionally recommend `tool_engineering_requirements_matrix` to map hypothesis → measurements → expected effect → observed. Right now the pack is decorative.
- **Time-to-clarity.** ~60s.

### Turn 23 — Step-complete on all 9 steps
- **Tool called.** `tool_step_complete(step_id=...)` per step.
- **Simulated result.** Each step's `summary.yaml` + `conclusions.md` finalised; `.os_state/state.json` step ledger marked complete.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — `tool_audit_quality_full`.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

### Turn 24 — `tool_plan_advance` ends the active_plan
- **Simulated result.** `active_plan.json` cleared; `next_protocol` per the protocol footer is `guidance/analysis_plan`. But the natural next step in our journey is audit + synthesis, not re-planning.
- **Was the result format clear?** PARTIALLY.
- **Did I know what to do next?** PARTIALLY — `next_protocol: guidance/analysis_plan` is a footer hint, not a hard pointer. For a benchmark with the hypothesis already supported, going back to analysis_plan feels wrong. The right path is `audit/audit_and_validation` then `synthesis/synthesis_paper`. The doc doesn't make that clear.
- **Friction.** FRICTION/MEDIUM — `next_protocol` is sometimes a "loopback for iteration", sometimes a "next mandatory step" — semantics aren't consistent across the catalogue.
- **Doc gap.** `docs/PROTOCOL_DOCTRINE.md` should explain `next_protocol` semantics (iterate-back vs forward-default).
- **Time-to-clarity.** ~60s.

### Turn 25 — Hypothesis status sync
- **Tool called.** `mem_hypothesis_list()` to confirm `H1.status=supported_with_qualifications` is what synthesis will pick up.
- **Simulated result.** 1 hypothesis returned.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

---

## Part 4 — Per-step literature gate (interleaved summary)

I interleaved `tool_audit_step_literature` after each analysis step (turns 12, 14, 20). The recurring issue: **the gate is calibrated for hypothesis-test analytical steps and over-fires on planning / grounding / placeholder steps.** Override path via `override_literature_gate=true + rationale=...` is documented but I had to invoke it twice in 9 steps. That ratio in production would be irritating.

---

## Part 5 — Audit + synthesis (turns 26–35)

### Turn 26 — `tool_audit_quality_full`
- **Tool called.** `tool_audit_quality_full()`.
- **Simulated result.** Per `TOOLS.md` § "Quality auditors": bundles `tool_audit_step_completeness + tool_audit_code_quality + tool_audit_claims + tool_audit_prose + tool_citations_verify + tool_preregister_diff` and writes `workspace/logs/audit_report.md` with GREEN / YELLOW / RED. Likely GREEN-with-2-YELLOWs (the 2 override_literature_gate overrides surface here, and `preregister_diff` flags that we didn't `tool_preregister_freeze`, just wrote the plan).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

### Turn 27 — `tool_route("draft the paper for an IEEE conference")`
- **Simulated result.** `intent_class=synthesize, sub_intent=paper, primary_protocol=synthesis/synthesis_paper, complexity=high` (multi-turn enforcement; protocol forces ONE section per researcher prompt).
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — "outline the paper" as the first synthesis prompt.
- **Friction.** FRICTION/LOW — the protocol's multi-turn pattern means the researcher must drive 7-10 prompts to get a paper. For a focused benchmark study with the hypothesis already settled, this is heavyweight. Autopilot mode bypasses but the docs don't loudly say so.
- **Doc gap.** `START.md` Cheatsheet should call out: "for a single-author short paper, `interaction.autonomy_level: autopilot` lets the AI chain sections."
- **Time-to-clarity.** ~30s.

### Turn 28 — Outline + per-section drafts (compressed)
- **Tools.** `tool_synthesize(section='outline')` → `tool_synthesize(section='methods')` → `_results` → `_discussion` → `_introduction` → `_abstract` → `_title_workshop`. Each call sets the section flag; the protocol enforces no chaining without autopilot.
- **Simulated result.** `synthesis/outline.md`, `synthesis/paper.md` accumulates sections. Citation auto-verify via `tool_citations_verify` happens in `final_assembly`.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none beyond turn 27's volume concern.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s/section.

### Turn 29 — `tool_synthesis_preview` before compile
- **Tool called.** `tool_synthesis_preview(mode='full')`.
- **Simulated result.** Predicts ~3200 words across IMRAD, 8 figures (3 focal + 5 step figures curated via `tool_synthesis_curate_figures`), 18 citations, 1 table. Gap warnings: "abstract is 180 words; quality_bar requires [200, 300]" → I extend the abstract.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~15s.

### Turn 30 — `tool_paper_compile_typst`
- **Tool called.** `tool_paper_compile_typst(venue_template='ieee_conf')`.
- **Simulated result.** Produces `synthesis/paper.typ` then `synthesis/paper.pdf` via Typst. **Success — milestone reached.**
- **Was the result format clear?** yes — `TOOLS.md` line 151 names the legal venue values; `ieee_conf` is one.
- **Did I know what to do next?** yes — build the dashboard.
- **Friction.** FRICTION/LOW — `templates/typst/` directory exists but I cannot verify (without reading `src/`) which fields the `ieee_conf` template requires for IEEE-specific metadata (author affiliations, IEEE keywords block, copyright footer). If the template is missing a field, would compile fail or silently default?
- **Doc gap.** `docs/VENUE_TEMPLATES.md` (likely present — referenced but not read here) should list required metadata per template.
- **Time-to-clarity.** ~30s.

### Turn 31 — `tool_route("build the dashboard")` → `tool_dashboard_create`
- **Tool called.** `tool_route("build a dashboard for this benchmark")` resolves to `synthesis/synthesis_dashboard`; shortcut tool `tool_dashboard_create`.
- **Simulated result.** Single-file `synthesis/dashboard.html`. Per `synthesis_dashboard.yaml`: 10 universal sections; figures grouped by hypothesis (H1 only); hover-lightbox SVGs; inline summaries. **Success — milestone 2 reached.**
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — content audit.
- **Friction.** none.
- **Doc gap.** "Dashboard v2" language in the user request — `synthesis_dashboard.yaml` doesn't version itself v1/v2. Unclear what "v2" means relative to docs.
- **Time-to-clarity.** ~20s.

### Turn 32 — `tool_audit_dashboard_content` + `tool_dashboard_reviewer_sim`
- **Simulated result.** Content gates: numeric grounding (every number ties to `workspace/.../eval.json`), figure-to-text proximity OK, per-section substantiveness OK, WCAG 2.2 AA pass, print stylesheet sanity OK, 5-minute reviewer simulator: extracts "variant A wins 12% on >=10^5 due to cache locality" — headline finding recoverable.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

### Turn 33 — `audit/pre_submission_checklist`
- **Tool called.** `tool_route("is this ready to submit")` → `audit/pre_submission_checklist`.
- **Simulated result.** Final GREEN / YELLOW / RED gate. Resurfaces the 2 override_literature_gate bypasses + the unfrozen preregistration. Researcher confirms each.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~15s.

### Turn 34 — `tool_audit_coherence` cross-check
- **Tool called.** `tool_audit_coherence()`.
- **Simulated result.** Verifies every paragraph in `synthesis/paper.md` Discussion / Results / Intro maps back to a step's `conclusions.md`. Pass.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

### Turn 35 — `sys_session_handoff`
- **Tool called.** `sys_checkpoint_create + sys_session_handoff`.
- **Simulated result.** Handoff doc written; running tasks empty; project state preserved.
- **Was the result format clear?** yes.
- **Did I know what to do next?** yes — done.
- **Friction.** none.
- **Doc gap.** none.
- **Time-to-clarity.** ~10s.

---

## Part 6 — Cross-checks + sign-off

| Cross-check | Status | Notes |
|---|---|---|
| `paper.pdf` produced via `tool_paper_compile_typst` (`ieee_conf`) | YES (T30) | Workflow confirms compile path is documented. |
| `dashboard.html` produced via `tool_dashboard_create` | YES (T31) | Single-file offline HTML per `TOOLS.md` line 154. |
| Performance plots with CI ribbons | YES (T19) | Bootstrap CI from the 10 reps; `tool_audit_figure_full` enforces DPI + sidecars. |
| Sample size justified | PARTIAL | `methodology/power_analysis` would have been the right protocol but `method_comparison` doesn't loop into it; the 10-rep adequacy gets a paragraph in the comparison_plan.md (T15) but no formal power calc. |
| Engineering pack tools used | NO | Pack flag fired (T6) but no protocol invokes the pack tools for this scenario. |
| Per-step literature gate satisfied | YES with 2 overrides | Override pattern documented; pre-submission audit resurfaces. |
| Hypothesis tracker updated | YES (T21) | `H1=supported_with_qualifications`; surfaces in dashboard "Findings by hypothesis" section. |
| Preregistration | written but NOT frozen | Acceptable for internal benchmark; `pre_submission_checklist` flagged. |

---

## Part 7 — Top 5 friction points

1. **MEDIUM — `discover/` protocol category named in docs but the FS has no `discover/` directory.** A fresh AI grepping the protocols tree to "find the intake protocol" finds nothing and risks reading `src/` source. *Fix:* either ship a `discover/` directory with a `discover/intake.yaml` placeholder that points at `tool_intake_autofill`, or remove `discover` from `AI_GUIDE.md` § "Protocol categories" and list intake as a shortcut-tool-only entry.

2. **MEDIUM — Per-step audits (completeness + literature) over-fire on non-analysis steps.** Planning / grounding / scaffolding steps don't naturally produce a focal figure or a findings claim, so `tool_audit_step_completeness` and `tool_audit_step_literature` BLOCK and force `override_literature_gate=true` invocations. *Fix:* classify step intent (plan / ground / analyse / visualise / synth) at step-create time and apply only the relevant gates; auto-waive figure + findings gates for plan/ground steps.

3. **MEDIUM — `methodology/method_comparison` reads as ML-flavoured; engineering benchmarks have to translate the vocabulary.** "Fold", "test set", "hyperparameter trial budget", "ROC vs PR" don't map cleanly to deterministic-microbenchmark land. The AI infers the mapping unaided. *Fix:* add an "engineering / systems benchmarks" sub-section to `method_comparison.yaml` describing the analogous concepts (warm-up runs, CPU governor, isolation, RNG-seed for inputs, paired Wilcoxon on heavy-tailed timings, log-log plots).

4. **MEDIUM — Engineering pack is decorative for the benchmark workflow.** Pack-detection fires on intake but no protocol routes into `tool_engineering_fault_tree_render` / `_fmea_render` / `_requirements_matrix` for a benchmark study. The pack feels orphaned. *Fix:* `method_comparison.yaml` (when engineering pack active) should optionally suggest `tool_engineering_requirements_matrix` to map hypothesis → measurement → expected → observed.

5. **MEDIUM — `next_protocol` semantics ambiguous.** `method_comparison.next_protocol: guidance/analysis_plan` looks like "the next mandatory step" but is actually "the loop-back protocol for iteration." On hypothesis-supported, the natural next step is `audit/audit_and_validation` → `synthesis/synthesis_paper`. *Fix:* `docs/PROTOCOL_DOCTRINE.md` should explain `next_protocol` as either `forward_default` or `iterate_back`, and the YAML schema should require the author to label which.

---

## Part 8 — Top 5 doc / guidance gaps

1. **"Code under benchmark" placement is undefined.** `inputs/raw_data/` (data), `inputs/literature/` (papers), `inputs/context/` (notes) — but where does the C / Rust / Python source that is the *subject* of the benchmark live? Add a one-line note in `docs/RESEARCHER_GUIDE.md` § "Where files go": `inputs/context/code/` for code-under-study, with provenance pointer.

2. **`venue_template` × `citation_style` compatibility matrix missing.** `templates/researcher_config.yaml` lists legal values for each independently; a 9×5 matrix in `docs/VENUE_TEMPLATES.md` (`ieee_conf` × `ieee`, etc.) would prevent silent mismatches.

3. **`mem_log` vs `mem_hypothesis_add` ambiguity.** `TOOLS.md` says `mem_log` replaces several `mem_*` calls but lists `mem_hypothesis_add` as separate. A canonical "use these, not those" table would help.

4. **Sample-size justification has no clear entry point from `method_comparison`.** For an engineering benchmark, "10 reps adequate?" needs an answer. `methodology/power_analysis` exists but `method_comparison` doesn't link to it. Add: "for non-statistical benchmarks, justify n_reps via a coefficient-of-variation calc; cite `methodology/power_analysis` if formal."

5. **`tool_plan_advance(skip_reason=...)` parameter undocumented in `TOOLS.md`.** I inferred it exists from the protocol skip pattern; a fresh AI without that intuition would not know to skip cleanly.

---

## Part 9 — Top 5 things that worked well

1. **`tool_route` triggers on `method_comparison` are excellent.** "benchmark these methods", "head-to-head", "bake-off", "horse race", "shoot-out", "which model is best" — comprehensive vocabulary capture. A researcher will land on the right protocol whichever phrase they use.

2. **`docs/START.md` is genuinely lean and complete for first-time setup.** The cheatsheet ("what you get out of the box", "where files go", "autonomy slider", "prompts by phase") is the right altitude. A fresh researcher gets to "I know what to type" in under 15 minutes.

3. **`docs/AI_GUIDE.md` § "session pattern" is the right level of abstraction.** Two MCP calls on first turn, skip on subsequent, complexity routing. The fresh-AI cognitive load is genuinely low.

4. **`method_comparison.yaml` editorial voice is opinionated and correct.** "Equal compute, equal information," "uncertainty around point estimates is bigger than researchers think," "pre-register the metric" — these rules are exactly what a benchmark needs. The protocol is methodologically rigorous even when the ML-flavour vocabulary slightly trips up the engineering case.

5. **Quality gates are real teeth, not paperwork.** `tool_audit_step_completeness`, `tool_audit_step_literature`, `tool_audit_quality_full`, `tool_audit_dashboard_content`, `tool_dashboard_reviewer_sim`, `pre_submission_checklist` — six independent gates, each surfacing a different failure mode, each with documented override + rationale logging. The "every override resurfaces at pre-submission" pattern is a thoughtful design.

---

## Part 10 — Final rating + rationale

**Rating: 7/10**

The workflow IS complete and DOES reach paper.pdf + dashboard.html for this scenario. The protocol catalogue + audit gate stack are genuinely strong. The friction is concentrated in three places: (1) ML-flavoured vocabulary in a protocol that is supposed to be field-general, (2) per-step gates over-fire on non-analysis steps and force overrides, (3) the engineering pack is decorative — it fires on detection but never gets called by the benchmark workflow.

A small set of fixes (label step intent at create time; add an engineering / systems sub-section to `method_comparison`; cross-link the engineering pack tools from `method_comparison` decomposition; clarify `next_protocol` semantics) would push this to 9/10 for the engineering-benchmark scenario.

---

## Part 11 — Onboarding-friction count (first 5 turns)

**4** (3 LOW + 1 MEDIUM). Distribution:

- T1: LOW — sys_boot pre-requisites under-stated for empty-folder cold-start
- T3: LOW — venue_template × citation_style compatibility not surfaced
- T4: LOW — code-under-benchmark placement undefined
- T5: MEDIUM — `discover/` category in docs but no `discover/` directory

---

## Part 12 — Milestones reached

- **paper.pdf step reached?** YES — turn 30, `tool_paper_compile_typst(venue_template='ieee_conf')`.
- **dashboard.html step reached?** YES — turn 31, `tool_dashboard_create()` after `synthesis/synthesis_dashboard` routing.
- **End-to-end workflow validated for engineering benchmark archetype?** YES, with the documented friction.
