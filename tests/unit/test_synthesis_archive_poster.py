"""Synthesis: poster section-detection fix + output archiving + overflow signal."""
from __future__ import annotations

import importlib

from research_os.tools.actions.synthesis.check import _check_poster

# The synthesis package re-exports the `typst_compile` function, shadowing the
# submodule of the same name — grab the real module via importlib so monkeypatch
# can reach compile_typst / _target_kind.
tc = importlib.import_module("research_os.tools.actions.synthesis.typst_compile")


SCAFFOLD_POSTER = """#import "_typst_templates/poster.typ": poster, headline, block-section
#show: poster.with(title: "X")
#headline[Headline finding as a sentence — across-the-room readable.]
#block-section(title: "Background")[ bg ]
#block-section(title: "Methods")[ m ]
#block-section(title: "Results")[ r ]
#block-section(title: "Implication")[ i ]
"""


def test_check_poster_recognises_scaffold_functions():
    res = _check_poster(SCAFFOLD_POSTER)
    # A correctly-authored scaffold poster must NOT be falsely blocked.
    assert res["blockers"] == []
    assert res["headline_count"] >= 1
    assert res["section_count"] >= 3


def test_check_poster_blocks_on_missing_sections_warns_on_headline():
    res = _check_poster("just some prose with no structure")
    # Too few sections is a structural BLOCKER.
    assert any("section" in b.lower() for b in res["blockers"])
    # Missing headline is a WARNING (a hand-rolled poster may carry it elsewhere),
    # not a false hard block.
    assert any("headline" in w.lower() for w in res["warnings"])
    assert not any("headline" in b.lower() for b in res["blockers"])


def test_target_kind_maps_filenames():
    from pathlib import Path
    assert tc._target_kind(Path("synthesis/poster.typ")) == "poster"
    assert tc._target_kind(Path("synthesis/paper.typ")) == "paper"


def test_typst_compile_archives_prior_render(tmp_path, monkeypatch):
    sdir = tmp_path / "synthesis"
    sdir.mkdir()
    (sdir / "paper.typ").write_text("= Title\nbody\n")
    (sdir / "paper.pdf").write_bytes(b"%PDF-1.7\n/Type /Page\nOLD RENDER\n")

    def fake_compile(src, out_path):
        out_path.write_bytes(b"%PDF-1.7\n/Type /Page\nNEW RENDER\n")
        return {"status": "success", "warnings": [], "errors": []}

    monkeypatch.setattr(tc, "compile_typst", fake_compile)
    res = tc.typst_compile(tmp_path, source="synthesis/paper.typ")
    assert res["status"] == "success"
    assert res["archived_prior_to"] is not None
    archived = list((sdir / "archive").glob("paper_*.pdf"))
    assert len(archived) == 1
    assert b"OLD RENDER" in archived[0].read_bytes()
    assert b"NEW RENDER" in (sdir / "paper.pdf").read_bytes()


def test_typst_compile_flags_poster_overflow(tmp_path, monkeypatch):
    sdir = tmp_path / "synthesis"
    sdir.mkdir()
    (sdir / "poster.typ").write_text("#headline[x]\n#block-section(title: \"A\")[y]\n")

    def fake_compile_two_pages(src, out_path):
        # Two page objects → a poster overflowed its single canvas.
        out_path.write_bytes(b"%PDF-1.7\n/Type /Page\n/Type /Page\n")
        return {"status": "success", "warnings": [], "errors": []}

    monkeypatch.setattr(tc, "compile_typst", fake_compile_two_pages)
    res = tc.typst_compile(tmp_path, source="synthesis/poster.typ", archive_prior=False)
    assert res["page_count"] == 2
    assert res["layout_warnings"]
    assert "overflow" in res["layout_warnings"][0].lower()


def test_typst_compile_page_count_excludes_pages_node(tmp_path, monkeypatch):
    sdir = tmp_path / "synthesis"
    sdir.mkdir()
    (sdir / "paper.typ").write_text("= T\n")

    def fake_compile(src, out_path):
        # One real page + the /Type /Pages tree node — count must be 1, not 2.
        out_path.write_bytes(b"%PDF\n/Type /Pages\n/Type /Page\n")
        return {"status": "success", "warnings": [], "errors": []}

    monkeypatch.setattr(tc, "compile_typst", fake_compile)
    res = tc.typst_compile(tmp_path, source="synthesis/paper.typ", archive_prior=False)
    assert res["page_count"] == 1
