"""Dashboard content gates tests (numeric grounding, figure proximity,
substantiveness, accessibility, palette, reviewer simulator)."""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.audit.dashboard_content import (
    audit_accessibility,
    audit_color_palette,
    audit_dashboard_content,
    audit_figure_proximity,
    audit_numeric_grounding,
    audit_print_friendly,
    audit_section_substantiveness,
    reviewer_simulator,
)


def _scaffold(root: Path, table_csv: str = "value\n100\n42\n0.05\n") -> None:
    (root / "workspace" / "01_de" / "outputs" / "tables").mkdir(parents=True)
    (root / "workspace" / "01_de" / "outputs" / "tables" / "results.csv").write_text(table_csv)
    (root / "workspace" / "citations.md").write_text("@s2024 paper\n")


# ── numeric grounding ───────────────────────────────────────────────


def test_numeric_grounding_clean(tmp_path: Path):
    _scaffold(tmp_path)
    html = "<p>We found 42 cells in 100 samples (p < 0.05).</p>"
    res = audit_numeric_grounding(html, tmp_path)
    assert res["blockers"] == []


def test_numeric_grounding_hallucinated_number_blocks(tmp_path: Path):
    _scaffold(tmp_path)
    # 999 is not in the source corpus.
    html = "<p>We observed 999 weird widgets.</p>"
    res = audit_numeric_grounding(html, tmp_path)
    assert res["blockers"], res


def test_numeric_grounding_ignores_years(tmp_path: Path):
    _scaffold(tmp_path)
    html = "<p>Smith et al. (2024) reported.</p>"
    res = audit_numeric_grounding(html, tmp_path)
    assert res["blockers"] == []


# ── figure proximity ────────────────────────────────────────────────


def test_figure_proximity_with_caption_passes():
    html = (
        "<p>See Figure 1 — UMAP of cells.</p>"
        "<figure><img src='x.png'><figcaption>UMAP of all cells.</figcaption></figure>"
    )
    res = audit_figure_proximity(html)
    assert res["warnings"] == []


def test_figure_proximity_orphan_warns():
    # Put a figure with caption far from any text mention.
    html = (
        "<p>" + ("filler " * 500) + "</p>"
        "<figure><img src='x.png'><figcaption>Unmentioned plot.</figcaption></figure>"
        "<p>" + ("filler " * 500) + "</p>"
    )
    res = audit_figure_proximity(html)
    assert res["warnings"]


# ── substantiveness ─────────────────────────────────────────────────


def test_section_substantiveness_short_section_warns():
    html = '<section id="abstract"><h2>Abstract</h2><p>Too short.</p></section>'
    res = audit_section_substantiveness(html)
    assert any("abstract" in w.lower() and "min" in w.lower() for w in res["warnings"])


def test_section_substantiveness_abstract_without_number_blocks():
    html = (
        '<section id="abstract"><h2>Abstract</h2>'
        + "<p>" + ("words " * 200) + "</p>"
        + "</section>"
    )
    res = audit_section_substantiveness(html)
    assert any("abstract" in b.lower() and "number" in b.lower() for b in res["blockers"])


def test_section_substantiveness_cliches_warn():
    html = (
        '<section id="abstract"><h2>Abstract</h2>'
        + "<p>In this study, we investigate something." + (" words" * 200) + " We found 42%.</p>"
        + "</section>"
    )
    res = audit_section_substantiveness(html)
    assert any("cliché" in w.lower() or "cliche" in w.lower() for w in res["warnings"])


# ── accessibility ───────────────────────────────────────────────────


def test_accessibility_missing_alt_warns():
    html = "<img src='x.png'>"
    res = audit_accessibility(html)
    assert any("alt" in w.lower() for w in res["warnings"])


def test_accessibility_heading_skip_warns():
    html = "<h1>T</h1><h3>S</h3>"
    res = audit_accessibility(html)
    assert any("heading hierarchy skip" in w.lower() for w in res["warnings"])


def test_accessibility_low_contrast_warns():
    # #888 on #aaa is well below 4.5:1.
    html = (
        "<style>p { color: #888888; background: #aaaaaa; }</style>"
        "<p>Hello</p>"
    )
    res = audit_accessibility(html)
    assert any("contrast" in w.lower() for w in res["warnings"])


# ── print + palette + reviewer ──────────────────────────────────────


def test_print_friendly_missing_stylesheet_warns():
    res = audit_print_friendly("<html></html>")
    assert any("print" in w.lower() for w in res["warnings"])


def test_color_palette_okabe_ito_passes():
    html = "".join(f"<span style='color:{c}'>x</span>" for c in (
        "#000000", "#e69f00", "#56b4e9", "#009e73",
    ))
    res = audit_color_palette(html)
    assert res["warnings"] == []


def test_color_palette_random_palette_warns():
    html = "".join(f"<span style='color:#{i:06x}'>x</span>" for i in (
        0xff0000, 0x123abc, 0x88cc99, 0x778899, 0xa55522, 0xff8866, 0x44aacc
    ))
    res = audit_color_palette(html)
    assert res["warnings"]


def test_reviewer_simulator_buried_lede_flagged():
    html = "<p>" + (" general words " * 100) + "</p>"
    res = reviewer_simulator(html)
    assert res["would_5min_skimmer_get_finding"] is False
    assert res["suggested_top_of_page_callout"]


def test_reviewer_simulator_finding_lede_passes():
    html = "<p>We found a 42% reduction in 100 samples; demonstrate effect.</p>"
    res = reviewer_simulator(html)
    assert res["would_5min_skimmer_get_finding"] is True


# ── wrapper ─────────────────────────────────────────────────────────


def test_audit_dashboard_content_missing_file(tmp_path: Path):
    res = audit_dashboard_content(tmp_path)
    assert res["status"] == "error"


def test_audit_dashboard_content_combined(tmp_path: Path):
    _scaffold(tmp_path)
    (tmp_path / "synthesis").mkdir()
    html = (
        "<html><body>"
        '<section id="abstract"><h2>Abstract</h2>'
        + "<p>We found 42% in 100 cells.</p>" * 30
        + "</section>"
        '<section id="findings"><h2>Findings</h2><p>x</p></section>'
        "</body></html>"
    )
    (tmp_path / "synthesis" / "dashboard.html").write_text(html)
    res = audit_dashboard_content(tmp_path)
    assert "sub_reports" in res
    assert "numeric_grounding" in res["sub_reports"]


def test_accessibility_data_alt_does_not_satisfy_alt():
    """`data-alt=` must not satisfy the alt-text check; a real `alt=`
    must. (SYN-8)"""
    bad = audit_accessibility('<img src="x.png" data-alt="nope">')
    assert any("alt=" in w for w in bad["warnings"]), bad["warnings"]
    good = audit_accessibility('<img src="x.png" alt="real">')
    assert not any("alt=" in w for w in good["warnings"]), good["warnings"]


def test_dashboard_content_ignores_commented_markup(tmp_path: Path):
    """Markup inside <!-- ... --> is stripped before the content scans
    so a commented <img> doesn't trip the alt-text gate. (SYN-2)"""
    html = (
        "<html><body>"
        "<!-- <img src=commented.png> -->"
        '<img src="real.png" alt="a described figure">'
        "</body></html>"
    )
    (tmp_path / "synthesis").mkdir(parents=True)
    (tmp_path / "synthesis" / "dashboard.html").write_text(html)
    res = audit_dashboard_content(tmp_path)
    a11y = res["sub_reports"]["accessibility"]
    assert not any("alt=" in w for w in a11y["warnings"]), a11y["warnings"]
