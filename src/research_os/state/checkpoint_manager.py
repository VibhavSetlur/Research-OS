#!/usr/bin/env python3
"""Checkpoint/Restore System — serialized snapshots at phase boundaries.

Enables resume from any checkpoint without rerunning expensive earlier phases.

Location: .os_state/checkpoints/<phase>_<timestamp>.json
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from research_os.utils.common import find_project_root


class CheckpointManager:
    """Manages phase-level checkpoints for the research pipeline."""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        if checkpoint_dir is None:
            root = find_project_root()
            checkpoint_dir = root / ".os_state" / "checkpoints"
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        phase: str,
        data: dict,
        metadata: Optional[dict] = None,
    ) -> Path:
        """Save a checkpoint for the given phase.

        Stores: phase data as JSON, file hashes for loaded data,
        and a preview manifest.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{phase}_{timestamp}.json"
        path = self._dir / filename

        checkpoint = {
            "phase": phase,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "data": data,
            "file_hashes": self._hash_loaded_files(data.get("loaded_files", [])),
        }

        fd, tmp_path = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(checkpoint, f, indent=2, default=str)
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return path

    def load(self, phase: str, latest: bool = True) -> Optional[dict]:
        """Load the latest (or specific) checkpoint for a phase."""
        checkpoints = self.list_for_phase(phase)
        if not checkpoints:
            return None
        target = checkpoints[-1] if latest else checkpoints[0]
        with open(target) as f:
            return json.load(f)

    def list_for_phase(self, phase: str) -> list[Path]:
        """List all checkpoints for a phase, sorted by timestamp."""
        pattern = f"{phase}_*.json"
        files = sorted(self._dir.glob(pattern))
        return files

    def list_all(self) -> list[dict]:
        """List all checkpoints with metadata."""
        results = []
        for f in sorted(self._dir.glob("*.json")):
            with open(f) as fh:
                cp = json.load(fh)
            results.append(
                {
                    "file": str(f),
                    "phase": cp.get("phase"),
                    "timestamp": cp.get("timestamp"),
                    "metadata": cp.get("metadata", {}),
                }
            )
        return results

    def delete(self, phase: str, keep_latest: int = 1) -> int:
        """Delete old checkpoints for a phase, keeping the latest N."""
        checkpoints = self.list_for_phase(phase)
        to_delete = checkpoints[:-keep_latest] if len(checkpoints) > keep_latest else []
        for cp in to_delete:
            cp.unlink()
        return len(to_delete)

    @staticmethod
    def _hash_loaded_files(file_paths: list[str]) -> dict[str, str]:
        """Compute SHA-256 hashes for listed files."""
        hashes = {}
        for fp in file_paths:
            path = Path(fp)
            if path.exists() and path.is_file():
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                hashes[fp] = h.hexdigest()[:16]
        return hashes

    def summary(self) -> str:
        checkpoints = self.list_all()
        lines = [
            "=" * 60,
            "CHECKPOINT STATUS",
            "=" * 60,
            "",
            f"  Total checkpoints: {len(checkpoints)}",
            "",
        ]
        if not checkpoints:
            lines.append("  No checkpoints saved yet.")
        else:
            lines.append("  Checkpoints:")
            for cp in checkpoints:
                ts = cp.get("timestamp", "unknown")[:19]
                meta = cp.get("metadata", {})
                extra = (
                    f" — {meta.get('description', '')}"
                    if meta.get("description")
                    else ""
                )
                lines.append(f"    - {cp['phase']} [{ts}]{extra}")
        lines.append("")
        return "\n".join(lines)

    def get_latest_checkpoint_summary(self) -> dict:
        """Return a summary of the latest checkpoint.

        Returns dict with: phase, timestamp, key results (effect sizes,
        significant findings), and pending actions. Feeds into session_restorer.py.
        """
        all_checkpoints = sorted(
            self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime
        )
        if not all_checkpoints:
            return {
                "phase": "none",
                "timestamp": None,
                "key_results": [],
                "pending_actions": [],
            }

        latest_path = all_checkpoints[-1]
        with open(latest_path) as f:
            cp = json.load(f)

        data = cp.get("data", {})
        key_results = []

        # Extract effect sizes and significant findings
        for finding in data.get("findings", []):
            if isinstance(finding, dict):
                result = {
                    "variable": finding.get(
                        "variable", finding.get("predictor", "unknown")
                    ),
                    "effect_size": finding.get(
                        "effect_size", finding.get("coef", finding.get("estimate"))
                    ),
                    "significant": finding.get("p_value", 1) < 0.05,
                }
                key_results.append(result)

        # Extract from analysis results if present
        for analysis in data.get("analysis_results", []):
            if isinstance(analysis, dict):
                result = {
                    "method": analysis.get("method", "unknown"),
                    "effect_size": analysis.get("effect_size"),
                    "significant": analysis.get("p_value", 1) < 0.05,
                }
                key_results.append(result)

        # Determine pending actions based on phase
        phase = cp.get("phase", "unknown")
        phase_next = {
            "research_init": "literature_deep",
            "literature_deep": "method_route",
            "method_route": "data_scaffold",
            "data_scaffold": "execute_analysis",
            "execute_analysis": "compile_outputs",
            "compile_outputs": "audit_validate",
            "audit_validate": "complete",
        }
        pending = [phase_next.get(phase, "complete")]

        return {
            "phase": phase,
            "timestamp": cp.get("timestamp"),
            "key_results": key_results,
            "pending_actions": pending,
        }
