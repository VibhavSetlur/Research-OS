"""Tests for the v1.11.0 real slide compilation engine.

Gates two engines (Reveal.js HTML + Touying-mini Typst → PDF) and the
5 stock templates. Mirrors test_poster_typst.py in shape: pytest.skip
when typst is absent so CI without a typst binary still passes the
HTML half.
"""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.slides import (
    SUPPORTED_ENGINES,
    SUPPORTED_TEMPLATES,
    compile_slides,
)

HAS_TYPST = shutil.which("typst") is not None

# Tiny 1x1 PNG fixture.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEX///+nxBvI"
    "AAAAC0lEQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Minimum viable project: one step with conclusions + a focal figure."""
    step = tmp_path / "workspace" / "step01_pilot"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "# Findings\n"
        "- Effect held at n=120 (AUROC 0.84)\n"
        "- Robust under shuffling\n\n"
        "# Decision\nProceed to step02.\n",
        encoding="utf-8",
    )
    fig_dir = step / "outputs" / "figures"
    fig_dir.mkdir(parents=True)
    (fig_dir / "focal.png").write_bytes(_PNG_1x1)
    (fig_dir / "focal.summary.md").write_text(
        "AUROC = 0.84 across 5 folds.", encoding="utf-8",
    )
    (fig_dir / "focal.caption.md").write_text(
        "Figure 1. Held-out AUROC vs shuffle baseline.", encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def project_no_sources(tmp_path: Path) -> Path:
    """A project with NO workspace + NO slides_spec — should fail prereq."""
    return tmp_path


# ---------------------------------------------------------------------------
# Reveal.js engine
# ---------------------------------------------------------------------------

def test_reveal_engine_produces_valid_html(project: Path) -> None:
    res = compile_slides(project, engine="reveal", print_handout=False)
    assert res["status"] == "success", res
    html_path = Path(res["files"][0])
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html and "</html>" in html
    assert "<section" in html  # at least one slide rendered
    assert res["slide_count"] >= 5


def test_reveal_engine_inlines_vendored_runtime(project: Path) -> None:
    res = compile_slides(project, engine="reveal", print_handout=False)
    assert res["status"] == "success"
    html = Path(res["files"][0]).read_text(encoding="utf-8")
    # Vendored reveal.js identifies itself by a few stable strings.
    # We assert the runtime <script> block is non-trivial AND that the
    # reveal API call is present.
    assert "Reveal.initialize" in html
    # The vendored runtime contains the IIFE export.
    assert "reveal.js" in html.lower() or "function Reveal" in html


def test_reveal_speaker_notes_embedded_when_enabled(project: Path) -> None:
    res = compile_slides(
        project, engine="reveal", speaker_notes_enabled=True, print_handout=False,
    )
    assert res["status"] == "success"
    html = Path(res["files"][0]).read_text(encoding="utf-8")
    # Template ships speaker_notes for every slide.
    assert '<aside class="notes"' in html


def test_reveal_speaker_notes_omitted_when_disabled(project: Path) -> None:
    res = compile_slides(
        project, engine="reveal", speaker_notes_enabled=False, print_handout=False,
    )
    assert res["status"] == "success"
    html = Path(res["files"][0]).read_text(encoding="utf-8")
    assert '<aside class="notes"' not in html


def test_reveal_embeds_figure_as_data_uri(project: Path) -> None:
    res = compile_slides(project, engine="reveal", print_handout=False)
    assert res["status"] == "success"
    html = Path(res["files"][0]).read_text(encoding="utf-8")
    assert "data:image/png;base64," in html


def test_reveal_theme_override(project: Path) -> None:
    res_white = compile_slides(project, engine="reveal", theme="white", print_handout=False)
    assert res_white["status"] == "success"
    html_white = Path(res_white["files"][0]).read_text(encoding="utf-8")

    res_black = compile_slides(project, engine="reveal", theme="black", print_handout=False)
    assert res_black["status"] == "success"
    html_black = Path(res_black["files"][0]).read_text(encoding="utf-8")

    # Different theme CSS bodies → different output bytes.
    assert html_white != html_black
    # The black theme stylesheet's background-color: # rule names the
    # dark theme's body color; the white theme uses a different value.
    # Cheap-but-decisive contrast check: bodies differ in length.
    assert abs(len(html_white) - len(html_black)) > 0


def test_reveal_html_size_under_8mb(project: Path) -> None:
    res = compile_slides(project, engine="reveal", print_handout=False)
    assert res["status"] == "success"
    size = Path(res["files"][0]).stat().st_size
    assert size < 8 * 1024 * 1024, f"slides.html is {size} bytes (>8MB cap)"


# ---------------------------------------------------------------------------
# Touying / Typst engine
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_touying_engine_compiles_to_pdf(project: Path) -> None:
    res = compile_slides(project, engine="touying", print_handout=False)
    assert res["status"] == "success", res
    files = res["files"]
    assert any(f.endswith("slides.typ") for f in files)
    pdf_files = [f for f in files if f.endswith("slides.pdf")]
    assert pdf_files, f"no PDF emitted; files={files}"
    pdf_path = Path(pdf_files[0])
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    # Real PDF starts with %PDF-
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_touying_handout_pdf_emitted_when_requested(project: Path) -> None:
    res = compile_slides(project, engine="touying", print_handout=True)
    assert res["status"] == "success"
    handout_pdfs = [f for f in res["files"] if f.endswith("slides_handout.pdf")]
    assert handout_pdfs, f"handout missing; files={res['files']}"
    p = Path(handout_pdfs[0])
    assert p.exists()
    assert p.stat().st_size < 4 * 1024 * 1024, "handout PDF >4MB"
    assert res["print_handout_emitted"] is True


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_touying_pdf_size_under_4mb(project: Path) -> None:
    res = compile_slides(project, engine="touying", print_handout=False)
    assert res["status"] == "success"
    pdf = next(Path(f) for f in res["files"] if f.endswith("slides.pdf"))
    assert pdf.stat().st_size < 4 * 1024 * 1024


# ---------------------------------------------------------------------------
# Template coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template", SUPPORTED_TEMPLATES)
def test_every_template_renders_non_empty_reveal(project: Path, template: str) -> None:
    res = compile_slides(project, engine="reveal", template=template, print_handout=False)
    assert res["status"] == "success", f"{template} failed: {res}"
    html = Path(res["files"][0]).read_text(encoding="utf-8")
    assert len(html) > 1000, f"{template} produced suspiciously small HTML"
    assert res["slide_count"] >= 4, f"{template} produced only {res['slide_count']} slides"


def test_supported_templates_list_has_five_entries() -> None:
    assert len(SUPPORTED_TEMPLATES) == 5
    for expected in (
        "conference_15min",
        "conference_5min_lightning",
        "lab_meeting_30min",
        "defense_45min",
        "public_outreach",
    ):
        assert expected in SUPPORTED_TEMPLATES


# ---------------------------------------------------------------------------
# Error envelopes
# ---------------------------------------------------------------------------

def test_missing_prereq_returns_clear_error(project_no_sources: Path) -> None:
    res = compile_slides(project_no_sources, engine="reveal", print_handout=False)
    assert res["status"] == "error"
    assert "slides_spec" in res["message"] or "conclusions" in res["message"]


def test_unknown_engine_returns_clear_error(project: Path) -> None:
    res = compile_slides(project, engine="impress", print_handout=False)
    assert res["status"] == "error"
    assert "engine" in res["message"]


def test_unknown_template_returns_clear_error(project: Path) -> None:
    res = compile_slides(project, engine="reveal", template="not_a_template", print_handout=False)
    assert res["status"] == "error"
    assert "template" in res["message"]


def test_unknown_theme_returns_clear_error(project: Path) -> None:
    res = compile_slides(project, engine="reveal", theme="solarized-mauve", print_handout=False)
    assert res["status"] == "error"
    assert "theme" in res["message"]


def test_engines_list_two_entries() -> None:
    assert set(SUPPORTED_ENGINES) == {"reveal", "touying"}


# ---------------------------------------------------------------------------
# Back-compat (legacy v1.10.x signature)
# ---------------------------------------------------------------------------

def test_backcompat_output_format_reveal_routes_to_reveal_engine(project: Path) -> None:
    """Old callers passed ``output_format='reveal'`` instead of engine='reveal'."""
    res = compile_slides(project, output_format="reveal", print_handout=False)
    assert res["status"] == "success"
    assert res["engine"] == "reveal"
    assert res["files"][0].endswith(".html")


def test_backcompat_output_format_beamer_routes_to_touying(project: Path) -> None:
    """Old callers passing 'beamer'/'pdf' should land on the PDF engine.

    We don't actually compile the PDF if typst is missing — but the
    engine resolution must still pick 'touying'.
    """
    res = compile_slides(project, output_format="beamer", print_handout=False)
    # Engine resolution succeeded; either success (typst present) or a
    # clean typst-missing error.
    if HAS_TYPST:
        assert res["status"] == "success", res
        assert res["engine"] == "touying"
    else:
        assert res["status"] == "error"
        assert "typst" in res.get("message", "").lower()


def test_backcompat_audience_kwarg_accepted(project: Path) -> None:
    """Old callers passed audience= in addition to template= — must not crash."""
    res = compile_slides(
        project,
        engine="reveal",
        template="conference_15min",
        audience="conference_talk_long",
        print_handout=False,
    )
    assert res["status"] == "success"
