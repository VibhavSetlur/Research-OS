# Migrating from Research-OS v1.x to v2.0.0 — SCAFFOLD

> **Phase 16 will copy this scaffold to `docs/MIGRATION_v1_to_v2.md` and fill in the actual
> renames, arg transformations, and per-pack notes from the V2_MIGRATION_TABLE.md that
> Phase 9 produces.** This file is a working outline so Phase 16 doesn't start from scratch.

## Upgrade in 5 steps

1. `pip install --upgrade research-os` (gets v2.0.0).
2. `research-os doctor` — surfaces any deprecation warnings in your current workspace.
3. Read the "Breaking changes" section below; update any explicit tool-name calls in your
   notes / scripts.
4. Re-run your last project with the new tool surface; old names alias to the new ones
   for v2.0.x so most projects will work unchanged.
5. Before v2.1.0 lands (deferred items): rename old call sites in your custom integrations.

## Breaking changes

### `sys_protocol_get` default `format` is now `summary`

Old:
```yaml
- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop"}
  # returned the full body (~5K tokens)
```

New:
```yaml
- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop"}
  # returns the summary (~500 tokens)

- tool: sys_protocol_get
  args: {protocol_name: "methodology/literature_loop", format: "full"}
  # opt back in to the full body explicitly
```

Reason: the Phase 15a baseline measured `sys_protocol_get(format="full")`-by-default as
the single biggest token-cost win for naive AI clients. The default flip is MAJOR-breaking
but the explicit `format="full"` arg keeps prior behavior available.

### Tool surface consolidated (~232 → ~15 unified)

Every legacy tool name still works via `_DEPRECATED_ALIASES` with automatic
parameter injection — calling `tool_audit_step_completeness(...)` continues to do
exactly what it did in v1.x. But the legacy names will be HARD-removed in v2.1.0.
Before then, update call sites to the new canonical names:

(table populated by Phase 16 from `docs/V2_MIGRATION_TABLE.md`)

| v1.x name | v2.0.x dispatch | v2.1.0 status |
|-----------|-----------------|---------------|
| tool_audit_step_completeness | tool_audit(scope="step", dimension="completeness") | removed |
| tool_audit_step_literature | tool_audit(scope="step", dimension="literature") | removed |
| tool_audit_synthesis | tool_audit(scope="synthesis", dimension="all") | removed |
| (...full list in V2_MIGRATION_TABLE.md...) | | |

### Removed in v2.0.0 (no alias)

(populated by Phase 14)

- v1.6.1-era deprecated aliases — runway expired 3+ MINOR cycles ago.
- Orphan tools — defined but never called by any protocol/doc/test.
- tikzposter LaTeX poster path — replaced by Typst poster in v1.11.0.
- Dead config fields from the v1.9.2 Lens 7 audit.

For each removed name, calling it now returns a helpful error message naming the
replacement path (`_REMOVED_TOOLS[name]`).

## New surface in v2.0.0 (additive — won't break anything)

- `research-os doctor` — diagnostic command (18+ checks).
- `research-os ide config-path <name>` — print MCP config path for one IDE.
- `tool_audit(scope, dimension, ...)` — unified per-dimension audit dispatcher.
- `tool_audit_findings(operation=query|diff, ...)` — query the cross-audit ledger.
- `tool_protocols_list`, `tool_tools_list` — flat AI-friendly discovery lists.
- `tool_dashboard`, `tool_step`, `tool_step_pipeline`, `tool_lessons`, `tool_reliability`,
  `tool_sensitivity`, `tool_preregister`, `tool_reviewer`, `tool_data`, `tool_figure`,
  `tool_thought` — consolidated family dispatchers (operation kwarg).
- `tool_route` output gains `recommended_action`, `tier`, `tier_transition`, `why_matched`.
- MCP `instructions` field on initialize — names the boot sequence.
- Every tool now has `status: live|alias|deprecated` + `pack: core|<pack>`.
- Every protocol now has `scope_tags: {domain, audience, workflow_shape}` + `tier:`.

## Per-pack notes

(populated by Phase 16 from per-pack readme + Phase 12 matrix)

### humanities
### qualitative
### theory_math
### wet_lab
### engineering

## Config field changes

(populated by Phase 14e)

- `researcher_config.synthesis.drafter_loop_enabled` (default true, NEW)
- `researcher_config.synthesis.drafter_loop_max_iterations` (default 3, NEW)
- `researcher_config.synthesis.drafter_loop_quality_threshold` (default 0.10, NEW)

## Validation

Phase 15b measured the upgrade impact via the same 20-agent multi-perspective harness
that produced the v1.11.0 baseline. Headline numbers in `docs/V2_VALIDATION_REPORT.md`.
