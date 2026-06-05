"""Tests for the dashboard story mode (Theme 21)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.synthesis.dashboard_story import (
    _apply_patch_blocks,
    dashboard_story_edit,
    dashboard_story_generate,
    dashboard_story_quality_bar,
)
from research_os.tools.actions.synthesis.dashboard_v2 import render_dashboard_v2


def _scaffold_full_story_fixture(root: Path, n_steps: int = 3,
                                   with_callout: bool = True) -> None:
    (root / "synthesis").mkdir()
    # A long-form abstract so reading time + word-count thresholds can pass.
    abstract = " ".join(["Researchers studied a complex phenomenon and reported findings"] * 50)
    spec = {
        "title": "Long-form research story",
        "abstract": abstract,
        "findings": [
            {"title": "F1", "summary": " ".join(["A reasonable headline finding."] * 8)},
        ],
    }
    (root / "synthesis" / "synthesis_spec.yaml").write_text(yaml.safe_dump(spec))
    for i in range(1, n_steps + 1):
        step = root / "workspace" / f"{i:02d}_demo"
        step.mkdir(parents=True)
        (step / "conclusions.md").write_text(
            "## Plain-language summary\n"
            + " ".join([f"We analysed something in step {i}."] * 30) + "\n"
            "## Findings\n- Headline finding\n"
        )
        if with_callout:
            (step / "findings_vs_literature.md").write_text(
                f"- **DISAGREES**: Prior work claimed Z but we observed Q for step {i}\n"
                "- **AGREES**: Matches the canonical result\n"
            )
        figs = step / "outputs" / "figures"
        figs.mkdir(parents=True)
        (figs / f"{i:02d}_main.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        (figs / f"{i:02d}_main.summary.md").write_text(f"Caption for figure {i}.")


# ──────────────────────────────────────────────────────────────────────
# Story generator
# ──────────────────────────────────────────────────────────────────────


def test_generate_produces_story_md(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    res = dashboard_story_generate(tmp_path)
    assert res["status"] == "success"
    p = tmp_path / "synthesis" / "dashboard_story.md"
    assert p.exists()
    body = p.read_text()
    assert "# Long-form research story" in body
    assert "## 01_demo" in body
    assert "## 02_demo" in body


def test_generate_includes_callouts(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path, with_callout=True)
    dashboard_story_generate(tmp_path)
    body = (tmp_path / "synthesis" / "dashboard_story.md").read_text()
    # Blockquote with the DISAGREES verdict, no doubled markers from
    # parsing the bullet source line.
    assert "> **DISAGREES**:" in body
    assert ">  **: Prior" not in body  # regression guard for the regex fix


def test_generate_embeds_figure_link(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    body = (tmp_path / "synthesis" / "dashboard_story.md").read_text()
    assert "![Caption for figure 1.](" in body


def test_generate_reading_minutes_in_plausible_range(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path, n_steps=6)
    res = dashboard_story_generate(tmp_path)
    assert res["reading_minutes"] >= 1
    assert res["reading_minutes"] <= 60  # generous upper bound


def test_generate_uses_abstract_md_fallback(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "abstract.md").write_text("# Abstract\nThis is the abstract body.\n")
    (tmp_path / "synthesis" / "synthesis_spec.yaml").write_text("title: T\n")  # no abstract
    assert dashboard_story_generate(tmp_path)["status"] == "success"
    body = (tmp_path / "synthesis" / "dashboard_story.md").read_text()
    assert "This is the abstract body" in body


# ──────────────────────────────────────────────────────────────────────
# Story editor
# ──────────────────────────────────────────────────────────────────────


def test_editor_read_returns_current(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    res = dashboard_story_edit(tmp_path)
    assert res["status"] == "success"
    assert "# Long-form research story" in res["content"]


def test_editor_overwrite_replaces_content(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    new = "# Replaced\n\nAll new content.\n"
    res = dashboard_story_edit(tmp_path, edits=new, mode="overwrite")
    assert res["status"] == "success"
    assert (tmp_path / "synthesis" / "dashboard_story.md").read_text() == new


def test_editor_patch_applies_cleanly(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    patch = (
        "<<<<replace>>>>\n"
        "# Long-form research story\n"
        "----with----\n"
        "# Polished title\n"
        "<<<<end>>>>"
    )
    res = dashboard_story_edit(tmp_path, edits=patch)
    assert res["status"] == "success"
    assert "Polished title" in (tmp_path / "synthesis" / "dashboard_story.md").read_text()


def test_editor_patch_multiple_blocks(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    patch = (
        "<<<<replace>>>>\n"
        "## 01_demo\n"
        "----with----\n"
        "## Step ONE (polished)\n"
        "<<<<end>>>>\n"
        "<<<<replace>>>>\n"
        "## 02_demo\n"
        "----with----\n"
        "## Step TWO (polished)\n"
        "<<<<end>>>>"
    )
    res = dashboard_story_edit(tmp_path, edits=patch)
    assert res["status"] == "success"
    body = (tmp_path / "synthesis" / "dashboard_story.md").read_text()
    assert "Step ONE" in body and "Step TWO" in body


def test_editor_patch_ambiguous_raises(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    dashboard_story_generate(tmp_path)
    # "##" appears many times — patch block matches >1 → should fail
    patch = "<<<<replace>>>>\n##\n----with----\n##!!\n<<<<end>>>>"
    res = dashboard_story_edit(tmp_path, edits=patch)
    assert res["status"] == "error"
    assert "matched" in res["message"]


def test_apply_patch_blocks_unit():
    text = "alpha beta gamma"
    p = "<<<<replace>>>>\nbeta\n----with----\nDELTA\n<<<<end>>>>"
    assert _apply_patch_blocks(text, p) == "alpha DELTA gamma"


# ──────────────────────────────────────────────────────────────────────
# Quality bar
# ──────────────────────────────────────────────────────────────────────


def test_quality_bar_skipped_without_file(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    res = dashboard_story_quality_bar(tmp_path)
    assert res["status"] == "skipped"


def test_quality_bar_flags_short_story(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "dashboard_story.md").write_text(
        "# T\n\nA tiny story.\n"
    )
    res = dashboard_story_quality_bar(tmp_path)
    assert res["status"] == "success"
    assert any("short" in w for w in res["warnings"])


def test_quality_bar_flags_no_adversarial_callout(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path, with_callout=False)
    dashboard_story_generate(tmp_path)
    res = dashboard_story_quality_bar(tmp_path)
    assert res["status"] == "success"
    assert res["has_adversarial_callout"] is False
    assert any("adversarial" in w for w in res["warnings"])


def test_quality_bar_flags_no_figure(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "dashboard_story.md").write_text(
        " ".join(["This story has no figures at all."] * 100) + "\n"
    )
    res = dashboard_story_quality_bar(tmp_path)
    assert res["has_figure"] is False
    assert any("first 1000 words" in w for w in res["warnings"])


def test_quality_bar_passes_when_all_good(tmp_path: Path):
    """Hand-built story with all 3 criteria satisfied → zero warnings."""
    (tmp_path / "synthesis").mkdir()
    body_words = " ".join(["Quality bar passing story content."] * 250)
    # Put the figure FIRST so the "figure in first 1000 words" rule is met.
    text = (
        "# Title\n\n"
        "![Inline](workspace/x.png)\n\n"
        f"{body_words}\n\n"
        "> **DISAGREES**: contradicts prior literature\n\n"
        f"{body_words}\n"
    )
    (tmp_path / "synthesis" / "dashboard_story.md").write_text(text)
    res = dashboard_story_quality_bar(tmp_path)
    assert res["has_adversarial_callout"] is True
    assert res["has_figure"] is True
    assert res["reading_minutes"] >= 5
    assert res["warnings"] == []


# ──────────────────────────────────────────────────────────────────────
# Renderer integration
# ──────────────────────────────────────────────────────────────────────


def test_renderer_pulls_existing_story_md(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    # Hand-write a story.md so renderer picks it up verbatim instead
    # of regenerating.
    (tmp_path / "synthesis" / "dashboard_story.md").write_text(
        "# Hand-polished\n\nThis prose came from the researcher.\n"
    )
    render_dashboard_v2(tmp_path)
    html = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert "Hand-polished" in html
    assert "This prose came from the researcher" in html


def test_renderer_default_mode_explore_vs_story(tmp_path: Path):
    _scaffold_full_story_fixture(tmp_path)
    render_dashboard_v2(tmp_path, default_mode="story")
    html_story = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert 'content="story"' in html_story
    render_dashboard_v2(tmp_path, default_mode="explore")
    html_expl = (tmp_path / "synthesis" / "dashboard.html").read_text()
    assert 'content="explore"' in html_expl
