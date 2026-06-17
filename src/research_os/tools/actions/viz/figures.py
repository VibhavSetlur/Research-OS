"""Figure utilities — palette lookup, caption-sidecar synthesis, quality audit.

Doctrine
--------
Research-OS does NOT generate publication figures for the AI. The
``visualization/figure_guidelines`` protocol tells the AI HOW to think
about figure construction; the AI then writes its own matplotlib /
ggplot2 / plotnine / Altair / Vega-Lite / d3 / plotly script tailored
to its dataset. This module exists only as a thin support layer for
that workflow:

* ``palette_for(kind, n)`` — colour-blind-safe palette lookup the AI's
  script can call (or copy the constants from). Backed by the published
  Okabe-Ito 8-colour set, viridis, and PuOr.
* ``caption_synthesise(...)`` — given an existing technical caption +
  the step's Findings section, produces a competent plain-English
  ``<name>.summary.md`` sidecar starter. The AI usually rewrites this
  in its own voice — the function exists so the sidecar is never
  silently missing.
* ``audit_figure_quality(...)`` — checks an existing figure for DPI,
  dimensions, caption + summary sidecars, SVG companion, plus an
  SVG-text overlap heuristic for the "labels stacked on each other"
  pitfall. Surfaces warnings + blockers consumed by
  ``tool_path_finalize`` / ``tool_audit_step_completeness``.
* ``step_figure_inventory(step_id, root)`` — lists every figure
  produced by a step + its sidecar status. Used by the audit gate.

``figure_create`` / ``tool_figure_create`` and all ``_render_*``
chart-kind dispatchers were removed (they were premade chart code
masquerading as guidance). The AI writes its own plotting code. See
CHANGELOG → migration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.viz")


_FIGURES_CONFIG_DEFAULTS = {
    "svg_allowed": False,
    "summary_sidecar": False,
    "interactive_html_allowed": True,
}


def _load_figures_config(root: Path) -> dict[str, Any]:
    """Read the `figures:` block from `inputs/researcher_config.yaml`.

    Returns the lean defaults (no SVG, no summary sidecar, interactive
    HTML allowed) when the file or block is absent, malformed, or the
    config dir is not under the supplied root. Always returns a dict
    that the figure-audit code can index without raising.
    """
    defaults = dict(_FIGURES_CONFIG_DEFAULTS)
    if not root:
        return defaults
    cfg_path = root / "inputs" / "researcher_config.yaml"
    if not cfg_path.exists():
        return defaults
    try:
        import yaml as _yaml

        data = _yaml.safe_load(cfg_path.read_text()) or {}
    except Exception as e:
        logger.debug("figures config parse skipped: %s", e)
        return defaults
    block = data.get("figures") or {}
    if not isinstance(block, dict):
        return defaults
    for key, val in block.items():
        if key in defaults and isinstance(val, type(defaults[key])):
            defaults[key] = val
    return defaults


# ---------------------------------------------------------------------------
# Palettes — colour-blind safe by default.
# ---------------------------------------------------------------------------

# Okabe-Ito 8-colour palette: distinguishable for all common colour-vision
# deficiencies (CVD). The canonical accessible categorical palette in
# scientific figures.
OKABE_ITO = [
    "#000000",  # black
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
]

# Polished primary/accent pair derived from the dashboard CSS so figures
# share visual identity with the deliverable they ship inside.
ACCENT_PRIMARY = "#2C5282"
ACCENT_GOLD = "#B7791F"
ACCENT_GREEN = "#276749"
ACCENT_RED = "#9B2C2C"


def palette_for(kind: str, n: int = 8) -> list[str]:
    """Return a recommended colour list for ``kind``.

    ``kind`` is one of:

    * ``"qualitative"`` — Okabe-Ito 8 (default; CVD-safe).
    * ``"sequential"``  — viridis sampled at ``n`` evenly-spaced points.
    * ``"diverging"``   — PuOr (purple → orange) sampled at ``n``.
    * ``"accent"``      — the 5 cohesive accent colours that
      ``apply_research_os_style`` actually applies (RO_PALETTE['accent']),
      so a figure coloured by hand matches one styled automatically.
    * ``"diverging_emphasis"`` — RO_PALETTE oxblood/forest delta pair.
    """
    kind = (kind or "qualitative").lower()
    if kind == "qualitative":
        return list((OKABE_ITO * ((n + 7) // 8))[:n])
    if kind in ("accent", "diverging_emphasis"):
        # Single source of truth: the palette apply_research_os_style sets as
        # the matplotlib cycle. Cycle to fill n when more slots are requested.
        from research_os.tools.actions.viz.style import RO_PALETTE

        base = list(RO_PALETTE.get(kind) or RO_PALETTE["accent"])
        if n <= len(base):
            return base[:n]
        return list((base * ((n + len(base) - 1) // len(base)))[:n])
    try:
        import matplotlib  # type: ignore
        import numpy as np  # type: ignore

        cmap_name = {"sequential": "viridis", "diverging": "PuOr"}.get(
            kind, "viridis"
        )
        cmap = matplotlib.colormaps.get(cmap_name)
        rgba = cmap(np.linspace(0.05, 0.95, max(2, n)))
        return [
            "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))
            for r, g, b, _ in rgba
        ]
    except Exception:
        return list((OKABE_ITO * ((n + 7) // 8))[:n])


# ---------------------------------------------------------------------------
# Caption-sidecar synthesis (prose helper, not figure generator).
# ---------------------------------------------------------------------------


def caption_synthesise(
    *,
    figure_path: str,
    root: Path,
    technical_caption: str | None = None,
    findings_context: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a plain-English ``<name>.summary.md`` next to a figure.

    Follows W3C two-part guidance: opener describing the structure +
    1-2 sentences of substance grounded in the step's actual Findings.
    Deliberately heuristic — the AI in the IDE rewrites it; this exists
    so the sidecar is never silently missing.
    """
    p = root / figure_path
    if not p.exists():
        return {"status": "error", "message": f"Figure not found: {figure_path}"}

    summary_path = p.with_suffix(".summary.md")
    if summary_path.exists() and not overwrite:
        return {
            "status": "success",
            "summary_path": str(summary_path.relative_to(root)),
            "already_exists": True,
            "advice": "Pass overwrite=true to replace the existing summary.",
        }

    cap_path = p.with_suffix(".caption.md")
    caption = technical_caption or (
        cap_path.read_text().strip() if cap_path.exists() else ""
    )

    name = p.stem
    descriptor = name.split("_", 1)[1] if "_" in name else name
    descriptor_phrase = descriptor.replace("_", " ")

    if findings_context is None:
        step_dir = p.parent.parent.parent
        conc = step_dir / "conclusions.md"
        if conc.exists():
            import re

            txt = conc.read_text()
            m = re.search(r"##\s*Findings\s*\n(.+?)(?:\n##|\Z)",
                          txt, flags=re.DOTALL | re.IGNORECASE)
            if m:
                findings_context = m.group(1).strip()

    parts: list[str] = []
    parts.append(
        f"**What it shows.** This figure presents the {descriptor_phrase} "
        f"for the analytical step `{p.parent.parent.parent.name}`."
    )
    if caption:
        first_sentence = caption.split(". ")[0].strip().rstrip(".") + "."
        parts.append(f"**How to read it.** {first_sentence}")
    if findings_context:
        bullets = [
            ln.strip().lstrip("-* ").strip()
            for ln in findings_context.splitlines()
            if ln.strip().startswith(("-", "*"))
        ]
        if bullets:
            parts.append(
                "**Why it matters.** " + bullets[0].rstrip(".") + "."
            )
        else:
            import re as _re
            stripped = "\n".join(
                ln for ln in findings_context.splitlines()
                if not ln.lstrip().startswith("|") and ln.strip()
            ).strip()
            if stripped:
                sentences = _re.split(r"(?<=[.!?])\s+(?=[A-Z(`])", stripped)
                first = next(
                    (s.strip() for s in sentences if len(s.strip()) > 20),
                    "",
                )
                if first:
                    parts.append(
                        "**Why it matters.** " + first.rstrip(".") + "."
                    )
    if len(parts) == 1:
        parts.append(
            "**How to read it.** _Plain-language description pending — "
            "add a 1-2 sentence cue here so non-expert readers can follow "
            "the figure without statistical training._"
        )

    summary_path.write_text("\n\n".join(parts) + "\n")
    return {
        "status": "success",
        "summary_path": str(summary_path.relative_to(root)),
        "characters": sum(len(s) for s in parts),
        "used_findings": bool(findings_context),
        "used_caption": bool(caption),
    }


# ---------------------------------------------------------------------------
# Figure-quality audit.
# ---------------------------------------------------------------------------


def _svg_text_diagnostics(svg_text: str) -> dict[str, Any]:
    """Heuristic legibility scan of an SVG: label collisions + default font.

    Returns {collisions, dejavu, n_text}. Best-effort, never raises.
    """
    import re

    texts: list[tuple[float, float, str]] = []
    # Pattern 1: <text x="..." y="...">...</text> (Altair, manual SVG).
    for m in re.finditer(
        r"<text[^>]*?x=\"([\d.\-]+)\"[^>]*?y=\"([\d.\-]+)\"[^>]*?>([^<]{1,40})</text>",
        svg_text,
    ):
        try:
            texts.append((float(m.group(1)), float(m.group(2)), m.group(3).strip()))
        except ValueError:
            continue
    # Pattern 2: matplotlib wraps text in <g transform="translate(X Y)"><text>.
    mpl_pat = re.compile(
        r"<g[^>]*?transform=\"translate\(([\d.\-]+)\s+([\d.\-]+)\)\"[^>]*?>"
        r"\s*(?:<g[^>]*?>\s*)?"
        r"<text[^>]*?>([^<]{1,40})</text>",
        re.DOTALL,
    )
    for m in mpl_pat.finditer(svg_text):
        try:
            texts.append((float(m.group(1)), float(m.group(2)), m.group(3).strip()))
        except ValueError:
            continue
    collisions = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            x1, y1, t1 = texts[i]
            x2, y2, t2 = texts[j]
            if not t1 or not t2:
                continue
            w1 = len(t1) * 5
            w2 = len(t2) * 5
            if abs(x1 - x2) < (w1 + w2) / 2 and abs(y1 - y2) < 8:
                collisions += 1
    # DejaVu is matplotlib's fallback font — its presence as the resolved
    # family reads as "nobody set a publication font".
    dejavu = bool(
        re.search(r"font-family\s*[:=]\s*['\"]?[^;'\"}>]*DejaVu", svg_text, re.I)
    )
    return {"collisions": collisions, "dejavu": dejavu, "n_text": len(texts)}


def audit_figure_quality(
    figure_path: str, root: Path,
) -> dict[str, Any]:
    """Audit an existing figure for publication-grade defaults.

    Checks:

    * DPI (≥300 ideal, 200 floor)
    * Smallest dimension (≥600 px for paper inclusion)
    * Aspect ratio sanity for time-series-named figures (wider preferred)
    * Caption sidecar (``<name>.caption.md``) — BLOCKER if missing
    * Summary sidecar (``<name>.summary.md``) — warning if missing
    * SVG companion of a PNG — warning if missing (limits editability +
      blocks the deeper SVG audit)
    * SVG label-collision heuristic — when the file is SVG, scan for
      ``<text>`` elements whose nominal bounding boxes overlap; flags
      the common "labels stacked on each other" pitfall surfaced by the
      figure_guidelines protocol's pre-publish self-review.

    Returns a structured dict with ``blockers`` and ``warnings`` that
    ``tool_path_finalize`` / ``tool_audit_step_completeness`` roll up
    into the step's go/no-go gate.
    """
    p = root / figure_path
    if not p.exists():
        return {"status": "error", "message": f"Figure not found: {figure_path}"}

    warnings: list[str] = []
    blockers: list[str] = []
    report: dict[str, Any] = {"path": figure_path}

    suffix = p.suffix.lower()

    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            from PIL import Image  # type: ignore

            with Image.open(p) as img:
                dpi = img.info.get("dpi", (72, 72))
                w, h = img.size
                report.update({
                    "format": img.format,
                    "size_px": [w, h],
                    "dpi": list(dpi) if isinstance(dpi, tuple) else dpi,
                })
                if isinstance(dpi, tuple) and dpi[0] < 200:
                    blockers.append(f"DPI {dpi[0]} below the 200 publication floor.")
                elif isinstance(dpi, tuple) and dpi[0] < 299.5:
                    warnings.append(
                        f"DPI {dpi[0]} acceptable for screen; aim for ≥300 for print."
                    )
                if min(w, h) < 600:
                    warnings.append(
                        f"Smallest dimension {min(w, h)}px small for paper inclusion."
                    )
                aspect = w / max(h, 1)
                if "trend" in p.stem.lower() or "time" in p.stem.lower():
                    if 0.85 <= aspect <= 1.15:
                        warnings.append(
                            "Aspect ratio near 1:1 — time-series plots read better "
                            "at a wider ratio (e.g. 16:9)."
                        )
        except ImportError:
            warnings.append(
                "Pillow not installed; install with `pip install Pillow` for DPI checks."
            )
        except Exception as exc:
            # A corrupt / unreadable / zero-byte image must not crash the audit.
            warnings.append(
                f"Could not read `{p.name}` for DPI/size checks ({exc}) — "
                "regenerate the figure; the file may be empty or corrupt."
            )

    # Legibility scan (text overlap + default font). Runs on a real SVG, OR
    # on a PNG/JPG's sibling .svg when one exists — so the user's "overlapping
    # text" pitfall is caught even in PNG-first projects that keep a vector
    # companion. PNG-only with no vector data can't be machine-checked.
    svg_to_scan: Path | None = None
    if suffix == ".svg":
        svg_to_scan = p
    elif suffix in {".png", ".jpg", ".jpeg"}:
        sib = p.with_suffix(".svg")
        if sib.exists():
            svg_to_scan = sib
    if svg_to_scan is not None:
        try:
            diag = _svg_text_diagnostics(svg_to_scan.read_text(errors="ignore"))
            where = "" if svg_to_scan == p else f" (companion {svg_to_scan.name})"
            if diag["collisions"]:
                warnings.append(
                    f"SVG text-overlap heuristic found ~{diag['collisions']} potential "
                    f"label collisions{where} — verify visually; consider ggrepel / "
                    "matplotlib adjustText / explicit jittered offsets."
                )
            if diag["dejavu"]:
                warnings.append(
                    f"Figure uses the DejaVu default font{where} — set an explicit "
                    "publication font (apply_research_os_style does this) so type "
                    "reads consistently across figures."
                )
            report["svg_text_collisions_est"] = diag["collisions"]
            report["uses_default_font"] = diag["dejavu"]
        except Exception as e:
            logger.debug("SVG diagnostics skipped: %s", e)
    elif suffix in {".png", ".jpg", ".jpeg"}:
        # No vector companion → label overlap is not machine-checkable. Record
        # it so the step gate / AI knows to eyeball the render (or save an SVG).
        report["overlap_checked"] = False

    cap = p.with_suffix(".caption.md")
    summary = p.with_suffix(".summary.md")
    if not cap.exists():
        blockers.append(
            f"Missing technical caption — write `{cap.name}` next to the figure."
        )
    # Summary sidecar is opt-in via researcher_config.figures.summary_sidecar
    # (default off). Auto-generated sidecar stubs tended to leak verbatim
    # into synthesis prose as placeholder captions — the AI now integrates
    # the plain-language version into conclusions.md next to the embed.
    cfg_figures = _load_figures_config(root)
    if cfg_figures.get("summary_sidecar", False) and not summary.exists():
        warnings.append(
            f"summary_sidecar=true but `{summary.name}` is missing — "
            "either set summary_sidecar=false (the lean default; integrate "
            "into conclusions.md) or author the sidecar manually."
        )
    svg_sibling = p.with_suffix(".svg")
    if (
        cfg_figures.get("svg_allowed", False)
        and suffix == ".png"
        and not svg_sibling.exists()
    ):
        warnings.append(
            "svg_allowed=true but no SVG companion present — either set "
            "svg_allowed=false (the lean default; PNG-only ships) or save "
            "the SVG alongside the PNG so the editorial pipeline can edit it."
        )

    report["caption_present"] = cap.exists()
    report["summary_present"] = summary.exists()
    report["svg_present"] = svg_sibling.exists()

    if blockers:
        status = "error"
        message = f"{len(blockers)} blocker(s): " + "; ".join(blockers)
    elif warnings:
        status = "warning"
        message = f"{len(warnings)} warning(s)."
    else:
        status = "success"
        message = "Figure passes the publication quality bar."

    return {
        "status": status,
        "message": message,
        "blockers": blockers,
        "warnings": warnings,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Step-level figure inventory (used by the completeness gate).
# ---------------------------------------------------------------------------


def step_figure_inventory(step_id: str, root: Path) -> dict[str, Any]:
    """Inventory every figure for ``step_id``, classifying caption + summary
    presence so the audit gate can BLOCK on missing material."""
    step_dir = root / "workspace" / step_id
    figures_dir = step_dir / "outputs" / "figures"
    if not figures_dir.exists():
        return {
            "status": "warning",
            "step_id": step_id,
            "figures": [],
            "missing_focal_figure": True,
            "missing_captions": [],
            "missing_summaries": [],
        }
    out: list[dict[str, Any]] = []
    missing_caps: list[str] = []
    missing_sums: list[str] = []
    for f in sorted(figures_dir.iterdir()):
        if f.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
            continue
        cap = f.with_suffix(".caption.md")
        sum_ = f.with_suffix(".summary.md")
        if not cap.exists():
            missing_caps.append(f.name)
        if not sum_.exists():
            missing_sums.append(f.name)
        out.append({
            "name": f.name,
            "caption_present": cap.exists(),
            "summary_present": sum_.exists(),
        })

    missing_focal = not any(
        f["name"].startswith(step_id.split("_", 1)[0] + "_") for f in out
    ) if out else True
    return {
        "status": "success" if (out and not missing_focal) else "warning",
        "step_id": step_id,
        "figures": out,
        "missing_focal_figure": missing_focal or not out,
        "missing_captions": missing_caps,
        "missing_summaries": missing_sums,
    }


__all__ = [
    "OKABE_ITO",
    "ACCENT_PRIMARY",
    "ACCENT_GOLD",
    "ACCENT_GREEN",
    "ACCENT_RED",
    "audit_figure_quality",
    "caption_synthesise",
    "palette_for",
    "step_figure_inventory",
]
