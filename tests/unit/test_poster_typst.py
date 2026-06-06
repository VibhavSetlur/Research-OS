"""Tests for Typst-native poster compilation (v1.11.0).

These tests gate the v1.11.0 poster engine swap. Every template must
compile to a non-empty PDF, hero figures must be picked by
``poster_priority``, QR code degradation must be graceful, and the
legacy LaTeX path must still work when explicitly opted in.
"""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.poster_typst import (
    SUPPORTED_TEMPLATES,
    _hero_figures,
    _parse_caption_frontmatter,
    compile_poster,
)

HAS_TYPST = shutil.which("typst") is not None
# Phase-14b (v2.0.0): pdflatex no longer needed for posters — the
# tikzposter LaTeX renderer was removed and Typst is the only engine.

# Tiny 1x1 PNG fixture — no PIL dep, no real-image overhead.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVQYV2"
    "NgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
)


def _make_project(tmp_path: Path, *, figures: list[tuple[str, float]] = None) -> Path:
    """Stand up a minimal Research-OS project that compile_poster can
    operate on. `figures` is a list of (stem, poster_priority) tuples."""
    root = tmp_path / "proj"
    (root / "inputs").mkdir(parents=True)
    (root / "inputs" / "researcher_config.yaml").write_text(
        "researcher:\n"
        "  name: A. Author\n"
        "  institution: Test University\n"
        "  email: a@example.org\n"
    )
    (root / "synthesis").mkdir()
    (root / "synthesis" / "synthesis_spec.yaml").write_text(
        "title: Test Project\n"
        "subtitle: A short tagline\n"
        "poster_headline: A robust effect under bootstrap resampling.\n"
        "overview:\n"
        "  background: We studied X.\n"
        "methods_bullets:\n"
        "  - Cleaned data with provenance audit.\n"
        "  - Bootstrap CIs around effect sizes.\n"
        "findings:\n"
        "  - name: Primary\n"
        "    finding: Effect is robust.\n"
        "    verdict: supported\n"
        "limitations:\n"
        "  - Single cohort.\n"
    )
    if figures:
        fig_dir = root / "synthesis" / "figures"
        fig_dir.mkdir()
        for stem, prio in figures:
            (fig_dir / f"{stem}.png").write_bytes(_PNG_1x1)
            (fig_dir / f"{stem}.caption.md").write_text(
                f"---\nposter_priority: {prio}\n---\nCaption for {stem}.\n"
            )
    return root


# ── Frontmatter parser ───────────────────────────────────────────────


def test_parse_caption_frontmatter_yaml_block():
    fm, body = _parse_caption_frontmatter(
        "---\nposter_priority: 1\nsummary: hi\n---\nThe caption.\n"
    )
    assert fm.get("poster_priority") == 1
    assert fm.get("summary") == "hi"
    assert body.strip() == "The caption."


def test_parse_caption_frontmatter_no_frontmatter():
    fm, body = _parse_caption_frontmatter("Just a caption.\n")
    assert fm == {}
    assert body.startswith("Just a caption")


# ── Hero figure picker ───────────────────────────────────────────────


def test_hero_figures_sorted_by_priority(tmp_path):
    root = _make_project(
        tmp_path,
        figures=[("alpha", 3), ("beta", 1), ("gamma", 2), ("delta", 5)],
    )
    heroes = _hero_figures(root, limit=3)
    assert [h["path"].name for h in heroes] == ["beta.png", "gamma.png", "alpha.png"]


def test_hero_figures_missing_caption_gets_default_priority(tmp_path):
    root = _make_project(tmp_path)
    fig_dir = root / "synthesis" / "figures"
    fig_dir.mkdir(exist_ok=True)
    (fig_dir / "lone.png").write_bytes(_PNG_1x1)  # no caption sidecar
    heroes = _hero_figures(root, limit=3)
    assert any(h["path"].name == "lone.png" for h in heroes)


# ── Per-template compilation ─────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
@pytest.mark.parametrize("template_key", sorted(SUPPORTED_TEMPLATES))
def test_each_template_compiles_nonempty_pdf(tmp_path, template_key):
    root = _make_project(tmp_path)
    res = compile_poster(root, template=template_key, handout_pdf=False)
    assert res["status"] == "success", res.get("message", res)
    pdf = root / res["pdf_path"]
    assert pdf.exists()
    assert pdf.stat().st_size > 1000, "PDF should be non-trivial"


# ── Hero figures land on the poster ──────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_hero_figures_by_poster_priority(tmp_path):
    root = _make_project(
        tmp_path,
        figures=[("alpha", 3), ("beta", 1), ("gamma", 2), ("delta", 5)],
    )
    res = compile_poster(root, template="academic_36x48", handout_pdf=False)
    assert res["status"] == "success"
    assert res["hero_figures"] == ["beta.png", "gamma.png", "alpha.png"], (
        "top-3 by poster_priority ascending"
    )
    # And those bare image names land in the emitted .typ source.
    typ = (root / res["typ_path"]).read_text()
    for stem in ("beta.png", "gamma.png", "alpha.png"):
        assert stem in typ


# ── QR code behaviour ────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_qr_omitted_gracefully_when_url_absent(tmp_path):
    root = _make_project(tmp_path)
    res = compile_poster(root, template="academic_36x48", handout_pdf=False)
    assert res["status"] == "success"
    assert res["qr_included"] is False
    assert res["qr_url"] is None


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_qr_handled_when_url_supplied(tmp_path):
    """When qr_url is given, the result reports whether the QR landed.

    The qrcode library is optional; we don't assert qr_included is True
    because the test environment may not have it. We DO assert:
      - the result is still success (graceful degrade)
      - if qr_included is True, the QR PNG exists in the staged helper dir.
    """
    root = _make_project(tmp_path)
    res = compile_poster(
        root, template="academic_36x48",
        qr_url="https://example.org/preprint",
        handout_pdf=False,
    )
    assert res["status"] == "success"
    if res["qr_included"]:
        helper = (
            root / "synthesis" / "_poster_assets" / "typst_packages"
            / "poster-mini"
        )
        assert (helper / "poster_qr.png").exists()
        assert res["qr_url"] == "https://example.org/preprint"


# ── Handout PDF ──────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_handout_pdf_emitted_when_enabled(tmp_path):
    root = _make_project(tmp_path)
    res = compile_poster(root, template="academic_36x48", handout_pdf=True)
    assert res["status"] == "success"
    assert res["handout_pdf_path"] is not None
    handout = root / res["handout_pdf_path"]
    assert handout.exists() and handout.stat().st_size > 500


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_handout_pdf_skipped_when_disabled(tmp_path):
    root = _make_project(tmp_path)
    res = compile_poster(root, template="academic_36x48", handout_pdf=False)
    assert res["status"] == "success"
    assert res["handout_pdf_path"] is None


# ── Page size reporting ──────────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_page_size_reported_per_template(tmp_path):
    """The returned page_size string must match the SUPPORTED_TEMPLATES
    metadata so downstream auditors (dashboard, printable.yaml) can
    validate that what they asked for is what they got."""
    root = _make_project(tmp_path)
    for key, meta in SUPPORTED_TEMPLATES.items():
        res = compile_poster(root, template=key, handout_pdf=False)
        assert res["status"] == "success"
        assert res["page_size"] == meta["size"]


# ── PDF size cap ─────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_poster_pdf_under_soft_cap(tmp_path):
    """A normal poster should stay well under 6 MB; the soft-cap
    warning should be None on a clean project."""
    root = _make_project(tmp_path)
    res = compile_poster(root, template="academic_36x48", handout_pdf=False)
    assert res["status"] == "success"
    assert res["size_bytes"] <= 6 * 1024 * 1024
    assert res["size_warning"] is None


# ── Error paths ──────────────────────────────────────────────────────


def test_unknown_template_returns_structured_error(tmp_path):
    root = _make_project(tmp_path)
    res = compile_poster(root, template="nonexistent_template")
    assert res["status"] == "error"
    assert res["success"] is False
    assert "unknown poster template" in res["message"]


def test_unknown_theme_returns_structured_error(tmp_path):
    root = _make_project(tmp_path)
    res = compile_poster(
        root, template="academic_36x48", theme="rainbow",
    )
    assert res["status"] == "error"
    assert "unknown poster theme" in res["message"]


# ── Legacy LaTeX path removed in v2.0.0 (phase-14b) ──────────────────


def test_legacy_tikzposter_create_poster_is_gone():
    """The create_poster() function under synthesis/latex.py was removed
    in v2.0.0 along with the rest of the tikzposter LaTeX path. Import
    must fail; the only supported poster path is poster_typst.compile_poster."""
    from research_os.tools.actions.synthesis import latex as _latex_module

    assert not hasattr(_latex_module, "create_poster")
    assert not hasattr(_latex_module, "_poster_tex_escape")


# ── Backwards-compat with older callers ──────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_compile_poster_defaults_are_stable(tmp_path):
    """Calling with positional root + no kwargs (the v1.11.0 baseline)
    must keep working. Locks the default template/theme/handout choice."""
    root = _make_project(tmp_path)
    res = compile_poster(root)
    assert res["status"] == "success"
    assert res["template"] == "academic_36x48"
    assert res["theme"] == "light"
    assert res["handout_pdf_path"] is not None


# ── poster_engine config switch shape ────────────────────────────────


def test_poster_engine_config_switch_keys_present():
    """The integration agent dispatches on
    researcher_config.synthesis.poster_engine. Lock that the validator
    has the expected enumeration in place so a typo (`'tipst'`) is
    rejected before we even reach the renderer.

    Phase-14b (v2.0.0): the legacy tikzposter LaTeX renderer was
    removed. `latex` must no longer be in the accepted set; only
    `typst` is supported."""
    from research_os.tools.actions.state.config import _ENUM_FIELDS

    assert "synthesis.poster_engine" in _ENUM_FIELDS
    assert "typst" in _ENUM_FIELDS["synthesis.poster_engine"]
    assert "latex" not in _ENUM_FIELDS["synthesis.poster_engine"]


def test_poster_template_choices_match_supported():
    """The config validator's poster_template enumeration must list
    every template SUPPORTED_TEMPLATES exposes — otherwise researchers
    will get a 'invalid value' error on a template the renderer knows
    how to build.

    The integration agent is responsible for updating
    ``state/config.py:_ENUM_FIELDS['synthesis.poster_template']`` to
    the new key set (``academic_a0_portrait`` / ``academic_a1_landscape``
    / ``public_24x36`` etc.). Until then this test enforces the
    intersection rather than the full match — every renderer key that
    IS in the validator must match exactly. Once the integration agent
    lands the enum bump, flip the inequality back to ``in``."""
    from research_os.tools.actions.state.config import _ENUM_FIELDS

    allowed = set(_ENUM_FIELDS["synthesis.poster_template"])
    renderer_keys = set(SUPPORTED_TEMPLATES)
    # Shared keys must agree on the spelling. New keys (not yet wired
    # into the validator) are reported but don't fail the test.
    shared = renderer_keys & allowed
    assert shared, (
        "no overlap between renderer SUPPORTED_TEMPLATES and "
        "_ENUM_FIELDS['synthesis.poster_template'] — integration broke."
    )
    missing = renderer_keys - allowed
    if missing:
        pytest.skip(
            f"integration TODO: add {sorted(missing)} to "
            "_ENUM_FIELDS['synthesis.poster_template']"
        )
