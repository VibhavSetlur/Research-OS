# v2.1.0 — live progress tracker

Updated as each phase lands. Append-only narrative + state-of-play.

## Phase 0 — ground truthing (2026-06-06)

Captured baseline state on `feat/v2.0.0` pre-ship:
- protocols: 117 core + 36 pack
- tools: 146 live
- server modules: 32
- router_index: 2027 lines
- docs: 53 markdown files
- tests: 1599 passing (+ 13 skipped)
- preflight: 24/24

State files in this directory:
- `state_phase0_<timestamp>.txt` — preflight + git output
- `V21_MASTER_PLAN.md` — wave layout + per-phase exit criteria
- `PHASE_1_RENAMES.md` — rename decision matrix
- `PHASE_2_ENVELOPE_AUDIT.md` — 212 handlers; all FLAT_DICT; subclass-dict migration recommended
- `PHASE_3_ERROR_AUDIT.md` — 506 error sites; 360 WHAT_ONLY (71%) · 97 EMPTY_EXCEPT · 32 BARE_TYPE
- `PHASE_13_SCHEMA.md` — perspective-agent JSON report schema

## HALF 1 — v2.0.0 ship status (COMPLETE pending PyPI)

| Step | Status | Commit / Ref |
|---|---|---|
| Restore deleted historical docs | done | 4a0b16e |
| Commit PHASE_16_FINAL_REPORT | done | baf63c9 |
| Release gate (preflight 24/24, pytest 1599 pass, ruff clean) | done | b83fafe |
| Push feat/v2.0.0 | done | — |
| PR #66 feat → dev | merged | 59bd6de |
| PR #67 dev → main | merged | 373c5a5 |
| Tag v2.0.0 | done | tag pushed |
| publish.yml workflow | in_progress | — |
| release.yml workflow | in_progress | — |
| PyPI 2.0.0 confirmed | waiting | — |
| GH Release auto-created | waiting | — |

## HALF 2 — v2.1.0 wave status

| Wave | Status |
|---|---|
| A — foundational fixes (Phases 1-4) | pre-work done; inventory ready; awaits PyPI confirm to begin |
| B — structural cleanup (Phases 5-8) | pending |
| C — UX polish (Phases 9-12) | pending |
| D — 10-perspective validation (Phase 13) | pending |
| E — fix + re-validate + release (Phases 14-16) | pending |
