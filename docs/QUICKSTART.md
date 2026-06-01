# Quickstart — 5 minutes

This page gets you from zero to "the AI is doing my research" in under 5
minutes. Want the explicit hand-holding version? Read
[FIRST_HOUR.md](FIRST_HOUR.md) first. For deeper material see
[GUIDE.md](GUIDE.md), [SETUP.md](SETUP.md), or
[RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md).

---

## 1. Install (60 s)

```bash
pip install "research-os[ci] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

`[ci]` is the lean install (enough for 90% of use cases). Use `[all]`
if you want shap / xgboost / jupyter / full literature providers
preinstalled. Need help with Python / pip / virtualenvs? See
[SETUP.md](SETUP.md).

Research OS is GLOBAL. You install it once. The same `research-os`
binary serves every project you scaffold.

## 2. Scaffold a project (15 s)

```bash
mkdir my-project && cd my-project
research-os init
```

`init` is the ONLY per-project command. It drops:

* `AGENTS.md` — the AI operating manual (every supported IDE reads from this).
* `inputs/researcher_config.yaml` — config + optional API keys (gitignored).
* `.os_state/` — internal state ledger.
* Pre-wired MCP configs for **Claude Code, OpenCode, Antigravity, Cursor,
  Claude Desktop, VS Code, Windsurf, Continue, Aider**. Whichever IDE you
  use, it should auto-detect.

## 3. Drop your files (1 min)

```bash
cp path/to/data.csv     inputs/raw_data/
cp path/to/paper.pdf    inputs/literature/
cp my_notes.md          inputs/context/
```

Anything: data, PDFs, prior write-ups, lab notebooks. The AI will read it all.

## 4. Open your AI IDE on this folder

Most IDEs auto-detect the MCP config. The IDE auto-launches
`research-os start` (the global MCP server) and points it at THIS
project via the `RESEARCH_OS_WORKSPACE` env var. You don't run
`research-os start` by hand.

If your IDE doesn't auto-detect, see [SETUP.md § 4](SETUP.md). The
status bar / MCP panel should show `research-os` connected.

## 5. Just talk

Try any of:

```
> fill out the intake
> what should I do next?
> run a baseline EDA on my data
> find papers about <topic>
> fit a logistic regression and check assumptions
> write the methods section
> make me a dashboard
> draft a poster for an academic conference
> write the paper for a journal submission
> check my workspace for issues
```

The AI loads the right protocol and walks through it. You can interrupt,
redirect, or just say "looks good, keep going" at any point.

---

## What to expect

* **The AI asks for confirmation** at meaningful checkpoints (creating
  experiments, writing to synthesis/, running long jobs) — controlled by
  `interaction.autonomy_level` in researcher_config.
* **Every method choice is grounded in real literature** via
  `tool_research_method` + verified citations. No hallucinations leak into
  final outputs.
* **Every script lives in a numbered experiment folder**
  (`workspace/01_baseline_eda/`, `workspace/02_…`) with versioned scripts
  (`_v1`, `_v2`, …) and structured outputs.
* **Append-only logs** track everything in `workspace/methods.md`,
  `workspace/analysis.md`, `workspace/citations.md`.

---

## What if I'm not ready to start a project yet?

You can install Research OS now and set up your IDE WITHOUT scaffolding any
project. See [SETUP.md § 5](SETUP.md) or paste
[`docs/SETUP_PROMPT.md`](SETUP_PROMPT.md) into any AI chat — it'll walk you
through install and IDE wiring for whatever IDE you use.

---

## Next reads

* [FIRST_HOUR.md](FIRST_HOUR.md) — 60-minute hand-held first session.
* [CHEATSHEET.md](CHEATSHEET.md) — every command worth knowing, one page.
* [USE_CASES.md](USE_CASES.md) — pick the right protocol by
  role × goal × output.
* [WALKTHROUGH.md](WALKTHROUGH.md) — exhaustive 10-day simulated
  project with realistic messy researcher prompts. Best for seeing
  every feature in context.
* [RESEARCHER_GUIDE.md](RESEARCHER_GUIDE.md) — non-technical walk-through of
  the workflow.
* [GUIDE.md](GUIDE.md) — full tool + protocol reference.
* [PROTOCOLS.md](PROTOCOLS.md) — when each protocol fires + what it does.
* [TOOLS.md](TOOLS.md) — every MCP tool with example invocations.
* [FAQ.md](FAQ.md) — common questions.
