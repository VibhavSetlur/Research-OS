# Phase 10 — server.py Refactor Plan (v2.0.0)

## Starting state
- `src/research_os/server.py` = 7499 lines (one mega-module)
- 352 tool definitions in `TOOL_DEFINITIONS` (post-Phase-9 will be smaller)
- `_ALIASES`, `_DEPRECATED_ALIASES`, `_ALIAS_PARAM_INJECTION`, `_REMOVED_TOOLS` all here
- `_HANDLERS` dict mapping tool_name → handler fn here
- Pack discovery (`_discover_packs_once`) here
- MCP wiring (`list_tools`, `_handle_tool_call`) here
- 6 `_handle_<top>` functions (sys_protocol_*, sys_boot, etc.)
- ~200 `_handle_tool_<name>` functions

## Goal
- `src/research_os/server.py` ≤ 300 lines (entry, MCP wiring, imports the rest)
- Modules ≤ 600 lines each
- Public API preserved: `from research_os.server import TOOL_DEFINITIONS, _HANDLERS, ...` still works

## Target layout
```
src/research_os/server/
    __init__.py                    # re-exports public API
    entry.py                       # ≤300 lines — MCP wiring, list_tools, dispatch glue
    registry.py                    # TOOL_DEFINITIONS + _HANDLERS dicts (assembled from sub-modules)
    aliases.py                     # _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS
    dispatch.py                    # _handle_tool_call, _resolve_tool_name, _inject_consolidation_param
    pack_loader.py                 # _discover_packs_once + plugin discovery
    rate_limiter.py                # RateLimiter + _rate_limiter instance
    envelopes.py                   # _success, _error, _text helpers
    optional_deps.py               # _MissingDependency, _lazy_import, _optional_dep_inventory
    tool_definitions/              # tool defs by domain (the dict literal SPLIT)
        __init__.py                # merges into TOOL_DEFINITIONS
        audit.py
        synthesis.py
        viz.py
        research.py
        methodology.py
        grounding.py
        meta.py                    # sys_* and tool_route, tool_protocols_list, etc.
        packs.py                   # pack-installed tool registration glue
    handlers/                      # handler functions by domain (mirrors tool_definitions/)
        __init__.py                # merges into _HANDLERS
        audit.py
        synthesis.py
        viz.py
        research.py
        methodology.py
        grounding.py
        meta.py
        packs.py
```

## Backwards compatibility
- `src/research_os/server.py` becomes a thin shim:
  ```python
  from research_os.server.entry import *
  from research_os.server.registry import TOOL_DEFINITIONS, _HANDLERS
  from research_os.server.aliases import _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS
  ```
- All existing tests must keep passing without modification.
- All imports from `research_os.server` must keep resolving.

## SINGLE-AGENT workflow
This phase is a HOLISTIC refactor — DO NOT fan out. One agent that:
1. Creates the new `src/research_os/server/` package directory + `__init__.py` shim.
2. Moves dispatch / aliases / rate limiter / envelopes / optional_deps first (smallest, most-stable).
3. Splits TOOL_DEFINITIONS into domain-grouped modules under `tool_definitions/`. For each domain, scan the existing entries and group by tool-name prefix or thematic family.
4. Splits the `_handle_*` functions into matching modules under `handlers/`.
5. Splits pack discovery into `pack_loader.py`.
6. Rewrites `entry.py` to be the thin MCP wiring layer (importing dispatch + registry + aliases).
7. Reduces the top-level `server.py` to a shim that re-exports.
8. After EACH module move: run `python -m pytest -q` and `python scripts/preflight.py`. If anything fails, fix before continuing.
9. At the end: verify `wc -l` on every new module ≤ 600 lines, and on `server.py` ≤ 300 lines.
10. Commit once at the end: `refactor(v2): split server.py into modular server/ package [phase-10]`.

## Constraint
- DO NOT remove or rename any tools.
- DO NOT change any tool signatures.
- DO NOT remove `_ALIASES` entries.
- DO NOT alter handler logic.
- ONLY move code into new files + add import shims.
