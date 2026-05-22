import subprocess
import sys
import logging
from typing import Dict, Any, List

logger = logging.getLogger("research.tools.environment")

def package_install(packages: List[str]) -> Dict[str, Any]:
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "install"] + packages, capture_output=True, text=True)
        return {"stdout": res.stdout, "stderr": res.stderr, "code": res.returncode}
    except Exception as e:
        logger.error(f"Package install failed: {e}")
        return {"error": str(e), "code": 1}

def env_freeze() -> Dict[str, Any]:
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
        return {"stdout": res.stdout, "stderr": res.stderr, "code": res.returncode}
    except Exception as e:
        logger.error(f"Env freeze failed: {e}")
        return {"error": str(e), "code": 1}
