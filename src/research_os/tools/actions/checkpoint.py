import zipfile
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger("research.tools.checkpoint")


def _snapshot_workspace(root: Path, checkpoint_id: str):
    workspace = root / "workspace"
    if not workspace.exists():
        return
    zip_path = root / ".os_state" / "checkpoints" / f"{checkpoint_id}_workspace.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for p in workspace.rglob("*"):
            # Exclude data/ directory
            if "workspace/data" in str(p) or "workspace/.os_state" in str(p):
                continue
            if p.is_file():
                zipf.write(p, p.relative_to(root))


def _restore_workspace(root: Path, checkpoint_id: str):
    zip_path = root / ".os_state" / "checkpoints" / f"{checkpoint_id}_workspace.zip"
    if not zip_path.exists():
        return
    with zipfile.ZipFile(zip_path, "r") as zipf:
        zipf.extractall(root)


def create_checkpoint(description: str, root: Path) -> Dict[str, Any]:
    from research_os.state.checkpoint_manager import CheckpointManager

    try:
        cm = CheckpointManager(root / ".os_state" / "checkpoints")
        metadata = {"description": description}
        path = cm.save(phase="manual", data={}, metadata=metadata)
        _snapshot_workspace(root, path.stem)
        return {
            "status": "success",
            "checkpoint_id": path.stem,
            "message": f"Checkpoint created: {path.stem}",
        }
    except Exception as e:
        logger.error(f"Checkpoint create failed: {e}")
        return {"status": "error", "message": str(e)}


def rollback_checkpoint(checkpoint_id: str, root: Path) -> Dict[str, Any]:

    try:
        files = list((root / ".os_state" / "checkpoints").glob(f"{checkpoint_id}.json"))
        if not files:
            return {
                "status": "error",
                "message": f"Checkpoint {checkpoint_id} not found.",
            }
        _restore_workspace(root, checkpoint_id)
        return {"status": "success", "message": f"Rolled back to {checkpoint_id}"}
    except Exception as e:
        logger.error(f"Checkpoint rollback failed: {e}")
        return {"status": "error", "message": str(e)}


def list_checkpoints(root: Path) -> Dict[str, Any]:
    from research_os.state.checkpoint_manager import CheckpointManager

    try:
        cm = CheckpointManager(root / ".os_state" / "checkpoints")
        cps = cm.list_all()
        return {"status": "success", "checkpoints": cps}
    except Exception as e:
        logger.error(f"Checkpoint list failed: {e}")
        return {"status": "error", "message": str(e)}
