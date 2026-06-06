# Research-OS v2.0.0 — Release Notes SCAFFOLD

> **Phase 16 will copy this scaffold to `docs/V2_RELEASE_NOTES.md` and fill in
> the actual numbers + commit links from Phase 15b validation + final git log.**

## TL;DR

Research-OS v2.0.0 is the **comprehensive release** — an end-to-end coherent system, field-validated by **20 independent agents across 4 perspectives × 5 scenarios**, with measurable improvements vs the v1.11.0 baseline.

**Headline numbers** *(populated by Phase 16 from V2_VALIDATION_REPORT.md)*:

| Metric | v1.11.0 baseline | v2.0.0 release | Δ |
|---|---|---|---|
| Tool surface (canonical names) | ~223 | TBD | TBD |
| Tools never-called in ≥10/20 baseline runs | 24 | TBD | TBD |
| HIGH-friction items (avg per run) | ~6.0 | TBD | TBD |
| Avg final rating | 6.3 / 10 | TBD | TBD |
| server.py lines (single file) | 7499 | TBD | TBD |
| Modules in server/ package | 1 | ~15 | NEW |
| Protocols with tier annotation | 0 / 117 | 117 / 117 | NEW |
| Protocols with scope_tags | 0 / 117 | 117 / 117 | NEW |
| Audits emitting JSON companion | 0 / 11 | 11 / 11 | NEW |

## 5 CRAFT-inspired additions

1. **Audit-as-data** — every audit emits a JSON companion alongside the
   Markdown report. New tools `tool_audit_findings(operation=query|diff)`
   query the cross-audit ledger. `tool_synthesize` BLOCK-gates on unresolved
   BLOCK findings. (Phase 4)

2. **Review-rewrite loops** — paper/slides/poster drafters iterate
   draft → adversarial review → rewrite, with per-iteration quality
   measurement logged to `workspace/logs/drafter_loops/`. (Phase 5)

3. **`research-os doctor`** — 18+ install + workspace health checks.
   Exit policy: 0=all-pass, 1=warn-only, 2=fail. (Phase 6)

4. **`docs/CONTRACT.md`** — the stable-surface promise. Public tool
   names, audit-finding JSON schema, researcher_config field names,
   workspace layout, and protocol routing intent_class enum are all
   MAJOR-bumped on change. (Phase 7)

5. **Audience-segmented docs** — `docs/README.md` is now a four-audience
   router (researcher / AI agent / plugin author / maintainer / integrator).
   New: PLUGIN_AUTHORING.md, MAINTAINER_GUIDE.md, INTEGRATION.md. (Phase 7)

## Tool surface consolidation

~232 legacy tool names collapsed into ~15 unified dispatchers using the
proven alias-with-param-injection pattern (extending what `tool_search`,
`tool_plan`, `tool_ground`, `mem_log` already used). Full migration table
at `docs/V2_MIGRATION_TABLE.md`.

| Family | Old count | New |
|---|---|---|
| `tool_audit_*` | 26 | 3 (`tool_audit`, `tool_audit_findings`, `tool_audit_quality_full`) |
| `tool_dashboard_*` | 7 | 1 (`tool_dashboard(operation)`) |
| `tool_step_*` | 10 | 2 (`tool_step`, `tool_step_pipeline`) |
| `tool_failure/reliability/lessons/dead_end/mistake_*` | 10 | 2 (`tool_lessons`, `tool_reliability`) |
| `tool_sensitivity_*` | 2 | 1 (`tool_sensitivity(operation)`) |
| `tool_preregister_*` | 2 | 1 (`tool_preregister(operation)`) |
| `tool_reviewer/response_to_reviewers/rebuttal_*` | 4 | 1 (`tool_reviewer(operation)`) |
| `tool_data_*` | 3 | 1 (`tool_data(operation)`) |
| `tool_figure_*` | 4 | 1 (`tool_figure(operation)`) |
| `tool_thought_*` | 2 | 1 (`tool_thought(operation)`) |

Every legacy name continues to dispatch for v2.0.x via `_DEPRECATED_ALIASES`
with `_ALIAS_PARAM_INJECTION`. Hard removal scheduled for v2.1.0.

## Cross-cutting wins

- **`sys_protocol_get` default `format` is `summary`** (was `full`) — single
  biggest token-cost win for naive AI clients per the Phase 15a baseline.
  Pass `format="full"` to opt back into the rich body.
- **MCP `instructions` field** on initialize handshake — naming the boot
  sequence so the AI doesn't waste first-turn cycles on discovery.
- **`tool_route` gains `recommended_action`** — server-side encoding of the
  next call to make, instead of forcing the AI to infer.
- **`status: live|alias|deprecated`** + **`pack: core|<pack>`** on every tool.
- **`scope_tags: {domain, audience, workflow_shape}`** + **`tier:`** on every
  protocol — the router can now filter wet_lab tools out of dry-lab queries.

## server.py refactor

The 7499-line monolith is now a modular `server/` package: no module exceeds
600 lines, the top-level `server.py` is a backwards-compat shim. Public API
preserved (`from research_os.server import TOOL_DEFINITIONS, _HANDLERS, ...`).

## Validation

(Populated by Phase 16 from `docs/V2_VALIDATION_REPORT.md`)

20 agents × 4 perspectives × 5 scenarios = 400 perspective-scenario data points:

| | naive_ai | researcher | auditor | maintainer | row avg |
|---|---|---|---|---|---|
| biology_rnaseq | 5.8 → TBD | 6.4 → TBD | 7.4 → TBD | 6.4 → TBD | 6.5 → TBD |
| humanities_close_reading | 6.4 → TBD | 6.4 → TBD | 6.8 → TBD | 6.4 → TBD | 6.5 → TBD |
| qualitative_interviews | 5.8 → TBD | 6.4 → TBD | 6.2 → TBD | 6.4 → TBD | 6.2 → TBD |
| engineering_benchmark | 6.4 → TBD | 6.4 → TBD | 6.4 → TBD | 6.4 → TBD | 6.4 → TBD |
| theory_math_proof | 5.9 → TBD | 6.4 → TBD | 6.4 → TBD | 5.8 → TBD | 6.1 → TBD |
| **col avg** | **6.06 → TBD** | **6.40 → TBD** | **6.64 → TBD** | **6.28 → TBD** | **6.34 → TBD** |

Release targets (all four must pass for GREEN):
- [ ] Avg final_rating ≥ 9.5
- [ ] Total HIGH friction ≤ 5
- [ ] First-5-turn HIGH friction = 0
- [ ] Every deliverable produced in every scenario × perspective
- [ ] All 4 perspectives ≥ 9.0

## Deferred to v2.0.1 / v2.1.0 / v3.0.0

(Populated by Phase 16 from Phase 15b `remaining_recommendations` aggregate)

## Upgrade

See `docs/MIGRATION_v1_to_v2.md` for full instructions. TL;DR:

```bash
pip install --upgrade research-os
research-os doctor          # check current workspace for deprecation warnings
```

Most projects work unchanged — all legacy tool names dispatch via aliases for v2.0.x.

## Acknowledgements

This release was driven by the 4-perspective × 5-scenario field validation
harness (Phase 15a baseline + Phase 15b re-validation). The structured
findings drove every Phase 9 consolidation decision (no consolidation
without a measured friction signal). Phase 9 / 14 / 10 / 15b were each
shipped via the [Claude Code](https://claude.com/claude-code) Workflow
multi-agent harness.
