from typing import Dict, Any, List
from pathlib import Path
import yaml
import logging

logger = logging.getLogger("research.tools.protocol")

_PROTOCOL_CACHE: Dict[str, Dict[str, Any]] = {}

def get_protocol(name: str, root: Path) -> Dict[str, Any]:
    try:
        if name in _PROTOCOL_CACHE:
             return {"content": yaml.dump(_PROTOCOL_CACHE[name])}
             
        p_file = root / "src" / "research_os" / "protocols" / f"{name}.yaml"
        if not p_file.exists():
             return {"error": "Protocol not found"}
             
        data = yaml.safe_load(p_file.read_text())
        _PROTOCOL_CACHE[name] = data
        return {"content": yaml.dump(data)}
    except Exception as e:
        logger.error(f"Get protocol failed: {e}")
        return {"error": str(e)}

def list_protocols(root: Path) -> Dict[str, Any]:
    try:
        p_dir = root / "src" / "research_os" / "protocols"
        if not p_dir.exists():
            return {"error": "Protocols directory not found"}
        protocols = []
        for p in p_dir.glob("*.yaml"):
            try:
                name = p.stem
                if name in _PROTOCOL_CACHE:
                     data = _PROTOCOL_CACHE[name]
                else:
                     data = yaml.safe_load(p.read_text())
                     _PROTOCOL_CACHE[name] = data
                     
                protocols.append({
                    "name": name,
                    "description": data.get("description", ""),
                    "version": data.get("version", "1.0.0")
                })
            except Exception:
                pass
        return {"protocols": protocols}
    except Exception as e:
         logger.error(f"List protocols failed: {e}")
         return {"error": str(e)}
