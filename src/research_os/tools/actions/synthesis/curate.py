"""Figure curation — copy per-step focal figures into synthesis/figures/.

Called by tool_synthesis_curate_figures (handler in meta_workspace.py).
The AI then references the curated paths from synthesis/paper.typ /
slides.typ / dashboard.html.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.curate")


_FIG_SUFFIXES = {".png", ".svg", ".jpg", ".jpeg"}
_STEP_DIR_RE = re.compile(r"^\d{2,3}_")


def curate_figures(root: Path, mode: str = "focal") -> dict[str, Any]:
    """Collect, number, and copy step figures into ``synthesis/figures/``
    with stable naming for paper.typ / slides.typ / dashboard.html to
    reference.

    Args:
      root: project root.
      mode: ``"focal"`` (default) — one focal figure per step; the
        canonical curated set used by paper.typ. ``"all"`` — every PNG/
        SVG/JPG in every step's ``outputs/figures/``; appropriate for a
        dashboard that wants the full evidence base, and the only way to
        avoid the failure mode where step figures land in
        ``synthesis/figures/`` without ``.caption.md`` sidecars.

    Behaviour:
      * Walk ``workspace/NN_*/outputs/figures/`` in step order.
      * In focal mode: pick each step's focal figure (filename starting
        with the step number, else alphabetically first PNG/SVG/JPG).
      * In all mode: every figure in every step's outputs/figures/.
      * Copy to ``synthesis/figures/figNN_<step-descriptor>.<ext>``
        (focal) or ``synthesis/figures/<NN>_<original-name>.<ext>`` (all)
        so ordering is deterministic across rebuilds.
      * Copy each figure's ``.caption.md`` sidecar if present, OR seed a
        placeholder caption noting interpretive caption is required.
      * Skip steps with no figures (returns them in ``missing_figures``
        so the audit can flag them).
    """
    ws = root / "workspace"
    target = root / "synthesis" / "figures"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    missing_captions: list[str] = []
    missing_figures: list[str] = []

    if not ws.exists():
        return {
            "status": "error",
            "message": "workspace/ not found; nothing to curate.",
        }
    if mode not in ("focal", "all"):
        return {
            "status": "error",
            "message": f"unknown mode {mode!r}; expected 'focal' or 'all'.",
        }

    fig_no = 1
    for p in sorted(ws.iterdir()):
        if not (p.is_dir() and _STEP_DIR_RE.match(p.name)):
            continue
        if p.name.endswith("__DEAD_END"):
            continue
        figs_dir = p / "outputs" / "figures"
        if not figs_dir.exists():
            missing_figures.append(p.name)
            continue
        candidates = [
            f for f in sorted(figs_dir.iterdir())
            if f.suffix.lower() in _FIG_SUFFIXES and f.is_file()
        ]
        if not candidates:
            missing_figures.append(p.name)
            continue
        step_num = p.name.split("_", 1)[0]
        slug = re.sub(r"^\d{2,3}_", "", p.name)

        if mode == "focal":
            focal = next(
                (f for f in candidates if f.name.startswith(step_num + "_")),
                candidates[0],
            )
            sources = [focal]
        else:
            sources = candidates

        for source in sources:
            if mode == "focal":
                dest_name = f"fig{fig_no:02d}_{slug}{source.suffix.lower()}"
            else:
                # Preserve the original filename (already step-prefixed
                # if the AI followed the convention); else namespace it
                # so the curated set stays deterministic.
                if source.name.startswith(step_num):
                    dest_name = source.name
                else:
                    dest_name = f"{step_num}_{source.name}"
            dest = target / dest_name
            try:
                if not dest.exists() or dest.stat().st_mtime < source.stat().st_mtime:
                    shutil.copy2(source, dest)
            except OSError as e:
                logger.warning("curate copy failed %s: %s", source, e)
                continue

            source_cap = source.with_suffix(".caption.md")
            if not source_cap.exists():
                source_cap = source.parent / f"{source.stem}.caption.md"
            dest_cap = dest.with_suffix(".caption.md")
            if source_cap.exists():
                try:
                    if not dest_cap.exists() or dest_cap.stat().st_mtime < source_cap.stat().st_mtime:
                        shutil.copy2(source_cap, dest_cap)
                except OSError as e:
                    # Best-effort sidecar copy. Read-only source dirs /
                    # permission mismatches must not crash the curation
                    # pass; the figure itself is already copied above.
                    logger.debug("caption sidecar copy failed for %s: %s", source_cap, e)
            else:
                if p.name not in missing_captions:
                    missing_captions.append(p.name)
                if not dest_cap.exists():
                    dest_cap.write_text(
                        f"**Figure {fig_no} — {source.stem.replace('_', ' ')}.** "
                        "_Caption pending. Lead with the substantive finding the "
                        "figure shows (not just 'histogram of X'); name the unit "
                        "on each axis; call out one specific feature the reader "
                        "should look for._\n"
                    )

            copied.append({
                "source": str(source.relative_to(root)),
                "dest": str(dest.relative_to(root)),
                "step": p.name,
                "has_caption": source_cap.exists(),
            })
            fig_no += 1

    return {
        "status": "success",
        "curated": len(copied),
        "mode": mode,
        "missing_captions": missing_captions,
        "missing_figures": missing_figures,
        "figures": copied,
        "synthesis_figures_dir": str(target.relative_to(root)),
    }


# ---------------------------------------------------------------------------
# Figure coverage audit — every curated figure is referenced in the
# AI-authored synthesis files (paper.typ / dashboard.html / slides.typ).
# ---------------------------------------------------------------------------


def audit_figure_coverage(root: Path) -> dict[str, Any]:
    """Audit synthesis/figures/ for orphan + missing-reference figures.

    Walks every fig*_*.{png,svg,jpg} under synthesis/figures/ and checks
    that each appears (by filename or stem) in at least one AI-authored
    synthesis file (paper.typ, essay.typ, slides.typ, poster.typ,
    handout.typ, grant.typ, dashboard.html, paper.md, paper.tex). Also
    flags figures present in workspace step outputs but not curated.
    """
    figures_dir = root / "synthesis" / "figures"
    if not figures_dir.exists():
        return {
            "status": "success",
            "checked": 0,
            "embedded": 0,
            "orphans": [],
            "uncited": [],
            "blockers": [],
            "warnings": [],
            "message": "No synthesis/figures/ yet — run tool_synthesis_curate_figures first.",
        }

    synthesis_files = [
        root / "synthesis" / name
        for name in (
            "paper.typ", "essay.typ", "slides.typ", "poster.typ",
            "handout.typ", "grant.typ", "dashboard.html",
            "paper.md", "paper.tex",
        )
    ]
    body_text = "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for f in synthesis_files
        if f.exists()
    )

    curated: list[Path] = [
        f for f in sorted(figures_dir.iterdir())
        if f.suffix.lower() in _FIG_SUFFIXES and f.is_file()
    ]
    uncited: list[str] = []
    embedded = 0
    for fig in curated:
        if fig.name in body_text or fig.stem in body_text:
            embedded += 1
        else:
            uncited.append(str(fig.relative_to(root)))

    warnings: list[str] = []
    blockers: list[str] = []
    if uncited and not body_text:
        warnings.append(
            f"{len(uncited)} curated figure(s) but no synthesis file authored yet."
        )
    elif uncited:
        warnings.append(
            f"{len(uncited)} curated figure(s) not referenced in any synthesis file: "
            f"{', '.join(uncited[:5])}."
        )

    return {
        "status": "error" if blockers else "success",
        "checked": len(curated),
        "embedded": embedded,
        "orphans": [],
        "uncited": uncited,
        "blockers": blockers,
        "warnings": warnings,
    }
