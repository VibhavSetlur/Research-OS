"""Figure palette source-of-truth + figure-quality legibility heuristics."""
from __future__ import annotations

from research_os.tools.actions.viz.figures import (
    _svg_text_diagnostics,
    audit_figure_quality,
    palette_for,
)
from research_os.tools.actions.viz.style import RO_PALETTE


def test_palette_accent_matches_apply_style_source():
    # tool_figure_palette('accent') must match what apply_research_os_style sets.
    assert palette_for("accent", 5) == RO_PALETTE["accent"]
    assert palette_for("accent", 3) == RO_PALETTE["accent"][:3]


def test_palette_accent_cycles_when_more_requested():
    out = palette_for("accent", 7)
    assert len(out) == 7
    assert out[:5] == RO_PALETTE["accent"]
    assert out[5] == RO_PALETTE["accent"][0]  # cycled


def test_palette_diverging_emphasis():
    assert palette_for("diverging_emphasis", 2) == RO_PALETTE["diverging_emphasis"]


def test_svg_diagnostics_detects_overlap():
    svg = (
        '<svg><text x="10" y="20">Label A</text>'
        '<text x="12" y="22">Label B</text></svg>'
    )
    diag = _svg_text_diagnostics(svg)
    assert diag["collisions"] >= 1


def test_svg_diagnostics_no_overlap_when_separated():
    svg = (
        '<svg><text x="10" y="20">Label A</text>'
        '<text x="10" y="200">Label B</text></svg>'
    )
    assert _svg_text_diagnostics(svg)["collisions"] == 0


def test_svg_diagnostics_detects_dejavu_default_font():
    svg = '<svg><text x="10" y="20" font-family="DejaVu Sans">x</text></svg>'
    assert _svg_text_diagnostics(svg)["dejavu"] is True
    svg2 = '<svg><text x="10" y="20" font-family="Helvetica">x</text></svg>'
    assert _svg_text_diagnostics(svg2)["dejavu"] is False


def test_audit_svg_missing_caption_blocks(tmp_path):
    fig = tmp_path / "fig_1.svg"
    fig.write_text('<svg><text x="0" y="0">ok</text></svg>')
    res = audit_figure_quality("fig_1.svg", tmp_path)
    assert res["status"] == "error"
    assert any("caption" in b.lower() for b in res["blockers"])


def test_audit_svg_overlap_warns(tmp_path):
    fig = tmp_path / "fig_1.svg"
    fig.write_text(
        '<svg><text x="10" y="20">Label A</text>'
        '<text x="12" y="22">Label B</text></svg>'
    )
    (tmp_path / "fig_1.caption.md").write_text("A caption.")
    res = audit_figure_quality("fig_1.svg", tmp_path)
    assert res["report"].get("svg_text_collisions_est", 0) >= 1
    assert any("overlap" in w.lower() for w in res["warnings"])


def test_audit_png_scans_svg_companion(tmp_path):
    # PNG-first project that keeps a vector companion → overlap still caught.
    (tmp_path / "fig_1.png").write_bytes(b"")  # empty PNG; PIL block tolerates
    (tmp_path / "fig_1.svg").write_text(
        '<svg><text x="10" y="20">Label A</text>'
        '<text x="12" y="22">Label B</text></svg>'
    )
    (tmp_path / "fig_1.caption.md").write_text("A caption.")
    res = audit_figure_quality("fig_1.png", tmp_path)
    assert res["report"].get("svg_text_collisions_est", 0) >= 1
