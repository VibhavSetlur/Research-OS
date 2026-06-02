# Protocol Reference

Research OS ships **88 YAML protocols** organised into nine categories.
Each protocol is a sequence of steps the AI should follow, with explicit
`expected_outputs`, a `next_protocol` pointer, and a `quality_bar`. All
are indexed in `src/research_os/protocols/_router_index.yaml` for
hierarchical routing via `tool_route`.

| Category | Count | What's in it |
|---|---|---|
| `methodology/` | 29 | Method pickers + per-family deep workflows (causal, ML, Bayesian, time-series, clinical, qualitative, mixed-methods, simulation, replication, ablation, pilot, evaluation design, hyperparameter sweep design, ethics review, EDA + hypothesis generation, method comparison, data-quality audit, power analysis, reproduction, methodological consultation). |
| `guidance/` | 19 | Session boot / resume / handoff / autopilot / collaboration, intake, iterative planning, dead-end routing, hypothesis + glossary tracking, mid-pipeline entry, code review, peer-review response, **scope-clarification**. |
| `synthesis/` | 14 | Paper, abstract, poster, dashboard, grant, report, slides, lay summary, progress update, cover letter, title workshop, handout, null-findings companion, synthesis-from-inputs. |
| `writing/` | 10 | Per-section drafting (methods / results / discussion / limitations / end-matter), writing core rules, citations ledger, conclusions, analysis log, README. |
| `visualization/` | 6 | Figure guidelines, viz workflow, single-figure critique, multi-panel composition, narrative arc, colour-accessibility audit. |
| `literature/` | 4 | Search, systematic review (PRISMA), evidence synthesis (GRADE), comparative paper review. |
| `audit/` | 3 | Master audit + validation, plus targeted gates. |
| `domain/` | 2 | Domain classification, research-design + sample-size justification. |
| `reproducibility/` | 1 | Per-step env lock, seed verification, container generation. |
| **Total** | **88** | |

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

The AI does **not** load every YAML to find the right one. Instead:

1. **`sys_boot`** — single call returns workspace state + recommended
   pipeline-next protocol + advice.
2. **`tool_route(prompt=<researcher's message>)`** — hierarchical
   L1 → L2 → L3 picker. Returns the deepest unambiguous level:
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
