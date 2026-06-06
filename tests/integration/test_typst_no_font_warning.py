"""Verify Typst PDF compilation no longer emits font-cascade warnings.

v1.11.1 known issue: with stock Linux installs that lack ``Linux
Libertine`` / ``Times New Roman`` / ``EB Garamond``, every paper
compile printed a noisy ``warning: unknown font family: …`` line per
listed fallback. v2.0.0 bundles New Computer Modern (NCM, GUST /
GPL3+FE+DE licensed) under ``src/research_os/assets/fonts/`` and wires
``--font-path`` into the three ``typst compile`` subprocess sites
(paper, poster, slides) via a single shared helper.

This test exercises the full ``paper_compile_typst`` path against
every venue template and asserts the returned ``typst_warnings`` list
is empty.

The test is skipped when:
  * the ``typst`` CLI is not on PATH (most CI matrices install it; the
    skip exists so the unit-test run still works on a stripped-down
    dev machine), or
  * the bundled fonts directory is missing (sdist-only install path
    that strips binary artifacts — in that case the older warning
    behaviour is acceptable and out of scope for this fix).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.typst import (
    VENUE_TEMPLATES,
    bundled_font_path,
    paper_compile_typst,
)


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def require_typst() -> None:
    """Skip when the typst CLI isn't installed."""
    if not shutil.which("typst"):
        pytest.skip("typst CLI not on PATH")


@pytest.fixture(scope="module")
def require_bundled_fonts() -> None:
    """Skip when the wheel didn't ship the bundled fonts (sdist install)."""
    if bundled_font_path() is None:
        pytest.skip("bundled NCM fonts not present in this install")


def _compile_minimal(venue: str) -> dict:
    """Run paper_compile_typst on a 3-line stub paper for the venue."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        synthesis = root / "synthesis"
        synthesis.mkdir()
        (synthesis / "paper.md").write_text(
            "# Test Title\n\nA single paragraph to exercise the venue template.\n",
            encoding="utf-8",
        )
        return paper_compile_typst(root, venue=venue)


def test_bundled_font_dir_present_and_contains_otfs() -> None:
    """The wheel must ship at least one OTF in the assets/fonts dir."""
    font_dir = bundled_font_path()
    assert font_dir is not None, "bundled font directory not located"
    otfs = list(font_dir.glob("*.otf"))
    assert otfs, f"no .otf files in {font_dir}"
    # Sanity: the two families our templates reference must both be present.
    names = {p.name for p in otfs}
    assert any("NewCM10" in n for n in names), \
        f"NewCM serif missing from {names}"
    assert any("NewCMSans10" in n for n in names), \
        f"NewCMSans missing from {names}"


@pytest.mark.parametrize("venue", VENUE_TEMPLATES)
def test_no_font_cascade_warning(
    require_typst, require_bundled_fonts, venue: str
) -> None:
    """Every venue template compiles a stub paper with zero font warnings."""
    result = _compile_minimal(venue)
    assert result.get("status") == "success", (
        f"compile failed for {venue}: {result.get('message')} "
        f"errors={result.get('typst_errors')}"
    )
    warnings = result.get("typst_warnings") or []
    # The font-cascade warning we're killing is the only class of
    # warning the bundled fonts can possibly fix. Be specific in the
    # assert message so future unrelated warnings (deprecations, etc.)
    # surface a clear diff instead of a generic "warnings != []".
    font_warnings = [
        w for w in warnings if "unknown font family" in w.lower()
    ]
    assert not font_warnings, (
        f"venue={venue} still emits font-cascade warnings: {font_warnings}"
    )
