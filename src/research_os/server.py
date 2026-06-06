#!/usr/bin/env python3
"""Research OS MCP server.

Exposes a focused set of MCP tools that an AI IDE (Cursor, Claude, Antigravity,
OpenCode, etc.) uses to drive a reproducible research workflow.

Conventions
-----------
* Tool names use underscores (e.g. ``sys_state_get``). For backward compatibility
  the dispatcher also accepts dot notation (``sys.state.get``) and rewrites it.
* Every handler returns a JSON envelope of the shape::
      {"status": "success"|"error", "data": {...}, "error": "..."}
* Errors are caught at the dispatcher; handlers may raise freely.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("research-os.server")

from research_os.project_ops import (
    _update_workflow_mermaid,
    _update_manifest,
    compute_file_hash,
    load_state,
    now_iso,
    scaffold_minimal_workspace,
    log_decision,
)


class _MissingDependency:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *args, **kwargs):
        raise RuntimeError(
            f"Optional dependency missing for {self.name}. "
            "Install with: pip install 'research-os[all]'"
        )


# Tracks (module, attribute) pairs that failed to import so the AI can ask
# for a real status read instead of finding out tool-by-tool.
_MISSING_DEPS: list[tuple[str, str]] = []


def _lazy_import(module_name: str, names: list[str]):
    try:
        mod = __import__(module_name, fromlist=names)
        return [getattr(mod, name) for name in names]
    except ImportError:
        for n in names:
            _MISSING_DEPS.append((module_name, n))
        return [_MissingDependency(name) for name in names]


def _optional_dep_inventory() -> dict:
    """Return a structured report of what's installed vs missing."""
    return {
        "missing": [
            {"module": m, "symbol": n} for (m, n) in _MISSING_DEPS
        ],
        "missing_count": len(_MISSING_DEPS),
        "advice": (
            "Install with: pip install 'research-os[all]' "
            "(omits R / Julia / Docker bindings — install those separately)."
            if _MISSING_DEPS
            else "All optional dependencies present."
        ),
    }


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

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

    @dataclass
    class TextContent:
        type: str
        text: str


_START_TIME = time.time()


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, max_calls: int = 200, window_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str = "default") -> bool:
        now = time.time()
        self.calls[client_id] = [
            t for t in self.calls[client_id] if now - t < self.window_seconds
        ]
        if len(self.calls[client_id]) >= self.max_calls:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return False
        self.calls[client_id].append(now)
        return True


_rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


def _success(data: Any = None) -> dict:
    return {"status": "success", "data": data or {}}


def _error(message: str) -> dict:
    return {"status": "error", "error": message}


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool definitions — keep the surface tight: one tool per concept.
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    # ── Routing (call THESE first) ───────────────────────────────────
    "sys_boot": {
        "short": "One-call session bootstrap — state + config + history + dep inventory + next protocol. Replaces 4-5 separate calls.",
        "description": "Single-call session bootstrap. Returns state + researcher config + protocol history tail + optional-dep inventory + recommended next protocol + pause classification + any active plan from a previous turn. Call this ONCE per session instead of sys_state_get + sys_config_get + sys_protocol_history + sys_protocol_next + sys_dep_inventory separately. Cuts a typical boot from ~5K tokens to ~800.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_route": {
        "short": "Prompt → protocol + decomposition. Call after every researcher message.",
        "description": "Hybrid router. Tries SEMANTIC search first (embeddings cosine over protocol descriptions + triggers) — best for fuzzy intent + as the protocol catalog grows. Falls back to the hierarchical L1→L2→L3 trigger picker when semantic confidence is low / unavailable. Returns primary_protocol, shortcut_tool, decomposition, complexity, ask_user, alternatives, method (=semantic|trigger), confidence (=high|medium|low|none). High-complexity prompts get an active_plan persisted to .os_state/.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "persist_plan": {"type": "boolean"},
            },
            "required": ["prompt"],
        },
    },
    "tool_semantic_route": {
        "short": "Direct semantic search over protocol embeddings. Returns top-k candidates with scores.",
        "description": "Embed the prompt with BAAI/bge-small-en-v1.5 (local ONNX, no network) and return the top-k protocols by cosine similarity, with the length-weighted trigger-phrase boost applied. Use this when you want to SEE the ranked candidates yourself — tool_route picks a primary; tool_semantic_route surfaces the alternatives so you can route deliberately. Requires the `semantic` extra (`pip install 'research-os[semantic]'`); falls back to status='unavailable' otherwise.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            },
            "required": ["prompt"],
        },
    },
    "sys_semantic_tool_search": {
        "short": "Find tools by what they do — semantic search over tool descriptions.",
        "description": "Given a natural-language description of what you want to do (e.g. 'compute kappa for inter-rater agreement on transcript codes'), return the top-k matching tool names ranked by semantic similarity to each tool's short + description + category. Useful when sys_active_tools doesn't surface the right tool because the active protocol's decomposition is narrow. Requires the `semantic` extra; falls back to status='unavailable' otherwise.",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
        },
    },
    "tool_plan_advance": {
        "short": "Mark current step done; get next step. Returns status='blocked' when a deliverable gate fails.",
        "description": "Walk the active_plan. Returns next_step + remaining. Returns status='blocked' when the next step is a deliverable tool (tool_synthesize / tool_dashboard / tool_poster_create / tool_latex_compile) and the quality gate finds blockers. Pass override_gate=true ONLY on explicit researcher approval of a partial deliverable; supply override_rationale so workspace/logs/override_log.md records WHY the bypass happened.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "override_gate": {
                    "type": "boolean",
                    "description": "Bypass the deliverable quality gate. Set only when the researcher explicitly authorised the bypass.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "One-line researcher-supplied reason for the bypass. Logged.",
                },
            },
        },
    },
    "tool_plan_turn": {
        "short": "Slice the active plan into this_turn (do now) + next_turn (queued) per model_profile.",
        "description": "Reads the active plan + the researcher's model_profile (small/medium/large) and returns the batch of steps the AI should execute THIS turn versus what to queue for the next turn. Also returns `chat_split_recommended` (true when the remaining plan is too long for one chat — the AI should hand off + open a fresh chat). Small models get 1 step/turn; medium 3; large 6. Heavyweight tools (tool_synthesize, tool_audit_reproducibility) count for more.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_plan_clear": {
        "short": "Discard the active plan (researcher pivoted away).",
        "description": "Use when the researcher abandons the previously-routed task mid-flow. Subsequent tool_route calls start fresh.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_tool_describe": {
        "short": "Return the full description + schema for one tool.",
        "description": "list_tools ships only short descriptions to keep context lean. When you genuinely need the full detail (parameter semantics, longer rationale, examples) for one tool, call this. Cheaper than re-listing every tool.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
            "required": ["tool_name"],
        },
    },
    "sys_active_tools": {
        "short": "Active tool shortlist for a protocol (essentials + decomposition tools).",
        "description": "Given a protocol name, return the tight set of tools the AI should prefer while executing it: ~10-15 tools = essentials + everything the protocol's decomposition actually calls. Use after sys_protocol_get to scope your working set instead of triaging all 212 tools per turn.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {"protocol_name": {"type": "string"}},
            "required": ["protocol_name"],
        },
    },
    "sys_active_project": {
        "short": "Return the project root the server resolved for THIS request (global-server mode).",
        "description": "Returns the currently-resolved project root + how it was resolved (env var / cwd walk / fallback). The Research OS MCP server is GLOBAL — one process serves multiple projects. Each request resolves a project per the rules: (1) RESEARCH_OS_WORKSPACE env var (the IDE MCP config typically sets this to ${workspaceFolder}); (2) the current working directory walked up for `.os_state/`; (3) the current working directory itself. Call this when you need to confirm which project this session is operating on, OR when a tool surprised you and you want to verify the root.",
        "category": "routing",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_help": {
        "short": "AI orientation — how to use Research OS efficiently (protocols + tools + routing).",
        "description": "Returns a compact orientation block for the AI: the session-start sequence (every turn is triggered by a researcher message — on the first turn, sys_boot is your 1st MCP call and tool_route(prompt=their message) is your 2nd, followed by sys_protocol_get / sys_active_tools as needed), the protocol categories with one-line summaries, and the tool namespaces (sys_* / tool_* / mem_*). Use this when starting cold (no prior session memory), when a new AI takes over from a handoff, or when a tool / protocol mention is ambiguous and the orientation block clarifies it.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Optional — a topic to focus the orientation on (e.g. 'synthesis', 'methodology', 'audit'). Returns category-specific guidance.",
                },
            },
        },
    },

    # ── Protocols / guidance ──────────────────────────────────────────
    "sys_protocol_get": {
        "short": "Load a protocol — format='summary' (cheap), 'step' (one step), 'lean' (small-model), 'dryrun' (preview), or 'full'.",
        "description": "Load a protocol YAML by name (e.g. 'guidance/project_startup'). Five formats — summary returns id + step headings + quality_bar + expected outputs in ~300 tokens; step returns one specific step body (requires step_id); full returns the entire YAML (~1.5-3K tokens); lean serves the protocol's explicit lean_variant block if present, else auto-distils (cap 3 steps, drop optional sub-steps, trim step descriptions to 200 chars) for small/fast models; dryrun returns the full tool-call sequence with predicted args without executing — for supervised review. Prefer summary first then step on demand; use lean when researcher_config.model_profile=='small'; use dryrun in supervised mode to preview before commit. Routing tip: call tool_route(prompt) BEFORE this to pick the right protocol_name.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": ["summary", "step", "full", "lean", "dryrun"],
                    "description": "summary | step | full | lean | dryrun (default: full for back-compat, but summary or lean is recommended).",
                },
                "step_id": {
                    "type": "string",
                    "description": "Required when format='step'.",
                },
            },
            "required": ["protocol_name"],
            "additionalProperties": False,
        },
    },
    "sys_protocol_list": {
        "short": "Full catalog dump across core + all packs (~100+ items). Optional `category` filter (pack name or first path segment). Prefer tool_route / tool_semantic_route — semantic routing scales as the catalog grows.",
        "description": "Returns every protocol name + one-line summary + pack_or_core source, walking both the in-tree core protocols and every registered pack (humanities, qualitative, theory_math, wet_lab, engineering, plus any externally-installed packs). Pass `category` (e.g. 'theory_math', 'audit', 'guidance') to narrow to one pack or one core category. Designed for debugging + maintainer browsing; not the primary entrypoint at runtime. For routing a user prompt, call tool_route (hybrid semantic + trigger). For inspecting ranked alternatives, call tool_semantic_route. For finding tools by what they do, call sys_semantic_tool_search. As the catalog grows beyond ~150 protocols, dumping the full list every turn wastes context — semantic retrieval is the AI-friendly path.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to a single category. For core protocols this matches the first path segment (e.g. 'guidance', 'audit'). For pack protocols it matches the pack name (e.g. 'theory_math') or the pack-internal category.",
                },
            },
        },
    },
    "tool_protocols_list": {
        "short": "Flat protocol catalog with category + pack + intent_class. Filterable.",
        "description": "Returns a flat list of every protocol with structured metadata: name, category, pack_or_'core', intent_class, tier (null until Phase 8), version, description_short. Filter with `category` (e.g. 'audit', 'guidance'), `pack` ('core' or a pack name), and `include_pack_protocols` (default true). Cheaper for the AI to scan than sys_protocol_list when it only needs the protocols in one category or one pack. Use this when a researcher asks 'what audit protocols do you have?' — narrower than dumping the full catalog.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to a single category (first path segment, e.g. 'guidance', 'audit', 'synthesis').",
                },
                "pack": {
                    "type": "string",
                    "description": "Filter to a single source: 'core' or a pack name ('humanities', 'qualitative', etc.).",
                },
                "include_pack_protocols": {
                    "type": "boolean",
                    "description": "When false, skip every pack-contributed protocol. Default true.",
                },
            },
        },
    },
    "tool_tools_list": {
        "short": "Flat tool catalog with scope + summary + required-fields. Filterable.",
        "description": "Returns a flat list of every registered MCP tool: name, scope ('core' or pack name), summary_first_line, input_schema_required_fields, deprecated, alias_of. Filter with `scope` ('all'|'core'|<pack-name>'), `include_deprecated` (default false), and `match_substring` (case-insensitive needle against name + summary). Use this to discover the tool surface at a glance without pulling every full description; call sys_tool_describe for one tool's full body when you actually need it.",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "'all' | 'core' | a pack name. Default 'all'.",
                },
                "include_deprecated": {
                    "type": "boolean",
                    "description": "When true, include alias entries flagged as deprecated. Default false.",
                },
                "match_substring": {
                    "type": "string",
                    "description": "Restrict to tools whose name or summary contains this substring (case-insensitive).",
                },
            },
        },
    },
    "sys_protocol_next": {
        "description": "Recommend the next protocol to run based on current workspace state and the pipeline.",
        "category": "protocol",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_protocol_validate": {
        "description": "Check whether the expected outputs of a protocol are present in the workspace.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {"protocol_name": {"type": "string"}},
            "required": ["protocol_name"],
        },
    },
    "sys_protocol_log": {
        "description": "Record a protocol execution (started|completed|failed|skipped) to the pipeline log.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "status": {"type": "string"},
                "details": {"type": "string"},
            },
            "required": ["protocol_name", "status"],
        },
    },
    "sys_protocol_history": {
        "description": "Return the most recent protocol execution log entries.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "number"}},
        },
    },

    # ── State & workspace ─────────────────────────────────────────────
    "sys_state_get": {
        "description": "Return the full workspace state: project name, pipeline stage, current path, all experiment paths, and active hypotheses.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "full | minimal | markdown — controls verbosity (default: full).",
                }
            },
        },
    },
    "sys_workspace_scaffold": {
        "description": "Create the standard Research OS directory layout. Used by `research-os init`; only call from inside the MCP if the researcher explicitly asks for a re-scaffold.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "ide": {
                    "type": "string",
                    "description": "all | cursor | claude | antigravity | opencode | vscode",
                    "default": "all",
                },
            },
        },
    },
    "sys_workspace_tree": {
        "description": "Return a structured tree of workspace/ — experiment paths, scripts, outputs. Call at session start for orientation.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "depth": {"type": "number"},
                "include_files": {"type": "boolean"},
            },
        },
    },

    # ── File I/O ──────────────────────────────────────────────────────
    "sys_file_read": {
        "description": "Read a workspace file. Up to 50 MB; use tool_data_sample for larger datasets.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys_file_write": {
        "description": "Write a file. Refuses to write into inputs/raw_data/ or inputs/literature/ (immutable). Use force=true to overwrite a file in synthesis/.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "content": {"type": "string"},
                "force": {"type": "boolean"},
            },
            "required": ["filepath", "content"],
        },
    },
    "sys_file_list": {
        "description": "List files in a workspace directory (recursive).",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
    "sys_file_delete": {
        "description": "Delete a workspace file or an empty directory.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys_file_validate_md": {
        "description": "Validate a markdown file against the headings/sections expected by a writing protocol.",
        "category": "file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "protocol_name": {"type": "string"},
            },
            "required": ["filepath", "protocol_name"],
        },
    },

    # ── Experiment paths ──────────────────────────────────────────────
    "sys_path_create": {
        "description": (
            "Create the next numbered experiment folder (workspace/NN_<slug>/). "
            "Populates README, conclusions, scripts/, data/, outputs/, environment/ "
            "subdirs. Updates state. Pass `branch_of=<existing path_id>` to fork an "
            "alternative analytical path — the new folder is named "
            "NN_<slug>_path_<k>, the path lineage carries through every subsequent "
            "step created with branch_of pointing back into the same lineage, and "
            "the new step's data/input symlinks to the PARENT step's output rather "
            "than to the previous numbered step (so branches are genuine forks)."
        ),
        "category": "path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Short descriptive slug DERIVED FROM THE STEP'S GOAL "
                        "(lowercase, words joined by underscores, ≤40 chars). "
                        "The AI picks this based on what the step actually does "
                        "for THIS project — there are no fixed canonical names. "
                        "Examples by domain (not requirements): "
                        "EDA → 'baseline_eda' / 'distribution_scan'; "
                        "cleaning → 'imputation' / 'outlier_handling'; "
                        "modelling → 'cox_ph' / 'random_forest' / 'cnn_baseline'; "
                        "audit → 'sensitivity' / 'calibration_check'."
                    ),
                },
                "hypothesis": {"type": "string"},
                "branch_of": {
                    "type": "string",
                    "description": (
                        "Optional parent step id (e.g. '04_logistic_regression'). "
                        "When set, the new folder gets a `_path_<k>` suffix and "
                        "the data/input is wired to the parent's output. Use when "
                        "the researcher wants to test an alternative pipeline "
                        "alongside the current one rather than replacing it."
                    ),
                },
                "from_step": {
                    "type": "string",
                    "description": (
                        "Optional upstream step id to source data/input from "
                        "(e.g. '03_normalization'). When omitted, the new step's "
                        "data/input symlinks to the previous numbered step's "
                        "data/output (or to inputs/raw_data/ for step 01). Use "
                        "when the linear-predecessor inheritance is wrong — "
                        "e.g. step 07 should read step 05's output, not step 06's."
                    ),
                },
                "allow_unfinalized_predecessor": {
                    "type": "boolean",
                    "description": (
                        "By default, create_numbered_experiment REFUSES "
                        "to scaffold step N+1 while step N's README + conclusions.md "
                        "are still placeholder text — preventing the 'forgot to "
                        "finalize step 01 before starting step 02' pattern. Set this "
                        "to true ONLY when the researcher explicitly authorises the "
                        "bypass (e.g. step N is pure data plumbing with nothing to "
                        "conclude). Pair with `override_rationale` so the bypass is "
                        "logged to workspace/logs/override_log.md."
                    ),
                },
                "override_rationale": {
                    "type": "string",
                    "description": (
                        "Required when allow_unfinalized_predecessor=true. The "
                        "researcher's reason for bypassing the finalize gate. "
                        "Surfaced verbatim in the override log + the pre-submission "
                        "audit so the bypass is never hidden."
                    ),
                },
            },
            "required": ["name"],
        },
    },
    "sys_path_abandon": {
        "description": (
            "Mark an experiment as a dead end. Renames the folder to "
            "NN_<slug>__DEAD_END (lineage tags such as `_path_2` are preserved, "
            "so a dead-ended branch becomes NN_<slug>_path_2__DEAD_END) and "
            "writes the rationale to analysis.md."
        ),
        "category": "path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_name": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["path_name", "rationale"],
        },
    },
    "sys_path_list": {
        "description": "List all numbered experiment folders with their status (active|completed|dead_end).",
        "category": "path",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_export_share_archive": {
        "description": (
            "Build a share-safe zip of this project (default: "
            "<project>_share_<YYYY-MM-DD>.zip in the project root). "
            "Excludes AI-internal files (AGENTS.md, CLAUDE.md, .os_state/, "
            ".claude/, MCP configs, GETTING_STARTED.md) and — unless "
            "include_raw_data=true — inputs/raw_data/. Includes inputs/ "
            "(minus raw_data), workspace/, synthesis/, docs/, environment/, "
            "and a top-level README.md if present. Equivalent to running "
            "`python scripts/export_share_archive.py` from the project root."
        ),
        "category": "interaction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "out": {"type": "string",
                        "description": "Optional explicit output zip path."},
                "include_raw_data": {
                    "type": "boolean",
                    "description": "Set true to bundle inputs/raw_data/ (default false to keep archives small and avoid PII)."
                },
            },
        },
    },
    "tool_synthesis_curate_figures": {
        "description": (
            "Collect each step's focal figure into synthesis/figures/ with "
            "stable, ordered names (fig01_<slug>.png, fig02_<slug>.png, …) "
            "so the dashboard + paper can embed them deterministically. "
            "Copies the figure's existing .caption.md sidecar if present, "
            "or seeds a placeholder explaining how to write one. Returns the "
            "list of curated figures plus any step that produced no figures "
            "(to flag in the audit) and any figure missing a caption. Run "
            "BEFORE tool_dashboard / tool_synthesize so the deliverables "
            "use a single canonical figure set rather than scanning the "
            "workspace anew each time."
        ),
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_path_finalize": {
        "description": (
            "Rewrite a step's stub README + every subfolder README from what "
            "actually got produced. Call this BEFORE marking a step complete: "
            "(a) `environment/README.md` is normalised to either 'used the "
            "project-global env' or a list of bespoke requirements, (b) "
            "`literature/README.md` either points at the global corpus + the "
            "step's decision log or lists the step-specific sources + the "
            "decisions they informed, (c) `data/output/README.md` lists every "
            "persisted artefact and which downstream step consumes it, (d) "
            "`outputs/README.md` enumerates produced figures / tables / "
            "reports, and (e) any stub sections in the step's main `README.md` "
            "are populated from `conclusions.md` + `analysis.md` decisions. "
            "Idempotent — running it a second time is a no-op if nothing "
            "changed. Defaults to the current path."
        ),
        "category": "path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_name": {
                    "type": "string",
                    "description": "Step folder name (e.g. '03_replicate_attitude_demographics'). Defaults to current_path.",
                },
            },
        },
    },

    # ── Checkpoints ───────────────────────────────────────────────────
    "sys_checkpoint_create": {
        "description": "Snapshot the current workspace (hardlinked, fast). Returns checkpoint_id.",
        "category": "checkpoint",
        "inputSchema": {
            "type": "object",
            "properties": {"description": {"type": "string"}},
        },
    },
    "sys_checkpoint_rollback": {
        "description": "Restore the workspace to a checkpoint. The current state is backed up first.",
        "category": "checkpoint",
        "inputSchema": {
            "type": "object",
            "properties": {"checkpoint_id": {"type": "string"}},
            "required": ["checkpoint_id"],
        },
    },
    "sys_checkpoint_list": {
        "description": "List all checkpoints with descriptions and timestamps.",
        "category": "checkpoint",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Researcher config ─────────────────────────────────────────────
    "sys_config_get": {
        "description": "Read inputs/researcher_config.yaml — the source of truth for autonomy level, expertise, model profile, research goal, and API keys (masked).",
        "category": "config",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys_config_set": {
        "description": "Set a single config value (dot notation, e.g. researcher.expertise_level=advanced).",
        "category": "config",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
    "sys_config_validate": {
        "description": "Validate the config schema and report which API keys are present.",
        "category": "config",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Notification / handoff ────────────────────────────────────────
    "sys_notify": {
        "description": "Notify the researcher (logged to workspace/logs/notifications.log).",
        "category": "interaction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "level": {"type": "string", "description": "info|warn|action_required"},
            },
            "required": ["message", "level"],
        },
    },
    "sys_session_handoff": {
        "description": "Generate a structured markdown handoff describing the project state, last action, and next step. Use at session end.",
        "category": "interaction",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Environment ───────────────────────────────────────────────────
    "sys_env_snapshot": {
        "description": "Snapshot the current Python (and optionally R/Julia) environment. Target by step_id='NN_slug' for a per-step snapshot, scope='project' for the eager-scaffolded project-global environment/ folder, or omit both for the legacy default (most-recent numbered step, or project-global when none exist).",
        "category": "environment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {
                    "type": "string",
                    "description": "Optional. NN_slug of the numbered step to snapshot into. Mutually exclusive with scope.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["project"],
                    "description": "Optional. Set to 'project' to snapshot into the project-global environment/ folder.",
                },
            },
        },
    },
    "sys_env_docker_generate": {
        "description": "Generate a Dockerfile from the environment snapshot for full reproducibility.",
        "category": "environment",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Memory / append-only logs ─────────────────────────────────────
    "mem_analysis_log": {
        "description": "Append an entry to workspace/analysis.md (chronological narrative log).",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {"entry": {"type": "string"}},
            "required": ["entry"],
        },
    },
    "mem_methods_append": {
        "description": "Append a structured method entry (step, dataset, implementation, parameters, justification, assumptions) to workspace/methods.md.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "step_number": {"type": "string"},
                "step_name": {"type": "string"},
                "dataset_name": {"type": "string"},
                "dataset_hash": {"type": "string"},
                "implementation": {"type": "string"},
                "parameters": {"type": "string"},
                "justification": {"type": "string"},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["method"],
        },
    },
    "mem_citations_generate": {
        "description": "Refresh workspace/citations.md from inputs/literature_index.yaml.",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "mem_intake_regenerate": {
        "description": "Regenerate inputs/intake.md (file inventory with SHA-256 hashes).",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "mem_decision_log": {
        "description": "Append a structured decision (context, selected, rationale) to workspace/analysis.md.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "selected": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["context", "selected", "rationale"],
        },
    },

    # ── Search & literature ───────────────────────────────────────────
    "tool_search_semantic_scholar": {
        "description": "Search Semantic Scholar for relevant academic papers.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_search_pubmed": {
        "description": "Search PubMed (biomedical literature).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_search_crossref": {
        "description": "Search Crossref for DOI-linked academic literature.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_search_arxiv": {
        "description": "Search arXiv for preprints (physics, math, CS, statistics, quantitative biology, etc.).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_search_web": {
        "description": "Search the web (Firecrawl primary, SerpAPI fallback). Use to ground methodology, find tools, or check current best practices.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_web_scrape": {
        "description": "Scrape a webpage and return markdown content.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "tool_literature_download": {
        "description": "Download a paper PDF. Default scope is inputs/literature/ (project-wide). Pass step_id='NN_<slug>' to save it under workspace/<step>/literature/ instead. Writes a .meta.yaml sidecar with title/authors/year/doi if provided so synthesis can cite it correctly.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filename": {"type": "string"},
                "step_id": {
                    "type": "string",
                    "description": "Optional: NN_<slug> to scope the download to that experiment step's literature folder.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Citation metadata to embed in the sidecar (title, authors, year, doi, venue, source).",
                },
                "skip_unpaywall": {"type": "boolean"},
            },
            "required": ["url", "filename"],
        },
    },
    "tool_literature_search_and_save": {
        "description": "Search a provider, download the top-N PDFs into the chosen scope (project or step), preserve citation metadata. One-shot 'find + save' for literature you want backing a specific analysis step.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {
                    "type": "string",
                    "description": "semantic_scholar | crossref | pubmed | arxiv (default semantic_scholar)",
                },
                "step_id": {"type": "string"},
                "limit": {"type": "number", "description": "Hits to consider (default 5)."},
                "download_top": {"type": "number", "description": "Top-N to actually download (default 3)."},
            },
            "required": ["query"],
        },
    },
    "tool_step_literature_list": {
        "description": "List PDFs in a specific experiment step's literature/ folder, OR across every step when no step_id is given.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
            },
        },
    },

    # ── Execution ─────────────────────────────────────────────────────
    "tool_python_exec": {
        "description": "Execute a Python script located in the workspace. Runs with host permissions — do NOT execute untrusted code.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_r_exec": {
        "description": "Execute an R script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_julia_exec": {
        "description": "Execute a Julia script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_bash_exec": {
        "description": "Execute a Bash script located in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["script_path"],
        },
    },
    "tool_package_install": {
        "description": "Install Python packages and append them to environment/requirements.txt.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["packages"],
        },
    },

    # ── Data ──────────────────────────────────────────────────────────
    "tool_data_sample": {
        "description": "Sample N rows from a dataset (CSV, Parquet, Feather, JSON, Excel).",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "n_rows": {"type": "number"},
                "strategy": {
                    "type": "string",
                    "description": "head | random | tail (default: head)",
                },
            },
            "required": ["filepath", "n_rows"],
        },
    },
    "tool_data_profile": {
        "description": "Profile a tabular dataset: schema, dtypes, missingness, descriptive stats, plus suggested next steps.",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool_data_convert": {
        "description": "Convert a dataset between CSV / Parquet / Feather / RDS.",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "output_format": {"type": "string"},
            },
            "required": ["filepath", "output_format"],
        },
    },

    # ── Audit ─────────────────────────────────────────────────────────
    # tool_audit is the unified per-dimension auditor. Pass scope (step |
    # project | synthesis) + dimension. Legacy per-dimension audit tool
    # names alias here with their scope+dimension injected automatically.
    # tool_audit_quality_full stays separate as the canonical aggregator.
    "tool_audit": {
        "short": "Unified per-dimension audit. scope=step|project|synthesis; dimension=completeness|literature|code_quality|prose|claims|figure|citations|assumptions|power|reproducibility|evalue|cliches|coherence|version_coherence|cross_deliverable|reviewer_responses|dashboard_content|figure_full|figure_interactivity|figure_coverage|all.",
        "description": "Unified audit dispatcher. Pick (scope, dimension): scope='step' for per-step gates (completeness, literature, code_quality, evalue, figure, figure_full, figure_interactivity, power, assumptions, reproducibility); scope='project' for project-wide gates (citations, claims, cliches, coherence, cross_deliverable, prose, version_coherence); scope='synthesis' for synthesis-side gates (all, dashboard_content, figure_coverage, reviewer_responses). Per-dimension kwargs are accepted on the same call (e.g. step_id, paper_path, filepath, target_path, override_no_pdfs, override_rationale, ...). Output schema matches the legacy per-dimension tool for the chosen (scope, dimension). Use tool_audit_quality_full to run all primary gates in one shot. Use tool_audit_findings to read the cross-audit findings ledger after one or more audits have written to it.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["step", "project", "synthesis"],
                    "description": "Audit scope. step = per-step gate. project = project-wide gate (paper / repo / citations). synthesis = synthesis-side gate (paper / dashboard / reviewer responses).",
                },
                "dimension": {
                    "type": "string",
                    "description": "What to audit. See the description for the full (scope, dimension) matrix.",
                },
                # Common per-dimension kwargs (all optional; consumed by the
                # downstream legacy handler). Listed here so MCP clients can
                # auto-complete; extra unknown kwargs are forwarded verbatim.
                "step_id": {"type": "string", "description": "scope='step' dimensions — optional step folder, default = all active steps."},
                "paper_path": {"type": "string", "description": "scope='synthesis' dimension='all' — manuscript to audit (default 'synthesis/paper.md')."},
                "filepath": {"type": "string", "description": "scope='step' dimensions ∈ {figure, power, assumptions} — file to audit."},
                "figure_path": {"type": "string", "description": "scope='step' dimension='figure_full' — figure to audit."},
                "target_path": {"type": "string", "description": "scope='project' dimension='claims' — manuscript to audit (default 'synthesis/paper.md')."},
                "tolerance": {"type": "number", "description": "scope='project' dimension='claims' — numeric tolerance (default 0.01 = 1%)."},
                "dashboard_path": {"type": "string", "description": "scope='synthesis' dimension='dashboard_content' — dashboard file path."},
                "effect_size": {"type": "number"},
                "alpha": {"type": "number"},
                "n": {"type": "number"},
                "risk_ratio": {"type": "number"},
                "ci_lower": {"type": "number"},
                "ci_upper": {"type": "number"},
                "run_ruff": {"type": "boolean"},
                "run_mypy": {"type": "boolean"},
                "targets": {"type": "array", "items": {"type": "string"}},
                "is_observational": {"type": "boolean"},
                "strictness": {"type": "string"},
                "autogen": {"type": "boolean"},
                "override_no_pdfs": {"type": "boolean"},
                "override_dashboard_content_gate": {"type": "boolean"},
                "override_cross_deliverable": {"type": "boolean"},
                "override_rationale": {"type": "string"},
            },
            "required": ["scope", "dimension"],
        },
    },
    "tool_audit_findings": {
        "short": "Read the cross-audit findings ledger. operation='query' filters; operation='diff' compares two snapshots.",
        "description": "Unified read interface for workspace/logs/.audit_findings.jsonl (the append-only ledger every Phase-4 audit writes to via write_audit_outputs). operation='query' (default) reduces to the latest snapshot per stable finding id and filters by severity ('block' | 'warn' | 'info'), dimension, step (matches evidence_paths containing '/<step>/'), and since (ISO-8601 cutoff). operation='diff' snapshots the ledger as of timestamp_a (EARLIER) and timestamp_b (LATER) and reports {added: [...], resolved: [...], changed: [...]} keyed by stable finding id. Read-only — never mutates the ledger. operation defaults to 'diff' when both timestamps are supplied without an explicit operation, otherwise 'query'.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["query", "diff"],
                    "description": "Default 'query'. Use 'diff' to compare two ledger snapshots.",
                },
                # query kwargs
                "severity": {
                    "type": "string",
                    "enum": ["block", "warn", "info"],
                    "description": "operation='query' — optional severity filter.",
                },
                "dimension": {
                    "type": "string",
                    "description": "operation='query' — optional dimension filter (e.g. 'completeness', 'prose').",
                },
                "step": {
                    "type": "string",
                    "description": "operation='query' — optional step folder filter (e.g. '02_eda').",
                },
                "since": {
                    "type": "string",
                    "description": "operation='query' — optional ISO-8601 cutoff; returns findings on/after this timestamp.",
                },
                # diff kwargs
                "timestamp_a": {
                    "type": "string",
                    "description": "operation='diff' — ISO-8601 timestamp for the EARLIER snapshot.",
                },
                "timestamp_b": {
                    "type": "string",
                    "description": "operation='diff' — ISO-8601 timestamp for the LATER snapshot; must be on/after timestamp_a.",
                },
            },
        },
    },
    "tool_step": {
        "short": "Unified step lifecycle tool. operation=iterate|iterations_list|revision_options|env_lock.",
        "description": "Unified step-lifecycle dispatcher. operation='iterate' bumps an analysis step into a new named iteration — copies selected scripts/figures/tables + their sidecars (.caption.md / .summary.md / .prov.json) + conclusions.md into workspace/<step>/.versions/v<n>/, appends a row to workspace/<step>/iterations.yaml with the REQUIRED rationale, and returns the recommended _v<n+1> rename for each script. operation='iterations_list' returns the iterations.yaml ledger for a step (rationale, snapshot dir, script/figure/table names per version). operation='revision_options' (call AFTER tool_path_finalize) surfaces the anti-one-shot pause-and-revise heuristic: would_benefit_from_revision, suggested_revisions, alternative_paths, handoff_recommended (true at 5+ finalized steps), risk_signals — AI MUST present VERBATIM and WAIT for researcher choice. operation='env_lock' pins the step's environment/ for years-later reproduction (requirements + python_version + optional conda.yaml / Dockerfile / Apptainer step.def / entrypoint.sh). Prefer over sys_env_snapshot for any step you intend to publish. Use tool_step_complete for the end-of-step bundle (finalize + completeness audit + literature gate + revision options).",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["iterate", "iterations_list", "revision_options", "env_lock"],
                    "description": "Which step sub-operation to invoke.",
                },
                "step_id": {
                    "type": "string",
                    "description": "Numbered step folder, e.g. '03_fit_baseline'. Required for iterate / iterations_list / revision_options; optional for env_lock (defaults to most-recent active step with a warning).",
                },
                # operation='iterate' kwargs
                "rationale": {
                    "type": "string",
                    "description": "operation='iterate' — REQUIRED. Why this iteration is happening (design change, parameter sweep, reviewer ask, etc.). Recorded in iterations.yaml.",
                },
                "scripts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='iterate' — optional names under scripts/ to include. Default: every script.",
                },
                "figures": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='iterate' — optional names under outputs/figures/ to include. Default: every figure.",
                },
                "tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='iterate' — optional names under outputs/tables/ to include. Default: every table.",
                },
                "bump_conclusion": {
                    "type": "boolean",
                    "description": "operation='iterate' — copy conclusions.md into the snapshot (default true).",
                },
                # operation='env_lock' kwargs
                "write_conda_yaml": {
                    "type": "boolean",
                    "description": "operation='env_lock' — also emit environment/conda.yaml.",
                },
                "write_dockerfile": {
                    "type": "boolean",
                    "description": "operation='env_lock' — also emit environment/Dockerfile.",
                },
                "write_apptainer": {
                    "type": "boolean",
                    "description": "operation='env_lock' — emit step.def for HPC Apptainer/Singularity.",
                },
                "write_entrypoint": {
                    "type": "boolean",
                    "description": "operation='env_lock' — emit environment/entrypoint.sh (default true).",
                },
            },
            "required": ["operation"],
        },
    },
    "tool_figure_caption_synthesise": {
        "short": "Write a plain-English <name>.summary.md next to a figure.",
        "description": "Generate a 2-3 sentence plain-language description next to a figure for non-expert / accessibility audiences (W3C two-part guidance). Reads the figure's existing <name>.caption.md sidecar + the step's conclusions.md Findings section to anchor the summary in the actual result. Idempotent — pass overwrite=true to replace an existing summary.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "figure_path": {"type": "string", "description": "Path relative to project root (e.g. workspace/03_baseline/outputs/figures/03_calibration.png)."},
                "technical_caption": {"type": "string"},
                "findings_context": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["figure_path"],
        },
    },
    "tool_figure_palette": {
        "short": "Recommended palette for a chart's encoding.",
        "description": "Returns colour-blind-safe defaults: Okabe-Ito (qualitative), viridis (sequential), PuOr (diverging), or the dashboard primary/gold/green/red accent set.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "qualitative (default) | sequential | diverging | accent"},
                "n": {"type": "number", "description": "Number of colours (default 8)."},
            },
        },
    },
    "tool_step_pipeline": {
        "short": "Unified step sub-task pipeline tool. operation=define|run|status|diagram.",
        "description": "Unified step-pipeline dispatcher for the per-step sub-task DAG (ingest→clean→validate→fit→diagnose→visualize→report). operation='define' (default when name/description/nodes/template imply authoring) seeds workspace/<step>/pipeline.yaml from a 7-node template; required for any step with >2 scripts (audit gate). operation='run' walks the pipeline.yaml DAG in topological order with content-hash caching — nodes whose script+inputs+params hash matches a previous successful run are SKIPPED; only the affected downstream chain re-runs after an edit; each output gets a .prov.json sidecar (PROV-O); pass `only` to restrict to nodes (upstream deps auto-included), `force=true` to bypass cache, `dry_run=true` to plan only. operation='status' reads pipeline.yaml + the most recent run log and per-node reports fresh / stale / never_run. operation='diagram' writes workspace/<step>/pipeline.mermaid which the dashboard's per-step appendix embeds. See guidance/analysis_plan for the workflow.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["define", "run", "status", "diagram"],
                    "description": "Which pipeline sub-operation to invoke.",
                },
                "step_id": {
                    "type": "string",
                    "description": "Numbered step folder (e.g. 03_logistic_baseline). Required for every operation.",
                },
                # operation='define' kwargs
                "name": {
                    "type": "string",
                    "description": "operation='define' — display name for the pipeline.",
                },
                "description": {
                    "type": "string",
                    "description": "operation='define' — free-text description of the pipeline.",
                },
                "nodes": {
                    "type": "array",
                    "description": "operation='define' — optional custom node list (see analysis_plan protocol for shape).",
                },
                "template": {
                    "type": "string",
                    "description": "operation='define' — default (7-node ingest→...→report).",
                },
                # operation='run' kwargs
                "only": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='run' — node IDs to run (transitive deps auto-included).",
                },
                "force": {
                    "type": "boolean",
                    "description": "operation='run' — skip the cache and re-run every node.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "operation='run' — plan only; do not execute.",
                },
            },
            "required": ["operation", "step_id"],
        },
    },
    # ── Grounded reasoning (ReAct + PROV-O + CoVe + Reflexion) ──────────
    "tool_thought_log": {
        "short": "Append one ReAct trace entry — thought / plan / action / observation / reflection / decision.",
        "description": "Persistent thinking log at workspace/.thoughts/thoughts.jsonl. Use to surface reasoning BEFORE acting (ReAct: thought → action → observation). Optional decision_id links the trace to a grounding record.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "thought | plan | action | observation | reflection | decision"},
                "content": {"type": "string"},
                "step_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["kind", "content"],
        },
    },
    "tool_thought_trace": {
        "short": "Read the recent thought trace (filterable by step / decision).",
        "description": "Returns the tail of workspace/.thoughts/thoughts.jsonl. Use to remind yourself what you concluded earlier in the session.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "tail": {"type": "number"},
            },
        },
    },
    "tool_grounding_register": {
        "short": "Bind a decision/claim to PROV-O sources (papers, context files, datasets, web, prior decisions).",
        "description": "Every methodological decision should cite the evidence that informed it. Sources are typed: paper | preprint | dataset | context_file | web | workspace_artefact | tool_research | prior_decision. Cited_text spans recommended where available. tool_grounding_verify gates synthesis on coverage.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
                "claim": {"type": "string"},
                "sources": {"type": "array"},
                "step_id": {"type": "string"},
                "confidence": {"type": "string", "description": "low | medium | high"},
                "notes": {"type": "string"},
            },
            "required": ["claim", "sources"],
        },
    },
    "tool_ground_from_context": {
        "short": "Shortcut: build a grounding record from inputs/context/ files in one call.",
        "description": "For decisions grounded in the researcher's narrative notes (not formal papers). Hashes each context file + records the cited excerpt.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
                "claim": {"type": "string"},
                "context_paths": {"type": "array", "items": {"type": "string"}},
                "cited_excerpts": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string"},
            },
            "required": ["claim", "context_paths"],
        },
    },
    "tool_claim_verify": {
        "short": "Chain-of-Verification (CoVe): record verification Q&A for a claim.",
        "description": "Each claim heading into the paper should be paired with N verification questions, independently answered. Claim is `verified` only when all `supports==true`. Surfaces in the master audit + dashboard.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "verifications": {"type": "array"},
                "decision_id": {"type": "string"},
                "step_id": {"type": "string"},
            },
            "required": ["claim", "verifications"],
        },
    },
    "tool_grounding_verify": {
        "short": "Audit gate — every decision in analysis.md must carry a grounding record.",
        "description": "Walks workspace/analysis.md decisions; flags any whose evidence chain is missing. Writes workspace/logs/grounding_audit.md; the master quality auditor uses it as a blocker for synthesis.",
        "category": "audit",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_lessons_record": {
        "short": "Reflexion: record a what-worked / what-didn't lesson for future runs.",
        "description": "After each step or plan, capture a textual lesson. tool_lessons_consult retrieves the top-K matching lessons for the next task and produces a prompt block to prepend to the next system prompt.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "description": "success | failure | partial | abandoned"},
                "reflection": {"type": "string"},
                "what_worked": {"type": "string"},
                "what_didnt": {"type": "string"},
                "recommendation": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "step_id": {"type": "string"},
                "scope": {"type": "string"},
            },
            "required": ["outcome", "reflection"],
        },
    },
    "tool_lessons_consult": {
        "short": "Retrieve top-K prior lessons relevant to the current task.",
        "description": "Returns lessons ranked by recency + tag overlap + keyword overlap. Failure-outcome lessons get a small boost (more actionable). Use the returned `prompt_block` to prepend a 'Prior lessons' section to the next AI turn.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "number"},
                "scope_filter": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task"],
        },
    },
    "tool_plan_step_grounded": {
        "short": "Plan a step with explicit Thought / Required-grounding / Action / Verification per sub-task.",
        "description": "Stronger than tool_plan_step. Auto-inventories the project's available evidence (inputs, context notes, literature, prior conclusions). Each sub-task has filled slots for thought, required grounding (which evidence will be consulted), action, expected outputs, verification question, and prior lessons consulted. Use for substantive analyses where every action should be traceable to evidence.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "inputs_to_consult": {"type": "array", "items": {"type": "string"}},
                "context_to_consult": {"type": "array", "items": {"type": "string"}},
                "literature_queries": {"type": "array", "items": {"type": "string"}},
                "max_substeps": {"type": "number"},
            },
            "required": ["goal"],
        },
    },
    # ── audit tools (code/prose/claims/evalue collapsed into tool_audit) ──
    "tool_preregister_freeze": {
        "short": "Freeze SAP + hypotheses BEFORE data analysis (content-hashed, immutable).",
        "description": "Snapshots methods.md + active hypotheses to workspace/.preregistration/prereg_<iso>.{md,yaml}. Diffed at synthesis time via tool_preregister_diff. See methodology/preregistration for the full SAP field list and the OSF submission flow.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "primary_outcomes": {"type": "string"},
                "secondary_outcomes": {"type": "string"},
                "target_n": {"type": "number"},
                "power_assumption": {"type": "string"},
                "stopping_rule": {"type": "string"},
                "subgroups": {"type": "array", "items": {"type": "string"}},
                "sensitivity": {"type": "array", "items": {"type": "string"}},
                "multiplicity": {"type": "string"},
                "inclusion": {"type": "array", "items": {"type": "string"}},
                "exclusion": {"type": "array", "items": {"type": "string"}},
                "missing_data": {"type": "string"},
                "additional_analyses": {"type": "array", "items": {"type": "string"}},
                "contingencies": {"type": "array", "items": {"type": "string"}},
                "anticipated_deviations": {"type": "array", "items": {"type": "string"}},
                "data_status": {"type": "string"},
            },
        },
    },
    "tool_preregister_diff": {
        "short": "Diff the frozen SAP against the current state — lists every deviation.",
        "description": "Loads the most recent .preregistration/prereg_*.yaml; compares hypotheses (added / removed / re-worded), methods.md (lines added / removed since freeze), and the paper's primary-outcome mention. Surfaces deviations the discussion section must acknowledge. Writes workspace/logs/preregistration_diff.md.",
        "category": "audit",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_sensitivity_define": {
        "short": "Author a multiverse / specification-curve sensitivity grid.",
        "description": "Creates workspace/<step>/sensitivity.yaml — base_script + a grid of analytic choices (covariate sets, exclusion rules, transformations, model families). The runner will fan out the Cartesian product; the base script reads each spec via env vars (RESEARCH_OS_SPEC_<KEY>) and writes a one-row {estimate, ci_lo, ci_hi, <spec_columns>} record per run.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "base_script": {"type": "string"},
                "estimate_column": {"type": "string"},
                "ci_columns": {"type": "array", "items": {"type": "string"}},
                "grid": {"type": "object"},
                "output_csv": {"type": "string"},
            },
            "required": ["step_id", "base_script"],
        },
    },
    "tool_sensitivity_run": {
        "short": "Execute the sensitivity grid + render the specification curve.",
        "description": "Runs base_script once per combination; collects {estimate, ci_lo, ci_hi, spec_columns} into the output CSV; renders a Steegen-style specification curve (ordered effect dots + CIs over a choice matrix) into outputs/figures/<NN>_specification_curve.png. Drops a provenance sidecar.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "max_specs": {"type": "number", "description": "Cap for testing — default = all combos."},
                "render_figure": {"type": "boolean"},
            },
            "required": ["step_id"],
        },
    },
    "tool_redteam_review": {
        "short": "Generate a hostile-reviewer report scaffold against the paper.",
        "description": "Writes workspace/reviews/redteam_<persona>_<ts>.md — the structure of a real journal reviewer report: summary, overall recommendation, major comments M1-M5, minor comments, threats-to-validity (internal/external/construct/statistical), devil's-advocate questions. Personas: methodological_skeptic | statistical_referee | sympathetic_peer. The model fills the scaffold using ONLY the listed workspace inventory.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "persona": {"type": "string", "description": "methodological_skeptic (default) | statistical_referee | sympathetic_peer"},
            },
        },
    },
    "tool_response_to_reviewers": {
        "short": "Write a response-to-reviewers template paired with the latest red-team report.",
        "description": "Produces synthesis/response_to_reviewers.md with one heading per reviewer comment (Mn, mn), pre-formatted for line-referenced rebuttal text. Read by the model to generate concrete response text once revisions are in.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_path": {"type": "string"},
            },
        },
    },
    "tool_null_findings_report": {
        "short": "Companion document for refuted / inconclusive / underpowered / abandoned analyses.",
        "description": "Walks the hypothesis tracker (refuted + inconclusive), every step's power_report.md (computed power < 0.8), and every __DEAD_END path. Writes synthesis/null_findings.md — a publishable companion that fights the file-drawer problem.",
        "category": "audit",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_audit_quality_full": {
        "short": "Run every quality gate in one call — completeness + code + prose + claims + prereg diff + grounding.",
        "description": "Master auditor. Runs all 6 quality gates: tool_audit_step_completeness + tool_audit_code_quality + tool_audit_prose + tool_audit_claims + tool_preregister_diff + tool_ground (grounding_verify) in one shot; aggregates the blocker set; writes workspace/logs/audit_master.md. tool_synthesize calls this as its first gate when no `section` is given. Grounding blockers surface as `[grounding] N decision(s) without grounding records`. NB: this master audit does NOT run the per-step literature gate — call `tool_audit_step_literature` per step (or rely on `tool_step_complete` to have caught it). The per-step literature check is run separately at synthesis time by `tool_audit_synthesis` / `tool_path_finalize`; if you skip it during the run, expect blockers at synthesis.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "skip": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "tool_slurm_submit": {
        "short": "Submit a SLURM job from researcher_config.runtime.cluster_defaults.",
        "description": "Generates an sbatch script (cpus, mem, time, partition, gpus, array, dependency, modules, conda env), submits it, records job_id + script in .os_state/cluster/jobs/<job_id>.json. All optional params default to runtime.cluster_defaults; typical call is just (step_id, cmd).",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "cmd": {"type": "string"},
                "job_name": {"type": "string"},
                "cpus": {"type": "number"},
                "mem": {"type": "string"},
                "time_limit": {"type": "string"},
                "partition": {"type": "string"},
                "gpus": {"type": "number"},
                "array": {"type": "string", "description": "e.g. '1-100%10' for 100 tasks, 10 concurrent."},
                "dependency": {"type": "string", "description": "e.g. 'afterok:12345'."},
                "modules": {"type": "array", "items": {"type": "string"}},
                "conda_env": {"type": "string"},
                "extra_sbatch": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["cmd"],
        },
    },
    "tool_slurm_status": {
        "short": "Live status via squeue + finished status via sacct for one or all project jobs.",
        "description": "When job_id is given, returns a single record (live + finished state, elapsed, max RSS, exit code). Without job_id, returns every job submitted from this project.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
        },
    },
    "tool_slurm_fetch": {
        "short": "Block until a SLURM job finishes; return stdout / stderr paths.",
        "description": "Polls squeue every poll_interval seconds until the job is no longer queued / running, then collects the log files under the recorded log_dir.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "poll_interval": {"type": "number"},
                "max_wait": {"type": "number"},
            },
            "required": ["job_id"],
        },
    },
    "tool_slurm_list": {
        "short": "List every SLURM job submitted from this project.",
        "description": "Reads .os_state/cluster/jobs/*.json. No external calls.",
        "category": "exec",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Synthesis & output ────────────────────────────────────────────
    "tool_synthesize_plan": {
        "description": "Inspect available sources (methods.md, conclusions per step, citations) and return the recommended section ordering. Call BEFORE tool_synthesize.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_synthesize": {
        "description": "Compile workspace findings into a publishable output. Without `section`, builds the full paper/poster/etc with numbered figures + tables + verified citations. With `section`, builds one section at a time (abstract | introduction | methods | results | discussion | conclusion | references). `output_type` drives the citation cap and section structure. Quality gate: refuses to build a full document if tool_audit_quality_full reports BLOCKERS. Phase-4c BLOCK-finding gate: ALSO refuses to compile when any unresolved BLOCK finding sits in workspace/logs/.audit_findings.jsonl (latest-snapshot semantics — a BLOCK from an earlier audit run that the latest rerun no longer reproduces is treated as resolved). The researcher (NOT the AI) can authorise a partial / WIP deliverable by passing override_completeness_gate=true (master quality gate bypass) or override_unresolved_blocks=true (BLOCK-finding ledger bypass) with a one-line override_rationale — both are logged to workspace/logs/override_log.md for the audit trail.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "description": "markdown | latex | both (default: markdown)",
                },
                "section": {
                    "type": "string",
                    "description": "Specific section to build, else full output.",
                },
                "output_type": {
                    "type": "string",
                    "description": "paper | abstract | poster | dashboard | report | grant (default: paper). Drives citation cap and section structure.",
                },
                "citation_style": {
                    "type": "string",
                    "description": "vancouver (default) | apa",
                },
                "override_completeness_gate": {
                    "type": "boolean",
                    "description": "Bypass the master quality gate for a partial / WIP deliverable. ONLY set when the researcher has explicitly authorised it. Logged.",
                },
                "override_unresolved_blocks": {
                    "type": "boolean",
                    "description": "Phase-4c: bypass the unresolved-BLOCK-findings gate (workspace/logs/.audit_findings.jsonl). ONLY set when the researcher has explicitly authorised compiling with active BLOCK findings on record. Logged to workspace/logs/override_log.md with the blocker ids.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "Required when override_completeness_gate=true OR override_unresolved_blocks=true. One-line reason the researcher authorised the bypass (e.g. 'reviewer asked for a preview of the discussion section before the final figures are in').",
                },
                "skip_gates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific audit names to skip (e.g. ['claims', 'prose']). Defaults to ['claims'] on first synthesis since paper.md doesn't exist yet.",
                },
                "auto_proceed": {
                    "type": "boolean",
                    "description": "AUTOPILOT-ONLY short-circuit (AUDIT-063). When true AND interaction.autonomy_level == 'autopilot', tool_synthesize processes ALL sections (methods → results → discussion → introduction → abstract) AND runs the full assembly in ONE call. Each per-section file is still written exactly as the multi-turn flow would write it. Passing true in manual/supervised/coaching modes returns an error — the multi-turn cadence is the deliberation pace those modes exist to provide. Default false.",
                },
            },
        },
    },
    "tool_latex_compile": {
        "description": "Compile synthesis/paper.tex to PDF (pdflatex + bibtex).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_poster_create": {
        "description": "Compile a conference poster from the curated synthesis spec. Default engine is Typst (academic_36x48 portrait, light theme, US-letter handout). Hero figures land on the poster sorted by `poster_priority` in each figure's .caption.md frontmatter (top 3). Optional QR PNG renders when qr_url is set + the qrcode package is installed (degrades gracefully). Set engine='latex' (or researcher_config.synthesis.poster_engine='latex') to fall back to the legacy tikzposter renderer; the legacy `layout` + `audience` kwargs route to that path.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "description": "typst (default) | latex (legacy tikzposter). Overrides researcher_config.synthesis.poster_engine.",
                },
                "template": {
                    "type": "string",
                    "description": "Typst engine only. academic_36x48 (default) | academic_48x36 | academic_a0_portrait | academic_a1_landscape | public_24x36.",
                },
                "theme": {
                    "type": "string",
                    "description": "Typst engine only. light (default) | dark | institution_branded.",
                },
                "qr_url": {
                    "type": "string",
                    "description": "Typst engine only. URL to encode in the footer QR code. Omitted gracefully if `qrcode` package is missing.",
                },
                "handout_pdf": {
                    "type": "boolean",
                    "description": "Typst engine only. Also emit synthesis/poster.handout.pdf (US-letter text-only condensed). Default true.",
                },
                "layout": {
                    "type": "string",
                    "description": "Legacy LaTeX engine only. billboard (default — readable from across the hall) | classic (IMRAD two-column).",
                },
                "audience": {
                    "type": "string",
                    "description": "Legacy LaTeX engine only. academic_conference (default) | symposium | industry | teaching.",
                },
            },
        },
    },
    "tool_dashboard": {
        "short": "Unified dashboard tool. operation=create|story_generate|story_edit|story_quality_bar|reviewer_sim|test_generate|test_run.",
        "description": "Unified dashboard dispatcher. operation='create' (default) renders the standalone offline HTML dashboard at synthesis/dashboard.html (v2 single-page-app by default; pass dashboard_legacy=true for the v1 long-scroll renderer; dashboard_default_mode='story' for narrative-first reading; audience ∈ {academic, executive, technical, teaching}; override_completeness_gate=true + override_rationale='<why>' suppresses the soft completeness warning panel for the FINAL deliverable). operation='story_generate' builds synthesis/dashboard_story.md (Theme 21 story-mode source) from workspace state. operation='story_edit' reads (no args) or patches synthesis/dashboard_story.md via `edits` (default mode='patch' diff-style payload, or mode='overwrite' to replace whole file). operation='story_quality_bar' WARNs when reading time falls outside 5-20 min, no figure in first 1000 words, or no DISAGREES/EXTENDS callout (no BLOCKERs — story mode is optional). operation='reviewer_sim' walks synthesis/dashboard.html top-to-bottom and returns whether a 5-minute skimmer would extract the headline finding. operation='test_generate' scaffolds tests/dashboard/ with the baseline Playwright + axe-core suite (pass overwrite=true to replace). operation='test_run' subprocesses pytest under tests/dashboard/ and returns structured failures + trace.zip paths (kwargs: only, visual, update_snapshots, timeout).",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create",
                        "story_generate",
                        "story_edit",
                        "story_quality_bar",
                        "reviewer_sim",
                        "test_generate",
                        "test_run",
                    ],
                    "description": "Which dashboard sub-operation to invoke. Defaults to 'create' when omitted.",
                },
                # operation='create' kwargs
                "title": {"type": "string", "description": "operation='create' — dashboard title."},
                "audience": {
                    "type": "string",
                    "description": "operation='create' — academic (default) | executive | technical | teaching.",
                },
                "dashboard_legacy": {
                    "type": "boolean",
                    "description": "operation='create' — use the v1 long-scroll renderer (back-compat). Default false (v2 single-page app).",
                },
                "dashboard_default_mode": {
                    "type": "string",
                    "description": "operation='create' — explore (default) | story. URL hash #mode=... and localStorage override at view time.",
                },
                "dashboard_search_enabled": {
                    "type": "boolean",
                    "description": "operation='create' — inline the MiniSearch full-text index. Default true.",
                },
                "dashboard_print_optimized": {
                    "type": "boolean",
                    "description": "operation='create' — include the print stylesheet that hides chrome + paginates sections. Default true.",
                },
                "override_completeness_gate": {
                    "type": "boolean",
                    "description": "operation='create' — suppress the step-completeness warning panel. Set only on explicit researcher approval. Logged.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "operation='create' — one-line reason for the bypass; logged to workspace/logs/override_log.md.",
                },
                # operation='story_edit' kwargs
                "edits": {
                    "type": "string",
                    "description": "operation='story_edit' — patch payload (`<<<<replace>>>>...----with----...<<<<end>>>>` blocks) OR full file content (with mode='overwrite').",
                },
                "mode": {
                    "type": "string",
                    "description": "operation='story_edit' — patch (default) | overwrite.",
                },
                # operation='reviewer_sim' kwargs
                "dashboard_path": {
                    "type": "string",
                    "description": "operation='reviewer_sim' — dashboard file path (default synthesis/dashboard.html).",
                },
                # operation='test_generate' kwargs
                "overwrite": {
                    "type": "boolean",
                    "description": "operation='test_generate' — overwrite existing test suite. Default false.",
                },
                # operation='test_run' kwargs
                "only": {"type": "string", "description": "operation='test_run' — pytest node-id filter."},
                "visual": {"type": "boolean", "description": "operation='test_run' — enable visual regression."},
                "update_snapshots": {"type": "boolean", "description": "operation='test_run' — update snapshot baselines."},
                "timeout": {"type": "number", "description": "operation='test_run' — timeout in seconds."},
            },
        },
    },

    # ── Reasoning / research-grounding ───────────────────────────────
    "tool_research_method": {
        "description": "Gather 5-10 academic + web sources about a method, dedupe, write a structured report. Use BEFORE choosing any statistical/computational method.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Method name + context, e.g. 'logistic regression with imbalanced classes'."},
                "limit": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    "tool_research_tool": {
        "description": "Find candidate libraries / CLIs / websites for a task. Tags each candidate as installable | api_available | external_tool | paid_or_licensed. Use when picking a tool.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "language": {"type": "string", "description": "any | python | r | julia | bash"},
            },
            "required": ["task"],
        },
    },
    "tool_external_tool_instructions": {
        "description": "When the chosen tool is external (website, GUI, paid service), write a WORKSHEET.md telling the researcher how to use it and where to drop the outputs.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "purpose": {"type": "string"},
                "url": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tool_name", "purpose", "url"],
        },
    },
    "tool_alternative_path_propose": {
        "description": (
            "Confidence-gated alternative-pipeline scan. Pulls literature on "
            "the user's chosen method AND on alternatives framed for the "
            "specific data shape, counts comparative-evidence signals, and "
            "returns a recommendation: `commit_user_method` (stay quiet — "
            "default) OR `branch_to_alternative` (surface the alternative to "
            "the researcher ONCE and, on confirmation, call `sys_path_create "
            "branch_of=<current>` to create an `NN_<slug>_alt_path_<k>` fork "
            "alongside the primary). Writes "
            "`outputs/reports/alternative_path_<slug>.md` with the cited "
            "evidence. Use BEFORE committing a methodology when you suspect a "
            "subfield-canonical alternative could materially out-perform the "
            "researcher's first instinct — but DO NOT call repeatedly for "
            "the same step (proposing weak alternatives erodes trust)."
        ),
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What the step is trying to do, e.g. 'differential expression on bulk RNA-seq with paired samples'.",
                },
                "user_method": {
                    "type": "string",
                    "description": "The method the user proposed (or the AI's default), e.g. 'DESeq2 with ~condition design'.",
                },
                "data_summary": {
                    "type": "string",
                    "description": "Short data-shape note that helps the literature scan (sample size, paired-ness, sparsity, etc.). Optional but recommended.",
                },
                "limit": {"type": "number"},
            },
            "required": ["task", "user_method"],
        },
    },
    "tool_plan_step": {
        "description": "Force a complex step to be broken into atomic sub-tasks BEFORE coding. Writes a plan markdown the AI executes piecewise. Required by analysis_plan when scope is non-trivial.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "max_substeps": {"type": "number"},
            },
            "required": ["goal"],
        },
    },

    # ── Intake auto-fill ──────────────────────────────────────────────
    "tool_intake_autofill": {
        "description": "Read inputs/ (data + literature + context notes) and propose project metadata (research question, domain, hypotheses). Fills blanks in researcher_config.yaml and rewrites inputs/intake.md.",
        "category": "intake",
        "inputSchema": {
            "type": "object",
            "properties": {
                "overwrite": {
                    "type": "boolean",
                    "description": "If true, overwrite even non-blank config fields (default false).",
                }
            },
        },
    },

    # ── Real background tasks ─────────────────────────────────────────
    "tool_task_run": {
        "description": "Spawn a real background subprocess (Popen). Returns task_id immediately. Use for any command expected to run longer than runtime.long_running_threshold_seconds.",
        "category": "tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell-tokenised command, or a list."},
                "cwd": {"type": "string", "description": "Working directory relative to project root."},
                "description": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    "tool_task_status": {
        "description": "Check a background task's status + tail of log.",
        "category": "tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "tail_lines": {"type": "number"},
            },
            "required": ["task_id"],
        },
    },
    "tool_task_list": {
        "description": "List all known background tasks with live status.",
        "category": "tasks",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_task_kill": {
        "description": "Kill a background task (SIGTERM by default).",
        "category": "tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "signal_name": {"type": "string", "description": "TERM | KILL | INT"},
            },
            "required": ["task_id"],
        },
    },

    # ── Multi-language script support ────────────────────────────────
    "tool_notebook_exec": {
        "short": "Execute a Jupyter notebook (papermill-aware with provenance sidecar).",
        "description": "Executes a .ipynb. When papermill is installed AND parameters is given, runs the notebook with parameter injection — output lands at notebook/runs/<stem>_<param-hash>.ipynb with a .prov.json sidecar capturing the input notebook + parameters + RNG seed + wall time. When papermill is absent, falls back to `jupyter nbconvert --execute --inplace` (parameters dict is ignored with a warning). Pass output_path to override the default runs/ location.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "timeout": {"type": "number"},
                "kernel": {"type": "string"},
                "parameters": {"type": "object",
                               "description": "Injected into the `parameters`-tagged cell (papermill only)."},
                "output_path": {"type": "string"},
            },
            "required": ["notebook_path"],
        },
    },
    "tool_rmarkdown_render": {
        "description": "Render an .Rmd or .qmd document (rmarkdown::render OR quarto render).",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_path": {"type": "string"},
                "output_format": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["doc_path"],
        },
    },

    # ── Multi-hypothesis tracking ────────────────────────────────────
    "mem_hypothesis_add": {
        "description": "Register a new hypothesis (tracked in state.active_hypotheses + analysis.md).",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "statement": {"type": "string"},
                "hypothesis_id": {"type": "string", "description": "Optional; auto-assigned H1, H2, ..."},
                "direction": {"type": "string"},
                "status": {"type": "string", "description": "testing|supported|refuted|inconclusive"},
            },
            "required": ["statement"],
        },
    },
    "mem_hypothesis_update": {
        "description": "Update a hypothesis (status + add evidence note).",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hypothesis_id": {"type": "string"},
                "status": {"type": "string"},
                "evidence": {"type": "string"},
                "step": {"type": "string"},
            },
            "required": ["hypothesis_id"],
        },
    },
    "mem_hypothesis_list": {
        "description": "List every tracked hypothesis.",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Iterative planning ───────────────────────────────────────────
    "tool_plan_next_step": {
        "description": "Survey current state, pull fresh literature + tool candidates, propose the BEST next step. Use for iterative workflows where the researcher wants the AI to decide what's worth doing next.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "search_literature": {"type": "boolean"},
                "search_tools": {"type": "boolean"},
            },
        },
    },
    "tool_branch_recommendation": {
        "description": "Decide whether to branch into a new parallel experiment or continue extending the current one.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },

    # ── Scratch sandbox ───────────────────────────────────────────────
    "tool_scratch_write": {
        "description": "Write a quick-test file to workspace/scratch/. Gitignored, no provenance — use for syntax checks, smoke tests, parameter sweeps. Anything important must be moved out into a proper experiment.",
        "category": "scratch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["filename", "content"],
        },
    },
    "tool_scratch_run": {
        "description": "Execute a script in workspace/scratch/. Language inferred from extension (.py | .R | .jl | .sh).",
        "category": "scratch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["filename"],
        },
    },
    "tool_scratch_list": {
        "description": "List files currently in workspace/scratch/.",
        "category": "scratch",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_scratch_clear": {
        "description": "Wipe workspace/scratch/ contents (keeps .gitignore and README).",
        "category": "scratch",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Workspace repair (heal, never delete) ────────────────────────
    "tool_workspace_repair": {
        "description": "Detect missing directories / corrupted state / stale paths and (optionally) heal them. NEVER deletes files.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"dry_run": {"type": "boolean"}},
        },
    },

    # ── Mid-flow context injection ───────────────────────────────────
    "tool_context_intake": {
        "description": "Detect new files dropped anywhere in the project and route each into the right inputs/ subfolder (literature / raw_data / context). Logs every move; never overwrites.",
        "category": "intake",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_dir": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "also_autofill": {"type": "boolean"},
            },
        },
    },

    # ── Verified citations ────────────────────────────────────────────
    "tool_citations_verify": {
        "description": "Verify every citation_key in workspace/citations.md by hitting Crossref. Reports verified vs unverified (possibly hallucinated) entries.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── Session resume + progress digest ─────────────────────────────
    "tool_session_resume": {
        "description": "Reconstruct intent + status from logs after a pause / handoff / new chat session. Returns a structured 'resume brief' (current stage, hypotheses, open paths, running tasks, recommended next protocol) plus the message the AI should hand back to the researcher.",
        "category": "interaction",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_progress_digest": {
        "description": "One-page summary of the project: experiments active/completed/dead-end, hypotheses by status, figures/tables/reports counts, citations counted. Writes workspace/logs/progress_digest.md AND returns the markdown.",
        "category": "interaction",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # tool_dead_end_lessons consolidated into
    # tool_lessons(operation='dead_end') — phase-9-c4.
    "tool_quick_review": {
        "description": "Stage a one-page critical-appraisal skeleton for a paper at workspace/reviews/<slug>.md. AI then populates it per the `guidance/quick_paper_review` protocol. Use for fast peer-review or 'what do you think of this paper?' requests.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_path": {
                    "type": "string",
                    "description": "Path to a local PDF/MD/TXT in inputs/literature/ OR a URL.",
                },
                "lens": {
                    "type": "string",
                    "description": "claims_vs_evidence (default) | methodological_rigour | novelty | statistical_inference | replicability",
                },
            },
            "required": ["paper_path"],
        },
    },
    "sys_dep_inventory": {
        "description": "Report which optional dependencies (search, viz, audit, ml, notebook, literature, web) failed to import. Call once at session start so you know which tools will work.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── New: caching, DAG, step env lock ─────────────────────────────
    "tool_cache_clear": {
        "short": "Wipe cached search results (optionally per-provider or older-than-N-days).",
        "description": "Manage the file-backed search cache at .os_state/cache/search/<provider>/. Call when you suspect stale results, or after a long break to free disk. Cache TTL defaults to 24h (configurable via runtime.cache_ttl_seconds).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Restrict to one provider (semantic_scholar | crossref | pubmed | arxiv | web). Omit for all.",
                },
                "older_than_days": {
                    "type": "number",
                    "description": "Only delete entries older than this many days. Omit for all entries.",
                },
            },
        },
    },
    "tool_workflow_dag": {
        "short": "Build a DAG of numbered steps + their data dependencies; write docs/workflow_dag.mermaid.",
        "description": "Walks each numbered step's data/input symlinks to derive cross-step dependencies, then writes docs/workflow_dag.mermaid with colour-coded nodes (active / completed / dead_end). Pass render_png=true to also emit a PNG (requires mmdc — npm install -g @mermaid-js/mermaid-cli). Auto-refreshed by sys_path_create and sys_path_abandon so the DAG stays in sync without manual calls.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "render_png": {"type": "boolean"},
                "output_dir": {
                    "type": "string",
                    "description": "Where to write (default: docs).",
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # Paywall + permanent-error memory.
    # tool_failure_record / tool_failure_check / tool_failure_list
    # consolidated into tool_lessons(operation='failure_{record,check,list}')
    # — phase-9-c4.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Telemetry-free local reliability log.
    # tool_reliability_log_event / tool_reliability_report consolidated
    # into tool_reliability(operation='log_event'|'report') — phase-9-c4.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Stale-state detection + cross-step coherence.
    # ------------------------------------------------------------------
    "tool_state_freshness_check": {
        "short": "Detect stale workspace state (state.json > 30d, citations older than newest PDF, orphan provenance).",
        "description": "Auto-called by sys_boot. If state.json mtime > stale_after_days (default 30), OR workspace/citations.md older than the newest inputs/literature/*.pdf, OR any per-step .prov.json points to a script that no longer exists, returns is_stale=true + a prompt_for_ai string the AI surfaces as a 'reconfirm before continuing?' question. Cheap; safe to call at every boot.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_after_days": {"type": "integer"},
            },
        },
    },
    # ------------------------------------------------------------------
    # Intake re-entry detection.
    # ------------------------------------------------------------------
    "tool_intake_freshness": {
        "short": "Return recommended intake depth (full | refresh-only | skip) based on intake.md freshness + step count.",
        "description": "Decides whether project_startup should fully autofill intake or skip / refresh-only. inputs/intake.md missing or stub → full. Exists with >500 substantive chars + edited in last fresh_window_days → skip. Older than fresh_window_days but substantive → refresh-only. Also reports mid_pipeline_entry_recommended=true when >=1 numbered step has conclusions.md.",
        "category": "data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fresh_window_days": {"type": "integer"},
            },
        },
    },
    # ------------------------------------------------------------------
    # writing_discussion verdict-driven paragraphs.
    # ------------------------------------------------------------------
    "tool_writing_discussion_from_verdicts": {
        "short": "Append one Discussion paragraph per non-AGREES verdict in any step's findings_vs_literature.md.",
        "description": "Reads every workspace/<step>/literature/findings_vs_literature.md, finds DISAGREES + EXTENDS verdicts that carry a Discussion implication block, and appends one paragraph per verdict to synthesis/discussion.md under HTML-comment-delimited markers (idempotent — re-runs replace the block; hand-edits outside the markers are preserved). Closes the audit gap where verdicts never reached the Discussion.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_discussion_coverage_audit": {
        "short": "BLOCK gate: every non-AGREES literature verdict must have a Discussion paragraph.",
        "description": "Companion to tool_writing_discussion_from_verdicts. Walks every step's findings_vs_literature.md and verifies synthesis/discussion.md mentions each DISAGREES/EXTENDS claim (>=50% key-word overlap). Returns status='error' + a blocker list if any verdict is uncovered — tool_writing_discussion's validate step honours this as a hard BLOCK unless override_discussion_coverage=true (logged to override_log.md with override_rationale).",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "override_discussion_coverage": {
                    "type": "boolean",
                    "description": "Set true to bypass the BLOCK when verdicts are intentionally not in the Discussion (e.g. the section is being rewritten). Requires override_rationale under interaction.quality_gate_policy=enforce. Logged to override_log.md.",
                },
                "override_rationale": {
                    "type": "string",
                    "description": "Short justification for the override. Required when quality_gate_policy=enforce.",
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # Adaptive friction (rigor signals + self-certify).
    # ------------------------------------------------------------------
    "tool_rigor_signals_scan": {
        "short": "Score project rigor 0-100 from methods.md, citations, git, preregistration, scripts, prior step summaries.",
        "description": "Infers rigor signals across 6 dimensions and returns trust_score 0-100 + per-signal breakdown + recommended_strictness (light when >=75, normal when >=50, strict when <50). Audits can scale strictness via tool_resolve_gate_strictness.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_resolve_gate_strictness": {
        "short": "Resolve effective gate strictness (light | normal | strict) from researcher_config + trust_score.",
        "description": "researcher_config.gate_strictness can be light | normal | strict | auto. auto follows the rigor_signals_scan trust_score. Returns the resolved value + source (config | auto | default). Light downgrades most blockers to notes; strict keeps full enforcement.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_self_certify": {
        "short": "Persist a researcher self-certification (domain + scope + rationale).",
        "description": "Researcher with deep expertise can self-certify equivalent work was done outside RO. Domains: literature_loop (alias lit_loop), stack_plan, preregistration, sensitivity_analysis, code_review, reproducibility. Persisted to workspace/researcher_certifications.yaml; audits downgrade matching blockers to notes (still surfaced for transparency).",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "scope": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["domain", "scope", "rationale"],
        },
    },
    "tool_list_certifications": {
        "short": "List active researcher self-certifications.",
        "description": "Return the list of currently-active researcher_certifications.yaml entries. Use when an audit blocker says 'consider tool_self_certify' to see whether a cert already exists.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ------------------------------------------------------------------
    # Quick mode + promote-to-step.
    # ------------------------------------------------------------------
    "tool_quick_route": {
        "short": "Detect throwaway / sanity-check / exploratory intent and short-circuit protocol load.",
        "description": "Call before tool_route on every prompt. If the prompt matches a quick trigger ('just make me a plot', 'sanity check', 'exploratory only', 'quick look', 'throwaway viz', 'quick check', 'scratch'), returns is_quick=true + complexity='quick' + recommended_tool='tool_scratch_write'. Quick mode bypasses protocols + audit gates; results land under workspace/scratch/. Researcher can later promote via tool_promote_to_step.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    "tool_promote_to_step": {
        "short": "Retroactively wrap a scratch result in proper provenance (new numbered step + sidecar + summary).",
        "description": "Promote a workspace/scratch/ artifact into a proper numbered step. Creates the next workspace/NN_<slug>/ folder, copies the scratch file into outputs/figures/ (or step root for non-image files), emits .prov.json sidecar pointing back to the original scratch, writes minimal conclusions.md + step_summary.yaml. By default literature_required=false on the promoted step.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scratch_path": {"type": "string"},
                "step_slug": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["scratch_path", "step_slug"],
        },
    },
    "tool_project_tier_strictness": {
        "short": "Map researcher_config.project_tier (throwaway | sketch | production) -> default gate_strictness.",
        "description": "researcher_config.project_tier sets the default audit strictness across a whole project. throwaway -> light, sketch -> normal, production -> strict. Returns the resolved tier + strictness.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # Dry-run + bundling + coaching (Themes 13 / 15 / 7).
    "tool_dry_run": {
        "short": "Preview a protocol's tool-call sequence without executing — for supervised review.",
        "description": "Wraps sys_protocol_get format='dryrun'. Returns the protocol's full step sequence with predicted tool calls inferred from each step's description body. No tool is actually invoked; no files are written. Useful before committing in supervised / coaching autonomy modes. Pass optional simulated_args to annotate expected per-step args; ignored if not provided.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "simulated_args": {"type": "object", "additionalProperties": True},
            },
            "required": ["protocol_name"],
            "additionalProperties": False,
        },
    },
    "tool_step_complete": {
        "short": "Bundle: tool_path_finalize + tool_audit_step_completeness + tool_audit_step_literature + tool_step_revision_options in one call.",
        "description": "One-shot end-of-step bundle. Calls (in order) tool_path_finalize, tool_audit_step_completeness, tool_audit_step_literature, then tool_step_revision_options on the named step. Returns a merged result {finalize, completeness, literature, revision} with overall_status='success' | 'warning' | 'error'. Reduces 4 tool calls to 1 — eliminates small-model drift between calls and halves the round-trip latency. The AI should still surface the revision options verbatim per the anti-one-shot doctrine.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "override_literature_gate": {"type": "boolean"},
                "override_rationale": {"type": "string"},
            },
            "required": ["step_id"],
            "additionalProperties": False,
        },
    },
    # tool_mistake_replay consolidated into
    # tool_lessons(operation='mistake_replay') — phase-9-c4.

    # ─── consolidated tools ─────────────────────────
    "tool_search": {
        "short": "Unified literature/web search. Replaces tool_search_{semantic_scholar,pubmed,crossref,arxiv,web} via source=… or auto.",
        "description": "One search tool, five providers + auto-routing. Pass source='semantic_scholar'|'pubmed'|'crossref'|'arxiv'|'web' to pin a provider, or source='auto' (default) to let Research-OS pick based on the query's domain (biomedical → semantic_scholar+pubmed; ML/methods → semantic_scholar+arxiv; social/behavioral → crossref+semantic_scholar; geoscience → crossref+arxiv; generic → web). The pre-consolidation per-provider names still work as deprecated aliases (logged for usage audit).",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["auto", "semantic_scholar", "pubmed", "crossref", "arxiv", "web"],
                },
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    "tool_plan": {
        "short": "Unified plan dispatcher. operation='turn'|'advance'|'clear'. Replaces tool_plan_{turn,advance,clear}.",
        "description": "Consolidates the three plan-progression tools behind one entry. operation='turn' returns the this-turn/next-turn batch (replaces tool_plan_turn). operation='advance' marks the current step done + returns the next (replaces tool_plan_advance; honours override_gate). operation='clear' discards the active plan (replaces tool_plan_clear). tool_plan_step_grounded stays standalone — distinct purpose.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["turn", "advance", "clear"]},
                "override_gate": {"type": "boolean"},
                "override_rationale": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    "sys_path": {
        "short": "Unified path dispatcher. operation='create'|'abandon'|'list'. Replaces sys_path_{create,abandon,list}.",
        "description": "One entry for the three path-lifecycle tools. operation='create' (was sys_path_create) takes name + hypothesis + branch_of. operation='abandon' (was sys_path_abandon) takes path_name + rationale. operation='list' (was sys_path_list) returns all paths with status.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["create", "abandon", "list"]},
                "name": {"type": "string"},
                "hypothesis": {"type": "string"},
                "branch_of": {"type": "string"},
                "from_step": {"type": "string"},
                "allow_unfinalized_predecessor": {"type": "boolean"},
                "override_rationale": {"type": "string"},
                "path_name": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    "tool_ground": {
        "short": "Register a grounded claim. mode='explicit' (sources) | 'from_context' (context_paths). Replaces tool_grounding_register + tool_ground_from_context.",
        "description": "Unified grounding tool. mode='explicit' uses an explicit `sources` list (replaces tool_grounding_register). mode='from_context' anchors the claim to files already in the project context (replaces tool_ground_from_context).",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["explicit", "from_context"]},
                "claim": {"type": "string"},
                "decision_id": {"type": "string"},
                "sources": {"type": "array"},
                "context_paths": {"type": "array"},
                "cited_excerpts": {"type": "array"},
                "step_id": {"type": "string"},
                "confidence": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["claim"],
        },
    },
    "tool_verify": {
        "short": "Verify a claim or the whole project's grounded claims. scope='claim'|'project'. Replaces tool_claim_verify + tool_grounding_verify.",
        "description": "Unified verification tool. scope='claim' checks one claim against a verifications list (replaces tool_claim_verify). scope='project' sweeps every registered grounded claim in the project (replaces tool_grounding_verify).",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["claim", "project"]},
                "claim": {"type": "string"},
                "verifications": {"type": "array"},
                "decision_id": {"type": "string"},
                "step_id": {"type": "string"},
            },
        },
    },
    "tool_lessons": {
        "short": "Unified lessons + failure-memory store. operation=record|consult|failure_record|failure_check|failure_list|dead_end|mistake_replay.",
        "description": "Single entry point for the 'what went wrong / what did we learn' family. operation='record' appends a Reflexion-style lesson (was tool_lessons_record). operation='consult' retrieves the top-K matching prior lessons for the next task (was tool_lessons_consult). operation='failure_record' persists a known-bad URL/DOI / paywall hit (was tool_failure_record). operation='failure_check' pre-checks before retrying a download (was tool_failure_check). operation='failure_list' returns the most recent failures (was tool_failure_list). operation='dead_end' pulls lessons from every __DEAD_END folder (was tool_dead_end_lessons). operation='mistake_replay' surfaces recurring patterns from reliability + override logs (was tool_mistake_replay). The legacy tool names continue to dispatch through this entry point via alias + param injection.",
        "category": "research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "record",
                        "consult",
                        "failure_record",
                        "failure_check",
                        "failure_list",
                        "dead_end",
                        "mistake_replay",
                    ],
                },
                # record args
                "outcome": {"type": "string"},
                "reflection": {"type": "string"},
                "what_worked": {"type": "string"},
                "what_didnt": {"type": "string"},
                "recommendation": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "step_id": {"type": "string"},
                "scope": {"type": "string"},
                # consult args
                "task": {"type": "string"},
                "top_k": {"type": "integer"},
                "scope_filter": {"type": "array", "items": {"type": "string"}},
                # failure_record / failure_check / failure_list args
                "tool": {"type": "string", "description": "For failure_record: which tool errored."},
                "target": {"type": "string", "description": "For failure_record/failure_check: URL or DOI being checked."},
                "reason": {"type": "string", "description": "For failure_record: error reason (paywall, permanent_404, ...)."},
                "error_text": {"type": "string"},
                "permanent": {"type": "boolean"},
                # failure_list / mistake_replay shared
                "limit": {"type": "integer"},
            },
        },
    },
    "tool_reliability": {
        "short": "Unified reliability log. operation='log_event'|'report'. Replaces tool_reliability_log_event + tool_reliability_report.",
        "description": "Telemetry-free local reliability log. operation='log_event' appends one redacted structural event (gate fire, tool error, recovery, etc.) to workspace/.os_state/reliability.jsonl (was tool_reliability_log_event). operation='report' aggregates the log into a markdown summary at workspace/logs/reliability_report.md (was tool_reliability_report). The log contains no project content — safe to paste into a GitHub issue when filing a regression report. Allowed event types: gate_fire, gate_recover, gate_abandon, tool_error, tool_success, protocol_start, protocol_complete, override_used, stale_state_detected, paywall_skipped.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["log_event", "report"]},
                # log_event args
                "event_type": {"type": "string"},
                "protocol_name": {"type": "string"},
                "model_profile": {"type": "string"},
                "payload": {"type": "object", "additionalProperties": True},
            },
        },
    },
    "mem_log": {
        "short": "Unified memory append. kind='methods'|'decision'|'hypothesis'|'analysis'. Replaces mem_{methods_append,decision_log,hypothesis_update,analysis_log}.",
        "description": "Consolidates the four memory-append tools behind one entry. kind='methods' (was mem_methods_append) takes method/parameters/justification. kind='decision' (was mem_decision_log) takes context/selected/rationale. kind='hypothesis' (was mem_hypothesis_update) takes hypothesis_id/status/evidence/step. kind='analysis' (was mem_analysis_log) takes a free-form entry.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["methods", "decision", "hypothesis", "analysis"]},
                "entry": {"type": "string"},
                "method": {"type": "string"},
                "step_name": {"type": "string"},
                "step_number": {"type": "string"},
                "dataset_name": {"type": "string"},
                "dataset_hash": {"type": "string"},
                "implementation": {"type": "string"},
                "parameters": {"type": "string"},
                "justification": {"type": "string"},
                "assumptions": {"type": "array"},
                "context": {"type": "string"},
                "selected": {"type": "string"},
                "rationale": {"type": "string"},
                "hypothesis_id": {"type": "string"},
                "status": {"type": "string"},
                "evidence": {"type": "string"},
                "step": {"type": "string"},
            },
            "required": ["kind"],
        },
    },
    "tool_deprecations_summary": {
        "short": "Aggregate counts from .os_state/deprecations.log — which deprecated aliases / redirects this project is still hitting.",
        "description": "Reads .os_state/deprecations.log (populated whenever a deprecated alias is invoked OR a redirect-stub protocol is loaded) and returns aggregated counts by kind/source/target. Use to audit which deprecated names the project still relies on before the next major (when aliases hard-remove).",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    # ── Typst PDF + dashboard content gates + synthesis preview + content depth ──
    "tool_paper_compile_typst": {
        "short": "Compile synthesis/paper.md → paper.typ → paper.pdf via Typst.",
        "description": "Markdown → Typst → PDF using a per-venue template (nature | science | nejm | cell | ieee_conf | neurips | acl | plos | generic_two_column | generic_thesis). Generates synthesis/paper.typ + synthesis/biblio.yml (Hayagriva) and runs `typst compile`. Returns pdf_path, page_count, citation_count, typst_warnings/errors. Reads researcher_config.writing_preferences.venue_template if `venue` not given. The LaTeX path (tool_latex_compile) remains available for journals that require .tex submission.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_path": {"type": "string", "description": "Default 'synthesis/paper.md'."},
                "venue": {"type": "string", "description": "One of: nature, science, nejm, cell, ieee_conf, neurips, acl, plos, generic_two_column, generic_thesis. Falls back to researcher_config or 'generic_two_column'."},
                "output": {"type": "string", "description": "Default 'synthesis/paper.pdf'."},
            },
        },
    },
    # tool_dashboard_story_generate / story_edit / story_quality_bar
    # consolidated into tool_dashboard(operation=story_*) — phase-9-c2.
    "tool_figure_interactive_autogen": {
        "short": "Write an interactive HTML companion (Vega-Lite for scatter/heatmap/time-series, vis-network for graphml) next to a static figure. Offline-capable.",
        "description": "Given a static figure (.png/.svg/.jpg), look for the sibling data file (<stem>_data.csv / <stem>_matrix.csv / <stem>_series.csv / <stem>.graphml), choose the right interactive kind by heuristics, and write <stem>.html next to the figure. The companion inlines the vendored Vega/Vega-Lite/Vega-Embed (or vis-network) bundle so it runs offline. Tagged with <meta name='ro-auto-generated' content='true'> so the researcher knows they can replace it. Idempotent — returns status='exists' if a companion is already there.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "figure_path": {"type": "string", "description": "Path to the static figure under workspace/<step>/outputs/figures/."},
            },
            "required": ["figure_path"],
        },
    },
    # tool_dashboard_reviewer_sim consolidated into
    # tool_dashboard(operation=reviewer_sim) — phase-9-c2.
    "tool_synthesis_preview": {
        "short": "Predict what tool_synthesize will produce — word counts, page count, figures, citations, gaps — without drafting.",
        "description": "Cheap deterministic dry-run (~1 sec vs ~30s for full synthesis). Reads workspace/<step>/conclusions.md + step_summary.yaml + findings_vs_literature.md + workspace/citations.md but does NOT call the AI to draft prose. Returns predicted_word_count_per_section, predicted_total_word_count, predicted_page_count or slide_count, predicted_figures_embedded, predicted_citations, predicted_steps_drawn_from, detected_gaps, estimated_render_time_seconds. mode='diff' compares against the existing deliverable on disk.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "paper | dashboard | poster | slides | grant | report. Default 'paper'."},
                "venue": {"type": "string"},
                "mode": {"type": "string", "description": "'fresh' (default) or 'diff' against existing deliverable."},
            },
        },
    },
    "tool_section_substantiveness": {
        "short": "Content depth audit for synthesis/paper.md — per-section checks beyond word counts.",
        "description": "Runs per-IMRAD-section audits: Abstract (≥1 number + ≥1 method + ≥1 conclusion verb), Introduction (≥3 cited prior works + 'in this study, we' pivot), Methods (every workspace step's primary method/tool named; coverage <50% BLOCKS, <80% WARNS), Results (≥1 statistic per finding; focal figures referenced), Discussion (Limitations paragraph + future-work direction + ≥1 paragraph per non-AGREES verdict), References (every cited key in bibliography, BLOCKER for missing). Returns blockers, warnings, sub_reports per section, cliché hits.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_path": {"type": "string", "description": "Default 'synthesis/paper.md'."},
            },
        },
    },
    # ── humanities essay scaffold ──────────────────────────────────────
    "tool_humanities_essay_scaffold": {
        "short": "Scaffold a non-IMRAD humanities essay.",
        "description": "Write synthesis/paper.md with the six interpretive section headings + one-paragraph stubs the synthesis/humanities_essay_structure protocol prescribes (introduction+thesis, contextual framing, three close readings, critical conversation, counter-argument+reply, conclusion+stakes). Idempotent: re-running on a partially drafted paper.md preserves substantive content (>200 non-stub chars under a heading) and only fills missing sections. Pairs with humanities_essay.typ for the venue layer (1.25in margins, 12pt serif, MLA-style unnumbered headings, footnote apparatus, 0.5in block-quote indent). No arguments — operates on the current project root.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── figure auto-embed + orphan-coverage audit ──────────────────────
    "tool_paper_figures_autoembed": {
        "short": "Walk every step's outputs/figures/ and embed them into the right section of synthesis/paper.md.",
        "description": "Discovers each numbered step's outputs/figures/ where step_summary.yaml.figures_for_paper is true (default), reads each figure's <stem>.caption.md YAML frontmatter (section_hint, figure_priority, poster_priority, alt_text, figures_for_paper, interactive_required), and inserts the markdown image blocks into synthesis/paper.md. Three modes: append_to_section (default; uses section_hint), explicit_map (caller supplies section_map={stem: section}), reorder (clusters all figures at end of Results sorted by figure_priority). Idempotent — a stem already present in the document is never re-inserted, so manual figure placements are preserved. Multi-paragraph captions split into a headline + a 'Note:' appendix. Calls rewrite_figure_xrefs automatically when researcher_config.synthesis.figure_xref_rewrite=true unless override_xref_rewrite is set. Writes an append-only log to workspace/logs/figure_auto_embed.md so the audit trail captures every run.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "Placement mode: append_to_section (default) | explicit_map | reorder.",
                },
                "section_map": {
                    "type": "object",
                    "description": "Only used when mode='explicit_map'. {figure_stem: section_name}. Overrides each figure's section_hint frontmatter.",
                    "additionalProperties": {"type": "string"},
                },
                "override_xref_rewrite": {
                    "type": "boolean",
                    "description": "When true, skip the figure-xref rewrite pass even if researcher_config.synthesis.figure_xref_rewrite=true. Use when paper.md has pre-formatted Pandoc cross-refs the AI must not touch.",
                },
            },
            "additionalProperties": False,
        },
    },
    # ── real slide compilation engine ──────────────────────────────────
    "tool_slides_create": {
        "short": "Compile a real presentation deck — Reveal.js HTML or Touying-compatible Typst PDF — from workspace findings + slides_spec.yaml.",
        "description": "Two production engines. engine='reveal' writes synthesis/slides.html — a single self-contained file backed by the vendored Reveal.js v5 runtime with stock speaker-notes plugin (press 's' for presenter view). engine='touying' writes synthesis/slides.typ against the bundled touying-mini.typ template and shells out to the typst CLI to produce synthesis/slides.pdf (requires typst on PATH). Five stock templates: conference_15min (12 slides), conference_5min_lightning (6 slides), lab_meeting_30min (16 slides + backup section), defense_45min (35 slides chapter-arc), public_outreach (12 slides, no jargon). theme='' picks per-engine default (white). speaker_notes_enabled=True (default) embeds the per-slide notes. print_handout=True (default) also emits synthesis/slides.handout.pdf — a 2-up A4 condensed PDF with speaker notes printed beneath each slide. Prereq: at least one workspace/<step>/conclusions.md OR synthesis/slides_spec.yaml; missing both returns a structured error. Back-compat: legacy output_format='reveal'|'beamer'|'pdf' and audience= kwargs are accepted and mapped to engine= silently.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "description": "reveal (default — single-file HTML, Reveal.js v5) | touying (Typst → PDF, requires typst CLI)",
                },
                "template": {
                    "type": "string",
                    "description": "conference_15min (default) | conference_5min_lightning | lab_meeting_30min | defense_45min | public_outreach",
                },
                "theme": {
                    "type": "string",
                    "description": "'' (default = white) | white | black. Reveal engine swaps the vendored theme CSS; touying engine flips the background/foreground in touying-mini.typ.",
                },
                "speaker_notes_enabled": {
                    "type": "boolean",
                    "description": "Default true. Embed per-slide speaker_notes from the template + slides_spec. Reveal surfaces via the notes plugin ('s' key opens presenter view); touying renders them only in handout mode.",
                },
                "print_handout": {
                    "type": "boolean",
                    "description": "Default true. Also emit synthesis/slides.handout.pdf — a 2-up A4 condensed PDF with speaker notes printed beneath each slide. Requires typst on PATH (reveal engine uses the touying handout path).",
                },
                "audience": {
                    "type": "string",
                    "description": "Back-compat: legacy callers passed audience= alongside template=. Accepted as a meta-hint; the template= argument is authoritative.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Back-compat: legacy kwarg. 'reveal'/'html' maps to engine='reveal'; 'beamer'/'pdf'/'typst'/'touying' maps to engine='touying'.",
                },
            },
        },
    },

    # ── reviewer-response scaffold (4 tools) ───────────────────────────
    "tool_reviewer_simulate": {
        "short": "Build a 7-persona pre-submission reviewer simulation brief against synthesis/paper.md.",
        "description": "Loads N reviewer personas (default: all 7 — methodology_skeptic, domain_expert, statistician, reproducibility_advocate, scope_creep_critic, novelty_critic, presentation_critic) and the paper, then writes workspace/reviewer/simulation_brief.md with each persona's lens + red flags + typical questions + signature phrasings. The AI in the host IDE drives — walks the paper through each persona, writes per-persona comment lists, then calls tool_rebuttal_draft for each substantive comment. Internal companion to guidance/peer_review_response (which handles ACTUAL external reviewer reports).",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "personas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of persona ids to load. Default: all 7 ship and run.",
                },
            },
        },
    },
    "tool_rebuttal_draft": {
        "short": "Scaffold a single rebuttal markdown file under workspace/reviewer/rebuttals/ with auto-discovered evidence inventory.",
        "description": "Given a verbatim reviewer comment + the persona id that raised it (+ optional researcher-supplied evidence_paths), write a rebuttal scaffold to workspace/reviewer/rebuttals/<slug>.md. The scaffold surfaces methods record, per-step findings_vs_literature.md, outputs (figures/tables/reports), and paper sections so the AI can ground the response. Flags any supplied evidence_paths that do not exist on disk.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "comment": {"type": "string", "description": "Verbatim reviewer comment."},
                "persona": {"type": "string", "description": "Persona id that raised the comment (e.g. statistician, novelty_critic)."},
                "evidence_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional workspace-relative paths the rebuttal will cite.",
                },
            },
            "required": ["comment", "persona"],
        },
    },
    "tool_reviewer_response_compile": {
        "short": "Assemble workspace/reviewer/rebuttals/*.md into response_to_reviewers.md (+ PDF via Typst when available).",
        "description": "Concatenates every rebuttal markdown under workspace/reviewer/rebuttals/, grouped by persona, into workspace/reviewer/response_to_reviewers.md. Best-effort PDF compile via the bundled Typst generic_two_column template — returns status='skipped' for the PDF leg when typst is not on PATH; the markdown is always produced. Returns rebuttal_count, personas_addressed, response_md path, response_pdf path (or null).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _log_search(root: Path, tool_name: str, query: str, count: int) -> None:
    log_path = root / "workspace" / "logs" / "searches.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": now_iso(),
                    "tool": tool_name,
                    "query": query,
                    "results_count": count,
                }
            )
            + "\n"
        )


def _read_profile(root: Path) -> dict:
    """Return autonomy_level, expertise_level, model_profile in <100 tokens."""
    cfg = get_config(root)
    if cfg.get("status") != "success":
        return {
            "autonomy_level": "supervised",
            "expertise_level": "intermediate",
            "model_profile": "medium",
        }
    config = cfg.get("config", {})
    return {
        "autonomy_level": config.get("interaction", {}).get(
            "autonomy_level", "supervised"
        ),
        "expertise_level": config.get("researcher", {}).get(
            "expertise_level", "intermediate"
        ),
        "model_profile": config.get("model_profile", "medium"),
    }


def _handle_sys_protocol_list(name, arguments, root):
    try:
        cat = arguments.get("category") if isinstance(arguments, dict) else None
        cat = cat if isinstance(cat, str) and cat else None
        protocols = list_protocols(category=cat)
        return _text(_success({
            "protocols": protocols,
            "count": len(protocols),
            "category": cat,
        }))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_tool_protocols_list(name, arguments, root):
    from research_os.tools.actions.listers import list_protocols_flat

    try:
        cat = arguments.get("category")
        pack = arguments.get("pack")
        include_packs = arguments.get("include_pack_protocols", True)
        if include_packs is None:
            include_packs = True
        protocols = list_protocols_flat(
            category=cat if isinstance(cat, str) and cat else None,
            pack=pack if isinstance(pack, str) and pack else None,
            include_pack_protocols=bool(include_packs),
        )
        return _text(_success({
            "protocols": protocols,
            "count": len(protocols),
            "filters": {
                "category": cat or None,
                "pack": pack or None,
                "include_pack_protocols": bool(include_packs),
            },
        }))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_tool_tools_list(name, arguments, root):
    from research_os.tools.actions.listers import list_tools_flat

    try:
        scope = arguments.get("scope") or "all"
        include_deprecated = bool(arguments.get("include_deprecated", False))
        match = arguments.get("match_substring")
        tools = list_tools_flat(
            TOOL_DEFINITIONS,
            aliases=_ALIASES,
            deprecated_aliases=_DEPRECATED_ALIASES,
            scope=scope,
            include_deprecated=include_deprecated,
            match_substring=match if isinstance(match, str) and match else None,
        )
        return _text(_success({
            "tools": tools,
            "count": len(tools),
            "filters": {
                "scope": scope,
                "include_deprecated": include_deprecated,
                "match_substring": match or None,
            },
        }))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_sys_protocol_get(name, arguments, root):
    p_name = arguments.get("protocol_name")
    fmt = (arguments.get("format") or "full").lower()
    step_id = arguments.get("step_id")
    profile = _read_profile(root)
    model_profile = profile.get("model_profile", "medium")
    try:
        import yaml as _yaml

        data = load_protocol(
            p_name, model_profile=model_profile, format=fmt, step_id=step_id
        )
        if fmt in {"summary", "step"}:
            # Lean structured payload (no yaml dump bulk).
            response = dict(data)
            response.setdefault(
                "_loaded_as", fmt
            )
        else:
            # format=full: AI explicitly opted into the bulk payload —
            # don't tack on another paragraph telling it to prefer
            # summary. Boot reminder also lives in sys_boot now.
            response = {"content": _yaml.dump(data, sort_keys=False)}
            if model_profile == "small":
                response["note"] = "Loaded in light mode (small model profile)."
        return _text(_success(response))
    except Exception as e:
        return _text(_error(str(e)))


# ── Routing handlers ──────────────────────────────────────────────────


def _handle_sys_boot(name, arguments, root):
    from research_os.tools.actions.router import sys_boot

    res = sys_boot(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "sys_boot failed")))


def _handle_tool_route(name, arguments, root):
    from research_os.tools.actions.router import route_request

    res = route_request(
        arguments["prompt"],
        root,
        persist_plan=bool(arguments.get("persist_plan", True)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_route failed")))


def _handle_tool_semantic_route(name, arguments, root):
    from research_os.tools.actions import semantic

    if not semantic.semantic_available():
        return _text(_success({
            "status": "unavailable",
            "reason": (
                "Semantic routing requires the `semantic` extra. "
                "Install with: pip install 'research-os[semantic]' "
                "and confirm protocols/_embeddings.npz is present "
                "(run scripts/build_embeddings.py)."
            ),
            "fastembed_installed": semantic.fastembed_available(),
            "embeddings_on_disk": semantic.embeddings_on_disk(),
        }))
    prompt = arguments["prompt"]
    top_k = int(arguments.get("top_k") or 5)
    matches = semantic.top_k_protocols(prompt, k=top_k)
    payload = semantic.semantic_route(prompt, k=top_k) or {}
    payload["status"] = "success"
    payload["matches"] = [{"id": m.id, "score": round(m.score, 4)} for m in matches]
    return _text(_success(payload))


def _handle_sys_semantic_tool_search(name, arguments, root):
    from research_os.tools.actions import semantic

    if not semantic.semantic_available():
        return _text(_success({
            "status": "unavailable",
            "reason": (
                "Semantic tool search requires the `semantic` extra. "
                "Install with: pip install 'research-os[semantic]'."
            ),
            "fastembed_installed": semantic.fastembed_available(),
            "embeddings_on_disk": semantic.embeddings_on_disk(),
        }))
    query = arguments["query"]
    top_k = int(arguments.get("top_k") or 5)
    matches = semantic.top_k_tools(query, k=top_k)
    return _text(_success({
        "status": "success",
        "query": query,
        "matches": [{"name": m.id, "score": round(m.score, 4)} for m in matches],
    }))


def _handle_tool_plan_advance(name, arguments, root):
    from research_os.project_ops import log_override
    from research_os.tools.actions.router import advance_plan

    override = bool(arguments.get("override_gate", False))
    res = advance_plan(root, override_gate=override)
    # Log the override ONLY when the gate would have blocked — a bypass
    # passed on a deliverable that already met the gate is a phantom
    # entry the pre-submission audit shouldn't have to defend.
    if override and res.get("bypassed_blockers"):
        log_override(
            root,
            tool="tool_plan_advance",
            gate="deliverable_completeness",
            rationale=arguments.get("override_rationale"),
            extra={"blocker_count": len(res["bypassed_blockers"])},
        )
    # status='blocked' is informational, not a transport-level error.
    if res.get("status") in {"success", "blocked"}:
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_plan_advance failed")))


def _handle_tool_plan_turn(name, arguments, root):
    from research_os.tools.actions.router import plan_turn

    res = plan_turn(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_plan_turn failed")))


def _handle_tool_plan_clear(name, arguments, root):
    from research_os.tools.actions.router import clear_active_plan

    res = clear_active_plan(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_plan_clear failed")))


def _handle_sys_active_tools(name, arguments, root):
    from research_os.tools.actions.router import active_tools_for_protocol

    p_name = arguments.get("protocol_name")
    if not p_name:
        return _text(_error("protocol_name is required"))
    res = active_tools_for_protocol(p_name)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "sys_active_tools failed")))


def _handle_tool_cache_clear(name, arguments, root):
    from research_os.tools.actions.search import cache_clear

    res = cache_clear(
        root,
        source=arguments.get("source"),
        older_than_days=arguments.get("older_than_days"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_cache_clear failed")))


def _handle_tool_step_env_lock(name, arguments, root):
    from research_os.tools.actions.exec import step_env_lock

    res = step_env_lock(
        root,
        step_id=arguments.get("step_id"),
        write_conda_yaml=bool(arguments.get("write_conda_yaml", False)),
        write_dockerfile=bool(arguments.get("write_dockerfile", False)),
        write_apptainer=bool(arguments.get("write_apptainer", False)),
        write_entrypoint=bool(arguments.get("write_entrypoint", True)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_step_env_lock failed")))


def _handle_tool_workflow_dag(name, arguments, root):
    from research_os.tools.actions.state import workflow_dag

    res = workflow_dag(
        root,
        render_png=bool(arguments.get("render_png", False)),
        output_dir=arguments.get("output_dir", "docs"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "tool_workflow_dag failed")))


def _handle_sys_tool_describe(name, arguments, root):
    tool_name = arguments.get("tool_name")
    if not tool_name:
        return _text(_error("tool_name is required"))
    canonical = _resolve_tool_name(tool_name)
    schema = TOOL_DEFINITIONS.get(canonical)
    if not schema:
        return _text(
            _error(
                f"Unknown tool '{tool_name}'. Try sys_protocol_list to browse, "
                "or tool_route to find by prompt."
            )
        )
    return _text(
        _success(
            {
                "name": canonical,
                "category": schema.get("category", ""),
                "short": schema.get("short", ""),
                "description": schema.get("description", ""),
                "inputSchema": schema.get("inputSchema", {}),
            }
        )
    )


def _handle_sys_protocol_validate(name, arguments, root):
    res = validate_protocol(arguments.get("protocol_name"), root)
    if "error" in res:
        return _text(_error(res["error"]))
    return _text(_success(res))


def _handle_sys_protocol_next(name, arguments, root):
    return _text(_success(get_next_protocol(root)))


def _handle_sys_protocol_log(name, arguments, root):
    from research_os.tools.actions.protocol import log_protocol_execution

    res = log_protocol_execution(
        root,
        arguments["protocol_name"],
        arguments["status"],
        arguments.get("details", ""),
    )
    return _text(_success(res))


def _handle_sys_protocol_history(name, arguments, root):
    from research_os.tools.actions.protocol import get_protocol_history

    res = get_protocol_history(root, arguments.get("limit", 20))
    return _text(_success(res))


def _handle_sys_workspace_scaffold(name, arguments, root):
    ide = arguments.get("ide", "all")
    valid = [
        "cursor", "claude", "antigravity", "opencode", "vscode",
        "windsurf", "continue", "aider",
    ]
    ide_flags = (
        valid
        if ide == "all"
        else [i.strip() for i in ide.split(",") if i.strip() in valid]
    )
    scaffold_minimal_workspace(
        root,
        arguments.get("project_name", "Research Project"),
        ide_flags=ide_flags,
        copy_agents=True,
    )
    if (root / ".os_state").exists() and (root / "workspace").exists():
        _profile_inputs(root)
    return _text(_success({"scaffolded": True, "ide_flags": ide_flags}))


def _handle_sys_workspace_tree(name, arguments, root):
    depth = arguments.get("depth", 3)
    include_files = arguments.get("include_files", True)
    tree = _build_tree(root / "workspace", depth, include_files)
    return _text(_success({"tree": tree}))


def _build_tree(path: Path, depth: int, include_files: bool) -> dict:
    if depth == 0:
        return {"_truncated": True}
    result: dict = {}
    try:
        for item in sorted(path.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                result[f"{item.name}/"] = _build_tree(item, depth - 1, include_files)
            elif include_files:
                result[item.name] = item.stat().st_size
    except (PermissionError, FileNotFoundError):
        pass
    return result


def _handle_sys_state_get(name, arguments, root):
    fmt = (arguments.get("format") or "full").lower()
    state = load_state(root)
    if fmt == "minimal":
        from research_os.state.state_ledger import ResearchLedger

        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
        return _text(_success({"minimal_context": ledger.get_project_summary(max_tokens=450)}))
    if fmt == "markdown":
        md_path = root / ".os_state" / "os_state.md"
        if not md_path.exists():
            return _text(_error("os_state.md missing — run a tool that mutates state first."))
        return _text(_success({"markdown": md_path.read_text()}))
    # full (lean projection — strip very large fields)
    paths = state.get("paths", {})
    out: dict[str, Any] = {
        "project_name": state.get("project_name") or state.get("project", ""),
        "pipeline_stage": state.get("pipeline_stage", state.get("phase", "init")),
        "step": state.get("step", 0),
        "current_path": state.get("current_path", "main"),
    }
    # Only include collection-valued fields when they have content —
    # empty list/dict/None on a fresh project just burns tokens.
    paths_summary = {k: v.get("status") for k, v in paths.items()}
    if paths_summary:
        out["paths_summary"] = paths_summary
    hypotheses = state.get("active_hypotheses") or []
    if hypotheses:
        out["active_hypotheses"] = hypotheses
    if state.get("resumable_from"):
        out["resumable_from"] = state["resumable_from"]
    return _text(_success(out))


def _handle_sys_file_read(name, arguments, root):
    p = root / arguments["filepath"]
    if not p.exists() or not p.is_file():
        return _text(_error(f"File not found: {arguments['filepath']}"))
    if p.stat().st_size > 50 * 1024 * 1024:
        return _text(_error("File too large (>50 MB). Use tool_data_sample for tabular data."))
    return _text(_success({"content": p.read_text(errors="replace")}))


def _handle_sys_file_write(name, arguments, root):
    p = root / arguments["filepath"]
    force = arguments.get("force", False)
    rel = str(p.relative_to(root)) if str(p).startswith(str(root)) else str(p)

    if rel.startswith("inputs/raw_data") or rel.startswith("inputs/literature"):
        if not rel.endswith("literature_index.yaml"):
            return _text(_error("WriteProtectedError: inputs/raw_data and inputs/literature are immutable."))
    if rel.startswith("synthesis/") and p.exists() and not force:
        return _text(_error("synthesis/ files exist — pass force=true to overwrite."))

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(arguments["content"])
    if rel.startswith("workspace/"):
        _update_manifest(root)
    return _text(_success({"written": True, "checksum": compute_file_hash(p)}))


def _handle_sys_file_list(name, arguments, root):
    from research_os.project_ops import LAZY_DIRS

    rel = arguments["directory"]
    p = root / rel
    if not p.exists() or not p.is_dir():
        # A lazy directory that hasn't been materialised yet is NOT an
        # error — it just hasn't received its first artefact. Return an
        # empty list with a hint so protocols can detect the empty state
        # without retry loops.
        if rel.strip("/") in LAZY_DIRS:
            return _text(_success({
                "files": [],
                "empty": True,
                "lazy_dir": True,
                "hint": (
                    f"`{rel}` is created on first write. "
                    "Drop files here (or via the wizard) to materialise it."
                ),
            }))
        return _text(_error("Directory not found"))
    files = [str(f.relative_to(root)) for f in p.rglob("*") if f.is_file()]
    return _text(_success({"files": files, "empty": not files}))


def _handle_sys_file_delete(name, arguments, root):
    p = root / arguments["filepath"]
    if not p.exists():
        return _text(_error("File or directory not found"))
    if p.is_file():
        p.unlink()
        return _text(_success({"deleted": True}))
    try:
        p.rmdir()
        return _text(_success({"deleted": True, "type": "directory"}))
    except OSError as e:
        return _text(_error(f"Cannot delete directory: {e}"))


def _handle_sys_file_validate_md(name, arguments, root):
    from research_os.tools.actions.audit.md_audit import validate_md_template

    res = validate_md_template(arguments["filepath"], arguments["protocol_name"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "Validation failed")))


def _handle_sys_path_create(name, arguments, root):
    from research_os.project_ops import create_numbered_experiment

    try:
        # The MCP handler defaults to enforcing
        # previous-step finalization. Researcher can opt out by passing
        # `allow_unfinalized_predecessor=true` (logged to override_log).
        allow_bypass = bool(arguments.get("allow_unfinalized_predecessor", False))
        res = create_numbered_experiment(
            root,
            arguments["name"],
            hypothesis=arguments.get("hypothesis", ""),
            branch_of=arguments.get("branch_of"),
            from_step=arguments.get("from_step"),
            enforce_predecessor_finalized=not allow_bypass,
        )
        if allow_bypass:
            from research_os.project_ops import log_override
            log_override(
                root,
                tool="sys_path_create",
                gate="enforce_predecessor_finalized",
                rationale=arguments.get("override_rationale"),
                extra={"new_step": res.get("path_id")},
            )
        return _text(_success(res))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_sys_path_abandon(name, arguments, root):
    res = abandon_path(arguments["path_name"], arguments["rationale"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "abandon failed")))


def _handle_sys_path_list(name, arguments, root):
    return _text(_success(list_paths(root)))


def _handle_tool_path_finalize(name, arguments, root):
    from research_os.tools.actions.audit.step_literature import (
        audit_step_literature,
    )
    from research_os.tools.actions.state.path import finalize_path

    # First-gate
    # literature-loop check. Closes the gap where
    # literature_per_step was documented as pipeline-mandatory but
    # never enforced (autopilot skipped it). Override via
    # override_literature_gate=true + override_rationale.
    override_lit = bool(arguments.get("override_literature_gate", False))
    override_rationale = str(arguments.get("override_rationale", "")).strip()
    path_name = arguments.get("path_name")
    step_id = path_name if (path_name and path_name != "main") else None
    try:
        lit_audit = audit_step_literature(root, step_id=step_id)
    except Exception as e:
        lit_audit = {"status": "error", "message": str(e), "blockers": []}
    if (
        lit_audit.get("status") == "error"
        and lit_audit.get("blockers")
        and not (override_lit and override_rationale)
    ):
        msg = (
            f"tool_path_finalize blocked by tool_audit_step_literature "
            f"({len(lit_audit['blockers'])} blocker(s)). "
            "Either run research/literature_per_step OR pass "
            "override_literature_gate=true + override_rationale=... to "
            "proceed. See workspace/logs/step_literature_audit.md."
        )
        return _text(_error({
            "message": msg,
            "literature_audit": lit_audit,
        }))

    res = finalize_path(arguments.get("path_name"), root)
    if isinstance(res, dict):
        res.setdefault("literature_audit", lit_audit)
        if override_lit and override_rationale:
            res["literature_override"] = {
                "override_literature_gate": True,
                "override_rationale": override_rationale,
            }
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "finalize failed")))


def _handle_tool_synthesis_curate_figures(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard import curate_figures

    res = curate_figures(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "curate failed")))


def _handle_sys_export_share_archive(name, arguments, root):
    """Run scripts/export_share_archive.py for the project root."""
    import subprocess as _sp
    import sys as _sys

    script = root / "scripts" / "export_share_archive.py"
    if not script.exists():
        # Lazy-scaffold the script if the project pre-dates the feature.
        try:
            from research_os.project_ops import _write_sharing_scripts, load_state
            project_name = (load_state(root) or {}).get("project_name") or root.name
            _write_sharing_scripts(root, project_name)
        except Exception as e:
            return _text(_error(f"export script missing and could not be scaffolded: {e}"))

    cmd = [_sys.executable, str(script)]
    if arguments.get("out"):
        cmd += ["--out", str(arguments["out"])]
    if arguments.get("include_raw_data"):
        cmd += ["--include-raw-data"]
    try:
        res = _sp.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(root))
        if res.returncode != 0:
            return _text(_error(
                f"export failed (rc={res.returncode}):\n"
                f"stdout:\n{res.stdout[-1000:]}\n"
                f"stderr:\n{res.stderr[-1000:]}"
            ))
        return _text(_success({"status": "success", "stdout": res.stdout.strip()}))
    except _sp.TimeoutExpired:
        return _text(_error("export timed out (>180s)"))
    except Exception as e:
        return _text(_error(f"export failed: {e}"))


def _handle_sys_checkpoint_create(name, arguments, root):
    res = create_checkpoint(arguments.get("description", "manual"), root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "checkpoint failed")))


def _handle_sys_checkpoint_rollback(name, arguments, root):
    res = rollback_checkpoint(arguments["checkpoint_id"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "rollback failed")))


def _handle_sys_checkpoint_list(name, arguments, root):
    res = list_checkpoints(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "checkpoint list failed")))


def _handle_sys_config_get(name, arguments, root):
    res = get_config(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "config not found")))


def _handle_sys_config_set(name, arguments, root):
    res = set_config(arguments["key"], arguments["value"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "set failed")))


def _handle_sys_config_validate(name, arguments, root):
    res = validate_config(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "validate failed")))


def _handle_sys_notify(name, arguments, root):
    res = notify_researcher(arguments["message"], arguments["level"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "notify failed")))


def _handle_sys_session_handoff(name, arguments, root):
    res = session_handoff(root)
    if res.get("status") == "success":
        return _text(res["content"])
    return _text(_error(res.get("message", "handoff failed")))


def _handle_sys_env_snapshot(name, arguments, root):
    step_id = arguments.get("step_id") if arguments else None
    scope = arguments.get("scope") if arguments else None
    res = env_snapshot(root, step_id=step_id, scope=scope)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "snapshot failed")))


def _handle_sys_env_docker_generate(name, arguments, root):
    res = env_docker_generate(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "docker generate failed")))


def _handle_mem_analysis_log(name, arguments, root):
    log_path = root / "workspace" / "analysis.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{now_iso()}] {arguments['entry']}\n")
    _update_workflow_mermaid(root)
    return _text(_success({"logged": True, "path": "workspace/analysis.md"}))


def _handle_mem_methods_append(name, arguments, root):
    m_path = root / "workspace" / "methods.md"
    m_path.parent.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    method = arguments["method"]
    if len(arguments) == 1:
        line = f"- {method}\n"
    else:
        step_name = arguments.get("step_name", "Step")
        step_number = arguments.get("step_number", "")
        heading = f"{step_number} — {step_name}" if step_number else step_name
        lines = [f"\n## {ts} — {heading}"]
        lines.append(f"  - **Method**: {method}")
        if arguments.get("dataset_name"):
            h = arguments.get("dataset_hash", "N/A")
            lines.append(f"  - **Dataset**: {arguments['dataset_name']} (sha256: {h})")
        if arguments.get("implementation"):
            lines.append(f"  - **Implementation**: {arguments['implementation']}")
        if arguments.get("parameters"):
            lines.append(f"  - **Parameters**: {arguments['parameters']}")
        if arguments.get("justification"):
            lines.append(f"  - **Justification**: {arguments['justification']}")
        if arguments.get("assumptions"):
            for a in arguments["assumptions"]:
                lines.append(f"  - **Assumption checked**: {a}")
        line = "\n".join(lines) + "\n"
    with open(m_path, "a") as f:
        f.write(line)
    return _text(_success({"logged": True, "path": "workspace/methods.md"}))


def _handle_mem_citations_generate(name, arguments, root):
    from research_os.project_ops import generate_citations_md

    return _text(_success({"citations_path": generate_citations_md(root)}))


def _handle_mem_intake_regenerate(name, arguments, root):
    from research_os.project_ops import regenerate_intake

    return _text(_success({"intake_path": regenerate_intake(root)}))


def _handle_mem_decision_log(name, arguments, root):
    res = log_decision(
        arguments["context"],
        arguments["selected"],
        arguments["rationale"],
        root=root,
    )
    return _text(_success(res))


def _handle_tool_search(name, arguments, root):
    """Unified search dispatcher (this-release consolidation of 5 search tools).

    Selects provider by:
      1. Explicit `source` arg (one of: semantic_scholar | pubmed | crossref |
         arxiv | web | auto).
      2. Legacy: if invoked under one of the deprecated per-provider names
         (tool_search_<provider>), pick that provider for back-compat.
      3. Default 'auto' — picks providers based on a quick keyword heuristic.
    """
    q = arguments["query"]
    limit = arguments.get("limit", 5)

    provider_fn = {
        "semantic_scholar": search_semantic_scholar,
        "pubmed": search_pubmed,
        "crossref": search_crossref,
        "arxiv": search_arxiv,
        "web": search_web,
    }
    legacy_map = {
        "tool_search_semantic_scholar": "semantic_scholar",
        "tool_search_pubmed": "pubmed",
        "tool_search_crossref": "crossref",
        "tool_search_arxiv": "arxiv",
        "tool_search_web": "web",
    }

    source = arguments.get("source")
    if not source:
        source = legacy_map.get(name, "auto")

    if source == "auto":
        ql = q.lower()
        if any(t in ql for t in ("rna", "gene", "snrna", "scrna", "protein",
                                 "clinical", "disease", "neuron", "patient",
                                 "tumor", "biomarker")):
            picks = ["semantic_scholar", "pubmed"]
        elif any(t in ql for t in ("transformer", "neural", "embedding",
                                   "diffusion", "llm")):
            picks = ["semantic_scholar", "arxiv"]
        elif any(t in ql for t in ("psychometric", "survey", "qualitative",
                                   "behavioral")):
            picks = ["crossref", "semantic_scholar"]
        elif any(t in ql for t in ("climate", "geology", "ocean", "atmosphere")):
            picks = ["crossref", "arxiv"]
        else:
            picks = ["web"]
        merged: list = []
        per_source = max(1, limit // len(picks))
        for src in picks:
            try:
                _log_search(root, f"tool_search:{src}", q, 0)
                sub = provider_fn[src](q, per_source) or []
                if isinstance(sub, list):
                    for item in sub:
                        if isinstance(item, dict):
                            item.setdefault("_source", src)
                    merged.extend(sub)
                elif isinstance(sub, dict):
                    sub.setdefault("_source", src)
                    merged.append(sub)
            except Exception as e:
                merged.append({"_source": src, "_error": str(e)})
        return _text(_success({"results": merged[:limit], "sources": picks,
                               "mode": "auto"}))

    if source not in provider_fn:
        return _text(_error(
            f"Unknown search source '{source}'. Valid: "
            f"{sorted(provider_fn)} | auto"
        ))
    fn = provider_fn[source]
    _log_search(root, f"tool_search:{source}", q, 0)
    res = fn(q, limit)
    return _text(_success(res))


def _handle_tool_web_scrape(name, arguments, root):
    return _text(_success(scrape_web(arguments["url"])))


def _handle_tool_literature_download(name, arguments, root):
    res = download_literature(
        arguments["url"],
        arguments["filename"],
        root,
        step_id=arguments.get("step_id"),
        metadata=arguments.get("metadata"),
        skip_unpaywall=bool(arguments.get("skip_unpaywall", False)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "download failed")))


def _handle_tool_literature_search_and_save(name, arguments, root):
    from research_os.tools.actions.search.literature import search_and_save

    res = search_and_save(
        arguments["query"],
        root,
        source=arguments.get("source", "semantic_scholar"),
        step_id=arguments.get("step_id"),
        limit=int(arguments.get("limit", 5)),
        download_top=int(arguments.get("download_top", 3)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "search_and_save failed")))


def _handle_tool_step_literature_list(name, arguments, root):
    from research_os.tools.actions.search.literature import step_literature_list

    res = step_literature_list(root, step_id=arguments.get("step_id"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "step_literature_list failed")))


def _handle_tool_python_exec(name, arguments, root):
    p = root / arguments["script_path"]
    if not p.exists() or not p.is_file():
        return _text(_error("Script not found"))

    step_name = p.stem
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    exec_log_path = log_dir / f"{step_name}_exec.log"

    cmd = [sys.executable, str(p)]
    timeout = int(arguments.get("timeout", 600))
    try:
        res = subprocess.run(
            cmd,
            cwd=str(p.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _text(_error(f"Script timed out after {timeout}s"))

    with open(exec_log_path, "a") as f:
        f.write(
            f"--- Executed at {now_iso()} ---\n"
            f"Command: {' '.join(cmd)}\n"
            f"Return Code: {res.returncode}\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\n\n"
        )

    return _text(
        _success({"stdout": res.stdout, "stderr": res.stderr, "code": res.returncode})
    )


def _handle_tool_script_exec(name, arguments, root):
    from research_os.tools.actions.exec.scripts import (
        execute_bash_script,
        execute_julia_script,
        execute_r_script,
    )

    timeout = arguments.get("timeout", 600)
    script_path = arguments["script_path"]
    fn = {
        "tool_r_exec": execute_r_script,
        "tool_julia_exec": execute_julia_script,
        "tool_bash_exec": execute_bash_script,
    }[name]
    res = fn(script_path, root, timeout)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "execution failed")))
    return _text(_success(res))


def _handle_tool_package_install(name, arguments, root):
    packages = arguments["packages"]
    res = package_install(packages)
    if res.get("status") == "success":
        req_path = root / "environment" / "requirements.txt"
        req_path.parent.mkdir(parents=True, exist_ok=True)
        existing = req_path.read_text().splitlines() if req_path.exists() else []
        with open(req_path, "a") as f:
            for pkg in packages:
                if pkg not in existing:
                    f.write(f"{pkg}\n")
    return _text(_success(res))


def _handle_tool_data_sample(name, arguments, root):
    from research_os.tools.actions.data import data_sample

    res = data_sample(
        arguments["filepath"],
        int(arguments.get("n_rows", 20)),
        arguments.get("strategy", "head"),
        root,
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", res.get("error", "sample failed"))))


def _handle_tool_data_profile(name, arguments, root):
    from research_os.tools.actions.data import data_profile

    res = data_profile(arguments["filepath"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", res.get("error", "profile failed"))))


def _handle_tool_data_convert(name, arguments, root):
    from research_os.tools.actions.data import data_convert

    res = data_convert(arguments["filepath"], arguments["output_format"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", res.get("error", "convert failed"))))


# ── tool_audit dispatcher ───────────────────────────────────────────
#
# The audit family collapses per-dimension audit tools into a single
# tool_audit(scope=, dimension=) entry point. Legacy per-dimension names
# continue to dispatch via _ALIASES + _ALIAS_PARAM_INJECTION (which set
# scope+dimension from the legacy name). The dispatcher reads scope+
# dimension off ``arguments`` and forwards to the matching private
# per-dimension handler — no audit logic is rewritten here; this is
# purely a surface unification.
_AUDIT_DISPATCH: dict[tuple[str, str], str] = {
    # scope=step
    ("step", "assumptions"):            "_handle_tool_audit_assumptions",
    ("step", "code_quality"):           "_handle_tool_audit_code_quality",
    ("step", "completeness"):           "_handle_tool_audit_step_completeness",
    ("step", "evalue"):                 "_handle_tool_audit_evalue",
    ("step", "figure"):                 "_handle_tool_audit_figure",
    ("step", "figure_full"):            "_handle_tool_audit_figure_full",
    ("step", "figure_interactivity"):   "_handle_tool_audit_figure_interactivity",
    ("step", "literature"):             "_handle_tool_audit_step_literature",
    ("step", "power"):                  "_handle_tool_audit_power",
    ("step", "reproducibility"):        "_handle_tool_audit_reproducibility",
    # scope=project
    ("project", "citations"):           "_handle_tool_audit_citations",
    ("project", "claims"):              "_handle_tool_audit_claims",
    ("project", "cliches"):             "_handle_tool_audit_cliches",
    ("project", "coherence"):           "_handle_tool_audit_coherence",
    ("project", "cross_deliverable"):   "_handle_tool_audit_cross_deliverable_consistency",
    ("project", "prose"):               "_handle_tool_audit_prose",
    ("project", "version_coherence"):   "_handle_tool_audit_version_coherence",
    # scope=synthesis
    ("synthesis", "all"):               "_handle_tool_audit_synthesis",
    ("synthesis", "dashboard_content"): "_handle_tool_audit_dashboard_content",
    ("synthesis", "figure_coverage"):   "_handle_tool_audit_figure_coverage",
    ("synthesis", "reviewer_responses"): "_handle_tool_audit_reviewer_responses",
}


def _handle_tool_audit(name, arguments, root):
    """Unified audit dispatcher.

    Routes (scope, dimension) → the matching per-dimension handler.
    Every legacy ``tool_audit_*`` name is aliased to this entry point and
    has its scope+dimension injected via ``_ALIAS_PARAM_INJECTION``, so
    callers (researchers, scripts, protocols) using the older per-
    dimension names keep working unchanged.
    """
    scope = arguments.get("scope")
    dimension = arguments.get("dimension")
    if not scope or not dimension:
        return _text(_error(
            "tool_audit requires scope= and dimension=. "
            "Valid scopes: step | project | synthesis. "
            "See docs/V2_MIGRATION_TABLE.md for the full dimension list."
        ))
    handler_name = _AUDIT_DISPATCH.get((scope, dimension))
    if not handler_name:
        return _text(_error(
            f"tool_audit: unknown (scope='{scope}', dimension='{dimension}'). "
            "See docs/V2_MIGRATION_TABLE.md for valid combinations."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_audit: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


def _handle_tool_audit_findings(name, arguments, root):
    """Unified findings-ledger dispatcher (query | diff).

    Replaces the two per-operation tools (tool_audit_findings_query +
    tool_audit_findings_diff). Operation defaults to 'query' when the
    diff-specific timestamps are absent and the caller did not specify
    operation explicitly.
    """
    op = arguments.get("operation")
    if not op:
        # Infer: diff if both timestamps are present, else query.
        if arguments.get("timestamp_a") and arguments.get("timestamp_b"):
            op = "diff"
        else:
            op = "query"
    if op == "query":
        return _handle_tool_audit_findings_query(name, arguments, root)
    if op == "diff":
        return _handle_tool_audit_findings_diff(name, arguments, root)
    return _text(_error(
        f"tool_audit_findings: unknown operation '{op}'. "
        "Use operation='query' or operation='diff'."
    ))


# ── tool_dashboard dispatcher ───────────────────────────────────────
#
# The dashboard family collapses seven per-operation tools into a single
# tool_dashboard(operation=...) entry point. Legacy per-operation names
# (tool_dashboard_create / story_generate / story_edit /
# story_quality_bar / reviewer_sim / test_generate / test_run) continue
# to dispatch via _ALIASES + _ALIAS_PARAM_INJECTION (which inject
# operation= from the legacy name). The dispatcher reads operation off
# arguments and forwards to the matching private per-operation handler
# — no dashboard logic is rewritten here; this is purely a surface
# unification mirroring tool_audit.
_DASHBOARD_DISPATCH: dict[str, str] = {
    "create":            "_handle_tool_dashboard_create",
    "story_generate":    "_handle_tool_dashboard_story_generate",
    "story_edit":        "_handle_tool_dashboard_story_edit",
    "story_quality_bar": "_handle_tool_dashboard_story_quality_bar",
    "reviewer_sim":      "_handle_tool_dashboard_reviewer_sim",
    "test_generate":     "_handle_tool_dashboard_test_generate",
    "test_run":          "_handle_tool_dashboard_test_run",
}


def _handle_tool_dashboard(name, arguments, root):
    """Unified dashboard dispatcher.

    Routes operation → the matching per-operation handler. Every legacy
    ``tool_dashboard_*`` name is aliased to this entry point and has its
    operation injected via ``_ALIAS_PARAM_INJECTION`` so callers
    (researchers, scripts, protocols) using the older per-operation
    names keep working unchanged. operation defaults to 'create' when
    omitted — the historically dominant call site.
    """
    op = arguments.get("operation") or "create"
    handler_name = _DASHBOARD_DISPATCH.get(op)
    if not handler_name:
        valid = ", ".join(sorted(_DASHBOARD_DISPATCH))
        return _text(_error(
            f"tool_dashboard: unknown operation '{op}'. "
            f"Valid operations: {valid}."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_dashboard: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


# ── tool_step + tool_step_pipeline dispatchers ──────────────────────
#
# The step family collapses four step-lifecycle tools into a single
# tool_step(operation=...) entry point, and four pipeline tools into a
# single tool_step_pipeline(operation=...) entry point. Legacy per-
# operation names (tool_step_iterate / iterations_list / revision_options
# / env_lock and tool_step_pipeline_{define,run,status,diagram})
# continue to dispatch via _ALIASES + _ALIAS_PARAM_INJECTION (which
# inject operation= from the legacy name). The dispatchers read
# operation off arguments and forward to the matching private per-
# operation handler — no step logic is rewritten here; this is purely
# a surface unification mirroring tool_dashboard. tool_step_complete
# stays standalone as the top-level end-of-step bundle (distinct from
# the per-operation sub-tools collapsed here).
_STEP_DISPATCH: dict[str, str] = {
    "iterate":           "_handle_tool_step_iterate",
    "iterations_list":   "_handle_tool_step_iterations_list",
    "revision_options":  "_handle_tool_step_revision_options",
    "env_lock":          "_handle_tool_step_env_lock",
}


def _handle_tool_step(name, arguments, root):
    """Unified step-lifecycle dispatcher.

    Routes operation → the matching per-operation handler. Every legacy
    ``tool_step_*`` name (except ``tool_step_complete`` and the pipeline
    family) is aliased to this entry point and has its operation
    injected via ``_ALIAS_PARAM_INJECTION`` so callers (researchers,
    scripts, protocols) using the older per-operation names keep working
    unchanged.
    """
    op = arguments.get("operation")
    if not op:
        valid = ", ".join(sorted(_STEP_DISPATCH))
        return _text(_error(
            f"tool_step requires operation=. Valid operations: {valid}."
        ))
    handler_name = _STEP_DISPATCH.get(op)
    if not handler_name:
        valid = ", ".join(sorted(_STEP_DISPATCH))
        return _text(_error(
            f"tool_step: unknown operation '{op}'. "
            f"Valid operations: {valid}."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_step: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


_STEP_PIPELINE_DISPATCH: dict[str, str] = {
    "define":  "_handle_tool_step_pipeline_define",
    "run":     "_handle_tool_step_pipeline_run",
    "status":  "_handle_tool_step_pipeline_status",
    "diagram": "_handle_tool_step_pipeline_diagram",
}


def _handle_tool_step_pipeline(name, arguments, root):
    """Unified step-pipeline dispatcher.

    Routes operation → the matching per-operation handler. Every legacy
    ``tool_step_pipeline_*`` name is aliased to this entry point and has
    its operation injected via ``_ALIAS_PARAM_INJECTION`` so callers
    using the older per-operation names keep working unchanged.
    """
    op = arguments.get("operation")
    if not op:
        valid = ", ".join(sorted(_STEP_PIPELINE_DISPATCH))
        return _text(_error(
            f"tool_step_pipeline requires operation=. "
            f"Valid operations: {valid}."
        ))
    handler_name = _STEP_PIPELINE_DISPATCH.get(op)
    if not handler_name:
        valid = ", ".join(sorted(_STEP_PIPELINE_DISPATCH))
        return _text(_error(
            f"tool_step_pipeline: unknown operation '{op}'. "
            f"Valid operations: {valid}."
        ))
    handler = globals().get(handler_name)
    if not callable(handler):
        return _text(_error(
            f"tool_step_pipeline: handler '{handler_name}' is not callable."
        ))
    return handler(name, arguments, root)


def _handle_tool_audit_synthesis(name, arguments, root):
    from research_os.tools.actions.audit import audit_synthesis
    from research_os.project_ops import log_override

    res = audit_synthesis(
        arguments["paper_path"],
        root,
        override_no_pdfs=bool(arguments.get("override_no_pdfs", False)),
        override_rationale=str(arguments.get("override_rationale", "")),
    )
    # Mirror the other six override gates in this file: when the bypass
    # is actually honoured by audit_synthesis (reflected in the result
    # via report["override_no_pdfs"]=True), append it to override_log.md
    # so pre_submission_checklist can surface the bypass.
    if res.get("override_no_pdfs"):
        try:
            log_override(
                root,
                tool="tool_audit_synthesis",
                gate="audit_synthesis_no_pdfs",
                rationale=str(arguments.get("override_rationale", "")),
            )
        except Exception as exc:  # pragma: no cover - logging best effort
            logger.debug("log_override(audit_synthesis_no_pdfs) failed: %s", exc)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_power(name, arguments, root):
    from research_os.tools.actions.audit import audit_power

    res = audit_power(
        arguments["filepath"],
        arguments.get("effect_size", 0.5),
        arguments["alpha"],
        arguments["n"],
        root,
    )
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_assumptions(name, arguments, root):
    from research_os.tools.actions.audit import audit_assumptions

    res = audit_assumptions(arguments["filepath"], root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_figure(name, arguments, root):
    from research_os.tools.actions.audit import audit_figure

    res = audit_figure(arguments["filepath"], root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_citations(name, arguments, root):
    from research_os.tools.actions.audit import audit_citations

    res = audit_citations(root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_audit_reproducibility(name, arguments, root):
    from research_os.tools.actions.audit import audit_reproducibility_full

    res = audit_reproducibility_full(root)
    if res.get("status") != "error":
        return _text(_success(res))
    return _text(_error(res.get("message", "audit failed")))


def _handle_tool_synthesize_plan(name, arguments, root):
    from research_os.tools.actions.synthesis.synthesize import synthesize_plan

    return _text(_success(synthesize_plan(root)))


def _handle_tool_synthesize(name, arguments, root):
    from research_os.tools.actions.audit.audit import (
        audit_quality_full, audit_step_completeness,
    )
    from research_os.tools.actions.audit.findings_query import (
        unresolved_block_findings,
    )
    from research_os.tools.actions.synthesis.synthesize import synthesize_workspace
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    # Server-enforced quality gate. Single-section synthesis (e.g. just
    # the abstract) clears with a lightweight check; full-document
    # synthesis must pass the master quality auditor.
    #
    # We log override_completeness_gate=true to override_log.md ONLY
    # when the gate it would have run actually returned blockers — a
    # bypass that didn't bypass anything (gate would have passed, or
    # didn't apply to the section call) is a phantom entry that
    # confuses the pre-submission audit.
    override_requested = bool(arguments.get("override_completeness_gate", False))
    rationale = arguments.get("override_rationale")
    full_doc = not arguments.get("section")
    bypass_logged = False
    policy = get_interaction_policy(root)["quality_gate_policy"]

    # Phase-4c gate: if any unresolved BLOCK finding sits in the
    # cross-audit ledger (workspace/logs/.audit_findings.jsonl), refuse
    # to compile. The latest-snapshot semantics mean a BLOCK finding
    # emitted on an earlier audit run but absent from the most recent
    # rerun is treated as resolved — only currently-active BLOCKs
    # stop synthesis. Override path: pass
    # override_unresolved_blocks=true with a rationale; the override is
    # recorded to workspace/logs/override_log.md so the pre-submission
    # audit can flag it.
    override_unresolved_blocks = bool(
        arguments.get("override_unresolved_blocks", False)
    )
    try:
        active_blocks = unresolved_block_findings(Path(root))
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.debug("unresolved_block_findings scan failed: %s", exc)
        active_blocks = []
    if active_blocks and not override_unresolved_blocks and not (
        policy == "warn_only"
    ):
        if (
            policy == "enforce"
            and override_requested
            and (not rationale or not str(rationale).strip())
        ):
            # Fall through to the existing enforce check below — it
            # rejects with the same shape and we don't want two errors
            # racing for the response slot.
            pass
        else:
            top = active_blocks[:10]
            lines = [
                f"- [{b.get('dimension','?')}] "
                f"{b.get('audit_name','?')}: "
                f"{(b.get('suggested_fix') or '').strip()[:160]}"
                for b in top
            ]
            extra = (
                f"\n  … and {len(active_blocks) - 10} more"
                if len(active_blocks) > 10
                else ""
            )
            return _text(_error(
                "BLOCKED by unresolved audit findings ledger "
                f"({len(active_blocks)} BLOCK finding(s) in "
                "workspace/logs/.audit_findings.jsonl). Resolve them "
                "(re-run the originating audit so the latest snapshot "
                "no longer surfaces them) before tool_synthesize.\n\n"
                + "\n".join(lines)
                + extra
                + "\n\nTo bypass for a partial / WIP deliverable, call "
                "again with override_unresolved_blocks=true AND "
                "override_rationale='<one-line why>'."
            ))
    elif active_blocks and override_unresolved_blocks:
        # Record the bypass before we run anything else so the override
        # trail captures it even if synthesis fails later.
        log_override(
            Path(root),
            tool="tool_synthesize",
            gate="unresolved_block_findings",
            rationale=rationale,
            extra={
                "blocker_count": len(active_blocks),
                "blocker_ids": [b.get("id") for b in active_blocks[:20]],
                "output_type": arguments.get("output_type", "paper"),
                "section": arguments.get("section"),
            },
        )
    # warn_only ⇒ never block; the gate-blocker list is surfaced as
    # warnings on the response. Sandbox / exploratory use only.
    soft_gate = policy == "warn_only"
    # enforce ⇒ overrides demand an explicit researcher rationale; a
    # call asking for the bypass without supplying WHY is rejected.
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: override_completeness_gate=true "
            "requires a one-line override_rationale (recorded to "
            "workspace/logs/override_log.md). Pass override_rationale='…' or "
            "ask the researcher; or relax the policy to 'allow_override' in "
            "inputs/researcher_config.yaml."
        ))

    def _record_bypass(gate_name: str, blockers: list[str] | None) -> None:
        nonlocal bypass_logged
        if bypass_logged:
            return
        log_override(
            root,
            tool="tool_synthesize",
            gate=gate_name,
            rationale=rationale,
            extra={
                "output_type": arguments.get("output_type", "paper"),
                "section": arguments.get("section"),
                "blocker_count": len(blockers or []),
            },
        )
        bypass_logged = True

    if full_doc:
        gate = audit_quality_full(
            root,
            # Skip claims gate on the FIRST synthesis (paper.md doesn't
            # exist yet to extract claims from). Honour an explicit
            # empty list — researcher asked for ALL gates to run.
            skip=arguments["skip_gates"] if "skip_gates" in arguments else ["claims"],
        )
        if gate.get("status") == "error":
            if override_requested:
                _record_bypass("quality_full", gate.get("blockers"))
            elif soft_gate:
                # warn_only policy — record the override (researcher set
                # the policy that turns blockers into warnings) and let
                # synthesis proceed. Blockers attach as warnings below.
                _record_bypass("quality_full", gate.get("blockers"))
            else:
                return _text(_error(
                    "BLOCKED by master quality gate. "
                    + (gate.get("advice") or "")
                    + "\n\nBlockers:\n"
                    + "\n".join(f"- {b}" for b in (gate.get("blockers") or [])[:15])
                    + (f"\n  … and {len(gate.get('blockers') or []) - 15} more"
                       if len(gate.get("blockers") or []) > 15 else "")
                    + "\n\nReport: " + str(gate.get("report_path"))
                    + "\n\nTo bypass for a partial / WIP deliverable, call "
                    "again with override_completeness_gate=true."
                ))
    else:
        # Lightweight gate for single-section calls — still want focal
        # figure + caption coverage.
        sc = audit_step_completeness(root)
        if sc.get("status") == "error":
            if override_requested or soft_gate:
                _record_bypass("step_completeness", sc.get("blockers"))
            else:
                return _text(_error(
                    "BLOCKED by step-completeness gate (section-only synthesis). "
                    + sc.get("advice", "")
                ))

    res = synthesize_workspace(
        root,
        output_format=arguments.get("output_format", "markdown"),
        section=arguments.get("section"),
        output_type=arguments.get("output_type", "paper"),
        citation_style=arguments.get("citation_style", "vancouver"),
        auto_proceed=bool(arguments.get("auto_proceed", False)),
    )
    if "error" in res:
        return _text(_error(res["error"]))

    # After writing the full paper, run the claims audit as a second
    # pass so any AI hallucinations surface immediately. Skip when the
    # researcher already overrode the gate (the bypass log captures it).
    if full_doc and not override_requested and not soft_gate:
        try:
            from research_os.tools.actions.audit.claim_grounding import (
                audit_claims,
            )

            cl = audit_claims(root)
            res["claim_grounding"] = {
                "status": cl.get("status"),
                "ungrounded": cl.get("ungrounded"),
                "coverage_pct": cl.get("coverage_pct"),
                "report_path": cl.get("report_path"),
            }
            if cl.get("ungrounded"):
                res["advice"] = (
                    f"Paper written, but {cl['ungrounded']} numeric claim(s) "
                    "are NOT grounded in any workspace output. Review "
                    f"{cl.get('report_path')} before submitting."
                )
        except Exception as e:
            logger.debug("claims audit skipped: %s", e)

    return _text(_success(res))


def _handle_tool_latex_compile(name, arguments, root):
    from research_os.tools.actions.synthesis.latex import latex_compile

    return _text(_success(latex_compile(root)))


def _handle_tool_paper_compile_typst(name, arguments, root):
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.typst import paper_compile_typst
    from research_os.tools.actions.state.config import get_research_config

    paper_path = arguments.get("paper_path", "synthesis/paper.md")
    venue = arguments.get("venue")
    output = arguments.get("output", "synthesis/paper.pdf")

    # Phase-5 review-rewrite loop. Config knobs:
    #   synthesis.drafter_loop_enabled (bool, default True)
    #   synthesis.drafter_loop_max_iterations (int, default 3)
    #   synthesis.drafter_loop_quality_threshold (float, default 0.10)
    # Tier overrides:
    #   project_tier=throwaway → max_iter clamped to 1.
    #   interaction.autonomy_level=autopilot → respects config max_iter.
    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}
    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    max_iter = int(synth.get("drafter_loop_max_iterations", 3))
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    # Allow per-call disable for back-compat / debugging.
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    if not loop_enabled:
        return _text(_success(paper_compile_typst(
            root,
            paper_path=paper_path,
            venue=venue,
            output=output,
        )))

    def _drafter(prior_output=None, findings=None, root=root):
        return paper_compile_typst(
            root,
            paper_path=paper_path,
            venue=venue,
            output=output,
        )

    reviewer = persona_reviewer(
        ["presentation_critic", "scope_creep_critic", "methodology_skeptic"]
    )
    loop_res = draft_with_review_rewrite(
        _drafter,
        reviewer,
        drafter_name="paper",
        root=Path(root),
        max_iter=max_iter,
        improvement_threshold=threshold,
    )
    final = loop_res.get("final_output") or {}
    if isinstance(final, dict):
        final["drafter_loop"] = {
            "iterations": loop_res["iterations"],
            "converged": loop_res["converged"],
            "stop_reason": loop_res["stop_reason"],
            "quality_progression": loop_res["quality_progression"],
        }
    return _text(_success(final))


def _handle_tool_dashboard_story_generate(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_generate,
    )
    res = dashboard_story_generate(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_generate failed")))
    return _text(_success(res))


def _handle_tool_dashboard_story_edit(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_edit,
    )
    res = dashboard_story_edit(
        root,
        edits=arguments.get("edits"),
        mode=arguments.get("mode", "patch"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_edit failed")))
    return _text(_success(res))


def _handle_tool_dashboard_story_quality_bar(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard_story import (
        dashboard_story_quality_bar,
    )
    res = dashboard_story_quality_bar(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "dashboard_story_quality_bar failed")))
    return _text(_success(res))


def _handle_tool_audit_figure_interactivity(name, arguments, root):
    from research_os.tools.actions.audit.figure_interactivity import (
        audit_figure_interactivity,
    )

    res = audit_figure_interactivity(
        root,
        strictness=arguments.get("strictness"),
        autogen=arguments.get("autogen"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_figure_interactivity failed")))
    return _text(_success(res))


def _handle_tool_figure_interactive_autogen(name, arguments, root):
    from research_os.tools.actions.audit.figure_interactivity import (
        figure_interactive_autogen,
    )

    fig_path = Path(arguments["figure_path"])
    if not fig_path.is_absolute():
        fig_path = root / fig_path
    if not fig_path.exists():
        return _text(_error(f"figure not found: {fig_path}"))
    res = figure_interactive_autogen(fig_path, root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "figure_interactive_autogen failed")))
    return _text(_success(res))


def _handle_tool_audit_dashboard_content(name, arguments, root):
    from research_os.tools.actions.audit.dashboard_content import audit_dashboard_content
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_dashboard_content_gate", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_dashboard_content_gate=true requires override_rationale."
        ))
    res = audit_dashboard_content(
        root,
        dashboard_path=arguments.get("dashboard_path", "synthesis/dashboard.html"),
    )
    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_audit_dashboard_content",
            gate="dashboard_content",
            rationale=rationale,
            extra={"blocker_count": len(res["blockers"])},
        )
        res["override_applied"] = True
        res["status"] = "success"
    return _text(_success(res))


def _handle_tool_dashboard_reviewer_sim(name, arguments, root):
    from research_os.tools.actions.audit.dashboard_content import reviewer_simulator

    dpath = root / arguments.get("dashboard_path", "synthesis/dashboard.html")
    if not dpath.exists():
        return _text(_error(f"{dpath.name} not found. Run tool_dashboard(operation='create') first."))
    html = dpath.read_text(encoding="utf-8", errors="replace")
    return _text(_success(reviewer_simulator(html)))


def _handle_tool_synthesis_preview(name, arguments, root):
    from research_os.tools.actions.synthesis.preview import synthesis_preview

    return _text(_success(synthesis_preview(
        root,
        target=arguments.get("target", "paper"),
        venue=arguments.get("venue"),
        mode=arguments.get("mode", "fresh"),
    )))


def _handle_tool_section_substantiveness(name, arguments, root):
    from research_os.tools.actions.audit.content_depth import section_substantiveness

    return _text(_success(section_substantiveness(
        root,
        paper_path=arguments.get("paper_path", "synthesis/paper.md"),
    )))


def _handle_tool_audit_cliches(name, arguments, root):
    from research_os.tools.actions.audit.content_depth import audit_cliches

    return _text(_success(audit_cliches(
        arguments.get("paper_path", "synthesis/paper.md"),
        root,
    )))


# ── humanities essay scaffold ─────────────────────────────────────────


def _handle_tool_humanities_essay_scaffold(name, arguments, root):
    from research_os.tools.actions.synthesis.humanities_essay_scaffold import (
        scaffold_humanities_essay,
    )
    return _text(_success(scaffold_humanities_essay(root)))


# ── figure auto-embed + orphan-coverage audit ────────────────────────


def _handle_tool_paper_figures_autoembed(name, arguments, root):
    from research_os.tools.actions.synthesis.figure_auto_embed import (
        auto_embed_figures,
        rewrite_figure_xrefs,
    )
    from research_os.tools.actions.state.config import get_research_config

    root_path = Path(root)
    paper = root_path / "synthesis" / "paper.md"
    mode = arguments.get("mode", "append_to_section")
    section_map = arguments.get("section_map")

    embed_res = auto_embed_figures(
        paper, root_path, mode=mode, section_map=section_map,
    )
    if embed_res.get("status") == "error":
        return _text(_error(embed_res.get("message", "auto-embed failed")))

    # Honour config — researcher can disable rewrite.
    rewrite_res: dict = {"skipped": True}
    skip_xref_rewrite = bool(arguments.get("override_xref_rewrite", False))
    try:
        cfg = get_research_config(root_path) or {}
        rewrite_on = (
            (cfg.get("synthesis", {}) or {}).get("figure_xref_rewrite", True)
        )
    except Exception:
        rewrite_on = True
    if rewrite_on and not skip_xref_rewrite:
        rewrite_res = rewrite_figure_xrefs(paper)

    return _text(_success({
        "embed": embed_res,
        "xref_rewrite": rewrite_res,
        "paper_path": str(paper.relative_to(root_path)),
    }))


def _handle_tool_audit_figure_coverage(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.synthesis.figure_auto_embed import (
        FigureCoverageAudit,
    )

    root_path = Path(root)
    audit = FigureCoverageAudit()
    # Run the Phase-4 audit to get structured findings, then fan them
    # out to workspace/figure_coverage_audit.{md,json} +
    # workspace/logs/.audit_findings.jsonl. Best-effort writes — if the
    # workspace dir is read-only we still want to return the audit verdict.
    findings: list = []
    try:
        findings = audit.run(root_path)
        write_audit_outputs(findings, "figure_coverage", root_path)
    except Exception:  # noqa: BLE001 — best-effort artefact write
        pass
    # Legacy dict surface preserved for back-compat callers (tests,
    # protocols that key on `status`/`blockers`/`checked`/`embedded`).
    res = audit.to_legacy_dict(root_path, findings)
    if res.get("status") == "error" and "blockers" in res:
        # Return as success-with-blockers so the audit aggregator can
        # surface them rather than treating the audit as a tool error.
        return _text(_success(res))
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_figure_coverage failed")))
    return _text(_success(res))


# ── real slide compilation engine ────────────────────────────────────


def _handle_tool_slides_create(name, arguments, root):
    """tool_slides_create — real engine (Reveal.js HTML / Touying Typst)."""
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.slides import compile_slides
    from research_os.tools.actions.state.config import get_research_config

    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}
    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    # Slides default is 2 iterations per spec; researcher can raise via
    # drafter_loop_max_iterations.
    max_iter = int(
        synth.get(
            "drafter_loop_max_iterations_slides",
            min(2, int(synth.get("drafter_loop_max_iterations", 3))),
        )
    )
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    def _do_compile():
        return compile_slides(
            root,
            engine=arguments.get("engine", "reveal"),
            template=arguments.get("template", "conference_15min"),
            theme=arguments.get("theme", ""),
            speaker_notes_enabled=bool(
                arguments.get("speaker_notes_enabled", True)
            ),
            print_handout=bool(arguments.get("print_handout", True)),
            audience=arguments.get("audience"),
            output_format=arguments.get("output_format"),
        )

    try:
        if not loop_enabled:
            result = _do_compile()
        else:
            def _drafter(prior_output=None, findings=None, root=root):
                return _do_compile()
            reviewer = persona_reviewer(
                ["presentation_critic", "scope_creep_critic"]
            )
            loop_res = draft_with_review_rewrite(
                _drafter,
                reviewer,
                drafter_name="slides",
                root=Path(root),
                max_iter=max_iter,
                improvement_threshold=threshold,
            )
            result = loop_res.get("final_output") or {}
            if isinstance(result, dict):
                result["drafter_loop"] = {
                    "iterations": loop_res["iterations"],
                    "converged": loop_res["converged"],
                    "stop_reason": loop_res["stop_reason"],
                    "quality_progression": loop_res["quality_progression"],
                }
    except Exception as exc:
        return _text(_error(f"tool_slides_create crashed: {exc}"))
    if result.get("status") != "success":
        return _text(_error(result.get("message", "slide compilation failed")))
    return _text(_success(result))


# ── cross-deliverable consistency audit ──────────────────────────────


def _handle_tool_audit_cross_deliverable_consistency(name, arguments, root):
    """Cross-deliverable consistency audit: 5 dimensions, override-aware."""
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.cross_deliverable import (
        CrossDeliverableConsistencyAudit,
        audit_cross_deliverable_consistency,
    )
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_cross_deliverable", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (
        policy == "enforce"
        and override_requested
        and (not rationale or not str(rationale).strip())
    ):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_cross_deliverable=true requires override_rationale."
        ))

    res = audit_cross_deliverable_consistency(root)

    # Phase-4 AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = CrossDeliverableConsistencyAudit().run(Path(root))
        write_audit_outputs(
            findings, "cross_deliverable_consistency", Path(root)
        )
    except Exception:  # pragma: no cover - defensive guard
        pass

    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_audit_cross_deliverable_consistency",
            gate="cross_deliverable_consistency",
            rationale=rationale,
            extra={
                "blocker_count": len(res["blockers"]),
                "deliverables_found": res.get("deliverables_found", []),
            },
        )
        res["override_applied"] = True
        res["status"] = "success"

    return _text(_success(res))


# ── reviewer-response scaffold (4 tools) ─────────────────────────────


def _handle_tool_reviewer_simulate(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import reviewer_simulate
    res = reviewer_simulate(root, personas=arguments.get("personas"))
    if res.get("status") == "error":
        return _text(_error(res.get("message", "reviewer_simulate failed")))
    return _text(_success(res))


def _handle_tool_rebuttal_draft(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import rebuttal_draft
    res = rebuttal_draft(
        root,
        comment=arguments["comment"],
        persona=arguments["persona"],
        evidence_paths=arguments.get("evidence_paths"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "rebuttal_draft failed")))
    return _text(_success(res))


def _handle_tool_reviewer_response_compile(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import (
        reviewer_response_compile,
    )
    res = reviewer_response_compile(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "compile failed")))
    return _text(_success(res))


def _handle_tool_audit_reviewer_responses(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import (
        audit_reviewer_responses,
    )
    res = audit_reviewer_responses(root)
    return _text(_success(res))


def _handle_tool_poster_create(name, arguments, root):
    from research_os.tools.actions.synthesis.drafter_loop import (
        draft_with_review_rewrite,
        persona_reviewer,
    )
    from research_os.tools.actions.synthesis.latex import create_poster
    from research_os.tools.actions.synthesis.poster_typst import compile_poster
    from research_os.tools.actions.state.config import get_research_config

    cfg = get_research_config(root) or {}
    synth = cfg.get("synthesis") or {}

    # Resolve engine: explicit argument > researcher_config > default 'typst'.
    engine = arguments.get("engine")
    if not engine:
        engine = synth.get("poster_engine") or "typst"

    if engine == "latex":
        # Legacy tikzposter path. Honors layout (billboard|classic) +
        # audience (academic_conference|symposium|industry|teaching).
        return _text(_success(create_poster(
            root,
            layout=arguments.get("layout", "billboard"),
            audience=arguments.get("audience", "academic_conference"),
        )))

    # Typst (default). Pull template/theme/qr/handout from config when the
    # caller didn't override.
    template = arguments.get("template")
    theme = arguments.get("theme")
    qr_url = arguments.get("qr_url")
    handout_pdf = arguments.get("handout_pdf")
    if template is None:
        template = synth.get("poster_template", "academic_36x48")
    if theme is None:
        theme = synth.get("poster_theme", "light")
    if qr_url is None:
        qr_url = synth.get("poster_qr_url") or None
    if handout_pdf is None:
        handout_pdf = bool(synth.get("poster_handout_pdf", True))

    loop_enabled = bool(synth.get("drafter_loop_enabled", True))
    max_iter = int(
        synth.get(
            "drafter_loop_max_iterations_poster",
            min(2, int(synth.get("drafter_loop_max_iterations", 3))),
        )
    )
    threshold = float(synth.get("drafter_loop_quality_threshold", 0.10))
    tier = (cfg.get("project_tier") or "production").strip().lower()
    if tier == "throwaway":
        max_iter = 1
    if arguments.get("drafter_loop") is False:
        loop_enabled = False

    def _do_compile():
        return compile_poster(
            root,
            template=template,
            theme=theme,
            qr_url=qr_url,
            handout_pdf=bool(handout_pdf),
        )

    if not loop_enabled:
        return _text(_success(_do_compile()))

    def _drafter(prior_output=None, findings=None, root=root):
        return _do_compile()

    reviewer = persona_reviewer(
        ["presentation_critic", "novelty_critic"]
    )
    loop_res = draft_with_review_rewrite(
        _drafter,
        reviewer,
        drafter_name="poster",
        root=Path(root),
        max_iter=max_iter,
        improvement_threshold=threshold,
    )
    result = loop_res.get("final_output") or {}
    if isinstance(result, dict):
        result["drafter_loop"] = {
            "iterations": loop_res["iterations"],
            "converged": loop_res["converged"],
            "stop_reason": loop_res["stop_reason"],
            "quality_progression": loop_res["quality_progression"],
        }
    return _text(_success(result))


def _handle_tool_dashboard_create(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.tools.actions.synthesis.latex import create_dashboard
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_completeness_gate", False))
    rationale = arguments.get("override_rationale")
    completeness_warnings: list[str] | None = None
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: override_completeness_gate=true "
            "requires a one-line override_rationale."
        ))

    gate = audit_step_completeness(root)
    if gate.get("status") == "error":
        completeness_warnings = gate.get("blockers")
        if override_requested:
            # Real bypass: blockers existed AND researcher authorised
            # suppression of the warning panel. Log it for the audit.
            log_override(
                root,
                tool="tool_dashboard_create",
                gate="step_completeness",
                rationale=rationale,
                extra={"blocker_count": len(completeness_warnings or [])},
            )

    legacy = bool(arguments.get("dashboard_legacy", False))
    if legacy:
        res = create_dashboard(
            root,
            title=arguments.get("title"),
            audience=arguments.get("audience", "academic"),
            suppress_audit_panel=override_requested and bool(completeness_warnings),
        )
    else:
        from research_os.tools.actions.synthesis.dashboard_v2 import render_dashboard_v2
        res = render_dashboard_v2(
            root,
            title=arguments.get("title"),
            audience=arguments.get("audience", "academic"),
            default_mode=arguments.get("dashboard_default_mode", "explore"),
            search_enabled=bool(arguments.get("dashboard_search_enabled", True)),
            print_optimized=bool(arguments.get("dashboard_print_optimized", True)),
            suppress_audit_panel=override_requested and bool(completeness_warnings),
        )
    if res.get("status") == "success":
        if completeness_warnings and not override_requested:
            res["completeness_warnings"] = completeness_warnings
            res["advice"] = (
                "Dashboard rendered, but step-completeness audit flagged "
                f"{len(completeness_warnings)} blocker(s). "
                "Resolve them before the FINAL deliverable."
            )
        return _text(_success(res))
    return _text(_error(res.get("message", "dashboard create failed")))


def _handle_tool_audit_step_completeness(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.audit import (
        StepCompletenessAudit,
        audit_step_completeness,
    )

    step_id = arguments.get("step_id")
    # Legacy procedural call still produces workspace/logs/step_completeness.md
    # byte-identical to v1.x — it is the source of truth for the
    # response body that callers (tool_synthesize, tool_path_finalize,
    # tool_dashboard_create) consume.
    result = audit_step_completeness(root, step_id=step_id)

    # Phase-4 AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = StepCompletenessAudit().run(root, step_id=step_id)
        write_audit_outputs(findings, "step_completeness", root)
    except Exception:  # pragma: no cover - defensive guard
        pass

    return _text(_success(result))


def _handle_tool_audit_step_literature(name, arguments, root):
    from research_os.tools.actions.audit.step_literature import audit_step_literature

    return _text(_success(audit_step_literature(
        root, step_id=arguments.get("step_id"),
    )))


def _handle_tool_audit_findings_query(name, arguments, root):
    """Phase-4c: filter the cross-audit findings ledger.

    Reads ``workspace/logs/.audit_findings.jsonl`` (latest snapshot per
    stable finding id), then filters by severity / dimension / step /
    since. Returns the list — does NOT mutate the ledger.
    """
    from research_os.tools.actions.audit.findings_query import (
        audit_findings_query,
    )

    res = audit_findings_query(
        Path(root),
        severity=arguments.get("severity"),
        dimension=arguments.get("dimension"),
        step=arguments.get("step"),
        since=arguments.get("since"),
    )
    return _text(_success(res))


def _handle_tool_audit_findings_diff(name, arguments, root):
    """Phase-4c: diff two snapshots of the findings ledger by stable id.

    Snapshots the ledger as of ``timestamp_a`` and ``timestamp_b`` (both
    ISO-8601), then reports findings added / resolved / changed between
    them. The structural diff ignores re-emission churn (generated_at +
    ro_version) so a finding that simply reruns is NOT reported as
    changed.
    """
    from research_os.tools.actions.audit.findings_query import (
        audit_findings_diff,
    )

    ts_a = arguments.get("timestamp_a")
    ts_b = arguments.get("timestamp_b")
    if not ts_a or not ts_b:
        return _text(_error(
            "tool_audit_findings_diff requires both timestamp_a and "
            "timestamp_b (ISO-8601 strings, e.g. '2026-06-05T12:00:00Z')."
        ))
    res = audit_findings_diff(Path(root), timestamp_a=ts_a, timestamp_b=ts_b)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "audit_findings_diff failed")))
    return _text(_success(res))


def _handle_tool_step_revision_options(name, arguments, root):
    from research_os.tools.actions.state.revision import step_revision_options

    try:
        res = step_revision_options(arguments["step_id"], root)
        if res.get("status") == "success":
            return _text(_success(res))
        return _text(_error(res.get("message", "step_revision_options failed")))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_tool_step_iterate(name, arguments, root):
    from research_os.tools.actions.state.iteration import iterate_step

    try:
        res = iterate_step(
            root,
            step_id=arguments["step_id"],
            rationale=arguments["rationale"],
            scripts=arguments.get("scripts"),
            figures=arguments.get("figures"),
            tables=arguments.get("tables"),
            bump_conclusion=bool(arguments.get("bump_conclusion", True)),
        )
        return _text(_success(res))
    except (ValueError, FileNotFoundError) as e:
        return _text(_error(str(e)))


def _handle_tool_step_iterations_list(name, arguments, root):
    from research_os.tools.actions.state.iteration import list_iterations

    try:
        return _text(_success(list_iterations(root, arguments["step_id"])))
    except (KeyError, FileNotFoundError) as e:
        return _text(_error(str(e)))


def _handle_tool_audit_version_coherence(name, arguments, root):
    from research_os.tools.actions.state.iteration import audit_version_coherence

    return _text(_success(audit_version_coherence(
        root, step_id=arguments.get("step_id"),
    )))


def _handle_tool_figure_caption_synthesise(name, arguments, root):
    from research_os.tools.actions.viz import caption_synthesise

    res = caption_synthesise(
        root=root,
        figure_path=arguments["figure_path"],
        technical_caption=arguments.get("technical_caption"),
        findings_context=arguments.get("findings_context"),
        overwrite=bool(arguments.get("overwrite", False)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "caption_synthesise failed")))


def _handle_tool_audit_figure_full(name, arguments, root):
    from research_os.tools.actions.viz import audit_figure_quality

    return _text(_success(audit_figure_quality(
        arguments["figure_path"], root,
    )))


def _handle_tool_figure_palette(name, arguments, root):
    from research_os.tools.actions.viz import palette_for

    colors = palette_for(arguments.get("kind", "qualitative"),
                         n=int(arguments.get("n", 8)))
    return _text(_success({"kind": arguments.get("kind", "qualitative"),
                           "colors": colors}))


def _handle_tool_step_pipeline_define(name, arguments, root):
    from research_os.tools.actions.exec.step_pipeline import define_pipeline

    res = define_pipeline(
        arguments["step_id"], root,
        name=arguments.get("name"),
        description=arguments.get("description", ""),
        nodes=arguments.get("nodes"),
        template=arguments.get("template", "default"),
    )
    if res.get("status") in {"success", "exists"}:
        return _text(_success(res))
    return _text(_error(res.get("message", "step_pipeline_define failed")))


def _handle_tool_step_pipeline_run(name, arguments, root):
    from research_os.tools.actions.exec.step_pipeline import run_pipeline

    res = run_pipeline(
        arguments["step_id"], root,
        only=arguments.get("only"),
        force=bool(arguments.get("force", False)),
        dry_run=bool(arguments.get("dry_run", False)),
    )
    return _text(_success(res) if res.get("status") == "success"
                 else _error(res.get("advice") or res.get("message", "pipeline run failed")))


def _handle_tool_step_pipeline_status(name, arguments, root):
    from research_os.tools.actions.exec.step_pipeline import pipeline_status

    return _text(_success(pipeline_status(arguments["step_id"], root)))


def _handle_tool_step_pipeline_diagram(name, arguments, root):
    from research_os.tools.actions.exec.step_pipeline import render_pipeline_diagram

    res = render_pipeline_diagram(arguments["step_id"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "pipeline diagram failed")))


def _handle_tool_dashboard_test_generate(name, arguments, root):
    from research_os.tools.actions.viz.dashboard_tests import (
        generate_dashboard_test_suite,
    )

    return _text(_success(generate_dashboard_test_suite(
        root, overwrite=bool(arguments.get("overwrite", False)),
    )))


def _handle_tool_dashboard_test_run(name, arguments, root):
    from research_os.tools.actions.viz.dashboard_tests import run_dashboard_tests

    return _text(_success(run_dashboard_tests(
        root,
        only=arguments.get("only"),
        visual=bool(arguments.get("visual", False)),
        update_snapshots=bool(arguments.get("update_snapshots", False)),
        timeout=int(arguments.get("timeout", 300)),
    )))


# ── Grounded reasoning handlers ──────────────────────────────────────


def _handle_tool_thought_log(name, arguments, root):
    from research_os.tools.actions.research.grounding import thought_log

    res = thought_log(
        root,
        kind=arguments["kind"],
        content=arguments["content"],
        step_id=arguments.get("step_id"),
        decision_id=arguments.get("decision_id"),
        metadata=arguments.get("metadata"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "thought_log failed")))


def _handle_tool_thought_trace(name, arguments, root):
    from research_os.tools.actions.research.grounding import thought_trace

    return _text(_success(thought_trace(
        root,
        step_id=arguments.get("step_id"),
        decision_id=arguments.get("decision_id"),
        tail=int(arguments.get("tail", 50)),
    )))


def _handle_tool_grounding_register(name, arguments, root):
    from research_os.tools.actions.research.grounding import grounding_register

    res = grounding_register(
        root,
        decision_id=arguments.get("decision_id"),
        claim=arguments["claim"],
        sources=arguments["sources"],
        step_id=arguments.get("step_id"),
        confidence=arguments.get("confidence", "medium"),
        notes=arguments.get("notes", ""),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "grounding_register failed")))


def _handle_tool_ground_from_context(name, arguments, root):
    from research_os.tools.actions.research.grounding import ground_from_context

    res = ground_from_context(
        root,
        decision_id=arguments.get("decision_id"),
        claim=arguments["claim"],
        context_paths=arguments["context_paths"],
        cited_excerpts=arguments.get("cited_excerpts"),
        confidence=arguments.get("confidence", "medium"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "ground_from_context failed")))


def _handle_tool_claim_verify(name, arguments, root):
    from research_os.tools.actions.research.grounding import claim_verify

    res = claim_verify(
        root,
        claim=arguments["claim"],
        verifications=arguments["verifications"],
        decision_id=arguments.get("decision_id"),
        step_id=arguments.get("step_id"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "claim_verify failed")))


def _handle_tool_grounding_verify(name, arguments, root):
    from research_os.tools.actions.research.grounding import grounding_verify

    return _text(_success(grounding_verify(root)))


def _handle_tool_lessons_record(name, arguments, root):
    from research_os.tools.actions.research.lessons import lessons_record

    res = lessons_record(
        root,
        outcome=arguments["outcome"],
        reflection=arguments["reflection"],
        what_worked=arguments.get("what_worked", ""),
        what_didnt=arguments.get("what_didnt", ""),
        recommendation=arguments.get("recommendation", ""),
        tags=arguments.get("tags"),
        step_id=arguments.get("step_id"),
        scope=arguments.get("scope", "step"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "lessons_record failed")))


def _handle_tool_lessons_consult(name, arguments, root):
    from research_os.tools.actions.research.lessons import lessons_consult

    return _text(_success(lessons_consult(
        root,
        task=arguments["task"],
        tags=arguments.get("tags"),
        top_k=int(arguments.get("top_k", 5)),
        scope_filter=arguments.get("scope_filter"),
    )))


def _handle_tool_plan_step_grounded(name, arguments, root):
    from research_os.tools.actions.research.research import plan_step_grounded

    res = plan_step_grounded(
        arguments["goal"], root,
        inputs_to_consult=arguments.get("inputs_to_consult"),
        context_to_consult=arguments.get("context_to_consult"),
        literature_queries=arguments.get("literature_queries"),
        max_substeps=int(arguments.get("max_substeps", 6)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "plan_step_grounded failed")))


# ── New: code / prose / claims / prereg / sensitivity / redteam / null / master / SLURM ──


def _handle_tool_audit_code_quality(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.code_quality import (
        CodeQualityAudit,
        audit_code_quality,
    )

    # Legacy report (preserves workspace/logs/code_quality.md byte-for-byte).
    legacy = audit_code_quality(
        root,
        step_id=arguments.get("step_id"),
        run_ruff=bool(arguments.get("run_ruff", True)),
        run_mypy=bool(arguments.get("run_mypy", False)),
    )

    # Phase-4 structured artefacts (JSON + JSONL ledger) alongside the
    # legacy markdown. Re-running audit_code_quality is cheap and keeps
    # the two output paths trivially consistent; if that ever shows up
    # in a profile, lift the per_step walk out into a shared helper.
    findings = CodeQualityAudit().run(
        root,
        step_id=arguments.get("step_id"),
        run_ruff=bool(arguments.get("run_ruff", True)),
        run_mypy=bool(arguments.get("run_mypy", False)),
    )
    written = write_audit_outputs(findings, "code_quality", root)
    legacy["audit_findings"] = {
        "count": len(findings),
        "block": sum(1 for f in findings if f.severity == "block"),
        "warn": sum(1 for f in findings if f.severity == "warn"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "json_path": str(written["json"].relative_to(root)),
        "jsonl_path": str(written["jsonl"].relative_to(root)),
    }
    return _text(_success(legacy))


def _handle_tool_audit_prose(name, arguments, root):
    from research_os.tools.actions.audit.prose_quality import audit_prose

    return _text(_success(audit_prose(
        root,
        targets=arguments.get("targets"),
        is_observational=arguments.get("is_observational"),
    )))


def _handle_tool_audit_claims(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.claim_grounding import (
        ClaimGroundingAudit,
        audit_claims,
    )

    target_path = arguments.get("target_path")
    tolerance = float(arguments.get("tolerance", 0.01))

    # Legacy procedural call still produces synthesis/claim_index.json and
    # workspace/logs/claim_grounding.md byte-identical to v1.x — keep it
    # as the source of truth for the response body that callers consume.
    result = audit_claims(root, target_path=target_path, tolerance=tolerance)

    # Phase-4 AuditBase fan-out: emit structured AuditFindings to the
    # standard {gate}_audit.md + {gate}_audit.json + .audit_findings.jsonl
    # artefacts. Failure to write the audit-outputs artefacts must not
    # mask the legacy auditor's response — wrap in a guard.
    try:
        findings = ClaimGroundingAudit().run(
            root, target_path=target_path, tolerance=tolerance
        )
        write_audit_outputs(findings, "claim_grounding", root)
    except Exception:  # pragma: no cover - defensive guard
        pass

    return _text(_success(result))


def _handle_tool_audit_evalue(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_evalue

    return _text(_success(audit_evalue(
        float(arguments["risk_ratio"]), root,
        ci_lower=arguments.get("ci_lower"),
        ci_upper=arguments.get("ci_upper"),
    )))


def _handle_tool_preregister_freeze(name, arguments, root):
    from research_os.tools.actions.audit.preregistration import (
        freeze_preregistration,
    )

    res = freeze_preregistration(
        root,
        primary_outcomes=arguments.get("primary_outcomes"),
        secondary_outcomes=arguments.get("secondary_outcomes"),
        target_n=arguments.get("target_n"),
        power_assumption=arguments.get("power_assumption"),
        stopping_rule=arguments.get("stopping_rule"),
        subgroups=arguments.get("subgroups"),
        sensitivity=arguments.get("sensitivity"),
        multiplicity=arguments.get("multiplicity"),
        inclusion=arguments.get("inclusion"),
        exclusion=arguments.get("exclusion"),
        missing_data=arguments.get("missing_data"),
        additional_analyses=arguments.get("additional_analyses"),
        contingencies=arguments.get("contingencies"),
        anticipated_deviations=arguments.get("anticipated_deviations"),
        data_status=arguments.get("data_status", "not yet collected"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "preregister_freeze failed")))


def _handle_tool_preregister_diff(name, arguments, root):
    from research_os.tools.actions.audit.preregistration import (
        diff_preregistration,
    )

    return _text(_success(diff_preregistration(root)))


def _handle_tool_sensitivity_define(name, arguments, root):
    from research_os.tools.actions.exec.sensitivity import define_sensitivity

    res = define_sensitivity(
        arguments["step_id"], root,
        base_script=arguments["base_script"],
        estimate_column=arguments.get("estimate_column", "estimate"),
        ci_columns=tuple(arguments.get("ci_columns", ["ci_lo", "ci_hi"])),
        grid=arguments.get("grid"),
        output_csv=arguments.get("output_csv", "data/output/grid_results.csv"),
    )
    if res.get("status") in {"success", "exists"}:
        return _text(_success(res))
    return _text(_error(res.get("message", "sensitivity_define failed")))


def _handle_tool_sensitivity_run(name, arguments, root):
    from research_os.tools.actions.exec.sensitivity import run_sensitivity

    res = run_sensitivity(
        arguments["step_id"], root,
        max_specs=arguments.get("max_specs"),
        render_figure=bool(arguments.get("render_figure", True)),
    )
    return _text(_success(res))


def _handle_tool_redteam_review(name, arguments, root):
    from research_os.tools.actions.audit.redteam import redteam_scaffold

    res = redteam_scaffold(
        root, persona=arguments.get("persona", "methodological_skeptic"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "redteam_review failed")))


def _handle_tool_response_to_reviewers(name, arguments, root):
    from research_os.tools.actions.audit.redteam import write_response_template

    res = write_response_template(root, review_path=arguments.get("review_path"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "response_to_reviewers failed")))


def _handle_tool_null_findings_report(name, arguments, root):
    from research_os.tools.actions.audit.null_findings import write_null_findings

    return _text(_success(write_null_findings(root)))


def _handle_tool_audit_quality_full(name, arguments, root):
    from research_os.tools.actions.audit._base import write_audit_outputs
    from research_os.tools.actions.audit.audit import (
        AuditMaster,
        audit_quality_full,
    )

    # 1) Legacy aggregator — writes workspace/logs/audit_master.md and
    # returns the dict shape MCP clients (and tool_synthesize) already
    # know how to read. The markdown format is pinned by snapshot test
    # and must stay byte-for-byte stable.
    legacy = audit_quality_full(
        root,
        target_path=arguments.get("target_path"),
        skip=arguments.get("skip"),
    )

    # 2) Phase-4 structured findings — fan out to the v2 writer so the
    # JSON companion + the cross-audit .audit_findings.jsonl ledger
    # pick up this run. Failures here must NEVER take the legacy
    # result down with them; the v2 writer is best-effort and
    # supplementary.
    try:
        audit = AuditMaster()
        findings = audit.run(root, legacy_result=legacy)
        paths = write_audit_outputs(findings, audit.name, root)
        legacy["audit_master_v2"] = {
            "finding_count": len(findings),
            "json_path": str(paths["json"].relative_to(root)),
            "jsonl_path": str(paths["jsonl"].relative_to(root)),
            "md_path": str(paths["md"].relative_to(root)),
        }
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("audit_master v2 writer failed")
        legacy["audit_master_v2_error"] = str(exc)

    # 3) Phase 8 — attach a tier-based progress summary so the AI can
    # see where the project sits in the lifecycle without re-routing.
    try:
        legacy["tier_progress"] = _build_tier_progress(root)
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("tier_progress build failed: %s", exc)

    return _text(_success(legacy))


def _build_tier_progress(root) -> dict:
    """Tier-based progress summary for tool_audit_master.

    Reads ``workspace/.os_state/current_tier.json`` and the protocol
    execution log to count how many distinct protocols have fired per
    tier. Returns a compact summary suitable for the audit_master
    response body (the v2 markdown writer is not modified).
    """
    from research_os.protocols._tiers import TIERS, tier_position
    from research_os.tools.actions.protocol import get_protocol_history
    from research_os.tools.actions.router import _resolve_tier
    from research_os.tools.actions.state.tier_state import (
        read_tier_state,
        tier_direction,
    )

    state = read_tier_state(root)
    current = state.get("current_tier")
    history = list(state.get("history") or [])

    # Per-tier protocol-fire counts from the execution log.
    per_tier_protocols: dict[str, set[str]] = {t: set() for t in TIERS}
    try:
        entries = (get_protocol_history(root, limit=500).get("entries") or [])
    except Exception:
        entries = []
    for ent in entries:
        pn = ent.get("protocol") or ent.get("protocol_name")
        if not isinstance(pn, str) or not pn:
            continue
        tier = _resolve_tier(pn)
        if tier and tier in per_tier_protocols:
            per_tier_protocols[tier].add(pn)

    per_tier_summary = []
    for t in TIERS:
        names = sorted(per_tier_protocols[t])
        per_tier_summary.append({
            "tier": t,
            "position": tier_position(t),
            "n_protocols_fired": len(names),
            "protocols": names[:5],  # cap the list — full set is in the log
            "is_current": (t == current),
        })

    last_transition = history[-1] if history else None
    direction = None
    if last_transition:
        direction = tier_direction(last_transition.get("from"), last_transition.get("to"))

    return {
        "current_tier": current,
        "current_tier_position": tier_position(current) if current else None,
        "n_tiers_visited": sum(1 for t in TIERS if per_tier_protocols[t]),
        "per_tier": per_tier_summary,
        "last_transition": last_transition,
        "last_transition_direction": direction,
        "transition_count": len(history),
    }


def _handle_tool_slurm_submit(name, arguments, root):
    from research_os.tools.actions.exec.cluster import submit_slurm

    res = submit_slurm(
        root,
        step_id=arguments.get("step_id"),
        cmd=arguments["cmd"],
        job_name=arguments.get("job_name"),
        cpus=arguments.get("cpus"),
        mem=arguments.get("mem"),
        time_limit=arguments.get("time_limit"),
        partition=arguments.get("partition"),
        gpus=arguments.get("gpus"),
        array=arguments.get("array"),
        dependency=arguments.get("dependency"),
        modules=arguments.get("modules"),
        conda_env=arguments.get("conda_env"),
        extra_sbatch=arguments.get("extra_sbatch"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "slurm_submit failed")))


def _handle_tool_slurm_status(name, arguments, root):
    from research_os.tools.actions.exec.cluster import status_slurm

    return _text(_success(status_slurm(root, job_id=arguments.get("job_id"))))


def _handle_tool_slurm_fetch(name, arguments, root):
    from research_os.tools.actions.exec.cluster import fetch_slurm

    return _text(_success(fetch_slurm(
        root, arguments["job_id"],
        poll_interval=int(arguments.get("poll_interval", 30)),
        max_wait=int(arguments.get("max_wait", 7200)),
    )))


def _handle_tool_slurm_list(name, arguments, root):
    from research_os.tools.actions.exec.cluster import list_slurm

    return _text(_success(list_slurm(root)))


# ── Research / reasoning ──────────────────────────────────────────────


def _handle_tool_research_method(name, arguments, root):
    from research_os.tools.actions.research.research import research_method

    res = research_method(arguments["query"], root, limit=int(arguments.get("limit", 5)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "research_method failed")))


def _handle_tool_research_tool(name, arguments, root):
    from research_os.tools.actions.research.research import research_tool

    res = research_tool(arguments["task"], root, language=arguments.get("language", "any"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "research_tool failed")))


def _handle_tool_external_tool_instructions(name, arguments, root):
    from research_os.tools.actions.research.research import external_tool_instructions

    res = external_tool_instructions(
        arguments["tool_name"],
        arguments["purpose"],
        arguments["url"],
        root,
        steps=arguments.get("steps"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "external_tool_instructions failed")))


def _handle_tool_alternative_path_propose(name, arguments, root):
    from research_os.tools.actions.research.research import alternative_path_propose

    res = alternative_path_propose(
        arguments["task"],
        arguments["user_method"],
        root,
        data_summary=arguments.get("data_summary", ""),
        limit=int(arguments.get("limit", 5)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "alternative_path_propose failed")))


def _handle_tool_plan_step(name, arguments, root):
    from research_os.tools.actions.research.research import plan_step

    res = plan_step(
        arguments["goal"], root, max_substeps=int(arguments.get("max_substeps", 6))
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "plan_step failed")))


# ── Intake auto-fill ──────────────────────────────────────────────────


def _handle_tool_intake_autofill(name, arguments, root):
    from research_os.tools.actions.data.intake import intake_autofill

    res = intake_autofill(root, overwrite=bool(arguments.get("overwrite", False)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "intake_autofill failed")))


# ── Background tasks ──────────────────────────────────────────────────


def _handle_tool_task_run(name, arguments, root):
    from research_os.tools.actions.exec.tasks import task_run

    res = task_run(
        arguments["command"],
        root,
        cwd=arguments.get("cwd"),
        description=arguments.get("description", ""),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_run failed")))


def _handle_tool_task_status(name, arguments, root):
    from research_os.tools.actions.exec.tasks import task_status

    res = task_status(
        arguments["task_id"], root, tail_lines=int(arguments.get("tail_lines", 50))
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_status failed")))


def _handle_tool_task_list(name, arguments, root):
    from research_os.tools.actions.exec.tasks import task_list

    res = task_list(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_list failed")))


def _handle_tool_task_kill(name, arguments, root):
    from research_os.tools.actions.exec.tasks import task_kill

    res = task_kill(
        arguments["task_id"], root, signal_name=arguments.get("signal_name", "TERM")
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_kill failed")))


# ── Notebook / R-markdown ─────────────────────────────────────────────


def _handle_tool_notebook_exec(name, arguments, root):
    from research_os.tools.actions.exec.notebook import execute_notebook

    res = execute_notebook(
        arguments["notebook_path"],
        root,
        timeout=int(arguments.get("timeout", 1800)),
        kernel=arguments.get("kernel", "python3"),
        parameters=arguments.get("parameters"),
        output_path=arguments.get("output_path"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "notebook exec failed")))


def _handle_tool_rmarkdown_render(name, arguments, root):
    from research_os.tools.actions.exec.notebook import render_rmarkdown

    res = render_rmarkdown(
        arguments["doc_path"],
        root,
        output_format=arguments.get("output_format", "html_document"),
        timeout=int(arguments.get("timeout", 1800)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "rmarkdown render failed")))


# ── Hypothesis tracking ───────────────────────────────────────────────


def _handle_mem_hypothesis_add(name, arguments, root):
    from research_os.tools.actions.memory.memory import hypothesis_add

    res = hypothesis_add(
        arguments["statement"],
        root,
        hypothesis_id=arguments.get("hypothesis_id"),
        direction=arguments.get("direction"),
        status=arguments.get("status", "testing"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "hypothesis_add failed")))


def _handle_mem_hypothesis_update(name, arguments, root):
    from research_os.tools.actions.memory.memory import hypothesis_update

    res = hypothesis_update(
        arguments["hypothesis_id"],
        root,
        status=arguments.get("status"),
        evidence=arguments.get("evidence"),
        step=arguments.get("step"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "hypothesis_update failed")))


def _handle_mem_hypothesis_list(name, arguments, root):
    from research_os.tools.actions.memory.memory import hypothesis_list

    res = hypothesis_list(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "hypothesis_list failed")))


# ── Iterative planning ───────────────────────────────────────────────


def _handle_tool_plan_next_step(name, arguments, root):
    from research_os.tools.actions.research.planning import plan_next_step

    res = plan_next_step(
        root,
        goal=arguments.get("goal"),
        search_literature=bool(arguments.get("search_literature", True)),
        search_tools=bool(arguments.get("search_tools", True)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "plan_next_step failed")))


def _handle_tool_branch_recommendation(name, arguments, root):
    from research_os.tools.actions.research.planning import branch_recommendation

    res = branch_recommendation(root, reason=arguments["reason"])
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "branch_recommendation failed")))


# ── Scratch ───────────────────────────────────────────────────────────


def _handle_tool_scratch_write(name, arguments, root):
    from research_os.tools.actions.state.scratch import scratch_write

    res = scratch_write(arguments["filename"], arguments["content"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "scratch_write failed")))


def _handle_tool_scratch_run(name, arguments, root):
    from research_os.tools.actions.state.scratch import scratch_run

    res = scratch_run(arguments["filename"], root, timeout=int(arguments.get("timeout", 60)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "scratch_run failed")))


def _handle_tool_scratch_list(name, arguments, root):
    from research_os.tools.actions.state.scratch import scratch_list

    res = scratch_list(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "scratch_list failed")))


def _handle_tool_scratch_clear(name, arguments, root):
    from research_os.tools.actions.state.scratch import scratch_clear

    res = scratch_clear(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "scratch_clear failed")))


# ── Workspace repair ──────────────────────────────────────────────────


def _handle_tool_workspace_repair(name, arguments, root):
    from research_os.tools.actions.state.repair import workspace_repair

    res = workspace_repair(root, dry_run=bool(arguments.get("dry_run", False)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "workspace_repair failed")))


# ── Mid-flow context intake ───────────────────────────────────────────


def _handle_tool_context_intake(name, arguments, root):
    from research_os.tools.actions.data.context_intake import context_intake

    res = context_intake(
        root,
        source_dir=arguments.get("source_dir"),
        dry_run=bool(arguments.get("dry_run", False)),
        also_autofill=bool(arguments.get("also_autofill", False)),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "context_intake failed")))


# ── Verified citations ────────────────────────────────────────────────


def _handle_tool_citations_verify(name, arguments, root):
    from research_os.tools.actions.synthesis.citations import verify_all_in_workspace

    res = verify_all_in_workspace(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "citations_verify failed")))


# ── Session resume / progress digest / dead-end lessons / quick review ─


def _handle_tool_session_resume(name, arguments, root):
    from research_os.tools.actions.research.planning import session_resume

    res = session_resume(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "session_resume failed")))


def _handle_tool_progress_digest(name, arguments, root):
    from research_os.tools.actions.research.planning import progress_digest

    res = progress_digest(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "progress_digest failed")))


def _handle_tool_dead_end_lessons(name, arguments, root):
    from research_os.tools.actions.research.planning import dead_end_lessons

    res = dead_end_lessons(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "dead_end_lessons failed")))


def _handle_tool_quick_review(name, arguments, root):
    from research_os.tools.actions.research.planning import quick_review

    res = quick_review(
        root,
        arguments["paper_path"],
        lens=arguments.get("lens", "claims_vs_evidence"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "quick_review failed")))


def _handle_sys_dep_inventory(name, arguments, root):
    return _text(_success(_optional_dep_inventory()))


def _handle_sys_active_project(name, arguments, root):
    """Report which project root the server resolved for this request."""
    env_root = os.environ.get("RESEARCH_OS_WORKSPACE", "").strip()
    via = "cwd"
    if env_root and Path(env_root).expanduser().resolve() == root:
        via = "RESEARCH_OS_WORKSPACE"
    elif (root / ".os_state").exists():
        via = "cwd→.os_state"
    has_state = (root / ".os_state").exists()
    payload: dict[str, Any] = {
        "project_root": str(root),
        "has_os_state": has_state,
        "resolved_via": via,
    }
    # Only surface the orientation advice when the project isn't
    # scaffolded — that's the only branch the AI needs to act on.
    if not has_state:
        payload["advice"] = (
            "No .os_state/ here — run `research-os init` or open a "
            "scaffolded folder. Project resolution order: "
            "RESEARCH_OS_WORKSPACE env var → cwd walked up → cwd."
        )
    return _text(_success(payload))


def _handle_sys_help(name, arguments, root):
    """Compact AI orientation block — how to use Research OS efficiently."""
    topic = (arguments or {}).get("topic", "").strip().lower()

    # Lean default: orientation only the AI needs on EVERY call lives
    # here; deep cuts (protocol categories, anti-patterns, docs index)
    # are one `topic=` request away when the AI actually needs them.
    core = {
        "namespaces": {
            "sys_*":  "workspace / state / files / paths / checkpoints",
            "tool_*": "research work (search / exec / audit / synthesis / plan)",
            "mem_*":  "append-only memory (methods / decisions / hypotheses / citations)",
        },
        "session_start": (
            "Every turn starts with a researcher message. On the FIRST "
            "turn of the session, sys_boot is your 1st MCP call and "
            "tool_route(prompt=their message) is your 2nd — fire them "
            "back-to-back. Then: tool_plan_turn if complexity=high; else "
            "shortcut_tool. On subsequent turns, skip sys_boot and go "
            "straight to tool_route."
        ),
        "when_uncertain": (
            "If tool_route returns ask_user, ask THAT question and re-route. "
            "Never guess. If nothing matches (resolved_level=0), follow the "
            "fallback's L1 menu prompt instead of loading a random protocol."
        ),
        "topics": [
            "synthesis", "methodology", "visualization", "audit",
            "literature", "writing", "routing", "iteration", "overrides",
            "recovery", "fields", "depth", "categories",
            "anti_patterns", "docs",
        ],
        "hint": "Call sys_help again with topic=<one of topics> for detail.",
    }
    if topic in {"categories", "protocols"}:
        return _text(_success({"protocol_categories": {
            "guidance": "session/flow (boot/resume/handoff/autopilot/casual/mid_entry/disagree/revise)",
            "discover": "intake + question lock-in + mid-pipeline entry",
            "domain": "domain classification + study design",
            "methodology": "method picking + per-method protocols (42)",
            "literature": "search + systematic review + GRADE + comparative review",
            "writing": "per-section drafting (methods/results/discussion/limitations/end-matter)",
            "visualization": "figures (rules/workflow/critique/multi-panel/arc/a11y)",
            "synthesis": "final deliverables (18: paper/poster/dashboard/slides/...)",
            "audit": "quality audit + pre-submission checklist + provenance completeness",
            "reproducibility": "snapshot + verify reruns",
        }}))
    if topic == "anti_patterns":
        return _text(_success({"anti_patterns": [
            "Don't call sys_state_get + sys_config_get + sys_protocol_history separately — sys_boot bundles them.",
            "Don't load full protocols when summary suffices (~300 tok vs 1.5-3K).",
            "Don't one-shot 400-line scripts — tool_step_pipeline_define + atomic sub-tasks.",
            "Don't invent citations — synthesis tools VERIFY every citation against Crossref/S2/PubMed/arXiv.",
            "Don't pick a method or library from training memory — tool_research_method / tool_research_tool first.",
            "Don't write under inputs/raw_data or inputs/literature (immutable; server blocks it).",
            "Don't skip the ask_user from tool_route — asking once costs less than picking wrong.",
            "Don't re-route after the researcher already picked one — use tool_plan_clear if they pivoted.",
            "Don't bypass a quality gate without override_rationale — the pre-submission audit will surface every silent bypass.",
            "Don't reuse a stale _v<n> filename — bump or call tool_step_iterate before editing scripts.",
            "Don't submit without audit/pre_submission_checklist — it catches what reviewers will catch.",
            "Don't push back on every choice — load guidance/constructive_disagreement only when evidence is unambiguous and the choice affects claims.",
        ]}))
    if topic == "routing":
        return _text(_success({
            "decision_tree": [
                "0. Every turn is triggered by a researcher message — you don't act before one arrives.",
                "1. First turn of the session: sys_boot is your 1st MCP call. Returns pause + active_plan + next_protocol.",
                "2. active_plan in progress (from a previous turn) → tool_plan_turn → walk it.",
                "3. pause_classification = ctx_exhaustion / mid_step → guidance/session_resume.",
                "4. Otherwise: tool_route(prompt=their verbatim message) is your 2nd MCP call.",
                "5. resolved_level=3 + complexity=low → call shortcut_tool OR load protocol summary.",
                "6. resolved_level=3 + complexity=high → tool_plan_turn then advance per step.",
                "7. resolved_level<3 OR ask_user non-null → ASK the question, re-route.",
                "8. resolved_level=0 → use the fallback ask_user; never guess a protocol.",
                "9. Subsequent turns: skip sys_boot — its payload is still in context — go straight to tool_route or continue the active plan.",
            ],
            "ambiguity_handling": (
                "L1 ties → ask which work-type. L2 ties → ask which sub-intent within the class. "
                "L3 ties (top two within 2 points) → ask which protocol. ALL three asks are "
                "one-sentence — cheaper than loading the wrong YAML."
            ),
            "complexity_signals": [
                ">18 words OR multiple verbs OR conjunctions ('and then', 'also', 'plus')",
                "deliverable phrases: 'full project', 'end to end', 'from scratch', 'wake me when', 'ship it'",
                "→ persisted active_plan; walk via tool_plan_turn + tool_plan_advance",
            ],
            "after_routing": "sys_active_tools(protocol_name) → ~10-15 tool shortlist for that protocol.",
        }))
    if topic == "iteration":
        return _text(_success({
            "modes": {
                "bug_fix": (
                    "Script has a defect. Bump _v<n>, re-run via tool_step_pipeline_run. "
                    "Content-hash cache invalidates affected nodes automatically. "
                    "No tool_step_iterate call needed — the live filename history (v1→v2→v3) is the audit trail."
                ),
                "deliberate_iteration": (
                    "Coordinated change (recolour Fig 2, tighten cutoff, swap model spec). "
                    "FIRST call tool_step_iterate(step_id, rationale=…) — snapshots scripts + "
                    "outputs + caption / summary / prov sidecars + conclusion into .versions/v<n>/. "
                    "Live filenames stay stable so cross-step references in conclusions / "
                    "dashboards don't rot. Then rename via the returned next_script_paths and re-run."
                ),
            },
            "after_either": (
                "Run tool_audit_version_coherence to confirm every output traces to the "
                "highest-version script on disk. Drift (a v2 figure produced by a v1 script) "
                "lands in workspace/logs/version_coherence.md."
            ),
            "common_mistake": (
                "Editing scripts in place without bumping _v<n>. The previous output's .prov.json "
                "still points at the old script name — content-hash invalidation works but the "
                "audit trail loses the iteration's history."
            ),
        }))
    if topic == "overrides":
        return _text(_success({
            "policy_levels": {
                "enforce": "default — AI refuses to bypass without an explicit current-message ask.",
                "allow_override": "AI may bypass when asked; logs the rationale.",
                "warn_only": "gate blockers become warnings (sandbox use only).",
            },
            "how_to_bypass": [
                "tool_synthesize(override_completeness_gate=true, override_rationale='<why>')",
                "tool_dashboard(operation='create', override_completeness_gate=true, override_rationale='<why>')",
                "tool_plan_advance(override_gate=true, override_rationale='<why>')",
            ],
            "rules": [
                "Authorisation must be in the researcher's CURRENT message ('skip the audit', 'just draft it', 'preview only').",
                "override_rationale is mandatory — silent bypass is a hard rule violation.",
                "Each bypass appends to workspace/logs/override_log.md.",
                "audit/pre_submission_checklist surfaces every unresolved bypass; RED if unresolved + no rationale.",
                "Hard rules (no fabricated citations, no inputs/raw_data writes) are absolute — the quality gate is the ONLY authorised escape hatch.",
            ],
        }))
    if topic == "recovery":
        return _text(_success({
            "stuck_paths": {
                "broken_workspace": "tool_workspace_repair — heals manifest + state-ledger drift, lazy-dir leftovers.",
                "dead_end_in_step": "sys_path(operation='abandon') + tool_lessons(operation='dead_end') + tool_plan_next_step.",
                "context_full": "sys_session_handoff + 'pick up where we left off' in fresh chat → guidance/session_resume.",
                "lost_active_project": "sys_active_project — returns resolved root + how resolved.",
                "lost_protocol": "sys_protocol_next (pipeline) or sys_protocol_list (browse).",
                "mid_plan_pivot": "tool_plan_clear — discard plan; re-tool_route on the new ask.",
            },
            "checkpoint_safety": (
                "sys_checkpoint_create BEFORE risky moves; sys_checkpoint_rollback restores. "
                "Hardlinked, fast. Always rollback to a checkpoint instead of `git reset --hard`."
            ),
            "missing_dependencies": (
                "sys_dep_inventory reports what failed to import. Tools that need the missing dep raise "
                "RuntimeError with 'pip install research-os[all]' instructions."
            ),
        }))
    if topic == "fields":
        return _text(_success({
            "principle": (
                "Research OS is FIELD-AGNOSTIC by design. Protocols name questions and "
                "grounding sources, not domain-specific methods. Every method choice "
                "comes from the literature via tool_research_method — never from training memory."
            ),
            "subfield_pipelines": (
                "For multi-stage canonical pipelines (snRNA-seq, metagenomics, protein "
                "embeddings, fMRI, MD), load methodology/deep_domain_research FIRST. It "
                "identifies the subfield from real signals (file names, columns, context), "
                "surveys ≥3 cited sources, proposes a stage × tool × runtime skeleton, "
                "and writes an assumption matrix per stage."
            ),
            "domain_specific_protocols": [
                "clinical_trials (CONSORT)",
                "qualitative_research (COREQ/SRQR)",
                "qualitative_quality_audit (saturation + intercoder + reflexivity)",
                "survey_psychometrics (EFA/CFA/IRT)",
                "cox_ph_diagnostics (survival)",
                "meta_analysis (random/fixed effects)",
                "bayesian_analysis (priors → posterior → checks)",
                "timeseries_analysis (forecasting / state-space)",
                "causal_inference_deep (DAG / IV / DiD / RDD)",
                "ablation_study (component-by-component)",
                "simulation_studies (ADEMP Monte Carlo)",
                "mixed_methods (concurrent / sequential)",
            ],
            "cross_disciplinary": (
                "When signals point to two subfields, deep_domain_research recommends running it "
                "once per subfield. Methodology decisions per stage cite the SUBFIELD's literature, "
                "not a generic table."
            ),
            "reporting_standards": (
                "domain_analysis classifies the field and picks the canonical reporting standard "
                "(CONSORT / PRISMA / STROBE / ARRIVE / TRIPOD-AI / SRQR / COREQ / SAGER / etc.). "
                "pre_submission_checklist verifies the right completed form is on file."
            ),
        }))
    if topic == "depth":
        return _text(_success({
            "depth_gradient": [
                "5-minute napkin     → guidance/casual_exploration",
                "30-minute appraisal → guidance/quick_paper_review",
                "Real EDA            → methodology/exploratory_data_analysis",
                "Per-step pipeline   → guidance/analysis_plan",
                "Method head-to-head → methodology/method_comparison",
                "Subfield-canonical  → methodology/deep_domain_research",
                "Systematic synthesis → literature/systematic_review",
                "Publication-grade   → synthesis/synthesis_paper",
            ],
            "expertise_levels": {
                "beginner":     "AI explains more; more confirmation gates; offers method consultation freely.",
                "intermediate": "default — concise; asks only on real ambiguity.",
                "advanced":     "fewer reminders; expects literature-grounded justifications without prompting.",
                "pi":           "AI defers to declared direction unless evidence contradicts (constructive_disagreement).",
            },
            "model_profile_effect": (
                "small  → 1 step/turn, terser protocols, lighter tool descriptions; "
                "medium → 3 steps/turn (default); "
                "large  → 6 steps/turn, full protocol detail, multi-step planning."
            ),
        }))
    if topic in {"literature"}:
        return _text(_success({
            "literature_protocols": {
                "literature_search": "multi-database search + dedup + PRISMA accounting + forward-citation walk + predatory-venue flag.",
                "systematic_review": "full PRISMA workflow.",
                "evidence_synthesis": "GRADE-style grading + contradiction detection.",
                "comparative_paper_review": "compare-and-contrast 2-N papers (journal club / related work / foundational).",
            },
            "search_tools": [
                "tool_search_semantic_scholar",
                "tool_search_pubmed",
                "tool_search_crossref",
                "tool_search_arxiv",
                "tool_search_web",
                "tool_literature_search_and_save  (combined search + download)",
            ],
            "after_search": "mem_citations_generate → workspace/citations.md. tool_citations_verify → online resolve every cite.",
        }))
    if topic in {"writing"}:
        return _text(_success({
            "writing_protocols": {
                "writing_core": "universal rules — voice, tense, banned phrases, vague quantifiers, anti-bullshit signals, numbered claim grounding.",
                "writing_methods": "Methods section + workspace/methods.md format.",
                "writing_results": "Results — report numbers; defer interpretation; full statistical form.",
                "writing_discussion": "Discussion — principal findings, alternative explanations, scope-limited implications.",
                "writing_limitations": "Limitations — no boilerplate; each limitation paired with downstream implication.",
                "writing_conclusions": "Per-step conclusions.md format.",
                "writing_citations": "workspace/citations.md maintenance.",
                "writing_readme": "Project + per-step READMEs.",
                "writing_analysis_log": "Structured entries in workspace/analysis.md.",
                "writing_data_availability": "End matter — data / code / CRediT / funding / COI / acknowledgements.",
            },
            "audits_attached": [
                "tool_audit_prose (hedging / vague / passive / causal-language)",
                "tool_audit_claims (every number traces to an artefact or verified citation)",
            ],
        }))
    if topic == "docs":
        return _text(_success({"docs_for_humans": [
            "docs/START.md            — install + first project + cheatsheet",
            "docs/RESEARCHER_GUIDE.md — full workflow walkthrough",
            "docs/USE_CASES.md        — role × goal × output map",
            "docs/SETUP.md            — per-IDE wiring",
            "docs/PROTOCOLS.md        — every protocol + triggers + quality bars",
            "docs/TOOLS.md            — every MCP tool with example calls",
            "docs/AI_GUIDE.md         — operating manual for the AI",
            "docs/PROTOCOL_DOCTRINE.md — scaffold-not-script principle",
            "docs/FAQ.md              — common questions",
            "docs/SHARING.md          — share-safe zip + GitHub paths",
        ]}))

    if topic in {"synthesis", "deliverable", "deliverables"}:
        return _text(_success({
            "synthesis_protocols": {
                "synthesis_paper": "IMRAD paper, venue-tailored",
                "synthesis_abstract": "structured / unstructured / preprint",
                "synthesis_poster": "billboard / classic LaTeX poster + QR",
                "synthesis_dashboard": "offline HTML dashboard, Playwright-tested",
                "synthesis_slides": "talks (lab / conference / defense / invited / teaching)",
                "synthesis_grant": "grant narrative (R01 / NSF / Wellcome / ERC)",
                "synthesis_report": "internal / client / technical / policy report",
                "synthesis_lay_summary": "public / press / patient / funder / blog / social",
                "synthesis_progress_update": "PI / advisor / lab / stand-up update",
                "synthesis_handout": "single-page printable leave-behind + QR",
                "synthesis_from_inputs": "synthesis when prior analysis ran outside RO",
                "synthesis_null_findings": "publishable companion for refuted / abandoned",
                "synthesis_cover_letter": "journal cover letter",
                "synthesis_title_workshop": "title generation + iteration",
            },
            "support_protocols": {
                "writing/writing_discussion": "Discussion section",
                "writing/writing_limitations": "Limitations sub-section",
                "writing/writing_results": "Results section",
                "writing/writing_methods": "Methods section",
                "writing/writing_data_availability": "end matter — CRediT / data / code / etc.",
                "writing/writing_core": "universal writing rules",
                "audit/pre_submission_checklist": "final ready-to-submit gate",
            },
        }))
    if topic in {"methodology", "methods"}:
        return _text(_success({
            "picker_protocols": ["methodology/methodology_selection", "methodology/deep_domain_research"],
            "per_method": [
                "causal_inference_deep", "machine_learning", "clinical_trials",
                "meta_analysis", "survey_psychometrics", "qualitative_research",
                "simulation_studies", "replication_study", "ablation_study",
                "pilot_study", "mixed_methods", "bayesian_analysis",
                "timeseries_analysis",
            ],
            "design_protocols": [
                "exploratory_data_analysis", "method_comparison",
                "data_quality_audit", "power_analysis", "evaluation_design",
                "hyperparameter_search_design", "data_ethics_review",
            ],
            "support": ["preregistration", "methodological_consultation",
                        "reproduction_attempt", "tool_discovery"],
        }))
    if topic in {"visualization", "viz", "figures"}:
        return _text(_success({
            "rules": "visualization/figure_guidelines",
            "workflow": "visualization/visualization_workflow",
            "critique": "visualization/figure_critique",
            "multi_panel": "visualization/multi_panel_composition",
            "arc": "visualization/figure_narrative_arc",
            "a11y": "visualization/color_accessibility_audit",
        }))
    if topic in {"audit", "quality"}:
        return _text(_success({
            "master_audit": "audit/audit_and_validation",
            "pre_submission": "audit/pre_submission_checklist",
            "reproducibility": "reproducibility/reproducibility",
            "specific_audits": [
                "tool_audit_step_completeness",
                "tool_audit_version_coherence",
                "tool_audit_code_quality",
                "tool_audit_prose",
                "tool_audit_claims",
                "tool_audit_figure_full",
                "tool_audit_citations",
                "tool_audit_assumptions",
                "tool_audit_reproducibility",
                "tool_preregister_diff",
            ],
            "iteration_versioning": {
                "snapshot": "tool_step_iterate",
                "list": "tool_step_iterations_list",
                "drift_check": "tool_audit_version_coherence",
            },
        }))

    return _text(_success(core))


# ---------------------------------------------------------------------------
# Reliability / failure / freshness / coherence handlers.
# ---------------------------------------------------------------------------


def _handle_tool_reliability_log_event(name, arguments, root):
    from research_os.tools.actions.state.reliability import log_event
    return _text(log_event(
        root,
        str(arguments.get("event_type", "")),
        protocol_name=arguments.get("protocol_name"),
        model_profile=arguments.get("model_profile"),
        payload=arguments.get("payload") or {},
    ))


def _handle_tool_reliability_report(name, arguments, root):
    from research_os.tools.actions.state.reliability import reliability_report
    return _text(reliability_report(root))


def _handle_tool_state_freshness_check(name, arguments, root):
    from research_os.tools.actions.state.freshness import state_freshness_check
    days = arguments.get("stale_after_days")
    kwargs = {}
    if isinstance(days, (int, float)) and days > 0:
        kwargs["stale_after_days"] = int(days)
    return _text(state_freshness_check(root, **kwargs))


def _handle_tool_audit_coherence(name, arguments, root):
    from research_os.tools.actions.audit.coherence import audit_coherence
    return _text(audit_coherence(
        root,
        paper_path=str(arguments.get("paper_path") or "synthesis/paper.md"),
    ))


def _handle_tool_failure_record(name, arguments, root):
    from research_os.tools.actions.state.paywall_memory import record_failure
    return _text(record_failure(
        root,
        tool=str(arguments.get("tool", "")),
        target=str(arguments.get("target", "")),
        reason=str(arguments.get("reason", "")),
        error_text=str(arguments.get("error_text", "")),
        permanent=bool(arguments.get("permanent", False)),
    ))


def _handle_tool_failure_check(name, arguments, root):
    from research_os.tools.actions.state.paywall_memory import is_known_bad
    return _text(is_known_bad(root, str(arguments.get("target", ""))))


def _handle_tool_failure_list(name, arguments, root):
    from research_os.tools.actions.state.paywall_memory import list_failures
    limit = arguments.get("limit")
    if isinstance(limit, (int, float)) and limit > 0:
        return _text(list_failures(root, limit=int(limit)))
    return _text(list_failures(root))


def _handle_tool_intake_freshness(name, arguments, root):
    from research_os.tools.actions.data.intake_freshness import intake_freshness
    days = arguments.get("fresh_window_days")
    kwargs = {}
    if isinstance(days, (int, float)) and days > 0:
        kwargs["fresh_window_days"] = int(days)
    return _text(intake_freshness(root, **kwargs))


def _handle_tool_writing_discussion_from_verdicts(name, arguments, root):
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        emit_discussion_paragraphs,
    )
    return _text(emit_discussion_paragraphs(root))


def _handle_tool_discussion_coverage_audit(name, arguments, root):
    from research_os.tools.actions.synthesis.discussion_from_verdicts import (
        discussion_coverage_audit,
    )
    from research_os.project_ops import log_override
    from research_os.tools.actions.state.config import get_interaction_policy

    override_requested = bool(arguments.get("override_discussion_coverage", False))
    rationale = arguments.get("override_rationale")
    policy = get_interaction_policy(root)["quality_gate_policy"]
    if (policy == "enforce" and override_requested
            and (not rationale or not str(rationale).strip())):
        return _text(_error(
            "interaction.quality_gate_policy=enforce: "
            "override_discussion_coverage=true requires override_rationale."
        ))
    res = discussion_coverage_audit(root)
    if res.get("blockers") and override_requested:
        log_override(
            root,
            tool="tool_discussion_coverage_audit",
            gate="discussion_coverage",
            rationale=rationale or "",
            extra={"uncovered_count": res.get("uncovered_count", 0)},
        )
        res["override_applied"] = True
        res["status"] = "success"
    return _text(res)


# Adaptive-friction + quick-mode handlers.


def _handle_tool_rigor_signals_scan(name, arguments, root):
    from research_os.tools.actions.state.rigor_signals import rigor_signals_scan
    return _text(rigor_signals_scan(root))


def _handle_tool_resolve_gate_strictness(name, arguments, root):
    from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness
    return _text(resolve_gate_strictness(root))


def _handle_tool_self_certify(name, arguments, root):
    from research_os.tools.actions.state.certifications import self_certify
    return _text(self_certify(
        root,
        domain=str(arguments.get("domain", "")),
        scope=str(arguments.get("scope", "")),
        rationale=str(arguments.get("rationale", "")),
    ))


def _handle_tool_list_certifications(name, arguments, root):
    from research_os.tools.actions.state.certifications import list_certifications
    return _text(list_certifications(root))


def _handle_tool_quick_route(name, arguments, root):
    from research_os.tools.actions.state.quick_mode import quick_route
    return _text(quick_route(root, str(arguments.get("prompt", ""))))


def _handle_tool_promote_to_step(name, arguments, root):
    from research_os.tools.actions.state.quick_mode import promote_to_step
    return _text(promote_to_step(
        root,
        scratch_path=str(arguments.get("scratch_path", "")),
        step_slug=str(arguments.get("step_slug", "")),
        rationale=str(arguments.get("rationale", "")),
    ))


def _handle_tool_project_tier_strictness(name, arguments, root):
    from research_os.tools.actions.state.quick_mode import project_tier_strictness
    return _text(project_tier_strictness(root))


# Lean variants / dry-run / bundling / coaching handlers (Themes 2/13/15/7).


def _handle_tool_dry_run(name, arguments, root):
    from research_os.tools.actions.protocol import load_protocol
    pname = arguments.get("protocol_name") or ""
    if not pname:
        return _text({"status": "error", "message": "protocol_name is required"})
    try:
        out = load_protocol(pname, format="dryrun")
        out["simulated_args"] = arguments.get("simulated_args") or {}
        return _text(out)
    except (FileNotFoundError, ValueError) as e:
        return _text({"status": "error", "message": str(e)})


def _handle_tool_step_complete(name, arguments, root):
    step_id = arguments.get("step_id") or ""
    if not step_id:
        return _text({"status": "error", "message": "step_id is required"})
    override_lit = bool(arguments.get("override_literature_gate"))
    rationale = arguments.get("override_rationale") or ""

    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.tools.actions.audit.step_literature import audit_step_literature
    from research_os.tools.actions.state.path import finalize_path
    from research_os.tools.actions.state.revision import step_revision_options

    merged = {"step_id": step_id, "stages": {}}
    statuses: list[str] = []
    try:
        merged["stages"]["finalize"] = finalize_path(step_id, root)
        statuses.append(merged["stages"]["finalize"].get("status", "success"))
    except Exception as e:
        merged["stages"]["finalize"] = {"status": "error", "message": str(e)}
        statuses.append("error")
    try:
        merged["stages"]["completeness"] = audit_step_completeness(root, step_id=step_id)
        statuses.append(merged["stages"]["completeness"].get("status", "success"))
    except Exception as e:
        merged["stages"]["completeness"] = {"status": "error", "message": str(e)}
        statuses.append("error")
    try:
        lit = audit_step_literature(root, step_id=step_id)
        if override_lit and rationale:
            lit["overridden"] = True
            lit["override_rationale"] = rationale
            if lit.get("status") == "error":
                lit["status"] = "warning"
        merged["stages"]["literature"] = lit
        statuses.append(lit.get("status", "success"))
    except Exception as e:
        merged["stages"]["literature"] = {"status": "error", "message": str(e)}
        statuses.append("error")
    try:
        merged["stages"]["revision"] = step_revision_options(step_id, root)
        statuses.append(merged["stages"]["revision"].get("status", "success"))
    except Exception as e:
        merged["stages"]["revision"] = {"status": "error", "message": str(e)}
        statuses.append("error")

    if "error" in statuses:
        merged["overall_status"] = "error"
    elif "warning" in statuses:
        merged["overall_status"] = "warning"
    else:
        merged["overall_status"] = "success"

    # Phase 8 — advance current_tier when the just-finished step's
    # protocol moves the project across a tier boundary. Best-effort;
    # never fails the bundle. tier_transition is null when no protocol
    # is associated with the step, or when the new tier matches the
    # current one.
    try:
        from research_os.tools.actions.router import _resolve_tier
        from research_os.tools.actions.state.tier_state import set_current_tier
        next_proto = _latest_protocol_for_step(root, step_id)
        if next_proto:
            new_tier = _resolve_tier(next_proto)
            if new_tier:
                trans = set_current_tier(
                    root,
                    new_tier,
                    source_protocol=next_proto,
                    via="tool_step_complete",
                )
                merged["tier_transition"] = trans
                merged["tier"] = new_tier
    except Exception as exc:
        logger.debug("tier advance on step_complete failed: %s", exc)

    merged["_note"] = (
        "Bundle result. Surface revision_options verbatim per the "
        "anti-one-shot doctrine; do not auto-scaffold the next step "
        "unless autonomy_level='autopilot'."
    )
    return _text(merged)


def _latest_protocol_for_step(root, step_id: str) -> str | None:
    """Resolve the protocol most likely "owned" by ``step_id``.

    Heuristics, cheapest first (all best-effort):
      1. ``.os_state/active_plan.json`` — the most recent route's primary.
      2. The latest entry in ``protocol_execution_log.jsonl``.

    Returns the bare protocol name (e.g. ``guidance/analysis_plan``) or
    None when nothing was logged yet.
    """
    import json as _json
    plan_path = root / ".os_state" / "active_plan.json"
    if plan_path.exists():
        try:
            plan = _json.loads(plan_path.read_text())
            pp = plan.get("primary_protocol")
            if isinstance(pp, str) and pp:
                return pp
        except Exception:
            pass
    log_path = root / ".os_state" / "protocol_execution_log.jsonl"
    if log_path.exists():
        try:
            last_proto = None
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = _json.loads(line)
                except Exception:
                    continue
                pn = entry.get("protocol") or entry.get("protocol_name")
                if pn:
                    last_proto = pn
            if last_proto:
                return last_proto
        except Exception:
            pass
    return None


def _handle_tool_mistake_replay(name, arguments, root):
    from research_os.tools.actions.state.mistake_replay import mistake_replay
    limit = arguments.get("limit") or 5
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5
    return _text(mistake_replay(root, limit=limit))


# ── consolidated handlers ─────────────────────────────


def _handle_tool_plan(name, arguments, root):
    """Unified plan dispatcher (turn | advance | clear).

    Selects op by:
      1. Explicit `operation` arg.
      2. Legacy: invoked under tool_plan_turn / _advance / _clear.
    """
    legacy = {
        "tool_plan_turn": "turn",
        "tool_plan_advance": "advance",
        "tool_plan_clear": "clear",
    }
    operation = arguments.get("operation") or legacy.get(name)
    if not operation:
        return _text(_error(
            "tool_plan requires operation='turn'|'advance'|'clear'"
        ))
    if operation == "turn":
        return _handle_tool_plan_turn(name, arguments, root)
    if operation == "advance":
        return _handle_tool_plan_advance(name, arguments, root)
    if operation == "clear":
        return _handle_tool_plan_clear(name, arguments, root)
    return _text(_error(f"Unknown plan operation '{operation}'"))


def _handle_sys_path(name, arguments, root):
    """Unified path dispatcher (create | abandon | list)."""
    legacy = {
        "sys_path_create": "create",
        "sys_path_abandon": "abandon",
        "sys_path_list": "list",
    }
    operation = arguments.get("operation") or legacy.get(name)
    if not operation:
        return _text(_error(
            "sys_path requires operation='create'|'abandon'|'list'"
        ))
    if operation == "create":
        return _handle_sys_path_create(name, arguments, root)
    if operation == "abandon":
        return _handle_sys_path_abandon(name, arguments, root)
    if operation == "list":
        return _handle_sys_path_list(name, arguments, root)
    return _text(_error(f"Unknown sys_path operation '{operation}'"))


def _handle_tool_ground(name, arguments, root):
    """Unified grounding-register dispatcher.

    mode='explicit'  → tool_grounding_register (sources list)
    mode='from_context' → tool_ground_from_context (context_paths list)
    """
    mode = arguments.get("mode")
    if not mode:
        if name == "tool_ground_from_context" or "context_paths" in arguments:
            mode = "from_context"
        else:
            mode = "explicit"
    if mode == "explicit":
        return _handle_tool_grounding_register(name, arguments, root)
    if mode == "from_context":
        return _handle_tool_ground_from_context(name, arguments, root)
    return _text(_error(
        f"Unknown ground mode '{mode}'. Use 'explicit' or 'from_context'."
    ))


def _handle_tool_verify(name, arguments, root):
    """Unified verify dispatcher.

    scope='claim'   → tool_claim_verify (claim + verifications list)
    scope='project' → tool_grounding_verify (whole-project sweep)
    """
    scope = arguments.get("scope")
    if not scope:
        if name == "tool_grounding_verify" or not arguments.get("claim"):
            scope = "project"
        else:
            scope = "claim"
    if scope == "claim":
        return _handle_tool_claim_verify(name, arguments, root)
    if scope == "project":
        return _handle_tool_grounding_verify(name, arguments, root)
    return _text(_error(
        f"Unknown verify scope '{scope}'. Use 'claim' or 'project'."
    ))


def _handle_tool_lessons(name, arguments, root):
    """Unified lessons + failure-memory dispatcher.

    Operations:
      record         → tool_lessons_record (Reflexion-style lesson append)
      consult        → tool_lessons_consult (retrieve top-K prior lessons)
      failure_record → tool_failure_record (paywall / 404 / permanent-error memory)
      failure_check  → tool_failure_check (is this URL/DOI known-bad?)
      failure_list   → tool_failure_list (recent tool failures)
      dead_end       → tool_dead_end_lessons (pull lessons from __DEAD_END folders)
      mistake_replay → tool_mistake_replay (recurring patterns from reliability + override log)
    """
    legacy = {
        "tool_lessons_record":   "record",
        "tool_lessons_consult":  "consult",
        "tool_failure_record":   "failure_record",
        "tool_failure_check":    "failure_check",
        "tool_failure_list":     "failure_list",
        "tool_dead_end_lessons": "dead_end",
        "tool_mistake_replay":   "mistake_replay",
    }
    op = arguments.get("operation") or legacy.get(name)
    if not op:
        # Heuristic fallback for the original tool_lessons surface.
        op = "consult" if "task" in arguments else "record"
    if op == "record":
        return _handle_tool_lessons_record(name, arguments, root)
    if op == "consult":
        return _handle_tool_lessons_consult(name, arguments, root)
    if op == "failure_record":
        return _handle_tool_failure_record(name, arguments, root)
    if op == "failure_check":
        return _handle_tool_failure_check(name, arguments, root)
    if op == "failure_list":
        return _handle_tool_failure_list(name, arguments, root)
    if op == "dead_end":
        return _handle_tool_dead_end_lessons(name, arguments, root)
    if op == "mistake_replay":
        return _handle_tool_mistake_replay(name, arguments, root)
    return _text(_error(f"Unknown lessons operation '{op}'"))


def _handle_tool_reliability(name, arguments, root):
    """Unified reliability-log dispatcher.

    Operations:
      log_event → tool_reliability_log_event (append structural event)
      report    → tool_reliability_report   (redacted markdown summary)
    """
    legacy = {
        "tool_reliability_log_event": "log_event",
        "tool_reliability_report":    "report",
    }
    op = arguments.get("operation") or legacy.get(name)
    if not op:
        # Heuristic: presence of event_type implies log_event; otherwise report.
        op = "log_event" if "event_type" in arguments else "report"
    if op == "log_event":
        return _handle_tool_reliability_log_event(name, arguments, root)
    if op == "report":
        return _handle_tool_reliability_report(name, arguments, root)
    return _text(_error(f"Unknown reliability operation '{op}'"))


def _handle_mem_log(name, arguments, root):
    """Unified memory-log dispatcher.

    kind='methods'    → mem_methods_append
    kind='decision'   → mem_decision_log
    kind='hypothesis' → mem_hypothesis_update
    kind='analysis'   → mem_analysis_log
    """
    legacy = {
        "mem_methods_append": "methods",
        "mem_decision_log": "decision",
        "mem_hypothesis_update": "hypothesis",
        "mem_analysis_log": "analysis",
    }
    kind = arguments.get("kind") or legacy.get(name)
    if not kind:
        return _text(_error(
            "mem_log requires kind='methods'|'decision'|'hypothesis'|'analysis'"
        ))
    if kind == "methods":
        return _handle_mem_methods_append(name, arguments, root)
    if kind == "decision":
        return _handle_mem_decision_log(name, arguments, root)
    if kind == "hypothesis":
        return _handle_mem_hypothesis_update(name, arguments, root)
    if kind == "analysis":
        return _handle_mem_analysis_log(name, arguments, root)
    return _text(_error(f"Unknown mem_log kind '{kind}'"))


def _handle_tool_deprecations_summary(name, arguments, root):
    """Aggregate counts from .os_state/deprecations.log."""
    log_path = root / ".os_state" / "deprecations.log"
    if not log_path.exists():
        return _text(_success({
            "total": 0,
            "by_kind": {},
            "by_source": {},
            "by_target": {},
            "note": "No deprecations.log yet. Aliases / redirects haven't been invoked.",
        }))
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_target: dict[str, int] = {}
    total = 0
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                total += 1
                k = e.get("kind", "unknown")
                by_kind[k] = by_kind.get(k, 0) + 1
                s = e.get("source", "")
                if s:
                    by_source[s] = by_source.get(s, 0) + 1
                t = e.get("target", "")
                if t:
                    by_target[t] = by_target.get(t, 0) + 1
    except Exception as e:
        return _text(_error(str(e)))
    return _text(_success({
        "total": total,
        "by_kind": dict(sorted(by_kind.items())),
        "by_source": dict(sorted(by_source.items(), key=lambda x: -x[1])),
        "by_target": dict(sorted(by_target.items(), key=lambda x: -x[1])),
        "log_path": ".os_state/deprecations.log",
        "advice": (
            "Replace deprecated names with their consolidated counterparts "
            "before the next major (when aliases / redirect stubs will be removed). "
            "See docs/MIGRATION.md for the full table."
        ),
    }))


_HANDLERS = {
    # routing (call these first)
    "sys_boot": _handle_sys_boot,
    "tool_route": _handle_tool_route,
    "tool_semantic_route": _handle_tool_semantic_route,
    "sys_semantic_tool_search": _handle_sys_semantic_tool_search,
    "tool_plan_advance": _handle_tool_plan_advance,
    "tool_plan_turn": _handle_tool_plan_turn,
    "tool_plan_clear": _handle_tool_plan_clear,
    "sys_tool_describe": _handle_sys_tool_describe,
    "sys_active_tools": _handle_sys_active_tools,
    "sys_active_project": _handle_sys_active_project,
    "sys_help": _handle_sys_help,
    "tool_cache_clear": _handle_tool_cache_clear,
    "tool_workflow_dag": _handle_tool_workflow_dag,
    # protocol
    "sys_protocol_get": _handle_sys_protocol_get,
    "sys_protocol_list": _handle_sys_protocol_list,
    "tool_protocols_list": _handle_tool_protocols_list,
    "tool_tools_list": _handle_tool_tools_list,
    "sys_protocol_next": _handle_sys_protocol_next,
    "sys_protocol_validate": _handle_sys_protocol_validate,
    "sys_protocol_log": _handle_sys_protocol_log,
    "sys_protocol_history": _handle_sys_protocol_history,
    # state / workspace
    "sys_state_get": _handle_sys_state_get,
    "sys_workspace_scaffold": _handle_sys_workspace_scaffold,
    "sys_workspace_tree": _handle_sys_workspace_tree,
    # files
    "sys_file_read": _handle_sys_file_read,
    "sys_file_write": _handle_sys_file_write,
    "sys_file_list": _handle_sys_file_list,
    "sys_file_delete": _handle_sys_file_delete,
    "sys_file_validate_md": _handle_sys_file_validate_md,
    # paths
    "sys_path_create": _handle_sys_path_create,
    "sys_path_abandon": _handle_sys_path_abandon,
    "sys_path_list": _handle_sys_path_list,
    "tool_path_finalize": _handle_tool_path_finalize,
    "tool_synthesis_curate_figures": _handle_tool_synthesis_curate_figures,
    "sys_export_share_archive": _handle_sys_export_share_archive,
    # checkpoints
    "sys_checkpoint_create": _handle_sys_checkpoint_create,
    "sys_checkpoint_rollback": _handle_sys_checkpoint_rollback,
    "sys_checkpoint_list": _handle_sys_checkpoint_list,
    # config
    "sys_config_get": _handle_sys_config_get,
    "sys_config_set": _handle_sys_config_set,
    "sys_config_validate": _handle_sys_config_validate,
    # interaction
    "sys_notify": _handle_sys_notify,
    "sys_session_handoff": _handle_sys_session_handoff,
    # environment
    "sys_env_snapshot": _handle_sys_env_snapshot,
    "sys_env_docker_generate": _handle_sys_env_docker_generate,
    # memory
    "mem_analysis_log": _handle_mem_analysis_log,
    "mem_methods_append": _handle_mem_methods_append,
    "mem_citations_generate": _handle_mem_citations_generate,
    "mem_intake_regenerate": _handle_mem_intake_regenerate,
    "mem_decision_log": _handle_mem_decision_log,
    # search
    "tool_search_semantic_scholar": _handle_tool_search,
    "tool_search_pubmed": _handle_tool_search,
    "tool_search_crossref": _handle_tool_search,
    "tool_search_arxiv": _handle_tool_search,
    "tool_search_web": _handle_tool_search,
    "tool_web_scrape": _handle_tool_web_scrape,
    "tool_literature_download": _handle_tool_literature_download,
    "tool_literature_search_and_save": _handle_tool_literature_search_and_save,
    "tool_step_literature_list": _handle_tool_step_literature_list,
    # execution
    "tool_python_exec": _handle_tool_python_exec,
    "tool_r_exec": _handle_tool_script_exec,
    "tool_julia_exec": _handle_tool_script_exec,
    "tool_bash_exec": _handle_tool_script_exec,
    "tool_package_install": _handle_tool_package_install,
    # data
    "tool_data_sample": _handle_tool_data_sample,
    "tool_data_profile": _handle_tool_data_profile,
    "tool_data_convert": _handle_tool_data_convert,
    # audit (see tool_audit dispatcher above)
    "tool_audit": _handle_tool_audit,
    "tool_audit_findings": _handle_tool_audit_findings,
    # step (see tool_step / tool_step_pipeline dispatchers above) —
    # phase-9-c3. tool_step_complete stays standalone as the top-level
    # end-of-step bundle; the per-operation tools (iterate / iterations_list
    # / revision_options / env_lock) are collapsed into tool_step and the
    # pipeline tools (define / run / status / diagram) into tool_step_pipeline.
    "tool_step": _handle_tool_step,
    "tool_step_pipeline": _handle_tool_step_pipeline,
    "tool_figure_caption_synthesise": _handle_tool_figure_caption_synthesise,
    "tool_figure_palette": _handle_tool_figure_palette,
    # tool_dashboard_test_generate / test_run consolidated into
    # tool_dashboard(operation=test_*) — phase-9-c2.
    # Grounded reasoning.
    "tool_thought_log": _handle_tool_thought_log,
    "tool_thought_trace": _handle_tool_thought_trace,
    "tool_grounding_register": _handle_tool_grounding_register,
    "tool_ground_from_context": _handle_tool_ground_from_context,
    "tool_claim_verify": _handle_tool_claim_verify,
    "tool_grounding_verify": _handle_tool_grounding_verify,
    "tool_lessons_record": _handle_tool_lessons_record,
    "tool_lessons_consult": _handle_tool_lessons_consult,
    "tool_plan_step_grounded": _handle_tool_plan_step_grounded,
    # New audit suite (audit handlers now folded into tool_audit dispatcher).
    "tool_preregister_freeze": _handle_tool_preregister_freeze,
    "tool_preregister_diff": _handle_tool_preregister_diff,
    "tool_sensitivity_define": _handle_tool_sensitivity_define,
    "tool_sensitivity_run": _handle_tool_sensitivity_run,
    "tool_redteam_review": _handle_tool_redteam_review,
    "tool_response_to_reviewers": _handle_tool_response_to_reviewers,
    "tool_null_findings_report": _handle_tool_null_findings_report,
    "tool_audit_quality_full": _handle_tool_audit_quality_full,
    "tool_slurm_submit": _handle_tool_slurm_submit,
    "tool_slurm_status": _handle_tool_slurm_status,
    "tool_slurm_fetch": _handle_tool_slurm_fetch,
    "tool_slurm_list": _handle_tool_slurm_list,
    # synthesis
    "tool_synthesize_plan": _handle_tool_synthesize_plan,
    "tool_synthesize": _handle_tool_synthesize,
    "tool_latex_compile": _handle_tool_latex_compile,
    # Typst + dashboard content + preview + content depth
    "tool_paper_compile_typst": _handle_tool_paper_compile_typst,
    "tool_figure_interactive_autogen": _handle_tool_figure_interactive_autogen,
    # tool_dashboard_story_* / reviewer_sim / create consolidated into
    # tool_dashboard(operation=...) — phase-9-c2.
    "tool_synthesis_preview": _handle_tool_synthesis_preview,
    "tool_section_substantiveness": _handle_tool_section_substantiveness,
    "tool_poster_create": _handle_tool_poster_create,
    "tool_dashboard": _handle_tool_dashboard,
    # ── headline tools ─────────────────────────────────
    "tool_humanities_essay_scaffold": _handle_tool_humanities_essay_scaffold,
    "tool_paper_figures_autoembed": _handle_tool_paper_figures_autoembed,
    "tool_slides_create": _handle_tool_slides_create,
    "tool_reviewer_simulate": _handle_tool_reviewer_simulate,
    "tool_rebuttal_draft": _handle_tool_rebuttal_draft,
    "tool_reviewer_response_compile": _handle_tool_reviewer_response_compile,
    # research / reasoning
    "tool_research_method": _handle_tool_research_method,
    "tool_research_tool": _handle_tool_research_tool,
    "tool_external_tool_instructions": _handle_tool_external_tool_instructions,
    "tool_alternative_path_propose": _handle_tool_alternative_path_propose,
    "tool_plan_step": _handle_tool_plan_step,
    # intake autofill
    "tool_intake_autofill": _handle_tool_intake_autofill,
    # tasks
    "tool_task_run": _handle_tool_task_run,
    "tool_task_status": _handle_tool_task_status,
    "tool_task_list": _handle_tool_task_list,
    "tool_task_kill": _handle_tool_task_kill,
    # multi-language scripts
    "tool_notebook_exec": _handle_tool_notebook_exec,
    "tool_rmarkdown_render": _handle_tool_rmarkdown_render,
    # hypothesis tracking
    "mem_hypothesis_add": _handle_mem_hypothesis_add,
    "mem_hypothesis_update": _handle_mem_hypothesis_update,
    "mem_hypothesis_list": _handle_mem_hypothesis_list,
    # iterative planning
    "tool_plan_next_step": _handle_tool_plan_next_step,
    "tool_branch_recommendation": _handle_tool_branch_recommendation,
    # scratch
    "tool_scratch_write": _handle_tool_scratch_write,
    "tool_scratch_run": _handle_tool_scratch_run,
    "tool_scratch_list": _handle_tool_scratch_list,
    "tool_scratch_clear": _handle_tool_scratch_clear,
    # workspace repair
    "tool_workspace_repair": _handle_tool_workspace_repair,
    # mid-flow context intake
    "tool_context_intake": _handle_tool_context_intake,
    # verified citations
    "tool_citations_verify": _handle_tool_citations_verify,
    # session resume + digest + quick review
    # tool_dead_end_lessons consolidated into tool_lessons(operation='dead_end').
    "tool_session_resume": _handle_tool_session_resume,
    "tool_progress_digest": _handle_tool_progress_digest,
    "tool_quick_review": _handle_tool_quick_review,
    "sys_dep_inventory": _handle_sys_dep_inventory,

    # tool_reliability_* consolidated into tool_reliability(operation='log_event'|'report').
    # tool_failure_* consolidated into tool_lessons(operation='failure_{record,check,list}').
    "tool_state_freshness_check": _handle_tool_state_freshness_check,
    "tool_intake_freshness": _handle_tool_intake_freshness,
    "tool_writing_discussion_from_verdicts": _handle_tool_writing_discussion_from_verdicts,
    "tool_discussion_coverage_audit": _handle_tool_discussion_coverage_audit,

    "tool_rigor_signals_scan": _handle_tool_rigor_signals_scan,
    "tool_resolve_gate_strictness": _handle_tool_resolve_gate_strictness,
    "tool_self_certify": _handle_tool_self_certify,
    "tool_list_certifications": _handle_tool_list_certifications,
    "tool_quick_route": _handle_tool_quick_route,
    "tool_promote_to_step": _handle_tool_promote_to_step,
    "tool_project_tier_strictness": _handle_tool_project_tier_strictness,

    # Lean variants + dry-run + bundling + coaching (Themes 2/13/15/7).
    # tool_mistake_replay consolidated into tool_lessons(operation='mistake_replay').
    "tool_dry_run": _handle_tool_dry_run,
    "tool_step_complete": _handle_tool_step_complete,

    # ── consolidated tools ───────────────────────────
    "tool_search": _handle_tool_search,
    "tool_plan": _handle_tool_plan,
    "sys_path": _handle_sys_path,
    "tool_ground": _handle_tool_ground,
    "tool_verify": _handle_tool_verify,
    "tool_lessons": _handle_tool_lessons,
    "tool_reliability": _handle_tool_reliability,
    "mem_log": _handle_mem_log,
    "tool_deprecations_summary": _handle_tool_deprecations_summary,
}

# Aliases — keep the AI's life easy when it forgets exact naming.
#
# Two flavours:
#   * non-deprecated nickname aliases (old typos / colloquial names) — silent.
#   * this-release consolidation aliases — flagged in _DEPRECATED_ALIASES below;
#     hits log to .os_state/deprecations.log so projects can audit usage
#     before the next major (when aliases hard-remove).
_ALIASES = {
    # Dot notation is handled generically by the dispatcher's dot→underscore
    # rewrite, no need to list here.
    "sys_state_summary": "sys_state_get",
    "tool_log_decision": "mem_decision_log",
    "view_workspace_tree": "sys_workspace_tree",

    # ── consolidation aliases ─────────────────────────
    # Search cluster (5 → 1).
    "tool_search_semantic_scholar": "tool_search",
    "tool_search_pubmed": "tool_search",
    "tool_search_crossref": "tool_search",
    "tool_search_arxiv": "tool_search",
    "tool_search_web": "tool_search",
    # Plan cluster (3 → 1, plan_step_grounded stays separate).
    "tool_plan_turn": "tool_plan",
    "tool_plan_advance": "tool_plan",
    "tool_plan_clear": "tool_plan",
    # Grounding cluster (4 → 2).
    "tool_grounding_register": "tool_ground",
    "tool_ground_from_context": "tool_ground",
    "tool_claim_verify": "tool_verify",
    "tool_grounding_verify": "tool_verify",
    # Lessons + failure-memory + dead-end + mistake-replay (8 → 1) — phase-9-c4.
    "tool_lessons_record":   "tool_lessons",
    "tool_lessons_consult":  "tool_lessons",
    "tool_failure_record":   "tool_lessons",
    "tool_failure_check":    "tool_lessons",
    "tool_failure_list":     "tool_lessons",
    "tool_dead_end_lessons": "tool_lessons",
    "tool_mistake_replay":   "tool_lessons",
    # Reliability log (2 → 1) — phase-9-c4.
    "tool_reliability_log_event": "tool_reliability",
    "tool_reliability_report":    "tool_reliability",
    # Path cluster (3 → 1).
    "sys_path_create": "sys_path",
    "sys_path_abandon": "sys_path",
    "sys_path_list": "sys_path",
    # Memory cluster (4 → 1).
    "mem_methods_append": "mem_log",
    "mem_decision_log": "mem_log",
    "mem_hypothesis_update": "mem_log",
    "mem_analysis_log": "mem_log",

    # ── audit cluster ───────────────────────────────────
    # Per-step audits.
    "tool_audit_assumptions": "tool_audit",
    "tool_audit_code_quality": "tool_audit",
    "tool_audit_evalue": "tool_audit",
    "tool_audit_figure": "tool_audit",
    "tool_audit_figure_full": "tool_audit",
    "tool_audit_figure_interactivity": "tool_audit",
    "tool_audit_power": "tool_audit",
    "tool_audit_reproducibility": "tool_audit",
    "tool_audit_step_completeness": "tool_audit",
    "tool_audit_step_literature": "tool_audit",
    # Project-wide audits.
    "tool_audit_citations": "tool_audit",
    "tool_audit_claims": "tool_audit",
    "tool_audit_cliches": "tool_audit",
    "tool_audit_coherence": "tool_audit",
    "tool_audit_cross_deliverable_consistency": "tool_audit",
    "tool_audit_prose": "tool_audit",
    "tool_audit_version_coherence": "tool_audit",
    # Synthesis-side audits.
    "tool_audit_synthesis": "tool_audit",
    "tool_audit_dashboard_content": "tool_audit",
    "tool_audit_figure_coverage": "tool_audit",
    "tool_audit_reviewer_responses": "tool_audit",
    # Findings ledger (2 → 1).
    "tool_audit_findings_query": "tool_audit_findings",
    "tool_audit_findings_diff": "tool_audit_findings",
    # Legacy nickname aliases — chain through the consolidated entry point.
    "tool_audit_figure_quality": "tool_audit",
    "tool_audit_statistical_power": "tool_audit",

    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create":            "tool_dashboard",
    "tool_dashboard_story_generate":    "tool_dashboard",
    "tool_dashboard_story_edit":        "tool_dashboard",
    "tool_dashboard_story_quality_bar": "tool_dashboard",
    "tool_dashboard_reviewer_sim":      "tool_dashboard",
    "tool_dashboard_test_generate":     "tool_dashboard",
    "tool_dashboard_test_run":          "tool_dashboard",

    # ── step cluster (8 → 2) ──────────────────────────
    # tool_step_complete stays standalone (top-level end-of-step bundle).
    # tool_step_literature_list lives with the literature/search family
    # and is owned by that cluster — NOT consolidated here.
    "tool_step_iterate":           "tool_step",
    "tool_step_iterations_list":   "tool_step",
    "tool_step_revision_options":  "tool_step",
    "tool_step_env_lock":          "tool_step",
    "tool_step_pipeline_define":   "tool_step_pipeline",
    "tool_step_pipeline_run":      "tool_step_pipeline",
    "tool_step_pipeline_status":   "tool_step_pipeline",
    "tool_step_pipeline_diagram":  "tool_step_pipeline",
}

# Aliases that should fire deprecation telemetry when invoked. Every name
# here MUST resolve through _ALIASES to a real handler — preflight enforces.
_DEPRECATED_ALIASES = {
    "tool_search_semantic_scholar",
    "tool_search_pubmed",
    "tool_search_crossref",
    "tool_search_arxiv",
    "tool_search_web",
    "tool_plan_turn",
    "tool_plan_advance",
    "tool_plan_clear",
    "tool_grounding_register",
    "tool_ground_from_context",
    "tool_claim_verify",
    "tool_grounding_verify",
    "tool_lessons_record",
    "tool_lessons_consult",
    # ── lessons + failure + reliability cluster (10 → 2) — phase-9-c4 ──
    "tool_failure_record",
    "tool_failure_check",
    "tool_failure_list",
    "tool_dead_end_lessons",
    "tool_mistake_replay",
    "tool_reliability_log_event",
    "tool_reliability_report",
    "sys_path_create",
    "sys_path_abandon",
    "sys_path_list",
    "mem_methods_append",
    "mem_decision_log",
    "mem_hypothesis_update",
    "mem_analysis_log",
    # ── audit cluster ───────────────────────────────────
    "tool_audit_assumptions",
    "tool_audit_code_quality",
    "tool_audit_evalue",
    "tool_audit_figure",
    "tool_audit_figure_full",
    "tool_audit_figure_interactivity",
    "tool_audit_power",
    "tool_audit_reproducibility",
    "tool_audit_step_completeness",
    "tool_audit_step_literature",
    "tool_audit_citations",
    "tool_audit_claims",
    "tool_audit_cliches",
    "tool_audit_coherence",
    "tool_audit_cross_deliverable_consistency",
    "tool_audit_prose",
    "tool_audit_version_coherence",
    "tool_audit_synthesis",
    "tool_audit_dashboard_content",
    "tool_audit_figure_coverage",
    "tool_audit_reviewer_responses",
    "tool_audit_findings_query",
    "tool_audit_findings_diff",
    # Legacy nickname aliases now also flow through the consolidated
    # tool_audit dispatcher and need param injection. Pre-v2 they silently
    # mapped to tool_audit_figure_full / tool_audit_power.
    "tool_audit_figure_quality",
    "tool_audit_statistical_power",
    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create",
    "tool_dashboard_story_generate",
    "tool_dashboard_story_edit",
    "tool_dashboard_story_quality_bar",
    "tool_dashboard_reviewer_sim",
    "tool_dashboard_test_generate",
    "tool_dashboard_test_run",
    # ── step cluster (8 → 2) ──────────────────────────
    "tool_step_iterate",
    "tool_step_iterations_list",
    "tool_step_revision_options",
    "tool_step_env_lock",
    "tool_step_pipeline_define",
    "tool_step_pipeline_run",
    "tool_step_pipeline_status",
    "tool_step_pipeline_diagram",
}


def _resolve_tool_name(name: str) -> str:
    """Normalize incoming tool name: dots→underscores, then alias lookup."""
    canonical = name.replace(".", "_")
    return _ALIASES.get(canonical, canonical)


# Maps legacy alias → kwarg(s) to inject. Lets the consolidated handler
# infer operation/kind/source/mode/scope from the caller's name so an
# old-style `tool_search_pubmed(query=...)` keeps working without the
# caller supplying `source='pubmed'`.
#
# Two value shapes are accepted:
#   * (key, value) tuple — single-kwarg injection (most clusters).
#   * tuple of (key, value) tuples — multi-kwarg injection (audit cluster
#     needs both scope and dimension).
_ALIAS_PARAM_INJECTION: dict[str, Any] = {
    "tool_search_semantic_scholar": ("source", "semantic_scholar"),
    "tool_search_pubmed":           ("source", "pubmed"),
    "tool_search_crossref":         ("source", "crossref"),
    "tool_search_arxiv":            ("source", "arxiv"),
    "tool_search_web":              ("source", "web"),
    "tool_plan_turn":               ("operation", "turn"),
    "tool_plan_advance":            ("operation", "advance"),
    "tool_plan_clear":              ("operation", "clear"),
    "tool_grounding_register":      ("mode", "explicit"),
    "tool_ground_from_context":     ("mode", "from_context"),
    "tool_claim_verify":            ("scope", "claim"),
    "tool_grounding_verify":        ("scope", "project"),
    "tool_lessons_record":          ("operation", "record"),
    "tool_lessons_consult":         ("operation", "consult"),
    # ── lessons + failure + reliability cluster — phase-9-c4 ──
    "tool_failure_record":          ("operation", "failure_record"),
    "tool_failure_check":           ("operation", "failure_check"),
    "tool_failure_list":            ("operation", "failure_list"),
    "tool_dead_end_lessons":        ("operation", "dead_end"),
    "tool_mistake_replay":          ("operation", "mistake_replay"),
    "tool_reliability_log_event":   ("operation", "log_event"),
    "tool_reliability_report":      ("operation", "report"),
    "sys_path_create":              ("operation", "create"),
    "sys_path_abandon":             ("operation", "abandon"),
    "sys_path_list":                ("operation", "list"),
    "mem_methods_append":           ("kind", "methods"),
    "mem_decision_log":             ("kind", "decision"),
    "mem_hypothesis_update":        ("kind", "hypothesis"),
    "mem_analysis_log":             ("kind", "analysis"),
    # ── audit cluster ──
    # Per-step audits.
    "tool_audit_assumptions":             (("scope", "step"), ("dimension", "assumptions")),
    "tool_audit_code_quality":            (("scope", "step"), ("dimension", "code_quality")),
    "tool_audit_evalue":                  (("scope", "step"), ("dimension", "evalue")),
    "tool_audit_figure":                  (("scope", "step"), ("dimension", "figure")),
    "tool_audit_figure_full":             (("scope", "step"), ("dimension", "figure_full")),
    "tool_audit_figure_interactivity":    (("scope", "step"), ("dimension", "figure_interactivity")),
    "tool_audit_power":                   (("scope", "step"), ("dimension", "power")),
    "tool_audit_reproducibility":         (("scope", "step"), ("dimension", "reproducibility")),
    "tool_audit_step_completeness":       (("scope", "step"), ("dimension", "completeness")),
    "tool_audit_step_literature":         (("scope", "step"), ("dimension", "literature")),
    # Project-wide audits.
    "tool_audit_citations":               (("scope", "project"), ("dimension", "citations")),
    "tool_audit_claims":                  (("scope", "project"), ("dimension", "claims")),
    "tool_audit_cliches":                 (("scope", "project"), ("dimension", "cliches")),
    "tool_audit_coherence":               (("scope", "project"), ("dimension", "coherence")),
    "tool_audit_cross_deliverable_consistency": (("scope", "project"), ("dimension", "cross_deliverable")),
    "tool_audit_prose":                   (("scope", "project"), ("dimension", "prose")),
    "tool_audit_version_coherence":       (("scope", "project"), ("dimension", "version_coherence")),
    # Synthesis-side audits.
    "tool_audit_synthesis":               (("scope", "synthesis"), ("dimension", "all")),
    "tool_audit_dashboard_content":       (("scope", "synthesis"), ("dimension", "dashboard_content")),
    "tool_audit_figure_coverage":         (("scope", "synthesis"), ("dimension", "figure_coverage")),
    "tool_audit_reviewer_responses":      (("scope", "synthesis"), ("dimension", "reviewer_responses")),
    # Findings ledger (2 → 1).
    "tool_audit_findings_query":          ("operation", "query"),
    "tool_audit_findings_diff":           ("operation", "diff"),
    # Legacy nickname aliases.
    "tool_audit_figure_quality":          (("scope", "step"), ("dimension", "figure_full")),
    "tool_audit_statistical_power":       (("scope", "step"), ("dimension", "power")),
    # ── dashboard cluster (7 → 1) ──────────────────────
    "tool_dashboard_create":              ("operation", "create"),
    "tool_dashboard_story_generate":      ("operation", "story_generate"),
    "tool_dashboard_story_edit":          ("operation", "story_edit"),
    "tool_dashboard_story_quality_bar":   ("operation", "story_quality_bar"),
    "tool_dashboard_reviewer_sim":        ("operation", "reviewer_sim"),
    "tool_dashboard_test_generate":       ("operation", "test_generate"),
    "tool_dashboard_test_run":            ("operation", "test_run"),
    # ── step cluster (8 → 2) ──────────────────────────
    "tool_step_iterate":                  ("operation", "iterate"),
    "tool_step_iterations_list":          ("operation", "iterations_list"),
    "tool_step_revision_options":         ("operation", "revision_options"),
    "tool_step_env_lock":                 ("operation", "env_lock"),
    "tool_step_pipeline_define":          ("operation", "define"),
    "tool_step_pipeline_run":             ("operation", "run"),
    "tool_step_pipeline_status":          ("operation", "status"),
    "tool_step_pipeline_diagram":         ("operation", "diagram"),
}


def _inject_consolidation_param(source_name: str, arguments: dict) -> dict:
    """Inject the consolidation parameter(s) implied by a deprecated alias.

    Accepts either a single (key, value) tuple or a tuple of (key, value)
    pairs. No-op if the caller already supplied the parameter (caller wins).
    """
    spec = _ALIAS_PARAM_INJECTION.get(source_name)
    if not spec:
        return arguments
    # Multi-kwarg form: tuple of (key, value) pairs.
    if (
        isinstance(spec, tuple)
        and spec
        and all(isinstance(p, tuple) and len(p) == 2 for p in spec)
    ):
        for key, value in spec:
            arguments.setdefault(key, value)
        return arguments
    # Single-kwarg form: (key, value).
    if isinstance(spec, tuple) and len(spec) == 2 and not isinstance(spec[0], tuple):
        key, value = spec
        arguments.setdefault(key, value)
        return arguments
    return arguments


def _log_deprecation(root: Path, source: str, target: str) -> None:
    """Append an alias-invocation event to .os_state/deprecations.log."""
    try:
        log_dir = root / ".os_state"
        if not log_dir.exists():
            return
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kind": "tool_alias",
            "source": source,
            "target": target,
        }
        with open(log_dir / "deprecations.log", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        # Best-effort telemetry — failing here must never break the dispatch.
        logger.debug("deprecation-log append failed: %s", exc)


# Tools removed in earlier releases — friendly error pointing the AI at the new path.
# Old plans, scripts, or third-party callers that still name these get a
# clear message instead of a generic "unknown tool" dead end.
_REMOVED_TOOLS = {
    "tool_figure_create": (
        "tool_figure_create was removed. Research-OS no longer ships "
        "premade chart code — write your own matplotlib / ggplot2 / Altair / "
        "plotnine / Vega-Lite / d3 script tailored to the data. Load the "
        "guidance with sys_protocol_get(protocol_name='visualization/figure_guidelines', "
        "format='summary'); call tool_research_method or tool_search_web first if "
        "you're unsure which plotting library is canonical for this data type. "
        "tool_figure_palette + tool_audit_figure_full are unchanged."
    ),
}


def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error("Rate limit exceeded — slow down."))
    canonical_input = name.replace(".", "_")
    resolved = _resolve_tool_name(name)
    logger.info(f"Tool call: {name} -> {resolved}")
    if canonical_input in _DEPRECATED_ALIASES and canonical_input != resolved:
        _log_deprecation(root, canonical_input, resolved)
        # Back-compat: inject the dispatch parameter the consolidated tool
        # expects, so a researcher (or older script) calling the legacy name
        # gets the legacy behaviour without specifying operation/kind/source.
        arguments = _inject_consolidation_param(canonical_input, dict(arguments or {}))
    if resolved in _REMOVED_TOOLS:
        return _text(_error(_REMOVED_TOOLS[resolved]))
    handler = _HANDLERS.get(resolved)
    if handler is None:
        return _text(
            _error(
                f"Unknown tool '{name}'. Call sys_protocol_list to see the tool surface "
                "or check tool_search_web for the right capability."
            )
        )
    try:
        return handler(resolved, arguments, root)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return _text(_error(str(e)))


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------


def _short_for_list(schema: dict) -> str:
    """Tight description used by list_tools — saves ~2K tokens per message.

    Resolution order:
        1. Explicit `short` field if present.
        2. First sentence of the full description, capped at 160 chars.
    The AI can call sys_tool_describe(name) for the full text on demand.
    """
    if isinstance(schema.get("short"), str) and schema["short"].strip():
        return schema["short"].strip()
    full = schema.get("description", "")
    first = full.split(". ")[0].strip()
    if not first.endswith("."):
        first += "."
    return first[:160]


# ── Pack discovery ───────────────────────────────────────────────────


def _discover_packs_once() -> None:
    """Discover installed protocol packs and merge them into core registries.

    Idempotent — safe to call multiple times; subsequent calls reset
    the plugin loader's state and rediscover. Bundled in-tree packs
    (humanities, qualitative) ship in this wheel and are loaded
    unconditionally; external packs come from the
    `research_os.protocol_pack` entry-point group.
    """
    try:
        from research_os.plugins import discover_packs
    except Exception as exc:
        logger.debug("plugin loader import failed: %s", exc)
        return
    # In-tree packs bundled with the core wheel. They register the
    # same way external packs would but skip the entry-point hop.
    bundled = [
        ("humanities", "research_os_humanities:register"),
        ("qualitative", "research_os_qualitative:register"),
        ("theory_math", "research_os_theory_math:register"),
        ("wet_lab", "research_os_wet_lab:register"),
        ("engineering", "research_os_engineering:register"),
    ]
    try:
        discover_packs(
            tool_definitions=TOOL_DEFINITIONS,
            handlers=_HANDLERS,
            bundled=bundled,
        )
    except Exception as exc:
        logger.warning("pack discovery raised unexpectedly: %s", exc)


# Run discovery at import time so list_tools / dispatcher see pack tools.
_discover_packs_once()


def _handle_sys_packs_installed(name, arguments, root):
    """Return diagnostics about installed packs."""
    from research_os.plugins import installed_packs, load_pack_errors
    packs = installed_packs()
    errors = load_pack_errors()
    return _text(_success({
        "packs": packs,
        "pack_count": len(packs),
        "errors": errors,
        "error_count": len(errors),
        "advice": (
            "Install third-party packs via pip; they auto-register on next "
            "server start via the `research_os.protocol_pack` entry-point group."
            if not errors else
            "One or more packs failed to register; inspect 'errors' for "
            "tracebacks. See workspace/logs/pack_errors.log for the full log."
        ),
    }))


# Register sys_packs_installed (defined here because it depends on the
# pack loader being imported; can't live in the main _HANDLERS block above).
TOOL_DEFINITIONS["sys_packs_installed"] = {
    "short": "List installed protocol packs (name, version, tool count, router entries, errors).",
    "description": "Returns the set of protocol packs currently registered with the server — both bundled (humanities, qualitative) and externally pip-installed via the `research_os.protocol_pack` entry-point group. Use to confirm a pack is loadable, to see its tool / router contributions, and to surface any registration errors (full traceback in `workspace/logs/pack_errors.log`).",
    "category": "routing",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}
_HANDLERS["sys_packs_installed"] = _handle_sys_packs_installed


# ── Adapter discovery ────────────────────────────────────────────────


def _discover_adapters_once() -> None:
    """Discover installed infrastructure adapters and merge their tools.

    Mirrors `_discover_packs_once()` but operates over the
    `research_os.adapter` entry-point group + the in-tree bundled
    adapter list. Idempotent; safe to call again from a test.
    """
    try:
        from research_os.adapters import discover_adapters
    except Exception as exc:
        logger.debug("adapter loader import failed: %s", exc)
        return
    bundled = [
        ("slurm", "research_os_adapter_slurm:register"),
        ("snakemake", "research_os_adapter_snakemake:register"),
        ("nextflow", "research_os_adapter_nextflow:register"),
        ("cytoscape", "research_os_adapter_cytoscape:register"),
        ("redcap", "research_os_adapter_redcap:register"),
        ("synapse", "research_os_adapter_synapse:register"),
    ]
    try:
        discover_adapters(
            tool_definitions=TOOL_DEFINITIONS,
            handlers=_HANDLERS,
            bundled=bundled,
        )
    except Exception as exc:
        logger.warning("adapter discovery raised unexpectedly: %s", exc)


_discover_adapters_once()


def _handle_sys_adapters_installed(name, arguments, root):
    from research_os.adapters import installed_adapters, load_adapter_errors
    adapters = installed_adapters()
    errors = load_adapter_errors()
    return _text(_success({
        "adapters": adapters,
        "adapter_count": len(adapters),
        "errors": errors,
        "error_count": len(errors),
    }))


def _handle_tool_adapter_extract(name, arguments, root):
    from research_os.adapters.runner import run_extract
    adapter_name = arguments.get("adapter_name")
    if not adapter_name:
        return _text(_error("adapter_name is required"))
    res = run_extract(root, adapter_name, step_id=arguments.get("step_id"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "extract failed")))


def _handle_tool_adapters_list(name, arguments, root):
    from research_os.adapters.runner import list_adapters
    return _text(_success(list_adapters(root)))


def _handle_tool_adapters_run_all(name, arguments, root):
    from research_os.adapters.runner import run_all
    return _text(_success(run_all(root, step_id=arguments.get("step_id"))))


TOOL_DEFINITIONS["sys_adapters_installed"] = {
    "short": "List installed infrastructure adapters (Slurm / Snakemake / Nextflow / Cytoscape / REDCap / Synapse / external).",
    "description": "Returns the set of infrastructure adapters currently registered via the `research_os.adapter` entry-point group. Adapters are pluggable detectors + provenance extractors for HPC schedulers, workflow engines, analysis platforms, and data systems. Use to confirm an adapter is loaded; pair with tool_adapters_list to check detection on the current project.",
    "category": "routing",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}
_HANDLERS["sys_adapters_installed"] = _handle_sys_adapters_installed

TOOL_DEFINITIONS["tool_adapter_extract"] = {
    "short": "Run one adapter's extract() + write provenance YAML to workspace/<step>/provenance/<adapter>.yaml.",
    "description": "Executes a specific installed adapter against the current project (or one step within it) and persists the extracted provenance as a structured YAML file. Returns the path to the YAML plus a small summary of cardinalities. Idempotent — re-running overwrites the YAML so it always reflects the current filesystem state.",
    "category": "state",
    "inputSchema": {
        "type": "object",
        "properties": {
            "adapter_name": {"type": "string"},
            "step_id": {"type": "string"},
        },
        "required": ["adapter_name"],
    },
}
_HANDLERS["tool_adapter_extract"] = _handle_tool_adapter_extract

TOOL_DEFINITIONS["tool_adapters_list"] = {
    "short": "List adapters + their detection status on the current project (e.g. 'slurm: detected_in_project=true').",
    "description": "Walks every installed adapter, calls its detect(root) callable, and returns the combined status. Detect is cheap (filesystem-only; no network). Use to surface which adapters are relevant before deciding whether to run tool_adapter_extract / tool_adapters_run_all.",
    "category": "state",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}
_HANDLERS["tool_adapters_list"] = _handle_tool_adapters_list

TOOL_DEFINITIONS["tool_adapters_run_all"] = {
    "short": "Run every detected adapter's extract() and write per-adapter provenance YAMLs.",
    "description": "Bulk version of tool_adapter_extract — walks every installed adapter, calls detect(), and runs extract() only on the matches. Writes one provenance/<adapter>.yaml per match. Returns a per-adapter status list.",
    "category": "state",
    "inputSchema": {
        "type": "object",
        "properties": {"step_id": {"type": "string"}},
        "additionalProperties": False,
    },
}
_HANDLERS["tool_adapters_run_all"] = _handle_tool_adapters_run_all


if HAS_MCP:
    server = Server("research-os")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        root = _resolve_project_root()
        profile = _read_profile(root)
        tools: list[Tool] = []
        for name, schema in TOOL_DEFINITIONS.items():
            desc = _short_for_list(schema)
            if profile.get("model_profile") == "small":
                # Already terse — but cap aggressively for the smallest models.
                desc = desc[:120]
            tools.append(
                Tool(name=name, description=desc, inputSchema=schema["inputSchema"])
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        # Per-request project resolution — supports global-server mode
        # (one `research-os start` process serving multiple projects).
        # Tools that need a project root receive the resolved path.
        root = _resolve_project_root()
        return _handle_tool_call(name, arguments, root)

    async def run_stdio() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )


def _inject_api_keys(root: Path) -> None:
    """Export literature / search API keys from researcher_config to env vars.

    Research OS does NOT manage LLM provider keys — your AI client owns that.
    Only research-data-source credentials (Semantic Scholar, PubMed, Crossref,
    Firecrawl, SerpAPI) are injected here, with SDK-friendly aliases.
    """
    try:
        import yaml as _yaml

        cfg_path = root / "inputs" / "researcher_config.yaml"
        if not cfg_path.exists():
            cfg_path = root / "researcher_config.yaml"
            if not cfg_path.exists():
                return
        cfg = _yaml.safe_load(cfg_path.read_text()) or {}
        api_keys = cfg.get("api_keys", {}) or {}
        allowed = {"semantic_scholar", "pubmed", "crossref", "firecrawl", "serpapi"}
        for key, value in api_keys.items():
            if not value or key not in allowed:
                continue
            env_name = key.upper()
            os.environ[env_name] = str(value)
            # SDK-compat aliases.
            if key == "semantic_scholar":
                os.environ["SEMANTIC_SCHOLAR_API_KEY"] = str(value)
                os.environ["S2_API_KEY"] = str(value)
            if key == "pubmed":
                os.environ["NCBI_API_KEY"] = str(value)
            if key == "firecrawl":
                os.environ["FIRECRAWL_API_KEY"] = str(value)
            if key == "serpapi":
                os.environ["SERPAPI_API_KEY"] = str(value)
    except Exception as e:  # pragma: no cover - non-fatal
        logger.debug(f"API key injection skipped: {e}")


def _resolve_project_root() -> Path:
    """Resolve the active project root for the current request.

    Resolution order:
      1. RESEARCH_OS_WORKSPACE environment variable (set by IDE MCP
         config, typically to ${workspaceFolder}).
      2. Current working directory walked up to the nearest `.os_state/`
         (the project marker dropped by `research-os init`).
      3. Current working directory itself (last resort — tools that
         need a real workspace will report it gracefully).
    """
    env_root = os.environ.get("RESEARCH_OS_WORKSPACE", "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    try:
        from research_os.utils.asset_manager import AssetManager
        detected = AssetManager.find_project_root()
        if (detected / ".os_state").exists():
            return detected
    except Exception:
        pass

    return Path.cwd().resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="research-os start",
        description=(
            "Run the Research OS MCP server over stdio. The server is "
            "GLOBAL — it does not need a `--workspace` argument. The "
            "active project is resolved per-request via the "
            "RESEARCH_OS_WORKSPACE env var (preferred; set by your IDE "
            "MCP config to ${workspaceFolder}) or by walking up from the "
            "current working directory looking for `.os_state/`."
        ),
    )
    parser.add_argument("--transport", default="stdio",
                        help="MCP transport (default: stdio). 'sse' reserved for future use.")
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "DEPRECATED. Workspace is auto-resolved from the "
            "RESEARCH_OS_WORKSPACE env var or the current working "
            "directory. Passing --workspace still works (back-compat) "
            "but is no longer required."
        ),
    )
    args = parser.parse_args()

    # Back-compat: if --workspace is passed explicitly, honour it by
    # setting the env var. Future requests will read it consistently.
    if args.workspace:
        os.environ["RESEARCH_OS_WORKSPACE"] = str(
            Path(args.workspace).expanduser().resolve()
        )

    # Inject API keys for the resolved project (if a project is on disk
    # at server start; otherwise keys are injected lazily on first call).
    try:
        _inject_api_keys(_resolve_project_root())
    except Exception:
        pass

    if HAS_MCP:
        import asyncio
        asyncio.run(run_stdio())
    else:
        sys.exit("MCP package missing. Install with: pip install 'research-os[all]'")


if __name__ == "__main__":
    main()
