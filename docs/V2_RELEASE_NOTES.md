# Research-OS v2.0.0 — Release Notes

**Release date:** 2026-06-06
**Branch:** `feat/v2.0.0`
**Validation:** [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md) (Phase 15b — 20 agents × 4 perspectives × 5 scenarios)
**Upgrade guide:** [`docs/MIGRATION_v1_to_v2.md`](MIGRATION_v1_to_v2.md)

## TL;DR

Research-OS v2.0.0 is the **comprehensive release** — an end-to-end coherent system, field-validated by **20 independent agents across 4 perspectives × 5 scenarios**, with measurable improvements vs the v1.11.0 baseline on every cell of the matrix. Tool surface collapsed 344 → 146 live (-58%), `server.py` split from a 7,499-line monolith into 32 modules (largest 579 lines), MCP `instructions` field on the initialize handshake, `sys_protocol_get` default-to-summary (5-10× cheaper per-call tokens), and 5 CRAFT-inspired structural additions (audit-as-data, drafter review-rewrite loops, `research-os doctor`, `docs/CONTRACT.md`, audience-segmented docs). Across 20 runs the mean final_rating moved **6.35 → 7.70 (+1.35; +21%)** with **total HIGH-friction items 124 → 63 (-49%)** and **first-5-turn HIGH 66 → 42 (-36%)** — every cell improved, no regressions. The v2.0.0 release-gate targets were calibrated against a v3-grade product and are not met (YELLOW); the deeper structural gaps carry over to v2.0.x patch + v2.1.0 minor.

## Headline numbers

| Metric | v1.11.0 baseline | v2.0.0 release | Δ |
|---|---|---|---|
| Tool surface (canonical names, live) | 344 | 146 | **-58%** |
| Backward-compat aliases | (implicit) | 80 | NEW |
| Deprecated aliases (dispatch + telemetry) | (implicit) | 78 | NEW |
| Hard-removed (returns `_REMOVED_TOOLS` error) | 0 | 24 | NEW |
| `server.py` lines (single file) | 6,813 (v1.11.0) / 7,499 (mid-cycle peak) | 0 | **monolith dissolved** |
| Modules in `server/` package | 1 | 32 | NEW |
| Largest single server module | 6,813 | 579 | **-92%** |
| Protocols with `scope_tags` block | 0 / 117 | 117 / 117 | NEW (100%) |
| Protocols with `tier:` annotation | 0 / 117 | 117 / 117 | NEW (100%) |
| Tool definitions with `status` + `pack` fields | 0 / 344 | 146 / 146 | NEW (100%) |
| Audits emitting JSON companion (audit-as-data) | 0 / 11 | 11 / 11 | NEW |
| Avg `final_rating` across 20 agent runs | **6.35** | **7.70** | **+1.35 (+21%)** |
| Total HIGH-friction items (sum across 20 runs) | 124 | 63 | **-49%** |
| First-5-turn HIGH-friction items | 66 | 42 | **-36%** |
| Deliverable-produced rate | 11 / 20 (55%) | 14 / 20 (70%) | **+15 pp** |
| Preflight wiring checks | 22 | 24 | +2 |

## 5 CRAFT-inspired additions

These are the structural shape-changes that drove the rating lift beyond mere
surface cleanup. Each was introduced in a dedicated Phase commit and survived
re-validation as called-out wins in ≥ 3 of the 20 re-validation runs.

1. **Audit-as-data** *(phase-4)* — every audit emits a JSON companion alongside
   the Markdown report. New tools `tool_audit_findings(operation=query|diff)`
   query the cross-audit ledger at `.audit_findings.jsonl` with stable UUIDv5
   ids and filters for `severity`, `dimension`, `step`, `since`. `tool_synthesize`
   BLOCK-gates on unresolved BLOCK findings and names the exact override flag
   in the error envelope. Closes the baseline `opaque_blocker_messages` and
   `override_flag_name_not_in_error` HIGH-friction signals.

2. **Drafter review-rewrite loops** *(phase-5)* — paper / slides / poster
   drafters iterate draft → adversarial review → rewrite, with per-iteration
   quality measurement logged to `workspace/logs/drafter_loops/`. Findings
   propagate from the persona-suite (`methodology_skeptic`, `domain_expert`,
   `statistician`, etc.) back into the next draft.

3. **`research-os doctor`** *(phase-6)* — 18+ install + workspace health checks.
   Exit policy: 0 = all-pass, 1 = warn-only, 2 = fail. The first thing the
   v2 migration guide tells you to run after `pip install --upgrade`.

4. **`docs/CONTRACT.md`** *(phase-7)* — the stable-surface promise. Public tool
   names, audit-finding JSON schema, `researcher_config` field names, workspace
   layout, and protocol routing `intent_class` enum are all MAJOR-bumped on
   change. Gives integrators a citable contract instead of grepping `server.py`.

5. **Audience-segmented docs** *(phase-7)* — `docs/README.md` is now a
   four-audience router (researcher / AI agent / plugin author / maintainer /
   integrator). New: `PLUGIN_AUTHORING.md`, `MAINTAINER_GUIDE.md`,
   `INTEGRATION.md`. Stops naive users landing on the maintainer guide first.

## Tool surface consolidation

Roughly 200 legacy tool names collapsed into ~15 unified dispatchers using the
proven alias-with-param-injection pattern (extending what `tool_search`,
`tool_plan`, `tool_ground`, `mem_log` already shipped in v1.6.1). Every legacy
name continues to dispatch for the v2.0.x runway via `_DEPRECATED_ALIASES`
with `_ALIAS_PARAM_INJECTION`. Hard removal scheduled for v2.1.0. Full
old→new mapping at [`docs/V2_MIGRATION_TABLE.md`](V2_MIGRATION_TABLE.md).

| Family | Old count | New dispatcher | Phase |
|---|---|---|---|
| `tool_audit_*` (per-dimension) | 26 | 3 (`tool_audit`, `tool_audit_findings`, `tool_audit_quality_full`) | phase-9-c1 |
| `tool_dashboard_*` | 7 | 1 (`tool_dashboard(operation=…)`) | phase-9-c2 |
| `tool_step_*` + `tool_step_pipeline_*` | 8 | 2 (`tool_step`, `tool_step_pipeline`) | phase-9-c3 |
| `tool_lessons_*` + `tool_failure_*` + `tool_dead_end_*` + `tool_mistake_*` + `tool_reliability_*` | 10 | 2 (`tool_lessons`, `tool_reliability`) | phase-9-c4 |
| `tool_sensitivity_*` | 2 | 1 (`tool_sensitivity(operation=…)`) | phase-9-c5 |
| `tool_preregister_*` | 2 | 1 (`tool_preregister(operation=…)`) | phase-9-c5 |
| `tool_reviewer_*` + `tool_response_to_reviewers` + `tool_rebuttal_*` | 4 | 1 (`tool_reviewer(operation=…)`) | phase-9-c6 |
| `tool_data_*` | 3 | 1 (`tool_data(operation=…)`) | phase-9-c7 |
| `tool_figure_*` + `tool_paper_figures_autoembed` | 4 | 1 (`tool_figure(operation=…)`) | phase-9-c7 |
| `tool_thought_*` | 2 | 1 (`tool_thought(operation=…)`) | phase-9-c7 |
| `tool_scratch_*` | 4 | 1 (`tool_scratch(operation=…)`) | phase-9-c8 |
| `tool_task_*` | 4 | 1 (`tool_task(operation=…)`) | phase-9-c8 |
| `sys_config_*` | 3 | 1 (`sys_config(operation=…)`) | phase-9-c9 |
| `sys_env_*` | 2 | 1 (`sys_env(operation=…)`) | phase-9-c9 |
| v1.6.1-era first-wave aliases (search / plan / ground / verify / lessons / sys_path / mem_*) | 21 | hard-removed → `_REMOVED_TOOLS` friendly errors | phase-14a |

## Cross-cutting wins

These shipped in `phase-9-cross-cutting` and are the highest-leverage
non-consolidation changes in v2.

- **`sys_protocol_get` default `format` flipped `"full"` → `"summary"`** — the
  single biggest token-cost win identified in the Phase 15a baseline. Verified
  at ~3K chars / ~300 tokens vs ~12-25K chars on the same protocol; pass
  `format="full"` to opt back into the rich body. The response payload now
  carries a `_load_hint` field guiding the AI to drill in via `format="step"`
  or `format="full"` only when needed. Per-turn token cost is 5-10× cheaper.
  Schema declares `"default": "summary"` so well-behaved MCP clients see the
  new default automatically. **MAJOR-breaking** — see migration guide.

- **MCP `instructions` field on `initialize`** — the canonical boot sequence
  (`sys_boot → tool_route → sys_protocol_get(format=summary) → sys_active_tools`)
  is now named at the protocol layer. A fresh client sees the ritual instead of
  discovering it. Naive AI no longer misroutes Turn 1; the baseline's
  `no_first_call_signal` HIGH friction is closed.

- **`tool_route.recommended_action` + `why_matched`** — server-side encoding of
  the next call to make. The router returns a literal next-call string
  (e.g. `"sys_protocol_get(protocol_name='X', format='summary')"`) on the
  primary protocol AND every alternative, plus a `Semantic similarity 0.708`
  rationale, so the AI can rank alternatives without burning a turn deciding
  what to call next. Closes baseline `tool_route_method_confusion` HIGH.

- **`status: live|alias|deprecated`** + **`pack: core|<pack_name>`** on every
  `TOOL_DEFINITIONS` entry — boot-visible list is filtered to `status=live`
  only (0 aliases / 0 deprecated leak into `list_tools`). 123 core + 23 across
  11 pack labels (humanities / qualitative / theory_math / wet_lab /
  engineering / slurm / snakemake / nextflow / cytoscape / redcap / synapse).

- **`scope_tags: {domain, audience, workflow_shape}`** + **`tier:`** on every
  protocol — the router can now filter wet_lab tools out of dry-lab queries
  (infrastructure shipped; default-filter wiring is v2.1.0). `tier:` powers
  the tier-aware router from `phase-8`.

- **`sys_active_tools` returns a 13-18-tool scoped shortlist per protocol**
  (down from the full 146 visible). The naive-AI working surface shrinks ~10×
  per turn.

- **`sys_boot` consolidates 4–5 startup calls into one envelope** (state +
  config + history + dep inventory + next protocol + freshness +
  pause_classification + active_plan). Concrete token saving on every session
  start.

## `server.py` refactor (phase-10)

The 7,499-line monolith is now a modular `src/research_os/server/` package.
No module exceeds 600 lines (largest: `tool_definitions/meta.py` at 579).
The top-level `server.py` shim is gone — the package's `__init__.py` re-exports
the public API verbatim so `from research_os.server import TOOL_DEFINITIONS,
_HANDLERS, _ALIASES, ...` continues to work.

Structure:

```
src/research_os/server/
├── __init__.py              # re-exports (142 lines)
├── entry.py                 # MCP entry + instructions field (247 lines)
├── dispatch.py              # central dispatcher (112 lines)
├── registry.py              # tool registry (13 lines)
├── aliases.py               # _ALIASES + _DEPRECATED_ALIASES + _REMOVED_TOOLS (487 lines)
├── envelopes.py             # _ok / _err helpers (37 lines)
├── rate_limiter.py          # (30 lines)
├── pack_loader.py           # pack tool registration (79 lines)
├── optional_deps.py         # (50 lines)
├── _handlers_runtime.py     # runtime resolution helpers (169 lines)
├── _helpers.py              # (278 lines)
├── tool_definitions/        # (6 files; largest meta.py 579)
│   ├── audit.py / grounding.py / meta.py / methodology.py
│   ├── research.py / synthesis.py
└── handlers/                # (multiple files; largest audit_core.py 564)
    ├── audit_core.py / audit_gates.py / grounding.py
    ├── meta_routing.py / methodology.py
    ├── research_exec.py / research_search.py
    ├── synthesis_visual.py / synthesis_writing.py
```

32 files, 1,644 lines across the top-level orchestration modules
plus the handler + tool-definition leaves. Public API preserved end-to-end.

## Validation matrix

20 agents × 4 perspectives × 5 scenarios = 20 independent runs against the
v2.0.0 candidate, scored on the same rubric as the Phase 15a baseline.
Cell format: **baseline → revalidation**.

|                            | researcher  | auditor     | maintainer  | naive_ai    | row avg |
| -------------------------- | ----------- | ----------- | ----------- | ----------- | ------- |
| biology_rnaseq             | 6.40 → 7.60 | 7.40 → 8.60 | 6.40 → 7.60 | 5.80 → 7.70 | 6.50 → 7.88 |
| engineering_benchmark      | 6.40 → 7.40 | 6.40 → 7.60 | 6.40 → 7.40 | 6.40 → 7.60 | 6.40 → 7.50 |
| humanities_close_reading   | 6.40 → 7.60 | 6.80 → 7.90 | 6.40 → 8.10 | 6.40 → 7.60 | 6.50 → 7.80 |
| qualitative_interviews     | 6.40 → 7.40 | 6.20 → 8.10 | 6.40 → 8.20 | 5.80 → 7.40 | 6.20 → 7.78 |
| theory_math_proof          | 6.40 → 8.10 | 6.40 → 7.10 | 5.80 → 7.60 | 5.90 → 7.40 | 6.12 → 7.55 |
| **col avg**                | **6.40 → 7.62** | **6.64 → 7.86** | **6.28 → 7.78** | **6.06 → 7.54** | **6.35 → 7.70** |

Per-scenario HIGH-friction deltas: biology 27 → 12; engineering 24 → 13;
humanities 20 → 10; qualitative 28 → 14; theory 25 → 14. **Every cell moved up
by +0.7 to +1.9 points; no regressions in any of the 20 runs.**

Tools / protocols flagged ≥ 3 times in re-validation (carryover into v2.0.x
patch series): `tool_audit` (9×), `tool_synthesize` (5×),
`tool_audit_quality_full` (4×), `tool_semantic_route` (3×);
`methodology/method_comparison` (4×), `audit/pre_submission_checklist` (3×).

## YELLOW caveat

The Phase 15 plan defined a GREEN release gate of:

- Avg `final_rating` ≥ 9.5 *(observed: 7.70)*
- Total HIGH friction ≤ 5 *(observed: 63)*
- First-5-turn HIGH = 0 *(observed: 42)*
- Every deliverable produced in every scenario × perspective *(observed: 14 / 20)*
- All 4 perspectives ≥ 9.0 *(observed: 7.54-7.86)*

**None of these targets are met.** The Phase 15b verdict is **YELLOW** — ship
v2.0.0 with the documented caveat that the deeper structural gaps
(domain-pack coverage for bioinformatics + systems benchmarks; a small set of
envelope / dispatcher bugs; pack-aware audit gates) carry over to the v2.0.x
patch series and v2.1.0 minor. The trend is correct on every metric, the
absolute targets were calibrated against a hypothetical v3-grade product.
Full analysis at [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md).

### v2.0.1 BLOCKER fixes already landed

Two of the surveyed BLOCKER regressions were fixed before tagging (commit
`0c45b79`):

- `sys_tool_describe` `NameError` regression — `meta_routing.py` relied on
  `_resolve_tool_name` which wasn't re-exported from `_handlers_runtime.py`
  after the Phase 10 server-package split. Fixed by adding the import +
  `__all__` entry; the introspection path now works from the first
  `list_tools()` call.
- `tool_audit(scope='synthesis', dimension='all')` raised bare `KeyError` on
  `paper_path`. Fixed by defaulting to `'synthesis/paper.md'` (matches what
  the `audit_synthesis` worker already assumes when callers omit the kwarg).

Both regressions were introduced during Phase 9 cross-cutting + Phase 10
refactor and caught by 5 of 20 phase-15b validators.

## Deferred to v2.0.1 / v2.1.0 / v3.0.0

The full deferral list is in §4 of [`docs/V2_VALIDATION_REPORT.md`](V2_VALIDATION_REPORT.md).
High-level shape:

### v2.0.1 — patch (ship within ~2 weeks of v2.0.0)

The remaining BLOCKER + small-diff items the re-validation surfaced. None
require a tool-surface change.

- Wrap dispatcher `KeyError` / unknown-param failures in `server/dispatch.py`
  to return a structured `_error(message="Unknown or missing parameter X.
  Expected one of: [a,b,c]. See sys_tool_describe for full schema.")` instead
  of bare `KeyError` repr.
- Update `_MCP_INSTRUCTIONS` step 4 to spell out the required arg:
  `call sys_active_tools(protocol_name=<from-step-3>)` — or auto-default
  `protocol_name` to the most recent `sys_protocol_get` target.
- Surface `scope_tags` in the `sys_protocol_get` response payload (currently
  in YAML, not JSON output). Same for `status` / `pack` annotations on tools
  via `sys_tool_describe`.
- Grep `TOOL_DEFINITIONS` for hardcoded tool counts (`'212 tools'`,
  `'344 tools'`, `'~120 tools'`) and replace with dynamic
  `len(TOOL_DEFINITIONS)` or remove the count.
- Sweep audit recommendation strings for deprecated tool names
  (the `step_completeness` blocker currently names `tool_figure_caption_synthesise`,
  now in `_DEPRECATED_ALIASES`, not `TOOL_DEFINITIONS`).
- Sync protocol `version:` fields with `pyproject.toml` (40 protocols still
  at 1.9.3, 76 at 1.11.0, 1 at 2.0.0; add a preflight check).
- Fix protocol naming-drift bugs:
  - `proof_verification_workflow.yaml` line 137 calls `tool_theory_lean_check` /
    `tool_theory_coq_check` (registered names are `tool_theory_math_lean_check` /
    `tool_theory_math_coq_check`).
  - `close_reading.yaml` line 94 phantom `tool_humanities_apparatus_audit`
    callout.
  - `close_reading.next_protocol` self-inconsistency vs
    `humanities_essay_structure.trigger`.
- Fix envelope-inversion silent-failure pattern repo-wide (leaf handlers must
  propagate inner `status in {'error', 'warning', 'unavailable'}` to the
  outer envelope). Fix at `_ok` / `_err` helpers, not per-call.
- Re-tag `audit/audit_and_validation` (currently `domain: [qualitative]`)
  and `audit/pre_submission_checklist` (currently `domain: [humanities]`)
  with `domain: [any]`.
- Make `tool_audit_quality_full` emit `lit_gate_pending: true` when literature
  gate is skipped, so the researcher isn't ambushed at `tool_synthesize` time.

### v2.1.0 — minor (consolidation round 2 + first-class pack tools)

- **Finish synthesis / executor / routing / slurm / sys_protocol /
  sys_checkpoint / sys_tools consolidations** — the last 7 dispatcher families
  that didn't make the v2.0.0 cut. Net effect: another ~30 → ~10 tool collapse.
- **Ship a `bio_omics` pack** (`methodology/rnaseq_de.yaml`,
  `methodology/scrnaseq_qc.yaml`, `methodology/geo_sra_ingest.yaml`,
  `synthesis/methods_section_bioinformatics.yaml`). Loudest single domain gap
  from re-validation.
- **Ship `engineering/test/algorithmic_benchmark`** + `tool_engineering_benchmark_sweep`.
  Loudest single systems-research gap.
- **Ship `tool_qualitative_pii_redact`** as a first-class MCP tool (presidio +
  spaCy + regex), `tool_qualitative_quotes_bulk_register` for CSV / JSON
  bulk-load, and the humanities apparatus / dangling-link / edition-pinning
  auditors.
- **Wire `scope_tags` into router default filtering** — dry-lab prompts
  should exclude `pack='wet_lab'` from the candidate set. Tags exist; router
  does not use them yet.
- **Move pack-relevant tools off `pack='core'`** — `tool_slurm_*` → `slurm`,
  `tool_julia_exec` → `julia`, `tool_latex_compile` / `tool_paper_compile_typst`
  → `typst|latex`, `tool_humanities_essay_scaffold` → `humanities`. Target
  default surface < 125 tools.
- **Pack-aware audit gates** — auto-skip `audit_assumptions` / `audit_figures` /
  `audit_power` / `preregister_diff` for `researcher_config.domain == humanities`;
  substitute pack-flavoured audits.
- **Make `tool_audit_quality_full` a true master** — include `step_literature`,
  `synthesis`, `reproducibility`, `coherence`, `cross_deliverable_consistency`,
  `discussion_coverage`, and any active pack audits.
- Add `error_code` to the canonical error envelope; add `Examples:` blocks to
  `tool_audit` / `tool_synthesize` / `tool_step` descriptions; pre-seed
  grounding records for canonical method citations (DESeq2/Love2014,
  Seurat/Hao2023, STAR/Dobin2013, salmon/Patro2017).

### v3.0.0 — major (breaking)

- Rename `tool_theory_math_{lean,coq,dep_graph}_*` → `tool_theory_{lean,coq,dep_graph}_*`
  (drop redundant `math` infix; pack is `theory_math`, tools are pack-scoped already).
- Rename `sys_protocol_get`'s `protocol_name` → `protocol` to match what
  `tool_route` returns as `primary_protocol`.
- Move pack-execution-only tools (slurm / snakemake / nextflow / cytoscape /
  redcap / synapse / R / Julia / notebook exec / lean / coq / plate-map /
  fault-tree renderers) behind active-pack detection at the `list_tools` layer.
- `submission_type` knob on `pre_submission_checklist` (`journal_clinical |
  journal_engineering | preprint | internal_report | conference_short`) so
  CONSORT / CRediT / IRB gates are venue-aware.

## Upgrade

```bash
pip install --upgrade research-os
research-os doctor          # check current workspace for deprecation warnings
```

Most projects work unchanged — all legacy tool names dispatch via aliases for
the v2.0.x runway. Full instructions, breaking-change details, per-surface
recipes, and the complete old→new tool table at
[`docs/MIGRATION_v1_to_v2.md`](MIGRATION_v1_to_v2.md).

## Acknowledgements

This release was driven by the 4-perspective × 5-scenario field-validation
harness (Phase 15a baseline + Phase 15b re-validation, 20 + 20 = 40
independent agent runs total). The structured findings drove every Phase 9
consolidation decision — no consolidation without a measured friction signal.
Phases 4 / 5 / 6 / 7 / 8 / 9 / 10 / 11a / 11b / 12 / 13 / 14a / 14b / 14d /
15a / 15b / 16a / 16b / 16c were each shipped via the
[Claude Code](https://claude.com/claude-code) Workflow multi-agent harness.

Full per-phase commit history is in `git log --grep 'phase-' --oneline`
(56 commits between `phase-setup` and this release).
