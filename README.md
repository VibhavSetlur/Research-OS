# Research OS

[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/VibhavSetlur/Research-OS)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![version](https://img.shields.io/badge/version-1.0.0-orange.svg)](CHANGELOG.md)

> A research operating system that turns your AI IDE into a rigorous
> research collaborator. Drop your data, talk in plain English, and
> Research OS picks the right protocol from 82, runs it through audited
> sub-task pipelines, and produces publication-grade outputs with
> verified citations and full provenance — no hallucinations leaking
> into the paper.

**Works with**: Claude Code, Claude Desktop, OpenCode, Antigravity,
Cursor, VS Code (with MCP extension), Windsurf, Continue, Aider —
anything that speaks the Model Context Protocol.
Research OS does NOT manage LLM provider keys — your IDE owns that.

---

## What you can do with Research OS

You talk; the AI picks the right workflow from 82 protocols and runs it.

### Plan + design a study

| Say… | And Research OS will… |
|---|---|
| *"do real EDA, I don't have a hypothesis yet"* | run a pre-registered exploration, cap subgroup splits, generate provisional hypotheses for confirmation later — [`exploratory_data_analysis`](docs/PROTOCOLS.md) |
| *"power analysis for the IRB"* | source the effect size assumption from literature, build a full power table + curve, write a reviewer-facing justification — [`power_analysis`](docs/PROTOCOLS.md) |
| *"design the evaluation strategy"* | pick a split that mirrors deployment, name the leakage story, pick the paired comparison test — [`evaluation_design`](docs/PROTOCOLS.md) |
| *"design the hyperparameter sweep"* | scope what hyperparams matter from literature, pick a search strategy, pin seeds + budgets, write the sweep protocol — [`hyperparameter_search_design`](docs/PROTOCOLS.md) |
| *"do a data ethics review"* | walk IRB / consent / privacy (HIPAA Safe Harbor + k-anonymity) / sharing / fairness / dual-use, produce a green / yellow / red verdict — [`data_ethics_review`](docs/PROTOCOLS.md) |
| *"freeze the analysis plan before I touch the data"* | content-hash the SAP, diff every deviation at synthesis time — [`preregistration`](docs/PROTOCOLS.md) |

### Run analyses

| Say… | And Research OS will… |
|---|---|
| *"run a baseline EDA"* | create a numbered experiment folder, write an atomic script, run it, drop figures + reports + conclusions — [`analysis_plan`](docs/PROTOCOLS.md) |
| *"benchmark random forest vs xgboost head-to-head"* | enforce equal-budget tuning, paired statistical test for the difference, report effect sizes with CIs alongside winner — [`method_comparison`](docs/PROTOCOLS.md) |
| *"audit this dataset"* | structural / completeness / distributional / duplicate / leakage / temporal / bias checks, verdict in one of four classes — [`data_quality_audit`](docs/PROTOCOLS.md) |
| *"reproduce this paper"* | inventory the authors' assets, pin the environment, rerun, build a numerical diff table, classify the verdict in one of six classes — [`reproduction_attempt`](docs/PROTOCOLS.md) |
| *"causal effect of X on Y, observational data"* | DAG + dowhy / IPW / DiD / RDD pipeline with E-value sensitivity — [`causal_inference_deep`](docs/PROTOCOLS.md) |
| *"Bayesian model with hierarchical priors"* | priors → posterior → diagnostics → posterior predictive checks → sensitivity sweep — [`bayesian_analysis`](docs/PROTOCOLS.md) |
| *"this isn't working — abandon it and try X"* | mark the folder `__DEAD_END`, capture the lesson for future steps, propose alternatives — [`dead_end_routing`](docs/PROTOCOLS.md) |

### Build figures

| Say… | And Research OS will… |
|---|---|
| *"make me a figure from this CSV"* | apply Okabe-Ito / viridis palette, ≥300 DPI, both caption sidecars, dual PNG + SVG export — [`visualization_workflow`](docs/PROTOCOLS.md) |
| *"compose figure 2 with panels A B C D"* | enforce shared scales where appropriate, consistent panel labels, write the combined caption — [`multi_panel_composition`](docs/PROTOCOLS.md) |
| *"order my figures for the paper"* | apply the cut-test, assign each kept figure to an arc position, sanity-check reading order — [`figure_narrative_arc`](docs/PROTOCOLS.md) |
| *"is this figure colour-blind safe"* | simulate deuteranopia + protanopia + tritanopia, check WCAG contrast, verify grayscale-survivability, flag colour-only categorical encoding — [`color_accessibility_audit`](docs/PROTOCOLS.md) |
| *"critique this figure"* | reviewer-style walk: chart family / encoding / caption alignment / sensitivity to alternative encoding — [`figure_critique`](docs/PROTOCOLS.md) |

### Write

| Say… | And Research OS will… |
|---|---|
| *"draft the results section"* | report numbers in full statistical form, defer interpretation, verify every figure reference resolves — [`writing_results`](docs/PROTOCOLS.md) |
| *"draft the discussion"* | walk principal-findings → comparison-to-prior-work → alternative-explanations → limitations → scope-limited implications → concrete future work — [`writing_discussion`](docs/PROTOCOLS.md) |
| *"tighten the limitations"* | enumerate from 8 categories, pair every limitation with its downstream implication, prioritise critical-first — [`writing_limitations`](docs/PROTOCOLS.md) |
| *"workshop the paper title"* | generate ≥6 alternatives across archetypes, run the substring test, shortlist 3, stress-test the winner — [`synthesis_title_workshop`](docs/PROTOCOLS.md) |
| *"draft the cover letter"* | fit + significance + suggested reviewers + disclosures, ≤400 words, one page — [`synthesis_cover_letter`](docs/PROTOCOLS.md) |
| *"draft the end matter"* | data + code availability + CRediT roles + funding + COI + acknowledgements per journal convention — [`writing_data_availability`](docs/PROTOCOLS.md) |
| *"is this ready to submit"* | final ready-to-submit gate — GREEN / YELLOW / RED + punch list — [`pre_submission_checklist`](docs/PROTOCOLS.md) |

### Synthesise deliverables

| Say… | And Research OS will… |
|---|---|
| *"draft the paper for a journal"* | IMRAD with venue profile (journal / conference / preprint / dissertation), verified citations, per-section quality gates — [`synthesis_paper`](docs/PROTOCOLS.md) |
| *"make me a conference poster"* | tikzposter PDF with QR code linking to the paper, single-headline test, billboard or classic layout — [`synthesis_poster`](docs/PROTOCOLS.md) |
| *"build a defense talk"* | Beamer / Marp / Reveal.js / PowerPoint with one of 6 audience profiles, mandatory speaker notes + Q&A backup deck — [`synthesis_slides`](docs/PROTOCOLS.md) |
| *"build a dashboard for executives"* | single-file offline HTML with sortable tables, lightbox, light/dark, print stylesheet — self-tested via Playwright suite — [`synthesis_dashboard`](docs/PROTOCOLS.md) |
| *"make a one-pager handout"* | printable A4/Letter with QR code, single headline + one figure, 5 audience profiles — [`synthesis_handout`](docs/PROTOCOLS.md) |
| *"draft an R01 narrative"* | Specific Aims first, Approach ≥1500 words, every Aim has milestones + pitfalls + alternatives, ≥15 verified citations — [`synthesis_grant`](docs/PROTOCOLS.md) |
| *"write a lay summary for the public"* | non-expert audience with reading-grade cap, jargon replaced, every number paired with an anchor comparison — [`synthesis_lay_summary`](docs/PROTOCOLS.md) |
| *"weekly update for my PI"* | sourced from the diff since the last update, blockers + ask explicit, one file per update so the chain becomes a project diary — [`synthesis_progress_update`](docs/PROTOCOLS.md) |
| *"draft the null findings companion"* | publishable companion for refuted / underpowered / abandoned (fights the file-drawer problem) — [`synthesis_null_findings`](docs/PROTOCOLS.md) |
| *"we already analysed this, just write it up"* | build a shadow workspace step, anchor synthesis to prior artefacts, stamp a provenance ceiling into the deliverable — [`synthesis_from_inputs`](docs/PROTOCOLS.md) |

### Read + understand

| Say… | And Research OS will… |
|---|---|
| *"review this paper"* | 20-40 min critical appraisal, three strengths + five concerns + verdict — [`quick_paper_review`](docs/PROTOCOLS.md) |
| *"journal club on these three papers"* | comparison matrix at parallel depth, common ground + disagreements with proposed drivers — [`comparative_paper_review`](docs/PROTOCOLS.md) |
| *"teach me mixed-effects models before I use them"* | layered explanation (intuition → mechanics → caveats), literature-grounded, reading list — [`methodological_consultation`](docs/PROTOCOLS.md) |
| *"find papers about X"* | multi-database search (Crossref + Semantic Scholar + PubMed + arXiv) + forward-citation walk + predatory-venue flagging — [`literature_search`](docs/PROTOCOLS.md) |
| *"do a systematic review of Y"* | full PRISMA flow with screening + dedup + GRADE evidence synthesis — [`systematic_review`](docs/PROTOCOLS.md) |

### Audit + ship

| Say… | And Research OS will… |
|---|---|
| *"audit my workspace"* | master quality audit — step completeness + code quality + prose quality + claim grounding + preregistration diff — [`audit_and_validation`](docs/PROTOCOLS.md) |
| *"check reproducibility"* | per-step env snapshot, seed verification, output hashing, Dockerfile generation, optional full clean-room rerun — [`reproducibility`](docs/PROTOCOLS.md) |
| *"vet this analysis script"* | code review for correctness / leakage / reproducibility — [`code_review`](docs/PROTOCOLS.md) |
| *"respond to reviewers"* | parse the reviewer report, classify each comment, draft the rebuttal letter with line refs — [`peer_review_response`](docs/PROTOCOLS.md) |
| *"send to a collaborator"* | write a `COLLABORATOR.md` in their vocabulary, package a share-safe zip, verify reproduction first — [`collaboration_handoff`](docs/PROTOCOLS.md) |
| *"wrap up the session"* | snapshot the workspace, write a fresh-AI-readable handoff doc with running tasks + hypotheses + dead-end lessons — [`chat_handoff`](docs/PROTOCOLS.md) |
| *"push back if you disagree with this plan"* | structured AI pushback (BLOCKER / CAUTION / CONSIDERATION) — grounded in evidence, max two rounds then defer — [`constructive_disagreement`](docs/PROTOCOLS.md) |

For the full role × goal × output map, see [docs/USE_CASES.md](docs/USE_CASES.md).
For every protocol with triggers and quality bars,
see [docs/PROTOCOLS.md](docs/PROTOCOLS.md).

---

## Install + first project (60 seconds)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"

mkdir my-project && cd my-project
research-os init                                # only command per project
```

Open your AI IDE on the folder. The MCP server auto-launches.
Drop your data into `inputs/raw_data/`, papers into `inputs/literature/`,
notes into `inputs/context/`. Then in the chat:

```
> fill out the intake
> what should I do next?
> run a baseline EDA
> draft the paper for a journal submission
```

**The MCP server is global.** Install once; the same `research-os`
binary serves every project. `research-os init` is the only per-project
command.

Need help? → [`docs/START.md`](docs/START.md) (5-minute install + first
project + cheatsheet) · [`docs/SETUP.md`](docs/SETUP.md) (per-IDE
wiring + troubleshooting).

---

## How it works

```
AI IDE  (Claude Code / OpenCode / Antigravity / Cursor / Claude Desktop /
         VS Code / Windsurf / Continue / Aider)
   │ MCP stdio
   ▼
research-os MCP server  (Python — ONE global process)
   │
   │  Per-request project resolution:
   │   1. $RESEARCH_OS_WORKSPACE (IDE sets this to ${workspaceFolder})
   │   2. cwd walked up to .os_state/
   │   3. cwd as fallback
   │
   ├── Routing      sys_boot → tool_route (L1→L2→L3) →
   │                sys_protocol_get format=summary → tool_plan_turn
   │
   ├── sys.*        workspace · state · paths · checkpoints · config ·
   │                files · repair · env · scratch · handoff ·
   │                tool_describe · active_tools · active_project · help
   │
   ├── tool.*       search · exec · audit · synthesis · tasks ·
   │                research · intake · literature · plan · sensitivity ·
   │                slurm · step_pipeline · viz · dashboard_tests ·
   │                preregister · redteam · null_findings
   │
   └── mem.*        append-only methods · analysis · citations ·
                    decisions · hypotheses
   │
   ▼
Your project files
(immutable inputs · iterative workspace · final synthesis · gitignored .os_state)
```

* **140 MCP tools** across `sys_*` / `tool_*` / `mem_*` namespaces.
* **82 YAML protocols** the AI picks from via `tool_route`.
  Hierarchical L1 → L2 → L3 routing keeps a typical session boot
  under ~1.2K tokens.
* **The AI plans and reasons; Research OS executes and enforces.**
  Research OS never calls an LLM itself — your IDE owns model access.

For the full architecture + every tool + every protocol,
see [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md).

---

## Your project layout

`research-os init` scaffolds the project so the AI has somewhere to
work and you have somewhere to drop files:

```
my-project/
│
├── inputs/                            ← IMMUTABLE — you drop files here
│   ├── raw_data/                      ← data files (CSV / parquet / FASTQ / ...)
│   ├── literature/                    ← PDFs of papers
│   ├── context/                       ← notes / drafts / prior reports
│   └── researcher_config.yaml         ← source of truth for AI behaviour
│                                        (every field is optional)
│
├── workspace/                         ← ACTIVE — AI lives here
│   ├── methods.md                     ← append-only method log
│   ├── analysis.md                    ← chronological narrative
│   ├── citations.md                   ← auto-generated bibliography
│   ├── 01_baseline_eda/               ← numbered experiment steps,
│   │   ├── scripts/                   ← versioned (_v1, _v2, ...)
│   │   ├── data/{input,output}/       ← input symlinks + derived data
│   │   ├── outputs/                   ← reports + figures + tables
│   │   │                                each figure ships .caption.md
│   │   │                                + .summary.md + .prov.json
│   │   ├── environment/               ← per-step requirements.txt
│   │   ├── pipeline.yaml              ← sub-task DAG for the step
│   │   ├── README.md                  ← step summary
│   │   └── conclusions.md             ← findings + decision + next
│   ├── 02_data_preparation/
│   └── scratch/                       ← AI sandbox (gitignored)
│
├── synthesis/                         ← FINAL — only when you ask
│   ├── paper.{md,tex,pdf} + references.bib
│   ├── abstract.md / discussion.md / limitations.md /
│   │   data_availability.md / cover_letter.md
│   ├── poster.{tex,pdf} + poster_qr.png
│   ├── dashboard.html                 ← single-file, offline-safe,
│   │                                    Playwright-tested
│   ├── slides.{tex,md,html,pptx}
│   ├── handout.pdf + handout_qr.png
│   ├── lay_summary.md
│   ├── progress_<date>.md             ← one file per PI update
│   └── null_findings.md
│
├── docs/                              ← research question, glossary,
│                                        domain summary, design notes
│
├── AGENTS.md                          ← canonical AI rules (every IDE reads)
├── CLAUDE.md  .cursor/  .claude/  .windsurfrules  opencode.json  ...
│                                       ← per-IDE MCP configs (auto-dropped)
└── .os_state/                         ← internal — do NOT edit by hand
```

**You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.**
Writes to `inputs/raw_data/` and `inputs/literature/` are blocked at
the server level — your data is immutable.

---

## Why use it — pain Research OS resolves

The functionality above is what Research OS DOES. The table below is
what it FIXES that bare LLM-in-an-IDE doesn't.

| Pain | What Research OS does |
|---|---|
| AI hallucinates citations | `tool_synthesize` pulls every citation from Crossref / Semantic Scholar / PubMed / arXiv; drops anything unverified; caps per section (3 abstract / 6 poster / 12 dashboard / 25 report / 40 paper) |
| AI hallucinates numbers | `tool_audit_claims` extracts every numeric claim from `synthesis/paper.md` and verifies each appears verbatim (or within 1% tolerance) in a workspace artefact. BLOCKS synthesis |
| AI guesses methodology | `tool_research_method` mandates literature grounding before any commit; `mem_decision_log` records rationale + citations; `tool_grounding_verify` audits coverage |
| AI writes 400-line one-shot scripts | `tool_plan_step` + `pipeline.yaml` force atomic versioned sub-tasks; the runner content-hash-caches so editing one stage only re-runs the affected chain |
| Researcher just wants to dump files | `tool_intake_autofill` reads `inputs/`, classifies domain, extracts question + hypotheses. Every config field is optional |
| Researcher enters mid-pipeline | `guidance/mid_pipeline_entry` classifies into 7 archetypes and routes past redundant intake |
| Researcher wants figures only, not a full analysis | `visualization/visualization_workflow` builds + polishes without the full analysis_plan loop |
| Researcher wants a talk deck | `synthesis/synthesis_slides` with 6 audience profiles + mandatory speaker notes + Q&A backup deck |
| Pre-registered analyses drift from the SAP | `tool_preregister_freeze` content-hashes the SAP before data; `tool_preregister_diff` surfaces every deviation at synthesis time |
| Null findings end up in the file drawer | `synthesis/synthesis_null_findings` assembles a publishable companion for refuted / underpowered / abandoned |
| Reviewer-style internal critique before submission | `tool_redteam_review` writes three personas: methodological skeptic / statistical referee / sympathetic peer |
| Pre-submission ready-to-submit gate | `audit/pre_submission_checklist` produces a GREEN / YELLOW / RED verdict + punch list |
| Long jobs on shared HPC | `tool_task_run` (real `subprocess.Popen`) backgrounds them; `tool_slurm_submit` for clusters |
| Multi-language / notebook / Quarto | First-class `.py`, `.R`, `.jl`, `.sh`, `.ipynb`, `.Rmd`, `.qmd` |
| Same project, different AI tomorrow | `sys_session_handoff` snapshots + writes a fresh-AI-readable handoff; `tool_session_resume` reconstructs intent in one call |
| 140 tools is too many for the AI to triage every turn | `tool_route` returns ~10-15 active tools per protocol; `sys_active_tools(protocol)` queries the same scope |
| Need to ship to a non-RO collaborator | `guidance/collaboration_handoff` writes a `COLLABORATOR.md` in their vocabulary and packages a share-safe zip |

---

## Documentation

Don't read all of these. Pick the one that matches what you need.

| First time | Day-to-day | Reference |
|---|---|---|
| [`docs/START.md`](docs/START.md) — install + first project + cheatsheet | [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) — full workflow walkthrough | [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md) — every protocol |
| [`docs/SETUP.md`](docs/SETUP.md) — install + per-IDE wiring | [`docs/USE_CASES.md`](docs/USE_CASES.md) — role × goal × output map | [`docs/TOOLS.md`](docs/TOOLS.md) — every MCP tool |
| [`docs/FAQ.md`](docs/FAQ.md) — common questions | [`docs/AI_GUIDE.md`](docs/AI_GUIDE.md) — for the AI itself | [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md) — for protocol authors |

Doc index: [`docs/README.md`](docs/README.md).

---

## Verify your install

```bash
python scripts/preflight.py
```

Runs 13 wiring checks (package imports, protocol loading, tool-handler
consistency, dispatcher aliases, workspace-scaffold smoke). Exits
non-zero on any failure with a clear detail dump.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — covers adding a tool, adding
or modifying a protocol (must follow the scaffold-not-script doctrine),
and the test conventions.

Issues + PRs welcome at <https://github.com/VibhavSetlur/Research-OS/issues>.

License: [MIT](LICENSE).
