"""Chaos → Research-OS migration — audit an existing messy project and move
it into RO format SAFELY, without breaking it.

docs/MIGRATION.md.

Researchers don't start clean. They arrive with a folder that grew organically:
``data.csv``, ``final_v2.py``, ``Untitled3.ipynb``, ``notes.txt``, a ``figs/``
dir, three README variants. RO's value proposition is "we order the chaos" — so
there must be a first-class, SAFE path from that chaos into the RO contract.

This module is the engine. It does three things, each a pure-ish, fail-safe
step the AI/daemon drives:

  1. ``audit_chaos(src)``     — classify every file (data / code / notebook /
                                doc / figure / env / junk) and report what's
                                there, WITHOUT touching anything. Read-only.
  2. ``plan_migration(...)``  — propose a mapping from each source file to its
                                RO home (inputs/raw_data, workspace steps,
                                docs, environment, …). A plan, not an action.
  3. ``apply_migration(...)`` — execute the plan. COPY by default (never move,
                                never delete the source) so the original is
                                always intact; verify every copy by size; emit
                                a manifest of what moved where.

Safety invariants (non-negotiable — this is someone's real research):
  * Never delete or overwrite a source file. Copy into a NEW RO root.
  * Never clobber an existing destination (skip + report collisions).
  * Every applied copy is verified (exists + size matches) or rolled into the
    failures list — a half-migrated project is reported, never silently wrong.
  * Dry-run is the default contract for plan; apply requires an explicit call.

stdlib only. Pure classification + a guarded copy. Trivially testable.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

# Extension → RO category. The category decides the destination home. Unknown
# extensions fall to "other" (staged under inputs/context for the researcher
# to triage — never dropped).
_DATA_EXT = {
    ".csv", ".tsv", ".parquet", ".feather", ".json", ".jsonl", ".xlsx",
    ".xls", ".h5", ".hdf5", ".nc", ".fasta", ".fastq", ".fa", ".fq",
    ".vcf", ".bam", ".sam", ".bed", ".gff", ".gtf", ".npy", ".npz", ".pkl",
    ".db", ".sqlite", ".dta", ".sav", ".rds",
}
_CODE_EXT = {
    ".py", ".r", ".jl", ".sh", ".bash", ".sql", ".cpp", ".c", ".rs",
    ".go", ".java", ".scala", ".m", ".do", ".pl",
}
_NOTEBOOK_EXT = {".ipynb", ".rmd", ".qmd"}
_DOC_EXT = {".md", ".txt", ".pdf", ".docx", ".doc", ".rst", ".org", ".tex"}
_FIGURE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".tiff", ".pdf"}
_ENV_NAMES = {
    "requirements.txt", "environment.yml", "environment.yaml", "pyproject.toml",
    "setup.py", "setup.cfg", "poetry.lock", "pipfile", "pipfile.lock",
    "renv.lock", "conda.yaml", "dockerfile", "makefile",
}
# Things we deliberately do NOT migrate (noise / VCS / caches).
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".ipynb_checkpoints", ".venv",
    "venv", "node_modules", ".mypy_cache", ".pytest_cache", ".os_state",
    ".DS_Store", ".idea", ".vscode",
}
_SKIP_FILES = {".ds_store", "thumbs.db"}


def _category(path: Path) -> str:
    """Classify a single file into an RO category."""
    name = path.name.lower()
    if name in _ENV_NAMES:
        return "environment"
    suffix = path.suffix.lower()
    if suffix in _NOTEBOOK_EXT:
        return "notebook"
    if suffix in _DATA_EXT:
        return "data"
    if suffix in _CODE_EXT:
        return "code"
    # A figure-capable extension that is ALSO a doc (pdf) → treat as doc only
    # when it reads like a paper; otherwise figure. We can't open it here, so
    # pdf is classified as doc (the safer home; the researcher can move a
    # figure pdf later). Pure image extensions → figure.
    if suffix in _FIGURE_EXT and suffix != ".pdf":
        return "figure"
    if suffix in _DOC_EXT:
        return "doc"
    return "other"


# Category → RO destination (relative to the new RO root). "other" lands in
# inputs/context so nothing is lost; the researcher triages from there.
_CATEGORY_HOME = {
    "data": "inputs/raw_data",
    "code": "inputs/context/legacy_code",
    "notebook": "inputs/context/legacy_notebooks",
    "doc": "inputs/literature",
    "figure": "inputs/context/legacy_figures",
    "environment": "environment",
    "other": "inputs/context",
}


def _iter_files(src: Path):
    """Walk ``src`` yielding files, skipping VCS/cache/noise dirs."""
    for p in sorted(src.rglob("*")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.name.lower() in _SKIP_FILES:
            continue
        yield p


def audit_chaos(src: str | Path) -> dict[str, Any]:
    """Read-only classification of an existing messy project directory.

    Returns counts per category, total bytes, and a per-file listing with its
    classified category + proposed RO home. Touches NOTHING. This is what the
    AI shows the researcher before any migration: "here's what you have, and
    here's where each piece would go."
    """
    src = Path(src)
    if not src.exists() or not src.is_dir():
        return {"status": "error", "message": f"not a directory: {src}"}
    files: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    total_bytes = 0
    for p in _iter_files(src):
        cat = _category(p)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        total_bytes += size
        counts[cat] = counts.get(cat, 0) + 1
        rel = p.relative_to(src)
        files.append({
            "source": str(rel),
            "category": cat,
            "size_bytes": size,
            "ro_home": _CATEGORY_HOME.get(cat, "inputs/context"),
        })
    return {
        "status": "success",
        "source": str(src),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "by_category": counts,
        "files": files,
        "note": (
            "Read-only audit. Nothing moved. Run plan_migration to see the "
            "exact destination map, then apply_migration to copy into an RO "
            "project (your original is never touched)."
        ),
    }


def plan_migration(src: str | Path, dest: str | Path) -> dict[str, Any]:
    """Propose a source→destination copy map into a (new) RO root at ``dest``.

    Does not copy. Flags any destination collision (a file already at the RO
    path) so apply can skip it safely. The AI reviews + confirms this plan
    with the researcher before applying.
    """
    audit = audit_chaos(src)
    if audit.get("status") != "success":
        return audit
    dest = Path(dest)
    moves: list[dict[str, Any]] = []
    collisions = 0
    for entry in audit["files"]:
        rel_src = Path(entry["source"])
        # Preserve the original filename; flatten into the category home but
        # keep a subpath hint when the source was nested, to avoid name clashes.
        home = Path(entry["ro_home"])
        # Keep the leaf name; if the file was nested, prefix the parent dir so
        # two data.csv files in different folders don't collide.
        if len(rel_src.parts) > 1:
            target_name = f"{rel_src.parts[-2]}__{rel_src.name}"
        else:
            target_name = rel_src.name
        target = home / target_name
        dest_path = dest / target
        collision = dest_path.exists()
        if collision:
            collisions += 1
        moves.append({
            "source": entry["source"],
            "target": str(target),
            "category": entry["category"],
            "size_bytes": entry["size_bytes"],
            "collision": collision,
        })
    return {
        "status": "success",
        "source": str(Path(src)),
        "dest": str(dest),
        "move_count": len(moves),
        "collisions": collisions,
        "moves": moves,
        "note": (
            "Plan only — nothing copied yet. apply_migration COPIES (never "
            "moves/deletes the source); collisions are skipped, not "
            "overwritten."
        ),
    }


def _sha256(path: Path, limit: int = 64 * 1024 * 1024) -> str | None:
    """Hash up to ``limit`` bytes of a file for copy verification (best-effort)."""
    try:
        h = hashlib.sha256()
        read = 0
        with open(path, "rb") as fh:
            while read < limit:
                chunk = fh.read(min(1024 * 1024, limit - read))
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
        return h.hexdigest()
    except OSError:
        return None


def apply_migration(
    src: str | Path,
    dest: str | Path,
    *,
    verify: bool = True,
) -> dict[str, Any]:
    """Execute the migration plan: COPY each source file to its RO home.

    SAFETY: copies only — the source is never moved or deleted; an existing
    destination is skipped (never overwritten); each copy is verified (size,
    and sha256 of a bounded prefix when ``verify``). Writes a
    ``migration_manifest.json`` under ``dest/.os_state/`` recording every
    copy + skip + failure, so the migration itself is auditable. Returns the
    same summary.
    """
    import json
    import time

    plan = plan_migration(src, dest)
    if plan.get("status") != "success":
        return plan
    src = Path(src)
    dest = Path(dest)
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for move in plan["moves"]:
        s = src / move["source"]
        d = dest / move["target"]
        if d.exists():
            skipped.append({"target": move["target"], "reason": "collision"})
            continue
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            ok = d.exists() and d.stat().st_size == s.stat().st_size
            if ok and verify and s.stat().st_size <= 64 * 1024 * 1024:
                ok = _sha256(s) == _sha256(d)
            if ok:
                copied.append({"source": move["source"], "target": move["target"]})
            else:
                failures.append({"target": move["target"], "reason": "verify_failed"})
        except OSError as exc:
            failures.append({"target": move["target"], "reason": str(exc)})

    manifest = {
        "schema": 1,
        "migrated_at": time.time(),
        "source": str(src),
        "dest": str(dest),
        "copied": len(copied),
        "skipped": len(skipped),
        "failures": len(failures),
        "copied_files": copied,
        "skipped_files": skipped,
        "failed_files": failures,
    }
    try:
        mdir = dest / ".os_state"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "migration_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass

    return {
        "status": "success" if not failures else "partial",
        "source": str(src),
        "dest": str(dest),
        "copied": len(copied),
        "skipped": len(skipped),
        "failures": len(failures),
        "manifest": str(dest / ".os_state" / "migration_manifest.json"),
        "note": (
            "Source left fully intact (copy-only). "
            + (
                f"{len(failures)} file(s) failed verification — see manifest."
                if failures else
                "All copies verified. Run the workspace audit next to confirm "
                "the RO structure is sound."
            )
        ),
    }
