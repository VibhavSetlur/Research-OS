"""v2.4.4 — Research-OS publication style preset.

Covers the new ``research_os.tools.actions.viz.style`` module:

* palette + figsize + rcParams constants exist and have the shape the
  protocol promises (5+ accent colours, 8+ destinations);
* ``apply_research_os_style`` returns a well-formed context dict whether
  matplotlib is installed or not;
* ``label_bars_above`` / ``label_diverging_bars`` / ``polish_axes`` /
  ``apply_suptitle`` no-op gracefully when handed inputs that don't look
  like matplotlib objects (so an AI script that calls them with the
  wrong type doesn't crash);
* the helpers are exported from the ``viz`` package alongside the
  pre-existing ``palette_for`` / ``audit_figure_quality`` surface.
"""

from __future__ import annotations

import re

import pytest


def test_ro_palette_has_required_keys():
    from research_os.tools.actions.viz import RO_PALETTE
    for key in ("accent", "diverging_emphasis", "neutral"):
        assert key in RO_PALETTE, f"RO_PALETTE missing key {key!r}"
    # accent should have at least 5 colours (the published reference
    # figures use 4 accents + 1 fifth slot for stacked-bar contrast).
    assert len(RO_PALETTE["accent"]) >= 5
    # diverging emphasis must be exactly two (positive / negative).
    assert len(RO_PALETTE["diverging_emphasis"]) == 2


def test_ro_palette_all_hex():
    from research_os.tools.actions.viz import RO_PALETTE
    hex_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for key, colours in RO_PALETTE.items():
        for c in colours:
            assert hex_re.match(c), f"{key} colour {c!r} is not a #rrggbb hex"


def test_ro_palette_neutral_carries_chrome_constants():
    """The neutral set is the chrome the dashboard CSS references — cream
    bg, warm-dark fg, muted secondary, hairline rule (in that order)."""
    from research_os.tools.actions.viz import (
        RO_BG, RO_FG, RO_MUTED, RO_PALETTE, RO_RULE,
    )
    assert RO_PALETTE["neutral"][0] == RO_BG
    assert RO_PALETTE["neutral"][1] == RO_FG
    assert RO_PALETTE["neutral"][2] == RO_MUTED
    assert RO_PALETTE["neutral"][3] == RO_RULE


def test_destination_figsizes_has_documented_destinations():
    """The protocol promises 8 destinations — single_col / two_col /
    full_width / slide / slide_half / dashboard / dashboard_tile /
    poster — so all 8 must round-trip from the constants table."""
    from research_os.tools.actions.viz import DESTINATION_FIGSIZES
    for dest in (
        "single_col", "two_col", "full_width",
        "slide", "slide_half",
        "dashboard", "dashboard_tile",
        "poster",
    ):
        assert dest in DESTINATION_FIGSIZES
        w, h = DESTINATION_FIGSIZES[dest]
        assert w > 0 and h > 0
        # Sanity: single_col is the smallest, poster is the biggest.
    assert DESTINATION_FIGSIZES["single_col"][0] < DESTINATION_FIGSIZES["poster"][0]


def test_apply_research_os_style_returns_context():
    """Always returns the full context dict whether matplotlib applies
    or not — callers branch on `applied` but use `figsize` / `palette`
    unconditionally."""
    from research_os.tools.actions.viz import apply_research_os_style
    style = apply_research_os_style(destination="single_col")
    assert set(style.keys()) >= {
        "destination", "figsize", "dpi", "palette",
        "italic_titles", "applied",
    }
    assert style["destination"] == "single_col"
    assert isinstance(style["figsize"], tuple)
    assert len(style["figsize"]) == 2
    assert style["dpi"] == 300
    assert isinstance(style["palette"], list)
    assert len(style["palette"]) >= 5


def test_apply_research_os_style_unknown_destination_falls_back():
    """Unknown destination falls back to single_col with a debug log
    line — never raises."""
    from research_os.tools.actions.viz import (
        DESTINATION_FIGSIZES, apply_research_os_style,
    )
    style = apply_research_os_style(destination="potato")
    assert style["destination"] == "single_col"
    assert style["figsize"] == DESTINATION_FIGSIZES["single_col"]


def test_apply_research_os_style_picks_named_palette():
    """`palette='diverging_emphasis'` returns the 2-colour signed-delta
    set, not the 5-colour accent set."""
    from research_os.tools.actions.viz import apply_research_os_style
    style = apply_research_os_style(palette="diverging_emphasis")
    assert len(style["palette"]) == 2


def test_apply_research_os_style_unknown_palette_falls_back():
    from research_os.tools.actions.viz import (
        RO_PALETTE, apply_research_os_style,
    )
    style = apply_research_os_style(palette="nonsense")
    assert style["palette"] == list(RO_PALETTE["accent"])


def test_helpers_safe_on_non_matplotlib_inputs():
    """`label_bars_above` / `label_diverging_bars` / `polish_axes` /
    `apply_suptitle` must no-op when the AI passes something that
    doesn't look like a matplotlib bar / axes / figure (e.g. plotly
    artefact, a tuple, None). Never raise."""
    from research_os.tools.actions.viz import (
        apply_suptitle, label_bars_above, label_diverging_bars, polish_axes,
    )

    # None for ax → caught by try/except inside each helper.
    label_bars_above(None, [])
    label_diverging_bars(None, [], [])
    polish_axes(None)
    apply_suptitle(None, "title", subtitle="sub")

    # A plain tuple passed where a bar is expected: helpers skip it
    # silently (it has no .get_height / .get_x methods).
    class _Stub:
        def get_ylim(self):
            return (0, 10)

        def get_xlim(self):
            return (-1, 1)

        def text(self, *a, **k):
            return None

        def grid(self, *a, **k):
            return None

        def set_axisbelow(self, val):
            return None

        @property
        def spines(self):
            class _S(dict):
                def __missing__(self, k):
                    obj = type("Sp", (), {"set_visible": lambda self, v: None})()
                    self[k] = obj
                    return obj
            return _S()
    ax = _Stub()
    label_bars_above(ax, [(1, 2, 3)])
    label_diverging_bars(ax, [(1, 2)], [0.5])
    polish_axes(ax)


def test_style_rcparams_uses_cream_background():
    """The single most visible identity choice — cream bg, not white —
    must be present in STYLE_RCPARAMS so the saved files inherit it."""
    from research_os.tools.actions.viz import RO_BG, STYLE_RCPARAMS
    assert STYLE_RCPARAMS["figure.facecolor"] == RO_BG
    assert STYLE_RCPARAMS["axes.facecolor"] == RO_BG
    assert STYLE_RCPARAMS["savefig.facecolor"] == RO_BG
    # Top + right spines off — the look-vs-default differentiator.
    assert STYLE_RCPARAMS["axes.spines.top"] is False
    assert STYLE_RCPARAMS["axes.spines.right"] is False
    # constrained_layout on so the first render isn't crowded.
    assert STYLE_RCPARAMS["figure.constrained_layout.use"] is True
    # 300 dpi on save (the audit gate's floor for publication).
    assert STYLE_RCPARAMS["savefig.dpi"] >= 300


def test_viz_package_exports_style_surface():
    """The new style helpers are exported alongside the existing
    palette_for / audit_figure_quality / step_figure_inventory so the
    AI's plotting script can import the whole figure surface from one
    place."""
    from research_os.tools.actions import viz
    for sym in (
        "apply_research_os_style", "RO_PALETTE", "RO_BG", "RO_FG",
        "RO_MUTED", "RO_RULE", "DESTINATION_FIGSIZES", "STYLE_RCPARAMS",
        "label_bars_above", "label_diverging_bars",
        "polish_axes", "apply_suptitle",
        "palette_for", "audit_figure_quality",
        "step_figure_inventory",
    ):
        assert hasattr(viz, sym), f"viz package missing export {sym!r}"
    # All listed in __all__ so `from ... import *` picks them up.
    for sym in (
        "apply_research_os_style", "RO_PALETTE",
        "label_bars_above", "polish_axes",
    ):
        assert sym in viz.__all__


@pytest.mark.parametrize("destination", [
    "single_col", "two_col", "full_width",
    "slide", "slide_half",
    "dashboard", "dashboard_tile", "poster",
])
def test_apply_research_os_style_round_trip(destination):
    """Every documented destination round-trips its figsize through
    the apply() call."""
    from research_os.tools.actions.viz import (
        DESTINATION_FIGSIZES, apply_research_os_style,
    )
    style = apply_research_os_style(destination=destination)
    assert style["figsize"] == DESTINATION_FIGSIZES[destination]
    assert style["destination"] == destination
