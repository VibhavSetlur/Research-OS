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
    compute_file_hash,
    load_state,
    now_iso,
    scaffold_minimal_workspace,
    log_decision,
)

from research_os.tools.actions.web_search import search_web, scrape_web
from research_os.tools.actions.environment import (
    package_install,
    env_freeze,
    env_restore,
)
from research_os.tools.actions.latex import latex_compile
from research_os.tools.actions.checkpoint import (
    create_checkpoint,
    rollback_checkpoint,
    list_checkpoints,
)
from research_os.tools.actions.path import create_path, abandon_path, list_paths
from research_os.tools.actions.literature import download_literature
from research_os.tools.actions.config import (
    get_config,
    set_config,
    init_config,
    validate_config,
)
from research_os.tools.actions.interaction import (
    notify_researcher,
    checkpoint_pending,
    checkpoint_approve,
    session_handoff,
)
from research_os.tools.actions.external_mcp import discover_mcp
from research_os.tools.actions.task import task_monitor, task_kill
from research_os.tools.actions.data import data_sample
from research_os.tools.actions.search import (
    search_semantic_scholar,
    search_pubmed,
    search_crossref,
)
from research_os.tools.actions.protocol import (
    get_protocol,
    list_protocols,
    validate_protocol,
)
from research_os.tools.actions.profiling import _profile_inputs

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
    "sys.workspace.scaffold": {
        "description": "Create the full directory structure for a new project.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"project_name": {"type": "string"}},
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
        "description": "Create a numbered experiment path in workspace/.",
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
        "description": "Compute post-hoc power for statistical tests. Warns if power < 0.8. Writes to workspace/<current_path>/outputs/reports/power_report.md.",
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
    "tool.audit.assumptions": {
        "description": "Re-run assumption checks on the fitted model or residuals. Writes to workspace/<current_path>/outputs/reports/assumption_report.md.",
        "category": "audit",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"],
        },
    },
    "tool.audit.figure_quality": {
        "description": "Check figure quality (DPI, colorblind-friendly, labels, error bars). Writes to workspace/<current_path>/outputs/reports/figure_audit.md.",
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
        "description": "Append to workspace/methods.md",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {"method": {"type": "string"}},
            "required": ["method"],
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
        "description": "Execute a python script in the workspace. WARNING: Scripts run with the same permissions as the host OS user. For strict sandboxing, run Research OS inside a Docker container.",
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
        "description": "Gather all workspace findings and compile a publication-ready paper in synthesis/. Combines analysis.md, methods.md, citations, figures, and audit report into synthesis/paper.md.",
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


def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error_envelope("Rate limit exceeded."))

    logger.info(f"Tool call: {name}")

    if name == "sys.guidance.list":
        res = list_protocols(root)
        if "error" in res:
            return _text(_error_envelope(res["error"]))
        # Lazy loading tier 1
        summaries = [
            {"name": p["name"], "description": p["description"]}
            for p in res["protocols"]
        ]
        return _text(_success_envelope({"protocols": summaries}))

    if name == "sys.guidance.get":
        p_name = arguments.get("protocol_name")
        # Check model profile
        config_res = get_config(root)
        profile = "large"
        if config_res.get("status") == "success":
            profile = config_res.get("config", {}).get("model_profile", "large")

        res = get_protocol(p_name, root)
        if "error" in res:
            return _text(_error_envelope(res["error"]))

        if profile == "small":
            # Step-by-step mode: simplify protocol and just return next steps or stripped version
            import yaml

            try:
                data = yaml.safe_load(res["content"])
                stripped = {
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "steps": data.get("steps", []),
                }
                res["content"] = yaml.dump(stripped)
                res["note"] = (
                    "Loaded in step-by-step mode due to 'small' model profile."
                )
            except Exception:
                pass

        return _text(_success_envelope(res))

    if name == "sys.guidance.validate":
        p_name = arguments.get("protocol_name")
        res = validate_protocol(p_name, root)
        if "error" in res:
            return _text(_error_envelope(res["error"]))
        return _text(_success_envelope(res))

    if name == "sys.tool.info":
        t_name = arguments.get("tool_name")
        if t_name in TOOL_DEFINITIONS:
            return _text(_success_envelope(TOOL_DEFINITIONS[t_name]))
        return _text(_error_envelope(f"Tool {t_name} not found."))

    if name == "sys.tool.search":
        q = arguments.get("query", "").lower()
        matches = []
        for t_name, t_schema in TOOL_DEFINITIONS.items():
            if q in t_name.lower() or q in t_schema.get("description", "").lower():
                matches.append(
                    {"name": t_name, "description": t_schema.get("description", "")}
                )
        return _text(_success_envelope({"tools": matches}))

    if name == "sys.workspace.scaffold":
        scaffold_minimal_workspace(
            root, arguments.get("project_name", "Research Project")
        )
        _profile_inputs(root)
        return _text(_success_envelope({"scaffolded": True}))

    if name == "sys.file.read":
        p = root / arguments["filepath"]
        if not p.exists() or not p.is_file():
            return _text(_error_envelope("File not found"))
        # Add a size limit of 50MB
        if p.stat().st_size > 50 * 1024 * 1024:
            return _text(
                _error_envelope("File too large (>50MB). Use tool.data.sample instead.")
            )
        return _text(_success_envelope({"content": p.read_text()}))

    if name == "sys.file.write":
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
        return _text(
            _success_envelope({"written": True, "checksum": compute_file_hash(p)})
        )

    if name == "sys.file.list":
        p = root / arguments["directory"]
        if not p.exists() or not p.is_dir():
            return _text(_error_envelope("Directory not found"))
        files = [str(f.relative_to(root)) for f in p.rglob("*") if f.is_file()]
        return _text(_success_envelope({"files": files}))

    if name == "sys.file.delete":
        p = root / arguments["filepath"]
        if p.exists() and p.is_file():
            p.unlink()
            return _text(_success_envelope({"deleted": True}))
        return _text(_error_envelope("File not found"))

    if name == "sys.state.get":
        return _text(_success_envelope(load_state(root)))

    if name == "sys.state.summary":
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

    if name == "sys.state.minimal_context":
        from research_os.state.state_ledger import ResearchLedger

        ledger = ResearchLedger(root)
        summary = ledger.get_project_summary(max_tokens=450)
        return _text(_success_envelope({"minimal_context": summary}))

    if name == "sys.state.health":
        from research_os.state.state_ledger import ResearchLedger
        ledger = ResearchLedger(root)
        return _text(_success_envelope(ledger.health()))

    if name == "sys.session.handoff":
        res = session_handoff(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "tool.task.create":
        from research_os.tools.actions.task import create_task

        res = create_task(arguments.get("task_description", ""), root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "tool.audit.synthesis":
        from research_os.tools.actions.audit import audit_synthesis

        res = audit_synthesis(arguments["paper_path"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] != "error"
            else _text(_error_envelope(res["message"]))
        )

    if name == "tool.audit.statistical_power":
        from research_os.tools.actions.audit import audit_power
        
        effect_size = arguments.get("effect_size", 0.5)
        res = audit_power(arguments["filepath"], effect_size, arguments["alpha"], arguments["n"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))

    if name == "tool.audit.assumptions":
        from research_os.tools.actions.audit import audit_assumptions
        
        res = audit_assumptions(arguments["filepath"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))

    if name == "tool.audit.figure_quality":
        from research_os.tools.actions.audit import audit_figure
        
        res = audit_figure(arguments["filepath"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))

    if name == "tool.audit.reproducibility_full":
        from research_os.tools.actions.audit import audit_reproducibility_full
        
        res = audit_reproducibility_full(root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))

    if name == "sys.checkpoint.create":
        res = create_checkpoint(arguments.get("description", ""), root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.checkpoint.rollback":
        res = rollback_checkpoint(arguments["checkpoint_id"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.checkpoint.list":
        res = list_checkpoints(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.checkpoint.pending":
        res = checkpoint_pending(
            arguments["description"], arguments["requires_approval"], root
        )
        return (
            _text(_success_envelope(res))
            if res["status"] != "error"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.checkpoint.approve":
        res = checkpoint_approve(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.path.create":
        res = create_path(arguments["name"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.path.abandon":
        res = abandon_path(arguments["path_name"], arguments["rationale"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.path.list":
        res = list_paths(root)
        return _text(_success_envelope(res))

    if name == "sys.config.init":
        res = init_config(root)
        return _text(_success_envelope(res))

    if name == "sys.config.get":
        res = get_config(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.config.set":
        res = set_config(arguments["key"], arguments["value"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.config.validate":
        res = validate_config(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.notify":
        res = notify_researcher(arguments["message"], arguments["level"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.external_mcp.discover":
        res = discover_mcp(root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "sys.task.monitor":
        res = task_monitor(arguments["task_id"], root)
        return _text(_success_envelope(res))

    if name == "sys.task.kill":
        res = task_kill(arguments["task_id"], root)
        return _text(_success_envelope(res))

    if name == "mem.analysis.log":
        log_path = root / "workspace" / "analysis.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{now_iso()}] {arguments['entry']}\n")
        return _text(_success_envelope({"logged": True}))

    if name == "mem.methods.append":
        m_path = root / "workspace" / "methods.md"
        m_path.parent.mkdir(parents=True, exist_ok=True)
        with open(m_path, "a") as f:
            f.write(f"- {arguments['method']}\n")
        return _text(_success_envelope({"logged": True}))

    if name == "tool.search.semantic_scholar":
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_semantic_scholar(q, limit)
        return _text(_success_envelope(res))

    if name == "tool.search.pubmed":
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_pubmed(q, limit)
        return _text(_success_envelope(res))

    if name == "tool.search.crossref":
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_crossref(q, limit)
        return _text(_success_envelope(res))

    if name == "tool.search.web":
        q = arguments["query"]
        limit = arguments.get("limit", 5)
        _log_search(root, name, q, 0)
        res = search_web(q, limit)
        if "warning" in res:
            return _text(_success_envelope(res))
        return _text(_success_envelope(res))

    if name == "tool.web.scrape":
        res = scrape_web(arguments["url"])
        return _text(_success_envelope(res))

    if name == "tool.literature.download":
        res = download_literature(arguments["url"], arguments["filename"], root)
        return (
            _text(_success_envelope(res))
            if res["status"] == "success"
            else _text(_error_envelope(res["message"]))
        )

    if name == "tool.python.exec":
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

    if name in ("tool.r.exec", "tool.julia.exec", "tool.bash.exec"):
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

    if name == "tool.package.install":
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

    if name in ("tool.env.freeze", "sys.env.snapshot"):
        from research_os.tools.actions.environment import env_snapshot
        res = env_snapshot(root)
        return _text(_success_envelope(res)) if res.get("status") == "success" else _text(_error_envelope(res.get("message", "Error")))

    if name == "tool.env.restore":
        from research_os.tools.actions.environment import env_restore
        res = env_restore(arguments.get("requirements", ""), root)
        return _text(_success_envelope(res)) if res.get("status") != "error" and res.get("code", 0) == 0 else _text(_error_envelope(res.get("error", "Error")))

    if name == "sys.env.docker.generate":
        from research_os.tools.actions.environment import env_docker_generate
        res = env_docker_generate(root)
        return _text(_success_envelope(res)) if res.get("status") == "success" else _text(_error_envelope(res.get("message", "Error")))

    if name == "tool.latex.compile":
        from research_os.tools.actions.latex import latex_compile
        return _text(_success_envelope(latex_compile(root)))

    if name == "tool.poster.create":
        from research_os.tools.actions.latex import create_poster
        return _text(_success_envelope(create_poster(root)))

    if name == "tool.data.sample":
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

    if name == "tool.data.convert":
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

    if name == "tool.log.decision":
        res = log_decision(
            arguments["context"],
            arguments["selected"],
            arguments["rationale"],
            root=root,
        )
        return _text(_success_envelope(res))

    if name == "tool.synthesize":
        from research_os.tools.actions.synthesize import synthesize_workspace

        fmt = arguments.get("output_format", "markdown")
        sec = arguments.get("section")
        res = synthesize_workspace(root, output_format=fmt, section=sec)
        if "error" in res:
            return _text(_error_envelope(res["error"]))
        return _text(_success_envelope(res))

    # Catch-all for unimplemeted tools
    if name.startswith("sys.") or name.startswith("tool.") or name.startswith("mem."):
        return _text(
            _success_envelope({"message": f"{name} is a stub implementation."})
        )

    return _text(_error_envelope(f"Unknown tool: {name}"))


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

    if HAS_MCP:
        import asyncio

        asyncio.run(run_stdio())
    else:
        sys.exit("MCP package missing.")


if __name__ == "__main__":
    main()
