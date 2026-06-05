# Use Cases — which protocol for which researcher, which moment

Research OS is designed for the **full** research life-cycle, not just the
linear data → publication path. This document is a role × goal map: pick
your role, find your situation, see the protocol the AI will route to.

You don't need to memorise this. Just talk in plain English; `tool_route`
picks the protocol. This page exists so you know what's possible.

---

## Common first prompts (start here)

These are the highest-leverage first-turn prompts validated against five
end-to-end scenarios. Each one routes cleanly; pick the row that matches
what you actually have on disk, paste a one-line variant into the chat,
and let the AI work.

| What you arrived with | Try this first prompt | Routes to |
|---|---|---|
| Data + a specific hypothesis | "I dropped my <dataset> in inputs/ — I want to test whether <hypothesis>." | `guidance/project_startup` → `tool_intake_autofill` |
| Data, no hypothesis yet | "I have <dataset> in inputs/ — explore it and help me find a hypothesis." | `methodology/exploratory_data_analysis` |
| A text corpus (humanities / lit) | "I have <N> texts in inputs/raw_data/ — test whether <stylistic claim>." (e.g. James's late-style vocabulary shift) | `humanities/method/digital_humanities_workflow` (auto-loads the humanities pack); see also `humanities/textual/distant_reading` + `humanities/method/close_reading` |
| Interview transcripts | "I have <N> interview transcripts in inputs/raw_data/ — walk this through to a paper + dashboard." | `methodology/qualitative_research` → `methodology/coding_scheme_development` → `methodology/qualitative_quality_audit` |
| Benchmark / engineering measurements | "Benchmark <variant A> vs <variant B> vs <variant C> across <input sizes>; quantify when A wins." | `methodology/method_comparison` (engineering pack auto-detects) |
| A theorem to prove | "I have a conjecture: <statement>. Help me prove it and write it up as a theory paper." | `theory_math/proof/proof_verification_workflow` (theory_math pack); see also `theory_math/conjecture/conjecture_tracking` |
| Mixed: "I have a draft and some data" | "I'm bringing this project into Research-OS; we've been working on it for months." | `guidance/mid_pipeline_entry` |
| You're not sure yet | "I have some data and some ideas — help me figure out where to start." | `guidance/scope_clarification` |

A couple of fresh-agent tips that the validation surfaced:

* **You don't have to phrase it as one of the above.** `tool_route` does
  semantic matching first, then a hierarchical L1 → L2 → L3 trigger
  picker. "head-to-head", "bake-off", "horse race" all hit
  `method_comparison`; "prove this", "I have a claim I need to prove",
  "proof verification" all hit the theory_math pack.
* **If the router picks the wrong protocol, say "actually I meant X".**
  The AI re-routes without re-loading the workspace.
* **If you don't have data yet, just say so.** "Teach me about <method>
  before I use it" loads `methodology/methodological_consultation` and
  doesn't commit you to a project.

---

## By role

### The graduate student / postdoc running their own analyses

| You want to… | Say something like… | Protocol |
|---|---|---|
| Set up a new project from data + papers | "fill the intake" | `guidance/project_startup` |
| Run the next experiment | "run an EDA", "fit a logistic regression" | `guidance/analysis_plan` |
| Decide what to do next | "what should I do next" | `guidance/iterative_planning` |
| Sandbox-explore without paperwork | "just poke at this", "sanity check" | `guidance/casual_exploration` |
| Generate hypotheses from data | "do real EDA — no hypothesis yet" | `methodology/exploratory_data_analysis` |
| Compare two methods head-to-head | "benchmark RF vs XGB on this" | `methodology/method_comparison` |
| Design the eval (split + CV + metrics) | "design the evaluation strategy" | `methodology/evaluation_design` |
| Design a hyperparameter sweep | "design the sweep, equal budgets" | `methodology/hyperparameter_search_design` |
| Workshop my paper title | "give me title alternatives" | `synthesis/synthesis_title_workshop` |
| Write the Discussion | "draft the discussion" | `writing/writing_discussion` |
| Write the Limitations | "tighten the limitations" | `writing/writing_limitations` |
| Write the paper | "draft the manuscript for a journal" | `synthesis/synthesis_paper` |
| Cover letter for submission | "draft a cover letter" | `synthesis/synthesis_cover_letter` |
| End-matter (data avail / CRediT / etc.) | "draft the end matter" | `writing/writing_data_availability` |
| Pre-submission final check | "is this ready to submit" | `audit/pre_submission_checklist` |
| Make a poster | "make me a conference poster" | `synthesis/synthesis_poster` |
| Make a one-pager / handout | "make a one-pager for the poster session" | `synthesis/synthesis_handout` |
| Make a dashboard | "build a dashboard" | `synthesis/synthesis_dashboard` |
| Wrap up a working session | "wrap up", "going to lunch" | `guidance/chat_handoff` |
| Come back next day | "pick up where we left off" | `guidance/session_resume` |

### The principal investigator / lab leader

| You want to… | Say something like… | Protocol |
|---|---|---|
| Read a draft paper for a journal club | "review this paper" | `guidance/quick_paper_review` |
| Compare 3-5 papers on a related-work search | "compare these papers", "journal club on these" | `literature/comparative_paper_review` |
| Get a weekly update for a meeting | "weekly update", "milestone update" | `synthesis/synthesis_progress_update` |
| Draft an NIH R01 | "draft an R01 grant" | `synthesis/synthesis_grant` |
| Draft the funder lay-summary section | "lay summary for the grant" | `synthesis/synthesis_lay_summary` |
| Vet a collaborator's analysis script | "review this code" | `guidance/code_review` |
| Respond to peer review on your paper | "draft a rebuttal" | `guidance/peer_review_response` |
| Package a finished project for a new lab | "send to a collaborator", "package for handoff" | `guidance/collaboration_handoff` |

### The methodologist / statistical consultant

| You want to… | Say something like… | Protocol |
|---|---|---|
| Teach a method to a consult-er | "explain mixed-effects models" | `methodology/methodological_consultation` |
| Justify a power calc for an upcoming RCT | "power analysis", "sample size" | `methodology/power_analysis` |
| Audit a dataset before recommending methods | "data quality audit" | `methodology/data_quality_audit` |
| Walk through methodology pick for a project | "which method should I use" | `methodology/methodology_selection` |
| Design split / CV / metric / paired test | "design the evaluation strategy" | `methodology/evaluation_design` |
| Design a hyperparameter sweep | "design the sweep" | `methodology/hyperparameter_search_design` |
| Walk an ethics review | "data ethics review" | `methodology/data_ethics_review` |
| Push back when the chosen direction is weak | "tell me if I'm wrong" | `guidance/constructive_disagreement` |
| Build the canonical pipeline for a subfield | "best-practice pipeline for snRNA-seq" | `methodology/deep_domain_research` |
| Pre-register the SAP | "freeze the analysis plan" | `methodology/preregistration` |
| Set up a simulation study (ADEMP) | "run a simulation study" | `methodology/simulation_studies` |

### The reviewer / journal-club host / reading-group leader

| You want to… | Say something like… | Protocol |
|---|---|---|
| Quick 30-min critique of a paper | "tear apart this paper" | `guidance/quick_paper_review` |
| Compare-and-contrast 3-5 papers | "journal club on these" | `literature/comparative_paper_review` |
| Critique a single figure from a paper | "critique Figure 2 of this paper" | `visualization/figure_critique` |
| Attempt to reproduce a published analysis | "reproduce this paper" | `methodology/reproduction_attempt` |
| Run a full systematic review (PRISMA) | "systematic review of X" | `literature/systematic_review` |
| Grade a body of evidence (GRADE) | "grade the evidence on X" | `literature/evidence_synthesis` |

### The communicator / outreach lead / press office

| You want to… | Say something like… | Protocol |
|---|---|---|
| Press release on a finding | "press release" | `synthesis/synthesis_lay_summary` (audience: press_release) |
| Patient-facing newsletter blurb | "patient newsletter explainer" | `synthesis/synthesis_lay_summary` (audience: patient_or_participant) |
| Twitter / Mastodon / Bluesky thread | "twitter thread on this paper" | `synthesis/synthesis_lay_summary` (audience: social_thread) |
| Lab blog post | "blog post about the project" | `synthesis/synthesis_lay_summary` (audience: blog_post) |
| Lay-summary box for an NIH grant | "funder lay-summary section" | `synthesis/synthesis_lay_summary` (audience: funder_lay_section) |

### The teacher / course instructor

| You want to… | Say something like… | Protocol |
|---|---|---|
| Build a lecture slide deck on a project | "build a teaching deck" | `synthesis/synthesis_slides` (audience: teaching) |
| Build a dashboard for a class | "teaching dashboard" | `synthesis/synthesis_dashboard` (audience: teaching) |
| Walk students through a method | "explain ANCOVA to me" | `methodology/methodological_consultation` |
| Have students reproduce a paper as an exercise | "reproduce this paper as a class exercise" | `methodology/reproduction_attempt` (audience: course_or_teaching) |

### The presenter / talk-giver

| You want to… | Say something like… | Protocol |
|---|---|---|
| Lab meeting slides | "lab meeting deck" | `synthesis/synthesis_slides` (audience: lab_meeting) |
| 12-minute conference talk | "conference slides, 12 min" | `synthesis/synthesis_slides` (audience: conference_talk_short) |
| Defense talk | "defense slides" | `synthesis/synthesis_slides` (audience: defense) |
| Invited seminar / job talk | "invited seminar deck" | `synthesis/synthesis_slides` (audience: invited_seminar) |
| Conference poster | "make a poster" | `synthesis/synthesis_poster` |

### The theorist / mathematician (theory_math pack)

The theory_math pack ships eight protocols for conjecture → proof
→ formal-check workflows. Activate by saying "prove this", "I have a
conjecture", "draft a proof", or by dropping a `.lean` / `.v` /
`.tex` proof draft into `inputs/raw_data/`. The pack also detects
`inputs/preliminaries.md` (definitions / lemmas the proofs assume).

| You want to… | Say something like… | Protocol |
|---|---|---|
| Register an open problem you might tackle later | "log this conjecture for now" | `theory_math/conjecture/conjecture_tracking` |
| Choose between direct / contradiction / induction / contrapositive / construction | "which proof strategy fits this claim" | `theory_math/method/proof_strategy_selection` |
| Walk a claim from statement to verified proof | "prove this claim end-to-end" | `theory_math/proof/proof_verification_workflow` |
| Maintain a reusable lemma library across proofs | "register this as a lemma" | `theory_math/proof/lemma_library` |
| Render the dependency DAG across lemmas + theorems | "show me the theorem dependency graph" | `theory_math/proof/theorem_dependency_graph` |
| Formalise a proof in Lean 4 + Mathlib | "formalise this in Lean" | `theory_math/formal/lean_integration` |
| Formalise a proof in Coq | "formalise this in Coq" | `theory_math/formal/coq_integration` |
| Compile the theory paper (Theorem / Proof / Refs, NOT IMRAD) | "compile the theory paper" | `theory_math/output/theory_paper_structure` |

Three theory-only tools come with the pack:

* `tool_theory_math_lean_check` — runs `lean --make` on a `.lean` file
  with structured error parsing. Writes an install hint when Lean is
  absent.
* `tool_theory_math_coq_check` — `coqc` equivalent for Coq sources.
* `tool_theory_math_dep_graph` — parses every `.lean` / `.v` under a
  source directory, extracts named theorems / lemmas / definitions +
  module imports, writes a Mermaid + JSON dependency graph.

When the formal-check trigger fires
(`proof_verification_workflow.quality_bar.formal_check_required_when`),
the workflow flags the candidate proof and routes through
`lean_integration` or `coq_integration`. Bourbaki-style careful
informal proofs remain valid — formal check is required only when the
result is foundational, contradicts a widely-believed conjecture, or
uses an unusual axiom.

### The "I'm starting in the middle" researcher

You already have data + analyses + figures from before RO was set up. You
don't want to redo the intake.

| You want to… | Say something like… | Protocol |
|---|---|---|
| Plug an in-progress project into RO | "bringing this into Research-OS" | `guidance/mid_pipeline_entry` |
| Synthesize from results you computed elsewhere | "we already analysed this, just write it up" | `synthesis/synthesis_from_inputs` |
| Polish figures you already have | "polish my figures" | `visualization/visualization_workflow` |
| Critique a figure you already drafted | "critique this figure" | `visualization/figure_critique` |
| Resume a paused RO project | "pick up where we left off" | `guidance/session_resume` |

### The "I just want a viz" researcher

| You want to… | Say something like… | Protocol |
|---|---|---|
| Build a figure deck from a results table | "build me figures from this CSV" | `visualization/visualization_workflow` |
| Polish a single figure | "polish my figure" | `visualization/visualization_workflow` |
| Critique a figure | "critique this figure" | `visualization/figure_critique` |
| Compose Figure 2 = panels A / B / C / D | "make figure 2 with panels" | `visualization/multi_panel_composition` |
| Order figures across a paper / talk / poster | "order my figures" | `visualization/figure_narrative_arc` |
| Color-blind + WCAG accessibility check | "check colour accessibility" | `visualization/color_accessibility_audit` |
| Just learn the figure conventions | "what's the figure style guide" | `visualization/figure_guidelines` |

### The "no project yet, just thinking" researcher

| You want to… | Say something like… | Protocol |
|---|---|---|
| Learn / compare methods before committing | "teach me about propensity scores" | `methodology/methodological_consultation` |
| Compare candidate papers in your area | "compare these foundational papers" | `literature/comparative_paper_review` |
| Power-justify an upcoming study | "how many subjects do I need" | `methodology/power_analysis` |
| Pre-register before data lands | "freeze the analysis plan" | `methodology/preregistration` |
| Choose a study design | "design the study" | `domain/research_design` |
| You don't know yet what to ask | "help me figure out where to start" | `guidance/scope_clarification` |

### The "this spans more than one field" researcher

| You want to… | Say something like… | Protocol |
|---|---|---|
| Pick which subfield drives the analysis | "this spans two fields — which goes first" | `guidance/scope_clarification` |
| Build the canonical pipeline for each subfield | "best-practice pipeline for X" | `methodology/deep_domain_research` |
| Pick a method that works across the subfield boundary | "which method fits both subfields" | `methodology/methodology_selection` (after `deep_domain_research` per side) |

---

## By depth of analysis

| Depth | When | Protocol |
|---|---|---|
| 5-minute napkin | "just poke at this", "sanity check" | `guidance/casual_exploration` |
| 30-minute appraisal | "review this paper" | `guidance/quick_paper_review` |
| Real EDA, hypothesis generation | "explore the data, find a hypothesis" | `methodology/exploratory_data_analysis` |
| Full per-step pipeline | "run the next experiment" | `guidance/analysis_plan` |
| Multi-method benchmark | "head-to-head comparison" | `methodology/method_comparison` |
| Subfield-grounded pipeline | "best-practice pipeline for X" | `methodology/deep_domain_research` |
| Full systematic synthesis | "systematic review on Y" | `literature/systematic_review` |
| Publication-grade synthesis | "draft the paper" | `synthesis/synthesis_paper` |

---

## By output type

| Want this output | Protocol |
|---|---|
| Polished single figure | `visualization/visualization_workflow` |
| Figure deck | `visualization/visualization_workflow` |
| Multi-panel figure (A / B / C / D) | `visualization/multi_panel_composition` |
| Figure ordering brief (across paper / talk) | `visualization/figure_narrative_arc` |
| Color accessibility audit report | `visualization/color_accessibility_audit` |
| Paper (IMRAD) | `synthesis/synthesis_paper` |
| Title (workshopped) | `synthesis/synthesis_title_workshop` |
| Discussion section | `writing/writing_discussion` |
| Results section | `writing/writing_results` |
| Limitations section | `writing/writing_limitations` |
| End matter (data / code / CRediT / etc.) | `writing/writing_data_availability` |
| Cover letter | `synthesis/synthesis_cover_letter` |
| Pre-submission checklist + verdict | `audit/pre_submission_checklist` |
| Abstract | `synthesis/synthesis_abstract` |
| Poster | `synthesis/synthesis_poster` |
| Dashboard (offline HTML) | `synthesis/synthesis_dashboard` |
| Slides (lab / conference / defense / etc.) | `synthesis/synthesis_slides` |
| Internal / technical report | `synthesis/synthesis_report` |
| Grant narrative | `synthesis/synthesis_grant` |
| Lay summary / press release / blog | `synthesis/synthesis_lay_summary` |
| PI / advisor / weekly update | `synthesis/synthesis_progress_update` |
| Printable one-pager / handout (with QR) | `synthesis/synthesis_handout` |
| Null-findings companion | `synthesis/synthesis_null_findings` |
| Critique brief (single paper) | `guidance/quick_paper_review` |
| Critique brief (single figure) | `visualization/figure_critique` |
| Comparative review brief (N papers) | `literature/comparative_paper_review` |
| Reproduction report | `methodology/reproduction_attempt` |
| Power justification paragraph | `methodology/power_analysis` |
| Evaluation protocol document | `methodology/evaluation_design` |
| Sweep design document | `methodology/hyperparameter_search_design` |
| Data ethics review document | `methodology/data_ethics_review` |
| Data-quality audit report | `methodology/data_quality_audit` |
| Methodological consultation notes (optional) | `methodology/methodological_consultation` |
| Per-step literature grounding (`findings_vs_literature.md`) | `literature/literature_per_step` *(v1.4.0)* |
| Language / tool-stack decision (R vs Python per sub-task) | `methodology/pick_tool_stack` *(v1.4.0)* |
| Mixed-language step (Python ↔ R ↔ Bash composition) | `methodology/mixed_language_orchestration` *(v1.4.0)* |

---

## End-to-end recipes (the protocol stack for a complete deliverable)

`tool_route` picks ONE protocol per researcher message. A full project
is many protocols composed in a pipeline. The recipes below show the
canonical compositions — the AI walks them automatically when each
protocol's `next_protocol` advances forward.

| If your project is… | The pipeline | Final deliverable |
|---|---|---|
| **Qualitative interview / focus-group study** | `guidance/project_startup` → `methodology/qualitative_research` → `methodology/coding_scheme_development` → `methodology/qualitative_quality_audit` → `audit/audit_and_validation` → `synthesis/synthesis_paper` → `synthesis/synthesis_dashboard` *(optional)* | `synthesis/paper.md` (+ `synthesis/dashboard.html`) |
| **Quantitative ML benchmark** | `guidance/project_startup` → `methodology/methodology_selection` → `methodology/evaluation_design` → `methodology/method_comparison` → `audit/audit_and_validation` → `synthesis/synthesis_paper` | `synthesis/paper.md` |
| **Theory / math proof** | `guidance/project_startup` → `theory_math/method/proof_strategy_selection` → `theory_math/proof/proof_verification_workflow` → `theory_math/output/theory_paper_structure` → `synthesis/synthesis_paper` (citation_style: amsplain) | `synthesis/paper.md` (Theorem / Proof / References) |
| **Close-reading humanities essay** | `guidance/project_startup` → `humanities/method/close_reading` → `synthesis/synthesis_paper` (citation_style: mla or chicago_author_date) | `synthesis/paper.md` |
| **Visualization-only deliverable** | `visualization/visualization_workflow` *(no full project pipeline)* | One figure or figure deck |

When the wrong recipe gets picked, say *"actually I meant <X>"* and the
AI re-routes without losing the workspace.

---

## What's new in v1.4.0

- **Per-step literature loop** — after every analysis step writes
  `## Findings` in `conclusions.md`, the AI now searches Semantic
  Scholar / PubMed / Crossref per claim, downloads top PDFs into
  `workspace/<step>/literature/`, and writes
  `findings_vs_literature.md` with a `## Claim:` block per finding
  (AGREES | DISAGREES | EXTENDS | DEFERRED + Evidence +
  Discussion implication). `tool_audit_step_literature` BLOCKS
  `tool_path_finalize` if missing or DISAGREES has no discussion.
  Trigger: *"ground this step"*, *"compare to literature"*, *"is
  this novel"*, or invoked automatically from
  `analysis_plan.ground_findings_in_literature`.
- **Language + tool-stack doctrine** — RO no longer defaults to
  Python out of habit. `pick_tool_stack` enumerates language
  candidates per sub-task, queries field practice (R Bioconductor
  for bulk DE, Python scanpy for scRNA-seq, R survival for Cox PH,
  WGCNA → R, geopandas → Python, …), and persists the choice + the
  citation that grounds it to
  `workspace/<step>/scratch/stack_plan.md`. Audit warns when this
  artefact is missing.
- **Mixed-language steps** — Python ↔ R ↔ Bash composition is now a
  first-class protocol (`mixed_language_orchestration`) with
  hand-off file contracts, serialization matrix (TSV / Parquet /
  .mtx / RDS — never cross-language pickle), per-language
  `pipeline.yaml` tags, and schema assertions at consumer entry.
- **Summary fill-rate fix** — `tool_figure_caption_synthesise` now
  pulls a "Why it matters" sentence from prose `## Findings`
  sections (no longer requires bullets); missing `.summary.md`
  sidecars now BLOCK at audit (were WARN).
- **9 grounding tools wired into protocols** — `thought_log`,
  `thought_trace`, `grounding_register`, `ground_from_context`,
  `claim_verify`, `grounding_verify`, `lessons_record`,
  `lessons_consult`, `plan_step_grounded` were orphan in v1.3.x;
  now invoked from `project_startup`, `analysis_plan`,
  `literature_per_step`, `writing_core`, and
  `pre_submission_checklist`.

See [CHANGELOG.md](../CHANGELOG.md) `[1.4.0]` for the full diff.

---

## You don't have to choose

`tool_route` picks the right protocol from a plain-English prompt. The
table above exists so you can see what's available and confirm the AI's
choice. If the wrong protocol gets picked, just say "actually I meant
X" — the AI re-routes without re-loading the workspace.

When you genuinely don't know what you want, say so:
> "I have some data and some ideas — help me figure out where to start."

The AI loads `guidance/scope_clarification`, classifies the ambiguity
(unclear intent / unformed intent / cross-disciplinary / wrong
entrypoint / too broad), asks ONE narrowing question, and re-routes on
your answer. The router treats ambiguity as a 1-sentence follow-up
cost, not as a wrong guess.

When the project genuinely spans two subfields (e.g. imaging + RNA-seq,
surveys + behavioural logs), the AI runs `methodology/deep_domain_research`
once per subfield and holds both pipelines side-by-side rather than
force-fitting into one.
