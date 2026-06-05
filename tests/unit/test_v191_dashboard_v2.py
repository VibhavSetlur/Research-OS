"""Tests for the v2 single-page dashboard renderer (Theme 17)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.dashboard_v2 import (
    CUSTOM_ELEMENTS_JS,
    DASHBOARD_V2_CSS,
    _detect_capabilities,
    _build_search_index,
    bundled_js,
    render_dashboard_v2,
)


def _scaffold(root: Path,
              n_steps: int = 1,
              with_figure: bool = True,
              with_interactive: bool = False,
              with_mermaid: bool = False,
              with_plotly: bool = False,
              with_graphml: bool = False,
              spec_extra: dict | None = None) -> None:
    """Build a minimal but realistic project tree under ``root``."""
    (root / "synthesis").mkdir(parents=True, exist_ok=True)
    spec = {
        "title": "Test project",
        "abstract": "A short abstract for testing dashboard rendering.",
        "findings": [{"title": "F1", "summary": "Big finding here."}],
    }
    if spec_extra:
        spec.update(spec_extra)
    import yaml
    (root / "synthesis" / "synthesis_spec.yaml").write_text(yaml.safe_dump(spec))
    for i in range(1, n_steps + 1):
        step = root / "workspace" / f"{i:02d}_demo"
        step.mkdir(parents=True)
        (step / "conclusions.md").write_text(
            "## Plain-language summary\nWe ran step "
            f"{i} and got results.\n"
            "## Findings\n- Headline finding for step "
            f"{i}\n## Decision\nproceed\n"
        )
        if with_figure:
            figs = step / "outputs" / "figures"
            figs.mkdir(parents=True)
            (figs / f"{i:02d}_volcano.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
            if with_interactive:
                (figs / f"{i:02d}_volcano.html").write_text("<html>interactive</html>")
            (figs / f"{i:02d}_volcano.caption.md").write_text("Volcano caption.")
            (figs / f"{i:02d}_volcano.summary.md").write_text("Volcano summary.")
        if with_mermaid:
            (step / "pipeline.mermaid").write_text("graph LR; A-->B")
        if with_plotly:
            (step / "outputs" / "figures" / "f.plotly.json").write_text("{}")
        if with_graphml:
            (step / "outputs" / "figures" / f"{i:02d}_net.graphml").write_text(
                '<?xml version="1.0"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns">'
                '<graph><node id="A"/><node id="B"/><edge source="A" target="B"/></graph>'
                '</graphml>'
            )


# ──────────────────────────────────────────────────────────────────────
# Vendor / bundle loader
# ──────────────────────────────────────────────────────────────────────


def test_vendored_bundles_present():
    """Every bundle named in MANIFEST.json must exist on disk."""
    base = Path(__file__).resolve().parents[2] / "src" / "research_os" / "assets" / "js"
    manifest = json.loads((base / "MANIFEST.json").read_text())
    for name in manifest["bundles"]:
        p = base / name
        assert p.exists(), f"missing vendored bundle {name}"
        assert p.stat().st_size > 1024, f"bundle {name} suspiciously small"


def test_vendored_licenses_present():
    base = Path(__file__).resolve().parents[2] / "src" / "research_os" / "assets" / "js" / "licenses"
    for name in ("minisearch", "vega", "vega-lite", "vega-embed",
                 "plotly", "mermaid", "vis-network"):
        assert (base / f"{name}.LICENSE.txt").exists(), f"missing license {name}"
    assert (base / "NOTICE.md").exists()


def test_detect_capabilities_empty(tmp_path: Path):
    caps = _detect_capabilities(tmp_path)
    assert caps == {"has_plotly": False, "has_mermaid": False, "has_network": False}


def test_detect_capabilities_mermaid(tmp_path: Path):
    _scaffold(tmp_path, with_mermaid=True)
    assert _detect_capabilities(tmp_path)["has_mermaid"] is True


def test_detect_capabilities_plotly_and_network(tmp_path: Path):
    _scaffold(tmp_path, with_plotly=True, with_graphml=True)
    caps = _detect_capabilities(tmp_path)
    assert caps["has_plotly"] and caps["has_network"]


def test_bundled_js_minimal(tmp_path: Path):
    _scaffold(tmp_path)
    blob, included = bundled_js(tmp_path)
    # MiniSearch + Vega-family + custom elements always included.
    assert "minisearch.min.js" in included
    assert "vega.min.js" in included
    assert "vega-lite.min.js" in included
    assert "vega-embed.min.js" in included
    assert "ro-custom-elements" in included
    # Conditionals NOT included
    assert "plotly.min.js" not in included
    assert "mermaid.min.js" not in included
    assert "vis-network.min.js" not in included
    assert len(blob) > 100_000  # vega + vega-lite alone are ~750 KB


def test_bundled_js_conditional_loaded(tmp_path: Path):
    _scaffold(tmp_path, with_mermaid=True, with_plotly=True, with_graphml=True)
    _, included = bundled_js(tmp_path)
    assert "plotly.min.js" in included
    assert "mermaid.min.js" in included
    assert "vis-network.min.js" in included


# ──────────────────────────────────────────────────────────────────────
# Renderer
# ──────────────────────────────────────────────────────────────────────


def test_renderer_basic_success(tmp_path: Path):
    _scaffold(tmp_path, n_steps=2)
    res = render_dashboard_v2(tmp_path)
    assert res["status"] == "success"
    assert res["renderer"] == "v2"
    assert res["steps"] == 2
    assert (tmp_path / "synthesis" / "dashboard.html").exists()
    assert res["size_kb"] > 100


def test_rendered_html_has_custom_elements(tmp_path: Path):
    _scaffold(tmp_path, with_interactive=True)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    for tag in ("ro-sidebar", "ro-search", "ro-filter", "ro-figure-toggle",
                "ro-table", "ro-mode-toggle"):
        assert f"<{tag}" in html, f"<{tag}> missing from rendered HTML"


def test_rendered_html_no_external_urls_in_src_href(tmp_path: Path):
    """Offline-only: no <script src=https://...> or <link href=https://...>."""
    _scaffold(tmp_path)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    bad = re.findall(r'(?:src|href)\s*=\s*["\']https?://[^"\']+["\']', html)
    assert not bad, f"external src/href found: {bad[:3]}"


def test_rendered_html_has_meta_renderer_v2(tmp_path: Path):
    _scaffold(tmp_path)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert '<meta name="ro-renderer" content="v2">' in html


def test_renderer_default_mode_respected(tmp_path: Path):
    _scaffold(tmp_path)
    render_dashboard_v2(tmp_path, default_mode="story")
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert '<meta name="ro-default-mode" content="story">' in html
    assert 'default="story"' in html


def test_renderer_search_disabled_drops_index(tmp_path: Path):
    _scaffold(tmp_path)
    res = render_dashboard_v2(tmp_path, search_enabled=False)
    assert res["search_enabled"] is False
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    # The index script must be absent (the JS querySelector reference
    # inside the inlined custom-elements bundle is allowed; it just
    # finds nothing to wire up).
    assert '<script type="application/x-ro-search-index">' not in html
    # Header must NOT instantiate the search element.
    head_to_main = html.split("<main", 1)[0]
    assert "<ro-search>" not in head_to_main


def test_renderer_print_optimized_toggle(tmp_path: Path):
    _scaffold(tmp_path)
    render_dashboard_v2(tmp_path, print_optimized=False)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    # Without print css the @media print block is gone.
    assert "@media print" not in html


def test_search_index_includes_step_content(tmp_path: Path):
    _scaffold(tmp_path, n_steps=3)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    m = re.search(
        r'<script type="application/x-ro-search-index">(.*?)</script>',
        html, re.DOTALL,
    )
    assert m, "search index script missing"
    docs = json.loads(m.group(1).replace("<\\/", "</"))
    titles = {d.get("title") for d in docs}
    assert "Abstract" in titles
    # At least one step title
    assert any(t and t.startswith("0") for t in titles)


def test_figure_toggle_has_both_static_and_interactive(tmp_path: Path):
    _scaffold(tmp_path, with_interactive=True)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert 'interactive-src=' in html
    # The toggle element renders the tabs in JS; the data attrs are present:
    assert 'static-src=' in html


def test_figure_toggle_only_static_when_no_companion(tmp_path: Path):
    _scaffold(tmp_path, with_interactive=False)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    # interactive-src is still emitted (as empty) — verify
    assert re.search(r'interactive-src="\s*"', html), "expected empty interactive-src"


def test_verdicts_section_renders_as_ro_table(tmp_path: Path):
    _scaffold(tmp_path)
    # Use the ResearchLedger lifecycle so the dashboard's _load_state
    # picks it up via load_state(root).
    from research_os.state.state_ledger import ResearchLedger
    rl = ResearchLedger(tmp_path / ".os_state" / "state_ledger.json")
    data = rl._load()
    data["active_hypotheses"] = [
        {"id": "H1", "text": "demo hypothesis", "status": "supported"},
        {"id": "H2", "text": "another", "status": "refuted"},
    ]
    rl._save(data)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert '<ro-table name="verdicts">' in html
    assert "H1" in html and "H2" in html


def test_sidebar_lists_steps(tmp_path: Path):
    _scaffold(tmp_path, n_steps=3)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    for i in range(1, 4):
        assert f"#step-0{i}-demo" in html or f"#step-{i:02d}-demo" in html


def test_filter_chips_have_status_keys(tmp_path: Path):
    _scaffold(tmp_path)
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert 'data-key="status:completed"' in html or 'data-key="status:active"' in html


def test_renderer_records_commit_hash_when_git_present(tmp_path: Path):
    _scaffold(tmp_path)
    git_dir = tmp_path / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "refs" / "heads" / "main").write_text("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert "deadbeefdead" in html  # first 12 chars in footer


def test_renderer_returns_js_bundles_list(tmp_path: Path):
    _scaffold(tmp_path)
    res = render_dashboard_v2(tmp_path)
    assert "minisearch.min.js" in res["js_bundles"]
    assert "ro-custom-elements" in res["js_bundles"]


# ──────────────────────────────────────────────────────────────────────
# Static asset sanity
# ──────────────────────────────────────────────────────────────────────


def test_custom_elements_define_all_eight(tmp_path: Path):
    """All eight <ro-*> custom elements must be registered in the JS."""
    needed = ["ro-mode-toggle", "ro-sidebar", "ro-search", "ro-filter",
              "ro-figure-toggle", "ro-table", "ro-brush-link",
              "ro-vega", "ro-plotly", "ro-mermaid", "ro-jump-to"]
    for tag in needed:
        assert f"customElements.define('{tag}'" in CUSTOM_ELEMENTS_JS, f"<{tag}> not defined"


def test_css_includes_print_stylesheet():
    assert "@media print" in DASHBOARD_V2_CSS


def test_css_includes_dark_mode_block():
    assert "prefers-color-scheme: dark" in DASHBOARD_V2_CSS


def test_search_index_builder_produces_documents():
    spec = {"abstract": "An abstract.", "findings": [{"title": "F1", "summary": "Hi."}]}
    docs = _build_search_index([], spec, [])
    assert any(d["title"] == "Abstract" for d in docs)
    assert any(d["title"] == "F1" for d in docs)


def test_search_index_handles_empty_inputs():
    assert _build_search_index([], {}, []) == []


# ──────────────────────────────────────────────────────────────────────
# Server handler integration
# ──────────────────────────────────────────────────────────────────────


def test_tool_dashboard_create_legacy_flag_routes_to_v1(tmp_path: Path, monkeypatch):
    _scaffold(tmp_path)
    from research_os import server
    monkeypatch.chdir(tmp_path)
    # default (no legacy) → v2
    out = server._handle_tool_dashboard_create(
        "tool_dashboard_create", {}, tmp_path,
    )
    text = out[0].text if hasattr(out[0], "text") else str(out)
    assert '"renderer": "v2"' in text or '"v2"' in text
    # legacy=true → v1 (no renderer field)
    out2 = server._handle_tool_dashboard_create(
        "tool_dashboard_create", {"dashboard_legacy": True}, tmp_path,
    )
    text2 = out2[0].text if hasattr(out2[0], "text") else str(out2)
    assert '"renderer": "v2"' not in text2
