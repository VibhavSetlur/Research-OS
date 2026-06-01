# Research OS

[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/VibhavSetlur/Research-OS)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![version](https://img.shields.io/badge/version-1.0.0-orange.svg)](CHANGELOG.md)

**An MCP-native operating system for reproducible, grounded,
citation-verified research. Drop your data, talk to your AI IDE in
plain English, get back rigorous pipelines, publication-grade figures
with provenance, plain-English captions, and a self-tested dashboard
you can email — without hallucinations leaking into the paper.**

Works with any MCP-capable AI IDE: Claude Code, OpenCode, Antigravity,
Cursor, Claude Desktop, VS Code, Windsurf, Continue, Aider. Research
OS does NOT manage LLM provider keys — your IDE owns that.

---

## Install + first project (60 seconds)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"

mkdir my-project && cd my-project
research-os init                                # only command per project
```

Open your AI IDE on the folder. The MCP server auto-launches.
Drop your data into `inputs/raw_data/`, papers into `inputs/literature/`,
notes into `inputs/context/`. Then type:

> *"fill out the intake"* → AI reads everything, proposes a research
> question + hypotheses.
> *"what should I do next?"* → iterative planning, grounded in real
> literature.
> *"run a baseline EDA"* → creates a numbered experiment folder, runs
> the script, writes conclusions.
> *"draft the paper for a journal submission"* → IMRAD synthesis with
> verified citations + per-section quality gates.

**The MCP server is global.** Install once; the same `research-os`
binary serves every project. `research-os init` is the only per-project
command.

---

## What it gives you

| Pain | What Research OS does |
|---|---|
| AI hallucinates citations | `tool_synthesize` pulls every citation from Crossref / Semantic Scholar / PubMed / arXiv; drops anything unverified; caps per section (3 abstract / 6 poster / 12 dashboard / 25 report / 40 paper). |
| AI hallucinates numbers | `tool_audit_claims` extracts every numeric claim from `synthesis/paper.md` and verifies each appears verbatim (or within 1% tolerance) in a workspace artefact. BLOCKS synthesis. |
| AI guesses methodology | `tool_research_method` mandates literature grounding before any commit; `mem_decision_log` records the rationale + citations. |
| AI writes 400-line one-shot scripts | `tool_plan_step` + `pipeline.yaml` force atomic versioned sub-tasks. |
| Researcher just wants to dump files | `tool_intake_autofill` reads `inputs/`, classifies domain, extracts question + hypotheses. Every config field is optional. |
| Researcher enters mid-pipeline | `guidance/mid_pipeline_entry` classifies into 7 archetypes (DATA-READY / ANALYSES-READY / FIGURES-READY / SYNTHESIS-READY / PRIOR-RO-PROJECT / CONCEPTUAL / MIXED) and routes past redundant intake. |
| Researcher just wants figures | `visualization/visualization_workflow` builds + polishes figures without the full analysis loop. |
| Researcher just wants a talk deck | `synthesis/synthesis_slides` with 6 audience profiles + mandatory speaker notes + Q&A backup deck. |
| Researcher just wants a lay summary | `synthesis/synthesis_lay_summary` with 6 audience profiles + reading-grade cap + anchor comparisons. |
| Long jobs on shared HPC | `tool_task_run` (real `subprocess.Popen`) backgrounds them; `tool_slurm_submit` for clusters. |
| Multi-language / notebook / Quarto | First-class `.py`, `.R`, `.jl`, `.sh`, `.ipynb`, `.Rmd`, `.qmd`. |
| Iterating on direction | `guidance/iterative_planning` reads state + searches literature/tools + proposes 2-3 concrete options. |
| Multiple hypotheses | `mem_hypothesis_*` maintains a ledger; every step declares which IDs it touches. |
| Same project, different AI tomorrow | `sys_session_handoff` snapshots + writes a fresh-AI-readable handoff; `tool_session_resume` reconstructs intent in one call. |
| 140 tools is too many for the AI to triage every turn | `tool_route` returns ~10-15 active tools per protocol; `sys_active_tools(protocol)` queries the same scope. |
| Pre-registered analyses drift from the SAP | `tool_preregister_freeze` content-hashes the SAP before data; `tool_preregister_diff` surfaces every deviation at synthesis time. |
| Null findings end up in the file drawer | `synthesis/synthesis_null_findings` assembles a publishable companion for refuted / underpowered / abandoned. |
| Reviewer-style internal critique | `tool_redteam_review` writes three personas: methodological skeptic / statistical referee / sympathetic peer. |
| Need to ship to a non-RO collaborator | `guidance/collaboration_handoff` writes a `COLLABORATOR.md` in their vocabulary and packages a share-safe zip. |
| Need to respond to peer review | `guidance/peer_review_response` parses the report, classifies each comment, drafts the rebuttal letter with line refs. |
| Pre-submission ready-to-submit gate | `audit/pre_submission_checklist` produces a GREEN / YELLOW / RED verdict + punch list. |

---

## Architecture (45 seconds)

```
AI IDE  (Claude Code / OpenCode / Antigravity / Cursor / Claude Desktop /
         VS Code / Windsurf / Continue / Aider)
   │ MCP stdio
   ▼
research-os MCP server (Python — ONE global process)
   │  resolves active project per request:
   │   1. $RESEARCH_OS_WORKSPACE (set by IDE MCP config to ${workspaceFolder})
   │   2. cwd walked up to .os_state/
   │   3. cwd as fallback
   │
   ├── Routing layer   sys_boot → tool_route (L1→L2→L3) →
   │                   sys_protocol_get format=summary → tool_plan_turn
   ├── sys.*           workspace, state, paths, checkpoints, config,
   │                   files, repair, env, scratch, handoff,
   │                   tool_describe, active_tools, active_project, help
   ├── tool.*          search, exec, audit, synthesis, tasks, research,
   │                   intake, literature, plan, sensitivity, slurm,
   │                   step_pipeline, viz, dashboard_tests, preregister,
   │                   redteam, null_findings
   └── mem.*           append-only methods, analysis, citations,
                       decisions, hypotheses
   │
   ▼
Workspace files
(immutable inputs · iterative workspace · final synthesis · gitignored .os_state)
```

140 MCP tools across `sys_*` / `tool_*` / `mem_*`. 82 YAML protocols
across nine categories. Hierarchical L1 → L2 → L3 routing keeps a
typical session boot under ~1.2K tokens.

---

## Workspace layout

```
my-project/
├── AGENTS.md                          # canonical AI rules (every IDE reads this)
├── inputs/                            # IMMUTABLE — you provide
│   ├── raw_data/                      # data files (CSV / parquet / FASTQ / ...)
│   ├── literature/                    # PDFs
│   ├── context/                       # notes, drafts, prior reports
│   └── researcher_config.yaml         # source of truth for AI behaviour
├── docs/                              # human-readable: question, glossary
├── workspace/                         # ACTIVE — experiments live here
│   ├── methods.md / analysis.md / citations.md
│   ├── NN_<slug>/                     # numbered experiment steps
│   │   ├── scripts/, data/, outputs/, environment/, literature/
│   │   ├── README.md, conclusions.md, pipeline.yaml
│   └── scratch/                       # AI sandbox (gitignored)
├── synthesis/                         # FINAL outputs — only when requested
│   ├── paper.{md,tex,pdf} + references.bib
│   ├── abstract.md / discussion.md / limitations.md / data_availability.md
│   ├── poster.{tex,pdf} + poster_qr.png
│   ├── dashboard.html (single-file, offline-safe)
│   ├── slides.{tex,md,html,pptx}
│   ├── handout.pdf + handout_qr.png
│   ├── lay_summary.md / cover_letter.md / progress_<date>.md
│   └── null_findings.md
└── .os_state/                         # internal — do NOT edit
```

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.
Writes under `inputs/raw_data/` and `inputs/literature/` are blocked
server-side.

---

## Documentation

| Doc | Read when |
|---|---|
| [`docs/START.md`](docs/START.md) | First time. Install + first project + cheatsheet in one. |
| [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) | Full workflow walkthrough. Read after first output. |
| [`docs/USE_CASES.md`](docs/USE_CASES.md) | Role × goal × output map — which protocol for which moment. |
| [`docs/SETUP.md`](docs/SETUP.md) | Install + per-IDE MCP wiring + troubleshooting. |
| [`docs/FAQ.md`](docs/FAQ.md) | Common questions. |
| [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md) | Catalogue of all 82 protocols. |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Catalogue of all 140 MCP tools. |
| [`docs/AI_GUIDE.md`](docs/AI_GUIDE.md) | Operating manual for the AI driving Research OS. |
| [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md) | Scaffold-not-script principle (for protocol authors). |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Adding tools / protocols / fixing bugs. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history. |

---

## Verify your install

```bash
python scripts/preflight.py
```

Runs 13 checks (package imports, protocol loading, tool/handler
consistency, dispatcher aliases, workspace-scaffold smoke). Exits
non-zero on any failure with a clear detail dump.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues + PRs welcome at
<https://github.com/VibhavSetlur/Research-OS/issues>.

License: [MIT](LICENSE).
