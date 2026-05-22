import logging
from typing import Dict, Any
from pathlib import Path
import urllib.request

logger = logging.getLogger("research.tools.literature")

def download_literature(url: str, filename: str, root: Path) -> Dict[str, Any]:
    try:
        out_path = root / "inputs" / "literature" / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, out_path)
        return {"status": "success", "filepath": str(out_path.absolute())}
    except Exception as e:
        logger.error(f"Download literature failed: {e}")
        return {"status": "error", "message": str(e)}
