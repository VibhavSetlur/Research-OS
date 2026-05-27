# Research OS — Guide

Research OS is an MCP server that gives AI coding IDEs (Cursor, Claude,
Antigravity, OpenCode, VS Code) the tools and protocols to do reproducible
research. **The IDE is the brain; Research OS is the body.**

---

## 1. Install

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Optional extras: `web`, `literature`, `viz`, `execution`, `r`, `julia`, `audit`, `poster`, `ml`.

## 2. Scaffold

```bash
mkdir my-project && cd my-project
research-os init                                # uses cwd name
# or:
research-os init my-project --name "PM2.5 Study" --domain clinical
```

`init` drops:

* `AGENTS.md`                  — operating manual the AI reads first.
* `inputs/researcher_config.yaml` — source of truth for AI behaviour.
* `.os_state/` + state ledger  — initial pipeline state.
* `.cursor/`, `.claude/`, `.antigravity/`, `.vscode/`, `opencode.json` —
  pre-wired MCP configs.

## 3. Start the server

```bash
research-os start --workspace .
```

Most IDEs auto-launch this via the MCP config dropped in step 2 — you typically
don't run `start` manually.

## 4. Add data, then talk to the AI

* Drop datasets into `inputs/raw_data/`.
* Drop PDFs into `inputs/literature/`.
* Open your IDE pointed at the project. Say:

  > "start the project"  · "analyse my data"  · "find related literature"  · "write the paper"

The AI follows AGENTS.md, calls `sys_protocol_next`, loads the protocol, and
walks through its steps using MCP tools.

---

## 5. The MCP tools (~65)

> Research OS does NOT manage LLM provider keys. Your IDE owns model access.
> The credentials below are for literature / search / scraping APIs only.

### System (`sys_*`)

| Tool | Description |
|---|---|
| `sys_protocol_get`     | Load a protocol YAML by name. |
| `sys_protocol_list`    | List every protocol with summary. |
| `sys_protocol_next`    | Recommend the next protocol from workspace state. |
| `sys_protocol_validate`| Check whether a protocol's expected outputs exist. |
| `sys_protocol_log`     | Record a protocol execution. |
| `sys_protocol_history` | Show recent protocol log entries. |
| `sys_state_get`        | Full state (or `format=minimal|markdown`). |
| `sys_workspace_scaffold` | Re-create the workspace layout. |
| `sys_workspace_tree`   | Structured view of `workspace/`. |
| `sys_file_read`        | Read a workspace file (≤50 MB). |
| `sys_file_write`       | Write a workspace file (respects immutability). |
| `sys_file_list`        | Recursively list a directory. |
| `sys_file_delete`      | Delete a file or empty directory. |
| `sys_file_validate_md` | Validate a markdown file against a writing protocol. |
| `sys_path_create`      | Create the next numbered experiment folder. |
| `sys_path_abandon`     | Rename a step to `__DEAD_END`. |
| `sys_path_list`        | List all numbered experiments + status. |
| `sys_checkpoint_create`| Hardlinked workspace snapshot. |
| `sys_checkpoint_rollback` | Restore a checkpoint (backs up current first). |
| `sys_checkpoint_list`  | List checkpoints. |
| `sys_config_get`       | Read `inputs/researcher_config.yaml` (API keys masked). |
| `sys_config_set`       | Set a config key (dot notation). |
| `sys_config_validate`  | Report missing required fields + which API keys are set. |
| `sys_notify`           | Notify the researcher (logged). |
| `sys_session_handoff`  | Generate a markdown handoff + resume prompt. |
| `sys_env_snapshot`     | Snapshot Python/R/Julia environment to current step. |
| `sys_env_docker_generate` | Build a Dockerfile from the environment snapshot. |

### Tools (`tool_*`)

| Tool | Description |
|---|---|
| `tool_search_semantic_scholar` | Semantic Scholar Graph API. |
| `tool_search_pubmed`     | PubMed via NCBI eutils. |
| `tool_search_crossref`   | Crossref. |
| `tool_search_arxiv`      | arXiv (no key required). |
| `tool_search_web`        | Firecrawl primary, SerpAPI fallback. |
| `tool_web_scrape`        | Scrape a webpage to markdown. |
| `tool_literature_download` | Download a paper PDF to `inputs/literature/`. |
| `tool_python_exec`       | Run a Python script in workspace. |
| `tool_r_exec`            | Run an R script. |
| `tool_julia_exec`        | Run a Julia script. |
| `tool_bash_exec`         | Run a Bash script. |
| `tool_package_install`   | `pip install` + append to requirements.txt. |
| `tool_data_sample`       | Sample N rows from CSV/Parquet/Feather/JSON/Excel. |
| `tool_data_profile`      | Schema + missingness + descriptive stats. |
| `tool_data_convert`      | CSV ↔ Parquet ↔ Feather ↔ RDS. |
| `tool_audit_synthesis`   | Section coverage, causal-language flags, citation density. |
| `tool_audit_power`       | Post-hoc statistical power. |
| `tool_audit_assumptions` | Re-run normality / homoscedasticity / etc. |
| `tool_audit_figure`      | DPI / size / format checks. |
| `tool_audit_citations`   | Verify each citation online. |
| `tool_audit_reproducibility` | Re-run every script and compare output hashes. |
| `tool_synthesize_plan`   | Show available sources + recommended ordering. |
| `tool_synthesize`        | Build synthesis/paper.md (or one section). |
| `tool_latex_compile`     | paper.tex → PDF. |
| `tool_poster_create`     | tikzposter → PDF. |
| `tool_dashboard_create`  | Single-file HTML dashboard. |

### Memory (`mem_*`)

| Tool | Description |
|---|---|
| `mem_analysis_log`      | Append a line to `workspace/analysis.md`. |
| `mem_methods_append`    | Append a structured method entry. |
| `mem_citations_generate`| Refresh `workspace/citations.md` from the literature index. |
| `mem_intake_regenerate` | Refresh `inputs/intake.md` (hashes). |
| `mem_decision_log`      | Append a structured decision (context/selected/rationale). |
| `mem_hypothesis_add`    | Register a new hypothesis. |
| `mem_hypothesis_update` | Update a hypothesis (status + evidence). |
| `mem_hypothesis_list`   | Show every tracked hypothesis. |

### Reasoning + research grounding (`tool_*`)

| Tool | Description |
|---|---|
| `tool_research_method` | Pull 5-10 academic + web sources about a method; write a structured report. Call BEFORE choosing any method. |
| `tool_research_tool`   | Find candidate libraries / CLIs / websites; tag each as installable / api / external / paid. |
| `tool_external_tool_instructions` | When the chosen tool is external (website / paid / GUI), write a WORKSHEET.md for the researcher. |
| `tool_plan_step`       | Force a complex step to be broken into atomic sub-tasks BEFORE coding. |
| `tool_intake_autofill` | Read inputs/, classify domain, extract research question + hypotheses, fill blank config fields. |

### Background tasks (`tool_task_*`)

| Tool | Description |
|---|---|
| `tool_task_run`     | Real `subprocess.Popen`; returns task_id immediately. |
| `tool_task_status`  | Poll status + tail log. |
| `tool_task_list`    | List all known tasks. |
| `tool_task_kill`    | Terminate a task. |

### Multi-language scripts

| File | Tool |
|---|---|
| `.py`   | `tool_python_exec` |
| `.R`    | `tool_r_exec` |
| `.jl`   | `tool_julia_exec` |
| `.sh`   | `tool_bash_exec` |
| `.ipynb`| `tool_notebook_exec` |
| `.Rmd`  | `tool_rmarkdown_render` |
| `.qmd`  | `tool_rmarkdown_render` (uses quarto) |

---

## 6. The pipeline (10 stages)

`sys_protocol_next` checks the workspace and returns the first stage whose
output does NOT yet exist on disk. The default chain:

| # | Protocol                              | Completed when ... |
|---|---------------------------------------|---------------------|
| 1 | `guidance/session_boot`               | protocol_execution_log.jsonl exists |
| 2 | `guidance/project_startup`            | inputs/intake.md + docs/research_question.md exist |
| 3 | `domain/domain_analysis`              | docs/domain_summary.md exists |
| 4 | `domain/research_design`              | docs/research_design.md exists |
| 5 | `methodology/methodology_selection`   | workspace/methods.md has substantive content |
| 6 | `literature/literature_search`        | inputs/literature_index.yaml + workspace/citations.md exist |
| 7 | `guidance/analysis_plan`              | at least one workspace/NN/conclusions.md is non-empty |
| 8 | `reproducibility/reproducibility`     | workspace/*/environment/requirements.txt exists |
| 9 | `audit/audit_and_validation`          | workspace/logs/audit_report.md exists |
| 10| `synthesis/synthesis_paper`           | synthesis/paper.md exists |

Side protocols (loaded on demand):

* `methodology/{clinical_trials,machine_learning,meta_analysis,causal_inference_deep,survey_psychometrics,research_methods,tool_discovery}`
* `literature/{systematic_review,evidence_synthesis}`
* `synthesis/{synthesis_abstract,synthesis_poster,synthesis_dashboard}`
* `writing/{writing_core,writing_methods,writing_citations,writing_conclusions,writing_analysis_log,writing_readme}`
* `guidance/{dead_end_routing,hypothesis_tracking,glossary_update,writing_standards}`
* `visualization/figure_guidelines`

---

## 7. Natural-language workflow

### What you say → what happens

| You say                                  | The AI does                                       |
|------------------------------------------|---------------------------------------------------|
| "start the project"                      | session_boot → project_startup → suggests first experiment |
| "look at my data"                        | tool_data_profile on every file in raw_data/      |
| "plan the next experiment"               | analysis_plan: scope → ground → create step → execute |
| "this isn't working, abandon"            | dead_end_routing: documents failure + chooses next direction |
| "find related literature"                | literature_search: multi-source + dedup + citations.md |
| "do a systematic review"                 | literature/systematic_review (PRISMA workflow)    |
| "fit a model"                            | methodology_selection → machine_learning (or relevant) |
| "write the methods"                      | writing_methods                                   |
| "write the paper"                        | synthesis_paper: plan → methods → results → discussion → abstract → assemble |
| "make a poster"                          | synthesis_poster (tikzposter PDF)                 |
| "make a dashboard"                       | synthesis_dashboard (single-file HTML)            |
| "check reproducibility"                  | reproducibility + (optional) tool_audit_reproducibility |
| "audit everything"                       | audit_and_validation: citations + assumptions + figures + causal language + lint |
| "what should I do next?"                 | sys_protocol_next                                 |
| "wrap up the session"                    | sys_session_handoff (writes resume prompt)        |

---

## 8. Configuration

`inputs/researcher_config.yaml` (auto-created on `init`) is the source of truth:

```yaml
project_name: "PM2.5 Study"
research_question: "What is the effect of PM2.5 on respiratory ER visits?"
domain: "environmental_health"

researcher:
  name: "Vibhav Setlur"
  field: "environmental epidemiology"
  expertise_level: "advanced"     # beginner | intermediate | advanced | pi

interaction:
  autonomy_level: "supervised"    # manual | supervised | autopilot

model_profile: "medium"           # small | medium | large

research_goal:
  output_types: ["paper", "dashboard"]
  target_venue: "journal"
  reporting_standard: "STROBE"
  
writing_preferences:
  citation_style: "vancouver"
  language: "en-US"

api_keys:
  firecrawl: ""                   # injected as FIRECRAWL_API_KEY at server start
  semantic_scholar: ""            # injected as SEMANTIC_SCHOLAR_API_KEY / S2_API_KEY
  pubmed: ""                      # injected as NCBI_API_KEY
  crossref: ""
  serpapi: ""
```

### Domain presets

Copy any of these into `inputs/researcher_config.yaml`:

* `templates/configs/rct_config.yaml` — Randomised controlled trials (CONSORT).
* `templates/configs/epidemiology_observational.yaml` — Observational health (STROBE).
* `templates/configs/genomics.yaml` — Bioinformatics (MINSEQE / MIAME).
* `templates/configs/nlp_benchmark.yaml` — NLP benchmarks (Model Cards).
* `templates/configs/economic_panel.yaml` — Panel data econometrics (AEA).

### Model profiles

| Profile  | Effect on protocols                            | Effect on tool descriptions |
|----------|------------------------------------------------|------------------------------|
| `small`  | Drops `model_adaptations`, `examples`, templates | Trimmed to first sentence    |
| `medium` | Standard.                                      | Full.                        |
| `large`  | Full + multi-step planning recommended.        | Full.                        |

---

## 9. Migrating an existing project into Research OS

```bash
cd my-existing-project
research-os init . --force
# inspect what was added (.os_state/, AGENTS.md, inputs/, etc.)
mv my_data*.csv inputs/raw_data/
mv references/*.pdf inputs/literature/
research-os start --workspace .
```

Then in your IDE:

> "I have an existing project — read inputs and current docs/, then propose how to continue."

The AI will run session_boot, project_startup, and figure out the right pipeline
stage based on which files already exist.

---

## 10. Troubleshooting

| Problem                                | Fix                                                  |
|----------------------------------------|------------------------------------------------------|
| `research-os: command not found`       | Add `~/.local/bin` to `PATH`.                        |
| `Not a Research OS workspace`          | `research-os init .` or pass `--workspace`.          |
| `WriteProtectedError`                  | Cannot write to `inputs/raw_data/` or `inputs/literature/`. Copy to `workspace/`. |
| `Protocol not found`                   | `sys_protocol_list` to see valid names.              |
| Tools missing in IDE                   | Restart IDE; check the IDE's MCP panel for stderr.   |
| `Firecrawl API key not set`            | Add `firecrawl: <key>` under `api_keys` in researcher_config. |
| Mermaid PNG not rendering              | `npm install -g @mermaid-js/mermaid-cli`.            |
| `pdflatex not found`                   | Install TeX Live for PDF compile.                    |
| `tool_audit_reproducibility` slow      | It re-runs every script. Skip in autopilot unless asked. |

---

## 11. File index

| File                                       | Role                                          |
|--------------------------------------------|-----------------------------------------------|
| `src/research_os/server.py`                | MCP server + dispatcher + 51 tool defs.       |
| `src/research_os/cli.py`                   | `init` and `start` commands.                  |
| `src/research_os/project_ops.py`           | Workspace scaffold, state, manifest, mermaid. |
| `src/research_os/state/state_ledger.py`    | Single source of truth for state.             |
| `src/research_os/tools/actions/*.py`       | One file per logical tool group.              |
| `src/research_os/protocols/**/*.yaml`      | 33 YAML protocols.                            |
| `templates/AGENTS.md`                      | AI operating rules dropped into every project.|
| `templates/configs/*.yaml`                 | Domain presets.                               |
| `templates/.{cursor,claude,antigravity}/`  | Per-IDE MCP + rule files.                     |
