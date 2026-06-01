# Research OS — Guide

Research OS is an MCP server. The AI in your IDE plans and reasons;
Research OS executes, records state, enforces immutability, **picks the
right protocol via a hierarchical router**, and walks the AI through it.

> Research OS does NOT manage LLM provider keys. Your IDE owns model access.
> The credentials Research OS uses (Crossref / Semantic Scholar / PubMed /
> Firecrawl / SerpAPI) are for literature + web search only, all optional.

---

## 0. How the AI is supposed to use it (the cheap path)

```
1. sys_boot                            # one MCP call: state + config + history
                                       # + dep inventory + next protocol +
                                       # pause classification + active plan
2. (await researcher's message)
3. tool_route(prompt=<their message>)  # hierarchical L1→L2→L3 picker
4. If complexity="high":
     a. tool_plan_turn                 # batch sized to model_profile
     b. execute every entry in this_turn; tool_plan_advance after each
     c. if chat_split_recommended → sys_session_handoff + ask for fresh chat
   If complexity="low":
     • call shortcut_tool directly, OR
     • sys_protocol_get name=<primary> format='summary' (~300 tokens)
       → then format='step' + step_id='<id>' when ready to execute
```

A typical session boot is ~1.2K tokens (vs ~5K with the old multi-call
pattern). See [PROTOCOLS.md](PROTOCOLS.md) for the router internals.

---

## 1. Install

```bash
pip install "research-os[ci] @ git+https://github.com/VibhavSetlur/Research-OS.git"
# or
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Extras: `ci` (lean — used by GitHub Actions), `all` (everything except
R / Julia / Docker, which need their own runtimes), or any subset of
`web`, `literature`, `viz`, `audit`, `ml`, `notebook`.

## 2. Scaffold

```bash
mkdir my-project && cd my-project
research-os init                                # uses cwd name
# or:
research-os init my-project --name "PM2.5 Study"
```

`init` drops:

* `AGENTS.md` — the AI operating manual.
* `inputs/researcher_config.yaml` — source of truth for behaviour (every
  field is optional).
* `.os_state/` + state ledger.
* `.cursor/`, `.claude/`, `.antigravity/`, `.vscode/`, `opencode.json` —
  pre-wired MCP configs for each IDE.

Drop your data into `inputs/raw_data/`, papers into `inputs/literature/`,
notes / drafts into `inputs/context/`. Open your IDE on the project. Say:

> "fill out the intake" → AI reads everything, fills `intake.md`, infers
>  question + domain + hypotheses, populates blank config fields.

> "start the project" / "run a baseline" → AI walks the pipeline.

> "what should I do next?" → iterative planning: literature + tool search +
>  2-3 concrete options + recommendation.

## 3. Start the server

```bash
research-os start
```

The MCP configs dropped by `init` already point to this command, so most IDEs
auto-launch it. You rarely run `start` manually.

---

## 4. The pipeline (10 stages)

`sys_protocol_next` returns the first stage whose outputs (and execution log)
say "not done yet".

| # | Protocol                              | Done when... |
|---|---------------------------------------|---|
| 1 | `guidance/session_boot`               | first protocol logged in `protocol_execution_log.jsonl` |
| 2 | `guidance/project_startup`            | `intake.md` filled + research question confirmed |
| 3 | `domain/domain_analysis`              | `docs/domain_summary.md` exists |
| 4 | `domain/research_design`              | `docs/research_design.md` exists |
| 5 | `methodology/methodology_selection`   | `workspace/methods.md` substantive |
| 6 | `literature/literature_search`        | `inputs/literature_index.yaml` + `citations.md` exist |
| 7 | `guidance/analysis_plan`              | at least one `workspace/NN/conclusions.md` is non-empty |
| 8 | `reproducibility/reproducibility`     | `workspace/*/environment/requirements.txt` exists |
| 9 | `audit/audit_and_validation`          | `workspace/logs/audit_report.md` exists |
| 10| `synthesis/synthesis_paper`           | `synthesis/paper.md` exists |

### Side / on-demand protocols

* `guidance/session_resume` — re-enter a paused project / new chat.
* `guidance/chat_handoff` — end a session cleanly with full handoff doc.
* `guidance/autopilot` — drive hands-off with explicit gates.
* `guidance/casual_exploration` — lightweight scratch-first mode.
* `guidance/quick_paper_review` — fast critical appraisal of someone
  else's paper (orthogonal to the main project).
* `guidance/iterative_planning` — for "what's next?" style work.
* `guidance/dead_end_routing` — abandon a failed path cleanly.
* `guidance/hypothesis_tracking` — register / update hypotheses.
* `guidance/glossary_update` / `guidance/writing_standards`.
* `methodology/{clinical_trials, machine_learning, meta_analysis,
  causal_inference_deep, survey_psychometrics, qualitative_research,
  simulation_studies, replication_study, ablation_study, pilot_study,
  mixed_methods, research_methods, tool_discovery}`.
* `literature/{systematic_review, evidence_synthesis}`.
* `synthesis/{synthesis_abstract, synthesis_poster, synthesis_dashboard,
  synthesis_grant, synthesis_report}`.
* `writing/{writing_core, writing_methods, writing_citations,
  writing_conclusions, writing_analysis_log, writing_readme}`.
* `visualization/figure_guidelines`.

---

## 5. MCP tools (98)

> All names use underscores. Dot notation + legacy names are auto-rewritten.
> Full catalogue: [TOOLS.md](TOOLS.md).

### Routing layer — call FIRST every session

| Tool | Purpose |
|---|---|
| `sys_boot` | One call returns state + config + history + dep inventory + next protocol + pause classification + active plan. Replaces 4-5 separate calls. |
| `tool_route` | Hierarchical L1→L2→L3 picker for "which protocol fits this prompt". Returns ambiguity-aware. |
| `tool_plan_turn` | Per-turn batching sized to model_profile (small=1, medium=3, large=6 steps). |
| `tool_plan_advance` / `tool_plan_clear` | Walk or discard the active plan. |
| `sys_tool_describe` | Full description for one tool on demand (paired with trimmed `list_tools`). |
| `sys_dep_inventory` | Which optional extras failed to import. |
| `sys_protocol_get` | `format='summary'` (~300 tokens) / `format='step' step_id='...'` / `format='full'`. |

### `sys_*` — workspace, state, files, paths, checkpoints

| Tool | Purpose |
|---|---|
| `sys_state_get` | Full / minimal / markdown snapshot. (Prefer `sys_boot` at session start.) |
| `sys_workspace_scaffold` / `_tree` | Re-create / inspect the workspace tree. |
| `sys_file_read/_write/_list/_delete/_validate_md` | File I/O. |
| `sys_path_create/_abandon/_list` | Numbered experiment folders. |
| `sys_checkpoint_create/_rollback/_list` | Workspace snapshots. |
| `sys_config_get/_set/_validate` | researcher_config.yaml. |
| `sys_notify` | Append to `workspace/logs/notifications.log`. |
| `sys_session_handoff` | Structured handoff doc + fresh checkpoint. |
| `sys_env_snapshot/_docker_generate` | Capture + containerise the env. |

### `tool_*` — research workflow

| Tool | Purpose |
|---|---|
| `tool_session_resume` / `tool_progress_digest` / `tool_dead_end_lessons` | Session continuity + bookkeeping. |
| `tool_quick_review` | Stage a critical-appraisal skeleton for someone else's paper. |
| `tool_search_semantic_scholar/_pubmed/_crossref/_arxiv/_web` | Literature + web search. |
| `tool_web_scrape` / `tool_literature_download` / `tool_literature_search_and_save` / `tool_step_literature_list` | URL scrape; per-step literature management. |
| `tool_python_exec` / `_r` / `_julia` / `_bash` / `_notebook` / `_rmarkdown_render` | Run scripts / notebooks. Returncode-aware. |
| `tool_package_install` | `pip install` + update requirements. |
| `tool_data_sample` / `_profile` / `_convert` | Sample, profile, convert tabular data. |
| `tool_audit_synthesis/_power/_assumptions/_figure/_citations/_reproducibility` | Real audits — citation lookups, statistical power, assumption tests, figure DPI, full re-runs. |
| `tool_synthesize_plan` / `tool_synthesize` | Plan section order; build paper / abstract / poster / dashboard / grant / report with verified citations. |
| `tool_latex_compile` / `tool_poster_create` / `tool_dashboard_create` | PDF + tikzposter + single-file HTML dashboard. |
| `tool_research_method` / `tool_research_tool` / `tool_external_tool_instructions` / `tool_plan_step` | Reasoning + grounding helpers. |
| `tool_plan_next_step` / `tool_branch_recommendation` | Iterative planning. |
| `tool_intake_autofill` / `tool_context_intake` | Auto-fill + mid-flow context injection. |
| `tool_task_run/_status/_list/_kill` | Real background subprocesses (zombie-aware) for shared servers. |
| `tool_scratch_write/_run/_list/_clear` | Workspace sandbox. |
| `tool_workspace_repair` | Heal a broken workspace; never deletes. |
| `tool_citations_verify` | Re-verify every citation_key in `workspace/citations.md`. |

### `mem_*` — append-only logs, decisions, hypotheses

| Tool | Purpose |
|---|---|
| `mem_analysis_log` / `mem_methods_append` / `mem_citations_generate` / `mem_intake_regenerate` / `mem_decision_log` | Append to the canonical workspace logs. |
| `mem_hypothesis_add/_update/_list` | Multi-hypothesis ledger. |

---

## 6. Codebase layout

```
src/research_os/
├── server.py                         # MCP server + dispatcher
├── cli.py                            # `init` + `start`
├── project_ops.py                    # scaffolding, state, mermaid, intake regen
├── config.py / errors.py / __init__.py
├── protocols/                        # 52 YAML protocols + _router_index.yaml
├── state/                            # ResearchLedger
├── utils/                            # asset manager, common helpers
└── tools/
    └── actions/
        ├── protocol.py               # YAML loader (cross-cutting)
        ├── router.py                 # sys_boot, tool_route, plan_turn (cross-cutting)
        ├── state/                    # config, path, checkpoint, interaction,
        │                             # scratch, repair
        ├── data/                     # data, profiling, intake, context_intake
        ├── exec/                     # scripts, notebook, tasks, environment
        ├── search/                   # search providers, literature download
        ├── research/                 # research_method/tool/plan, planning
        ├── audit/                    # audit, md_audit
        ├── synthesis/                # synthesize, latex, citations
        └── memory/                   # hypotheses, append-only helpers
```

All non-cross-cutting tools live inside one of the eight subpackages.
Only `protocol.py` (YAML loader) and `router.py` (sys_boot + tool_route
+ plan_turn + active plan) live flat at the top — both touch every
category, so flattening them avoids circular sub-packages.

---

## 7. Tests

```
tests/
├── conftest.py                       # isolates each test on tmp_path
├── unit/                             # pure-function tests, fast
├── integration/                      # workspace + pipeline + reorganization-aware
└── tools/                            # one file per new MCP tool group
```

Run all:
```bash
pytest -q
```

Run a slice:
```bash
pytest tests/unit -q
pytest tests/integration -q
pytest tests/tools/test_planning.py -q
```

---

## 8. Configuration

`inputs/researcher_config.yaml` is auto-created on `init`. Every field is
optional. Set only what you care about — the rest gets sensible defaults
applied silently by `session_boot`.

```yaml
project_name: ""                  # blank → uses directory name
research_question: ""             # blank → tool_intake_autofill proposes
domain: ""                        # blank → AI classifies from inputs
hypotheses: []                    # AI tracks via mem_hypothesis_*

researcher:
  name: ""
  field: ""
  expertise_level: ""             # beginner | intermediate | advanced | pi

interaction:
  autonomy_level: "supervised"    # manual | supervised | autopilot

model_profile: "medium"           # small | medium | large

runtime:
  shared_server: false
  long_running_threshold_seconds: 60
  default_n_for_sampling: 1000

research_goal:
  output_types: []                # paper | abstract | poster | dashboard | report | exploratory
  target_venue: ""
  reporting_standard: ""
  poster_dimensions: "36x48"

writing_preferences:
  citation_style: "apa"
  language: "en-US"

api_keys:                         # all optional — NO LLM provider keys
  semantic_scholar: ""
  pubmed: ""
  crossref: ""
  firecrawl: ""
  serpapi: ""
```

### One config, no presets

There is ONE template: `templates/researcher_config.yaml`. Every field
is blank. Copy it to `inputs/researcher_config.yaml` and let the AI
fill it from your `inputs/` + an `intake_autofill` pass — never from a
modality-specific preset. Modality presets bake in a "right answer"
the project may not actually have.

For *patterns* the AI can use to recognise project shapes (without
copying), see [`docs/DOMAIN_HINT_EXAMPLES.md`](DOMAIN_HINT_EXAMPLES.md).
That file is deliberately small and cross-domain — three reasoning
patterns, not a taxonomy.

---

## 9. FAQ for power users

**Custom / novel methodology** — Skip `tool_research_tool` (or run it just
to confirm no library fits). Run `tool_research_method` for published
precedent. Document with `mem_methods_append implementation="custom"` and
`mem_decision_log` explaining why off-the-shelf was inadequate. Prototype
in `workspace/scratch/`.

**Branching** — When an alternative methodology deserves its own thread,
create a parallel numbered path. Use `tool_branch_recommendation` if
uncertain whether to branch or extend.

**Multiple hypotheses** — `mem_hypothesis_add` for each; every experiment
step declares which hypothesis IDs it touches via `mem_hypothesis_update`.

**Mid-flow context** — Researcher dropped a new paper / dataset?
`tool_context_intake also_autofill=true` routes the file and re-runs intake.

**Workspace looks broken** — `tool_workspace_repair`. Heals missing
directories, regenerates manifest + mermaid, backs up corrupted state
ledgers. Never deletes.

**Long-running jobs** — `tool_task_run` for real background subprocesses;
poll with `tool_task_status`. Especially important on shared HPC.

**Iterative ("what's next?") workflow** — Load `guidance/iterative_planning`
or call `tool_plan_next_step` for a single-turn recommendation.

**Hallucinated citations** — Cannot happen for synthesis outputs.
`tool_synthesize` pulls every citation from Crossref / Semantic Scholar /
PubMed / arXiv and drops anything unverified. Confirm with
`tool_citations_verify`.

---

## 10. Migrating an existing project into Research OS

```bash
cd my-existing-project
research-os init . --force                  # safe — keeps your existing files
mv my_data*.csv inputs/raw_data/
mv references/*.pdf inputs/literature/
research-os start
```

In your IDE:

> "I have an existing project — fill out the intake, then propose how to continue."

`tool_intake_autofill` reads everything, classifies, proposes, and the
pipeline picks up from whichever stage already has outputs on disk.

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `research-os: command not found` | Add `~/.local/bin` to `PATH`. |
| `Not a Research OS workspace` | `research-os init .` here, or open a folder that has been initialised. The server is global and resolves per-request. |
| `WriteProtectedError` | You tried to write into `inputs/raw_data/` or `inputs/literature/`. Write to `workspace/` instead. |
| `Protocol not found` | `sys_protocol_list`. |
| Tools missing in IDE | Restart IDE; check its MCP panel for stderr. |
| `No web-search provider configured` | Set `firecrawl` or `serpapi` in researcher_config. |
| Mermaid PNG not rendering | `npm install -g @mermaid-js/mermaid-cli`. |
| `pdflatex not found` | Install TeX Live for PDF compile. |
| `tool_audit_reproducibility` slow | It re-runs every script. Skip in autopilot unless explicitly asked. |
| State / dir looks broken | `tool_workspace_repair`. |
