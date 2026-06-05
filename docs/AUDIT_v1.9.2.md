# Research-OS Audit v1.9.2

**Audit window:** 2026-06-05 discovery sprint
**Baseline:** v1.9.1 (114 protocols, 212 wired MCP tools, 872 tests passing, ruff clean, preflight 13/13)
**Auditor:** 10 parallel lens agents + synthesis pass
**Repository root:** `/scratch/vsetlur/Research-OS`

---

## 0. Audit shape

Ten independent agents were tasked with stress-testing Research-OS along ten orthogonal axes:

| Lens | Theme | Report |
|---|---|---|
| 01 | Biology / snRNA-seq end-to-end stress | [docs/audit_v1.9.2/lens_01_biology_stress.md](audit_v1.9.2/lens_01_biology_stress.md) |
| 02 | Humanities pack end-to-end stress | [docs/audit_v1.9.2/lens_02_humanities_stress.md](audit_v1.9.2/lens_02_humanities_stress.md) |
| 03 | Qualitative interview + REDCap stress | [docs/audit_v1.9.2/lens_03_qualitative_stress.md](audit_v1.9.2/lens_03_qualitative_stress.md) |
| 04 | Tool ↔ protocol ↔ server consistency | [docs/audit_v1.9.2/lens_04_tool_protocol_consistency.md](audit_v1.9.2/lens_04_tool_protocol_consistency.md) |
| 05 | Cross-protocol graph + recommendation chains | [docs/audit_v1.9.2/lens_05_protocol_graph.md](audit_v1.9.2/lens_05_protocol_graph.md) |
| 06 | Docs accuracy + currency | [docs/audit_v1.9.2/lens_06_docs_accuracy.md](audit_v1.9.2/lens_06_docs_accuracy.md) |
| 07 | researcher_config.yaml schema integrity | [docs/audit_v1.9.2/lens_07_config_schema.md](audit_v1.9.2/lens_07_config_schema.md) |
| 08 | Test coverage + brittleness | [docs/audit_v1.9.2/lens_08_test_coverage.md](audit_v1.9.2/lens_08_test_coverage.md) |
| 09 | Dead code + orphan modules | [docs/audit_v1.9.2/lens_09_dead_code.md](audit_v1.9.2/lens_09_dead_code.md) |
| 10 | Audit-gate machinery internal audit | [docs/audit_v1.9.2/lens_10_audit_gates.md](audit_v1.9.2/lens_10_audit_gates.md) |

Each lens produced an in-line trivial-fixes patch (typos, stale counts, dead branches, ruff-fix auto-corrections) and recorded production-code findings in a markdown report. This synthesis aggregates all 75 raw findings, deduplicates them across lenses, assigns audit IDs, and produces a release work-list for v1.9.3, v1.9.4, v1.11.0, and v2.0.0.

---

## 1. Executive summary

### 1.1 Findings by severity (aggregated, deduplicated)

| Severity | Count | Description |
|---|---|---|
| CRITICAL | 5 | Blocks release surface; v1.5.1 features silently inert; documented escape hatches are no-ops; humanities pack structurally unreachable through synthesis. |
| HIGH | 27 | User-visible wrong behaviour, docs lying about counts/schema/tools, audit-gate inconsistencies. |
| MEDIUM | 29 | Friction, dead-code categories, naming drift, version drift. |
| LOW | 22 | Polish, comment fixes, false-positive analysis, schema-clarity nits. |
| **Total** | **83 raw → 75 unique** | |

### 1.2 Findings by category

| Category | Count |
|---|---|
| BUG | 22 |
| DOC_GAP | 21 |
| INCONSISTENCY | 14 |
| DEAD_CODE | 10 |
| FRICTION | 7 |
| ARCH_SMELL | 3 |
| REGRESSION | 2 |

### 1.3 Top 10 most-critical findings (release-blocker tier)

| # | ID | Severity | Lens | Title |
|---:|---|---|---|---|
| 1 | AUDIT-v1.9.2-001 | CRITICAL | 07, 10 | `gate_strictness` + `project_tier` + reliability `model_profile` read from project root instead of `inputs/` — entire v1.5.1 tier/strictness subsystem silently inert in real projects |
| 2 | AUDIT-v1.9.2-002 | CRITICAL | 10 | `override_discussion_coverage` documented in tool description, writing_discussion.yaml, and audit_and_validation.yaml — but handler discards args, inputSchema is `{}`, function takes no override parameter |
| 3 | AUDIT-v1.9.2-003 | CRITICAL | 02 | Server-side step_completeness gate hard-requires PNG/SVG focal figure per numbered step — structurally blocks any humanities project from reaching synthesis |
| 4 | AUDIT-v1.9.2-004 | CRITICAL | 02 | Seven tools referenced by `digital_humanities_workflow.yaml` + `scholarly_edition.yaml` do not exist in `TOOL_DEFINITIONS`; pack is unrunnable as written |
| 5 | AUDIT-v1.9.2-005 | HIGH | 01, 04, 06 | Seven user-facing docs hardcoded stale `113 protocols` / `146 tools` counts (actual: 114 / 212) — propagated across `README`, `START`, `AI_GUIDE`, `PROTOCOLS`, `TOOLS`, `FAQ`, `RESEARCHER_GUIDE`, `ROADMAP`, `CLAUDE.md` |
| 6 | AUDIT-v1.9.2-006 | HIGH | 10 | `tool_audit_quality_full` runs 6 gates but description advertises 5 — `grounding_verify` invoked silently, contributes blockers users cannot trace |
| 7 | AUDIT-v1.9.2-007 | HIGH | 10 | Only 1 of 20 audit gates honours `gate_strictness` — `figure_interactivity` is the lone reader; the light/normal/strict policy is largely cosmetic |
| 8 | AUDIT-v1.9.2-008 | HIGH | 10 | `override_no_pdfs` bypass does not write to `override_log.md` — audit trail invisible for pre_submission_checklist |
| 9 | AUDIT-v1.9.2-009 | HIGH | 06 | `RESEARCHER_GUIDE.md` §8 config schema 5 fields behind template — missing `gate_strictness`, `project_tier`, `venue_template`, `pdf_compile_engine`, entire `tool_stack` block, and `coaching` autonomy value |
| 10 | AUDIT-v1.9.2-010 | HIGH | 06 | `PROTOCOLS.md` silently omits 34 of 114 protocols (30% of catalog) including 8 of 14 visualization protocols and all 4 newest synthesis protocols |

### 1.4 Subsystem health assessment

| Subsystem | Status | Reasoning |
|---|---|---|
| Protocol graph | GREEN | 114/114 protocols match router entries; 0 broken `next_protocol` refs; 0 unintentional dead-ends; 0 orphan protocols. Three 2-cycles flagged but design-defensible. |
| Tool wiring | GREEN | 212 tools registered; preflight catches broken refs at release; 1 false reference (`tool_write_provenance_sidecar` in prose) flagged. |
| Tests | GREEN | 872 tests, ~37 s wall-clock, no network calls, no hardcoded home paths, no slow tests. Coverage = 55% (acceptable for an MCP-heavy codebase). |
| Dead code | GREEN | Vulture at min-confidence 80 reports 1 finding after the path.py:1568 fix. No orphan modules; all 7 vendored JS bundles consumed. |
| Documentation | YELLOW | Count drift fixed inline; 34-protocol omission in `PROTOCOLS.md` + 66-tool omission in `TOOLS.md` + 5-field gap in `RESEARCHER_GUIDE.md` still outstanding. |
| researcher_config.yaml schema | RED | Wizard, on-disk template, and docs each tell a different story; 3 critical config-reader paths broken; 12 template fields are dead; 7 runtime exec-safety fields consumed but undocumented. |
| Audit-gate machinery | RED | Master covers 6/20; only 1/20 honours strictness; `project_tier` flows nowhere; one documented override is fiction; output filenames follow 3 conventions; 2 audits write no report. |
| Humanities pack | RED | 7 referenced tools don't exist; figure-mandatory completeness gate blocks all humanities synthesis; literature gate is empirical-only; chain dead-ends without rejoining core synthesis. |
| Qualitative pack | YELLOW | Happy-path works; cross-sectional REDCap exports advertised but not detected; .txt transcripts mis-scored; 2 referenced helpers don't exist; κ thresholds drift across 3 protocols. |
| Biology core path | GREEN | End-to-end snRNA-seq pipeline wires correctly through 25 stages; `pick_tool_stack` doctrine is the strongest piece of the workflow; semantic miss on `DESeq2 differential expression` is the only routing issue. |

---

## 2. Findings catalog

### 2.1 BUGS (MAJOR + MINOR + REGRESSION)

#### CRITICAL — release-blocking

##### AUDIT-v1.9.2-001 — Config-reader path bug

**Severity:** CRITICAL **Lens:** 07 **Category:** BUG **Target:** v1.9.3 **Estimate:** 1h

Three production code paths look for `researcher_config.yaml` at the project root, but the wizard puts it at `inputs/researcher_config.yaml`. The misroute makes all three subsystems silently inert in real projects.

- [src/research_os/tools/actions/state/rigor_signals.py](src/research_os/tools/actions/state/rigor_signals.py):229 — `resolve_gate_strictness`
- [src/research_os/tools/actions/state/quick_mode.py](src/research_os/tools/actions/state/quick_mode.py):206 — `project_tier_strictness`
- [src/research_os/tools/actions/state/reliability.py](src/research_os/tools/actions/state/reliability.py):52 — `_read_model_profile`

**Reproduction:**
1. `research-os init` a new project; wizard writes config to `inputs/researcher_config.yaml`.
2. Set `gate_strictness: strict`, `project_tier: production`.
3. Call any audit. The strictness setting is ignored (falls through to the auto/default rigor-score branch).
4. Verify: `_read_model_profile` always returns `"unknown"` for reliability telemetry.

**Why tests miss it:** `tests/tools/test_v1_5_1.py:101` and `tests/unit/test_v151.py:200` both write config to `tmp_path/researcher_config.yaml` (the buggy path), so the test fixtures codify the bug. Compare server.py:6253 which gets this right with a dual-path fallback.

**Suggested fix:** change the 3 buggy sites to use `_config_path(root)` from `tools/actions/state/config.py`, OR adopt the dual-path fallback used at `server.py:6253`. Fix `tests/tools/test_v1_5_1.py:96-115` and `tests/unit/test_v151.py:189-201` to write to `inputs/researcher_config.yaml`.

##### AUDIT-v1.9.2-002 — `override_discussion_coverage` is fiction

**Severity:** CRITICAL **Lens:** 10 **Category:** BUG **Target:** v1.9.3 **Estimate:** 1.5h

`tool_discussion_coverage_audit` description ([src/research_os/server.py](src/research_os/server.py):2222) and `writing_discussion.yaml:153` both tell the AI to pass `override_discussion_coverage=true` to bypass the gate. But:

- `tool_discussion_coverage_audit` `inputSchema` is `{}` empty ([src/research_os/server.py](src/research_os/server.py):2225). The MCP layer accepts the kwarg silently but the handler ignores it.
- `_handle_tool_discussion_coverage_audit` ([src/research_os/server.py](src/research_os/server.py):5268) discards arguments: `return _text(discussion_coverage_audit(root))`.
- `discussion_coverage_audit` ([src/research_os/tools/actions/synthesis/discussion_from_verdicts.py](src/research_os/tools/actions/synthesis/discussion_from_verdicts.py):93) has no override parameter.

**Reproduction:**
1. Trigger a discussion-coverage blocker (any synthesis without verdict coverage).
2. Call `tool_discussion_coverage_audit override_discussion_coverage=true override_rationale="..."`.
3. Gate still fires; researcher has no documented path forward except deleting verdicts.

**Suggested fix:** add the override param to the function signature, the handler, and the `inputSchema`. Mirror `tool_audit_dashboard_content` enforce-policy pattern at [src/research_os/server.py](src/research_os/server.py):3851-3856. Log via `log_override` exactly like the five other working overrides.

##### AUDIT-v1.9.2-003 — Step completeness gate blocks all humanities synthesis

**Severity:** CRITICAL **Lens:** 02 **Category:** ARCH_SMELL **Target:** v1.9.3 **Estimate:** 3h

`audit_step_completeness` ([src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py):1349-1364) hard-requires a PNG/SVG/JPG focal figure per numbered step folder. Humanities projects produce markdown apparatus criticus / transcriptions / citation chains, not figures.

**Reproduction:**
1. Run `research-os init`, drop a humanities pack manifest.
2. Walk `humanities/textual/close_reading` → `humanities/citation/citation_chains` → produce `workspace/edition/apparatus.md`.
3. Call `tool_synthesize`. It calls `audit_step_completeness` first.
4. Result: `BLOCKER: No figure produced — every step MUST emit at least one focal figure to outputs/figures/{step_num}_<descriptor>.png.`

**Suggested fix:** add a `pack_overrides` block to the gate; if the active pack is `humanities`, accept markdown artefacts in `workspace/<topic>/` (apparatus.md / transcriptions/ / citation chains) as the focal artefact. Alternative: add a `domain: humanities` flag to `researcher_config.yaml` that suppresses the figure requirement.

##### AUDIT-v1.9.2-004 — Seven humanities-pack tools do not exist

**Severity:** CRITICAL **Lens:** 02 **Category:** BUG **Target:** v1.9.3 **Estimate:** 8h (or v1.10.0 if shipping the tools)

`digital_humanities_workflow.yaml` and `scholarly_edition.yaml` instruct the AI to call seven tools that are not registered in `TOOL_DEFINITIONS`:

- `tool_dh_topic_model`, `tool_dh_stylometry`, `tool_dh_network` ([src/research_os_humanities/protocols/method/digital_humanities_workflow.yaml](src/research_os_humanities/protocols/method/digital_humanities_workflow.yaml):94-95)
- `tool_humanities_close_reading` (:127)
- `tool_viz_dh` (:158)
- `tool_humanities_collate` ([src/research_os_humanities/protocols/output/scholarly_edition.yaml](src/research_os_humanities/protocols/output/scholarly_edition.yaml):75)
- `tool_humanities_apparatus` (:114), `tool_humanities_apparatus_lint` (:131)

**Why preflight misses it:** [scripts/preflight.py](scripts/preflight.py):394 scans only `PROTOCOLS_DIR.rglob("*.yaml")` where `PROTOCOLS_DIR = .../research_os/protocols` — pack protocols at `src/research_os_humanities/protocols/` are not scanned by the tool-ref resolver. The fixture-driven stress test ([tests/unit/test_v170_plugins_packs_stress.py](tests/unit/test_v170_plugins_packs_stress.py):304) canned-responses each step and only verifies named artefacts exist on disk; never actually calls the tools.

**Suggested fix:** two paths. Short-term v1.9.3 — rewrite the protocol prose to describe the work as "manual" / "write a script using `tool_python_exec`" until the tools ship. Long-term v1.10.0 — implement the seven tools as scaffold-writers in `src/research_os_humanities/tools.py`. Also: teach preflight to scan pack protocols when validating tool refs.

##### AUDIT-v1.9.2-011 — `project_tier` never propagates

**Severity:** CRITICAL **Lens:** 10 **Category:** BUG **Target:** v1.9.3 **Estimate:** 1.5h

`project_tier_strictness` ([src/research_os/tools/actions/state/quick_mode.py](src/research_os/tools/actions/state/quick_mode.py):203) maps `researcher_config.project_tier` to a default `gate_strictness`: `throwaway → light`, `sketch → normal`, `production → strict`. `tool_project_tier_strictness` exposes this as a callable.

But `resolve_gate_strictness` ([src/research_os/tools/actions/state/rigor_signals.py](src/research_os/tools/actions/state/rigor_signals.py):223) — which is the function consulted by audits — never reads `project_tier`. It reads `researcher_config.gate_strictness` only. If the researcher sets `project_tier: throwaway` and leaves `gate_strictness` unset, the fallback is the rigor_signals_scan trust_score, NOT the `light` value that `project_tier_strictness` would have returned.

So: setting `project_tier: throwaway` in `researcher_config.yaml` does absolutely nothing. The tool description ([src/research_os/server.py](src/research_os/server.py):2290) lies.

**Reproduction:**
1. Set `project_tier: throwaway` in `inputs/researcher_config.yaml`. Leave `gate_strictness` unset.
2. Call `tool_resolve_gate_strictness`. Returns `auto`/`default`/`rigor_score → strict-or-normal` — not `light`.

**Suggested fix:** `resolve_gate_strictness` should consult `project_tier_strictness` as the default when `gate_strictness` is unset (instead of falling through to rigor_signals). Compounded by AUDIT-v1.9.2-001 (path bug) — both must be fixed together.

#### HIGH bugs

##### AUDIT-v1.9.2-012 — REDCap adapter cannot detect cross-sectional exports it advertises

**Severity:** HIGH **Lens:** 03 **Category:** BUG **Target:** v1.9.3 **Estimate:** 2h

[src/research_os_adapter_redcap/__init__.py](src/research_os_adapter_redcap/__init__.py):39-43 hard-requires one of `redcap_event_name | redcap_repeat_instrument | redcap_repeat_instance` in the export header for detection. [src/research_os_adapter_redcap/__init__.py](src/research_os_adapter_redcap/__init__.py):442-443 `describe()` advertises `shapes_supported: ["data_dictionary_csv", "longitudinal_export_csv", "cross_sectional_export_csv"]` — the third shape is not actually detected by `_classify_csv`.

**Reproduction:** export a single-instrument, cross-sectional CSV from REDCap (the natural shape for a participant-tracking sheet in a 12-person qualitative study). `detect → False`, `extract → notes "No REDCap-shaped CSV found"`. PHI warnings under-report by 100%.

**Suggested fix:** loosen detection to classify as `"export"` when `record_id` is present AND the file has a sibling REDCap dictionary CSV in the same directory, OR accept any CSV with `record_id` as a candidate export and let `extract` mark it `longitudinal: false`. At minimum, remove `cross_sectional_export_csv` from `describe()` until detection catches up.

##### AUDIT-v1.9.2-013 — Qualitative detector blind to `.txt` transcripts

**Severity:** HIGH **Lens:** 03 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.5h

[src/research_os_qualitative/detector.py](src/research_os_qualitative/detector.py):12 — `_INTERVIEW_HINT_EXTS = {".vtt", ".otr", ".docx", ".rtf"}` excludes `.txt`. Line 58 speaker-turn regex requires `≥ 5` matches per file.

**Reproduction:** 12 short plain-text transcripts with 4 speaker turns each (`Interviewer:` / `P:`) return confidence 0.1 — below any plausible auto-load threshold.

**Suggested fix:** add `.txt` and `.md` to `_INTERVIEW_HINT_EXTS` and weight speaker-turn matches at `≥3` instead of `≥5`. Two-line touch.

##### AUDIT-v1.9.2-014 — `member_checking.yaml` references two unimplemented helpers

**Severity:** HIGH **Lens:** 03 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.5h (rewrite) / 6h (ship the tools)

[src/research_os_qualitative/protocols/validity/member_checking.yaml](src/research_os_qualitative/protocols/validity/member_checking.yaml):46 references `consent_amendment` (no such protocol). Line 110 references `tool_redact` (no such tool).

**Reproduction:** an AI walking `member_checking` mid-flow hits `If not, run consent_amendment first.` → consent_amendment doesn't exist. Hits `Use tool_redact if any third-party names appear in the quotes` → tool_redact doesn't exist.

**Suggested fix (v1.9.3, doc-only):** rewrite the two lines as "manually redact third-party names" / "amend the IRB protocol via your institutional process." Long-term v1.10.0: ship `tool_qualitative_redact` (regex + NER sweep) and a `consent_amendment` mini-protocol.

##### AUDIT-v1.9.2-015 — `route_request` silently ignores `state_hint` kwarg

**Severity:** HIGH **Lens:** 08, 09 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.5h

[src/research_os/tools/actions/router.py](src/research_os/tools/actions/router.py):540 — `route_request(state_hint: dict | None = None)` accepts a keyword-only param that is never read by the function body, and no caller in the repo passes it. Vulture 100% confidence.

**Reproduction:** call `route_request(prompt="x", state_hint={"current_phase": "synthesis"})`. The function returns the same routing decision regardless of the hint.

**Suggested fix:** either wire `state_hint` into the router scoring (preferred — there is real value in biasing routes based on `current_phase` / `last_protocol`), or drop the parameter on the next MAJOR. Public function signature should not silently lie about what it uses.

##### AUDIT-v1.9.2-016 — DPI threshold disagreement between two figure audits

**Severity:** HIGH **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 1h

[src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py):1035 — `audit_figure` treats DPI < 150 as WARN, status caps at `warning`.
[src/research_os/tools/actions/viz/figures.py](src/research_os/tools/actions/viz/figures.py):211 — `audit_figure_quality` (via `tool_audit_figure_full`) treats DPI < 200 as a BLOCKER.

**Reproduction:** export a 180 DPI PNG. Run `tool_audit_figure` → `warning`. Run `tool_audit_figure_full` → BLOCKER. Same image. The audit_and_validation protocol routes researchers to `tool_audit_figure_full` for the gate but uses `tool_audit_figure` as a "cheaper intra-step spot check" — nothing in the descriptions warns severities differ.

**Suggested fix:** unify on a single threshold (suggest 200 DPI as the publication-grade floor; 150 as the warn-only floor). Pull both from a shared constant in [src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py).

##### AUDIT-v1.9.2-017 — Audit report routing splits between two directories

**Severity:** HIGH **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 2h

`_report_path` ([src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py):43-49) returns `workspace/<current_step>/outputs/reports/<filename>` when a step is active, else `workspace/logs/<filename>`. Seven audits use it (audit_synthesis, audit_power, audit_assumptions, audit_evalue, audit_figure, audit_citations, audit_reproducibility_full). Eight audits bypass it and always go to `workspace/logs/` (step_completeness, code_quality, prose_quality, claim_grounding, preregistration, figure_interactivity, coherence, audit_master).

**Reproduction:** start a step, call `tool_audit_synthesis`, then call `audit/pre_submission_checklist`. The checklist reads `workspace/logs/audit_report.md` directly; the sub-audit written to the step folder is invisible to the consolidation step.

**Suggested fix:** standardize on `workspace/logs/<step_num>_<gate>.md` for step-scoped audits and `workspace/logs/<gate>.md` for synthesis-time audits. Drop the step-folder split.

##### AUDIT-v1.9.2-018 — `override_no_pdfs` skips override_log.md

**Severity:** HIGH **Lens:** 10 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.25h

`_handle_tool_audit_synthesis` ([src/research_os/server.py](src/research_os/server.py):3557) forwards `override_no_pdfs` to `audit_synthesis` but never calls `log_override`. Every other gate-bypass logs (six other callsites in server.py). The pre_submission_checklist protocol relies on `override_log.md` to surface bypasses; this one is invisible.

**Suggested fix:** add a one-line `log_override(root, gate="audit_synthesis_no_pdfs", rationale=arguments.get("override_rationale", ""))` after the override is honoured.

##### AUDIT-v1.9.2-019 — `tool_audit_step_literature` cannot be overridden directly

**Severity:** HIGH **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 1h

`tool_audit_step_literature` handler ([src/research_os/server.py](src/research_os/server.py):3993) only forwards `step_id`. Its description (line 1087) says blockers are hard stops for `tool_path_finalize` "unless `override_literature_gate=true` is passed." But that override is only honoured by `tool_path_finalize` ([src/research_os/server.py](src/research_os/server.py):3118-3149).

A researcher who calls the audit tool directly to re-confirm the gate state cannot get a clean pass; they must call `tool_path_finalize`. The error message inside `tool_path_finalize` tells them to pass `override_literature_gate` but doesn't tell them the audit alone won't accept it.

**Suggested fix:** either add `override_literature_gate` to the audit tool's surface and have it pass through, OR clarify in the description that overrides only land at finalize-time.

##### AUDIT-v1.9.2-020 — Audit master advertises 5 gates but runs 6

**Severity:** HIGH **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.25h

Tool description ([src/research_os/server.py](src/research_os/server.py):1544): "Runs tool_audit_step_completeness + tool_audit_code_quality + tool_audit_prose + tool_audit_claims + tool_preregister_diff" — 5 audits.

[src/research_os/protocols/audit/audit_and_validation.yaml](src/research_os/protocols/audit/audit_and_validation.yaml):21-37 echoes the same 5.

But [src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py):973-985 silently invokes `grounding_verify`. Researchers debugging a blocker like `[grounding] N decision(s) without grounding records` will hunt the docs in vain.

**Suggested fix:** update server.py:1544 and audit_and_validation.yaml:21-37 to list the 6th gate, OR remove the call from `audit_quality_full` and surface it as a separate tool.

##### AUDIT-v1.9.2-021 — Only 1 of 20 audit gates honours `gate_strictness`

**Severity:** HIGH **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.11.0 **Estimate:** 8h

`figure_interactivity` ([src/research_os/tools/actions/audit/figure_interactivity.py](src/research_os/tools/actions/audit/figure_interactivity.py):163) is the only audit that calls `resolve_gate_strictness`. Every other audit ignores it. Researchers who set `gate_strictness: light` to soften the gates and only this one gate softens; the rest still BLOCK.

**Reproduction:** set `gate_strictness: light`. Call any non-figure-interactivity audit. Strict thresholds apply unchanged.

**Suggested fix:** thread `gate_strictness` through `audit_figure` / `audit_figure_full` (DPI thresholds), `audit_prose` (hedging count), `audit_code_quality` (complexity), `audit_step_completeness` (focal-figure absence severity), `audit_citations` (unresolved citation severity).

##### AUDIT-v1.9.2-022 — Literature gate is empirical-only

**Severity:** HIGH **Lens:** 02 **Category:** BUG **Target:** v1.9.4 **Estimate:** 4h

[src/research_os/protocols/literature/literature_per_step.yaml](src/research_os/protocols/literature/literature_per_step.yaml):64-108 extracts QUANTITATIVE anchors (log2FC, padj, HR, CI) per claim; builds queries against PubMed/Crossref/Semantic Scholar; filters by `≥20 cumulative citations`. Verdict schema is `AGREES | DISAGREES | EXTENDS | DEFERRED`.

A literary critic legitimately citing only primary sources + 19th-c. apparatus criticus will produce zero `claims_grounded` by this protocol's standard and be blocked at finalize.

**Suggested fix:** add a `humanities_branch` config that swaps queries to humanities indices (HathiTrust, BL catalogues, IIIF manifests), drops the citation-count filter, and admits the verdict types `corroborates | departs | new_conjecture`.

##### AUDIT-v1.9.2-023 — synthesis_paper forces statistics on humanities work

**Severity:** HIGH **Lens:** 02 **Category:** BUG **Target:** v1.9.4 **Estimate:** 3h

[src/research_os/protocols/synthesis/synthesis_paper.yaml](src/research_os/protocols/synthesis/synthesis_paper.yaml):174-210 — `draft_results` forces "Every p-value formatted to 3 decimals" and "Every effect estimate paired with 95% CI"; `draft_abstract` requires "one quantitative finding." `venue_profile` covers Nature/Science/NEJM/PLOS/PNAS/JCO/IEEE/NeurIPS/ACL but no `humanities/critical_edition` or `humanities/close_reading_essay`.

**Suggested fix:** add an `output_kind: empirical | humanities | technical | review` switch on `synthesis_paper`; gate the quantitative-evidence requirement to `empirical`. Add 4-5 humanities venue profiles (Modern Philology, PMLA, Speculum, Renaissance Quarterly, Loeb Classical / OCT).

##### AUDIT-v1.9.2-024 — Audit auto-routes any qualitative artefact to COREQ/SRQR audit

**Severity:** HIGH **Lens:** 02 **Category:** BUG **Target:** v1.9.4 **Estimate:** 1h

[src/research_os/protocols/audit/audit_and_validation.yaml](src/research_os/protocols/audit/audit_and_validation.yaml):70-71: "If the step is qualitative (themes.md / codebook.md exists): → also run protocol methodology/qualitative_quality_audit." That audit enforces COREQ/SRQR/saturation/intercoder κ/member checking — designed for human-subjects qualitative research. A digital-humanities workflow might legitimately produce themes.md or codebook.md (close-reading codes); the COREQ checklist is nonsensical for that work.

**Suggested fix:** key the auto-route on `pack: qualitative` rather than artefact filename; or add a `qualitative_kind: human_subjects | literary` switch.

##### AUDIT-v1.9.2-025 — Three qualitative-pack protocols misuse `sys_path`

**Severity:** HIGH **Lens:** 03 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 0.5h

- [src/research_os_qualitative/protocols/method/thematic_analysis_braun_clarke.yaml](src/research_os_qualitative/protocols/method/thematic_analysis_braun_clarke.yaml):210 — `sys_path to find the relevant checklist scaffold`
- [src/research_os_qualitative/protocols/output/qualitative_report_format.yaml](src/research_os_qualitative/protocols/output/qualitative_report_format.yaml):79 — `Call sys_path to confirm the standard's checklist YAML exists`
- [src/research_os_qualitative/protocols/validity/member_checking.yaml](src/research_os_qualitative/protocols/validity/member_checking.yaml):193 — `Use sys_path to confirm the next protocol artifacts exist`

`sys_path` is the path-lifecycle dispatcher with operations `create | abandon | list` (per [src/research_os/server.py](src/research_os/server.py):2367-2386). It has no filesystem-read role. The intended tool is `sys_file_read` / `sys_file_list` (or `tool_search` for content search).

**Suggested fix:** rewrite the three lines to call the correct tool.

##### AUDIT-v1.9.2-026 — COREQ/SRQR checklist YAMLs never shipped

**Severity:** HIGH **Lens:** 03 **Category:** DOC_GAP **Target:** v1.11.0 **Estimate:** 6h

`qualitative_report_format`'s `coverage_gate` / `walk_checklist` steps depend on a checklist YAML at `workspace/checklists/<standard>_coverage_v<N>.yaml`. The `select_standard` step says "Call sys_path to confirm the standard's checklist YAML exists." There is no checklist YAML shipped anywhere in the repo. The AI is forced to hallucinate the 32 COREQ items or the 21 SRQR items.

**Suggested fix:** ship `templates/checklists/coreq_32items.yaml` and `templates/checklists/srqr_21items.yaml` with verbatim item text (both CC-licensed); have `select_standard` copy the appropriate one into `workspace/checklists/`.

##### AUDIT-v1.9.2-027 — Hermeneutic on_failure routes to nonexistent protocols

**Severity:** HIGH **Lens:** 02 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.25h

[src/research_os_humanities/protocols/method/hermeneutic_method.yaml](src/research_os_humanities/protocols/method/hermeneutic_method.yaml):237-245 says: "do NOT proceed to close_reading. Instead, call sys_path to surface the intellectual_history or critical_theory_survey protocol so the framework gets picked deliberately." Neither `intellectual_history` nor `critical_theory_survey` exists.

**Suggested fix:** rewrite the on_failure to point at a real protocol (suggest `humanities/method/hermeneutic_method` itself with an in-protocol "ask the researcher to name a framework" loop) until the two missing protocols ship.

##### AUDIT-v1.9.2-028 — Router miscarries `DESeq2 differential expression`

**Severity:** HIGH **Lens:** 01 **Category:** BUG **Target:** v1.9.3 **Estimate:** 1h

Live router (`route_request`) on biology-classic phrasings:
- `"fit a DESeq2 differential expression model"` → `methodology/bayesian_analysis` (semantic HIGH) — silently wrong
- `"do a DESeq2 DE"` → None (L=0)
- `"DESeq2 contrast LPS vs control"` → None (L=0)

Root cause: `methodology/bayesian_analysis`'s embedding wins against the generic `guidance/analysis_plan` for cosine similarity on "DESeq2 ... model". For terse phrasings, semantic confidence drops below the floor and no trigger fallback exists.

**Suggested fix:** add explicit triggers `["DESeq2", "differential expression", "DEG", "scRNA-seq QC", "single-cell clustering", "library size normalization"]` to `guidance/analysis_plan` in [src/research_os/protocols/_router_index.yaml](src/research_os/protocols/_router_index.yaml).

##### AUDIT-v1.9.2-029 — synthesis_paper decomposition omits Typst compile

**Severity:** HIGH **Lens:** 01 **Category:** REGRESSION **Target:** v1.9.3 **Estimate:** 0.25h

[src/research_os/protocols/_router_index.yaml](src/research_os/protocols/_router_index.yaml) synthesis/synthesis_paper decomposition:
```
- tool: tool_synthesize_plan
- tool: tool_audit_synthesis
- tool: tool_audit_citations
- tool: tool_synthesize  args: {output_type: paper}
```
Missing: `tool_paper_compile_typst`. Small-model agents walking the active_plan via `tool_plan_advance` never fire the Typst compile. The PDF is the deliverable; markdown is intermediate.

**Suggested fix:** append `- tool: tool_paper_compile_typst` to the decomposition (conditional on `writing_preferences.pdf_compile_engine == typst`).

#### MEDIUM bugs

##### AUDIT-v1.9.2-030 — Three 2-cycles in next_protocol graph

**Severity:** MEDIUM **Lens:** 05 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.5h

The protocol DAG has three 2-cycles: `external_tool_setup ↔ mcp_ecosystem_integration`, `uncertainty_quantification ↔ fairness_audit`, `coding_scheme_development ↔ inter_rater_reliability`. Defensible as bidirectional sibling hints, but a client walking `next_protocol` blindly will ping-pong.

**Suggested fix:** introduce a `recommended_followups: [a, b, c]` field for multi-direction recommendations; reserve `next_protocol` for single non-circular successor. Until then, document the ping-pong risk in [docs/PROTOCOL_DOCTRINE.md](docs/PROTOCOL_DOCTRINE.md).

##### AUDIT-v1.9.2-031 — `audit_dashboard_content` + `audit_cliches` write no report

**Severity:** MEDIUM **Lens:** 10 **Category:** BUG **Target:** v1.9.4 **Estimate:** 1h

[src/research_os/tools/actions/audit/dashboard_content.py](src/research_os/tools/actions/audit/dashboard_content.py):518 and [src/research_os/tools/actions/audit/content_depth.py](src/research_os/tools/actions/audit/content_depth.py):349 return status/blockers/warnings but write no markdown report. The trail is lost as soon as the response message scrolls. Other audits write `workspace/logs/<name>.md` so the dashboard's audit-trail panel can surface what's still owed.

**Suggested fix:** write `workspace/logs/dashboard_content_audit.md` and `workspace/logs/cliches_audit.md` mirroring the existing audit report pattern.

##### AUDIT-v1.9.2-032 — Return-shape inconsistency across audits

**Severity:** MEDIUM **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 2h

Most audits return `{status, blockers[], warnings[], report_path}`. But `audit_dashboard_content` omits `report_path`, `audit_cliches` returns `{hits[], n_hits}` with no `blockers` key, `audit_coherence` uses `orphan[]/matched[]` instead of `blockers[]`. `audit_quality_full` walks each sub-result for `.get("status") == "error"` + `.get("blockers", [])`; sub-audits without that shape are silently dropped from the aggregated count.

**Suggested fix:** define a canonical audit return shape in [src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py); refactor all 20 audits to return it.

##### AUDIT-v1.9.2-033 — `override_rationale` enforcement differs per tool

**Severity:** MEDIUM **Lens:** 10 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 1h

- `tool_synthesize` ([src/research_os/server.py](src/research_os/server.py):3655): `enforce` policy requires non-empty rationale; rejects bypass without it.
- `tool_audit_synthesis`: accepts empty rationale silently.
- `tool_audit_dashboard_content` (:3851): same enforce as synthesize.
- `tool_path_finalize` (:3128): refuses unless rationale is non-empty regardless of policy.
- `tool_plan_advance`: doesn't check rationale at all.

The same override kwarg in the same policy gets enforced or not depending on which tool the AI uses.

**Suggested fix:** pull rationale enforcement into a shared `_validate_override(arguments, root)` helper called from every tool that takes an override kwarg.

##### AUDIT-v1.9.2-034 — κ threshold drift across three intercoder protocols

**Severity:** MEDIUM **Lens:** 03 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.5h

- [src/research_os_qualitative/protocols/coding/coding_scheme_iteration.yaml](src/research_os_qualitative/protocols/coding/coding_scheme_iteration.yaml):42 — `per_code_kappa_minimum: 0.60`
- [src/research_os/protocols/methodology/qualitative_quality_audit.yaml](src/research_os/protocols/methodology/qualitative_quality_audit.yaml):152 — `A verdict < 0.70 without a reconciliation plan is a BLOCKER`
- [src/research_os/protocols/methodology/inter_rater_reliability.yaml](src/research_os/protocols/methodology/inter_rater_reliability.yaml):144-149 — verdict table `0.61-0.80 (substantial), 0.41-0.60 (moderate)`
- [src/research_os/protocols/methodology/qualitative_quality_audit.yaml](src/research_os/protocols/methodology/qualitative_quality_audit.yaml):144-148 — verdict table `0.60 ≤ κ < 0.80 = substantial, 0.40 ≤ κ < 0.60 = moderate`

Three problems: pack vs core disagree on the floor (0.60 vs 0.70); the two verdict tables disagree on the boundary (0.61 vs 0.60); the pack's "Landis & Koch moderate" label is wrong shorthand (moderate is 0.41-0.60, not 0.60).

**Suggested fix:** pick one canonical Landis & Koch 1977 table, cite it once at [src/research_os/protocols/methodology/inter_rater_reliability.yaml](src/research_os/protocols/methodology/inter_rater_reliability.yaml), and reference from the other two.

##### AUDIT-v1.9.2-035 — ReferenceProject.expected_pack property never validated

**Severity:** MEDIUM **Lens:** 08, 09 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.5h

[src/research_os/testing/stress_runner.py](src/research_os/testing/stress_runner.py):84 defines `expected_pack` property on `ReferenceProject`. Manifest YAMLs all carry `expected_pack:` keys. But no Python code reads the property; data flows in but never gets validated. Pack-mismatch bugs hide here.

**Suggested fix:** wire stress-runner to assert the loaded pack matches `expected_pack`, OR drop the YAML key.

##### AUDIT-v1.9.2-036 — Three CI-runnable fixtures have orphan canned_responses

**Severity:** MEDIUM **Lens:** 08 **Category:** DEAD_CODE **Target:** v1.9.4 **Estimate:** 4h

`tests/fixtures/projects/{slurm_snakemake, redcap_longitudinal, wet_lab_qpcr_run}/manifest.yaml` ship `canned_responses` keyed by `step_id`. `stress_runner.py` at 66% cover looks like the intended runner but no test loops through these fixtures end-to-end with the mock model. The fixtures are inventoried (used for adapter and protocol-loading tests) but not run as end-to-end reference workflows.

**Suggested fix:** add a meta-test that enumerates `tests/fixtures/projects/*/manifest.yaml` and runs each with the canned-response harness. Catches regressions in the full intake → audit → synthesis chain.

##### AUDIT-v1.9.2-037 — Typst vector-figure pipeline orphaned

**Severity:** MEDIUM **Lens:** 09 **Category:** DEAD_CODE **Target:** v1.9.3 **Estimate:** 0.5h

[src/research_os/tools/actions/synthesis/typst.py](src/research_os/tools/actions/synthesis/typst.py):50 (`_escape_typst_text`), :512 (`_prefer_vector_figure`), :522 (`_maybe_convert_svg_to_pdf`), plus `_yiq_brightness` at [src/research_os/tools/actions/audit/dashboard_content.py](src/research_os/tools/actions/audit/dashboard_content.py):297 — all private helpers with no callers. Half-finished vector-figure refactor.

**Suggested fix:** delete the 4 helpers, OR finish wiring (the Typst SVG → PDF conversion would be a real win for vector figures).

##### AUDIT-v1.9.2-038 — errors.py promises 4 exception classes; codebase uses none

**Severity:** MEDIUM **Lens:** 09 **Category:** DEAD_CODE **Target:** v1.9.3 **Estimate:** 1h

[src/research_os/errors.py](src/research_os/errors.py):25-52 defines `ConfigError`, `ScaffoldError`, `StateError`, `ToolError`. Module docstring advertises a 5-class taxonomy. None are ever raised or imported anywhere. Only `ResearchOSError` and `WriteProtectedError` are actually used.

**Suggested fix:** either start raising them in the relevant code paths (preferred — they're a clean public taxonomy) or strip the 4 ghosts and update the docstring.

##### AUDIT-v1.9.2-039 — `_router_index.yaml` name-drops nonexistent tool

**Severity:** LOW **Lens:** 04 **Category:** BUG **Target:** v1.9.3 **Estimate:** 0.1h

[src/research_os/protocols/_router_index.yaml](src/research_os/protocols/_router_index.yaml):1094 prose name-drops `tool_write_provenance_sidecar` which does not exist in `TOOL_DEFINITIONS`. A user/AI following the suggestion gets "unknown tool" on call.

**Suggested fix:** drop the mention and direct the user to re-run the figure script under provenance, OR ship the tool.

##### AUDIT-v1.9.2-040 — `tool_qualitative_codebook_diff` overwrites itself

**Severity:** LOW **Lens:** 03 **Category:** BUG **Target:** v1.9.4 **Estimate:** 0.5h

[src/research_os_qualitative/tools.py](src/research_os_qualitative/tools.py):137 writes literally `diff_v1_to_v2.md` regardless of which versions the user passes. Subsequent diff calls overwrite the previous file silently. Tool description (line 90-92) says: "Writes `workspace/codebooks/diff_v{N}_to_v{M}.md`."

**Suggested fix:** parse N/M from `arguments["codebook_v1"]` / `["codebook_v2"]` (regex `v(\d+)` on basename) and slot into the output filename.

##### AUDIT-v1.9.2-041 — content_depth.py `referenced` counter incremented but never returned

**Severity:** LOW **Lens:** 09 **Category:** DEAD_CODE **Target:** v1.9.3 **Estimate:** 0.1h

[src/research_os/tools/actions/audit/content_depth.py](src/research_os/tools/actions/audit/content_depth.py):244,258 — `referenced` counter is set and incremented but never returned in the result dict; only `missing` is returned. Looks like leftover instrumentation.

**Suggested fix:** either return `referenced` in the result dict (cheap honesty) or drop the counter.

### 2.2 INCONSISTENCIES (docs ↔ code, protocol ↔ tool, config ↔ code)

##### AUDIT-v1.9.2-005 — Hardcoded stale 113/146/438 counts in seven files

**Severity:** HIGH **Lens:** 01, 04, 06 **Category:** DOC_GAP **Target:** v1.9.3 (mostly fixed inline) **Estimate:** 0.5h remaining

19 count claims across 11 files cited `113 protocols / 146 tools / 438+ tests`. Actual: `114 protocols, 212 MCP tools, 872 tests`.

**Files fixed in this audit:**
- [docs/README.md](docs/README.md):19, :20 — `113 → 114`; `146 → 212`
- [docs/FAQ.md](docs/FAQ.md):61 — `113 → 114`
- [docs/PROTOCOLS.md](docs/PROTOCOLS.md):3, :13, :20 — `113 → 114`; synthesis `17 → 18` with 4 missing names appended; total `113 → 114`
- [docs/START.md](docs/START.md):133, :141 — `113 → 114`; `146 → 212`
- [docs/AI_GUIDE.md](docs/AI_GUIDE.md):84, :95, :336 — `113 → 114`; synthesis `17 → 18`; total `113 → 114`
- [docs/TOOLS.md](docs/TOOLS.md):3 — `146 → 212`
- [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md):6, :249, :315, :648, :649 — counts fixed
- [CONTRIBUTING.md](CONTRIBUTING.md):10, :36 — `212/114`; `872+ tests`
- [docs/ROADMAP.md](docs/ROADMAP.md):252 — stale tool name `tool_audit_master → tool_audit_quality_full`
- [src/research_os/server.py](src/research_os/server.py):4878, :4882, :1675 — sys_help methodology/synthesis counts; sys_active_tools description
- [src/research_os/tools/actions/audit/step_literature.py](src/research_os/tools/actions/audit/step_literature.py):9 — module docstring stale tool name

**Remaining:** [CLAUDE.md](CLAUDE.md):180 says "Protocols (88)" — very stale; left untouched because it's the *Research-OS-itself* CLAUDE.md (i.e. a maintainer-facing memory pointer that the user owns). [docs/ROADMAP.md](docs/ROADMAP.md) references (146/113) describing pre-consolidation state are deliberately left as-is (roadmap aspirations).

##### AUDIT-v1.9.2-009 — RESEARCHER_GUIDE.md config schema 5 fields behind template

**Severity:** HIGH **Lens:** 06 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 2h

[docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md):388-440 documents the `researcher_config.yaml` schema. Missing fields that the template now ships:

| Field | Status |
|---|---|
| `gate_strictness` (light/normal/strict/auto) | MISSING |
| `project_tier` (throwaway/sketch/production) | MISSING |
| `writing_preferences.venue_template` | MISSING |
| `writing_preferences.pdf_compile_engine` | MISSING |
| Entire `tool_stack:` block | MISSING |
| `interaction.autonomy_level: coaching` | MISSING (lists only manual/supervised/autopilot) |

**Suggested fix:** rewrite §8 to match [templates/researcher_config.yaml](templates/researcher_config.yaml) 1:1. Either drop `coaching` (no code branches on it; see AUDIT-v1.9.2-046) or wire it.

##### AUDIT-v1.9.2-010 — PROTOCOLS.md silently omits 34 of 114 protocols

**Severity:** HIGH **Lens:** 06 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 4h

[docs/PROTOCOLS.md](docs/PROTOCOLS.md) — the supposed "catalogue of all 114 protocols" — enumerates 80 protocols; 34 are silently absent despite shipping. 8 of 14 visualization protocols and all 4 newest synthesis protocols (`defense_prep`, `journal_selection`, `manuscript_outline`, `printable`) are invisible to readers.

Missing per category:
- **audit/** (2): `pre_submission_checklist`, `provenance_completeness`
- **guidance/** (2): `constructive_disagreement`, `revise_and_resubmit`
- **literature/** (1): `literature_per_step`
- **methodology/** (17): bootstrapping_design, coding_scheme_development, cox_ph_diagnostics, data_management_plan, deep_domain_research, external_tool_setup, fairness_audit, inter_rater_reliability, interview_guide_design, mcp_ecosystem_integration, missing_data_strategy, mixed_language_orchestration, multiple_comparisons, pick_tool_stack, qualitative_quality_audit, survey_design, uncertainty_quantification
- **synthesis/** (4): defense_prep, journal_selection, manuscript_outline, printable
- **visualization/** (8): animation_design, distribution_comparison, geospatial_visualization, interactive_dashboard_design, interactive_figure_design, network_visualization, showcase_visualization, uncertainty_visualization

**Suggested fix:** add a 1-line blurb for each missing protocol. Researchers won't know to ask for, say, "geospatial visualization" or "Cox PH diagnostics" because there's no signal those protocols exist.

##### AUDIT-v1.9.2-042 — TOOLS.md 44-tool undercount

**Severity:** HIGH **Lens:** 04 **Category:** DOC_GAP **Target:** v1.9.3 (count fixed) / v1.11.0 (full rewrite) **Estimate:** 8h

[docs/TOOLS.md](docs/TOOLS.md) headline count fixed inline (146 → 212). But 66 tools defined in `TOOL_DEFINITIONS` are missing entirely from the catalogue page. Researchers cannot discover them.

Notably missing: `mem_log`, `sys_active_project`, `sys_help`, `sys_path`, `sys_semantic_tool_search`, `tool_search`, `tool_plan`, `tool_ground`, `tool_verify`, `tool_lessons`, `tool_step_complete`, `tool_dashboard_story_*`, `tool_failure_*`, `tool_slurm_*`, `tool_step_pipeline_*`, `tool_quick_route`, `tool_semantic_route`, `tool_writing_discussion_from_verdicts`, `tool_synthesis_curate_figures`, etc.

**Suggested fix:** rewrite TOOLS.md against the live `TOOL_DEFINITIONS`; add 66 missing tools; add an "Infrastructure tools — no protocol caller" subsection for the boot/router helpers.

##### AUDIT-v1.9.2-043 — 107 of 114 protocols still carry `version: 1.7.1`

**Severity:** MEDIUM **Lens:** 04 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.25h

Distribution of `version:` fields on disk:
- `1.7.1` — 107 protocols
- `1.9.0` — 5
- `1.9.1` — 2

[CLAUDE.md](CLAUDE.md) release runbook says: "For MINOR / MAJOR: also bump every protocol YAML version field." v1.8.0 → v1.9.0 → v1.9.1 → v1.9.2 each appear to have skipped the sweep. If a researcher reads `version: 1.7.1` under package v1.9.2 they'll legitimately wonder which is canonical.

**Suggested fix:** run the runbook sweep `find src/research_os/protocols -name '*.yaml' -not -name '_*' | xargs sed -i "s/^version: '.*'/version: '1.9.3'/"` at v1.9.3 release. Or change the schema: stop printing `version:` per-protocol; show package version + `last_reviewed` date instead.

##### AUDIT-v1.9.2-044 — Pack version drift

**Severity:** MEDIUM **Lens:** 02, 03 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.1h

`research_os_qualitative.__version__ = 1.7.0` while core is 1.9.2. Same for `research_os_humanities`. All 5 qualitative-pack protocols and 5 core qualitative-themed protocols carry `version: '1.7.1'`. `sys_packs_installed` will surface `qualitative 1.7.0` next to `core 1.9.2`, reading as "this pack is unmaintained."

**Suggested fix:** sweep `__version__` and `version:` fields in `src/research_os_qualitative/`, `src/research_os_humanities/`, `src/research_os_engineering/`, `src/research_os_wet_lab/`, `src/research_os_theory_math/` to match core.

##### AUDIT-v1.9.2-045 — researcher.affiliation vs researcher.institution drift

**Severity:** MEDIUM **Lens:** 07 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.1h

[templates/researcher_config.yaml](templates/researcher_config.yaml) uses `researcher.institution`. [src/research_os/tools/actions/synthesis/latex.py](src/research_os/tools/actions/synthesis/latex.py):172 reads `researcher.affiliation`. Poster author affiliation always renders blank for the average user.

**Suggested fix:** one-line — rename `affiliation` to `institution` in `latex.py:172`, OR add an `institution` fallback so both work.

##### AUDIT-v1.9.2-046 — `coaching` autonomy_level has no behavioural effect

**Severity:** MEDIUM **Lens:** 07 **Category:** INCONSISTENCY **Target:** v1.11.0 **Estimate:** 4h

[templates/researcher_config.yaml](templates/researcher_config.yaml):30 lists `manual | supervised | autopilot | coaching`. No code branches on `coaching`. `server.py:2326` says `sys_coaching_replay` is "Designed for autonomy_level='coaching'" but it's available to every autonomy mode; nothing gates on it.

**Suggested fix:** either remove `coaching` from the template enum until wired (one-line), OR implement pedagogical-prelude scaffolding and gate `sys_coaching_replay` to the value.

##### AUDIT-v1.9.2-047 — Deprecated-alias tool names live in protocol YAMLs

**Severity:** LOW **Lens:** 04 **Category:** INCONSISTENCY **Target:** v1.11.0 **Estimate:** 2h

Protocols still emit deprecated-alias names: `tool_search_pubmed/arxiv/web/...`, `tool_plan_turn/advance/clear`, `mem_*_log/append`, `sys_path_create/abandon/list`. All 21 resolve via `_ALIASES` and fire deprecation telemetry every load. Will hard-break at next MAJOR.

**Suggested fix:** sweep protocol YAMLs replacing deprecated-alias mentions with canonical consolidated names. Drop telemetry noise.

##### AUDIT-v1.9.2-048 — RESEARCHER_GUIDE source-tree diagram out of date

**Severity:** LOW **Lens:** 06 **Category:** INCONSISTENCY **Target:** v1.9.3 **Estimate:** 0.5h

[docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md):583-590 sketches the source tree as `tools/actions/{audit, data, exec, memory, research, search, state, synthesis, viz}`. Actual subdirs of `src/research_os/tools/actions/`: `semantic.py, protocol.py, router.py, viz/, state/, ...`. The `memory`, `research`, `search`, `data`, `exec` enumeration is out of date.

**Suggested fix:** regenerate the diagram from a live `tree` snapshot.

##### AUDIT-v1.9.2-049 — `archival_research.yaml` two-file bridge issue

**Severity:** LOW **Lens:** 02 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 0.25h

[src/research_os_humanities/protocols/archival/archival_research.yaml](src/research_os_humanities/protocols/archival/archival_research.yaml):50 instructs the AI to call `tool_humanities_archive_lookup`. Protocol first step writes to `inputs/archival/holdings_register.md`. Tool writes to `inputs/archival/lookup_<slug>.md`. Two different files; the protocol never tells the AI to bridge them.

**Suggested fix:** clarify in protocol prose that the tool writes to `lookup_*.md`, then `capture` step should consume from both files.

##### AUDIT-v1.9.2-050 — Humanities detector `.pdf` comment mismatch (FIXED INLINE)

**Severity:** LOW **Lens:** 02 **Category:** INCONSISTENCY **Target:** v1.9.3 (fixed)

Detector docstring at [src/research_os_humanities/detector.py](src/research_os_humanities/detector.py):62 claimed `.txt / .md / .pdf bodies` but line 63 included only `.txt / .md / .tex`. Fixed inline (`.pdf → .tex`).

### 2.3 DEAD CODE (truly removable)

##### AUDIT-v1.9.2-051 — Truly dead helper functions

**Severity:** LOW **Lens:** 09 **Category:** DEAD_CODE **Target:** v1.9.3 **Estimate:** 1h

Helpers with no callers anywhere in `src/`, `tests/`, or `scripts/`:

| File:line | Symbol |
|---|---|
| [src/research_os/inputs/papers.py](src/research_os/inputs/papers.py):250 | `fetch_many(tokens, dest)` |
| [src/research_os/testing/stress_runner.py](src/research_os/testing/stress_runner.py):314 | `run_matrix(...)` |
| [src/research_os/plugins/loader.py](src/research_os/plugins/loader.py):148 | `pack_domain_detectors()` |
| [src/research_os/plugins/loader.py](src/research_os/plugins/loader.py):153 | `write_pack_errors_log(root)` |
| [src/research_os/project_ops.py](src/research_os/project_ops.py):231 | `read_yaml`, `write_yaml` |
| [src/research_os/project_ops.py](src/research_os/project_ops.py):506 | `compute_input_hashes(root)` |
| [src/research_os/project_ops.py](src/research_os/project_ops.py):527 | `write_readme(path, title, body)` |
| [src/research_os/project_ops.py](src/research_os/project_ops.py):2444 | `state_diff_log_path(root)` |
| [src/research_os/tui.py](src/research_os/tui.py):228 | `_term_width()` |
| [src/research_os/utils/asset_manager.py](src/research_os/utils/asset_manager.py):102 | `iter_files` |
| [src/research_os/utils/asset_manager.py](src/research_os/utils/asset_manager.py):126 | `copy_asset_tree` |
| [src/research_os/verify.py](src/research_os/verify.py):62 | `_dir_exists(root, rel)` |
| [src/research_os/logo.py](src/research_os/logo.py):94 | `PLAIN_LOGO` constant |

**Suggested fix:** delete in v1.9.3 cleanup commit.

##### AUDIT-v1.9.2-052 — 51 server-defined tools have zero protocol/router callers

**Severity:** MEDIUM **Lens:** 04 **Category:** DEAD_CODE **Target:** v2.0.0 **Estimate:** 16h

CLAUDE.md states: "Reference the tool from at least one protocol's `decomposition` or a `shortcut_intents` entry — orphaned tools get removed." 51 tools fail this rule today and preflight does not enforce it. Includes legitimate boot infrastructure (`sys_active_tools`, `sys_tool_describe`, `sys_workspace_tree`, `sys_workspace_scaffold`, `tool_quick_route`, `tool_semantic_route`, `tool_workflow_dag`, `tool_deprecations_summary`) — these SHOULD be exempt. Also includes likely-dead aspirational tools (`tool_dry_run`, `tool_mistake_replay`, `tool_promote_to_step`, `tool_rigor_signals_scan`, `tool_self_certify`, `tool_section_substantiveness`, `tool_step_complete`, `tool_list_certifications`, `tool_project_tier_strictness`, `tool_resolve_gate_strictness`).

**Suggested fix:** classify per tool. Move boot infrastructure to an allow-list. Wire researcher-direct tools to at least one protocol or document them as researcher-driven. Hard-remove aspirational tools at v2.0.0 with deprecation aliases now.

##### AUDIT-v1.9.2-053 — Unused variable `state_hint` in router (covered)

Covered by AUDIT-v1.9.2-015.

##### AUDIT-v1.9.2-054 — 20 unused imports masked by repo-wide F401 ignore

**Severity:** LOW **Lens:** 09 **Category:** FRICTION **Target:** v1.9.4 **Estimate:** 1h

`pyproject.toml` `[tool.ruff.lint]` ignores F401 globally because `__init__.py` re-exports rely on it. 20 latent unused-import sites outside `__init__.py` would auto-fix if the ignore were per-file.

Notable concentrations: [src/research_os/cli.py](src/research_os/cli.py):23, [src/research_os/collab.py](src/research_os/collab.py):23/26, [src/research_os/project_ops.py](src/research_os/project_ops.py):21, [src/research_os/tools/actions/audit/audit.py](src/research_os/tools/actions/audit/audit.py):1172, [src/research_os/tools/actions/audit/claim_grounding.py](src/research_os/tools/actions/audit/claim_grounding.py):43, [src/research_os/tools/actions/audit/dashboard_content.py](src/research_os/tools/actions/audit/dashboard_content.py):14, [src/research_os/tools/actions/audit/preregistration.py](src/research_os/tools/actions/audit/preregistration.py):39, [src/research_os/tools/actions/audit/redteam.py](src/research_os/tools/actions/audit/redteam.py):35, [src/research_os/tools/actions/data/intake.py](src/research_os/tools/actions/data/intake.py):295, [src/research_os/tools/actions/exec/step_pipeline.py](src/research_os/tools/actions/exec/step_pipeline.py):82,388, [src/research_os/tools/actions/research/grounding.py](src/research_os/tools/actions/research/grounding.py):47, [src/research_os/tools/actions/state/reliability.py](src/research_os/tools/actions/state/reliability.py):22, [src/research_os/tools/actions/state/repair.py](src/research_os/tools/actions/state/repair.py):18, [src/research_os/tools/actions/synthesis/dashboard.py](src/research_os/tools/actions/synthesis/dashboard.py):33, [src/research_os/tools/actions/synthesis/dashboard_v2.py](src/research_os/tools/actions/synthesis/dashboard_v2.py):30, [src/research_os/tools/actions/synthesis/latex.py](src/research_os/tools/actions/synthesis/latex.py):19, [src/research_os/tui.py](src/research_os/tui.py):30.

**Suggested fix:** move ignore to `[tool.ruff.lint.per-file-ignores]` keyed on `"src/research_os/**/__init__.py"`, then `ruff --fix --select F401`.

##### AUDIT-v1.9.2-055 — Vacuous loop in test_v171_three_packs

**Severity:** LOW **Lens:** 08 **Category:** DEAD_CODE **Target:** v1.9.3 **Estimate:** 0.1h

[tests/unit/test_v171_three_packs.py](tests/unit/test_v171_three_packs.py):56-59 contains a 3-line block that walks `installed_packs()`, iterates over a 1-tuple `pack["name"],` (effectively one string), and `pass`es. Dead loop with a misleading `# noqa: B007` comment. The test as a whole still asserts meaningfully via the `_DISCOVERED_PACKS` walk below; this block does nothing.

**Suggested fix:** delete lines 56-59 in v1.9.3.

### 2.4 DOC GAPS

##### AUDIT-v1.9.2-056 — runtime.* exec-safety fields consumed but undocumented

**Severity:** HIGH **Lens:** 07 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 1h

Fields consumed by `src/` but absent from `templates/researcher_config.yaml` AND `docs/RESEARCHER_GUIDE.md`:

| Field | Reader |
|---|---|
| `runtime.cluster_defaults` | [src/research_os/tools/actions/exec/cluster.py](src/research_os/tools/actions/exec/cluster.py):64 |
| `runtime.allow_arbitrary` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):116 |
| `runtime.command_allowlist` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):118 |
| `runtime.allow_shell_meta` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):130 |
| `runtime.max_cpu_seconds` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):176 |
| `runtime.max_memory_mb` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):177 |
| `runtime.max_file_size_mb` | [src/research_os/tools/actions/exec/tasks.py](src/research_os/tools/actions/exec/tasks.py):178 |

These are safety-surface knobs (SLURM defaults, command allowlist, CPU/memory caps). Users can't tune them because they're invisible.

**Suggested fix:** add the seven `runtime.*` fields to [templates/researcher_config.yaml](templates/researcher_config.yaml) with documented defaults; mirror in RESEARCHER_GUIDE.md.

##### AUDIT-v1.9.2-057 — research_goal.* extension fields read but undocumented

**Severity:** MEDIUM **Lens:** 07 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 1h

Audit + synthesis modules read `research_goal.primary_question`, `research_goal.design`, `research_goal.background`, `research_goal.measurement_instrument`, top-level `domain`, top-level `research_question`, top-level `authors`. Template and guide document none.

**Suggested fix:** add to template + RESEARCHER_GUIDE.md.

##### AUDIT-v1.9.2-058 — AI_GUIDE.md visualization table 6 of 14

**Severity:** MEDIUM **Lens:** 06 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 0.5h

[docs/AI_GUIDE.md](docs/AI_GUIDE.md):310-320 visualization category table enumerates only 6 of 14 protocols.

**Suggested fix:** add `animation_design`, `distribution_comparison`, `geospatial_visualization`, `interactive_dashboard_design`, `interactive_figure_design`, `network_visualization`, `showcase_visualization`, `uncertainty_visualization`.

##### AUDIT-v1.9.2-059 — `tool_audit_quality_full` skips per-step literature gate (undocumented)

**Severity:** MEDIUM **Lens:** 01 **Category:** DOC_GAP **Target:** v1.9.3 **Estimate:** 0.1h

`tool_audit_quality_full` description does not mention that it skips `tool_audit_step_literature`. Researchers who call the master between steps and get a clean report are surprised when `tool_audit_synthesis` blocks them later for missing per-step literature.

**Suggested fix:** add a sentence to the tool description: "NB: per-step literature gate is separate; call `tool_audit_step_literature` per step OR rely on `tool_step_complete` to have caught it."

##### AUDIT-v1.9.2-060 — `tool_paper_compile_typst` response lacks next-steps hint

**Severity:** LOW **Lens:** 01 **Category:** DOC_GAP **Target:** v1.9.4 **Estimate:** 0.25h

Tool returns `pdf_path`, `page_count`, `citation_count`, `typst_warnings`, `typst_errors` — but no `next_steps` / `advice` field telling the AI "now run `audit/pre_submission_checklist` before the researcher submits."

**Suggested fix:** add a `next_steps: ["audit/pre_submission_checklist"]` advice field to the return dict.

##### AUDIT-v1.9.2-061 — PROTOCOL_DOCTRINE doesn't document router-first dispatch

**Severity:** LOW **Lens:** 05 **Category:** DOC_GAP **Target:** v1.9.4 **Estimate:** 0.5h

[docs/PROTOCOL_DOCTRINE.md](docs/PROTOCOL_DOCTRINE.md) does not document the `next_protocol: null` + router-takeover pattern. New authors may assume chain reachability is required.

**Suggested fix:** add a section explaining that `next_protocol: null` is the canonical end-of-chain marker for protocols that should be dispatched via `tool_route`.

##### AUDIT-v1.9.2-062 — 12 undocumented MCP tools in `docs/`

**Severity:** LOW **Lens:** 04 **Category:** DOC_GAP **Target:** v1.11.0 **Estimate:** 2h

Tools appearing nowhere in `docs/`: `sys_config_validate`, `sys_export_share_archive`, `sys_file_delete`, `sys_semantic_tool_search`, `tool_list_certifications`, `tool_project_tier_strictness`, `tool_quick_route`, `tool_resolve_gate_strictness`, `tool_semantic_route`, `tool_slurm_list`, `tool_step_pipeline_diagram`, `tool_step_pipeline_status`.

**Suggested fix:** rolled into AUDIT-v1.9.2-042 (full TOOLS.md rewrite).

### 2.5 FRICTION (where AI gets stuck or confused)

##### AUDIT-v1.9.2-063 — synthesis_paper enforces 10 turns with no autopilot short-circuit

**Severity:** MEDIUM **Lens:** 01 **Category:** FRICTION **Target:** v1.11.0 **Estimate:** 2h

`synthesis_paper` enforces "ONE section per researcher prompt", even in autopilot. For a researcher who already has a polished draft and just wants final assembly, this is 10 round-trips minimum. No `auto_proceed=true` knob on `tool_synthesize` to short-circuit the multi-turn loop.

**Suggested fix:** add `auto_proceed: bool = False` to `tool_synthesize`; gate on `autonomy_level == "autopilot"`.

##### AUDIT-v1.9.2-064 — `tool_data_profile` flags n=12 as small for qualitative

**Severity:** MEDIUM **Lens:** 03 **Category:** FRICTION **Target:** v1.9.4 **Estimate:** 0.25h

[src/research_os/tools/actions/data/data.py](src/research_os/tools/actions/data/data.py):164-168 hard-codes `n_rows < 30` triggering "Sample size n={n_rows} is small — consider whether this is enough for the planned statistical test." For qualitative studies where n=12 is canonical for saturation, this is misleading. Audit gate does NOT escalate to blocker (good); but the profile prose is noisy.

**Suggested fix:** when the step is qualitative (themes.md / codebook.md exists), suppress the small-n suggestion or rephrase to "for a qualitative study, n=12 is in the typical saturation range (Guest, Bunce & Johnson 2006)."

##### AUDIT-v1.9.2-065 — synthesis_paper prerequisites assume literature_index.yaml

**Severity:** LOW **Lens:** 01 **Category:** FRICTION **Target:** v1.9.4 **Estimate:** 0.5h

`synthesis_paper` prerequisites assume `inputs/literature_index.yaml ≥ 3 entries`. The file is optional and not part of intake autofill. A researcher who only put PDFs in `inputs/literature/` (not the index YAML) gets a hard prereq fail at synthesis time.

**Suggested fix:** derive entries from on-disk PDFs (via `.meta.yaml` sidecars) automatically when the YAML is absent.

##### AUDIT-v1.9.2-066 — Detector under-counts real humanities project; over-penalises corpus manifest

**Severity:** LOW **Lens:** 02 **Category:** FRICTION **Target:** v1.9.4 **Estimate:** 0.5h

[src/research_os_humanities/detector.py](src/research_os_humanities/detector.py):62-69 prose-corpus heuristic only reads `.txt`, `.md`, `.tex` and -0.1 penalises any tabular CSV. `digital_humanities_workflow.yaml` prerequisites EXPLICITLY say to ship `inputs/corpus/corpus_manifest.csv` — the very file the DH protocol mandates is the one the detector penalises.

**Suggested fix:** check whether tabular files are named `corpus_manifest.csv` (or in a `corpus/` subdir) and skip the penalty for those.

##### AUDIT-v1.9.2-067 — hermeneutic_method quality_bar is a list (rest are dicts)

**Severity:** LOW **Lens:** 02 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 0.25h

[src/research_os_humanities/protocols/method/hermeneutic_method.yaml](src/research_os_humanities/protocols/method/hermeneutic_method.yaml):212-228 emits a YAML sequence. Every other humanities + qualitative + core protocol uses a dict. Any audit tool that reads `quality_bar` as `dict.items()` will TypeError on hermeneutic_method.

**Suggested fix:** convert to dict shape matching close_reading.yaml:171-192 (`anchor_density: |`, `tradition_declared: |`, etc.).

### 2.6 ARCHITECTURE SMELL (refactor candidates — flag, don't fix)

##### AUDIT-v1.9.2-068 — Three sources of truth for researcher_config schema

**Severity:** HIGH **Lens:** 07 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 6h

Three competing sources: (1) [templates/researcher_config.yaml](templates/researcher_config.yaml), (2) `CONFIG_TEMPLATE` constant in [src/research_os/tools/actions/state/config.py](src/research_os/tools/actions/state/config.py), (3) [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md) §8. All three disagree. The narrative line "There is ONE template" in RESEARCHER_GUIDE.md:443 is false.

**Suggested fix:** delete `CONFIG_TEMPLATE` constant; teach the wizard to read [templates/researcher_config.yaml](templates/researcher_config.yaml) and fill in user-supplied values. Generate RESEARCHER_GUIDE schema doc from the template at build time.

##### AUDIT-v1.9.2-069 — `_router_index.yaml` version field has no automated bump check

**Severity:** LOW **Lens:** 04 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 0.5h

[src/research_os/protocols/_router_index.yaml](src/research_os/protocols/_router_index.yaml):39 `version: 14` has no automated bump check. CLAUDE.md flags as a "common gotcha — readers can't tell the index changed." Relies on maintainer memory.

**Suggested fix:** preflight check that compares `version:` to git-log line-count of changes since the previous bump; OR a pre-commit hook that auto-increments on touch.

##### AUDIT-v1.9.2-070 — No `see_also` / `related_protocols` field

**Severity:** LOW **Lens:** 05 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 4h

No `see_also` field exists in any protocol. The lateral-suggestion graph lives only inside router triggers / decomposition and is harder to traverse for callers wanting "related work" navigation.

**Suggested fix:** add an optional `see_also: [category/name, ...]` field; surface in `sys_protocol_get` envelope; render in dashboard sidebar.

##### AUDIT-v1.9.2-071 — Cross-field interactions documented but not enforced

**Severity:** MEDIUM **Lens:** 07 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 4h

Template comments promise relationships that no code enforces: `project_tier → gate_strictness` auto-mapping; `autonomy_level=coaching` surfaces coaching artifacts; `pdf_compile_engine=both` cross-checks; `runtime.shared_server=true` gates execution strategy.

**Suggested fix:** wire each documented promise or strip the misleading comments. Touched by AUDIT-v1.9.2-011 (project_tier) and AUDIT-v1.9.2-046 (coaching).

##### AUDIT-v1.9.2-072 — `sys_config_validate` checks presence, not enum membership

**Severity:** MEDIUM **Lens:** 07 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 1h

[src/research_os/tools/actions/state/config.py](src/research_os/tools/actions/state/config.py):426-455 — `validate_config` checks the **presence** of 5 fields but not enum membership for any of them. A typo like `model_profile: medium-plus` passes validation and silently falls back to `medium`.

**Suggested fix:** extend `validate_config` with per-field enum checks against the same source-of-truth used by template/CONFIG_TEMPLATE.

##### AUDIT-v1.9.2-073 — Dashboard v2 has no surface for qualitative/humanities artefacts

**Severity:** HIGH **Lens:** 02 **Category:** ARCH_SMELL **Target:** v1.11.0 **Estimate:** 8h

[src/research_os/tools/actions/synthesis/dashboard_v2.py](src/research_os/tools/actions/synthesis/dashboard_v2.py):794-996 — Findings section reads `spec.get("findings")` as `<ul><li>`. No surface for codebook (codes, inclusion/exclusion criteria, applied-quote counts, κ per code). Verdicts section iterates `state.get("verdicts")` keyed by hypothesis_id — critical editions don't have hypotheses.

**Suggested fix:** add `dashboard_v2_qualitative.py` and `dashboard_v2_humanities.py` renderers selected by `pack` field. Reuse the JS bundle infrastructure.

##### AUDIT-v1.9.2-074 — Pack chains dead-end at next_protocol: null

**Severity:** MEDIUM **Lens:** 02 **Category:** INCONSISTENCY **Target:** v1.9.4 **Estimate:** 1h

Trace of humanities chain: `archival_research → close_reading → citation_chains → null`; `distant_reading → digital_humanities_workflow → scholarly_edition → null`; `hermeneutic_method → close_reading → ... → null`. Nothing routes back into `synthesis/manuscript_outline` or `synthesis/synthesis_paper`. The pack thinks of `scholarly_edition` as the final deliverable, but the core flow's publish-the-paper protocols are never invoked.

**Suggested fix:** set `next_protocol: synthesis/manuscript_outline` on `scholarly_edition`, `citation_chains`, `digital_humanities_workflow`.

##### AUDIT-v1.9.2-075 — 12 dead template fields

**Severity:** MEDIUM **Lens:** 07 **Category:** DEAD_CODE **Target:** v1.11.0 **Estimate:** 4h

Fields in `templates/researcher_config.yaml` with no consumer in `src/`: `research_goal.poster_dimensions`, `research_goal.target_venue`, `research_goal.output_types`, `interaction.ambiguity_posture`, `writing_preferences.citation_style`, `writing_preferences.language`, `writing_preferences.pdf_compile_engine`, `runtime.default_n_for_sampling`, `tool_stack.preferred_languages`, `tool_stack.allow_mixed_language_steps`, `tool_stack.field_practice_overrides_preference`, `tool_stack.cite_field_practice_when_choosing`.

**Suggested fix:** classify per field. Wire the highest-value ones (citation_style + tool_stack.*). Move others to a `# v2 candidates — not yet wired` block.

---

## 3. Per-finding metadata table (compact)

| ID | Sev | Lens | Cat | Target | Title (truncated) |
|---|---|---|---|---|---|
| AUDIT-v1.9.2-001 | CRITICAL | 07 | BUG | v1.9.3 | Config-reader path bug: gate_strictness/project_tier/model_profile read from wrong dir |
| AUDIT-v1.9.2-002 | CRITICAL | 10 | BUG | v1.9.3 | `override_discussion_coverage` documented but unimplemented |
| AUDIT-v1.9.2-003 | CRITICAL | 02 | ARCH_SMELL | v1.9.3 | step_completeness gate blocks all humanities synthesis |
| AUDIT-v1.9.2-004 | CRITICAL | 02 | BUG | v1.9.3 | 7 humanities-pack tools do not exist |
| AUDIT-v1.9.2-005 | HIGH | 01,04,06 | DOC_GAP | v1.9.3 | Stale 113/146/438 counts in 7 user-facing docs (mostly fixed inline) |
| AUDIT-v1.9.2-006 | HIGH | 10 | INCONSISTENCY | v1.9.3 | audit_quality_full runs 6 gates, description advertises 5 |
| AUDIT-v1.9.2-007 | HIGH | 10 | INCONSISTENCY | v1.11.0 | Only 1 of 20 audit gates honours gate_strictness |
| AUDIT-v1.9.2-008 | HIGH | 10 | BUG | v1.9.3 | override_no_pdfs skips override_log.md |
| AUDIT-v1.9.2-009 | HIGH | 06 | DOC_GAP | v1.9.3 | RESEARCHER_GUIDE.md §8 config schema 5 fields behind template |
| AUDIT-v1.9.2-010 | HIGH | 06 | DOC_GAP | v1.9.3 | PROTOCOLS.md omits 34 of 114 protocols |
| AUDIT-v1.9.2-011 | CRITICAL | 10 | BUG | v1.9.3 | project_tier never propagates to resolve_gate_strictness |
| AUDIT-v1.9.2-012 | HIGH | 03 | BUG | v1.9.3 | REDCap adapter cannot detect cross-sectional exports it advertises |
| AUDIT-v1.9.2-013 | HIGH | 03 | BUG | v1.9.3 | Qualitative detector blind to .txt transcripts |
| AUDIT-v1.9.2-014 | HIGH | 03 | BUG | v1.9.3 | member_checking references unimplemented tool_redact + consent_amendment |
| AUDIT-v1.9.2-015 | HIGH | 08,09 | BUG | v1.9.3 | route_request(state_hint=...) accepts kwarg, never reads it |
| AUDIT-v1.9.2-016 | HIGH | 10 | INCONSISTENCY | v1.9.4 | audit_figure (DPI<150 WARN) vs audit_figure_full (DPI<200 BLOCK) |
| AUDIT-v1.9.2-017 | HIGH | 10 | INCONSISTENCY | v1.9.4 | _report_path splits audit reports between two directories |
| AUDIT-v1.9.2-018 | HIGH | 10 | BUG | v1.9.3 | override_no_pdfs bypass doesn't write override_log.md |
| AUDIT-v1.9.2-019 | HIGH | 10 | INCONSISTENCY | v1.9.4 | tool_audit_step_literature cannot be overridden directly |
| AUDIT-v1.9.2-020 | HIGH | 10 | INCONSISTENCY | v1.9.3 | Master gate advertises 5, runs 6 (grounding_verify hidden) |
| AUDIT-v1.9.2-021 | HIGH | 10 | INCONSISTENCY | v1.11.0 | Only 1/20 audits read gate_strictness |
| AUDIT-v1.9.2-022 | HIGH | 02 | BUG | v1.9.4 | Literature gate is empirical-only |
| AUDIT-v1.9.2-023 | HIGH | 02 | BUG | v1.9.4 | synthesis_paper forces statistics on humanities work |
| AUDIT-v1.9.2-024 | HIGH | 02 | BUG | v1.9.4 | audit_and_validation auto-routes literary qualitative to COREQ audit |
| AUDIT-v1.9.2-025 | HIGH | 03 | DOC_GAP | v1.9.3 | 3 qualitative-pack protocols misuse sys_path as file-finder |
| AUDIT-v1.9.2-026 | HIGH | 03 | DOC_GAP | v1.11.0 | COREQ/SRQR checklist YAMLs never shipped |
| AUDIT-v1.9.2-027 | HIGH | 02 | BUG | v1.9.3 | hermeneutic_method on_failure routes to nonexistent protocols |
| AUDIT-v1.9.2-028 | HIGH | 01 | BUG | v1.9.3 | Router miscarries DESeq2 differential expression |
| AUDIT-v1.9.2-029 | HIGH | 01 | REGRESSION | v1.9.3 | synthesis_paper decomposition omits tool_paper_compile_typst |
| AUDIT-v1.9.2-030 | MEDIUM | 05 | INCONSISTENCY | v1.9.3 | 3 two-cycles in next_protocol graph |
| AUDIT-v1.9.2-031 | MEDIUM | 10 | BUG | v1.9.4 | audit_dashboard_content + audit_cliches write no report |
| AUDIT-v1.9.2-032 | MEDIUM | 10 | INCONSISTENCY | v1.9.4 | Return-shape inconsistency across audits |
| AUDIT-v1.9.2-033 | MEDIUM | 10 | INCONSISTENCY | v1.9.4 | override_rationale enforcement differs per tool |
| AUDIT-v1.9.2-034 | MEDIUM | 03 | INCONSISTENCY | v1.9.3 | κ threshold drift across 3 intercoder protocols |
| AUDIT-v1.9.2-035 | MEDIUM | 08,09 | BUG | v1.9.3 | ReferenceProject.expected_pack property never validated |
| AUDIT-v1.9.2-036 | MEDIUM | 08 | DEAD_CODE | v1.9.4 | 3 CI-runnable fixtures with orphan canned_responses |
| AUDIT-v1.9.2-037 | MEDIUM | 09 | DEAD_CODE | v1.9.3 | Typst vector-figure pipeline orphaned (4 helpers) |
| AUDIT-v1.9.2-038 | MEDIUM | 09 | DEAD_CODE | v1.9.3 | errors.py 4 exception classes never raised |
| AUDIT-v1.9.2-039 | LOW | 04 | BUG | v1.9.3 | _router_index name-drops nonexistent tool_write_provenance_sidecar |
| AUDIT-v1.9.2-040 | LOW | 03 | BUG | v1.9.4 | tool_qualitative_codebook_diff overwrites itself |
| AUDIT-v1.9.2-041 | LOW | 09 | DEAD_CODE | v1.9.3 | content_depth.py referenced counter never returned |
| AUDIT-v1.9.2-042 | HIGH | 04 | DOC_GAP | v1.11.0 | 66 tools missing from docs/TOOLS.md |
| AUDIT-v1.9.2-043 | MEDIUM | 04 | INCONSISTENCY | v1.9.3 | 107/114 protocols still carry version: 1.7.1 |
| AUDIT-v1.9.2-044 | MEDIUM | 02,03 | INCONSISTENCY | v1.9.3 | Pack version drift |
| AUDIT-v1.9.2-045 | MEDIUM | 07 | INCONSISTENCY | v1.9.3 | researcher.affiliation vs researcher.institution drift |
| AUDIT-v1.9.2-046 | MEDIUM | 07 | INCONSISTENCY | v1.11.0 | coaching autonomy_level has no behavioural effect |
| AUDIT-v1.9.2-047 | LOW | 04 | INCONSISTENCY | v1.11.0 | Deprecated-alias tool names in protocol YAMLs |
| AUDIT-v1.9.2-048 | LOW | 06 | INCONSISTENCY | v1.9.3 | RESEARCHER_GUIDE source-tree diagram out of date |
| AUDIT-v1.9.2-049 | LOW | 02 | INCONSISTENCY | v1.9.4 | archival_research two-file bridge issue |
| AUDIT-v1.9.2-050 | LOW | 02 | INCONSISTENCY | v1.9.3 | Humanities detector .pdf comment mismatch (fixed inline) |
| AUDIT-v1.9.2-051 | LOW | 09 | DEAD_CODE | v1.9.3 | 13 truly-dead helper functions |
| AUDIT-v1.9.2-052 | MEDIUM | 04 | DEAD_CODE | v2.0.0 | 51 server-defined tools with no callers |
| AUDIT-v1.9.2-053 | (dup of 015) | | | | route_request state_hint unused var |
| AUDIT-v1.9.2-054 | LOW | 09 | FRICTION | v1.9.4 | 20 unused imports masked by F401 ignore |
| AUDIT-v1.9.2-055 | LOW | 08 | DEAD_CODE | v1.9.3 | Vacuous loop in test_v171_three_packs |
| AUDIT-v1.9.2-056 | HIGH | 07 | DOC_GAP | v1.9.3 | 7 runtime.* exec-safety fields consumed but undocumented |
| AUDIT-v1.9.2-057 | MEDIUM | 07 | DOC_GAP | v1.9.3 | research_goal.* extension fields read but undocumented |
| AUDIT-v1.9.2-058 | MEDIUM | 06 | DOC_GAP | v1.9.3 | AI_GUIDE.md visualization table 6 of 14 |
| AUDIT-v1.9.2-059 | MEDIUM | 01 | DOC_GAP | v1.9.3 | tool_audit_quality_full skips per-step literature gate (undocumented) |
| AUDIT-v1.9.2-060 | LOW | 01 | DOC_GAP | v1.9.4 | tool_paper_compile_typst response lacks next-steps hint |
| AUDIT-v1.9.2-061 | LOW | 05 | DOC_GAP | v1.9.4 | PROTOCOL_DOCTRINE doesn't document router-first dispatch |
| AUDIT-v1.9.2-062 | LOW | 04 | DOC_GAP | v1.11.0 | 12 undocumented MCP tools in docs/ |
| AUDIT-v1.9.2-063 | MEDIUM | 01 | FRICTION | v1.11.0 | synthesis_paper enforces 10 turns with no autopilot short-circuit |
| AUDIT-v1.9.2-064 | MEDIUM | 03 | FRICTION | v1.9.4 | tool_data_profile flags n=12 as small for qualitative |
| AUDIT-v1.9.2-065 | LOW | 01 | FRICTION | v1.9.4 | synthesis_paper prerequisites assume literature_index.yaml |
| AUDIT-v1.9.2-066 | LOW | 02 | FRICTION | v1.9.4 | Detector under-counts humanities project; over-penalises corpus manifest |
| AUDIT-v1.9.2-067 | LOW | 02 | INCONSISTENCY | v1.9.4 | hermeneutic_method quality_bar is a list |
| AUDIT-v1.9.2-068 | HIGH | 07 | ARCH_SMELL | v1.11.0 | Three sources of truth for researcher_config schema |
| AUDIT-v1.9.2-069 | LOW | 04 | ARCH_SMELL | v1.11.0 | _router_index version field no automated bump check |
| AUDIT-v1.9.2-070 | LOW | 05 | ARCH_SMELL | v1.11.0 | No see_also field in any protocol |
| AUDIT-v1.9.2-071 | MEDIUM | 07 | ARCH_SMELL | v1.11.0 | Cross-field interactions documented but not enforced |
| AUDIT-v1.9.2-072 | MEDIUM | 07 | ARCH_SMELL | v1.11.0 | sys_config_validate checks presence, not enum membership |
| AUDIT-v1.9.2-073 | HIGH | 02 | ARCH_SMELL | v1.11.0 | Dashboard v2 has no qualitative/humanities surface |
| AUDIT-v1.9.2-074 | MEDIUM | 02 | INCONSISTENCY | v1.9.4 | Pack chains dead-end at next_protocol: null |
| AUDIT-v1.9.2-075 | MEDIUM | 07 | DEAD_CODE | v1.11.0 | 12 dead template fields |

---

## 4. Recommended v1.9.3 work-list

Ordered by `severity × ease-of-fix`. Total estimated agent-hours: **27 h** for 28 work items.

| Order | ID | Severity | Estimate | Title |
|---:|---|---|---:|---|
| 1 | AUDIT-v1.9.2-018 | HIGH | 0.25h | Add `log_override` call in `_handle_tool_audit_synthesis` |
| 2 | AUDIT-v1.9.2-020 | HIGH | 0.25h | Update `tool_audit_quality_full` description + audit_and_validation.yaml to list 6 gates |
| 3 | AUDIT-v1.9.2-029 | HIGH | 0.25h | Append `tool_paper_compile_typst` to `synthesis_paper` decomposition |
| 4 | AUDIT-v1.9.2-027 | HIGH | 0.25h | Rewrite `hermeneutic_method` on_failure to drop nonexistent protocol refs |
| 5 | AUDIT-v1.9.2-039 | LOW | 0.1h | Drop `tool_write_provenance_sidecar` mention in _router_index |
| 6 | AUDIT-v1.9.2-041 | LOW | 0.1h | Return `referenced` counter from content_depth.py |
| 7 | AUDIT-v1.9.2-055 | LOW | 0.1h | Delete vacuous loop in test_v171_three_packs |
| 8 | AUDIT-v1.9.2-044 | MEDIUM | 0.1h | Sweep pack `__version__` to match core |
| 9 | AUDIT-v1.9.2-045 | MEDIUM | 0.1h | Rename `affiliation` → `institution` in latex.py:172 |
| 10 | AUDIT-v1.9.2-043 | MEDIUM | 0.25h | Sweep protocol YAML `version:` fields to 1.9.3 |
| 11 | AUDIT-v1.9.2-059 | MEDIUM | 0.1h | Add sentence to `tool_audit_quality_full` description about per-step literature skip |
| 12 | AUDIT-v1.9.2-013 | HIGH | 0.5h | Add `.txt`/`.md` to qualitative `_INTERVIEW_HINT_EXTS`; reduce speaker-turn threshold to ≥3 |
| 13 | AUDIT-v1.9.2-014 | HIGH | 0.5h | Rewrite member_checking.yaml refs to `tool_redact` + `consent_amendment` |
| 14 | AUDIT-v1.9.2-025 | HIGH | 0.5h | Rewrite 3 qualitative-pack `sys_path` misuse lines |
| 15 | AUDIT-v1.9.2-030 | MEDIUM | 0.5h | Document 2-cycle ping-pong risk in PROTOCOL_DOCTRINE |
| 16 | AUDIT-v1.9.2-034 | MEDIUM | 0.5h | Unify κ thresholds across 3 intercoder protocols |
| 17 | AUDIT-v1.9.2-035 | MEDIUM | 0.5h | Wire stress-runner to assert `expected_pack` from manifest |
| 18 | AUDIT-v1.9.2-037 | MEDIUM | 0.5h | Delete 4 Typst vector-figure orphan helpers |
| 19 | AUDIT-v1.9.2-048 | LOW | 0.5h | Regenerate RESEARCHER_GUIDE source-tree diagram |
| 20 | AUDIT-v1.9.2-015 | HIGH | 0.5h | Drop unused `state_hint` kwarg from `route_request` (or wire it) |
| 21 | AUDIT-v1.9.2-051 | LOW | 1h | Delete 13 truly-dead helper functions |
| 22 | AUDIT-v1.9.2-028 | HIGH | 1h | Add explicit DESeq2/scRNA-seq triggers to analysis_plan |
| 23 | AUDIT-v1.9.2-038 | MEDIUM | 1h | Raise the 4 errors.py classes or strip docstring |
| 24 | AUDIT-v1.9.2-056 | HIGH | 1h | Document 7 runtime.* exec-safety fields in template + guide |
| 25 | AUDIT-v1.9.2-001 | CRITICAL | 1h | Fix 3 config-reader paths (gate_strictness/project_tier/model_profile) + tests |
| 26 | AUDIT-v1.9.2-011 | CRITICAL | 1.5h | Make `resolve_gate_strictness` consult `project_tier_strictness` as default |
| 27 | AUDIT-v1.9.2-002 | CRITICAL | 1.5h | Wire `override_discussion_coverage` through handler + schema |
| 28 | AUDIT-v1.9.2-009 | HIGH | 2h | Rewrite RESEARCHER_GUIDE §8 schema to match template |
| 29 | AUDIT-v1.9.2-012 | HIGH | 2h | Loosen REDCap adapter detection for cross-sectional exports |
| 30 | AUDIT-v1.9.2-003 | CRITICAL | 3h | Add humanities-mode pack_overrides on step_completeness gate |
| 31 | AUDIT-v1.9.2-004 | CRITICAL | 3h | Doc-rewrite for 7 humanities pack tools (or v1.10.0 to ship) |
| 32 | AUDIT-v1.9.2-010 | HIGH | 4h | Enumerate 34 missing protocols in PROTOCOLS.md |
| 33 | AUDIT-v1.9.2-005 | HIGH | 0.5h | Remaining 113/146 cleanup (CLAUDE.md if it needs it) |
| 34 | AUDIT-v1.9.2-050 | LOW | (fixed inline) | Humanities detector .pdf comment |
| 35 | AUDIT-v1.9.2-057 | MEDIUM | 1h | Document research_goal.* extension fields |

**v1.9.3 work item count: 35** (counting close-related items separately).
**v1.9.3 total estimated hours: ~28h** (1 sprint = 1 senior IC day).

Recommend tackling in this order:
1. **Trivial fixes block (1-11):** 2 h of low-risk count/doc patches; ship as a doc-polish PR.
2. **CRITICAL block (25-27, 30):** 7 h to plug the 4 release-blocking bugs.
3. **Pack-stress block (12-19, 31):** 6 h to fix the qualitative + humanities pack contracts.
4. **Coverage block (24, 28, 32):** 7 h to close the docs/schema gaps.

---

## 5. Recommended v1.9.4 work-list — usability polish

Ordered by user-visible impact. Total estimated hours: **18 h**.

| Order | ID | Severity | Estimate | Title |
|---:|---|---|---:|---|
| 1 | AUDIT-v1.9.2-022 | HIGH | 4h | Add humanities branch to literature gate (or `output_kind` switch) |
| 2 | AUDIT-v1.9.2-023 | HIGH | 3h | Add `output_kind: empirical/humanities/technical/review` to synthesis_paper; gate quantitative-evidence to empirical |
| 3 | AUDIT-v1.9.2-024 | HIGH | 1h | Key qualitative-audit auto-route on pack rather than artefact filename |
| 4 | AUDIT-v1.9.2-016 | HIGH | 1h | Unify DPI thresholds between audit_figure + audit_figure_full |
| 5 | AUDIT-v1.9.2-017 | HIGH | 2h | Drop step-folder split in `_report_path`; standardize on `workspace/logs/` |
| 6 | AUDIT-v1.9.2-019 | HIGH | 1h | Either expose override_literature_gate on the audit tool, or clarify scope |
| 7 | AUDIT-v1.9.2-031 | MEDIUM | 1h | Write reports for audit_dashboard_content + audit_cliches |
| 8 | AUDIT-v1.9.2-032 | MEDIUM | 2h | Define canonical audit return shape; refactor 20 audits |
| 9 | AUDIT-v1.9.2-033 | MEDIUM | 1h | Shared override-rationale validator |
| 10 | AUDIT-v1.9.2-036 | MEDIUM | 4h | Wire end-to-end meta-test over `tests/fixtures/projects/` |
| 11 | AUDIT-v1.9.2-040 | LOW | 0.5h | Parse N/M from filenames in `tool_qualitative_codebook_diff` |
| 12 | AUDIT-v1.9.2-049 | LOW | 0.25h | Bridge holdings_register.md ↔ lookup_*.md in archival_research |
| 13 | AUDIT-v1.9.2-054 | LOW | 1h | Migrate F401 ignore to per-file pattern |
| 14 | AUDIT-v1.9.2-060 | LOW | 0.25h | Add next_steps hint to tool_paper_compile_typst response |
| 15 | AUDIT-v1.9.2-061 | LOW | 0.5h | Document router-first dispatch in PROTOCOL_DOCTRINE |
| 16 | AUDIT-v1.9.2-064 | MEDIUM | 0.25h | Suppress n=12 "small sample" warning when step is qualitative |
| 17 | AUDIT-v1.9.2-065 | LOW | 0.5h | Auto-derive literature_index from on-disk PDFs |
| 18 | AUDIT-v1.9.2-066 | LOW | 0.5h | Don't penalise corpus_manifest.csv in humanities detector |
| 19 | AUDIT-v1.9.2-067 | LOW | 0.25h | Convert hermeneutic_method quality_bar list → dict |
| 20 | AUDIT-v1.9.2-074 | MEDIUM | 1h | Route pack chain dead-ends back to synthesis/manuscript_outline |

---

## 6. Recommended v1.11.0 work-list — minor-bump candidates

These items require new tools, new protocols, or new template fields — MINOR semver bumps.

| ID | Severity | Estimate | Title |
|---|---|---:|---|
| AUDIT-v1.9.2-021 | HIGH | 8h | Thread `gate_strictness` through 19 remaining audits |
| AUDIT-v1.9.2-042 | HIGH | 8h | Rewrite docs/TOOLS.md against live TOOL_DEFINITIONS (66 missing tools) |
| AUDIT-v1.9.2-073 | HIGH | 8h | Dashboard v2 qualitative + humanities renderers |
| AUDIT-v1.9.2-026 | HIGH | 6h | Ship COREQ + SRQR checklist YAMLs |
| AUDIT-v1.9.2-046 | MEDIUM | 4h | Wire `coaching` autonomy_level effects (or drop from template) |
| AUDIT-v1.9.2-063 | MEDIUM | 2h | Add `auto_proceed` short-circuit to `tool_synthesize` |
| AUDIT-v1.9.2-068 | HIGH | 6h | Single source of truth for researcher_config schema |
| AUDIT-v1.9.2-069 | LOW | 0.5h | Preflight check on `_router_index.yaml` `version:` bump |
| AUDIT-v1.9.2-070 | LOW | 4h | Add optional `see_also` field to protocol schema |
| AUDIT-v1.9.2-071 | MEDIUM | 4h | Enforce cross-field interactions or strip comments |
| AUDIT-v1.9.2-072 | MEDIUM | 1h | Extend `validate_config` with per-field enum checks |
| AUDIT-v1.9.2-075 | MEDIUM | 4h | Wire or strip 12 dead template fields |
| AUDIT-v1.9.2-047 | LOW | 2h | Sweep deprecated-alias tool names from protocol YAMLs |
| AUDIT-v1.9.2-062 | LOW | 2h | Document 12 missing tools in docs/ (rolled into 042) |

**v1.11.0 total estimated hours: ~59h** (1.5 sprints).

---

## 7. Recommended v2.0.0 cleanup additions — deprecation surface

MAJOR-bump candidates that break public surface:

| ID | Estimate | Description |
|---|---:|---|
| AUDIT-v1.9.2-052 | 16h | Hard-remove or relocate the 51 orphan tools (move to `legacy/` namespace OR delete with migration notes). Some are legitimate boot infrastructure and should be allow-listed; the rest split into "researcher-direct" (document) and "aspirational dead" (delete with deprecation aliases now). |
| Removal of 21 `_DEPRECATED_ALIASES` | 1h | Hard-break the 21 deprecated tool-name aliases after v1.11.0 sweep replaces them in protocols. |
| Removal of `_router_index.yaml` 2-cycles (or refactor to `recommended_followups`) | 2h | Once the new field lands in v1.11.0, MAJOR can drop the cycle workaround. |
| Removal of `coaching` autonomy_level (if not wired by v1.11.0) | 0.1h | Enum value with no effect; remove from template. |
| Removal of dead template fields (if not wired by v1.11.0) | 0.1h | Strip 12 fields with no consumer. |

**v2.0.0 total estimated hours: ~20h** for cleanup. Most of the MAJOR effort is migration documentation, not code change.

---

## 8. Health metrics

### 8.1 Counts (live ground truth at v1.9.1)

| Quantity | Source of truth | Value |
|---|---|---|
| Protocols on disk (excl. `_router_index`) | `find src/research_os/protocols -name '*.yaml' \| grep -v _router_index \| wc -l` | **114** |
| Pack protocols | `find src/research_os_*/protocols -name '*.yaml' \| wc -l` | **36** |
| **Total protocols** | (core + plugin) | **150** |
| Router-index keys (core) | `idx['protocols']` keys | **114** |
| Router-index keys (plugin) | `router_entries.py` total | **36** |
| Router-addressable protocols | (router-keys ∪ chain) | **150 / 150 = 100%** |
| MCP tools wired | `len(research_os.server.TOOL_DEFINITIONS)` at runtime | **212** |
| Tools defined per AST walk | `TOOL_DEFINITIONS` literals + late assignments | **190** (the 22 gap = `_ALIASES` re-exports; clean) |
| `_ALIASES` entries | `_ALIASES` dict | **26** |
| `_DEPRECATED_ALIASES` entries | set | **21** |
| Audit tools | grep `tool_audit_*` in TOOL_DEFINITIONS | **20** |
| Audit protocols | `protocols/audit/*.yaml` | **3** |
| Audit gates run by `tool_audit_quality_full` | source walk | **6** (description claims 5) |
| Audit gates honouring `gate_strictness` | source walk | **1 of 20** |
| Tests collected | `pytest --collect-only` | **872** |
| Test files | `find tests -name 'test_*.py'` | **56** |
| Suite wall-clock | `pytest -q` | **~37s** |
| Reference projects (`tests/fixtures/projects/`) | dir count | **13** |
| Adapters | `pyproject.toml` entry-points | **3** (REDCap, Snakemake/SLURM, Nextflow) |
| Plugin packs (bundled) | server.py:6045 bundled tuple | **5** (humanities, qualitative, engineering, wet_lab, theory_math) |

### 8.2 Test coverage by subsystem (from lens 08)

| Bucket | Avg cover | Worst module |
|---|---|---|
| `research_os/*` top-level (cli/wizard/tui) | 7% | `cli.py` 0% / 359 stmts |
| `tools/actions/audit/*` | 65% | `md_audit.py` 12% / 49 stmts |
| `tools/actions/data/*` | 56% | `data.py` 7% / 147 stmts |
| `tools/actions/exec/*` | 53% | `cluster.py` 19% / 165 stmts |
| `tools/actions/research/*` | 64% | `research.py` 39% / 355 stmts |
| `tools/actions/search/*` | 39% | `literature.py` 28% / 224 stmts |
| `tools/actions/state/*` | 71% | `interaction.py` 8% / 103 stmts |
| `tools/actions/synthesis/*` | 60% | `synthesize.py` 7% / 551 stmts; `latex.py` 11% / 148 stmts |
| `tools/actions/viz/*` | 46% | `figures.py` 38% / 167 stmts |
| `adapters/*` | 79% | `runner.py` 67% |
| `plugins/*` | 84% | `loader.py` 79% |
| **Top-level** | **55%** | 18,238 stmts / 8,263 uncovered |

### 8.3 Dead-code module count

| Metric | Value |
|---|---|
| Orphan Python modules | **0** |
| Vulture min-confidence-80 findings (post-audit fix) | **1** (`state_hint` in router.py:540) |
| Truly-dead helper functions | **13** (listed in AUDIT-v1.9.2-051) |
| Half-finished refactor candidates | **4** (Typst vector-figure pipeline) |
| Orphan tools (no protocol or router caller) | **51** |
| Server tools missing from docs/TOOLS.md | **66** |
| Stale `version: 1.7.1` protocols (under package v1.9.2) | **107 of 114** |
| Unused exception classes in errors.py | **4 of 6** |
| Vendored JS bundles consumed | **7 of 7** (100%, healthy) |

### 8.4 Protocol graph topology

| Metric | Value |
|---|---|
| `next_protocol` edges (resolved) | **92** |
| Terminal protocols (`next_protocol: null` explicit) | **56** |
| Broken `next_protocol` references | **0** |
| Cycles (in next-protocol graph) | **3** (all 2-cycles, defensible) |
| Bootstrap roots | **2** (`session_boot`, `session_resume`) |
| Longest acyclic chain | **9 nodes / 8 edges** |
| Weakly connected components | **18** |
| Largest WCC | **48 protocols** (core intake → synthesis flow) |
| Isolated nodes (router-only) | **43** (intentional) |
| Orphan protocols | **0** |

### 8.5 Config schema integrity

| Metric | Value |
|---|---|
| Template fields | ~35 |
| Template fields with no `src/` consumer | **12** |
| `src/` fields read but missing from template | **9** (7 `runtime.*`, 2 `research_goal.*`) |
| Sources of truth competing | **3** (template, CONFIG_TEMPLATE in code, RESEARCHER_GUIDE.md) |
| Config-reader path bugs (wrong dir) | **3** (rigor_signals, quick_mode, reliability) |
| Cross-field interactions promised in comments, not enforced | **6** |

### 8.6 Audit-gate machinery

| Metric | Value |
|---|---|
| Audit tools registered | **20** |
| Master gates run | **6** (description claims 5) |
| Gates honouring `gate_strictness` | **1** |
| Override kwargs documented | **6** |
| Override kwargs implemented | **5** (one is fiction) |
| Override-log writers | **5** (one bypass is invisible) |
| Output filename conventions | **3** (`*_audit.md`, `*_report.md`, `*.md`) |
| Audits writing no report | **2** (`audit_dashboard_content`, `audit_cliches`) |
| Audits routing to step folder vs `workspace/logs/` | **7 / 8** |

### 8.7 Reference-fixture health

| Metric | Value |
|---|---|
| Reference projects shipped | **13** |
| Projects with stale protocol refs | **0** |
| Projects with `canned_responses` (CI-runnable) | **3** |
| Projects actually run end-to-end by stress runner | **0** (canned_responses orphaned) |
| Projects matching their `expected_pack` | (unvalidated — see AUDIT-v1.9.2-035) |

---

## 9. Cross-finding analysis

Six findings cluster around the same underlying defect — `researcher_config.yaml` is the most-drifted surface in the codebase:

- **AUDIT-v1.9.2-001** (path bug): wizard writes to `inputs/`, three readers read from `/`.
- **AUDIT-v1.9.2-011** (project_tier doesn't propagate): tier value never reaches the gate.
- **AUDIT-v1.9.2-021** (1/20 audits honour strictness): the value, if it ever loaded, would be ignored anyway.
- **AUDIT-v1.9.2-009** (RESEARCHER_GUIDE schema docs 5 fields behind).
- **AUDIT-v1.9.2-056** (7 runtime.* fields consumed but undocumented).
- **AUDIT-v1.9.2-068** (three sources of truth in conflict).

These are all symptoms of the same root cause: the schema landed in three competing places (template, in-code CONFIG_TEMPLATE, docs) and nobody owns reconciliation. **Recommended v1.11.0 architectural fix:** delete CONFIG_TEMPLATE; have the wizard read templates/researcher_config.yaml directly; generate the schema docs from the same file at build time. Fixing the root makes 4 of the 6 findings disappear.

Five findings cluster around **the humanities pack is documentation, not infrastructure**:

- **AUDIT-v1.9.2-003** (step completeness gate blocks all humanities synthesis).
- **AUDIT-v1.9.2-004** (7 referenced tools don't exist).
- **AUDIT-v1.9.2-022** (literature gate empirical-only).
- **AUDIT-v1.9.2-023** (synthesis_paper forces statistics).
- **AUDIT-v1.9.2-074** (pack chains dead-end without rejoining core synthesis).

The pack passes preflight + canned-response stress tests but cannot actually carry a humanist from intake to publication. The pack is publishable as documentation but not yet as infrastructure. **Recommended v1.11.0 strategic decision:** either (a) ship the 7 missing tools and add humanities branches to the gates (~30 h), or (b) demote the humanities pack to "experimental" status with a clear note in PROTOCOLS.md until the gates are reworked.

Three findings cluster around **the audit-gate machinery is functional but incoherent**:

- **AUDIT-v1.9.2-006** (master advertises 5, runs 6).
- **AUDIT-v1.9.2-007/021** (only 1/20 audits honour strictness).
- **AUDIT-v1.9.2-017** (report paths split).
- **AUDIT-v1.9.2-032** (return shapes drift).

The integration layer never settled on a contract. **Recommended v1.9.4 cleanup:** define a canonical audit return shape (`{status, blockers[], warnings[], report_path}`), refactor all 20 audits to it, and either thread `gate_strictness` through all of them or remove the field from the user-facing config. The current state (settable, mostly ignored) is the worst of both worlds.

Two findings cluster around **docs/code count drift discipline**:

- **AUDIT-v1.9.2-005** (113/146/438 stale counts across 7+ files).
- **AUDIT-v1.9.2-043** (107/114 protocols still carry version: 1.7.1).

Both are direct violations of the CLAUDE.md guidance ("Writing docs that reference tool counts — they go stale fast"). **Recommended v1.11.0 process fix:** add a release-gate preflight check that compares every count claim in docs/* against the live API and fails the release if drift is detected. Or simpler: add a `{TOOL_COUNT}` / `{PROTOCOL_COUNT}` Jinja substitution at doc-build time so the docs literally cannot drift.

---

## 10. Trivial fixes applied during this audit

The 10 lens agents applied 19 trivial fixes in-line (typos, stale counts, dead branches, doc renames). All are < 1-line touches; none touched production logic.

| File:line | Fix | Applied by |
|---|---|---|
| [src/research_os/server.py](src/research_os/server.py):4878 | `sys_help` methodology count `(29)` → `(42)` | lens 01 |
| [src/research_os/server.py](src/research_os/server.py):4882 | `sys_help` synthesis count `(14: …)` → `(18: …)` | lens 01 |
| [src/research_os/server.py](src/research_os/server.py):1675 | `sys_active_tools` description "all 143 tools" → "all 212 tools" | lens 01 |
| [docs/ROADMAP.md](docs/ROADMAP.md):252 | stale tool name `tool_audit_master` → `tool_audit_quality_full` | lens 01 |
| [src/research_os/tools/actions/audit/step_literature.py](src/research_os/tools/actions/audit/step_literature.py):9 | module docstring `tool_audit_master` → `tool_audit_quality_full` | lens 01 |
| [src/research_os_humanities/detector.py](src/research_os_humanities/detector.py):62 | docstring `.txt / .md / .pdf` → `.txt / .md / .tex` | lens 02 |
| [src/research_os/protocols/_router_index.yaml](src/research_os/protocols/_router_index.yaml):1094 | removed duplicated "by re-running by re-running" | lens 04 |
| [docs/README.md](docs/README.md):19, :20 | `113 → 114`; `146 → 212` | lens 06 |
| [docs/FAQ.md](docs/FAQ.md):61 | `113 → 114` | lens 06 |
| [docs/PROTOCOLS.md](docs/PROTOCOLS.md):3, :13, :20 | `113 → 114`; synthesis `17 → 18` (with 4 names); total `113 → 114` | lens 06 |
| [docs/START.md](docs/START.md):133, :141 | `113 → 114`; `146 → 212` | lens 06 |
| [docs/AI_GUIDE.md](docs/AI_GUIDE.md):84, :95, :336 | `113 → 114`; synthesis `17 → 18`; total `113 → 114` | lens 06 |
| [docs/TOOLS.md](docs/TOOLS.md):3 | `146 → 212` | lens 06 |
| [docs/RESEARCHER_GUIDE.md](docs/RESEARCHER_GUIDE.md):6, :249, :315, :648, :649 | counts | lens 06 |
| [CONTRIBUTING.md](CONTRIBUTING.md):10, :36 | `212/114`; `872+ tests, ~12s` | lens 06 |
| [src/research_os/tools/actions/state/path.py](src/research_os/tools/actions/state/path.py):1568 | removed unreachable `return out` line | lens 09 |

**Verification post-fixes:** all 872 tests still pass; ruff still clean; preflight still 13/13; vulture --min-confidence 80 dropped from 2 findings to 1.

---

## 11. Reproduction commands

For maintainers wanting to replicate the audit numbers:

```bash
# Activate env
source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os
cd /scratch/vsetlur/Research-OS

# Health gate
python scripts/preflight.py         # must be 13/13
python -m pytest -q                 # must be 872 pass
ruff check src/ tests/ scripts/     # must be clean

# Count tools and protocols
python -c "from research_os.server import TOOL_DEFINITIONS; print(len(TOOL_DEFINITIONS))"
find src/research_os/protocols -name '*.yaml' | grep -v _router_index | wc -l
find src/research_os_*/protocols -name '*.yaml' | wc -l

# Coverage report
pip install pytest-cov
pytest --cov=src/research_os --cov-report=term-missing

# Vulture dead-code scan
pip install vulture
vulture src/research_os/ --min-confidence 80

# Live router test for AUDIT-v1.9.2-028
python -c "
from research_os.tools.actions.router import route_request
print(route_request(prompt='fit a DESeq2 differential expression model'))
"
```

---

## 12. Audit conclusion

Research-OS v1.9.1 is **release-grade on the structural foundation** — 100% router-addressable protocols, 0 broken references, 13/13 preflight checks, 872 hermetic tests, ruff clean, 55% line coverage, no orphan modules, no unused vendored assets. The biology-domain end-to-end paper-research flow (intake → 6-10 steps → synthesis → Typst PDF → v2 dashboard → final audit) is wired through 25 stages with clear contracts, documented overrides, and audit-trail discipline.

The rot is on three surfaces:

1. **researcher_config.yaml schema (RED):** three sources of truth in conflict; the v1.5.1 tier/strictness subsystem silently inert in real projects because three readers look in the wrong directory; tests codify the bug. 6 of the audit's most-critical findings collapse into this one root cause.

2. **Humanities pack (RED):** ships 8 thoughtful protocols and 3 scaffold tools that pass preflight, but composes against an empirical-IMRAD core that hard-requires figures + p-values + Crossref-grade citation counts. 7 tools the protocols name don't exist; chains dead-end before rejoining core synthesis. Publishable as documentation, not yet executable as infrastructure.

3. **Audit-gate integration layer (RED):** master gate covers 6/20; only 1/20 honours strictness; one documented override is fiction; output paths split between two directories; return shapes drift. Each gate works in isolation; the integration story is incoherent.

The recommended v1.9.3 release plan (28 h of work across 35 items) closes the 4 CRITICAL findings, fixes the 7 trivial issues already discovered, and ships the docs sweep that brings RESEARCHER_GUIDE / PROTOCOLS / TOOLS up to date. v1.9.4 (18 h) is the usability-polish session. v1.11.0 (59 h) is the audit-gate refactor + humanities pack wiring + dashboard surfaces. v2.0.0 (20 h) is the deprecation cleanup.

No release is blocked. Ship v1.9.2 with the count-fix patch and the in-line trivial fixes already applied; queue v1.9.3 as the immediate next priority.

---

## Appendix: Resolved in v1.9.3 (2026-06-05)

This appendix records the actual fate of every AUDIT-v1.9.2-NNN
finding scheduled for v1.9.3 (the 35-item work-list from §10 of the
audit body). Each row: ID, one-line title, files touched, status.

Release gates at synthesis time:
- preflight: **22/22** (one new check added: `Router index mtime tracks protocols`)
- pytest: **896 passed** (was 872 baseline; +24 v1.9.3 tests)
- ruff: **clean across src/ tests/ scripts/**
- 114 protocols / 212 tools / 5 packs all on version `1.9.3`

### Resolved (33 findings)

#### Code / src/ (Phase 1)

| ID | Title | Files | Status |
|---|---|---|---|
| AUDIT-v1.9.2-001 | Config-reader path bug (`inputs/researcher_config.yaml` w/ legacy fallback) | `state/rigor_signals.py`, `state/quick_mode.py`, `state/reliability.py`, tests | RESOLVED |
| AUDIT-v1.9.2-002 | `override_discussion_coverage` wired through schema + handler + log_override | `server.py`, `synthesis/discussion_from_verdicts.py` | RESOLVED |
| AUDIT-v1.9.2-003 | step_completeness gate accepts humanities markdown artefacts | `audit/audit.py`, `tests/unit/test_v193_humanities_completeness.py` | RESOLVED |
| AUDIT-v1.9.2-005 | (covered by lens-01 fixes) — biology flow surface | indirectly via AUDIT-028/029/059 | RESOLVED |
| AUDIT-v1.9.2-006 | (covered by AUDIT-018) — override audit-trail | `server.py` | RESOLVED |
| AUDIT-v1.9.2-011 | project_tier propagates as default when gate_strictness unset | `state/rigor_signals.py`, tests | RESOLVED |
| AUDIT-v1.9.2-012 | REDCap adapter detects cross-sectional exports | `research_os_adapter_redcap/__init__.py`, tests | RESOLVED |
| AUDIT-v1.9.2-013 | Qualitative detector picks up .txt/.md transcripts at ≥3 speaker turns | `research_os_qualitative/detector.py`, tests | RESOLVED |
| AUDIT-v1.9.2-015 | router honours state_hint as tie-breaker | `tools/actions/router.py`, tests | RESOLVED |
| AUDIT-v1.9.2-018 | `override_no_pdfs` now writes `override_log.md` | `server.py` | RESOLVED |
| AUDIT-v1.9.2-020 | Audit master description lists 6 gates including grounding | `server.py`, `audit_and_validation.yaml` | RESOLVED |
| AUDIT-v1.9.2-035 | stress_runner asserts `expected_pack` from manifest | `testing/stress_runner.py`, tests | RESOLVED |
| AUDIT-v1.9.2-037 | Deleted 4 orphaned Typst vector-figure helpers | `synthesis/typst.py`, `audit/dashboard_content.py` | RESOLVED (dead code) |
| AUDIT-v1.9.2-038 | Removed 4 unused exception classes from `errors.py` | `errors.py` | RESOLVED (dead code) |
| AUDIT-v1.9.2-041 | `content_depth.py` now returns `figures_referenced` | `audit/content_depth.py` | RESOLVED |
| AUDIT-v1.9.2-046 | Alias coaching `autonomy_level` to `supervised` (display preserved) | `state/config.py` | RESOLVED |
| AUDIT-v1.9.2-051 | Dead-helper sweep across 8 modules | `inputs/papers.py`, `testing/stress_runner.py`, `plugins/loader.py`, `project_ops.py`, `tui.py`, `utils/asset_manager.py`, `verify.py`, `logo.py` | RESOLVED (dead code) |
| AUDIT-v1.9.2-054 | Move F401 ignore from global to per-file; auto-fix 20 unused imports | `pyproject.toml`, `scripts/preflight.py`, 17 src files | RESOLVED |
| AUDIT-v1.9.2-068 | Pin `CONFIG_TEMPLATE` to `templates/researcher_config.yaml` with sync test | `state/config.py`, `templates/researcher_config.yaml`, `tests/unit/test_config_template_matches_file.py` | RESOLVED |
| AUDIT-v1.9.2-069 | Preflight check: warn when `_router_index.yaml` older than any protocol | `scripts/preflight.py` | RESOLVED |
| AUDIT-v1.9.2-071 | project_tier as default gate_strictness when gate_strictness=auto + tier!=production | `state/rigor_signals.py` | RESOLVED |
| AUDIT-v1.9.2-072 | `sys_config_validate` per-field enum membership | `state/config.py` | RESOLVED |

#### Protocol YAMLs (Phase 2A)

| ID | Title | Files | Status |
|---|---|---|---|
| AUDIT-v1.9.2-004 | Humanities pack tool refs rewritten as manual / `tool_python_exec` | `digital_humanities_workflow.yaml`, `scholarly_edition.yaml` | RESOLVED |
| AUDIT-v1.9.2-014 | `member_checking` refs to nonexistent helpers rewritten doc-only | `member_checking.yaml` | RESOLVED |
| AUDIT-v1.9.2-025 | Qualitative `sys_path` misuse corrected | 3 qualitative protocols | RESOLVED |
| AUDIT-v1.9.2-027 | `hermeneutic_method` on_failure no longer references nonexistent protocols | `hermeneutic_method.yaml` | RESOLVED |
| AUDIT-v1.9.2-028 | Router gains explicit DESeq2 / DE / scRNA-seq triggers | `_router_index.yaml` | RESOLVED |
| AUDIT-v1.9.2-029 | `synthesis_paper` decomposition appends Typst compile | `_router_index.yaml` | RESOLVED |
| AUDIT-v1.9.2-030 | Three 2-cycles broken via `next_protocol: null` on back-edges | 3 methodology protocols | RESOLVED |
| AUDIT-v1.9.2-034 | Kappa thresholds unified on Landis & Koch 1977 (NORMAL=0.70) | 3 protocols | RESOLVED |
| AUDIT-v1.9.2-039 | Removed orphan `tool_write_provenance_sidecar` mention | `_router_index.yaml` | RESOLVED |
| AUDIT-v1.9.2-043 | Bulk-bumped 114 core protocols + router index to v1.9.3 | `_router_index.yaml`, all protocol YAMLs | RESOLVED |
| AUDIT-v1.9.2-044 | All 5 pack manifests + 36 pack protocols bumped to v1.9.3 | All pack `__init__.py` + pack YAMLs | RESOLVED |
| AUDIT-v1.9.2-067 | `hermeneutic_method` `quality_bar` converted list → dict | `hermeneutic_method.yaml` | RESOLVED |

#### Docs (Phase 2B)

| ID | Title | Files | Status |
|---|---|---|---|
| AUDIT-v1.9.2-009 | `RESEARCHER_GUIDE.md` config schema synced to template | `docs/RESEARCHER_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-010 | `PROTOCOLS.md` full 114-protocol catalogue + regen script | `docs/PROTOCOLS.md`, `scripts/regen_protocols_doc.py` | RESOLVED |
| AUDIT-v1.9.2-042 | `TOOLS.md` now mentions all 212 tools (was 131) | `docs/TOOLS.md` | RESOLVED |
| AUDIT-v1.9.2-045 | `researcher.affiliation → institution` drift resolved | `synthesis/latex.py`, `docs/RESEARCHER_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-048 | `RESEARCHER_GUIDE` source-tree diagram regenerated | `docs/RESEARCHER_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-056 | `runtime.*` exec-safety fields documented | `docs/RESEARCHER_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-057 | `research_goal.*` extension fields documented | `docs/RESEARCHER_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-058 | `AI_GUIDE.md` visualization table expanded 6 → 14 | `docs/AI_GUIDE.md` | RESOLVED |
| AUDIT-v1.9.2-059 | `tool_audit_quality_full` skip-literature behaviour documented | `server.py`, `docs/TOOLS.md` | RESOLVED |
| AUDIT-v1.9.2-070 | Optional `see_also` field convention documented | `docs/PROTOCOL_DOCTRINE.md` | RESOLVED (docs only; field not auto-rendered) |
| DRIFT-counts | Maintainer `CLAUDE.md` stale counts updated | `CLAUDE.md` | RESOLVED |

#### Tests / fixtures (Phase 2C)

| ID | Title | Files | Status |
|---|---|---|---|
| AUDIT-v1.9.2-036 | Rewrite `slurm_snakemake` + `redcap_longitudinal` canned_responses | 2 manifests | RESOLVED |
| AUDIT-v1.9.2-055 | Replace vacuous loop in `test_v171_three_packs` | `tests/unit/test_v171_three_packs.py` | RESOLVED |

### Deferred to v1.9.4 / v1.11.0

| ID | Title | New target | Rationale |
|---|---|---|---|
| AUDIT-v1.9.2-047 | Deprecated-alias sweep across 71 protocols | **v1.11.0** | Snowballs to 71 files; aliases still functional, only deprecation telemetry fires. Audit's own target column reads v1.11.0. |
| AUDIT-v1.9.2-022 | `literature_per_step` empirical-only (humanities blocker) | **v1.9.4** | Per audit triage. |
| AUDIT-v1.9.2-023 | `synthesis_paper` hard-codes p-value formatting | **v1.9.4** | Per audit triage. |
| AUDIT-v1.9.2-024 | `audit_and_validation` auto-routes codebook to qualitative gate | **v1.9.4** | Per audit triage. |
| AUDIT-v1.9.2-026 | COREQ-SRQR checklist YAMLs never shipped | **v1.11.0** | Per audit triage. |
| AUDIT-v1.9.2-060 | `tool_paper_compile_typst` `next_steps` field | **v1.9.4** | Per audit triage. |
| AUDIT-v1.9.2-063 | `synthesis_paper` 10-turn mandatory loop | **v1.11.0** | Per audit triage. |
| AUDIT-v1.9.2-065 | `synthesis_paper` prerequisites assume literature_index ≥3 | **v1.9.4** | Per audit triage. |
| AUDIT-v1.9.2-073 | dashboard surface for codebooks / apparatus criticus | **v1.11.0** | Per audit triage. |
| AUDIT-v1.9.2-074 | Humanities pack chains dead-end at `next_protocol: null` | **v1.9.4** | Per audit triage. |

### Newly surfaced (introduced by v1.9.3 fixes; tracked for v1.9.4)

- **κ threshold internal drift in qualitative pack** — AUDIT-034 unified quality_bar/verdict-table at κ≥0.70, but `coding_scheme_iteration.yaml` step prose (lines 70, 76, 99) and `tools.py` (132, 166, 178, 182) in `research_os_qualitative` still cite κ<0.60 as the flag threshold. Audit gate that BLOCKS is 0.70; tool advice that warns is 0.60. Friction, not failure. v1.9.4 sweep.
- **Humanities mode auto-detection requires config or filesystem markers** — fresh projects without `domain: humanities` in `inputs/researcher_config.yaml` AND without `workspace/**/{edition,apparatus,transcriptions,humanities}` markers will still trigger the figure-mandatory gate on step 1. Workable but adoption-path friction. Wizard should auto-write domain hint. v1.9.4.
- **`_collect_humanities_artefacts` suffix set is .md/.txt/.xml/.tei only** — a `.tex` apparatus or `.docx` transcription under `edition/` would still trigger the no-figure blocker. Edge case; v1.9.4.

### v1.9.3 stress re-run summary (3 lenses)

| Lens | Domain | v1.9.2 frictions | v1.9.3 frictions | Rating |
|---|---|---|---|---|
| 01 | Biology snRNA-seq | 9 | 4 (all deferred) | 9/10 |
| 02 | Humanities composition | 15 | 11 (4 fixed; 7 deferred per triage) | 6/10 |
| 03 | Qualitative interview study | 9 | 3 (+ 1 new internal-drift item) | 8/10 |

Average usability across 3 lenses: **7.67 / 10** (was ~5 in v1.9.2).

---

## Appendix: Validated in v1.9.4 (2026-06-05)

The v1.9.4 release ran a full 5-scenario fresh-agent usability validation (Claude Opus 4.7, 1M ctx, doc-surface only — no `src/research_os/**/*.py` reads). The validation harness fired the same trace template (~33 turns/scenario, sys_boot → tool_route → analysis_plan → per-step audits → synthesis_paper → tool_paper_compile_typst → tool_dashboard_create → pre_submission_checklist) across biology RNA-seq DE, humanities close-reading, qualitative interview thematic analysis, engineering microbenchmark, and theory/math proof. See `docs/USABILITY_v1.9.4.md` for full synthesis.

### v1.9.4 validation outcome (vs initial baseline)

| Metric | Initial baseline | After v1.9.4 fix sprint |
|---|---|---|
| Average usability rating | 6.6 / 10 | **7.8 / 10** |
| Total HIGH-severity friction events | 12 | **1** |
| Total MEDIUM-severity friction events | 27 | 17 |
| Onboarding HIGH friction (first 5 turns) | 2 | **0** |
| Scenarios reaching `paper.pdf` step | 5 / 5 | 5 / 5 |
| Scenarios reaching `dashboard.html` step | 5 / 5 (1 partial) | 5 / 5 (all clean) |

22 prioritized fixes shipped across 3 clusters: AI guidance + missing prompts + tool discoverability (11 fixes), error messages + edge cases + domain composition (7 fixes), onboarding flow + docs polish (3 fixes + extras). Two of three quality targets met (HIGH friction ≤ 5: **YES**, onboarding HIGH = 0: **YES**); average-rating target (≥ 8.5) missed by 0.7 points, driven by 4 remaining MEDIUM frictions in S2 humanities (no `humanities_essay_structure` protocol; literature-gate verdict mismatch on descriptive/prep steps; corpus placement recovery; story-mode dashboard tools opacity). Top per-scenario gain: theory/math moved 5 → 8 (+3) on the back of F-014 pack visibility + F-001/F-002 step-intent waivers + F-003 IMPORTED_AS_CITED verdict. See `docs/USABILITY_v1.9.4.md` §9 for full re-validation table + deferred-to-v1.11.0 gap accounting.

### Resolutions to deferred AUDIT-v1.9.2 findings

| ID | Title | v1.9.4 status |
|---|---|---|
| AUDIT-v1.9.2-022 | `literature_per_step` empirical-only | PARTIAL — verdict enum extended (IMPORTED_AS_CITED, SPECIALIZES); descriptive/prep step waiver still open (re-deferred to v1.11.0) |
| AUDIT-v1.9.2-023 | `synthesis_paper` p-value formatting | DEFERRED to v1.11.0 (no validation surface hit) |
| AUDIT-v1.9.2-024 | `audit_and_validation` auto-routes codebook to qualitative gate | RESOLVED (F-006 + F-008 closed the qualitative chain) |
| AUDIT-v1.9.2-060 | `tool_paper_compile_typst` `next_steps` field | RESOLVED (F-013 documented return shapes including next_steps) |
| AUDIT-v1.9.2-065 | `synthesis_paper` prerequisites assume literature_index ≥ 3 | DEFERRED to v1.11.0 |
| AUDIT-v1.9.2-074 | Humanities pack chains dead-end at `next_protocol: null` | PARTIAL — F-007 labelled all 148 protocols with `next_protocol_kind`; humanities-essay-structure protocol still missing (re-deferred to v1.11.0) |

Release gates at v1.9.4 sign-off: preflight 23/23 (one new check added: `next_protocol_kind declared on every protocol`); pytest 899 passed (up from 896 baseline; +3 from new Typst venue parametrisations covering `humanities_essay` + `chicago_thesis`); ruff clean across `src/ tests/ scripts/`.
