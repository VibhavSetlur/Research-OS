"""Research OS MCP server — modular package (Phase-10 split).

This is the thin shim that preserves the historical public API. Internals
live under ``research_os.server.<submodule>``; tests and external callers
keep importing ``from research_os.server import TOOL_DEFINITIONS, _HANDLERS,
main, _handle_tool_call, _handle_tool_X, search_pubmed, …`` exactly as
before.

Layout
------
* aliases.py             — _ALIASES, _DEPRECATED_ALIASES, _ALIAS_PARAM_INJECTION, _REMOVED_TOOLS
* envelopes.py           — _success, _error, _text + TextContent fallback
* optional_deps.py       — _MissingDependency, _lazy_import, _optional_dep_inventory
* rate_limiter.py        — RateLimiter + _rate_limiter
* dispatch.py            — _handle_tool_call, _resolve_tool_name, _inject_consolidation_param
* pack_loader.py         — _discover_packs_once, _discover_adapters_once
* registry.py            — TOOL_DEFINITIONS, _HANDLERS (merged from sub-modules)
* entry.py               — MCP wiring, list_tools, call_tool, main()
* tool_definitions/      — TOOL_DEFINITIONS split by domain
* handlers/              — handlers split by domain
* _helpers.py            — shared helper funcs (_log_search, _read_profile, etc.)
* _handlers_runtime.py   — shared imports for handler modules
"""
from __future__ import annotations

# ── Infrastructure modules ────────────────────────────────────────────
from .aliases import (  # noqa: F401
    _ALIAS_PARAM_INJECTION,
    _ALIASES,
    _DEPRECATED_ALIASES,
    _REMOVED_TOOLS,
)
from .envelopes import (  # noqa: F401
    HAS_MCP,
    TextContent,
    _error,
    _success,
    _text,
)
from .optional_deps import (  # noqa: F401
    _MISSING_DEPS,
    _MissingDependency,
    _lazy_import,
    _optional_dep_inventory,
)
from .rate_limiter import (  # noqa: F401
    RateLimiter,
    _rate_limiter,
)
from .dispatch import (  # noqa: F401
    _handle_tool_call,
    _inject_consolidation_param,
    _log_deprecation,
    _resolve_tool_name,
)
from .pack_loader import (  # noqa: F401
    _discover_adapters_once,
    _discover_packs_once,
)

# ── Registry (TOOL_DEFINITIONS + _HANDLERS) ───────────────────────────
from .registry import TOOL_DEFINITIONS, _HANDLERS  # noqa: F401

# ── Helpers shared by handlers (re-exported for tests) ────────────────
from ._helpers import (  # noqa: F401
    _AUDIT_DISPATCH,
    _STEP_DISPATCH,
    _STEP_PIPELINE_DISPATCH,
    _build_tier_progress,
    _build_tree,
    _latest_protocol_for_step,
    _log_search,
    _read_profile,
    _recommended_action_for_route,
)

# ── Lazy-imported tool actions (tests monkeypatch on
#    research_os.server.search_pubmed etc.) ─────────────────────────────
from ._handlers_runtime import (  # noqa: F401
    abandon_path,
    create_checkpoint,
    create_path,
    download_literature,
    env_docker_generate,
    env_snapshot,
    get_config,
    get_next_protocol,
    init_config,
    list_checkpoints,
    list_paths,
    list_protocols,
    load_protocol,
    notify_researcher,
    package_install,
    rollback_checkpoint,
    scrape_web,
    search_arxiv,
    search_crossref,
    search_pubmed,
    search_semantic_scholar,
    search_web,
    session_handoff,
    set_config,
    validate_config,
    validate_protocol,
    _profile_inputs,
)

# ── MCP entry point (triggers pack discovery + metadata annotation) ──
from .entry import (  # noqa: F401
    _MCP_INSTRUCTIONS,
    _annotate_core_tool_metadata,
    _inject_api_keys,
    _resolve_project_root,
    _short_for_list,
    main,
)

# When the MCP package is installed, expose the Server object + run_stdio
# (used by older entry points / smoke tests).
try:
    from .entry import call_tool, list_tools, run_stdio, server  # noqa: F401
except ImportError:  # pragma: no cover
    pass


# ── Re-export every handler function (for tests that do
#    ``from research_os.server import _handle_tool_X``) ─────────────────
from .handlers.meta_routing import *  # noqa: F401,F403
from .handlers.meta_workspace import *  # noqa: F401,F403
from .handlers.meta_sys import *  # noqa: F401,F403
from .handlers.meta_help import *  # noqa: F401,F403
from .handlers.research_search import *  # noqa: F401,F403
from .handlers.research_exec import *  # noqa: F401,F403
from .handlers.audit_core import *  # noqa: F401,F403
from .handlers.audit_gates import *  # noqa: F401,F403
from .handlers.synthesis_writing import *  # noqa: F401,F403
from .handlers.synthesis_visual import *  # noqa: F401,F403
from .handlers.synthesis_reviewer import *  # noqa: F401,F403
from .handlers.methodology import *  # noqa: F401,F403
from .handlers.grounding import *  # noqa: F401,F403
