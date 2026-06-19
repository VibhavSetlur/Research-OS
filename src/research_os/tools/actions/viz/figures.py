"""Figure utilities — palette lookup, quality audit, step inventory.

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
* ``audit_figure_quality(...)`` — checks an existing figure for DPI,
  dimensions, the technical ``<name>.caption.md`` sidecar, SVG companion,
  plus an SVG-text overlap heuristic for the "labels stacked on each
  other" pitfall. Surfaces warnings + blockers consumed by
  ``tool_path_finalize`` / ``tool_audit_step_completeness``.
* ``step_figure_inventory(step_id, root)`` — lists every figure
  produced by a step + its caption status. Used by the audit gate.

Each figure ships exactly three sidecars: the ``.png`` (or ``.svg`` /
``.html`` when the researcher asks), a ``<name>.prov.json`` provenance
record, and a ``<name>.caption.md`` the synthesis pipeline embeds. The
old plain-English ``<name>.summary.md`` sidecar was retired in 3.2 — its
interpretation now lives inline in ``conclusions.md`` next to the embed.

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
    "interactive_html_allowed": True,
}


def _load_figures_config(root: Path) -> dict[str, Any]:
    """Read the `figures:` block from `inputs/researcher_config.yaml`.

    Returns the lean defaults (no SVG, interactive HTML allowed) when the
    file or block is absent, malformed, or the config dir is not under the
    supplied root. Always returns a dict that the figure-audit code can
    index without raising.
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
    try:
        n = max(0, int(n))
    except (TypeError, ValueError):
        n = 8
    if n == 0:
        return []
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
    if not cap.exists():
        blockers.append(
            f"Missing technical caption — write `{cap.name}` next to the figure."
        )
    # The plain-English interpretation lives inline in conclusions.md next
    # to the embed (the old <name>.summary.md sidecar was retired in 3.2).
    cfg_figures = _load_figures_config(root)
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
# Figure design / style audit (3.2.8) — reviews STYLISTIC choices, the way a
# design reviewer would. Pairs with audit_figure_quality (technical: DPI,
# caption presence, overlap). This judges the chart's colour, labelling,
# caption framing, and shape against the figure-design principles so a figure
# matches the page it ships in. Wired into the figure_full audit dimension.
# ---------------------------------------------------------------------------


def _find_plotting_source(p: Path, root: Path) -> str:
    """Best-effort: read the plotting script that most likely produced ``p``.

    Looks in the figure's step ``scripts/`` dir + the synthesis ``scripts/``
    dir for .py / .R / .jl files; concatenates their text. Used by the
    colormap + zero-baseline checks (a banned colormap is set in code, not in
    the PNG). Never raises; returns "" when nothing is found.
    """
    import re as _re

    candidates: list[Path] = []
    # Walk up to find a `scripts/` sibling of the figure's `outputs/` dir, plus
    # the project-level synthesis/scripts and workspace/<step>/scripts.
    for base in (p.parent, p.parent.parent, p.parent.parent.parent):
        sc = base / "scripts"
        if sc.is_dir():
            candidates.append(sc)
    for rel in ("synthesis/scripts",):
        sc = root / rel
        if sc.is_dir():
            candidates.append(sc)
    stem = _re.sub(r"\W+", "", p.stem.lower())
    blobs: list[str] = []
    seen: set[Path] = set()
    for sc in candidates:
        for f in sorted(sc.rglob("*")):
            if f in seen or f.suffix.lower() not in {".py", ".r", ".jl"}:
                continue
            seen.add(f)
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Prioritise a script that names this figure; otherwise include all.
            if stem and stem in _re.sub(r"\W+", "", txt.lower()):
                blobs.insert(0, txt)
            else:
                blobs.append(txt)
    return "\n".join(blobs)


def _figure_is_synthesis_bound(p: Path, root: Path) -> bool:
    """A figure under synthesis/ ships to an external reader; leaks there are
    blockers. A working figure under workspace/ leaks only warn."""
    try:
        rel = p.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return "synthesis" in p.parts
    return rel.parts and rel.parts[0] == "synthesis"


# Axis-label heuristics.
_RAW_COLUMN_RE = __import__("re").compile(r"^[a-z]+(?:_[a-z0-9]+)+$")
_DIMENSIONAL_HINT_RE = __import__("re").compile(
    r"\b(mass|weight|length|width|height|depth|time|duration|distance|speed|"
    r"temperature|temp|voltage|current|pressure|concentration|dose|age|"
    r"size|area|volume|rate|frequency|wavelength|energy|force|power)\b",
    __import__("re").IGNORECASE,
)
_UNIT_IN_PARENS_RE = __import__("re").compile(r"\([^)]*\b(?:[a-zµμ%°]{1,6}|per|/)\b[^)]*\)")

# Caption-mechanics openers (caption describing the chart, not the finding).
_CAPTION_MECHANICS_RE = __import__("re").compile(
    r"^\s*(?:histogram|bar\s*chart|bar\s*plot|scatter(?:\s*plot)?|box\s*plot|"
    r"line\s*(?:chart|plot)|heatmap|plot\s+of|figure\s+showing|this\s+(?:figure|"
    r"plot|chart|graph)|a\s+(?:plot|chart|graph|figure)\s+of)\b",
    __import__("re").IGNORECASE,
)

# Internal-reference leakage in figure text / caption.
_FIG_LEAK_RE = __import__("re").compile(
    r"(?i)(?:\bstep[ _]?\d+\b|workspace/|\.png\b|\.csv\b|\.parquet\b|"
    r"pipeline_\d|v\d+\.py\b|/[A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+)"
)


def _svg_chart_hexes(svg_text: str) -> list[str]:
    """Every #rrggbb fill/stroke in an SVG (lowercased)."""
    import re as _re

    return [("#" + m.group(1)).lower() for m in _re.finditer(r"#([0-9a-fA-F]{6})\b", svg_text)]


def audit_figure_style(figure_path: str, root: Path) -> dict[str, Any]:
    """Review a figure's STYLISTIC choices (colour / labels / caption / shape).

    Checks (severities per the 3.2.8 design spec):

    * ``forbidden_colormap_detection`` — jet/turbo/rainbow/hsv/… on a
      quantitative figure → block (set in the plotting script or embedded SVG).
    * ``palette_adherence`` — chart hues drifting off every professional
      palette → warn (>5).
    * ``too_many_categorical_colors`` — >8 distinct non-grey hues → warn.
    * ``axis_label_and_unit_presence`` — an axis region with no text → block;
      a raw column-name axis (``body_mass_g``) or a dimensional axis with no
      unit-in-parens → warn.
    * ``caption_finding_led`` — caption opens with chart mechanics → warn.
    * ``internal_reference_leakage`` — step ids / paths / source filenames in
      figure text or caption → block (synthesis-bound) / warn (working).
    * ``zero_baseline_disclosure`` — truncated bar baseline with no caption
      note → warn.
    * ``too_many_series_spaghetti`` — >7 un-faceted line series → warn.
    * ``aspect_ratio_sanity`` — time-series ~1:1 / ranked-bar too tall → warn.

    Best-effort + never raises; returns ``{status, blockers, warnings,
    report}`` so the figure_full audit can merge it with the technical audit.
    """
    import re as _re

    p = root / figure_path
    if not p.exists():
        return {"status": "error", "message": f"Figure not found: {figure_path}"}

    from research_os.tools.actions.viz.palettes import (
        BANNED_COLORMAPS,
        all_allowed_chart_hexes,
        is_near_neutral,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {"path": figure_path}
    suffix = p.suffix.lower()
    stem_low = p.stem.lower()
    synth_bound = _figure_is_synthesis_bound(p, root)

    svg_text = ""
    if suffix == ".svg":
        try:
            svg_text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            svg_text = ""
    else:
        sib = p.with_suffix(".svg")
        if sib.exists():
            try:
                svg_text = sib.read_text(encoding="utf-8", errors="replace")
            except OSError:
                svg_text = ""

    src = _find_plotting_source(p, root)
    caption = ""
    cap_path = p.with_suffix(".caption.md")
    if cap_path.exists():
        try:
            caption = cap_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            caption = ""

    # --- forbidden_colormap_detection (block on quantitative) ---------------
    banned_hit: str | None = None
    haystack = f"{src}\n{svg_text}"
    for cm in BANNED_COLORMAPS:
        if _re.search(rf"\b{_re.escape(cm)}\b", haystack, _re.I):
            banned_hit = cm
            break
    # cmap=... / scale_*_gradientn forms.
    cmap_m = _re.search(r"""cmap\s*=\s*['"](jet|turbo|rainbow|hsv|nipy_spectral|gist_rainbow)""", src, _re.I)
    if cmap_m and not banned_hit:
        banned_hit = cmap_m.group(1)
    if banned_hit:
        blockers.append(
            f"Banned colormap '{banned_hit}' on a quantitative figure. "
            "Rainbow/jet/turbo/hsv are non-monotonic in luminance — they "
            "mislead and fail colour-vision deficiency. Use viridis (sequential) "
            "or PuOr/RdBu (diverging)."
        )
    report["banned_colormap"] = banned_hit

    # --- palette_adherence + too_many_categorical_colors --------------------
    if svg_text:
        hexes = _svg_chart_hexes(svg_text)
        chart_hues = {h for h in hexes if not is_near_neutral(h)}
        allowed = all_allowed_chart_hexes()
        off = sorted(h for h in chart_hues if h not in allowed)
        report["off_palette_count"] = len(off)
        report["distinct_chart_hues"] = len(chart_hues)
        if len(off) > 5:
            warnings.append(
                f"{len(off)} chart colour(s) outside every professional palette "
                "— a figure should match the palette of the page it ships in "
                "(restraint + consistent meaning). See tool_figure_palette."
            )
        if len(chart_hues) > 8:
            warnings.append(
                f"{len(chart_hues)} distinct categorical colours — beyond ~8 "
                "hues are indistinguishable. Direct-label the series or facet "
                "instead of adding colours."
            )

    # --- axis_label_and_unit_presence ---------------------------------------
    if svg_text:
        texts = [
            _re.sub(r"<[^>]+>", "", t).strip()
            for t in _re.findall(r"<text[^>]*>(.*?)</text>", svg_text, _re.S | _re.I)
        ]
        texts = [t for t in texts if t]
        report["svg_text_labels"] = len(texts)
        if not texts:
            blockers.append(
                "Figure SVG has no text — an axis region with zero labels is "
                "unreadable. Label both axes (quantity + unit)."
            )
        else:
            raw_cols = sorted({t for t in texts if _RAW_COLUMN_RE.match(t)})
            if raw_cols:
                warnings.append(
                    f"Axis label(s) are raw column names ({', '.join(raw_cols[:3])}) "
                    "— rename to human-readable quantities with units "
                    "(\"Body mass (g)\", not \"body_mass_g\")."
                )
            # Dimensional axis with no unit-in-parens anywhere.
            dimensional = [t for t in texts if _DIMENSIONAL_HINT_RE.search(t)]
            if dimensional and not any(_UNIT_IN_PARENS_RE.search(t) for t in texts):
                warnings.append(
                    "An axis names a dimensional quantity but no unit-in-parens "
                    "is present — add units (e.g. \"Time (s)\", \"Mass (kg)\")."
                )

    # --- caption_finding_led ------------------------------------------------
    if caption:
        cap_body = _re.sub(r"^\s*\*?\*?(?:figure|fig\.?)\s*\d*[.:—-]*\*?\*?\s*", "",
                           caption.strip(), flags=_re.I)
        first_sentence = _re.split(r"(?<=[.!?])\s+", cap_body.strip(), maxsplit=1)[0]
        if _CAPTION_MECHANICS_RE.match(first_sentence):
            warnings.append(
                "Caption opens with chart mechanics "
                f"({first_sentence[:50]!r}) — lead with the FINDING the figure "
                "shows, not \"Histogram of …\" / \"Scatter plot of …\"."
            )
        if len(_re.split(r"(?<=[.!?])\s+", cap_body.strip())) > 4 or len(cap_body) > 600:
            warnings.append(
                "Caption is long — a figure caption is 1-3 sentences (what to "
                "see + what it means). Move detail to the body text."
            )

    # --- internal_reference_leakage -----------------------------------------
    leak_sources = caption
    if svg_text:
        leak_sources += "\n" + " ".join(
            _re.sub(r"<[^>]+>", "", t)
            for t in _re.findall(r"<text[^>]*>(.*?)</text>", svg_text, _re.S | _re.I)
        )
    leaks = sorted(set(m.group(0) for m in _FIG_LEAK_RE.finditer(leak_sources)))
    if leaks:
        msg = (
            f"{len(leaks)} internal reference(s) in the figure / caption "
            f"({', '.join(leaks[:4])}). A reader has no workspace — strip step "
            "ids, paths, and source filenames."
        )
        if synth_bound:
            blockers.append(msg)
        else:
            warnings.append(msg)
    report["internal_leaks"] = leaks

    # --- zero_baseline_disclosure -------------------------------------------
    if src:
        is_bar = bool(_re.search(r"\.bar\(|\bgeom_col\b|\bgeom_bar\b|kind\s*=\s*['\"]bar", src, _re.I))
        ylim_m = _re.search(r"set_ylim\(\s*([0-9.]+)|ylim\s*=?\s*\(?\s*c?\(?\s*([0-9.]+)", src, _re.I)
        nonzero_floor = False
        if ylim_m:
            val = ylim_m.group(1) or ylim_m.group(2)
            try:
                nonzero_floor = float(val) > 0
            except (TypeError, ValueError):
                nonzero_floor = False
        if is_bar and nonzero_floor:
            disclosed = bool(_re.search(r"truncat|axis starts at|baseline|cropped|broken axis",
                                        caption, _re.I))
            if not disclosed:
                warnings.append(
                    "Bar chart with a non-zero y-axis floor and no caption note "
                    "— a truncated bar baseline exaggerates differences. Either "
                    "start the axis at zero or disclose the truncation in the "
                    "caption."
                )

    # --- too_many_series_spaghetti ------------------------------------------
    faceted = bool(_re.search(r"facet_wrap|facet_grid|subplots\(|add_subplot", src, _re.I))
    n_series = 0
    if svg_text and not faceted:
        # Distinct coloured line paths (stroke + no fill) — rough proxy.
        n_series = len(_re.findall(r"<path[^>]*\bstroke\s*:\s*#[0-9a-fA-F]{6}", svg_text, _re.I))
        n_series += len(_re.findall(r'<path[^>]*\bstroke="#[0-9a-fA-F]{6}"', svg_text, _re.I))
    if src and not faceted:
        n_series = max(n_series, len(_re.findall(r"\bgeom_line\b|\.plot\(", src)))
    if n_series > 7:
        warnings.append(
            f"~{n_series} overlapping line series with no faceting — beyond ~7 "
            "lines is spaghetti. Facet, direct-label the few that matter, or "
            "grey out the rest."
        )
    report["line_series_est"] = n_series

    # --- aspect_ratio_sanity (PNG dimensions) -------------------------------
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            from PIL import Image  # type: ignore

            with Image.open(p) as img:
                w, h = img.size
            aspect = w / max(h, 1)
            report["aspect_ratio"] = round(aspect, 2)
            if _re.search(r"time|trend|series|forecast", stem_low) and 0.85 <= aspect <= 1.15:
                warnings.append(
                    "Time-series / trend figure is ~1:1 — read it wider "
                    "(e.g. 16:9) so the trajectory is legible."
                )
            if _re.search(r"bar|ranked|lollipop|categor|rank", stem_low) and aspect > 1.3:
                warnings.append(
                    "Ranked / categorical figure is wide — a horizontal layout "
                    "(taller than wide) fits long category labels better."
                )
        except Exception:
            pass

    if blockers:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "success"
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Step-level figure inventory (used by the completeness gate).
# ---------------------------------------------------------------------------


def step_figure_inventory(step_id: str, root: Path) -> dict[str, Any]:
    """Inventory every figure for ``step_id``, classifying caption
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
        }
    out: list[dict[str, Any]] = []
    missing_caps: list[str] = []
    for f in sorted(figures_dir.iterdir()):
        if f.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
            continue
        cap = f.with_suffix(".caption.md")
        if not cap.exists():
            missing_caps.append(f.name)
        out.append({
            "name": f.name,
            "caption_present": cap.exists(),
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
    }


__all__ = [
    "OKABE_ITO",
    "ACCENT_PRIMARY",
    "ACCENT_GOLD",
    "ACCENT_GREEN",
    "ACCENT_RED",
    "audit_figure_quality",
    "audit_figure_style",
    "palette_for",
    "step_figure_inventory",
]
