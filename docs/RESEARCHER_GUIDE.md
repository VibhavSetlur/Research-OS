# Researcher Guide

The full guide to working with Research OS day-to-day. Read after
[START.md](START.md) (5-minute install + first project). This document
covers: the mental model, the file layout, a typical session, the
canonical 10-stage pipeline, all 117 core protocols and 144 live MCP
tools, the config schema, power-user patterns, and troubleshooting.

For the AI-driving-Research-OS guide (which the AI itself reads), see
[AI_GUIDE.md](AI_GUIDE.md). For the v2.0.0 upgrade recipe, see
`CHANGELOG.md [2.0.0]`.

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
"pre-boot" pass before you type. v2.0.0 ships the canonical boot
ritual at the MCP handshake (`instructions` field on `initialize`), so
a fresh client sees it instead of discovering it. On the **first turn
of a session**, the AI fires these calls back-to-back:

```
(your message arrives — every turn starts here)
1. sys_boot                            # FIRST MCP call (first turn only):
                                       # state + config + history + dep
                                       # inventory + next protocol +
                                       # pause classification + active plan
2. tool_route(prompt=<their message>)  # SECOND MCP call: hybrid router
                                       # (semantic first, hierarchical
                                       # L1 → L2 → L3 fallback). Returns
                                       # primary_protocol, recommended_action
                                       # (literal next-call string),
                                       # why_matched, tier, alternatives,
                                       # decomposition, complexity, ask_user,
                                       # shortcut_tool.
3. If complexity = "high":
     a. tool_plan(operation='turn')   # batch sized to model_profile
     b. execute every entry in this_turn IN ORDER
     c. tool_plan(operation='advance') after each
     d. if chat_split_recommended → sys_session_handoff,
        ask for fresh chat
   If complexity = "low":
     • call shortcut_tool directly, OR
     • sys_protocol_get format='summary' (DEFAULT, ~300 tokens) →
       format='step' + step_id=<id> when ready to execute
4. sys_active_tools(protocol_name=<from-step-2>)
                                       # 13-18-tool scoped shortlist for
                                       # the protocol's working surface
```

On subsequent turns of the same session, `sys_boot`'s payload is still
in context — the AI skips it and goes straight to `tool_route` (or
continues an in-flight plan via `tool_plan(operation='advance')`).

A typical session boot is ~1.2K tokens (vs ~5K with naive multi-call).
v2.0.0 flipped `sys_protocol_get`'s default `format` from `full` to
`summary` (5-10× cheaper per-turn load on the same protocol).

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
│   ├── paper.typ / .pdf  (or .tex when LaTeX submission required)
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

### Extra `inputs/` subfolders some packs expect

The wizard always creates `raw_data/`, `literature/`, and `context/`.
Pack-specific protocols may also expect:

| Subfolder | What goes there | Required by |
|---|---|---|
| `inputs/corpus/` | A text corpus you'll analyse computationally (novels, transcripts, primary sources). Create when you stage the corpus; the humanities pack will populate `inputs/corpus/corpus_manifest.csv` during intake. | `humanities/textual/distant_reading`, `humanities/method/digital_humanities_workflow` |
| `inputs/textual/passages/` | Hand-picked passages for line-by-line close reading. One Markdown file per passage with the block quote at the top + edition pin in the front matter. | `humanities/method/close_reading` |
| `inputs/preliminaries.md` | Free-text Markdown defining every object in your theorem claim, plus the key prior results you'll cite as lemmas. Hard prerequisite — `proof_strategy_selection` blocks if this file is missing. | `theory_math/method/proof_strategy_selection`, downstream theory protocols |
| `inputs/context/code/` | The source code under benchmark (the C / Rust / Python implementation you're measuring, **not** your analysis scripts). Keeping it under `context/` instead of `raw_data/` makes it inspectable but not server-immutable, so you can iterate on the implementation. | `methodology/method_comparison` (engineering pack) |
| `inputs/context/instruments/` | IRB protocols, interview guides, survey instruments, consent forms. Surfaces in `tool_audit_quality_full` and `methodology/qualitative_quality_audit`. | `methodology/qualitative_research` |

The wizard does not pre-create these because most projects don't need
them — but mention them when you stage files so a fresh AI agent knows
where to look. The immutability guarantee only applies to
`inputs/raw_data/` and `inputs/literature/`; the extra subfolders
above stay editable.

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
have < 3 active paths), runs `sys_path(operation='create')`, sets up
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

`synthesis/synthesis_poster` builds a Typst poster PDF with a QR code
linking back to the paper and a single-headline test.

#### The paper pipeline (file flow)

When `synthesis/synthesis_paper` runs, the AI authors
`synthesis/paper.typ` directly and the tool surface validates +
compiles. Two stages, not three:

```
synthesis/paper.typ   →   synthesis/paper.pdf
(AI-authored,             (tool_typst_compile output;
following the              re-run after any .typ edit)
synthesis_paper protocol)
```

* **`paper.typ`** — the AI authors this directly, section by section,
  importing the venue template from `_typst_templates/`. Per-pack
  section overrides (e.g. `theory_math` swaps IMRAD for
  Theorem/Proof) are encoded in the active pack's
  `synthesis_paper.yaml` design principles; the AI applies them as
  it writes.
* **`paper.tex`** — only emitted when the venue requires LaTeX
  (Nature, Cell, NeurIPS LaTeX templates). The AI authors `.tex`
  directly and calls `tool_latex_compile`.
* **`paper.pdf`** — the file you send to a co-author or upload to a
  preprint server. Never edit by hand; re-run the compile.

The AI's edits go in `paper.typ`. The `tool_synthesis_check` audit
runs against `paper.typ` (or `paper.tex`) and surfaces missing
sections, ungrounded claims, citation issues, and AI clichés before
compile.

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
| 10| `synthesis/synthesis_paper`           | `synthesis/paper.typ` + `paper.pdf` exist |

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

## 6. The on-demand protocol surface (117 core, +36 pack)

For per-protocol triggers + quality bars, see
[PROTOCOLS.md](PROTOCOLS.md). All 117 carry `tier:` + `scope_tags`
(v2.0.0). High-level inventory:

**Guidance (19)** — session + flow control. `session_boot` /
`session_resume` / `chat_handoff` / `collaboration_handoff` /
`autopilot` / `casual_exploration` / `quick_paper_review` /
`code_review` / `peer_review_response` / `project_startup` /
`analysis_plan` / `iterative_planning` / `dead_end_routing` /
`hypothesis_tracking` / `glossary_update` / `mid_pipeline_entry` /
`constructive_disagreement` / `scope_clarification` /
`revise_and_resubmit`.

**Domain + methodology (45)** — 2 in `domain/`
(`domain_analysis`, `research_design`) + 43 in `methodology/`:
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
language/tool-stack doctrine: `pick_tool_stack` (R vs Python per
sub-task — bulk RNA-seq → R Bioconductor, scRNA-seq → Python scanpy,
Cox PH → R survival, WGCNA → R, geospatial → Python geopandas,
psychometrics → R psych/lavaan; persists to
`workspace/<step>/scratch/stack_plan.md`) / `mixed_language_orchestration`
(Python↔R↔Bash composition) + the cross-cutting protocols
`qualitative_pii_redaction`, `bootstrapping_design`,
`cox_ph_diagnostics`, `data_management_plan`, `fairness_audit`,
`inter_rater_reliability`, `interview_guide_design`,
`mcp_ecosystem_integration`, `missing_data_strategy`,
`multiple_comparisons`, `survey_design`, `uncertainty_quantification`,
`coding_scheme_development`, `qualitative_quality_audit`,
`external_tool_setup`.

**Literature (5)** — `literature_search` (with forward-citation walk +
predatory-venue check) / `systematic_review` / `evidence_synthesis` /
`comparative_paper_review` / `literature_per_step` (per-step search →
download → cite → write `findings_vs_literature.md` with
`AGREES \| DISAGREES \| EXTENDS \| DEFERRED \| IMPORTED_AS_CITED`
verdicts; gated by `tool_audit(scope='step', dimension='literature')`
before `tool_path_finalize`).

**Writing (10)** — `writing_core` (universal rules) + per-section:
`writing_methods` / `writing_results` / `writing_discussion` /
`writing_limitations` / `writing_conclusions` / `writing_citations` /
`writing_readme` / `writing_analysis_log` / `writing_data_availability`
(end matter — data / code / CRediT / funding / COI / ack).

**Visualization (14)** — `figure_guidelines` (style + rules) /
`visualization_workflow` (build / polish) / `figure_critique` /
`multi_panel_composition` / `figure_narrative_arc` /
`color_accessibility_audit` / `interactive_figure_design` /
`interactive_dashboard_design` / `animation_design` /
`distribution_comparison` / `geospatial_visualization` /
`network_visualization` / `showcase_visualization` /
`uncertainty_visualization`.

**Synthesis (20)** — `synthesis_paper` / `synthesis_abstract` /
`synthesis_poster` (with QR + single-headline test) /
`synthesis_dashboard` (Playwright-tested) / `synthesis_grant` /
`synthesis_report` / `synthesis_null_findings` (anti-file-drawer) /
`synthesis_slides` (talks) / `synthesis_lay_summary` (outreach) /
`synthesis_progress_update` (PI / advisor) / `synthesis_handout`
(printable + QR) / `synthesis_from_inputs` (no in-RO analysis) /
`synthesis_cover_letter` / `synthesis_title_workshop` /
`manuscript_outline` / `journal_selection` / `defense_prep` /
`printable` / `humanities_essay_structure` / `reviewer_response`.

**Audit + reproducibility (4)** — `audit/audit_and_validation` (master
quality audit, `tool_audit_quality_full`) /
`audit/pre_submission_checklist` (final GREEN/YELLOW/RED gate) /
`audit/provenance_completeness` (per-output `.prov.json` sidecar
check) / `reproducibility/reproducibility` (env snapshot + Dockerfile
+ seed verification).

**Pack-loaded protocols (+36)** — installed packs add protocols under
`humanities/` (archival, citation, method, output, textual; 12
protocols), `qualitative/` (coding, method, output, validity; 8
protocols), and `theory_math/` (conjecture, formal, method, output,
proof; 16 protocols). Run `sys_packs_installed` to see which packs
are active; `tool_protocols_list(pack='theory_math')` to filter the
catalogue.

---

## 7. MCP tools (144 live)

> All names use underscores. Dot notation + legacy names are
> auto-rewritten. Full catalogue (alphabetical, with aliases) at
> [TOOLS.md](TOOLS.md). At runtime, prefer
> `sys_tool_describe(name)` / `sys_active_tools(protocol_name)` /
> `tool_tools_list(scope='core')` over reading this doc — they
> reflect what's actually installed.

v2.0.0 consolidated ~344 v1.x tool names; v2.3.0 retired the
synthesis auto-generators in favour of AI-direct authoring. The
remaining 144 tools dispatch via `scope` / `dimension` / `operation`
/ `kind` parameters on a small set of entry points. Legacy names
return a friendly `_REMOVED_TOOLS` error naming the new entry point
(see CHANGELOG `[2.3.0]` for the synthesis surface migration).

### Discovery layer — call FIRST every session

| Tool | Purpose |
|---|---|
| `sys_boot` | One envelope returns state + config + history + dep inventory + recommended next protocol + pause classification + active plan. Replaces 4-5 separate calls. |
| `tool_route` | Hybrid (semantic + L1 → L2 → L3) protocol picker. Returns `primary_protocol`, `recommended_action` (literal next-call string), `why_matched` (similarity + matched triggers + tier), `tier`, `alternatives`, `decomposition`, `complexity`, `ask_user`, `shortcut_tool`. **v2.0 enriched envelope.** |
| `tool_plan` | Unified plan dispatcher. `operation='turn'\|'advance'\|'clear'`. Replaces `tool_plan_turn` / `tool_plan_advance` / `tool_plan_clear` (hard-removed in v2.0.0). |
| `sys_active_project` | Returns the project root the server resolved for THIS request + how (env var / cwd walk / fallback). |
| `sys_help` | AI orientation block — pass `topic=` for routing / iteration / overrides / recovery / fields / depth / per-category guidance. |
| `sys_tool_describe` | Full description + schema + `status` + `pack` for one tool. |
| `sys_active_tools` | 13-18-tool scoped shortlist for one protocol (essentials + decomposition tools). |
| `sys_protocol_get` | `format='summary'` is the v2.0 DEFAULT (~300 tokens). Pass `format='step' step_id='...'` (~150-500 tokens) when executing a step; `format='full'` (~1.5-3K tokens) only when you need every step. |
| `sys_dep_inventory` | Which optional extras failed to import. |
| `sys_packs_installed` | List installed protocol packs (name, version, tool count, router entries, errors). |
| `sys_adapters_installed` | List installed infrastructure adapters. |
| `tool_protocols_list` | **v2.0 new.** Flat protocol catalogue with metadata (name, category, pack, intent_class, tier, version). Filterable. |
| `tool_tools_list` | **v2.0 new.** Flat MCP tool catalogue (scope, summary, required fields, deprecation status). Filterable. |

### `sys_*` — workspace, state, files, paths, checkpoints

| Tool | Purpose |
|---|---|
| `sys_state_get` | Full / minimal / markdown state snapshot. (Prefer `sys_boot` at session start.) |
| `sys_workspace_scaffold` / `sys_workspace_tree` | Re-create / inspect the workspace tree. |
| `sys_file_read` / `_write` / `_list` / `_delete` / `_validate_md` | File I/O (write blocked under `inputs/raw_data/` and `inputs/literature/`). |
| `sys_path` | **Unified path-lifecycle dispatcher.** `operation='create'\|'abandon'\|'list'`. Legacy names (`sys_path_create`, `sys_path_abandon`, `sys_path_list`) hard-removed in v2.0.0 — call `sys_path(operation=...)`. |
| `sys_checkpoint_create` / `_rollback` / `_list` | Workspace snapshots (hardlinked, fast). |
| `sys_config` | **Unified config dispatcher.** `operation='get'\|'set'\|'validate'`. Operates on `researcher_config.yaml`. Aliases `sys_config_get` / `sys_config_set` / `sys_config_validate` still callable. |
| `sys_notify` | Append to `workspace/logs/notifications.log`. |
| `sys_session_handoff` | Structured handoff doc + fresh checkpoint. |
| `sys_env` | **Unified env dispatcher.** `operation='snapshot'\|'docker_generate'`. Capture + containerise the env. |

### `tool_*` — research workflow

| Tool | Purpose |
|---|---|
| `tool_session_resume` / `tool_progress_digest` / `tool_lessons` (`operation='dead_end'`) | Session continuity + bookkeeping. |
| `tool_quick_review` / `tool_redteam_review` | Stage critical-appraisal + adversarial-review skeletons. |
| `tool_search` | **Unified search dispatcher.** `source='semantic_scholar'\|'pubmed'\|'crossref'\|'arxiv'\|'web'\|'auto'`. Replaces `tool_search_*` (hard-removed in v2.0.0). |
| `tool_literature_download` / `tool_literature_search_and_save` / `tool_step_literature_list` | Per-step literature management. |
| `tool_python_exec` / `tool_r_exec` / `tool_julia_exec` / `tool_bash_exec` / `tool_notebook_exec` / `tool_rmarkdown_render` | Run scripts / notebooks. Returncode-aware. |
| `tool_package_install` | `pip install` + update requirements. |
| `tool_data` | **Unified data dispatcher.** `operation='sample'\|'profile'\|'convert'`. |
| `tool_audit` | **Unified audit dispatcher.** `scope='step'\|'project'\|'synthesis'` × `dimension='completeness'\|'code_quality'\|'prose'\|'claims'\|'citations'\|'assumptions'\|'figure_full'\|'literature'\|'power'\|'reproducibility'\|...'`. Replaces 23 per-dimension `tool_audit_*` tools. |
| `tool_audit_findings` | **v2.0.0 new.** Query the cross-audit ledger at `workspace/logs/.audit_findings.jsonl`. `operation='query'` filters by severity / dimension / step / since; `operation='diff'` compares two snapshots. |
| `tool_audit_quality_full` | Master audit: runs every gate in one call; returns structured per-component verdicts. |
| `tool_synthesize_plan` | Inspect workspace + report what's ready to draft (per-section source paths + gaps). Read-only. |
| `tool_synthesis_scaffold` | Write a tiny `<=80`-line skeleton `synthesis/<paper\|slides\|poster\|essay>.typ` or `dashboard.html` for the AI to author into. Idempotent. |
| `tool_synthesis_check` | Per-IMRAD-section content depth audit (paper / essay), slide-count + speaker-notes + path-leak audit (slides), section + headline + QR audit (poster), engineering invariants (dashboard: offline, alt-text, semantic, no placeholders). Multi-mode (`all` / `substantiveness` / `structure` / `accessibility` / `cliches`). |
| `tool_typst_compile` | Generic Typst compiler. Takes any AI-authored `.typ` source + Hayagriva biblio, renders PDF. Resolves bundled venue templates from `_typst_templates/`. |
| `tool_latex_compile` | LaTeX compiler for journals that require `.tex` submission. AI authors `synthesis/paper.tex`; tool runs pdflatex × bibtex × pdflatex × pdflatex. |
| `tool_figure_palette` | Colour-blind-safe palette (Okabe-Ito qualitative / viridis sequential / PuOr diverging / accent). Read-only. |
| `tool_research_method` / `tool_research_tool` / `tool_external_tool_instructions` / `tool_plan_step` / `tool_plan_step_grounded` | Reasoning + grounding helpers. |
| `tool_plan_next_step` / `tool_branch_recommendation` / `tool_alternative_path_propose` | Iterative planning. |
| `tool_ground` / `tool_verify` | Bind decisions to PROV-O sources; verify claims (Chain-of-Verification). |
| `tool_preregister` | **Unified preregister dispatcher.** `operation='freeze'\|'diff'`. Lock the SAP before data; diff at synthesis. |
| `tool_sensitivity` | **Unified sensitivity dispatcher.** `operation='define'\|'run'`. Specification-curve / multiverse analyses. |
| `tool_reviewer` | **Reviewer-response dispatcher.** `operation='response'\|'rebuttal'\|'compile'`. Real external-review response scaffolding. Pre-submission self-review is done directly by the AI walking the paper through the persona YAMLs in `src/research_os/assets/reviewer_personas/`. |
| `tool_step` | **Unified step lifecycle dispatcher.** `operation='iterate'\|'iterations_list'\|'revision_options'\|'env_lock'`. |
| `tool_step_pipeline` | **Unified step pipeline dispatcher.** `operation='define'\|'run'\|'status'\|'diagram'`. Per-step sub-task DAG with content-hash caching. |
| `tool_step_complete` | One-call gate for "this step is done." Bundles per-step audits + `tool_path_finalize`. |
| `tool_workflow_dag` | Project-wide step DAG (Mermaid + optional PNG). Auto-refreshed on path create/abandon. |
| `tool_slurm_submit` / `_status` / `_fetch` / `_list` / `_job_status` / `_estimate_cost` | HPC submission (pack: `slurm`). |
| `tool_task` | **Unified background-task dispatcher.** `operation='run'\|'status'\|'list'\|'kill'`. Real `subprocess.Popen` for shared servers. |
| `tool_scratch` | **Unified scratch dispatcher.** `operation='write'\|'run'\|'list'\|'clear'`. Workspace sandbox (gitignored). |
| `tool_workspace_repair` | Heal a broken workspace; never deletes. |
| `tool_intake_autofill` / `tool_context_intake` | Auto-fill + mid-flow context injection. |
| `tool_lessons` | **Unified lessons dispatcher.** `operation='record'\|'consult'\|'failure_record'\|'failure_check'\|'failure_list'\|'dead_end'\|'mistake_replay'`. |
| `tool_reliability` | **Unified reliability dispatcher.** `operation='log_event'\|'report'`. |
| `tool_thought` | **Unified ReAct trace dispatcher.** `operation='log'\|'trace'`. |
| `tool_null_findings_report` | Anti-file-drawer report assembly. |
| `tool_cache_clear` | Wipe search cache per provider / older-than-N-days. |
| `tool_deprecations_summary` | Aggregate `.os_state/deprecations.log` — which deprecated aliases your project still hits. |

### `mem_*` — append-only logs, decisions, hypotheses

| Tool | Purpose |
|---|---|
| `mem_log` | **Unified memory dispatcher.** `kind='methods'\|'decision'\|'hypothesis'\|'analysis'`. Replaces `mem_methods_append` / `mem_decision_log` / `mem_hypothesis_update` / `mem_analysis_log` (all hard-removed in v2.0.0). The pre-v1.6.1 nickname `tool_log_decision` still resolves to `mem_log(kind='decision')`. |
| `mem_citations_generate` | Refresh `workspace/citations.md` from project + per-step literature sidecars. |
| `mem_intake_regenerate` | Regenerate `inputs/intake.md` with fresh hashes. |
| `mem_hypothesis_add` / `mem_hypothesis_list` | Multi-hypothesis ledger (register + list). |

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
                                  # — drives tool_plan(operation='turn') batch size

writing_preferences:
  citation_style: "apa"           # apa | vancouver | acm | ieee | nature
                                  # Humanities (MLA / Chicago) + math
                                  # (amsplain / siam) styles are on the
                                  # roadmap; for now use the closest
                                  # match and edit the bibliography
                                  # style in the generated .tex / .typ
                                  # if your venue requires a specific
                                  # one.
  language: "en-US"
  # Typst venue template imported by AI-authored synthesis/paper.typ.
  #   nature | science | nejm | cell | ieee_conf | neurips | acl
  #   plos  | generic_two_column | generic_thesis
  # For humanities-essay or Chicago-thesis layouts, use
  # generic_thesis and adjust the front matter; dedicated
  # humanities_essay and chicago_thesis templates are planned.
  venue_template: "generic_two_column"
  # PDF engine for the synthesis pipeline. "typst" recommended (fast,
  # single-binary install). Use "latex" when a journal requires .tex.
  pdf_compile_engine: "typst"     # typst | latex | both

# Compute environment + exec-safety knobs. All optional; defaults shown.
runtime:
  shared_server: false                  # true on HPC / shared boxes
                                        # — flips long_running default
  long_running_threshold_seconds: 60    # tool_task(operation='run') vs inline cutoff
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
parallel numbered path via `sys_path(operation='create')`. Use
`tool_branch_recommendation` if uncertain whether to branch or
extend. For methodology-level branches (e.g. "the literature also
supports X for this data shape"), `tool_alternative_path_propose` is
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

`tool_task(operation='run')` for real background subprocesses
(`subprocess.Popen`, zombie-aware); poll with
`tool_task(operation='status', task_id=...)`. Especially important on
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

`tool_citations_verify` pulls every citation from Crossref / Semantic
Scholar / PubMed / arXiv and drops anything unverified. The
`tool_synthesis_check` audit surfaces unresolved citation keys before
compile.

### Hallucinated numbers

`tool_audit_claims` extracts every numeric claim from
`synthesis/paper.typ` (or `.md`) and verifies each appears verbatim
(or within 1% tolerance) in some workspace CSV / JSON / MD / TXT.
Surfaces as blockers on `tool_synthesis_check` until cleared.

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

v2.0.0 dissolved the 7,499-line `server.py` monolith into a modular
`src/research_os/server/` package (32 files; largest 579 lines).
Top-level `from research_os.server import TOOL_DEFINITIONS,
_HANDLERS, _ALIASES, ...` continues to work unchanged.

```
src/research_os/
├── server/                      # MCP server package (replaced server.py in v2.0.0)
│   ├── __init__.py              # re-exports (TOOL_DEFINITIONS, _HANDLERS, _ALIASES, ...)
│   ├── entry.py                 # MCP entry + instructions field
│   ├── dispatch.py              # central dispatcher (alias + param injection)
│   ├── registry.py              # tool registry
│   ├── aliases.py               # _ALIASES + _DEPRECATED_ALIASES + _REMOVED_TOOLS
│   ├── envelopes.py             # _ok / _err helpers
│   ├── rate_limiter.py
│   ├── pack_loader.py           # pack tool registration
│   ├── optional_deps.py
│   ├── _handlers_runtime.py     # runtime resolution helpers
│   ├── _helpers.py
│   ├── tool_definitions/        # tool definitions
│   │   ├── audit.py / grounding.py / meta.py / methodology.py
│   │   ├── research.py / synthesis.py
│   └── handlers/                # dispatch handlers
│       ├── audit_core.py / audit_gates.py / grounding.py
│       ├── meta_routing.py / methodology.py
│       ├── research_exec.py / research_search.py
│       └── synthesis_visual.py / synthesis_writing.py
├── cli.py                       # `init` + `start` + `doctor` (v2.0.0)
├── cli_doctor.py                # `research-os doctor` health checks
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
│   └── runner.py                # tool_adapter_extract / _adapters_run_all
├── assets/js/                   # bundled JS (mermaid, plotly, vega, vis-network)
├── data/typst/                  # 11 Typst venue templates (Nature, Science, …)
├── inputs/                      # paper + paste intake helpers
├── plugins/                     # domain-pack loader + pack_api surface
├── protocols/                   # 117 YAML protocols + _router_index.yaml + _tiers.py
│   ├── audit/        (3)        # audit_and_validation, pre_submission_checklist, provenance_completeness
│   ├── domain/       (2)
│   ├── guidance/    (19)        # autopilot, code_review, mid_pipeline_entry, scope_clarification, …
│   ├── literature/   (5)
│   ├── methodology/ (43)        # the biggest category
│   ├── reproducibility/ (1)
│   ├── synthesis/   (20)
│   ├── visualization/ (14)
│   └── writing/     (10)
├── state/                       # ResearchLedger (state.json schema)
├── testing/                     # stress-runner harness (not the unit tests)
├── utils/                       # asset manager, common helpers
└── tools/
    └── actions/
        ├── protocol.py          # YAML loader + protocol_completion injection
        ├── router.py            # sys_boot, tool_route (recommended_action / why_matched / tier)
        ├── semantic.py          # sys_semantic_tool_search, tool_semantic_route
        ├── audit/               # audit, md_audit, code_quality, content_depth,
        │                        #   coherence, prose_quality, claim_grounding,
        │                        #   preregistration, redteam, dashboard_content,
        │                        #   figure_interactivity, step_literature,
        │                        #   null_findings, findings_ledger
        ├── data/                # data (sample/profile/convert), intake, context_intake
        ├── exec/                # scripts, notebook, tasks, environment,
        │                        #   sensitivity, step_pipeline, cluster
        ├── memory/              # mem_log + hypotheses + append-only helpers
        ├── research/            # research_method/tool/plan, planning, grounding,
        │                        #   lessons, plan_next_step, thought
        ├── search/              # tool_search (unified provider dispatcher),
        │                        #   literature download / cache
        ├── state/               # sys_config + sys_path + sys_env, checkpoint,
        │                        #   scratch, repair, reliability, certifications,
        │                        #   freshness, iteration, mistake_replay,
        │                        #   provenance, paywall_memory, quick_mode,
        │                        #   revision, rigor_signals, interaction,
        │                        #   extractors
        ├── synthesis/           # synthesize, latex, citations, dashboard,
        │                        #   dashboard_app, dashboard_story, typst,
        │                        #   preview, discussion_from_verdicts, drafter_loops
        └── viz/                 # figures, dashboard_tests

src/research_os_humanities/      # bundled humanities pack (12 protocols + 4 tools)
src/research_os_qualitative/     # bundled qualitative pack (8 protocols + 3 tools)
src/research_os_theory_math/     # bundled theory_math pack (16 protocols + 3 tools)

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

## Appendix A. Common figure recipes (which protocol stack builds each)

The visualization category has 14 protocols and Research-OS does not
ship a parametric chart-builder — the AI writes the plotting script
per the `visualization/figure_guidelines` style guide. The table below
maps the six most common publication-grade figures to the protocol
stack that produces each, so you (or the AI) know which one-liner gets
you there fastest.

| Figure recipe | When you'd reach for it | Protocol stack the AI walks |
|---|---|---|
| **Volcano plot** (-log10 p-value vs effect size, labelled tails) | Differential expression / GWAS / any "many tests, name the hits" output | `visualization/figure_guidelines` → `visualization/visualization_workflow` → `visualization/interactive_figure_design` (>200 marks gets an HTML companion via `tool_audit(scope='step', dimension='figure_interactivity')`) |
| **UMAP / t-SNE** (per-cell or per-sample embedding, colored by cluster / condition) | scRNA-seq / single-cell ATAC / any high-dim sample-level visualisation | `visualization/figure_guidelines` → `visualization/visualization_workflow` → `visualization/interactive_figure_design` (>200 cells) → `visualization/color_accessibility_audit` (cluster palettes are the most common a11y miss) |
| **Heatmap with row/column clustering** (genes × samples; correlations; ARI confusion) | Co-expression / correlation matrix / clustering quality | `visualization/figure_guidelines` → `visualization/visualization_workflow` → `visualization/multi_panel_composition` (paired with the dendrogram + annotation bars) → `tool_audit(scope='step', dimension='figure_interactivity')` (auto-companion when matrix > 50×50) |
| **Forest plot** (effect size + CI per study / subgroup) | Meta-analysis / multi-cohort comparison / Cox PH subgroup interactions | `methodology/meta_analysis` (or `methodology/cox_ph_diagnostics`) → `visualization/figure_guidelines` → `visualization/uncertainty_visualization` (the CI is the figure) |
| **Survival / Kaplan-Meier curve** (with at-risk table, log-rank p) | Time-to-event analysis; clinical trials; cohort studies | `methodology/clinical_trials` / `methodology/cox_ph_diagnostics` → `visualization/figure_guidelines` → `visualization/uncertainty_visualization` (CI ribbons, at-risk row) |
| **Log-log benchmark scaling plot** (runtime vs n, fitted exponent + CI) | Systems / algorithms benchmark; engineering pack | `methodology/method_comparison` (including the engineering / systems-benchmark addendum) → `visualization/figure_guidelines` → `visualization/uncertainty_visualization` (the CI on the exponent is the headline) |

For every recipe, the AI also pairs `tool_audit(scope='step',
dimension='figure_full')` and auto-synthesises a `<figure>.caption.md`
+ `<figure>.summary.md` sidecar via
`tool_figure(operation='caption_synthesise')`. Skipping the sidecar
blocks at the per-step completeness audit, so don't.

Two general principles the stack enforces:

- **Pick the chart family from `figure_guidelines` before plotting**,
  not after. Bar-with-error-bars is rarely the right comparison; the
  guidelines protocol routes you to `distribution_comparison`,
  `uncertainty_visualization`, or `multi_panel_composition` as
  appropriate.
- **Run `color_accessibility_audit` on every figure that uses
  colour to encode information.** WCAG contrast + colour-blindness
  simulation + grayscale-survivability is one tool call; reviewers
  catch un-redundant colour encoding more than any other figure flaw.

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| Anything wrong with the install | `research-os doctor` *(v2.0.0)* — 20+ install + workspace health checks; exit 0/1/2; `--verbose` for fix hints. |
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
| `tool_audit(scope='step', dimension='reproducibility')` slow | It re-runs every script. Skip in autopilot unless explicitly asked. |
| `Protocol not found` | `sys_protocol_list` (or `tool_protocols_list` for filterable catalogue). |
| "Unknown tool" error | The dispatcher accepts `sys_state_get` / `sys.state.get` / legacy v1.x names via `_ALIASES`. If a name is in `_REMOVED_TOOLS` (Phase 14a), the error names the canonical v2 entry point. If still failing, "Call `tool_tools_list` and tell me what's available." |
| AI calls deprecated tool names | Harmless — `_ALIASES` dispatches old names through the v2.0.x runway. `tool_deprecations_summary` aggregates `.os_state/deprecations.log` for a sweep before v2.1.0. |
| `BLOCK: unresolved audit findings` from `tool_synthesize` | Run `tool_audit_findings(operation='query', severity='block')` to list active blockers; fix them or pass `override_unresolved_blocks=true` + `override_rationale='...'`. |

For more: [FAQ.md](FAQ.md).

---

## See also

* [START.md](START.md) — install + first-hour walkthrough + cheatsheet.
* [USE_CASES.md](USE_CASES.md) — role × goal × output map.
* [SETUP.md](SETUP.md) — install + per-IDE wiring + troubleshooting.
* [FAQ.md](FAQ.md) — common questions.
* [PROTOCOLS.md](PROTOCOLS.md) — catalogue of all 117 core protocols.
* [TOOLS.md](TOOLS.md) — catalogue of all 144 live MCP tools.
* [AI_GUIDE.md](AI_GUIDE.md) — operating manual for the AI driving Research OS.
* `CHANGELOG.md [2.0.0]` — upgrade recipe + old → new tool table.
* `CHANGELOG.md [2.0.0]` — celebratory v2.0.0 release notes.
* `CHANGELOG.md [2.0.0]` — Phase 15b validation results.
* [CONTRACT.md](CONTRACT.md) — stable surface for integrators.
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — scaffold-not-script
  principle (for protocol authors / contributors).
