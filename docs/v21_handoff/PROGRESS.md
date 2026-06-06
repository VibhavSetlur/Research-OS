# v2.1.0 — final ship summary

## TL;DR

**v2.0.0 + v2.1.0 both shipped to PyPI on 2026-06-06.**

- v2.0.0: https://pypi.org/project/research-os/2.0.0/ · https://github.com/VibhavSetlur/Research-OS/releases/tag/v2.0.0
- v2.1.0: https://pypi.org/project/research-os/2.1.0/ · https://github.com/VibhavSetlur/Research-OS/releases/tag/v2.1.0

## v2.1.0 phase ledger

| Phase | Status | Output |
|---|---|---|
| Phase 0 — ground truth | done | state_phase0_<ts>.txt, V21_MASTER_PLAN.md |
| Wave A / Phase 1 — filename rename | done | dashboard_v2 → dashboard_app (+ migration shims at old paths) |
| Wave A / Phase 2 — envelope | done | v2.1.0 envelope shape via central `_success`/`_error`; auto-lifts payload fields; tokens_estimate heuristic; ro_version from `__version__` |
| Wave A / Phase 3 — errors | done | `RoError(what, why, next_action)` + dispatcher catches for RoError/KeyError/TypeError/FileNotFoundError; did-you-mean on unknown tool + protocol typos |
| Wave A / Phase 4 — doc drift (targeted) | done | dashboard_v2 references swept in live docs; CONTRACT §A.6.1 + §A.6.2 added |
| Wave B / Phase 5 — protocol taxonomy reorg | DEFERRED to v2.2.0 | needs dedicated session |
| Wave B / Phase 6 — router slim | DEFERRED to v2.2.0 | needs Phase 5 first |
| Wave B / Phase 7 — paper pipeline doc | done | docs/PAPER_PIPELINE.md |
| Wave B / Phase 8 — gates firing matrix | done | PHASE_8_GATE_FIRING_MATRIX.md (audit only); wiring deferred to v2.1.x |
| Wave C / Phases 9-12 | DEFERRED to v2.1.x | tier surfacing, workspace normalize, pack consistency, adapter consistency — audits only |
| Wave D / Phase 13 — 10-perspective validation | done | V21_VALIDATION_REPORT.md (5.54/10 avg baseline; 18 surfaced fixes) |
| Wave E / Phase 14 — apply fixes (11 of 18) | done | FIX-1, 2, 3, 4, 5, 8, 9, 11, 13, 14, 18 |
| Wave E / Phase 15 — mini re-validation | done | PHASE_15_MINI_REVALIDATION.md (9/9 spot-checks PASS) |
| Wave E / Phase 16 — release | done | CHANGELOG 2.1.0; PR feat → dev (#68); dev → main (#69); tag v2.1.0 on b19cab9; PyPI 2.1.0 confirmed |

## Numbers (final)

| Metric | v1.11.0 baseline | v2.0.0 | v2.1.0 |
|---|---|---|---|
| Tool surface | 344 | 146 | 146 (unchanged this cycle) |
| Server modules | 1 (6,813 LOC) | 32 (largest 579) | 32 |
| Protocols (core + packs) | 117 | 153 | 153 |
| Router_index lines | 1,977 | 2,027 | 2,054 (added triggers; slim deferred to v2.2.0) |
| Tests | 899 | 1,599 | 1,605 (+ 6 v2.1.0 regression tests) |
| Preflight | 22/22 | 24/24 | 24/24 |
| Wave-D 10-perspective avg | 6.35 | 7.70 | 5.54 baseline → ~7.0-7.5 projected after 11 fixes |
| CodeQL (PR) | n/a | fail (148 surfaced) | **pass** |

## v2.1.x deferred work (acknowledged in CHANGELOG)

Honest gap between current ~7.0-7.5 projection and 8.5 GREEN target:

- FIX-6 — narrow handler-level `except Exception` (7/10 perspectives)
- FIX-7 — migrate pack tools to v2.1.0 envelope (5/10)
- FIX-10 — extend AI_GUIDE/TOOLS/RESEARCHER_GUIDE with v2.1.0 docs (4/10)
- FIX-12 — pack-context bias in router (5/10; v2.2.0 architectural)
- FIX-15 — causal-language detector defaults (2/10 BLOCK for methodology audit)
- FIX-16 — namespace-aware did-you-mean ranking (5/10)
- FIX-17 — re-tag mis-scope-tagged protocols (2/10)

Phase 5 (taxonomy reorg) + Phase 6 (router slim) deferred to v2.2.0.

## Validation evidence shipped

- `docs/V21_VALIDATION_REPORT.md` — 386 lines, full 10-perspective × 6-dimension matrix, friction-points-by-frequency table, worst-prompt analysis, v2.1.0 / v2.1.x / v2.2.0 / v3.0.0 deferral roadmap
- `docs/v21_handoff/PHASE_15_MINI_REVALIDATION.md` — 9 spot-check matrix
- 7 phase-handoff files in `docs/v21_handoff/`

## Total artifact count

- Commits on feat/v2.1.0: 10 (phase-0 scaffold + 4 Wave-A + 1 Wave-B + 4 Wave-E batches)
- Files written/edited: ~40
- Tests added: 6 (test_v210_envelope_shape × 11 + test_v210_errors × 6 - delta from pre-existing)
- Total agent invocations in Wave D: 31 (10 perspectives + 20 prompts + 1 synthesis)
