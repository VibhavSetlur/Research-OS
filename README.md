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
  <a href="docs/RESEARCHER_GUIDE.md">Full guide</a> ·
  <a href="docs/FAQ.md">FAQ</a>
</p>

---

## Install

```bash
pip install "research-os[all]"
```

Then scaffold a project, open it in your AI IDE, and start talking:

```bash
mkdir my-project && cd my-project
research-os init                  # arrow-key wizard
```

See **[Use it](#use-it)** below for the full flow.

---

## What is Research OS?

An MCP server that sits between your AI coding assistant and your research project. You chat in plain English; Research OS quietly enforces the things AI tools won't enforce on their own:

- **No invented citations.** Every paper is verified via Crossref / Semantic Scholar / PubMed / arXiv before it lands in your draft. Unverifiable ones are dropped, not silently retained.
- **No invented numbers.** Every quantitative claim in your paper has to point at a real workspace file. Synthesis blocks if anything is ungrounded.
- **No 400-line unreviewable scripts.** Work is split into atomic, content-hash-cached sub-steps. Edit one; only the affected parts re-run.
- **No lost context.** Decisions, hypotheses, dead-ends, and draft revisions are recorded as you go. Tomorrow's chat resumes exactly where today's ended.

It works with the AI tools you already use — **Claude Code, Cursor, Claude Desktop, Antigravity, VS Code, Windsurf, OpenCode, Continue, Aider**. One install, one wizard, and the AI you already trust now produces work that's honest enough to publish.

---

## Three ways to work

The wizard's first question — *"What are you building?"* — sets a
**workspace mode** that reshapes the scaffold and how the AI works:

- **analysis** *(default)* — data → results → paper. Numbered experiment
  steps; "done" is grounded figures + conclusions. The classic flow the
  rest of this README describes.
- **tool_build** — you're building software (a CLI, a library, a service).
  Research OS governs the build from above (spec / decisions / eval) while
  the tool lives in its own git repo; "done" is **tests + build + eval
  passing**, not figures. → [docs/TOOL_BUILDER.md](docs/TOOL_BUILDER.md)
- **exploration** — scratch-first. Poke at the data with light gates;
  promote a probe to a real step only when it earns it.

Set it at init (`research-os init --workspace-mode <mode>`) or change it
later in `inputs/researcher_config.yaml` (`workspace.mode`).

---

## What it can do for you

No commands to memorize. Describe what you want; the AI routes to the right protocol.

**Starting a project**

> "I have a CSV of patient outcomes and three PDFs — help me get started"

The AI reads your `inputs/` folder, proposes a research question + hypotheses, surfaces relevant prior work, and asks you to confirm before any analysis starts.

**Doing the work**

> "run a baseline EDA on the patient data"

You get `workspace/01_baseline_eda/` with scripts you can read, figures with proper captions, tables, and a written conclusion linking back to your hypotheses. Numbered, cached, re-runnable.

> "compare logistic regression and gradient boosting"

A head-to-head benchmark with the same eval, same metrics, paired tests, and a clear winner — not a generic "both have tradeoffs" answer.

**Writing it up**

> "draft the discussion"

A discussion section that cites your actual results. Every cite is verified; every number traces to a real workspace file.

> "build me a dashboard" / "make a poster for next week"

The AI authors the deliverable directly — `synthesis/dashboard.html` (single-file, offline, accessible) or a Typst conference poster — following the matching synthesis protocol. Research-OS validates the AI's draft (`tool_synthesis_check`) and compiles `.typ` sources to PDF (`tool_typst_compile`). No rigid templates; the AI custom-designs each artefact.

**Shipping it**

> "is this ready to submit?"

A GREEN / YELLOW / RED verdict with a punch list — every check a journal will run, before they run it.

> "going to lunch — pick up here tomorrow"

State, plan, hypotheses, dead-ends, and active drafts persist. Tomorrow's session resumes exactly where today's ended.

→ Full catalogue: **[USE_CASES.md](docs/USE_CASES.md)** (by role · by goal · by output type)

→ See it on real projects: **[SCENARIOS.md](docs/SCENARIOS.md)** — seven complete worked examples, from a messy CSV to a published paper, with the exact prompts.

---

## What you actually see

A clean three-folder workspace. You only touch one of them.

```
my-project/
│
├── inputs/                 ← YOU drop files here (immutable; AI reads, never writes)
│   ├── raw_data/             CSVs, parquet, FASTQ, NIfTI, … the data
│   ├── literature/           PDFs of papers the project draws on
│   ├── context/              PI emails, lab notebooks, prior reports
│   └── researcher_config.yaml  (one optional config file — tunes AI behavior)
│
├── workspace/              ← AI works here (you read; the AI writes)
│   ├── 01_baseline_eda/      Each analysis step in its own numbered folder
│   │   ├── scripts/            Scripts you can read + re-run
│   │   ├── outputs/            Figures (with captions), tables, reports
│   │   ├── README.md           Past decisions, inputs, outputs, takeaway
│   │   └── conclusions.md      Detailed findings + tables + interpretations
│   ├── methods.md            Project-wide append-only methods narrative
│   ├── analysis.md           Decision log + dead-ends + rationale
│   ├── citations.md          Verified citations only
│   └── logs/                 Every audit pass + every quality-gate override
│
└── synthesis/              ← AI writes the deliverables here
    ├── paper.typ             AI-authored Typst source
    ├── paper.pdf             Compiled via tool_typst_compile
    ├── slides.typ            AI-authored Touying deck
    ├── slides.pdf            Compiled
    ├── poster.typ            AI-authored Typst poster
    ├── poster.pdf            Compiled
    ├── dashboard.html        AI-authored single-file (offline, accessible)
    ├── biblio.yml            Hayagriva citations
    └── figures/              Curated focal figures (PNG + .caption.md)
```

The split has a single principle: **you own `inputs/`, the AI owns the rest, and nothing exists until you ask for it**. A fresh project isn't pre-cluttered with empty folders; `workspace/01_*` only appears the first time you run an analysis step.

→ Deeper tour: **[RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md)**

---

## Use it

**1. Install** — one install serves every project.

```bash
pip install "research-os[all]"
```

Upgrade:

```bash
pip install --upgrade "research-os[all]"
```

**2. Scaffold a project** — arrow-key wizard.

```bash
mkdir my-project && cd my-project
research-os init
```

**3. Check health** (optional).

```bash
research-os doctor
```

**4. Open the folder in your AI IDE and talk.** The MCP server auto-launches.

```
> fill out the intake
> run a baseline analysis on the patient data
> what should I do next?
> draft the discussion
> is this ready to submit?
```

→ Full walkthrough: **[START.md](docs/START.md)** · Per-IDE wiring: **[SETUP.md](docs/SETUP.md)** · CLI reference: **[CLI.md](docs/CLI.md)**

---

## What's inside

* **MCP tools** in three namespaces — `sys_*` (system / workspace /
  files / state), `tool_*` (research work), `mem_*` (append-only memory).
  Family-level consolidation (`tool_audit`, `tool_search`,
  `tool_step`, `tool_lessons`, `mem_log`, etc.) dispatches by `scope` /
  `operation` / `dimension`. Synthesis is **AI-direct authoring**: the
  AI writes `paper.typ` / `slides.typ` / `poster.typ` / `dashboard.html`
  directly, with `tool_synthesize_plan` for inspection, `tool_synthesis_check`
  for validation, and `tool_typst_compile` for PDF rendering.
* **Core protocols** + bundled domain packs (humanities,
  qualitative, theory_math, wet_lab, engineering) the AI picks from
  via `tool_route`. Every protocol carries
  `scope_tags: {domain, audience, workflow_shape}` and a `tier`
  annotation so the router can filter by context.
* **In-tree adapter packs** — `slurm`, `nextflow`, `snakemake`,
  `cytoscape`, `redcap`, `synapse` — bridge Research OS to common
  external systems via plugin hooks.
  All domain packs and infrastructure adapters are bundled in the
  wheel and always loaded; the `pip install research-os[<name>]`
  extras are reserved no-ops today (names held for a future PyPI split).
* **MCP `instructions` field** shipped at handshake — compliant
  clients (Claude Code, Cursor, Cline, etc.) see the canonical boot
  sequence (`sys_boot → tool_route → sys_protocol_get →
  sys_active_tools`) without the AI having to discover it.
* **Cheap-by-default token costs.** `sys_protocol_get` returns
  `format='summary'` (~3K chars vs ~12-25K for full YAML) — 5-10×
  cheaper per-turn load. `sys_active_tools(protocol_name)` returns a
  scoped tool shortlist instead of the full catalogue.
* **Structured tool responses.** Every handler returns an envelope
  with `status` / `payload` / `audit_findings` /
  `next_recommended_call` / `tier_transition` / `tokens_estimate` /
  `ro_version` — a literal next-call hint on every reply.
* **WHAT / WHY / NEXT errors.** Dispatcher catches typed exceptions
  and renders a structured error envelope with did-you-mean
  suggestions on unknown tool + protocol typos.
* **Audit-as-data.** Every audit emits a JSON companion alongside
  its Markdown report. Findings live in a cross-audit append-only
  ledger (`workspace/logs/.audit_findings.jsonl`) with stable UUIDv5
  ids, queryable via `tool_audit_findings(operation='query'|'diff')`.
  Synthesis BLOCK-gates on unresolved BLOCK findings.

→ **[CHANGELOG.md](CHANGELOG.md)** for the full release history.

---

## Why use it

Research OS exists because AI coding assistants are *fast* but they
*cheat* — they invent citations that don't exist, they hallucinate p-values,
they write 400-line scripts you can't audit, and they lose track of what
they decided last week. The honest fix isn't a better prompt; it's a
system that won't let any of those things land in your final paper.

| The problem | What Research OS does about it |
|---|---|
| AI invents citations | Every cite is verified against Crossref / Semantic Scholar / PubMed / arXiv. Unverifiable ones are dropped. |
| AI invents numbers | Every quantitative claim in your paper traces back to a real workspace file. Synthesis blocks if anything is ungrounded. |
| AI writes massive unreviewable scripts | Work is split into atomic, content-hash-cached sub-tasks. Edit one; only the affected parts re-run. |
| AI loses context between sessions | Decisions, hypotheses, dead-ends, and drafts persist. Tomorrow's chat picks up where today's ended. |
| Figures drift from their captions | Every figure ships with a caption, a plain-English summary, a provenance sidecar (script + seed + library versions), and an SVG companion. |
| "Pre-registered analysis" silently changes | The Statistical Analysis Plan is content-hashed. Every deviation surfaces at synthesis time. |
| Negative results vanish into the file drawer | First-class workflow for refuted / underpowered / abandoned findings. |
| Pre-submission anxiety | Final check walks every gate a journal will run — verdict + actionable punch list. |

---

## Documentation

| If you're… | Read this |
|---|---|
| **New here** | [docs/START.md](docs/START.md) — install + first project in 15 min |
| **Looking for an example** | [docs/SCENARIOS.md](docs/SCENARIOS.md) — seven complete worked projects · [docs/USE_CASES.md](docs/USE_CASES.md) — what to say for what you want |
| **Going deep** | [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) — the full workflow guide |
| **Wiring an IDE** | [docs/SETUP.md](docs/SETUP.md) — Claude Code, Cursor, VS Code, etc. |
| **Stuck** | [docs/FAQ.md](docs/FAQ.md) — common questions |
| **Building a tool, not analysing data** | [docs/TOOL_BUILDER.md](docs/TOOL_BUILDER.md) — tool_build mode: spec → implement → test → ship |
| **Curious about a protocol** | [docs/PROTOCOLS.md](docs/PROTOCOLS.md) — every workflow with triggers + quality bars |
| **Looking up a tool** | [docs/TOOLS.md](docs/TOOLS.md) — every MCP tool with examples |
| **Upgrading from v1.x** | [CHANGELOG.md](CHANGELOG.md) — see the `[2.0.0]` section for the v1 → v2 surface map |
| **Sharing a finished project** | [docs/SHARING.md](docs/SHARING.md) — share-safe zip + GitHub paths |
| **Contributing a protocol** | [docs/PROTOCOL_DOCTRINE.md](docs/PROTOCOL_DOCTRINE.md) — the scaffold-not-script principle |
| **Driving the AI side** | [docs/AI_GUIDE.md](docs/AI_GUIDE.md) — what the AI itself reads |

Doc index: **[docs/README.md](docs/README.md)**

---

## Tune how the AI behaves

A single file — `inputs/researcher_config.yaml` — controls everything.
Every field is optional. The two that matter most:

```yaml
interaction:
  quality_gate_policy: enforce        # enforce | allow_override | warn_only
  ambiguity_posture: ask_when_uncertain  # vs take_best_default
```

→ Full reference: **[RESEARCHER_GUIDE.md § config](docs/RESEARCHER_GUIDE.md#8-configuration-inputsresearcher_configyaml)**

---

## Contributing

Issues and PRs welcome.

- **Found a bug?** → [Open an issue](https://github.com/VibhavSetlur/Research-OS/issues/new?template=bug_report.md)
- **Want a feature?** → [Request one](https://github.com/VibhavSetlur/Research-OS/issues/new?template=feature_request.md)
- **Code contribution?** → [CONTRIBUTING.md](CONTRIBUTING.md) covers the workflow, branch model, and test conventions.
- **Asking a question?** → [GitHub Discussions](https://github.com/VibhavSetlur/Research-OS/discussions)
- **Security report?** → [SECURITY.md](SECURITY.md)

---

## License

[MIT](LICENSE) · Research OS does not collect telemetry · Research OS does not manage LLM provider keys (your AI IDE owns model access).

If you use Research OS in published work, citation info lives in [CITATION.cff](CITATION.cff).
