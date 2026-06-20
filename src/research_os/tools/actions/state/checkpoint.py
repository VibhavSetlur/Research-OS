"""Checkpoints — copied workspace snapshots managed by ResearchLedger."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_os.state.state_ledger import ResearchLedger

logger = logging.getLogger("research_os.tools.checkpoint")


def _ledger(root: Path) -> ResearchLedger:
    return ResearchLedger(root / ".os_state" / "state_ledger.json")


def create_checkpoint(
    description: str,
    root: Path,
    *,
    tag: str | None = None,
    keep: int = 5,
) -> dict[str, Any]:
    """Snapshot the workspace (copied files) and record metadata in state.

    Parameters
    ----------
    description : str
        Free-text describing why this checkpoint exists.
    root : Path
        Project root.
    tag : str | None, optional
        Optional retention tag (e.g. ``"before-major-refactor"``,
        ``"release-candidate"``). Tagged checkpoints survive the
        per-create GC pass; use them for snapshots you want to keep
        even after dozens of new checkpoints land.
    keep : int, default 5
        How many untagged checkpoints to retain after this create.
        Older untagged checkpoints are pruned at the end of this call.
    """
    try:
        checkpoint_id = (
            f"ckpt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:6]}"
        )
        ledger = _ledger(root)
        snap = ledger.snapshot_workspace(checkpoint_id, root=root)

        # Record description in a sidecar metadata file
        meta_path = root / ".os_state" / "checkpoints" / f"{checkpoint_id}.meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_payload: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files_snapshotted": snap.get("files_snapshotted"),
            "files_ref_only": snap.get("files_ref_only"),
        }
        if tag:
            meta_payload["tag"] = tag
        meta_path.write_text(json.dumps(meta_payload, indent=2))

        # Run GC immediately after writing so unbounded growth isn't
        # gated on the AI remembering to start a new step. Tagged
        # checkpoints are preserved by the GC; untagged ones beyond
        # `keep` are removed.
        gc_report: dict[str, Any] = {}
        try:
            from research_os.project_ops import _prune_old_checkpoints

            gc_report = _prune_old_checkpoints(root, keep=keep)
        except Exception as e:  # noqa: BLE001 — defensive; GC failure must not break create
            logger.debug("checkpoint GC skipped: %s", e)

        result: dict[str, Any] = {
            "status": "success",
            "checkpoint_id": checkpoint_id,
            "description": description,
            "files_snapshotted": snap.get("files_snapshotted"),
            "message": f"Checkpoint created: {checkpoint_id}",
        }
        if tag:
            result["tag"] = tag
        if gc_report:
            result["gc"] = gc_report
        return result
    except Exception as e:
        logger.exception("create_checkpoint failed")
        return {"status": "error", "message": str(e)}


def rollback_checkpoint(checkpoint_id: str, root: Path) -> dict[str, Any]:
    """Restore the workspace to a checkpoint (creates a backup first)."""
    try:
        ledger = _ledger(root)
        res = ledger.rollback(checkpoint_id, root=root)
        return {
            "status": "success",
            "checkpoint_id": res.get("checkpoint_id"),
            "backup_id": res.get("backup_id"),
            "files_restored": res.get("files_restored"),
            "files_removed": res.get("files_removed"),
            "message": f"Rolled back to {checkpoint_id}",
        }
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception("rollback_checkpoint failed")
        return {"status": "error", "message": str(e)}


def list_checkpoints(root: Path) -> dict[str, Any]:
    """List every checkpoint with its description."""
    try:
        checkpoints_dir = root / ".os_state" / "checkpoints"
        if not checkpoints_dir.exists():
            return {"status": "success", "checkpoints": []}

        out: list[dict[str, Any]] = []
        for meta in sorted(checkpoints_dir.glob("*.meta.json")):
            try:
                data = json.loads(meta.read_text())
                entry: dict[str, Any] = {
                    "id": data.get("checkpoint_id"),
                    "description": data.get("description", ""),
                    "created_at": data.get("created_at"),
                    "files": data.get("files_snapshotted", 0),
                }
                if data.get("tag"):
                    entry["tag"] = data["tag"]
                out.append(entry)
            except Exception:
                continue
        # Fallback: list directories that have no sidecar
        for d in sorted(checkpoints_dir.iterdir()):
            if d.is_dir() and not any(c["id"] == d.name for c in out):
                out.append({"id": d.name, "description": "(no metadata)"})
        return {"status": "success", "checkpoints": out}
    except Exception as e:
        logger.exception("list_checkpoints failed")
        return {"status": "error", "message": str(e)}
