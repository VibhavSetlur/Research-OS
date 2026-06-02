# Changelog

All notable changes to Research OS are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) ·
Versioning: [SemVer](https://semver.org).

---

## [1.1.1] — Repo + docs polish (2026-06-02)

A maintenance release focused on **GitHub repo infrastructure** and a
**user-first README rewrite**. No protocol or tool changes; same 88
protocols, same 143 MCP tools, same 418-test pass.

### Added — repo infrastructure

* **`SECURITY.md`** — vulnerability reporting policy, supported-version
  table, scope clarification (in-scope vs out-of-scope).
* **`CODE_OF_CONDUCT.md`** — Contributor Covenant v2.1, with private
  reporting address + scaled-response policy.
* **`.github/PULL_REQUEST_TEMPLATE.md`** — type checklist, protocol /
  tool sub-checklists, test plan, breaking-change section.
* **`.github/dependabot.yml`** — weekly bumps for GitHub Actions + Python
  deps, grouped minor/patch updates, opinionated about `mcp` majors.
* **`.github/workflows/codeql.yml`** — CodeQL static security analysis on
  push, PR, and weekly schedule.
* **`.github/workflows/release.yml`** — auto-creates a GitHub Release on
  every `v*` tag with the matching CHANGELOG section as the body. Runs
  in parallel with `publish.yml` (PyPI).
* **`docs/RELEASING.md`** — maintainer release runbook (versioning,
  branch model, patch / minor / major / hotfix flows, pre- and
  post-release checklists, yank procedure).

### Improved — docs

* **README rewrite — user-first.** Reframed around what the project IS,
  what it DOES, what you SEE, and HOW to use it — with navigation links
  to the deep docs instead of inlining everything. Tool / protocol
  counts and architecture details are now one click away in
  `RESEARCHER_GUIDE.md` and `PROTOCOLS.md`. New top-of-README quick-link
  bar (Quick start · Use cases · Full guide · FAQ).
* **`CONTRIBUTING.md`** — adds the `main` / `dev` / `feat-*` / `fix-*` /
  `hotfix-*` branch model + PR flow, points maintainers at the new
  `docs/RELEASING.md`. Counts synced (143 tools, 88 protocols, 418 tests).
* **`README.md` badge bar** — PyPI version + Python versions + license +
  tests-status badges via shields.io (auto-updating, no more stale
  hardcoded version badge).

### Improved — CI

* **`test.yml` runs on `dev` branch too.** Previously only `main` push +
  PR to `main` triggered CI; now `dev` does too, so PRs into `dev` get
  the same green-or-red signal before they reach `main`.

### Bumped

* `research-os` package: 1.1.0 → 1.1.1
* `CITATION.cff` version

### Test + quality status

* 418 tests pass (unchanged surface).
* Preflight 13/13.
* Ruff clean.
* 88 protocols, 143 MCP tools (no surface changes).

---

## [1.1.0] — Guidance refinement (2026-06-02)

A non-breaking refinement focused on **how the AI navigates Research-OS
when the researcher's intent isn't a clean match** — open-ended asks,
cross-disciplinary projects, cold starts after a long handoff, ambiguity
at any router level. No tool surface changes; the MCP server still ships
the same 143 tools.

418 tests green (up from 417); preflight 13/13; one new protocol
brings the total to 88.

### Added

* **`guidance/scope_clarification` — 88th protocol.** Converts vague,
  open-ended, or cross-disciplinary asks into a workable scope BEFORE
  the AI picks a downstream protocol. Classifies ambiguity into five
  buckets (unclear intent / unformed intent / cross-disciplinary /
  wrong entrypoint / too broad), asks ONE narrowing question, then
  hands control back to `tool_route` with the narrowed prompt. Reaches
  `methodology/methodological_consultation` for "teach me" asks,
  `methodology/exploratory_data_analysis` for "find a hypothesis" asks,
  and `methodology/deep_domain_research` once per subfield for genuinely
  multi-field projects.
  ([`scope_clarification.yaml`](src/research_os/protocols/guidance/scope_clarification.yaml))

* **`discover/clarify` sub-intent.** Indexed in the router hierarchy so
  triggers like "where should I start", "i have data and ideas",
  "narrow this down for me", "this spans two fields" resolve cleanly.

* **`sys_help` topics — eight new categories.** Topics that aren't
  protocol categories but the AI needs on demand:
  - `routing` — the L1 → L2 → L3 decision tree + ambiguity rules
  - `iteration` — bug-fix versioning vs. deliberate `tool_step_iterate`
  - `overrides` — when / how to bypass a quality gate safely
  - `recovery` — what to do when stuck (broken workspace, lost project,
    dead-end mid-step, ctx exhaustion)
  - `fields` — how Research-OS stays field-agnostic; subfield pipelines
  - `depth` — depth gradient (napkin → publication) + expertise levels
  - `literature` — literature-search protocols + search-tool catalogue
  - `writing` — per-section writing protocols + attached audits
  ([`server.py`](src/research_os/server.py))

* **Router fallback now teaches.** When no trigger matches
  (`resolved_level=0`), the fallback returns the L1 menu WITH per-class
  trigger hints (`"start session", "pick up where we left off"` for the
  session class; `"draft the paper", "make a poster"` for synthesize;
  etc.) and tells the AI explicitly to prefer `sys_help(topic='categories')`
  or `sys_protocol_next` over guessing. Cuts the AI's clarification round
  from two questions to one.
  ([`router.py`](src/research_os/tools/actions/router.py))

* **Stronger routing advice.** `_route_advice_hier` now spells out:
  - For complex/L3 matches → tool_plan_turn + chat_split_recommended.
  - For shortcut-only → "summarise + wait for next ask" closure.
  - For primary protocols → call `sys_active_tools(protocol_name)` to
    scope the working tool set.
  - For ambiguous matches → "ask verbatim; do NOT load a YAML at
    format='full' to disambiguate".

### Improved

* **`protocol_completion` injected step is now actionable.** Tells the AI
  to log `status='failed'` (not 'completed') when a quality gate blocks,
  to confirm the override-log captured any bypass rationale this turn,
  to skip the trailing summary on shortcut-tool calls (the result IS the
  answer), and to prefer `tool_route` on the researcher's next message
  over the pipeline pointer when they redirect.
  ([`protocol.py`](src/research_os/tools/actions/protocol.py))

* **`sys_help` default + anti-patterns.** Added "when_uncertain"
  guidance to the lean default; expanded `anti_patterns` from 5 to 12
  to cover the gate-override silent-bypass case, the stale `_v<n>` reuse
  case, the redundant constructive-disagreement push-back case, and the
  re-route-after-the-researcher-already-picked case. `topic="docs"`
  now lists every doc with a one-line hook.
  ([`server.py`](src/research_os/server.py))

* **`session_boot` documents the no-match fallback.** When `tool_route`
  returns `resolved_level=0` AND the researcher's ask is open-ended /
  cross-disciplinary, the protocol now points at
  `guidance/scope_clarification` explicitly instead of leaving the AI to
  improvise.
  ([`session_boot.yaml`](src/research_os/protocols/guidance/session_boot.yaml))

* **`iterative_planning` enforces grounding + honours
  `ambiguity_posture`.** The option-presentation step now spells out
  that rationales must be SOURCED from grounded evidence (literature /
  audit warnings / decision log) — "AI intuition" rationales collapse
  under `constructive_disagreement`. Adds an explicit `AMBIGUITY POSTURE
  GATE` so `take_best_default` users get the runner-up surfaced too.
  ([`iterative_planning.yaml`](src/research_os/protocols/guidance/iterative_planning.yaml))

* **AGENTS.md template gains 4 quick-lookup rows.** Vague /
  cross-disciplinary asks → `scope_clarification`; tool shortlist →
  `sys_active_tools`; cold start → `sys_help(topic='routing')`;
  override how-to → `sys_help(topic='overrides')`. The Lost? hint now
  enumerates every `sys_help` topic instead of just listing categories.
  ([`AGENTS.md`](templates/AGENTS.md))

* **`AI_GUIDE.md` documents new ambiguity path.** New section "When the
  researcher's intent is unclear or cross-disciplinary" enumerates the
  five clarification buckets and explains the
  `tool_route → scope_clarification → tool_route` re-entry pattern.

### Fixed

* **`methodology/tool_discovery` next_protocol pointed at the
  pre-1.0 `methodology/research_methods`**, which was renamed to
  `methodology/methodology_selection` during 1.0.0 hardening. The
  pipeline pointer was silently dangling — preflight didn't catch it
  because the freshness check only validates `_router_index.yaml`
  references, not protocol-internal `next_protocol` fields.
  ([`tool_discovery.yaml`](src/research_os/protocols/methodology/tool_discovery.yaml))

* **`sys_active_tools` description had a stale tool count.** Said
  "all 94 tools per turn"; actually 143.
  ([`server.py`](src/research_os/server.py))

* **Tool count drift across docs.** README.md was right at 143; multiple
  reference docs lagged at 140. Synced
  `docs/README.md`, `docs/START.md`, `docs/TOOLS.md`,
  `docs/RESEARCHER_GUIDE.md` (2 places) to 143.

* **Protocol count drift across docs.** Updated 87 → 88 in
  `README.md`, `docs/README.md`, `docs/RESEARCHER_GUIDE.md`,
  `docs/AI_GUIDE.md`, `docs/FAQ.md`, `docs/PROTOCOLS.md` (table + total).

* **Version not auto-derived in wizard / logo.** Both hardcoded "1.0.0";
  now read from `research_os.__version__`. One source of truth across
  the package.

### Bumped

* `research-os` package: 1.0.0 → 1.1.0
  ([`pyproject.toml`](pyproject.toml), [`__init__.py`](src/research_os/__init__.py))
* All 88 protocol YAMLs: version 1.0.0 → 1.1.0 (no schema changes —
  scaffold doctrine + step structure preserved).
* Router index version: 2 → 3.
* `CITATION.cff` version + date.

### Test + quality status

* **418 tests pass** (up from 417 — the new
  `guidance/scope_clarification` is auto-covered by
  `tests/integration/test_all_protocols_load.py` + protocol-loader
  unit tests).
* Preflight 13/13.
* 88 protocols indexed; all router refs + tool refs resolve.
* All protocols at version 1.1.0.
* 143 MCP tools (unchanged surface).

---

## [1.0.0] — Hardening (post-review)

15-finding code-review pass fixed in-place against v1.0.0; no version
bump (no API changes). 417 tests green (up from 395), preflight 13/13.

* **Mega-script blocker no longer fires on stray figures.** The
  blocker now counts only artefacts that bear the step's number
  prefix toward `categories_hit`. A legacy step that produced one
  CSV no longer blocks `tool_synthesize` because someone dropped an
  unrelated `panel.png` into `outputs/figures/`.
  ([`audit.py`](src/research_os/tools/actions/audit/audit.py))
* **Version-coherence audit no longer cries wolf or sleeps through drift.**
  The stem-prefix derivation used a non-anchored `startswith` that
  both (a) conflated unrelated sibling scripts like `01_fit_v2.py` /
  `01_fit_extended_v3.py` (false drift) AND (b) missed
  unsuffixed-to-versioned bumps like `02_clean.py` → `02_clean_v2.py`
  (silent miss). Now exact-stem matching catches the real case in
  both directions.
  ([`iteration.py`](src/research_os/tools/actions/state/iteration.py))
* **`tool_step_iterate` is safe under concurrent IDE sessions.**
  `fcntl.flock` serialises the read-ledger → pick `n` → create
  `.versions/v<n>/` → write-ledger critical section. The archive
  dir is verified unused before mkdir so a stale `vN` can't be
  clobbered. `_bump_script_suffix` scans the folder for the
  highest existing `_v<n>` and returns `_v<n+1>`, so the rename
  advice never overwrites an existing file. Atomic ledger writes
  via temp + replace.
  ([`iteration.py`](src/research_os/tools/actions/state/iteration.py))
* **`tool_audit_version_coherence` surfaces typos and warnings.**
  An unknown `step_id` now raises `FileNotFoundError` instead of
  returning empty success. A ledger entry with empty `snapshot_dir`
  is flagged as malformed instead of silently resolving to the step
  dir. Top-level `status` escalates to `warning` when any per-step
  warning fires (stale captions etc.), not only on drift.
* **Override audit trail is honest.** `log_override` now fires only
  when the bypassed gate would have blocked — phantom entries from
  defensive `override=true` calls (or section-only synthesis where
  the full gate never ran) no longer pollute
  `workspace/logs/override_log.md`. The plan-persisted
  `override_completeness_gate` flag inside `active_plan.json` gets
  its own log entry on the deliverable step.
  ([`server.py`](src/research_os/server.py),
  [`router.py`](src/research_os/tools/actions/router.py))
* **Dashboard override actually suppresses the warning panel.**
  `override_completeness_gate=true` on `tool_dashboard_create` now
  plumbs through to `render_dashboard` via a `suppress_audit_panel`
  flag so the schema's promise (drop the warning section in the
  rendered HTML) is honoured.
  ([`dashboard.py`](src/research_os/tools/actions/synthesis/dashboard.py))
* **Cold init keeps the short intake pointer.** `scaffold_minimal_workspace`
  no longer unconditionally overwrites the new short
  `inputs/intake.md` with the legacy long-form table — it
  regenerates the full intake only when the researcher dropped
  files or passed config overrides.
  ([`project_ops.py`](src/research_os/project_ops.py))
* **`sys_file_list` on lazy dirs returns empty, not error.** Cold
  protocols that probe `inputs/raw_data`, `inputs/literature`,
  `inputs/context` no longer break on a fresh project — the handler
  returns `{files: [], empty: true, lazy_dir: true}` with a hint.
  ([`server.py`](src/research_os/server.py))
* **`interaction.quality_gate_policy` and `interaction.ambiguity_posture`
  are now live config.** `tool_synthesize` and `tool_dashboard_create`
  read the policy: `warn_only` turns blockers into warnings;
  `enforce` rejects overrides without a rationale; `allow_override`
  is the existing behaviour. New `get_interaction_policy` helper
  exposed via `state` package.
  ([`state/config.py`](src/research_os/tools/actions/state/config.py))
* **`audit/pre_submission_checklist` reads the override log.** A new
  `override_audit_review` step surfaces every entry in
  `workspace/logs/override_log.md` and folds unresolved bypasses
  into the GREEN / YELLOW / RED verdict. The audit trail is no
  longer write-only.
* **`ensure_lazy_dir` is real now.** Synthesis writers route through
  it instead of ad-hoc `mkdir`; the helper rejects paths not in
  `LAZY_DIRS` so the lazy surface can't silently grow.
  ([`project_ops.py`](src/research_os/project_ops.py))
* **sys.* output token-bloat trim.** `sys_help` default returns a
  lean orientation block + topic index (deep dives behind
  `topic=categories|anti_patterns|docs`); `sys_active_project`
  emits the orientation advice only when the project isn't
  scaffolded; `sys_state_get` omits empty `paths_summary` /
  `active_hypotheses` / `resumable_from`; `sys_protocol_get`
  format=full drops the redundant "prefer summary" reminder.
* **README rewrite.** Reframed as user/functionality-first — what it
  does, what you say, what you get, the layout you touch. Setup +
  per-IDE wiring + tool catalogues offloaded to `docs/`.

---

## [1.0.0] — Initial public release

The first public release of Research OS — an MCP-native operating system
for reproducible, grounded, citation-verified research. Built for any
researcher who can talk in plain English to an AI IDE.

### Architecture

* **MCP server is GLOBAL.** Install once with `pip install research-os`;
  the SAME `research-os start` binary serves every project. Each IDE
  request resolves the active project per-call via:
    1. `RESEARCH_OS_WORKSPACE` env var (set by the IDE MCP config to
       `${workspaceFolder}` so each IDE project gets its own context),
    2. the current working directory walked up to `.os_state/`,
    3. the current working directory as a fallback.
  No more per-workspace server pinning. `research-os init` is the only
  per-project command.
* **140 MCP tools** across three namespaces:
  - `sys_*` — system, workspace, state, files, paths, checkpoints
  - `tool_*` — research work: search, exec, audit, synthesis, intake, plan
  - `mem_*` — append-only memory: methods, citations, decisions, hypotheses
* **87 YAML protocols** the AI loads contextually, organised in nine
  categories: guidance, discover, domain, methodology, literature,
  writing, visualization, synthesis, audit, reproducibility.
* **Hierarchical L1 → L2 → L3 router** (`tool_route`) — picks the right
  protocol from a plain-English prompt in ~250 tokens. Persists a plan
  for complex / multi-step prompts. Returns an `ask_user` sentence
  instead of guessing when ambiguous.
* **AI orientation tools** — `sys_help` returns the AI's operating
  manual (routing pattern, namespaces, protocol categories,
  anti-patterns); `sys_active_project` reports which project the
  global server resolved for THIS request.

### Protocol surface (87 protocols)

**Guidance + session + flow control (15)**
* `session_boot`, `session_resume`, `chat_handoff`, `autopilot`,
  `collaboration_handoff`, `casual_exploration`, `quick_paper_review`,
  `code_review`, `peer_review_response`, `project_startup`,
  `analysis_plan`, `iterative_planning`, `dead_end_routing`,
  `hypothesis_tracking`, `glossary_update`
* `mid_pipeline_entry` — enter Research OS with work already done outside
* `constructive_disagreement` — structured AI pushback when grounded
  evidence disagrees with the researcher's direction

**Domain + methodology (24)**
* `domain_analysis`, `research_design`
* `methodology_selection`, `deep_domain_research`, `preregistration`,
  `tool_discovery`
* Per-method: `causal_inference_deep`, `machine_learning`,
  `clinical_trials`, `meta_analysis`, `survey_psychometrics`,
  `qualitative_research`, `simulation_studies`, `replication_study`,
  `ablation_study`, `pilot_study`, `mixed_methods`, `bayesian_analysis`,
  `timeseries_analysis`
* New design protocols: `exploratory_data_analysis` (real EDA +
  hypothesis generation), `method_comparison` (N-method head-to-head),
  `data_quality_audit`, `power_analysis`, `evaluation_design`
  (split / CV / metrics / paired test), `hyperparameter_search_design`
  (sweep design), `data_ethics_review` (IRB / privacy / consent /
  fairness / dual-use), `reproduction_attempt` (reproduce a published
  paper), `methodological_consultation` (teach / explain / compare
  methods without project commit)

**Literature (4)**
* `literature_search` — multi-database search, dedup, PRISMA
  accounting, forward-citation walk, predatory-venue flagging
* `systematic_review` — full PRISMA workflow
* `evidence_synthesis` — GRADE-style grading + contradiction detection
* `comparative_paper_review` — compare-and-contrast 2-N papers

**Writing (9)**
* `writing_core` — universal rules (voice, claim grounding, banned
  phrases, vague-quantifier audit, anti-bullshit detection, numbered
  claim grounding pattern)
* `writing_methods`, `writing_results`, `writing_discussion`,
  `writing_limitations`, `writing_conclusions`, `writing_citations`,
  `writing_readme`, `writing_analysis_log`, `writing_data_availability`
  (end matter: data / code availability, CRediT, funding, COI, ack)

**Visualization (6)**
* `figure_guidelines` — style + chart-chooser + per-step focal-figure
  rule, server-enforced
* `visualization_workflow` — build / polish figures without committing
  to the full analysis_plan loop
* `figure_critique` — reviewer-style critique of a single figure
* `multi_panel_composition` — compose Figure 2 = panels A / B / C / D
* `figure_narrative_arc` — order figures across paper / talk / poster
* `color_accessibility_audit` — color-blindness simulation (3 types) +
  WCAG contrast + grayscale-survivability + redundant-encoding audit

**Synthesis (14)**
* `synthesis_paper` — IMRAD paper, venue-tailored (journal / conference
  / preprint / dissertation / report)
* `synthesis_abstract` — structured / unstructured / preprint / poster /
  grant abstract
* `synthesis_poster` — billboard + classic LaTeX poster, audience
  profiles, QR code mandatory, single-headline test
* `synthesis_dashboard` — offline HTML dashboard, Playwright-tested,
  4 audience profiles, evidence traceability matrix
* `synthesis_grant` — grant narrative (R01 / NSF / Wellcome / ERC /
  DOE / industry)
* `synthesis_report` — internal / client / technical / policy report
* `synthesis_null_findings` — publishable companion for refuted /
  underpowered / abandoned findings (fights the file-drawer problem)
* `synthesis_slides` — talks (lab_meeting / conference_short /
  conference_long / defense / invited_seminar / teaching) with mandatory
  speaker notes + Q&A backup deck
* `synthesis_lay_summary` — non-expert summary (public / press / patient
  / funder / blog / social) with reading-grade cap + anchor comparisons
* `synthesis_progress_update` — short PI / advisor / lab / stand-up update
* `synthesis_handout` — single-page printable leave-behind + QR
* `synthesis_from_inputs` — synthesis when prior analyses ran OUTSIDE
  Research OS (shadow workspace step + provenance ceiling)
* `synthesis_cover_letter` — journal cover letter (fit + significance +
  reviewers + disclosures)
* `synthesis_title_workshop` — generate / iterate / pick a title
  (≥6 alternatives across archetypes, substring test, shortlist)

**Audit + reproducibility (3)**
* `audit_and_validation` — master quality audit (citations / power /
  assumptions / figures / code / per-step completeness)
* `pre_submission_checklist` — final ready-to-submit gate
  (GREEN / YELLOW / RED + punch list)
* `reproducibility` — env snapshot + seed verification + Dockerfile
  generation

### Quality guarantees

* **Real, verified citations** — every citation traces to Crossref /
  Semantic Scholar / PubMed / arXiv. Synthesis refuses hallucinations.
* **Numbered claim grounding** — every number in synthesis traces to a
  workspace artefact (`tool_audit_claims`).
* **Per-step completeness gate** — synthesis BLOCKS until every active
  step has a focal figure + caption sidecars + non-stub conclusions.
* **Pre-registration drift** — `tool_preregister_freeze` content-hashes
  the SAP before data; `tool_preregister_diff` surfaces every
  deviation at synthesis time.
* **Code quality** — `tool_audit_code_quality` blocks bare-except,
  import-*, eval / exec, hardcoded absolute paths, functions > 150 lines.
* **Prose quality** — `tool_audit_prose` flags hedging clusters, vague
  quantifiers, passive voice, causal language on observational designs.
* **Color accessibility** — Okabe-Ito / viridis / PuOr defaults;
  `visualization/color_accessibility_audit` provides deeper checks.

### Reasoning + memory

* **Grounded reasoning** — ReAct + CoVe + PROV-O + Reflexion. Every
  decision binds to evidence (papers / context / datasets / web).
* **Sub-task pipelines** — `pipeline.yaml` declares atomic nodes
  (ingest → validate → clean → fit → diagnose → visualize → report).
  Content-hash cached; edits re-run only the affected chain.
* **Provenance sidecars** — every figure / table / model emits a
  `<name>.prov.json` recording script + input hashes + parameters +
  RNG seed + library versions + wall time.
* **Lessons across sessions** — `tool_lessons_record` /
  `tool_lessons_consult` so the next attempt doesn't repeat past
  mistakes.

### Scaffold doctrine

Codified in [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md):
every protocol names the QUESTIONS the AI must answer + the GROUNDING
it must cite. Tools, thresholds, finite method menus, and canned step
sequences are PRESCRIPTION and out of scope. Protocols are scaffolds
for reasoning, not scripts to execute.

### Operations

* **HPC ready** — SLURM submit / status / fetch. Per-step Apptainer
  recipes + reproducer `entrypoint.sh`.
* **Per-step environment locking** — `tool_step_env_lock` pins
  `requirements.txt` + `python_version.txt` (+ optional `conda.yaml`
  + per-step `Dockerfile`) inside each step.
* **Self-tested dashboards** — auto-generated Playwright suite covers
  TOC scroll-spy, theme toggle, sortable tables, lightbox figures,
  print stylesheet, ARIA snapshot, axe-core WCAG, visual regression.
* **Background tasks** — `tool_task_run` (real `Popen`) for long jobs;
  `tool_task_status` polls without blocking the chat.
* **Session resume / handoff** — `tool_session_resume` reconstructs
  intent from logs after any pause; `sys_session_handoff` snapshots a
  checkpoint + writes a fresh-AI-readable handoff doc.

### Docs (10 docs, consolidated)

* [`docs/README.md`](docs/README.md) — table of contents + pick-your-path
* [`docs/START.md`](docs/START.md) — install + first project + cheatsheet (replaces QUICKSTART + FIRST_HOUR + CHEATSHEET)
* [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md) — full workflow walkthrough (replaces GUIDE + WALKTHROUGH + the old RESEARCHER_GUIDE)
* [`docs/USE_CASES.md`](docs/USE_CASES.md) — role × goal × output map
* [`docs/SETUP.md`](docs/SETUP.md) — install + per-IDE MCP wiring (absorbs SETUP_PROMPT)
* [`docs/FAQ.md`](docs/FAQ.md) — common questions
* [`docs/AI_GUIDE.md`](docs/AI_GUIDE.md) — orientation for the AI driving Research OS
* [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md) — protocol catalogue + triggers + quality bars
* [`docs/TOOLS.md`](docs/TOOLS.md) — every MCP tool with example calls
* [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md) — the scaffold-not-script principle

### Robustness refinements (folded into 1.0.0)

* **No empty-folder pollution.** Scaffolding now creates only directories
  guaranteed to be populated. `synthesis/`, `environment/`, and
  `inputs/{raw_data,literature,context}/` are LAZY — they materialise at
  first write via `ensure_lazy_dir(root, rel)`. A fresh `research-os init`
  surface has zero orphan `.gitkeep`-only folders. `_prune_stale_gitkeeps`
  now also removes any empty lazy-dir leftovers from pre-1.0 projects.
* **No premade boilerplate.** `docs/research_overview.md` is no longer
  written at init — it is created lazily by `tool_intake_autofill` once
  the researcher has actual context to summarise. `inputs/intake.md` is
  reduced to a one-sentence pointer.
* **Mega-script blocker.** `tool_audit_step_completeness` now BLOCKS
  (not just warns) when a step's outputs span multiple categories
  (figures + tables + reports) without a `pipeline.yaml` declaring the
  sub-task DAG. Atomic scripts per sub-task are mandatory — the
  reproducibility guarantee depends on it.
* **Deliberate iteration versioning.** New `tool_step_iterate(step_id,
  rationale=…)` snapshots a coordinated unit (scripts + outputs +
  caption / summary / prov sidecars + conclusion) into
  `.versions/v<n>/` before the researcher edits anything. The live
  filenames stay stable so cross-step references in conclusions /
  dashboards don't rot. `tool_step_iterations_list` returns the ledger.
* **Version-coherence audit.** `tool_audit_version_coherence` walks
  every step and flags drift: an output whose `.prov.json` points at a
  script no longer on disk OR at `_v<k>` when `_v<k+1>` exists OR a
  caption sidecar older than its figure. Report at
  `workspace/logs/version_coherence.md`.
* **Override discoverability + audit trail.** The previously-undeclared
  `override_completeness_gate` parameter is now in the inputSchema for
  `tool_synthesize` and `tool_dashboard_create`; `override_gate` /
  `override_rationale` are documented on `tool_plan_advance`. Every
  bypass appends to `workspace/logs/override_log.md` (the
  pre-submission audit surfaces them).
* **User-side override policy.** `researcher_config.yaml` gains
  `interaction.quality_gate_policy` (`enforce` | `allow_override` |
  `warn_only`) and `interaction.ambiguity_posture`
  (`ask_when_uncertain` | `take_best_default`). Defaults are
  conservative; the researcher tightens or loosens to taste.
* **Per-IDE rule parity.** `.windsurfrules` and `.continuerules` now
  use the same `sys_boot` + `tool_route` boot pattern as
  `AGENTS.md` / `.claude/` / `.cursor/` / `.antigravity/` —
  no more legacy `sys_config_get + sys_state_get` cost.
* **AGENTS.md escape clause.** Hard rule 11 (multi-script DAG) is
  tightened. New rule 12 separates bug-fix versioning (bump `_v<n>`)
  from deliberate iteration (`tool_step_iterate` first). A new
  "When the researcher explicitly overrides a rule" section formalises
  the bypass protocol: explicit current-message authorisation,
  `override_rationale` mandatory, logged.

### Test + quality status

* 380+ tests pass; preflight 13 / 13 checks green
* 87 protocols indexed; all router refs + tool refs resolve
* All protocols at version 1.0.0
* 143 MCP tools (140 baseline + `tool_step_iterate` +
  `tool_step_iterations_list` + `tool_audit_version_coherence`)
