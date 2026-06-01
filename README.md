<p align="center">
  <img src="assets/logo.svg" alt="Research OS — grounded · cited · auditable" width="520">
</p>

# Research OS

[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/VibhavSetlur/Research-OS)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![version](https://img.shields.io/badge/version-1.0.0-orange.svg)](CHANGELOG.md)

> A research operating system that turns your AI IDE into a rigorous
> research collaborator. Drop your data, talk in plain English, and
> Research OS picks the right protocol, runs it through audited
> sub-task pipelines, and produces publication-grade outputs with
> verified citations and full provenance — no hallucinations leaking
> into the paper.

Works with: **Claude Code, Claude Desktop, OpenCode, Antigravity,
Cursor, VS Code (with MCP), Windsurf, Continue, Aider** — anything
that speaks the Model Context Protocol. Research OS does NOT manage
LLM provider keys; your IDE owns that.

---

## Install + your first project (60 seconds)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"

mkdir my-project && cd my-project
research-os init                    # arrow-key wizard (default)
# or: research-os init my-project --yes    # one-shot, no prompts (CI / scripts)
```

`init` is the only per-project command. The 7-step wizard:

* asks where the project lives, what it's called, which AI IDEs you use,
* lets you **paste a Slack thread / email / PI message** that gets parsed
  + saved straight into `inputs/context/` with provenance frontmatter,
* lets you **paste arXiv IDs · DOIs · PDF URLs** and downloads them into
  `inputs/literature/` (Unpaywall for DOIs; manual-link fallback when
  not open-access),
* offers to **symlink existing data files** in the target folder into
  `inputs/raw_data/`,

Arrow keys + Space to navigate, Tab to autocomplete paths, Esc to cancel.
Finished in under a minute.

Open your AI IDE on the folder — the MCP server auto-launches. Drop
files into `inputs/raw_data/`, papers into `inputs/literature/`,
notes into `inputs/context/`. Then in the chat:

```
> fill out the intake
> what should I do next?
> run a baseline EDA
> draft the paper for a journal submission
```

**The MCP server is global.** Install once; the same `research-os`
binary serves every project. `research-os init` is the only
per-project command.

Need step-by-step setup or per-IDE wiring? →
[`docs/START.md`](docs/START.md) · [`docs/SETUP.md`](docs/SETUP.md) ·
[`docs/FAQ.md`](docs/FAQ.md).

---

## What it does

You talk; the AI picks the right workflow from **87 protocols** and
runs it through **140 MCP tools** that enforce real quality gates.

### Across 7 capability groups (linked to triggers + outputs)

| | What you say · what you get |
|---|---|
| **Plan + design** | EDA + hypothesis generation · power analysis · evaluation design (split / CV / paired test) · hyperparameter sweep design · data ethics review (IRB / privacy / fairness) · preregistration |
| **Run analyses** | iterative experiments with provenance · head-to-head method comparison · data-quality audit · reproduction of published work · causal / Bayesian / time-series / ML / clinical / qualitative / mixed-methods pipelines · dead-end routing |
| **Build figures** | full viz workflow · multi-panel composition (Figure 2 = A/B/C/D) · figure narrative arc · colour-blind + WCAG accessibility audit · reviewer-style figure critique |
| **Write** | per-section drafting (methods · results · discussion · limitations · end-matter with CRediT) · title workshop · cover letter · pre-submission ready-to-submit gate |
| **Synthesise** | IMRAD paper · abstract · poster + QR · talk slides (lab / conference / defense) · self-tested dashboard · printable handout + QR · grant narrative · lay summary · PI progress update · null-findings companion · synthesis from inputs (no in-RO analysis) |
| **Read + understand** | quick paper critique · multi-paper comparative review · methodological consultation (teach me X) · literature search with forward-citation walk · full PRISMA systematic review |
| **Audit + ship** | quality audit · reproducibility verification · code review · peer-review response · collaboration handoff (share-safe zip) · structured AI pushback when grounded evidence disagrees |

→ [**docs/USE_CASES.md**](docs/USE_CASES.md) maps your role × goal ×
output to the right protocol.
→ [**docs/PROTOCOLS.md**](docs/PROTOCOLS.md) catalogues every protocol
with triggers + quality bars.

---

## How it works

```
AI IDE  (Claude Code / Claude Desktop / OpenCode / Antigravity /
         Cursor / VS Code / Windsurf / Continue / Aider)
   │ MCP stdio
   ▼
research-os MCP server  (Python — ONE global process)
   │
   ├── Routing      sys_boot → tool_route (L1→L2→L3) → tool_plan_turn
   ├── sys.*        workspace · state · paths · checkpoints · config ·
   │                files · repair · env · scratch · handoff · help
   ├── tool.*       search · exec · audit · synthesis · tasks ·
   │                research · intake · literature · plan · sensitivity ·
   │                slurm · step_pipeline · viz · preregister · redteam
   └── mem.*        append-only methods · analysis · citations ·
                    decisions · hypotheses
   │
   ▼
Your project files
(immutable inputs · iterative workspace · final synthesis)
```

**The AI plans and reasons; Research OS executes and enforces.**
Research OS never calls an LLM itself. For the full architecture +
every tool + every protocol, see
[`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md).

---

## Your project layout

`research-os init` creates this skeleton; the AI fills the rest as
you work.

```
my-project/
├── inputs/                  ← IMMUTABLE — you drop files here
│   ├── raw_data/                  data: CSV / parquet / FASTQ / ...
│   ├── literature/                PDFs of papers
│   ├── context/                   notes / drafts / prior reports
│   └── researcher_config.yaml     AI behaviour (every field optional)
│
├── workspace/               ← ACTIVE — AI lives here
│   ├── methods.md / analysis.md / citations.md
│   ├── 01_baseline_eda/           numbered experiment steps
│   │   ├── scripts/  (_v1, _v2, ...)
│   │   ├── data/{input,output}/
│   │   ├── outputs/{reports,figures,tables}/
│   │   │     each figure ships .caption.md + .summary.md + .prov.json
│   │   ├── environment/  (per-step requirements.txt)
│   │   ├── pipeline.yaml          sub-task DAG for the step
│   │   └── conclusions.md
│   └── scratch/                   AI sandbox (gitignored)
│
├── synthesis/               ← FINAL — only when you ask
│   paper · abstract · poster + QR · dashboard · slides ·
│   handout + QR · lay_summary · cover_letter · progress_<date>
│
├── AGENTS.md                ← canonical AI rules (every IDE reads)
├── CLAUDE.md  .cursor/  .claude/  .windsurfrules  ...
│                              per-IDE MCP configs (auto-dropped)
└── .os_state/               ← internal — do NOT edit by hand
```

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.

---

## Why use it — pain Research OS resolves

| Pain | Resolution |
|---|---|
| AI hallucinates citations | `tool_synthesize` verifies every cite online; drops the rest. Per-section caps (3 abstract / 12 dashboard / 40 paper). |
| AI hallucinates numbers | `tool_audit_claims` traces every number in `paper.md` to a workspace artefact. BLOCKS synthesis. |
| AI guesses methodology | `tool_research_method` mandates literature grounding before any commit. |
| AI writes 400-line one-shot scripts | `tool_plan_step` + `pipeline.yaml` force atomic versioned sub-tasks. |
| Pre-registered analyses drift | `tool_preregister_freeze` content-hashes the SAP; `_diff` surfaces every deviation. |
| Null findings → file drawer | `synthesis/synthesis_null_findings` publishable companion for refuted / underpowered / abandoned. |
| Researcher enters mid-pipeline | `guidance/mid_pipeline_entry` classifies into 7 archetypes; skips redundant intake. |
| The full tool surface is too many to triage every turn | `tool_route` returns ~10-15 active tools per protocol via `sys_active_tools`. |
| Same project, different AI tomorrow | `sys_session_handoff` snapshots + writes a fresh-AI-readable handoff; `tool_session_resume` reconstructs intent in one call. |
| Long jobs on shared HPC | `tool_task_run` backgrounds them; `tool_slurm_submit` for clusters. |

For the full list, see [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) § Power-user patterns.

---

## Documentation

Pick the one that matches what you need.

| First time | Day-to-day | Reference |
|---|---|---|
| [`docs/START.md`](docs/START.md) — install + first project + cheatsheet | [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) — full workflow walkthrough | [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md) — every protocol |
| [`docs/SETUP.md`](docs/SETUP.md) — install + per-IDE wiring | [`docs/USE_CASES.md`](docs/USE_CASES.md) — role × goal × output map | [`docs/TOOLS.md`](docs/TOOLS.md) — every MCP tool |
| [`docs/FAQ.md`](docs/FAQ.md) — common questions | [`docs/SHARING.md`](docs/SHARING.md) — zip + GitHub paths for sending to collaborators | [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md) — for protocol authors |
| | [`docs/AI_GUIDE.md`](docs/AI_GUIDE.md) — for the AI itself | |

Doc index: [`docs/README.md`](docs/README.md).

---

## Verify your install

```bash
python scripts/preflight.py            # 13 wiring checks
pytest -q                              # 380 tests, ~8 s
ruff check src/ tests/ scripts/
```

---

## Contributing + License

See [CONTRIBUTING.md](CONTRIBUTING.md) — covers adding a tool, adding
or modifying a protocol (must follow the scaffold-not-script
doctrine), and the test conventions. Issues + PRs welcome at
<https://github.com/VibhavSetlur/Research-OS/issues>.

License: [MIT](LICENSE).
