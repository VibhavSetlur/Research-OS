#!/usr/bin/env python3
"""Research OS MCP server v0.1.0 — Research Guidance Engine"""

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
    def __init__(self, name):
        self.name = name
    def __call__(self, *args, **kwargs):
        raise RuntimeError(f"Optional dependency missing for {self.name}. Please install required extras.")

def _lazy_import(module_name, names):
    try:
        mod = __import__(module_name, fromlist=names)
        return [getattr(mod, name) for name in names]
    except ImportError:
        return [_MissingDependency(name) for name in names]

search_web, scrape_web = _lazy_import("research_os.tools.actions.web_search", ["search_web", "scrape_web"])
package_install, = _lazy_import("research_os.tools.actions.environment", ["package_install"])
create_checkpoint, rollback_checkpoint, list_checkpoints = _lazy_import("research_os.tools.actions.checkpoint", ["create_checkpoint", "rollback_checkpoint", "list_checkpoints"])
create_path, abandon_path, list_paths = _lazy_import("research_os.tools.actions.path", ["create_path", "abandon_path", "list_paths"])
download_literature, = _lazy_import("research_os.tools.actions.literature", ["download_literature"])
get_config, set_config, init_config, validate_config = _lazy_import("research_os.tools.actions.config", ["get_config", "set_config", "init_config", "validate_config"])
notify_researcher, checkpoint_pending, checkpoint_approve, session_handoff = _lazy_import("research_os.tools.actions.interaction", ["notify_researcher", "checkpoint_pending", "checkpoint_approve", "session_handoff"])
discover_mcp, = _lazy_import("research_os.tools.actions.external_mcp", ["discover_mcp"])
task_monitor, task_kill = _lazy_import("research_os.tools.actions.task", ["task_monitor", "task_kill"])
search_semantic_scholar, search_pubmed, search_crossref = _lazy_import("research_os.tools.actions.search", ["search_semantic_scholar", "search_pubmed", "search_crossref"])
load_protocol, list_protocols, validate_protocol, get_next_protocol = _lazy_import("research_os.tools.actions.protocol", ["load_protocol", "list_protocols", "validate_protocol", "get_next_protocol"])
_profile_inputs, = _lazy_import("research_os.tools.actions.profiling", ["_profile_inputs"])

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
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, max_calls: int = 100, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = defaultdict(list)

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
# Envelope
# ---------------------------------------------------------------------------


def _envelope(data: Any = None, *, status: str = "success") -> dict:
    return {"status": status, "data": data or {}}


def _success_envelope(data: Any = None) -> dict:
    return _envelope(data, status="success")


def _error_envelope(message: str) -> dict:
    return _envelope({"error": message}, status="error")


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = {
    "sys.guidance.get": {
        "description": "Returns the full YAML content of a guidance protocol.",
        "category": "guidance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {
                    "type": "string",
                    "description": "Protocol name (e.g., domain_analysis)",
                }
            },
            "required": ["protocol_name"],
        },
    },
    "sys.guidance.list": {
        "description": "Lists all available protocols with one-line summaries.",
        "category": "guidance",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.guidance.validate": {
        "description": "Validates if the expected outputs of a protocol exist in the workspace.",
        "category": "guidance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {
                    "type": "string",
                    "description": "Protocol name (e.g., domain_analysis)",
                }
            },
            "required": ["protocol_name"],
        },
    },
    "sys.protocol.next": {
        "description": "Returns the recommended next protocol based on pipeline stage and which expected outputs are present. Use after session_boot to confirm the right next action.",
        "category": "guidance",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.workspace.scaffold": {
        "description": "Create the full directory structure for a new project.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "git_init": {
                    "type": "boolean",
                    "description": "Initialize a git repository (default: false)",
                    "default": False,
                },
                "ide": {
                    "type": "string",
                    "description": "IDE(s) to configure. Use 'all' for all supported IDEs, or comma-separated: 'cursor,claude,opencode,vscode,antigravity'. Default: all",
                    "default": "all",
                },
            },
        },
    },
    "sys.file.read": {
        "description": "Securely read a file from the workspace.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys.file.write": {
        "description": "Securely write to a file in the workspace.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "content": {"type": "string"},
                "force": {
                    "type": "boolean",
                    "description": "Force overwrite even in protected directories like synthesis/",
                },
            },
            "required": ["filepath", "content"],
        },
    },
    "sys.file.list": {
        "description": "List files in a directory.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
    "sys.file.delete": {
        "description": "Delete a file.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "sys.workspace.tree": {
        "description": "Returns a structured tree of workspace/ showing experiment paths, scripts, outputs, and key files. Use at session start for orientation.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "depth": {"type": "number", "description": "Tree depth (default 3)"},
                "include_files": {"type": "boolean", "description": "Include file names (default true)"},
            },
        },
    },
    "sys.state.get": {
        "description": "Get full workspace state.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.state.summary": {
        "description": "Get a brief summary of the state.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.state.summary_md": {
        "description": "Return .os_state/os_state.md content — a human-readable project status snapshot.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.state.health": {
        "description": "Returns current context estimate, paths, and handoff recommendation.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.session.handoff": {
        "description": "Creates a structured markdown summary + next step prompt for session handoff.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.state.minimal_context": {
        "description": "Get a <=500 token snapshot of the current state, optimized for small models.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.checkpoint.create": {
        "description": "Snapshot workspace state.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"description": {"type": "string"}},
        },
    },
    "sys.checkpoint.rollback": {
        "description": "Rollback to a checkpoint.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"checkpoint_id": {"type": "string"}},
            "required": ["checkpoint_id"],
        },
    },
    "sys.checkpoint.list": {
        "description": "List all checkpoints.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.checkpoint.pending": {
        "description": "Register a pending action for approval.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "requires_approval": {"type": "boolean"},
            },
            "required": ["description", "requires_approval"],
        },
    },
    "sys.checkpoint.approve": {
        "description": "Approve a pending action.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.path.create": {
        "description": "Create the next numbered experiment folder with a unique descriptive name (format: {step_number}_{descriptor}). Optionally append _path_{N} to start a new research track.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short name for the experiment (e.g. bayesian_model)"},
            },
            "required": ["name"],
        },
    },
    "sys.path.abandon": {
        "description": "Mark an experiment path as a dead end (renames directory with __DEAD_END suffix).",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_name": {"type": "string", "description": "Name of the path directory (e.g. 03_bayesian_model)"},
                "rationale": {"type": "string", "description": "Why this path was abandoned"},
            },
            "required": ["path_name", "rationale"],
        },
    },
    "sys.path.list": {
        "description": "List all numbered experiment paths with their status.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.config.init": {
        "description": "Initialize researcher configuration.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.config.get": {
        "description": "Get researcher configuration.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.config.set": {
        "description": "Set a specific config value.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"],
        },
    },
    "sys.config.validate": {
        "description": "Validate configuration and API keys.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.config.profile": {
        "description": "Return only behavioral profile fields (autonomy, expertise, model_profile) in <100 tokens. Use at session start instead of full config.get.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "sys.config.explain": {
        "description": "Return documentation for any config key, e.g. interaction.autonomy_level.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Dot-notation config key, e.g. interaction.autonomy_level"}
            },
            "required": ["key"],
        },
    },
    "sys.notify": {
        "description": "Notify researcher.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}, "level": {"type": "string"}},
            "required": ["message", "level"],
        },
    },
    "sys.external_mcp.discover": {
        "description": "Discover external MCP servers.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool.task.create": {
        "description": "Create a background task for long-running operations.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"task_description": {"type": "string"}},
            "required": ["task_description"],
        },
    },
    "sys.task.monitor": {
        "description": "Monitor a background task.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    "sys.task.kill": {
        "description": "Kill a background task.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    "sys.tool.info": {
        "description": "Get full schema for a tool.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
            "required": ["tool_name"],
        },
    },
    "sys.tool.search": {
        "description": "Search tools by description.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "tool.audit.synthesis": {
        "description": "Audit a generated manuscript for completeness and scientific claims.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_path": {"type": "string"}},
            "required": ["paper_path"],
        },
    },
    "tool.audit.statistical_power": {
        "description": "Compute post-hoc power for statistical tests. Warns if power < 0.8. Writes to the current experiment step's outputs/reports directory.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "effect_size": {"type": "number"},
                "alpha": {"type": "number"},
                "n": {"type": "number"}
            },
            "required": ["filepath", "alpha", "n"],
        },
    },
    "sys.md.validate": {
        "description": "Validates a written MD file against a writing protocol template.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to MD file"},
                "protocol_name": {"type": "string", "description": "Writing protocol to check against (e.g., writing_methods)"}
            },
            "required": ["filepath", "protocol_name"],
        },
    },
    "tool.audit.md_consistency": {
        "description": "Scans written MD files and verifies they follow templates (alias for sys.md.validate).",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "protocol_name": {"type": "string"}
            },
            "required": ["filepath", "protocol_name"],
        },
    },
    "tool.audit.assumptions": {
        "description": "Re-run assumption checks on the fitted model or residuals. Writes to the current experiment step's outputs/reports directory.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool.audit.figure_quality": {
        "description": "Check figure quality (DPI, colorblind-friendly, labels, error bars). Writes to the current experiment step's outputs/reports directory.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool.audit.reproducibility_full": {
        "description": "Run a full reproducibility check using Docker. Writes to workspace/logs/reproducibility_report.md.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        },
    },
    "mem.analysis.log": {
        "description": "Append to workspace/analysis.md",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {"entry": {"type": "string"}},
            "required": ["entry"],
        },
    },
    "mem.methods.append": {
        "description": "Append a method entry to workspace/methods.md with structured format.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "Method name (required, all others optional)"},
                "step_number": {"type": "string", "description": "Step number e.g. 01"},
                "step_name": {"type": "string", "description": "Step name e.g. Baseline EDA"},
                "dataset_name": {"type": "string", "description": "Dataset used"},
                "dataset_hash": {"type": "string", "description": "SHA-256 of dataset"},
                "implementation": {"type": "string", "description": "Tool/package and version e.g. pandas v2.0"},
                "parameters": {"type": "string", "description": "Key parameters or settings"},
                "justification": {"type": "string", "description": "Why this method was chosen"},
                "assumptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Assumptions checked before using this method",
                },
            },
            "required": ["method"],
        },
    },
    "mem.citations.generate": {
        "description": "Generate workspace/citations.md from inputs/literature_index.yaml.",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "mem.intake.regenerate": {
        "description": "Regenerate inputs/intake.md with current file hashes.",
        "category": "memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "view.workspace.tree": {
        "description": "Returns a structured tree of workspace/. Alias for sys.workspace.tree.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "depth": {"type": "number", "description": "Tree depth (default 3)"},
                "include_files": {"type": "boolean", "description": "Include file names (default true)"},
            },
        },
    },
    "tool.search.semantic_scholar": {
        "description": "Search Semantic Scholar.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"],
        },
    },
    "tool.search.pubmed": {
        "description": "Search PubMed.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"],
        },
    },
    "tool.search.crossref": {
        "description": "Search Crossref.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"],
        },
    },
    "tool.search.web": {
        "description": "Search the web.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"],
        },
    },
    "tool.web.scrape": {
        "description": "Scrape a webpage.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "tool.literature.download": {
        "description": "Download a paper PDF.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "filename": {"type": "string"}},
            "required": ["url", "filename"],
        },
    },
    "tool.python.exec": {
        "description": "Execute a Python script. WARNING: runs with host permissions — use Docker for sandboxing.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"script_path": {"type": "string"}},
            "required": ["script_path"],
        },
    },
    "tool.r.exec": {
        "description": "Execute an R script in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number", "description": "Timeout in seconds (default 300)"}
            },
            "required": ["script_path"],
        },
    },
    "tool.julia.exec": {
        "description": "Execute a Julia script in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number", "description": "Timeout in seconds (default 300)"}
            },
            "required": ["script_path"],
        },
    },
    "tool.bash.exec": {
        "description": "Execute a Bash script in the workspace.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string"},
                "timeout": {"type": "number", "description": "Timeout in seconds (default 300)"}
            },
            "required": ["script_path"],
        },
    },
    "tool.package.install": {
        "description": "Install Python packages.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"packages": {"type": "array", "items": {"type": "string"}}},
            "required": ["packages"],
        },
    },
    "sys.env.snapshot": {
        "description": "Snapshot current multi-language environment (Python, R, Julia).",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool.env.freeze": {
        "description": "Freeze current environment (Deprecated, use sys.env.snapshot).",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool.env.restore": {
        "description": "Restore a frozen environment.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "string",
                    "description": "Requirements format text"
                }
            },
            "required": [],
        },
    },
    "sys.env.docker.generate": {
        "description": "Generates a Dockerfile to run all snapshotted environments.",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool.latex.compile": {
        "description": "Compile paper.tex in the synthesis directory to PDF using pdflatex and bibtex.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "tool.poster.create": {
        "description": "Generate a professional LaTeX poster in synthesis/poster.pdf using tikzposter.",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tool.data.sample": {
        "description": "Sample data.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string"},
                "n_rows": {"type": "number"},
                "strategy": {"type": "string"},
            },
            "required": ["filepath", "n_rows", "strategy"],
        },
    },
    "tool.data.convert": {
        "description": "Convert data between common formats (CSV, RDS, Feather, Parquet).",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Input file path"},
                "output_format": {"type": "string", "description": "Desired output format (e.g. csv, rds, feather, parquet)"}
            },
            "required": ["filepath", "output_format"],
        },
    },
    "tool.log.decision": {
        "description": "Log a key reasoning step.",
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
    "tool.synthesize": {
        "description": "Compile workspace findings into synthesis/paper.md. For complex papers, call section-by-section: section='methods', section='results', section='discussion', then call without section for final assembly.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "latex", "both"],
                    "description": "Output format for the compiled paper (default: markdown)",
                },
                "section": {
                    "type": "string",
                    "description": "Specific section to generate (e.g. abstract, methods, results, discussion). If omitted, generates the full paper.",
                },
            },
            "required": [],
        },
    },
    "tool.synthesize.plan": {
        "description": "Show synthesis plan: available source sections and recommended ordering. Always call this first before using tool.synthesize so the AI can decide the sequence of section generation.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "sys.protocol.log": {
        "description": "Log a protocol execution to the protocol execution log (.os_state/protocol_execution_log.jsonl).",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string", "description": "Name of the protocol"},
                "status": {"type": "string", "description": "Execution status: started | completed | failed | skipped"},
                "details": {"type": "string", "description": "Optional details about the execution"},
            },
            "required": ["protocol_name", "status"],
        },
    },
    "sys.protocol.history": {
        "description": "Read recent protocol execution history.",
        "category": "system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "number", "description": "Number of recent entries to return (default: 20)"},
            },
            "required": [],
        },
    },
}

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _log_search(root: Path, tool_name: str, query: str, count: int):
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


def _handle_sys_guidance_list(name: str, arguments: dict, root: Path) -> list[TextContent]:
        try:
            protocols = list_protocols()
            # Rename summary to description to keep backward compatibility with clients if needed
            summaries = [{"name": p["name"], "description": p["summary"]} for p in protocols]
            return _text(_success_envelope({"protocols": summaries}))
        except Exception as e:
            return _text(_error_envelope(str(e)))


def _handle_sys_guidance_get(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p_name = arguments.get("protocol_name")
        config_res = get_config(root)
        profile = "large"
        if config_res.get("status") == "success":
            profile = config_res.get("config", {}).get("model_profile", "large")

        try:
            import yaml
            light = (profile == "small")
            data = load_protocol(p_name, light=light)
            # Inject model adaptations if they exist for the current profile
            if "model_adaptations" in data and profile in data["model_adaptations"]:
                adaptations = data["model_adaptations"][profile]
                for step_id, overrides in adaptations.items():
                    for step in data.get("steps", []):
                        if step.get("id") == step_id:
                            step.update(overrides)
                del data["model_adaptations"]
            res = {"content": yaml.dump(data)}
            if profile == "small":
                res["note"] = "Loaded in step-by-step mode due to 'small' model profile."
            if p_name != "guidance/session_boot":
                res["_reminder"] = "Check your session_boot profile before executing these steps if you haven't already."
            return _text(_success_envelope(res))
        except Exception as e:
            return _text(_error_envelope(str(e)))


def _handle_sys_guidance_validate(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p_name = arguments.get("protocol_name")
        res = validate_protocol(p_name, root)
        if "error" in res:
            return _text(_error_envelope(res["error"]))
        return _text(_success_envelope(res))


def _handle_sys_protocol_next(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = get_next_protocol(root)
        return _text(_success_envelope(res))


def _handle_sys_protocol_log(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.protocol import log_protocol_execution
        res = log_protocol_execution(
            root,
            arguments["protocol_name"],
            arguments["status"],
            arguments.get("details", ""),
        )
        return _text(_success_envelope(res))


def _handle_sys_protocol_history(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.protocol import get_protocol_history
        res = get_protocol_history(root, arguments.get("limit", 20))
        return _text(_success_envelope(res))


def _handle_sys_tool_info(name: str, arguments: dict, root: Path) -> list[TextContent]:
        t_name = arguments.get("tool_name")
        if t_name in TOOL_DEFINITIONS:
            return _text(_success_envelope(TOOL_DEFINITIONS[t_name]))
        return _text(_error_envelope(f"Tool {t_name} not found."))


def _handle_sys_tool_search(name: str, arguments: dict, root: Path) -> list[TextContent]:
        q = arguments.get("query", "").lower()
        matches = []
        for t_name, t_schema in TOOL_DEFINITIONS.items():
            if q in t_name.lower() or q in t_schema.get("description", "").lower():
                matches.append(
                    {"name": t_name, "description": t_schema.get("description", "")}
                )
        return _text(_success_envelope({"tools": matches}))


def _handle_tool_r_exec(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.execution import execute_r_script
        res = execute_r_script(arguments["script_path"], root, timeout=arguments.get("timeout", 300))
        return _text(_success_envelope(res)) if "error" not in res else _text(_error_envelope(res["error"]))


def _handle_tool_julia_exec(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.execution import execute_julia_script
        res = execute_julia_script(arguments["script_path"], root, timeout=arguments.get("timeout", 300))
        return _text(_success_envelope(res)) if "error" not in res else _text(_error_envelope(res["error"]))


def _handle_tool_bash_exec(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.execution import execute_bash_script
        res = execute_bash_script(arguments["script_path"], root, timeout=arguments.get("timeout", 300))
        return _text(_success_envelope(res)) if "error" not in res else _text(_error_envelope(res["error"]))


def _handle_sys_workspace_scaffold(name: str, arguments: dict, root: Path) -> list[TextContent]:
        ide_str = arguments.get("ide", "all")
        valid_ides = ["cursor", "claude", "opencode", "vscode", "antigravity"]
        ide_flags = valid_ides if ide_str == "all" else [i.strip() for i in ide_str.split(",") if i.strip() in valid_ides]
        scaffold_minimal_workspace(
            root,
            arguments.get("project_name", "Research Project"),
            git_init=arguments.get("git_init", False),
            ide_flags=ide_flags,
            copy_agents=True,
        )
        if (root / ".os_state").exists() and (root / "workspace").exists():
            _profile_inputs(root)
        return _text(_success_envelope({"scaffolded": True, "ide_flags": ide_flags}))


def _handle_sys_file_read(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p = root / arguments["filepath"]
        if not p.exists() or not p.is_file():
            return _text(_error_envelope("File not found"))
        # Add a size limit of 50MB
        if p.stat().st_size > 50 * 1024 * 1024:
            return _text(
                _error_envelope("File too large (>50MB). Use tool.data.sample instead.")
            )
        return _text(_success_envelope({"content": p.read_text()}))


def _handle_sys_file_write(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p = root / arguments["filepath"]
        force = arguments.get("force", False)
        # Immutability enforcement
        if "inputs/raw_data" in str(p) or "inputs/literature" in str(p):
            if "inputs/literature_index.yaml" not in str(p):
                return _text(
                    _error_envelope("WriteProtectedError: Cannot modify raw inputs.")
                )
        if "synthesis/" in str(p) and p.exists() and not force:
            return _text(
                _error_envelope(
                    "WriteProtectedError: Cannot overwrite files in synthesis/ without force=true."
                )
            )

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(arguments["content"])
        # Sync manifest when writing to workspace/
        if "workspace/" in arguments["filepath"]:
            _update_manifest(root)
        return _text(
            _success_envelope({"written": True, "checksum": compute_file_hash(p)})
        )


def _handle_sys_file_list(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p = root / arguments["directory"]
        if not p.exists() or not p.is_dir():
            return _text(_error_envelope("Directory not found"))
        files = [str(f.relative_to(root)) for f in p.rglob("*") if f.is_file()]
        return _text(_success_envelope({"files": files}))


def _handle_sys_file_delete(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p = root / arguments["filepath"]
        if p.exists() and p.is_file():
            p.unlink()
            return _text(_success_envelope({"deleted": True}))
        return _text(_error_envelope("File not found"))


def _handle_sys_workspace_tree(name: str, arguments: dict, root: Path) -> list[TextContent]:
        depth = arguments.get("depth", 3)
        include_files = arguments.get("include_files", True)
        tree = _build_tree(root / "workspace", depth, include_files)
        return _text(_success_envelope({"tree": tree}))


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
    except PermissionError:
        pass
    return result


def _handle_sys_state_get(name: str, arguments: dict, root: Path) -> list[TextContent]:
        return _text(_success_envelope(load_state(root)))


def _handle_sys_state_summary(name: str, arguments: dict, root: Path) -> list[TextContent]:
        state = load_state(root)
        paths = list(state.get("paths", {}).keys())
        return _text(
            _success_envelope(
                {
                    "current_path": state.get("current_path"),
                    "paths": paths,
                }
            )
        )


def _handle_sys_state_summary_md(name: str, arguments: dict, root: Path) -> list[TextContent]:
        summary_path = root / ".os_state" / "os_state.md"
        if not summary_path.exists():
            return _text(_error_envelope("os_state.md not found. Run save_state first to generate it."))
        return _text(_success_envelope({"content": summary_path.read_text()}))


def _handle_sys_state_minimal_context(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.state.state_ledger import ResearchLedger

        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
        summary = ledger.get_project_summary(max_tokens=450)
        return _text(_success_envelope({"minimal_context": summary}))


def _handle_sys_state_health(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.state.state_ledger import ResearchLedger
        import json
        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
        result = ledger.health(root=root)
        result["workspace_tree"] = _build_tree(root / "workspace", 2, True)
        # Check manifest/state ledger sync
        manifest_file = root / ".os_state" / "manifest.json"
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text())
                manifest_paths = set(manifest.get("paths", {}).keys())
                state = load_state(root)
                state_paths = set(state.get("paths", {}).keys())
                if manifest_paths != state_paths:
                    result["manifest_valid"] = False
                    result["manifest_warning"] = f"Manifest has {len(manifest_paths)} paths, state has {len(state_paths)} paths"
                else:
                    result["manifest_valid"] = True
            except Exception:
                result["manifest_valid"] = False
        return _text(_success_envelope(result))


def _handle_sys_session_handoff(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = session_handoff(root)
        if res["status"] == "success":
            return _text(res["content"])
        return _text(_error_envelope(res["message"]))


def _handle_tool_task_create(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.task import create_task

        res = create_task(arguments.get("task_description", ""), root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_tool_synthesize_plan(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.synthesize import synthesize_plan
        res = synthesize_plan(root)
        return _text(_success_envelope(res))


def _handle_tool_audit_synthesis(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.audit import audit_synthesis

        res = audit_synthesis(arguments["paper_path"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] != "error"
            else _text(_error_envelope(res["message"]))
        )


def _handle_tool_audit_statistical_power(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.audit import audit_power

        effect_size = arguments.get("effect_size", 0.5)
        res = audit_power(arguments["filepath"], effect_size, arguments["alpha"], arguments["n"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))


def _handle_tool_audit_assumptions(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.audit import audit_assumptions

        res = audit_assumptions(arguments["filepath"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))


def _handle_tool_audit_figure_quality(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.audit import audit_figure

        res = audit_figure(arguments["filepath"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))


def _handle_tool_audit_reproducibility_full(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.audit import audit_reproducibility_full

        res = audit_reproducibility_full(root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))


def _handle_sys_checkpoint_create(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = create_checkpoint(arguments.get("description", "manual"), root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_checkpoint_rollback(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = rollback_checkpoint(arguments["checkpoint_id"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_checkpoint_list(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = list_checkpoints(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_checkpoint_pending(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = checkpoint_pending(
            arguments["description"], arguments["requires_approval"], root
        )
        return (
            _text(_success_envelope(res))
            if res["status"] != "error"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_checkpoint_approve(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = checkpoint_approve(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_path_create(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = create_path(arguments["name"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_path_abandon(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = abandon_path(arguments["path_name"], arguments["rationale"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_path_list(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = list_paths(root)
        return _text(_success_envelope(res))


def _handle_sys_config_init(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = init_config(root)
        return _text(_success_envelope(res))


def _handle_sys_config_get(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = get_config(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_config_set(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = set_config(arguments["key"], arguments["value"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_config_validate(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = validate_config(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_config_profile(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = get_config(root)
        if res["status"] == "success":
            config = res.get("config", {})
            profile = {
                "autonomy_level": config.get("interaction", {}).get("autonomy_level", "supervised"),
                "expertise_level": config.get("researcher", {}).get("expertise_level", "intermediate"),
                "model_profile": config.get("model_profile", "medium"),
            }
            return _text(_success_envelope(profile))
        return _text(_success_envelope({"autonomy_level": "supervised", "expertise_level": "intermediate", "model_profile": "medium"}))


def _handle_sys_config_explain(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.config import explain_config as _explain
        res = _explain(root, arguments.get("key", ""))
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))


def _handle_sys_notify(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = notify_researcher(arguments["message"], arguments["level"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_external_mcp_discover(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = discover_mcp(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_sys_task_monitor(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = task_monitor(arguments["task_id"], root)
        return _text(_success_envelope(res))


def _handle_sys_task_kill(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = task_kill(arguments["task_id"], root)
        return _text(_success_envelope(res))


def _handle_mem_analysis_log(name: str, arguments: dict, root: Path) -> list[TextContent]:
        log_path = root / "workspace" / "analysis.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{now_iso()}] {arguments['entry']}\n")
        _update_workflow_mermaid(root)
        return _text(_success_envelope({"logged": True}))


def _handle_mem_citations_generate(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.project_ops import generate_citations_md
        path = generate_citations_md(root)
        return _text(_success_envelope({"citations_path": path}))


def _handle_mem_intake_regenerate(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.project_ops import regenerate_intake
        path = regenerate_intake(root)
        return _text(_success_envelope({"intake_path": path}))


def _handle_view_workspace_tree(name: str, arguments: dict, root: Path) -> list[TextContent]:
        return _handle_sys_workspace_tree(name, arguments, root)


def _handle_mem_methods_append(name: str, arguments: dict, root: Path) -> list[TextContent]:
        m_path = root / "workspace" / "methods.md"
        m_path.parent.mkdir(parents=True, exist_ok=True)
        ts = now_iso()
        method = arguments["method"]
        # If only method is provided (bare string), write old format with deprecation note
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
                    lines.append(f"  - **Assumption**: {a}")
            line = "\n".join(lines) + "\n"
        with open(m_path, "a") as f:
            f.write(line)
        return _text(_success_envelope({"logged": True}))


def _handle_tool_search_semantic_scholar(name: str, arguments: dict, root: Path) -> list[TextContent]:
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_semantic_scholar(q, limit)
        return _text(_success_envelope(res))


def _handle_tool_search_pubmed(name: str, arguments: dict, root: Path) -> list[TextContent]:
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_pubmed(q, limit)
        return _text(_success_envelope(res))


def _handle_tool_search_crossref(name: str, arguments: dict, root: Path) -> list[TextContent]:
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_crossref(q, limit)
        return _text(_success_envelope(res))


def _handle_tool_search_web(name: str, arguments: dict, root: Path) -> list[TextContent]:
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_web(q, limit)
        if "warning" in res:
            return _text(_success_envelope(res))
        return _text(_success_envelope(res))


def _handle_tool_web_scrape(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = scrape_web(arguments["url"])
        return _text(_success_envelope(res))


def _handle_tool_literature_download(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = download_literature(arguments["url"], arguments["filename"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )


def _handle_tool_python_exec(name: str, arguments: dict, root: Path) -> list[TextContent]:
        p = root / arguments["script_path"]
        if not p.exists() or not p.is_file():
            return _text(_error_envelope("Script not found"))

        # Determine step for logging
        step_name = p.stem
        log_dir = root / "workspace" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        exec_log_path = log_dir / f"{step_name}_exec.log"

        cmd = [sys.executable, str(p)]
        res = subprocess.run(cmd, cwd=str(p.parent), capture_output=True, text=True)

        with open(exec_log_path, "a") as f:
            f.write(
                f"--- Executed at {now_iso()} ---\nCommand: {' '.join(cmd)}\nReturn Code: {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\n\n"
            )

        return _text(
            _success_envelope(
                {"stdout": res.stdout, "stderr": res.stderr, "code": res.returncode}
            )
        )


def _handle_tool_r_exec_group(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.execution import execute_r_script, execute_julia_script, execute_bash_script

        timeout = arguments.get("timeout", 300)
        script_path = arguments["script_path"]

        if name == "tool.r.exec":
            res = execute_r_script(script_path, root, timeout)
        elif name == "tool.julia.exec":
            res = execute_julia_script(script_path, root, timeout)
        else:
            res = execute_bash_script(script_path, root, timeout)

        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))


def _handle_tool_package_install(name: str, arguments: dict, root: Path) -> list[TextContent]:
        packages = arguments["packages"]
        # Verify in a sub-process
        res = package_install(packages)
        if res.get("status") == "success":
            req_path = root / "environment" / "requirements.txt"
            req_path.parent.mkdir(parents=True, exist_ok=True)
            with open(req_path, "a") as f:
                for pkg in packages:
                    f.write(f"{pkg}\n")
        return _text(_success_envelope(res))


def _handle_tool_env_freeze_group(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.environment import env_snapshot
        res = env_snapshot(root)
        return _text(_success_envelope(res)) if res.get("status") == "success" else _text(_error_envelope(res.get("message", "Error")))


def _handle_tool_env_restore(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.environment import env_restore
        res = env_restore(arguments.get("requirements", ""), root)
        return _text(_success_envelope(res)) if res.get("status") != "error" and res.get("code", 0) == 0 else _text(_error_envelope(res.get("error", "Error")))


def _handle_sys_env_docker_generate(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.environment import env_docker_generate
        res = env_docker_generate(root)
        return _text(_success_envelope(res)) if res.get("status") == "success" else _text(_error_envelope(res.get("message", "Error")))


def _handle_tool_latex_compile(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.latex import latex_compile
        return _text(_success_envelope(latex_compile(root)))


def _handle_tool_poster_create(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.latex import create_poster
        return _text(_success_envelope(create_poster(root)))


def _handle_tool_data_sample(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.data import data_sample
        res = data_sample(
            arguments["filepath"], arguments["n_rows"], arguments["strategy"], root
        )
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(
                _error_envelope(res.get("message", res.get("error", "Unknown error")))
            )
        )


def _handle_tool_data_convert(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.data import data_convert
        res = data_convert(
            arguments["filepath"], arguments["output_format"], root
        )
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(
                _error_envelope(res.get("message", res.get("error", "Unknown error")))
            )
        )


def _handle_tool_log_decision(name: str, arguments: dict, root: Path) -> list[TextContent]:
        res = log_decision(
            arguments["context"],
            arguments["selected"],
            arguments["rationale"],
            root=root,
        )
        return _text(_success_envelope(res))


def _handle_tool_synthesize(name: str, arguments: dict, root: Path) -> list[TextContent]:
        from research_os.tools.actions.synthesize import synthesize_workspace

        fmt = arguments.get("output_format", "markdown")
        sec = arguments.get("section")
        res = synthesize_workspace(root, output_format=fmt, section=sec)
        if "error" in res:
            return _text(_error_envelope(res["error"]))
        return _text(_success_envelope(res))



def _handle_sys_md_validate(name: str, arguments: dict, root: Path) -> list[TextContent]:
    from research_os.tools.actions.md_audit import validate_md_template
    res = validate_md_template(arguments["filepath"], arguments["protocol_name"], root)
    if res["status"] == "success":
        return _text(_success_envelope(res))
    return _text(_error_envelope(res.get("message", "Validation failed") + str(res.get("errors", ""))))

_HANDLERS = {
    "sys.md.validate": _handle_sys_md_validate,
    "tool.audit.md_consistency": _handle_sys_md_validate,
    "sys.guidance.list": _handle_sys_guidance_list,
    "sys.guidance.get": _handle_sys_guidance_get,
    "sys.guidance.validate": _handle_sys_guidance_validate,
    "sys.tool.info": _handle_sys_tool_info,
    "sys.tool.search": _handle_sys_tool_search,
    "tool.r.exec": _handle_tool_r_exec_group,
    "tool.julia.exec": _handle_tool_r_exec_group,
    "tool.bash.exec": _handle_tool_r_exec_group,
    "sys.protocol.next": _handle_sys_protocol_next,
    "sys.protocol.log": _handle_sys_protocol_log,
    "sys.protocol.history": _handle_sys_protocol_history,
    "sys.workspace.scaffold": _handle_sys_workspace_scaffold,
    "sys.workspace.tree": _handle_sys_workspace_tree,
    "sys.file.read": _handle_sys_file_read,
    "sys.file.write": _handle_sys_file_write,
    "sys.file.list": _handle_sys_file_list,
    "sys.file.delete": _handle_sys_file_delete,
    "sys.state.get": _handle_sys_state_get,
    "sys.state.summary": _handle_sys_state_summary,
    "sys.state.summary_md": _handle_sys_state_summary_md,
    "sys.state.minimal_context": _handle_sys_state_minimal_context,
    "sys.state.health": _handle_sys_state_health,
    "sys.session.handoff": _handle_sys_session_handoff,
    "tool.task.create": _handle_tool_task_create,
    "tool.synthesize": _handle_tool_synthesize,
    "tool.synthesize.plan": _handle_tool_synthesize_plan,
    "tool.audit.synthesis": _handle_tool_audit_synthesis,
    "tool.audit.statistical_power": _handle_tool_audit_statistical_power,
    "tool.audit.assumptions": _handle_tool_audit_assumptions,
    "tool.audit.figure_quality": _handle_tool_audit_figure_quality,
    "tool.audit.reproducibility_full": _handle_tool_audit_reproducibility_full,
    "sys.checkpoint.create": _handle_sys_checkpoint_create,
    "sys.checkpoint.rollback": _handle_sys_checkpoint_rollback,
    "sys.checkpoint.list": _handle_sys_checkpoint_list,
    "sys.checkpoint.pending": _handle_sys_checkpoint_pending,
    "sys.checkpoint.approve": _handle_sys_checkpoint_approve,
    "sys.path.create": _handle_sys_path_create,
    "sys.path.abandon": _handle_sys_path_abandon,
    "sys.path.list": _handle_sys_path_list,
    "sys.config.init": _handle_sys_config_init,
    "sys.config.get": _handle_sys_config_get,
    "sys.config.set": _handle_sys_config_set,
    "sys.config.validate": _handle_sys_config_validate,
    "sys.config.profile": _handle_sys_config_profile,
    "sys.config.explain": _handle_sys_config_explain,
    "sys.notify": _handle_sys_notify,
    "sys.external_mcp.discover": _handle_sys_external_mcp_discover,
    "sys.task.monitor": _handle_sys_task_monitor,
    "sys.task.kill": _handle_sys_task_kill,
    "mem.analysis.log": _handle_mem_analysis_log,
    "mem.methods.append": _handle_mem_methods_append,
    "mem.citations.generate": _handle_mem_citations_generate,
    "mem.intake.regenerate": _handle_mem_intake_regenerate,
    "view.workspace.tree": _handle_view_workspace_tree,
    "tool.search.semantic_scholar": _handle_tool_search_semantic_scholar,
    "tool.search.pubmed": _handle_tool_search_pubmed,
    "tool.search.crossref": _handle_tool_search_crossref,
    "tool.search.web": _handle_tool_search_web,
    "tool.web.scrape": _handle_tool_web_scrape,
    "tool.literature.download": _handle_tool_literature_download,
    "tool.python.exec": _handle_tool_python_exec,
    "tool.package.install": _handle_tool_package_install,
    "tool.env.freeze": _handle_tool_env_freeze_group,
    "sys.env.snapshot": _handle_tool_env_freeze_group,
    "tool.env.restore": _handle_tool_env_restore,
    "sys.env.docker.generate": _handle_sys_env_docker_generate,
    "tool.latex.compile": _handle_tool_latex_compile,
    "tool.poster.create": _handle_tool_poster_create,
    "tool.data.sample": _handle_tool_data_sample,
    "tool.data.convert": _handle_tool_data_convert,
    "tool.log.decision": _handle_tool_log_decision,
}

def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error_envelope("Rate limit exceeded."))
    logger.info(f"Tool call: {name}")
    handler = _HANDLERS.get(name)
    if handler is None:
        if name.startswith("sys.") or name.startswith("tool.") or name.startswith("mem."):
            return _text(_error_envelope(f"Tool '{name}' is not yet implemented. Use sys.tool.search to find an alternative."))
        return _text(_error_envelope(f"Unknown tool: {name}"))
    try:
        return handler(name, arguments, root)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return _text(_error_envelope(str(e)))

if HAS_MCP:
    server = Server("research-os")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        import os

        root = Path(os.getcwd())
        config_res = get_config(root)
        profile = "large"
        if config_res.get("status") == "success":
            profile = config_res.get("config", {}).get("model_profile", "large")

        tools = []
        for name, schema in TOOL_DEFINITIONS.items():
            desc = schema["description"]
            if profile == "small":
                desc = desc.split(".")[0] + "."  # Bare essentials
            tools.append(
                Tool(name=name, description=desc, inputSchema=schema["inputSchema"])
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        import os

        root = Path(os.getcwd())
        return _handle_tool_call(name, arguments, root)

    async def run_stdio() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio")
    parser.add_argument("--workspace", type=str)
    args = parser.parse_args()

    if args.workspace:
        os.chdir(args.workspace)

    # Inject API keys from researcher_config.yaml into environment
    try:
        root = Path(os.getcwd())
        import yaml
        config_file = root / "researcher_config.yaml"
        if config_file.exists():
            with open(config_file) as f:
                cfg = yaml.safe_load(f)
            api_keys = cfg.get("api_keys", {}) if cfg else {}
            for key, value in api_keys.items():
                if value:
                    os.environ[key.upper()] = value
    except Exception:
        pass  # Non-fatal — keys simply won't be injected

    if HAS_MCP:
        import asyncio

        asyncio.run(run_stdio())
    else:
        sys.exit("MCP package missing.")


if __name__ == "__main__":
    main()