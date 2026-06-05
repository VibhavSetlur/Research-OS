"""Synthesis preview tests."""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.synthesis.preview import synthesis_preview


def _scaffold(
    root: Path,
    n_steps: int = 3,
    with_disagree: bool = True,
    with_figures: bool = True,
) -> None:
    (root / "workspace").mkdir(parents=True)
    (root / "workspace" / "citations.md").write_text(
        "@a2024 paper one\n@b2025 paper two\n"
    )
    for i in range(1, n_steps + 1):
        d = root / "workspace" / f"{i:02d}_step"
        d.mkdir()
        (d / "conclusions.md").write_text("## Findings\n\n" + "Words " * 50)
        (d / "step_summary.yaml").write_text(
            f"step_id: {i:02d}_step\nprimary_tool: tool_x\n"
        )
        if with_figures:
            figs = d / "outputs" / "figures"
            figs.mkdir(parents=True)
            (figs / "focal.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        reports = d / "outputs" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        if with_disagree and i == 1:
            (reports / "findings_vs_literature.md").write_text(
                "## Claim 1\n\nVerdict: DISAGREES with literature.\n"
            )


def test_preview_paper_basic(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="paper")
    assert res["target"] == "paper"
    assert res["predicted_total_word_count"] > 0
    assert "predicted_word_count_per_section" in res
    assert res["predicted_page_count"] >= 1


def test_preview_dashboard_target(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="dashboard")
    assert res["target"] == "dashboard"
    assert "findings" in res["predicted_word_count_per_section"]


def test_preview_slides_returns_slide_count(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="slides")
    assert res["predicted_slide_count"] is not None


def test_preview_citations_listed(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="paper")
    assert set(res["predicted_citations"]) >= {"a2024", "b2025"}


def test_preview_figures_listed(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="paper")
    assert len(res["predicted_figures_embedded"]) >= 3


def test_preview_gap_when_no_disagree(tmp_path: Path):
    _scaffold(tmp_path, with_disagree=False)
    res = synthesis_preview(tmp_path, target="paper")
    gap_types = [g["gap_type"] for g in res["detected_gaps"]]
    assert "no_disagree_verdicts" in gap_types


def test_preview_estimated_render_time_plausible(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="paper")
    assert 0 < res["estimated_render_time_seconds"] < 300


def test_preview_diff_mode_against_existing(tmp_path: Path):
    _scaffold(tmp_path)
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis" / "paper.md").write_text("Tiny stub.\n")
    res = synthesis_preview(tmp_path, target="paper", mode="diff")
    assert "diff_mode" in res
    assert res["diff_mode"]["net_word_delta"] > 0


def test_preview_diff_mode_when_no_existing(tmp_path: Path):
    _scaffold(tmp_path)
    res = synthesis_preview(tmp_path, target="paper", mode="diff")
    assert "diff_mode" in res
    assert all(v == "new" for v in res["diff_mode"]["what_would_change"].values())
