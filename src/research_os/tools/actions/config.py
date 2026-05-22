import logging
from typing import Dict, Any
from pathlib import Path
import yaml
import os

logger = logging.getLogger("research.tools.config")

def get_config(root: Path) -> Dict[str, Any]:
    try:
        config_path = root / "inputs" / "researcher_config.yaml"
        if not config_path.exists():
            return {"status": "error", "message": "Config not found"}
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return {"status": "success", "config": config}
    except Exception as e:
        logger.error(f"Get config failed: {e}")
        return {"status": "error", "message": str(e)}

def set_config(key: str, value: Any, root: Path) -> Dict[str, Any]:
    try:
        config_path = root / "inputs" / "researcher_config.yaml"
        if not config_path.exists():
            config = {}
        else:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                
        # Simple dot notation support for key
        parts = key.split('.')
        current = config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
            
        return {"status": "success", "message": f"Set {key} = {value}"}
    except Exception as e:
        logger.error(f"Set config failed: {e}")
        return {"status": "error", "message": str(e)}

def init_config(root: Path) -> Dict[str, Any]:
    # Placeholder for AI-driven init process
    config_path = root / "inputs" / "researcher_config.yaml"
    if not config_path.exists():
        # Create default
        default_config = {
            "researcher": {"name": "", "expertise_level": "intermediate", "field": ""},
            "interaction": {"autonomy_level": "supervised", "notification_preferences": {"on_error": True}},
            "api_keys": {"firecrawl": "", "openai": ""}
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        return {"status": "success", "message": "Initialized default config. Please populate api keys."}
    return {"status": "success", "message": "Config already exists."}

def validate_config(root: Path) -> Dict[str, Any]:
    # Validate keys/connections
    res = get_config(root)
    if res["status"] == "error":
        return res
    config = res["config"]
    validations = []
    # Test Firecrawl
    fc_key = config.get("api_keys", {}).get("firecrawl")
    if fc_key:
         validations.append("Firecrawl API Key: Present")
    else:
         validations.append("Firecrawl API Key: Missing")
         
    return {"status": "success", "validations": validations}
