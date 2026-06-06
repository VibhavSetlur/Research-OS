# Scenario 1 — Computational Biology: RNA-seq Differential Expression

**Validation pass:** Research-OS v1.9.4 — INITIAL VALIDATION (fresh-agent doc-surface walkthrough).
**Date:** 2026-06-05.
**Hypothesis under test:** *"LPS treatment induces immune-response gene programs in mouse microglia."*
**Data assumed in `inputs/`:** GSE-like bulk RNA-seq count matrix (gene × sample), 6 treatment + 6 control samples, sample metadata, optional gene annotation file. Mixed R + Python expected (DESeq2 in R for DE; Python for plotting / GSEA wrappers).
**Deliverables expected:** `synthesis/paper.pdf` (generic_two_column Typst), `synthesis/dashboard.html` (explore mode), volcano plot + heatmap + GSEA bar chart traceable through workspace provenance.

**Method:** I role-play a fresh AI agent that has just been dropped into a freshly scaffolded Research-OS project. I read only the docs and templates that an end-user-facing AI would read (per the validation constraints) and I SIMULATE every MCP tool call by looking up what each tool's docs say it returns. When I cannot determine the answer from the documentation, I log a doc gap.

---

## Section 1 — Project setup (turns 1-5)

### Turn 1
- **What I wanted to do:** Orient myself. The user has just opened the empty folder in Claude Code. They send: *"i dropped my microglia RNA-seq data in inputs/ — i want to test whether LPS induces immune-response genes."*
- **Tool I called:** `sys_boot` (per `templates/AGENTS.md` + `templates/CLAUDE.md` "FIRST MCP call, first turn only").
- **Simulated result:** The docs say `sys_boot` returns `state + researcher_config + protocol history tail + dep inventory + recommended next protocol + pause classification + any active plan`. For a fresh project I would expect: empty state, default `researcher_config` (auto-created on `research-os init`), no history, no active plan, `pause_classification=fresh_session`, `recommended_next_protocol=guidance/project_startup`.
- **Format clear?** Yes — `AI_GUIDE.md` lines 24-32 enumerate the keys.
- **Did I know what to do next?** Yes — call `tool_route` second.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 2 (same turn, second MCP call)
- **What I wanted to do:** Translate the user's plain-English ask into a protocol.
- **Tool I called:** `tool_route(prompt="i dropped my microglia RNA-seq data in inputs/ — i want to test whether LPS induces immune-response genes")`.
- **Simulated result:** Per `TOOLS.md`, returns `primary_protocol`, `shortcut_tool`, `decomposition`, `complexity`, `ask_user`. The router index has triggers for "deseq2" and "differential expression" (`_router_index.yaml` lines 361-362). Without grepping the router internals (which I am not allowed to do), the doc surface strongly suggests this is an "intake-shaped ask" that maps to `guidance/project_startup` → `tool_intake_autofill` shortcut. `complexity` would likely be `high` because it bundles intake + analysis + synthesis.
- **Format clear?** Yes.
- **Did I know what to do next?** Mostly — the AGENTS.md says: `complexity==high` → `tool_plan_turn`, walk with `tool_plan_advance`. `complexity==low` → call `shortcut_tool` directly. I am not 100% sure whether a fresh project with no intake.md routes to "intake_autofill" (shortcut) or to "project_startup" (full protocol). The doc does say `tool_route` may recommend the shortcut.
- **Friction:** FRICTION/LOW — the router's behaviour for "data + hypothesis in one breath" is not explicit in docs. A worked example in `docs/USE_CASES.md` showing "researcher arrives with data + hypothesis simultaneously" would resolve it.
- **Doc gap:** No example trace in `USE_CASES.md` of a mixed "I have data AND a hypothesis" first prompt. They are documented separately.
- **Time-to-clarity:** ~90s of re-reading.

### Turn 3
- **What I wanted to do:** Confirm there's a `researcher_config.yaml` and inspect it; verify the inputs exist.
- **Tool I called:** Sequenced calls implied by `project_startup.scan_inputs`: `sys_file_list directory="inputs/raw_data"`, `sys_file_list directory="inputs/literature"`, `sys_file_list directory="inputs/context"` (one batch).
- **Simulated result:** lists e.g. `counts.tsv`, `sample_metadata.csv`, possibly empty literature/, optional context notes.
- **Format clear?** Yes — `TOOLS.md` documents `sys_file_list`.
- **Did I know what to do next?** Yes — call `tool_intake_freshness` next, per `project_startup.check_intake_freshness`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 4
- **What I wanted to do:** Decide whether to auto-fill intake.
- **Tool I called:** `tool_intake_freshness`. Then `tool_intake_autofill` (no args, per protocol).
- **Simulated result:** `recommended_depth='full'` because `inputs/intake.md` doesn't exist. Then `tool_intake_autofill` is supposed to (a) infer domain → `transcriptomics / bulk RNA-seq / mouse microglia`, (b) extract the research question from context, (c) extract hypotheses (H1 = "LPS treatment induces immune-response gene programs"), (d) write `inputs/intake.md` + `docs/research_overview.md` + populate state. Per `templates/researcher_config.yaml`, blank fields like `project_name`, `output_types` get filled.
- **Format clear?** Yes-ish. The doc tells me the SIDE EFFECTS but I do not know the exact return-payload shape (does it return the proposed intake as a dict? Just a status? A diff?). I would have to inspect the JSON-style return.
- **Did I know what to do next?** Yes — present the proposed (question, domain, hypotheses) to the researcher and ask for approval.
- **Friction:** FRICTION/LOW — unclear return shape of `tool_intake_autofill`. Workable, but I'd want a docstring sample.
- **Doc gap:** Sample return JSON for `tool_intake_autofill` in `TOOLS.md` or a `sys_tool_describe(tool_intake_autofill)` example output.
- **Time-to-clarity:** ~60s.

### Turn 5
- **What I wanted to do:** Profile each dataset before locking in methods.
- **Tool I called:** `tool_data_profile filepath="inputs/raw_data/counts.tsv"` and `tool_data_profile filepath="inputs/raw_data/sample_metadata.csv"`. Then `sys_env_snapshot`.
- **Simulated result:** Schema, dtypes, missingness, descriptive stats. For a 60K-gene × 12-sample matrix that's straightforward. Then env snapshot writes `environment/requirements.txt`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `ground_in_recent_literature` step of `project_startup` (mandatory literature pass).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Onboarding friction count (first 5 turns): **2 LOW** (router ambiguity for mixed intake+hypothesis, return-shape opacity for `tool_intake_autofill`).

---

## Section 2 — Hypothesis + planning (turns 6-10)

### Turn 6
- **What I wanted to do:** Ground the project in current literature (mandatory `project_startup.ground_in_recent_literature`).
- **Tool I called:** parallel `tool_search_semantic_scholar query="LPS microglia transcriptomics" year_min=2023`, `tool_search_pubmed query="LPS microglia RNA-seq immune" year_min=2023`, `tool_research_method method="DESeq2 differential expression" domain="bulk RNA-seq"`. Save hits to `inputs/literature/` and register first grounding via `tool_ground_from_context decision="project_intake"`.
- **Simulated result:** Search returns paper hits; `tool_literature_search_and_save` would actually pull PDFs.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `present_startup_summary`, then `domain/domain_analysis` (per `next_protocol`).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 7
- **What I wanted to do:** Run `domain/domain_analysis` (auto-next).
- **Tool I called:** `sys_protocol_get format='summary' name='domain/domain_analysis'`. I do not actually see this file in `protocols/domain/` because that subfolder isn't shown in my dir list — wait, it IS listed as a category in `protocols/`. Let me check by name: I see `protocols/domain/` directory exists (Bash output showed `domain` listed). I would load the YAML summary.
- **Simulated result:** Loads a ~300-token summary; the protocol classifies the domain and flags any bias concerns.
- **Format clear?** Yes.
- **Did I know what to do next?** Mostly — but I notice `AI_GUIDE.md` doesn't explicitly name the `domain` category protocols. Only `methodology` is detailed.
- **Friction:** FRICTION/LOW — `docs/PROTOCOLS.md` would help me know which protocols are in `domain/` without grepping. (I'm told NOT to read source.)
- **Doc gap:** `PROTOCOLS.md` index by category. (It may exist — I should look.)
- **Time-to-clarity:** ~30s.

### Turn 8
- **What I wanted to do:** Pick a methodology — for RNA-seq DE, the canonical is DESeq2.
- **Tool I called:** Load `methodology/methodology_selection` summary, then `methodology/pick_tool_stack` (since `analysis_plan.scope_step` says "for DESeq2 vs pydeseq2" you MUST invoke pick_tool_stack and persist `stack_plan.md`).
- **Simulated result:** `pick_tool_stack` walks through `enumerate_language_candidates` → R Bioconductor DESeq2 vs Python pydeseq2 vs none-in-Julia. Doc literally says (lines 21-23) "Bulk RNA-seq DE testing → R Bioconductor (DESeq2, edgeR, limma)." So this is a slam-dunk decision and the stack_plan.md gets written.
- **Format clear?** Yes — exemplary. This protocol carries the field-practice answer in the doctrine block.
- **Did I know what to do next?** Yes — back to `analysis_plan`.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~20s.

### Turn 9
- **What I wanted to do:** Register the hypothesis (H1) formally.
- **Tool I called:** `mem_hypothesis_add` with text and status `testing`. Also `mem_decision_log` for the DESeq2 choice with a cited paper (Love, Huber, Anders 2014).
- **Simulated result:** Append-only ledger entry to `workspace/analysis.md`. State.active_hypotheses updated.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 10
- **What I wanted to do:** Build a per-step plan (analysis_plan steps for the whole DE pipeline). Reasonable break-down for an RNA-seq DE project:
  1. `01_qc_library_size` — library size + sample correlation + PCA (QC).
  2. `02_filter_lowcount_norm` — gene filtering + DESeq2 size-factor normalization.
  3. `03_deseq2_de_lps_vs_control` — DE model fit + Wald test + IHW/BH adjustment.
  4. `04_volcano_and_heatmap` — focal volcano + top-50 DEG heatmap.
  5. `05_gsea_immune_pathways` — GSEA / fgsea with Hallmark or GO Immune sets.
  6. `06_overlap_with_literature` — compare DEG set to published LPS-microglia studies.
- **Tool I called:** `tool_plan_step` for the higher-complexity step (step 03), or rely on the active_plan from `tool_route` if it persisted one. Otherwise just walk `analysis_plan` per step.
- **Simulated result:** A 6-step active plan; `tool_plan_turn` returns 3 steps/turn at `model_profile=medium`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — enter the per-step loop.
- **Friction:** FRICTION/LOW — six steps × ~6 sub-actions per step is a lot of `tool_plan_advance` calls in one chat. `AI_GUIDE.md` says `chat_split_recommended` may fire; I'd expect at least one handoff between step 3 and step 4. Hand-off is documented but I'm uncertain how big "fits in one chat" really is. The `chat_split_recommended` heuristic is opaque.
- **Doc gap:** `docs/AI_GUIDE.md` mentions `chat_split_recommended` but doesn't name the heuristic (turn count? token budget? step count?).
- **Time-to-clarity:** ~60s.

---

## Section 3 — Per-step execution (turns 11-25, interleaved with literature gate)

### Turn 11 — Step 01 (QC)
- **What I wanted to do:** Run `analysis_plan` for `01_qc_library_size`. Scope: library size dist + sample-sample correlation + PCA on rlog/vst-transformed counts.
- **Tool I called:** `sys_path_create name="qc_library_size" hypothesis="H1: LPS induces immune programs (QC prerequisite)"` → creates `workspace/01_qc_library_size/`. Then `tool_step_pipeline_define` because this step has 4 sub-tasks (load → library_size_qc → sample_correlation → pca). Write four atomic scripts:
  - `01a_load_counts_v1.R` (R: read counts + metadata, return SummarizedExperiment).
  - `01b_library_size_qc_v1.R` (R: per-sample read totals + boxplot).
  - `01c_sample_correlation_v1.R` (R: cor() on vst-transformed → heatmap).
  - `01d_pca_v1.R` (R: prcomp + ggplot2 PCA plot).
- **Simulated result:** `tool_step_pipeline_run` executes the DAG content-hash cached; produces 3 figures (library_size.png, sample_correlation.png, pca.png), 1 focal figure (pca.png), 1 table (qc_summary.csv), 1 report (qc_report.md). Each figure gets `.caption.md`, `.summary.md`, `.prov.json`, `.svg`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `ground_findings_in_literature` (per `analysis_plan.ground_findings_in_literature`). But QC is a "pure data engineering" step — the protocol says I can mark `literature_required: false` in `step_summary.yaml`. Good — saves a literature loop.
- **Friction:** FRICTION/LOW — to know I can skip the per-step lit loop I had to scroll deep into the `analysis_plan.ground_findings_in_literature` step description (lines 462-465). It's there but easy to miss; a callout box would help.
- **Doc gap:** A flowchart of "when does literature_per_step apply?" — QC, normalization, format conversion all exempt; everything else mandatory.
- **Time-to-clarity:** ~90s.

### Turn 12 — Step 01 finalize
- **What I wanted to do:** Finalize the step.
- **Tool I called:** `tool_step_complete(step_id="01_qc_library_size")` — per `AGENTS.md` this bundles `tool_path_finalize` + `tool_audit_step_completeness` + `tool_audit_step_literature` + `tool_step_revision_options`.
- **Simulated result:** Returns a combined report. Should be GREEN since QC step has focal figure + sidecars + non-stub conclusions + `literature_required: false`.
- **Format clear?** Yes — `AGENTS.md` lines 84-89 explicitly describe the bundling.
- **Did I know what to do next?** Yes — present to researcher, get (a) proceed.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 13 — Step 02 (filter + normalize)
- **What I wanted to do:** Filter low-count genes, normalize with DESeq2 size factors.
- **Tool I called:** `sys_path_create name="filter_norm_deseq2"`. Then `tool_step_pipeline_define` (sub-tasks: `02a_filter_lowcount_v1.R`, `02b_size_factor_norm_v1.R`). `literature_required: false` again (pure data engineering).
- **Simulated result:** Produces a filtered SummarizedExperiment (saved as RDS in `data/output/`), a filter-pass-rate table, one diagnostic figure (gene count before/after).
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 14 — Step 02 finalize
- **What I wanted to do:** finalize.
- **Tool I called:** `tool_step_complete(step_id="02_filter_norm_deseq2")`.
- **Simulated result:** GREEN.
- **Friction:** none. **Doc gap:** none. **Time-to-clarity:** ~5s.

### Turn 15 — Step 03 (DE model fit — the headline step)
- **What I wanted to do:** Fit `DESeq()` with `design = ~ condition`, run Wald test for LPS vs Control, apply BH adjustment, save full DE table.
- **Tool I called:** `tool_research_method query="DESeq2 dispersion shrinkage small-n design"` (per `analysis_plan.ground_methods` — even though the method is committed, I need a cited justification for the FDR + LFC threshold choices). Then `tool_literature_search_and_save query="Love Huber Anders 2014 DESeq2" step_id="03_deseq2_de_lps_vs_control" download_top=2`. Then `sys_path_create name="deseq2_de_lps_vs_control"`. Write scripts: `03a_fit_deseq2_v1.R`, `03b_extract_results_v1.R`, `03c_export_de_table_v1.R`. Declare pipeline.yaml.
- **Simulated result:** Produces `de_full_table.csv`, `de_significant_padj05.csv`, a diagnostic dispersion plot, MA plot. Library versions printed to stderr.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — `ground_findings_in_literature` (the per-step literature gate).
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 16 — Step 03 per-step literature gate (HARD GATE)
- **What I wanted to do:** Compare the DEG count + top genes against published LPS-microglia studies.
- **Tool I called:** Load `literature/literature_per_step` (full). Walk: `extract_step_claims` → `build_search_queries` (e.g. "LPS microglia DEG count", "microglia LPS Tnf Il1b Nfkb upregulation"), `search_literature` → `download_relevant` → `write_findings_vs_literature` → `register_grounding` → `verify_key_claims` → `update_step_summary` → `gate`.
- **Simulated result:** Writes `workspace/03_deseq2_de_lps_vs_control/literature/findings_vs_literature.md` with per-claim blocks (verdict AGREES/DISAGREES/EXTENDS/DEFERRED). Hank Plüger 2024 microglia LPS bulk RNA-seq paper would be a likely AGREES verdict. Then `tool_audit_step_literature step_id=...` GATE.
- **Format clear?** Yes — the literature_per_step protocol's step list is clean.
- **Did I know what to do next?** Yes — finalize the step.
- **Friction:** FRICTION/MEDIUM — running this loop end-to-end for every step is a lot of work, and the researcher might want to defer some claims. The DEFERRED verdict path is documented but the all-DEFERRED-blocks-finalize behaviour means there's a risk of paralysis. I'd want a clearer guide on "if you can't find literature for claim X, defer with rationale Y" patterns.
- **Doc gap:** A worked example of `findings_vs_literature.md` (perhaps in `docs/RESEARCHER_GUIDE.md` or as a template) would make this much faster.
- **Time-to-clarity:** ~180s of reading the protocol.

### Turn 17 — Step 03 finalize
- **What I wanted to do:** finalize.
- **Tool I called:** `tool_step_complete(step_id="03_deseq2_de_lps_vs_control")`.
- **Simulated result:** Should be GREEN. Present-to-researcher → (a) proceed.
- **Friction:** none. **Doc gap:** none. **Time-to-clarity:** ~10s.

### Turn 18 — handoff?
- **What I wanted to do:** I am now ~17 turns in. Per `tool_step_revision_options.handoff_recommended`, this may fire (>= 5 steps finalized this conversation — only 3 steps so far, so probably not). Continue.
- **Friction:** none.
- **Doc gap:** none.

### Turn 19 — Step 04 (volcano + heatmap)
- **What I wanted to do:** Make the headline volcano plot + top-50 DEG heatmap. Focal figure = volcano.
- **Tool I called:** `sys_protocol_get format='summary' name='visualization/figure_guidelines'` for palette/DPI rules. Then `visualization/interactive_figure_design` because a volcano is one of the named interactive-companion candidates (per the visualization protocol table in `AI_GUIDE.md`: "volcano, UMAP, heatmap"). Static PNG/SVG fallback REQUIRED. Then `sys_path_create name="volcano_and_heatmap"`. Write `04a_volcano_v1.py` (Python matplotlib, Okabe-Ito palette), `04b_heatmap_top50_v1.py` (seaborn clustered heatmap), `04c_volcano_interactive_v1.py` (Plotly HTML companion). Each script writes both sidecars.
- **Simulated result:** `volcano.png` + `volcano.svg` + `volcano.html` + 4 sidecars; `heatmap.png` + 4 sidecars. `tool_audit_figure_interactivity` for the volcano — passes because companion HTML exists.
- **Format clear?** Yes — `AGENTS.md` Rule 10 spells out the four sidecars + the interactive companion requirement.
- **Did I know what to do next?** Yes — per-step lit gate. Volcano + heatmap claims include "X immune genes pass FDR<0.05 |LFC|>1" which is a literature-comparable claim.
- **Friction:** FRICTION/LOW — the boundary between `figure_guidelines`, `visualization_workflow`, and `interactive_figure_design` is fuzzy. I had to read three protocol summaries to decide what to load. The 14-protocol visualization table in `AI_GUIDE.md` is helpful but doesn't say "for a focal volcano, load X + Y in this order".
- **Doc gap:** A "common figure recipes" appendix (volcano, UMAP, survival curve, forest plot) showing which protocol stack to load.
- **Time-to-clarity:** ~120s.

### Turn 20 — Step 04 lit gate + finalize
- **What I wanted to do:** literature gate + finalize.
- **Tool I called:** Run `literature_per_step` for step 04 (only if claims are independent from step 03 — in this case the volcano just visualises step 03's result, so I could mark this `literature_required: false`. The protocol says "pure data engineering" — visualization isn't strictly engineering but the doctrine says the underlying claims are already covered upstream. UNCLEAR.) Then `tool_step_complete(step_id="04_volcano_and_heatmap")`.
- **Simulated result:** Either GREEN if `literature_required: false` is acceptable for viz steps, or yet-another lit loop.
- **Format clear?** Partly.
- **Did I know what to do next?** Yes-ish.
- **Friction:** FRICTION/MEDIUM — the `literature_required: false` exemption is documented for "pure data engineering (QC, normalization, format conversion)" but NOT for pure visualization-of-prior-step. This is a real-world common case; the doc should explicitly authorise it.
- **Doc gap:** Expand the "skip the per-step lit loop" exemption list to include "pure visualization of a prior step's result with no new quantitative claim".
- **Time-to-clarity:** ~90s.

### Turn 21 — Step 05 (GSEA)
- **What I wanted to do:** GSEA against Hallmark + GO BP Immune gene sets using fgsea (R) or gseapy (Python).
- **Tool I called:** `methodology/pick_tool_stack` to decide R fgsea vs Python gseapy. Per the protocol's field-practice block, neither is strongly dominant — likely R fgsea since the upstream is already R. Save `scratch/stack_plan.md`. Then `sys_path_create name="gsea_hallmark_go_immune"`, write `05a_prep_ranked_genelist_v1.R`, `05b_fgsea_hallmark_v1.R`, `05c_fgsea_go_bp_v1.R`, `05d_gsea_barplot_v1.R`. Pipeline.yaml + run.
- **Simulated result:** Produces `gsea_hallmark.csv`, `gsea_go_bp.csv`, `gsea_immune_barplot.png` (focal), all sidecars.
- **Format clear?** Yes.
- **Did I know what to do next?** Lit gate next.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 22 — Step 05 lit gate + finalize
- **What I wanted to do:** Per-step literature compare — does the literature show Hallmark INFLAMMATORY_RESPONSE / INTERFERON_GAMMA_RESPONSE / TNF_NFKB consistently enriched under LPS in microglia? Yes per published evidence; verdict = AGREES.
- **Tool I called:** `literature_per_step` → `tool_step_complete`.
- **Simulated result:** GREEN.
- **Friction:** none. **Doc gap:** none. **Time-to-clarity:** ~30s.

### Turn 23 — Step 06 (literature-set overlap)
- **What I wanted to do:** Overlap our DEG set with published LPS-microglia DEG sets (e.g. Holtman 2015, Hammond 2019, MGEnrichR sets).
- **Tool I called:** `sys_path_create name="lit_set_overlap"`. Two scripts: fetch reference DEG sets (Python pandas), compute Jaccard / Fisher overlap (Python scipy). Focal figure: overlap Venn / bar.
- **Simulated result:** Produces `overlap_table.csv`, `overlap_venn.png` + sidecars.
- **Format clear?** Yes.
- **Did I know what to do next?** Lit gate + finalize.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~30s.

### Turn 24 — Step 06 finalize
- **What I wanted to do:** finalize. `tool_step_revision_options.handoff_recommended` is likely TRUE now (6 steps finalized this conversation). Per the doc I should propose a handoff.
- **Tool I called:** `tool_step_complete(step_id="06_lit_set_overlap")` → `sys_session_handoff` → tell researcher to open a fresh chat.
- **Simulated result:** Handoff doc written; researcher opens new chat; new chat calls `sys_boot` + `tool_session_resume`.
- **Format clear?** Yes — `AI_GUIDE.md` hand-off section is explicit.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/LOW — the handoff text format and the "what should the resume chat do first?" handshake is documented but I'd want a worked-example transcript of a handoff that says "step 06 done; next: tool_audit_quality_full before synthesis".
- **Doc gap:** A canonical resume transcript in `RESEARCHER_GUIDE.md`.
- **Time-to-clarity:** ~60s.

### Turn 25 — New chat resume
- **What I wanted to do:** Pick up.
- **Tool I called:** `sys_boot` → `tool_session_resume` → `sys_protocol_next`.
- **Simulated result:** Recommends `audit/audit_and_validation` or `audit/pre_submission_checklist` next, or `synthesis/synthesis_paper`.
- **Format clear?** Yes.
- **Friction:** none. **Doc gap:** none. **Time-to-clarity:** ~10s.

---

## Section 4 — Per-step literature gate (interleaved — summarised)

Per-step literature loop ran on steps 03 (DE), 05 (GSEA), 06 (overlap). Skipped on steps 01, 02 (data engineering: `literature_required: false`). Step 04 (viz) is ambiguous — see Turn 20 FRICTION/MEDIUM.

The loop itself is well-specified (`literature_per_step` 10 steps, verdict taxonomy is clean: AGREES / DISAGREES / EXTENDS / DEFERRED). Friction is mostly volume: per-claim PDF downloads + grounding registration on every analytical step is a lot of network round-trips.

---

## Section 5 — Audit + synthesis (turns 26-35)

### Turn 26
- **What I wanted to do:** Full quality audit before synthesis.
- **Tool I called:** `tool_audit_quality_full`.
- **Simulated result:** Aggregates `tool_audit_step_completeness` + `tool_audit_claims` + `tool_audit_code_quality` + `tool_audit_prose` + `tool_citations_verify` + `tool_preregister_diff`. Returns GREEN / YELLOW / RED per gate.
- **Format clear?** Yes — `AI_GUIDE.md` lists all six.
- **Did I know what to do next?** Yes — if GREEN, proceed to synthesis.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 27
- **What I wanted to do:** Load synthesis_paper protocol.
- **Tool I called:** `sys_protocol_get format='summary' name='synthesis/synthesis_paper'`.
- **Simulated result:** 16-step protocol: `gate_completeness` → `select_venue_profile` → `plan_sections` → `draft_methods/results/discussion/introduction/abstract` → `final_assembly` → `compile_pdf` → `workshop_the_title` → `build_end_matter` → `draft_cover_letter` → `run_pre_submission_checklist` → `report_to_researcher`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 28
- **What I wanted to do:** Run `tool_synthesize` for the paper.
- **Tool I called:** `tool_synthesize_plan` first (proposes section order), then `tool_synthesize output_type="paper" venue="generic_two_column"`.
- **Simulated result:** Reads workspace, gates via `tool_audit_quality_full` (first gate per AI_GUIDE.md), compiles `synthesis/paper.md` with VERIFIED citations only (Crossref/SS/PubMed/arXiv check). Numbers traced via `tool_audit_claims`.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 29
- **What I wanted to do:** Compile PDF.
- **Tool I called:** `tool_paper_compile_typst venue="generic_two_column"`.
- **Simulated result:** `synthesis/paper.md` → `synthesis/paper.typ` → `synthesis/paper.pdf`. Per `TOOLS.md` line 151 this is the recommended path. **PAPER STEP REACHED.**
- **Format clear?** Yes.
- **Did I know what to do next?** Yes — dashboard next.
- **Friction:** FRICTION/LOW — `templates/typst/` directory exists (per the `ls templates/` result earlier). I'd want a one-line note in `TOOLS.md` saying which venue templates ship with Research-OS so I don't have to grep `templates/typst/`.
- **Doc gap:** Venue template catalogue. (The `templates/typst/` README would help.)
- **Time-to-clarity:** ~30s.

### Turn 30
- **What I wanted to do:** Build the dashboard. Researcher wants "explore mode".
- **Tool I called:** Load `synthesis/synthesis_dashboard` summary. Walk: `select_audience` → `confirm_sources_exist` → `run_completeness_audit` → `finalize_all_steps` → `curate_figures` → `author_synthesis_spec` → `ensure_interactive_companions` → `build_story_mode_source` → `build_dashboard` → `verify_quality` → `share`.
- **Tool I called:** `tool_synthesis_curate_figures` → `tool_dashboard_story_generate` (since researcher wants explore mode, this builds `synthesis/dashboard_story.md`) → `tool_dashboard_create mode="explore"`.
- **Simulated result:** Single-file `synthesis/dashboard.html`. **DASHBOARD STEP REACHED.**
- **Format clear?** Yes. I'm assuming `mode="explore"` is a valid arg — the doc surface doesn't explicitly show all `tool_dashboard_create` args.
- **Did I know what to do next?** Yes.
- **Friction:** FRICTION/MEDIUM — `tool_dashboard_create` docstring in `TOOLS.md` says "Single-file offline HTML dashboard" but doesn't enumerate the `mode` parameter values. The protocol references "story mode" and there's a `tool_dashboard_story_generate`, implying multiple modes (story / explore / executive?). The user asked for "explore mode" specifically — I'd need to `sys_tool_describe(tool_dashboard_create)` to confirm.
- **Doc gap:** `TOOLS.md` should list `tool_dashboard_create`'s mode enum (explore / story / executive / teaching?).
- **Time-to-clarity:** ~120s.

### Turn 31
- **What I wanted to do:** Verify dashboard quality.
- **Tool I called:** `tool_audit_dashboard_content` + `tool_dashboard_reviewer_sim`.
- **Simulated result:** Reviewer-sim checks the 5-minute reviewer scenario. Returns GREEN / YELLOW.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

---

## Section 6 — Cross-checks + sign-off (turns 32-35)

### Turn 32
- **What I wanted to do:** Run pre-submission checklist.
- **Tool I called:** Load `audit/pre_submission_checklist` summary. Walk: `scope_submission` → `artefact_inventory` → `paper_content_checks` → `figure_table_checks` → `end_matter_checks` → `cover_letter_check` → `ethics_and_compliance_checks` → `reproducibility_checks` → `claim_grounding_audit` → `override_audit_review` → `venue_specific_checks` → `revision_addendum` → `produce_the_verdict`.
- **Simulated result:** GREEN verdict (hopefully) with punch list of any YELLOW items.
- **Format clear?** Yes — `AI_GUIDE.md` and `README.md` both reference the GREEN/YELLOW/RED verdict.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 33
- **What I wanted to do:** `tool_audit_reproducibility` (re-run all scripts in clean env).
- **Tool I called:** `tool_audit_reproducibility` — slow, runs in background via `tool_task_run`.
- **Simulated result:** Hashes match for all scripts.
- **Format clear?** Yes.
- **Did I know what to do next?** Yes.
- **Friction:** none.
- **Doc gap:** none.
- **Time-to-clarity:** ~10s.

### Turn 34
- **What I wanted to do:** Generate a session handoff doc for the researcher to archive.
- **Tool I called:** `sys_session_handoff`.
- **Simulated result:** Writes handoff. Done.
- **Format clear?** Yes.
- **Friction:** none. **Doc gap:** none. **Time-to-clarity:** ~5s.

### Turn 35
- **What I wanted to do:** Report final status to researcher with paths to paper.pdf + dashboard.html.
- **Tool I called:** No tool — natural-language report.
- **Result:** **Both deliverable steps reached.**

---

## Section 7 — Top 5 friction points

| # | Severity | Title | Tool / Protocol | Suggested Fix |
|---|---|---|---|---|
| 1 | MEDIUM | `literature_required: false` exemption ambiguous for visualization-only steps | `analysis_plan.ground_findings_in_literature` + `literature_per_step` | Explicitly authorise "pure visualization of a prior step's quantitative result with no new numeric claim" as an exemption (alongside QC/normalization/format conversion). Add to the protocol's `Skip ONLY when` block. |
| 2 | MEDIUM | `tool_dashboard_create` modes not enumerated in user-facing docs | `tool_dashboard_create` / `synthesis_dashboard` | Add the `mode` enum (e.g. `explore` / `story` / `executive` / `teaching`) to `TOOLS.md` row for `tool_dashboard_create`. Cross-link from `synthesis_dashboard` protocol. |
| 3 | MEDIUM | High volume of `literature_per_step` work per analytical step risks paralysis on hard-to-ground claims | `literature_per_step` | Provide a worked-example `findings_vs_literature.md` template in `templates/` plus 2-3 example DEFERRED rationales the AI can copy. |
| 4 | LOW | First-prompt with data + hypothesis bundled is under-exemplified | `tool_route` / `USE_CASES.md` | Add a row to `USE_CASES.md`: "I have data AND a hypothesis" → expected route + first turn pattern. |
| 5 | LOW | Visualization protocol stack for common figures (volcano / UMAP / forest) requires reading 3 protocols to decide ordering | `visualization/*` | Add a "common figure recipes" appendix to `RESEARCHER_GUIDE.md` showing which protocol stack to load for each canonical figure type. |

---

## Section 8 — Top 5 doc/guidance gaps

1. **`docs/PROTOCOLS.md` category index** — I didn't open it (the validation kept me in the few docs I knew about), but knowing what's in each category folder (`domain/`, `methodology/`, `visualization/`, …) without grepping `protocols/` would save ~30-60s per fresh session.
2. **Return-shape examples for high-value tools** — `tool_intake_autofill`, `tool_dashboard_create`, `tool_step_complete`, `tool_audit_quality_full`. A `sys_tool_describe(name)` worked-example block in `TOOLS.md` (one tool per category) would unblock fresh agents.
3. **`chat_split_recommended` heuristic** — `AI_GUIDE.md` mentions it but doesn't name the threshold (step count? turn count? token budget?). I had to guess.
4. **Canonical handoff + resume transcript** — `AI_GUIDE.md` describes the mechanics; a transcript example in `RESEARCHER_GUIDE.md` would close the loop.
5. **Venue template catalogue** — the typst templates ship in `templates/typst/` but a one-line "available venues" list in `TOOLS.md` next to `tool_paper_compile_typst` would help fresh agents pick without grepping.

---

## Section 9 — Top 5 things that worked WELL (positive findings)

1. **The two-call boot pattern (`sys_boot` + `tool_route`) is BEAUTIFUL.** Documented identically in three places (`AGENTS.md`, `templates/CLAUDE.md`, `AI_GUIDE.md`) — zero ambiguity. Fresh agent gets unblocked in seconds.
2. **`tool_step_complete` bundling** — the four-tool bundle (finalize + completeness + literature + revision_options) reduces friction dramatically on small models and is well-advertised in `AGENTS.md`.
3. **`pick_tool_stack` is exemplary doctrine** — the protocol literally carries the answer ("Bulk RNA-seq DE → R Bioconductor DESeq2/edgeR/limma") in its doctrine block. Zero ambiguity for a real-world RNA-seq agent.
4. **Hard rules in `AGENTS.md` are absolute and clear** — no causal language on observational data, no inventing citations, immutable `inputs/raw_data` + `inputs/literature`. A fresh agent cannot accidentally violate these.
5. **The four-sidecar figure contract (`.caption.md` + `.summary.md` + `.prov.json` + `.svg`)** — concrete, mechanical, easy to comply with. Every figure step has the same shape; no guesswork.

---

## Section 10 — Final rating: 7/10

**Rationale:** The doc surface is genuinely high-quality. The boot pattern, the per-step loop in `analysis_plan`, the hard rules in `AGENTS.md`, and the scaffold-not-script doctrine are all clear and would let a fresh AI agent execute end-to-end. The friction is in the periphery: visualization protocol stack selection, dashboard mode enumeration, literature gate exemption boundaries, and a few opaque return-shape questions. Nothing is BLOCKING, but a fresh agent will spend ~5-10 minutes of doc-time on these gaps that better cross-linking + 2-3 worked examples could erase. A v1.9.5 round focused on "examples in TOOLS.md" + a "common recipes" appendix would push this to 9/10.

## Section 11 — Onboarding friction count (first 5 turns): **2 (both LOW)**

## Section 12 — Reached paper.pdf step? **YES (Turn 29).** Reached dashboard.html step? **YES (Turn 30).**
