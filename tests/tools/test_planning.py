"""Tests for the iterative-planning tools."""

from unittest.mock import patch

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.research.planning import (
    branch_recommendation,
    dead_end_lessons,
    plan_next_step,
    progress_digest,
    quick_review,
    session_resume,
)


def test_plan_next_step_writes_report(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    with patch(
        "research_os.tools.actions.search.search.search_semantic_scholar",
        return_value=[{"title": "T", "authors": ["A"], "year": 2024,
                       "url": "http://x", "doi": "10.1/x", "abstract": ""}],
    ), patch(
        "research_os.tools.actions.search.search.search_web",
        return_value={"results": [{"title": "tool",
                                   "url": "http://t", "description": "d"}]},
    ):
        res = plan_next_step(tmp_path, goal="baseline EDA")
    assert res["status"] == "success"
    plan = tmp_path / res["plan_path"]
    assert plan.exists()
    body = plan.read_text()
    assert "Next-step plan" in body
    assert "baseline EDA" in body or "Recommended next steps" in body


def test_plan_next_step_with_no_providers(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    with patch(
        "research_os.tools.actions.search.search.search_semantic_scholar",
        side_effect=Exception("offline"),
    ), patch(
        "research_os.tools.actions.search.search.search_web",
        side_effect=Exception("offline"),
    ):
        res = plan_next_step(tmp_path, goal="anything")
    assert res["status"] == "success"
    assert res["literature_hits"] == 0


def test_branch_recommendation_returns_guidance(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    res = branch_recommendation(tmp_path, reason="alternative model")
    assert res["status"] == "success"
    assert res["recommendation"] in {"branch", "extend_current"}
    assert "guidance" in res


def test_session_resume_returns_brief(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Resume Test")
    res = session_resume(tmp_path)
    assert res["status"] == "success"
    assert res["project_name"] == "Resume Test"
    assert res["pause_reason"] in {
        "unknown", "fresh_session", "mid_step", "completed_step",
        "dead_end", "long_running_job", "ctx_exhaustion",
    }
    assert "resume_message" in res
    # The resume record is persisted.
    assert "resume_record" in res


def test_progress_digest_counts_outputs(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Digest Test")
    # Add a fake figure to verify counting works.
    fig_dir = tmp_path / "workspace" / "01_eda" / "outputs" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    (fig_dir / "scatter.png").write_bytes(b"\x89PNG\r\n")
    res = progress_digest(tmp_path)
    assert res["status"] == "success"
    assert (tmp_path / res["digest_path"]).exists()
    assert "outputs" in res
    assert "hypotheses_by_status" in res


def test_dead_end_lessons_with_no_dead_ends(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Lessons Test")
    res = dead_end_lessons(tmp_path)
    assert res["status"] == "success"
    assert res["dead_end_count"] == 0
    assert (tmp_path / res["report_path"]).exists()


def test_quick_review_stages_skeleton(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Review Test")
    # inputs/literature/ is a LAZY dir created at first write.
    (tmp_path / "inputs" / "literature").mkdir(parents=True, exist_ok=True)
    fake_pdf = tmp_path / "inputs" / "literature" / "paper.pdf"
    fake_pdf.write_text("%PDF-1.4 fake")
    res = quick_review(tmp_path, "inputs/literature/paper.pdf")
    assert res["status"] == "success"
    review = tmp_path / res["review_path"]
    assert review.exists()
    body = review.read_text()
    assert "Verdict" in body
    assert "Three strengths" in body
    assert "Five concerns" in body


def test_quick_review_missing_paper(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Review Test")
    res = quick_review(tmp_path, "inputs/literature/missing.pdf")
    assert res["status"] == "error"
