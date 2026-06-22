"""Workspace repair — heal a broken workspace without losing data.

Common breakage modes:
  - .os_state/state_ledger.json corrupted or missing.
  - Top-level directories deleted by the researcher.
  - Mermaid diagram desynced from actual paths.
  - Manifest stale (lists paths that no longer exist).
  - Symlinks broken (workspace/.os_state).

The repair tool is conservative: it NEVER deletes files. It only recreates
missing directories, regenerates derived metadata, and reports what it did.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.repair")


def workspace_repair(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Detect and (optionally) fix workspace integrity issues."""
    from research_os.project_ops import (
        EAGER_DIRS,
        _update_manifest,
        _update_workflow_mermaid,
        default_state,
        load_state,
        manifest_path,
        save_state,
        state_json_path,
        write_json,
    )

    actions: list[str] = []
    issues: list[str] = []

    # 1. Top-level directories.
    # Repair only ensures EAGER dirs exist. LAZY dirs (synthesis/,
    # environment/, inputs/raw_data/, inputs/literature/, inputs/context/)
    # are intentionally absent until the first writer materialises them
    # via ensure_lazy_dir — repairing them would re-introduce the empty
    # folder noise the lazy split was designed to eliminate.
    for rel in EAGER_DIRS:
        d = root / rel
        if not d.exists():
            issues.append(f"missing dir: {rel}")
            if not dry_run:
                d.mkdir(parents=True, exist_ok=True)
                actions.append(f"created {rel}/")

    # 2. State ledger
    state_path = state_json_path(root)
    if not state_path.exists():
        issues.append("state_ledger.json missing")
        if not dry_run:
            save_state(root, default_state())
            actions.append("recreated state_ledger.json with defaults")
    else:
        try:
            with open(state_path) as f:
                json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            issues.append(f"state_ledger.json corrupted: {e}")
            if not dry_run:
                # Back the corrupted file up, then reseed.
                backup = state_path.with_suffix(
                    f".broken_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
                )
                state_path.rename(backup)
                actions.append(f"corrupted state backed up to {backup.name}")
                save_state(root, default_state())
                actions.append("recreated state_ledger.json with defaults")

    # 3. Manifest
    mp = manifest_path(root)
    if not mp.exists():
        issues.append("manifest.json missing")
        if not dry_run:
            write_json(mp, {"schema_version": "2.0", "paths": {}, "created_at": _now()})
            actions.append("created manifest.json")

    # 4. workspace/.os_state symlink
    ws_os_state = root / "workspace" / ".os_state"
    if not ws_os_state.exists():
        issues.append("workspace/.os_state symlink missing")
        if not dry_run:
            try:
                ws_os_state.symlink_to(root / ".os_state", target_is_directory=True)
                actions.append("recreated workspace/.os_state symlink")
            except OSError as e:
                actions.append(f"could not recreate symlink: {e}")

    # 5. Per-experiment subdirs (if folder exists but a key subdir is missing).
    #    The data/* subdirs come in two flavours: the 3.2 names and the
    #    pre-3.2 legacy names. We only flag a data subdir as missing when
    #    NEITHER the 3.2 name NOR its legacy alias is present, so repairing a
    #    pre-3.2 project doesn't sprinkle empty 3.2 dirs next to the old ones.
    workspace = root / "workspace"
    expected_subs = {"scripts", "outputs/reports",
                     "outputs/figures", "outputs/tables", "environment"}
    # data subdir → its legacy alias (None = no alias / always expected).
    data_subs = {
        "data/past_step_input": "data/input",
        "data/next_step_output": "data/output",
        "data/share": None,
    }
    if workspace.exists():
        for exp in workspace.iterdir():
            if not (exp.is_dir() and exp.name[:2].isdigit()):
                continue
            for sub in expected_subs:
                d = exp / sub
                if not d.exists():
                    issues.append(f"missing {exp.name}/{sub}")
                    if not dry_run:
                        d.mkdir(parents=True, exist_ok=True)
                        actions.append(f"recreated {exp.name}/{sub}")
            for sub, legacy in data_subs.items():
                d = exp / sub
                alias = (exp / legacy) if legacy else None
                present = d.exists() or d.is_symlink() or (
                    alias is not None and (alias.exists() or alias.is_symlink())
                )
                if not present:
                    issues.append(f"missing {exp.name}/{sub}")
                    if not dry_run:
                        d.mkdir(parents=True, exist_ok=True)
                        actions.append(f"recreated {exp.name}/{sub}")

    # 6. Regenerate derived artifacts
    if not dry_run and (issues or True):
        try:
            _update_manifest(root)
            actions.append("regenerated manifest.json")
        except Exception as e:
            actions.append(f"manifest regen failed: {e}")
        try:
            _update_workflow_mermaid(root)
            actions.append("regenerated workflow.mermaid")
        except Exception as e:
            actions.append(f"mermaid regen failed: {e}")

    # 7. Stale path entries in state
    try:
        state = load_state(root)
        stale: list[str] = []
        for pid, info in list(state.get("paths", {}).items()):
            if pid == "main":
                continue
            exp_dir = root / "workspace" / pid
            if not exp_dir.exists():
                stale.append(pid)
        if stale:
            issues.append(f"state lists missing experiment paths: {stale}")
            if not dry_run:
                for pid in stale:
                    state["paths"][pid]["status"] = "missing_on_disk"
                save_state(root, state)
                actions.append(f"marked {len(stale)} stale paths as missing_on_disk")
    except Exception as e:
        actions.append(f"could not audit state.paths: {e}")

    # 8. Checkpoint integrity. An interrupted snapshot leaves a checkpoint
    #    directory with no checkpoint_manifest.json (and/or a .incomplete
    #    sentinel) — invisible to rollback, _prune_old_checkpoints, and
    #    list_checkpoints' usable set. Quarantine (never delete — honour the
    #    repair invariant) by renaming to <id>.incomplete so it drops out of
    #    every checkpoint lister and stops accumulating.
    checkpoints_dir = root / ".os_state" / "checkpoints"
    if checkpoints_dir.exists():
        try:
            for d in sorted(checkpoints_dir.iterdir()):
                if not d.is_dir():
                    continue
                if d.name.endswith(".incomplete"):
                    continue  # already quarantined
                manifest = d / "checkpoint_manifest.json"
                interrupted = (d / ".incomplete").exists() or not manifest.exists()
                if not interrupted:
                    continue
                issues.append(f"incomplete checkpoint (no manifest): {d.name}")
                if not dry_run:
                    quarantine = d.with_name(f"{d.name}.incomplete")
                    try:
                        if quarantine.exists():
                            # Disambiguate a name collision; never overwrite.
                            quarantine = d.with_name(
                                f"{d.name}.incomplete_{_now().replace(':', '').replace('-', '')}"
                            )
                        d.rename(quarantine)
                        actions.append(
                            f"quarantined incomplete checkpoint {d.name} → "
                            f"{quarantine.name}"
                        )
                    except OSError as e:
                        actions.append(
                            f"could not quarantine checkpoint {d.name}: {e}"
                        )
        except OSError as e:
            actions.append(f"could not audit checkpoints: {e}")

    return {
        "status": "success",
        "dry_run": dry_run,
        "issues_detected": len(issues),
        "issues": issues,
        "actions_taken": actions,
        "message": (
            "Workspace healthy." if not issues
            else f"Repaired {len(actions)} issue(s)." if not dry_run
            else f"Detected {len(issues)} issue(s); rerun with dry_run=false to fix."
        ),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
