"""Tests for the reasoning / research tools."""

from unittest.mock import patch

from research_os.tools.actions.research import (
    external_tool_instructions,
    plan_step,
    research_method,
    research_tool,
)


def test_research_method_runs_and_writes_report(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace" / "logs").mkdir(parents=True)

    with patch("research_os.tools.actions.search.search_semantic_scholar", return_value=[
        {"title": "Paper 1", "authors": ["A B"], "year": 2024, "url": "http://x",
         "doi": "10.1/x", "abstract": "About logistic regression."}
    ]), patch("research_os.tools.actions.search.search_crossref", return_value=[]), \
         patch("research_os.tools.actions.search.search_pubmed", return_value=[]), \
         patch("research_os.tools.actions.search.search_web", return_value={
             "results": [{"title": "Web", "url": "http://web", "description": "doc"}]
         }):
        res = research_method("logistic regression", tmp_path, limit=3)

    assert res["status"] == "success"
    assert res["academic_count"] == 1
    assert res["web_count"] == 1
    report = tmp_path / res["report_path"]
    assert report.exists()
    body = report.read_text()
    assert "logistic regression" in body.lower()


def test_research_tool_tags_external(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace" / "logs").mkdir(parents=True)

    with patch("research_os.tools.actions.search.search_web") as mock_search:
        mock_search.return_value = {
            "results": [
                {"title": "PyPI page", "url": "https://pypi.org/project/foo",
                 "description": "Open source library."},
                {"title": "WebApp",   "url": "https://example.com/app",
                 "description": "An online tool you use in your browser."},
            ]
        }
        res = research_tool("clustering", tmp_path, language="python")

    assert res["status"] == "success"
    tags = [set(c["accessibility_tags"]) for c in res["candidates"]]
    assert any("installable_via_package_manager" in t for t in tags)
    assert any("external_tool" in t for t in tags)


def test_external_tool_instructions_creates_worksheet(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace" / "logs").mkdir(parents=True)

    res = external_tool_instructions(
        "FancyOnlineTool", "Convert raw DICOMs to NIfTI",
        "https://convert.example.com", tmp_path,
    )
    assert res["status"] == "success"
    worksheet = tmp_path / res["worksheet_path"]
    assert worksheet.exists()
    assert "FancyOnlineTool" in worksheet.read_text()


def test_plan_step_writes_plan(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace" / "logs").mkdir(parents=True)

    res = plan_step("Fit baseline + tuned models with cross-validation", tmp_path)
    assert res["status"] == "success"
    plan = tmp_path / res["plan_path"]
    assert plan.exists()
    assert "Sub-tasks" in plan.read_text()
