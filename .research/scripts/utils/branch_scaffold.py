#!/usr/bin/env python3
"""Experiment branch scaffolding — auto-creates self-contained experiment workspaces.

When a new research branch is created, this module scaffolds a full directory
under 02_experiments/<experiment_id>/ so scripts, outputs, artifacts, and
decisions travel together.

Usage:
    from branch_scaffold import BranchScaffold
    scaffold = BranchScaffold()
    scaffold.create_branch_workspace("hypothesis_B")
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("research.branch_scaffold")

EXPERIMENT_SUBDIRS = [
    "scripts",
    "outputs",
    "outputs/figures",
    "outputs/tables",
    "outputs/artifacts",
    "outputs/analysis",
]


class BranchScaffold:
    """Auto-scaffold branch-specific workspace directories."""

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = self._find_project_root()
        self.root = Path(project_root)

    @staticmethod
    def _find_project_root() -> Path:
        p = Path.cwd()
        for _ in range(10):
            if (p / ".research").exists():
                return p
            if p.parent == p:
                break
            p = p.parent
        return Path.cwd()

    def create_branch_workspace(self, branch_id: str, hypothesis: str = "") -> dict:
        """Create full directory structure for a new branch.

        Args:
            branch_id: Unique branch identifier
            hypothesis: Research hypothesis for this branch

        Returns:
            Dict of created directories
        """
        created = {}
        exp_root = self.root / "02_experiments" / branch_id

        for subdir in EXPERIMENT_SUBDIRS:
            dir_path = exp_root / subdir
            dir_path.mkdir(parents=True, exist_ok=True)
            created[f"02_experiments/{branch_id}/{subdir}"] = str(dir_path)

            readme = dir_path / "README.md"
            if not readme.exists():
                self._write_readme(readme, branch_id, hypothesis, subdir)

        decisions = exp_root / "decisions.yaml"
        if not decisions.exists():
            decisions.write_text(
                "schema_version: '1.0'\n"
                f"experiment_id: {branch_id}\n"
                "parent_experiment: main\n"
                f"created: {datetime.now(timezone.utc).isoformat()}\n"
                "decisions:\n"
                "  decision_001:\n"
                f"    date: {datetime.now(timezone.utc).date().isoformat()}\n"
                "    context: Experiment branch created.\n"
                "    options_considered:\n"
                "      - Queue the idea for later\n"
                "      - Create an isolated experiment branch\n"
                "    selected: Create an isolated experiment branch\n"
                f"    rationale: {hypothesis or 'Exploratory branch'}\n"
                "    linked_literature: []\n"
            )
            created[f"02_experiments/{branch_id}/decisions.yaml"] = str(decisions)

        self._write_branch_manifest(branch_id, hypothesis, created)
        self._update_root_manifests(branch_id)

        logger.info("Scaffolded workspace for branch '%s': %d directories", branch_id, len(created))
        return created

    def _write_readme(self, path: Path, branch_id: str, hypothesis: str, category: str):
        """Write a README.md for a branch-specific directory."""
        content = f"""# Branch: {branch_id} — {category}

**Hypothesis**: {hypothesis or "Exploratory branch"}
**Created**: {datetime.now(timezone.utc).isoformat()}
**Parent**: main

This directory contains `{category}` files specific to the `{branch_id}` experiment.
The experiment is isolated so divergent hypotheses never overwrite each other.

## Merge Protocol
When this branch is merged into main:
1. Review outputs and sibling `.meta.yaml` files
2. Promote selected outputs into `03_synthesis/`
3. Synthesize decisions into `03_synthesis/global_methods.md`
4. Preserve this experiment directory for auditability
"""
        path.write_text(content)

    def _write_branch_manifest(self, branch_id: str, hypothesis: str, created: dict):
        """Write a branch-specific manifest.json."""
        manifest = {
            "branch_id": branch_id,
            "hypothesis": hypothesis,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "directories": created,
            "files": {},
            "merge_status": None,
        }

        branch_manifest_dir = self.root / "03_synthesis" / "branches"
        branch_manifest_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = branch_manifest_dir / f"{branch_id}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def _update_root_manifests(self, branch_id: str):
        """Update the root 03_synthesis/manifest.json with branch information."""
        manifest_path = self.root / "03_synthesis" / "manifest.json"
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        manifest.setdefault("branches", {})
        manifest["branches"][branch_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def get_branch_dirs(self, branch_id: str) -> dict:
        """Get all directories for a specific branch.

        Returns:
            Dict mapping category to directory path
        """
        result = {}

        for subdir in EXPERIMENT_SUBDIRS:
            dir_path = self.root / "02_experiments" / branch_id / subdir
            if dir_path.exists():
                result[subdir] = str(dir_path)

        return result

    def list_branch_workspaces(self) -> list:
        """List all branch workspaces that exist on disk."""
        branches = []

        experiments = self.root / "02_experiments"
        if experiments.exists():
            for d in experiments.iterdir():
                if d.is_dir():
                    branches.append(d.name)

        return sorted(set(branches))

    def cleanup_branch_workspace(self, branch_id: str, dry_run: bool = True) -> dict:
        """List files that would be removed for a branch workspace.

        Args:
            branch_id: Branch to clean up
            dry_run: If True, only list files; if False, actually remove

        Returns:
            Dict of affected paths
        """
        affected = {}

        for subdir in EXPERIMENT_SUBDIRS:
            dir_path = self.root / "02_experiments" / branch_id / subdir
            if dir_path.exists():
                if dry_run:
                    files = list(dir_path.rglob("*"))
                    affected[f"02_experiments/{branch_id}/{subdir}"] = {
                        "path": str(dir_path),
                        "file_count": len([f for f in files if f.is_file()]),
                        "action": "would_remove",
                    }
                else:
                    shutil.rmtree(dir_path)
                    affected[f"02_experiments/{branch_id}/{subdir}"] = {
                        "path": str(dir_path),
                        "action": "removed",
                    }

        return affected
