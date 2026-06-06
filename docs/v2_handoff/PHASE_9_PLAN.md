# Phase 9 — Tool Consolidation Plan (v2.0.0)

## Inputs
- Phase 15a baseline: `docs/v2_handoff/validation_baseline/*.json` (20 runs)
- 121 HIGH-friction items dominated by `tool_surface_bloat` (11×) and `tool_sprawl` (3×)
- 24 tools never-called in ≥10/20 runs; 48 tools never-called in 5–9/20 runs
- 6 tools flagged convoluted in ≥5/20 runs
- Existing scaffolding in `server.py`: `_ALIASES`, `_DEPRECATED_ALIASES`, `_ALIAS_PARAM_INJECTION`, `_REMOVED_TOOLS`

## Re-reading the signal

Many "never-called" tools are **downstream of where validation stopped** (paper_compile, slides_create, poster_create, dashboard_*) — they're useful, just unreached by the 4-turn scenarios. The actionable signal is:

1. **Family consolidation** — collapse `tool_audit_*` (26), `tool_dashboard_*` (7), `tool_step_*` (10), `tool_failure_*`/`tool_reliability_*`/`tool_lessons_*` (5+2+2), `tool_sensitivity_*` (2), `tool_preregister_*` (2), `tool_reviewer_*` (2), `tool_slurm_*` (4), `tool_data_*` (3), `tool_thought_*` (2), `tool_step_pipeline_*` (4) into one consolidated tool per family with a `scope=`/`operation=`/`source=` kwarg, mirroring the proven pattern from `tool_search` (5→1), `tool_plan` (3→1), `tool_ground` (4→2), `mem_log` (4→1).
2. **Status field + filter** — add `status: live|alias|deprecated` to every TOOL_DEFINITIONS entry; default `tool_tools_list` and `list_tools` to `live` only.
3. **Pack annotation** — `pack: core|humanities|qualitative|theory_math|wet_lab|engineering|<adapter>` on every tool; surface in `tool_route`, `sys_active_tools`, `tool_tools_list`.
4. **scope_tags on protocols** — `{domain: [...], audience: [...], workflow_shape: [...]}` so router filters wet_lab tools out of dry-lab queries.
5. **Cheap MCP-level wins** — flip `sys_protocol_get` default `format` from `full` → `summary`; add `instructions` field to MCP initialize handshake; `recommended_action` on `tool_route` output.

## Consolidation clusters (9 parallel agents)

| Cluster | Old tools (N) | New unified tool | Dispatch kwarg(s) |
|---|---|---|---|
| C1 audit | 26 → 3 | `tool_audit` (scope=, dimension=) + `tool_audit_findings` (operation=query\|diff) + `tool_audit_quality_full` (kept; aggregator) | scope ∈ {step, synthesis, project}; dimension ∈ {completeness, literature, code, prose, claims, figure, citations, assumptions, power, reproducibility, evalue, cliches, coherence, version, cross_deliverable, reviewer_responses, dashboard_content, figure_interactivity, figure_coverage, statistical_power} |
| C2 dashboard | 7 → 1 | `tool_dashboard` | operation ∈ {create, story_generate, story_edit, story_quality_bar, reviewer_sim, test_generate, test_run} |
| C3 step | 10 → 2 | `tool_step` (operation=create\|complete\|iterate\|iterations_list\|revision_options\|env_lock\|promote_to_step\|...) + `tool_step_pipeline` (operation=define\|run\|status\|diagram) | as labeled |
| C4 failure_reliability_lessons | 5 (failure)+2(reliability)+2(lessons)+1(mistake)+1(dead_end) → 1 | `tool_lessons` (operation=record\|consult\|check\|list\|replay\|dead_end) + `tool_reliability` (operation=log_event\|report) | preserve reliability_log_event semantics |
| C5 sensitivity | 2 → 1 | `tool_sensitivity` | operation ∈ {define, run} |
| C6 preregister | 2 → 1 | `tool_preregister` | operation ∈ {freeze, diff} |
| C7 reviewer | 4 (reviewer_simulate, response_to_reviewers, rebuttal_draft, reviewer_response_compile) → 1 | `tool_reviewer` | operation ∈ {simulate, rebuttal, compile, summarize} |
| C8 slurm | 4 → 1 | `tool_slurm` (in adapter pack, not core) | operation ∈ {submit, fetch, status, list} |
| C9 data + figure + thought | 3+2+2 → 3 | `tool_data` (operation=convert\|profile\|sample) + `tool_figure` (operation=palette\|caption_synthesise\|interactive_autogen) + `tool_thought` (operation=log\|trace) | as labeled |

## Per-cluster agent workflow

For each cluster the agent MUST:
1. Read the current TOOL_DEFINITIONS entries for the cluster (use `grep -n '"tool_<prefix>_' src/research_os/server.py`).
2. Read the current handlers (`_handle_tool_<prefix>_*` functions).
3. Design a unified handler that dispatches on the kwarg, preserving every legacy behavior.
4. Add the unified TOOL_DEFINITIONS entry.
5. Add `_ALIASES` entries: every old name → new name.
6. Add `_DEPRECATED_ALIASES` set entries: every old name (so deprecation telemetry fires).
7. Add `_ALIAS_PARAM_INJECTION` entries: (old_name → (kwarg, value)).
8. Verify the new handler covers every prior call signature.
9. Add one row per consolidation to `docs/V2_MIGRATION_TABLE.md`.
10. Run `python scripts/preflight.py && python -m pytest -q -k 'audit or step or dashboard or sensitivity or preregister or reviewer or data or figure or thought or lessons or reliability or failure'` (cluster-specific keyword).
11. Report PASS/FAIL + line-count delta + new tool surface count.

## Cross-cutting (run last, single agent)

After all 9 cluster agents land:
1. **Add `status` + `pack` + `scope_tags` to every TOOL_DEFINITIONS entry** (sweep `tool_definitions/registry.py` or `server.py` based on Phase 10 state).
2. **Default `sys_protocol_get` format to `summary`** (was `full`; document as MAJOR-breaking in CHANGELOG).
3. **Default `tool_tools_list` `include_deprecated=False` and add `status=live` filter** (already supported).
4. **Add MCP `instructions` field** to the initialize handshake telling the AI the boot sequence (sys_boot → tool_route → sys_protocol_get(summary) → sys_active_tools).
5. **Add `recommended_action` field to `tool_route`** output (server-side encoding of the next call to make).
6. **`scope_tags` on every protocol YAML** — sweep all 117 yamls and annotate.

## Expected end state

- Tool surface: 352 → ~120 (canonical names; aliases continue to dispatch silently for 1 minor)
- HIGH friction `tool_surface_bloat`: 11 → 0
- HIGH friction `tool_sprawl`: 3 → 0
- New `status: live|alias|deprecated` field on every tool def
- New `pack:` and `scope_tags:` annotations on every tool + protocol
- `docs/V2_MIGRATION_TABLE.md` with every old→new row + arg transformation + status (aliased v2.0.x / removed v2.1.0)
- All existing tests pass (alias dispatch preserves behavior)
- One commit per cluster: `feat(v2): consolidate <family> [phase-9-c<N>]`
