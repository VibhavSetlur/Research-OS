"""Compile-smoke tests for the synthesis starter scaffolds.

Every Typst scaffold kind that ``synthesis_scaffold`` seeds must compile
to a PDF out of the box — the AI authors the content into a skeleton that
already compiles, so a fresh project never hits an unresolved-import or
missing-file error before it has written a single word.

Two surfaces are covered:

1. Each scaffold ``kind`` (paper, slides, poster, handout, grant, essay)
   seeds a .typ whose ``#import`` resolves to symbols the bundled
   template actually exports, and compiles via the production
   ``typst_compile`` path (which materialises the templates + a biblio).

2. The uniform ``template`` / ``conf`` interface added to every
   paper-style venue template compiles under the venue-agnostic import
   form the scaffold emits — so the scaffold works for ANY
   ``writing_preferences.venue_template`` the researcher selects, not
   just ``generic_two_column``.

Tests skip gracefully when the ``typst`` binary is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.scaffold import synthesis_scaffold
from research_os.tools.actions.synthesis.typst import _find_templates_dir
from research_os.tools.actions.synthesis.typst_compile import typst_compile

pytestmark = pytest.mark.skipif(
    shutil.which("typst") is None,
    reason="typst binary not installed",
)

# Every Typst scaffold kind. (dashboard is HTML, not Typst — excluded.)
_TYPST_KINDS = ["paper", "slides", "poster", "handout", "grant", "essay"]

# Every paper-style venue that must expose the uniform template/conf surface.
_PAPER_VENUES = [
    "generic_two_column", "generic_thesis", "chicago_thesis",
    "humanities_essay", "nature", "science", "nejm", "cell",
    "ieee_conf", "neurips", "acl", "plos",
]


@pytest.mark.parametrize("kind", _TYPST_KINDS)
def test_scaffold_kind_compiles(tmp_path: Path, kind: str):
    """Each scaffold kind seeds a .typ that compiles to a PDF."""
    res = synthesis_scaffold(tmp_path, kind=kind, confirmed=True)
    assert res["status"] == "success", res
    src = Path(res["path"])
    assert src.suffix == ".typ"

    out = typst_compile(tmp_path, source=str(src.relative_to(tmp_path)))
    assert out["status"] == "success", out.get("typst_errors") or out
    assert out["pdf_path"] is not None
    assert Path(out["pdf_path"]).exists()


@pytest.mark.parametrize("venue", _PAPER_VENUES)
def test_every_paper_venue_exposes_uniform_interface(tmp_path: Path, venue: str):
    """The scaffold's venue-agnostic import form compiles for ANY venue.

    The scaffold seeds ``#import ".../<venue>.typ": template, conf`` +
    ``#show: template.with(conf(...))``. Every paper-style venue must
    therefore export both ``template`` and ``conf`` and accept the
    normalised config the scaffold passes (authors as ``(name:,
    affiliation:)`` dicts).
    """
    tdir = _find_templates_dir()
    assert tdir is not None, "bundled typst templates dir not found"

    local = tmp_path / "_typst_templates"
    local.mkdir()
    for name in (f"{venue}.typ", "common.typ"):
        shutil.copyfile(tdir / name, local / name)

    src = tmp_path / "paper.typ"
    src.write_text(
        f'#import "_typst_templates/{venue}.typ": template, conf\n'
        "#show: template.with(conf(\n"
        "  title: [A venue-agnostic title],\n"
        "  authors: ((name: \"Author One\", affiliation: \"Inst A\"),"
        " (name: \"Author Two\", affiliation: \"Inst B\")),\n"
        "  abstract: [A short abstract exercising the conf normaliser.],\n"
        "))\n"
        "= Introduction\nBody.\n= Methods\nMore body.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.pdf"
    proc = subprocess.run(
        ["typst", "compile", "--root", str(tmp_path), str(src), str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
