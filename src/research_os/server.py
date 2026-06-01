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
        "description": "Hierarchical L1→L2→L3 picker. Returns primary_protocol, shortcut_tool, decomposition, complexity, ask_user, alternatives. High-complexity prompts get an active_plan persisted to .os_state/. See guidance/iterative_planning for the workflow.",
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
    "tool_plan_advance": {
        "short": "Mark current step done; get next step. Returns status='blocked' when a deliverable gate fails.",
        "description": "Walk the active_plan. Returns next_step + remaining. Returns status='blocked' when the next step is a deliverable tool (tool_synthesize / tool_dashboard_create / tool_poster_create / tool_latex_compile) and the quality gate finds blockers. Pass override_gate=true only on explicit researcher approval of a partial deliverable.",
        "category": "routing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "override_gate": {"type": "boolean"},
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
        "description": "Given a protocol name, return the tight set of tools the AI should prefer while executing it: ~10-15 tools = essentials + everything the protocol's decomposition actually calls. Use after sys_protocol_get to scope your working set instead of triaging all 94 tools per turn.",
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
        "description": "Returns a compact orientation block for the AI: the routing pattern (sys_boot → tool_route → sys_protocol_get → sys_active_tools), the protocol categories with one-line summaries, the tool namespaces (sys_* / tool_* / mem_*), and the canonical session-start flow. Use this when starting cold (no prior session memory), when a new AI takes over from a handoff, or when a tool / protocol mention is ambiguous and the orientation block clarifies it.",
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
        "short": "Load a protocol — format='summary' (cheap), 'step' (one step), or 'full' (entire YAML).",
        "description": "Load a protocol YAML by name (e.g. 'guidance/project_startup'). Three formats — summary returns id + step headings + quality_bar + expected outputs in ~300 tokens; step returns one specific step body (requires step_id); full returns the entire YAML (~1.5-3K tokens). Prefer summary first, then step on demand. Routing tip: call tool_route(prompt) BEFORE this to pick the right protocol_name.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "format": {
                    "type": "string",
                    "description": "summary | step | full (default: full for backward compatibility, but summary is recommended).",
                },
                "step_id": {
                    "type": "string",
                    "description": "Required when format='step'.",
                },
            },
            "required": ["protocol_name"],
        },
    },
    "sys_protocol_list": {
        "description": "List every available protocol with a one-line summary.",
        "category": "protocol",
        "inputSchema": {"type": "object", "properties": {}},
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
            "BEFORE tool_dashboard_create / tool_synthesize so the deliverables "
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
        "description": "Snapshot the current Python (and optionally R/Julia) environment to workspace/<step>/environment/requirements.txt.",
        "category": "environment",
        "inputSchema": {"type": "object", "properties": {}},
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
    "tool_audit_synthesis": {
        "description": "Audit a generated manuscript for completeness, claim grounding, and citation coverage.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_path": {"type": "string"}},
            "required": ["paper_path"],
        },
    },
    "tool_audit_power": {
        "description": "Compute post-hoc statistical power. Warns if power < 0.8. Writes a report to the current experiment's outputs/reports/.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "effect_size": {"type": "number"},
                "alpha": {"type": "number"},
                "n": {"type": "number"},
            },
            "required": ["filepath", "alpha", "n"],
        },
    },
    "tool_audit_assumptions": {
        "description": "Re-run assumption checks (normality, homoscedasticity, independence) on residuals or model output.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool_audit_figure": {
        "description": "Check figure quality: DPI, colorblind-friendly palette, axis labels, error bars.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool_audit_citations": {
        "description": "Verify every citation in workspace/citations.md against an online lookup (Crossref / Semantic Scholar). Flags unverified entries.",
        "category": "audit",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_audit_reproducibility": {
        "description": "Re-run every experiment script in a clean environment and verify outputs match. Slow but the gold-standard reproducibility check.",
        "category": "audit",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_audit_step_completeness": {
        "short": "Per-step gate: focal figure + caption + summary + non-stub conclusions. BLOCKS tool_synthesize when failing.",
        "description": "Server-enforced 'did the step actually finish?' check. Validates that EVERY active numbered step has: (a) conclusions.md with non-stub Findings + Decision; (b) at least one focal figure under outputs/figures/; (c) sibling .caption.md + .summary.md for each figure; (d) at least one runnable script. Returns status='error' if any step has BLOCKERS — tool_synthesize honours this and refuses to assemble until cleared. Pass step_id to audit one step instead of the whole project. Writes report to workspace/logs/step_completeness.md.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {
                    "type": "string",
                    "description": "Optional — audit one step instead of all active ones.",
                }
            },
        },
    },
    "tool_figure_create": {
        "short": "Publication-grade figure with enforced palette / DPI / dual PNG+SVG export + caption sidecars.",
        "description": "Build a figure that clears the figure_guidelines bar in one call: SciencePlots-style typography (or built-in equivalent), Okabe-Ito / viridis / PuOr palettes, mandatory axis labels with units, inline n annotation, 95% CI band on regression overlays. Writes <step>/outputs/figures/<step_num>_<name>.{png,svg} + <name>.caption.md + (when plain_english is given) <name>.summary.md. Supported `kind`: bar, barh, line, scatter, hist, box, violin, heatmap, forest. `data` accepts a list-of-dicts, column-dict, or a path to CSV/TSV/JSON/Parquet. Set `interactive=true` (or `backend='plotly'`) for an interactive HTML companion when plotly is installed.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string", "description": "Numbered step folder, e.g. '03_logistic_baseline'."},
                "name": {"type": "string", "description": "Short descriptor — step number auto-prefixed if missing."},
                "kind": {"type": "string", "description": "bar | barh | line | scatter | hist | box | violin | heatmap | forest"},
                "data": {"description": "list of row-dicts, column-dict, OR string path to CSV/TSV/JSON/Parquet."},
                "x": {"type": "string"},
                "y": {"type": "string"},
                "z": {"type": "string", "description": "heatmap value column"},
                "error": {"type": "string", "description": "column with error/CI radius"},
                "color_by": {"type": "string", "description": "grouping column for line / scatter"},
                "bins": {"type": "number", "description": "histogram bin count (default 30)"},
                "regression": {"type": "boolean", "description": "scatter: add OLS line + 95% CI band"},
                "palette": {"type": "string", "description": "qualitative (default) | sequential | diverging | accent"},
                "style": {"type": "string", "description": "default | nature | ieee | notebook | no_latex"},
                "title": {"type": "string"},
                "xlabel": {"type": "string"},
                "ylabel": {"type": "string"},
                "caption": {"type": "string", "description": "Technical caption for the figure sidecar."},
                "plain_english": {"type": "string", "description": "Plain-language summary for the .summary.md sidecar."},
                "interactive": {"type": "boolean", "description": "Also write an HTML plotly companion (requires plotly)."},
                "backend": {"type": "string", "description": "matplotlib (default) | plotnine | plotly"},
            },
            "required": ["step_id", "name", "kind", "data"],
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
    "tool_audit_figure_full": {
        "short": "Full figure audit — DPI + caption + summary + SVG companion + aspect ratio.",
        "description": "Strict superset of `tool_audit_figure` (which checks DPI + dimensions only). Adds: missing caption / summary sidecars, PNG without SVG companion, time-series aspect-ratio sanity. Emits BLOCKERs vs warnings the step-completeness gate consumes. Use this for any figure heading into the dashboard, paper, or poster.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "figure_path": {"type": "string"},
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
    "tool_step_pipeline_define": {
        "short": "Author the step's sub-task DAG (ingest→clean→validate→fit→diagnose→visualize→report).",
        "description": "Seeds workspace/<step>/pipeline.yaml from a 7-node template; required for any step with >2 scripts (audit gate). See guidance/analysis_plan for the workflow.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string", "description": "Numbered step folder (e.g. 03_logistic_baseline)."},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "nodes": {"type": "array", "description": "Optional custom node list — see protocol for shape."},
                "template": {"type": "string", "description": "default (7-node ingest→...→report)."},
            },
            "required": ["step_id"],
        },
    },
    "tool_step_pipeline_run": {
        "short": "Execute the step's sub-task DAG with content-hash caching.",
        "description": "Walks the pipeline.yaml DAG in topological order. Nodes whose script + inputs + params hash matches a previous successful run are SKIPPED (cached) — only the affected downstream chain re-runs after an edit. Each produced output gets a .prov.json sidecar (PROV-O). Pass `only` to restrict to a subset of nodes (their upstream deps are pulled in automatically). Pass `force=true` to bypass the cache. Pass `dry_run=true` to see what would run.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "only": {"type": "array", "items": {"type": "string"}, "description": "Node IDs to run (transitive deps auto-included)."},
                "force": {"type": "boolean", "description": "Skip the cache and re-run every node."},
                "dry_run": {"type": "boolean", "description": "Plan only; do not execute."},
            },
            "required": ["step_id"],
        },
    },
    "tool_step_pipeline_status": {
        "short": "Per-node staleness report — what's fresh, stale, or never run.",
        "description": "Reads pipeline.yaml + the most recent run log; for each node reports fresh (content hash matches last successful run), stale (inputs/params/script changed), or never_run.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {"step_id": {"type": "string"}},
            "required": ["step_id"],
        },
    },
    "tool_step_pipeline_diagram": {
        "short": "Render the step's sub-task DAG as a Mermaid + (optional) PNG.",
        "description": "Writes workspace/<step>/pipeline.mermaid; the dashboard's per-step appendix embeds it so reviewers see the analysis as a graph, not a mystery script.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {"step_id": {"type": "string"}},
            "required": ["step_id"],
        },
    },
    "tool_dashboard_test_generate": {
        "short": "Scaffold tests/dashboard/ with Playwright invariant suite + axe-core accessibility.",
        "description": "Writes a baseline pytest-playwright suite covering: no console errors, semantic landmarks, TOC anchors, theme toggle CSS-var flip, sortable tables, figure lightbox, print stylesheet, ARIA landmarks, axe-core WCAG 2.1 AA. Visual regression is opt-in via ROS_DASHBOARD_VISUAL=1. Researcher adds their own test_*.py files in the same folder; tool_dashboard_test_run picks them up.",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "overwrite": {"type": "boolean"},
            },
        },
    },
    "tool_dashboard_test_run": {
        "short": "Execute the Playwright suite; return structured failures + trace.zip paths.",
        "description": "Subprocess pytest under tests/dashboard/. Parses junit.xml; returns per-test failures with message + trace tail. Persists workspace/logs/dashboard_tests.json so the next iteration can read the failure set. trace.zip files under test-results/ are time-travel debug UIs (`playwright show-trace`).",
        "category": "viz",
        "inputSchema": {
            "type": "object",
            "properties": {
                "only": {"type": "string", "description": "Pytest node-id filter."},
                "visual": {"type": "boolean", "description": "Enable visual regression."},
                "update_snapshots": {"type": "boolean"},
                "timeout": {"type": "number"},
            },
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
    # ── New audit tools (code, prose, claims, preregistration, master) ──
    "tool_audit_code_quality": {
        "short": "Per-script audit: ruff + AST complexity + smells + docstrings.",
        "description": "Walks workspace/<step>/scripts/*.py. Runs ruff if installed; runs an AST-based scan for cyclomatic complexity (>10 warn, >20 block), function length (>80 warn, >150 block), missing module/public-function docstrings, bare-except / import-* / eval-exec / hardcoded-absolute-path smells. Writes workspace/logs/code_quality.md; returns blockers that the master quality auditor consumes.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "string"},
                "run_ruff": {"type": "boolean"},
                "run_mypy": {"type": "boolean"},
            },
        },
    },
    "tool_audit_prose": {
        "short": "Prose audit: hedging, vague quantifiers, passive voice, reading level, reporting-standard coverage.",
        "description": "Audits synthesis/*.md + every conclusions.md. Flags 40+ hedge phrases, numbers-without-precision ('many subjects'), passive-voice ratio, Flesch-Kincaid grade level, causal language on observational designs. Checks CONSORT / STROBE / PRISMA / ARRIVE section coverage based on the project's domain. Writes workspace/logs/prose_audit.md.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"}},
                "is_observational": {"type": "boolean"},
            },
        },
    },
    "tool_audit_claims": {
        "short": "Verify every quantitative number in the paper traces to a workspace output.",
        "description": "Extracts every numeric claim (AUROC = 0.84, p = 0.012, n = 423) from synthesis/paper.md (or target_path) and confirms each appears verbatim or within 1% tolerance in some workspace CSV/TSV/JSON/MD/TXT. Catches AI-hallucinated numbers. BLOCKS tool_synthesize when ungrounded claims are found.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string", "description": "Default synthesis/paper.md."},
                "tolerance": {"type": "number", "description": "Float tolerance (default 0.01 = 1%)."},
            },
        },
    },
    "tool_audit_evalue": {
        "short": "E-value sensitivity to unmeasured confounding (VanderWeele & Ding 2017).",
        "description": "Given an observed risk ratio + 95% CI, computes the E-value — the minimum strength of association an unmeasured confounder would need (with BOTH exposure and outcome) to explain away the observed effect. Persists workspace/<step>/outputs/reports/evalue_report.md.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "risk_ratio": {"type": "number"},
                "ci_lower": {"type": "number"},
                "ci_upper": {"type": "number"},
            },
            "required": ["risk_ratio"],
        },
    },
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
        "short": "Run every quality gate in one call — completeness + code + prose + claims + prereg diff.",
        "description": "Master auditor. Runs tool_audit_step_completeness + tool_audit_code_quality + tool_audit_prose + tool_audit_claims + tool_preregister_diff in one shot; aggregates the blocker set; writes workspace/logs/audit_master.md. tool_synthesize calls this as its first gate when no `section` is given.",
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
        "description": "Compile workspace findings into a publishable output. Without `section`, builds the full paper/poster/etc with numbered figures + tables + verified citations. With `section`, builds one section at a time (abstract | introduction | methods | results | discussion | conclusion | references). `output_type` drives the citation cap and section structure.",
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
            },
        },
    },
    "tool_latex_compile": {
        "description": "Compile synthesis/paper.tex to PDF (pdflatex + bibtex).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_poster_create": {
        "description": "Generate a LaTeX poster (tikzposter) from the workspace. Layouts: `billboard` (default — Mike Morrison Better Poster pattern: giant plain-English headline + ammo bar of methods/findings/limitations + QR code) or `classic` (two-column IMRAD). Audience profile gates copy density and call-to-action: academic_conference (default), symposium, industry, teaching.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout": {
                    "type": "string",
                    "description": "billboard (default — readable from across the hall) | classic (IMRAD two-column)",
                },
                "audience": {
                    "type": "string",
                    "description": "academic_conference (default) | symposium | industry | teaching",
                },
            },
        },
    },
    "tool_dashboard_create": {
        "description": "Generate a standalone, offline HTML dashboard (sortable tables, lightbox gallery, light/dark toggle, print-friendly) at synthesis/dashboard.html. Tailored to audience: academic | executive | technical | teaching.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "audience": {
                    "type": "string",
                    "description": "academic (default) | executive | technical | teaching",
                },
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
    "tool_dead_end_lessons": {
        "description": "Pull lessons from every __DEAD_END folder so future steps don't repeat them. Writes workspace/logs/dead_end_lessons.md.",
        "category": "research",
        "inputSchema": {"type": "object", "properties": {}},
    },
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
    "tool_step_env_lock": {
        "short": "Pin per-step env (requirements + python_version + optional conda / Docker / Apptainer / entrypoint).",
        "description": "Locks the active step's environment/ for years-later reproduction. Optional artefacts via write_conda_yaml, write_dockerfile, write_apptainer, write_entrypoint. Prefer over sys_env_snapshot for any step you intend to publish.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_id": {
                    "type": "string",
                    "description": "Numbered step slug (e.g. '01_baseline_eda'). Defaults to the most-recent active step but a warning is returned.",
                },
                "write_conda_yaml": {"type": "boolean"},
                "write_dockerfile": {"type": "boolean"},
                "write_apptainer": {"type": "boolean", "description": "Emit step.def for HPC Apptainer/Singularity."},
                "write_entrypoint": {"type": "boolean", "description": "Emit environment/entrypoint.sh (default true)."},
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
        protocols = list_protocols()
        return _text(_success({"protocols": protocols}))
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
            response = {"content": _yaml.dump(data, sort_keys=False)}
            if model_profile == "small":
                response["note"] = "Loaded in light mode (small model profile)."
            if p_name != "guidance/session_boot":
                response["_reminder"] = (
                    "Confirm session_boot has run this session; if not, load it first."
                )
            response["_load_tip"] = (
                "Loaded as full. Prefer format='summary' (~300 tokens) or "
                "format='step' + step_id='<id>' to save context."
            )
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


def _handle_tool_plan_advance(name, arguments, root):
    from research_os.tools.actions.router import advance_plan

    res = advance_plan(
        root, override_gate=bool(arguments.get("override_gate", False)),
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
    return _text(
        _success(
            {
                "project_name": state.get("project_name") or state.get("project", ""),
                "pipeline_stage": state.get("pipeline_stage", state.get("phase", "init")),
                "step": state.get("step", 0),
                "current_path": state.get("current_path", "main"),
                "paths_summary": {k: v.get("status") for k, v in paths.items()},
                "active_hypotheses": state.get("active_hypotheses", []),
                "resumable_from": state.get("resumable_from"),
            }
        )
    )


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
    p = root / arguments["directory"]
    if not p.exists() or not p.is_dir():
        return _text(_error("Directory not found"))
    files = [str(f.relative_to(root)) for f in p.rglob("*") if f.is_file()]
    return _text(_success({"files": files}))


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
        res = create_numbered_experiment(
            root,
            arguments["name"],
            hypothesis=arguments.get("hypothesis", ""),
            branch_of=arguments.get("branch_of"),
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
    from research_os.tools.actions.state.path import finalize_path

    res = finalize_path(arguments.get("path_name"), root)
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
    res = env_snapshot(root)
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
    q = arguments["query"]
    limit = arguments.get("limit", 5)
    handler_map = {
        "tool_search_semantic_scholar": search_semantic_scholar,
        "tool_search_pubmed": search_pubmed,
        "tool_search_crossref": search_crossref,
        "tool_search_arxiv": search_arxiv,
        "tool_search_web": search_web,
    }
    fn = handler_map[name]
    _log_search(root, name, q, 0)
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


def _handle_tool_audit_synthesis(name, arguments, root):
    from research_os.tools.actions.audit import audit_synthesis

    res = audit_synthesis(arguments["paper_path"], root)
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
    from research_os.tools.actions.synthesis.synthesize import synthesize_workspace

    # Server-enforced quality gate. Single-section synthesis (e.g. just
    # the abstract) clears with a lightweight check; full-document
    # synthesis must pass the master quality auditor.
    skip_gate = arguments.get("override_completeness_gate", False)
    full_doc = not arguments.get("section")
    if full_doc and not skip_gate:
        gate = audit_quality_full(
            root,
            # Skip claims gate on the FIRST synthesis (paper.md doesn't
            # exist yet to extract claims from).
            skip=arguments.get("skip_gates") or ["claims"],
        )
        if gate.get("status") == "error":
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
    elif not skip_gate:
        # Lightweight gate for single-section calls — still want focal
        # figure + caption coverage.
        sc = audit_step_completeness(root)
        if sc.get("status") == "error":
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
    )
    if "error" in res:
        return _text(_error(res["error"]))

    # After writing the full paper, run the claims audit as a second
    # pass so any AI hallucinations surface immediately.
    if full_doc and not skip_gate:
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


def _handle_tool_poster_create(name, arguments, root):
    from research_os.tools.actions.synthesis.latex import create_poster

    return _text(_success(create_poster(
        root,
        layout=arguments.get("layout", "billboard"),
        audience=arguments.get("audience", "academic_conference"),
    )))


def _handle_tool_dashboard_create(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_step_completeness
    from research_os.tools.actions.synthesis.latex import create_dashboard

    skip_gate = arguments.get("override_completeness_gate", False)
    if not skip_gate:
        gate = audit_step_completeness(root)
        if gate.get("status") == "error":
            # Soft-fail to a warning the dashboard still renders. The
            # dashboard is more useful as a "where are we now" snapshot
            # than the paper, so we don't BLOCK it — we annotate that
            # blockers exist so the editor sees them.
            arguments.setdefault("_completeness_warnings", gate.get("blockers"))

    res = create_dashboard(
        root,
        title=arguments.get("title"),
        audience=arguments.get("audience", "academic"),
    )
    if res.get("status") == "success":
        if arguments.get("_completeness_warnings"):
            res["completeness_warnings"] = arguments["_completeness_warnings"]
            res["advice"] = (
                "Dashboard rendered, but step-completeness audit flagged "
                f"{len(arguments['_completeness_warnings'])} blocker(s). "
                "Resolve them before the FINAL deliverable."
            )
        return _text(_success(res))
    return _text(_error(res.get("message", "dashboard create failed")))


def _handle_tool_audit_step_completeness(name, arguments, root):
    from research_os.tools.actions.audit.audit import audit_step_completeness

    return _text(_success(audit_step_completeness(
        root, step_id=arguments.get("step_id"),
    )))


def _handle_tool_figure_create(name, arguments, root):
    from research_os.tools.actions.viz import figure_create

    try:
        res = figure_create(
            root=root,
            step_id=arguments["step_id"],
            name=arguments["name"],
            kind=arguments["kind"],
            data=arguments["data"],
            x=arguments.get("x"),
            y=arguments.get("y"),
            z=arguments.get("z"),
            error=arguments.get("error"),
            color_by=arguments.get("color_by"),
            bins=int(arguments.get("bins", 30)),
            regression=bool(arguments.get("regression", False)),
            palette=arguments.get("palette", "qualitative"),
            style=arguments.get("style", "default"),
            title=arguments.get("title", ""),
            xlabel=arguments.get("xlabel", ""),
            ylabel=arguments.get("ylabel", ""),
            caption=arguments.get("caption", ""),
            plain_english=arguments.get("plain_english"),
            interactive=bool(arguments.get("interactive", False)),
            backend=arguments.get("backend", "matplotlib"),
            extra=arguments.get("extra"),
        )
    except KeyError as e:
        return _text(_error(f"Missing required parameter: {e}"))
    except Exception as e:
        return _text(_error(f"figure_create failed: {e}"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "figure_create failed")))


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
    from research_os.tools.actions.audit.code_quality import audit_code_quality

    return _text(_success(audit_code_quality(
        root,
        step_id=arguments.get("step_id"),
        run_ruff=bool(arguments.get("run_ruff", True)),
        run_mypy=bool(arguments.get("run_mypy", False)),
    )))


def _handle_tool_audit_prose(name, arguments, root):
    from research_os.tools.actions.audit.prose_quality import audit_prose

    return _text(_success(audit_prose(
        root,
        targets=arguments.get("targets"),
        is_observational=arguments.get("is_observational"),
    )))


def _handle_tool_audit_claims(name, arguments, root):
    from research_os.tools.actions.audit.claim_grounding import audit_claims

    return _text(_success(audit_claims(
        root,
        target_path=arguments.get("target_path"),
        tolerance=float(arguments.get("tolerance", 0.01)),
    )))


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
    from research_os.tools.actions.audit.audit import audit_quality_full

    return _text(_success(audit_quality_full(
        root,
        target_path=arguments.get("target_path"),
        skip=arguments.get("skip"),
    )))


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
    env_used = False
    if env_root and Path(env_root).expanduser().resolve() == root:
        via = "RESEARCH_OS_WORKSPACE env var"
        env_used = True
    elif (root / ".os_state").exists():
        via = "cwd walked up to .os_state/"
    return _text(_success({
        "project_root": str(root),
        "has_os_state": (root / ".os_state").exists(),
        "resolved_via": via,
        "env_var_set": env_used,
        "advice": (
            "This server is GLOBAL — one process serves multiple projects. "
            "Each request resolves a project per these rules: "
            "(1) RESEARCH_OS_WORKSPACE env var (the IDE MCP config usually "
            "sets this to ${workspaceFolder}); (2) cwd walked up for "
            "`.os_state/`; (3) cwd. If `has_os_state` is False, the "
            "project hasn't been scaffolded — tell the researcher to run "
            "`research-os init` here, or to open a folder that has been "
            "initialised."
        ),
    }))


def _handle_sys_help(name, arguments, root):
    """Compact AI orientation block — how to use Research OS efficiently."""
    topic = (arguments or {}).get("topic", "").strip().lower()

    core = {
        "what_research_os_is": (
            "Research OS is an MCP server that scaffolds + audits "
            "research projects end-to-end (data → publication) AND "
            "supports off-axis work (viz only / talks / lay summaries / "
            "method consultation / reproduction / mid-pipeline entry). "
            "One install, one global server, per-project init."
        ),
        "tool_namespaces": {
            "sys_*":  "system / workspace / state / files / paths / checkpoints",
            "tool_*": "research work — search, exec, audit, synthesis, intake, plan",
            "mem_*":  "append-only memory — methods, citations, decisions, hypotheses",
        },
        "session_start_pattern": [
            "1. sys_boot — one call returns state + config + history + advice",
            "2. (await researcher's first message)",
            "3. tool_route(prompt) — picks the right protocol L1→L2→L3",
            "4. If `complexity:high`, tool_plan_turn → walk via tool_plan_advance",
            "5. If `complexity:low`, run shortcut_tool OR sys_protocol_get format='summary'",
        ],
        "protocol_categories": {
            "guidance":      "session + flow control (boot / resume / handoff / autopilot / casual / mid_entry / disagree)",
            "discover":      "intake + question lock-in",
            "domain":        "domain classification + study design",
            "methodology":   "method picking + per-method protocols (ML / Bayes / RCT / qualitative / consult / EDA / comparison / etc.)",
            "literature":    "search + systematic review + evidence synthesis + comparative paper review",
            "writing":       "per-section drafting (methods / results / discussion / limitations / end_matter)",
            "visualization": "figures (rules / workflow / critique / multi-panel / arc / a11y)",
            "synthesis":     "final deliverables (paper / abstract / poster / dashboard / slides / lay / handout / report / grant / null_findings / progress_update / from_inputs / cover_letter / title)",
            "audit":         "quality audit + pre-submission checklist",
            "reproducibility": "snapshot + verify everything reruns clean",
        },
        "routing_principle": (
            "tool_route is the FIRST tool after every researcher message. "
            "It returns a tight routing decision in ~250 tokens. Don't "
            "search for protocols manually; let the router pick. When "
            "ambiguous it returns `ask_user` — ask that question and "
            "re-route, never guess."
        ),
        "anti_patterns": [
            "Don't call sys_state_get + sys_config_get + sys_protocol_history separately — use sys_boot.",
            "Don't load full protocols with sys_protocol_get format='full' when summary suffices.",
            "Don't one-shot 400-line scripts — tool_plan_step + sub-task pipelines (see guidance/analysis_plan).",
            "Don't invent citations — synthesis tools VERIFY every citation.",
            "Don't write under inputs/raw_data or inputs/literature — server blocks it.",
        ],
        "docs_for_humans": [
            "docs/START.md — install + first project + cheatsheet",
            "docs/RESEARCHER_GUIDE.md — full workflow walkthrough",
            "docs/USE_CASES.md — role × goal × output map",
            "docs/PROTOCOLS.md — protocol catalogue + triggers",
            "docs/TOOLS.md — every MCP tool with example calls",
            "docs/PROTOCOL_DOCTRINE.md — scaffold-not-script principle",
            "docs/FAQ.md — common questions",
        ],
    }

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
                "tool_audit_code_quality",
                "tool_audit_prose",
                "tool_audit_claims",
                "tool_audit_figure_full",
                "tool_audit_citations",
                "tool_audit_assumptions",
                "tool_audit_reproducibility",
                "tool_preregister_diff",
            ],
        }))

    return _text(_success(core))


_HANDLERS = {
    # routing (call these first)
    "sys_boot": _handle_sys_boot,
    "tool_route": _handle_tool_route,
    "tool_plan_advance": _handle_tool_plan_advance,
    "tool_plan_turn": _handle_tool_plan_turn,
    "tool_plan_clear": _handle_tool_plan_clear,
    "sys_tool_describe": _handle_sys_tool_describe,
    "sys_active_tools": _handle_sys_active_tools,
    "sys_active_project": _handle_sys_active_project,
    "sys_help": _handle_sys_help,
    "tool_cache_clear": _handle_tool_cache_clear,
    "tool_step_env_lock": _handle_tool_step_env_lock,
    "tool_workflow_dag": _handle_tool_workflow_dag,
    # protocol
    "sys_protocol_get": _handle_sys_protocol_get,
    "sys_protocol_list": _handle_sys_protocol_list,
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
    # audit
    "tool_audit_synthesis": _handle_tool_audit_synthesis,
    "tool_audit_power": _handle_tool_audit_power,
    "tool_audit_assumptions": _handle_tool_audit_assumptions,
    "tool_audit_figure": _handle_tool_audit_figure,
    "tool_audit_citations": _handle_tool_audit_citations,
    "tool_audit_reproducibility": _handle_tool_audit_reproducibility,
    "tool_audit_step_completeness": _handle_tool_audit_step_completeness,
    "tool_figure_create": _handle_tool_figure_create,
    "tool_figure_caption_synthesise": _handle_tool_figure_caption_synthesise,
    "tool_audit_figure_full": _handle_tool_audit_figure_full,
    "tool_figure_palette": _handle_tool_figure_palette,
    "tool_step_pipeline_define": _handle_tool_step_pipeline_define,
    "tool_step_pipeline_run": _handle_tool_step_pipeline_run,
    "tool_step_pipeline_status": _handle_tool_step_pipeline_status,
    "tool_step_pipeline_diagram": _handle_tool_step_pipeline_diagram,
    "tool_dashboard_test_generate": _handle_tool_dashboard_test_generate,
    "tool_dashboard_test_run": _handle_tool_dashboard_test_run,
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
    # New audit suite.
    "tool_audit_code_quality": _handle_tool_audit_code_quality,
    "tool_audit_prose": _handle_tool_audit_prose,
    "tool_audit_claims": _handle_tool_audit_claims,
    "tool_audit_evalue": _handle_tool_audit_evalue,
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
    "tool_poster_create": _handle_tool_poster_create,
    "tool_dashboard_create": _handle_tool_dashboard_create,
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
    # session resume + digest + dead-end lessons + quick review
    "tool_session_resume": _handle_tool_session_resume,
    "tool_progress_digest": _handle_tool_progress_digest,
    "tool_dead_end_lessons": _handle_tool_dead_end_lessons,
    "tool_quick_review": _handle_tool_quick_review,
    "sys_dep_inventory": _handle_sys_dep_inventory,
}

# Aliases — keep the AI's life easy when it forgets exact naming.
_ALIASES = {
    # Dot notation is handled generically by the dispatcher's dot→underscore
    # rewrite, no need to list here.
    #
    # Only aliases that an active researcher might still type at the prompt
    # survive. Aliases that pointed at stale names with no real callers have
    # been removed — they were costing list-tools tokens without paying back.
    "tool_audit_figure_quality": "tool_audit_figure_full",
    "tool_audit_statistical_power": "tool_audit_power",
    "sys_state_summary": "sys_state_get",
    "tool_log_decision": "mem_decision_log",
    "view_workspace_tree": "sys_workspace_tree",
}


def _resolve_tool_name(name: str) -> str:
    """Normalize incoming tool name: dots→underscores, then alias lookup."""
    canonical = name.replace(".", "_")
    return _ALIASES.get(canonical, canonical)


def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error("Rate limit exceeded — slow down."))
    resolved = _resolve_tool_name(name)
    logger.info(f"Tool call: {name} -> {resolved}")
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
            "DEPRECATED in v1.0.0. Workspace is auto-resolved from the "
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
