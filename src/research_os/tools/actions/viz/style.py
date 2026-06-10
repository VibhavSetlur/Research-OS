"""Research-OS publication style for matplotlib.

A single import + call gives the AI's plotting script the visual identity
of the Research-OS reference figures: cream background, italic serif
titles, muted CVD-safe accent palette, clean spines, value labels above
bars, and figsizes pre-tuned for the destination (single-column paper,
two-column paper, slide, dashboard tile, poster).

Usage from any AI-authored matplotlib script::

    from research_os.tools.actions.viz import apply_research_os_style

    style = apply_research_os_style(destination="single_col")
    fig, ax = plt.subplots(figsize=style["figsize"])
    bars = ax.bar(x, y, color=style["palette"][0])
    from research_os.tools.actions.viz import label_bars_above, polish_axes
    label_bars_above(ax, bars, unit="ms")
    polish_axes(ax)

Or to take just the colour cycle (no rcParams)::

    from research_os.tools.actions.viz import RO_PALETTE
    colors = RO_PALETTE["accent"]

The style is designed so the FIRST render does not need a v2 to fix
spacing problems — figsizes leave room for legends, ``constrained_layout``
is on by default, value labels float above bars by ``2 %`` of the y-range
so a re-render after data updates doesn't crash labels into the next bar.
The protocol ``visualization/figure_guidelines`` still mandates the
view-and-iterate self-review loop after the first save (overlap problems
that escape constrained_layout still need a human-style eyeball check),
but applying this style up front fixes the common cases before they ship.

Doctrine
--------
Research-OS does not generate figures for the AI — the AI writes its own
plotting code. This module is a *style preset*, not a chart-builder. The
preset is opinionated but optional: matching it gives every figure visual
cohesion with the dashboard scaffold; departing from it (e.g. a journal
demands a specific template) is fine. The protocol gives the AI the
choice.

When matplotlib is not installed (the package is still importable, the
helpers just no-op the rcParams write), the helpers return a populated
context dict with ``applied=False`` so callers can branch without
guarding every reference behind a ``try / except``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("research_os.tools.viz.style")


# ---------------------------------------------------------------------------
# Palettes — five muted accent colours that match the dashboard scaffold,
# plus an emphasis-diverging pair (oxblood / forest) for delta plots and
# a neutral chrome set for backgrounds, foreground, and rules.
# ---------------------------------------------------------------------------

RO_PALETTE: dict[str, list[str]] = {
    # 5 accent colours, ordered to read as the primary palette on a cream
    # background. Navy + olive + forest + oxblood are perceptually well-
    # separated under deuteranopia + protanopia simulation; mustard is the
    # fifth slot for when 5 categories are unavoidable.
    "accent": [
        "#1F4D7A",  # navy
        "#9B7E2D",  # olive gold
        "#3F6049",  # forest
        "#9B3737",  # oxblood
        "#C3A14E",  # mustard
    ],
    # Diverging pair for delta plots. Forest = positive / better, oxblood =
    # negative / worse. Both legible against cream and survive CVD.
    "diverging_emphasis": [
        "#9B3737",  # oxblood (negative)
        "#3F6049",  # forest (positive)
    ],
    # Page chrome: cream bg, warm dark fg, muted text, hairline rule.
    "neutral": [
        "#FBF8F3",  # cream background
        "#3D3A35",  # warm dark grey foreground
        "#7C7468",  # muted secondary text
        "#D6CFC2",  # hairline rule
    ],
}

# Public hex constants that the dashboard CSS and the figure protocol
# reference by name. Edit RO_PALETTE above and these stay in sync.
RO_BG = RO_PALETTE["neutral"][0]
RO_FG = RO_PALETTE["neutral"][1]
RO_MUTED = RO_PALETTE["neutral"][2]
RO_RULE = RO_PALETTE["neutral"][3]


# ---------------------------------------------------------------------------
# Destination figsizes — set ONCE at figure construction so labels render
# at the right size on the first save. Skipping this is the most common
# source of "figure looks fine on my monitor, blown out at print size".
# ---------------------------------------------------------------------------

DESTINATION_FIGSIZES: dict[str, tuple[float, float]] = {
    # Paper / journal slots.
    "single_col": (3.5, 2.6),     # Nature / Cell single column
    "two_col":    (7.2, 4.4),     # Two-column figure
    "full_width": (7.2, 3.0),     # Wide banner (time series, long bars)
    # Slides + screens.
    "slide":      (10.0, 5.6),    # 16:9 slide content area (one figure)
    "slide_half": (5.0, 4.0),     # Two-up on a slide
    # Dashboard tiles + posters.
    "dashboard":  (8.0, 4.5),     # Dashboard hero / lead figure
    "dashboard_tile": (5.5, 3.5), # Dashboard grid tile
    "poster":     (12.0, 7.5),    # Conference poster panel
}


# ---------------------------------------------------------------------------
# rcParams — the actual style. Everything besides the colour cycle is
# matplotlib-version-agnostic; colour cycle is set in apply_research_os_style
# because it needs ``cycler`` from matplotlib.
# ---------------------------------------------------------------------------

STYLE_RCPARAMS: dict[str, Any] = {
    # Backgrounds: cream everywhere including the saved file. This is the
    # single biggest change vs default matplotlib — the cream warmth
    # carries through to the dashboard so figures don't read as "pasted
    # in from a different document".
    "figure.facecolor": RO_BG,
    "axes.facecolor": RO_BG,
    "savefig.facecolor": RO_BG,
    "savefig.edgecolor": RO_BG,
    "savefig.dpi": 300,
    "figure.dpi": 110,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,

    # Spines + ticks: drop top + right, warm dark grey on the rest. Ticks
    # outward + short (matches the reference figures).
    "axes.edgecolor": RO_FG,
    "axes.linewidth": 0.8,
    "axes.labelcolor": RO_FG,
    "axes.titlecolor": RO_FG,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": RO_FG,
    "ytick.color": RO_FG,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 3.0,
    "ytick.major.size": 3.0,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,

    # Grid: subtle dotted horizontal hairline on cream. Below data marks.
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": RO_RULE,
    "grid.linewidth": 0.5,
    "grid.linestyle": (0, (1, 2)),
    "grid.alpha": 0.7,
    "axes.axisbelow": True,

    # Typography: serif stack so titles + axis labels match the reference
    # figures. Inter / Source Sans is provided as a sans fallback for
    # legends + value labels when the AI wants a contrasting weight.
    "font.family": "serif",
    "font.serif": [
        "EB Garamond", "Garamond", "Crimson Text", "Source Serif Pro",
        "Liberation Serif", "DejaVu Serif", "serif",
    ],
    "font.sans-serif": [
        "Inter", "Helvetica Neue", "Source Sans Pro", "Roboto",
        "Liberation Sans", "DejaVu Sans", "sans-serif",
    ],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.titleweight": "normal",
    "axes.titlepad": 12,
    "axes.labelsize": 9,
    "axes.labelpad": 6,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "legend.title_fontsize": 8.5,
    "legend.frameon": False,
    "legend.handlelength": 1.4,
    "legend.columnspacing": 1.5,
    "legend.borderaxespad": 0.0,

    # Layout: constrained_layout handles 90 % of the "labels run off the
    # edge" problem before the AI has to look at the render. h_pad +
    # w_pad reserve breathing room around the axes for value labels and
    # suptitle. hspace + wspace separate subplots by enough that panel
    # titles don't crash into the panel above.
    "figure.constrained_layout.use": True,
    "figure.constrained_layout.h_pad": 0.06,
    "figure.constrained_layout.w_pad": 0.06,
    "figure.constrained_layout.hspace": 0.05,
    "figure.constrained_layout.wspace": 0.05,

    # Lines + patches: thinner default lines, thin edge stroke on bars +
    # patches so adjacent bars don't visually merge on cream.
    "patch.linewidth": 0.6,
    "patch.edgecolor": RO_FG,
    "patch.facecolor": RO_PALETTE["accent"][0],
    "lines.linewidth": 1.4,
    "lines.markersize": 5,

    # Error bars + boxplots: warm dark grey instead of pure black.
    "boxplot.boxprops.color": RO_FG,
    "boxplot.whiskerprops.color": RO_FG,
    "boxplot.capprops.color": RO_FG,
    "boxplot.medianprops.color": RO_PALETTE["accent"][3],
}


# ---------------------------------------------------------------------------
# Apply + helpers — what the AI imports.
# ---------------------------------------------------------------------------


def apply_research_os_style(
    destination: str = "single_col",
    *,
    palette: str = "accent",
    italic_titles: bool = True,
) -> dict[str, Any]:
    """Apply the Research-OS style to matplotlib rcParams + return a context.

    Parameters
    ----------
    destination : str
        Which slot the figure will land in. Picks an opinionated figsize +
        DPI so the FIRST render is sized for its target — single_col,
        two_col, full_width, slide, slide_half, dashboard, dashboard_tile,
        poster. Unknown destinations fall back to single_col with a debug
        log line.
    palette : str
        Which palette in ``RO_PALETTE`` to set as the matplotlib colour
        cycle. ``accent`` (default) is the 5-colour cohesive set the
        dashboard ships with. Pass ``"diverging_emphasis"`` for delta /
        signed-effect plots.
    italic_titles : bool
        Forwarded in the returned context so helpers (``apply_suptitle``)
        know whether to italicise the suptitle. Doesn't touch rcParams
        directly because the italic toggle is per-text-element in matplotlib.

    Returns
    -------
    dict
        Context with keys: figsize (tuple), dpi (int), palette (list[str]),
        destination (str), italic_titles (bool), applied (bool). When
        matplotlib isn't importable, applied=False but the rest is still
        populated so the caller can branch on the figsize / palette.
    """
    figsize = DESTINATION_FIGSIZES.get(destination)
    if figsize is None:
        logger.debug(
            "Unknown destination %r; falling back to single_col", destination,
        )
        destination = "single_col"
        figsize = DESTINATION_FIGSIZES[destination]

    palette_colors = list(RO_PALETTE.get(palette, RO_PALETTE["accent"]))

    try:
        import matplotlib as mpl  # type: ignore
        from cycler import cycler  # type: ignore

        mpl.rcParams.update(STYLE_RCPARAMS)
        mpl.rcParams["axes.prop_cycle"] = cycler("color", palette_colors)
        applied = True
    except ImportError:
        applied = False
    except Exception as e:
        logger.debug("apply_research_os_style: rcParams update failed: %s", e)
        applied = False

    return {
        "destination": destination,
        "figsize": figsize,
        "dpi": 300,
        "palette": palette_colors,
        "italic_titles": italic_titles,
        "applied": applied,
    }


def label_bars_above(
    ax: Any,
    bars: Any,
    *,
    fmt: str = "{:.0f}",
    unit: str = "",
    color: str | None = None,
    fontsize: float = 8,
    offset_frac: float = 0.02,
    italic: bool = True,
) -> None:
    """Float italic value labels above each bar.

    Matches the reference figure aesthetic (``467 ms``, ``128 ms``, …) and
    keeps the label clear of the next bar in a stacked / grouped chart by
    using ``offset_frac`` of the y-range as headroom. Pass ``unit="ms"``
    or ``"%"`` to suffix every label.

    Silently no-ops if the iterable doesn't look like matplotlib bars.
    """
    try:
        ylim = ax.get_ylim()
        offset = (ylim[1] - ylim[0]) * offset_frac
    except Exception:
        return
    for bar in bars:
        try:
            h = bar.get_height()
            x = bar.get_x() + bar.get_width() / 2
        except AttributeError:
            continue
        if h is None or h == 0:
            continue
        label = fmt.format(h)
        if unit:
            label = f"{label} {unit}".rstrip()
        try:
            ax.text(
                x, h + offset, label,
                ha="center", va="bottom",
                fontsize=fontsize,
                fontstyle="italic" if italic else "normal",
                color=color or RO_FG,
            )
        except Exception as e:
            logger.debug("label_bars_above: text failed: %s", e)


def label_diverging_bars(
    ax: Any,
    bars: Any,
    values: list[float],
    *,
    fmt: str = "{:+.4f}",
    fontsize: float = 8,
    offset_frac: float = 0.01,
) -> None:
    """Value labels left/right of zero-line for diverging horizontal bars.

    Negative values get the label inside-right of the bar (closer to zero)
    in oxblood; positive get the label inside-left of the bar in forest.
    Matches the right panel of the reference figure.
    """
    try:
        xlim = ax.get_xlim()
        offset = (xlim[1] - xlim[0]) * offset_frac
    except Exception:
        return
    for bar, v in zip(bars, values):
        try:
            y = bar.get_y() + bar.get_height() / 2
        except AttributeError:
            continue
        if v == 0 or v is None:
            continue
        label = fmt.format(v)
        ha = "left" if v > 0 else "right"
        x = v + (offset if v > 0 else -offset)
        color = RO_PALETTE["diverging_emphasis"][1] if v > 0 else RO_PALETTE["diverging_emphasis"][0]
        try:
            ax.text(
                x, y, label,
                ha=ha, va="center",
                fontsize=fontsize, fontstyle="italic",
                color=color,
            )
        except Exception as e:
            logger.debug("label_diverging_bars: text failed: %s", e)


def polish_axes(
    ax: Any,
    *,
    grid: str = "y",
    spines: tuple[str, ...] = ("left", "bottom"),
) -> None:
    """Drop top+right spines, add subtle horizontal grid (or as requested).

    Idempotent — safe to call after the AI built the chart even if
    apply_research_os_style was already called (rcParams set spines off
    globally; this call only re-asserts on a specific axes).
    """
    try:
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(side in spines)
        if grid in ("y", "x", "both"):
            ax.grid(
                True, axis=grid,
                color=RO_RULE, linewidth=0.5,
                linestyle=(0, (1, 2)), alpha=0.7,
            )
            ax.set_axisbelow(True)
        elif grid in ("none", "off", None, False):
            ax.grid(False)
    except Exception as e:
        logger.debug("polish_axes failed: %s", e)


def apply_suptitle(
    fig: Any,
    title: str,
    *,
    subtitle: str | None = None,
    italic: bool = True,
    y: float = 0.98,
) -> None:
    """Italic serif suptitle + optional smaller subtitle line.

    Matches the reference figure header::

        Step 25 · per-stage per-query latency for the frozen pipeline_3 stack
        Cold = first query of the direction (one-shot warm-up cost).  ...

    Positions the suptitle high enough (``y=0.98``) that constrained_layout
    doesn't crash it into the top spine.
    """
    try:
        fig.suptitle(
            title,
            fontsize=11,
            fontstyle="italic" if italic else "normal",
            y=y, color=RO_FG,
        )
        if subtitle:
            fig.text(
                0.5, y - 0.04, subtitle,
                ha="center", va="top",
                fontsize=8,
                fontstyle="italic" if italic else "normal",
                color=RO_MUTED,
            )
    except Exception as e:
        logger.debug("apply_suptitle failed: %s", e)


__all__ = [
    "RO_PALETTE",
    "RO_BG",
    "RO_FG",
    "RO_MUTED",
    "RO_RULE",
    "DESTINATION_FIGSIZES",
    "STYLE_RCPARAMS",
    "apply_research_os_style",
    "label_bars_above",
    "label_diverging_bars",
    "polish_axes",
    "apply_suptitle",
]
