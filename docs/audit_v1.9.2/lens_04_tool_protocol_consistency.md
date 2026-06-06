# Lens 04 — Tool ↔ Protocol ↔ Server Consistency Audit

**Audit sprint:** Research-OS v1.9.1 → v1.9.2 discovery
**Date:** 2026-06-05
**Auditor lens:** 04 of 10

## Headline counts (ground truth from disk / AST)

| Item | Count | Source of truth |
|---|---:|---|
| `TOOL_DEFINITIONS` keys (server.py) | **190** | AST walk of literal + 5 late `TOOL_DEFINITIONS[...] = {...}` assignments at lines 6088, 6166, 6174, 6189, 6197 |
| Protocols on disk (`*.yaml` excl. `_router_index.yaml`) | **114** | `pathlib.Path('protocols').rglob('*.yaml')` |
| Protocols in `_router_index.yaml` | **114** | `idx['protocols']` keys |
| `_router_index.yaml` `version:` field | **14** | line 39 |
| Package `__version__` | **1.9.2** | `src/research_os/__init__.py` |
| `_ALIASES` entries | **26** | `_ALIASES` dict at server.py:5826 |
| `_DEPRECATED_ALIASES` entries | **21** | `_DEPRECATED_ALIASES` set at server.py:5867 |

Router-index ↔ on-disk protocol set: **exact match** (0 protocols missing from index, 0 router entries pointing at missing files). Preflight `check_router_index_consistent` validates this on every release.

The hard wiring is clean. The lying-to-users docs and the orphan-tool drift are where the rot lives.

---

## 1. TOOLS.md drift — docs lie to users (HIGH)

`docs/TOOLS.md` opens with **"146 MCP tools across three namespaces"** (line 3). Server defines **190**. That's a **44-tool undercount** — every doc that copies the 146 number propagates the lie.

### Stale-count instances grepped from `docs/`:

| File:line | Claim |
|---|---|
| `docs/TOOLS.md:3` | "146 MCP tools" |
| `docs/README.md:20` | "Catalogue of all 146 MCP tools" |
| `docs/START.md:141` | "146 MCP tools across three namespaces" |
| `docs/ROADMAP.md:35` | "113 protocols in 9 categories; 146 MCP tools" |
| `docs/ROADMAP.md:43` | "~34 of 146 tools still orphan" (actual orphan count is now 51) |
| `docs/ROADMAP.md:120` | "113 protocols + 146 tools is a lot" |
| `docs/ROADMAP.md:482` | "146 tools" (twice in one paragraph) |
| `docs/RESEARCHER_GUIDE.md:6` | "all 113 protocols and 146 MCP tools" |
| `docs/RESEARCHER_GUIDE.md:315` | "## 7. MCP tools (146 total)" |
| `docs/RESEARCHER_GUIDE.md:649` | "catalogue of all 146 MCP tools" |

CLAUDE.md (project-internal) warns:

> **Writing docs that reference tool counts** — they go stale fast. Either omit the number, or `git grep` the number before bumping.

The advice is good. It wasn't followed at the v1.9.x bump cycle. **Recommend:** decide on a single source of truth — either replace every "146"/"113" with a build-time substitution (`scripts/build_docs.py` could swap a `{TOOL_COUNT}` token from the live `TOOL_DEFINITIONS`), or strip the numbers entirely and let `sys_tool_describe` / `sys_protocol_list` be the canonical answer.

### 66 tools defined in server, NOT mentioned in TOOLS.md

Tools shipped, dispatched, and orphaned from the catalogue page users read:

```
mem_log
sys_active_project, sys_adapters_installed, sys_checkpoint_list,
sys_checkpoint_rollback, sys_config_set, sys_config_validate,
sys_env_docker_generate, sys_export_share_archive, sys_file_delete,
sys_file_list, sys_file_validate_md, sys_file_write, sys_help,
sys_packs_installed, sys_path, sys_semantic_tool_search
tool_adapter_extract, tool_adapters_list, tool_adapters_run_all,
tool_alternative_path_propose, tool_audit_coherence,
tool_audit_figure_interactivity, tool_dashboard_story_edit,
tool_dashboard_story_generate, tool_dashboard_story_quality_bar,
tool_deprecations_summary, tool_discussion_coverage_audit,
tool_dry_run, tool_failure_check, tool_failure_list,
tool_failure_record, tool_figure_interactive_autogen,
tool_ground, tool_intake_freshness, tool_lessons,
tool_list_certifications, tool_mistake_replay, tool_path_finalize,
tool_plan, tool_project_tier_strictness, tool_promote_to_step,
tool_quick_route, tool_reliability_log_event, tool_reliability_report,
tool_resolve_gate_strictness, tool_rigor_signals_scan, tool_search,
tool_self_certify, tool_semantic_route, tool_slurm_fetch,
tool_slurm_list, tool_slurm_status, tool_slurm_submit,
tool_state_freshness_check, tool_step_complete, tool_step_iterate,
tool_step_iterations_list, tool_step_pipeline_define,
tool_step_pipeline_diagram, tool_step_pipeline_run,
tool_step_pipeline_status, tool_step_revision_options,
tool_synthesis_curate_figures, tool_verify,
tool_writing_discussion_from_verdicts
```

Note: a number of these (`tool_search`, `tool_plan`, `tool_ground`,
`tool_verify`, `tool_lessons`, `sys_path`, `mem_log`) are the
**consolidated** tools that the deprecated aliases in `_ALIASES`
target — the docs still reference the old `_pubmed`/`_arxiv`/etc.
names. The migration is incomplete on the docs side.

### Phantom entries (in TOOLS.md, not in `TOOL_DEFINITIONS`)

* `tool_audit_statistical_power` — fine, documented as legacy alias example.
* `tool_figure_create` — fine, documented as removed-in-v1.3.0 (lines 250+).

No real phantoms. The drift is one-directional: server has things docs do not.

---

## 2. Orphan tools (no protocol or router-index references) — MEDIUM

A "truly orphan" tool is one that:
1. is not referenced from any protocol YAML's `description` / `steps` / etc.,
2. is not referenced from `_router_index.yaml` (`shortcut_tool`, `decomposition.tool`, `shortcut_intents.tool`),
3. has no `_ALIASES` entry whose deprecated name IS referenced from a protocol/router.

CLAUDE.md states: **"Reference the tool from at least one protocol's `decomposition` or a `shortcut_intents` entry — orphaned tools get removed."**
51 tools fail this rule today:

```
mem_intake_regenerate
sys_active_project, sys_active_tools, sys_adapters_installed,
sys_checkpoint_list, sys_checkpoint_rollback, sys_config_validate,
sys_export_share_archive, sys_file_delete, sys_help, sys_packs_installed,
sys_protocol_validate, sys_semantic_tool_search, sys_tool_describe,
sys_workspace_scaffold, sys_workspace_tree
tool_adapter_extract, tool_adapters_list, tool_adapters_run_all,
tool_audit_cliches, tool_audit_dashboard_content, tool_audit_evalue,
tool_cache_clear, tool_dashboard_reviewer_sim, tool_dashboard_test_run,
tool_data_convert, tool_data_sample, tool_deprecations_summary,
tool_dry_run, tool_list_certifications, tool_mistake_replay,
tool_project_tier_strictness, tool_promote_to_step, tool_quick_route,
tool_resolve_gate_strictness, tool_rigor_signals_scan,
tool_scratch_clear, tool_scratch_list, tool_section_substantiveness,
tool_self_certify, tool_semantic_route, tool_slurm_fetch,
tool_slurm_list, tool_slurm_status, tool_step_complete,
tool_step_iterations_list, tool_step_pipeline_diagram,
tool_step_pipeline_status, tool_synthesis_preview, tool_task_kill,
tool_workflow_dag
```

### Sub-class A — legitimate "router / boot infrastructure" tools

These do real work but are invoked by `sys_boot` / `tool_route` /
the dispatcher rather than by a protocol. They are intentionally
absent from any protocol decomposition:

* `sys_active_tools`, `sys_tool_describe`, `sys_semantic_tool_search`,
  `sys_workspace_tree`, `sys_workspace_scaffold` — surfaced via
  `sys_boot` envelope.
* `tool_quick_route`, `tool_semantic_route`, `tool_workflow_dag` —
  dispatch / wiring helpers.
* `tool_deprecations_summary` — debug surface.

**Action:** add a short "Infrastructure tools — never called by a protocol directly" section to TOOLS.md to make this category explicit, and remove the "orphans get removed" promise from CLAUDE.md OR teach preflight about an allow-list (today it does not check at all).

### Sub-class B — adapter / packs surface (4 tools)

`sys_adapters_installed`, `sys_packs_installed`, `tool_adapter_extract`,
`tool_adapters_list`, `tool_adapters_run_all` — all documented in
`docs/ADAPTERS.md` and `docs/PLUGIN_AUTHORING.md`. These are the
adapter ecosystem MVP. They are not used in any shipped protocol
(no protocol opinionates about adapter discovery yet). Either:

* document them as "researcher-driven, no protocol caller is expected", OR
* land a `methodology/adapter_discovery` protocol that wires them.

### Sub-class C — likely-dead / never-shipped tools

These tools have no protocol caller, no router caller, and the docs
either don't mention them or mention them only in `ROADMAP.md`
(aspirational):

* `tool_dry_run` (`docs/ROADMAP.md` only — aspirational)
* `tool_mistake_replay` (`docs/ROADMAP.md` only)
* `tool_promote_to_step` (`docs/ROADMAP.md` only)
* `tool_rigor_signals_scan` (`docs/ROADMAP.md` only)
* `tool_self_certify` (`docs/ROADMAP.md` only)
* `tool_section_substantiveness` (`docs/ROADMAP.md` + `TOOLS.md`)
* `tool_step_complete` (`docs/ROADMAP.md` only) — likely shadowed by `sys_protocol_log`
* `tool_list_certifications` — completely undocumented in `docs/`
* `tool_project_tier_strictness` — undocumented
* `tool_resolve_gate_strictness` — undocumented

**Action:** decide per tool: (a) wire into a protocol, (b) hide / remove on the next MAJOR with deprecation alias now, or (c) document as a researcher-direct tool with an example call. Do not silently ship 51 unused tools — the LLM picks them up via `sys_active_tools` / `sys_tool_describe` and wastes context tokens on capabilities that no protocol scaffolds around.

### Sub-class D — sys/file/checkpoint utilities the researcher uses directly

* `sys_file_delete`, `sys_help`, `sys_checkpoint_list`,
  `sys_checkpoint_rollback`, `sys_active_project`,
  `sys_config_set`, `sys_config_validate`, `sys_protocol_validate`,
  `sys_export_share_archive`, `mem_intake_regenerate`,
  `tool_cache_clear`, `tool_scratch_clear`, `tool_scratch_list`,
  `tool_task_kill`

These are user-invoked panic-buttons / inspection knobs. Expected to
be orphan from protocols. Document the category.

### Sub-class E — pipeline tools where the parent is used but the children aren't

* `tool_step_pipeline_define`, `_run` — defined and used somewhere?
* `tool_step_pipeline_diagram`, `tool_step_pipeline_status`,
  `tool_step_iterations_list` — companion tools to a pipeline that
  no protocol decomposes.
* `tool_audit_cliches`, `tool_audit_dashboard_content`,
  `tool_audit_evalue` — audit tools that exist in TOOLS.md catalogue
  but no audit protocol calls them.
* `tool_dashboard_reviewer_sim`, `tool_dashboard_test_run` — same.

**Action:** the dashboard-test-and-review and audit-clichés/E-value tools represent unused capability. Either pull them into `audit/audit_and_validation` decomposition or document as "researcher-direct, no protocol caller".

---

## 3. Protocols referencing non-existent tools — LOW

Cross-checked every `(sys_|tool_|mem_)<id>` substring in every protocol YAML against `TOOL_DEFINITIONS` ∪ `_ALIASES.keys()`. After filtering out trailing-underscore glob patterns (e.g. `tool_search_*`, `sys_file_*`), three residuals:

| Match | Protocol(s) | Verdict |
|---|---|---|
| `tool_discovery` | `methodology/tool_discovery` | False positive — appears in YAML as the protocol's *own filename string*, not a tool ref. |
| `tool_list` | `writing/writing_analysis_log` | False positive — the YAML reads `tools: {tool_list}` as a literal placeholder/template field, NOT a tool reference. Could be made clearer (rename placeholder), but not a broken ref. |
| `tool_name` | `guidance/analysis_plan` | False positive — `tool_external_tool_instructions tool_name=<X>` — `tool_name=` is a kwarg of `tool_external_tool_instructions`, the regex matched the kwarg name. |

**No actual broken tool refs.** The wiring layer (preflight `check_router_index_consistent` + `check_protocol_tool_refs`) catches this on every release.

The deprecated-alias references that protocols still emit (`tool_search_pubmed`, `tool_search_arxiv`, `tool_search_crossref`, `tool_search_semantic_scholar`, `tool_search_web`, `tool_plan_turn`, `tool_plan_advance`, `tool_plan_clear`, `tool_grounding_register`, `tool_grounding_verify`, `tool_claim_verify`, `tool_ground_from_context`, `tool_lessons_record`, `tool_lessons_consult`, `sys_path_create`, `sys_path_abandon`, `sys_path_list`, `mem_methods_append`, `mem_decision_log`, `mem_hypothesis_update`, `mem_analysis_log`) all resolve via `_ALIASES` and fire deprecation telemetry per `_DEPRECATED_ALIASES`. They will hard-break on the next MAJOR. **Recommend a v1.10/v1.11 sweep replacing deprecated-alias mentions in protocols with the canonical consolidated names** — otherwise an AI parsing the protocol YAML still sees and tries to use the old names, log gets noisier each call.

---

## 4. Router-index unknown tool refs — LOW

Searched `_router_index.yaml` for `(sys_|tool_|mem_)<id>` patterns that don't resolve via `TOOL_DEFINITIONS` ∪ `_ALIASES`:

| Match | Context | Verdict |
|---|---|---|
| `tool_discovery` | `protocols.methodology/tool_discovery` block key (line 695) | False positive — protocol-name string. |
| `tool_pick` | `hierarchy.methodology.sub_intents.tool_pick` (line 89), `protocols.methodology/tool_discovery.sub_intent: tool_pick` (line 697) | False positive — `sub_intent` label, not a tool ref. |
| `tool_setup` | `hierarchy.methodology.sub_intents.tool_setup` (line 103), `protocols.methodology/external_tool_setup.sub_intent: tool_setup` (line 555) | False positive — `sub_intent` label. |
| `tool_write_provenance_sidecar` | `protocols.audit/audit_and_validation` decomposition `purpose:` prose (line 1094) | Mentioned in prose as something the researcher could invoke manually — but **the tool does not exist** in `TOOL_DEFINITIONS`. The doc string promises a tool that ships nowhere. |

**Finding:** `tool_write_provenance_sidecar` is name-dropped in the router-index's `audit/audit_and_validation.decomposition[0].purpose` as a fallback for manual sidecar generation, but no such tool exists. The user/AI following this guidance will get "unknown tool" if they try to call it. Either:
* Ship the tool, OR
* Drop the mention and direct the user to re-run the figure script under provenance.

---

## 5. Protocol schema validation — CLEAN

Ran `yaml.safe_load` on all 114 protocols. All parse. All have the canonical fields: `id`, `name`, `version`, `schema_version`, `description`. 112 of 114 have `steps`/`expected_outputs`/`next_protocol`/`on_failure`; the 2 without (`synthesis/synthesis_handout`, `synthesis/synthesis_poster`) are **redirect-only stubs** with `redirect_to`/`redirect_params` (valid pattern).

* `id` matches filename stem for all 114 protocols.
* All `next_protocol` references resolve to real protocol files.
* All `on_failure` references resolve.
* All `redirect_to` references resolve.
* All `decomposition[].protocol` references in `_router_index.yaml` resolve to real protocol files (0 broken).

**The task spec mentions `intent_class` / `decomposition` as required fields** — these are router-index fields, NOT protocol-YAML fields. Convention here is that the router index OWNS those metadata, the protocol YAML owns the operational scaffold. That convention is consistent across all 114 protocols.

---

## 6. Protocol version drift — MEDIUM

114 protocols. Package on v1.9.2. Protocol-YAML `version:` field distribution:

| `version:` | Count |
|---:|---:|
| `1.7.1` | 107 |
| `1.9.0` | 5 |
| `1.9.1` | 2 |

The CLAUDE.md release runbook step 3 says (commented out for PATCH releases):

> For MINOR / MAJOR: also bump every protocol YAML version field (skip for PATCH releases unless protocol behavior changed)

v1.8.0 → v1.9.0 → v1.9.1 → v1.9.2 each appear to have skipped the protocol-version sweep. End result: 107/114 protocols claim `1.7.1`, last touched ages ago. If a researcher reads `version: 1.7.1` from a YAML loaded under package v1.9.2 they'll legitimately wonder which is canonical.

**Recommend** either:
* Sweep all protocol `version:` fields to match `__version__` on every MINOR (per the existing runbook), OR
* Stop printing `version:` per-protocol and only show package version + `last_reviewed` date (more honest — most protocols have NOT changed since v1.7.1, the field is accurate per-protocol but misleading vs. package).

`last_reviewed`: 42 of 114 protocols carry the field. None are stale per the 180-day threshold (`check_protocol_freshness` in `scripts/preflight.py:484`). The 72 without an explicit `last_reviewed` fall back to git mtime — acceptable per design.

---

## 7. `_router_index.yaml` `version:` field — LOW

`version: 14` at line 39. There's no automated check that this bumps when the file changes; CLAUDE.md flags as "Common gotcha":

> **Editing `_router_index.yaml` without bumping `version:`** at the top of the file → readers can't tell the index changed.

No tooling catches the drift. The number drifts whenever a maintainer remembers. Recommend a preflight check that compares `version:` to the git log line count of changes since the previous bump, or a pre-commit hook that auto-increments on touch.

---

## Trivial fixes applied

| File:line | Fix |
|---|---|
| `src/research_os/protocols/_router_index.yaml:1094` | Removed duplicated `"by re-running by re-running"` in the `audit/audit_and_validation` decomposition prose. |

No other trivial fixes were within scope (the count-update edits would touch 10+ files and are deliberately left to the v1.9.2 release PR per the maintainer's preferred workflow — counts go stale immediately after a release anyway).

---

## Findings summary

| # | Severity | Category | Title |
|---|---|---|---|
| 1 | HIGH | DOC_GAP | TOOLS.md and 4 other docs claim 146 tools — actual is 190 (44-tool undercount) |
| 2 | MEDIUM | DEAD_CODE | 51 server-defined tools have zero protocol/router callers and the orphan-removal promise in CLAUDE.md is unenforced |
| 3 | MEDIUM | DOC_GAP | 66 server-defined tools have no entry in `docs/TOOLS.md` (researchers can't discover them) |
| 4 | LOW | BUG | Router-index decomposition prose references `tool_write_provenance_sidecar` which does not exist in `TOOL_DEFINITIONS` |
| 5 | MEDIUM | INCONSISTENCY | 107/114 protocols still carry `version: 1.7.1` under package v1.9.2 (release runbook step skipped at last 3 MINOR bumps) |
| 6 | LOW | INCONSISTENCY | Protocols still emit deprecated-alias tool names (`tool_search_pubmed`, etc.) in their YAML — fires deprecation telemetry every load; will hard-break at next MAJOR |
| 7 | LOW | DOC_GAP | 8+ undocumented tools (`sys_config_validate`, `sys_export_share_archive`, `sys_file_delete`, `sys_semantic_tool_search`, `tool_list_certifications`, `tool_project_tier_strictness`, `tool_quick_route`, `tool_resolve_gate_strictness`, `tool_semantic_route`, `tool_slurm_list`, `tool_step_pipeline_diagram`, `tool_step_pipeline_status`) appear NOWHERE in `docs/` |
| 8 | LOW | ARCH_SMELL | `_router_index.yaml` `version:` field has no automated bump check — relies on maintainer memory |

## Suggested release targeting

* **v1.9.2 (PATCH, in-flight):** trivial fix already applied. Update the "146" / "113" counts in `docs/TOOLS.md`, `docs/README.md`, `docs/START.md`, `docs/RESEARCHER_GUIDE.md`, `docs/ROADMAP.md`. Drop or implement `tool_write_provenance_sidecar`.
* **v1.9.3 (PATCH):** sweep deprecated-alias tool references in protocol YAMLs to canonical names.
* **v1.10.0 (MINOR):** rewrite `docs/TOOLS.md` against the live `TOOL_DEFINITIONS`; add 66 missing tools; add the "infrastructure tools — no protocol caller" category. Add preflight check that `_router_index.yaml.version` bumped when protocols/ changed.
* **v2.0.0 (MAJOR):** hard-remove the 21 deprecated aliases; decide per-tool whether to wire or remove the 51 orphans (move undocumented orphans + sub-class C "likely-dead" tools to a `legacy/` namespace or delete with migration notes).
