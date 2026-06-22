# Scenarios — Research OS on real projects, start to finish

Most docs tell you *what* a tool or protocol does. This one shows you
what a whole project actually feels like: a named researcher, real data
on disk, the exact words they typed, what Research OS did in response,
and what landed in `synthesis/` at the end.

None of these are toy examples. Each one is a project shape we see
constantly — a grad student with a messy CSV, a postdoc reproducing a
paper, a PI prepping a grant, an engineer benchmarking their own code, a
qualitative researcher with interview transcripts. Read the one closest
to your situation, then steal the prompts.

Conventions used below:

- **You:** is what you type into your AI chat (Claude Code, Cursor,
  Antigravity, …). Plain English. You never call MCP tools by hand.
- **Research OS:** is what the server does behind the scenes — the
  protocol it routes to, the files it writes, the gates it runs.
- File paths are real and relative to your project root.

---

## Scenario 1 — Grad student, messy CSV, no hypothesis yet

**Maya, 2nd-year PhD in ecology.** Her advisor handed her three years of
field-station sensor data — `soil_moisture.csv`, 280k rows, 14 columns,
some obviously broken sensors — and said "see if there's a paper in
here." She has no hypothesis. She's never used Research OS.

### Day 1 — get oriented without committing

```bash
cd ~/projects && research-os init drought-response --ide cursor
# wizard asks "What are you building?" → she picks analysis (default)
cp ~/Downloads/soil_moisture.csv drought-response/inputs/raw_data/
```

> **You:** I have soil_moisture.csv in inputs — 3 years of field sensor
> readings, some sensors are flaky. I don't have a hypothesis yet.
> Explore it and tell me if there's something worth chasing.

**Research OS** routes to `methodology/exploratory_data_analysis` (not
the full project pipeline — she said "no hypothesis yet"). It creates
`workspace/01_baseline_eda/`, writes an atomic profiling script, runs
it, and reports back: 4 of 22 sensors flatline after month 8 (stuck
values), strong seasonal cycle, and a suspicious step-change in two
plots in summer 2023.

> **You:** The step-change in 2023 is interesting. What could cause
> that, and is it real or an artifact?

**Research OS** stays in EDA, branches a focused look at those two plots,
checks for sensor recalibration timestamps in the metadata column, and
writes `workspace/01_baseline_eda/conclusions.md`: the step-change
aligns with a documented irrigation-system change, not a sensor fault —
a *real* effect. That's the hypothesis seed.

### Day 2 — turn the lead into a project

> **You:** OK, there's a project here: does the 2023 irrigation change
> shift the soil-moisture recovery curve after rain events? Set it up
> properly.

**Research OS** now routes to `guidance/project_startup`, calls
`tool_intake_autofill`, proposes a research question + domain + a
testable hypothesis (H1: post-2023 recovery half-life is shorter), and
writes `inputs/intake.md` + `docs/research_overview.md`. Maya tweaks the
wording and approves.

The rest of the week is `guidance/analysis_plan` steps: rain-event
detection (`02_event_detection`), recovery-curve fitting
(`03_recovery_fits`), a pre/post comparison with a proper paired test
(`04_prepost_test`). Each step is a numbered folder with its own script,
figures, and `conclusions.md`. When she says *"actually use a
mixed-effects model, sensors are nested in plots,"* the script bumps to
`_v2` and the old one stays on disk.

### End of project — the paper

> **You:** Write this up for a journal. Then make a poster for the
> department retreat.

**Research OS** walks `synthesis/synthesis_paper`: workshops the title,
drafts Methods → Results → Discussion → Limitations → Intro → Abstract,
assembles end matter (data availability, CRediT), and runs
`audit/pre_submission_checklist` for a GREEN/YELLOW/RED verdict. It
flags one YELLOW: a causal phrasing in the Discussion for an
observational design — she softens it. Then `synthesis/synthesis_poster`
builds a Typst poster PDF with a QR back to the preprint.

**What's on disk at the end:** `synthesis/paper.pdf`,
`synthesis/poster.pdf`, and a `workspace/` tree where every figure
traces back to the exact script and data slice that produced it.

---

## Scenario 2 — Postdoc reproducing a published analysis

**Daniel, computational-biology postdoc.** A high-profile paper claims a
gene-expression signature predicts treatment response. He wants to
reproduce it before building on it — partly for a journal club, partly
because the effect size looks too clean.

```bash
research-os init repro-signature --ide claude
cp ~/papers/zhang2024.pdf repro-signature/inputs/literature/
cp ~/data/GSE######_counts.tsv repro-signature/inputs/raw_data/
```

> **You:** I'm trying to reproduce Zhang 2024 (PDF in inputs/literature).
> They claim a 12-gene signature predicts response from the counts
> table I dropped in raw_data. Walk me through reproducing it.

**Research OS** routes to `methodology/reproduction_attempt`. It reads
the PDF, extracts the claimed pipeline (normalization → DE → signature
scoring → AUC), and sets up `workspace/01_normalization/` to mirror
their stated method. It logs a `mem_log(kind='decision')` every time the
paper is ambiguous about a parameter, so the "where we diverged" list
writes itself.

> **You:** Their methods don't say which normalization they used. Try
> the two most likely and see if the AUC is sensitive to it.

**Research OS** uses `tool_sensitivity(operation='define')` to set up a
small multiverse (TMM vs median-of-ratios), runs both, and reports: the
headline AUC drops from 0.91 to 0.78 under the alternative
normalization. That's the crux. The reproduction report
(`workspace/logs/` + a `synthesis/synthesis_report`) documents it
plainly: *partially reproducible; the central claim is normalization-
sensitive and the paper under-specifies the choice.*

**Why this matters:** the deliverable isn't "I got the same number." It's
a defensible reproduction report with the divergence points pinned to
evidence — exactly what a journal club or a rebuttal needs.

---

## Scenario 3 — PI prepping an R01 between meetings

**Dr. Okafor, PI.** She has a finished Research OS project from last
year (the paper's already out) and a Tuesday deadline to get an R01
draft to her program officer. She's not analyzing anything new — she's
repackaging completed work into a grant.

> **You:** pick up where we left off

**Research OS** loads `guidance/session_resume`, reads the prior state,
and summarizes the completed project in two sentences.

> **You:** Draft an NIH R01 from this project. Aim 1 is the published
> work; Aims 2-3 are the obvious extensions we discussed.

**Research OS** routes to `synthesis/synthesis_grant` (funder: nih_r01).
It enforces the structure that reviewers expect: Specific Aims ≤ 1 page,
each Aim with milestones + pitfalls + alternatives, Approach ≥ 1500
words, ≥ 15 verified citations pulled from the project's existing
bibliography (no hallucinated refs — they're verified against Crossref /
PubMed). It drafts Aim 1 from the real results and scaffolds Aims 2-3
from the decision log's "future work" entries.

> **You:** The Specific Aims page is over a page. Tighten it and add a
> lay-summary box for the program officer.

**Research OS** trims to length and routes the box through
`synthesis/synthesis_lay_summary` (audience: funder_lay_section).

**On disk:** `synthesis/grant.pdf` plus a `lay_summary.md`. Every
citation resolves. She edits the science, not the formatting.

---

## Scenario 4 — Engineer benchmarking their own tool (tool_build mode)

**Sam, research software engineer.** They're writing a FASTQ
deduplicator in Rust and need to prove it beats `seqkit rmdup` before
claiming it in a methods paper. This is **building software**, not
analyzing data — so it inits in `tool_build` mode.

```bash
research-os init fastq-dedup --workspace-mode tool_build --ide opencode
```

This seeds a different scaffold: `spec/`, `decisions/`, `eval/`,
`milestones.md`, and an inner git repo. "Done" here means tests + build
+ eval pass, not figures.

> **You:** Spec it out — it must handle paired-end reads and beat seqkit
> rmdup on a 10 GB input by at least 2x wall-clock, same dedup results.

**Research OS** routes to `build/spec_and_design`: records the
acceptance criteria (the 2x target, identical output invariant), the
interface contract, and the first ADRs in `decisions/`.

> **You:** Implement the paired-end parser.

**Research OS** routes to `build/implement_iteration`: writes the code
in the inner repo, proves it with a unit test, runs the build + lint,
and commits — all gated by `tool_build` and `tool_git`.

> **You:** Now benchmark it against seqkit on the 10 GB test file.

**Research OS** routes to `build/benchmark_vs_baseline`: runs both,
captures wall-clock + peak memory + a diff proving identical dedup
output, and writes the result into `eval/`. It reports: 2.7x faster,
output identical. The acceptance criterion passes.

> **You:** Cut a release.

**Research OS** routes to `build/release_and_changelog`: tags the inner
repo, writes the changelog entry, and confirms the eval + tests + build
are all green.

**Full walkthrough:** [TOOL_BUILDER.md](TOOL_BUILDER.md).

---

## Scenario 5 — Qualitative researcher with interview transcripts

**Priya, health-services researcher.** She has 18 semi-structured
interview transcripts about clinician burnout and needs to get from raw
transcripts to a publishable qualitative paper — with the
trustworthiness rigor reviewers in her field demand.

```bash
research-os init burnout-study --ide cursor
cp ~/interviews/*.txt burnout-study/inputs/raw_data/
cp ~/irb/interview_guide.pdf burnout-study/inputs/context/instruments/
```

> **You:** I have 18 interview transcripts in raw_data about clinician
> burnout. Walk this through to a paper plus a dashboard.

**Research OS** routes the chain: `methodology/qualitative_research`
(open + axial coding, theme synthesis) →
`methodology/coding_scheme_development` (hybrid codebook) →
`methodology/qualitative_quality_audit`. That last one is the part that
makes it publishable: it requires **saturation evidence** (not a power
calc — qualitative sample size is justified by saturation, per Guest,
Bunce & Johnson 2006), a reflexivity statement, intercoder agreement,
member-checking notes, and quote anonymization.

> **You:** Show me where saturation actually flattens.

**Research OS** produces the saturation curve from
`qualitative_quality_audit::saturation_evidence_check` — new codes per
transcript, flattening around interview 14. That's the defensible "why
18 was enough" answer.

Then `audit/audit_and_validation` → `synthesis/synthesis_paper`
(IMRAD-flavored, with anonymized quotes) →
`synthesis/synthesis_dashboard` (a story-mode offline HTML she can email
to her co-authors).

**On disk:** `synthesis/paper.pdf` and `synthesis/dashboard.html` —
single-file, opens offline, no server needed.

---

## Scenario 6 — Bringing a half-finished project into Research OS

**Lin, applied-stats researcher.** She's been working in a messy folder
for three months — scripts, figures, a half-written draft — before she
ever heard of Research OS. She does *not* want to redo the intake or
re-run everything.

```bash
research-os init . --ide claude    # init in the existing folder
# her existing files are untouched; RO scaffolds around them
```

> **You:** I'm bringing this project into Research-OS. We've been at it
> for months — there's a draft, some figures, and analysis scripts
> already. Don't make me start over.

**Research OS** routes to `guidance/mid_pipeline_entry`. Instead of
forcing the 10-stage pipeline from stage 1, it inventories what already
exists, asks where the real outputs live, and rebuilds the expected
metadata from the files already present (via `tool_workspace_repair` if
the layout is irregular).

> **You:** We already have the results. Just help me write it up
> properly and check the claims.

**Research OS** routes to `synthesis/synthesis_from_inputs` — it drafts
the paper from her existing results rather than re-deriving them, then
`audit/pre_submission_checklist` flags two ungrounded claims and one
figure missing a caption. She fixes the source; the gate goes GREEN.

**The point:** Research OS meets you where you are. The pipeline is a
default, not a toll booth.

---

## Scenario 7 — "I just need one good figure"

**Tom, MD doing a quick analysis.** He has a results CSV and a poster
session tomorrow. He does not want a project — he wants one
publication-quality figure.

```bash
research-os init quick-fig --workspace-mode exploration --ide cursor
cp ~/results.csv quick-fig/inputs/raw_data/
```

> **You:** build me a figure from results.csv — Kaplan-Meier by
> treatment arm, colour-blind safe, 300 DPI.

**Research OS** routes straight to `visualization/visualization_workflow`
— no project pipeline. It pulls a color-blind-safe palette
(`tool_figure_palette`, Okabe-Ito), writes the plotting script, renders
at 300 DPI, and drops the figure with a `.caption.md` beside it.

> **You:** Add risk tables under the curves and critique it like a
> reviewer would.

**Research OS** updates the figure, then routes
`visualization/figure_critique` for a reviewer-style pass (legibility at
poster distance, axis honesty, redundant encoding). Ten minutes, one
figure, no ceremony.

---

## How these compose

`tool_route` picks **one** protocol per message. A whole project is many
protocols chained — Research OS walks the chain automatically as each
protocol's `next_protocol` advances. The canonical end-to-end pipelines
(qualitative study, ML benchmark, theory proof, humanities essay,
tool-build) are tabulated in
[USE_CASES.md § End-to-end recipes](USE_CASES.md#end-to-end-recipes-the-protocol-stack-for-a-complete-deliverable).

If the router ever picks the wrong protocol, say *"actually I meant X"* —
it re-routes without reloading your workspace.

---

## Where to go next

- **Want the full role × goal × output map?** → [USE_CASES.md](USE_CASES.md)
- **Want the day-to-day mechanics?** → [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md)
- **Installing for the first time?** → [START.md](START.md)
- **Building a tool, not analyzing data?** → [TOOL_BUILDER.md](TOOL_BUILDER.md)
- **Stuck?** → [FAQ.md](FAQ.md)
