# Research-OS v1.9.3 — Detailed changelog

Released: 2026-06-05
Classification: **MINOR** (new args on existing tool, schema-key migration, new preflight check)

v1.9.3 is the v1.9.2 audit-followup release: 33 of the 35 audit
findings scheduled for this window resolved, 10 deferred to v1.9.4 or
v1.11.0 per the audit's own triage table. The release closes the
4 CRITICAL findings (config-path bug + override-discussion-coverage
wiring + step-completeness humanities exception + figure-blocker
audit-trail). No new tools added. No public-API tool removed.

Release gates:
- preflight: 22/22 (one new check: `Router index mtime tracks protocols`)
- pytest: 896 passed (up from 872 baseline; +24 v1.9.3 tests)
- ruff: clean across src/ tests/ scripts/
- 114 protocols / 212 tools / 5 packs on version `1.9.3`

---

## Bugs fixed

### Config-path + tier subsystem (the v1.5.1 silent-failure root cause)

- **AUDIT-v1.9.2-001** — Three readers (`resolve_gate_strictness`,
  `project_tier_strictness`, `_read_model_profile`) now consult
  `inputs/researcher_config.yaml` with a root-level fallback for
  legacy projects. Affects
  `src/research_os/tools/actions/state/rigor_signals.py`,
  `state/quick_mode.py`, `state/reliability.py`. The tests that
  codified the bug (`tests/tools/test_v1_5_1.py`,
  `tests/unit/test_v151.py`) were rewritten to use the canonical
  `inputs/` path.
- **AUDIT-v1.9.2-011** — `resolve_gate_strictness` now maps
  `project_tier` (throwaway / sketch / production) to gate strictness
  (light / normal / strict) when explicit `gate_strictness` is unset,
  with `source=project_tier` surfaced in the result.
- **AUDIT-v1.9.2-071** — Widened: `project_tier=throwaway|sketch`
  takes precedence over `gate_strictness=auto`. `production+auto`
  still defers to rigor scan.

### Override wiring + audit trail

- **AUDIT-v1.9.2-002** — `tool_discussion_coverage_audit` `inputSchema`
  now declares `override_discussion_coverage` + `override_rationale`;
  handler enforces `quality_gate_policy`, logs via `log_override`,
  marks `override_applied` on the result. Mirrors
  `tool_audit_dashboard_content`. (Files: `server.py`,
  `synthesis/discussion_from_verdicts.py`.)
- **AUDIT-v1.9.2-018** — `_handle_tool_audit_synthesis` appends a
  `log_override` entry (`gate=audit_synthesis_no_pdfs`) whenever
  `audit_synthesis` reflects `override_no_pdfs=True` in the report.
  `pre_submission_checklist` can now surface this bypass.

### Humanities flow (figure-mandatory wall)

- **AUDIT-v1.9.2-003** — `step_completeness` audit accepts humanities
  markdown artefacts. New `_is_humanities_project` detects via config
  (domain/pack/packs keys with legacy root-level fallback) OR via
  workspace markers (transcriptions/edition/apparatus/humanities
  subdirs). `_collect_humanities_artefacts` accepts `apparatus.md`,
  `transcriptions/`, `citation_chains.md`, `close_reading.md` as
  focal artefacts. (File: `audit/audit.py`. Tests:
  `tests/unit/test_v193_humanities_completeness.py`.)
- **AUDIT-v1.9.2-027** — `hermeneutic_method` `on_failure` rewritten:
  no longer references nonexistent `intellectual_history` or
  `critical_theory_survey`; now routes to `literature/literature_search`.
- **AUDIT-v1.9.2-067** — `hermeneutic_method` `quality_bar` converted
  from list to dict with 6 named keys (matches `close_reading.yaml`
  convention; `dict.items()` readers no longer `TypeError`).

### Adapter / detector accuracy

- **AUDIT-v1.9.2-012** — REDCap adapter `_classify_csv` now accepts a
  CSV with `record_id` + sibling dictionary, or with `*_complete`
  sentinel / REDCap-stamped columns. Cross-sectional 12-row exports
  detect cleanly; longitudinal regression intact; bare CSVs with
  `record_id` alone still rejected. Tests:
  `tests/unit/test_v193_redcap_cross_sectional.py`.
- **AUDIT-v1.9.2-013** — Qualitative detector picks up `.txt` / `.md`
  transcripts at ≥3 speaker turns (was ≥5). The exact 12-participant
  short-interview fixture from lens-03 now scores confidence 1.0
  (was 0.1). Tests: `tests/unit/test_v193_qualitative_detector.py`.

### Routing accuracy

- **AUDIT-v1.9.2-015** — `route_request` honours `state_hint` as a
  tie-breaker. When `state_hint['current_phase']` matches a
  protocol's `intent_class`, that entry gets `+1` bias (does not
  flip clear winners). Tests:
  `tests/unit/test_v193_route_state_hint.py`.
- **AUDIT-v1.9.2-028** — Router gains explicit DESeq2 / DE / scRNA-seq
  triggers under `guidance/analysis_plan`: `DESeq2`, `deseq2`,
  `differential expression`, `DEG`, `DE analysis`, `single-cell DE`,
  `scRNA-seq QC`, `single-cell clustering`,
  `library size normalization`. Stops `bayesian_analysis` from
  miscarrying biology-classic phrasings.
- **AUDIT-v1.9.2-029** — `synthesis_paper` decomposition appends
  `tool_paper_compile_typst` (conditional on
  `writing_preferences.pdf_compile_engine == typst`), so a small-model
  agent walking `active_plan` reaches the PDF deliverable instead of
  stopping at markdown.

### Cycle breakage

- **AUDIT-v1.9.2-030** — Three 2-cycles broken via `next_protocol: null`
  on back-edges, with inline comments explaining the cycle break.
  Forward edges intact, re-entry via dispatcher. Affected:
  `mcp_ecosystem_integration` → `external_tool_setup`;
  `fairness_audit` → `uncertainty_quantification`;
  `inter_rater_reliability` → `coding_scheme_development`.

### Pack stress fixtures

- **AUDIT-v1.9.2-035** — `stress_runner.run_stress` now runs the
  matching pack's domain detector and surfaces a mismatch /
  low-confidence note when `ReferenceProject.expected_pack` disagrees
  with detection (observability-only; doesn't fail the run). Tests:
  `tests/unit/test_v193_expected_pack_validation.py`.
- **AUDIT-v1.9.2-036** — `slurm_snakemake` + `redcap_longitudinal`
  canned_responses rewritten against current step IDs (orphan IDs
  replaced with real `guidance/project_startup` +
  `methodology/exploratory_data_analysis` +
  `audit/audit_and_validation` step IDs).

### Tool-ref cleanup in protocols

- **AUDIT-v1.9.2-004** — Humanities pack tool refs rewritten: 8
  nonexistent tool calls
  (`tool_dh_topic_model`, `tool_dh_stylometry`, `tool_dh_network`,
  `tool_humanities_close_reading`, `tool_viz_dh`,
  `tool_humanities_collate`, `tool_humanities_apparatus`,
  `tool_humanities_apparatus_lint`) replaced with manual prose or
  `tool_python_exec` instructions. No new tool added.
- **AUDIT-v1.9.2-014** — `member_checking.yaml`:
  `consent_amendment` rewritten as "amend the IRB protocol via your
  institutional process"; `tool_redact` rewritten as "manually
  redact third-party names."
- **AUDIT-v1.9.2-025** — Qualitative `sys_path` misuse corrected:
  3 protocols (`thematic_analysis_braun_clarke`,
  `qualitative_report_format`, `member_checking`) now use
  `sys_file_list` / `sys_file_read` / `tool_search` instead of
  `sys_path` (which is a path-lifecycle dispatcher, not a finder).
- **AUDIT-v1.9.2-039** — Removed orphan `tool_write_provenance_sidecar`
  mention from router-index `provenance_completeness` decomposition.

### Audit-gate consistency

- **AUDIT-v1.9.2-034** — Kappa thresholds unified on
  Landis & Koch 1977: `qualitative_quality_audit` verdict table
  standardised; `coding_scheme_iteration` pack
  `per_code_kappa_minimum` raised from 0.60 to 0.70 to match audit
  blocker; `inter_rater_reliability` documents
  LIGHT (≥0.60) / NORMAL (≥0.70) / STRICT (≥0.80) defaults as the
  single source of truth.
- **AUDIT-v1.9.2-020** — `tool_audit_quality_full` description +
  `audit_and_validation.yaml` step doc now list all 6 gates including
  `grounding_verify` (was silently absent).
- **AUDIT-v1.9.2-059** — `tool_audit_quality_full` description +
  `TOOLS.md` entry spell out that the master audit does NOT run
  `tool_audit_step_literature`; researchers must call it per step
  (or rely on `tool_step_complete`).
- **AUDIT-v1.9.2-041** — `content_depth.py` audit result now includes
  `figures_referenced` alongside `figures_unreferenced` (cheap
  honesty).

---

## Coherence fixes (protocol ↔ tool ↔ docs alignment)

- **Tool docs ↔ tool inventory**: `docs/TOOLS.md` went from
  131/212 tool names mentioned to 212/212. Added a new
  "Infrastructure + power-user tools" section with 14 sub-tables
  (routing/dispatch, state/config/files, reliability/coaching,
  step pipelines, audit extensions, synthesis extensions, viz
  adapters, SLURM, workflow-engine adapters, data-repo + clinical
  adapters, adapter framework, qualitative/humanities/engineering/
  wet-lab/theory-math packs). [AUDIT-042]
- **Protocols doc ↔ protocols on disk**: `docs/PROTOCOLS.md` now has
  a full 114-protocol catalogue bracketed by
  `AUTO:PROTOCOL_CATALOGUE_START`/`END` sentinels; auto-generated by
  the new `scripts/regen_protocols_doc.py`. [AUDIT-010]
- **Config schema ↔ config template**: `docs/RESEARCHER_GUIDE.md` §8
  rewritten to mirror `templates/researcher_config.yaml` 1:1.
  Added `gate_strictness`, `project_tier`,
  `writing_preferences.venue_template` + `pdf_compile_engine`, the
  full `tool_stack` block, the coaching `autonomy_level` comment,
  the `research_goal.*` extension fields (primary_question, design,
  background, measurement_instrument), the top-level domain /
  research_question / authors hints, and the 7 `runtime.*`
  exec-safety fields. [AUDIT-009, AUDIT-056, AUDIT-057]
- **researcher.institution as canonical key**: `synthesis/latex.py:172`
  now reads `researcher.institution` first, falls back to
  `researcher.affiliation` for legacy configs. RESEARCHER_GUIDE
  annotates `institution` as "rendered as poster / paper author
  affiliation." [AUDIT-045]
- **Source-tree diagram**: `docs/RESEARCHER_GUIDE.md` §11 source-tree
  block rewritten from a stale 9-line sketch to a 50-line live
  snapshot. [AUDIT-048]
- **Visualization protocol coverage**: `docs/AI_GUIDE.md`
  visualization table expanded 6 → 14 protocols (added
  distribution_comparison, uncertainty_visualization,
  interactive_figure_design, interactive_dashboard_design,
  geospatial_visualization, network_visualization, animation_design,
  showcase_visualization). [AUDIT-058]
- **Cross-referencing convention**: `docs/PROTOCOL_DOCTRINE.md` now
  documents the optional `see_also` field convention (with explicit
  v1.9.3 status note that the field is documented but not yet
  auto-rendered). [AUDIT-070]
- **Maintainer counts**: `CLAUDE.md` updated 88→114 protocols,
  418+→895+ tests, preflight 13/13→21/21.

---

## Dead code removed

All zero-caller, confirmed via grep across `src/`, `tests/`,
`docs/`, `references/`, `__all__`, and pyproject entry points.

- **AUDIT-v1.9.2-037** — 4 orphaned Typst vector-figure helpers:
  `_escape_typst_text`, `_prefer_vector_figure`,
  `_maybe_convert_svg_to_pdf`, `_yiq_brightness`
  (from `synthesis/typst.py` + `audit/dashboard_content.py`).
- **AUDIT-v1.9.2-038** — 4 unused exception classes from `errors.py`:
  `ConfigError`, `ScaffoldError`, `StateError`, `ToolError`.
  Module docstring updated to reflect the actual 2-class taxonomy
  (`ResearchOSError` + `WriteProtectedError`).
- **AUDIT-v1.9.2-051** — 14 helpers / 1 constant across 8 files:
  `fetch_many` (papers.py), `run_matrix` /
  `pack_domain_detectors` / `write_pack_errors_log` (stress_runner.py),
  `read_yaml` / `write_yaml` (plugins/loader.py),
  `compute_input_hashes` / `write_readme` / `state_diff_log_path`
  (project_ops.py), `_term_width` (tui.py),
  `iter_files` / `copy_asset_tree` / `_dir_exists`
  (utils/asset_manager.py), `PLAIN_LOGO` (logo.py). Now-unused
  imports also dropped (`shutil`/`fnmatch`/`Iterable` in
  asset_manager, `shutil` in tui).

---

## Tests added

24 net new tests across 7 v1.9.3 test files (872 → 896 total):

- `tests/unit/test_v193_config_path_and_tier.py` — 7 tests
  (AUDIT-001 + 011: inputs/ path + project_tier propagation +
  legacy fallback)
- `tests/unit/test_v193_humanities_completeness.py` — 4 tests
  (AUDIT-003: apparatus.md accepted, transcriptions/ filesystem
  detection, no-artefact still blocks, non-humanities still requires
  figure)
- `tests/unit/test_v193_redcap_cross_sectional.py` — 4 tests
  (AUDIT-012: complete sentinel, sibling dictionary, longitudinal
  regression, false-positive guard)
- `tests/unit/test_v193_qualitative_detector.py` — 3 tests
  (AUDIT-013: txt transcript at 3 turns scores, .md in hints,
  empty inputs safe)
- `tests/unit/test_v193_route_state_hint.py` — 2 tests
  (AUDIT-015: state_hint accepted without crash, biases when
  matching intent_class)
- `tests/unit/test_v193_expected_pack_validation.py` — 3 tests
  (AUDIT-035: mismatch produces note, silent when unset, unknown
  pack name reports detector-unavailable)
- `tests/unit/test_config_template_matches_file.py` — 1 test
  (AUDIT-068: CONFIG_TEMPLATE constant mirrors
  templates/researcher_config.yaml byte-for-byte)

---

## Config schema cleanup

- **AUDIT-v1.9.2-068** — `CONFIG_TEMPLATE` in
  `src/research_os/tools/actions/state/config.py` rewritten to mirror
  `templates/researcher_config.yaml` byte-for-byte (modulo the
  `project_name` placeholder). Added a SOURCE-OF-TRUTH preamble to
  the template. New sync test
  (`tests/unit/test_config_template_matches_file.py`) prevents
  future drift.
- **AUDIT-v1.9.2-072** — `sys_config_validate` now performs per-field
  enum membership checks. Added `_ENUM_FIELDS` table + `_dotted_get`
  helper. `validate_config` returns `enum_violations` and folds
  off-enum values into the human-readable message for:
  `autonomy_level`, `gate_strictness`, `project_tier`,
  `model_profile`, `pdf_compile_engine`, `citation_style`,
  `quality_gate_policy`, `ambiguity_posture`.
- **AUDIT-v1.9.2-046** — `coaching` autonomy_level aliased to
  `supervised` for the scheduler (display preserved). Added
  `normalize_autonomy_level` + `_AUTONOMY_ALIASES`. Template comments
  document `coaching` as a pedagogical alias of `supervised`, so
  the listed enum is no longer behaviourally vacuous.

---

## Audit-gate consistency

- **AUDIT-v1.9.2-020** — Master audit (`tool_audit_quality_full`)
  description + the `audit_and_validation.yaml` step doc now list all
  6 gates: `step_completeness`, `dashboard_content`,
  `content_depth`, `audit_synthesis`, `discussion_coverage`,
  `grounding_verify`. (`grounding_verify` was previously silently
  invoked but undocumented.)
- **AUDIT-v1.9.2-059** — Master audit description + `TOOLS.md` entry
  now spell out the per-step literature skip with a one-sentence
  warning telling the AI to call `tool_audit_step_literature`
  explicitly (or rely on `tool_step_complete`) or expect blockers at
  `tool_audit_synthesis` / `tool_path_finalize`.
- **AUDIT-v1.9.2-018** — `override_no_pdfs` now writes to
  `override_log.md`, closing the audit-trail gap that would have bitten
  a biology synthesis attempt.
- **AUDIT-v1.9.2-002** — `override_discussion_coverage` now end-to-end
  (description + inputSchema + handler with `quality_gate_policy`
  enforcement + `log_override`).
- **AUDIT-v1.9.2-034** — Kappa thresholds standardised at the
  quality_bar / verdict-table level across the qualitative gate
  surface (κ≥0.70 NORMAL floor; Landis & Koch boundaries).

---

## New preflight check

- **AUDIT-v1.9.2-069** — `check_router_index_bumped`
  (warn-only; always returns True) added to `scripts/preflight.py`.
  Emits a clear hint when any protocol YAML is fresher than
  `_router_index.yaml`. Preflight now reports **22 checks** (was 21).

---

## Bulk version bump

- **AUDIT-v1.9.2-043** — All 114 core protocols now carry
  `version: '1.9.3'` (was 107× 1.7.1 + 5× 1.9.0 + 2× 1.9.1).
  Router index version bumped 14 → 15.
- **AUDIT-v1.9.2-044** — All 5 pack `__version__` strings bumped to
  1.9.3 (was 2× 1.7.0 + 3× 1.7.1); all 36 pack protocol YAMLs bumped
  to 1.9.3. `sys_packs_installed` will now surface consistent versions.

---

## Deferred (per audit's own triage table)

10 findings moved to v1.9.4 or v1.11.0 per the audit body's target
column. None of these are blockers for v1.9.3 ship.

| ID | Title | New target |
|---|---|---|
| AUDIT-v1.9.2-022 | `literature_per_step` empirical-only (humanities blocker) | v1.9.4 |
| AUDIT-v1.9.2-023 | `synthesis_paper` hard-codes p-value formatting | v1.9.4 |
| AUDIT-v1.9.2-024 | `audit_and_validation` auto-routes codebook to qualitative gate | v1.9.4 |
| AUDIT-v1.9.2-026 | COREQ-SRQR checklist YAMLs never shipped | v1.11.0 |
| AUDIT-v1.9.2-047 | Deprecated-alias sweep across 71 protocols | v1.11.0 |
| AUDIT-v1.9.2-060 | `tool_paper_compile_typst` `next_steps` field | v1.9.4 |
| AUDIT-v1.9.2-063 | `synthesis_paper` 10-turn mandatory loop | v1.11.0 |
| AUDIT-v1.9.2-065 | `synthesis_paper` prerequisites assume `literature_index` ≥3 | v1.9.4 |
| AUDIT-v1.9.2-073 | dashboard surface for codebooks / apparatus criticus | v1.11.0 |
| AUDIT-v1.9.2-074 | Humanities pack chains dead-end at `next_protocol: null` | v1.9.4 |

---

## Stress re-run (3 lenses)

After all v1.9.3 fixes landed, the same three stress agents from the
v1.9.2 audit re-ran their composition traces:

| Lens | Domain | v1.9.2 frictions | v1.9.3 frictions | Rating |
|---|---|---|---|---|
| 01 | Biology snRNA-seq | 9 | 4 (all deferred) | 9/10 |
| 02 | Humanities composition | 15 | 11 (4 fixed; 7 deferred per triage) | 6/10 |
| 03 | Qualitative interview study | 9 | 3 (+ 1 new internal-drift item) | 8/10 |

Average usability across 3 lenses: **7.67 / 10** (was ~5 in v1.9.2).

Highlights:

- Biology: 5 same DESeq2/scRNA phrasings that failed routing in v1.9.2
  now route to `guidance/analysis_plan` with confidence 0.659. Typst
  PDF compile reachable from `tool_plan_advance`.
- Humanities: markdown-only step (`apparatus.md` + `transcriptions/` +
  `citation_chains.md` + `conclusions.md`) passes `step_completeness`
  with no figure blocker. The remaining 11 frictions are all
  v1.9.4-targeted (literature_per_step / synthesis_paper /
  qualitative-auto-route empirical assumptions).
- Qualitative: 12-row REDCap participant tracking CSV now detects;
  `.txt` transcripts at 3 turns confidence 0.1 → 1.0;
  `member_checking.yaml` doc-only rewrites close all hallucination
  paths. New v1.9.4 work item: internal κ drift in
  `coding_scheme_iteration.yaml` prose + `tools.py`.

---

## Files touched

- **src/**: 26 files
- **tests/**: 7 new test files, 2 rewritten
- **docs/**: 8 files
- **templates/**: 1 file
- **scripts/**: 2 files (preflight.py + new regen_protocols_doc.py)
- **packs**: 5 `__init__.py` + 36 protocol YAMLs
- **CLAUDE.md** + **pyproject.toml** (F401 per-file ignore)
- **All 114 core protocols** + `_router_index.yaml` (version bump)

---

## Migration notes for users

- **`researcher.affiliation` is now `researcher.institution`** —
  `synthesis/latex.py` falls back to the old key, so existing
  projects keep rendering. Update at your leisure.
- **`coaching` autonomy_level** — still listed in the enum and still
  accepted; the scheduler now aliases it to `supervised` (which is
  what it always behaved as). Display strings preserved.
- **`project_tier`** — if you set `project_tier: throwaway|sketch`
  and leave `gate_strictness: auto`, gates now relax accordingly.
  v1.9.2 silently ignored the tier setting in this case.
- **Override args on `tool_discussion_coverage_audit`** — new optional
  args `override_discussion_coverage` + `override_rationale`. Gated
  by `quality_gate_policy`. No-op for projects that don't use them.
- **`tool_audit_quality_full`** — still skips per-step literature.
  This is now explicit in the description and in `TOOLS.md`. Call
  `tool_audit_step_literature` per step OR rely on
  `tool_step_complete` to invoke it.

---

## Acknowledgements

This release is the synthesis of:

- 1 audit pass (v1.9.2 discovery sprint, 75 findings, 10 lenses)
- 1 prioritisation pass (35-item v1.9.3 work-list)
- 3 parallel code/YAML/docs fix passes (Phase 1 + 2A + 2B + 2C)
- 3 parallel stress re-runs (biology / humanities / qualitative)
- 1 synthesis pass (this changelog)

Total: ~28 agent-hours per the audit estimate, delivered in a
single multi-agent workflow with serial gate validation between
phases.
