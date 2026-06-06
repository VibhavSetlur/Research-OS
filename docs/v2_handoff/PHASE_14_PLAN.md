# Phase 14 — Deprecation Cleanup Plan (v2.0.0)

## Dependency
Must run AFTER Phase 9 (consolidation) so the v2.0.0 alias surface is finalized.

## Removal categories

### 14a — v1.6.1 deprecated aliases (runway expired)
v1.6.1 introduced the first wave of consolidation aliases. v2.0.0 is at least 4 MINOR versions past, so the runway is expired.

Per the existing `_DEPRECATED_ALIASES` set (line 7009 of `server.py` pre-refactor), every alias listed there as of v1.6.1 is eligible. Phase 9 will ADD new aliases (these stay), Phase 14 REMOVES the v1.6.1-era ones.

Workflow:
1. `git log --diff-filter=A -- src/research_os/server.py` to find when each alias was introduced.
2. Any alias introduced ≤ v1.6.1: candidate for removal.
3. Move from `_ALIASES` / `_DEPRECATED_ALIASES` into `_REMOVED_TOOLS` with a helpful redirect message ("renamed to X in v1.6.1, removed in v2.0.0; call X instead").

### 14b — v1.5.0 orphan tools (kept for stress-matrix; now cleaned)
Audit each `_handle_tool_*` for grep results. If zero callers in protocols, docs, tests, AND no entry-point pack uses it → remove tool + handler.

### 14c — tikzposter LaTeX path (Phase 2 replaced)
v1.11.0 replaced tikzposter with Typst poster. The LaTeX path is dead code.

Find:
- `tools/actions/synthesis/poster_latex_*`
- `templates/poster_latex/*`
- Any `tool_poster_create` branch that dispatches to LaTeX

Remove all. Add `_REMOVED_TOOLS` entry for any tool name that callers might still try.

### 14d — V2_MIGRATION_TABLE.md REMOVE column
Every row in `docs/V2_MIGRATION_TABLE.md` with `status: removed v2.0.0` (not aliased). Execute the removal.

### 14e — Dead config fields (v1.9.2 audit Lens 7)
The v1.9.2 audit identified config fields that were declared but never read. The fields:
- (read `git log --grep "Lens 7" --all` to find the original audit doc)
- Cross-reference each field against `grep -rn "<field>" src/`

Remove from:
- `researcher_config.yaml` defaults
- `src/research_os/researcher_config.py` schema
- Any docs that mention them

### 14f — Dead code (v1.9.2 audit Lens 9)
Same provenance: Lens 9 listed unreferenced functions/classes. Validate against current `grep` and remove.

## Per-removal checklist
For each file/symbol slated for removal:
1. `grep -rn '<symbol>' src/ tests/ docs/ templates/` — must show ZERO real callers.
2. Check `entry_points` in `pyproject.toml` — no plugin depends on it.
3. Delete the symbol or file.
4. If it was a tool: add `_REMOVED_TOOLS[name]` with a helpful migration message.
5. Add a CHANGELOG `### Removed` entry under v2.0.0 with the replacement path.
6. Run `python scripts/preflight.py && python -m pytest -q`. If any test fails, the removal had a hidden dependency — investigate.

## Workflow
- 4 parallel agents:
  - Agent A: 14a (alias expiration sweep)
  - Agent B: 14b + 14c (orphan tools + tikzposter)
  - Agent C: 14d (migration table REMOVE rows)
  - Agent D: 14e + 14f (dead config fields + dead code)
- Each agent commits separately: `chore(v2): remove <category> [phase-14<letter>]`

## Constraint
- DO NOT remove a tool whose deprecation runway is < 3 minor cycles old.
- DO NOT modify behavior — only deletions.
- If grep shows a real caller, that means the removal is premature; document the blocker and skip.
