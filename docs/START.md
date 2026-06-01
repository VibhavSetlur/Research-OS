# Start here

Everything you need to be productive with Research OS — installation,
first project, copy-paste prompts. Read top to bottom (~15 minutes), or
skip to the section you need.

If you'd rather watch the AI handle install + IDE wiring for you, paste
the [Setup Prompt](#setup-prompt-paste-into-any-ai) into any AI chat.

---

## Install (60 s)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Extras: `all` (everything Python — recommended), `ci` (lean, used by
CI), or a subset of `web` / `literature` / `viz` / `audit` / `ml` /
`notebook`.

**Research OS is global.** Install once; the same `research-os`
binary serves every project you scaffold.

Verify:

```bash
research-os --help
```

If `research-os: command not found`, add `~/.local/bin` (or your
virtualenv's `bin/`) to your `PATH`.

Need help with Python / pip / virtualenvs / conda? See
[SETUP.md](SETUP.md).

---

## Scaffold your first project (15 s)

```bash
mkdir my-project && cd my-project
research-os init
```

`init` is the only per-project command. It drops:

- `AGENTS.md` — the AI's operating manual (every supported IDE reads it)
- `inputs/{raw_data, literature, context}/` — where YOU drop files
- `workspace/`, `synthesis/`, `docs/`, `.os_state/` — AI workspace + outputs
- Pre-wired MCP configs for **Claude Code, OpenCode, Antigravity, Cursor,
  Claude Desktop, VS Code, Windsurf, Continue, Aider**

You typically need to **restart your IDE** so it picks up the new MCP config.

---

## Drop your files (1 min)

```bash
mv path/to/data.csv      inputs/raw_data/
mv path/to/paper.pdf     inputs/literature/
mv my_notes.md           inputs/context/
```

The AI reads all of it. No data? Skip this — you can drop files later, or
talk to the AI in pure consult mode ("teach me about propensity scores
before I use them").

`inputs/raw_data/` and `inputs/literature/` are **immutable** — Research
OS blocks writes server-side.

---

## Open your AI IDE on the project and talk

The MCP server auto-launches per-IDE-project. The status bar / MCP panel
should show **`research-os` connected**.

Open the chat and try one of:

```
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
* **82 protocols** the AI picks from via `tool_route`. Covers the
  canonical data → publication pipeline plus partial / off-axis
  workflows (visualization-only, talks, lay summaries, EDA + hypothesis
  generation, method comparison, reproduction, methodological
  consultation, multi-paper review, mid-pipeline entry).
* **140 MCP tools** across three namespaces — `sys_*` (system /
  workspace / files / state), `tool_*` (research work), `mem_*`
  (append-only memory).

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

### CLI (two commands)

```bash
research-os init                          # scaffold THIS folder
research-os init my-project --name "X"    # scaffold ./my-project
research-os init . --force                # re-scaffold (preserves data + config)
research-os init --ide cursor,claude      # only those two IDEs
research-os start                         # run the MCP server (global)
```

You rarely run `research-os start` by hand — your IDE auto-launches it.

### Where files go

```
inputs/raw_data/      ← your data (immutable — RO blocks writes)
inputs/literature/    ← your PDFs (immutable — RO blocks writes)
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
| `manual` | nothing — asks before every tool call | learning / debugging |
| `supervised` *(default)* | reads + searches autonomously; asks before creating experiments, writing to `synthesis/`, long jobs | day-to-day |
| `autopilot` | runs end-to-end; asks only before final synthesis | well-scoped projects |

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

* `sys_boot` — one-call session start
* `tool_route(prompt)` — picks the right protocol from your message
* `sys_protocol_get format='summary'` — load step headings (~300 tokens)
* `sys_active_tools(protocol)` — tool shortlist per protocol
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
>    pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
>    ```
>    Use a virtualenv if I tell you to; otherwise install with
>    `--user`.
> 3. **Verify**: run `research-os --help` and show me the output.
> 4. **Detect my AI IDE.** Ask which I'm using (Claude Code / OpenCode /
>    Antigravity / Cursor / Claude Desktop / VS Code with MCP / Windsurf
>    / Continue / Aider / other). For the chosen IDE, tell me what file
>    Research OS will drop on `init`. If it needs a global config
>    snippet, show it to me — DO NOT modify global configs without my
>    approval.
> 5. **Show me the two-command workflow**:
>    ```
>    mkdir my-project && cd my-project
>    research-os init     # scaffolds + drops IDE config
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

---

## What to read next

* [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — the full workflow guide
  (mental model, every protocol, real session transcripts, power-user
  patterns, troubleshooting).
* [USE_CASES.md](USE_CASES.md) — pick the right protocol by role × goal
  × output.
* [SETUP.md](SETUP.md) — detailed install + per-IDE wiring +
  troubleshooting.
* [FAQ.md](FAQ.md) — common questions.
* [PROTOCOLS.md](PROTOCOLS.md) — catalogue of all 82 protocols.
* [TOOLS.md](TOOLS.md) — catalogue of all 140 MCP tools.
* [AI_GUIDE.md](AI_GUIDE.md) — operating manual for the AI driving
  Research OS (useful for debugging "why did the AI do that?").
