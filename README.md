<p align="center">
  <img src="assets/logo.svg" alt="Research OS — grounded · cited · auditable" width="520">
</p>

<h1 align="center">Research OS</h1>

<p align="center">
  <a href="https://pypi.org/project/research-os/"><img src="https://img.shields.io/pypi/v/research-os?color=orange&label=pypi&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/research-os/"><img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT"></a>
  <a href="https://github.com/VibhavSetlur/Research-OS/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/VibhavSetlur/Research-OS/test.yml?branch=main&label=tests" alt="tests"></a>
</p>

<p align="center">
  <strong>Talk to your AI in plain English. Get publication-grade research back.</strong><br>
  No hallucinated citations. No fabricated numbers. Every figure traceable to the script that made it.
</p>

<p align="center">
  <a href="docs/START.md">Quick start</a> ·
  <a href="docs/USE_CASES.md">What you can ask for</a> ·
  <a href="docs/SCENARIOS.md">Worked examples</a> ·
  <a href="docs/RESEARCHER_GUIDE.md">Full guide</a> ·
  <a href="docs/FAQ.md">FAQ</a>
</p>

---

## 30-second version

```bash
pip install research-os
mkdir thesis-chapter-3 && cd thesis-chapter-3
research-os init                  # arrow-key wizard, ~20 seconds
```

Open the folder in Claude Code (or Cursor, or any MCP-capable AI IDE) and talk:

> **You:** I have a CSV of 2,400 patients at `~/data/cohort.csv`. I want to know whether the new drug lowers 30-day readmission, controlling for age and comorbidity. Hypothesis: it does, and the effect is bigger for older patients.

> **AI:** *Captures your question, domain, and both hypotheses; profiles the CSV; proposes a baseline EDA + a logistic regression with an age interaction; asks you to confirm before running anything.*

From there: `run the baseline EDA` → `fit the model` → `draft the results section` → `is this ready to submit?`. Every figure lands with a caption and the script that made it; every citation is verified; every number in the draft traces back to a real file on disk.

That's the whole idea. The rest of this page explains why it matters.

> **Want the most robust setup, not just the fastest one?** The 30-second path
> works, but a few minutes of proper onboarding pays off: let the AI scan your
> inputs, help you frame the question, pick the right mode, and wire exactly one
> IDE before you start producing work. The README's
> [setup prompt](#prefer-to-let-your-ai-set-it-up-paste-this-fill-in-the-blanks)
> walks the AI through that in order, and [docs/START.md](docs/START.md) is the
> guided onboarding. For a self-improving layer on top — memory across projects,
> reusable skills, autonomous long runs — pair it with
> [Hermes](https://hermes-agent.nousresearch.com) (see
> [Pair it with a self-improving agent layer](#pair-it-with-a-self-improving-agent-layer)).

---

## The problem it solves

AI coding assistants are fast, and they will cheerfully lie to you. Not maliciously — they pattern-match. Ask for a literature review and you'll get plausible citations to papers that don't exist. Ask for a results section and you'll get confident p-values that were never computed. Ask a follow-up next week and last week's decisions are gone.

For throwaway code, fine. For research that ends up in a thesis, a grant, or a paper, those failures are career-damaging — and they're invisible until a reviewer (or a retraction) finds them.

Research OS is an **MCP server that sits between your AI and your project** and refuses to let those four things happen:

| The failure mode | What Research OS does instead |
|---|---|
| **Invented citations** | Every reference is checked against Crossref / Semantic Scholar / PubMed / arXiv before it lands in a draft. Can't verify it? It's dropped, not quietly kept. |
| **Invented numbers** | Every quantitative claim in your write-up must point at a real file in `workspace/`. If a number isn't grounded in an artifact, synthesis blocks. |
| **400-line unreviewable scripts** | Work is split into small, content-hash-cached steps. Change one input; only the affected parts re-run. You can actually read what ran. |
| **Lost context** | Decisions, hypotheses, dead-ends, and draft revisions are written down as you go. Tomorrow's chat resumes exactly where today's ended. |

It works with the AI tools you already use — **Claude Code, Cursor, Claude Desktop, Antigravity, VS Code, Windsurf, OpenCode, Continue, Aider**. One install, one wizard, and the assistant you already trust does work that's traceable, grounded, and reproducible — the rigor you'd need *before* you submit, not a guarantee a reviewer will accept it.

---

## What working with it actually feels like

No commands to memorize, no DSL to learn. You describe what you want; the AI loads the right protocol and walks it.

**Starting** — you don't even need to touch a file:

> "Here's my project: does sleep duration predict exam scores in this dataset? Data's at `~/study/students.csv`. I think more sleep helps, more so for younger students."

The AI records your question + hypotheses, profiles the data, surfaces relevant prior work, and asks you to confirm before any analysis starts. (Prefer to drop files in `inputs/` first? That works too — same result.)

**Doing the work:**

> "run a baseline EDA"

You get `workspace/01_baseline_eda/` — readable scripts, figures with real captions, tables, and a written conclusion that links back to your hypotheses. Numbered, cached, re-runnable.

> "compare logistic regression against gradient boosting"

A real head-to-head: same split, same metrics, paired significance test, and a stated winner — not a hand-wavy "both have tradeoffs."

**Writing it up:**

> "draft the discussion"

A discussion that cites *your* results. Every citation verified, every figure and number traceable.

> "make me a poster for the lab meeting Thursday"

The AI authors `synthesis/poster.typ` directly and compiles it to PDF — no rigid template, custom-designed for your content, validated before it ships.

**Shipping it:**

> "is this ready to submit?"

A GREEN / YELLOW / RED verdict with a punch list — every check a journal will run, before they run it.

> "going to lunch, pick up tomorrow"

State, plan, hypotheses, dead-ends, and drafts all persist. Tomorrow's session opens exactly where you left off.

→ Full catalogue of what to say: **[USE_CASES.md](docs/USE_CASES.md)** · Seven complete worked projects (messy CSV → published paper, with the exact prompts): **[SCENARIOS.md](docs/SCENARIOS.md)**

---

## Three ways to work (set once, at init)

The wizard's first question — *"What are you building?"* — picks a **workspace mode** that reshapes the scaffold and how the AI behaves:

- **analysis** *(default)* — data → results → paper. Numbered experiment steps; "done" means grounded figures + conclusions.
- **tool_build** — you're building software (a CLI, a library, a pipeline). Research OS governs the build from above (spec → implement → test → benchmark) while the tool lives in its own git repo; "done" means **tests + build + eval pass**, not figures. → [docs/TOOL_BUILDER.md](docs/TOOL_BUILDER.md)
- **exploration** — scratch-first. Poke at the data with light gates; promote a probe to a real step only when it earns it.

Three more modes cover bigger shapes — **hybrid** (build a tool *and* use it on data in one project), **notebook** (Jupyter is the unit of work), and **multi_study** (a program of sub-studies sharing a codebook). Set the mode at init (`research-os init --workspace-mode <mode>`) or change it later in `inputs/researcher_config.yaml`.

---

## What you actually see on disk

A clean three-folder workspace. You only ever touch one of them.

```
thesis-chapter-3/
│
├── inputs/                 ← YOU own this (the AI reads, never overwrites)
│   ├── raw_data/             your data — CSV, Parquet, FASTQ, NIfTI, …
│   ├── literature/           PDFs of papers the project draws on
│   ├── context/              PI emails, lab notes, prior drafts
│   └── researcher_config.yaml  one optional file that tunes AI behavior
│
├── workspace/              ← the AI works here (you read; it writes)
│   ├── 01_baseline_eda/      one analysis step per numbered folder
│   │   ├── scripts/            code you can read + re-run
│   │   ├── outputs/            figures (with captions), tables, reports
│   │   └── conclusions.md      findings + interpretation, tied to hypotheses
│   ├── methods.md            project-wide methods narrative (append-only)
│   ├── analysis.md           decision log + dead-ends + rationale
│   ├── citations.md          verified citations only
│   └── logs/                 every audit pass + every gate override
│
└── synthesis/              ← deliverables land here (only when you ask)
    ├── paper.typ → paper.pdf       AI-authored, compiled for you
    ├── poster.typ → poster.pdf
    ├── slides.typ → slides.pdf
    ├── dashboard.html              single-file, offline, accessible
    └── figures/                    curated focal figures + captions
```

One principle holds it together: **you own `inputs/`, the AI owns the rest, and nothing exists until you ask for it.** A fresh project isn't pre-cluttered with empty folders — `workspace/01_*` appears the first time you run a step.

→ Deeper tour: **[RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md)** · Exact layout per mode: **[PROJECT_LAYOUT.md](docs/PROJECT_LAYOUT.md)**

---

## Install & run

```bash
# 1. Install once — the same binary serves every project you scaffold.
pip install research-os

# 2. Scaffold a project (arrow-key wizard).
mkdir my-project && cd my-project
research-os init

# 3. (Optional) confirm everything's healthy.
research-os doctor

# 4. Open the folder in your AI IDE and talk. The MCP server auto-launches.
#    > here's my project: I want to know if X drives Y; data's at <path>
#    > what should I do next?
#    > draft the results section
#    > is this ready to submit?
```

The full experience ships in the base install — no extras to remember. A handful of features that need their own system runtime (the enforcement daemon, R, Julia) are opt-in; see [SETUP.md](docs/SETUP.md).

### Prefer to let your AI set it up? Paste this (fill in the blanks)

If you'd rather not run the wizard yourself, give your AI assistant the prompt below. It's written so the AI wires up **only your IDE** (not all of them), sets up the MCP server + daemon, and reminds you to restart — the one step people miss. Fill in the three blanks and paste it into your AI IDE / agent, opened in the folder you want the project in:

```text
Set up a Research OS project in this folder for me. Do NOT install integrations
for editors I don't use.

  • My AI IDE / agent:        ______   (e.g. Claude Code, Cursor, VS Code,
                                       Windsurf, OpenCode, Aider — pick ONE)
  • My research question:     ______
  • My data / inputs are at:  ______   (a path, a URL, or "none yet")

Do exactly this, in order:
  1. Run:  research-os init --ide <my IDE from above> --question "<my question>"
     (if research-os isn't installed yet: pip install research-os, then run it).
     Use ONLY my IDE for --ide — never "all".
  2. If I gave a data path, bring it into inputs/raw_data/ (copy if small/portable,
     symlink if large/shared) and record where it came from.
  3. Set up the MCP server for my IDE and, if I want durable long runs, the
     enforcement daemon (research-os daemon start). Tell me which you wired.
  4. Then STOP and tell me to RESTART my AI session in this project — the MCP
     server only loads on a fresh session. Don't continue until I've restarted.

After I restart, confirm you can see the Research OS tools and tell me the first
step toward my question.
```

Why the restart matters: an IDE/agent loads its MCP servers when the session starts, so the Research OS tools only appear **after** you reopen the project. Pointing your AI at Research OS without this almost always ends with it improvising instead of using the real tools.

→ Full walkthrough: **[START.md](docs/START.md)** · Per-IDE wiring: **[SETUP.md](docs/SETUP.md)** · CLI reference: **[CLI.md](docs/CLI.md)**

---

## Two layers, and why they matter

**1. The reasoning core (always on).** The MCP server every command above talks to. Three tool namespaces — `sys_*` (workspace / files / state), `tool_*` (research work), `mem_*` (append-only memory) — plus ~146 protocols the AI routes to via `tool_route`. The core is *reactive*: it runs in your IDE, responds to each prompt, and never blocks. Most projects need nothing more.

**2. The enforcement daemon (optional).** For big or long-lived projects, a local daemon adds what a reactive server can't:

- **Background runs** with a durable journal, provenance, and lineage — long jobs don't freeze the chat.
- **Freshness gates** — it won't let the AI ship a result built on data that changed underneath it.
- **Hard, human-approved gates** — the AI can't self-approve past a real checkpoint.
- **A resource budget** the machine actually enforces, and completion notifications.

The core behaves *identically* with or without the daemon — it only ever *adds* enforcement, never changes the tools. → [DAEMON.md](docs/DAEMON.md) · [ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Pair it with a self-improving agent layer

Research OS is the rigor substrate. The AI on top is the brain. If that AI layer can **learn your project and carry skills across sessions** — like [Hermes Agent](https://hermes-agent.nousresearch.com) — the pairing compounds: protocols govern *how to reason* and *what to verify*, while the agent's skills carry the domain how-to and improve over time. It works with any AI; Hermes is just the closest fit.

```bash
research-os hermes add     # wire Research OS into Hermes, then ask:
                           # "set up my AI for this project"
```

→ The `guidance/agent_setup` protocol walks the whole setup. Works with Claude Code, Cursor, a bare API, or Hermes.

---

## Why trust the output

| The worry | The guarantee |
|---|---|
| AI invented a citation | Verified against four databases; unverifiable ones dropped. |
| AI invented a number | Every claim traces to a real `workspace/` file or synthesis blocks. |
| Script too big to review | Atomic, content-hash-cached sub-steps; edit one, re-run only what's affected. |
| Context lost between sessions | Decisions / hypotheses / dead-ends / drafts persist on disk. |
| Figure drifts from its caption | Each figure ships with caption + plain-English summary + provenance sidecar (script, seed, library versions). |
| Pre-registered plan silently changed | The analysis plan is content-hashed; every deviation surfaces at synthesis. |
| Negative results vanish | First-class workflow for refuted / underpowered / abandoned findings. |
| Pre-submission anxiety | A final check runs every gate a journal will — verdict + punch list. |

→ Full release history: **[CHANGELOG.md](CHANGELOG.md)**

---

## Documentation

| If you're… | Read this |
|---|---|
| **New here** | [docs/START.md](docs/START.md) — install + first project in ~15 min |
| **Looking for an example** | [docs/SCENARIOS.md](docs/SCENARIOS.md) — seven complete worked projects · [docs/USE_CASES.md](docs/USE_CASES.md) — what to say for what you want |
| **Going deep** | [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) — the full workflow guide |
| **Wiring an IDE** | [docs/SETUP.md](docs/SETUP.md) — Claude Code, Cursor, VS Code, etc. |
| **Stuck** | [docs/FAQ.md](docs/FAQ.md) — common questions |
| **Building a tool, not analysing data** | [docs/TOOL_BUILDER.md](docs/TOOL_BUILDER.md) — tool_build mode end to end |
| **Curious about a protocol** | [docs/PROTOCOLS.md](docs/PROTOCOLS.md) — every workflow with triggers + quality bars |
| **Looking up a tool** | [docs/TOOLS.md](docs/TOOLS.md) — every MCP tool with examples |
| **Understanding how it's built** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the core, the daemon, the seam between them |
| **Running long / enforced jobs** | [docs/DAEMON.md](docs/DAEMON.md) — the optional enforcement daemon |
| **Sharing a finished project** | [docs/SHARING.md](docs/SHARING.md) — share-safe zip + GitHub paths |
| **Contributing a protocol** | [docs/PROTOCOL_DOCTRINE.md](docs/PROTOCOL_DOCTRINE.md) — the scaffold-not-script principle |
| **Driving the AI side** | [docs/AI_GUIDE.md](docs/AI_GUIDE.md) — what the AI itself reads |

Doc index: **[docs/README.md](docs/README.md)**

---

## Tune how the AI behaves

One optional file — `inputs/researcher_config.yaml` — controls everything. Every field has a sensible default. The two that matter most:

```yaml
interaction:
  quality_gate_policy: enforce          # enforce | allow_override | warn_only
  ambiguity_posture: ask_when_uncertain # vs take_best_default
```

You can change these mid-session just by telling the AI ("switch to autopilot", "stop asking, use your best judgment").

→ Full reference: **[RESEARCHER_GUIDE.md § config](docs/RESEARCHER_GUIDE.md#8-configuration-inputsresearcher_configyaml)**

---

## Contributing

Issues and PRs welcome.

- **Found a bug?** → [Open an issue](https://github.com/VibhavSetlur/Research-OS/issues/new?template=bug_report.md)
- **Want a feature?** → [Request one](https://github.com/VibhavSetlur/Research-OS/issues/new?template=feature_request.md)
- **Code contribution?** → [CONTRIBUTING.md](CONTRIBUTING.md) covers the workflow, branch model, and test conventions.
- **Have a question?** → [GitHub Discussions](https://github.com/VibhavSetlur/Research-OS/discussions)
- **Security report?** → [SECURITY.md](SECURITY.md)

---

## License

[MIT](LICENSE) · No telemetry · Research OS never touches your LLM provider keys (your AI IDE owns model access).

If you use Research OS in published work, citation metadata lives in [CITATION.cff](CITATION.cff).
