import logging
from typing import Dict, Any
from pathlib import Path
from research_os.tools.actions.config import get_config

logger = logging.getLogger("research.tools.external_mcp")

def discover_mcp(root: Path) -> Dict[str, Any]:
    res = get_config(root)
    if res["status"] == "error":
         return res
    config = res["config"]
    servers = config.get("external_mcp_servers", [])
    return {"status": "success", "servers": servers}
