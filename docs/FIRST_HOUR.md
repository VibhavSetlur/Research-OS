# Your first hour with Research OS

A walkthrough for a researcher who just installed Research OS. Read top
to bottom. You should be productive by the end.

> **Pre-req**: `pip install "research-os @ git+https://github.com/VibhavSetlur/Research-OS.git"`
> done; an AI IDE installed (Cursor / Claude Code / VS Code / Windsurf /
> Continue / OpenCode / Aider / Antigravity).

---

## Minute 0-5 — Scaffold your first project

```bash
mkdir my-first-project && cd my-first-project
research-os init --name "my-first-project"
```

You'll see a workspace layout printed. The folders that matter:

```
inputs/raw_data/      ← drop your CSVs / parquet / FASTQ here
inputs/literature/    ← drop your PDFs here
inputs/context/       ← drop notes / drafts / prior reports here
docs/                 ← human-readable: research question, glossary
workspace/            ← AI lives here (you don't touch this)
synthesis/            ← final outputs (created when you ask)
```

`research-os init` also drops MCP configs for every supported IDE. **You
do not need to run `research-os start` yourself** — your IDE auto-launches
the MCP server when you open the project.

---

## Minute 5-10 — Drop your data

Move (or symlink) your files into the right `inputs/` subfolder.

- Tabular data → `inputs/raw_data/`
- PDFs of papers → `inputs/literature/`
- Notes / past reports / project briefs → `inputs/context/`

If you don't have data yet, that's fine — you can drop it in later and
say "I dropped new files, integrate them."

---

## Minute 10-15 — Open your IDE and ask the AI to introduce itself

Open your IDE on the project folder. The MCP server connects
automatically (look for "research-os" in the MCP server status — Cursor
shows it in Settings → MCP; Claude Desktop in the lower-right status bar).

Open the chat panel and type:

```
fill out the intake
```

The AI reads your `inputs/`, infers the domain, proposes a research
question + hypotheses, and shows you what it inferred. You either
approve or refine. This is your first interaction; it should take ~30
seconds.

If you don't have data yet, try:

```
i'm thinking about doing a project on X — what should i know about
the methods first
```

This triggers the **methodological consultation** protocol — the AI
teaches you the relevant methods without needing data.

---

## Minute 15-30 — Run your first analysis

Pick ONE of these depending on what you actually want:

| If you want… | Say… |
|---|---|
| Real exploratory analysis | "do real EDA — i don't have a hypothesis yet" |
| A quick look (no paperwork) | "just poke at the data" |
| To run a specific model | "fit a logistic regression and check assumptions" |
| The AI to recommend next steps | "what should i do next" |
| Just polish figures you have | "polish my figures" |

The AI will create `workspace/01_<descriptive_name>/`, write a script,
run it, produce a figure, and write conclusions. **Watch what it does.**
Question anything that looks wrong — the AI defers to your judgement
on methodology calls.

---

## Minute 30-45 — Iterate

You don't get the right analysis on the first try. That's normal.

| Course-correction phrase | What happens |
|---|---|
| "actually, group by quarter instead of month" | AI bumps the script to `_v2`, re-runs, updates conclusions |
| "try a tree-based model in parallel" | AI creates `workspace/03_random_forest/` as a parallel path |
| "this is a dead end" | AI marks the folder `__DEAD_END`, captures the lesson, proposes alternatives |
| "find papers on X" | AI runs a multi-database literature search |
| "explain ANCOVA to me" | AI teaches you the method without committing to it |

---

## Minute 45-60 — Produce something

Pick a deliverable:

| Output | Say… |
|---|---|
| Single figure for a talk | "make me a figure from this CSV" |
| Lab meeting slides | "build a lab meeting deck" |
| Conference poster | "make me a conference poster" |
| Paper draft | "draft the paper for a journal submission" |
| Dashboard for stakeholders | "build a dashboard for executives" |
| One-page handout | "make a one-pager for the poster session" |
| Weekly update for my PI | "weekly update for my PI" |
| Lay summary for a press release | "press release on this finding" |

The AI assembles the output, audits it, and tells you where it landed
(typically `synthesis/<output>.md` or `synthesis/<output>.pdf`).

---

## What you've learned in 60 minutes

1. **One global MCP server, per-project init.** You ran
   `research-os init` once for THIS project; the same `research-os`
   binary serves every project you scaffold.
2. **You don't call MCP tools.** You talk to the AI. The AI picks the
   right protocol from your plain-English prompt via `tool_route`.
3. **`inputs/` is yours; `workspace/` is the AI's; `synthesis/` is what
   you ship.** Never write under `inputs/raw_data/` or
   `inputs/literature/` — Research OS blocks it.
4. **Numbered experiment folders.** Every analytical step lives in
   `workspace/NN_<descriptive_slug>/` with its own scripts, outputs,
   figures, conclusions. The slug describes what the step DOES.
5. **Provenance, auto.** Every figure / table / model emits a
   `.prov.json` sidecar with the script + parameters + seed + library
   versions. You can trace any number in the paper to a workspace
   artefact.
6. **Quality gates BLOCK bad synthesis.** Missing figure → paper won't
   assemble. Hallucinated citation → synthesis refuses. Ungrounded
   number → audit flags it.

---

## What to read next

- [QUICKSTART.md](QUICKSTART.md) — the dense 5-minute version
- [CHEATSHEET.md](CHEATSHEET.md) — one page, every command worth knowing
- [USE_CASES.md](USE_CASES.md) — pick a protocol by role × goal × output
- [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — full walkthrough
- [FAQ.md](FAQ.md) — when things go wrong

---

## When things go wrong

| Symptom | Fix |
|---|---|
| AI seems lost / confused | Type `tool_help` (or "show me sys_help") — the AI re-orients itself |
| Wrong protocol picked | "actually I meant <X>" — AI re-routes |
| AI making bad calls | "switch to manual mode" — autonomy goes down to per-step confirmation |
| Workspace looks broken | "fix the workspace" — runs `tool_workspace_repair` (never deletes) |
| Chat is too long | "hand off the session" — AI writes a resume doc; open a fresh chat and say "pick up where we left off" |
| Deleted something by mistake | `sys_checkpoint_rollback <id>` — RO auto-snapshots at every protocol boundary |

You're now using Research OS. Welcome.
