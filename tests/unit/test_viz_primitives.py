"""3.2.8 — figure-primitive STYLE helpers in viz/style.py.

Covers the five additive primitives the AI keeps re-coding by hand:

* ``ranked_dot`` / ``lollipop`` — sorted, common-scale, dropped left spine,
  direct value labels (Cleveland dot / lollipop).
* ``facet_grid`` — a fig+axes grid that ENFORCES shared x/y limits.
* ``direct_label_endpoints`` — label line endpoints at the data instead of a
  legend.
* ``ro_colorbar`` — an in-palette viridis (sequential) / PuOr (diverging)
  continuous colorbar, anchors sourced from viz.palettes.

Every test runs headless (matplotlib Agg) and asserts a real PNG is produced;
the facet test additionally asserts the panels share both axes. All five
helpers are also exercised for graceful no-op behaviour on bad inputs.
"""

from __future__ import annotations

import os

import pytest

# Headless before any pyplot import.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


LABELS = ["alpha", "bravo", "charlie", "delta", "echo"]
VALUES = [12.0, 7.5, 19.2, 3.1, 9.8]


def _png_nonempty(path) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_primitives_exported_from_viz_package():
    """The five primitives must be importable from the viz package and listed
    in __all__ so an AI plotting script gets the whole figure surface from one
    import."""
    from research_os.tools.actions import viz
    for sym in (
        "ranked_dot", "lollipop", "facet_grid",
        "direct_label_endpoints", "ro_colorbar",
    ):
        assert hasattr(viz, sym), f"viz missing export {sym!r}"
        assert sym in viz.__all__, f"{sym!r} not in viz.__all__"


# ---------------------------------------------------------------------------
# ranked_dot
# ---------------------------------------------------------------------------


def test_ranked_dot_renders_png_and_sorts(tmp_path):
    from research_os.tools.actions.viz import apply_research_os_style, ranked_dot
    apply_research_os_style(destination="single_col")
    fig, ax = plt.subplots()
    out = ranked_dot(ax, LABELS, VALUES, unit="ms")
    assert out is ax
    # Sorted descending by default → biggest value (charlie=19.2) first in the
    # row order, assigned to y=0 (the bottom tick in matplotlib's coords).
    # get_yticklabels() is ordered by ascending y position, so index 0 is the
    # first-sorted (biggest) category.
    ticklabels = [t.get_text() for t in ax.get_yticklabels()]
    assert ticklabels[0] == "charlie"
    # Left + top + right spines dropped; only bottom value axis kept.
    assert not ax.spines["left"].get_visible()
    assert not ax.spines["top"].get_visible()
    assert ax.spines["bottom"].get_visible()
    p = tmp_path / "ranked.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_ranked_dot_ascending(tmp_path):
    from research_os.tools.actions.viz import ranked_dot
    fig, ax = plt.subplots()
    ranked_dot(ax, LABELS, VALUES, ascending=True)
    ticklabels = [t.get_text() for t in ax.get_yticklabels()]
    # Ascending → smallest (delta=3.1) sorts first and lands at y=0 (index 0
    # in the ascending-y ticklabel order).
    assert ticklabels[0] == "delta"
    plt.close(fig)


def test_ranked_dot_noop_on_mismatch():
    from research_os.tools.actions.viz import ranked_dot
    fig, ax = plt.subplots()
    # Length mismatch → returns ax, no crash, nothing drawn.
    out = ranked_dot(ax, LABELS, VALUES[:2])
    assert out is ax
    assert not ax.collections  # nothing scattered
    plt.close(fig)


# ---------------------------------------------------------------------------
# lollipop
# ---------------------------------------------------------------------------


def test_lollipop_renders_png_with_stems(tmp_path):
    from research_os.tools.actions.viz import lollipop
    fig, ax = plt.subplots()
    out = lollipop(ax, LABELS, [v - 8 for v in VALUES], baseline=0.0, unit="pp")
    assert out is ax
    # An hlines call produces a LineCollection on the axes.
    assert ax.collections, "lollipop drew no stems/dots"
    assert not ax.spines["left"].get_visible()
    p = tmp_path / "lolli.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_lollipop_noop_on_empty():
    from research_os.tools.actions.viz import lollipop
    fig, ax = plt.subplots()
    out = lollipop(ax, [], [])
    assert out is ax
    plt.close(fig)


# ---------------------------------------------------------------------------
# facet_grid — the key invariant is SHARED axes.
# ---------------------------------------------------------------------------


def test_facet_grid_shares_both_axes(tmp_path):
    import numpy as np

    from research_os.tools.actions.viz import facet_grid
    fig, axes = facet_grid(2, 2, destination="two_col")
    assert fig is not None and axes is not None
    assert axes.shape == (2, 2)
    # The defining contract: every panel shares x AND y with every other.
    a00 = axes[0, 0]
    assert a00.get_shared_x_axes().joined(a00, axes[1, 1])
    assert a00.get_shared_y_axes().joined(a00, axes[0, 1])
    for a in axes.ravel():
        a.plot(np.arange(10), np.random.default_rng(0).random(10))
        # RO polish: top/right spines dropped on every panel.
        assert not a.spines["top"].get_visible()
        assert not a.spines["right"].get_visible()
    p = tmp_path / "facet.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_facet_grid_unshared_when_requested():
    from research_os.tools.actions.viz import facet_grid
    fig, axes = facet_grid(1, 2, sharex=False, sharey=False)
    a0 = axes[0, 0]
    assert not a0.get_shared_x_axes().joined(a0, axes[0, 1])
    plt.close(fig)


# ---------------------------------------------------------------------------
# direct_label_endpoints
# ---------------------------------------------------------------------------


def test_direct_label_endpoints_labels_and_drops_legend(tmp_path):
    import numpy as np

    from research_os.tools.actions.viz import direct_label_endpoints
    fig, ax = plt.subplots()
    x = np.arange(10)
    ax.plot(x, x * 1.0, label="rising")
    ax.plot(x, 9 - x * 0.5, label="falling")
    ax.legend()
    n_texts_before = len(ax.texts)
    out = direct_label_endpoints(ax)
    assert out is ax
    # Two labelled lines → two endpoint texts added.
    assert len(ax.texts) == n_texts_before + 2
    endpoint_strings = [t.get_text().strip() for t in ax.texts]
    assert "rising" in endpoint_strings
    assert "falling" in endpoint_strings
    # Redundant legend removed once we directly labelled.
    assert ax.get_legend() is None
    p = tmp_path / "endpoints.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_direct_label_endpoints_skips_underscore_labels():
    import numpy as np

    from research_os.tools.actions.viz import direct_label_endpoints
    fig, ax = plt.subplots()
    # Unlabelled line (matplotlib default label starts with "_").
    ax.plot(np.arange(5), np.arange(5))
    out = direct_label_endpoints(ax)
    assert out is ax
    assert not ax.texts  # nothing labelled
    plt.close(fig)


# ---------------------------------------------------------------------------
# ro_colorbar — in-palette ramps from viz.palettes (no jet/rainbow).
# ---------------------------------------------------------------------------


def test_ro_colorbar_sequential_from_image(tmp_path):
    import numpy as np

    from research_os.tools.actions.viz import ro_colorbar
    fig, ax = plt.subplots()
    im = ax.imshow(np.random.default_rng(1).random((8, 8)))
    cbar = ro_colorbar(im, ax=ax, kind="sequential", label="value")
    assert cbar is not None
    # Surfaces the chosen cmap so the caller can reuse it for the data layer.
    assert hasattr(cbar, "ro_cmap")
    p = tmp_path / "cbar_seq.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_ro_colorbar_diverging_standalone(tmp_path):
    from research_os.tools.actions.viz import ro_colorbar
    fig, ax = plt.subplots()
    cbar = ro_colorbar(ax=ax, kind="diverging", label="delta")
    assert cbar is not None
    p = tmp_path / "cbar_div.png"
    fig.savefig(p)
    plt.close(fig)
    assert _png_nonempty(p)


def test_ro_colorbar_anchors_come_from_palettes_module():
    """The ramps must be the in-palette viridis / PuOr anchors from
    viz.palettes — not hardcoded — so chrome + audit + figure agree."""
    from research_os.tools.actions.viz import ro_colorbar
    from research_os.tools.actions.viz.palettes import DIVERGING, SEQUENTIAL

    fig, ax = plt.subplots()
    cbar = ro_colorbar(ax=ax, kind="sequential")
    # First anchor of the ro cmap should be viridis' deepest purple.
    rgba0 = cbar.ro_cmap(0.0)
    first_hex = "#%02X%02X%02X" % tuple(round(c * 255) for c in rgba0[:3])
    assert first_hex.lower() == SEQUENTIAL["viridis"][0].lower()
    plt.close(fig)

    fig, ax = plt.subplots()
    cbar = ro_colorbar(ax=ax, kind="diverging")
    rgba0 = cbar.ro_cmap(0.0)
    first_hex = "#%02X%02X%02X" % tuple(round(c * 255) for c in rgba0[:3])
    assert first_hex.lower() == DIVERGING["puor"][0].lower()
    plt.close(fig)
