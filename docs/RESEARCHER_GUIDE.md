# Researcher Guide

The full guide to working with Research OS day-to-day. Read after
[START.md](START.md) (5-minute install + first project). This document
covers: the mental model, the file layout, a typical session, the
canonical 10-stage pipeline, all 114 protocols and 212 MCP tools, the
config schema, power-user patterns, and troubleshooting.

For the AI-driving-Research-OS guide (which the AI itself reads), see
[AI_GUIDE.md](AI_GUIDE.md).

---

## 1. The mental model

```
You — drop files, talk to the AI, approve or redirect.
AI in your IDE — plans, reasons, writes scripts, drafts text.
Research OS — executes, records state, enforces immutability, picks
              the right protocol via a hierarchical router, walks the
              AI through it.
```

You never call MCP tools directly. You just talk. The AI translates
your intent into the right `tool_route` call, loads the picked protocol,
executes via the right `sys_*` / `tool_*` / `mem_*` tools, and reports
back.

> Research OS does NOT manage LLM provider keys. Your IDE owns model
> access. The only credentials Research OS uses are for literature +
> web search (Crossref / Semantic Scholar / PubMed / Firecrawl /
> SerpAPI), all optional. Public endpoints work without keys.

---

## 2. The session pattern (how the AI is supposed to use Research OS)

The AI only ever acts AFTER your message arrives — there is no
"pre-boot" pass before you type. On the **first turn of a session**,
the AI fires two MCP calls back-to-back:

```
(your message arrives — every turn starts here)
1. sys_boot                            # FIRST MCP call (first turn only):
                                       # state + config + history + dep
                                       # inventory + next protocol +
                                       # pause classification + active plan
2. tool_route(prompt=<their message>)  # SECOND MCP call: hierarchical
                                       # L1 → L2 → L3 picker; returns
                                       # primary_protocol, shortcut_tool,
                                       # decomposition, complexity,
                                       # ask_user
3. If complexity = "high":
     a. tool_plan_turn               # batch sized to model_profile
     b. execute every entry in this_turn IN ORDER
     c. tool_plan_advance after each
     d. if chat_split_recommended → sys_session_handoff,
        ask for fresh chat
   If complexity = "low":
     • call shortcut_tool directly, OR
     • sys_protocol_get format='summary' (~300 tokens) →
       format='step' + step_id=<id> when ready to execute
```

On subsequent turns of the same session, `sys_boot`'s payload is still
in context — the AI skips it and goes straight to `tool_route` (or
continues an in-flight plan via `tool_plan_advance`).

A typical session boot is ~1.2K tokens (vs ~5K with naive multi-call).

---

## 3. Where files go

```
my-project/
├── inputs/                  ← IMMUTABLE — researcher provides
│   ├── raw_data/            ← drop your CSVs / parquet / FASTQ / ...
│   ├── literature/          ← drop your PDFs
│   ├── context/             ← drop notes / drafts / prior reports
│   ├── researcher_config.yaml  ← source of truth for AI behaviour
│   └── intake.md            ← auto-filled by tool_intake_autofill
│
├── docs/                    ← human-readable
│   ├── research_overview.md
│   ├── domain_summary.md
│   ├── research_design.md
│   └── glossary.md
│
├── workspace/               ← ACTIVE — experiments live here
│   ├── methods.md           ← append-only method log
│   ├── analysis.md          ← chronological narrative
│   ├── citations.md         ← auto-generated bibliography
│   ├── workflow.mermaid     ← cross-step DAG
│   ├── 01_baseline_eda/     ← numbered experiment steps
│   │   ├── README.md
│   │   ├── conclusions.md
│   │   ├── scripts/         ← versioned scripts (_v1, _v2, ...)
│   │   ├── data/{input,output}/
│   │   ├── outputs/{reports,figures,tables}/
│   │   ├── environment/     ← per-step requirements.txt
│   │   └── literature/      ← step-scoped PDFs (optional)
│   ├── 02_data_preparation/
│   ├── scratch/             ← AI sandbox (gitignored)
│   └── logs/                ← search / audit / repair / task logs
│
├── synthesis/               ← FINAL — only created when you ask
│   ├── paper.md / .tex / .pdf
│   ├── abstract.md
│   ├── poster.tex / .pdf + poster_qr.png
│   ├── dashboard.html       ← single-file, offline-safe
│   ├── slides.{tex,md,html,pptx}
│   ├── handout.pdf + handout_qr.png
│   ├── lay_summary.md
│   ├── cover_letter.md
│   ├── data_availability.md / author_contributions.md / ...
│   └── references.bib
│
├── AGENTS.md                ← canonical AI rules (every IDE reads it)
├── CLAUDE.md  .windsurfrules  .cursor/  .claude/  ...
└── .os_state/               ← internal (do NOT edit by hand)
```

You touch `inputs/`. The AI touches `workspace/` and `synthesis/`.
Nothing in `inputs/raw_data/` or `inputs/literature/` is ever modified
— Research OS blocks writes at the server level.

---

## 4. A typical session (narrative)

### 4.1 First time — set up the project

> **You:** I dropped my CSV and a couple of papers in inputs/. Fill out
> the intake.

The AI calls `tool_intake_autofill`, reads everything, proposes a
research question + domain + hypotheses, and shows you what it
inferred. You approve or refine.

### 4.2 Start analysing

> **You:** OK, run a baseline EDA on the data.

The AI loads `guidance/analysis_plan`, creates
`workspace/01_baseline_eda/`, writes an atomic Python (or R / Julia)
script, runs it, drops outputs + figures + reports into the step, and
writes `conclusions.md`.

### 4.3 Course-correct mid-flow

> **You:** Actually, group by quarter instead of month.

The AI bumps the script to `_v2`, re-runs, updates conclusions. Old
versions stay on disk for provenance.

### 4.4 Branch into a parallel approach

> **You:** Try a tree-based model too, in parallel.

The AI calls `tool_branch_recommendation` (decides: branch since we
have < 3 active paths), runs `sys_path_create`, sets up
`workspace/03_random_forest/`, executes, compares across the paths.

### 4.5 Mid-flow context (a new paper appears)

> **You:** My PI sent me a new paper. *(drag-drop into the project)*
> Integrate it.

`tool_context_intake also_autofill=true` auto-routes the file to
`inputs/literature/`, updates the bibliography, revisits the research
question / hypotheses if the new paper warrants it, and annotates
`analysis.md`.

### 4.6 Decide what's next

> **You:** What should I do next?

The AI loads `guidance/iterative_planning`. Surveys state, pulls fresh
literature on your open question, searches the web for relevant tools,
and proposes 2-3 concrete options with a recommendation.

### 4.7 Synthesise

> **You:** Write the paper for a journal submission.

The AI loads `synthesis/synthesis_paper` → workshops the title via
`synthesis/synthesis_title_workshop` → drafts Methods → Results →
`writing/writing_discussion` → `writing/writing_limitations` →
Introduction → Abstract → assembles the end matter via
`writing/writing_data_availability` (CRediT / data avail / funding /
COI / ack) → drafts the cover letter via
`synthesis/synthesis_cover_letter` → runs
`audit/pre_submission_checklist` for a final GREEN / YELLOW / RED gate.

Also want a poster?

> **You:** And make a poster for the academic conference.

`synthesis/synthesis_poster` builds a tikzposter PDF with a QR code
linking back to the paper and a single-headline test.

### 4.8 Hand off at end-of-day

> **You:** Wrap up the session.

`sys_session_handoff` writes a markdown summary with state + recent
analysis + a resume prompt you can paste into a fresh chat tomorrow.

---

## 5. The canonical 10-stage pipeline

`sys_protocol_next` returns the first stage whose outputs (and
execution log) say "not done yet".

| # | Protocol                              | Done when... |
|---|---------------------------------------|---|
| 1 | `guidance/session_boot`               | first protocol logged |
| 2 | `guidance/project_startup`            | `intake.md` filled + research question confirmed |
| 3 | `domain/domain_analysis`              | `docs/domain_summary.md` exists |
| 4 | `domain/research_design`              | `docs/research_design.md` exists |
| 5 | `methodology/methodology_selection`   | `workspace/methods.md` substantive |
| 6 | `literature/literature_search`        | `inputs/literature_index.yaml` + `citations.md` exist |
| 7 | `guidance/analysis_plan`              | at least one `workspace/NN/conclusions.md` non-empty |
| 8 | `reproducibility/reproducibility`     | `workspace/*/environment/requirements.txt` exists |
| 9 | `audit/audit_and_validation`          | `workspace/logs/audit_report.md` exists |
| 10| `synthesis/synthesis_paper`           | `synthesis/paper.md` exists |

You do NOT have to follow this in order. Off-pipeline entry points:

- **No data, just a question** → `methodology/methodological_consultation`
- **Data, results, no RO history** → `guidance/mid_pipeline_entry` →
  `synthesis/synthesis_from_inputs`
- **Just want a figure** → `visualization/visualization_workflow`
- **Just want a poster** → `synthesis/synthesis_poster`
- **Just want a lab-meeting deck** → `synthesis/synthesis_slides`
- **Quick critique of someone else's paper** →
  `guidance/quick_paper_review`
- **Multi-paper journal club** → `literature/comparative_paper_review`
- **Power analysis only** → `methodology/power_analysis`
- **Reproduce a published paper** → `methodology/reproduction_attempt`
- **Lay summary / press release** → `synthesis/synthesis_lay_summary`

For the full role × goal × output map, see [USE_CASES.md](USE_CASES.md).

---

## 6. The on-demand protocol surface (114 total)

For per-protocol triggers + quality bars, see
[PROTOCOLS.md](PROTOCOLS.md). High-level inventory:

**Guidance (17)** — session + flow control. `session_boot` /
`session_resume` / `chat_handoff` / `collaboration_handoff` /
`autopilot` / `casual_exploration` / `quick_paper_review` /
`code_review` / `peer_review_response` / `project_startup` /
`analysis_plan` / `iterative_planning` / `dead_end_routing` /
`hypothesis_tracking` / `glossary_update` / `mid_pipeline_entry` /
`constructive_disagreement`.

**Domain + methodology (42)** — `domain_analysis` / `research_design` /
`methodology_selection` / `deep_domain_research` / `preregistration` /
`tool_discovery` + per-method: `causal_inference_deep` /
`machine_learning` / `clinical_trials` / `meta_analysis` /
`survey_psychometrics` / `qualitative_research` / `simulation_studies`
/ `replication_study` / `ablation_study` / `pilot_study` /
`mixed_methods` / `bayesian_analysis` / `timeseries_analysis` +
design / workflow: `exploratory_data_analysis` / `method_comparison` /
`data_quality_audit` / `power_analysis` / `evaluation_design` /
`hyperparameter_search_design` / `data_ethics_review` /
`reproduction_attempt` / `methodological_consultation` +
**v1.4.0** language/tool-stack doctrine: **`pick_tool_stack`** (R vs
Python per sub-task — bulk RNA-seq → R Bioconductor, scRNA-seq →
Python scanpy, Cox PH → R survival, WGCNA → R, geospatial → Python
geopandas, psychometrics → R psych/lavaan; persists to
`workspace/<step>/scratch/stack_plan.md`) / **`mixed_language_orchestration`**
(Python↔R↔Bash composition: hand-off file contracts, serialization
matrix, per-language `pipeline.yaml` tags, schema assertions).

**Literature (5)** — `literature_search` (with forward-citation walk +
predatory-venue check) / `systematic_review` / `evidence_synthesis` /
`comparative_paper_review` / **`literature_per_step`** (v1.4.0 —
per-step search → download → cite → write `findings_vs_literature.md`
with AGREES \| DISAGREES \| EXTENDS \| DEFERRED verdicts; gated by
`tool_audit_step_literature` before `tool_path_finalize`).

**Writing (9)** — `writing_core` (universal rules) + per-section:
`writing_methods` / `writing_results` / `writing_discussion` /
`writing_limitations` / `writing_conclusions` / `writing_citations` /
`writing_readme` / `writing_analysis_log` / `writing_data_availability`
(end matter — data / code / CRediT / funding / COI / ack).

**Visualization (6)** — `figure_guidelines` (style + rules) /
`visualization_workflow` (build / polish) / `figure_critique` /
`multi_panel_composition` / `figure_narrative_arc` /
`color_accessibility_audit`.

**Synthesis (14)** — `synthesis_paper` / `synthesis_abstract` /
`synthesis_poster` (with QR + single-headline test) /
`synthesis_dashboard` (Playwright-tested) / `synthesis_grant` /
`synthesis_report` / `synthesis_null_findings` (anti-file-drawer) /
`synthesis_slides` (talks) / `synthesis_lay_summary` (outreach) /
`synthesis_progress_update` (PI / advisor) / `synthesis_handout`
(printable + QR) / `synthesis_from_inputs` (no in-RO analysis) /
`synthesis_cover_letter` / `synthesis_title_workshop`.

**Audit + reproducibility (3)** — `audit_and_validation` (master
quality audit) / `pre_submission_checklist` (final GREEN/YELLOW/RED
gate) / `reproducibility` (env snapshot + Dockerfile + seed
verification).

---

## 7. MCP tools (212 total)

> All names use underscores. Dot notation + legacy names are
> auto-rewritten. Full catalogue with example calls:
> [TOOLS.md](TOOLS.md).

### Routing layer — call FIRST every session

| Tool | Purpose |
|---|---|
| `sys_boot` | One call returns state + config + history + dep inventory + next protocol + pause classification + active plan. Replaces 4-5 separate calls. |
| `tool_route` | Hierarchical L1 → L2 → L3 picker for "which protocol fits this prompt". Returns ambiguity-aware (`ask_user` for L≥2 ties). |
| `tool_plan_turn` | Per-turn batching sized to `model_profile` (small=1, medium=3, large=6 steps). Returns `chat_split_recommended` for long plans. |
| `tool_plan_advance` / `tool_plan_clear` | Walk or discard the active plan. |
| `sys_active_project` | Returns the project root the server resolved for THIS request + how (env var / cwd walk / fallback). |
| `sys_help` | AI orientation block — routing pattern, namespaces, protocol categories, anti-patterns. Pass `topic=` for category-specific guidance. |
| `sys_tool_describe` | Full description + schema for one tool. |
| `sys_active_tools` | Tool shortlist for a protocol (essentials + decomposition tools). |
| `sys_protocol_get` | `format='summary'` (~300 tokens) / `format='step' step_id='...'` / `format='full'`. |
| `sys_dep_inventory` | Which optional extras failed to import. |

### `sys_*` — workspace, state, files, paths, checkpoints

| Tool | Purpose |
|---|---|
| `sys_state_get` | Full / minimal / markdown state snapshot. (Prefer `sys_boot` at session start.) |
| `sys_workspace_scaffold` / `sys_workspace_tree` | Re-create / inspect the workspace tree. |
| `sys_file_read` / `_write` / `_list` / `_delete` / `_validate_md` | File I/O (write blocked under `inputs/raw_data/` and `inputs/literature/`). |
| `sys_path_create` / `_abandon` / `_list` | Numbered experiment folders. |
| `sys_checkpoint_create` / `_rollback` / `_list` | Workspace snapshots (hardlinked, fast). |
| `sys_config_get` / `_set` / `_validate` | `researcher_config.yaml`. |
| `sys_notify` | Append to `workspace/logs/notifications.log`. |
| `sys_session_handoff` | Structured handoff doc + fresh checkpoint. |
| `sys_env_snapshot` / `_docker_generate` | Capture + containerise the env. |

### `tool_*` — research workflow

| Tool | Purpose |
|---|---|
| `tool_session_resume` / `tool_progress_digest` / `tool_dead_end_lessons` | Session continuity + bookkeeping. |
| `tool_quick_review` / `tool_redteam_review` | Stage critical-appraisal + adversarial-review skeletons. |
| `tool_search_semantic_scholar` / `_pubmed` / `_crossref` / `_arxiv` / `_web` | Literature + web search. |
| `tool_literature_download` / `tool_literature_search_and_save` / `tool_step_literature_list` | Per-step literature management. |
| `tool_python_exec` / `_r_exec` / `_julia_exec` / `_bash_exec` / `tool_notebook_exec` / `tool_rmarkdown_render` | Run scripts / notebooks. Returncode-aware. |
| `tool_package_install` | `pip install` + update requirements. |
| `tool_data_sample` / `_profile` / `_convert` | Sample, profile, convert tabular data. |
| `tool_audit_synthesis` / `_step_completeness` / `_code_quality` / `_prose` / `_claims` / `_figure_full` / `_citations` / `_assumptions` / `_reproducibility` / `_quality_full` | Real audits — citation lookups, statistical power, assumption tests, figure DPI, full re-runs, master quality audit. |
| `tool_synthesize_plan` / `tool_synthesize` | Plan section order; build paper / abstract / poster / dashboard / grant / report / slides / lay / handout with verified citations. |
| `tool_latex_compile` / `tool_poster_create` / `tool_dashboard_create` / `tool_dashboard_test_generate` / `tool_dashboard_test_run` | PDF + tikzposter + single-file HTML dashboard + Playwright suite. |
| `tool_research_method` / `tool_research_tool` / `tool_external_tool_instructions` / `tool_plan_step` | Reasoning + grounding helpers. |
| `tool_plan_next_step` / `tool_branch_recommendation` / `tool_alternative_path_propose` | Iterative planning. |
| `tool_grounding_register` / `_verify` | Bind decisions to PROV-O sources. |
| `tool_preregister_freeze` / `_diff` | Lock the SAP before data; diff at synthesis. |
| `tool_sensitivity_define` / `_run` | Specification-curve / multiverse analyses. |
| `tool_step_pipeline_define` / `_run` / `tool_workflow_dag` / `tool_step_env_lock` | Per-step sub-task pipelines + DAG + env locking. |
| `tool_slurm_submit` / `_status` / `_fetch` | HPC submission. |
| `tool_task_run` / `_status` / `_list` / `_kill` | Real background subprocesses for shared servers. |
| `tool_scratch_write` / `_run` / `_list` / `_clear` | Workspace sandbox. |
| `tool_workspace_repair` | Heal a broken workspace; never deletes. |
| `tool_intake_autofill` / `tool_context_intake` | Auto-fill + mid-flow context injection. |
| `tool_lessons_record` / `_consult` | Carry lessons across sessions. |
| `tool_null_findings_report` | Anti-file-drawer report assembly. |
| `tool_cache_clear` | Wipe search cache per provider / older-than-N-days. |

### `mem_*` — append-only logs, decisions, hypotheses

| Tool | Purpose |
|---|---|
| `mem_analysis_log` / `mem_methods_append` / `mem_citations_generate` / `mem_intake_regenerate` / `mem_decision_log` | Append to canonical workspace logs. |
| `mem_hypothesis_add` / `_update` / `_list` | Multi-hypothesis ledger. |

---

## 8. Configuration (`inputs/researcher_config.yaml`)

Auto-created on `init`. **Every field is optional** — blank fields get
sensible defaults applied silently. The file is reserved for fields a
**researcher actively chooses**: who they are, what they want to
produce, how they want the AI to behave. Domain / research question /
hypotheses are NOT here — those are AI-inferred via
`tool_intake_autofill` and written to `inputs/intake.md` +
`docs/research_overview.md` (with hypotheses also tracked in
`.os_state/state.json`).

Fields are ordered most → least important:

The canonical schema lives at
[`templates/researcher_config.yaml`](../templates/researcher_config.yaml)
— this section mirrors it 1:1.

```yaml
researcher:                       # who AI is talking to (most important)
  name: ""
  institution: ""                 # rendered as poster / paper author affiliation
  orcid: ""
  email: ""

project_name: ""                  # blank → uses directory name

research_goal:                    # what you want the AI to produce
  output_types: []                # paper | abstract | poster |
                                  # dashboard | report | exploratory
  target_venue: ""                # journal | conference | preprint |
                                  #   dissertation | report
  poster_dimensions: "36x48"
  # Optional extension fields read by audit + synthesis tools when
  # present (each is OPTIONAL — blanks are inferred via intake):
  # primary_question: ""          # single sentence — preregistration anchor
  # design: ""                    # observational | RCT | cohort | …
  # background: ""                # one paragraph — paper Background prefill
  # measurement_instrument: ""    # name of scale / assay; surfaces in audits

interaction:                      # how the AI should behave
  # manual | supervised | autopilot | coaching
  #   coaching → AI doesn't auto-execute; surfaces pedagogical preludes,
  #              explains WHY each gate exists, asks the researcher to
  #              draft then critiques. Pair with tool_mistake_replay.
  autonomy_level: "supervised"
  quality_gate_policy: "enforce"  # enforce | allow_override | warn_only
  ambiguity_posture: "ask_when_uncertain"  # | take_best_default

# How hard audits enforce gates. Pre-v1.5.1 behaviour was "normal".
#   light  → most blockers become notes (sandbox / exploratory)
#   normal → pre-v1.5.1 behaviour
#   strict → every gate at full enforcement
#   auto   → follows tool_rigor_signals_scan; substantive projects
#            with methods.md + citations + preregistration score
#            high and get "light"; sketches score low and get "strict"
gate_strictness: "auto"           # light | normal | strict | auto

# Sets the default audit strictness across the whole project.
#   throwaway → light  (sandbox / exploratory; no publication intent)
#   sketch    → normal (working draft; may or may not publish)
#   production → strict (active path to submission / hand-off)
project_tier: "production"        # throwaway | sketch | production

model_profile: "medium"           # small | medium | large
                                  # — drives tool_plan_turn batch size

writing_preferences:
  citation_style: "apa"           # apa | vancouver | acm | ieee | nature
  language: "en-US"
  # Typst venue template for tool_paper_compile_typst.
  #   nature | science | nejm | cell | ieee_conf | neurips | acl
  #   plos  | generic_two_column | generic_thesis
  venue_template: "generic_two_column"
  # PDF engine for the synthesis pipeline. "typst" recommended (fast,
  # single-binary install). Use "latex" when a journal requires .tex.
  pdf_compile_engine: "typst"     # typst | latex | both

# Compute environment + exec-safety knobs. All optional; defaults shown.
runtime:
  shared_server: false                  # true on HPC / shared boxes
                                        # — flips long_running default
  long_running_threshold_seconds: 60    # tool_task_run vs inline cutoff
  default_n_for_sampling: 1000          # default sample size for sampling
  cluster_defaults:                     # SLURM defaults for tool_slurm_submit
    partition: ""                       # blank → no --partition flag
    time: "01:00:00"                    # wall clock per job
    cpus_per_task: 4
    mem: "8G"
  # Subprocess / command-execution safety surface (all defaults are SAFE).
  allow_arbitrary: false                # true permits commands outside allowlist
  command_allowlist:                    # extend the built-in safe set
    - "python"
    - "Rscript"
    - "git"
  allow_shell_meta: false               # true permits ; | & $() in args
  max_cpu_seconds: 1800                 # per-subprocess CPU cap (30 min)
  max_memory_mb: 4096                   # per-subprocess RSS cap (4 GiB)
  max_file_size_mb: 100                 # per-output-file size cap

# Language + tool-stack preferences. Read by methodology/pick_tool_stack.
# AI uses these as hints (NOT hard constraints) — field-practice wins.
tool_stack:
  preferred_languages: ["python", "R"]      # order = tie-breaker
  allow_mixed_language_steps: true
  field_practice_overrides_preference: true # R Bioconductor for DE etc.
  cite_field_practice_when_choosing: true

# Top-level helpers read by various tools (all optional):
# domain: ""                       # short label (e.g. "neuroscience")
# research_question: ""            # convenience mirror of research_goal.primary_question
# authors: []                      # list of names for paper/poster title block

api_keys:                         # all optional — NO LLM provider keys
  semantic_scholar: ""
  pubmed: ""
  crossref: ""
  firecrawl: ""
  serpapi: ""
```

### One config, no presets

There is ONE template: `templates/researcher_config.yaml`. Every field
is blank. The AI never invents identity (`researcher.*`) or goals
(`research_goal.*`) — those come from you. Research-inferred metadata
(domain, question, hypotheses) lives outside the config, populated by
an `intake_autofill` pass.

---

## 9. Power-user patterns

### Custom / novel methodology

Skip `tool_research_tool` (or run it to confirm no library fits). Run
`tool_research_method` for published precedent. Document with
`mem_methods_append implementation="custom"` and `mem_decision_log`
explaining why off-the-shelf was inadequate. Prototype in
`workspace/scratch/`; promote into a numbered step when it works.

### Branching

When an alternative methodology deserves its own thread, create a
parallel numbered path via `sys_path_create`. Use
`tool_branch_recommendation` if uncertain whether to branch or extend.
For methodology-level branches (e.g. "the literature also supports X
for this data shape"), `tool_alternative_path_propose` is
confidence-gated.

### Multiple hypotheses

`mem_hypothesis_add` for each (auto-assigned `H1, H2, …` or you pick
the ID). Every experiment step declares which hypothesis IDs it
touches via `mem_hypothesis_update status=testing|supported|refuted|
inconclusive evidence=<one-line>`.

### Mid-flow context

Researcher drops a new paper / dataset?
`tool_context_intake also_autofill=true` routes the file and re-runs
intake.

### Long-running jobs

`tool_task_run` for real background subprocesses (`subprocess.Popen`,
zombie-aware); poll with `tool_task_status`. Especially important on
shared HPC. For SLURM clusters, use `tool_slurm_submit` /
`tool_slurm_status` / `tool_slurm_fetch`.

### Iterative ("what's next?") workflow

Load `guidance/iterative_planning` or call `tool_plan_next_step` for a
single-turn recommendation.

### Specification curves / multiverse

Define a grid of analytic choices via `tool_sensitivity_define`; run
the fan-out via `tool_sensitivity_run`. Returns a specification-curve
plot that distinguishes ROBUST findings from FRAGILE ones.

### Preregistration drift

`tool_preregister_freeze` content-hashes the SAP before data;
`tool_preregister_diff` surfaces every deviation at synthesis time so
the Discussion can acknowledge them honestly.

### Hallucinated citations

Cannot happen for synthesis outputs. `tool_synthesize` pulls every
citation from Crossref / Semantic Scholar / PubMed / arXiv and drops
anything unverified. Confirm on demand with `tool_citations_verify`.

### Hallucinated numbers

`tool_audit_claims` extracts every numeric claim from
`synthesis/paper.md` and verifies each appears verbatim (or within 1%
tolerance) in some workspace CSV / JSON / MD / TXT. BLOCKS
`tool_synthesize` until cleared.

### Multi-project / shared data

Two patterns:

* **Symlink shared data**: `ln -s /path/to/shared/raw inputs/raw_data`
  — Research OS treats it as immutable, same as a local copy.
* **Separate Research OS workspaces per paper**: each gets its own
  `inputs/`, `workspace/`, `synthesis/`. Use `inputs/context/` to
  drop pointers to sibling projects.

---

## 10. Migrating an existing project into Research OS

```bash
cd my-existing-project
research-os init . --force                 # safe — keeps your existing files
mv my_data*.csv inputs/raw_data/
mv references/*.pdf inputs/literature/
mv notes/*.md inputs/context/
```

Open your IDE on the folder. Then:

> "I have an existing project — bring it into research-os."

Loads `guidance/mid_pipeline_entry` — classifies your project into one
of seven entry archetypes (DATA-READY / ANALYSES-READY / FIGURES-READY
/ SYNTHESIS-READY / PRIOR-RO-PROJECT / CONCEPTUAL / MIXED) and routes
to the right downstream protocol without forcing redundant intake. The
provenance ceiling is recorded so any downstream synthesis discloses
what was reasoned vs imported.

For a project where the analyses were done OUTSIDE Research OS:

> "We already analysed this, just write it up."

Loads `synthesis/synthesis_from_inputs`. Builds a SHADOW workspace
step that anchors the synthesis, imports the artefacts, runs the
chosen target synthesis on top, and stamps a provenance ceiling
paragraph into the deliverable.

---

## 11. Codebase layout (for power users + contributors)

```
src/research_os/
├── server.py                    # MCP server + dispatcher + 212 tool defs
├── cli.py                       # `init` + `start`
├── wizard.py                    # interactive `init` wizard
├── project_ops.py               # scaffolding, state, mermaid, intake regen
├── collab.py                    # multi-researcher project ops
├── verify.py                    # `research-os verify` integrity check
├── tui.py                       # status / log TUI
├── logo.py                      # ASCII logo
├── config.py / errors.py / __init__.py
├── adapters/                    # external-API adapter framework
│   ├── base.py                  # ResearchAdapter ABC
│   ├── loader.py                # discover installed adapters
│   └── runner.py                # tool_adapter_extract / _run_all
├── assets/js/                   # bundled JS (mermaid, plotly, vega, vis-network)
├── data/typst/                  # 11 Typst venue templates (Nature, Science, …)
├── inputs/                      # paper + paste intake helpers
├── plugins/                     # domain-pack loader + pack_api surface
├── protocols/                   # 114 YAML protocols + _router_index.yaml
│   ├── audit/        (3)        # audit_and_validation, pre_submission_checklist …
│   ├── domain/       (2)
│   ├── guidance/    (16)        # autopilot, code_review, mid_pipeline_entry …
│   ├── literature/   (5)
│   ├── methodology/ (37)        # the biggest category
│   ├── reproducibility/ (1)
│   ├── synthesis/   (18)
│   ├── visualization/ (14)
│   └── writing/     (18)
├── state/                       # ResearchLedger (state.json schema)
├── testing/                     # stress-runner harness (not the unit tests)
├── utils/                       # asset manager, common helpers
└── tools/
    └── actions/
        ├── protocol.py          # YAML loader + protocol_completion injection
        ├── router.py            # sys_boot, tool_route, plan_turn
        ├── semantic.py          # sys_semantic_tool_search, tool_semantic_route
        ├── audit/               # audit, md_audit, code_quality, content_depth,
        │                        #   coherence, prose_quality, claim_grounding,
        │                        #   preregistration, redteam, dashboard_content,
        │                        #   figure_interactivity, step_literature,
        │                        #   null_findings
        ├── data/                # data, profiling, intake, context_intake
        ├── exec/                # scripts, notebook, tasks, environment,
        │                        #   sensitivity, step_pipeline, cluster
        ├── memory/              # mem_* hypotheses + append-only helpers
        ├── research/            # research_method/tool/plan, planning, grounding,
        │                        #   lessons, plan_next_step
        ├── search/              # search providers (pubmed, arxiv, web, scholar),
        │                        #   literature download / cache
        ├── state/               # config, path, checkpoint, scratch, repair,
        │                        #   reliability, certifications, freshness,
        │                        #   iteration, mistake_replay, provenance,
        │                        #   paywall_memory, quick_mode, revision,
        │                        #   rigor_signals, interaction, extractors
        ├── synthesis/           # synthesize, latex, citations, dashboard,
        │                        #   dashboard_v2, dashboard_story, typst,
        │                        #   preview, discussion_from_verdicts
        └── viz/                 # figures, dashboard_tests

tests/
├── conftest.py                  # isolates each test on tmp_path
├── unit/                        # pure-function tests, fast (~700 cases)
├── integration/                 # workspace + pipeline + reorg-aware
└── tools/                       # one file per MCP tool group

Run `tree -L 3 src/research_os` for the live tree.
```

Run all tests:
```bash
pytest -q
```

Run a slice:
```bash
pytest tests/unit -q
pytest tests/integration -q
pytest tests/tools/test_router.py -q
```

Preflight (everything-is-wired check):
```bash
python scripts/preflight.py
```

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `research-os: command not found` | Add `~/.local/bin` (or your venv's `bin/`) to `PATH`. |
| `Not a Research OS workspace` | `research-os init .` here, or open a folder that has been initialised. The server is global and resolves per-request. |
| `WriteProtectedError` | You tried to write into `inputs/raw_data/` or `inputs/literature/`. Write to `workspace/` instead. |
| Tools missing in IDE | Restart IDE; check its MCP panel for stderr. |
| AI seems lost / confused | "show me sys_help" — AI re-orients. |
| AI seems to forget context | "re-run sys_protocol_get for the current protocol". |
| Wrong protocol picked | "actually I meant <X>" — AI re-routes. |
| AI making bad calls | Switch autonomy to `manual` or `supervised`. |
| Workspace looks broken | "fix the workspace" — `tool_workspace_repair`, never deletes. |
| Chat too long | "hand off the session" — open fresh chat, "pick up where we left off". |
| Deleted by mistake | "list checkpoints" → "rollback to <id>". |
| Stale memory / re-doing work | `sys_protocol_next` checks BOTH execution log AND on-disk artifacts; if both say "done", the AI moves on. After migrating from outside RO, `tool_workspace_repair` rebuilds expected metadata. |
| `No web-search provider configured` | Set `firecrawl` or `serpapi` in researcher_config (optional). |
| Mermaid PNG not rendering | `npm install -g @mermaid-js/mermaid-cli`. |
| `pdflatex not found` | Install TeX Live. The relevant tools fail gracefully without it. |
| `tool_audit_reproducibility` slow | It re-runs every script. Skip in autopilot unless explicitly asked. |
| `Protocol not found` | `sys_protocol_list`. |
| "Unknown tool" error | The dispatcher accepts `sys_state_get` / `sys.state.get` / legacy `sys_guidance_get`. If still failing, "Call `sys_protocol_list` and tell me what's available." |

For more: [FAQ.md](FAQ.md).

---

## See also

* [START.md](START.md) — install + first-hour walkthrough + cheatsheet.
* [USE_CASES.md](USE_CASES.md) — role × goal × output map.
* [SETUP.md](SETUP.md) — install + per-IDE wiring + troubleshooting.
* [FAQ.md](FAQ.md) — common questions.
* [PROTOCOLS.md](PROTOCOLS.md) — catalogue of all 114 protocols.
* [TOOLS.md](TOOLS.md) — catalogue of all 212 MCP tools.
* [AI_GUIDE.md](AI_GUIDE.md) — operating manual for the AI driving Research OS.
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — scaffold-not-script
  principle (for protocol authors / contributors).
