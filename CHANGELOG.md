# Changelog

All notable changes to Research OS are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) ·
Versioning: [SemVer](https://semver.org).

---

## [1.5.0] — Close v1.4.0 audit gaps + reliability + paywall memory + stale-state + intake re-entry (2026-06-04)

MINOR release. Closes every audit gap surfaced in the v1.4.0 stress test
and adds four telemetry-free local utilities: reliability log, paywall
memory, stale-state detection, intake re-entry detection.

### Added — Theme 1: close v1.4.0 audit gaps

- **`tool_writing_discussion_from_verdicts`** — walks every step's
  `literature/findings_vs_literature.md`, finds DISAGREES + EXTENDS
  verdicts with a Discussion implication, and emits one paragraph per
  verdict into `synthesis/discussion.md` inside HTML-comment markers
  (idempotent — re-runs replace the auto-block; hand-edits outside the
  markers are preserved). Closes the v1.4.0 gap where verdicts never
  reached the Discussion.
- **`tool_discussion_coverage_audit`** — companion BLOCK gate. Every
  non-AGREES verdict in any step's `findings_vs_literature.md` must
  have a matching paragraph in `synthesis/discussion.md` (≥50%
  key-word overlap). Hard-wired into `writing_discussion.validate` —
  there is no override flag; coverage of contested literature is the
  entire point of the Discussion.
- **`tool_audit_synthesis` default-deny when `papers_downloaded == 0`**.
  Synthesis blocks when zero PDFs exist across all
  literature-required steps (`inputs/literature/` also empty). Override
  path: `override_no_pdfs=true` + `override_rationale=...` for
  structurally-unavailable literature (closed field, novel
  measurement).
- **`literature/literature_per_step` is now pipeline-mandatory in
  `analysis_plan`**. v1.4.0 routed it via trigger; v1.5.0 hard-wires
  it as the first gate of `finalize_step`. Steps that are pure data
  engineering set `literature_required: false` in
  `step_summary.yaml` to skip.
- **Missing `scratch/stack_plan.md` — promoted from WARN to BLOCKER**
  in `tool_audit_step_completeness`. Override is by writing the file
  with a one-line rationale, not by flag — the cost of writing the
  rationale down is small and the gap matters at synthesis time.

### Added — Theme 9: telemetry-free local reliability log

- **`tool_reliability_log_event`** — append one JSONL line per
  significant occurrence (gate fire, recovery, abandon, tool error,
  protocol start/complete, override used, stale state, paywall skipped)
  to `workspace/.os_state/reliability.jsonl`. No project content, no
  PII — payloads are redacted (strings >80 chars truncated; nested
  dicts walked). Never phones home.
- **`tool_reliability_report`** — produce a redacted markdown summary
  at `workspace/logs/reliability_report.md` the researcher can paste
  into a GitHub issue when filing a regression report.

### Added — Theme 11: stale-state detection + cross-step coherence

- **`tool_state_freshness_check`** — auto-called by `sys_boot`.
  Surfaces a "stale state — reconfirm?" prompt when (a)
  `workspace/state.json` mtime > 30 days, (b)
  `workspace/citations.md` older than newest
  `inputs/literature/*.pdf`, or (c) per-step `.prov.json` sidecars
  point to scripts that no longer exist. Returns is_stale + signals +
  prompt_for_ai for the AI to surface.
- **`tool_audit_coherence`** — cross-step coherence audit. Scores
  every paragraph in `synthesis/paper.md` against every step's
  `conclusions.md` via Jaccard shingle overlap (no embedding model
  required). Paragraphs scoring < 0.05 in Results / Discussion /
  Intro / Conclusion are flagged orphan — catches the failure mode
  where prose carried over from a prior chat about an abandoned
  step. Writes `workspace/logs/coherence_audit.md`.

### Added — Theme 12: paywall + permanent-error memory

- **`workspace/.os_state/tool_failures.jsonl`** logs URL/DOI tried +
  error + timestamp + tool.
- **`tool_failure_record` / `tool_failure_check` / `tool_failure_list`**
  expose the cache to protocols.
- **`tool_literature_download` and `tool_literature_search_and_save`**
  now pre-check the cache before retrying. Paywall / 404 / 403 errors
  auto-mark `permanent=true` so the cache survives across chats.

### Added — Theme 14: intake re-entry detection

- **`tool_intake_freshness`** — returns `recommended_depth: full |
  refresh-only | skip` based on `inputs/intake.md` substance + age
  (default fresh window 90 days). Skip when substantive AND edited in
  the last 90 days; refresh-only when substantive but older. Also
  flags whether ≥1 numbered step has `conclusions.md` so
  `mid_pipeline_entry` becomes the default routing.
- **`guidance/project_startup`** now calls `tool_intake_freshness` as
  its first substantive step (skips autofill when fresh, routes to
  `mid_pipeline_entry` when steps already exist).

### Improved

- **`sys_boot`** now returns a `freshness` block (is_stale + signals +
  prompt_for_ai) so the AI surfaces drift signals on the first turn.
- **`session_resume`** explicitly calls `tool_state_freshness_check`
  before the resume brief.
- **Orphan tool sweep** — every v1.5.0 tool is referenced from at
  least one protocol; preflight verifies tool refs resolve.

### Migration notes (v1.4.x → v1.5.0)

Three behaviour changes can surface as a BLOCKER on existing
workspaces — read these before upgrading:

1. **`tool_audit_synthesis` default-deny on zero PDFs.** Projects
   that previously assembled a paper without per-step
   `literature/*.pdf` files (e.g. relied solely on author-year prose
   citations) will flip to `status='error'` at the audit. **Fix
   options:** (a) run `tool_literature_search_and_save` for each
   step's claims, or (b) pass `override_no_pdfs=true` +
   `override_rationale=<one-sentence reason>` — both arguments are
   required (override silently passes only when paired).
2. **`tool_path_finalize` runs `tool_audit_step_literature` as its
   first gate.** Existing steps without
   `workspace/<step>/literature/findings_vs_literature.md` will block
   on finalize. **Fix options:** (a) run
   `research/literature_per_step` for the step, (b) set
   `literature_required: false` in `step_summary.yaml` for pure
   data-engineering steps, or (c) pass
   `override_literature_gate=true` + `override_rationale=...` to
   `tool_path_finalize`.
3. **`tool_audit_step_completeness` promotes missing
   `scratch/stack_plan.md` from WARN to BLOCKER.** No flag-based
   override — write the file. A one-line library-choice rationale
   suffices (the field-practice rationale matters at synthesis time).

### Validation

- `python scripts/preflight.py` — 14/14
- `python -m pytest -q` — 508 passed (492 baseline + 16 new across
  `tests/unit/test_v150.py` + `tests/tools/test_v1_5_0.py`; one
  existing audit test updated for the v1.5.0 stack_plan
  WARN→BLOCK semantics)
- `ruff check src/ tests/ scripts/` — clean
- Tool count: 146 → 156. Protocol count unchanged at 113.
- **Stress audit** — 3 parallel reviewers (correctness / integration /
  regression) produced 27 findings; 5 must-fix issues addressed
  before tag (override-rationale pairing, coherence numbered-list +
  code-block filters, single-word claim threshold,
  `audit_step_literature` wiring into `tool_path_finalize`,
  migration docs).

---

## [1.4.3] — Roadmap published (2026-06-04)

PATCH release. Docs-only — no code or behaviour change. Publishes
`docs/ROADMAP.md` so the v1.5.0 → v2.0.0 plan is on `main` and
available to future contributor / maintainer sessions without
relying on conversation history.

### Added

- **`docs/ROADMAP.md`.** 25-theme plan from v1.5.0 (close v1.4.0
  audit gaps + reliability log + paywall memory) through v2.0.0
  (consolidation cut). Includes per-theme MCP-capability framing
  (what the MCP CAN and CANNOT do), per-release effort estimate,
  and the suggested release sequence table.

### Validation

- `python scripts/preflight.py` — 14/14
- `python -m pytest -q` — 492 passed
- `ruff check src/ tests/ scripts/` — clean
- No code changes; docs-only.

---

## [1.4.2] — README PyPI badge cache-bust (2026-06-04)

PATCH release. README-only — no code or behaviour change. Forces image
proxies (GitHub `camo.githubusercontent.com` + PyPI's README image
cache) to refresh the PyPI version badge, which was still showing
`v1.3.3` for some viewers after v1.4.0 / v1.4.1 shipped.

### Fixed

- **README PyPI badge.** Added `&cacheSeconds=300` to the shields.io
  badge URL (`img.shields.io/pypi/v/research-os.svg`). Tells shields.io
  to refresh every 5 minutes instead of using the default longer
  cache. The new URL also breaks GitHub's stale camo proxy cache (a
  new src URL forces a re-proxy) and the new sdist upload regenerates
  PyPI's rendered README. Both viewers should now see the correct
  current version within minutes of the next release.
- **Note on reality:** the shields.io URL itself was always returning
  the correct version (confirmed via `curl`); only the downstream
  image proxies were serving stale frames. There was never a packaging
  / release-pipeline bug — purely a CDN/proxy cache issue.

### Validation

- No tests touched. preflight 14/14, pytest 492 passed, ruff clean.

### Migration

None — README-only release.

---

## [1.4.1] — Docs sync to v1.4.0 surfaces (2026-06-04)

PATCH release. Docs-only — no code or behaviour change. Closes the gap
between the v1.4.0 release notes and what user-facing docs actually say,
so a fresh reader landing on README / RESEARCHER_GUIDE / USE_CASES sees
the literature loop + language doctrine documented, not just mentioned in
CHANGELOG.

### Fixed

- **Count refs across 8 docs.** `110 protocols` → `113 protocols`,
  `149 MCP tools` → `146 MCP tools` in README.md, FAQ.md, PROTOCOLS.md,
  START.md, AI_GUIDE.md, RESEARCHER_GUIDE.md, TOOLS.md, CONTRIBUTING.md.
- **PROTOCOLS.md category table.** Updated stale per-category counts
  (methodology 29 → 42, synthesis 14 → 17, visualization 6 → 14,
  literature 4 → 5) and total (88 → 113). Added inline v1.4.0 callouts
  per category.
- **TOOLS.md audit section.** Added `tool_audit_step_completeness`
  + new `tool_audit_step_literature` entries with v1.4.0 behaviour
  notes (BLOCK on missing `.summary.md`, WARN on missing
  `stack_plan.md`, BLOCK on missing `findings_vs_literature.md`).
- **RESEARCHER_GUIDE.md.** Surface `literature_per_step`,
  `pick_tool_stack`, and `mixed_language_orchestration` in the
  category inventory with one-line descriptions.
- **AI_GUIDE.md.** Category table now flags which categories grew
  in v1.4.0 + names the new protocols.
- **USE_CASES.md.** New "What's new in v1.4.0" section + 3 new
  rows in the "By output type" table (literature_per_step,
  pick_tool_stack, mixed_language_orchestration).

### Validation

- preflight 14/14, pytest 492 passed, ruff clean — no functional
  changes; tests run for safety only.
- All count references now reflect the authoritative counts from
  `len(TOOL_DEFINITIONS)` (146) and the protocol YAML inventory (113).

### Migration

None — docs-only release.

---

## [1.4.0] — Literature loop + language/tool-stack doctrine + summary fill-rate fix (2026-06-04)

Rolls v1.3.4 fixes + four new pillars driven by user feedback after the 22-turn stress test:
(a) summary.md still empty in places,
(b) literature must be downloaded + cited per step (not just method-grounding at start),
(c) language + tool-set must be chosen carefully (and mixable),
(d) cited-literature must validate or guide each analysis step.

**Stats:** 113 protocols (all bumped to 1.4.0), 146 MCP tools, **491 tests pass** (+10 v1.4.0 regression). Preflight 14/14, ruff clean.

### Added — per-step literature loop

- **NEW protocol** `literature/literature_per_step.yaml` — invoked from `analysis_plan` after `document_conclusions`. Walk: extract top-5 claims from `conclusions.md` → search Semantic Scholar / PubMed / Crossref per claim → download top-3 PDFs into `workspace/<step>/literature/` → write `findings_vs_literature.md` with one `## Claim:` block per finding (Verdict: AGREES | DISAGREES | EXTENDS | DEFERRED + Evidence + Discussion implication) → register `tool_grounding_register` per non-deferred claim → CoVe-verify top-3 with `tool_claim_verify` → update `step_summary.yaml` with a structured `literature:` roll-up.
- **NEW tool** `tool_audit_step_literature` — per-step gate before `tool_path_finalize`. BLOCKS when `findings_vs_literature.md` is missing, any claim lacks a verdict, any DISAGREES verdict lacks a Discussion implication block, all-DEFERRED step has no PDFs in `workspace/<step>/literature/`, or `step_summary.yaml.literature.claims_grounded == 0` without `literature_required: false`. Writes `workspace/logs/step_literature_audit.md`.
- **Extended `audit_synthesis`** (was already v1.3.4 aggregation): now also aggregates per-step `literature_deferred` lists and `literature.claims_grounded == 0` across the workspace and BLOCKS final assembly. Override path: `override_completeness_gate=true` + `override_rationale=…`.
- **Wired 4 grounding tools** into existing protocols (they were orphan in v1.3.x):
  - `tool_ground_from_context` — `guidance/project_startup` registers the PI brief / context files as the upstream grounding anchor.
  - `tool_grounding_register` — `literature_per_step` calls per non-deferred claim.
  - `tool_claim_verify` — `writing/writing_core` + `literature_per_step` call on top-3 load-bearing claims.
  - `tool_grounding_verify` — `analysis_plan.lightweight_step_audit` + `audit/pre_submission_checklist.claim_grounding_audit` run as project-wide gates.

### Added — language + tool-stack doctrine

- **NEW protocol** `methodology/pick_tool_stack.yaml` — sister to `figure_guidelines.pick_library` but at the ANALYSIS level. Domain-to-library matrix: bulk RNA-seq → R Bioconductor (DESeq2/edgeR/limma), scRNA-seq → Python scanpy, Cox PH → R survival/survminer, WGCNA → R, PPI → Python networkx, geospatial → Python geopandas, psychometrics → R psych/lavaan. Steps: enumerate candidates → query field practice via PubMed/Semantic Scholar → check env compatibility → decide on mixing → record in `workspace/<step>/scratch/stack_plan.md`. Routed via `tool_route` triggers ("pick language", "deseq2 or pydeseq2", "seurat or scanpy", …).
- **NEW protocol** `methodology/mixed_language_orchestration.yaml` — explicit doctrine for Python ↔ R ↔ Bash composition WITHIN a single step. Hand-off-file contracts, serialization matrix (TSV / Parquet / .mtx / RDS / pickle / JSON / BED), per-language `pipeline.yaml` tags, schema assertions at consumer entry, per-language env snapshots, tools.md coverage.
- **researcher_config.yaml `tool_stack` block** — new fields: `preferred_languages: [python, R]`, `allow_mixed_language_steps: bool`, `field_practice_overrides_preference: bool`, `cite_field_practice_when_choosing: bool`.
- **Wired `tool_thought_log`, `tool_lessons_record`, `tool_lessons_consult`, `tool_plan_step_grounded`** into `analysis_plan` (consult before step / log decision at decide_next / record reflection after step).
- **Wired `tool_thought_trace`** into `pre_submission_checklist` (replay decision chains during reviewer-response prep).

### Fixed — summary.md fill-rate

- `figures.py::caption_synthesise` — when conclusions.md `## Findings` is prose (no bullets), now sentence-splits the prose + drops markdown table rows + uses the first ≥20-char sentence as "Why it matters." Same root-cause fix as v1.3.4's `path.py::_bullet_lines`, ported to the figure-sidecar code path. Empty "Why it matters" was the dominant cause of stub summary.md files in the stress test.
- `audit.py` — missing `.summary.md` now BLOCKS (was WARN in v1.3.x). Matches `visualization_workflow.yaml`'s stated doctrine ("Any figure WITHOUT .caption.md AND .summary.md is a BLOCKER") that the audit was contradicting.

### Orphan tool resolution (Pillar 4)

The 43-tool orphan-sweep deferred in v1.3.4 was approached additively: wire what's useful, defer removal to v2.0.0. All 9 grounded-reasoning tools (`thought_log`, `thought_trace`, `grounding_register`, `ground_from_context`, `claim_verify`, `grounding_verify`, `lessons_record`, `lessons_consult`, `plan_step_grounded`) now have at least one protocol reference. The remaining ~34 unused tools will be evaluated per-tool in v1.5.0 (wire-or-remove); removal of any non-aliased tool is MAJOR (v2.0.0).

### Validation

- preflight 14/14, pytest 491 passed (+10 v1.4.0 regression tests covering: `audit_step_literature` missing/disagrees-without-discussion/complete-loop/skipped-data-eng-step, `audit_synthesis` literature_deferred BLOCK, `caption_synthesise` prose fallback, `audit` missing-summary BLOCK escalation), ruff clean
- 113 protocols (3 new, all bumped to 1.4.0), 146 MCP tools (1 new), embeddings rebuilt
- pyproject.toml + __init__.py + CITATION.cff + 110 existing protocol YAMLs all bumped together
- `_router_index.yaml` bumped 9 → 10; 3 new entries (`literature/literature_per_step`, `methodology/pick_tool_stack`, `methodology/mixed_language_orchestration`)

### Stress-test driven additions (post 3-agent audit)

After the in-conversation 8-turn verification + 3 parallel audit agents (PI cold review + RO-creator judge + improvement-priorities verifier) converged:

- **`audit/step_literature.py`** — closed a silent-skip loophole: a step whose `conclusions.md` exists but whose `## Findings` section is < 40 chars previously returned `info["skipped"]` and was exempt from the literature gate. This let regenerated step-summary stubs (`findings: []`, truncated headline) opt out of the loop entirely. v1.4.0 now BLOCKS on stub-Findings + non-stub-conclusions; the AI must either repopulate Findings OR explicitly tag `literature_required: false`.
- **`audit/audit.py`** — `audit_step_completeness` now WARNS when a step has scripts but no `scratch/stack_plan.md` (the `methodology/pick_tool_stack` artefact). Promotes to BLOCKER in v1.5.0.
- **`analysis_plan.scope_step`** — added explicit pointer to `methodology/pick_tool_stack` when the step's method choice is non-trivial. Cheap wiring fix; addresses the audit finding that `pick_tool_stack` was orphan in the common path.

### Deferred to v1.5.0 / v2.0.0

Audit-surfaced gaps that ARE real but too large for a v1.4.0 patch:

- **v1.5.0: ingest `findings_vs_literature.md` into `writing/writing_core` Discussion synthesis.** Audit converged-on issue A — DISAGREES verdicts currently never reach the manuscript prose; the sidecar is a write-only side-channel. Fix: `writing/writing_core` discussion-drafting step must read every step's `findings_vs_literature.md` and produce one Discussion paragraph per non-AGREES verdict, citing the contested literature.
- **v1.5.0: default-deny synthesis when `papers_downloaded == 0` across all literature-required steps.** Audit converged-on issue C — `tool_audit_step_literature` only blocks when ALL claims are DEFERRED with no PDFs; mixed AGREES + 0 PDFs sails through, leaving the loop confabulation-anchored.
- **v1.5.0: inject `literature_per_step` into `analysis_plan` decomposition (mandatory between findings-write and `path_finalize`).** Audit converged-on issue D — currently trigger-routed, not pipeline-mandatory; coverage gap (2 of 10 steps had files in the baseline).
- **v1.5.0: promote stack_plan.md from WARN to BLOCK** + auto-invoke `pick_tool_stack` from `methodology/methodology_selection.pick_tools` when the method choice spans language boundaries.
- **v1.5.0: evaluate the ~34 remaining orphan tools** (9 grounding tools now wired); wire-or-recommend-removal per tool.
- **v2.0.0 (MAJOR): tool removal pass** — recommended-for-removal tools dropped.

### Migration notes (v1.3.x → v1.4.0)

- **Backwards-compatible additions.** Existing projects work unchanged; the literature loop is opt-in via `analysis_plan.ground_findings_in_literature` (only fires when AI invokes the new sub-protocol) AND via the new audit gate (which only blocks when run; existing `tool_path_finalize` callers don't auto-invoke it yet — opt in by calling `tool_audit_step_literature` before finalize OR `override_literature_gate=true`).
- **One enforcement tightening:** missing `.summary.md` now BLOCKS at `audit_step_completeness`. Projects with stub summaries that v1.3.x silently warned-but-passed will fail audit at v1.4.0. Resolve by calling `tool_figure_caption_synthesise` per figure OR rerunning `tool_path_finalize`.
- The `tool_stack` block in `researcher_config.yaml` is OPTIONAL; defaults preserve v1.3.x behaviour (`preferred_languages: ["python", "R"]`, `field_practice_overrides_preference: true`).

---

## [1.3.4] — 22-turn stress-test fixes: synthesis audit aggregation + pending-citation block + sub-section regex + dashboard embed_figures (2026-06-04)

Patch driven by a 22-turn agent stress test against a multi-modal Alzheimer's progression project (10 analysis steps including WGCNA + Cox PH + cross-cohort validation). Three audit agents (PI cold review + RO-creator judge + improvement priorities) converged on the same gaps. v1.3.4 closes the P0/P1 set.

**Stats:** 110 protocols (all bumped to 1.3.4), 145 MCP tools, **481 tests pass** (+4 v1.3.4 regression). Preflight 14/14, ruff clean.

### Fixed — `audit_synthesis` is no longer structural-only

The 22-turn test exposed that v1.3.3's audit could pass a 5,529-word paper with 10 per-step "literature grounding deferred" warnings silently — it never opened any `step_summary.yaml`. v1.3.4:

* Aggregates `warnings:` from every `workspace/<step>/step_summary.yaml`.
* `recurring_blockers[]` surfaces signatures that recur across ≥3 steps OR match literature-deferred / pending-verification patterns.
* HARD BLOCKER on `pending verification` citations: `workspace/citations.md` scanned; any unverified count > 0 escalates the audit to `status='error'`. Override via `override_completeness_gate=true + override_rationale=...`.
* New report fields: `propagated_step_warnings`, `recurring_blockers`, `unverified_citations`, `citation_count_pandoc`, `citation_count_authoryear`.

### Fixed — `_section` regex no longer truncates at `###` / `####` sub-headers

`audit.py:134` IMRAD word-count regex was `(?=^##|\Z)` — `###` matched the terminator and clobbered all sub-section content from the parent count. v1.3.4 changes to `(?=^##\s|\Z)`. Turn 22 of the stress test had to demote `### N.M` sub-headers to bold so the audit would count properly; that workaround is no longer needed.

### Fixed — `_bullet_lines` falls back to sentence-split for prose / table Findings

When `## Findings` was prose-led or table-led (no `-`/`*`/`+` bullets), the v1.3.3 extractor returned `[]` and `step_summary.yaml.findings` was silently empty. Turn 8 (step 04 WGCNA) and turn 12 (step 06 hubs) both wrote table-led Findings — both ended up with empty findings in their sidecars, breaking the v1.3.3 "synthesis composes by deterministic merge" promise. v1.3.4 falls back to sentence-split on the prose body, strips markdown table rows.

### Fixed — `audit_synthesis` also counts author-year prose citations

v1.3.3 regex was `\[@key\]|\\cite{key}` only. A paper written in `(Mostafavi et al. 2018)` Markdown style got a misleading `citation_count: 0`. v1.3.4 adds an author-year pattern; report exposes BOTH `citation_count_pandoc` and `citation_count_authoryear`; `citation_count` is the sum.

### Added — `render_dashboard(embed_figures="auto" | "inline" | "relative")`

22-turn test produced a 5 MB `dashboard.html` (95% base64 image data). v1.3.4:

* `"auto"` (default): inline if ≤3 figures AND ≤1 MB total, else `"relative"`.
* `"relative"`: emit `<img src="../workspace/<step>/outputs/figures/<file>.png">` — HTML drops from ~5 MB to ~80 KB, git diffs stay readable, browsers cache figures across regenerations.
* `"inline"`: preserves the legacy base64 single-file behavior — right for `sys_export_share_archive` / email attachments.

Also: `figures_embedded` count now derived from the RENDERED HTML (counts `data:image/` + `<img src="...">`), not from the spec — under-reported by 90%+ on auto-derived dashboards.

### Fixed — STATE.md grammar (truncated "We test whether <q> and " fragment)

22-turn test's research question was compound ("Which gene co-expression modules...and which DEGs are cell-line-specific vs shared?"). The fallback hypothesis template lowercased + prefixed → "We test whether which gene...and " (mid-clause dangle). v1.3.4 detects compound questions (commas + "and"/"or", multiple "?"s, or length >160) and uses a quoted form: `Central question: "<original>"`. Simple questions still get the `"We test whether ..."` rewrite with trailing-conjunction stripping.

### Fixed — `tools.md` regex no longer extracts English stopwords as packages

22-turn test had `tools.md` containing `` `the` — third-party / domain package ``. v1.3.4:

* Tightened regex anchors at line-start (no leading whitespace) so import-like prose in docstrings doesn't match.
* Captured module name must be ≥3 chars.
* New `ENGLISH_STOPWORDS` filter on top of `STDLIB_SKIP`.
* When NO third-party imports are detected, writes an explicit `_(No third-party packages detected ...)_` note so the section marker is created — fixes the idempotency bug where stdlib-only steps wrote NO entry, then got skipped on every subsequent finalize. The 22-turn test had steps 02/06/08/09/10 missing despite being finalized.

### Validation

* preflight 14/14 · pytest 481 passed (+4 new regression tests) · ruff clean
* All 4 v1.3.4 regression tests cover: step-warning aggregation → BLOCKER; pending-verification BLOCKER; author-year citation counter; `###` sub-section word count preservation.

### Deferred to v1.4.0 (MAJOR, deprecation pass)

* Orphan tool sweep — 43 of 145 tools are never referenced from any protocol or shortcut. Includes the entire "grounded reasoning" cluster (`tool_thought_log`/`_trace`, `tool_grounding_register`, `tool_ground_from_context`, `tool_claim_verify`, `tool_lessons_record`/`_consult`, `tool_plan_step_grounded`) — 7 tools, zero protocol uptake. Removing requires MAJOR bump per maintainer rules.
* `_router_index.yaml` decomposition stress: only 51 unique tools referenced; protocol YAMLs collectively reference 111. The gap suggests the router itself under-uses the surface.

---

## [1.3.3] — Anti-one-shot enforcement + step_summary.yaml + synthesis quality gates + dashboard paper-as-interactive (2026-06-03)

The deepest fix in the 1.3.x cycle. AI agents tend to "complete" long
plans as fast as possible — context fills, the AI stops introspecting,
and the output is a sketch. The v1.3.2 e2e exposed this: a 10-step
analysis produced a 900-word paper that used 10 of 17 workspace
figures. v1.3.3 forces mandatory pauses + concrete revision options
+ real quality gates so the AI cannot one-shot through a quality output.

**Stats:** 110 protocols, **145 MCP tools** (+1: `tool_step_revision_options`).
**477 tests pass** (+4 v1.3.3 regression tests). Preflight 14/14. Ruff clean.

### Added — `tool_step_revision_options` (the anti-one-shot gate)

New tool the AI calls AFTER `tool_path_finalize`. Returns:
* `would_benefit_from_revision: bool` — composite heuristic
* `risk_signals: [...]` — e.g. "citations claimed but zero `tool_search_*` calls logged"
* `suggested_revisions: [...]` — specific fixes ("Findings is only 120 chars — should be ≥300 with explicit numbers + figure refs")
* `alternative_paths: [...]` — stratified / sensitivity / method-comparison branches the researcher could fork via `branch_of=<step>`
* `handoff_recommended: bool` — true when ≥5 steps have been finalized this conversation
* `n_finalized_steps_this_project: int`

The AI MUST present these VERBATIM to the researcher and WAIT for their choice (`proceed | revise | branch | handoff`). Refuses to auto-scaffold the next step unless `autonomy_level == 'autopilot'` AND `would_benefit_from_revision is False`.

### Added — `analysis_plan.present_to_researcher` mandatory pause step

New mandatory step in `guidance/analysis_plan` that runs IMMEDIATELY after `finalize_step`. Calls `tool_step_revision_options`, formats the output as a 4-choice question, and explicitly forbids auto-scaffolding the next step in the same turn. New ONE-SHOT GUARD: if the AI calls `sys_path_create` immediately after `tool_path_finalize` without calling `tool_step_revision_options` first, the routing log flags this as a protocol violation.

### Added — `step_summary.yaml` sidecar at finalize

Structured machine-readable mirror of `conclusions.md` the synthesis pipeline consumes deterministically (no NLP parsing). Fields: `headline`, `methods_block`, `plain_language_summary`, `findings: [...]`, `decision`, `limitations: [...]`, `references_to_ground: [...]`, `figures: [{name, path, caption_path, summary_path, audit}]`, `tables: [...]`, `reports: [...]`, `warnings: [...]`.

### Added — `synthesis_paper` multi-turn enforcement doctrine

The protocol description now enforces ONE section per researcher prompt (turn 1: outline → turn 2: methods → turn 3: results → … → turn 10: cover letter). The AI refuses to chain >1 section per turn. A real paper deserves the deliberative pace + the context window stays healthy.

### Added — quality-bar gates on `tool_audit_synthesis`

`audit_synthesis` now computes per-section word counts vs MIN_BAR (abstract 150 / introduction 300 / methods 400 / results 400 / discussion 300; total ≥1500) AND `figure_coverage_ratio = figures_used / figures_available_in_workspace` (target ≥0.8). Emits `gate_blockers: [...]` with specific revision instructions per gap. Escalates to `status='error'` (BLOCKER) ONLY when total ≥500 words — stub-shaped papers get the same gaps as warnings so the AI sees where to expand but isn't blocked on a sketch.

### Added — per-step retrospective at finalize (Anticipated reviewer questions)

`tool_path_finalize` auto-appends `## Anticipated reviewer questions` to conclusions.md (idempotent). Content-aware questions based on methods + limitations + figure/table counts (e.g. "On n=12, how reliable are dispersion estimates?"). Self-critique scaffold so the AI sees its weaknesses before synthesis.

### Added — dashboard.py paper-as-interactive rewrite

`_figure_block` now emits, per figure: clickable static image (lightbox via `<a target='_blank'>`), technical caption, **`.summary.md` plain-English sidecar in `<aside class='figsummary'>`**, and **interactive HTML companion in `<details><summary>↗ Open interactive companion</summary><iframe ...></iframe></details>`** when one exists. Plus CSS for the new blocks. The dashboard now actually implements what the v1.3.1 protocol described.

### Added — long-context handoff hint in `sys_boot`

`sys_boot` response now includes `handoff_recommended: bool` (true when ≥5 finalized steps) + a `handoff_hint` string the AI surfaces to the researcher. Prevents the "AI one-shots step 6, 7, 8 in lossy context" failure mode.

### Validation

* preflight 14/14 · pytest 477 passed · ruff clean
* 4 new regression tests: `test_step_revision_options_flags_placeholder_conclusions`, `test_step_revision_options_clean_step_passes`, `test_finalize_emits_step_summary_yaml`, `test_finalize_appends_anticipated_reviewer_questions`

---

## [1.3.2] — Multi-language env hardening + richer intake + comment-preserving config + exploratory hardening (2026-06-03)

Post-v1.3.1 patch focused on three explicit researcher asks +
exploratory hardening surfaced by the e2e test bed.

**Stats:** 110 protocols, 149 MCP tools. 473 tests pass.
Preflight 14/14, ruff clean.

### Added — multi-language environment hardening

* `_detect_languages_in_use` now reads BOTH `workspace/` scripts AND
  `inputs/raw_data/` file types. FASTQ/BAM/VCF → `domain_hint:bioinformatics`;
  H5AD/loom → `single_cell`; NIfTI/DICOM → `neuroimaging`; shp/geojson →
  `geospatial`; sav/sas7bdat/dta → `survey`; edf/bdf → `eeg`; mat →
  `matlab_interop`. Also detects Rust (`Cargo.toml`), Go (`go.mod`),
  Node (`package.json`).
* `sys_env_snapshot` returns a `domain_hints` field + writes a
  `environment/language_recommendations.md` listing the canonical
  package stack per detected hint (e.g. bioinformatics →
  Bioconductor/DESeq2/edgeR if R is present, pysam/biopython if
  Python-only).
* When ≥2 non-shell languages detected, auto-generates
  `environment/Dockerfile.suggested` (Python + R + Julia + Quarto
  base layers as needed). Researcher reviews and renames to
  `Dockerfile` when ready.

### Added — richer `docs/research_overview.md`

`tool_intake_autofill` now writes a multi-section overview instead
of just question + hypotheses:

* Project + domain header with "_Why this domain_" rationale
* Research question
* Background (auto-extracted snippet from `inputs/context/*.md`)
* Hypotheses (with explicit fallback prompt when none inferable)
* Input data inventory table (file path, size, row count for
  CSV/TSV)
* Planned analyses placeholder + back-links to existing numbered
  steps
* Literature-to-find checklist from extracted named-paper
  references — checkbox-style for trackable progress

### Added — comment-preserving `researcher_config.yaml` writer

`config.py` now uses `ruamel.yaml` (added to core deps) for
round-trip YAML. The rich inline help comments in `CONFIG_TEMPLATE`
survive every override write — previously every `cli.py init` /
wizard / `sys_config_set` call stripped them via PyYAML. Falls back
to PyYAML with a logged warning if `ruamel.yaml` isn't installed.

### Added — researcher_config consultation in session handoff

`sys_session_handoff` now prepends a "Researcher config (consult
before acting)" section to the handoff doc summarising autonomy /
quality_gate_policy / ambiguity_posture / model_profile /
shared_server / writing_preferences / output types / target venue /
researcher identity / API keys configured. A fresh AI session
reading the handoff doc sees these without a separate
`sys_config_get` call.

### Added — `analysis_plan.ground_methods` is now a HARD GATE

(Continued from v1.3.1 round 2; explicitly named here for the
release notes.) Replaced prose with 4-action sequence; anti-pattern
"We use X because it's standard" rejected; correct form names
paper + DOI + saved PDF + why.

### Added — anti-hallucination grounding warning at finalize

(Continued from v1.3.1 round 2.) `tool_path_finalize` scans
`workspace/logs/searches.log` and warns when `conclusions.md` cites
references but zero `tool_search_*` calls were ever logged.

### Hardened — exploratory fixes

* **`slugify`**: caps at 40 chars + explicit defence against
  `..` / `/` path-traversal sequences (in addition to the existing
  regex strip).
* **`_load_active_plan`**: auto-archives plans older than 7 days
  (with `status: in_progress`) into `.os_state/handoffs/` so a
  stale abandoned plan doesn't keep being surfaced as the
  "active next-action" by `sys_boot`.
* **`_update_workflow_mermaid`**: silently no-ops when `root` isn't
  a Research-OS project (no `.os_state/`). v1.3.1 confirmed the
  pollution-prevention pattern via raise-on-write in
  `create_numbered_experiment`; this generalises to every other
  writer.
* **`branch_of` validation**: confirmed `create_numbered_experiment`
  raises `ValueError` with a clear message when `branch_of` names
  a step that doesn't exist on disk (was already correct; verified
  + documented).

### Maintainer

* Added `TODO.md` (gitignored) for deferred work: project_ops folder
  refactor, `tool_pi_review`, `tool_synthesis_curate_figures`,
  `tool_protocol_freshness_check`, `methodology/small_n_studies`
  protocol, `tool_figure_html_smoke_test`, Bloom-filter author
  check, DOI/PMID extractor, `tool_step_initial_inspect`,
  decision-verb-shape audit gate, length-based stub check.

---

## [1.3.1] — PI-level e2e gap-closure: finalize completes the picture + grounding + aesthetics + paper PDF + dashboard-as-paper (2026-06-03)

### Round 2 — additional gap-closures the same day

After the round-1 fixes shipped, the researcher surfaced a deeper
set of gaps the same day. Round 2 closes the next layer:

**FIXED — workspace-pollution guard.** `_update_workflow_mermaid`
now refuses to write into ``root/workspace/`` unless ``root`` is a
valid Research-OS project (``.os_state/`` present). A v1.3.0
misconfigured caller had silently written
`workspace/workflow.mermaid` into the Research-OS source repo;
guard prevents this class of bug across every writer.

**ADDED — anti-hallucination grounding warning at finalize.**
`tool_path_finalize` now scans `workspace/logs/searches.log` and
warns when `conclusions.md` cites references but ZERO
`tool_search_*` calls have been logged for the project. The
citations may be coming from training memory rather than
verifiable lookups; the warning makes that visible at every step
finalize so the AI / researcher can run actual searches before
submission. Surfaces as a BLOCKER at pre-submission audit.

**STRENGTHENED — `analysis_plan` `ground_methods` is now a HARD
GATE.** Replaced "you SHOULD search literature" prose with explicit
4-action sequence:
  (1) surface candidate methods online (`tool_research_method` +
      parallel `tool_search_semantic_scholar` + `tool_search_pubmed`
      + `tool_search_web` "best <method> 2024 2025"),
  (2) ground each decision in a SPECIFIC paper saved into the
      step's literature folder via `tool_literature_search_and_save`,
  (3) compare findings to current literature (flag divergence
      from recent published numbers),
  (4) record the decision-with-citation chain via
      `mem_methods_append` + `mem_decision_log` + `mem_hypothesis_update`.
Anti-pattern explicitly named:
  "We use DESeq2 because it's standard" → ungrounded; rejected.
  "We use DESeq2 (Love, Huber, Anders 2014, doi:10.1186/...) because
   the n=8 design benefits from empirical-Bayes shrinkage..." → correct.

**ADDED — `figure_guidelines` publication-aesthetics block.**
Past the existing pitfall catalog: a `publication_aesthetics`
section spelling out the moves that lift figures from "default
ggplot output" to publication-grade:
  - pick a stylesheet (SciencePlots / theme_classic / latimes), patch
    rcParams once in a project-wide `viz_style.py`
  - pin a font stack (Inter / Helvetica Neue / Source Sans / Roboto
    / Liberation Sans → DejaVu Sans fallback)
  - set `figsize` from the destination (single-column = 3.5", two-
    column = 7.2", 16:9 slide = 13.3×7.5") BEFORE adjusting fonts
  - annotate the data, not the chart (inline callouts > caption-only)
  - color palettes beyond Okabe-Ito (`glasbey` via `colorcet` for
    >8 categories; `cmocean` for continuous; `TwoSlopeNorm` for
    diverging-with-emphasis)
  - iconography for categorical encodings (inline labels > legend)
Plus references the AI should consult online before unfamiliar chart
kinds: Wong 2011 (Okabe-Ito), Wilke 2019 (Fundamentals of Data Viz),
Tufte 2001, Cleveland & McGill 1984, Heer & Bostock 2010, Healy 2018,
Frank Harrell BBR.

**OVERHAULED — `synthesis_paper` `compile_pdf` step.** Was
optional; now DEFAULT for any serious draft. Decision tree maps
the venue/output to LaTeX (journal class files) vs Typst (modern
preprint / thesis / general manuscript) vs poster vs dashboard.
Typst conversion is explicitly supported with proper preamble,
inline figure embedding, and CSL bibliography style. paper.md is
the WORKING DRAFT; paper.pdf is the deliverable. Markdown alone
is not a publication artefact.

**OVERHAULED — `synthesis_dashboard` reframed as paper-as-interactive.**
Was a metrics-overview screenshot gallery. Now: the paper, told as
an interactive guided walk-through. Section order mirrors the paper
1:1 (TL;DR/abstract → intro → methods → findings → discussion →
limitations → reproducibility → references). Every figure ships
with BOTH its `.caption.md` AND its `.summary.md` inline (the
paper has only the caption; the dashboard adds the accessible
summary — that's what makes it "guided"). Findings ordered by
HYPOTHESIS, not by step number. Inline "Why?" expanders next to
methods sentences reveal the conclusions.md `## Methods (full
detail)` block + linked citation. Hover/lightbox opens the full
SVG. Visual coherence with the paper PDF (same font, palette,
spacing).

**VALIDATION (round 2):** preflight 14/14, pytest 473 passed
(round 1 already brought this up), ruff clean.

### Round 1 — initial gap-closures (earlier same day)

Patch release after a 10-step PI-level genomics e2e (Himes 2014
airway-DE replication with 6 cell lines × 2 conditions × 2 sequencing
batches; produced a 12-section paper.md + abstract.md + dashboard.html
+ 17 PNG/SVG figures + 1 interactive Plotly companion). Three parallel
sub-agents (PI-walks-in-cold audit / Research-OS-system judge /
improvement-priorities engineer) surfaced 21 + 18 + 12 specific gaps;
v1.3.1 closes the P0/P1 set.

**Stats:** 110 protocols, 149 MCP tools. **473 tests** pass (was 467;
+6 regressions for the new finalize behaviors + the named-paper false-
match guard). Preflight 14/14, ruff clean.

### Fixed — `tool_path_finalize` now actually completes the picture

Six finalize-time behaviors were either missing or wired to the wrong
target. The e2e exposed each. All six fixed:

* **Env auto-snapshot lands in the PROJECT-GLOBAL folder.**
  v1.3.0 added the auto-snapshot but called `env_snapshot(root)` with
  no `scope=`, which lands in the most-recent active step's folder
  rather than `environment/requirements.txt` at project root.
  v1.3.1 passes `scope='project'` so the project-global file actually
  populates with pinned versions (the e2e's was a comment-only template
  through all 10 finalizes).
* **`workspace/citations.md` scrapes `## References to ground` from
  every step's `conclusions.md`.** Previously the project bibliography
  only assembled from `inputs/literature_index.yaml` + per-step
  `*.meta.yaml` sidecars, which the AI typically doesn't write. Now the
  citations file actually fills in (the e2e's went from empty → 20+
  scoped entries across the 10 steps).
* **Per-step `literature/key_papers.md` auto-populates** from the same
  `## References to ground` section. Was a seed template the AI never
  filled in across all 10 e2e steps.
* **`mem_decision_log` mirrors the `## Decision` verb at finalize.**
  Across all 10 e2e steps the decision-log was empty even though
  every `conclusions.md` had a clean `## Decision\nPROCEED ...` block.
  Finalize now extracts the verb (PROCEED / BRANCH / DEAD-END / HOLD /
  ABANDON), validates it, and calls `log_decision`. Idempotent on the
  marker `step=<id>; verb=<V>`.
* **Step status flips `active → completed`.** Previously even a fully
  finalized step kept `status: active` in the ledger, so STATE.md
  showed `→` instead of `✓` until the next `sys_path_create` flipped
  it as a side effect. Finalize now updates the ledger directly and
  re-renders STATE.md.
* **`workspace/tools.md` filters stdlib noise** (pathlib, sys,
  warnings, json, re, …). v1.3.0's auto-import scan listed every
  imported module; v1.3.1 keeps only the third-party / domain stack
  (statsmodels, pandas, plotly, scipy, …).

### Fixed — `visualization/interactive_figure_design` was unroutable

The new v1.3.0 protocol was registered with `intent_class: visualize`
+ `sub_intent: interactive_figure` — neither exists in the router's
`hierarchy:` block, so semantic + trigger routing both silently
ignored it. Re-mapped to `intent_class: synthesize` +
`sub_intent: interactive` (the closest valid hierarchy node).

### Fixed — `audit_figure_quality` SVG label-overlap heuristic now sees matplotlib output

The v1.3.0 regex expected `<text x= y= >...</text>`. matplotlib's
`savefig(*.svg)` actually emits
`<g transform="translate(X Y)"><text>...</text></g>` — the v1.3.0
regex missed every matplotlib SVG. Added a second pattern that parses
the `transform="translate(...)"` wrapper, so the heuristic now fires
on the figures most AI agents actually produce.

### Fixed — `_extract_named_papers` false-matches

Patched in the round-3 work but solidified here with regression test
(`tests/tools/test_intake.py::test_extract_named_papers_excludes_months_and_journals`).
Stop-list now covers month abbreviations + names + days + common
journal-name first-words (Biology, Cell, Nature, Science, PNAS, Genet,
Genome, Methods, Genetics, Lancet, BMJ, JAMA, Cancer, Brain, Heart,
Kidney, Blood). The "Himes BE, et al PLOS ONE 2014" pattern still
matches; "Nov 2014" / "Biology 2014" do not.

### Fixed — AGENTS.md template no longer references `tool_figure_create`

`templates/AGENTS.md` rule #10 still recommended the removed v1.3.0
tool. Rewrote to point at `visualization/figure_guidelines` +
`tool_figure_palette` + `tool_audit_figure_full` +
`visualization/interactive_figure_design`.

### Added — `sys_path_create` inputSchema exposes the finalize-gate bypass

The v1.3.0 finalize gate (refuse step N+1 while step N is placeholder)
worked but was undiscoverable — the bypass field wasn't in the public
schema, so the AI couldn't ask for it. v1.3.1 adds
`allow_unfinalized_predecessor` + `override_rationale` + `from_step`
to the inputSchema. When the AI bypasses, the rationale is logged to
`workspace/logs/override_log.md` and surfaced at pre-submission audit.

### Added — `figure_guidelines` pitfalls catalog: 3 new entries from the e2e

* `legend_missing_shape_or_color_key` — when color + shape both encode
  variables but only one has a legend (e2e step 04 PCA).
* `invisible_legend_swatches` — white-fill `mpatches.Patch` with thin
  black edge becomes invisible at small sizes (e2e step 01).
* `bar_chart_with_zero_range_artifact` — three bars at 305/340/395
  look identical when y starts at 0; annotate values or crop axis
  (e2e step 06).

### Added — `interactive_figure_design` gains "ship offline-capable HTML" step

Plotly's default `include_plotlyjs=True` embeds the CDN URL. For
reviewers behind firewalls or archival readers, the file must use
`include_plotlyjs='inline'`. Protocol now lists the offline-capable
variant per library (Plotly / Bokeh / Altair).

### Changed — Docs counts refreshed

`docs/{TOOLS,PROTOCOLS,README,START,RESEARCHER_GUIDE}.md` +
`CONTRIBUTING.md` now say **149 MCP tools** + **110 protocols** to
match the actual count. (v1.3.0 docs claimed 143-145 tools + 88-100
protocols depending on file.)

### Changed — Every protocol YAML bumped to `version: 1.3.1`

Per maintainer guidance (any release that touches a finalize-time
behavior is a behavior change visible to every protocol). 110
protocols updated.

### Migration

None. All v1.3.0 callers continue to work. The new finalize behaviors
fire automatically; the new `sys_path_create` schema fields are
optional. If a v1.3.0 project's `workspace/citations.md` or per-step
`literature/key_papers.md` is stale, re-run
`tool_path_finalize` on each step to back-fill.

---

## [1.3.0] — Guidance-not-code doctrine + cross-project profile + step-gate enforcement (2026-06-03)

Three audit rounds against a graduate-level genomics e2e (Himes 2014
airway RNA-seq differential expression) + a parallel
"PI-walks-into-the-project-cold" sub-agent audit. Each round surfaced
architectural gaps that needed protocol + scaffold fixes rather than
patches.

**Stats:** 110 protocols (+1 new: `visualization/interactive_figure_design`).
144 MCP tools (-1: `tool_figure_create` removed, see Migration). 467
tests pass (was 453; +14 regressions across the rounds). Preflight 14/14,
ruff clean.

### Migration — `tool_figure_create` removed (guidance, not code)

The doctrine: **Research-OS is a guidance system, not a chart library.**
The AI writes its own matplotlib / ggplot2 / Altair / plotnine / d3 /
plotly script tailored to its dataset and field — guided by
`visualization/figure_guidelines`. Tools support that workflow with
audit + sidecar + palette utilities, not premade chart code.

* `tool_figure_create` is gone. Old callers receive a friendly
  deprecation message via the `_REMOVED_TOOLS` dispatcher entry that
  points at the protocol.
* The 30+ `_render_*` chart-kind dispatchers in
  `tools/actions/viz/figures.py` are gone with it. The module is now
  ~400 lines of palette + caption-sidecar + audit utilities.
* `tests/unit/test_viz_renderers.py` removed.
* `tool_figure_palette`, `tool_figure_caption_synthesise`, and
  `tool_audit_figure_full` are unchanged.
* All 21 protocol YAMLs that referenced `tool_figure_create` were
  updated to point at `visualization/figure_guidelines` instead.

### Added — `visualization/interactive_figure_design` protocol

Per-figure interactivity (hover, brush, zoom, lasso) as a companion to
the static PNG/SVG — NOT a dashboard, not a paper figure.
Library-by-data-type table (plotly / Altair / mpld3 / pyvis / igv.js /
cellxgene / glimma), interaction-design checklist, mandatory static
fallback. Router-indexed at `intent_class=visualize,
sub_intent=interactive_figure`.

### Added — `workspace/tools.md` (4th project-scope log)

Joins `methods.md` / `analysis.md` / `citations.md` as an append-only
project log. Tracks which Research-OS tools, 3rd-party packages, and
external services each step depended on — so a reviewer can audit
reproducibility without re-deriving the stack from scripts.
`tool_path_finalize` auto-appends a per-step section from
`conclusions.md` (Tools/Software/Methods) plus a fallback that scans
`scripts/` for top-level imports.

### Added — Project-root `README.md` from init

The GitHub / repo-browser-cold-open front page (distinct from
`GETTING_STARTED.md`, which targets the researcher actively driving
this project). Pre-fills the project name + research question +
domain when set via the wizard. Includes a "Reproducing the analysis"
block so a fresh clone can be re-run without inside knowledge.

### Added — Cross-project researcher profile

`~/.config/research-os/profile.yaml` (XDG-compliant) seeds the wizard
with the researcher's saved name / email / institution / ORCID +
api_keys + writing_preferences. The wizard's Step 6b asks once; future
projects auto-populate. Per-project `inputs/researcher_config.yaml`
always wins on conflict. Chmod 600 (api keys may be present).

### Added — Eager `inputs/{raw_data,literature,context}/` with seeded READMEs

`GETTING_STARTED.md` told researchers to drop files at these paths but
the directories were lazy and didn't exist yet (`cp foo.csv
inputs/raw_data/` failed without `mkdir -p`). Now eager + each ships a
one-paragraph README explaining what belongs there.

### Added — Step-finalization enforcement gate

`create_numbered_experiment` now refuses to scaffold step N+1 while
step N is still in placeholder form (README has stub markers,
conclusions.md is template). Audit surfaced the failure mode: the AI
moved from step 01 to step 02 without finalizing step 01, leaving
`workspace/analysis.md` missing the step 01 entry. The MCP
`sys_path_create` handler accepts
`allow_unfinalized_predecessor=true` (with rationale logged to
override_log) for legitimate data-plumbing-only steps.

### Added — `data/project_inputs` symlink on every step

Steps with `from_step` symlinked `data/input` to the previous step's
`data/output/`, which is empty when the upstream step wrote to
`outputs/` (figures/tables/reports) rather than `data/output/`.
Audit surfaced: step 02 inherited an empty data/input. Every step now
also gets a `data/project_inputs` symlink pointing back at the
project's `inputs/raw_data/` as a fallback.

### Added — `create_numbered_experiment` validates root

Refuses to scaffold if `root/.os_state/` is missing. Audit surfaced
a real bug: a misconfigured caller had silently created a step
folder in the Research-OS source repo. No more silent cwd pollution.

### Added — Online-research step in `guidance/project_startup`

Before declaring startup complete, the AI MUST run at least one
`tool_search_*` / `tool_research_method` pass on the research
question + named-paper references the PI brief surfaced. Search log
goes to `workspace/logs/search_log.md`. Closes the "AI relies on
pre-training memory instead of current literature" gap.

### Added — `intake_autofill` smarter extraction

* Natural-language hypothesis detection — when an explicit
  H1/H2/H3 list is absent, picks out sentences like "We
  hypothesise…", "X is associated with Y", "replicates the…",
  "differs across…".
* Named-paper extraction — PI brief references like "Himes 2014",
  "the GTEx airway atlas" surface as `named_paper_references` +
  concrete `next_actions` ("run `tool_literature_search_and_save
  query=…`").
* Fallback hypothesis from research_question when nothing else found
  ("We test whether …").

### Added — Multi-script chronological naming (`01a_`, `01b_`, `01c_`)

`guidance/analysis_plan.yaml` `write_atomic_scripts` step now
explicitly recommends letter-suffix naming for sub-tasks meant to
run in a fixed sequence — `01a_load_counts_v1.py` /
`01b_library_size_qc_v1.py` / `01c_pca_v1.py`. The descriptive-only
naming stays available for true DAGs with non-linear dependencies.

### Added — `figure_guidelines` pitfall catalog expansion

New pitfalls added from the e2e:

* `label_overlap_on_scatter_or_volcano` — use ggrepel / adjustText.
* `y_axis_clipped_by_extreme_values` — cap p-values at 1e-30, annotate.
* `filtered_but_labeled_points` — don't plot a label at coordinates
  the point doesn't truly occupy (e.g. IL6 + CCL2 below low-count
  filter showing at y=0 with full labels).
* `heatmap_columns_not_grouped_by_annotation` — sort columns BEFORE
  plotting; the eye can't see treatment blocks if conditions
  alternate.
* `heatmap_title_overlapping_annotation_strip` — use gridspec, not
  `add_patch` at negative y-coords.
* `font_size_too_small_at_paper_scale` — set figsize to final print
  slot.
* New `pick_library` step: research the right plotting stack for the
  data type FIRST (RNA-seq → ggplot2 + EnhancedVolcano; single-cell
  → scanpy; GWAS → qqman; not always matplotlib).

### Added — `audit_figure_quality` SVG label-overlap heuristic

When the figure is SVG, scans `<text>` elements for nominal
bounding-box collisions and surfaces ~N suspected overlaps as
warnings. PNG-only figures get a "ship the SVG too" warning so the
deeper audit can run.

### Added — `tool_path_finalize` auto-snapshots env

If a step produced outputs (figures/tables/reports) but
`environment/requirements.txt` is still the comment-only template,
finalize calls `sys_env_snapshot` automatically. Closes "env folder
is generic, not project-specific" gap from the e2e audit.

### Added — `plain_english_summary` detection from `conclusions.md`

Previously only checked `context/notes.md` — but the AI wrote the
summary inside `conclusions.md` (the natural place), so finalize
flagged it as missing. Now scans both, plus accepts several heading
variants ("Plain-language summary", "Plain-English summary", "TL;DR",
"Lay summary").

### Removed — `.os_state/state_ledger.yaml` duplicate

The yaml mirror of `state_ledger.json` was redundant — STATE.md at
project root + the JSON ledger cover both human + machine reading.
`.os_state/` is now 3 files instead of 4 (manifest.json,
state_ledger.json, state_ledger.lock; active_plan.json appears only
during live planning).

### Changed — Every protocol YAML bumped to `version: 1.3.0`

Per maintainer guidance (MINOR bump = bump every protocol). 108
protocols updated.

### Changed — Researcher-facing docs counts

`docs/{START,FAQ,README,AI_GUIDE,RESEARCHER_GUIDE}.md` updated:
"100 protocols" → "110 protocols", "six visualization protocols" →
"14 visualization protocols".

### Fixed

* `_has_user_inputs` no longer counts the seeded
  `inputs/{raw_data,literature,context}/README.md` as user content
  (would have re-triggered intake regen on cold init).
* `_REMOVED_TOOLS` dispatcher entry routes `tool_figure_create`
  callers to a clear migration message instead of "Unknown tool".
* `_router_index.yaml` decomposition entries that contained
  `tool_figure_create` were cleaned up (would otherwise emit
  "unknown tool 'an AI-authored plotting script'" preflight errors
  after the bulk sed).
* `_write_project_root_readme` f-string escaping fixed
  (`{figures,tables,reports}` was interpreted as a format spec).

### Validation — full graduate-level e2e analysis

After the structural changes below, an end-to-end research project
(Pygoscelis penguin bill morphometrics, n = 334) was driven through
Research-OS as the AI client would: 3 numbered steps (baseline EDA →
two-way ANOVA + Tukey + Kruskal-Wallis sensitivity → allometric
regression), each with its own `pipeline.yaml` + 2–4 atomic scripts +
4/2/2 publication-grade figures + 3/4/2 tables + 2/2/1 reports +
substantive `conclusions.md` (~120 lines each). The synthesis paper
weighs in at ~1,400 words. Every per-step finalize updated
`workspace/analysis.md`, `workspace/methods.md`, and
`workspace/citations.md` without manual intervention. The e2e run
surfaced six follow-on bugs (see below) — all fixed in this same
release with regression tests pinning each one.

### Added — `sys_env_snapshot` accepts a target scope

`sys_env_snapshot` previously only wrote into the most-recent active
numbered step (a hidden global), which made it impossible to snapshot
the project-wide environment, or a specific step that wasn't the
latest. v1.3.0 adds:

* `step_id="NN_slug"` — snapshot into `workspace/NN_slug/environment/`.
* `scope="project"` — snapshot into the project-global `environment/`
  folder (newly eager-scaffolded — see below).
* Omit both → legacy behavior (most-recent step, or project-global
  when no numbered steps exist yet).

### Added — `tool_path_finalize` now updates the project-scope logs

`finalize_path` was purely observational (rewrote per-step READMEs
from on-disk state). v1.3.0 extends it to refresh the project-scope
append-only logs the AI was supposed to be touching manually but
typically forgot:

* `workspace/analysis.md` ← step-finalized heading + headline from
  Findings + output counts + decision count (idempotent on the
  step-named marker).
* `workspace/methods.md` ← if `conclusions.md` has a `## Methods
  (full detail)` (or `## Methods`) section, mirrored under a
  step-tagged subsection.
* `workspace/citations.md` ← regenerated from project-level
  `inputs/literature_index.yaml` + every per-step
  `literature/.meta.yaml` sidecar.

`finalize_path` also returns a `warnings` list surfacing:
* stub `Findings` / `Decision` / `Plain-language summary` sections in
  `conclusions.md`,
* missing environment snapshot when the step produced outputs.

These are nudges, not blockers — the AI can override with a
`mem_decision_log` rationale if the omission was deliberate.

### Improved — init scaffolding (`research-os init`)

* **`CONTRIBUTORS.md` is no longer created at init.** The previous
  default produced an opaque audit file in every fresh project that
  confused new researchers and was outdated the moment they added an
  IDE. It's now opt-in — written on the first `research-os ide
  add|remove` (or explicit share action). Behavior in tests:
  `tests/unit/test_core.py::test_scaffold_creates_complete_workspace`
  now asserts it does NOT exist after a cold scaffold.
* **`environment/` is now eager + scaffolded.** Previously a LAZY_DIR
  (folder absent until something wrote into it). Researchers reported
  not knowing whether the project even had a reproducibility story.
  v1.3.0 ships:
  * `environment/requirements.txt` — pip stub with a header pointing
    at `sys_env_snapshot` and per-step alternatives.
  * `environment/README.md` — explains the global vs per-step split
    and the Dockerfile / conda / R / Julia hooks.

### Improved — `guidance/analysis_plan.yaml` doctrine

Two protocol steps were rewritten to match the new tool behaviors and
to make per-step file hygiene less optional:

* `snapshot_step_environment` — used to say "SKIP in the common case";
  now says "call every step that ran code". Variants spell out
  `step_id=` vs `scope="project"`. Reproducibility is treated as the
  default deal, not an opt-in.
* `finalize_step` — the description now lists everything `finalize_path`
  does, including the new project-scope log refresh + warning surface,
  so the AI knows the call is the canonical end-of-step ritual rather
  than just "rewrite some READMEs".

### Improved — visualization defaults (publication-grade)

Quick hits in `tools/actions/viz/figures.py`:
* **Chart-kind-aware gridlines.** Scatter / forest / dot_whisker /
  raincloud / slope / alluvial / consort_flow / funnel / calibration
  now render with NO gridlines (they competed with the marks). Bar /
  line / hist / box / violin / heatmap keep a faint horizontal grid
  to help the eye land on values.
* **Lighter sample-size annotation.** The boxed `n = ...` corner
  label became a plain light-grey text — same information, less
  visual weight.
* **Title padding.** `ax.set_title(..., pad=8)` so titles no longer
  collide with top spines or top-most tick labels.

### Fixed — six follow-on bugs surfaced by the e2e analysis

1. **`intake_autofill` misclassified the penguin dataset as
   "economics".** No `biology` / `ecology` domain existed in
   `DOMAIN_HINTS`. Added a `biology_ecology` bucket with the columns
   and keywords actual ecology / morphometric datasets carry
   (`species`, `sex`, `island`, `bill_*`, `body_mass_g`,
   `Pygoscelis`, `dimorphism`, `allometric`, etc.). Also dropped
   `year` from the `economics` columns since it false-positives every
   longitudinal study.
2. **`intake_autofill` overwrote researcher-supplied `--domain` /
   `--question`.** Init-time wizard input was being clobbered by
   weaker auto-inferences. v1.3.0 respects existing
   `state.domain` / `state.research_question` unless they're
   placeholders.
3. **`_propose_hypotheses` regex missed markdown bullets-with-bold.**
   Advisor notes commonly use `- **H1** — text` or
   `- **H2**: text` but the regex required a bare `H1: text`. New
   regex handles list markers, bold/italic emphasis, and `:`/`-`/`—`
   separators.
4. **`finalize_path` headline extraction was eating `**` opening
   markers.** `lstrip("-* ")` consumed the bullet's leading `**`,
   leaving the trailing `**` orphaned and surviving emphasis-strip.
   Replaced with a precise list-marker strip so the regex finds both
   ends of the bold pair. Side-fix: continuation lines under the
   first bullet are now joined (the headline used to truncate
   mid-sentence).
5. **`finalize_path` Outputs section listed sidecars as figures.**
   The figure inventory walked every file under `outputs/figures/`
   including `.caption.md`, `.summary.md`, and `.svg` companions —
   producing READMEs with "16 figures" when the step had 4 real
   PNGs. New `_figure_table_inventory` filters by extension and
   dedups the SVG companion when a PNG sibling exists.
6. **`create_numbered_experiment(from_step=X)` deep-copied X's
   whole step** (scripts, outputs, environment, everything) via
   `shutil.copytree`. The intent of `from_step` is "wire data/input
   from X's data/output"; the deep copy bloated workspaces, polluted
   per-step provenance, and broke `tool_path_finalize`'s artefact
   inventory. v1.3.0 strips it to symlink-only.

Also surfaced + auto-fixed by the new finalize doctrine: the
README's `## Input data` section was previously left as the
`*(list inputs used)*` stub. v1.3.0's
`_input_inventory_for_readme` populates it from `data/input/`
symlinks + `pipeline.yaml`-referenced raw inputs.

### Added — regression tests (+11 = 5 initial + 6 e2e)

Initial pass:
* `tests/tools/test_iteration.py`
  * `test_finalize_appends_step_entry_to_analysis_md`
  * `test_finalize_mirrors_methods_section_into_methods_md`
  * `test_finalize_warns_on_stub_findings`
  * `test_env_snapshot_step_id_param`
  * `test_env_snapshot_project_scope`
* `tests/unit/test_core.py::test_scaffold_creates_complete_workspace`
  updated: asserts `environment/` IS scaffolded, `CONTRIBUTORS.md`
  is NOT.

E2e pass (one per bug above):
* `tests/tools/test_iteration.py`
  * `test_finalize_headline_strips_markdown_bold`
  * `test_finalize_input_data_section_backfilled`
  * `test_finalize_figure_inventory_filters_sidecars`
  * `test_from_step_does_not_copy_outputs`
  * `test_intake_biology_domain_recognised`
  * `test_intake_extracts_markdown_hypotheses`

### Bumped

* `research-os` package: 1.2.2 → 1.3.0
* `CITATION.cff` version + date
* Embeddings rebuilt against the updated protocol bodies.

### Deferred (logged for v1.4.0)

* **Router slim refactor.** `_router_index.yaml` still holds the
  centralized trigger + decomposition + hierarchy + shortcut
  metadata. Audit confirmed it's correctly used server-side
  (so it does NOT cost AI tokens directly), but it has grown large
  (~76 KB) and per-protocol metadata would be cleaner in each
  protocol's own YAML frontmatter, with a build-time aggregation
  step. Scoped for v1.4.0 to avoid churn during a patch cycle.

### Test + quality status

```
preflight  : 14 / 14 ✓
pytest     : 464 / 464 ✓  (was 453 in v1.2.2)
ruff       : clean ✓
```

---

## [1.2.2] — Session-pattern phrasing + output coverage + routing patches (2026-06-03)

A bug-fix audit. **No protocol or tool removals.** 453 tests pass
(was 447; +6 regression tests for the fixes below). Same 109
protocols + 145 MCP tools.

### Fixed — session-pattern phrasing (the headline bug)

Docs and templates described the session sequence as `1. sys_boot →
2. (await researcher's message) → 3. tool_route`, suggesting the AI
fires `sys_boot` *before* a message arrives. An AI client cannot
call any tool until a researcher message triggers its turn — the
ordering as written was logically impossible. Rewritten throughout
to say: every turn is triggered by a researcher message, and on the
first turn the AI fires `sys_boot` as its 1st MCP call and
`tool_route(prompt=their verbatim message)` as its 2nd, back-to-back.

Files corrected:
* `docs/AI_GUIDE.md`, `docs/RESEARCHER_GUIDE.md`, `docs/PROTOCOLS.md`
* `templates/AGENTS.md`, `templates/CLAUDE.md`,
  `templates/.windsurfrules`, `templates/.continuerules`,
  `templates/.claude/rules/research-os.md`,
  `templates/.antigravity/rules/research-os.md`,
  `templates/.cursor/rules/research-os.mdc`
* `src/research_os/protocols/guidance/session_boot.yaml` — removed
  the contradictory `await_first_message` step; renamed the
  remaining flow so `boot` is explicitly "your first MCP call AFTER
  the researcher's message arrives" and `route_first_message` is the
  second call.
* `src/research_os/server.py` — `sys_help`'s `session_start` text +
  `routing` decision-tree + the `sys_help` tool description.

### Fixed — routing gaps surfaced by stress-testing

Stress-tested the router with 10 researcher personas (terse PI,
chatty grad, hesitant beginner, jargon-heavy senior, vague /
cross-disciplinary, kitchen-sink ambitious, pivot mid-session,
collaboration / handoff, recovery, edge / adversarial). Findings
fixed:

* **`baseline EDA` didn't route.** `_router_index.yaml` listed
  `"exploratory data analysis"` and `"do an eda"` as triggers for
  `guidance/analysis_plan` but not the natural-voice variants
  documented in `RESEARCHER_GUIDE.md` Section 4.2 as the canonical
  first-analysis prompt. Added `baseline eda`, `do a baseline`,
  `baseline analysis`, `eda on my`, `eda pass`, `first analysis`,
  `first experiment`.
* **"I just dropped a paper" had no shortcut.** Added a
  `context_intake` entry to `shortcut_intents` with the natural
  phrasings researchers actually use ("integrate this paper", "pi
  sent me a paper", "new paper in literature", …) → `tool_context_intake`.
* **Punctuation broke shortcut matching.** `_match_shortcut` did
  exact space-bounded substring matching, so "the workspace looks
  broken, fix it" didn't match the `broken` trigger because of the
  trailing comma. `route_request` now strips `,.;:!?` from the
  prompt before normalising — sub-string triggers match across
  punctuation now.
* **`workspace_repair` + `step_iterate` shortcuts gained natural
  variants** (`workspace looks broken`, `repair the workspace`,
  `recolor figure`, `tighten the cutoff`, `iterate on figure`, …).
* **Semantic path mis-handled complex multi-step prompts.** When the
  semantic router picked a narrow leaf protocol (e.g.
  `writing/writing_methods`) for a prompt the heuristic flagged
  complex, it would set `complexity="high"` without persisting an
  `active_plan` (because the leaf has no decomposition). Fixed in
  two ways:
  * If a stronger top-3 trigger-router candidate has its own
    decomposition, the semantic path defers to it — multi-protocol
    prompts now reach `guidance/analysis_plan` (or similar parent
    with a real plan) as before.
  * Otherwise the response keeps the semantic primary but downgrades
    `complexity` to `low` so the response shape is internally
    consistent (no plan promised when none was persisted).
* Bumped router index `version: 6 → 7` and rebuilt embeddings
  (`_embeddings.npz`, dim=384, 109 protocols + 145 tools).

### Improved — analysis-step doctrine (length + when to split + outputs)

`guidance/analysis_plan.yaml`:
* New **"STEPS CAN GROW"** note in `scope_step`: a step can be long
  when the researcher wants depth on one coherent goal — there is no
  artificial cap.
* New **"WHEN TO SUGGEST A NEW STEP"** block in `create_step_folder`
  with operational heuristics (covering ≥2 unrelated hypotheses,
  scope drift past the ≤2-sentence charter, estimator-family change,
  sub-population restriction added mid-stream, hard-to-caption with
  ONE focal figure) plus AUTONOMY-aware behaviour: surface to the
  researcher in supervised mode, call `tool_branch_recommendation`
  in autopilot. **Never force a new step** — long focused steps are
  preferable to step-fragmentation.
* **Output coverage** rewritten in `write_atomic_scripts`. Reports +
  tables + figures are now equal first-class outputs (was: reports
  + figures required, tables advisory). Each script defaults to
  emitting all three unless the step is genuinely non-numeric.

`visualization/figure_guidelines.yaml`:
* New top-level section `figure_family_when_step_has_a_model`. For
  any step that fits a statistical or ML model, generate the
  publication-quality FAMILY (diagnostic + summary + comparison) by
  default — not just the single focal chart. Domain-specific
  recommendations baked in (Cox → KM + Schoenfeld + cumulative
  hazard; Bayesian → trace + posterior + posterior predictive; ML
  classifier → ROC + PR + calibration + confusion; meta-analysis →
  forest + funnel + L'Abbé; etc.). Skip only when the researcher
  explicitly asks for "just the headline figure".
* Added pointers to the v1.2.1 deep-figure specialist protocols
  (`uncertainty_visualization`, `distribution_comparison`,
  `network_visualization`, `geospatial_visualization`,
  `animation_design`, `interactive_dashboard_design`,
  `showcase_visualization`) so the AI reaches for them automatically
  when the focal chart is non-trivial.

### Fixed — audit gap on numeric findings without a table

`src/research_os/tools/actions/audit/audit.py` →
`_step_completeness` now emits a non-blocking WARNING when a step
has a figure + numeric findings (≥2 numeric / statistical signals
in `## Findings`) but no CSV / TSV / parquet in `outputs/tables/`.
Reviewers and `tool_synthesize` expect a machine-readable companion
to every chart (coefficient table for a model, metric matrix for a
comparison). Threshold is soft — qualitative steps with no numeric
content are exempt automatically.

### Added — regression tests (+6)

* `tests/tools/test_router.py`
  * `test_route_punctuation_does_not_block_shortcut`
  * `test_route_baseline_eda_prompt_resolves`
  * `test_route_context_intake_shortcut`
  * `test_semantic_leaf_no_decomposition_downgrades_complexity`
* `tests/tools/test_iteration.py`
  * `test_step_completeness_warns_on_numeric_findings_without_table`
  * `test_step_completeness_quiet_when_table_exists`

### Bumped

* `research-os` package: 1.2.1 → 1.2.2
* `_router_index.yaml`: 6 → 7
* `CITATION.cff` version + date
* Embeddings rebuilt against the updated index + protocol bodies.

### Test + quality status

```
preflight  : 14 / 14 ✓
pytest     : 453 / 453 ✓  (was 447 in v1.2.1)
ruff       : clean ✓
```

---

## [1.2.1] — Showcase-tier visualization + tool / MCP integration + 100% routing (2026-06-02)

Patch release bundling everything in the never-tagged v1.2.0 work
plus a substantial follow-up tranche. **Supersedes v1.2.0** (never
published to PyPI). **No breaking changes** relative to v1.1.1.

**Stats:** **109 protocols** (was 88 at v1.1.1) · **145 MCP tools** ·
**438 tests passing** · **preflight 14/14** · **100% routing top-1**
on the 74-prompt canonical benchmark · **98.5% combined** on the
134-prompt fixture (canonical + stress paraphrases + viz prompts).

### Added — 4 novel protocols for top-tier work

* **`visualization/interactive_dashboard_design`** — next tier beyond
  the offline-HTML `synthesis_dashboard`. Audience / deployment /
  device sizing → stack picker (Observable Framework, Streamlit,
  Shiny, Dash, Panel, Quarto+shinylive, React+D3/Vega-Lite,
  kepler.gl, deck.gl) → interactive vocabulary (filter, brush-and-
  link, drill-down, parameterised view, temporal scrub) → versioned
  data layer → polish pass → reproducible deploy + cite-able URL.
  Quality bar: Tableau-tier is the floor, not the ceiling.

* **`visualization/showcase_visualization`** — for HCI / VIS / data-
  art / journal-cover / journalism-grade work where the visual IS
  the contribution. Layered read (3-second / 30-second / 3-minute
  test), chart-form picker with precedent citations, top-tier
  stack defaults (D3, Three.js + react-three-fiber, Observable +
  Plot, Vega-Lite, Pixi.js, Lottie / Rive), typography + palette
  pass, external design review, archival packaging at 3 sizes.
  Quality bar: Distill.pub article, NYT graphics, Pudding feature.

* **`methodology/external_tool_setup`** — guides researchers through
  installing top-tier external stacks (Node + npm for Observable /
  D3, Quarto, Docker, R + tidyverse, Julia, system libraries for
  geospatial, ffmpeg, LaTeX, hosted-service CLIs). Per-OS install
  commands paired with verification commands. Auto-install is OFF
  by default; the protocol proposes a setup script the researcher
  reviews + runs.

* **`methodology/mcp_ecosystem_integration`** — compose other MCP
  servers (Postgres, BigQuery, Slack, GitHub, Notion, Figma, Linear,
  Brave Search, Tavily, filesystem) alongside Research OS in the
  same IDE session. Vetting (provenance / license / auth model /
  data egress / maintenance), tool-name collision check, install +
  IDE config wiring, smoke test, README documentation. Research OS
  never installs other servers — produces the plan the researcher
  executes.

### Added — 5 new visualization protocols (originally v1.2.0)

* **`visualization/network_visualization`** — DAGs, citation
  networks, knowledge graphs. Layout algorithm picker, visual
  encoding budget, hairball detector, reproducible coords. Now
  routes upward to interactive_dashboard_design /
  showcase_visualization for next-tier output.
* **`visualization/geospatial_visualization`** — choropleth, points,
  raster, flow. Equal-area projection enforcement, classification
  break pre-specification, top-tier interactive stack (pydeck /
  deck.gl / kepler.gl / Mapbox GL) listed alongside the static
  baseline.
* **`visualization/animation_design`** — time-series / model
  behaviour / talks. Static-fallback mandatory; small-multiples
  vs animation justification; top-tier web stack (D3 transitions,
  Three.js, Lottie, Vega-Lite signals) for showcase animations.
* **`visualization/uncertainty_visualization`** — intervals, fans,
  ensembles, posteriors, calibration. Now references Vega-Lite,
  Observable Plot, bokeh / holoviews for interactive uncertainty
  exploration alongside matplotlib + arviz.
* **`visualization/distribution_comparison`** — raincloud, halfeye,
  ridgeline, beeswarm — beyond bar + error bar. Interactive
  options (Vega-Lite, Observable Plot, bokeh with linked
  brushing) added.

### Added — 12 high-impact methodology + synthesis protocols (originally v1.2.0)

Pre-data-collection qualitative + survey:
* **`methodology/interview_guide_design`** — paradigm selection,
  topic mapping, sensitive-topic ordering, pilot revision triggers,
  IRB alignment.
* **`methodology/coding_scheme_development`** — inductive / deductive
  / hybrid, per-code definition + inclusion / exclusion / canonical
  example, calibration rounds, freeze + amendment workflow.
* **`methodology/inter_rater_reliability`** — statistic choice
  (Cohen's κ / Fleiss' κ / Krippendorff's α / ICC / weighted κ),
  pre-specified threshold + field justification, remediation.
* **`methodology/survey_design`** — instrument review, construct
  definition, cognitive interviewing, pilot for psychometric
  staging, translation.

Statistical reasoning gaps:
* **`methodology/multiple_comparisons`** — family enumeration, FWER
  vs FDR, correction method with dependence-structure rationale.
* **`methodology/bootstrapping_design`** — resampling-scheme picker,
  interval-method picker (percentile / basic / studentised / BCa /
  ABC), B with MC-error sizing.
* **`methodology/uncertainty_quantification`** — calibrated
  predictive uncertainty (conformal / temperature / quantile /
  deep ensemble / MC dropout / Bayesian NN); reliability +
  sharpness + proper scoring rules.

Applied ML + safety + grants:
* **`methodology/fairness_audit`** — group / intersectional fairness
  audit; decision-context characterisation, criterion choice with
  impossibility trade-offs, mitigation, model card, monitoring.
* **`methodology/data_management_plan`** — NIH DMSP / NSF / Wellcome
  / ERC compliance with FAIR alignment.

Pre-submission + venue:
* **`synthesis/journal_selection`** — comparison across scope /
  evidence / format / timeline / cost / open-science fit; legitimacy
  vetting (predatory checks).
* **`synthesis/manuscript_outline`** — outline + storyboard before
  drafting; figures-first narrative; load-bearing-claims audit.
* **`synthesis/defense_prep`** — dissertation defense / job talk Q&A
  prep; weak-claim audit; question bank across framing / method /
  evidence / limitations / reproducibility / big-picture.

### Headline: semantic protocol + tool routing (originally v1.2.0)

`tool_route` is now a **hybrid semantic + trigger router**, hitting
**100% top-1 accuracy** on the 74-prompt canonical benchmark and
**98.5%** across 134 prompts (canonical + paraphrase stress + viz).

1. **Local embedding search** — BAAI/bge-small-en-v1.5 via
   `fastembed` (ONNX, no network, no LLM API keys, optional
   `[semantic]` extra ~150 MiB). Each protocol embedded once at
   build time; ships in `protocols/_embeddings.npz` (347 KiB).
   At request time we embed only the prompt and cosine-rank against
   the in-memory matrix.
2. **Length-weighted trigger boost with force-include** — exact-
   phrase matches on a protocol's triggers add a per-protocol
   boost sized by the LONGEST matched trigger. Triggered protocols
   are force-included in the candidate pool even when their
   pre-boost cosine falls outside the semantic top-N (fixed a
   silent bug where the most deterministic phrases could be
   missed).
3. **Parent-intent tiebreak** — when top-1 and top-2 share their
   parent `intent_class`, picking either is acceptable so top-1
   wins instead of triggering `ask_user`. Ambiguity is reserved
   for cross-intent cases.
4. **Conditional narrow-spread + capped triggers in embedding doc** —
   narrow-spread suppression is OFF when top-1 already scores high
   (we found a real topic, just adjacent topics share vocabulary).
   Build-time doc composition caps triggers per protocol so
   richly-triggered protocols don't dominate.
5. **Trigger-router fallback** — if `fastembed` isn't installed OR
   semantic confidence is low / none, the original hierarchical
   trigger-substring router serves the request. Nothing breaks
   for users without the `[semantic]` extra.

The AI gets ranked candidates with `method` (`"semantic" | "trigger"`)
and `confidence` (`"high" | "medium" | "low" | "none"`) every turn.

#### New MCP tools

* **`tool_semantic_route(prompt, top_k)`** — direct semantic search
  over protocols. Returns ranked candidates with cosine scores +
  the confidence verdict. Inspect alternatives without taking
  `tool_route`'s primary pick.
* **`sys_semantic_tool_search(query, top_k)`** — semantic search
  over the 145 tool definitions. Find tools by what they DO
  ("compute kappa for inter-rater agreement on transcript codes" →
  returns the matching tool list) when `sys_active_tools` is too
  narrow.

#### Token-usage win

Per turn, the semantic router saves an estimated **~20–30% of routing-
related tokens** vs the trigger-only path — driven by fewer wrong-
protocol loads (~250–290 tok saved per turn) and fewer ambiguity
roundtrips (~400–600 tok per saved clarify-and-re-route). The
`tool_route` reply itself is ~120 tok bigger (adds ranked candidates
+ method + confidence) but is net-positive because the AI almost
never picks the wrong protocol and re-loads.

### Changed — AI is now formally away from the router index

The router index `_router_index.yaml` (~1,700 lines) is now declared
**maintainer-only**:

* Header comment marks it private implementation detail; AI clients
  route through `tool_route` which reads it server-side.
* `AGENTS.md` adds an explicit "Never load `_router_index.yaml`
  directly" rule.
* `sys_protocol_list` description deprioritised: now says "prefer
  `tool_route` / `tool_semantic_route` — semantic routing scales as
  the catalog grows." The AI is steered away from raw catalog
  dumping toward semantic retrieval — important now that the
  catalog crosses 100 protocols.

### Changed — researcher_config simplification

* **Removed**: `model_tuning` block (five knobs that duplicated
  `model_profile`); `research_question` / `domain` / `hypotheses`
  top-level fields (AI-inferred; now in `inputs/intake.md` +
  `docs/research_overview.md` + `.os_state/state.json`);
  `researcher.field` / `researcher.expertise_level` / 
  `research_goal.reporting_standard` (all AI-inferred).
* **Reordered** to lead with what a researcher actually fills:
  `researcher` (name / institution / orcid / email) →
  `project_name` → `research_goal` → `interaction` →
  `model_profile` → `writing_preferences` → `runtime` →
  `api_keys`.
* `tool_intake_autofill` now reports `state_fields_updated`
  (was `config_fields_updated`).
* `regenerate_intake` sources domain / question / hypotheses from
  state (override > state > placeholder), not config.

### Improved — per-IDE + cross-model

* **Fixed BLOCKING Cursor rules bug**: `.cursor/rules/research-os.mdc`
  documented the obsolete `sys_config_get + sys_state_get +
  sys_protocol_next` bootstrap. Now uses canonical
  `sys_boot + tool_route + tool_plan_turn`.
* Per-model-tier guidance in `model_profile` comments with named
  classes (Haiku 4.5, Sonnet 4.5/4.6, Opus 4.x, GPT-4o-mini /
  4o / 5, Gemini Flash / Pro / 3, Llama 3.3 / 4) mapped to small
  / medium / large profiles.
* Wizard model-tier prompt — `research-os init` asks which AI model
  class is in use and writes `model_profile` accordingly.

### Improved — doctrine sweep (partial)

* `methodology/cox_ph_diagnostics` (`1.1.0 → 1.2.0`) — removed
  `editorial_voice.mode: prescription`, hardcoded `p<0.05`,
  library-specific function calls, canned 4-strategy menu.
* `methodology/bayesian_analysis` (`1.1.0 → 1.2.0`) — replaced
  algorithm-default and hardcoded MCMC thresholds with field-
  convention pointers + Vehtari et al. (2021) citation.

### Internal

* New `src/research_os/tools/actions/semantic.py` (~280 lines) —
  runtime semantic router with force-include trigger boost +
  parent-intent tiebreak + conditional narrow-spread + length-
  weighted trigger boost.
* New `scripts/build_embeddings.py` — deterministic source-hash;
  `--check` mode for stale detection.
* New preflight gate: `check_embeddings_fresh`.
* `numpy >= 1.23` is core; `fastembed >= 0.4` is the `[semantic]`
  extra.
* Router index version 3 → 6 (12 new sub-intents, 21 new
  protocol entries, header rewritten as maintainer-only).
* 109 protocols + 145 tools fully indexed in semantic embeddings.

### Migration

None required.

* **Without `[semantic]`** — `tool_route` uses the hierarchical
  trigger router exactly as before. The new tools return
  `status: "unavailable"` with an install hint.
* **With `[semantic]`** — `tool_route` automatically picks the
  semantic path on confident prompts and falls back to triggers
  otherwise. AI clients see a superset of the previous response
  shape (adds `method` + `confidence` + ranked candidates).
* Existing `researcher_config.yaml` files keep working — the
  removed fields are silently ignored.

### Stats

* **88 → 109 protocols** (+21 net new)
* **143 → 145 tools** (+2 semantic; nothing removed)
* **Preflight: 13 → 14 gates** (+ embedding freshness)
* **Tests: ~418 → 438 passing**
* **Router index version: 3 → 6**
* **Embedding bundle: 347 KiB** (BGE-small-en-v1.5; 384-dim
  float32; pre-built for 109 protocols + 145 tools)
* **Routing accuracy: 100% top-1 / 100% top-3** on the 74-prompt
  canonical benchmark; **98.5% combined** on the 134-prompt
  paraphrase + jargon + viz fixture.

---

## [1.2.0] — Never tagged

Its work landed in [1.2.1] above (consolidated and extended).

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
