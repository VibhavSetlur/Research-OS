# Use Cases — "I want to X" → what to say → what fires

You don't memorize protocols. You say what you want in plain English;
`tool_route` maps your message to the right protocol, and your
**workspace mode** shapes how it runs. This page exists so you can see
what's possible and confirm the AI's choice.

> **Want a real project instead of a lookup table?**
> [SCENARIOS.md](SCENARIOS.md) walks two worked projects end to end — a basic
> one (one dataset → a grounded result) and a deep PI-level program touching
> every capability (onboarding, iterative planning, branching, synthesis
> meetings, a live dashboard, Docker runs, provenance, sharing/handoff) — with
> the exact prompts and what lands on disk.

---

## Real research goals (start here)

These are the goals researchers actually arrive with. Find yours, say the
prompt, and let the AI work. Each routes cleanly.

### "I want to write a paper from my data."

**Say:** *"My data's in `inputs/raw_data/` and I want to test whether
\<hypothesis\>. Onboard me, then take it through to a journal paper."*

**What fires:** onboarding (`session_boot` → `project_startup`) →
`guidance/analysis_plan` per experiment step → `audit/audit_and_validation`
→ `synthesis/synthesis_paper`. **Mode:** analysis.
**You get:** numbered steps under `workspace/NN_*` with grounded figures
and conclusions, then a content-grounded paper **structure** assembled
from *your* results — an outline tailored to your audience and venue that
you render, not a fixed template filled in. Every number traces back to a
step; every citation is verified.

### "I want to build a dashboard."

**Say:** *"build a dashboard for executives from my results."*

**What fires:** `synthesis/synthesis_dashboard`. **Mode:** analysis.
**You get:** a dashboard **structure** — sections, the figures and tables
to feature, the narrative order — grounded in your computed results and
tuned to the audience (`audience: academic | executive | technical |
teaching`). Research OS assembles the structure for you to render; it
doesn't hand you a fixed HTML palette.

### "I want to reproduce a published result."

**Say:** *"reproduce this paper"* (drop the PDF in `inputs/literature/`).

**What fires:** `methodology/reproduction_attempt`. **Mode:** analysis
(or exploration if you're just probing). **You get:** a reproduction
report — what matched, what didn't, and where the discrepancy lives —
with every comparison grounded in re-run computation, not eyeballing.

### "I want to run a long Docker job and walk away."

**Say (in the terminal):**

```bash
research-os daemon setup            # once
research-os daemon start
research-os daemon docker myimg:1.0 --gpus all -- python train.py
research-os daemon runs             # check history later
research-os daemon logs <run_id>    # manifest + output
```

**What fires:** the **per-project daemon**, not an inline tool. The run
is journaled and provenanced; the exact image digest is recorded so it
reproduces bit-for-bit; the project root is mounted so outputs land back
in the workspace. It survives the IDE closing and rehydrates after a
reboot. On a shared box set `runtime.shared_server: true` so the AI asks
before allocating heavy resources. (For SLURM: `research-os daemon submit
job.sbatch`.)

### "I want to hand this off to a collaborator."

**Say:** *"package this project for handoff to a collaborator."*

**What fires:** `guidance/collaboration_handoff`. **Mode:** any.
**You get:** a self-contained package — data provenance, the decision
trail, what's done and what's pending — so a new person (or a fresh chat)
can pick it up. To wrap a working session instead, say *"hand off the
session"* (`guidance/chat_handoff`); to resume, *"pick up where we left
off"* (`guidance/session_resume`).

### "I want to build a pipeline tool, not analyze data."

**Say (init in the right mode first):**

```bash
research-os init . --workspace-mode tool_build
```

then *"spec out a fast FASTQ deduplicator — it must handle paired-end
reads and beat `seqkit rmdup` on 10 GB inputs"*, then *"implement the
parser"*, then *"benchmark it against seqkit."*

**What fires:** `build/spec_and_design` → `build/implement_iteration`
(loop) → `build/test_strategy` → `build/benchmark_vs_baseline` →
`build/release_and_changelog`. **Mode:** tool_build. **You get:** a
tested, benchmarked tool in its own inner git repo with a governance
surface (`spec/`, `decisions/`, `eval/`). "Done" is a passing eval +
green tests + a clean build, not a figure. Full walkthrough:
[TOOL_BUILDER.md](TOOL_BUILDER.md).

---

## Common first prompts

The highest-leverage first-turn prompts, validated against end-to-end
scenarios. Pick the row matching what you have on disk.

| What you arrived with | First prompt | Routes to |
|---|---|---|
| Data + a specific hypothesis | "I dropped \<dataset\> in inputs/ — test whether \<hypothesis\>." | `guidance/project_startup` → `tool_intake_autofill` |
| Data, no hypothesis yet | "I have \<dataset\> in inputs/ — explore it and help me find a hypothesis." | `methodology/exploratory_data_analysis` |
| Brand-new, just want to look | "i have a csv, what do i do?" / "look at my data" / "make a chart" | the router coaches from plain phrasing |
| Building a tool (tool_build mode) | "spec out \<the tool\>, here's what it must do." / "implement the next feature." | `build/spec_and_design` → `build/implement_iteration` |
| Quick scratch poke (exploration mode) | "just poke at this data, nothing formal." | `guidance/casual_exploration` |
| A text corpus (humanities) | "I have \<N\> texts in inputs/raw_data/ — test whether \<stylistic claim\>." | `humanities/method/digital_humanities_workflow` |
| Interview transcripts | "I have \<N\> transcripts in inputs/raw_data/ — walk this to a paper + dashboard." | `methodology/qualitative_research` → `coding_scheme_development` → `qualitative_quality_audit` |
| Benchmark / engineering measurements | "Benchmark A vs B vs C across input sizes; quantify when A wins." | `methodology/method_comparison` |
| A theorem to prove | "I have a conjecture: \<statement\>. Help me prove it and write it up." | `theory_math/proof/proof_verification_workflow` |
| A draft + some data already going | "I'm bringing this into Research-OS; we've worked on it for months." | `guidance/mid_pipeline_entry` |
| Not sure yet | "I have some data and ideas — help me figure out where to start." | `guidance/scope_clarification` |

A few routing facts the validation surfaced:

- **You don't have to phrase it like the table.** `tool_route` does
  semantic matching first, then a hierarchical L1 → L2 → L3 trigger
  picker. "head-to-head", "bake-off", "horse race" all hit
  `method_comparison`; "prove this", "proof verification" hit theory_math.
- **Wrong protocol? Say "actually I meant X."** It re-routes without
  reloading the workspace.
- **No data yet? Say so.** *"Teach me about \<method\> before I use it"*
  loads `methodology/methodological_consultation` and commits you to
  nothing.

---

## By workspace mode

The first fork is *what kind of project this is*, set at `research-os
init .` (`--workspace-mode`, or the wizard) and stored as
`workspace.mode` in `inputs/researcher_config.yaml`.

| You're… | Mode | Say something like… | Routes to |
|---|---|---|---|
| Analyzing data toward a finding / paper | **analysis** *(default)* | "fill the intake", "run an EDA", "draft the paper" | the analysis protocols below |
| Building software you iterate on | **tool_build** | "spec out a fast deduplicator", "implement the next feature", "benchmark vs baseline", "cut a release" | `build/spec_and_design` · `build/implement_iteration` · `build/test_strategy` · `build/benchmark_vs_baseline` · `build/release_and_changelog` |
| Poking around, no committed direction | **exploration** | "just poke at this", "smoke-test an idea in scratch" | `guidance/casual_exploration` (promote a probe to a numbered step only when it earns it) |
| Working notebook-first | **notebook** | "open a notebook and explore X", "turn this notebook into a step" | `notebook/notebook_workflow` |
| Building a tool AND using it on data | **hybrid** | "build the parser, then run it on my data and improve it" | `hybrid/hybrid_workflow` · `hybrid/tool_to_analysis_handoff` |
| Running a program (several sub-studies) | **multi_study** | "set up a program with three studies sharing a codebook" | `program/program_setup` · `program/study_register` · `program/cross_study_synthesis` |

---

## By role

### Graduate student / postdoc running their own analyses

| You want to… | Say… | Protocol |
|---|---|---|
| Set up from data + papers | "fill the intake" | `guidance/project_startup` |
| Run the next experiment | "run an EDA", "fit a logistic regression" | `guidance/analysis_plan` |
| Decide what's next | "what should I do next" | `guidance/iterative_planning` |
| Generate hypotheses from data | "do real EDA — no hypothesis yet" | `methodology/exploratory_data_analysis` |
| Compare two methods head-to-head | "benchmark RF vs XGB" | `methodology/method_comparison` |
| Design the eval (split + CV + metrics) | "design the evaluation strategy" | `methodology/evaluation_design` |
| Write the paper | "draft the manuscript for a journal" | `synthesis/synthesis_paper` |
| Pre-submission final check | "is this ready to submit" | `audit/pre_submission_checklist` |
| Make a poster / dashboard | "make a conference poster" / "build a dashboard" | `synthesis/synthesis_poster` · `synthesis/synthesis_dashboard` |
| Wrap up / resume | "wrap up" / "pick up where we left off" | `guidance/chat_handoff` · `guidance/session_resume` |

### Principal investigator / lab leader

| You want to… | Say… | Protocol |
|---|---|---|
| Review a draft for journal club | "review this paper" | `guidance/quick_paper_review` |
| Compare 3–5 related papers | "journal club on these" | `literature/comparative_paper_review` |
| Weekly meeting update | "weekly update" | `synthesis/synthesis_progress_update` |
| Draft an NIH R01 | "draft an R01 grant" | `synthesis/synthesis_grant` |
| Vet a collaborator's script | "review this code" | `guidance/code_review` |
| Respond to peer review | "draft a rebuttal" | `guidance/peer_review_response` |
| Package a project for a new lab | "package for handoff" | `guidance/collaboration_handoff` |

### Methodologist / statistical consultant

| You want to… | Say… | Protocol |
|---|---|---|
| Teach a method | "explain mixed-effects models" | `methodology/methodological_consultation` |
| Justify a power calc | "power analysis", "sample size" | `methodology/power_analysis` |
| Audit a dataset | "data quality audit" | `methodology/data_quality_audit` |
| Pick a method | "which method should I use" | `methodology/methodology_selection` |
| Build the canonical pipeline for a subfield | "best-practice pipeline for snRNA-seq" | `methodology/deep_domain_research` |
| Pre-register the analysis plan | "freeze the analysis plan" | `methodology/preregistration` |
| Run a simulation study (ADEMP) | "run a simulation study" | `methodology/simulation_studies` |

### Reviewer / journal-club host

| You want to… | Say… | Protocol |
|---|---|---|
| Quick critique of a paper | "tear apart this paper" | `guidance/quick_paper_review` |
| Compare 3–5 papers | "journal club on these" | `literature/comparative_paper_review` |
| Critique a single figure | "critique Figure 2" | `visualization/figure_critique` |
| Reproduce a published analysis | "reproduce this paper" | `methodology/reproduction_attempt` |
| Full systematic review (PRISMA) | "systematic review of X" | `literature/systematic_review` |
| Grade a body of evidence (GRADE) | "grade the evidence on X" | `literature/evidence_synthesis` |

### Communicator / outreach

| You want to… | Say… | Protocol |
|---|---|---|
| Press release on a finding | "press release" | `synthesis/synthesis_lay_summary` (press_release) |
| Patient-facing blurb | "patient newsletter explainer" | `synthesis/synthesis_lay_summary` (patient_or_participant) |
| Social thread | "twitter thread on this paper" | `synthesis/synthesis_lay_summary` (social_thread) |
| Lab blog post | "blog post about the project" | `synthesis/synthesis_lay_summary` (blog_post) |

### Presenter / talk-giver

| You want to… | Say… | Protocol |
|---|---|---|
| Lab meeting slides | "lab meeting deck" | `synthesis/synthesis_slides` (lab_meeting) |
| 12-min conference talk | "conference slides, 12 min" | `synthesis/synthesis_slides` (conference_talk_short) |
| Defense talk | "defense slides" | `synthesis/synthesis_slides` (defense) |
| Conference poster | "make a poster" | `synthesis/synthesis_poster` |

### Theorist / mathematician (theory_math pack)

Activate by saying "prove this", "I have a conjecture", "draft a proof",
or by dropping a `.lean` / `.v` / `.tex` draft into `inputs/raw_data/`.
The pack also reads `inputs/preliminaries.md` (definitions + lemmas your
proofs assume — a hard prerequisite for strategy selection).

| You want to… | Say… | Protocol |
|---|---|---|
| Register an open problem | "log this conjecture" | `theory_math/conjecture/conjecture_tracking` |
| Choose a proof strategy | "which proof strategy fits this claim" | `theory_math/method/proof_strategy_selection` |
| Statement → verified proof | "prove this claim end-to-end" | `theory_math/proof/proof_verification_workflow` |
| Formalize in Lean 4 / Coq | "formalise this in Lean" / "…in Coq" | `theory_math/formal/lean_integration` · `coq_integration` |
| Compile the theory paper | "compile the theory paper" | `theory_math/output/theory_paper_structure` |

### Starting in the middle / just want a viz

| You want to… | Say… | Protocol |
|---|---|---|
| Plug an in-progress project into RO | "bringing this into Research-OS" | `guidance/mid_pipeline_entry` |
| Synthesize from results computed elsewhere | "we already analysed this, just write it up" | `synthesis/synthesis_from_inputs` |
| Build a figure deck from a results table | "build me figures from this CSV" | `visualization/visualization_workflow` |
| Multi-panel figure (A/B/C/D) | "make figure 2 with panels" | `visualization/multi_panel_composition` |
| Critique a figure | "critique this figure" | `visualization/figure_critique` |
| Color-blind / WCAG check | "check colour accessibility" | `visualization/color_accessibility_audit` |

### No project yet, just thinking

| You want to… | Say… | Protocol |
|---|---|---|
| Learn / compare methods | "teach me about propensity scores" | `methodology/methodological_consultation` |
| Power-justify an upcoming study | "how many subjects do I need" | `methodology/power_analysis` |
| Pre-register before data lands | "freeze the analysis plan" | `methodology/preregistration` |
| Choose a study design | "design the study" | `domain/research_design` |
| Don't know what to ask | "help me figure out where to start" | `guidance/scope_clarification` |

---

## By output type

| Want this output | Protocol |
|---|---|
| Polished figure / figure deck | `visualization/visualization_workflow` |
| Multi-panel figure (A/B/C/D) | `visualization/multi_panel_composition` |
| Paper (IMRAD) | `synthesis/synthesis_paper` |
| Discussion / Results / Limitations section | `writing/writing_discussion` · `writing/writing_results` · `writing/writing_limitations` |
| Cover letter | `synthesis/synthesis_cover_letter` |
| Pre-submission checklist + verdict | `audit/pre_submission_checklist` |
| Abstract | `synthesis/synthesis_abstract` |
| Poster | `synthesis/synthesis_poster` |
| Dashboard | `synthesis/synthesis_dashboard` |
| Slides (lab / conference / defense) | `synthesis/synthesis_slides` |
| Internal / technical report | `synthesis/synthesis_report` |
| Grant narrative | `synthesis/synthesis_grant` |
| Lay summary / press release / blog | `synthesis/synthesis_lay_summary` |
| PI / weekly update | `synthesis/synthesis_progress_update` |
| One-pager / handout (with QR) | `synthesis/synthesis_handout` |
| Reproduction report | `methodology/reproduction_attempt` |
| Power justification paragraph | `methodology/power_analysis` |
| Evaluation protocol document | `methodology/evaluation_design` |
| Data-quality audit report | `methodology/data_quality_audit` |

> **What "output" means here.** Research OS provides **structure**, not a
> fixed template. A synthesis protocol assembles a content-grounded
> *outline* — the right sections, the figures and numbers to feature, the
> narrative order — tailored to your audience and venue, for you to
> render. It does not hand you a canned `.typ`/`.html` palette to fill in.

---

## End-to-end recipes (the protocol stack for a complete deliverable)

`tool_route` picks ONE protocol per message. A full project is many
protocols composed — the AI walks them automatically as each protocol's
`next_protocol` advances.

| If your project is… | The pipeline | Final deliverable |
|---|---|---|
| **Qualitative interview study** | `project_startup` → `qualitative_research` → `coding_scheme_development` → `qualitative_quality_audit` → `audit_and_validation` → `synthesis_paper` (+ `synthesis_dashboard`) | Paper structure (+ dashboard structure) |
| **Quantitative ML benchmark** | `project_startup` → `methodology_selection` → `evaluation_design` → `method_comparison` → `audit_and_validation` → `synthesis_paper` | Paper structure |
| **Theory / math proof** | `project_startup` → `proof_strategy_selection` → `proof_verification_workflow` → `theory_paper_structure` → `synthesis_paper` | Theory paper structure (Theorem / Proof / References) |
| **Building a tool (tool_build)** | `spec_and_design` → `implement_iteration` (loop) → `test_strategy` → `benchmark_vs_baseline` → `release_and_changelog` | A tested, benchmarked tool in its own git repo |

When the wrong recipe gets picked, say *"actually I meant \<X\>"* and the
AI re-routes without losing the workspace.

---

## Deep scenarios (the whole machine, including the daemon)

The recipes above are protocol stacks. The scenarios below are
*narratives* of messy, real research with the daemon running — long jobs,
walking away, autonomy, mode changes. The daemon is OPTIONAL: with none
running, everything still works over stdio; the daemon adds durable
execution, recovery, enforcement, and notifications. Start one with
`research-os daemon start`.

### Scenario 1 — overnight run on a shared cluster, then walk away

A postdoc on a shared box has a 9-hour sweep.

1. *"my data's at /scratch/me/cohort.parquet — set up an analysis project
   and plan a hyperparameter sweep"* → the AI inits, symlinks the 80 GB
   data into `inputs/raw_data/` (recording path + hash and flagging the
   project not-self-contained rather than copying), onboards, and plans
   step `01_sweep`.
2. Because `runtime.shared_server: true`, the AI **asks** before
   launching — the sweep wants ~40 GB and 9 h. The researcher approves.
3. The job runs through the **daemon** (`research-os daemon run` /
   `daemon docker`), not inline, so it survives the IDE closing. The
   daemon journals it, applies the resource budget, and the researcher
   goes home.
4. The login node reboots overnight. The daemon **rehydrates**: the run
   is marked `interrupted`, and `sys_boot` next morning leads with
   *"1 run was interrupted — resume it."*
5. When the sweep finishes, the daemon **notifies** and (if configured)
   re-prompts the AI to score the result and plan `02_analysis`.

### Scenario 2 — exploration that earns its way into a real analysis

1. *"set up an exploration project — poke at whether dosage tracks
   outcome before I commit"* → inits in **exploration** mode.
2. Three probes later, one holds up. The AI: *"this looks real — we can
   promote to analysis mode."*
3. *"yes, switch to analysis"* → the AI **plans** the numbered-step
   surface, then on confirm **applies it additively** — scratch probes
   preserved, the earned probe promoted into step `01`.

### Scenario 3 — plan deeply, then let the AI run toward the goal

1. *"plan this deeply, then run it toward the goal on your own; nothing
   destructive autonomously, cap any run at 16 GB"* → the AI walks
   `methodology/deep_planning` to write a branchable roadmap in
   `inputs/research_plan.md`.
2. On approval, it hands off to `guidance/roadmap_execution`: pick the
   next milestone → execute → score it → record evidence → re-plan →
   continue. Quality is enforced by per-milestone judging + audit gates.
3. If the agent is **Hermes Agent**, it orchestrates the loop, pulls
   relevant skills each cycle, and notifies the researcher at decision
   points or if a run would exceed the 16 GB cap.

---

## You don't have to choose

`tool_route` picks the right protocol from a plain-English prompt. When
you genuinely don't know what you want, say so:

> "I have some data and some ideas — help me figure out where to start."

The AI loads `guidance/scope_clarification`, classifies the ambiguity,
asks ONE narrowing question, and re-routes on your answer. When a project
spans two subfields, the AI runs `methodology/deep_domain_research` once
per subfield and holds both pipelines side-by-side rather than
force-fitting one.

For the full feature history, see [CHANGELOG.md](../CHANGELOG.md).
