# Research-OS roadmap (post v1.4.2)

*Self-contained planning doc. Goal: make Research-OS reliable, usable at every researcher experience level, in every domain, with any AI model from a $5 Gemini Flash run to a $50 Opus 4.7 run. Written so it is actionable AFTER context compression — no reliance on conversation history.*

---

## What Research-OS actually is (so the plan stays grounded)

A **Python package** that ships an **MCP server**. The MCP server runs as a sidecar process to the researcher's AI chat IDE (Claude Code, Cursor, Codex, OpenCode, Antigravity, Continue, Aider, VS Code, Windsurf). The IDE owns the model + the conversation; the MCP server provides **tools** (Python functions exposed via MCP) and **protocols** (YAML scaffolds the AI loads on demand).

**What the MCP can do:**
- Read/write files in the workspace
- Define tools with JSON schemas, return structured data
- Make HTTP calls (literature search, PDF download, web fetch)
- Run subprocesses (Python / R / Julia / bash scripts)
- Log to local files
- Serve protocol YAML on demand
- Build search/routing indexes over its protocols
- Generate dashboards, figures, audit reports

**What the MCP CANNOT do (constraints that shape this roadmap):**
- See token counts, dollar cost, or IDE billing — the IDE never sends these
- Know what model is running — only what the researcher wrote in `researcher_config.yaml`
- Force the model to call a specific tool — only suggest via routing
- Run code between AI turns — only when invoked by a tool call
- Push notifications to the AI — only respond to its calls
- Hold cross-session conversation state in memory — only via workspace files

The roadmap respects all of these constraints. Anything that would require "MCP enforces a $5 budget" or "MCP knows you're on Haiku and switches protocol variant" is structurally impossible — those have to flow through `researcher_config.yaml` (researcher self-declares) and the AI honestly honors them.

---

## Current state (v1.4.2, June 2026)

- **113 protocols** in 9 categories; **146 MCP tools**
- Strong on biology/clinical/quantitative paper publication with frontier models (Opus 4.7, Sonnet 4.6, GPT-5)
- Stress-tested via 22-turn agent sequences + 3-agent audits per release
- Open audit-surfaced gaps (deferred from v1.4.0):
  1. `findings_vs_literature.md` is a write-only side-channel — verdicts never reach the Discussion
  2. PDF retrieval is structurally optional — `papers_downloaded: 0` with mixed AGREES sails through
  3. `literature_per_step` is trigger-routed, not pipeline-mandatory
  4. `stack_plan.md` is a WARN, not a BLOCK
  5. ~34 of 146 tools still orphan (no protocol references them)

---

## Themes for v1.5.0 → v2.0.0

### Theme 1 — Close the v1.4.0 audit gaps (must-do for v1.5.0)

1. **`findings_vs_literature.md` → Discussion pipe.** `writing/writing_discussion` reads every step's verdict file and emits one Discussion paragraph per non-AGREES verdict citing the contested literature. Without this, the literature loop is theater.
2. **Default-deny synthesis when `papers_downloaded == 0`** across all literature-required steps. Override via `override_no_pdfs=true` + rationale.
3. **`literature_per_step` injected into `analysis_plan.decomposition`** as a pipeline-mandatory sub-protocol between findings-write and `path_finalize`. Coverage went from 2/10 → expected 10/10.
4. **`stack_plan.md` WARN → BLOCK.** Pair with: auto-invoke `pick_tool_stack` from `methodology_selection.pick_tools`.
5. **Orphan tool sweep.** For each of the ~34 unreferenced tools: wire it into a protocol OR mark deprecated (queue removal for v2.0.0).

**Effort:** ~1 week. **Lands v1.5.0.**

---

### Theme 2 — Lean protocol variants the AI opts into (replaces my earlier "MCP serves weak-model variant" — that was wrong; MCP can't know the model)

Reality: the AI reads `researcher_config.model_profile` at startup. The MCP can offer LEAN variants of long protocols; the AI honestly picks based on its self-knowledge.

- **`format='lean'`** option on `sys_protocol_get` (alongside today's `summary` / `step` / `full`). Returns a 2-3 step distilled variant of the protocol with bullet-point step descriptions, all optional sub-steps removed, and structured-output schemas inlined.
- **Per-protocol `lean_variant` field in YAML.** Author writes both. If absent, server auto-distills (cap at 3 steps, drop "consider X" wording, inline schemas).
- **AI guidance in `AGENTS.md`:** if `researcher_config.model_profile == "small"`, prefer `format='lean'` by default. If `medium`, use `summary`. If `large`, use `full` when needed.
- **More JSON schemas on tools.** Today many tool inputs are free-form strings. Adding `additionalProperties: false` + required fields on every input gives a smaller model less room to drift. Validation happens at MCP tool-call layer with explicit retry-on-mismatch.

**Effort:** ~2 weeks (variant authoring + schema tightening pass). **Lands v1.6.0.**

---

### Theme 3 — Adaptive friction (stop hassling rigorous researchers)

The MCP CAN read project files and infer rigor signals. It cannot read minds, but it can read code, methods.md, citations, version control state.

- **`tool_rigor_signals_scan`** (new tool). Scans the project for: substantive `methods.md` on first load, citation density in any prose, version-controlled inputs (`.git` present), preregistration artifact, well-commented scripts (heuristic), prior `step_summary.yaml` quality. Returns a `trust_score` (0-100) + signals list.
- **Gate strictness scales with `trust_score`.** High score: gates emit *notes* instead of *blockers*. Low score: full enforcement. Researcher overrides via `researcher_config.gate_strictness: light | normal | strict`.
- **Per-step skip annotations.** Researcher writes `<!-- ro:skip lit_loop, reason: already did project-wide review -->` in `conclusions.md`; audit honors it (logged to `override_log.md`).
- **`tool_self_certify`** persistent across sessions. Stores `researcher_certifications.yaml` in workspace; audit checks it before firing each gate.

**Effort:** ~1.5 weeks. **Lands v1.5.1 or v1.6.0.**

---

### Theme 4 — Domain packs via plugin system

The MCP CAN ship a plugin loader. Protocols are YAML; tools are Python with a registration decorator. Third-party packages can extend.

- **Plugin architecture.** Entry-point group `research_os.protocol_pack`. Each pack ships: protocols (YAML), optional tools (Python with `@register_tool`), router-index entries, optional domain detectors.
- **`pip install research-os[humanities]`** style extras + standalone `pip install research-os-humanities` for community packs.
- **Launch packs** (4-5 to demonstrate the system, then community-driven):
  - `humanities` — textual analysis, archival research, source provenance (manuscript → edition → translation → quotation)
  - `qualitative` — coding scheme refinement, member-checking, grounded theory cycles, inter-rater reliability
  - `theory_math` — proof-step verification, theorem dependency graphs, Lean/Coq hooks, conjecture tracking
  - `wet_lab` — versioned bench protocols, reagent + lot tracking, plate-map provenance, instrument-run logs
  - `engineering` — design iteration with FMEA, test-failure causation, build-test-fix loops
- **Domain detector at intake.** `tool_domain_detect` reads `inputs/` file types + brief content, suggests the pack: "this looks like archival history — install `[humanities]`?"

**Effort:** ~4 weeks (plugin infra) + ~2 weeks per pack. **Lands v1.7.0 (infra) → v1.7.x (packs).**

---

### Theme 5 — Quick mode (stop being overkill on throwaway work)

The MCP CAN add an intent class to `tool_route`. The AI calls `tool_route` already; this is a routing change.

- **`tool_route` returns `complexity: quick`** for intents matching: "just make me a plot", "sanity check", "exploratory only", "throwaway viz", "quick look at this".
- **Quick mode behavior:** no protocol load, single shortcut tool, outputs land in `workspace/scratch/`, no provenance sidecars required, no audit gates fire.
- **`tool_promote_to_step`** wraps a quick-mode result in proper provenance retroactively if the researcher decides it earned its keep.
- **`researcher_config.project_tier: throwaway | sketch | production`** sets default audit strictness across the whole project.

**Effort:** ~1 week. **Lands v1.5.1.**

---

### Theme 6 — Protocol + tool consolidation (cull the surface)

113 protocols + 146 tools is a lot for a small/medium model to navigate. Reduce by combining + removing without losing capability.

**Tools to consolidate / remove:**
- The 9 grounded-reasoning tools (`thought_log`, `thought_trace`, `grounding_register`, `ground_from_context`, `claim_verify`, `grounding_verify`, `lessons_record`, `lessons_consult`, `plan_step_grounded`) — wired in v1.4.0 but several do near-identical things. Consolidate to 4: `tool_thought_log` (append), `tool_ground` (register + ground_from_context merged with mode param), `tool_verify` (claim_verify + grounding_verify merged), `tool_lessons` (record + consult merged with operation param).
- The 5 search tools (`tool_search_semantic_scholar` / `_pubmed` / `_crossref` / `_arxiv` / `_web`) → consolidate to 1: `tool_search` with `source: auto | semantic_scholar | pubmed | crossref | arxiv | web` (auto picks based on domain). Today's per-provider tools become internal dispatch.
- The 4 plan tools (`tool_plan_turn` / `_advance` / `_clear` / `_step_grounded`) → consolidate to 2: `tool_plan(operation: turn | advance | clear)` + `tool_plan_grounded` standalone.
- Audit family is already focused (~10 tools); keep.
- **Target: 146 → ~90 tools.**

**Protocols to consolidate / remove:**
- 42 methodology protocols include lots of per-family deep workflows (causal_inference_deep, machine_learning, clinical_trials, etc.) that are rarely loaded. Merge family protocols into a single `methodology/per_family.yaml` with `domain` parameter — the AI picks the relevant section instead of loading a different file. Each section becomes a 1-page sub-protocol.
- 17 synthesis protocols can compress to 8 by merging closely related ones: `synthesis_poster` + `synthesis_handout` (printable variants), `synthesis_slides` (multi-audience), `synthesis_lay_summary` (audience-parametrized).
- Drop `pre_submission_checklist` as a separate protocol — merge into `audit_and_validation` as a final phase.
- **Target: 113 → ~75 protocols.**

**Net effect:** smaller surface, faster routing, less for small models to misnavigate, no capability loss.

**Effort:** ~3 weeks (carefully — needs migration aliases for back-compat). **Lands v1.6.0 (additive consolidation) → v2.0.0 (remove deprecated aliases).**

---

### Theme 7 — Coaching mode (researchers who want to learn)

The MCP CAN respect `autonomy_level` and the AI honors it.

- **`autonomy_level: coaching`** — RO doesn't auto-execute; protocol step descriptions become "ask the researcher to draft X, then critique their draft against this checklist".
- **Per-protocol pedagogical prefix.** Optional `coaching_prelude` field in each protocol YAML. Loaded when `autonomy_level == coaching`. AI surfaces it as a question before executing.
- **Gate explanations are pedagogical.** Instead of "BLOCKER: missing summary.md", the gate emits "this gate exists because [reason]; here's what fails in published work when summaries are stubs". AI surfaces.
- **`tool_mistake_replay`** — pulls local override + BLOCK history (Theme 9 telemetry) and presents the researcher's recurring gaps as a learning artifact.

**Effort:** ~2 weeks. **Lands v1.6.0.**

---

### Theme 8 — Custom infrastructure adapters

The MCP CAN parse project files to detect infrastructure. Plugin system (Theme 4) lets third parties ship adapters.

- **Adapter registry** built on plugin system. Adapters expose: detect (returns `True/False` from project state), describe (returns capabilities), extract (returns tools.md entries from project files).
- **Launch adapters:**
  - Slurm/PBS — parse `#SBATCH` headers, capture cluster + partition + time
  - Snakemake — parse `Snakefile`, render DAG, capture rule provenance
  - Nextflow — parse `.nf`, capture process resources
  - Cytoscape sessions — parse `.cys`, extract network metadata
  - GraphPad Prism — parse `.pzfx`, extract analysis tables
  - REDCap exports — parse `.csv` + data dictionary
  - Synapse repos — `synapseclient` integration
- **Domain-aware `tools.md` extractor.** Today's regex parses Python imports. Extend to: R `library()` calls + BiocManager versions, `module load` directives, conda env files, npm package.json, Cargo.toml, Pipfile, Project.toml.
- **Auto-detect at startup.** If sbatch headers found → suggest Slurm adapter. Snakefile present → suggest Snakemake adapter.

**Effort:** ~3 weeks (framework) + ~1 week per adapter. **Lands v1.8.0.**

---

### Theme 9 — Telemetry-free local reliability logging

The MCP CAN write to local files. Privacy-preserving — never leaves the workspace unless researcher explicitly shares.

- **`workspace/.os_state/reliability.jsonl`** logs (one line per event): protocol name + version, `model_profile` (from config — what researcher claims), gate fires, recovery success, abandon, tool errors. No project content, no PII.
- **`tool_reliability_report`** the researcher voluntarily runs to share when filing a bug — produces a redacted summary.
- **No telemetry by default.** No phone-home. Optional opt-in for anonymized aggregate metrics (default OFF, requires explicit `runtime.share_anonymous_metrics: true`).
- **Internal use:** the maintainer runs the same `tool_reliability_report` on their stress-test reference projects to detect regressions across releases.

**Effort:** ~1 week. **Lands v1.5.0.**

---

### Theme 10 — Continuous stress-testing in CI

The MCP CAN be tested in CI. Reference projects + a model-runner harness.

- **Reference project corpus.** 3-5 canonical projects, one per domain pack, locked snapshots stored in `tests/fixtures/projects/`.
- **CI runs the full pipeline** against each project on every PR, comparing to last-release baseline.
- **Per-protocol SLO metrics.** Success rate, gate-recovery rate, time-to-completion, tool-error rate. Regression on any metric blocks merge.
- **Multi-model test matrix.** Quarterly run against Opus 4.7 / Sonnet 4.6 / Haiku 4.5 / GPT-5 / Gemini 3 Pro / Gemini Flash / DeepSeek-V3 / Llama 3.3 70B (local). Surface per-protocol per-model success rates as a public chart in `docs/RELIABILITY.md`.
- **Researcher-visible quality signal.** A user can see "this protocol works at 95% on Sonnet, 75% on Haiku" before choosing.

**Effort:** ~2 weeks setup + ongoing. **Lands v1.7.0.**

---

### Theme 11 — Stale-state detection + recovery

The MCP CAN read file mtimes and state.json timestamps.

- **`tool_state_freshness_check`** runs at `sys_boot`. If `state.json` last write > 30 days ago, OR `workspace/citations.md` older than newest `inputs/literature/*.pdf`, OR per-step provenance points to scripts that no longer exist, surface a "stale state — reconfirm?" prompt.
- **Cross-step coherence audit** (new tool `tool_audit_coherence`). Verifies every paragraph in `synthesis/paper.md` maps to a step's `conclusions.md`; flags orphan paragraphs. Catches the failure mode where Discussion text was written in a prior chat and the step it referenced was later abandoned.

**Effort:** ~1 week. **Lands v1.5.1.**

---

### Theme 12 — Retry policy + paywall memory

The MCP CAN remember per-tool failures across calls within a workspace.

- **`workspace/.os_state/tool_failures.jsonl`** logs: URL/DOI tried, error reason, timestamp, tool. `tool_literature_download` checks this before retrying — skips known paywalls + permanent 404s.
- **Per-step retry policy** in `step_summary.yaml`: `tool_failures: [{tool, target, reason, retry_after}]`. Audit shows the researcher what's been tried + what's still possible.

**Effort:** ~0.5 weeks. **Lands v1.5.0.**

---

### Theme 13 — Dry-run mode for protocols

The MCP CAN serve a dry-run version of a protocol — returns the tool sequence it WOULD invoke, without writing files.

- **`sys_protocol_get format='dryrun'`** returns the protocol's full tool-call sequence with predicted args, without executing.
- **`tool_dry_run`** wraps an existing protocol invocation in a dry-run shell; AI uses to preview before committing.
- **Use case:** researcher in supervised mode can review the plan before letting the AI execute. Cheaper than committing + rolling back.

**Effort:** ~1 week. **Lands v1.6.0.**

---

### Theme 14 — Intake re-entry detection

The MCP CAN detect existing workspace artifacts before re-running intake.

- **`project_startup` skips intake autofill** when `inputs/intake.md` exists AND has substantive content AND was edited in last 90 days.
- **`mid_pipeline_entry` becomes the default** when ≥1 numbered step folder exists with `conclusions.md`.
- **`tool_intake_freshness`** returns recommended intake depth (full | refresh-only | skip) based on workspace state.

**Effort:** ~0.5 weeks. **Lands v1.5.1.**

---

### Theme 15 — Tool-call output coalescing for small models

The MCP CAN bundle frequently-called-together tools into single tool calls.

- **`tool_step_complete`** new bundle: runs `tool_path_finalize` + `tool_audit_step_completeness` + `tool_audit_step_literature` + `tool_step_revision_options` in one call. Returns combined result. Reduces 4 tool calls → 1; eliminates small-model drift between calls.
- **Audit family bundle.** `tool_audit_quality_full` already does this; verify coverage for the new v1.4.0 gates.
- **Search + download bundle.** Already exists: `tool_literature_search_and_save`. Add similar bundles for other multi-step flows.

**Effort:** ~1 week. **Lands v1.6.0.**

---

---

## Synthesis output quality themes (16-25)

**Motivation:** observed quality issues in v1.4.x synthesis outputs:
- `synthesis/paper.md` ships as raw markdown — not what reviewers, journals, or PIs want
- `dashboard.html` has nice typography but weak content structure, no real interactivity, no search/filter/nav
- Interactive figure companions exist as a protocol but aren't enforced — most projects ship static-only
- Slide deck output is markdown, not actual slides
- Poster is templated but not auto-compiled to PDF
- No preview before generation → researcher discovers quality issues post-commit
- Numbers / figures / citations drift across paper / dashboard / slides
- Sections often look templated rather than substantive (each project produces similar-looking output)

Synthesis is the **last mile** — every other improvement is wasted if what lands on the PI's desk looks generic. These 10 themes overhaul the publication-stage outputs.

---

### Theme 16 — Typst-native paper compilation (replaces raw markdown output)

The MCP CAN shell out to Typst (`typst compile`). Typst is fast (10-100× LaTeX), type-safe, modern, single-binary install.

- **`tool_paper_compile_typst`** — compiles `synthesis/paper.md` → `synthesis/paper.typ` → `synthesis/paper.pdf`.
- **Markdown → Typst translation layer.** Headings, lists, citations, figure refs, math, tables all map cleanly. Implemented as a small Python translator (don't pull in pandoc unless researcher already has it).
- **Per-venue templates** in `templates/typst/`: `nature.typ`, `science.typ`, `nejm.typ`, `cell.typ`, `ieee_conf.typ`, `neurips.typ`, `acl.typ`, `plos.typ`, `generic_two_column.typ`, `generic_thesis.typ`. Researcher picks via `researcher_config.writing_preferences.venue_template`.
- **Citation styles via Hayagriva** (Typst's bibliography engine) — supports APA / Vancouver / IEEE / ACM / Nature / Cell out of the box.
- **Figures embed as PDF** (preferred for vector) or PNG (raster fallback). Auto-detects.
- **Paper.md remains the source of truth** (AI-editable, version-controlled, diff-friendly). The PDF is the deliverable.
- **LaTeX still available** via existing `tool_latex_compile` for venues that require `.tex` submission.

**Effort:** ~3 weeks. **Lands v1.9.0.**

---

### Theme 17 — Interactive dashboard rebuild (single-page web app)

Today's dashboard is a long-scroll static HTML. Needs to be a real app.

- **Sidebar navigation.** Step list (collapsible), section anchors, "jump to figure", "jump to claim". Sticky on scroll.
- **Search box.** Full-text search across all step conclusions + paper sections, with hit highlighting. (Lunr.js or MiniSearch — both offline.)
- **Filter panel.** By hypothesis ID, step status (active / completed / dead-end), decision type, contains-DISAGREES-verdict, has-PDF-evidence.
- **Brushing across figures** (Vega-Lite cross-filter). Click a point on the volcano → corresponding row highlights in the DGE table.
- **Plotly figures inline-rendered** when interactive HTML exists for a figure (per Theme 20).
- **Per-figure tab toggle:** static (PNG) ↔ interactive (HTML iframe). Researcher picks default per project.
- **Reactive tables** with sort, filter, CSV export.
- **Mermaid diagrams** rendered for workflow.mermaid + protocol decomposition.
- **Print stylesheet** that flattens to a printable static PDF (Theme 18 enforces this works).
- **Offline-only** — no CDN, all JS/CSS inlined. Single file delivery.

**Effort:** ~4 weeks (substantial frontend work, but uses established libraries). **Lands v1.9.0 - v1.10.0.**

---

### Theme 18 — Dashboard content quality gates (not just structure)

Today's audit checks the dashboard renders. It does NOT check the CONTENT inside is good.

- **Numeric claim cross-check.** Every number on the dashboard (DGE counts, p-values, hazard ratios, sample sizes) must trace to a workspace table cell. Use `tool_audit_claims` extended to scan dashboard HTML. BLOCK if ungrounded.
- **Figure-to-text proximity audit.** Every figure must be cited within ±2 paragraphs of its placement. Orphan figures (cited nowhere or far from citation) flagged.
- **Section substantiveness audit.** Per-section min/max word counts + min-claims (e.g. Discussion ≥3 distinct claims with citations). Stub detection.
- **Accessibility audit** (WCAG 2.2 AA). Contrast ratios, keyboard nav, ARIA labels, alt text on every figure (pulled from `.summary.md`), heading hierarchy. Fails surface as warnings.
- **Print-friendly variant audit.** Generate the print stylesheet output, verify no figures lost, no critical content hidden by `display: none`, page-break sanity.
- **Color palette consistency.** Every figure on the dashboard uses the same CVD-safe palette (Okabe-Ito / viridis / PuOr). Mismatches flagged.
- **Dashboard-specific reviewer simulation.** New tool `tool_dashboard_reviewer_sim` walks the dashboard top-to-bottom asking "would a 5-min skim convey the finding?" — flags sections that bury the lede.

**Effort:** ~2 weeks. **Lands v1.9.0.**

---

### Theme 19 — Real slide deck + poster compilation (PDF / Reveal.js native, not markdown)

Today `synthesis_slides` outputs markdown. Researchers want actual slides. Poster exists but should be PDF-native.

- **Slides:** `tool_slides_compile` → Reveal.js HTML (offline-capable, animations, speaker notes) OR Typst Touying (PDF slides, academic talk style). Researcher picks engine; both supported.
- **Per-audience density profiles:** lab meeting (12 slides, dense), 12-min conf (8 slides, headline per slide), defense (30 slides, every result), invited seminar (20 slides, narrative arc). Loads template + word/figure budget per slide accordingly.
- **Auto-embed interactive figures** in Reveal.js path (per Theme 20 + 21).
- **Speaker notes auto-drafted** from each step's `.summary.md`.
- **Poster:** `tool_poster_create` → PDF via Typst poster templates (v2.0.0: tikzposter LaTeX path removed; Typst is the only supported engine). Templates per size (36×48, 48×36, A0 portrait, A1 landscape, public 24×36). Print-ready bleeds, embedded fonts, RGB→CMYK conversion option. QR code with project DOI/URL auto-embedded.
- **One-headline test enforced** (poster body must have exactly one headline conclusion; gate BLOCKS if multiple compete).

**Effort:** ~3 weeks. **Lands v1.10.0.**

---

### Theme 20 — Per-figure interactive companion enforcement

The visualization/interactive_figure_design protocol already documents WHEN to make interactive figures. Audit needs to enforce it.

- **`tool_audit_figure_interactivity`** new gate. For each figure in `workspace/<step>/outputs/figures/`:
  - If figure has >200 marks (volcano, UMAP, scatter with n>200 points) → interactive `<name>.html` companion REQUIRED. BLOCK if missing.
  - If figure is a heatmap with >50 rows OR >50 cols → interactive companion REQUIRED (clustergrammer / Vega-Lite).
  - If figure is a network with >30 nodes → interactive companion REQUIRED (pyvis / cytoscape.js).
  - Time-series with >1000 points → interactive companion REQUIRED (Plotly zoom+brush).
- **Auto-generate fallbacks.** If researcher hasn't built the interactive companion, RO has a deterministic generator that produces a competent default from the data + the existing static figure's encoding. Researcher rewrites in their voice; the auto-fallback ensures the companion is never silently missing.
- **Static PNG remains the headline artifact** (required by paper PDFs); the interactive is a companion.
- **All HTML companions are offline-capable.** No CDN. inline JS/CSS or self-contained.

**Effort:** ~2 weeks. **Lands v1.9.0.**

---

### Theme 21 — Dashboard "story mode" + "explore mode"

Two distinct dashboard reading patterns. Today's dashboard does neither well.

- **Story mode** (Distill.pub aesthetic): narrative scroll, paragraph-by-paragraph, figures inline, sidenotes for technical detail. Optimized for a reader new to the project who wants the finding.
- **Explore mode** (current dashboard, polished): free navigation, all artifacts surfaced, search + filter, sidebar TOC. Optimized for a collaborator / reviewer who wants to verify.
- **Mode toggle in dashboard header.** Researcher sets default in `researcher_config.dashboard.default_mode: story | explore`.
- **Story mode source:** auto-generated from `synthesis/abstract.md` + each step's `.summary.md` (plain-English layer). Researcher polishes via `tool_dashboard_story_edit`.
- **Explore mode source:** today's dashboard content + Theme 17 features.

**Effort:** ~3 weeks. **Lands v1.10.0.**

---

### Theme 22 — Synthesis preview before commit (cheap dry-run)

Researcher should see what they're about to get BEFORE the AI spends tokens generating it.

- **`tool_synthesis_preview`** — for any synthesis target (paper / dashboard / poster / slides / grant / report), returns:
  - Predicted word count per section
  - Predicted page count (paper / poster) or slide count (deck)
  - List of figures that will be embedded
  - List of citations that will appear
  - List of steps each section draws from
  - Detected gaps (sections likely to be thin, figures missing captions)
  - Estimated render time
- **Researcher approves or requests changes** before the full synthesis runs. Saves a re-run if the structure is wrong.
- **Diff mode:** if a deliverable already exists, preview shows what would CHANGE on regenerate.

**Effort:** ~1.5 weeks. **Lands v1.9.0.**

---

### Theme 23 — Cross-deliverable consistency audit

Today's paper, dashboard, slides, poster all draw from the same workspace but drift in:
- Different numbers in abstract vs paper body (rounding mismatches)
- Same finding written 3 different ways across deliverables
- Figure numbers don't match across paper + slides
- Citation keys differ (some deliverables use `[@key]`, others use `(Doe 2024)`)
- Decimal precision varies

Fixes:

- **`tool_audit_deliverable_consistency`** scans all `synthesis/*` artifacts, surfaces:
  - Numbers that should match but don't (groups of equivalent claims)
  - Figure numbering inconsistencies
  - Citation key discrepancies
  - Section heading inconsistencies
  - Same finding worded differently (cosine similarity → flag if multiple < 0.7 phrasings of same numeric claim)
- **`tool_canonicalize_claims`** — researcher-approved canonical form for each repeated claim. Subsequent regenerates use the canonical form.
- **`workspace/synthesis_canon.yaml`** — single source of truth for: precision per number, citation key format, figure numbering scheme, headline statement.

**Effort:** ~2 weeks. **Lands v1.10.0.**

---

### Theme 24 — Reviewer-response scaffold (anticipate before submission)

Researchers write papers; reviewers find problems. RO can predict the obvious ones.

- **`tool_reviewer_simulate`** — given the drafted paper + each step's findings_vs_literature.md, generates 10-20 anticipated reviewer comments grouped by severity:
  - **Methodological** — "why DESeq2 not edgeR?", "why FDR 0.05 not 0.01?", "where's the sensitivity analysis?"
  - **Statistical** — "no multiple-testing correction in Section 3", "power analysis missing", "CI not reported for HR"
  - **Reproducibility** — "code/data availability statement says X but Y is private"
  - **Literature** — "Smith 2024 reports the opposite" (pulled from DISAGREES verdicts)
  - **Presentation** — "Figure 3 axis labels unreadable", "Table 2 lacks units"
- **Reviewer comments map to specific paper sections + line numbers.**
- **`tool_rebuttal_draft`** — given reviewer-sim output OR an actual reviewer's comments, scaffolds the rebuttal: per comment → paper change required → new draft language.
- **`tool_revision_diff`** — shows what changed between submission v1 and v2, formatted for reviewer-response document.

**Effort:** ~2 weeks. **Lands v1.10.0.**

---

### Theme 25 — Content depth enforcement (sections substantive, not templated)

Today's audit checks structure (sections exist, word counts above floor). Doesn't check that each section says something substantive. A 500-word Discussion of generic platitudes passes today.

- **Per-section content audit** beyond word count:
  - **Abstract** — must include: 1 finding with a number, 1 methodological choice, 1 conclusion. BLOCK if any missing.
  - **Introduction** — must include ≥3 cited prior works framing the question, 1 explicit "in this study, we…" sentence.
  - **Methods** — must mention every step's primary method by name, every software/library by name + version, every dataset by name + size. Coverage matrix: % of workspace steps actually described.
  - **Results** — must reference every focal figure, every primary statistic with its CI/p-value, every comparison made.
  - **Discussion** — must include ≥1 paragraph per non-AGREES literature verdict (per Theme 1 / v1.5.0), ≥1 explicit limitations paragraph, ≥1 future-work direction.
  - **References** — every cited key must appear in the bibliography, every bibliography entry must be cited.
- **`tool_section_substantiveness`** runs all of the above, BLOCKS synthesis assembly if any required element is missing.
- **Cliche detection.** Sentences matching common AI-generated patterns ("In this study, we investigate…", "Our results demonstrate that…", "Future work should explore…") flagged; replacement suggestions provided.
- **Per-step coverage in Methods/Results.** New gate: for every numbered step folder, Methods section must mention the step's slug or primary tool, Results section must cite the step's focal figure. Missing coverage = uneven paper.

**Effort:** ~2 weeks. **Lands v1.9.0.**

---

### Theme 26 — Live-doctrine vs historical-commentary separation (token-waste purge)

**Motivation:** every protocol YAML, tool description, and code comment currently carries inline historical commentary — "v1.4.0 added X", "v1.3.4 fixed Y", "previously this clobbered, now we ...", "v1.5.0 promotes to BLOCK". Every time the AI loads a protocol via `sys_protocol_get`, every time it reads a tool description via `sys_tool_describe`, it pays the token cost of historical narrative that belongs in git log + CHANGELOG, not in the live doctrine.

The MCP already carries the right signals for "when was this current":
- `version:` field on every protocol YAML
- `schema_version:` field
- `last_reviewed:` date
- `git log` / `git blame` for line-level history
- `CHANGELOG.md` for human-readable version notes

Live protocol bodies + tool descriptions should be **timeless** — what to do NOW, not the history of why it changed. This was the intent. Drift accumulated across v1.3.x and v1.4.x patch cycles where every fix added a "v1.X.Y: this now does Z" note.

**Concrete cleanup pass:**

- **Audit every `src/research_os/protocols/**/*.yaml`** for inline version mentions matching: `v\d+\.\d+\.\d+`, `as of (v|version)`, `previously this`, `now we`, `was the bug`, `the v1.X.Y stress test`, `bump to BLOCK in v...`. Move historical context to `CHANGELOG.md`. Keep only timeless rules in the live body.
- **Audit every `TOOL_DEFINITIONS["..."]["description"]` in `src/research_os/server.py`** for same patterns. Tool descriptions get loaded on every routing call; bloated ones cost real tokens.
- **Audit code comments in `src/research_os/tools/actions/**/*.py`** for inline version narrative. Comments that explain WHY a non-obvious choice was made stay (they're load-bearing). Comments that narrate "v1.3.4 changed this regex from X to Y because turn-22 of the stress test..." get stripped (git blame + CHANGELOG carries this).
- **Update `last_reviewed:`** date on every touched protocol.
- **Bump `schema_version:`** if the body's prescriptive content materially changed.
- **Do NOT touch the `version:` field semantics** — version is the package release, not the protocol revision.

**Lint enforcement (prevents regression):**

- Add `scripts/preflight.py` check: regex over `src/research_os/protocols/**/*.yaml` + `TOOL_DEFINITIONS` description strings for `v\d+\.\d+\.\d+` / `as of v` / `previously` / `now we` patterns. **Warn** on hit; **fail** if hit AND file was changed in this PR (so new additions can't introduce new commentary).
- Whitelist by file: `CHANGELOG.md`, `docs/RELEASING.md`, `docs/ROADMAP.md`, `docs/CHANGELOG_*.md` (anywhere version-mention is the point).
- Author guide update in `docs/PROTOCOL_DOCTRINE.md`: explicit rule "no version mentions in protocol bodies; CHANGELOG + git log are authoritative".

**Estimated savings:** today's protocols carry ~50-200 tokens of historical narrative each across 113 protocols → ~6-15K tokens of pure waste per `sys_protocol_get format='full'` call cascade. Tool descriptions add another ~10-30 tokens of narrative per tool across 146 tools → ~2-4K tokens per `sys_tool_describe` sweep. Total context-token savings per session: **~10-20K tokens** with no doctrine loss. On a 22-turn run with cached protocol loads, savings are ~30% of cached-input cost — meaningful at scale.

**Effort:** ~2 weeks (substantial careful editing across 113 protocols + 146 tool descriptions + ~30 code files, with preflight lint regression test). **Lands v1.5.2 — pure hygiene PATCH after v1.5.0 + v1.5.1 ship.**

**Going forward:** every PR that touches a protocol body or tool description gets the preflight lint applied. New "v1.6.0 added X" / "this used to clobber, now ..." narrative can't land. The discipline becomes structural rather than aspirational.

---

## Suggested release sequence

| Version | Themes | Effort | Headline |
|---|---|---|---|
| **v1.5.0** | 1 (audit gaps) + 9 (local reliability log) + 12 (paywall memory) | ~2 weeks | Literature loop is pipeline-mandatory + actually pipes into Discussion; never retry known paywalls |
| **v1.5.1** | 3 (adaptive friction) + 5 (quick mode) + 11 (stale-state) + 14 (intake re-entry) | ~3 weeks | Stops being overkill on rigorous users / throwaway work / mid-project entry |
| **v1.5.2** | 26 (version-commentary purge + preflight lint) | ~2 weeks | **Token-waste hygiene PATCH:** strip inline "v1.4.0 added X" / "v1.3.4 fixed Y" narrative from all 113 protocol bodies + 146 tool descriptions + code comments. Preflight lint prevents regression. Estimated ~10-20K tokens saved per session. |
| **v1.6.0** | 2 (lean variants) + 6 (consolidation phase 1) + 7 (coaching) + 13 (dry-run) + 15 (bundling) | ~7 weeks | Smaller surface (146→90 tools, 113→75 protocols), coaching mode, lean variants for small models |
| **v1.7.0** | 4 (plugin system + 2 first packs) + 10 (CI stress-test infra) | ~8 weeks | Plugin system + qualitative + humanities packs + per-release multi-model stress matrix |
| **v1.7.x** | 4 (remaining packs: theory_math, wet_lab, engineering) | ~6 weeks | Domain coverage complete |
| **v1.8.0** | 8 (infra adapters) | ~6 weeks | Slurm / Snakemake / Nextflow / Cytoscape / REDCap / Synapse |
| **v1.9.0** | 16 (Typst PDF) + 17 (interactive dashboard) + 18 (dashboard content gates) + 20 (interactive figure enforcement) + 22 (synthesis preview) + 25 (content depth) | ~10 weeks | **Synthesis overhaul phase 1:** paper compiles to PDF, dashboard is a real web app with search/nav/brushing, every figure has interactive companion, content depth enforced |
| **v1.10.0** | 19 (real slides + poster) + 21 (story/explore modes) + 23 (consistency audit) + 24 (reviewer scaffold) | ~7 weeks | **Synthesis overhaul phase 2:** real slide decks (Reveal/Touying), PDF posters, dashboard story mode, cross-deliverable consistency, reviewer-comment anticipation |
| **v2.0.0** (MAJOR) | Remove deprecated tool/protocol aliases from Theme 6 consolidation; breaking schema cleanups | ~2 weeks | Clean cut after 1.x stabilizes |

**Total calendar:** ~9 months at ~75% utilization.

---

## What's NOT in this roadmap and why

- **Session budget enforcement / cost caps.** The MCP cannot see token usage — only the IDE / API client knows that. Researchers track cost in their IDE billing.
- **MCP-side model identity detection.** The MCP cannot know which model is running; it relies on `researcher_config.model_profile`. The AI honestly self-reports.
- **MCP-pushed notifications.** MCP only responds to AI tool calls; it can't proactively interrupt the conversation. Workspace files (`STATE.md`, `step_summary.yaml`) carry state across turns.
- **Cross-session AI memory.** The AI starts each session fresh. RO persists everything to workspace files; AI re-reads via `sys_boot`.
- **Auto-model-switching.** Same constraint as budget — only the IDE can switch models. RO can recommend (in a tool's response text) but can't enforce.

---

## What "all positive honest assessment" requires after v1.10.0

For a researcher in any field, on any model, at any expertise level:

- **Throwaway plot?** Quick mode. 30 seconds. No protocol overhead.
- **Already rigorous?** Trust-score-driven adaptive friction. Gates warn instead of block.
- **Pure-theory math / wet-lab / humanities?** `pip install research-os[your_domain]`. Protocols fit your work.
- **Bespoke pipeline?** Slurm / Snakemake / Nextflow / Cytoscape / etc. adapter. tools.md captures it.
- **Cheap model?** Lean variants opt-in via `model_profile: small`. JSON-schema validation prevents drift. Bundled tools reduce call count. CI reliability matrix tells you which protocols work at which model tier.
- **Want to learn vs auto-do?** `autonomy_level: coaching`.
- **Trust the output?** `docs/RELIABILITY.md` shows per-protocol per-model success rates from current CI corpus.
- **Paper for submission?** Compiles to PDF via Typst with venue-correct template (Nature / Science / NEJM / IEEE / NeurIPS / ACL / generic). Not markdown.
- **Dashboard for collaborators?** Real single-page web app — sidebar nav, search across steps, interactive figures with brushing, story-mode or explore-mode. Not a long-scroll markdown render.
- **Slide deck for a talk?** Real slides — Reveal.js (HTML) or Touying (PDF) — per audience density (lab meeting / 12-min conf / defense / invited seminar). Speaker notes auto-drafted from per-step summaries.
- **Poster for a conference?** Print-ready PDF, embedded fonts, RGB→CMYK option, QR code, one-headline test enforced.
- **Every figure with >200 marks?** Interactive companion auto-generated if researcher didn't write one. Static PNG remains the paper-PDF artifact.
- **Want to know what the synthesis will look like before generating?** `tool_synthesis_preview` returns word count + figure count + TOC + predicted gaps. Approve before commit.
- **Cross-deliverable consistency?** Numbers in paper match numbers in dashboard match numbers in slides. Citation keys consistent. Figure numbering consistent.
- **Pre-submission?** Reviewer-simulation scaffold generates 10-20 anticipated comments so you fortify the draft before submitting, not after.
- **Section depth?** Every section audited for substantive content (Discussion has ≥1 paragraph per non-AGREES literature verdict, Methods covers every step, Results references every focal figure). No more generic-template Discussion sections passing audit.

The only remaining honest caveat: even Opus 4.7 hallucinates plausible-sounding details about what it doesn't know. RO's audit gates catch the consequences (unverified citation, missing provenance, claims not in workspace, cross-deliverable drift). They don't cure the root cause — and no MCP-level system can. That's the model's job, not ours.

After v1.10.0, the synthesis output a researcher hands their PI / submits to a journal / pins to a conference board is **indistinguishable in form from work produced over weeks by a careful human**, while being produced in hours from a thoroughly-audited workspace. That's the bar.
