"""Scratch sandbox — workspace/scratch/ for quick AI experiments.

The AI should NOT pollute numbered experiment folders with one-off tests
(quick syntax checks, library smoke tests, parameter sweeps). The scratch
sandbox is a free-for-all: created on demand, contents are gitignored,
and anything important moves OUT of scratch into a proper step.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.scratch")


_LANG_RUNNERS: dict[str, list[str]] = {
    ".py": [sys.executable],
    ".R":  ["Rscript"],
    ".jl": ["julia"],
    ".sh": ["/bin/bash", "-e"],
}


def _scratch_dir(root: Path) -> Path:
    d = root / "workspace" / "scratch"
    d.mkdir(parents=True, exist_ok=True)
    # gitignore the scratch contents (not the folder itself)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n!.gitignore\n!README.md\n")
    readme = d / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Scratch\n\n"
            "AI sandbox for quick tests. Contents are gitignored.\n"
            "Anything important MUST be moved to a proper experiment folder "
            "(`sys_path(operation='create')`) before it counts as research.\n"
        )
    return d


def scratch_write(filename: str, content: str, root: Path) -> dict[str, Any]:
    """Write a file into workspace/scratch/ (no provenance, no immutability)."""
    try:
        d = _scratch_dir(root)
        # Reject path-traversal attempts.
        if "/" in filename or ".." in filename:
            return {
                "status": "error",
                "message": "Scratch filenames may not contain '/' or '..'.",
            }
        target = d / filename
        target.write_text(content)
        return {
            "status": "success",
            "path": str(target.relative_to(root)),
            "message": f"Wrote {len(content)} chars to scratch/{filename}.",
        }
    except Exception as e:
        logger.exception("scratch_write failed")
        return {"status": "error", "message": str(e)}


def scratch_run(filename: str, root: Path, *, timeout: int = 60) -> dict[str, Any]:
    """Execute a script in workspace/scratch/. Language inferred from extension."""
    try:
        d = _scratch_dir(root)
        target = d / filename
        if not target.exists() or not target.is_file():
            return {"status": "error", "message": f"scratch/{filename} not found"}
        ext = target.suffix.lower()
        runner = _LANG_RUNNERS.get(ext)
        if not runner:
            return {
                "status": "error",
                "message": f"No runner for {ext}. Allowed: {sorted(_LANG_RUNNERS)}",
            }
        if runner[0] != sys.executable and not shutil.which(runner[0]):
            return {
                "status": "error",
                "message": f"{runner[0]} not on PATH — install it first.",
            }
        cmd = runner + [str(target)]
        t0 = time.time()
        try:
            res = subprocess.run(
                cmd, cwd=str(d), capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"Scratch run timed out after {timeout}s"}
        elapsed = time.time() - t0
        return {
            "status": "success",
            "exit_code": res.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "stdout": res.stdout[-2000:],
            "stderr": res.stderr[-2000:],
        }
    except Exception as e:
        logger.exception("scratch_run failed")
        return {"status": "error", "message": str(e)}


_PRESERVED = {".gitignore", ".gitkeep", "README.md"}


def scratch_list(root: Path) -> dict[str, Any]:
    """List files currently in scratch (excludes scaffold/preserved files)."""
    try:
        d = _scratch_dir(root)
        entries = [
            {
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
            for f in d.iterdir()
            if f.is_file() and f.name not in _PRESERVED
        ]
        files = sorted(entries, key=lambda x: x["modified"])
        return {"status": "success", "count": len(files), "files": files}
    except Exception as e:
        logger.exception("scratch_list failed")
        return {"status": "error", "message": str(e)}


def scratch_clear(root: Path) -> dict[str, Any]:
    """Wipe scratch contents (keeps .gitignore, .gitkeep, README)."""
    try:
        d = _scratch_dir(root)
        removed = 0
        for f in d.iterdir():
            if f.name in _PRESERVED:
                continue
            if f.is_file():
                f.unlink()
                removed += 1
            elif f.is_dir():
                shutil.rmtree(f, ignore_errors=True)
                removed += 1
        return {"status": "success", "removed": removed}
    except Exception as e:
        logger.exception("scratch_clear failed")
        return {"status": "error", "message": str(e)}
