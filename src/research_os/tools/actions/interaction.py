import logging
from typing import Dict, Any
from pathlib import Path
from research_os.project_ops import now_iso

logger = logging.getLogger("research.tools.interaction")

def notify_researcher(message: str, level: str, root: Path) -> Dict[str, Any]:
    try:
        log_path = root / "workspace" / "logs" / "notifications.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{now_iso()}] [{level.upper()}] {message}\n")
        return {"status": "success", "message": "Notification logged."}
    except Exception as e:
        logger.error(f"Notify failed: {e}")
        return {"status": "error", "message": str(e)}

def checkpoint_pending(description: str, requires_approval: bool, root: Path) -> Dict[str, Any]:
    # Write pending action to a state file
    try:
        pending_path = root / ".research" / "pending_approval.txt"
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.write_text(description)
        return {"status": "pending_approval", "message": "Awaiting researcher approval via sys.checkpoint.approve"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def checkpoint_approve(root: Path) -> Dict[str, Any]:
    try:
        pending_path = root / ".research" / "pending_approval.txt"
        if pending_path.exists():
            pending_path.unlink()
            return {"status": "success", "message": "Action approved."}
        return {"status": "error", "message": "No pending action found."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
