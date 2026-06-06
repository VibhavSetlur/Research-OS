# v2.1.0 — master plan

**Theme:** consistency, organization, multi-perspective validation. MINOR bump (no public-contract breaking changes). Runway-expired v1.x aliases hard-removed per `docs/V2_MIGRATION_TABLE.md`.

## Baseline (Phase 0, captured 2026-06-06 09:26 CDT)
- branch start: `feat/v2.1.0` off `main` post-v2.0.0 merge
- version: 2.0.0 → 2.1.0
- protocols: 117 core + 36 pack = 153 indexed
- tools: 146 live (with 80 back-compat aliases + 78 deprecated + 24 removed)
- server modules: 32 (largest = `tool_definitions/meta.py` at 579 LOC)
- router_index: 2027 lines
- docs: 53 markdown files
- tests: 1599 passing (+ 13 skipped)
- preflight: 24/24

## Wave layout

| Wave | Phases | Parallelism | Depends on |
|---|---|---|---|
| A | 1 rename · 2 envelope · 3 errors · 4 doc-drift | 4 Phase-leads × 8-12 file-cluster agents | — |
| B | 5 taxonomy · 6 router · 7 paper-format · 8 gates-fire | 4 Phase-leads × ~10 agents each | Wave A |
| C | 9 tier · 10 workspace · 11 pack · 12 adapter | 4 Phase-leads × 5-7 agents | Wave B |
| D | 13 multi-perspective validation | 10 perspective-agents (worktree) + 40 prompt-agents + 1 synthesis agent | Wave C |
| E | 14 fixes · 15 re-validation · 16 release | dynamic | Wave D |

## Phase-by-phase exit criteria

### Phase 1 — Filename normalization
- Decision matrix in `docs/v21_handoff/PHASE_1_RENAMES.md` ✓
- All renames executed; migration aliases at old paths
- Preflight green; tests green

### Phase 2 — Envelope standardization
- Audit table in `docs/v21_handoff/PHASE_2_ENVELOPE_AUDIT.md`
- `src/research_os/server/envelope.py` helper + decorator
- All public handlers wrapped
- Fixture test per handler asserts envelope shape
- `docs/CONTRACT.md` adds envelope to stable surface

### Phase 3 — Error messages
- Audit table in `docs/v21_handoff/PHASE_3_ERROR_AUDIT.md`
- `src/research_os/server/errors.py` with `RoError(what, why, next_action)`
- All raised exceptions inherit RoError or follow WHAT/WHY/NEXT
- FileNotFound errors include nearest-match suggestions (≤3 paths)

### Phase 4 — Doc drift
- Audit table in `docs/v21_handoff/PHASE_4_DOC_DRIFT.md`
- All tool / protocol / count references current
- All markdown links resolve

### Phase 5 — Protocol taxonomy
- Taxonomy map in `docs/v21_handoff/PHASE_5_TAXONOMY.md`
- All protocols moved
- `src/research_os/protocols/_aliases.yaml` mechanism for old path strings
- Preflight green; semantic embeddings rebuilt

### Phase 6 — Router consolidation
- Audit in `docs/v21_handoff/PHASE_6_ROUTING_AUDIT.md`
- Semantic-primary + hierarchical-fallback resolver
- `_router_index.yaml` < 500 lines (from 2027)
- `_decompositions.yaml` carries multi-tool sequences
- Routing accuracy parity or better on 30 validation queries

### Phase 7 — Paper format
- Audit in `docs/v21_handoff/PHASE_7_PAPER_FORMAT_AUDIT.md`
- Canonical: `paper.md` → `paper.typ` (or `paper.tex` if engine=latex) → `paper.pdf`
- `docs/PAPER_PIPELINE.md` written
- All 5 packs aligned

### Phase 8 — Gates fire
- Firing matrix in `docs/v21_handoff/PHASE_8_GATE_FIRING_MATRIX.md`
- Every gate either fires somewhere OR is annotated `optional`

### Phase 9 — Tier surfacing
- `current_tier.json` per project (carry from v2.0.0)
- `tool_route` output includes tier + tier_transition
- `tool_step_complete` advances tier
- dashboard header shows tier badge
- `research-os doctor` reports tier

### Phase 10 — Workspace layout canonical
- Audit in `docs/v21_handoff/PHASE_10_WORKSPACE_AUDIT.md`
- `tool_workspace_normalize` (dry-run + apply modes)
- `sys_workspace_scaffold` produces canonical from start
- Preflight check: reference projects conform

### Phase 11 — Pack consistency
- Audit in `docs/v21_handoff/PHASE_11_PACK_CONSISTENCY.md`
- `docs/PLUGIN_AUTHORING.md` is the canonical template
- All 5 packs align

### Phase 12 — Adapter consistency
- Audit in `docs/v21_handoff/PHASE_12_ADAPTER_CONSISTENCY.md`
- All 6 adapters align on hook surface

### Phase 13 — Multi-perspective validation
- 10 perspective agents run real pipelines in `/tmp/ro_v21_validation/`
- 40 random NL prompts agents run in `/tmp/ro_v21_prompts/`
- Each agent writes a structured JSON report (schema below)
- Synthesis writes `docs/V21_VALIDATION_REPORT.md`

### Phase 14 — Fix list
- Apply fixes from V21_VALIDATION_REPORT.md v2.1.0 fix list
- Regression test per fix (mandatory)

### Phase 15 — Final re-validation
- Targets:
  - Avg rating ≥ 8.5; no perspective < 7.5
  - Naive AI ≥ 8.0; researcher avg ≥ 8.5; auditor/repro avg ≥ 8.5; maintainer ≥ 8.0
  - System consistency ≥ 9.0
  - Random-prompt routing accuracy ≥ 90%
  - 0 internal contradictions; 0 stale references
- If targets miss: 1 more targeted fix pass + re-run; up to 2 iterations.
  Remaining gaps go to v2.1.1 explicitly (no rating padding).

### Phase 16 — Release
- README · START · AI_GUIDE · RESEARCHER_GUIDE · FAQ · PROTOCOLS · TOOLS · CONTRACT updated
- `docs/MIGRATION_v2_0_to_v2_1.md` written
- `docs/V21_RELEASE_NOTES.md` written
- CHANGELOG `[2.1.0]` entry
- Version bumps: pyproject + __init__ + CITATION + protocol version fields on touched protocols + router_index top-level version
- PR feat/v2.1.0 → dev → main; tag v2.1.0; PyPI confirm

## Perspective specs (Phase 13)

P1 **naive_ai** — first-time, doc-surface only · scenario: biology_rnaseq
P2 **experienced_ai** — knows RO well; wants shortcuts · scenario: humanities_close_reading
P3 **undergrad** — learning research process · scenario: qualitative_interviews (n=4 synthetic)
P4 **grad_dissertation** — rigor + reproducibility · scenario: engineering_benchmark (3 algos × 5 sizes)
P5 **postdoc_audit** — re-analyze with intentional flaws · scenario: flawed_biology_fixture
P6 **pi_review** — publication-ready review · scenario: theory_math_proof
P7 **industry** — time-constrained, applied · scenario: rapid_prototyping (throwaway tier)
P8 **methodology_auditor** — external reviewer · scenario: read P1's complete biology project
P9 **reproducibility** — can someone redo this? · scenario: read P4's engineering project
P10 **maintainer** — what breaks under refactor? · scenario: trace implicit deps in core API

## Per-perspective JSON report schema

See `docs/v21_handoff/PHASE_13_SCHEMA.md` (to be written before Wave D).

## Operating principles

- Workflow-heavy; isolation=worktree where agents mutate in parallel
- TaskList for wave + phase tracking
- Pause + ask the researcher on ambiguous decisions (e.g. dashboard naming, taxonomy edge cases)
- Honest validation accounting; no rating padding
- Hard-removed v1.x aliases ONLY past their declared runway (most expire v2.2.0, not v2.1.0)
- Preserve every historical doc (NEVER-DELETE list)
- conda env active for every session entry
