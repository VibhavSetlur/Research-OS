# Researcher Guide — using Research OS day-to-day

A non-technical walkthrough of the typical research workflow. Assumes
[QUICKSTART.md](QUICKSTART.md) is done (you've installed, scaffolded, and
your IDE is connected).

---

## The mental model

```
You — drop files, talk to the AI, approve or redirect.
AI in your IDE — plans, reasons, writes scripts, drafts text.
Research OS — executes, records, enforces rules, prevents mistakes.
```

You never call MCP tools directly. You just talk. The AI translates your
intent into the right tool calls, following protocols that Research OS
loads on demand.

---

## Where files go

```
my-project/
├── inputs/raw_data/         ← drop your data here (CSVs, parquet, FASTQs, ...)
├── inputs/literature/       ← drop PDFs here
├── inputs/context/          ← drop notes, drafts, prior reports, anything text
├── docs/                    ← human-readable: research question, glossary, design
├── workspace/               ← AI lives here (experiments, methods, analysis logs)
│   ├── 01_baseline_eda/     ← numbered experiment steps
│   ├── 02_data_preparation/
│   ├── scratch/             ← AI sandbox (gitignored)
│   ├── methods.md           ← every method used, appended
│   ├── analysis.md          ← chronological narrative
│   └── citations.md         ← bibliography
└── synthesis/               ← final outputs (only created when you ask)
    ├── paper.md / .tex / .pdf
    ├── abstract.md
    ├── poster.pdf
    ├── dashboard.html
    └── references.bib
```

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`. Nothing in
`inputs/raw_data/` or `inputs/literature/` is ever modified — Research OS
blocks writes at the server level.

---

## A typical session

### 1. First time (set up the project)

> **You:** I dropped my CSV and a couple of papers in inputs/. Fill out the intake.

The AI calls `tool_intake_autofill`, reads everything, proposes a research
question + domain + hypotheses, and shows you what it inferred. You approve
or refine.

### 2. Start analysing

> **You:** OK, run a baseline EDA on the data.

The AI loads the `guidance/analysis_plan` protocol, creates
`workspace/01_baseline_eda/`, writes an atomic Python (or R / Julia)
script, runs it, drops the output figures + report into the experiment
folder, and writes conclusions.

### 3. Course-correct mid-flow

> **You:** Actually, group by quarter instead of month.

The AI bumps the script to `_v2`, re-runs, updates conclusions. Old
versions stay on disk for provenance.

### 4. Branch into a parallel approach

> **You:** Try a tree-based model too, in parallel to the logistic regression.

The AI calls `tool_branch_recommendation` (decides: branch since we have
< 3 active paths), runs `sys_path_create`, sets up
`workspace/03_random_forest/`, executes, compares results across the two
paths.

### 5. Mid-flow context (a new paper or dataset appears)

> **You:** My PI sent me a new paper, here it is.
> *(drag-drop or paste the PDF into `inputs/literature/` or anywhere in the project)*
> Integrate it.

The AI calls `tool_context_intake also_autofill=true`. The new paper is
auto-routed to `inputs/literature/`, the bibliography is updated, the
research question / hypotheses are revisited if the new paper warrants it,
and `analysis.md` is annotated with the integration.

### 6. Decide what's next

> **You:** What should I do next?

The AI loads `guidance/iterative_planning`. It surveys state, pulls fresh
literature on your open question, searches the web for relevant tools, and
proposes 2-3 concrete options with a recommendation.

### 7. Synthesise

> **You:** Write the paper for a journal submission.

The AI loads `synthesis/synthesis_paper`, picks the `journal` venue profile
(structured abstract, ~4000 words, ≤40 citations, ≥1 figure), drafts each
section (methods → results → discussion → introduction → abstract), audits
citations, and writes `synthesis/paper.md` plus `synthesis/references.bib`.

If you want a poster too:

> **You:** Also make a poster for an academic conference.

The AI loads `synthesis/synthesis_poster`, picks the `academic_conference`
audience (36×48 portrait, 5-block tikzposter), curates 2-4 publication-grade
figures, builds `synthesis/poster.pdf`.

### 8. Hand off the project at end-of-day

> **You:** Wrap up the session.

The AI calls `sys_session_handoff` — writes a markdown summary with state +
recent analysis + a resume prompt you can paste into a fresh chat next time.

---

## The autonomy slider

Set in `inputs/researcher_config.yaml`:

| Mode | What the AI does without asking | Best for |
|---|---|---|
| `manual` | nothing — asks before every tool call | learning, watching the AI work, debugging |
| `supervised` (default) | reads + searches autonomously; asks before creating experiments, writing to `synthesis/`, running long jobs | day-to-day research |
| `autopilot` | runs end-to-end; asks only before final synthesis + very long jobs | well-scoped projects you want to leave running |

You can change this mid-session: just say "switch to autopilot" — the AI
calls `sys_config_set interaction.autonomy_level=autopilot` and adjusts.

---

## Useful prompts (just copy-paste)

### Starting a project

```
fill out the intake
look at my data
what is in my inputs folder?
i'm bringing this into research-os — we've been working on it for months
i already have results, just write it up
do real EDA — i don't have a hypothesis yet
```

### Mid-flow analysis

```
run a baseline EDA
fit a logistic regression and check assumptions
what should I do next?
benchmark random forest vs xgboost head-to-head
audit this dataset for data quality
power analysis for the upcoming RCT
freeze the analysis plan
this experiment isn't working — abandon it and try X instead
```

### Reading + understanding

```
review this paper
tear apart this paper as a tough reviewer
journal club on these three papers
explain mixed-effects models to me
teach me propensity scores before i use them
walk me through bayesian model averaging
reproduce this paper — i want the same numbers
find me papers about <topic>
do a systematic review of <topic>
```

### Visualization

```
make me a figure from this CSV
polish my figures for the talk
build a figure deck for the paper
critique this figure
remake this chart for the dashboard
```

### Writing + synthesis

```
draft the paper for a journal submission
draft an NIH R01 narrative
make a dashboard for executives
build a poster for the conference
build a slide deck for my defense
build slides for a 12-minute conference talk
write a lay summary for the public
write a press release on this finding
weekly update for my PI
status update for my advisor
write the methods section
```

### Operations

```
check reproducibility
audit my workspace for issues
fix my workspace
wrap up the session
pick up where we left off
send to a collaborator
```

For a complete role × goal × output map, see [USE_CASES.md](USE_CASES.md).

---

## What if something goes wrong?

* **AI is making bad choices** → switch autonomy to `supervised` or
  `manual`. Ask the AI to "explain the rationale" before each step.
* **Workspace looks broken** → "Run `tool_workspace_repair`." Heals
  without deleting.
* **AI seems to forget context** → "Re-run `sys_protocol_get` for the
  current protocol and confirm where you are."
* **The chat is too long** → "Hand off the session." Then paste the
  resume prompt into a fresh chat.
* **Something deleted by mistake** → `sys_checkpoint_list` shows snapshots;
  `sys_checkpoint_rollback <id>` restores. Research OS auto-snapshots at
  every protocol boundary.

---

## See also

* [QUICKSTART.md](QUICKSTART.md) — 5-minute start.
* [USE_CASES.md](USE_CASES.md) — role × goal × output map for picking the right protocol.
* [GUIDE.md](GUIDE.md) — full tool + protocol reference (technical).
* [PROTOCOLS.md](PROTOCOLS.md) — what each protocol does + when it fires.
* [TOOLS.md](TOOLS.md) — every MCP tool, with example calls.
* [FAQ.md](FAQ.md) — common questions.
