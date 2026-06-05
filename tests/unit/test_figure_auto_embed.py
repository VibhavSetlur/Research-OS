"""Unit tests for src/research_os/tools/actions/synthesis/figure_auto_embed.py.

Covers the v1.11.0 headline feature: discovery + caption frontmatter +
section-aware embedding + cross-reference rewriting + audit gate.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from research_os.tools.actions.synthesis.figure_auto_embed import (
    audit_figure_coverage,
    auto_embed_figures,
    discover_figures,
    read_caption_frontmatter,
    rewrite_figure_xrefs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_step(
    root: Path,
    step_id: str,
    figures: list[tuple[str, str | None, bool]] | None = None,
    *,
    figures_for_paper: bool = True,
) -> Path:
    """Create workspace/<step>/outputs/figures/ + step_summary.yaml.

    ``figures`` is a list of (stem, caption_md_text, on_disk) tuples.
    """
    step_dir = root / "workspace" / step_id
    fig_dir = step_dir / "outputs" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    (step_dir / "step_summary.yaml").write_text(
        f"step_intent: analyse\nfigures_for_paper: {str(figures_for_paper).lower()}\n"
    )
    for stem, cap, on_disk in figures or []:
        if on_disk:
            (fig_dir / f"{stem}.png").write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        if cap is not None:
            (fig_dir / f"{stem}.caption.md").write_text(cap)
    return step_dir


def _paper_skeleton() -> str:
    return textwrap.dedent(
        """\
        # A Paper

        ## Abstract

        Abstract text.

        ## Introduction

        Intro text.

        ## Methods

        Methods text.

        ## Results

        Results text.

        ## Discussion

        Discussion text.

        ## References

        References.
        """
    )


# ---------------------------------------------------------------------------
# 1. discover_figures honours figures_for_paper
# ---------------------------------------------------------------------------


def test_discover_finds_figures_with_default_field(tmp_path: Path) -> None:
    _make_step(tmp_path, "01_pilot", [("vol", None, True)])
    figs = discover_figures(tmp_path)
    assert len(figs) == 1
    assert figs[0]["stem"] == "vol"
    assert figs[0]["step_id"] == "01_pilot"


def test_discover_skips_step_with_figures_for_paper_false(tmp_path: Path) -> None:
    _make_step(
        tmp_path,
        "01_pilot",
        [("vol", None, True)],
        figures_for_paper=False,
    )
    assert discover_figures(tmp_path) == []


# ---------------------------------------------------------------------------
# 2. caption frontmatter
# ---------------------------------------------------------------------------


def test_caption_frontmatter_parses_known_fields(tmp_path: Path) -> None:
    cap = tmp_path / "x.caption.md"
    cap.write_text(
        textwrap.dedent(
            """\
            ---
            section_hint: Discussion
            figure_priority: 2
            poster_priority: 1
            alt_text: a custom alt
            figures_for_paper: true
            ---
            The headline caption.
            """
        )
    )
    fm = read_caption_frontmatter(cap)
    assert fm["section_hint"] == "Discussion"
    assert fm["figure_priority"] == 2
    assert fm["poster_priority"] == 1
    assert fm["alt_text"] == "a custom alt"
    assert fm["figures_for_paper"] is True
    assert "headline caption" in fm["_body"]


def test_caption_frontmatter_defaults_when_missing(tmp_path: Path) -> None:
    cap = tmp_path / "x.caption.md"
    cap.write_text("Just a caption, no frontmatter.\n")
    fm = read_caption_frontmatter(cap)
    assert fm["section_hint"] == "Results"
    assert fm["figure_priority"] == 100
    assert fm["figures_for_paper"] is True


# ---------------------------------------------------------------------------
# 3. auto_embed placement
# ---------------------------------------------------------------------------


def test_section_hint_drives_placement(tmp_path: Path) -> None:
    _make_step(
        tmp_path,
        "01_x",
        [
            (
                "vol",
                "---\nsection_hint: Discussion\n---\nThe volcano plot.",
                True,
            )
        ],
    )
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())

    res = auto_embed_figures(paper, tmp_path)
    assert res["status"] == "success"
    assert res["embedded"] == 1
    text = paper.read_text()
    # Make sure the figure sits inside the Discussion section.
    disc_start = text.index("## Discussion")
    refs_start = text.index("## References")
    discussion_block = text[disc_start:refs_start]
    assert "![" in discussion_block
    assert "vol" in discussion_block


def test_auto_embed_is_idempotent(tmp_path: Path) -> None:
    _make_step(tmp_path, "01_x", [("vol", "Caption text.", True)])
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())

    first = auto_embed_figures(paper, tmp_path)
    text_after_first = paper.read_text()
    second = auto_embed_figures(paper, tmp_path)
    text_after_second = paper.read_text()
    assert first["embedded"] == 1
    assert second["embedded"] == 0
    assert second["skipped_already_present"] == 1
    assert text_after_first == text_after_second


def test_mode_explicit_map_respects_section_map(tmp_path: Path) -> None:
    _make_step(
        tmp_path,
        "01_x",
        [("vol", "---\nsection_hint: Methods\n---\nCaption.", True)],
    )
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())

    auto_embed_figures(
        paper,
        tmp_path,
        mode="explicit_map",
        section_map={"vol": "Discussion"},
    )
    text = paper.read_text()
    methods_block = text[text.index("## Methods"):text.index("## Results")]
    disc_block = text[text.index("## Discussion"):text.index("## References")]
    # Should land in Discussion (override), not Methods (section_hint).
    assert "vol" not in methods_block.split("Results")[0]
    assert "vol" in disc_block


def test_mode_append_to_section_lands_at_end(tmp_path: Path) -> None:
    _make_step(tmp_path, "01_x", [("vol", "A caption.", True)])
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())

    auto_embed_figures(paper, tmp_path, mode="append_to_section")
    text = paper.read_text()
    # In the Results section, the figure should appear AFTER "Results text."
    results_block = text[text.index("## Results"):text.index("## Discussion")]
    assert results_block.index("Results text.") < results_block.index("vol")


def test_reorder_mode_orders_by_figure_priority(tmp_path: Path) -> None:
    _make_step(
        tmp_path,
        "01_x",
        [
            ("low_pri", "---\nfigure_priority: 50\n---\nLow caption.", True),
            ("hi_pri", "---\nfigure_priority: 1\n---\nHi caption.", True),
        ],
    )
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())

    auto_embed_figures(paper, tmp_path, mode="reorder")
    text = paper.read_text()
    # hi_pri (priority 1) must appear BEFORE low_pri (priority 50).
    assert text.index("hi_pri") < text.index("low_pri")


def test_missing_figure_file_returns_clear_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set up one real figure so discovery returns something.
    _make_step(tmp_path, "02_y", [("real", "Real caption.", True)])
    # Patch discover_figures so the auto-embed pass thinks a "ghost"
    # figure exists on disk too — simulating a stale registry.
    from research_os.tools.actions.synthesis import figure_auto_embed as mod

    real = mod.discover_figures(tmp_path)
    ghost = dict(real[0])
    ghost["stem"] = "ghost"
    ghost["path"] = "workspace/02_y/outputs/figures/ghost.png"
    monkeypatch.setattr(mod, "discover_figures", lambda r: real + [ghost])

    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())
    res = auto_embed_figures(paper, tmp_path)
    assert any("ghost" in m for m in res["missing_file"])
    # The real figure embedded fine.
    assert res["embedded"] == 1


# ---------------------------------------------------------------------------
# 4. caption rendering — headline + Note
# ---------------------------------------------------------------------------


def test_multi_paragraph_caption_splits_headline_and_note(tmp_path: Path) -> None:
    body = (
        "---\nsection_hint: Results\n---\n"
        "The headline caption.\n\nA supplementary note about it."
    )
    _make_step(tmp_path, "01_x", [("vol", body, True)])
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())
    auto_embed_figures(paper, tmp_path)
    text = paper.read_text()
    assert "**Figure (vol).** The headline caption." in text
    assert "*Note:* A supplementary note about it." in text


# ---------------------------------------------------------------------------
# 5. cross-reference rewriting
# ---------------------------------------------------------------------------


def test_xref_rewrite_swaps_bare_stems_to_at_fig(tmp_path: Path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text(
        textwrap.dedent(
            """\
            ## Results

            See 01_volcano for details.

            ![cap](fig/01_volcano.png){#fig:01_volcano}
            """
        )
    )
    res = rewrite_figure_xrefs(paper)
    assert res["status"] == "success"
    # one rewrite — the bare token outside the image.
    assert res["rewritten"] >= 1
    text = paper.read_text()
    assert "@fig:01_volcano" in text
    # second pass is a no-op.
    again = rewrite_figure_xrefs(paper)
    assert again["rewritten"] == 0


def test_xref_rewrite_leaves_code_blocks_alone(tmp_path: Path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text(
        textwrap.dedent(
            """\
            ```python
            x = "01_volcano"
            ```

            See 01_volcano in text.

            ![c](fig/01_volcano.png){#fig:01_volcano}
            """
        )
    )
    rewrite_figure_xrefs(paper)
    text = paper.read_text()
    code_block = text.split("```python")[1].split("```")[0]
    assert "@fig:01_volcano" not in code_block
    assert "01_volcano" in code_block  # still there
    # Prose got rewritten.
    prose = text.split("```")[2]
    assert "@fig:01_volcano" in prose


def test_xref_rewrite_only_runs_when_called(tmp_path: Path) -> None:
    # Gate-by-config behavior is enforced at the handler layer; here we
    # just confirm the function itself is opt-in (returns no rewrite
    # when there are no known stems).
    paper = tmp_path / "paper.md"
    paper.write_text("Some prose with 01_volcano but no image.\n")
    res = rewrite_figure_xrefs(paper)
    assert res["status"] == "success"
    assert res["rewritten"] == 0


# ---------------------------------------------------------------------------
# 6. audit_figure_coverage
# ---------------------------------------------------------------------------


def test_audit_figure_coverage_blocks_on_orphan(tmp_path: Path) -> None:
    _make_step(tmp_path, "01_x", [("vol", "A caption.", True)])
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())
    res = audit_figure_coverage(tmp_path)
    assert res["status"] == "error"
    assert any("vol" in b for b in res["blockers"])


def test_audit_figure_coverage_passes_after_embed(tmp_path: Path) -> None:
    _make_step(tmp_path, "01_x", [("vol", "A caption.", True)])
    paper = tmp_path / "synthesis" / "paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(_paper_skeleton())
    auto_embed_figures(paper, tmp_path)
    res = audit_figure_coverage(tmp_path)
    assert res["status"] == "success"
    assert res["blockers"] == []
    assert res["embedded"] == 1


# ---------------------------------------------------------------------------
# 7. Discovery skips per-figure figures_for_paper=false
# ---------------------------------------------------------------------------


def test_per_figure_figures_for_paper_false_is_skipped(tmp_path: Path) -> None:
    _make_step(
        tmp_path,
        "01_x",
        [
            (
                "skip_me",
                "---\nfigures_for_paper: false\n---\nNot for the paper.",
                True,
            ),
            ("keep", "A caption.", True),
        ],
    )
    stems = {f["stem"] for f in discover_figures(tmp_path)}
    assert "skip_me" not in stems
    assert "keep" in stems


# ---------------------------------------------------------------------------
# 8. Smoke: missing paper.md path returns error not exception
# ---------------------------------------------------------------------------


def test_auto_embed_returns_error_when_paper_missing(tmp_path: Path) -> None:
    res = auto_embed_figures(tmp_path / "no_paper.md", tmp_path)
    assert res["status"] == "error"
