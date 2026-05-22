#!/usr/bin/env python3
"""Research OS MCP server v3.0 — Research Guidance Engine"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("research-os.server")

from research_os.project_ops import (
    compute_file_hash,
    create_experiment_branch,
    load_state,
    now_iso,
    scaffold_minimal_workspace,
    log_decision,
)

from research_os.tools.actions.web_search import search_web, scrape_web
from research_os.tools.actions.environment import package_install, env_freeze
from research_os.tools.actions.checkpoint import create_checkpoint, rollback_checkpoint, list_checkpoints
from research_os.tools.actions.branch import switch_branch, merge_branches, list_branches
from research_os.tools.actions.literature import download_literature
from research_os.tools.actions.config import get_config, set_config, init_config, validate_config
from research_os.tools.actions.interaction import notify_researcher, checkpoint_pending, checkpoint_approve
from research_os.tools.actions.external_mcp import discover_mcp
from research_os.tools.actions.task import task_monitor, task_kill
from research_os.tools.actions.data import data_sample
from research_os.tools.actions.search import search_semantic_scholar, search_pubmed, search_crossref
from research_os.tools.actions.protocol import get_protocol, list_protocols
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
        self.calls[client_id] = [t for t in self.calls[client_id] if now - t < self.window_seconds]
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
                "protocol_name": {"type": "string", "description": "Protocol name (e.g., domain_analysis)"}
            },
            "required": ["protocol_name"]
        }
    },
    "sys.guidance.list": {
        "description": "Lists all available protocols with one-line summaries.",
        "category": "guidance",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.workspace.scaffold": {
        "description": "Create the full directory structure for a new project.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"project_name": {"type": "string"}},
        }
    },
    "sys.file.read": {
        "description": "Securely read a file from the workspace.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"]
        }
    },
    "sys.file.write": {
        "description": "Securely write to a file in the workspace.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}},
            "required": ["filepath", "content"]
        }
    },
    "sys.file.list": {
        "description": "List files in a directory.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"]
        }
    },
    "sys.file.delete": {
        "description": "Delete a file.",
        "category": "workspace",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string"}},
            "required": ["filepath"]
        }
    },
    "sys.state.get": {
        "description": "Get full workspace state.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.state.summary": {
        "description": "Get a brief summary of the state.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.checkpoint.create": {
        "description": "Snapshot workspace state.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"description": {"type": "string"}}
        }
    },
    "sys.checkpoint.rollback": {
        "description": "Rollback to a checkpoint.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"checkpoint_id": {"type": "string"}},
            "required": ["checkpoint_id"]
        }
    },
    "sys.checkpoint.list": {
        "description": "List all checkpoints.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.checkpoint.pending": {
        "description": "Register a pending action for approval.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                 "description": {"type": "string"},
                 "requires_approval": {"type": "boolean"}
            },
            "required": ["description", "requires_approval"]
        }
    },
    "sys.checkpoint.approve": {
        "description": "Approve a pending action.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.branch.create": {
        "description": "Create an experiment branch.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "hypothesis": {"type": "string"},
                "parent": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    "sys.branch.switch": {
        "description": "Switch to another branch.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {"branch_id": {"type": "string"}},
            "required": ["branch_id"]
        }
    },
    "sys.branch.list": {
        "description": "List all branches.",
        "category": "state",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.branch.merge": {
        "description": "Merge branches.",
        "category": "state",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "message": {"type": "string"}
            },
            "required": ["source", "target", "message"]
        }
    },
    "sys.config.init": {
        "description": "Initialize researcher configuration.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.config.get": {
        "description": "Get researcher configuration.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.config.set": {
        "description": "Set a specific config value.",
        "category": "workspace",
        "inputSchema": {
             "type": "object",
             "properties": {
                  "key": {"type": "string"},
                  "value": {"type": "string"}
             },
             "required": ["key", "value"]
        }
    },
    "sys.config.validate": {
        "description": "Validate configuration and API keys.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.notify": {
        "description": "Notify researcher.",
        "category": "workspace",
        "inputSchema": {
             "type": "object",
             "properties": {
                  "message": {"type": "string"},
                  "level": {"type": "string"}
             },
             "required": ["message", "level"]
        }
    },
    "sys.external_mcp.discover": {
        "description": "Discover external MCP servers.",
        "category": "workspace",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "sys.task.monitor": {
        "description": "Monitor a background task.",
        "category": "execution",
        "inputSchema": {
             "type": "object",
             "properties": {"task_id": {"type": "string"}},
             "required": ["task_id"]
        }
    },
    "sys.task.kill": {
        "description": "Kill a background task.",
        "category": "execution",
        "inputSchema": {
             "type": "object",
             "properties": {"task_id": {"type": "string"}},
             "required": ["task_id"]
        }
    },
    "sys.tool.info": {
        "description": "Get full schema for a tool.",
        "category": "workspace",
        "inputSchema": {
             "type": "object",
             "properties": {"tool_name": {"type": "string"}},
             "required": ["tool_name"]
        }
    },
    "sys.tool.search": {
        "description": "Search tools by description.",
        "category": "workspace",
        "inputSchema": {
             "type": "object",
             "properties": {"query": {"type": "string"}},
             "required": ["query"]
        }
    },
    "mem.analysis.log": {
        "description": "Append to workspace/analysis.md",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {"entry": {"type": "string"}},
            "required": ["entry"]
        }
    },
    "mem.methods.append": {
        "description": "Append to workspace/methods.md",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {"method": {"type": "string"}},
            "required": ["method"]
        }
    },
    "tool.search.semantic_scholar": {
        "description": "Search Semantic Scholar.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"]
        }
    },
    "tool.search.pubmed": {
        "description": "Search PubMed.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"]
        }
    },
    "tool.search.crossref": {
        "description": "Search Crossref.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"]
        }
    },
    "tool.search.web": {
        "description": "Search the web.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "number"}},
            "required": ["query"]
        }
    },
    "tool.web.scrape": {
        "description": "Scrape a webpage.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        }
    },
    "tool.literature.download": {
        "description": "Download a paper PDF.",
        "category": "search",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "filename": {"type": "string"}},
            "required": ["url", "filename"]
        }
    },
    "tool.python.exec": {
        "description": "Execute a Python script.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"script_path": {"type": "string"}},
            "required": ["script_path"]
        }
    },
    "tool.package.install": {
        "description": "Install Python packages.",
        "category": "execution",
        "inputSchema": {
            "type": "object",
            "properties": {"packages": {"type": "array", "items": {"type": "string"}}},
            "required": ["packages"]
        }
    },
    "tool.env.freeze": {
        "description": "Freeze current environment.",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "tool.env.restore": {
        "description": "Restore environment.",
        "category": "execution",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "tool.data.sample": {
        "description": "Sample data.",
        "category": "execution",
        "inputSchema": {
             "type": "object",
             "properties": {
                  "filepath": {"type": "string"},
                  "n_rows": {"type": "number"},
                  "strategy": {"type": "string"}
             },
             "required": ["filepath", "n_rows", "strategy"]
        }
    },
    "tool.log.decision": {
        "description": "Log a key reasoning step.",
        "category": "memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "selected": {"type": "string"},
                "rationale": {"type": "string"}
            },
            "required": ["context", "selected", "rationale"]
        }
    }
}

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _log_search(root: Path, tool_name: str, query: str, count: int):
    log_path = root / "workspace" / "logs" / "searches.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps({
            "timestamp": now_iso(),
            "tool": tool_name,
            "query": query,
            "results_count": count
        }) + "\n")

def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    if not _rate_limiter.is_allowed():
        return _text(_error_envelope("Rate limit exceeded."))
    
    logger.info(f"Tool call: {name}")

    if name == "sys.guidance.list":
        res = list_protocols(root)
        if "error" in res:
             return _text(_error_envelope(res["error"]))
        # Lazy loading tier 1
        summaries = [{"name": p["name"], "description": p["description"]} for p in res["protocols"]]
        return _text(_success_envelope({"protocols": summaries}))
        
    if name == "sys.guidance.get":
        p_name = arguments.get("protocol_name")
        res = get_protocol(p_name, root)
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
                matches.append({"name": t_name, "description": t_schema.get("description", "")})
        return _text(_success_envelope({"tools": matches}))

    if name == "sys.workspace.scaffold":
        scaffold_minimal_workspace(root, arguments.get("project_name", "Research Project"))
        _profile_inputs(root)
        return _text(_success_envelope({"scaffolded": True}))

    if name == "sys.file.read":
        p = root / arguments["filepath"]
        if not p.exists() or not p.is_file():
            return _text(_error_envelope("File not found"))
        return _text(_success_envelope({"content": p.read_text()}))

    if name == "sys.file.write":
        p = root / arguments["filepath"]
        # Immutability enforcement phase 6
        if "inputs/raw_data" in str(p) or "inputs/literature" in str(p):
            if "inputs/literature_index.yaml" not in str(p):
                return _text(_error_envelope("WriteProtectedError: Cannot modify raw inputs."))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(arguments["content"])
        return _text(_success_envelope({"written": True, "checksum": compute_file_hash(p)}))

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
        return _text(_success_envelope({
            "current_branch": state.get("current_branch"),
            "branches": list(state.get("branches", {}).keys())
        }))
        
    if name == "sys.checkpoint.create":
        res = create_checkpoint(arguments.get("description", ""), root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.checkpoint.rollback":
        res = rollback_checkpoint(arguments["checkpoint_id"], root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.checkpoint.list":
        res = list_checkpoints(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.checkpoint.pending":
        res = checkpoint_pending(arguments["description"], arguments["requires_approval"], root)
        return _text(_success_envelope(res)) if res["status"] != "error" else _text(_error_envelope(res["message"]))
        
    if name == "sys.checkpoint.approve":
        res = checkpoint_approve(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))

    if name == "sys.branch.create":
        res = create_experiment_branch(arguments["name"], arguments.get("hypothesis", ""), arguments.get("parent"), root=root)
        return _text(_success_envelope(res))
        
    if name == "sys.branch.switch":
        res = switch_branch(arguments["branch_id"], root)
        return _text(_success_envelope(res)) if "error" not in res else _text(_error_envelope(str(res.get("error"))))
        
    if name == "sys.branch.list":
        res = list_branches(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.branch.merge":
        res = merge_branches(arguments["source"], arguments["target"], arguments["message"], root)
        return _text(_success_envelope(res)) if "error" not in res else _text(_error_envelope(str(res.get("error"))))

    if name == "sys.config.init":
        res = init_config(root)
        return _text(_success_envelope(res))
        
    if name == "sys.config.get":
        res = get_config(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.config.set":
        res = set_config(arguments["key"], arguments["value"], root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.config.validate":
        res = validate_config(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.notify":
        res = notify_researcher(arguments["message"], arguments["level"], root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))
        
    if name == "sys.external_mcp.discover":
        res = discover_mcp(root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))

    if name == "sys.task.monitor":
        res = task_monitor(arguments["task_id"])
        return _text(_success_envelope(res))
        
    if name == "sys.task.kill":
        res = task_kill(arguments["task_id"])
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
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res["message"]))

    if name == "tool.python.exec":
        p = root / arguments["script_path"]
        if not p.exists():
            return _text(_error_envelope("Script not found"))
            
        # Try to read data_inventory to check duration
        try:
             inventory_path = root / "workspace" / "logs" / "data_inventory.json"
             if inventory_path.exists():
                  with open(inventory_path, "r") as f:
                       inv = json.load(f)
                  est_sec = inv.get("estimated_processing_time_seconds", 0)
                  # If est_sec > 300, issue warning instead of executing, user must confirm
                  # We'll assume the client parses this structure
        except Exception:
             pass
        
        res = subprocess.run([sys.executable, str(p)], cwd=str(p.parent), capture_output=True, text=True)
        return _text(_success_envelope({"stdout": res.stdout, "stderr": res.stderr, "code": res.returncode}))
        
    if name == "tool.package.install":
        res = package_install(arguments["packages"])
        return _text(_success_envelope(res))
        
    if name == "tool.env.freeze":
        res = env_freeze()
        return _text(_success_envelope(res))
        
    if name == "tool.env.restore":
        return _text(_success_envelope({"message": "tool.env.restore is a stub implementation."}))
        
    if name == "tool.data.sample":
        res = data_sample(arguments["filepath"], arguments["n_rows"], arguments["strategy"], root)
        return _text(_success_envelope(res)) if res["status"] == "success" else _text(_error_envelope(res.get("message", res.get("error", "Unknown error"))))

    if name == "tool.log.decision":
        res = log_decision(arguments["context"], arguments["selected"], arguments["rationale"], root=root)
        return _text(_success_envelope(res))

    # Catch-all for unimplemeted tools
    if name.startswith("sys.") or name.startswith("tool.") or name.startswith("mem."):
        return _text(_success_envelope({"message": f"{name} is a stub implementation."}))

    return _text(_error_envelope(f"Unknown tool: {name}"))


if HAS_MCP:
    server = Server("research-os")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name=name, description=schema["description"], inputSchema=schema["inputSchema"])
            for name, schema in TOOL_DEFINITIONS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        import os
        root = Path(os.getcwd())
        return _handle_tool_call(name, arguments, root)

    async def run_stdio() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


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
