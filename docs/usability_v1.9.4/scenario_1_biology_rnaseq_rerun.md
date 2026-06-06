# Scenario 1 — Biology / RNA-seq DE (Re-validation, v1.9.4)

**Scenario ID:** `1_biology_rnaseq`
**Hypothesis:** *LPS treatment induces immune-response gene programs in mouse microglia.*
**Data:** 6 treatment + 6 control mouse-microglia RNA-seq samples (assumed pre-staged in `inputs/raw_data/`).
**Stack:** Mixed R (DESeq2, fgsea) + Python (volcano + heatmap, sanity QC).
**Expected deliverables:** `synthesis/paper.pdf` via `generic_two_column` Typst template + `synthesis/dashboard.html` in `explore` mode, with traceable volcano plot, heatmap, and GSEA output.

**Validation mode:** Fresh agent. Documentation-surface only. All tool calls simulated by reading the relevant protocol YAML + `docs/TOOLS.md` and inferring the return shape from the documented schema.

**Package version under test:** `1.9.4` (pyproject + CITATION cff). Protocol YAML version stamps still read `1.9.3` (1.9.4 is a fix-only bump). Doc surface includes `CHANGELOG.md` (1.9.3 entry) + `CHANGELOG_DETAILED_v1.9.3.md`, both already enumerating the DESeq2/DE router triggers and the `tool_paper_compile_typst` decomposition wiring.

---

## 1. Project setup (turns 1-5)

### Turn 1
- **Wanted:** Orient. I'm a fresh AI in a brand-new shell, told "this is a Research-OS project" with the hypothesis above and 12 FASTQ-like samples in `inputs/raw_data/`.
- **Tool called:** none yet — first read `AGENTS.md`/`templates/CLAUDE.md` (proxy for what the wizard drops) and `docs/START.md` to learn the two-call boot rule.
- **Simulated result:** Two-call rule is unambiguous — `sys_boot` then `tool_route(prompt=<verbatim>)`. Both `templates/CLAUDE.md` and `templates/.claude/rules/research-os.md` state this verbatim and they're already in scope of a freshly-init'd project.
- **Format clear?** yes — Both files lead with the boot sequence; tool names use the canonical underscore form.
- **Know next?** yes — Fire `sys_boot`.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~30s.

### Turn 2
- **Wanted:** Fire the boot call to inventory state + config.
- **Tool called:** `sys_boot()`.
- **Simulated result (from TOOLS.md):** `{state, researcher_config (default — empty researcher block), protocol_history: [], dep_inventory, recommended_next_protocol: "guidance/project_startup", pause_classification: "fresh_session", active_plan: null}`. The wizard has dropped `inputs/{raw_data,literature,context}/` plus default `researcher_config.yaml` with `autonomy_level=supervised`, `model_profile=medium`, `quality_gate_policy=enforce`, `tool_stack.preferred_languages=[python, R]`, `field_practice_overrides_preference=true`.
- **Format clear?** yes — TOOLS.md ships a `tool_intake_autofill` return-shape example, and the README + AI_GUIDE both describe the `sys_boot` payload keys in plain English. I can infer the shape with confidence.
- **Know next?** yes — `tool_route` next, with the researcher's verbatim hypothesis.
- **Friction:** none.
- **Doc gap:** none (the return-shape examples added to TOOLS.md are a real win — see §9).
- **TTC:** ~20s.

### Turn 3
- **Wanted:** Route the researcher's first message: "Test whether LPS treatment induces immune-response gene programs in mouse microglia — RNA-seq, 6 treated + 6 control."
- **Tool called:** `tool_route(prompt="Test whether LPS treatment induces immune-response gene programs in mouse microglia — RNA-seq, 6 treated + 6 control.")`.
- **Simulated result:** `intent_class=discover, sub_intent=intake, primary_protocol=guidance/project_startup, shortcut_tool=tool_intake_autofill, complexity=medium, ask_user=null`. The router's `discover/intake` class is documented in AI_GUIDE.md as resolving to the `tool_intake_autofill` shortcut. The DESeq2/DE triggers (added in v1.9.3 / re-checked v1.9.4) would only fire on a *follow-on* execute message; the first turn is intake.
- **Format clear?** yes — AI_GUIDE.md explicitly explains the `discover` category resolves to a shortcut, not a YAML protocol.
- **Know next?** yes — Run `tool_intake_autofill`, then load `guidance/project_startup` summary.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~25s.

### Turn 4
- **Wanted:** Populate `inputs/researcher_config.yaml` with the researcher's identity, venue intent, and tool-stack preferences before intake fires.
- **Tool called:** `sys_config_set` (multiple keys) — citation_style="vancouver" (biomedical), venue_template="generic_two_column" (explicitly requested), output_types=["paper", "dashboard"], tool_stack.preferred_languages=["R", "python"] (R first because Bioconductor field practice), field_practice_overrides_preference=true.
- **Simulated result:** OK ack per key. `researcher_config.yaml` template is byte-for-byte mirrored in `templates/researcher_config.yaml`, with inline commentary on every field — I can pick `vancouver` and `generic_two_column` without leaving the doc surface.
- **Format clear?** yes — `researcher_config.yaml` is the most legible config file I've seen in a research tool.
- **Know next?** yes — Now call `tool_intake_autofill`.
- **Friction:** none.
- **Doc gap:** none. (Honestly: this is a positive — see §9.)
- **TTC:** ~40s (mostly reading the citation-style choices for biomedical fields).

### Turn 5
- **Wanted:** Intake the data dump.
- **Tool called:** `tool_intake_autofill()`.
- **Simulated result (per TOOLS.md example shape):** `{status: "ok", domain_inferred: "biology_genomics", research_question: "Does LPS treatment induce a pro-inflammatory transcriptional program in mouse primary microglia?", hypotheses_drafted: [{id: "H01", text: "LPS-treated microglia upregulate canonical NF-κB / TLR4 immune-response genes (Il1b, Tnf, Cxcl10, Nfkbia) relative to vehicle controls (|log2FC|>1, padj<0.05)."}, {id: "H02", text: "Pathway-level GSEA against MSigDB Hallmark sets is dominated by INFLAMMATORY_RESPONSE, TNF_SIGNALING_VIA_NFKB, and INTERFERON responses."}], files_seen: {raw_data: ["12 FASTQ pairs"], literature: [], context: []}, wrote: ["inputs/intake.md","docs/research_overview.md",".os_state/state.json"], next_steps: "Run domain/domain_analysis then methodology/methodology_selection. Bulk RNA-seq DE is mapped to R Bioconductor (DESeq2/edgeR/limma) in methodology/pick_tool_stack."}`.
- **Format clear?** yes.
- **Know next?** yes.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~20s.

**Onboarding-friction (first 5 turns):** **0**.

---

## 2. Hypothesis + planning (turns 6-10)

### Turn 6
- **Wanted:** Confirm classification + reporting standard.
- **Tool called:** `sys_protocol_get(name="domain/domain_analysis", format="summary")` → walk the steps → write `docs/domain_summary.md`.
- **Simulated result:** Domain=`biology / functional genomics / bulk-RNA-seq`, reporting standard hint = MINSEQE + ARRIVE 2.0 (the latter for the mouse-husbandry side), known biases = batch effects, ribo/globin contamination, low-input variance for n=6+6, sex/age confounders if not blocked.
- **Format clear?** yes.
- **Know next?** yes — `domain/research_design` next.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~30s.

### Turn 7
- **Wanted:** Sample-size justification + design lock.
- **Tool called:** `sys_protocol_get(name="domain/research_design", format="summary")` → drafts a `docs/research_design.md` with: design = 2-arm parallel, n=6/arm (post-hoc power: with mean dispersion 0.05 and log2FC=1 → ~78% at α=0.05 per gene, citing the DESeq2 power vignette).
- **Simulated result:** Written.
- **Format clear?** yes.
- **Know next?** yes — `methodology/methodology_selection`.
- **Friction:** **FRICTION/LOW** — the power analysis vignette is named in the protocol but the protocol assumes the AI will fetch the canonical paper itself via `tool_research_method`. That's fine because of the `ground_methods` HARD GATE in `analysis_plan`, but a fresh agent might double-back here vs. pushing the citation work into the per-step loop. The AI_GUIDE could clarify that grounding lives at the analysis step, not at design.
- **Doc gap:** "where does power justification grounding live" — answer is buried in `analysis_plan.ground_methods` rather than in `research_design`.
- **TTC:** ~60s (re-reading both protocols to confirm).

### Turn 8
- **Wanted:** Pick the methods stack.
- **Tool called:** `sys_protocol_get(name="methodology/methodology_selection", format="summary")` + `sys_protocol_get(name="methodology/pick_tool_stack", format="full")` because methodology_selection.classify_step_intent step demands a language-stack sub-decision when the choice is non-trivial.
- **Simulated result:** Protocol explicitly tells me bulk RNA-seq DE → R Bioconductor (DESeq2/edgeR/limma) with `field_practice_overrides_preference=true`. Pick DESeq2 (Love 2014). Volcano + heatmap can stay in Python (matplotlib/seaborn for portability), GSEA via R `fgsea` (Korotkevich 2021).
- **Format clear?** yes — `pick_tool_stack.yaml` has an explicit table for bulk RNA-seq DE that names DESeq2 + cites field practice.
- **Know next?** yes — Now run `literature/literature_search` to seed the project corpus, then enter the `guidance/analysis_plan` loop.
- **Friction:** none. (This is a major v1.9.x positive — see §9.)
- **Doc gap:** none.
- **TTC:** ~45s.

### Turn 9
- **Wanted:** Seed project-level literature corpus (DESeq2 paper, fgsea, microglia-LPS reference review). This is the project-wide search; the per-step literature loop is later.
- **Tool called:** `tool_research_method(query="bulk RNA-seq differential expression n=6 vs 6 mouse microglia LPS")` + `tool_literature_search_and_save(query="DESeq2 differential expression normalization", source="semantic_scholar", limit=5, download_top=2)` + `tool_literature_search_and_save(query="fgsea GSEA implementation", source="semantic_scholar", limit=5, download_top=2)`.
- **Simulated result:** ~5 papers per query land in `inputs/literature/` (or `workspace/<step>/literature/` once steps exist). `workspace/citations.md` gets seeded.
- **Format clear?** yes — analysis_plan.ground_methods has explicit copy-paste tool invocations.
- **Know next?** yes — Register hypotheses with `mem_hypothesis_add` (already covered by intake), then create the first step folder.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~40s.

### Turn 10
- **Wanted:** Register the hypotheses formally so the per-step loop can `mem_hypothesis_update` them.
- **Tool called:** `mem_hypothesis_add(H01, …)` and `mem_hypothesis_add(H02, …)` — autofill already drafted; this is a confirm-and-commit.
- **Simulated result:** Two hypothesis records persisted to state.active_hypotheses + appended to analysis.md.
- **Format clear?** yes.
- **Know next?** yes — Enter `guidance/analysis_plan`.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~15s.

---

## 3. Per-step execution (turns 11-25) — 7 analysis steps

The plan I'll walk (each step gets the full `analysis_plan.yaml` loop: orient → scope → ground_methods → pick_tools → classify_step_intent → create_step_folder → write_atomic_scripts → document_conclusions → ground_findings_in_literature → snapshot_step_environment → finalize_step → lightweight_step_audit → present_to_researcher → decide_next):

| #  | Step slug                            | Intent    | Lang   | Focal output                              |
|----|--------------------------------------|-----------|--------|-------------------------------------------|
| 01 | `qc_alignment_fastqc`                | `analyse` | bash/R | QC summary + alignment-rate table         |
| 02 | `count_matrix_assembly`              | `ground` then `analyse` | R | gene × sample count matrix (Rsubread)    |
| 03 | `library_size_normalisation_eda`     | `analyse` | R      | PCA + sample correlation heatmap          |
| 04 | `deseq2_de_lps_vs_ctrl`              | `analyse` | R      | DESeq2 results table (focal: MA plot)     |
| 05 | `volcano_top_immune_genes`           | `visualise` (inherits from 04) | py | volcano (focal figure for H01)        |
| 06 | `heatmap_immune_panel`               | `visualise` (inherits from 04) | py | heatmap of top-50 immune genes            |
| 07 | `fgsea_hallmark_pathways`            | `analyse` | R      | GSEA NES table + enrichment plot (focal for H02) |

### Turn 11 — Step 01 (qc_alignment_fastqc)
- **Wanted:** Plan the first step.
- **Tool called:** `sys_protocol_get(name="guidance/analysis_plan", format="summary")` → execute `scope_step` (state goal: per-sample FASTQC + STAR alignment QC, n=12) → `ground_methods` (search "FASTQC STAR alignment QC RNA-seq best practice", save the canonical FASTQC + STAR papers into the step's literature/) → `classify_step_intent=analyse` → `sys_path_create(name="qc_alignment_fastqc", hypothesis="H01")` → write atomic scripts: `01a_run_fastqc_v1.sh`, `01b_star_align_v1.sh`, `01c_alignment_qc_summary_v1.R` → `tool_step_pipeline_define` with a 3-node DAG.
- **Simulated result:** step folder created with the canonical subtree. Each script gets a `_v1` suffix per the analysis_plan naming convention. Per-step `requirements.txt` (FASTQC, STAR, Rsubread) captured via `tool_step_env_lock`. Outputs: alignment-rate table, per-sample QC report. Focal figure: per-sample read-quality boxplot. Captions + summaries via `tool_figure_caption_synthesise`.
- **Format clear?** yes — analysis_plan.create_step_folder + analysis_plan.write_atomic_scripts together explain naming, the letter-suffix style A, and the sub-task DAG.
- **Know next?** yes — `document_conclusions` → `ground_findings_in_literature` → `finalize_step`.
- **Friction:** **FRICTION/LOW** — this is a heavy turn (one researcher prompt drove ~9 tool calls). The `model_profile=medium` documented batch size is 3 steps/turn but a "step" here means a full analysis-plan iteration; what counts toward the 3? Doc doesn't fully disambiguate "analysis-plan inner-loop step" vs. "research-pipeline outer-stage step". I treated it as the outer loop and let the turn run long.
- **Doc gap:** "step" overload — the same word means both a *pipeline stage* and an *analysis_plan inner-loop iteration*. `tool_plan_turn`'s sizing in PROTOCOLS.md is ambiguous.
- **TTC:** ~120s.

### Turn 12 — Step 01 (close the loop)
- **Wanted:** Run per-step literature loop, finalize, present.
- **Tool called:** `tool_audit_step_literature(step_id="01_qc_alignment_fastqc")` — but this step is genuinely pure-data-QC; set `literature_required: false` in `step_summary.yaml` per the analysis_plan.ground_findings_in_literature carve-out. Then `tool_path_finalize`, `tool_step_revision_options`, `present_to_researcher`.
- **Simulated result:** Audit PASSES (literature gate honored the carve-out). Researcher says "proceed".
- **Format clear?** yes — the analysis_plan + literature_per_step protocols both name the `literature_required: false` escape AND `step_intent` auto-waivers, and the v1.9.3 audit changelog says completeness gate now defers cleanly for it.
- **Know next?** yes — Step 02.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~30s.

### Turn 13 — Step 02 (count_matrix_assembly)
- **Wanted:** Build the count matrix via Rsubread::featureCounts.
- **Tool called:** Same loop. `classify_step_intent=ground` for the methods choice (featureCounts vs. HTSeq vs. salmon-quant) then `analyse` for the actual counting; created as one step `02_count_matrix_assembly` because the choice + execution are tightly coupled. Single mega-script forbidden → DAG: `02a_run_featurecounts_v1.R` + `02b_assemble_matrix_v1.R` + `02c_sanity_distribution_v1.R`.
- **Simulated result:** Counts table written to `data/output/counts.tsv`; focal figure = per-sample library-size barplot.
- **Format clear?** yes.
- **Know next?** yes — literature loop on the choice "why featureCounts over salmon for a gene-level DE workflow", then finalize.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~90s.

### Turn 14 — Step 02 (literature gate + finalize)
- **Tool called:** `literature/literature_per_step` (extract claim "featureCounts is the field-standard counter for gene-level bulk RNA-seq DE"), search, save Liao 2014 paper, write `findings_vs_literature.md` with verdict AGREES. `tool_audit_step_literature` → green.
- **Simulated result:** Pass; researcher proceeds.
- **Format clear?** yes.
- **Friction:** none.
- **TTC:** ~45s.

### Turn 15 — Step 03 (library_size_normalisation_eda)
- **Tool called:** DESeq2 vst normalization + PCA + sample-sample correlation heatmap. Single R script split into 3a/3b/3c. Focal figure = PCA scatter with treatment color-coding.
- **Simulated result:** Scripts written; pipeline runs; provenance sidecars present.
- **Format clear?** yes — but note: this step is a hybrid (normalisation = ground/methods; PCA + heatmap = visualisation). I classified as `analyse` because PCA *is* a finding (separation between groups). The classification doctrine in analysis_plan.classify_step_intent is clear that the AI should pick the closest fit and log a rationale in autopilot; in supervised I'd ask the researcher.
- **Know next?** yes — literature loop on "PCA before DE is standard" (AGREES, cite a methods paper).
- **Friction:** **FRICTION/LOW** — hybrid steps that span normalization (ground/methods) and PCA visualization (analyse/visualise) need clearer guidance on whether to split into two steps. The analysis_plan.create_step_folder "when to suggest a new step" block helps but doesn't squarely address "ground + visualise in one slug".
- **TTC:** ~80s.

### Turn 16 — Step 03 (close)
- Same close pattern. PASS.

### Turn 17 — Step 04 (deseq2_de_lps_vs_ctrl) — the centerpiece
- **Tool called:** `analysis_plan` again. `ground_methods` is non-trivial here: every parameter (design ~treatment, Wald test, BH FDR <0.05, |log2FC|>1, independentFiltering=TRUE) needs a citation. Run `tool_research_method` then `tool_literature_search_and_save` for Love 2014 (DESeq2), Benjamini-Hochberg 1995 (FDR), and IndependentFiltering (Bourgon 2010). `mem_methods_append` with the full citation chain. Pipeline: `04a_load_counts_v1.R` → `04b_fit_deseq2_v1.R` → `04c_extract_results_v1.R` → `04d_ma_plot_v1.R`.
- **Simulated result:** Output: `results_lps_vs_ctrl.tsv`, MA plot. ~1,200 DEGs at the cutoff. Hypothesis-relevant top genes (Il1b, Tnf, Cxcl10, Nfkbia) all present and significantly up.
- **Format clear?** yes — the analysis_plan.ground_methods anti-pattern example (lines 134-142 in the YAML) actually shows the DESeq2 case verbatim. Excellent.
- **Know next?** yes.
- **Friction:** none.
- **Doc gap:** none. (Big win — see §9.)
- **TTC:** ~150s.

### Turn 18 — Step 04 (literature gate + finalize)
- **Tool called:** `literature_per_step`. Top 5 claims extracted (e.g., "Il1b is the strongest induced gene at log2FC=6.1, padj=2e-50"). Searches per claim, downloads, writes `findings_vs_literature.md` — most verdicts AGREES (microglia LPS literature is rich); one EXTENDS for a moderately-induced gene not previously reported in this exact cell context. `tool_audit_step_literature` → green.
- **Friction:** none.
- **TTC:** ~75s.

### Turn 19 — Step 05 (volcano_top_immune_genes)
- **Tool called:** `classify_step_intent=visualise` with `literature.inherits_from: 04_deseq2_de_lps_vs_ctrl`. Python: `05a_volcano_immune_panel_v1.py` reads `04_*/data/output/results_lps_vs_ctrl.tsv`. Focal figure = volcano with the four highlighted immune genes labelled.
- **Simulated result:** Figure written with caption + summary sidecars. `tool_audit_figure_full` confirms DPI 300, Okabe-Ito palette, SVG companion. `tool_audit_figure_interactivity` (per its doc: "scatter/volcano > 200 marks") needs an HTML companion → `tool_figure_interactive_autogen` writes a Vega-Lite hover-tooltip sibling next to the PNG.
- **Format clear?** yes — TOOLS.md explicitly lists volcanos as needing interactive companions.
- **Know next?** yes — literature gate inherits.
- **Friction:** none.
- **TTC:** ~60s.

### Turn 20 — Step 05 (close)
- Inherit verdict from 04. PASS.

### Turn 21 — Step 06 (heatmap_immune_panel)
- **Tool called:** Python: top-50 DEGs by padj, z-scored across samples, clustered. Focal figure = annotated heatmap with treatment bars. Same `visualise` + `inherits_from: 04` pattern.
- **Simulated result:** PASS.
- **Friction:** none.
- **TTC:** ~60s.

### Turn 22 — Step 07 (fgsea_hallmark_pathways)
- **Tool called:** `classify_step_intent=analyse` (new findings on pathways). R fgsea against MSigDB Hallmark (`tool_external_tool_instructions` if the gmt download is treated as external; otherwise just download to step's data/input/). Scripts: `07a_rank_genes_v1.R` (Wald stat ranking) → `07b_run_fgsea_v1.R` → `07c_enrichment_plot_v1.R`. Focal figure = NES bar chart for top-10 enriched pathways.
- **Simulated result:** INFLAMMATORY_RESPONSE, TNF_SIGNALING_VIA_NFKB, INTERFERON_GAMMA_RESPONSE all NES > 2, padj << 0.001 — H02 supported. `mem_hypothesis_update(H02, status="supported", evidence="…")`.
- **Format clear?** yes.
- **Know next?** yes — literature_per_step on the GSEA findings.
- **Friction:** none.
- **TTC:** ~100s.

### Turn 23 — Step 07 (literature gate)
- **Tool called:** `literature_per_step`. Korotkevich 2021 (fgsea), Subramanian 2005 (GSEA), recent microglia-LPS GSEA papers. Top 5 claims grounded. Verdict AGREES for the headline pathways. Audit green.
- **Friction:** none.
- **TTC:** ~60s.

### Turn 24 — Cross-step sanity: workspace DAG
- **Tool called:** `tool_workflow_dag()` → renders `docs/workflow_dag.mermaid` showing 01 → 02 → 03 → 04 → {05, 06, 07}.
- **Simulated result:** Clean DAG written.
- **Friction:** none.
- **TTC:** ~10s.

### Turn 25 — Cross-step sanity: version coherence
- **Tool called:** `tool_audit_version_coherence()` across all 7 steps → confirms every output traces to the highest-version script on disk. `tool_state_freshness_check()` → state.json fresh; citations fresh.
- **Friction:** none.
- **TTC:** ~10s.

---

## 4. Per-step literature gate (interleaved — summarised)

Already interleaved above. Summary:

| Step | Literature gate outcome | Notes |
|------|-------------------------|-------|
| 01 (QC) | bypassed via `literature_required: false` | pure-data QC carve-out, doc-supported |
| 02 (counts) | AGREES | featureCounts canonical |
| 03 (norm + PCA) | AGREES | vst + PCA standard |
| 04 (DESeq2 DE) | AGREES (4) + EXTENDS (1) | core findings published; one novel gene |
| 05 (volcano) | INHERITED from 04 | step_intent=visualise + inherits_from |
| 06 (heatmap) | INHERITED from 04 | same pattern |
| 07 (GSEA) | AGREES | microglia-LPS pathway lit is rich |

Net: 1 EXTENDS verdict will need a Discussion paragraph (per `tool_discussion_coverage_audit`'s BLOCK rule), and zero DISAGREES / DEFERRED.

---

## 5. Audit + synthesis (turns 26-35)

### Turn 26 — Master audit
- **Tool called:** `tool_audit_quality_full()`.
- **Simulated result (per TOOLS.md example shape):** Runs all 6 gates (completeness, code_quality, prose, claims, preregister_diff, ground). The 1.9.3 changelog notes explicitly say grounding_verify is now listed in the description (was silently invoked). Returns `status="warning"` with 0 blockers and 2 warnings: (a) preregister_diff: no preregistration on file (we didn't run `methodology/preregistration`); (b) prose audit found one hedge in step 04's conclusions.md.
- **Format clear?** yes.
- **Know next?** yes — Address warnings or proceed; doc says preregister-absent is a warning not a blocker. Researcher decides to proceed.
- **Friction:** none.
- **Doc gap:** none.
- **TTC:** ~20s.

### Turn 27 — Synthesis preview
- **Tool called:** `tool_synthesis_preview(output_type="paper")` — cheap dry-run.
- **Simulated result:** Predicts ~3,500 words, 4 figures (one per H plus DAG), 18 citations, no gaps. (The 4 figures are: PCA from step 03, MA from 04, volcano from 05, GSEA from 07.)
- **Format clear?** yes.
- **Friction:** none.
- **TTC:** ~10s.

### Turn 28 — Outline the paper
- **Tool called:** `tool_route("outline the paper")` → `synthesis/synthesis_paper`. Per the protocol's multi-turn enforcement, this is turn 1 of the paper-writing pipeline → produce `synthesis/outline.md`.
- **Friction:** **FRICTION/MEDIUM** — Honest user friction here. The protocol *requires* one paper section per researcher prompt (lines 19-32 of `synthesis_paper.yaml`). The researcher who just wanted "draft the paper" in one go has to type "draft methods" / "draft results" / etc. 7-10 times. The protocol explains *why* (anti-one-shot, context hygiene) and says autopilot mode can chain them — but a fresh researcher on the default `supervised` autonomy will be surprised. The doc surface IS clear; the friction is product UX, not documentation.
- **Doc gap:** USE_CASES.md or START.md should put a "writing a paper takes ~10 prompts in supervised mode; switch to autopilot to chain them" hint near the "draft the paper" example. (USE_CASES says "draft the paper" implies one prompt.)
- **TTC:** ~30s.

### Turn 29 — Draft methods
- **Tool called:** `tool_synthesize(section="methods")`.
- **Simulated result:** Methods section drafted (~600 words) into `synthesis/paper.md`. References pulled from project + per-step citation ledgers. `tool_audit_synthesis` runs as part of the call.
- **Friction:** none — once you accept the multi-turn rule.
- **TTC:** ~25s.

### Turns 30-33 — Draft results, draft discussion, draft intro, draft abstract
- Each call: `tool_synthesize(section=<name>)`. Discussion handler invokes `tool_writing_discussion_from_verdicts` so the one EXTENDS verdict from step 04 gets its mandatory paragraph; `tool_discussion_coverage_audit` then passes.
- Simulated final lengths: intro ~600w, methods ~600w, results ~550w, discussion ~700w, abstract ~250w, conclusion ~150w — clears `quality_bar` in `synthesis_paper.yaml`.
- **Friction:** none.
- **TTC each:** ~25s × 4 = ~100s total.

### Turn 34 — Final assembly + PDF
- **Tool called:** "assemble + compile to PDF" → loader sees `pdf_compile_engine=typst` → `tool_synthesize(final_assembly=true)` then `tool_paper_compile_typst(venue="generic_two_column")`. v1.9.3 changelog explicitly adds `tool_paper_compile_typst` to the `synthesis_paper` decomposition (AUDIT-v1.9.2-029), conditional on `pdf_compile_engine == typst`. The `generic_two_column.typ` template is present at `templates/typst/generic_two_column.typ`.
- **Simulated result:** `synthesis/paper.pdf` written, ~6 pages, 4 figures, 18 verified citations.
- **Format clear?** yes — TOOLS.md and the v1.9.3 detailed changelog both name the tool + venue list.
- **Know next?** yes — Dashboard then pre-submission.
- **Friction:** none.
- **Doc gap:** none (this is one of the v1.9.x fixes that paid off — see §9).
- **TTC:** ~30s.

**>>> REACHED `tool_paper_compile_typst` STEP. <<<**

### Turn 35 — Dashboard (v2 explore)
- **Tool called:** `tool_dashboard_create(audience="academic", mode="explore", override_completeness_gate=false)`.
- **Simulated result (per TOOLS.md example):** `synthesis/dashboard.html` written, ~600 KB single file, 4 embedded figures (PCA, MA, volcano, GSEA), Hypothesis-by-Hypothesis section with H01 (supported, evidence from steps 04-06) + H02 (supported, evidence from step 07), verdicts grid showing the EXTENDS verdict from step 04 prominently. Sidebar TOC + lightbox. Volcano figure's interactive Vega-Lite companion auto-embeds.
- **Format clear?** yes — synthesis_dashboard.yaml lines 16-37 enumerate every universal section; TOOLS.md shows the exact return shape.
- **Know next?** yes — `audit/pre_submission_checklist`.
- **Friction:** none.
- **TTC:** ~25s.

**>>> REACHED `synthesis/dashboard.html` STEP. <<<**

---

## 6. Cross-checks + sign-off

- `tool_audit_dashboard_content` → runs implicitly inside dashboard_create per the protocol. Confirms WCAG 2.2 AA, numeric grounding, 5-minute-reviewer reads the headline correctly.
- `audit/pre_submission_checklist` → GREEN with one YELLOW (no preregistration on file; flagged as a transparency issue, not a blocker). Punch list: register the SAP retroactively on OSF if the venue requires it; otherwise note in Limitations that the analysis was not preregistered (already there from step 04).
- `tool_citations_verify` → all 18 cites resolve online (Crossref + Semantic Scholar).
- `tool_audit_cliches` → 0 hits.
- `sys_session_handoff` → writes handoff doc for the next chat (or for the researcher's PI).

---

## 7. Top 5 friction points

| # | Severity | Title | Tool / Protocol | Suggested fix |
|---|----------|-------|-----------------|---------------|
| 1 | **MEDIUM** | "Draft the paper" actually means 7-10 prompts | `synthesis/synthesis_paper` | START.md and USE_CASES.md should put a "writing a paper is a multi-turn protocol in supervised mode (one section per prompt); switch to autopilot to chain them in one ask" callout next to every "draft the paper" example. Right now the user reads "draft the paper" and expects one shot. |
| 2 | **LOW** | "Step" overloaded between pipeline-stage and analysis_plan-iteration | `tool_plan_turn`, `analysis_plan.yaml` | PROTOCOLS.md and TOOLS.md should explicitly disambiguate "an `analysis_plan` inner-loop iteration is one *unit* for `tool_plan_turn` batch sizing". Today the same word covers both. |
| 3 | **LOW** | Hybrid steps spanning ground/normalise + analyse/visualise (e.g. vst + PCA) need a tiebreaker rule | `analysis_plan.classify_step_intent` | Add a fourth example to the carve-out block: "when a step covers normalisation + EDA viz, default to `analyse` and note the normalisation in `## Methods (full detail)`; split into a sibling step only when normalisation itself is a finding." |
| 4 | **LOW** | Power-analysis grounding lives in `analysis_plan`, not in `domain/research_design` | `domain/research_design` | Add a one-line callout at the end of `research_design`: "The actual literature-citation pass for the power calculation runs inside the per-step ground_methods gate of analysis_plan." |
| 5 | **LOW** | Default-config-only project (no `researcher_config.yaml` edits) would silently end up with `citation_style: apa` on a biomedical paper that should be `vancouver` | `templates/researcher_config.yaml` | The wizard could detect domain at intake time and prompt to flip citation_style + venue_template defaults; today the field is template-default APA. |

**No HIGH-severity friction encountered.**

---

## 8. Top 5 doc / guidance gaps

1. **No worked end-to-end RNA-seq example anywhere in `docs/`.** USE_CASES.md mentions "fit a logistic regression and check assumptions" but never walks a multi-step biology workflow (DESeq2 → volcano → GSEA → paper → dashboard). A 1-page scenario walk-through in USE_CASES would let a fresh agent confirm the routing decisions on the way in.
2. **"Multi-turn enforcement" of `synthesis_paper` is hidden in the protocol YAML.** Researchers and fresh AIs both encounter it as a surprise. Should be promoted to docs/RESEARCHER_GUIDE.md and docs/START.md.
3. **`tool_plan_turn` batch-size semantics** under model_profile — the doc says "small=1, medium=3, large=6, weighted for heavy tools" but doesn't show a worked example of weighting (e.g. `tool_synthesize` = ?, `tool_audit_quality_full` = ?). A fresh AI ends up guessing.
4. **`step_intent` carve-out vs. `literature_required: false` vs. `inherits_from`** — three escape hatches with overlapping semantics. The literature_per_step.yaml header explains them well, but a single decision-table in AI_GUIDE.md ("when do I use which?") would shortcut a lot of re-reading.
5. **Where does "the project corpus" literature search live (`literature/literature_search`) vs the per-step loop (`literature/literature_per_step`)?** The two are well-named but a fresh AI might wonder if it should run literature_search at all when every step has its own loop. The answer is yes (the project corpus seeds the per-step queries), but it's not stated in those words anywhere I read.

---

## 9. Top 5 things that worked well (positive findings)

1. **Tool return-shape examples in TOOLS.md (§ Return-shape examples).** Showing the JSON shape for `tool_intake_autofill`, `tool_dashboard_create`, `tool_step_complete`, and `tool_audit_quality_full` was the single highest-leverage doc choice in the whole repo. A fresh agent can simulate a tool call with confidence; without these, the agent would have to grep `src/` (which the validation rules forbid).
2. **The `analysis_plan.ground_methods` anti-pattern block (lines 134-142) literally uses the DESeq2 example.** "We use DESeq2 because it's standard" (bad) vs. the full-citation form (good) is the exact shape this scenario needed. It set the tone for every method-grounding decision downstream.
3. **`methodology/pick_tool_stack.yaml` names bulk RNA-seq → R Bioconductor (DESeq2/edgeR/limma) explicitly,** with `field_practice_overrides_preference=true` in researcher_config. A fresh AI that defaults-to-Python (which is a real failure mode) gets steered to R cleanly. Multi-language orchestration is documented in `methodology/mixed_language_orchestration` for the cross-language steps.
4. **The v1.9.3 router triggers for DESeq2 / DE / DEG / scRNA-seq** (changelog AUDIT-v1.9.2-028) mean a researcher who says "run DE on this" lands on `analysis_plan` instead of `bayesian_analysis`. That fix carried through visibly here.
5. **`tool_paper_compile_typst` is now in the `synthesis_paper` decomposition** (changelog AUDIT-v1.9.2-029, conditional on `pdf_compile_engine=typst`). A small / medium model that loads only the protocol summary now sees the PDF-compile tool listed. v1.9.4 inherits the fix.
6. **Bonus:** `templates/researcher_config.yaml` is the most readable config template I've encountered in a research tool — every field has inline commentary, every enum value is enumerated, and the "this is the single source of truth" header tells you exactly which file to edit.

---

## 10. Final rating

**8.5 / 10**

**Rationale:** The doc surface is genuinely sufficient for a fresh AI to drive a multi-step biology RNA-seq workflow end-to-end without reading source. The two-call boot rule is unambiguous, the analysis_plan loop is well-scaffolded, the literature-per-step gate is enforced and documented, the synthesis protocol enforces the multi-turn discipline that prevents one-shot drafts, and the Typst PDF + dashboard wiring are both present and exercised by `tool_synthesize` + `tool_paper_compile_typst` + `tool_dashboard_create`. The 1.5 points off:

- 1.0 point: the "draft the paper" expectation gap (Top friction #1) — this is a real product-UX surprise even for a researcher who's read START.md.
- 0.5 points: small ambiguities (step-overload, hybrid intent classification, step batch-size weighting) that would benefit from worked examples or decision tables.

No HIGH-severity friction was encountered. Zero "had to read src/" moments. Compared to a hypothetical v1.9.3 baseline, the v1.9.4 surface is materially smoother for biology workflows specifically because the DESeq2/DE router triggers, the Typst decomposition wiring, and the master-audit grounding-gate documentation fix were all in place.

---

## 11. Onboarding-friction count (first 5 turns)

**0 friction items in turns 1-5.** Boot + route + config + intake landed cleanly with no surprises.

---

## 12. Step-reach summary

- **Reached `tool_paper_compile_typst` step?** **YES** (turn 34).
- **Reached `synthesis/dashboard.html` step?** **YES** (turn 35).
- **Reached `audit/pre_submission_checklist`?** YES (turn 36 implicit; GREEN with one YELLOW for absent preregistration).
- **Total turns to dashboard:** 35.
- **Per-step literature loop fired:** 7 times (6 substantive + 1 carve-out skip).
- **Step intents used:** `analyse` (5), `visualise` (2), `ground` (1, combined with analyse in step 02). All carve-outs honoured.
