# Research-OS v1.9.4 — Fresh-Agent Usability Validation (Synthesis)

**Date:** 2026-06-05
**Method:** 5 fresh-agent doc-surface walkthroughs (Claude Opus 4.7, 1M ctx). Each agent had access to `docs/*.md`, `README.md`, `templates/*`, `protocols/**/*.yaml`, and `CHANGELOG.md` only — no `src/research_os/**/*.py` reads. MCP tool calls were simulated from the documented descriptions + protocol `expected_outputs`.
**Scenarios:** RNA-seq differential expression (biology), Henry James close-reading (humanities), n=8 clinician interviews (qualitative), quicksort microbenchmark (engineering), chordal-graph theorem (theory/math).
**Total turns logged:** 165 (≈33/scenario).
**Per-scenario reports:** `docs/usability_v1.9.4/scenario_{1..5}_*.md`.

---

## 1. Executive summary

| Metric | Value |
|---|---|
| Average usability rating | **6.6 / 10** (7,7,7,7,5) |
| Total turns logged | 165 |
| Scenarios reaching `paper.pdf` step | 5 / 5 |
| Scenarios reaching `dashboard.html` step | 5 / 5 (1 partial — theory) |
| Total HIGH-severity friction events | **12** |
| Total MEDIUM-severity friction events | **27** |
| Total LOW-severity friction events | **29** |
| Total onboarding friction (first 5 turns) | 15 (4 HIGH-loaded in theory + humanities) |

**Headline finding.** Four of the five scenarios (biology, humanities, qualitative, engineering) score 7/10 and reach both deliverables cleanly. The doc-surface for the empirical+IMRAD spine — `sys_boot` → `tool_route` → `analysis_plan` → per-step audits → `synthesis_paper` → `tool_paper_compile_typst` → `tool_dashboard_create` — is genuinely high quality. The boot pattern, the per-step audit stack, and the `pick_tool_stack` doctrine are exemplary.

The **theory/math scenario alone scored 5/10** because every audit gate and verdict enum assumes empirical IMRAD. The theory_math pack itself (8 protocols, well-designed) is excellent in isolation but is **invisible from user-facing docs** and structurally **misaligned with the per-step gate stack**. This is the same shape of finding that humanities had to a smaller degree (the pack is well-built but the last-mile assembly tooling is STEM-biased).

**The single highest-leverage v1.9.4 work-item is "make per-step audits intent-aware."** Three scenarios (humanities, qualitative, theory, engineering) all hit the same root cause: `tool_audit_step_completeness` requires a focal figure + non-stub conclusions; `tool_audit_step_literature` requires an AGREES/DISAGREES/EXTENDS/DEFERRED verdict. These assumptions break on (a) corpus-audit / planning / grounding steps that have no claim yet, (b) qualitative reports that have no figure, (c) viz-only steps that re-render prior step's result, (d) theory steps that have no script. The fix has the same shape in all four cases: classify step intent at create-time and waive the structurally-inappropriate gates.

---

## 2. Per-scenario distillation

### Scenario 1 — Biology / RNA-seq DE (rating 7/10, 35 turns)
Walked LPS-microglia 6v6 bulk RNA-seq from intake through DESeq2 → volcano/heatmap → GSEA → literature-set overlap → audit → paper (generic_two_column) → dashboard (explore mode) in 35 turns. **Zero HIGH friction.** Three MEDIUM frictions, all peripheral: (a) `literature_required: false` exemption is documented for data-engineering steps but not for pure-viz steps that have no new numeric claim; (b) `tool_dashboard_create` `mode` enum (explore/story/executive/teaching) isn't enumerated in TOOLS.md; (c) `literature_per_step` is high-volume on analytical steps and lacks DEFERRED worked examples. Boot pattern + `pick_tool_stack` doctrine + four-sidecar figure contract worked beautifully. Onboarding: 2 LOW frictions in turns 1-5.

### Scenario 2 — Humanities / Henry James close-reading (rating 7/10, 30 turns)
Hybrid distant+close reading on 4 James novels reached both deliverables. **Humanities pack protocols (close_reading, distant_reading, digital_humanities_workflow, citation_chains) are the single strongest positive finding of the entire validation** — they read like they were written by working humanists. But the **last-mile assembly is STEM-biased**: `tool_citations_verify` runs Crossref/SS/PubMed/arXiv only — humanities monographs (Cohn, Banfield, Palmer) often lack DOIs and block paper assembly (HIGH); `researcher_config.citation_style` enum is STEM-only (no MLA/Chicago) and there is no `humanities_essay.typ` Typst template (HIGH); `tool_audit_prose` mis-flags humanities hedging as vague quantifiers (MEDIUM); there is no `tool_humanities_apparatus_audit` enforcing the close_reading quality bar (MEDIUM); per-step literature gate forces awkward DEFERRED verdicts on early pipeline steps (MEDIUM). Onboarding: 3 frictions in turns 1-5 (1 HIGH on citation_style enum).

### Scenario 3 — Qualitative / n=8 clinician interviews (rating 7/10, 35 turns)
Thematic analysis with hybrid deductive+inductive coding reached both deliverables. **`qualitative_quality_audit.yaml` is the single strongest protocol in the chain** — saturation evidence (not power) for n=8, explicit single-coder handling, absent-member-checking documented as limitation. Major gap: **NO pre-coding PII redaction tool, protocol, or template anywhere** (HIGH). HIPAA/IRB/GDPR require this; quote-level audit at the END is too late because coding has already happened on un-redacted text. Secondary frictions (all MEDIUM): `qualitative_research.next_protocol = guidance/analysis_plan` mis-routes (should point to `qualitative_quality_audit`); `coding_scheme_development` assumes ≥2 coders with no single-coder branch; figure-required hard-fail conflicts with no-figure qualitative steps; `tool_step_complete` is referenced but not in TOOLS.md table; `workspace/.qualitative/` vs `workspace/<NN_slug>/` directory inconsistency. Onboarding: 2 LOW frictions.

### Scenario 4 — Engineering / quicksort microbenchmark (rating 7/10, 35 turns)
3 quicksort variants × 5 input sizes × 10 reps benchmarked through `method_comparison` (9 steps) to paper.pdf (ieee_conf) + dashboard.html. **Zero HIGH friction.** Six MEDIUM frictions concentrated in three themes: (1) `discover/` is named as a protocol category in docs but no `discover/` directory exists in the protocols tree (doc-vs-implementation drift); (2) per-step audits over-fire on planning/grounding/scaffolding steps (same root cause as theory/humanities/qual) and force `override_literature_gate=true` workarounds; (3) `method_comparison` reads as ML-flavoured (folds, hyperparameter trials, ROC) and engineering benchmarks must translate vocabulary unaided; (4) engineering pack fires on detection but no protocol routes into the pack tools (`tool_engineering_fault_tree_render`, `_fmea_render`, `_requirements_matrix` are orphaned); (5) `next_protocol` semantics are ambiguous (loop-back vs forward-default); (6) "code under benchmark" file-location is undefined. Onboarding: 4 frictions (3 LOW + 1 MEDIUM).

### Scenario 5 — Theory / chordal-graph chromatic-number theorem (rating 5/10, 35 turns)
Reached paper.pdf via `tool_paper_compile_typst(generic_thesis)` and a partial dashboard.html with multiple overrides. **The theory_math pack (8 protocols + 3 tools) is well-designed and theorist-literate** — `proof_strategy_selection` forces small-case probes, `lemma_library` applies semver to lemmas, `theory_paper_structure` uses the non-IMRAD 6-section format that *Annals*/JAMS/FOCS expect, `conjecture_tracking` status lattice (open/partial_progress/proven/disproven/counter_example_found) is mathematically literate. But it is bolted onto a core that assumes empirical IMRAD. **9 HIGH frictions:** literature-gate verdict enum has no value for cited prior results imported as lemmas; `tool_audit_step_completeness` demands figure+script+conclusions that theory steps never have; `tool_dashboard_create` assumes numeric grounding; `synthesis_paper` vs `theory_paper_structure` integration is undocumented; theory_math pack is invisible in USE_CASES/PROTOCOLS/START/FAQ/AI_GUIDE. The pack design is 8/10 but the surrounding integration is closer to 3/10. Onboarding: 4 frictions in turns 1-5 (1 HIGH).

---

## 3. Cross-scenario themes (the highest-leverage fixes)

A friction theme that hits 3+ scenarios is structural, not scenario-specific. Eight such themes emerged.

### Theme A — Per-step audits are not intent-aware (5/5 scenarios)
`tool_audit_step_completeness` demands focal figure + sidecars + non-stub conclusions + no mega-script. `tool_audit_step_literature` demands `findings_vs_literature.md` with an AGREES/DISAGREES/EXTENDS/DEFERRED verdict per claim. These assumptions break on:
- **Biology (S1):** pure-visualization steps that re-render a prior step's result with no new numeric claim. `literature_required: false` is documented for data engineering but not for viz-only.
- **Humanities (S2):** corpus-audit and raw-model-output steps with no comparative claim yet; close-reading "apparatus.md" markdown documents that the audit may not count as a focal artefact (v1.9.3 partially fixed this but the fresh-agent reading the docs doesn't know).
- **Qualitative (S3):** qualitative reports with no figure and no statistical claim; figure-required hard-fail vs `qualitative_research.expected_outputs` saying no figure expected.
- **Engineering (S4):** planning/grounding steps (methods spec, literature ground) that have no figure and no findings; AI must use `override_literature_gate=true` twice in 9 steps.
- **Theory (S5):** every proof step lacks figure+script+conclusions; literature-gate verdict enum has no value for "cited prior result imported as lemma".

**Root cause:** the audits treat all steps as analytical/empirical. Step intent (plan / ground / analyse / visualise / synth / proof / apparatus) is never declared at create-time.

### Theme B — Pack-specific protocols are well-designed but the user-facing docs ignore them (3/5: humanities, qualitative, theory)
The protocol packs (`research_os_humanities/`, qualitative methodology, `research_os_theory_math/`) consistently score 8-9/10 on internal design but the user-facing entry points to them are weak or missing:
- **Theory (S5, HIGH):** `docs/USE_CASES.md` has no theorist row; `docs/PROTOCOLS.md` does not list the 8 theory_math protocols; `docs/START.md` has no theory example; `docs/FAQ.md` never mentions theory. A working mathematician has no doc-surface reason to believe Research-OS supports them.
- **Qualitative (S3, MEDIUM):** end-to-end recipe (`qualitative_research` → `coding_scheme_development` → `qualitative_quality_audit` → `audit_and_validation` → `synthesis_paper` → `synthesis_dashboard`) is not documented anywhere; AI must read 4 separate YAMLs to compose it.
- **Humanities (S2, MEDIUM):** TOOLS.md lists only 2 dedicated humanities tools and never says "the pack is scaffold-first, use `tool_python_exec` for distant-reading methods"; that warning is buried in `distant_reading.yaml` step body.

**Pattern:** packs contribute router triggers + tools at import time, but no doc rolls those up into user-readable "here's what this pack does and when it fires" pages.

### Theme C — Last-mile assembly tooling is STEM-biased (3/5: humanities, theory + engineering on edges)
Citation verification, citation styles, and Typst templates all assume STEM publishing norms:
- **Humanities (S2, HIGH):** `tool_citations_verify` (Crossref/SS/PubMed/arXiv) doesn't cover humanities monographs (Princeton UP, Cornell UP) that often lack DOIs; it is a HARD gate that blocks paper assembly.
- **Humanities (S2, HIGH):** `researcher_config.citation_style` enum is `apa|vancouver|acm|ieee|nature` — no MLA, no Chicago author-date, no Chicago notes-bib; no `humanities_essay.typ` Typst template.
- **Theory (S5, MEDIUM):** `citation_style` enum has no math styles (amsplain, alpha, siam).
- **Engineering (S4, LOW):** `venue_template × citation_style` compatibility matrix missing — `ieee_conf` template vs `citation_style: ieee` coherence is not documented.

### Theme D — `next_protocol` semantics are ambiguous (3/5: engineering, qualitative, theory)
`next_protocol:` field can mean "the forward default step" or "the loopback for iteration", and the doctrine never says which:
- **Engineering (S4, MEDIUM):** `method_comparison.next_protocol: guidance/analysis_plan` is a loopback hint but reads as forward default; on hypothesis-supported the actual next step is `audit/audit_and_validation`.
- **Qualitative (S3, MEDIUM):** `qualitative_research.next_protocol: guidance/analysis_plan` mis-routes the AI; should be `methodology/qualitative_quality_audit`.
- **Theory (S5, LOW):** `conjecture_tracking.next_protocol: null` is plausible (it's a registry) but the user doesn't know to manually invoke the proof workflow next.

### Theme E — Multi-protocol routing decomposition is opaque (2/5 + edges across all)
`tool_route` may match multiple protocols inside the same sub_intent (humanities had `close_reading` + `distant_reading` + `digital_humanities_workflow` all hit the same prompt) but the resolution mechanism is undocumented. Engineering (S4) hit a related issue with `discover/` category in docs but no `discover/` directory.

### Theme F — Tool return-shape opacity (4/5)
Multiple scenarios logged that high-value tools' return JSON shapes aren't documented:
- `tool_intake_autofill` (S1, S2, S3 — what it returns + how it handles text corpora vs tabular vs interview transcripts).
- `tool_dashboard_create` (S1 — `mode` enum not enumerated).
- `tool_step_complete` (S3 — referenced but not in TOOLS.md table).
- `tool_audit_quality_full` (S1 — bundle contents listed but not return-shape).
- `tool_redteam_review` (S5 — referenced in proof_verification_workflow.yaml but not in TOOLS.md).
- `tool_plan_advance(skip_reason=...)` (S4 — skip parameter undocumented).

### Theme G — Domain-pack composition gaps (3/5)
Packs detect on intake but no protocol routes into the pack tools downstream:
- **Engineering (S4, MEDIUM):** engineering pack fires but `tool_engineering_fault_tree_render` / `_fmea_render` / `_requirements_matrix` are never referenced from `method_comparison` decomposition. Pack is decorative.
- **Qualitative (S3, MEDIUM):** qualitative pack has only 2 tools (`tool_qualitative_codebook_diff`, `_quote_provenance`); no `tool_qualitative_pii_redact`, no `tool_qualitative_code_transcript`, no `tool_qualitative_apply_codebook`.
- **Theory (S5, MEDIUM):** `tool_theory_math_dep_graph` only parses `.lean`/`.v`; informal-markdown proofs yield empty graphs.

### Theme H — Per-step literature gate over-fires on early/non-analytical steps (4/5)
QC, corpus-audit, planning, grounding, and lemma-cite steps all triggered literature-gate friction:
- **Biology (S1):** `literature_required: false` for QC works but viz-only exemption isn't documented.
- **Humanities (S2):** corpus-audit step had to invent a DEFERRED verdict.
- **Engineering (S4):** literature-grounding step itself triggered the literature gate; needed `override_literature_gate=true`.
- **Theory (S5):** every cited-prior-lemma needed a shoehorned AGREES verdict because IMPORTED_AS_CITED isn't in the enum.

---

## 4. What worked well (preserve these — they are load-bearing)

Listed because protecting these patterns matters as much as fixing friction.

1. **Two-call boot pattern (`sys_boot` + `tool_route`).** Documented identically in `AGENTS.md`, `templates/CLAUDE.md`, `docs/AI_GUIDE.md`, and per-IDE rules files. All 5 fresh agents were unblocked in under 30s. **Zero ambiguity in 5/5 scenarios.**
2. **`pick_tool_stack` carries field-practice answers in its doctrine block.** Biology agent landed on R Bioconductor DESeq2 in 20s because the protocol literally says "Bulk RNA-seq DE → R Bioconductor (DESeq2, edgeR, limma)". This pattern should be copied everywhere.
3. **Hard rules in `AGENTS.md` are absolute and mechanical.** No causal language on observational data, no invented citations, immutable `inputs/raw_data` + `inputs/literature`. A fresh agent cannot accidentally violate these.
4. **Four-sidecar figure contract (`.caption.md` + `.summary.md` + `.prov.json` + `.svg`).** Concrete, mechanical, easy to comply with. Every figure step has the same shape. (S1, S4 specifically called this out.)
5. **`tool_step_complete` bundling.** Wraps `tool_path_finalize` + `tool_audit_step_completeness` + `tool_audit_step_literature` + `tool_step_revision_options` into one call. Reduces friction on small models. (Note: it's also Friction #5 in S3 because it's referenced but not in TOOLS.md table — fix the doc gap, keep the design.)
6. **Quality-gate stack has real teeth.** Six independent gates (step_completeness, step_literature, quality_full, dashboard_content, reviewer_sim, pre_submission_checklist) each surface a different failure mode. "Every override resurfaces at pre-submission" is a thoughtful design pattern. (S4 specifically called this out.)
7. **Typst-first PDF compilation with pre-built venue templates.** No LaTeX dependency hell. Generic_two_column + generic_thesis + ieee_conf all worked in their scenarios. (S1, S3, S4, S5.)
8. **`researcher_config.yaml` template is self-documenting.** Every field has an inline comment + enum + consequences. Fresh agent can configure without external docs. (S3 specifically called this out.)
9. **Scaffold-not-script doctrine is genuinely respected.** `distant_reading` names LDA / BERTopic / Burrows's Delta / NetworkX without hardcoding hyperparameters. `pick_tool_stack` recommends but doesn't choose for the AI. (S2, S5 confirmed.)
10. **Humanities pack protocols are field-true.** `close_reading.yaml`, `distant_reading.yaml`, `digital_humanities_workflow.yaml`, `citation_chains.yaml` were the strongest single positive finding. Same compliment applies to `qualitative_quality_audit.yaml` (S3) and `proof_strategy_selection.yaml` + `lemma_library.yaml` (S5).
11. **Per-step `findings_vs_literature.md` with AGREES/DISAGREES/EXTENDS/DEFERRED verdicts.** When the verdict enum fits the step, this is excellent — gives synthesis_paper concrete material to draft the Discussion from. (S1, S3, S4 confirmed.)
12. **Router trigger vocabulary on `method_comparison` is excellent.** "benchmark these methods", "head-to-head", "bake-off", "shoot-out", "horse race", "which model is best" — comprehensive vocabulary capture. (S4 specifically called this out.)
13. **Dashboard v2 story-mode design is well thought out.** `synthesis_dashboard.yaml` treats the dashboard as paper-as-interactive with per-hypothesis grouping. Maps cleanly onto humanities block-quote + apparatus + close-reading verdict workflow. (S2 specifically called this out.)
14. **`docs/START.md` is genuinely lean and complete for first-time setup.** Cheatsheet altitude is right; fresh researcher reaches "I know what to type" in under 15 minutes. (S4 specifically called this out.)

---

## 5. v1.9.4 fix list (prioritized by frequency × severity)

Total: **22 items**, sized at 15-180 minutes each. Estimated total effort: ~24 hours of focused edits.

Items grouped by category. Each entry has id / title / category / est_minutes / files_to_touch / rationale.

### Category: EDGE_CASE (5 items) — make per-step audits intent-aware (Theme A)

**F-001** — Add step-intent classification to step-create
- Category: `EDGE_CASE`
- est_minutes: **120**
- files_to_touch: `src/research_os/protocols/guidance/analysis_plan.yaml`, `templates/step_summary.yaml.template` (if exists, else create), `docs/AI_GUIDE.md` § per-step loop
- rationale: 5/5 scenarios hit per-step-audit over-fire. Adding a `step_intent: plan|ground|analyse|visualise|synth|proof|apparatus` field at create-time is the single highest-leverage fix in the validation; it lets F-002 + F-003 + F-004 auto-waive correctly.

**F-002** — Auto-waive figure requirement for plan/ground/proof/apparatus steps in `tool_audit_step_completeness`
- Category: `EDGE_CASE`
- est_minutes: **45**
- files_to_touch: `docs/TOOLS.md` (entry for `tool_audit_step_completeness`), `src/research_os/protocols/guidance/analysis_plan.yaml`, `src/research_os/protocols/methodology/qualitative_research.yaml` (add explicit `figure_required: false` note), `src/research_os_humanities/protocols/method/close_reading.yaml` (already markdown-aware in v1.9.3 per CHANGELOG, just document in TOOLS.md)
- rationale: hit by S1 (viz-only), S2 (corpus audit, close-reading apparatus markdown), S3 (qualitative no-figure), S4 (planning steps), S5 (every proof step). Without F-001 this needs to be done as a hardcoded carve-out list; with F-001 it becomes intent-driven.

**F-003** — Extend `tool_audit_step_literature` verdict enum: add `IMPORTED_AS_CITED` and `SPECIALIZES`; document when DEFERRED is the intended answer
- Category: `EDGE_CASE`
- est_minutes: **60**
- files_to_touch: `src/research_os/protocols/literature/literature_per_step.yaml`, `docs/TOOLS.md` (entry for `tool_audit_step_literature`)
- rationale: S5 HIGH (theory cited-prior lemmas have no fitting verdict); S2 + S4 forced DEFERRED on early steps with no comparative claim; S1 (viz-only steps). The enum is the wrong shape for non-empirical-finding steps. Add 2 verdicts + document the DEFERRED carve-out.

**F-004** — Document the "pure visualization of prior step" exemption alongside QC/normalization in `literature_per_step.yaml`'s `Skip ONLY when` block
- Category: `EDGE_CASE`
- est_minutes: **15**
- files_to_touch: `src/research_os/protocols/literature/literature_per_step.yaml`, `src/research_os/protocols/guidance/analysis_plan.yaml` § `ground_findings_in_literature`
- rationale: S1 MEDIUM. Cheap one-line fix; reduces literature-loop volume on viz steps.

**F-005** — Document per-step audit override paths (every `override_*` flag, where it lives, what its rationale schema is)
- Category: `EDGE_CASE`
- est_minutes: **45**
- files_to_touch: `docs/TOOLS.md`, `docs/AI_GUIDE.md`
- rationale: S5 HIGH ("no doc shows how to override per-step audit gates; only synthesis-level overrides documented"); S4 had to invoke `override_literature_gate=true` twice without crisp guidance. Override is the escape hatch — document it once, well, with examples.

### Category: AI_GUIDANCE (5 items) — fix protocol "WHEN to call this" + next_protocol semantics (Themes D, G)

**F-006** — Fix `qualitative_research.next_protocol` to point at `methodology/qualitative_quality_audit` (not `guidance/analysis_plan`)
- Category: `AI_GUIDANCE`
- est_minutes: **15**
- files_to_touch: `src/research_os/protocols/methodology/qualitative_research.yaml`
- rationale: S3 MEDIUM. One-line fix; mis-routes the AI to a generic analysis-plan loop instead of the qualitative-specific audit.

**F-007** — Add `next_protocol_kind: forward_default | iterate_back | terminal` to protocol schema; document in PROTOCOL_DOCTRINE.md; backfill all 88 protocols
- Category: `AI_GUIDANCE`
- est_minutes: **180**
- files_to_touch: `docs/PROTOCOL_DOCTRINE.md`, every `src/research_os/protocols/**/*.yaml` (88 files, mechanical edit), `scripts/preflight.py` (add a check)
- rationale: S3 + S4 + S5 MEDIUM. Semantics are ambiguous across the catalogue. Labelling each `next_protocol` as forward/iterate-back/terminal removes the "is this a loopback or the next mandatory step?" ambiguity.

**F-008** — Add the end-to-end qualitative recipe to `docs/USE_CASES.md` (qualitative_research → coding_scheme_development → qualitative_quality_audit → audit_and_validation → synthesis_paper → synthesis_dashboard)
- Category: `AI_GUIDANCE`
- est_minutes: **30**
- files_to_touch: `docs/USE_CASES.md`
- rationale: S3 MEDIUM. Each protocol is router-discoverable in isolation but the composition is implicit. Add 1 recipe row.

**F-009** — When engineering pack is active, `method_comparison` decomposition should mention `tool_engineering_requirements_matrix` for hypothesis→measurement→expected→observed mapping
- Category: `AI_GUIDANCE`
- est_minutes: **30**
- files_to_touch: `src/research_os/protocols/methodology/method_comparison.yaml`, `docs/TOOLS.md` (engineering pack section)
- rationale: S4 MEDIUM. Engineering pack fires on intake but is orphaned from the benchmark workflow. Optional pack-aware decomposition closes the loop.

**F-010** — Engineering/systems-benchmark sub-section in `method_comparison.yaml`: warm-up runs vs folds, CPU governor + isolation, paired Wilcoxon on heavy-tailed timings, log-log plots, stdlib sort as baseline
- Category: `AI_GUIDANCE`
- est_minutes: **45**
- files_to_touch: `src/research_os/protocols/methodology/method_comparison.yaml`
- rationale: S4 MEDIUM. `method_comparison` reads as ML-flavoured even though it's named generically. Add the 1-paragraph translation table at the top of relevant steps.

### Category: MISSING_PROMPT (3 items) — tool outputs need next-step pointers (Theme F)

**F-011** — Enumerate `tool_dashboard_create` `mode` parameter values in TOOLS.md (explore/story/executive/teaching); cross-link from `synthesis_dashboard.yaml`
- Category: `MISSING_PROMPT`
- est_minutes: **15**
- files_to_touch: `docs/TOOLS.md`, `src/research_os/protocols/synthesis/synthesis_dashboard.yaml`
- rationale: S1 MEDIUM. Trivial doc fix; researcher asked for "explore mode" and the doc didn't enumerate it.

**F-012** — Add `tool_step_complete` as a first-class entry in TOOLS.md table, or document it as alias for `tool_path_finalize` in the audit-extensions section
- Category: `MISSING_PROMPT`
- est_minutes: **20**
- files_to_touch: `docs/TOOLS.md`
- rationale: S3 MEDIUM. Tool is referenced (AGENTS.md, audit-extensions) but missing from the canonical table; fresh AI is confused about whether it's an alias.

**F-013** — Add return-shape examples (sample JSON) for `tool_intake_autofill`, `tool_dashboard_create`, `tool_step_complete`, `tool_audit_quality_full` in TOOLS.md
- Category: `MISSING_PROMPT`
- est_minutes: **60**
- files_to_touch: `docs/TOOLS.md`
- rationale: S1 + S3 (intake_autofill on non-tabular data); S1 (dashboard_create modes); general tool opacity. Pick the 4 highest-traffic tools and show one return-shape block each.

### Category: TOOL_DISCOVERABILITY (3 items) — protocols/docs should mention tools they depend on (Themes B, C, F)

**F-014** — Add the theory_math pack to user-facing docs: USE_CASES.md (theorist row), PROTOCOLS.md (8-protocol section), START.md (theory example), AI_GUIDE.md (pack section)
- Category: `TOOL_DISCOVERABILITY`
- est_minutes: **90**
- files_to_touch: `docs/USE_CASES.md`, `docs/PROTOCOLS.md`, `docs/START.md`, `docs/AI_GUIDE.md`
- rationale: S5 HIGH. Single biggest reason theory scored 5/10 — a working mathematician has no doc-surface reason to believe the pack exists. The pack itself is 8/10 work.

**F-015** — Document `tool_redteam_review` in TOOLS.md (referenced in `proof_verification_workflow.yaml` but absent from catalogue); same audit for any other orphaned tool references
- Category: `TOOL_DISCOVERABILITY`
- est_minutes: **30**
- files_to_touch: `docs/TOOLS.md`, audit pass over all protocol YAMLs grepping for `tool_*` references
- rationale: S5 MEDIUM. Phantom tool references erode trust in the doc surface.

**F-016** — Add "common figure recipes" appendix to `docs/RESEARCHER_GUIDE.md` (volcano / UMAP / heatmap / forest / survival curve / log-log benchmark) mapping each to its protocol stack
- Category: `TOOL_DISCOVERABILITY`
- est_minutes: **60**
- files_to_touch: `docs/RESEARCHER_GUIDE.md`
- rationale: S1 LOW + general usability. Visualization protocol stack selection currently requires reading 3 protocols; recipes collapse the decision.

### Category: DOMAIN_COMPOSITION (4 items) — pack gaps (Themes B, C, G)

**F-017** — Ship `methodology/qualitative_pii_redaction.yaml` protocol + `tool_qualitative_pii_redact` tool (presidio / spaCy NER + regex pass) as a prerequisite of `qualitative_research`
- Category: `DOMAIN_COMPOSITION`
- est_minutes: **180**
- files_to_touch: `src/research_os/protocols/methodology/qualitative_pii_redaction.yaml` (new), `src/research_os/server.py` (new tool), `src/research_os/tools/actions/data/` (handler), `docs/TOOLS.md`, `templates/qualitative/pii_policy.md` (new template), `src/research_os/protocols/methodology/qualitative_research.yaml` (link from `ingest_transcripts`)
- rationale: S3 HIGH. HIPAA/IRB/GDPR-required for any real qualitative work; current `quote_anonymisation_audit` at the END is too late because coding has already happened on un-redacted text. This is the single most material protective gap across the validation.

**F-018** — Extend `researcher_config.citation_style` enum: add `mla`, `chicago_author_date`, `chicago_notes_bib`, `amsplain`, `siam`; ship `humanities_essay.typ` and `chicago_thesis.typ` Typst templates
- Category: `DOMAIN_COMPOSITION`
- est_minutes: **120**
- files_to_touch: `templates/researcher_config.yaml`, `src/research_os/wizard.py` (validate enum), `templates/typst/humanities_essay.typ` (new), `templates/typst/chicago_thesis.typ` (new), `docs/VENUE_TEMPLATES.md`
- rationale: S2 HIGH + S5 MEDIUM. Humanities/theory scholars currently have no in-band citation style; the venue template gap forces them to generic_two_column or generic_thesis, neither of which fits their field.

**F-019** — Add WorldCat / OpenLibrary / LOC ISBN-based verifiers to `tool_citations_verify` as fallbacks; surface "verified via ISBN" as a first-class status; per-pack relaxed gate
- Category: `DOMAIN_COMPOSITION`
- est_minutes: **150**
- files_to_touch: `src/research_os/tools/actions/research/citation_verify.py` (assumed location), `docs/TOOLS.md`, `src/research_os/protocols/synthesis/synthesis_paper.yaml` (final_assembly gate doc)
- rationale: S2 HIGH. Currently `tool_citations_verify` blocks humanities paper assembly because foundational monographs (Cohn, Banfield, Palmer) lack DOIs. Override exists but the gate is a HARD blocker by design; adding ISBN fallback removes the friction without weakening the gate.

**F-020** — Ship `tool_humanities_apparatus_audit(apparatus_path)` that machine-checks each interpretive claim for line/page anchors, tradition-declared header, counter-instance section, secondary-criticism ledger
- Category: `DOMAIN_COMPOSITION`
- est_minutes: **150**
- files_to_touch: `src/research_os/server.py`, `src/research_os/tools/actions/audit/` (new handler), `docs/TOOLS.md`, `src/research_os_humanities/protocols/method/close_reading.yaml` (reference the tool)
- rationale: S2 MEDIUM. `close_reading.yaml`'s quality_bar (anchor_density, counter_instance, tradition_declared, edition_pinned, secondary_ledger) lives only in YAML — there is no MCP tool that machine-checks an apparatus.md file against those bars. AI is on its honour while statistics-flavoured gates fire loudly.

### Category: ONBOARDING (2 items) — first-5-turns flow tightening

**F-021** — Add a `## Common first prompts` block to `docs/USE_CASES.md` covering: (a) "I have data AND a hypothesis simultaneously" (S1), (b) "I have a corpus of N texts" → humanities pack triggers (S2), (c) "I have interview transcripts" → qualitative pack triggers (S3), (d) "I want to benchmark X vs Y" → engineering trigger vocab (S4), (e) "I have a conjecture, help me prove it" → theory_math pack (S5)
- Category: `ONBOARDING`
- est_minutes: **60**
- files_to_touch: `docs/USE_CASES.md`, `docs/START.md` (cross-link)
- rationale: First-turn ambiguity hit 4/5 scenarios. 5 worked examples in USE_CASES.md collapses the cognitive load for the AI's first `tool_route` call.

**F-022** — Remove `discover/` from `docs/AI_GUIDE.md` § "Protocol categories" OR ship `discover/intake.yaml` placeholder that points at `tool_intake_autofill`; surface "code under benchmark" + "inputs/preliminaries.md" + "inputs/corpus/" file-location conventions in RESEARCHER_GUIDE.md
- Category: `ONBOARDING`
- est_minutes: **45**
- files_to_touch: `docs/AI_GUIDE.md`, `docs/RESEARCHER_GUIDE.md`, `docs/START.md`, `templates/SETUP.md` (if exists)
- rationale: S4 MEDIUM (`discover/` doc-vs-FS drift); S5 MEDIUM (`inputs/preliminaries.md` undocumented prereq); S4 LOW (code-under-benchmark location); S2 LOW (humanities `inputs/corpus/` subfolder). Cluster of small file-location-convention gaps; fix in one pass.

### Category: ERROR_MESSAGE (0 items in this pass)

No friction in this validation was about raised exceptions with poor messages — the workflow simulations didn't actually invoke MCP. Defer this category until a v1.9.4 hot-loop validation that actually invokes the MCP server.

---

## 6. Deferred to v1.11.0+

Items the fix-list could touch but are out of scope for a v1.9.4 docs-and-protocols patch release. Three categories.

**D-01** — `tool_audit_prose` pack-aware register (humanities-mode tolerates hedging; qualitative-mode tolerates first-person reflexivity)
- Why deferred: requires non-trivial NLP rules + per-pack profile schema + tests. Not a doc/protocol fix.
- Severity: MEDIUM (S2). Workaround: `pre_submission_checklist` resurfaces every prose-audit override, and the override path is documented.

**D-02** — `tool_dashboard_create` theory schema (theorem cards, proof tree, lemma library, dependency graph rendering)
- Why deferred: requires a new dashboard layout template + tool_audit_dashboard_content theory branch + integration with `tool_theory_math_dep_graph`. Net-new feature, not a v1.9.4 patch.
- Severity: HIGH (S5). Workaround: `override_completeness_gate=true` produces a partial dashboard; documented in F-005.

**D-03** — `tool_qualitative_apply_codebook` / `tool_qualitative_code_transcript` LLM-assisted coding wrapper
- Why deferred: net-new tool with non-trivial prompt-engineering + provenance design. Coding scheme development still works via `tool_python_exec` + LLM script today.
- Severity: LOW (S3). Workaround: existing pattern is functional.

**D-04** — `tool_theory_math_dep_graph` informal-markdown proof parser
- Why deferred: requires natural-language proof parsing or a markdown convention; non-trivial design.
- Severity: MEDIUM (S5). Workaround: protocol already documents `workspace/docs/dep_graph_manual.md` manual fallback.

**D-05** — `chat_split_recommended` heuristic exposure (turn count, token budget, step count) in AI_GUIDE.md
- Why deferred: the heuristic itself may need re-tuning before being made user-visible; document after stabilising.
- Severity: LOW (S1).

**D-06** — Multi-protocol routing decomposition algorithm exposure (how `tool_route` picks among competing L3 matches)
- Why deferred: router internals may change in v1.11; documenting now risks doc-vs-code drift.
- Severity: LOW (S2).

**D-07** — `single_coder` branch in `coding_scheme_development.yaml`
- Why deferred: requires methodological design work (constant-comparison self-calibration protocol); not a 30-minute fix.
- Severity: MEDIUM (S3). Workaround: AI documents single-coder as limitation; `qualitative_quality_audit::intercoder_agreement_check` handles it gracefully downstream.

---

## 7. Notes on validation methodology

- All 5 agents followed the same trace template: project setup (T1-5), hypothesis+planning (T6-10), per-step execution (T11-25), audit+synthesis (T26-35).
- "Time-to-clarity" estimates are doc-read time, not tool-execution time. Useful as relative friction signal.
- Tool calls were simulated from `docs/TOOLS.md` descriptions + protocol `expected_outputs`. When a tool's behavior was ambiguous from docs alone, the agent logged it as a friction event (this is intentional — opacity is the finding).
- Source code under `src/research_os/` was off-limits to enforce fresh-agent constraints. Any place where an agent reported needing to read source to understand behavior is a documentation gap (logged accordingly).
- One scenario (S4) referenced reading `src/research_os/protocols/_router_index.yaml` and a few `router_entries.py`-style hints — those are user-facing protocol files per the validation rules, so reading them is fine, but the friction is that the fresh AI shouldn't need to.

---

## 8. Sign-off

This synthesis report covers 5 scenarios × 165 turns. The next phase is to apply the 22 prioritized fixes (estimated ~24 hours focused work). After fixes, a v1.9.4-validation re-run on the same 5 scenarios should target an average rating of ≥ 8/10 and ≤ 5 HIGH-severity friction events across all scenarios combined.

---

## 9. Re-validation results (post-fix sprint)

The 22-fix sprint (three clusters: AI guidance + missing prompts + tool discoverability; error messages + edge cases + domain composition; onboarding flow + docs polish) landed across docs, protocol YAMLs, templates, and two Python touchpoints required by the fix list (`state/config.py` + `synthesis/typst.py` for F-018's `citation_style` enum extension + Typst venue registration). A re-validation round was then run on 4 of 5 scenarios (S1 biology, S2 humanities, S3 qualitative, S5 theory). S4 engineering was not re-run individually but received the targeted fixes (F-009 cross-link, F-010 engineering-systems-benchmark addendum, F-007 `next_protocol_kind`, F-022 code-under-benchmark docs) and is carried at its initial 7/10 rating; the conservative 5-scenario average below reflects that carry-over.

### 9.1 Per-scenario movement

| Scenario | Initial rating | Re-run rating | HIGH (init → final) | MEDIUM (init → final) | First-5-turn HIGH (init → final) |
|---|---|---|---|---|---|
| 1 — Biology / RNA-seq DE | 7/10 | **9/10** | 0 → 0 | 3 → 1 | 0 → 0 |
| 2 — Humanities / close-reading | 7/10 | **7/10** | 2 → 0 | 6 → 4 | 1 → 0 |
| 3 — Qualitative / interviews | 7/10 | **8/10** | 1 → 0 | 6 → 4 | 0 → 0 |
| 4 — Engineering / benchmark | 7/10 | 7/10 (carry-over) | 0 → 0 | 6 → 6 | 0 → 0 |
| 5 — Theory / chordal-graph | 5/10 | **8/10** | 9 → 1 | 6 → 2 | 1 → 0 |
| **Totals** | **avg 6.6** | **avg 7.8** | **12 → 1** | **27 → 17** | **2 → 0** |

### 9.2 Final metrics vs targets

| Metric | Target | Final | Met? |
|---|---|---|---|
| Average usability rating | ≥ 8.5 | **7.8** | NO |
| Total HIGH friction across 5 scenarios | ≤ 5 | **1** | YES |
| Onboarding HIGH friction (first 5 turns) | 0 | **0** | YES |

Two of three targets met. The average-rating target was missed by 0.7 points; the only scenario that did not crack 8/10 was S2 humanities, where the missing `humanities_essay_structure` protocol and the still-empirical-claim-centric `tool_audit_step_literature` continue to cause 4 MEDIUM frictions. S5 theory moved 3 points (5 → 8) on the back of F-014 (theory_math pack visibility) + F-001/F-002 (step-intent waivers) + F-003 (IMPORTED_AS_CITED verdict) — the single largest per-scenario gain of the sprint.

### 9.3 Highest-leverage fixes (top 10 by rating-move contribution)

1. **F-014** — theory_math pack surfaced in USE_CASES / PROTOCOLS / START / AI_GUIDE: drove S5 from 5 → 8.
2. **F-001 / F-002** — step-intent classification + figure-gate auto-waiver for plan/ground/proof/apparatus/synth: removed override-loop friction across S1, S2, S3, S5.
3. **F-003** — `IMPORTED_AS_CITED` + `SPECIALIZES` literature verdicts: eliminated S5's 9-HIGH literature-gate verdict-mismatch cluster.
4. **F-017** — `qualitative_pii_redaction` protocol + template as a hard upstream gate of `qualitative_research`: closed S3's only HIGH (HIPAA/IRB/GDPR pre-coding gap).
5. **F-018** — `citation_style` enum extended (mla / chicago / amsplain / siam) + `humanities_essay.typ` + `chicago_thesis.typ` Typst templates: removed the two STEM-bias HIGH frictions S2 logged on `researcher_config`.
6. **F-013** — Return-shape JSON examples in TOOLS.md for `tool_intake_autofill` / `tool_dashboard_create` / `tool_step_complete` / `tool_audit_quality_full`: noted by S1 as "single highest-leverage doc choice; lets a fresh agent simulate calls without grepping src/".
7. **F-008** — End-to-end qualitative recipe in USE_CASES.md (`qualitative_research → coding_scheme_development → qualitative_quality_audit → audit_and_validation → synthesis_paper`): removed the chain-composition friction that drove S3 toward `analysis_plan` mis-routing.
8. **F-006** — `qualitative_research.next_protocol` fixed to point at `qualitative_quality_audit`: closed the same mis-route at the YAML level.
9. **F-011 / F-012** — `tool_dashboard_create` mode enum + `tool_step_complete` first-class table entry in TOOLS.md: removed two opacity MEDIUMs that hit S1 and S3.
10. **F-021 / F-022** — Common first prompts + `inputs/` subfolder conventions (preliminaries.md, corpus/, transcripts/, context/code/): drove all 5 onboarding-HIGH events to zero.

### 9.4 Gaps deferred to v1.11.0 (target-miss accounting)

The 0.7-point average-rating gap to the 8.5 target is concentrated in S2 humanities. Four MEDIUM frictions remain after the sprint:

1. **No `humanities/output/humanities_essay_structure.yaml`** paralleling `theory_math/output/theory_paper_structure.yaml`. `humanities_essay.typ` Typst template ships in v1.9.4 but no protocol drives it; `synthesis_paper` defaults to IMRAD. Deferred — requires new protocol + decomposition wiring; sized similar to F-014.
2. **`tool_audit_step_literature` is still empirical-claim-centric** for descriptive / prep / pure-viz steps. F-001/F-003/F-004 partially closed this for proof + viz-with-inheritance steps, but descriptive/prep steps in humanities + qualitative still need either a `descriptive_step` step_intent waiver or a verdict-enum case for "no claim, scoping only". Re-noted as AUDIT-v1.9.2-022's continuation. Deferred to v1.11.0.
3. **`inputs/raw_data/` immutability vs `inputs/corpus/` placement recovery undocumented.** F-022 documented the BEFORE convention; the AFTER-misplaced recovery path (symlink? acceptance of `raw_data/<slug>/` as corpus root?) still missing. Doc-only fix; defer to v1.9.5 patch.
4. **Story-mode dashboard sub-tools** (`tool_dashboard_story_generate`, `tool_dashboard_story_edit`, `tool_dashboard_story_quality_bar`) not enumerated in TOOLS.md spotlight tables. F-011 documented the `mode` enum but not the supporting tools. Doc-only fix; defer to v1.9.5 patch.

S5 theory's one remaining HIGH is the `PROTOCOLS.md` auto-generated catalogue silently omitting pack protocols (the regen script does not walk `research_os_<pack>/protocols/` namespace packages). Curated tables now list the 8 theory_math protocols (F-014), so this is a fresh-AI discoverability surprise rather than a workflow blocker. Deferred — needs `scripts/regen_protocols_doc.py` updated to walk namespace packages.

Additional v1.11.0 carry-overs from the original deferred list (D-01..D-07) remain unchanged: pack-aware `tool_audit_prose`, theory dashboard schema, LLM-assisted qualitative coding tool, informal-markdown proof parser, `chat_split_recommended` heuristic exposure, router decomposition algorithm exposure, single-coder branch in `coding_scheme_development`.

### 9.5 Release gate snapshot (post-sprint)

- preflight: **23/23 passed** (added one new check during the sprint: `next_protocol_kind declared on every protocol`)
- pytest: **899 passed** in 22s (up from 896 baseline; +3 from new Typst venue parametrisations covering `humanities_essay` + `chicago_thesis`)
- ruff: clean across `src/ tests/ scripts/`
- embeddings: rebuilt — 151 protocols + 212 tools (BAAI/bge-small-en-v1.5, dim=384)

### 9.6 Classification

v1.9.4 ships as a **MINOR** release: one new protocol (`methodology/qualitative_pii_redaction.yaml`), one new schema field (`next_protocol_kind` on all 148 protocols), `citation_style` enum widened (mla / chicago_author_date / chicago_notes_bib / amsplain / siam), two new Typst venue templates (`humanities_essay`, `chicago_thesis`), and `step_summary.yaml.template` shipped as a documented contract — all additive, all backwards-compatible.
