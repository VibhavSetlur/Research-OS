"""Artifact detection — closing the provenance loop (Phase 1.8).

JUDGE-3 (docs/ROADMAP.md §8): provenance records inputs → command →
env. The other half is *outputs* — what the run actually produced. This
module fingerprints a run's working directory before and after execution
and reports the files that were created or modified as artifacts, each
with size + sha256 + mtime, so a run becomes a complete, reproducible
record: inputs ⇒ code@commit ⇒ outputs.

Design constraints (all best-effort, never blocks or fails a run):

* Snapshot is a flat ``{relpath: (mtime, size)}`` map, cheap to take.
* The diff records files whose (mtime, size) changed or that are new.
* Bounded: ``max_artifacts`` caps the count; files larger than
  ``max_hash_bytes`` are listed but not hashed (hash=None).
* Ignored: VCS/cache/dependency dirs that are never research outputs.
* Pure stdlib, import-cheap; no dependency on the rest of the daemon.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

# Directory names that never contain research artifacts worth tracking.
DEFAULT_IGNORE_DIRS = frozenset({
    ".git",
    ".hg",
    ".svn",
    ".os_state",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".ipynb_checkpoints",
    ".conda",
})

# 100 MB: above this we record the artifact but skip the hash (cost).
DEFAULT_MAX_HASH_BYTES = 100 * 1024 * 1024
# Cap how many artifacts we record so a run that writes thousands of tiny
# files (e.g. a checkpoint dir) can't blow up the manifest.
DEFAULT_MAX_ARTIFACTS = 500


def _iter_files(root: Path, ignore_dirs: frozenset[str]):
    """Yield (relpath_str, abspath) for every file under root, pruning
    ignored directories. Symlinks are not followed (avoid cycles / escapes)."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune ignored dirs in place so os.walk doesn't descend into them.
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for fname in filenames:
            ap = Path(dirpath) / fname
            try:
                rel = ap.relative_to(root)
            except ValueError:
                continue
            yield str(rel), ap


def snapshot(
    root: str | os.PathLike,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
) -> dict[str, tuple[float, int]]:
    """Fingerprint a directory tree: ``{relpath: (mtime, size)}``.

    Cheap (stat-only, no hashing). Returns an empty dict if root is missing
    or unreadable — callers treat that as "nothing to diff against."
    """
    out: dict[str, tuple[float, int]] = {}
    try:
        base = Path(root)
        if not base.is_dir():
            return out
        for rel, ap in _iter_files(base, ignore_dirs):
            try:
                st = ap.stat()
                out[rel] = (st.st_mtime, st.st_size)
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - snapshot must never raise
        return out
    return out


def _hash_file(path: Path, max_bytes: int) -> str | None:
    """sha256 of a file, or None if too large / unreadable."""
    try:
        if path.stat().st_size > max_bytes:
            return None
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    except OSError:
        return None


def diff(
    root: str | os.PathLike,
    before: dict[str, tuple[float, int]],
    *,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
    max_artifacts: int = DEFAULT_MAX_ARTIFACTS,
    max_hash_bytes: int = DEFAULT_MAX_HASH_BYTES,
) -> dict:
    """Diff the current state of ``root`` against a ``before`` snapshot.

    Returns ``{"artifacts": [...], "truncated": bool}`` where each artifact
    is ``{path, change, size, mtime, sha256}`` with ``change`` ∈ {created,
    modified}. Files unchanged since the snapshot are omitted. Never raises.
    """
    artifacts: list[dict] = []
    truncated = False
    try:
        base = Path(root)
        if not base.is_dir():
            return {"artifacts": [], "truncated": False}
        after = snapshot(base, ignore_dirs)
        # Stable, deterministic order: created/modified first by path.
        changed: list[tuple[str, str, tuple[float, int]]] = []
        for rel, fp in after.items():
            prev = before.get(rel)
            if prev is None:
                changed.append((rel, "created", fp))
            elif prev != fp:
                changed.append((rel, "modified", fp))
        changed.sort(key=lambda x: x[0])
        for rel, change, (mtime, size) in changed:
            if len(artifacts) >= max_artifacts:
                truncated = True
                break
            ap = base / rel
            artifacts.append({
                "path": rel,
                "change": change,
                "size": size,
                "mtime": mtime,
                "sha256": _hash_file(ap, max_hash_bytes),
            })
    except Exception:  # noqa: BLE001 - diff must never break a run
        return {"artifacts": artifacts, "truncated": truncated}
    return {"artifacts": artifacts, "truncated": truncated}
