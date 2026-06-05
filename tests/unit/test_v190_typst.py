"""Typst PDF compilation tests."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.typst import (
    VENUE_TEMPLATES,
    _find_templates_dir,
    citations_md_to_hayagriva,
    compile_typst,
    md_to_typst,
    paper_compile_typst,
)

HAS_TYPST = shutil.which("typst") is not None


# ── md_to_typst conversions ──────────────────────────────────────────


def test_md_to_typst_headings():
    src = "# H1\n\n## H2\n\n### H3\n"
    out = md_to_typst(src)
    # H1 becomes the title (consumed); H2/H3 -> ==/===.
    assert "== H2" in out
    assert "=== H3" in out


def test_md_to_typst_bold_italic_code():
    src = "## Heading\n\nThis is **bold** and *italic* and `code`.\n"
    out = md_to_typst(src)
    assert "*bold*" in out
    assert "_italic_" in out
    assert "`code`" in out


def test_md_to_typst_link():
    src = "## H\n\nSee [the docs](https://example.com/x).\n"
    out = md_to_typst(src)
    assert '#link("https://example.com/x")[the docs]' in out


def test_md_to_typst_image():
    src = "## H\n\n![A figure](fig.png)\n"
    out = md_to_typst(src)
    assert '#figure(image("fig.png"' in out
    assert "caption: [A figure]" in out


def test_md_to_typst_quote():
    src = "## H\n\n> a quoted thing\n"
    out = md_to_typst(src)
    assert "#quote[a quoted thing]" in out


def test_md_to_typst_pandoc_cite():
    src = "## H\n\nThe finding [@smith2024] held.\n"
    out = md_to_typst(src)
    assert "#cite(<smith2024>)" in out


def test_md_to_typst_multi_pandoc_cite():
    src = "## H\n\nMultiple [@a2024; @b2025] cites.\n"
    out = md_to_typst(src)
    assert "#cite(<a2024>)" in out
    assert "#cite(<b2025>)" in out


def test_md_to_typst_footnote():
    src = "## H\n\nClaim[^1].\n"
    out = md_to_typst(src)
    assert "#footnote[1]" in out


def test_md_to_typst_code_block():
    src = "## H\n\n```python\nx = 1\n```\n"
    out = md_to_typst(src)
    assert "#raw(" in out
    assert 'lang: "python"' in out
    assert "block: true" in out


def test_md_to_typst_table():
    src = (
        "## H\n\n"
        "| col1 | col2 |\n"
        "| --- | --- |\n"
        "| a | b |\n"
        "| c | d |\n"
    )
    out = md_to_typst(src)
    assert "#table(" in out
    assert "columns: 2" in out


def test_md_to_typst_lists():
    src = "## H\n\n- one\n- two\n\n1. first\n2. second\n"
    out = md_to_typst(src)
    assert "- one" in out
    assert "+ first" in out


def test_md_to_typst_pulls_title_from_h1():
    src = "# A Real Title\n\n## Methods\n\nWe did things.\n"
    out = md_to_typst(src)
    assert "[A Real Title]" in out


def test_md_to_typst_unknown_venue_falls_back():
    out = md_to_typst("# T\n\n## M\n", venue_template="does_not_exist")
    assert "generic_two_column" in out


def test_md_to_typst_bibliography_block_present():
    out = md_to_typst("# T\n\n## H\n", venue_template="nature")
    assert '#bibliography("biblio.yml"' in out


# ── citations_md_to_hayagriva ───────────────────────────────────────


def test_citations_to_hayagriva_basic(tmp_path: Path):
    cit = tmp_path / "citations.md"
    cit.write_text(
        "@smith2024 Smith J. (2024). A real paper.\n"
        "title: A Real Paper\n"
        "author: Smith, J. and Doe, A.\n"
        "year: 2024\n"
        "journal: Nature\n"
        "doi: 10.1038/abc\n"
    )
    yaml_out = citations_md_to_hayagriva(cit)
    assert "smith2024:" in yaml_out
    assert "type: article" in yaml_out
    assert '"A Real Paper"' in yaml_out
    assert "doi:" in yaml_out


def test_citations_to_hayagriva_missing_file(tmp_path: Path):
    assert citations_md_to_hayagriva(tmp_path / "nope.md") == ""


def test_citations_to_hayagriva_dedupes_keys(tmp_path: Path):
    cit = tmp_path / "citations.md"
    cit.write_text(
        "@a2024 First entry.\nauthor: A\n\n"
        "@a2024 Second entry with same key.\nauthor: B\n"
    )
    out = citations_md_to_hayagriva(cit)
    # Only the first entry should be retained.
    assert out.count("a2024:") == 1


# ── compile_typst ────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_compile_typst_smoke(tmp_path: Path):
    src = tmp_path / "doc.typ"
    src.write_text("= Hello\n\nWorld.\n")
    pdf = tmp_path / "doc.pdf"
    res = compile_typst(src, pdf)
    assert res["status"] == "success", res
    assert pdf.exists()


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_compile_typst_parses_errors(tmp_path: Path):
    src = tmp_path / "bad.typ"
    src.write_text("#undefined-function()\n")
    res = compile_typst(src, tmp_path / "bad.pdf")
    assert res["status"] == "error"
    assert isinstance(res["errors"], list)


def test_compile_typst_missing_source(tmp_path: Path):
    res = compile_typst(tmp_path / "missing.typ", tmp_path / "out.pdf")
    assert res["status"] == "error"


# ── paper_compile_typst end-to-end (gated on typst CLI) ─────────────


SAMPLE_PAPER = (
    "# Sample Paper\n\n"
    "## Abstract\n\n"
    "We found 42% in n=100 samples.\n\n"
    "## Methods\n\n"
    "We applied X.\n\n"
    "## Results\n\n"
    "Strong effect (p < 0.001).\n\n"
    "## Discussion\n\n"
    "Limitations: small sample. Future work: replicate.\n"
)


def _scaffold(tmp_path: Path) -> Path:
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "synthesis" / "paper.md").write_text(SAMPLE_PAPER)
    (tmp_path / "workspace" / "citations.md").write_text("placeholder:\n")
    return tmp_path


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
@pytest.mark.parametrize("venue", VENUE_TEMPLATES)
def test_paper_compile_typst_each_venue(tmp_path: Path, venue: str):
    root = _scaffold(tmp_path)
    res = paper_compile_typst(root, venue=venue)
    assert res["status"] == "success", res
    assert Path(res["pdf_path"]).exists()
    assert res["venue"] == venue


def test_paper_compile_typst_missing_paper(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    res = paper_compile_typst(tmp_path, venue="generic_two_column")
    assert res["status"] == "error"


def test_paper_compile_typst_invalid_venue(tmp_path: Path):
    root = _scaffold(tmp_path)
    res = paper_compile_typst(root, venue="totally_made_up")
    assert res["status"] == "error"
    assert "Unknown venue" in res["message"]


def test_find_templates_dir_exists():
    d = _find_templates_dir()
    assert d is not None
    assert (d / "generic_two_column.typ").exists()
    for v in VENUE_TEMPLATES:
        assert (d / f"{v}.typ").exists(), f"missing template: {v}.typ"
