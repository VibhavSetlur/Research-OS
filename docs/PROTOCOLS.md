# Protocol Reference

Research OS ships **114 YAML protocols** organised into nine categories.
Each protocol is a sequence of steps the AI should follow, with explicit
`expected_outputs`, a `next_protocol` pointer, and a `quality_bar`. All
are indexed in `src/research_os/protocols/_router_index.yaml` for
hierarchical routing via `tool_route`.

| Category | Count | What's in it |
|---|---|---|
| `methodology/` | 42 | Method pickers + per-family deep workflows (causal, ML, Bayesian, time-series, clinical, qualitative, mixed-methods, simulation, replication, ablation, pilot, evaluation design, hyperparameter sweep design, ethics review, EDA + hypothesis generation, method comparison, data-quality audit, power analysis, reproduction, methodological consultation). **v1.4.0** adds `pick_tool_stack` (R vs Python per sub-task, field-practice grounded) and `mixed_language_orchestration` (Python↔R↔Bash composition doctrine). |
| `guidance/` | 19 | Session boot / resume / handoff / autopilot / collaboration, intake, iterative planning, dead-end routing, hypothesis + glossary tracking, mid-pipeline entry, code review, peer-review response, **scope-clarification**. |
| `synthesis/` | 18 | Paper, abstract, poster, dashboard, grant, report, slides, lay summary, progress update, cover letter, title workshop, handout, null-findings companion, synthesis-from-inputs, manuscript_outline, journal_selection, defense_prep, printable. |
| `visualization/` | 14 | Figure guidelines, viz workflow, single-figure critique, multi-panel composition, narrative arc, colour-accessibility audit, interactive figure design. |
| `writing/` | 10 | Per-section drafting (methods / results / discussion / limitations / end-matter), writing core rules, citations ledger, conclusions, analysis log, README. |
| `literature/` | 5 | Search, systematic review (PRISMA), evidence synthesis (GRADE), comparative paper review. **v1.4.0** adds `literature_per_step` — per-step search → download → cite → write `findings_vs_literature.md` (AGREES \| DISAGREES \| EXTENDS \| DEFERRED). |
| `audit/` | 3 | Master audit + validation, pre-submission checklist, provenance completeness. |
| `domain/` | 2 | Domain classification, research-design + sample-size justification. |
| `reproducibility/` | 1 | Per-step env lock, seed verification, container generation. |
| **Total** | **114** | |

The protocol surface deliberately covers BOTH the canonical
data → publication pipeline AND the partial / off-axis workflows
real researchers actually run: visualization-only requests, talk decks,
lay summaries for non-experts, PI progress updates, exploratory data
analysis with hypothesis generation, head-to-head method comparisons,
standalone power analyses, reproduction attempts of published work,
teaching / consultation modes, multi-paper comparative reviews,
mid-pipeline entry, per-section paper drafting (results / discussion /
limitations / end-matter), multi-panel figure composition, figure
narrative arcs, color accessibility audits, cover letters, title
workshops, printable handouts, evaluation + sweep design, and data
ethics review. See [USE_CASES.md](USE_CASES.md) for a role × goal map
of when each protocol fires.

For the format of a protocol file, see
[CONTRIBUTING.md § Adding or modifying a protocol](../CONTRIBUTING.md).

---

## How the AI picks a protocol (the hierarchical router)

The AI does **not** load every YAML to find the right one. The AI only
ever acts AFTER a researcher message arrives; on the first turn of a
session it fires these two calls back-to-back:

1. **`sys_boot`** — FIRST MCP call (first turn only). Returns workspace
   state + recommended pipeline-next protocol + advice.
2. **`tool_route(prompt=<researcher's verbatim message>)`** — SECOND
   MCP call. Hierarchical L1 → L2 → L3 picker. Returns the deepest
   unambiguous level:
   * L1 `intent_class` — one of `session | discover | plan | execute |
     methodology | literature | synthesize | audit_wrap | memory |
     review`
   * L2 `sub_intent` — narrower bucket within the class
   * L3 specific protocol
   When ambiguous at any level, the router returns an `ask_user`
   sentence so the AI disambiguates with one researcher follow-up
   instead of guessing wrong.
3. **`sys_protocol_get format='summary'`** loads step headings only
   (~300 tokens). `format='step' step_id='<id>'` loads one step body
   when ready to execute.

This entire path costs ~1.2K tokens — vs the ~5K it took before the
routing layer existed.

---

## The main pipeline (10 stages, in order)

| # | Protocol | What it does | Done when |
|---|---|---|---|
| 1 | `guidance/session_boot` | One-call boot via `sys_boot`; route first message via `tool_route` | first entry in execution log |
| 2 | `guidance/project_startup` | Intake autofill, profile data, lock research question | intake.md filled + research_overview.md confirmed |
| 3 | `domain/domain_analysis` | Classify domain, pick reporting standard, list biases | docs/domain_summary.md exists |
| 4 | `domain/research_design` | Choose study design + sample size justification | docs/research_design.md exists |
| 5 | `methodology/methodology_selection` | Pick statistical / computational methods (literature-grounded) | workspace/methods.md substantive |
| 6 | `literature/literature_search` | Multi-database search + dedup + PRISMA accounting | literature_index.yaml + citations.md exist |
| 7 | `guidance/analysis_plan` | Per-step loop: scope → ground → execute → document → snapshot | ≥1 experiment with non-empty conclusions.md |
| 8 | `reproducibility/reproducibility` | Lock environments, verify seeds, generate Dockerfile | per-experiment requirements.txt exist |
| 9 | `audit/audit_and_validation` | Citation / power / assumption / figure / code audits | workspace/logs/audit_report.md exists |
| 10 | `synthesis/synthesis_paper` | Compile paper (venue-tailored, verified citations) | synthesis/paper.md exists |

`sys_protocol_next` returns the first stage whose outputs (or execution
log) say "not done yet". The pipeline works off both the execution log
AND on-disk artifacts so migrated projects resume cleanly.

---

## On-demand protocols

### Guidance — session + flow control

| Protocol | Intent (L1 / L2) | Triggered by |
|---|---|---|
| `guidance/session_boot` | session / boot | "start session", "hi", "begin" |
| `guidance/session_resume` | session / resume | "pick up", "where were we", "another session" |
| `guidance/chat_handoff` | session / handoff | "wrap up", "going to lunch", "switch chat" |
| `guidance/collaboration_handoff` | session / collaborator | "send to a collaborator", "another lab is taking this" |
| `guidance/autopilot` | session / autopilot | "autopilot", "you drive", "wake me up" |
| `guidance/casual_exploration` | plan / casual | "just poke", "exploratory only", "sanity check" |
| `guidance/quick_paper_review` | review / quick | "tear apart", "tough reviewer", "quick review" |
| `guidance/code_review` | review / code | "review my code", "vet this script", "is this correct" |
| `guidance/peer_review_response` | review / respond | "respond to reviewers", "draft a rebuttal", "revise and resubmit" |
| `guidance/project_startup` | discover / intake | "fill the intake", "what do I have" |
| `guidance/analysis_plan` | execute / new_experiment | "run a baseline", "next experiment", "fit a model" |
| `guidance/iterative_planning` | plan / next_step | "what should I do next", "I'm stuck" |
| `guidance/dead_end_routing` | execute / abandon | "dead end", "abandon", "not working" |
| `guidance/hypothesis_tracking` | memory / hypothesis | "add hypothesis", "list hypotheses" |
| `guidance/glossary_update` | memory / glossary | "add to glossary", "define term" |
| `guidance/mid_pipeline_entry` | discover / mid_entry | "i'm mid-way through", "i already have results", "bringing this into RO" |
| `guidance/scope_clarification` | discover / clarify | "where should I start", "i have data and ideas", "this spans two fields", "narrow this down" |

### Domain — classification + design

* `domain/domain_analysis` — classify the field + reporting standard.
* `domain/research_design` — pick design + justify sample size.

### Methodology — pick + apply

| Protocol | When |
|---|---|
| `methodology/methodology_selection` | Top-level method picker (absorbs the lightweight "lookup mode") |
| `methodology/preregistration` | Freeze the SAP + hypotheses BEFORE data analysis |
| `methodology/causal_inference_deep` | DAG + dowhy / IPW / DiD / RDD |
| `methodology/machine_learning` | TRIPOD-AI ML pipeline |
| `methodology/bayesian_analysis` | Priors → posterior → diagnostics → checks → sensitivity |
| `methodology/timeseries_analysis` | Time-aware analysis + forecasting (ARIMA/ETS/state-space/ML) |
| `methodology/clinical_trials` | CONSORT-compliant RCT |
| `methodology/meta_analysis` | Random/fixed effects + heterogeneity |
| `methodology/survey_psychometrics` | EFA/CFA + reliability + IRT |
| `methodology/qualitative_research` | COREQ/SRQR interviews / thematic |
| `methodology/simulation_studies` | ADEMP Monte Carlo / agent-based |
| `methodology/replication_study` | Direct / conceptual replication |
| `methodology/ablation_study` | Component-by-component ablation |
| `methodology/pilot_study` | Feasibility / variance estimation |
| `methodology/mixed_methods` | Concurrent / sequential qual + quant |
| `methodology/tool_discovery` | Find candidate libraries / CLIs |
| `methodology/exploratory_data_analysis` | Real EDA + hypothesis generation (pre-registered scope) |
| `methodology/method_comparison` | Head-to-head benchmark of N methods on one task |
| `methodology/data_quality_audit` | Standalone data QC (schema / missingness / leakage / bias) |
| `methodology/power_analysis` | Standalone power / sample-size justification |
| `methodology/reproduction_attempt` | Reproduce a published analysis (rerun their pipeline) |
| `methodology/methodological_consultation` | Teach / explain / compare methods (no project commit) |
| `methodology/evaluation_design` | Design split / CV / metric set / paired comparison test |
| `methodology/hyperparameter_search_design` | Design a sweep (space, budget, strategy, early-stopping) |
| `methodology/data_ethics_review` | IRB / privacy / consent / sharing / fairness / dual-use |

### Literature

* `literature/literature_search` — multi-database search.
* `literature/systematic_review` — full PRISMA workflow.
* `literature/evidence_synthesis` — GRADE-style grading + contradiction detection.
* `literature/comparative_paper_review` — compare-and-contrast 2-N papers (journal club / related work / reviewer-asked / foundational).

### Writing

* `writing/writing_core` — universal rules; loaded implicitly by every
  synthesis. Includes vague-quantifier audit + anti-bullshit signals +
  numbered claim grounding pattern.
* `writing/writing_methods` — append a structured method entry.
* `writing/writing_results` — Results section drafting (report numbers,
  defer interpretation, full statistical form).
* `writing/writing_discussion` — Discussion section drafting (the hardest
  section — principal findings, alternative explanations, limitations
  route, scope-limited implications, concrete future work).
* `writing/writing_limitations` — Limitations sub-section (no boilerplate;
  every limitation paired with downstream implication; critical-first).
* `writing/writing_citations` — maintain workspace/citations.md.
* `writing/writing_conclusions` — per-step conclusions.md.
* `writing/writing_analysis_log` — append structured entry to analysis.md.
* `writing/writing_readme` — project + per-step README.
* `writing/writing_data_availability` — end matter (data + code
  availability, CRediT, funding, COI, acknowledgements).

### Synthesis — final deliverables

Each is venue/audience-tailored and enforces quality minimums:

* `synthesis/synthesis_paper` — IMRAD, venue profiles
  (journal / conference / preprint / dissertation / report). Word-count
  bands, figure DPI ≥300, citation cap 40, verified online.
* `synthesis/synthesis_abstract` — structured (journal/preprint) vs
  unstructured (conference) vs grant style. Cap 3 citations.
* `synthesis/synthesis_poster` — tikzposter, billboard mode (Morrison
  Better Poster) + classic IMRAD. Audience profiles (academic_conference
  / symposium / industry / teaching). ≥2 figures ≥300 DPI, ≤6 citations.
* `synthesis/synthesis_dashboard` — single-file HTML, audience profiles
  (academic / executive / technical / teaching). Sortable tables,
  lightbox, light/dark, print stylesheet, evidence-traceability matrix,
  outstanding-artefacts panel.
* `synthesis/synthesis_null_findings` — publishable companion for
  refuted / inconclusive / underpowered / abandoned findings — fights
  the file-drawer problem.
* `synthesis/synthesis_grant` — funder profiles
  (nih_r01 / nsf / wellcome / erc / doe / industry). Specific Aims first.
* `synthesis/synthesis_report` — audience profiles
  (internal_team / client / technical_audit / policy_brief).
* `synthesis/synthesis_slides` — presentation deck (lab meeting /
  conference short / conference long / defense / invited seminar /
  teaching). Beamer / Marp / Reveal.js / PowerPoint output. Speaker
  notes + Q&A anticipation are part of the deliverable.
* `synthesis/synthesis_lay_summary` — non-expert summary
  (general_public / press_release / funder_lay_section /
  patient_or_participant / social_thread / blog_post). Reading-grade
  capped; jargon replaced; numbers anchored.
* `synthesis/synthesis_progress_update` — short PI / advisor / lab /
  stand-up update. Sourced from the diff since the last update;
  blockers + ask explicit.
* `synthesis/synthesis_from_inputs` — synthesis when prior analyses
  were done OUTSIDE Research-OS. Builds a shadow workspace step,
  imports the artefacts, runs the chosen target synthesis on top,
  with a provenance ceiling stated in the final deliverable.
* `synthesis/synthesis_cover_letter` — journal cover letter (fit +
  significance + reviewers + disclosures + word cap ≤ 400).
* `synthesis/synthesis_title_workshop` — title generation + iteration
  (≥6 alternatives across archetypes, substring test, shortlist of 3,
  stress test the winner).
* `synthesis/synthesis_handout` — single-page printable leave-behind /
  one-pager (5 audience profiles, QR code mandatory).

### Theory + math pack (8 protocols, opt-in via the `theory_math` pack)

Loaded when the theory_math pack is installed (it ships in the default
wheel). Trigger phrases: "prove this", "I have a conjecture", "draft a
proof", "iterate on the proof", "formalise in Lean / Coq".

| Protocol | When |
|---|---|
| `theory_math/conjecture/conjecture_tracking` | Register an open problem for later attack; the open-problem register |
| `theory_math/method/proof_strategy_selection` | Choose between direct / contradiction / induction / contrapositive / construction |
| `theory_math/proof/proof_verification_workflow` | End-to-end: claim → strategy → draft → independent review → optional formal check → publish |
| `theory_math/proof/lemma_library` | Maintain a reusable lemma library with versioned dependents tracking |
| `theory_math/proof/theorem_dependency_graph` | Render the dependency DAG across lemmas + theorems for impact-of-change analysis |
| `theory_math/formal/lean_integration` | Formalise a proof in Lean 4 + Mathlib |
| `theory_math/formal/coq_integration` | Formalise a proof in Coq |
| `theory_math/output/theory_paper_structure` | Theorem / Proof / References paper structure (NOT IMRAD) |

Three theory-only tools ship with the pack: `tool_theory_math_lean_check`,
`tool_theory_math_coq_check`, `tool_theory_math_dep_graph`. See
[TOOLS.md § Theory + math pack](TOOLS.md#theory--math-pack).

### Audit + reproducibility

* `audit/audit_and_validation` — master quality audit
  (`tool_audit_quality_full`): step completeness, code quality, prose
  quality, claim grounding, pre-registration diff, grounding
  verification. Single call, every gate. Aggregates to
  `workspace/logs/audit_master.md`.
* `reproducibility/reproducibility` — per-step env snapshot, seed
  verification, output hashing, Apptainer + Dockerfile + entrypoint
  generation.

### Visualization

* `visualization/figure_guidelines` — chart-chooser + formatting standards
  (palettes, fonts, DPI, error indicators). The style-and-rules
  reference.
* `visualization/visualization_workflow` — build / polish a figure or
  figure deck WITHOUT committing to the full analysis_plan loop. The
  workflow counterpart of figure_guidelines.
* `visualization/figure_critique` — reviewer-style critique of a
  single figure (chart family, encoding, caption alignment,
  sensitivity to alternative encoding).
* `visualization/multi_panel_composition` — compose a multi-panel
  figure (Figure 2 = A / B / C / D) with shared scales + combined
  caption.
* `visualization/figure_narrative_arc` — order figures across a paper /
  talk / poster (figure budget + arc + cut decisions + reading-order
  sanity check).
* `visualization/color_accessibility_audit` — color-blindness
  simulation (3 types) + WCAG contrast + grayscale-survivability +
  redundant-encoding audit.

---

## Full catalogue by category

The curated tables above (organised by intent / picker logic) cover the
protocols the router reaches most often. The block below is the
**ground-truth roster** — every YAML on disk, regenerated from source
by `python scripts/regen_protocols_doc.py`. If a protocol is missing
from the curated tables but present here, the router still knows about
it via `_router_index.yaml`; load it with `sys_protocol_get`.

<!-- AUTO:PROTOCOL_CATALOGUE_START -->
<!-- AUTO-GENERATED by scripts/regen_protocols_doc.py — DO NOT EDIT BY HAND -->

_All 114 protocols, grouped by category, alphabetised within each._

### `audit/` (3 protocols)

| Protocol | One-liner |
|---|---|
| `audit_and_validation` | Validate citations, statistical assumptions, figure quality, |
| `pre_submission_checklist` | Final ready-to-submit gate. Walks the project through every |
| `provenance_completeness` | Every figure, table, model artefact, and report output in the workspace |

### `domain/` (2 protocols)

| Protocol | One-liner |
|---|---|
| `domain_analysis` | Classify the research domain, surface the relevant reporting standards, and list domain-specific biases to… |
| `research_design` | Choose the right study design (RCT, cohort, case-control, etc.) and compute / justify the sample size. |

### `guidance/` (19 protocols)

| Protocol | One-liner |
|---|---|
| `analysis_plan` | Per-step loop. Scope → plan-breakdown → literature-ground → execute (atomic versioned scripts) → document →… |
| `autopilot` | Hands-off "drive the project to its next deliverable without checking in |
| `casual_exploration` | Lightweight mode for "I just want to poke at this." Skips reproducibility |
| `chat_handoff` | Produce a fully-formed handoff brief so the project can be picked up by |
| `code_review` | Critically review the analysis scripts in a numbered step (or |
| `collaboration_handoff` | Package the project for handoff to a human collaborator who is |
| `constructive_disagreement` | Protocol for the case where the AI's grounded judgement disagrees |
| `dead_end_routing` | What to do when an experiment path fails or a methodology proves unworkable. Preserves the failed path and… |
| `glossary_update` | Add or refine a definition in docs/glossary.md. Run this protocol the first time any non-trivial term appears… |
| `hypothesis_tracking` | Maintain a clear ledger of active, supported, and refuted hypotheses across the project. |
| `iterative_planning` | For researchers who want the AI to PROPOSE next steps rather than dictate them. Iteratively assesses state +… |
| `mid_pipeline_entry` | Routing protocol for researchers entering Research-OS with WORK ALREADY |
| `peer_review_response` | Process a peer-review report against the submitted paper. Produces |
| `project_startup` | First substantive protocol. Auto-fills intake from researcher dumps, locks in research question, classifies… |
| `quick_paper_review` | Fast (20-40 minute) critical appraisal of someone else's paper. NOT a full |
| `revise_and_resubmit` | End-to-end orchestration for a Revise & Resubmit decision from a |
| `scope_clarification` | Convert a vague, broad, or cross-disciplinary research ask into a |
| `session_boot` | Mandatory boot sequence on the FIRST TURN of every session. Every |
| `session_resume` | Re-enter a paused / interrupted / handed-off project — possibly in a |

### `literature/` (5 protocols)

| Protocol | One-liner |
|---|---|
| `comparative_paper_review` | Compare-and-contrast review of TWO OR MORE papers. Distinct from: |
| `evidence_synthesis` | Build an evidence table from the literature corpus, grade each entry, and flag contradictions. |
| `literature_per_step` | After every analysis step writes its findings, RO grounds those |
| `literature_search` | Systematic search across 2-4 academic databases. Produces a |
| `systematic_review` | Full PRISMA workflow for a primary systematic review or meta-analysis project. |

### `methodology/` (42 protocols)

| Protocol | One-liner |
|---|---|
| `ablation_study` | Systematic removal / replacement of model or pipeline components to |
| `bayesian_analysis` | A first-class Bayesian workflow following Gelman et al.'s Bayesian |
| `bootstrapping_design` | Bootstrap and resampling methods are the workhorse for non-parametric |
| `causal_inference_deep` | Reasoning scaffold for causal inference from observational data. |
| `clinical_trials` | Reasoning scaffold for analysing a randomised clinical trial. Names |
| `coding_scheme_development` | Before multiple coders apply a coding scheme to qualitative data |
| `cox_ph_diagnostics` | Whenever a Cox proportional-hazards model is fit (lifelines `CoxPHFitter`, |
| `data_ethics_review` | Walk an ethics review of the data + analysis. Covers IRB / REC |
| `data_management_plan` | A Data Management Plan (DMP) is a standalone document — distinct from |
| `data_quality_audit` | Standalone data quality audit — for the case where the researcher |
| `deep_domain_research` | Reasoning scaffold for entering an unfamiliar subfield. Before any |
| `evaluation_design` | Standalone design protocol for the EVALUATION REGIME — the |
| `exploratory_data_analysis` | Real EDA workflow — open-ended, hypothesis-GENERATING, NOT a |
| `external_tool_setup` | Many top-tier deliverables require tools beyond `pip install |
| `fairness_audit` | When a predictive model or decision system will be used in a |
| `hyperparameter_search_design` | Design a hyperparameter sweep — the search space, the budget, the |
| `inter_rater_reliability` | When more than one rater applies categorical (or ordinal, or |
| `interview_guide_design` | Qualitative protocols in Research-OS pick up at open coding. This |
| `machine_learning` | Reasoning scaffold for a predictive-modelling workflow. Names the |
| `mcp_ecosystem_integration` | Research OS is one MCP server. Researchers may need access to |
| `meta_analysis` | Reasoning scaffold for pooling effect estimates across primary |
| `method_comparison` | Compare N candidate methods on the SAME prediction / estimation |
| `methodological_consultation` | Lightweight protocol for the case where the researcher wants to |
| `methodology_selection` | Pick the statistical / computational method(s) for the active |
| `missing_data_strategy` | Missing data is not a nuisance to be silently dropped — it is a |
| `mixed_language_orchestration` | When `pick_tool_stack` lands on "mixed" — i.e. one analysis step |
| `mixed_methods` | Concurrent or sequential integration of qualitative and quantitative |
| `multiple_comparisons` | When a study tests more than one hypothesis on the same data, the |
| `pick_tool_stack` | Sister protocol to `visualization/figure_guidelines`'s `pick_library` |
| `pilot_study` | Small-N preliminary run to de-risk a full study: feasibility, instrument |
| `power_analysis` | Standalone power / sample-size justification — for the case where the |
| `preregistration` | Freeze the Statistical Analysis Plan (SAP) BEFORE data analysis so |
| `qualitative_quality_audit` | Companion to `methodology/qualitative_research`. The research protocol |
| `qualitative_research` | Interview / focus-group / ethnographic studies with thematic, framework, |
| `replication_study` | Re-execute a previously published analysis with explicit comparison to |
| `reproduction_attempt` | Attempt to REPRODUCE a published analysis — rerun the authors' |
| `simulation_studies` | Monte Carlo, agent-based, discrete-event, or in-silico studies. Follows |
| `survey_design` | survey_psychometrics analyses a survey that already exists. THIS |
| `survey_psychometrics` | Reasoning scaffold for analysing survey / multi-item-scale / |
| `timeseries_analysis` | First-class protocol for analyses where time order matters: |
| `tool_discovery` | Find the right Python / R / Julia library for a specific task and verify it can be installed. |
| `uncertainty_quantification` | Predictive models report point estimates by default. Calibrated |

### `reproducibility/` (1 protocols)

| Protocol | One-liner |
|---|---|
| `reproducibility` | Lock down environments, verify the pipeline runs end-to-end, and produce a Dockerfile for full portability. |

### `synthesis/` (18 protocols)

| Protocol | One-liner |
|---|---|
| `defense_prep` | A dissertation defense, a job talk, or a high-stakes conference |
| `journal_selection` | Picking the wrong venue wastes months. The right venue is the |
| `manuscript_outline` | Drafting a paper before outlining is the most common source of |
| `printable` | One protocol for every print-first deliverable. The protocol is |
| `synthesis_abstract` | Generate a structured / unstructured abstract tuned to the target venue. |
| `synthesis_cover_letter` | Draft the cover letter that accompanies a journal submission. The |
| `synthesis_dashboard` | Generate a polished single-file HTML dashboard that reads as |
| `synthesis_from_inputs` | Synthesis for the case where the researcher has finished analyses, |
| `synthesis_grant` | Draft a grant proposal narrative tuned to the target funder (NIH / NSF / Wellcome / ERC / DoE / DARPA /… |
| `synthesis_handout` | Redirect stub. The handout / one-pager content was consolidated |
| `synthesis_lay_summary` | Compile a plain-language summary of the project for a NON-EXPERT |
| `synthesis_null_findings` | Assemble a publishable companion document for findings that DIDN'T |
| `synthesis_paper` | Compile the final IMRAD paper into synthesis/paper.md (and |
| `synthesis_poster` | Redirect stub. Poster content was consolidated into |
| `synthesis_progress_update` | Compile a short progress update — the kind a researcher sends their |
| `synthesis_report` | Compile a non-journal report for internal stakeholders, clients, or a technical audience. |
| `synthesis_slides` | Compile a presentation deck — lab meeting, conference talk, defense, |
| `synthesis_title_workshop` | Generate, iterate, and pick a title for a paper / abstract / |

### `visualization/` (14 protocols)

| Protocol | One-liner |
|---|---|
| `animation_design` | Animation earns its place when CHANGE OVER TIME (or another |
| `color_accessibility_audit` | Audit one or more figures (or a dashboard's CSS palette) for |
| `distribution_comparison` | Comparing distributions across groups is one of the most common |
| `figure_critique` | Reviewer-style critique of ONE figure. Distinct from |
| `figure_guidelines` | The reasoning scaffold for producing publication-grade figures. |
| `figure_narrative_arc` | Choose and ORDER the figures that appear in a paper / talk / poster |
| `geospatial_visualization` | Data with a location dimension — counties, countries, points, |
| `interactive_dashboard_design` | `synthesis_dashboard` produces a single-file offline HTML — the |
| `interactive_figure_design` | When a SINGLE figure is best served by interactivity — hover-to- |
| `multi_panel_composition` | Compose a multi-panel figure — the kind where Figure 2 has panels |
| `network_visualization` | When relationships matter more than aggregates — co-authorship, |
| `showcase_visualization` | Most viz protocols treat the figure as a SUPPORT for a written |
| `uncertainty_visualization` | Point estimates without uncertainty mislead. A bar with no error, |
| `visualization_workflow` | Workflow protocol for when a researcher wants FIGURES — one, a few, or a |

### `writing/` (10 protocols)

| Protocol | One-liner |
|---|---|
| `writing_analysis_log` | Format for structured entries appended to `workspace/analysis.md` — |
| `writing_citations` | Maintain workspace/citations.md so every claim is grounded and every citation is verified online. |
| `writing_conclusions` | How to write per-step conclusions.md. Called by analysis_plan's document_conclusions step. |
| `writing_core` | Universal writing rules. Loaded implicitly by every writing/* and |
| `writing_data_availability` | Draft the Data Availability, Code Availability, Author Contributions |
| `writing_discussion` | Draft / iterate the Discussion section. The Discussion is where most |
| `writing_limitations` | Draft the limitations section / sub-section. Limitations are the |
| `writing_methods` | Document the methods used in an experiment in workspace/methods.md (append-only). |
| `writing_readme` | Maintain the project-level README and per-step READMEs. Per-step |
| `writing_results` | Draft the Results section. Results writing is its own skill: report |
<!-- AUTO:PROTOCOL_CATALOGUE_END -->

---

## Cross-intent shortcuts (no protocol load, single tool call)

`tool_route` also matches cross-cutting intents that don't need a
protocol:

| Trigger | Tool called |
|---|---|
| "progress", "where are we", "digest" | `tool_progress_digest` |
| "lessons", "what did we learn" | `tool_dead_end_lessons` |
| "list protocols", "available protocols" | `sys_protocol_list` |
| "missing dependencies", "what's installed" | `sys_dep_inventory` |
| "broken", "fix workspace" | `tool_workspace_repair` |
| "background", "kick off", "going to lunch" | `tool_task_run` |
| "quick test", "scratch", "throwaway" | `tool_scratch_write` |

---

## Anti-one-shot: the active plan + per-turn batching

When `tool_route` detects a complex prompt (>25 words OR multiple verbs
OR conjunctions like "and then" / "also"), it persists a planning
record to `.os_state/active_plan.json` and returns `complexity="high"`.
The AI MUST walk the plan instead of one-shotting:

* `tool_plan_turn` — returns `this_turn` (steps to execute now) +
  `next_turn` (queued), sized to the researcher's `model_profile`
  (small=1 step/turn, medium=3, large=6; heavy tools like
  `tool_synthesize` count for more).
* `tool_plan_advance` — after each step completes.
* `tool_plan_clear` — if the researcher pivots mid-plan.

When `chat_split_recommended=true` (long plan remaining), the AI hands
off + asks the researcher to open a fresh chat with "pick up where we
left off". `tool_session_resume` will read the handoff and active plan.

---

## Quality minimums

Every protocol declares a `quality_bar` block. Examples:

* `synthesis_paper`: abstract 200-300 words, methods ≥400 words, ≥1
  figure, ≥8 citations, every claim grounded, no causal language for
  observational designs.
* `synthesis_poster`: ≥2 figures ≥300 DPI, ≤6 citations, font ≥24pt,
  one headline message.
* `synthesis_dashboard`: single-file offline HTML, semantic landmarks,
  print-friendly, ≤12 citations, ≥3 sections.
* `synthesis_grant`: Specific Aims ≤500 words (1 page), Approach
  ≥1500 words, every Aim has milestones + pitfalls + alternatives,
  ≥15 citations.
* `methodology/qualitative_research`: every theme ≥2 quotes from ≥2
  participants; at least one disconfirming case reported; codebook
  reproducible by a second coder; reflexivity statement explicit.
* `methodology/replication_study`: replication criterion declared
  BEFORE looking at the new estimate; verdict supported by both
  criterion + sensitivity around original spec.
* `methodology/simulation_studies`: ADEMP written BEFORE code runs;
  Monte Carlo SE reported with every point estimate; sensitivity rerun
  confirms headline.

The AI is instructed to refuse to mark a synthesis complete until the
quality bar passes.

---

## How `model_profile` affects protocols

When the protocol loader reads a YAML, it applies the researcher's
`model_profile`:

* `small` — drops verbose keys (`model_adaptations`, `examples`,
  `templates`) to keep tokens minimal. AI tool descriptions are also
  trimmed.
* `medium` — standard (default).
* `large` — full detail; protocols may suggest multi-step planning.

`tool_plan_turn` also reads `model_profile` to size per-turn batches.
A researcher on a small local model gets 1 tool call per turn; a large
frontier model gets 6.

---

## Adding a new protocol

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the schema. Two
mandatory follow-ups:

1. Add an entry to `_router_index.yaml` with `intent_class`,
   `sub_intent`, `summary`, `triggers` (plus optional `shortcut_tool`,
   `token_estimate`, `decomposition`). Preflight will fail if you
   forget.
2. Add a test in `tests/tools/test_router.py` for a triggering prompt
   to verify the router picks your protocol.

The loader auto-injects a `protocol_completion` step — don't add one
yourself.
