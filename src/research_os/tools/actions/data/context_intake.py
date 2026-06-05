"""Mid-flow context injection — researcher drops new files during any step.

Use case: the researcher's PI hands them a new paper midway through analysis.
They drop it into a folder (anywhere inside the project, even a `dropbox/`
pile) and tell the AI "there's new context, integrate it". This tool:

1. Discovers files that look new (mtime > last_seen, or absent from manifest).
2. Auto-routes each to the right inputs/ subfolder:
     PDFs → inputs/literature/
     CSV/Parquet/etc. → inputs/raw_data/
     .md/.txt/.rst → inputs/context/
     Everything else → inputs/context/ with a warning.
3. Records the integration in workspace/analysis.md + .os_state/context_intake_log.jsonl
4. Tells the AI to re-run tool_intake_autofill if the new files might change
   the research question or hypotheses.

NEVER deletes / overwrites. Conflicts get renamed `_imported_N`.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.data.context_intake")


_ROUTING = {
    "literature": {".pdf", ".epub", ".djvu", ".ps"},
    "raw_data": {
        ".csv", ".tsv", ".parquet", ".feather", ".arrow",
        ".xlsx", ".xls", ".sas7bdat", ".sav", ".dta",
        ".fasta", ".fastq", ".bam", ".vcf", ".gtf", ".gff",
        ".nii", ".dcm", ".h5", ".hdf5", ".json", ".jsonl",
        ".tiff", ".tif", ".png", ".jpg", ".jpeg",
        ".shp", ".geojson", ".nc", ".npy", ".npz", ".pkl",
    },
    "context": {".md", ".txt", ".rst", ".org", ".odt", ".docx", ".rtf"},
}

# Files written by ``research-os init`` (and ``_setup_mcp_configs``) at the
# project root. These are scaffold, not researcher input; if context_intake
# scoops them into ``inputs/`` it will (a) re-trigger intake autofill noise
# and (b) confuse the AI when ``AGENTS.md`` shows up as "new literature".
_SCAFFOLD_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GETTING_STARTED.md",
    "README.md",
    # STATE.md is the canonical project-status file written by
    # save_state at PROJECT ROOT. context_intake must never scoop it
    # into inputs/ — it's not researcher input, it's the AI's status
    # board.
    "STATE.md",
    "CONTRIBUTORS.md",
    "opencode.json",
    "mcp_config.json",
    ".aider.conf.yml",
    ".windsurfrules",
    ".continuerules",
    ".cursorrules",
}

# Top-level directories the scaffold owns or that we never want to scan
# for "new" researcher files. Includes the obvious project bookkeeping
# folders plus common conda/git/IDE noise.
_EXCLUDED_DIRS = {
    "inputs", "workspace", "synthesis", "docs", "environment", ".os_state",
    "scripts",  # project-owned share-archive + GitHub-init scripts
    "tests",    # researcher's pytest suite, not "incoming context"
    "node_modules", "__pycache__", "venv", ".venv", "env",
    "dist", "build", ".pytest_cache", ".ruff_cache", ".mypy_cache",
}


def _route(suffix: str) -> str:
    suffix = suffix.lower()
    for target, exts in _ROUTING.items():
        if suffix in exts:
            return target
    return "context"  # default


def _log_path(root: Path) -> Path:
    return root / ".os_state" / "context_intake_log.jsonl"


def _previously_seen(root: Path) -> set[str]:
    log = _log_path(root)
    if not log.exists():
        return set()
    seen: set[str] = set()
    try:
        for line in log.read_text().splitlines():
            try:
                entry = json.loads(line)
                seen.add(entry.get("imported_as", ""))
            except Exception:
                continue
    except Exception:
        pass
    return seen


def context_intake(
    root: Path, *, source_dir: str | None = None,
    dry_run: bool = False, also_autofill: bool = False,
) -> dict[str, Any]:
    """Detect new files anywhere in the project and route them into inputs/."""
    try:
        from research_os.project_ops import now_iso

        # Where to look:
        candidates: list[Path] = []
        if source_dir:
            base = root / source_dir
            if not base.exists():
                return {"status": "error", "message": f"source_dir {source_dir} not found"}
            candidates.extend(p for p in base.rglob("*") if p.is_file())
        else:
            # Scan dirs the researcher would plausibly drop files into.
            # Skip excluded dirs, hidden dirs, and any top-level scaffold
            # file (AGENTS.md, CLAUDE.md, etc.).
            for child in root.iterdir():
                if child.is_dir() and (
                    child.name in _EXCLUDED_DIRS or child.name.startswith(".")
                ):
                    continue
                if child.is_dir():
                    candidates.extend(p for p in child.rglob("*") if p.is_file())
                elif (
                    child.is_file()
                    and not child.name.startswith(".")
                    and child.name not in _SCAFFOLD_NAMES
                ):
                    candidates.append(child)

        # Filter to candidates that look genuinely new.
        seen = _previously_seen(root)
        new_files: list[Path] = []
        for c in candidates:
            # Skip things already inside inputs/ — they're not "new".
            try:
                c.relative_to(root / "inputs")
                continue
            except ValueError:
                pass
            # Skip files we've already routed before.
            inputs_target = _route(c.suffix) + "/" + c.name
            if inputs_target in seen:
                continue
            new_files.append(c)

        if not new_files:
            return {
                "status": "success",
                "new_files_count": 0,
                "imported": [],
                "message": "No new context files detected.",
            }

        # Route each. Never overwrite.
        imported: list[dict[str, Any]] = []
        log_entries: list[dict[str, Any]] = []
        for src in new_files:
            target_subdir = _route(src.suffix)
            target_dir = root / "inputs" / target_subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / src.name
            if dest.exists():
                # Rename to avoid clobber.
                stem, suf = dest.stem, dest.suffix
                i = 1
                while (target_dir / f"{stem}_imported_{i}{suf}").exists():
                    i += 1
                dest = target_dir / f"{stem}_imported_{i}{suf}"

            entry = {
                "timestamp": now_iso(),
                "src": str(src.relative_to(root)) if src.is_relative_to(root) else str(src),
                "imported_as": f"{target_subdir}/{dest.name}",
                "size_bytes": src.stat().st_size,
                "routing_reason": f"ext={src.suffix.lower()}",
            }
            if not dry_run:
                try:
                    shutil.copy2(src, dest)
                    log_entries.append(entry)
                    imported.append(entry)
                except Exception as e:
                    entry["error"] = str(e)
                    imported.append(entry)

        # Append to the log
        if not dry_run and log_entries:
            log = _log_path(root)
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a") as f:
                for entry in log_entries:
                    f.write(json.dumps(entry) + "\n")

            # Mirror to workspace/analysis.md so it shows up in the narrative.
            analysis = root / "workspace" / "analysis.md"
            analysis.parent.mkdir(parents=True, exist_ok=True)
            with open(analysis, "a") as f:
                f.write(
                    f"\n[{now_iso()}] **Context injected** "
                    f"{len(log_entries)} new file(s):\n"
                )
                for e in log_entries:
                    f.write(f"  - `{e['src']}` → `inputs/{e['imported_as']}`\n")

        # Optionally re-run autofill so the AI's view stays current.
        autofill_summary = None
        if also_autofill and not dry_run:
            from research_os.tools.actions.data.intake import intake_autofill

            autofill_summary = intake_autofill(root)

        return {
            "status": "success",
            "dry_run": dry_run,
            "new_files_count": len(new_files),
            "imported": imported,
            "log_path": str(_log_path(root).relative_to(root)),
            "autofill_result": autofill_summary,
            "next_action": (
                "Review the imported files; if the research question or "
                "hypotheses might change, call `tool_intake_autofill` "
                "(or call this tool again with `also_autofill=true`)."
            ),
        }
    except Exception as e:
        logger.exception("context_intake failed")
        return {"status": "error", "message": str(e)}
