"""3.2.8 — the design audit: reviews STYLISTIC choices of a deliverable.

Covers the new dashboard / poster / figure design checks plus the Wave-0
audit-staleness fixes (removed per_step/audit sections, neon+restraint colour
judgement, size-aware poster font floor).

The load-bearing guard in this file is the FALSE-POSITIVE guard: a clean
scaffolded dashboard (every archetype) and a custom-but-professional palette
must NOT trip the design audit. A design lint that wrongly refuses a good
deliverable is worse than no lint.
"""
from __future__ import annotations

from pathlib import Path

import research_os.tools.actions.audit.dashboard_content as D
from research_os.tools.actions.synthesis import scaffold as S
from research_os.tools.actions.synthesis.check import _check_poster
from research_os.tools.actions.viz.figures import audit_figure_style


# ===========================================================================
# Wave-0: audit-staleness fixes
# ===========================================================================


def test_per_step_and_audit_sections_removed():
    """The per_step + audit sections rewarded the banned per-step recap; they
    are gone from both the expected-section list and the substantiveness bars."""
    assert "per_step" not in D.DASHBOARD_SECTIONS
    assert "audit" not in D.DASHBOARD_SECTIONS
    assert "per_step" not in D.SECTION_BARS
    assert "audit" not in D.SECTION_BARS


def test_color_audit_is_quality_not_membership():
    """audit_color_palette judges quality (neon + restraint), not membership —
    a custom-but-professional clinical palette passes; neon blocks."""
    clinical = (
        "<style>.p{color:#2B5F8C}.a{color:#2A7F7B}.n{color:#B3401F}</style>"
    )
    res = D.audit_color_palette(clinical)
    assert res["blockers"] == []
    assert res["warnings"] == []

    neon = "<style>.x{color:#00ff00}.y{color:#ff00ff}</style>"
    res2 = D.audit_color_palette(neon)
    assert any("neon" in b.lower() for b in res2["blockers"])


def test_color_audit_warns_on_rainbow_restraint():
    """Many distinct off-palette hues → restraint warning (not a block)."""
    many = "<style>" + "".join(
        f".c{i}{{color:#{h}}}" for i, h in enumerate(
            ("1166aa", "aa6611", "66aa11", "8811aa", "11aaaa", "aa1166")
        )
    ) + "</style>"
    res = D.audit_color_palette(many)
    assert res["blockers"] == []  # none are neon
    assert any("restraint" in w.lower() or "palette" in w.lower() for w in res["warnings"])


def test_color_audit_scans_chrome_style_block():
    """The colour audit must SEE the <style> chrome (neon set in CSS blocks)."""
    html = "<style>:root{--accent:#00ff00}</style><body><p>x</p></body>"
    res = D.audit_color_palette(html)
    assert any("neon" in b.lower() for b in res["blockers"])


def test_color_audit_ignores_script_hex_literals():
    """Hex literals inside <script> are vendored JS, not design choices."""
    html = "<script>var c='#00ff00'; // neon literal in JS</script><p>x</p>"
    res = D.audit_color_palette(html)
    assert res["blockers"] == []


def test_poster_font_floor_is_size_aware():
    """The misleading flat 14pt floor is gone: a 16pt body on a full poster now
    trips (was silently passing), but 28pt does not."""
    tiny = _check_poster('#set text(size: 16pt)\n= A\n= B\n= C\n')
    assert 16.0 in tiny["hardcoded_font_pt"]
    ok = _check_poster('#set text(size: 28pt)\n= A\n= B\n= C\n')
    assert ok["hardcoded_font_pt"] == []


# ===========================================================================
# False-positive guard — the load-bearing test
# ===========================================================================


def _design_issues(html: str) -> dict[str, tuple[list, list]]:
    """Run every dashboard design check on comment-stripped HTML; return only
    the checks that produced a blocker or warning."""
    html = D._strip_html_comments(html)
    checks = {
        "palette": D.audit_color_palette(html),
        "scroll": D.scroll_budget_estimate(html),
        "nav": D.in_page_nav_required(html),
        "recap": D.per_step_recap_headings(html),
        "leaks": D.workspace_path_and_tool_leaks(html),
        "density": D.section_count_and_density_budget(html),
        "figcaps": D.uncaptioned_or_label_only_figures(html),
        "cvd": D.color_not_sole_channel(html),
        "offline": D.self_contained_offline(html),
        "archetype": D.archetype_declared_and_consistent(html),
    }
    return {
        k: (v.get("blockers", []), v.get("warnings", []))
        for k, v in checks.items()
        if v.get("blockers") or v.get("warnings")
    }


def test_clean_scaffold_single_viewport_brief_no_design_issues():
    issues = _design_issues(S._compose_dashboard("single-viewport-brief"))
    assert issues == {}, issues


def test_clean_scaffold_scroll_lite_narrative_no_design_issues():
    issues = _design_issues(S._compose_dashboard("scroll-lite-narrative"))
    assert issues == {}, issues


def test_clean_scaffold_all_archetypes_no_design_blockers():
    """Every archetype × palette must produce ZERO design blockers."""
    for arch in S.DASHBOARD_ARCHETYPES:
        for pal in (None, "clinical", "okabe_ito"):
            html = D._strip_html_comments(S._compose_dashboard(arch, pal))
            for check in (
                D.scroll_budget_estimate, D.per_step_recap_headings,
                D.workspace_path_and_tool_leaks, D.self_contained_offline,
                D.audit_color_palette,
            ):
                blk = check(html).get("blockers", [])
                assert blk == [], f"{arch}/{pal}: {check.__name__} blocked: {blk}"


def test_custom_clinical_palette_dashboard_passes_color_audit():
    """A custom-but-professional palette (clinical) must PASS the colour audit
    — no neon, no spurious off-palette restraint warning."""
    html = D._strip_html_comments(S._compose_dashboard("scroll-lite-narrative", "clinical"))
    res = D.audit_color_palette(html, declared_palette="clinical")
    assert res["blockers"] == []
    assert res["warnings"] == []


# ===========================================================================
# Dashboard design checks — block / warn fixtures
# ===========================================================================


_NEON_RAINBOW_STEP_DASHBOARD = (
    '<style>.x{color:#00ff00}.y{color:#ff00ff}.z{color:#ff0000}.a{color:#00ffff}</style>'
    '<body data-archetype="single-viewport-brief">'
    + "".join(
        f'<section id="s{i}"><h2>Step 0{i} — phase {i}</h2>'
        f'<p>see workspace/0{i}_eda/conclusions.md and run tool_audit_step.</p></section>'
        for i in range(1, 10)
    )
    + "</body>"
)


def test_neon_blocks():
    res = D.audit_color_palette(_NEON_RAINBOW_STEP_DASHBOARD)
    assert any("neon" in b.lower() for b in res["blockers"])


def test_endless_scroll_blocks():
    res = D.scroll_budget_estimate(_NEON_RAINBOW_STEP_DASHBOARD)
    assert res["blockers"]


def test_per_step_recap_blocks_at_three():
    res = D.per_step_recap_headings(_NEON_RAINBOW_STEP_DASHBOARD)
    assert res["blockers"]
    # 1-2 step headings warn, not block.
    two = '<h2>Step 01</h2><h2>Step 02</h2>'
    res2 = D.per_step_recap_headings(two)
    assert res2["blockers"] == []
    assert res2["warnings"]


def test_generic_container_headings_warn():
    html = "<h2>Overview</h2><h2>Results</h2><h2>Conclusion</h2>"
    res = D.per_step_recap_headings(html)
    assert any("container" in w.lower() for w in res["warnings"])


def test_workspace_and_tool_leaks_block():
    res = D.workspace_path_and_tool_leaks(_NEON_RAINBOW_STEP_DASHBOARD)
    assert res["blockers"]
    leaks_lower = " ".join(res["leaks"]).lower()
    assert "workspace/" in leaks_lower or "conclusions.md" in leaks_lower


def test_tool_name_leak_blocks():
    res = D.workspace_path_and_tool_leaks("<p>then call tool_audit_step to verify.</p>")
    assert res["blockers"]


def test_buried_lede_blocks():
    html = (
        '<section id="background"><h2>Background</h2>'
        '<p>' + ("context " * 50) + '</p></section>'
    )
    res = D.hero_answers_in_first_viewport(html)
    assert res["blockers"]


def test_hero_with_number_and_verb_passes():
    html = (
        '<section id="headline"><h2>Headline finding</h2>'
        '<p>Reranking lifted hits@10 by 5.9pp over the baseline.</p></section>'
    )
    res = D.hero_answers_in_first_viewport(html)
    assert res["blockers"] == []
    assert res["has_hero_section"] and res["number_in_lede"] and res["finding_verb_in_lede"]


def test_uncaptioned_figure_blocks():
    html = '<figure><img src="x.png" alt="a"></figure>'
    res = D.uncaptioned_or_label_only_figures(html)
    assert res["blockers"]


def test_label_only_caption_warns():
    html = '<figure><img src="x.png" alt="a"><figcaption>Figure 3: accuracy</figcaption></figure>'
    res = D.uncaptioned_or_label_only_figures(html)
    assert res["warnings"]


def test_interpretive_caption_passes():
    html = (
        '<figure><img src="x.png" alt="a"><figcaption>Reranking lifted hits@10 '
        'by 5.9pp; the gain concentrates in long-tail queries.</figcaption></figure>'
    )
    res = D.uncaptioned_or_label_only_figures(html)
    assert res["blockers"] == [] and res["warnings"] == []


def test_color_only_delta_warns():
    html = '<span class="delta up">+5</span><span class="delta down">12</span>'
    res = D.color_not_sole_channel(html)
    # The down delta has no sign/word → warn.
    assert res["warnings"]


def test_color_delta_with_sign_passes():
    html = '<span class="delta up">+5 (better)</span><span class="delta down">-12 (worse)</span>'
    res = D.color_not_sole_channel(html)
    assert res["warnings"] == []


def test_network_dependency_blocks():
    for html in (
        '<script src="https://cdn.example.com/x.js"></script>',
        '<link href="https://fonts.googleapis.com/x" rel="stylesheet">',
        '<style>@import url(https://x.com/y.css);</style>',
        '<img src="https://example.com/fig.png">',
    ):
        res = D.self_contained_offline(html)
        assert res["blockers"], html


def test_offline_dashboard_passes():
    res = D.self_contained_offline('<img src="figures/01.png" alt="x"><link href="style.css">')
    assert res["blockers"] == []


def test_archetype_missing_stamp_warns():
    res = D.archetype_declared_and_consistent("<body><section></section></body>")
    assert any("data-archetype" in w for w in res["warnings"])


def test_archetype_mismatch_warns():
    # Declares brief but has a nav + many sections.
    html = (
        '<body data-archetype="single-viewport-brief"><nav></nav>'
        + "".join(f'<section id="s{i}"></section>' for i in range(5))
        + "</body>"
    )
    res = D.archetype_declared_and_consistent(html)
    assert res["consistent"] is False
    assert res["warnings"]


def test_in_page_nav_required_for_narrative():
    html = (
        '<body data-archetype="scroll-lite-narrative">'
        + "".join(f'<section id="s{i}"><h2>Claim {i}</h2></section>' for i in range(5))
        + "</body>"
    )
    res = D.in_page_nav_required(html)
    assert res["warnings"]  # no anchors / nav


# ===========================================================================
# Poster design checks
# ===========================================================================


def test_poster_single_headline_present():
    two = (
        '#headline[A first finding]\n#headline[A second finding]\n'
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(two)
    assert any("exactly one" in w.lower() for w in res["warnings"])


def test_poster_headline_is_a_finding_warns_on_topic():
    text = (
        '#headline[A study of reranking methods]\n'
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("topic" in w.lower() for w in res["warnings"])


def test_poster_headline_finding_passes():
    text = (
        '#headline[Reranking lifted hits@10 by 5.9pp]\n'
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert not any("topic" in w.lower() for w in res["warnings"])


def test_poster_too_many_sections_warns():
    text = "".join(f'#block-section(title:"S{i}")[]\n' for i in range(9))
    res = _check_poster(text)
    assert any("directory" in w.lower() for w in res["warnings"])


def test_poster_internal_step_leak_blocks():
    text = (
        '#block-section(title:"A")[see step 4 and workspace/03_eda/x]\n'
        '#block-section(title:"B")[]\n#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("workspace reference" in b.lower() for b in res["blockers"])


def test_poster_density_blocks_over_budget():
    big = "word " * 1400
    text = (
        f'#block-section(title:"A")[{big}]\n'
        '#block-section(title:"B")[]\n#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("budget" in b.lower() for b in res["blockers"])


def test_poster_qr_and_contact_nudge():
    text = (
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("contact" in w.lower() for w in res["warnings"])


def test_poster_portrait_geometry_warns_on_three_columns():
    text = (
        '#show: poster.with(size: "36x48", columns-n: 3)\n'
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("portrait" in w.lower() for w in res["warnings"])


def test_poster_figure_uncaptioned_warns():
    text = (
        '#poster-figure(path: "figures/f.png")\n'
        '#block-section(title:"A")[]\n#block-section(title:"B")[]\n'
        '#block-section(title:"C")[]\n'
    )
    res = _check_poster(text)
    assert any("without a caption" in w.lower() for w in res["warnings"])


# ===========================================================================
# Figure design checks
# ===========================================================================


def _fig_root(tmp_path: Path, bound: str = "synthesis") -> Path:
    (tmp_path / bound / "figures").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_figure_banned_colormap_blocks(tmp_path: Path):
    root = _fig_root(tmp_path)
    sc = root / "synthesis" / "scripts"
    sc.mkdir(parents=True)
    (sc / "fig.py").write_text('plt.imshow(z, cmap="turbo")')
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><text>x (m)</text><text>y (m)</text></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text("Field peaks centrally.")
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert any("colormap" in b.lower() for b in res["blockers"])


def test_figure_missing_axis_text_blocks(tmp_path: Path):
    root = _fig_root(tmp_path)
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><path stroke="#1f4d7a" d="M0 0"/></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text("Trend rose 5pp.")
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert any("no text" in b.lower() or "axis" in b.lower() for b in res["blockers"])


def test_figure_raw_column_axis_warns(tmp_path: Path):
    root = _fig_root(tmp_path)
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><text>body_mass_g</text><text>flipper_length_mm</text>'
        '<path stroke="#1f4d7a"/></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text("Heavier birds had longer flippers.")
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert any("raw column" in w.lower() for w in res["warnings"])


def test_figure_caption_mechanics_warns(tmp_path: Path):
    root = _fig_root(tmp_path)
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><text>Mass (g)</text><text>Length (mm)</text><path stroke="#1f4d7a"/></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text(
        "Scatter plot of mass against length."
    )
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert any("mechanics" in w.lower() for w in res["warnings"])


def test_figure_internal_leak_blocks_for_synthesis(tmp_path: Path):
    root = _fig_root(tmp_path)
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><text>Mass (g)</text><text>Length (mm)</text></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text(
        "Generated from workspace/03_eda/out.csv in step 3."
    )
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert any("internal reference" in b.lower() for b in res["blockers"])


def test_clean_figure_passes(tmp_path: Path):
    root = _fig_root(tmp_path)
    (root / "synthesis" / "figures" / "fig.svg").write_text(
        '<svg><text>Accuracy (%)</text><text>Training epoch</text>'
        '<path stroke="#1f4d7a" d="M0 0 L10 10"/></svg>'
    )
    (root / "synthesis" / "figures" / "fig.caption.md").write_text(
        "**Figure 1.** Accuracy rose 5.9pp over baseline by epoch 30."
    )
    res = audit_figure_style("synthesis/figures/fig.svg", root)
    assert res["blockers"] == []
    assert res["warnings"] == []
