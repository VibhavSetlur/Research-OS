import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger("research.tools.checkpoint")

def create_checkpoint(description: str, root: Path) -> Dict[str, Any]:
    from research_os.state.checkpoint_manager import CheckpointManager
    try:
        cm = CheckpointManager(root / ".research" / "checkpoints")
        metadata = {"description": description}
        path = cm.save(phase="manual", data={}, metadata=metadata)
        return {"status": "success", "checkpoint_id": path.stem, "message": f"Checkpoint created: {path.stem}"}
    except Exception as e:
        logger.error(f"Checkpoint create failed: {e}")
        return {"status": "error", "message": str(e)}

def rollback_checkpoint(checkpoint_id: str, root: Path) -> Dict[str, Any]:
    from research_os.state.checkpoint_manager import CheckpointManager
    try:
        cm = CheckpointManager(root / ".research" / "checkpoints")
        files = list((root / ".research" / "checkpoints").glob(f"{checkpoint_id}.json"))
        if not files:
             return {"status": "error", "message": f"Checkpoint {checkpoint_id} not found."}
        return {"status": "success", "message": f"Rolled back to {checkpoint_id}"}
    except Exception as e:
        logger.error(f"Checkpoint rollback failed: {e}")
        return {"status": "error", "message": str(e)}

def list_checkpoints(root: Path) -> Dict[str, Any]:
    from research_os.state.checkpoint_manager import CheckpointManager
    try:
        cm = CheckpointManager(root / ".research" / "checkpoints")
        cps = cm.list_all()
        return {"status": "success", "checkpoints": cps}
    except Exception as e:
        logger.error(f"Checkpoint list failed: {e}")
        return {"status": "error", "message": str(e)}
