// Phase 10 — server.py Refactor
// SINGLE AGENT. Holistic refactor of 7499-line server.py into modular server/ package.

export const meta = {
  name: 'v2-phase-10-server-refactor',
  description: 'Phase 10: split server.py into modular server/ package (single holistic agent)',
  phases: [
    { title: 'Server refactor', detail: 'one agent, ~600 lines per new module, tests must pass after each move' },
  ],
}

const REPO = '/scratch/vsetlur/Research-OS'
const CONDA = `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`

phase('Server refactor')

const result = await agent(
  `Phase 10 — server.py refactor (SINGLE AGENT, do not fan out internally).

CWD: ${REPO}
Branch: feat/v2.0.0
Conda env: ${CONDA}

CONTEXT
=======
After Phase 9 + Phase 14, src/research_os/server.py is now smaller (probably ~5500 lines after consolidation + removals). We need to split it into a modular package so no single file exceeds 600 lines (300 lines for the entry).

READ FIRST
==========
- docs/v2_handoff/PHASE_10_PLAN.md (target layout, constraints, workflow)
- The current src/research_os/server.py (read the full file once you know its post-Phase-9 length)

TARGET LAYOUT
=============
    src/research_os/server/
        __init__.py                    # re-exports public API for backwards compat
        entry.py                       # ≤300 lines — MCP wiring (Server instance, list_tools, dispatch glue)
        registry.py                    # TOOL_DEFINITIONS + _HANDLERS dicts (assembled from sub-modules)
        aliases.py                     # _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS
        dispatch.py                    # _handle_tool_call, _resolve_tool_name, _inject_consolidation_param
        pack_loader.py                 # _discover_packs_once + plugin discovery
        rate_limiter.py                # RateLimiter + _rate_limiter instance
        envelopes.py                   # _success, _error, _text helpers
        optional_deps.py               # _MissingDependency, _lazy_import, _optional_dep_inventory
        tool_definitions/
            __init__.py                # merges sub-module dicts into TOOL_DEFINITIONS
            audit.py
            synthesis.py
            viz.py
            research.py
            methodology.py
            grounding.py
            meta.py                    # sys_*, tool_route, tool_protocols_list, tool_tools_list, etc.
            packs.py                   # post-discovery pack-tool registration glue
        handlers/
            __init__.py                # merges sub-module dicts into _HANDLERS
            audit.py | synthesis.py | viz.py | research.py | methodology.py | grounding.py | meta.py | packs.py
- The old src/research_os/server.py becomes a thin SHIM:
    \`\`\`python
    from research_os.server.entry import *  # noqa: F401,F403
    from research_os.server.registry import TOOL_DEFINITIONS, _HANDLERS  # noqa: F401
    from research_os.server.aliases import _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS  # noqa: F401
    \`\`\`

WORKFLOW (DO IN THIS ORDER)
============================
1. \`${CONDA} && python -m pytest -q\` — baseline test count + pass.
2. Create src/research_os/server/ directory + empty __init__.py.
3. Move the SMALLEST modules first (least dependent):
   a. rate_limiter.py → move RateLimiter class + _rate_limiter instance.
   b. envelopes.py → move _success, _error, _text helpers.
   c. optional_deps.py → move _MissingDependency, _lazy_import, _optional_dep_inventory.
   d. aliases.py → move _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS.
   e. dispatch.py → move _handle_tool_call, _resolve_tool_name, _inject_consolidation_param.
   f. pack_loader.py → move _discover_packs_once.
4. After EACH module move: replace original code in server.py with \`from research_os.server.<module> import *\` or similar, then run \`python -m pytest -q\`. If it fails, fix BEFORE continuing.
5. Now split TOOL_DEFINITIONS. Read the full dict, group entries by tool-name prefix into the domain modules under tool_definitions/. For each:
   - Create the module (e.g. tool_definitions/audit.py) with \`AUDIT_TOOL_DEFINITIONS: dict = {...}\` containing only that domain's entries.
   - In tool_definitions/__init__.py: \`TOOL_DEFINITIONS = {**AUDIT_TOOL_DEFINITIONS, **SYNTHESIS_TOOL_DEFINITIONS, ...}\`
6. Similarly split _HANDLERS into handlers/<domain>.py modules.
7. Move the remaining \`_handle_tool_*\` functions to their matching handlers/<domain>.py module.
8. Create entry.py with the MCP \`Server(name='research-os', ...)\` wiring + the list_tools handler + the call_tool handler. Keep it ≤300 lines.
9. Reduce src/research_os/server.py to the thin shim (above).
10. \`wc -l src/research_os/server.py\` — confirm ≤300 lines.
11. \`wc -l src/research_os/server/*.py src/research_os/server/tool_definitions/*.py src/research_os/server/handlers/*.py\` — confirm none exceed 600 lines.
12. Final \`python scripts/preflight.py && python -m pytest -q && ruff check src/\` — full pass required.
13. Single commit: \`refactor(v2): split server.py into modular server/ package [phase-10]\`

CONSTRAINTS
===========
- DO NOT remove, rename, or change semantics of any tool. This is PURE refactor.
- DO NOT change any handler logic.
- DO NOT remove _ALIASES entries.
- ONLY move code; add imports + shims for backwards compat.
- If you find legitimate duplicate code while refactoring, document it for a follow-up PR but DO NOT consolidate in this commit.
- If after refactor a test fails that didn't fail before: REVERT the most-recent module move and isolate.

REPORT BACK
===========
- Final \`wc -l\` for src/research_os/server.py and every new module.
- Confirmation: all baseline tests still pass.
- Confirmation: preflight 23/24 or 24/24.
- Commit SHA.
- Any code patterns that smelled like duplicates (for v2.1.0 follow-up).
- Any module that came out >600 lines (with justification, e.g. tool defs for a large domain).`,
  { label: 'phase-10-refactor', phase: 'Server refactor' }
)

return { result }
