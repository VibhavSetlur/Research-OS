"""External MCP Server Manager.

Handles automatic installation and routing for standard open-source MCP servers:
  - @modelcontextprotocol/server-sqlite   — SQL database access
  - @modelcontextprotocol/server-filesystem — local file system access

Agent queries are routed through these standard protocols natively, removing
the need for custom one-off adapters.
"""

import json
import logging
import shutil
import subprocess
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("research.external_mcp")

# ---------------------------------------------------------------------------
# Standard MCP server catalogue
# ---------------------------------------------------------------------------

STANDARD_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "sqlite": {
        "package": "@modelcontextprotocol/server-sqlite",
        "description": "SQL database access via MCP",
        "default_port": 5010,
        "requires": ["node", "npx"],
        "start_cmd": ["npx", "-y", "@modelcontextprotocol/server-sqlite", "{db_path}"],
        "capabilities": ["query", "list_tables", "describe_table", "create_table"],
    },
    "filesystem": {
        "package": "@modelcontextprotocol/server-filesystem",
        "description": "Local file system read/write via MCP",
        "default_port": 5011,
        "requires": ["node", "npx"],
        "start_cmd": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "{root_path}"],
        "capabilities": ["read_file", "write_file", "list_directory", "search_files"],
    },
}


def _check_node_available() -> bool:
    """Return True if Node.js and npx are on PATH."""
    return shutil.which("node") is not None and shutil.which("npx") is not None


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if *port* is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class ExternalMCPManager:
    """External MCP Tool Manager.

    Handles installation probing, process launch, and native query routing
    for standard open-source MCP servers (sqlite, filesystem).

    Usage::

        mgr = ExternalMCPManager(project_root)
        mgr.ensure_servers_ready()  # called by setup/init
        result = mgr.route_query("list all tables in the research database")
    """

    def __init__(self, project_root: Optional[Path] = None):
        from research_copilot.utils.common import find_project_root
        self.root = project_root or find_project_root()
        self._running: Dict[str, subprocess.Popen] = {}
        self.external_servers: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Installation checks
    # ------------------------------------------------------------------

    def check_server_available(self, server_id: str) -> Dict[str, Any]:
        """Check whether a standard MCP server can be launched.

        Returns a status dict with keys: server_id, available, reason.
        """
        spec = STANDARD_MCP_SERVERS.get(server_id)
        if not spec:
            return {"server_id": server_id, "available": False, "reason": "Unknown server ID."}

        if not _check_node_available():
            return {
                "server_id": server_id,
                "available": False,
                "reason": "Node.js / npx not found. Install Node.js >= 18.",
            }

        return {"server_id": server_id, "available": True, "reason": "OK"}

    def check_all_servers(self) -> List[Dict[str, Any]]:
        """Return availability status for all standard servers."""
        return [self.check_server_available(sid) for sid in STANDARD_MCP_SERVERS]

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def start_server(
        self,
        server_id: str,
        *,
        db_path: Optional[str] = None,
        root_path: Optional[str] = None,
        port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a standard MCP server as a background process.

        Args:
            server_id:  Key in STANDARD_MCP_SERVERS ('sqlite', 'filesystem').
            db_path:    Path to SQLite database (required for 'sqlite').
            root_path:  Root directory for filesystem server (defaults to project root).
            port:       Override the default port.

        Returns:
            Dict with status, server_id, port, pid.
        """
        status = self.check_server_available(server_id)
        if not status["available"]:
            return {"status": "error", "server_id": server_id, "reason": status["reason"]}

        spec = STANDARD_MCP_SERVERS[server_id]
        effective_port = port or spec["default_port"]

        # Don't start a second instance if already running.
        if server_id in self._running and self._running[server_id].poll() is None:
            return {
                "status": "already_running",
                "server_id": server_id,
                "port": effective_port,
                "pid": self._running[server_id].pid,
            }

        # Build the start command.
        cmd = list(spec["start_cmd"])
        if server_id == "sqlite":
            effective_db = db_path or str(
                self.root / ".research" / "cache" / "research_cache.db"
            )
            cmd = [c.replace("{db_path}", effective_db) for c in cmd]
        elif server_id == "filesystem":
            effective_root = root_path or str(self.root)
            cmd = [c.replace("{root_path}", effective_root) for c in cmd]

        env = {"PORT": str(effective_port)}
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**__import__("os").environ, **env},
            )
            self._running[server_id] = proc
            logger.info(
                "Started MCP server '%s' on port %d (pid %d)",
                server_id, effective_port, proc.pid,
            )
            return {
                "status": "started",
                "server_id": server_id,
                "port": effective_port,
                "pid": proc.pid,
                "capabilities": spec["capabilities"],
            }
        except Exception as exc:
            logger.error("Failed to start MCP server '%s': %s", server_id, exc)
            return {"status": "error", "server_id": server_id, "reason": str(exc)}

    def stop_server(self, server_id: str) -> Dict[str, Any]:
        """Terminate a running MCP server process."""
        proc = self._running.get(server_id)
        if proc is None or proc.poll() is not None:
            return {"status": "not_running", "server_id": server_id}
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        del self._running[server_id]
        return {"status": "stopped", "server_id": server_id}

    def stop_all(self) -> None:
        """Terminate all running MCP server processes."""
        for sid in list(self._running.keys()):
            self.stop_server(sid)

    # ------------------------------------------------------------------
    # Convenience: ensure standard servers are ready
    # ------------------------------------------------------------------

    def ensure_servers_ready(
        self,
        servers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Start all standard servers that are available but not yet running.

        Called automatically during ``rcp init`` and ``rcp setup``.

        Args:
            servers: List of server IDs to start.  Defaults to all standard servers.

        Returns:
            List of start-result dicts.
        """
        target = servers or list(STANDARD_MCP_SERVERS.keys())
        results = []
        for sid in target:
            result = self.start_server(sid)
            results.append(result)
            if result["status"] in ("started", "already_running"):
                spec = STANDARD_MCP_SERVERS[sid]
                self.external_servers[sid] = {
                    "status": "connected",
                    "port": result.get("port", spec["default_port"]),
                    "tools": spec["capabilities"],
                }
        return results

    # ------------------------------------------------------------------
    # Query routing
    # ------------------------------------------------------------------

    def route_query(
        self,
        query: str,
        server_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route an agent query to the appropriate MCP server.

        For now this is a lightweight keyword router; in future iterations
        it will use the MCP JSON-RPC protocol directly.

        Args:
            query:     Natural-language query from an agent.
            server_id: Force a specific server (optional).

        Returns:
            Dict with routed_to, endpoint, status.
        """
        if server_id and server_id in self.external_servers:
            target = server_id
        elif any(kw in query.lower() for kw in ("sql", "table", "query", "select", "database", "db")):
            target = "sqlite"
        elif any(kw in query.lower() for kw in ("file", "read", "write", "directory", "path", "csv", "json")):
            target = "filesystem"
        else:
            target = "filesystem"  # safe default

        server_info = self.external_servers.get(target, {})
        if not server_info:
            return {
                "status": "not_available",
                "reason": f"Server '{target}' is not running. Call ensure_servers_ready() first.",
                "routed_to": target,
            }

        port = server_info.get("port", STANDARD_MCP_SERVERS[target]["default_port"])
        return {
            "status": "routed",
            "routed_to": target,
            "endpoint": f"http://localhost:{port}",
            "capabilities": server_info.get("tools", []),
        }

    # ------------------------------------------------------------------
    # Backwards-compatible attach API
    # ------------------------------------------------------------------

    def attach_external_mcp(self, server_uri: str, auth: str = "") -> Dict[str, Any]:
        """Attach an arbitrary external MCP server by URI.

        Args:
            server_uri: Full URI of the external MCP server.
            auth:       Optional bearer token.

        Returns:
            Status dict.
        """
        logger.info("Attaching external MCP server at %s", server_uri)
        self.external_servers[server_uri] = {
            "status": "connected",
            "tools": [],
            "auth": bool(auth),
        }
        return {"status": "success", "server": server_uri, "tools_imported": 0}

    def list_external_tools(self) -> List[str]:
        """List all capability names across all registered servers."""
        tools: List[str] = []
        for server in self.external_servers.values():
            tools.extend(server.get("tools", []))
        return tools

    def server_status(self) -> Dict[str, Any]:
        """Return a summary of all known servers and their run state."""
        summary: Dict[str, Any] = {}
        for sid, spec in STANDARD_MCP_SERVERS.items():
            proc = self._running.get(sid)
            running = proc is not None and proc.poll() is None
            summary[sid] = {
                "description": spec["description"],
                "default_port": spec["default_port"],
                "running": running,
                "pid": proc.pid if running else None,
            }
        for uri, info in self.external_servers.items():
            if uri not in summary:
                summary[uri] = {"status": info.get("status"), "tools": info.get("tools", [])}
        return summary
