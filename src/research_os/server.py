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


def _lazy_import(module_name: str, names: list[str]):
    try:
        mod = __import__(module_name, fromlist=names)
        return [getattr(mod, name) for name in names]
    except ImportError:
        return [_MissingDependency(name) for name in names]


search_web, scrape_web = _lazy_import(
    "research_os.tools.actions.web_search", ["search_web", "scrape_web"]
)
package_install, env_snapshot, env_docker_generate = _lazy_import(
    "research_os.tools.actions.environment",
    ["package_install", "env_snapshot", "env_docker_generate"],
)
create_checkpoint, rollback_checkpoint, list_checkpoints = _lazy_import(
    "research_os.tools.actions.checkpoint",
    ["create_checkpoint", "rollback_checkpoint", "list_checkpoints"],
)
create_path, abandon_path, list_paths = _lazy_import(
    "research_os.tools.actions.path", ["create_path", "abandon_path", "list_paths"]
)
download_literature, = _lazy_import(
    "research_os.tools.actions.literature", ["download_literature"]
)
get_config, set_config, init_config, validate_config = _lazy_import(
    "research_os.tools.actions.config",
    ["get_config", "set_config", "init_config", "validate_config"],
)
notify_researcher, session_handoff = _lazy_import(
    "research_os.tools.actions.interaction",
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
    "research_os.tools.actions.profiling", ["_profile_inputs"]
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


# Backward-compatible aliases for older callers / tests.
def _envelope(data: Any = None, *, status: str = "success") -> dict:
    if status == "error":
        return {"status": "error", "data": {"error": data if isinstance(data, str) else (data or {})}}
    return {"status": status, "data": data or {}}


def _success_envelope(data: Any = None) -> dict:
    return _envelope(data, status="success")


def _error_envelope(message: str) -> dict:
    return _envelope(message, status="error")


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool definitions — keep the surface tight: one tool per concept.
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    # ── Protocols / guidance ──────────────────────────────────────────
    "sys_protocol_get": {
        "description": "Load a protocol YAML by name (e.g. 'guidance/project_startup'). Returns the steps, expected_outputs, and next_protocol the AI should follow.",
        "category": "protocol",
        "inputSchema": {
            "type": "object",
            "properties": {"protocol_name": {"type": "string"}},
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
        "description": "Create the next numbered experiment folder (workspace/NN_<slug>/). Populates README, conclusions, scripts/, data/, outputs/, environment/ subdirs. Updates state.",
        "category": "path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short slug, e.g. baseline_eda"},
                "hypothesis": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    "sys_path_abandon": {
        "description": "Mark an experiment as a dead end. Renames the folder to NN_<slug>__DEAD_END and writes the rationale to analysis.md.",
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
        "description": "Download a paper PDF into inputs/literature/.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["url", "filename"],
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

    # ── Synthesis & output ────────────────────────────────────────────
    "tool_synthesize_plan": {
        "description": "Inspect available sources (methods.md, conclusions per step, citations) and return the recommended section ordering. Call BEFORE tool_synthesize.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_synthesize": {
        "description": "Compile workspace findings into synthesis/paper.md (or specific section). Section parameter generates one section at a time: abstract | introduction | methods | results | discussion | conclusion.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "description": "markdown | latex | both (default: markdown)",
                },
                "section": {"type": "string"},
            },
        },
    },
    "tool_latex_compile": {
        "description": "Compile synthesis/paper.tex to PDF (pdflatex + bibtex).",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_poster_create": {
        "description": "Generate a LaTeX poster (tikzposter) from the workspace.",
        "category": "synthesis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool_dashboard_create": {
        "description": "Generate a standalone HTML dashboard summarising the project (key figures, tables, conclusions). Written to synthesis/dashboard.html.",
        "category": "synthesis",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
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
        "description": "Execute a Jupyter .ipynb in place (jupyter nbconvert --execute --inplace).",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "timeout": {"type": "number"},
                "kernel": {"type": "string"},
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
    profile = _read_profile(root)
    model_profile = profile.get("model_profile", "medium")
    try:
        import yaml as _yaml

        data = load_protocol(p_name, model_profile=model_profile)
        response = {"content": _yaml.dump(data, sort_keys=False)}
        if model_profile == "small":
            response["note"] = "Loaded in light mode (small model profile)."
        if p_name != "guidance/session_boot":
            response["_reminder"] = (
                "Confirm session_boot has run this session; if not, load it first."
            )
        return _text(_success(response))
    except Exception as e:
        return _text(_error(str(e)))


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
    valid = ["cursor", "claude", "antigravity", "opencode", "vscode"]
    ide_flags = valid if ide == "all" else [i.strip() for i in ide.split(",") if i.strip() in valid]
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
    from research_os.tools.actions.md_audit import validate_md_template

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
    res = download_literature(arguments["url"], arguments["filename"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "download failed")))


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
    from research_os.tools.actions.execution import (
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
    from research_os.tools.actions.synthesize import synthesize_plan

    return _text(_success(synthesize_plan(root)))


def _handle_tool_synthesize(name, arguments, root):
    from research_os.tools.actions.synthesize import synthesize_workspace

    fmt = arguments.get("output_format", "markdown")
    sec = arguments.get("section")
    res = synthesize_workspace(root, output_format=fmt, section=sec)
    if "error" in res:
        return _text(_error(res["error"]))
    return _text(_success(res))


def _handle_tool_latex_compile(name, arguments, root):
    from research_os.tools.actions.latex import latex_compile

    return _text(_success(latex_compile(root)))


def _handle_tool_poster_create(name, arguments, root):
    from research_os.tools.actions.latex import create_poster

    return _text(_success(create_poster(root)))


def _handle_tool_dashboard_create(name, arguments, root):
    from research_os.tools.actions.latex import create_dashboard

    res = create_dashboard(root, title=arguments.get("title"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "dashboard create failed")))


# ── Research / reasoning ──────────────────────────────────────────────


def _handle_tool_research_method(name, arguments, root):
    from research_os.tools.actions.research import research_method

    res = research_method(arguments["query"], root, limit=int(arguments.get("limit", 5)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "research_method failed")))


def _handle_tool_research_tool(name, arguments, root):
    from research_os.tools.actions.research import research_tool

    res = research_tool(arguments["task"], root, language=arguments.get("language", "any"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "research_tool failed")))


def _handle_tool_external_tool_instructions(name, arguments, root):
    from research_os.tools.actions.research import external_tool_instructions

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


def _handle_tool_plan_step(name, arguments, root):
    from research_os.tools.actions.research import plan_step

    res = plan_step(
        arguments["goal"], root, max_substeps=int(arguments.get("max_substeps", 6))
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "plan_step failed")))


# ── Intake auto-fill ──────────────────────────────────────────────────


def _handle_tool_intake_autofill(name, arguments, root):
    from research_os.tools.actions.intake import intake_autofill

    res = intake_autofill(root, overwrite=bool(arguments.get("overwrite", False)))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "intake_autofill failed")))


# ── Background tasks ──────────────────────────────────────────────────


def _handle_tool_task_run(name, arguments, root):
    from research_os.tools.actions.tasks import task_run

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
    from research_os.tools.actions.tasks import task_status

    res = task_status(
        arguments["task_id"], root, tail_lines=int(arguments.get("tail_lines", 50))
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_status failed")))


def _handle_tool_task_list(name, arguments, root):
    from research_os.tools.actions.tasks import task_list

    res = task_list(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_list failed")))


def _handle_tool_task_kill(name, arguments, root):
    from research_os.tools.actions.tasks import task_kill

    res = task_kill(
        arguments["task_id"], root, signal_name=arguments.get("signal_name", "TERM")
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "task_kill failed")))


# ── Notebook / R-markdown ─────────────────────────────────────────────


def _handle_tool_notebook_exec(name, arguments, root):
    from research_os.tools.actions.notebook import execute_notebook

    res = execute_notebook(
        arguments["notebook_path"],
        root,
        timeout=int(arguments.get("timeout", 1800)),
        kernel=arguments.get("kernel", "python3"),
    )
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "notebook exec failed")))


def _handle_tool_rmarkdown_render(name, arguments, root):
    from research_os.tools.actions.notebook import render_rmarkdown

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
    from research_os.tools.actions.memory import hypothesis_add

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
    from research_os.tools.actions.memory import hypothesis_update

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
    from research_os.tools.actions.memory import hypothesis_list

    res = hypothesis_list(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "hypothesis_list failed")))


_HANDLERS = {
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
}

# Aliases — keep the AI's life easy when it forgets exact naming.
_ALIASES = {
    # Legacy: dot notation
    # Handled generically by dot→underscore in dispatcher.
    # Legacy: old tool names
    "sys_guidance_get": "sys_protocol_get",
    "sys_guidance_list": "sys_protocol_list",
    "sys_guidance_validate": "sys_protocol_validate",
    "sys_md_validate": "sys_file_validate_md",
    "tool_audit_md_consistency": "sys_file_validate_md",
    "view_workspace_tree": "sys_workspace_tree",
    "tool_env_freeze": "sys_env_snapshot",
    "tool_env_restore": "sys_env_snapshot",
    "tool_log_decision": "mem_decision_log",
    "tool_audit_statistical_power": "tool_audit_power",
    "tool_audit_figure_quality": "tool_audit_figure",
    "tool_audit_reproducibility_full": "tool_audit_reproducibility",
    "sys_state_summary": "sys_state_get",
    "sys_state_summary_md": "sys_state_get",
    "sys_state_health": "sys_state_get",
    "sys_state_minimal_context": "sys_state_get",
    "sys_config_profile": "sys_config_get",
    "sys_config_init": "sys_workspace_scaffold",
    "sys_config_explain": "sys_config_get",
    "sys_tool_info": "sys_protocol_get",
    "sys_tool_search": "sys_protocol_list",
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


if HAS_MCP:
    server = Server("research-os")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        root = Path(os.getcwd())
        profile = _read_profile(root)
        tools: list[Tool] = []
        for name, schema in TOOL_DEFINITIONS.items():
            desc = schema["description"]
            if profile.get("model_profile") == "small":
                # Keep only the first sentence to save context for small models.
                desc = desc.split(".")[0] + "."
            tools.append(
                Tool(name=name, description=desc, inputSchema=schema["inputSchema"])
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        root = Path(os.getcwd())
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio")
    parser.add_argument("--workspace", type=str)
    args = parser.parse_args()

    if args.workspace:
        os.chdir(args.workspace)

    _inject_api_keys(Path(os.getcwd()))

    if HAS_MCP:
        import asyncio

        asyncio.run(run_stdio())
    else:
        sys.exit("MCP package missing. Install with: pip install 'research-os[all]'")


if __name__ == "__main__":
    main()
