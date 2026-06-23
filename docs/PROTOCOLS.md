# Protocol Reference

Research OS ships **130+ core YAML protocols** organised into thirteen
categories, plus pack-specific protocols (humanities, qualitative,
theory_math, wet_lab, engineering) when those packs are installed.
Each protocol is a sequence of steps the AI should follow, with
explicit `expected_outputs`, a `next_protocol` pointer, a
`quality_bar`, and — new in v2.0.0 — a `tier:` annotation +
`scope_tags: {domain, audience, workflow_shape}` block. All are
indexed in `src/research_os/protocols/_router_index.yaml` for
hierarchical + semantic routing via `tool_route`.

Counts below are accurate as of v3.11.1. The catalogue grows between
releases; run `tool_protocols_list` for the live, flat list with
filters rather than trusting a hardcoded number.

| Category | Count | What's in it |
|---|---|---|
| `methodology/` | 44 | Method pickers + per-family deep workflows (causal, ML, Bayesian, time-series, clinical, qualitative, mixed-methods, simulation, replication, ablation, pilot, evaluation design, hyperparameter sweep design, ethics review, EDA + hypothesis generation, method comparison, data-quality audit, power analysis, reproduction, methodological consultation, meta-analysis, spatial, survey psychometrics, preregistration), plus the cross-cutting protocols `pick_tool_stack` (R vs Python per sub-task), `mixed_language_orchestration` (Python↔R↔Bash composition), `qualitative_pii_redaction`, `bootstrapping_design`, `cox_ph_diagnostics`, `data_management_plan`, `fairness_audit`, `inter_rater_reliability`, `interview_guide_design`, `mcp_ecosystem_integration`, `missing_data_strategy`, `multiple_comparisons`, `survey_design`, `uncertainty_quantification`, `tool_discovery`, `external_tool_setup`, `deep_domain_research`. |
| `synthesis/` | 22 | Paper, abstract, poster, dashboard, grant, report, slides, lay summary, progress update, cover letter, title workshop, handout, null-findings companion, synthesis-from-inputs, manuscript_outline, journal_selection, defense_prep, printable, `deliverable_design`, `synthesis_step_report` (per-step interim report), `humanities_essay_structure`, `reviewer_response`. |
| `guidance/` | 19 | Session boot / resume / handoff / autopilot / collaboration, intake, iterative planning, dead-end routing, hypothesis + glossary tracking, mid-pipeline entry, code review, peer-review response, scope-clarification, constructive_disagreement, revise_and_resubmit. |
| `visualization/` | 14 | Figure guidelines, viz workflow, single-figure critique, multi-panel composition, narrative arc, colour-accessibility audit, interactive figure design, animation, distribution comparison, geospatial, interactive dashboard design, network, showcase, uncertainty. |
| `writing/` | 10 | Per-section drafting (methods / results / discussion / limitations / end-matter), writing core rules, citations ledger, conclusions, analysis log, README. |
| `literature/` | 5 | Search, systematic review (PRISMA), evidence synthesis (GRADE), comparative paper review, `literature_per_step` (per-step search → download → cite → write `findings_vs_literature.md` with `AGREES \| DISAGREES \| EXTENDS \| DEFERRED \| IMPORTED_AS_CITED` verdicts). |
| `build/` | 5 | The **tool_build** workspace mode lifecycle: spec_and_design, implement_iteration, test_strategy, benchmark_vs_baseline, release_and_changelog. |
| `audit/` | 3 | Master audit + validation, pre-submission checklist, provenance completeness. |
| `exploration/` | 3 | The **exploration** workspace mode: exploration_loop, exploration_triage, exploration_promote (promote a probe to a real step when it earns it). |
| `domain/` | 2 | Domain classification, research-design + sample-size justification. |
| `reproducibility/` | 1 | Per-step env lock, seed verification, container generation. |
| `notebook/` | 1 | notebook_workflow — interactive notebook-driven analysis. |
| `program/` | 1 | program_setup — multi-project program scaffolding. |
| **Core total** | **130** | All protocols carry `tier:` + `scope_tags`. |

Pack-specific protocols (loaded only when the matching pack is
installed) add more across `humanities/` (archival, citation,
method, output, textual), `qualitative/` (coding, method, output,
validity), `theory_math/` (conjecture, formal, method, output,
proof), `wet_lab/`, and `engineering/`. Run `sys_packs_installed` to
see which packs are active in your project and `tool_protocols_list`
for the flat catalogue with filters.

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

## How the AI picks a protocol (the v2 router)

The AI does **not** load every YAML to find the right one. The AI only
ever acts AFTER a researcher message arrives; on the first turn of a
session it fires these calls back-to-back:

1. **`sys_boot`** — FIRST MCP call (first turn only). Returns workspace
   state + config + history + dep inventory + recommended pipeline-next
   protocol + pause classification + any active plan.
2. **`tool_route(prompt=<researcher's verbatim message>)`** — SECOND
   MCP call. Hybrid router: tries SEMANTIC search first (embeddings
   over protocol descriptions + triggers) and falls back to the
   hierarchical L1 → L2 → L3 trigger picker when semantic confidence
   is low. Returns:
   * `primary_protocol` — name of the best-matching protocol
   * **`recommended_action`** *(v2.0 new)* — literal next-call
     string, e.g. `sys_protocol_get(protocol_name='X', format='summary')`.
     Use it verbatim — no decoding required.
   * **`why_matched`** *(v2.0 new)* — short rationale (semantic
     similarity score, matched triggers, tier).
   * **`tier`** *(v2.0 new)* — the matched protocol's tier (one of
     `intake | plan | execute | ground | synthesize | review |
     finalize`) for filtering candidates.
   * `alternatives` — ranked alternates each with their own
     `recommended_action` + `why_matched`.
   * L1 `intent_class` — one of `session | discover | plan | execute |
     methodology | literature | synthesize | audit_wrap | memory |
     review`.
   * L2 `sub_intent` — narrower bucket within the class.
   * `decomposition` — ordered sub-task list (for `complexity: high`).
   * `complexity` — `low` vs `high`.
   * `ask_user` — one-sentence clarifier when the prompt is genuinely
     ambiguous.
   * `shortcut_tool` — when a single tool handles the intent (e.g.
     `tool_intake_autofill`), skip the protocol load entirely.
3. **`sys_protocol_get`** — defaults to `format='summary'`
   *(v2.0 change — was `full`)*. Step headings only, ~300 tokens.
   `format='step' step_id='<id>'` loads one step body when ready to
   execute (~150-500 tokens). The response includes a `_load_hint`
   guiding the AI to drill into `format='full'` only when needed.
4. **`sys_active_tools(protocol_name=<from-step-3>)`** — returns the
   tight 13-18-tool shortlist the AI should prefer while executing the
   protocol. Shrinks the working surface ~10× per turn.

This entire path costs ~1.2K tokens — vs the ~5K it took before the
routing layer existed.

### Discovery: `tool_protocols_list`

For audits, dashboards, or AI-driven catalogue browsing, call
**`tool_protocols_list`** *(v2.0 new)* — returns the flat protocol
catalogue with structured metadata (name, category, pack, intent_class,
tier, version, short description). Supports filters by `category`,
`pack`, `intent_class`, and `tier`. The discovery counterpart of
`sys_protocol_list` (which returns one-liners suitable for AI
orientation).

---

## The main pipeline (10 stages, in order)

| # | Protocol | What it does | Done when |
|---|---|---|---|
| 1 | `guidance/session_boot` | One-call boot via `sys_boot`; route first message via `tool_route` | first entry in execution log |
| 2 | `guidance/project_startup` | Intake autofill, profile data, lock research question | intake.md filled + research_overview.md confirmed |
| 3 | `domain/domain_analysis` | Classify domain, pick reporting standard, list biases | `domain_summary.md` written to the project's `docs/` |
| 4 | `domain/research_design` | Choose study design + sample size justification | `research_design.md` written to the project's `docs/` |
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
* `synthesis/synthesis_poster` — Typst poster (academic_36x48 default,
  academic_48x36, academic_a0_portrait, academic_a1_landscape,
  public_24x36). Audience profiles (academic_conference / symposium /
  industry / teaching). ≥2 figures ≥300 DPI, ≤6 citations.
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
[TOOLS.md](TOOLS.md#catalogue-alphabetical-by-canonical-name) (alphabetical catalogue).

### Audit + reproducibility

* `audit/audit_and_validation` — master quality audit
  (`tool_audit_quality_full`): step completeness, code quality, prose
  quality, claim grounding, pre-registration diff, grounding
  verification. Single call, every gate. Aggregates to
  `workspace/logs/audit_master.md`. **v2.0.0:** returns structured
  per-component verdicts: `components: {step_completeness,
  code_quality, prose_quality, claims, preregistration_diff,
  grounding}` each with `{status, blockers, advice}`.
* `audit/pre_submission_checklist` — final GREEN/YELLOW/RED gate.
  Reads `workspace/logs/override_log.md` and asks the researcher to
  confirm each bypass before submission.
* `audit/provenance_completeness` — every figure / table / model /
  report output in the workspace has a `.prov.json` sidecar with
  inputs, version, content hash.
* `reproducibility/reproducibility` — per-step env snapshot, seed
  verification, output hashing, Apptainer + Dockerfile + entrypoint
  generation.

### Per-dimension audits via `tool_audit`

v2.0.0 collapsed 23 per-dimension `tool_audit_*` tools into the
`tool_audit(scope, dimension)` dispatcher. The matching `scope` +
`dimension` per gate:

| Gate | Call |
|---|---|
| Step completeness | `tool_audit(scope='step', dimension='completeness')` |
| Step code quality | `tool_audit(scope='step', dimension='code_quality')` |
| Step assumptions (residual normality, etc.) | `tool_audit(scope='step', dimension='assumptions')` |
| Step figure full (DPI / sidecars / SVG / text overlap) | `tool_audit(scope='step', dimension='figure_full')` |
| Step figure interactivity | `tool_audit(scope='step', dimension='figure_interactivity')` |
| Step literature loop | `tool_audit(scope='step', dimension='literature')` |
| Step power | `tool_audit(scope='step', dimension='power')` |
| Step reproducibility | `tool_audit(scope='step', dimension='reproducibility')` |
| Step E-value (causal sensitivity) | `tool_audit(scope='step', dimension='evalue')` |
| Project claims (numeric grounding) | `tool_audit(scope='project', dimension='claims')` |
| Project citations | `tool_audit(scope='project', dimension='citations')` |
| Project cliches | `tool_audit(scope='project', dimension='cliches')` |
| Project coherence | `tool_audit(scope='project', dimension='coherence')` |
| Project cross-deliverable consistency | `tool_audit(scope='project', dimension='cross_deliverable')` |
| Project prose | `tool_audit(scope='project', dimension='prose')` |
| Project version coherence | `tool_audit(scope='project', dimension='version_coherence')` |
| Synthesis manuscript (all gates) | `tool_audit(scope='synthesis', dimension='all')` |
| Synthesis dashboard content | `tool_audit(scope='synthesis', dimension='dashboard_content')` |
| Synthesis figure coverage | `tool_audit(scope='synthesis', dimension='figure_coverage')` |
| Synthesis reviewer responses | `tool_audit(scope='synthesis', dimension='reviewer_responses')` |

The legacy per-dimension names (`tool_audit_step_completeness`,
`tool_audit_claims`, etc.) continue to dispatch through the v2.0.x
runway via aliases — old calls still work. Phase 14a hard-removed the
v1.6.1 first-wave aliases (`tool_search_*`, `tool_plan_*`,
`tool_ground_*`, `tool_verify_*`, `sys_path_*`, `mem_*_log` /
`mem_*_append`); calling those returns a friendly `_REMOVED_TOOLS`
error envelope naming the canonical v2 entry point. See
`CHANGELOG.md [2.0.0]` for the full table.

### Cross-audit findings ledger (v2.0.0 new)

Every audit emits a JSON companion alongside the Markdown report and
appends structured rows to the project-level append-only ledger at
`workspace/logs/.audit_findings.jsonl`. Each row carries `id` (stable
UUIDv5), `audit_name`, `severity` (`block | warn | info`), `dimension`,
`evidence_paths`, `suggested_fix`, `ro_version`, `generated_at`.

Query the ledger with `tool_audit_findings`:

* `tool_audit_findings(operation='query', severity='block')` — list
  current active blockers (latest snapshot per stable id).
* `tool_audit_findings(operation='query', dimension='claims', step='03_de_analysis')` —
  filter by dimension + step.
* `tool_audit_findings(operation='diff', timestamp_a=..., timestamp_b=...)` —
  confirm a fix actually resolved a BLOCK finding between two audit runs.

`tool_audit(scope='synthesis')` surfaces unresolved BLOCKs in the
ledger in its error envelope; triage them with
`tool_audit_findings(operation='query', severity='block')` and resolve
the source before authoring or compiling the deliverable.

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

_All 142 protocols, grouped by category, alphabetised within each._

### `audit/` (3 protocols)

| Protocol | One-liner |
|---|---|
| `audit_and_validation` | Validate citations, statistical assumptions, figure quality, |
| `pre_submission_checklist` | Final ready-to-submit gate. Walks the project through every |
| `provenance_completeness` | Every figure, table, model artefact, and report output in the workspace |

### `build/` (9 protocols)

| Protocol | One-liner |
|---|---|
| `benchmark_vs_baseline` | Reason about how to measure the tool honestly against the right |
| `dependency_integration` | The closing step of the "borrow it or build it" arc: take a candidate that |
| `implement_iteration` | The core build loop for tool_build mode — the analog of |
| `integration_spike` | The decisive middle step of the "borrow it or build it" arc: before a |
| `method_scouting` | The opening move when a tool_build or hybrid project needs a capability it |
| `package_and_publish` | The distribution step a tool takes after it has a cut release: make it |
| `release_and_changelog` | Turn a set of committed increments into a release a consumer can adopt |
| `spec_and_design` | The opening move of a tool_build workspace. Before any code, pin down |
| `test_strategy` | Reason about what testing regime actually fits the tool being built — |

### `domain/` (2 protocols)

| Protocol | One-liner |
|---|---|
| `domain_analysis` | Classify the research domain, surface the reporting standard the field actually uses, and list the biases… |
| `research_design` | Choose the study design that fits the question (interventional vs observational, comparative vs descriptive,… |

### `exploration/` (3 protocols)

| Protocol | One-liner |
|---|---|
| `exploration_loop` | The core loop of an exploration-mode workspace: a tight, cheap |
| `exploration_promote` | The bridge out of exploration mode: take a scratch probe that earned it |
| `exploration_triage` | The orienting pass for an exploration-mode workspace facing a fresh, |

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

### `hybrid/` (2 protocols)

| Protocol | One-liner |
|---|---|
| `hybrid_workflow` | The home loop of a hybrid project: one where the deliverable is BOTH a tool |
| `tool_to_analysis_handoff` | The transition protocol of a hybrid project: the moment a tool increment is |

### `literature/` (5 protocols)

| Protocol | One-liner |
|---|---|
| `comparative_paper_review` | Compare-and-contrast review of TWO OR MORE papers. Distinct from: |
| `evidence_synthesis` | Build an evidence table from the literature corpus, grade each entry on the field's certainty framework, and… |
| `literature_per_step` | After every analysis step writes its findings, RO grounds those |
| `literature_search` | Multi-database literature search across several academic providers. |
| `systematic_review` | Full PRISMA workflow for a primary systematic review or meta-analysis project. |

### `methodology/` (44 protocols)

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
| `qualitative_pii_redaction` | Run BEFORE `qualitative_research` opens transcripts for coding. |
| `qualitative_quality_audit` | Companion to `methodology/qualitative_research`. The research protocol |
| `qualitative_research` | Interview / focus-group / ethnographic studies with thematic, framework, |
| `replication_study` | Re-execute a previously published analysis with explicit comparison to |
| `reproduction_attempt` | Attempt to REPRODUCE a published analysis — rerun the authors' |
| `simulation_studies` | Monte Carlo, agent-based, discrete-event, or in-silico studies. Follows |
| `spatial_analysis` | Reasoning scaffold for analysing data with a spatial structure — |
| `survey_design` | Distinct from survey_psychometrics, which analyses a survey that |
| `survey_psychometrics` | Reasoning scaffold for analysing survey / multi-item-scale / |
| `timeseries_analysis` | First-class protocol for analyses where time order matters: |
| `tool_discovery` | Find the right Python / R / Julia library for a specific task and verify it can be installed. |
| `uncertainty_quantification` | Predictive models report point estimates by default. Calibrated |

### `notebook/` (4 protocols)

| Protocol | One-liner |
|---|---|
| `notebook_promote` | The bridge out of a notebook. A notebook is excellent for working out an |
| `notebook_reproduce` | The hardening pass for a notebook that already runs interactively but is |
| `notebook_synthesize` | The terminal move of a notebook workspace: take the figures, tables, and |
| `notebook_workflow` | The home loop of a notebook (Jupyter-first) workspace. The unit of work |

### `program/` (4 protocols)

| Protocol | One-liner |
|---|---|
| `codebook_governance` | The protocol for the most dangerous moment in a research program: changing |
| `cross_study_synthesis` | The terminal move of a multi_study program: read across the completed |
| `program_setup` | The opening move of a multi_study (program) workspace. Before any single |
| `study_register` | The recurring move of a multi_study program: register a new sub-study under |

### `reproducibility/` (1 protocols)

| Protocol | One-liner |
|---|---|
| `reproducibility` | Lock down environments, verify the pipeline runs end-to-end, and produce a Dockerfile for full portability. |

### `synthesis/` (22 protocols)

| Protocol | One-liner |
|---|---|
| `defense_prep` | A dissertation defense, a job talk, or a high-stakes conference |
| `deliverable_design` | The design SKILL for shareable research deliverables — the deliverable-level |
| `humanities_essay_structure` | Guide the AI to author `synthesis/essay.typ` directly as a |
| `journal_selection` | Picking the wrong venue wastes months. The right venue is the |
| `manuscript_outline` | Drafting a paper before outlining is the most common source of |
| `printable` | Guide the AI to author a printable deliverable directly. One |
| `reviewer_response` | Run a 7-persona adversarial self-review against the FINISHED paper |
| `synthesis_abstract` | Generate a structured / unstructured abstract tuned to the target venue. |
| `synthesis_cover_letter` | Draft the cover letter that accompanies a journal submission. The |
| `synthesis_dashboard` | Guide the AI to author `synthesis/dashboard.html` as a **custom, |
| `synthesis_from_inputs` | Synthesis for the case where the researcher has finished analyses, |
| `synthesis_grant` | Guide the AI to author `synthesis/grant.typ` directly as a grant |
| `synthesis_handout` | Redirect stub. The handout / one-pager content lives in |
| `synthesis_lay_summary` | Compile a plain-language summary of the project for a NON-EXPERT |
| `synthesis_null_findings` | Assemble a publishable companion document for findings that DIDN'T |
| `synthesis_paper` | Guide the AI to author `synthesis/paper.typ` directly, section by |
| `synthesis_poster` | Redirect stub. Poster content lives in |
| `synthesis_progress_update` | Compile a short progress update — the kind a researcher sends their |
| `synthesis_report` | Compile a non-journal report for internal stakeholders, clients, or a technical audience. |
| `synthesis_slides` | Guide the AI to author `synthesis/slides.typ` directly (Touying |
| `synthesis_step_report` | Guide the AI to author a **self-contained, presentation-grade visual |
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
| `writing_citations` | Maintain workspace/citations.md so every claim is grounded and every |
| `writing_conclusions` | How to write per-step `workspace/<step>/conclusions.md`. Called by |
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

| Trigger | Tool called (v2 canonical name) |
|---|---|
| "progress", "where are we", "digest" | `tool_progress_digest` |
| "lessons", "what did we learn" | `tool_lessons(operation='dead_end')` |
| "list protocols", "available protocols" | `sys_protocol_list` or `tool_protocols_list` |
| "list tools", "available tools" | `tool_tools_list` |
| "missing dependencies", "what's installed" | `sys_dep_inventory` |
| "broken", "fix workspace" | `tool_workspace_repair` |
| "background", "kick off", "going to lunch" | `tool_task(operation='run')` |
| "quick test", "scratch", "throwaway" | `tool_scratch(operation='write')` |
| "fill out the intake", "what do I have" | `tool_intake_autofill` |
| "is install OK", "health check" | (CLI) `research-os doctor` |

---

## Anti-one-shot: the active plan + per-turn batching

When `tool_route` detects a complex prompt (>25 words OR multiple verbs
OR conjunctions like "and then" / "also"), it persists a planning
record to `.os_state/active_plan.json` and returns `complexity="high"`.
The AI MUST walk the plan instead of one-shotting:

* `tool_plan(operation='turn')` — returns `this_turn` (steps to execute
  now) + `next_turn` (queued), sized to the researcher's `model_profile`
  (small=1 step/turn, medium=3, large=6; heavy tools like
  `tool_typst_compile` count for more).
* `tool_plan(operation='advance')` — after each step completes.
* `tool_plan(operation='clear')` — if the researcher pivots mid-plan.

(The legacy `tool_plan_turn` / `tool_plan_advance` / `tool_plan_clear` names were hard-removed
in v2.0.0 — call `tool_plan(operation=...)` with the matching
`operation`. The `_REMOVED_TOOLS` error envelope names the canonical
entry point if a stale caller hits the old name.)

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

`tool_plan(operation='turn')` also reads `model_profile` to size
per-turn batches. A researcher on a small local model gets 1 tool call
per turn; a large frontier model gets 6.

---

## Tier annotations (v2.0.0 new)

Every protocol carries a `tier:` annotation that places it in the
project lifecycle. The tier taxonomy is intentionally narrow (7
buckets, ordered) — it's about progress reporting + flow rules, not
protocol search. The existing `intent_class` (10 values) +
`sub_intent` (60+ values) remain the routing axes.

```
intake → plan → execute → ground → synthesize → review → finalize
```

* `intake` — bootstrap, project intake, research overview
  (`guidance/project_startup`, `domain/domain_analysis`, …).
* `plan` — hypothesis, methodology, decomposition
  (`guidance/analysis_plan`, `methodology/methodology_selection`,
  `methodology/preregistration`, …).
* `execute` — analysis, code, data steps (per-method protocols, EDA,
  `methodology/exploratory_data_analysis`, …).
* `ground` — literature gate, claim grounding
  (`literature/literature_per_step`, `literature/literature_search`,
  …).
* `synthesize` — paper, slides, poster, dashboard drafting
  (`synthesis/synthesis_paper`, `synthesis/synthesis_dashboard`, …).
* `review` — reviewer simulation, drafter loop, peer-review prep
  (`synthesis/reviewer_response`, `guidance/peer_review_response`,
  …).
* `finalize` — cross-deliverable consistency, submission prep
  (`audit/pre_submission_checklist`, `audit/provenance_completeness`,
  …).

`tool_route` echoes the resolved protocol's tier in `why_matched` on
every successful match; `tool_step_complete` advances the workspace's
`current_tier` when a step moves the project across a tier boundary.
Backward transitions (re-running an `execute` step after the project
has reached `synthesize`) are tracked so the AI can flag pivots in
progress digests.

---

## `scope_tags` (v2.0.0 new)

Every protocol carries a `scope_tags:` block that describes its
applicability:

```yaml
scope_tags:
  domain: [any]                # or [theory_math, qualitative, ...]
  audience: [researcher, naive_ai]
  workflow_shape: [experiment_pipeline]
```

* `domain` — `any` or any subset of
  `theory_math | qualitative | humanities | wet_lab | engineering |
  empirical_statistical`. Cross-cutting protocols (e.g.
  `audit/audit_and_validation`) use `[any]`.
* `audience` — `researcher | naive_ai | auditor | maintainer`. Drives
  prose voice + assumed expertise.
* `workflow_shape` — `experiment_pipeline | proof |
  archive_lookup | benchmark | qualitative_interview |
  systematic_review | ...`. Used by the router to filter candidates
  whose shape obviously doesn't match the prompt.

The router can now filter wet-lab protocols out of dry-lab queries
based on `scope_tags`, though default-filter wiring is scheduled for
v2.1.0 — the infrastructure shipped in v2.0.0 carries the tags but
the router does not yet exclude on them automatically.

---

## Adding a new protocol

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the schema. Mandatory
follow-ups for v2.0.0:

1. Set `tier:` on the protocol (one of the 7 lifecycle buckets above).
2. Set `scope_tags: {domain, audience, workflow_shape}` (preflight
   fails if missing).
3. Add an entry to `_router_index.yaml` with `intent_class`,
   `sub_intent`, `summary`, `triggers` (plus optional `shortcut_tool`,
   `token_estimate`, `decomposition`). Preflight will fail if you
   forget.
4. Add a test in `tests/tools/test_router.py` for a triggering prompt
   to verify the router picks your protocol.

The loader auto-injects a `protocol_completion` step — don't add one
yourself.
