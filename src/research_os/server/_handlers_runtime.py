"""Shared imports for handler modules.

Phase-10 modular split: every handlers/<domain>.py file imports from here
via `from ._handlers_runtime import *` so all handlers see the same
module-level surface (envelope helpers, lazy-imported tool actions, logger,
common stdlib modules) that the old monolithic server.py provided.
"""
from __future__ import annotations

import argparse  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import subprocess  # noqa: F401
import sys  # noqa: F401
import time  # noqa: F401
from collections import defaultdict  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401


logger = logging.getLogger("research-os.server")


# ── Envelope helpers ─────────────────────────────────────────────────
from .envelopes import HAS_MCP, TextContent, _error, _success, _text  # noqa: E402,F401

# ── Optional-dep helpers ─────────────────────────────────────────────
from .optional_deps import (  # noqa: E402,F401
    _MISSING_DEPS,
    _MissingDependency,
    _lazy_import,
    _optional_dep_inventory,
)

# ── project_ops re-exports ───────────────────────────────────────────
from research_os.project_ops import (  # noqa: E402,F401
    _update_workflow_mermaid,
    _update_manifest,
    compute_file_hash,
    load_state,
    now_iso,
    scaffold_minimal_workspace,
    log_decision,
)


# ── Lazy imports of optional dependencies (shared with _core) ────────
search_web, scrape_web = _lazy_import(
    "research_os.tools.actions.search",
    ["search_web", "scrape_web"],
)
package_install, env_snapshot, env_docker_generate = _lazy_import(
    "research_os.tools.actions.exec",
    ["package_install", "env_snapshot", "env_docker_generate"],
)
create_checkpoint, rollback_checkpoint, list_checkpoints = _lazy_import(
    "research_os.tools.actions.state",
    ["create_checkpoint", "rollback_checkpoint", "list_checkpoints"],
)
create_path, abandon_path, list_paths = _lazy_import(
    "research_os.tools.actions.state",
    ["create_path", "abandon_path", "list_paths"],
)
download_literature, = _lazy_import(
    "research_os.tools.actions.search",
    ["download_literature"],
)
get_config, set_config, init_config, validate_config = _lazy_import(
    "research_os.tools.actions.state",
    ["get_config", "set_config", "init_config", "validate_config"],
)
(append_agent_note,) = _lazy_import(
    "research_os.tools.actions.state",
    ["append_agent_note"],
)
notify_researcher, session_handoff = _lazy_import(
    "research_os.tools.actions.state",
    ["notify_researcher", "session_handoff"],
)
search_semantic_scholar, search_pubmed, search_crossref, search_arxiv = _lazy_import(
    "research_os.tools.actions.search",
    [
        "search_semantic_scholar",
        "search_pubmed",
        "search_crossref",
        "search_arxiv",
    ],
)
load_protocol, list_protocols, validate_protocol, get_next_protocol = _lazy_import(
    "research_os.tools.actions.protocol",
    ["load_protocol", "list_protocols", "validate_protocol", "get_next_protocol"],
)
_profile_inputs, = _lazy_import(
    "research_os.tools.actions.data",
    ["_profile_inputs"],
)


# ── Tool definitions (some handlers reference TOOL_DEFINITIONS for
#    introspection — sys_tool_describe, sys_active_tools, etc.) ──────
from research_os.server.tool_definitions import TOOL_DEFINITIONS  # noqa: E402,F401


# Alias surface used by sys_tool_describe / tool_tools_list / etc.
from .aliases import (  # noqa: E402,F401
    _ALIASES,
    _DEPRECATED_ALIASES,
    _ALIAS_PARAM_INJECTION,
    _REMOVED_TOOLS,
)

# Dispatcher resolution used by sys_tool_describe to follow alias chains.
from .dispatch import _resolve_tool_name  # noqa: E402,F401


# Shared helper funcs used by multiple handler modules (_log_search,
# _read_profile, _recommended_action_for_route, _build_tree,
# _latest_protocol_for_step).
from ._helpers import (  # noqa: E402,F401
    _log_search,
    _read_profile,
    _recommended_action_for_route,
    _build_tree,
    _latest_protocol_for_step,
    _build_tier_progress,
    _AUDIT_DISPATCH,
    _STEP_DISPATCH,
    _STEP_PIPELINE_DISPATCH,
)


# Names exported via `from ._handlers_runtime import *` — must include
# the underscore-prefixed envelope helpers and lazy-imported tool actions.
__all__ = [
    # aliases
    "_ALIASES", "_DEPRECATED_ALIASES", "_ALIAS_PARAM_INJECTION", "_REMOVED_TOOLS",
    "_resolve_tool_name",
    # helpers
    "_log_search", "_read_profile", "_recommended_action_for_route",
    "_build_tree", "_latest_protocol_for_step", "_build_tier_progress",
    # audit + step dispatch tables (tool_dashboard removed in v2.3.0)
    "_AUDIT_DISPATCH",
    "_STEP_DISPATCH", "_STEP_PIPELINE_DISPATCH",
    # stdlib + common
    "Any", "Path", "argparse", "dataclass", "defaultdict",
    "json", "logger", "logging", "os", "subprocess", "sys", "time",
    # MCP types
    "HAS_MCP", "TextContent",
    # envelopes
    "_text", "_success", "_error",
    # optional-deps
    "_MISSING_DEPS", "_MissingDependency", "_lazy_import", "_optional_dep_inventory",
    # project_ops
    "_update_workflow_mermaid", "_update_manifest",
    "compute_file_hash", "load_state", "now_iso",
    "scaffold_minimal_workspace", "log_decision",
    # lazy imports
    "search_web", "scrape_web",
    "package_install", "env_snapshot", "env_docker_generate",
    "create_checkpoint", "rollback_checkpoint", "list_checkpoints",
    "create_path", "abandon_path", "list_paths",
    "download_literature",
    "get_config", "set_config", "init_config", "validate_config",
    "append_agent_note",
    "notify_researcher", "session_handoff",
    "search_semantic_scholar", "search_pubmed", "search_crossref", "search_arxiv",
    "load_protocol", "list_protocols", "validate_protocol", "get_next_protocol",
    "_profile_inputs",
    # registry
    "TOOL_DEFINITIONS",
]
