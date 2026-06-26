# Start here

Everything you need to be productive with Research OS — installation,
first project, copy-paste prompts. Read top to bottom (~15 minutes), or
skip to the section you need.

If you'd rather watch the AI handle install + IDE wiring for you, paste
the [Setup Prompt](#setup-prompt-paste-into-any-ai) into any AI chat.

---

## Quickstart — 4 steps

```bash
# 1. Install (once, globally — one server serves every project)
pip install research-os

# 2. Scaffold a project
mkdir my-project && cd my-project
research-os init                 # arrow-key wizard

# 3. Confirm it's healthy (optional but recommended)
research-os doctor               # python + conda env + IDE wiring + pack health
research-os ide list             # which IDEs are wired in this workspace

# 4. Open the folder in your AI IDE and talk
#    > here's my project: I want to know if X affects Y; my data's at <path>
#    > what should I do next?
```

That's everything. The rest of this guide unpacks each step and shows
you the full prompt catalogue.

---

## Your first ten minutes (a real walkthrough)

Say you've got a CSV of clinical-trial outcomes and a question. Here's the
whole arc, start to finish — the words you type are in **bold**.

1. **Scaffold and open.**

   ```bash
   mkdir aspirin-rct && cd aspirin-rct
   research-os init          # pick "analysis" mode, your IDE, defaults for the rest
   ```

   Open `aspirin-rct/` in Claude Code (or Cursor / VS Code / …). The MCP
   panel shows **`research-os` connected**.

2. **Tell it what you're doing** — no files required yet:

   > **"My trial data is at `~/data/aspirin.csv`. I want to know if
   > low-dose aspirin reduces 30-day cardiac events versus placebo,
   > adjusting for age and prior MI. Hypothesis: it does."**

   The AI records the question + hypothesis, profiles the CSV (rows,
   columns, types, missingness), flags anything odd, and asks you to
   confirm the framing. Nothing has run yet — it checks with you first.

3. **Run the baseline.**

   > **"run a baseline EDA"**

   You get `workspace/01_baseline_eda/` — a script you can read, figures
   with captions, a summary table, and `conclusions.md` tying what it
   found back to your hypothesis.

4. **Do the real analysis.**

   > **"fit the adjusted model"**

   The AI picks the method (logistic regression here), justifies it,
   writes `workspace/02_*/`, reports the effect with a CI and the
   adjusted covariates, and records the decision in `analysis.md`.

5. **Write it up.**

   > **"draft the results and discussion"**

   Prose that cites *your* numbers — every value traceable to step 02,
   every reference verified. If you ask for a citation it can't verify,
   it tells you, rather than inventing a DOI.

6. **Check before you ship.**

   > **"is this ready to submit?"**

   A GREEN / YELLOW / RED verdict and a punch list: ungrounded claims,
   missing limitations, unverified cites — every gate a reviewer applies,
   run early.

You never wrote a config file, memorized a command, or trusted a number on
faith. That's the loop. → Seven fuller examples across domains:
[SCENARIOS.md](SCENARIOS.md).

---

## Install (60 s)

```bash
pip install research-os
```

Extras: `all` (everything Python — recommended), `ci` (lean, used by
CI), or a subset of `web` / `literature` / `viz` / `audit` / `ml` /
`notebook`.

**Research OS is global.** Install once; the same `research-os`
binary serves every project you scaffold.

Verify:

```bash
research-os --help
# Eleven commands: init / ide / mcp / hermes / route / api-key / start / daemon / doctor / refresh / completion
```

If `research-os: command not found`, add `~/.local/bin` (or your
virtualenv's `bin/`) to your `PATH`.

Need help with Python / pip / virtualenvs / conda? See
[SETUP.md](SETUP.md).

---

## Scaffold your first project (15 s)

```bash
mkdir my-project && cd my-project
research-os init                 # interactive arrow-key wizard (default)
# research-os init --yes         # non-interactive (CI / scripts)
```

`init` is the only per-project command. The wizard's first question —
**"What are you building?"** — sets the *workspace mode* (see
[Pick a workspace mode](#pick-a-workspace-mode) below). It then collects:
location, project name, optional domain + research question, which AI
IDEs to wire up, and whether to run a post-scaffold smoke check. Pass any
of `--workspace-mode / --name / --domain / --question / --ide` to
pre-fill an answer and the wizard will skip that step. It drops:

- `AGENTS.md` — the AI's operating manual (every supported IDE reads it)
- `inputs/{raw_data, literature, context}/` — where YOU drop files
- `workspace/`, `synthesis/`, `docs/`, `.os_state/` — AI workspace + outputs
- Pre-wired MCP configs for **Claude Code, OpenCode, Antigravity, Cursor,
  Claude Desktop, VS Code, Windsurf, Continue, Aider**

You typically need to **restart your IDE** so it picks up the new MCP config.

---

## Pick a workspace mode

The very first wizard question — *"What are you building?"* — sets a
**workspace mode** that shapes the scaffold and how the AI works. Most
people want the default. The three options:

| Pick this if you're… | Mode | What changes |
|---|---|---|
| Turning data into results + a write-up | **analysis** *(default)* | Numbered experiment steps under `workspace/NN_*`; "done" = grounded figures + conclusions. |
| Building / iterating on software (a CLI, library, service) | **tool_build** | Governance layer (`spec/`, `decisions/`, `eval/`) above an inner git repo; "done" = tests + build + eval pass. → [TOOL_BUILDER.md](TOOL_BUILDER.md) |
| Just poking around with no committed direction | **exploration** | Scratch-first (`workspace/scratch/`), light gates; promote a probe to a real step only when it earns it. |

Set it without the wizard via `research-os init --workspace-mode <mode>`,
or change it later in `inputs/researcher_config.yaml`
(`workspace.mode`). Not sure? Pick **analysis** — you can switch.

---

## New here? The 3-minute on-ramp

Never used a research workflow tool before? You don't need to learn any
of the vocabulary on this page yet. Here's the whole thing:

1. **Drop a file in `inputs/`.** A CSV, a spreadsheet, a PDF — whatever
   you've got. (No data yet? Skip to step 2 and just ask a question.)

   ```bash
   mv ~/Downloads/my_data.csv inputs/raw_data/
   ```

2. **Open the folder in your AI IDE and say what you want — in plain
   English.** You don't call any commands. Try literally any of these:

   ```
   i have a csv, what do i do?
   look at my data
   make a chart from this
   is my result significant?
   ```

3. **Read what the AI says back, and answer its one question if it asks
   one.** It will tell you what it found, propose a next step, and wait
   for your OK before doing anything heavy.

That's it. The AI figures out which of the built-in workflows fits your
words and walks you through it. You'll pick up the rest by doing.

**What to expect — the coaching posture.** Research OS is built to be a
careful collaborator, not an eager autocomplete:

* It **looks before it leaps.** On a fresh project it reads your files
  and proposes a plan; it asks before creating experiments or writing
  final outputs.
* It **won't make things up.** Every citation in a write-up is checked
  against real databases; every number has to trace back to a real file
  it produced. If it can't, it says so instead of guessing.
* It **explains, if you want.** Ask *"explain that to me"* or *"why did
  you pick that test?"* and it will. Ask *"teach me about ANCOVA before I
  use it"* and it'll teach you with no commitment to a project.
* It **remembers.** Close the chat, come back tomorrow, say *"pick up
  where we left off"* — your data, decisions, and progress are still
  there.

When you're ready for more, the [1-hour walkthrough](#the-1-hour-walkthrough-optional)
below shows the full arc; [USE_CASES.md](USE_CASES.md) maps "what I want"
to "what to say"; and [SCENARIOS.md](SCENARIOS.md) walks seven complete
real projects from first prompt to finished `synthesis/` output.

---

## Inspect + manage IDE wiring

The `ide` subcommand lets you add, remove, or list IDE MCP configs
without re-running `research-os init`:

```bash
research-os ide list                       # show every supported IDE
                                           # marks which are already wired

research-os ide add cursor                 # wire Cursor only
research-os ide add windsurf aider         # wire several at once
research-os ide remove opencode            # un-wire OpenCode

research-os ide config-path cursor         # print where Cursor's MCP config lands
                                           # (useful for `cat` / `jq` / debugging)
```

`research-os ide` walks up from CWD for `.os_state/`, so it works from
any subdirectory of the project — no need to `cd` to the root first.

---

## Confirm install + workspace health

```bash
research-os doctor                # full report (install + workspace)
research-os doctor --verbose      # show fix hints for passing checks too
research-os doctor --json         # machine-readable
research-os doctor --workspace-only   # skip install checks (CI use)
```

The doctor checks: python version, conda env, version consistency
across `pyproject.toml` / `__init__.py` / `CITATION.cff`, pack
registration, embeddings freshness, typst / chromium on PATH, IDE MCP
wiring, orphan figures, unresolved BLOCK
gates, disk usage, git cleanliness, and `.gitignore` coverage. Exits
`0` (all pass), `1` (warnings only), or `2` (failures present).

---

## Bring in your project — chat or files (1 min)

Fastest path: just tell the AI what you're studying — no files required.
Open the chat (next section) and say something like *"I want to know if X
affects Y; my data's a CSV at `~/data.csv`; hypotheses: …"*. The AI captures
your question, domain, and hypotheses into the intake and shows you to
approve.

Prefer to stage files first? Drop them in:

```bash
mv path/to/data.csv      inputs/raw_data/
mv path/to/paper.pdf     inputs/literature/
mv my_notes.md           inputs/context/
```

The AI reads all of it. No data? That's fine — describe the project in
chat, or talk to the AI in pure consult mode ("teach me about propensity
scores before I use them").

`inputs/raw_data/` and `inputs/literature/` are **source-of-truth** —
Research OS soft-guards them, so the AI overwrites them only with
`force=true` plus your OK. The rest of `inputs/` (`context/`, `intake.md`,
`researcher_config.yaml`) is AI-maintained: whether you drop files in or
just describe the project in chat, the AI fills in the intake for you.
Only `.os_state/` is ever hard-locked.

### When your project needs extra `inputs/` subfolders

The wizard always creates `raw_data/`, `literature/`, and `context/`.
Some packs and protocols expect additional subfolders that the
protocol itself will create the first time you use it — but if you
want to pre-stage files, drop them in the right place from the start:

| You have… | Drop it here | Used by |
|---|---|---|
| A text corpus (novels, transcripts, primary sources) | `inputs/corpus/` (humanities) OR `inputs/raw_data/<slug>/` | `humanities/textual/distant_reading`, `humanities/method/digital_humanities_workflow` |
| Hand-picked passages for close reading | `inputs/textual/passages/` | `humanities/method/close_reading` |
| Definitions / preliminaries for a theorem | `inputs/preliminaries.md` (free-text Markdown — define every object in your claim, plus key prior results) | `theory_math/method/proof_strategy_selection` (hard prerequisite — the protocol blocks without it) |
| Source code under benchmark (the C / Rust / Python you're measuring, not analysis scripts) | `inputs/context/code/` | `methodology/method_comparison` (engineering pack) |
| Interview / survey instruments, IRB protocols, consent forms | `inputs/context/` | `methodology/qualitative_research`, audit gates |
| Reference / lookup tables that aren't raw observations | `inputs/context/` | analysis steps that need them |

If you only realise mid-session, just `mkdir inputs/<subfolder>` and
drop the files in — the immutability guarantee only applies to
`raw_data/` and `literature/`.

---

## Open your AI IDE on the project and talk

The MCP server auto-launches per-IDE-project. The status bar / MCP panel
should show **`research-os` connected**.

Open the chat and try one of:

```
here's my project: I want to know if X affects Y; data's at <path>
fill out the intake
what should I do next?
run a baseline EDA on my data
do real EDA — i don't have a hypothesis yet
write the paper for a journal submission
make me a dashboard for executives
make me a figure from this CSV
explain ANCOVA to me
```

The AI translates your plain-English prompt into the right protocol via
`tool_route`. You don't call MCP tools directly; you just talk.

For longer, scenario-flavoured first-turn prompts (text corpus,
interview transcripts, benchmark study, theorem-to-prove, mixed data +
hypothesis), see the **Common first prompts** table at the top of
[USE_CASES.md](USE_CASES.md) — those are the variants validated
against end-to-end fresh-agent walkthroughs.

---

## Two ways to start a project — CLI or just prompt your AI

You don't have to memorise CLI flags. Pick whichever fits:

**(a) CLI wizard** — `research-os init` (arrow-key Q&A), then open the
folder and talk. Best when you want to set model_profile / mode / identity
up front.

**(b) Just prompt your AI** — open any folder in your AI IDE and paste a
**scaffold prompt** below. The AI interviews you (or reads your filled-in
blanks), runs init with the right mode, brings your data in, and fills the
intake. No CLI needed.

### Scaffold prompts (fill in the blanks, paste into your AI)

Each prompt has fill-in lines (`>>> …`) and a free-text **CONTEXT** block
where you can dump anything — paste a paper abstract, a Slack message, your
PI's email, rough notes — the AI parses it. Leave any line blank and the AI
will ask. Pick the one matching the work:

**Analysis** (the default — data → numbered steps → paper):
```
Set up a new Research OS analysis project here, then get me started.
Project name:  >>>
My question:   >>> (what do you want to find out?)
My data is at: >>> (a path, a URL, or "I'll describe it below" / "none yet")
Output I want: >>> (paper / report / dashboard / poster / not sure)
Autonomy:      >>> (ask me each step / supervised / run adaptively)
Shared server? >>> (yes = HPC/shared box, be careful with resources / no)

CONTEXT (paste anything — abstract, notes, prior results, constraints):
>>>


Steps: interview me on anything blank, run `research-os init` (analysis
mode), bring my data into inputs/raw_data (copy or symlink — reason about
which), fill the intake, then tell me the first step.
```

**Tool-build** (you're building software, RO governs the build):
```
Set up a new Research OS tool_build project here.
Tool name:        >>>
What it must do:  >>>
Done = ?          >>> (what test/eval proves it works)

CONTEXT (paste a spec, an issue, example inputs/outputs):
>>>


Steps: interview me on anything blank, init in tool_build mode, draft
spec/requirements.md from the context, then propose the build approach.
```

**Exploration** (scratch-first, "I'm not sure yet"):
```
Set up a Research OS exploration project here — I want to poke at
something before committing to a plan.
Rough question / hunch: >>>
What I have:            >>> (data path / nothing / "see context")

CONTEXT (dump anything):
>>>


Steps: init in exploration mode, then help me frame the first cheap probe.
When a probe earns it, remind me we can promote to analysis mode.
```

**Notebook** (Jupyter-first data analysis):
```
Set up a Research OS notebook project here for interactive data analysis.
What I'm exploring: >>>
Data is at:         >>>

CONTEXT:
>>>


Steps: init in notebook mode, bring the data in, scaffold a first notebook
I can run top-to-bottom.
```

**Multi-study / program** (several studies under one umbrella):
```
Set up a Research OS multi_study program here — this is several related
studies, not one.
Program goal:        >>>
The studies (rough): >>>

CONTEXT (shared codebook, prereg notes, the studies):
>>>


Steps: init in multi_study mode, seed the shared commons, then register
the first study.
```

**Deep iterative planning, then let the AI run** (plan → autonomous build):
```
I want to plan this deeply before building, then have you execute toward
the goal mostly on your own.
The goal:        >>>
Constraints:     >>> (compute, deadline, what must NOT happen autonomously)
Data is at:      >>>

CONTEXT (everything relevant — the more the better):
>>>


Steps: init the right mode, then walk me through deep_planning to build a
branchable roadmap in inputs/research_plan.md. Once I approve it, run the
roadmap_execution loop toward the goal at the autonomy I set — score each
milestone, re-plan from results, and notify me at decision points or if
anything exceeds the resources I allowed. (If you're Hermes Agent, you can
orchestrate this loop and improve from each result.)
```

Already have a messy folder of data + scripts? Don't init blind — paste:
`organize my existing project into research-os` (it audits → plans →
copies safely, never touching your originals).

---

### Using a small or medium AI? Set `model_profile` first

**The single most important knob if you're not on a frontier model.**
Open `inputs/researcher_config.yaml` (auto-created) and change:

```yaml
model_profile: "small"    # for Claude Haiku 4.5, GPT-4o-mini,
                          # Gemini 2.5 Flash, Llama 3.3, local models
model_profile: "medium"   # default — Claude Sonnet, GPT-4o, Gemini Pro
model_profile: "large"    # for Claude Opus, GPT-5/o-series, Gemini 3 Pro
```

Small models get 1 step/turn, summary-only protocol loads, and prefer
shortcut tools — designed to keep context lean. If your AI runs out of
context mid-plan, drop a tier; if it hands off after every step, bump
up. Full table in [SETUP.md § 6](SETUP.md#pick-the-right-model_profile-for-your-ai).

---

## What you get out of the box

* **Real, verified citations.** Synthesis tools pull every citation from
  Crossref / Semantic Scholar / PubMed / arXiv and refuse hallucinations.
* **Per-step provenance.** Every figure / table / model emits a
  `<name>.prov.json` sidecar with script + parameters + RNG seed +
  library versions + wall-time.
* **Quality gates that block bad synthesis.** Missing focal figure →
  the paper won't assemble. Ungrounded number → audit flags it.
  Hallucinated citation → synthesis refuses.
* **Sub-task pipelines, not mega-scripts.** Steps with >2 scripts must
  declare a `pipeline.yaml` of atomic nodes (ingest → validate → clean
  → fit → diagnose → visualize → report). Content-hash cached.
* **A broad protocol catalogue** the AI picks from via `tool_route`. Each
  protocol carries `scope_tags: {domain, audience, workflow_shape}` and a
  `tier` so the router filters intelligently. Covers the canonical data
  → publication pipeline plus partial / off-axis workflows
  (visualization-only, talks, lay summaries, EDA + hypothesis
  generation, method comparison, reproduction, methodological
  consultation, multi-paper review, mid-pipeline entry, plus pre-data
  qualitative + survey design, IRR, fairness, calibrated UQ,
  manuscript outline, venue selection, defense prep, Data
  Management Plans, and the `build/*` arc for tool_build mode).
* **Live MCP tools** across three namespaces — `sys_*` (system /
  workspace / files / state), `tool_*` (research work), `mem_*`
  (append-only memory). Consolidated families
  (`tool_audit`, `tool_search`, `tool_step`, `tool_lessons`, etc.)
  dispatch by `scope` / `operation` / `dimension`. Legacy v1 tool names
  still resolve via backward-compat aliases — see
  `CHANGELOG.md [2.0.0]` for the surface map.

---

## The 1-hour walkthrough (optional)

### Minutes 0-15 — set up + introduce

After install + scaffold, your first prompt should be one of:

| If you have… | Say… |
|---|---|
| Data + papers in `inputs/` | "fill out the intake" |
| A draft / partial work | "i'm bringing this into research-os" |
| A question, no data | "teach me about <method> before i use it" |
| A pilot already done elsewhere | "we already analysed this, just write it up" |
| A conjecture you want to prove | "I have a conjecture — set up a theory_math project, pick a strategy, draft a verified proof" |
| Interview transcripts | "qualitative project — assume thematic analysis unless transcripts suggest grounded theory" |
| A text corpus for close reading | "humanities project — close reading on the corpus in inputs/raw_data/" |

### Minutes 15-30 — run your first real step

| You want… | Say… |
|---|---|
| Exploratory analysis | "do real EDA — i don't have a hypothesis yet" |
| Quick poke (no paperwork) | "just sanity-check the data" |
| Specific model | "fit a logistic regression and check assumptions" |
| Method comparison | "benchmark random forest vs xgboost head-to-head" |
| Data quality | "data quality audit on this csv" |
| Power justification | "power analysis for the IRB" |
| What's next? | "what should I do next" |

### Minutes 30-45 — iterate

| Phrase | What happens |
|---|---|
| "actually, group by quarter instead of month" | AI bumps the script to `_v2`, re-runs |
| "try a tree-based model in parallel" | AI creates a parallel `workspace/NN_/` path |
| "this is a dead end" | AI marks the folder `__DEAD_END` and captures the lesson |
| "find papers on X" | Multi-database literature search |
| "critique this figure" | Reviewer-style critique |
| "explain X to me" | Methodological consultation (no project commit) |

### Minutes 45-60 — produce something

| Output | Say… |
|---|---|
| Single figure for a talk | "make me a figure from this CSV" |
| Lab meeting slides | "build a lab meeting deck" |
| Conference poster + QR | "make me a conference poster" |
| Paper draft for a journal | "draft the paper for a journal submission" |
| Dashboard for stakeholders | "build a dashboard for executives" |
| One-page handout | "make a one-pager for the poster session" |
| Weekly PI update | "weekly update for my PI" |
| Lay summary / press release | "press release on this finding" |

---

## Cheatsheet — every command worth knowing

### CLI (ten commands)

```bash
research-os init                          # scaffold THIS folder
research-os init my-project --name "X"    # scaffold ./my-project
research-os init . --force                # re-scaffold (preserves data + config)
research-os init --ide cursor,claude      # only those two IDEs

research-os ide list                      # what IDEs are wired here?
research-os ide add cursor                # wire Cursor (without re-init)
research-os ide remove opencode           # un-wire OpenCode
research-os ide config-path cursor        # print where Cursor's MCP config lives

research-os doctor                        # diagnose install + workspace health
research-os doctor --json                 # machine-readable
research-os doctor --workspace-only       # skip install-side checks

research-os start                         # run the MCP server (global)
                                          # you rarely run this by hand —
                                          # your IDE auto-launches it

research-os hermes add                    # wire the Hermes agent (optional)
research-os route "fit a survival model"  # preview which protocol the router picks
research-os refresh                       # re-sync this project's template files
                                          #   (AGENTS.md / CLAUDE.md / IDE rules)
                                          #   after upgrading research-os
research-os completion bash               # emit a shell-completion script
```

### Where files go

```
inputs/raw_data/      ← your data (source-of-truth; soft-guarded, force=true to overwrite)
inputs/literature/    ← your PDFs (source-of-truth; soft-guarded, force=true to overwrite)
inputs/context/       ← your notes / drafts / past reports
docs/                 ← research question, domain, glossary
workspace/            ← AI lives here; numbered experiment folders
workspace/scratch/    ← AI sandbox (gitignored)
synthesis/            ← final outputs (only created when you ask)
.os_state/            ← internal — do NOT edit by hand
```

### Autonomy slider (`inputs/researcher_config.yaml`)

| Mode | What the AI does without asking | Best for |
|---|---|---|
| `adaptive` *(default)* | per-action risk gating: flows on cheap/reversible work, pauses before irreversible/expensive actions (deleting data, paid API calls, long jobs) | most people — you rarely need to change it |
| `manual` | nothing — asks before every tool call | learning / debugging |
| `supervised` | reads + searches autonomously; asks before creating experiments, writing to `synthesis/`, long jobs | when you want a tighter leash than adaptive |
| `autopilot` | runs end-to-end; asks only before the final ship gate | well-scoped projects you trust it to drive |
| `coaching` | like supervised, plus pedagogical preludes that explain the *why* before each move | learning the method as you go |

Switch mid-session: *"switch to autopilot"* / *"switch to manual"*.

### Prompts by phase

**Starting a project**
```
fill out the intake
look at my data
i'm bringing this into research-os, we've been working on it for months
we already analysed this, just write it up
```

**Mid-flow analysis**
```
run a baseline EDA
fit a logistic regression and check assumptions
do real EDA — i don't have a hypothesis yet
benchmark random forest vs xgboost head-to-head
data quality audit on this csv
power analysis for the IRB
design the evaluation strategy
design the hyperparameter sweep
freeze the analysis plan
what should i do next?
this isn't working — abandon it and try X
```

**Reading + understanding**
```
review this paper
tear apart this paper as a tough reviewer
journal club on these three papers
explain mixed-effects models to me
teach me propensity scores before i use them
reproduce this paper
find me papers about X
do a systematic review of X
data ethics review on this dataset
```

**Visualization**
```
make me a figure from this CSV
polish my figures for the talk
build a figure deck for the paper
critique this figure
make figure 2 with panels A B C D
order my figures for the paper
check colour accessibility on my figures
```

**Writing + synthesis**
```
workshop the title
draft the methods
draft the results
draft the discussion
tighten the limitations
draft the end matter (data avail / CRediT / etc.)
draft the cover letter

draft the paper for a journal submission
draft an NIH R01 narrative
make a dashboard for executives
build a poster for the conference
build a slide deck for my defense
make a one-pager for the poster session
write a lay summary for the public
press release on this finding
weekly update for my PI
```

**Audit + ship**
```
check reproducibility
audit my workspace for issues
is this ready to submit
fix my workspace
```

**Session control**
```
wrap up the session
pick up where we left off
hand off to a collaborator
switch to autopilot mode
push back if you disagree with my plan
```

### Routing primitives (the AI calls these — you don't)

* `sys_boot` — one-call session start (state + config + history + dep
  inventory + next protocol + freshness + pause classification +
  active plan)
* `tool_route(prompt)` — picks the right protocol from your message;
  returns `recommended_action` (literal next-call string), `tier`,
  and `why_matched` for the AI to rank options
* `sys_protocol_get` — defaults to `format='summary'` (~3K chars);
  pass `format='full' | 'step' | 'lean' | 'dryrun'` only when needed
* `sys_active_tools(protocol)` — a scoped tool shortlist per
  protocol, instead of the full catalogue
* `sys_help` — AI orientation (which protocol does what)
* `sys_active_project` — which project did the global server resolve

### When something is wrong

| Symptom | Fix |
|---|---|
| AI seems lost / confused | *"show me sys_help"* — AI re-orients |
| Wrong protocol picked | *"actually I meant X"* — AI re-routes |
| AI making bad calls | *"switch to manual mode"* |
| Workspace looks broken | *"fix the workspace"* — `tool_workspace_repair`, never deletes |
| Chat is too long | *"hand off the session"* — open fresh chat, *"pick up where we left off"* |
| Deleted by mistake | *"list checkpoints"* → *"rollback to <id>"* |
| Install / wiring uncertain | `research-os doctor` — full health check |

---

## Setup Prompt (paste into any AI)

Want an AI to handle install + IDE wiring? Paste this into Claude /
ChatGPT / Cursor / OpenCode / Aider / anywhere:

> I want to install and configure **Research OS** on this machine.
> Research OS is an MCP-native research operating system hosted at
> <https://github.com/VibhavSetlur/Research-OS>. Please walk me through
> all of this, asking me ONE question at a time when you need input:
>
> 1. **Check Python ≥ 3.10.** If missing, suggest how to install for my
>    OS (macOS / Linux / Windows / WSL — ask which I'm on).
> 2. **Install with all optional extras**:
>    ```
>    pip install research-os
>    ```
>    Use a virtualenv if I tell you to; otherwise install with
>    `--user`.
> 3. **Verify**: run `research-os --help` and show me the output. There
>    should be seven subcommands: `init`, `ide`, `mcp`, `api-key`, `start`, `doctor`, `completion`.
> 4. **Detect my AI IDE.** Ask which I'm using (Claude Code / OpenCode /
>    Antigravity / Cursor / Claude Desktop / VS Code with MCP / Windsurf
>    / Continue / Aider / other). For the chosen IDE, tell me what file
>    Research OS will drop on `init`. You can preview the path with
>    `research-os ide config-path <ide>`. If it needs a global config
>    snippet, show it to me — DO NOT modify global configs without my
>    approval.
> 5. **Show me the workflow**:
>    ```
>    mkdir my-project && cd my-project
>    research-os init     # scaffolds + drops IDE config
>    research-os doctor   # confirm install + workspace are healthy
>    research-os ide list # confirm the right IDE was wired
>    ```
>    Then open the IDE on the folder and chat. Mention that
>    `research-os start` is auto-launched by the IDE; I rarely run it
>    manually.
> 6. **Show me 5 essential prompts** I'll use most often:
>    - "fill out the intake"
>    - "what should I do next?"
>    - "run a baseline EDA"
>    - "draft the paper for a journal submission"
>    - "make me a dashboard"
> 7. **Optional credentials**: Research OS does NOT manage LLM provider
>    keys — my IDE owns model access. Optional literature / web search
>    keys live in `inputs/researcher_config.yaml api_keys.*`. Don't ask
>    me for them now.
> 8. **Point me at the docs**:
>    - `docs/START.md` — this file
>    - `docs/RESEARCHER_GUIDE.md` — full workflow walkthrough
>    - `docs/USE_CASES.md` — role × goal × output map
>    - `docs/FAQ.md` — common questions
>    - `CHANGELOG.md [2.0.0]` — if upgrading from v1.x

---

## What to read next

* [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — the full workflow guide
  (mental model, every protocol, real session transcripts, power-user
  patterns, troubleshooting).
* [USE_CASES.md](USE_CASES.md) — pick the right protocol by role × goal
  × output.
* [TOOL_BUILDER.md](TOOL_BUILDER.md) — building software instead of
  analysing data? The **tool_build** workspace mode.
* [SETUP.md](SETUP.md) — detailed install + per-IDE wiring +
  troubleshooting.
* [FAQ.md](FAQ.md) — common questions.
* [PROTOCOLS.md](PROTOCOLS.md) — catalogue of every protocol.
* [TOOLS.md](TOOLS.md) — catalogue of every MCP tool.
* `CHANGELOG.md [2.0.0]` — if you're coming
  from v1.x: the consolidated tool surface + alias map.
* [AI_GUIDE.md](AI_GUIDE.md) — operating manual for the AI driving
  Research OS (useful for debugging "why did the AI do that?").
