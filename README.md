# Research OS

[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/VibhavSetlur/Research-OS)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**From raw data to publication-ready manuscript — a research operating 
system that runs inside your AI IDE. Drop your data,
ask in plain English, get back reproducible pipelines, publication-grade
figures with provenance, plain-English captions, and a self-tested
dashboard you can email.**

Built for researchers of any experience level. The AI does the
typing; Research OS makes sure the typing is rigorous — every figure
carries its provenance sidecar, every paper number traces back to a
workspace output, every methodological decision cites the evidence
that informed it.

Works with any MCP-capable IDE (Claude Code, OpenCode, Antigravity,
Cursor, VS Code, Windsurf, Continue, Aider). Research OS doesn't
manage LLM provider keys — your IDE owns that.

---

## What it does in one screen

* **Sub-task pipelines, not mega-scripts.** Every analytical step
  declares a `pipeline.yaml` of small, focused nodes (`ingest →
  validate → clean → fit → diagnose → visualize → report`). Topologically
  ordered, content-hash cached — edits re-run only the affected chain.
* **Provenance on every output.** Each figure / table / model emits a
  `<name>.prov.json` sidecar (PROV-O compatible) recording the script,
  input hashes, parameters, RNG seed, library versions, wall time. The
  audit gate blocks synthesis below 50% provenance coverage.
* **25 publication-grade figure kinds via one tool call.** ROC, PR,
  calibration, QQ, residual diagnostics (4-panel), partial dependence,
  forest, dot-and-whisker, ridgeline, raincloud, posterior (HDI + ROPE),
  variable importance, funnel, alluvial, hierarchical heatmap, CONSORT
  flow — all colour-blind safe, ≥300 DPI, dual PNG + SVG, with technical
  + plain-English captions.
* **Grounded reasoning (ReAct + CoVe + PROV-O + Reflexion).** Every
  decision binds to the evidence that informed it (papers / context
  files / datasets / web). Chain-of-Verification per claim. Lessons
  carry across sessions.
* **Quality gates that block bad synthesis.** Code quality (ruff +
  AST), prose quality (hedging + reporting-standard coverage), claim
  grounding (paper numbers must trace to outputs — catches AI
  hallucinations), pre-registration drift, per-step completeness.
* **Self-tested dashboards.** Auto-generated Playwright suite covers
  TOC scroll-spy, theme toggle, sortable tables, lightbox figures,
  print stylesheet, ARIA snapshot, axe-core WCAG, visual regression.
  The AI iterates until tests pass.
* **HPC ready.** SLURM submit / status / fetch. Per-step Apptainer
  recipes + reproducer `entrypoint.sh`.

140 MCP tools, 82 YAML protocols, full hierarchical L1→L2→L3 routing
keeps every session boot under ~1.2K tokens. The protocol surface covers
both the canonical data → publication pipeline AND the partial / off-axis
workflows real researchers run (visualization-only, talk decks, lay
summaries, PI updates, EDA + hypothesis generation, head-to-head method
comparison, standalone power + evaluation + sweep + ethics design,
reproduction of published work, teaching / consultation, multi-paper
compare, mid-pipeline entry, per-section paper drafting,
multi-panel figures, figure narrative arcs, color accessibility audits,
cover letters, title workshops, printable handouts, and a
pre-submission final-gate checklist). See
[`docs/USE_CASES.md`](docs/USE_CASES.md) for the role × goal map.

**The MCP server is GLOBAL.** Install once with
`pip install research-os`; the SAME `research-os start` binary serves
every project. Each IDE request resolves the active project per call
via `RESEARCH_OS_WORKSPACE` (set by the IDE MCP config to
`${workspaceFolder}`), or by walking up from the current working
directory. `research-os init` is the only per-project command.

---

## Quick start (≤60 seconds)

```bash
pip install "research-os @ git+https://github.com/VibhavSetlur/Research-OS.git"
# (extras: [viz] for matplotlib+plotly, [audit] for assumption diagnostics,
#          [literature] for richer search providers, [all] for everything)

mkdir my-project && cd my-project
research-os init                     # scaffolds + drops MCP config for every IDE
```

Open your AI IDE on the project. Drop your data into `inputs/raw_data/`,
papers into `inputs/literature/`, notes into `inputs/context/`. Then say:

> *"fill out the intake"* — AI reads everything, proposes research question + hypotheses + domain.

> *"what should I do next?"* — iterative planning with grounded reasoning.

> *"run a baseline EDA as a sub-task pipeline"* — creates `workspace/01_baseline_eda/`, defines the pipeline.yaml, executes each node with provenance.

> *"freeze the analysis plan before I touch the data"* — pre-registers the SAP; deviations diff at synthesis.

> *"build the dashboard and run the playwright tests"* — assembles the dashboard, generates the test suite, runs it, iterates.

> *"write the paper for a journal"* — IMRAD synthesis with verified citations + claim grounding (no hallucinated numbers).

The CLI is two commands by design:

| Command                              | What it does                              |
|--------------------------------------|-------------------------------------------|
| `research-os init [dir]`             | Scaffold a workspace.                     |
| `research-os start [--workspace .]`  | Run the MCP server (your IDE talks to it). |

Don't have a project yet? Paste
[`docs/SETUP_PROMPT.md`](docs/SETUP_PROMPT.md) into any AI chat — it walks
the install + IDE wiring without needing one.

---

## Why use it

| Pain | What Research OS does about it |
|---|---|
| AI hallucinates citations | `tool_synthesize` pulls every citation from real providers (Crossref / Semantic Scholar / PubMed / arXiv), drops unverified entries, and caps per-section (3 abstract / 6 poster / 12 dashboard / 25 report / 40 paper). |
| AI guesses methodology from training memory | `tool_research_method` mandates literature grounding before any choice; `mem_decision_log` records the rationale + citations. |
| AI writes 400-line one-shot scripts | `tool_plan_step` forces breakdown into atomic, versioned sub-tasks; protocol forbids mega-shots. |
| Researcher just wants to dump files and talk | `tool_intake_autofill` reads `inputs/`, classifies domain, extracts research question + hypotheses, fills `intake.md`. Every config field is optional. |
| Researcher mid-flow drops a new paper | `tool_context_intake` auto-routes the file into the right `inputs/` subfolder and re-runs intake autofill. |
| AI gets stuck / workspace looks broken | `tool_workspace_repair` heals missing dirs, regenerates manifest + mermaid, backs up corrupted state — **never deletes**. |
| Long jobs on shared HPC | `tool_task_run` (real `Popen`) backgrounds them; `tool_task_status` polls without blocking the chat. |
| Multi-language / notebook / Quarto workflows | First-class `.py`, `.R`, `.jl`, `.sh`, `.ipynb`, `.Rmd`, `.qmd`. |
| Custom analyses (not just off-the-shelf libs) | Protocols explicitly support custom methodology — `mem_methods_append implementation="custom"`. Use `workspace/scratch/` to prototype. |
| Iterating on direction (researcher wants AI to propose) | `guidance/iterative_planning` protocol reads state + searches literature/tools + proposes 2-3 options with rationale. |
| Multiple hypotheses to track | `mem_hypothesis_add` / `_update` / `_list` maintains a ledger across experiment steps. |
| Per-step literature | `tool_literature_download step_id=<NN_slug>` saves PDFs to `workspace/<step>/literature/`. Sidecar `.meta.yaml` lets synthesis cite them properly. |
| AI burns tokens picking the wrong protocol | `tool_route` does a hierarchical L1→L2→L3 walk over `_router_index.yaml` and returns the answer in ~250 tokens. `sys_protocol_get format='summary'` loads a 300-token outline. A typical session boot costs ~1.2K tokens (vs ~5K under the old "load everything" pattern). |
| AI one-shots complex prompts on smaller models | `tool_route` persists an `active_plan` for any complex prompt. `tool_plan_turn` slices it into batches sized to `model_profile` (1 / 3 / 6 steps per turn). When the plan won't fit one chat, it recommends a handoff + fresh chat. |
| Same project, different AI tomorrow | `sys_session_handoff` snapshots a checkpoint + writes a "fresh AI can resume cold" doc. `tool_session_resume` reconstructs intent + status in one call. |
| 137 tools is too many for the AI to triage every turn | `tool_route` returns an `active_tools` shortlist (~10-15 tools = essentials + the chosen protocol's decomposition). `sys_active_tools(protocol)` queries the same scope directly. AI focuses on the working set instead of every tool every turn. |
| Need a visual of how steps depend on each other | `tool_workflow_dag` walks each numbered step's `data/input` symlink to derive cross-step edges, writes `docs/workflow_dag.mermaid` (+ PNG if `mmdc` is installed). Auto-refreshed on every `sys_path_create` / `sys_path_abandon`. |
| Step results break years later when the global env drifts | `tool_step_env_lock` pins `requirements.txt` + `python_version.txt` (+ optional `conda.yaml` + per-step `Dockerfile`) inside `workspace/<NN>/environment/`. Each step is self-contained. |
| AI runs runaway / unsafe shell commands on shared HPC | `tool_task_run` validates argv[0] against a configurable allowlist, refuses shell metacharacters by default, applies `setrlimit` for CPU / RSS / file-size, and audits every accepted task to `workspace/logs/task_audit.log`. |
| API rate limits during heavy synthesis | Search providers cache results under `.os_state/cache/search/` with a 24h TTL (`runtime.cache_ttl_seconds`). 429s trigger exponential backoff honouring `Retry-After`. `tool_cache_clear` wipes per-provider or older-than-N-days. |
| AI hallucinates a number in the paper | `tool_audit_claims` extracts every numeric claim from `synthesis/paper.md` and verifies each appears verbatim (or within 1% tolerance) in some workspace CSV / JSON / MD / TXT. BLOCKS `tool_synthesize` until cleared. |
| AI commits a methodological choice without showing its work | `tool_grounding_register` binds each decision to PROV-O sources (papers, context files, datasets, web). `tool_grounding_verify` audits every decision in `analysis.md`; un-grounded decisions become a master-audit blocker. |
| Step output appears six months later — where did it come from? | `tool_figure_create` / the pipeline runner / `tool_sensitivity_run` / Papermill `tool_notebook_exec` each drop a `<file>.prov.json` sidecar recording script + git SHA + input hashes + params + RNG seed + library versions + wall time. |
| Dashboard CSS / JS regressions go unnoticed | `tool_dashboard_test_generate` writes a Playwright suite covering scroll-spy, theme toggle, sortable tables, lightbox, print stylesheet, ARIA snapshot, axe-core WCAG, visual regression. `tool_dashboard_test_run` returns structured failures + `trace.zip` paths for time-travel debugging. |
| Same analysis under different reasonable choices flips the result | `tool_sensitivity_define` / `tool_sensitivity_run` enumerate a Cartesian grid of covariate sets / exclusion rules / model families and render a Steegen-style **specification curve**. Distinguishes ROBUST findings from FRAGILE ones. |
| Null findings end up in the file drawer | `tool_null_findings_report` assembles `synthesis/null_findings.md` from refuted hypotheses, underpowered tests, and dead-end paths — a publishable companion document. Routes via the new `synthesis/synthesis_null_findings` protocol. |
| Pre-registered analyses drift from the SAP | `tool_preregister_freeze` content-hashes the SAP before data. `tool_preregister_diff` lists every deviation at synthesis time so the Discussion can acknowledge them honestly. |
| Need to hand off to a human collaborator | `guidance/collaboration_handoff` writes a `COLLABORATOR.md` in their vocabulary, packages a share-safe zip, and verifies reproduction first. |
| Need to respond to peer review | `guidance/peer_review_response` parses the reviewer report, classifies each comment (accept / clarify / push back), routes new experiments via `analysis_plan`, drafts the rebuttal letter with line refs. |
| Submitting to an HPC cluster | `tool_slurm_submit` generates an `sbatch` script from `researcher_config.runtime.cluster_defaults`, records the job id; `tool_slurm_status` polls; `tool_slurm_fetch` waits + pulls logs back into the step folder. |
| Multi-script step gets reorganised across many files | `tool_step_pipeline_define` writes a 7-node `pipeline.yaml` (ingest → validate → clean → fit → diagnose → visualize → report). `tool_step_pipeline_run` walks the DAG, caches by content hash, drops a `.pipeline_run/run_<ts>.json` audit trail. |
| Reviewer-style internal critique before submission | `tool_redteam_review` writes a hostile-reviewer scaffold (M1-M5 major, threats to validity, devil's-advocate questions) under three personas (methodological skeptic / statistical referee / sympathetic peer). |
| Carry lessons across sessions | `tool_lessons_record` captures what worked / didn't; `tool_lessons_consult` retrieves the top-K relevant prior lessons + returns a prompt block ready to prepend to the next system prompt. |

---

## Workspace layout example

`research-os init` creates a clean skeleton. The AI fills the rest as you
work. **Real projects look like this after a few sessions** (the step
names below — `01_baseline_eda`, `02_data_preparation`,
`03_logistic_baseline`, `04_random_forest` — are **illustrative only**;
the AI derives each slug from the actual goal of the step it's creating,
following the naming rules in the `guidance/analysis_plan` protocol
(loaded contextually, not in `AGENTS.md`):

```text
my-project/
│
├── AGENTS.md                         # canonical AI rules (every IDE reads this)
├── GETTING_STARTED.md                # friendly intro for the researcher
├── CLAUDE.md  .windsurfrules  ...    # per-IDE shim rule files
├── README.md                         # project README (you write this)
├── .gitignore
│
├── inputs/                           # IMMUTABLE — researcher provides
│   ├── researcher_config.yaml        # source of truth for AI behaviour (gitignored)
│   ├── intake.md                     # auto-filled by tool_intake_autofill
│   ├── literature_index.yaml         # filename → citation_key mapping
│   ├── raw_data/
│   │   ├── cohort_2024.csv
│   │   ├── exposures.parquet
│   │   └── README.md                 # describes what's in this folder
│   ├── literature/                   # PROJECT-WIDE PDFs (anchor papers)
│   │   ├── vanderweele2020e_value.pdf
│   │   └── vanderweele2020e_value.pdf.meta.yaml
│   └── context/                      # notes, drafts, prior reports
│       ├── pi_briefing.md
│       └── prior_analysis_2022.pdf
│
├── docs/                             # human-readable
│   ├── research_question.md          # confirmed during project_startup
│   ├── domain_summary.md             # classified during domain_analysis
│   ├── research_design.md            # chosen during research_design
│   └── glossary.md                   # terms; extended by glossary_update
│
├── workspace/                        # ACTIVE — experiments live here
│   │
│   ├── methods.md                    # APPEND-ONLY method log (mem_methods_append)
│   ├── analysis.md                   # APPEND-ONLY narrative + workflow diagram
│   ├── citations.md                  # auto-generated bibliography
│   ├── workflow.mermaid              # auto-updated; rendered to .png if mmdc present
│   ├── workflow.png
│   │
│   ├── logs/
│   │   ├── searches.log              # every tool_search_* logged
│   │   ├── errors.log
│   │   ├── audit_report.md           # produced by audit_and_validation
│   │   └── context_intake_log.jsonl  # every file the AI auto-routed
│   │
│   ├── scratch/                      # AI sandbox (GITIGNORED)
│   │   ├── README.md                 # explains scratch policy
│   │   ├── try_groupby.py            # one-off tests live here, then get
│   │   └── sql_smoke.py              #   promoted into a numbered step or deleted
│   │
│   ├── 01_baseline_eda/              # ── EXPERIMENT STEP #1 ──
│   │   ├── README.md                 # goal, inputs, methods, outputs, decision
│   │   ├── conclusions.md            # findings + limitations + decision (proceed/branch/dead-end)
│   │   ├── scripts/
│   │   │   ├── 01_baseline_eda_v1.py    # first cut
│   │   │   ├── 01_baseline_eda_v2.py    # bumped after researcher asked for groupby by quarter
│   │   │   └── 01_baseline_eda_v3.py    # third version after audit flagged DPI
│   │   ├── literature/               # PDFs SCOPED to this step (canonical references)
│   │   │   ├── tukey1977eda.pdf
│   │   │   ├── tukey1977eda.pdf.meta.yaml
│   │   │   └── literature_index.yaml
│   │   ├── data/
│   │   │   ├── input/                # symlinked → ../../inputs/raw_data/
│   │   │   └── output/               # derived data (parquet, csv)
│   │   ├── outputs/
│   │   │   ├── reports/              # markdown summary WITH numbers + interpretation
│   │   │   │   └── distributions.md
│   │   │   ├── figures/              # PNG ≥150 DPI (300+ for publication)
│   │   │   │   ├── age_histogram.png
│   │   │   │   ├── age_histogram.caption.md
│   │   │   │   └── correlations_heatmap.png
│   │   │   └── tables/               # CSV / markdown
│   │   │       └── missingness_summary.csv
│   │   └── environment/
│   │       └── requirements.txt      # pip freeze at this step (per-step reproducibility)
│   │
│   ├── 02_data_preparation/          # ── EXPERIMENT STEP #2 ──
│   │   ├── README.md / conclusions.md
│   │   ├── scripts/
│   │   │   └── 02_data_preparation_v1.py
│   │   ├── data/
│   │   │   ├── input/                # symlinked → ../../01_baseline_eda/data/output/
│   │   │   └── output/
│   │   ├── outputs/{reports,figures,tables}/
│   │   └── environment/
│   │
│   ├── 03_logistic_baseline__DEAD_END/   # ── ABANDONED STEP (preserved, never deleted) ──
│   │   ├── README.md
│   │   ├── conclusions.md            # "## Why this path failed" section
│   │   ├── scripts/
│   │   │   ├── 03_logistic_baseline_v1.py
│   │   │   └── 03_logistic_baseline_v2.py
│   │   ├── literature/
│   │   ├── data/, outputs/, environment/
│   │   └── (renamed by sys_path_abandon — researcher can re-open at any time)
│   │
│   └── 04_random_forest/             # ── BRANCH PATH (parallel to abandoned 03) ──
│       ├── README.md / conclusions.md
│       ├── scripts/
│       │   ├── 04_random_forest_v1.py
│       │   ├── 04_random_forest_v2.py    # iterated after sub-task 3 failed
│       │   └── 04_random_forest_calibration_v1.py    # atomic sub-task
│       ├── literature/
│       │   ├── breiman2001rf.pdf
│       │   └── breiman2001rf.pdf.meta.yaml
│       ├── data/, outputs/, environment/
│
├── synthesis/                        # FINAL outputs (only created when you ask)
│   ├── paper.md                      # IMRAD with numbered figures, verified citations
│   ├── paper.tex                     # LaTeX with natbib + bibtex
│   ├── paper.pdf
│   ├── abstract.md                   # structured (journal) / unstructured (conference)
│   ├── poster.tex  /  poster.pdf     # tikzposter, audience-tailored
│   ├── dashboard.html                # single-file, sortable tables, light/dark
│   ├── references.bib                # BibTeX of every verified citation actually used
│   ├── figures/                      # numbered + copied (fig01_…, fig02_…)
│   ├── tables/                       # numbered + copied (tab01_…, tab02_…)
│   └── dashboard_figures/            # copies for offline dashboard
│
├── environment/                      # project-level baseline (per-step lives inside each step)
│   ├── requirements.txt
│   ├── Dockerfile                    # generated by sys_env_docker_generate
│   └── ...
│
└── .os_state/                        # internal — do not edit by hand
    ├── state_ledger.json             # primary state
    ├── state_ledger.yaml             # human-readable copy
    ├── manifest.json                 # workspace tree snapshot
    ├── os_state.md                   # human-readable status
    ├── protocol_execution_log.jsonl  # every protocol run
    ├── context_intake_log.jsonl
    ├── checkpoints/                  # hardlinked workspace snapshots
    ├── handoffs/                     # session handoff markdowns
    ├── cache/                        # API response cache
    └── tasks/                        # background subprocess registry
```

### Step naming — AI-derived, not hardcoded

**Nothing about the slug `baseline_eda` (or any other name) is special to
Research OS.** The AI picks every slug based on the goal of the step it's
about to create. The full rules live in the `guidance/analysis_plan`
protocol (the `create_step_folder` step) — short version:

* lowercase + underscores, ≤ 40 chars, descriptive
* mention the method when one is selected (`cox_ph_treatment_effect`, not generic `survival`)
* mention the sub-population if restricted (`logistic_under_65`)
* `NN_` prefix is auto-assigned by `sys_path_create` — don't pass it
* same goal, different parameters → bump `_v<n>` on the script
* different goal → new numbered step (different slug)

Plausible slugs the AI might pick (purely illustrative — different
projects look totally different):

```
01_baseline_eda           02_imputation_mice         03_cox_ph_full_cohort
01_distribution_scan      02_outlier_winsorise       03_ipw_treatment_effect
01_corpus_profile         02_bert_finetune_sentiment 03_attention_ablation
01_rna_seq_qc             02_deseq2_de               03_gsea_pathway
```

### How numbered steps grow over a session

*(Slugs below are made up to illustrate — your AI picks names from your
project's actual goals.)*

1. **AI creates the first step folder** via `sys_path_create name="<slug>"`,
   e.g. `name="baseline_eda"`. The server auto-prefixes `01_`. `data/input/`
   is symlinked to `inputs/raw_data/`.
2. **AI writes the main script** as `<NN>_<slug>_v1.<ext>` (atomic,
   single-purpose, RNG seeds set, library versions printed to stderr).
3. **Researcher pivots** ("group by quarter instead of month"). AI bumps
   to `<NN>_<slug>_v2.<ext>` (new version, not overwrite), re-runs,
   updates `conclusions.md`.
4. **AI creates the next step** with a slug describing its NEW goal. The
   server picks `02_`. Its `data/input/` symlinks to step 01's
   `data/output/`. Chain continues.
5. **A step fails** (e.g. assumption violated). AI calls
   `sys_path_abandon path_name="<NN>_<slug>" rationale="…"`. The folder
   is renamed `<NN>_<slug>__DEAD_END`. Files preserved. The
   `conclusions.md` gets a `## Why this path failed` section.
6. **AI creates an alternative step** — fresh slug describing the new
   approach. The server picks the next number. Its `data/input/` symlinks
   past the dead-end (to whichever earlier step produced its input).
   `tool_branch_recommendation` advises whether to branch or extend.
7. **Per-step literature** — AI downloads a canonical reference into the
   step's `literature/` with a `.meta.yaml` sidecar (instead of polluting
   project-wide `inputs/literature/`). Synthesis cites it correctly later.
8. **Scratch** — quick syntax checks live in `workspace/scratch/`
   (gitignored). Real work moves into a numbered step or gets deleted.

### Final outputs (synthesis is project-wide, not per-step)

`synthesis/` is built only when you ask ("write the paper" / "make a dashboard").
Per-step folders have `outputs/{reports,figures,tables}/` — **no dashboards**,
because dashboards are a project-level summary, not per-experiment.

### `.os_state/` is gitignored beyond the state ledger

`.gitignore` keeps `cache/`, `checkpoints/`, `handoffs/` out of git; the
ledger + manifest + protocol log are committed so collaborators can resume.

---

## Architecture (45 seconds)

```
AI IDE (Claude Code / OpenCode / Antigravity / Cursor / Claude / VS Code / Windsurf / Continue / Aider)
        │ MCP stdio
        ▼
research-os MCP server (Python)
        │
        ├── Routing layer    sys_boot  →  tool_route (L1→L2→L3 hierarchical)
        │                    sys_protocol_get format=summary | step | full
        │                    tool_plan_turn (per-model_profile batching)
        │                    tool_plan_advance / tool_plan_clear
        ├── sys.*    workspace, state, paths, checkpoints, config, files,
        │            repair, env, scratch, session_handoff, tool_describe
        ├── tool.*   search, exec, audit, synthesis, tasks, research,
        │            intake, literature, session_resume, progress_digest,
        │            dead_end_lessons, quick_review, workspace_repair
        └── mem.*    append-only methods / analysis / citations / decisions
                     / hypotheses
        │
        ▼
    Workspace files
    (immutable inputs · iterative workspace · final synthesis · gitignored .os_state)
```

The IDE plans and decides; Research OS executes and records. No autonomous
decisions in Research OS — your model stays in control. The routing layer
keeps a typical session boot under ~1.2K tokens regardless of how many
protocols + tools exist on disk.

---

## Documentation

| File | Read when |
|---|---|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | First time, dense version. 5 minutes. |
| [`docs/FIRST_HOUR.md`](docs/FIRST_HOUR.md) | First-time, hand-held version. 60 minutes top to bottom. |
| [`docs/CHEATSHEET.md`](docs/CHEATSHEET.md) | One page. Every command worth knowing. |
| [`docs/AI_GUIDE.md`](docs/AI_GUIDE.md) | Orientation for the AI driving Research OS (operating manual). |
| [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) | End-to-end simulated project — shell commands + realistic chat prompts from data download through paper + handoff + resume. |
| [`docs/SETUP.md`](docs/SETUP.md) | Install + per-IDE MCP wiring + troubleshooting. |
| [`docs/SETUP_PROMPT.md`](docs/SETUP_PROMPT.md) | Paste-into-any-AI installer prompt (no project needed). |
| [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) | Non-technical walkthrough of the workflow. |
| [`docs/USE_CASES.md`](docs/USE_CASES.md) | Role × goal × output map — which protocol for which researcher, which moment. |
| [`docs/GUIDE.md`](docs/GUIDE.md) | Full technical reference: every tool + protocol + the pipeline. |
| [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md) | Protocol catalog — when each fires, what it does, quality bars. |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Tool catalog with example invocations. |
| [`docs/FAQ.md`](docs/FAQ.md) | Common questions. |
| [`templates/AGENTS.md`](templates/AGENTS.md) | The AI operating manual dropped into every workspace. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Adding tools, protocols, or fixing bugs. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history. |

---

## What's in the box

* **140 MCP tools** across `sys_*`, `tool_*`, `mem_*` namespaces. Dot
  notation (`sys.state.get`) and legacy names auto-rewrite. Run
  `python scripts/preflight.py` after install to verify everything is wired.
* **82 YAML protocols** — the AI loads the right one based on what you ask.
  Each declares an explicit `quality_bar` so output stays publication-grade
  even on smaller models. Coverage spans methodology (RCTs, clinical
  trials, observational causal, ML, meta-analysis, survey psychometrics,
  qualitative research, simulation/ADEMP studies, replication studies,
  ablation studies, pilot studies, mixed methods, exploratory data
  analysis with hypothesis generation, head-to-head method comparison,
  standalone data quality audit, standalone power analysis, reproduction
  of published work, methodological consultation / teaching), literature
  (broad search, PRISMA systematic review, GRADE evidence synthesis,
  comparative paper review for 2-N papers / journal clubs / related-work
  sections), synthesis (paper, abstract, poster, dashboard, report,
  grant, slides, lay summary, progress update, from-inputs, null
  findings), visualization (figure rules, visualization workflow,
  figure critique), and guidance (session boot/resume, autopilot,
  quick paper review, code review, peer-review response, casual
  exploration, chat/AI-to-AI handoff, collaboration handoff, iterative
  planning, dead-end routing, mid-pipeline entry).
* **One neutral config** at `templates/researcher_config.yaml`. No
  modality presets — `domain_analysis` infers the project shape from
  signals + literature, and the AI fills the config per-project. See
  [`docs/DOMAIN_HINT_EXAMPLES.md`](docs/DOMAIN_HINT_EXAMPLES.md) for
  three cross-domain reasoning patterns (never templates to copy).
* **8 IDE rule templates** auto-dropped on init.
* **Real, verified citations** — synthesis outputs cannot contain
  hallucinated references.
* **Per-step literature** — papers can be scoped to a specific experiment
  step with full metadata sidecars.
* **Session resume + handoff** — `tool_session_resume` reconstructs intent
  from logs after any pause (different chat, different AI model, next
  day). `sys_session_handoff` snapshots a checkpoint and writes a
  fresh-AI-readable handoff doc.
* **Progress digest + dead-end lessons** — one-page status report
  (`tool_progress_digest`) plus reusable lessons from every abandoned
  path (`tool_dead_end_lessons`) so the next attempt doesn't repeat
  yesterday's mistake.
* **Workspace repair, scratch sandbox, mid-flow context intake, background
  tasks** — built-in robustness for shared servers and long-running work.
* **Optional-dependency inventory** (`sys_dep_inventory`) — surfaces at
  session start which extras failed to import so the AI doesn't try a
  broken tool late.

---

## Verify your install

```bash
python scripts/preflight.py
```

Runs ~11 checks in a few seconds (package imports, protocol loading,
tool/handler consistency, dispatcher aliases, workspace-scaffold smoke).
Exits non-zero on any failure with a clear detail dump.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues + PRs welcome at
<https://github.com/VibhavSetlur/Research-OS/issues>.
