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

        # Check permissions (warning if world-readable)
        warning = None
        if os.name != "nt":
            try:
                mode = os.stat(config_path).st_mode
                if bool(mode & 0o004):  # Others have read permission
                    warning = "WARNING: inputs/researcher_config.yaml is world-readable! Please run `chmod 600 inputs/researcher_config.yaml` to secure your API keys."
            except Exception:
                pass

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Mask API keys before returning
        safe_config = _mask_api_keys(config)

        res = {"status": "success", "config": safe_config}
        if warning:
            res["warning"] = warning
        return res
    except Exception as e:
        logger.error(f"Get config failed: {e}")
        return {"status": "error", "message": str(e)}


def set_config(key: str, value: Any, root: Path) -> Dict[str, Any]:
    try:
        config_path = root / "inputs" / "researcher_config.yaml"
        if not config_path.exists():
            config = {}
        else:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

        # Simple dot notation support for key
        parts = key.split(".")
        current = config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
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
        template = '''# ============================================================
# Researcher Configuration
# Uncomment and fill in the options below.
# ============================================================

# researcher:
#   name: "Your Name"
#   expertise_level: "intermediate"   # beginner, intermediate, advanced, pi
#   field: "environmental epidemiology"
#   institution: ""
#   orcid: ""

# interaction:
#   autonomy_level: "supervised"   # manual, supervised, autopilot

# research_goal:
#   output_types: ["paper", "poster", "dashboard"]   # paper, poster, dashboard, abstract, exploratory
#   target_venue: "journal"   # journal, conference, preprint, dissertation, report, exploratory
#   poster_dimensions: "36x48"

# model_profile: "medium"   # small, medium, large

# api_keys:
#   firecrawl: ""   # Get from https://firecrawl.io
#   semantic_scholar: ""
#   pubmed: ""
#   crossref: ""
#   serpapi: ""

# external_mcp_servers: []

# writing_preferences:
#   citation_style: "apa"
#   default_reporting_standard: "strobe"
'''
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(template)

        # Restrict permissions
        if os.name != "nt":
            try:
                os.chmod(config_path, 0o600)
            except Exception:
                pass

        # Add to .gitignore
        gitignore_path = root / ".gitignore"
        gitignore_content = ""
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()

        if "inputs/researcher_config.yaml" not in gitignore_content:
            with open(gitignore_path, "a") as gf:
                gf.write("\n# Secure config\ninputs/researcher_config.yaml\n")

        return {
            "status": "success",
            "message": "Initialized default config and secured it. Please populate api keys.",
        }
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


def _mask_api_keys(config: Dict[str, Any]) -> Dict[str, Any]:
    import copy

    safe_config = copy.deepcopy(config)
    if "api_keys" in safe_config and isinstance(safe_config["api_keys"], dict):
        for k, v in safe_config["api_keys"].items():
            if isinstance(v, str) and len(v) > 8:
                safe_config["api_keys"][k] = f"{v[:4]}...{v[-4:]}"
            elif isinstance(v, str) and len(v) > 0:
                safe_config["api_keys"][k] = "***"
    return safe_config
