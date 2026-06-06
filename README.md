<p align="center">
  <img src="assets/logo.svg" alt="Research OS — grounded · cited · auditable" width="520">
</p>

<h1 align="center">Research OS</h1>

<p align="center">
  <a href="https://pypi.org/project/research-os/"><img src="https://img.shields.io/pypi/v/research-os.svg?color=orange&cacheSeconds=300" alt="PyPI"></a>
  <a href="https://pypi.org/project/research-os/"><img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT"></a>
  <a href="https://github.com/VibhavSetlur/Research-OS/actions/workflows/test.yml"><img src="https://github.com/VibhavSetlur/Research-OS/actions/workflows/test.yml/badge.svg" alt="tests"></a>
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/release-v2.1.1-purple.svg" alt="v2.1.1"></a>
</p>

<p align="center">
  <strong>Talk to your AI in plain English. Get publication-grade research back.</strong><br>
  No hallucinated citations. No fabricated numbers. Every figure traceable to the script that made it.
</p>

<p align="center">
  <a href="docs/START.md">Quick start</a> ·
  <a href="docs/USE_CASES.md">What you can ask for</a> ·
  <a href="docs/RESEARCHER_GUIDE.md">Full guide</a> ·
  <a href="docs/FAQ.md">FAQ</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

## What is Research OS?

It's a layer that sits between **you**, **your data**, and **whatever AI
coding assistant you already use** (Claude Code, Cursor, Claude Desktop,
Antigravity, VS Code, Windsurf, OpenCode, Continue, Aider).

You drop files in a folder. You chat with your AI. Research OS quietly
makes sure the AI:

- **doesn't make up citations** — every paper cited is verified online
- **doesn't make up numbers** — every figure in your paper traces back
  to a real script and a real dataset
- **doesn't write one giant unreviewable script** — work is broken into
  small, cached, reproducible steps
- **doesn't lose track** — your decisions, hypotheses, dead-ends, and
  drafts are recorded so the next chat picks up where this one ended

You get the speed of AI. The work is honest enough to publish.

---

## What it can do for you

You don't memorise commands. You just describe what you want.

| You say… | You get… |
|---|---|
| *"fill out the intake"* | The AI reads your files, proposes a research question + hypotheses, and asks you to confirm. |
| *"what should I do next?"* | A short recommended next step — sourced from your state, the literature, and any dead-ends already logged. |
| *"run a baseline EDA"* | A numbered experiment folder with scripts, figures (with captions), tables, and a written conclusion. |
| *"compare logistic regression and gradient boosting"* | A head-to-head benchmark — same eval, same metrics, paired test, clear winner. |
| *"draft the discussion"* | A draft Discussion section that cites your actual results — not invented ones. |
| *"build me a dashboard"* | A single-file HTML dashboard. Print-friendly, colour-blind safe, plays offline. |
| *"make a poster for next week"* | A LaTeX conference poster with QR code, ≥300 DPI figures, one headline message. |
| *"is this ready to submit?"* | A GREEN / YELLOW / RED verdict with a punch list — every check journals run, before they run it. |
| *"going to lunch"* | A clean handoff so tomorrow's session resumes exactly where you left off. |

→ Full catalogue: **[USE_CASES.md](docs/USE_CASES.md)** (by role · by goal · by output type)

---

## What you actually see

You open your AI IDE. The MCP server auto-connects. Your folder looks like:

```
my-project/
├── inputs/             ← you drop files here
│   ├── raw_data/         (CSVs, parquet, FASTQ, …)
│   ├── literature/       (PDFs of papers)
│   └── context/          (notes, Slack threads, PI emails)
│
├── workspace/          ← the AI works here
│   ├── 01_baseline_eda/   (each experiment in its own numbered folder)
│   ├── methods.md         (what was done, in plain English)
│   └── logs/              (every audit + every quality-gate bypass)
│
└── synthesis/          ← your finished deliverables land here
    └── paper.md           (or poster.pdf, dashboard.html, slides.pptx…)
```

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.
Things only get created when you ask for them, so a fresh project
isn't cluttered with empty folders.

→ Deeper tour: **[RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md)**

---

## How to use it — 4 steps

**1. Install once** (the server is global — it serves every project):

```bash
pip install "research-os[all]"
```

**2. Scaffold a project**:

```bash
mkdir my-project && cd my-project
research-os init                  # 6-step arrow-key wizard
```

The wizard asks where the project goes, which AI IDEs you use (it drops
the right MCP config in each), and lets you paste PDFs, DOIs, or notes
straight in.

**3. Check health** (optional but recommended):

```bash
research-os doctor                # python, conda env, IDE wiring, pack health
research-os ide list              # which IDEs are wired in this workspace
```

**4. Open the folder in your AI IDE and just talk**:

```
> what's in my inputs folder?
> fill out the intake
> run a baseline analysis on the patient data
> what should I do next?
```

That's the whole workflow.

→ Full first-hour walkthrough: **[START.md](docs/START.md)**
→ Per-IDE wiring details: **[SETUP.md](docs/SETUP.md)**

---

## What ships in v2.0.0

* **146 MCP tools** across three namespaces — `sys_*` (system / workspace /
  files / state), `tool_*` (research work), `mem_*` (append-only memory).
  Down from 344 in v1.x — consolidated families (`tool_audit`,
  `tool_dashboard`, `tool_search`, `tool_figure`, `tool_step`,
  `tool_lessons`, `mem_log`, etc.) dispatch by `scope` / `operation` /
  `dimension`. Every v1 tool name still works via 80 backward-compat
  aliases for the v2.0.x patch line.
* **117 protocols** the AI picks from via `tool_route`. Every protocol
  ships with `scope_tags: {domain, audience, workflow_shape}` and a
  `tier` annotation so the router can filter intelligently.
* **MCP `instructions` field** shipped at handshake — compliant clients
  (Claude Code, Cursor, Cline, etc.) see the canonical boot sequence
  (`sys_boot → tool_route → sys_protocol_get → sys_active_tools`)
  without the AI having to discover it.
* **`sys_protocol_get` defaults to `format='summary'`** (~3K chars
  vs ~12-25K for full YAML) — 5-10× cheaper per-turn load.
* **`tool_route` returns `recommended_action` + `why_matched` + `tier`**
  — a literal next-call string per candidate so the AI never burns a
  turn deciding what to call next.
* **`sys_active_tools(protocol_name)`** returns a 13–18-tool scoped
  shortlist (down from 146 visible) per protocol.
* **`status` + `pack` on every tool definition** — boot-visible
  `list_tools` is filtered to `status=live` (146 core/pack tools);
  aliases + deprecated names are still callable but not advertised.

→ **[CHANGELOG.md](CHANGELOG.md)** for the full release history.
  Upgrading from v1.x? See the [`[2.0.0]` section](CHANGELOG.md) for
  the surface map.

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
| **Looking for an example** | [docs/USE_CASES.md](docs/USE_CASES.md) — what to say for what you want |
| **Going deep** | [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) — the full workflow guide |
| **Wiring an IDE** | [docs/SETUP.md](docs/SETUP.md) — Claude Code, Cursor, VS Code, etc. |
| **Stuck** | [docs/FAQ.md](docs/FAQ.md) — common questions |
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

→ Full reference: **[RESEARCHER_GUIDE.md § config](docs/RESEARCHER_GUIDE.md#9-the-config-file)**

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
