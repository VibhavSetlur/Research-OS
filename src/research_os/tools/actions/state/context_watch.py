"""Live context drop-zone detection.

``inputs/context/`` (and each step's ``context/``) is a free drop-zone:
the researcher can drop a paper, a screenshot, a txt note, a PI email —
anything — at ANY point, even mid-session, then say "I put something in
context". The AI must notice and read it.

``detect_new_context`` compares the current context files against a
small marker (``.os_state/context_seen.json``) and reports what's NEW or
CHANGED since the last turn. sys_boot peeks (``update_marker=False``);
tool_route consumes (``update_marker=True``) so each drop is surfaced
once, on the next prompt after it lands.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.context_watch")

_MARKER = ".os_state/context_seen.json"
_MAX_REPORT = 12


def _context_dirs(root: Path) -> list[Path]:
    dirs = [root / "inputs" / "context"]
    ws = root / "workspace"
    if ws.exists():
        for d in sorted(ws.iterdir()):
            c = d / "context"
            if c.is_dir():
                dirs.append(c)
    return dirs


def _snapshot(root: Path) -> dict[str, list[int]]:
    """Map rel-path → [size, mtime] for every researcher-dropped context
    file (skips our auto-seed READMEs and dotfiles)."""
    out: dict[str, list[int]] = {}
    for base in _context_dirs(root):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.name == "README.md" or p.name.startswith("."):
                continue
            try:
                st = p.stat()
                rel = str(p.relative_to(root))
            except (OSError, ValueError):
                continue
            out[rel] = [int(st.st_size), int(st.st_mtime)]
    return out


def detect_new_context(root: Path, *, update_marker: bool = True) -> dict[str, Any]:
    """Report context files added / changed since the last seen snapshot.

    Returns ``{new_files, changed_files, hint, first_scan}``. On the very
    first scan (no marker yet) it establishes a baseline and reports
    nothing — the initial briefing docs are handled by intake, not flagged
    as a surprise drop.
    """
    root = Path(root)
    current = _snapshot(root)
    marker = root / _MARKER
    first = not marker.exists()
    prior: dict[str, list[int]] = {}
    if not first:
        try:
            loaded = json.loads(marker.read_text())
            if isinstance(loaded, dict):
                prior = loaded
        except (OSError, ValueError):
            prior = {}

    new_files: list[str] = []
    changed_files: list[str] = []
    if not first:
        for rel, sig in sorted(current.items()):
            if rel not in prior:
                new_files.append(rel)
            elif prior[rel] != sig:
                changed_files.append(rel)

    if update_marker:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps(current, sort_keys=True) + "\n")
        except OSError as e:
            logger.debug("context marker write skipped: %s", e)

    hint = ""
    if new_files or changed_files:
        shown = (new_files + changed_files)[:_MAX_REPORT]
        hint = (
            f"{len(new_files)} new + {len(changed_files)} changed file(s) in "
            "context/ since last turn — the researcher dropped material for "
            "you. READ them (sys_file_read) before proceeding and fold "
            "anything relevant into the current step's plan / analysis: "
            + ", ".join(shown)
        )
    return {
        "new_files": new_files,
        "changed_files": changed_files,
        "hint": hint,
        "first_scan": first,
    }


def glossary_unfilled(root: Path) -> bool:
    """True if docs/glossary.md exists but has no data rows (header only).

    The reaction-similarity project shipped an empty glossary; this lets
    sys_boot nudge the AI to populate domain terms it encounters.
    """
    g = Path(root) / "docs" / "glossary.md"
    if not g.exists():
        return False
    try:
        txt = g.read_text()
    except OSError:
        return False
    rows = [ln for ln in txt.splitlines() if ln.strip().startswith("|")]
    # header row + separator row = 2; any real term adds a 3rd.
    return len(rows) <= 2
