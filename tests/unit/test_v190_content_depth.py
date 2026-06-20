"""Content depth audit tests (per-section + cliché detection +
per-step coverage promotion)."""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.audit.content_depth import (
    CLICHES,
    audit_cliches,
    audit_abstract,
    audit_discussion,
    audit_introduction,
    audit_methods,
    audit_references_present,
    audit_results,
    section_substantiveness,
)


# ── per-section ─────────────────────────────────────────────────────


def test_abstract_without_number_blocks():
    res = audit_abstract("We did things. We found qualitative effects.")
    assert any("number" in b.lower() for b in res["blockers"])


def test_abstract_with_number_and_verb_passes():
    text = "We applied PCA. We found a 42% reduction in noise."
    res = audit_abstract(text)
    assert res["blockers"] == []


def test_introduction_without_pivot_blocks():
    text = (
        "Background per (Smith 2024). Per (Jones 2023). "
        "Per (Doe 2024). Things are studied."
    )
    res = audit_introduction(text)
    assert any("pivot" in b.lower() or "in this study" in b.lower() for b in res["blockers"])


def test_introduction_few_citations_blocks():
    text = "In this study, we report a thing."
    res = audit_introduction(text)
    assert any("3" in b for b in res["blockers"])


def test_introduction_full_passes():
    text = (
        "Background per (Smith 2024). Per (Jones 2023). "
        "Per (Doe 2024). In this study, we report X."
    )
    res = audit_introduction(text)
    assert res["blockers"] == []


def test_methods_low_step_coverage_blocks(tmp_path: Path):
    # 4 steps in workspace, none mentioned in methods text.
    workspace = tmp_path / "workspace"
    for i in range(1, 5):
        d = workspace / f"{i:02d}_step_alpha"
        d.mkdir(parents=True)
        (d / "step_summary.yaml").write_text("primary_tool: tool_x\n")
    text = "We used some methods."
    res = audit_methods(text, tmp_path)
    assert res["step_coverage_pct"] < 50
    assert res["blockers"]


def test_methods_full_coverage_passes(tmp_path: Path):
    workspace = tmp_path / "workspace"
    for slug in ("01_alpha", "02_beta", "03_gamma"):
        (workspace / slug).mkdir(parents=True)
        (workspace / slug / "step_summary.yaml").write_text("primary_tool: tool_x\n")
    text = "We ran alpha, beta, and gamma steps in sequence."
    res = audit_methods(text, tmp_path)
    assert res["step_coverage_pct"] == 100


def test_methods_underscored_slug_matches_prose(tmp_path: Path):
    """C7: a step folder slug (baseline_eda) described in natural-language
    Methods prose ('baseline EDA', with a space) must count as covered.
    Previously the underscored token never matched prose → false 0% block."""
    workspace = tmp_path / "workspace"
    for slug in ("03_baseline_eda", "04_logistic_regression"):
        (workspace / slug).mkdir(parents=True)
        (workspace / slug / "step_summary.yaml").write_text("primary_tool: tool_x\n")
    text = (
        "We first performed baseline EDA on the cohort, then fit a "
        "logistic regression model to the outcome."
    )
    res = audit_methods(text, tmp_path)
    assert res["step_coverage_pct"] == 100
    assert res["blockers"] == []


def test_results_no_statistics_warns(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    text = "We saw an effect."
    res = audit_results(text, tmp_path)
    assert any("statistic" in w.lower() for w in res["warnings"])


def test_results_with_stats_passes(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    text = "We observed a strong effect (p = 0.01, 95% CI [0.1, 0.3])."
    res = audit_results(text, tmp_path)
    assert res["n_statistics"] >= 1


def test_discussion_without_limitations_blocks(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    text = "We discussed. Future work includes follow-up."
    res = audit_discussion(text, tmp_path)
    assert any("limitations" in b.lower() for b in res["blockers"])


def test_discussion_without_future_work_blocks(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    text = "We discussed. ### Limitations\n\nSmall sample size limited the analysis."
    res = audit_discussion(text, tmp_path)
    assert any("future" in b.lower() for b in res["blockers"])


def test_discussion_full_passes(tmp_path: Path):
    (tmp_path / "workspace").mkdir()
    text = (
        "Our findings extend prior work.\n\n"
        "### Limitations\n\nThe cohort is limited; we cannot generalize.\n\n"
        "Future work should replicate in a larger sample."
    )
    res = audit_discussion(text, tmp_path)
    assert res["blockers"] == []


# ── references ─────────────────────────────────────────────────────


def test_references_missing_cited_key_blocks():
    text = (
        "## Introduction\n\nPer [@orphan2024] we expected.\n\n"
        "## References\n\n@other2024 Other.\n"
    )
    res = audit_references_present(text)
    assert any("orphan2024" in b for b in res["blockers"])


# ── cliché ─────────────────────────────────────────────────────────


def test_audit_cliches_each_cliche_fires(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    paper = tmp_path / "synthesis" / "paper.md"
    body = "\n\n".join(cliche.capitalize() + " more text." for cliche, _ in CLICHES)
    paper.write_text(body)
    res = audit_cliches("synthesis/paper.md", tmp_path)
    # All cliché patterns should be hit at least once.
    assert res["n_hits"] >= len(CLICHES)


def test_audit_cliches_clean_paper_passes(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    paper = tmp_path / "synthesis" / "paper.md"
    paper.write_text("We found that 42% of cells expressed the marker.")
    res = audit_cliches("synthesis/paper.md", tmp_path)
    assert res["n_hits"] == 0


# ── wrapper section_substantiveness ────────────────────────────────


def _full_paper() -> str:
    return (
        "# Title\n\n"
        "## Abstract\n\n"
        "We applied X. We found a 42% effect in n=100 samples (p < 0.01)."
        "We demonstrate this consistently.\n\n"
        "## Introduction\n\n"
        "Per (Smith 2024). Per (Jones 2023). Per (Doe 2024). "
        "In this study, we report a 42% effect.\n\n"
        "## Methods\n\n"
        "We ran alpha, beta, gamma steps in sequence.\n\n"
        "## Results\n\n"
        "Strong effect (p = 0.01, 95% CI [0.1, 0.3]).\n\n"
        "## Discussion\n\n"
        "Findings extend prior work.\n\n"
        "### Limitations\n\nCohort limited; we cannot fully generalize. Caveats remain.\n\n"
        "Future work: replicate.\n\n"
        "## References\n\n"
        "@smith2024 paper one.\n"
    )


def test_section_substantiveness_full_paper_passes(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "synthesis" / "paper.md").write_text(_full_paper())
    res = section_substantiveness(tmp_path)
    assert res["status"] == "success", res["blockers"]


def test_section_substantiveness_thin_paper_blocks(tmp_path: Path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "synthesis" / "paper.md").write_text(
        "# T\n\n## Abstract\n\nQualitative things.\n\n"
        "## Introduction\n\nWe did stuff.\n\n"
        "## Methods\n\nThings.\n\n"
        "## Results\n\nWe saw things.\n\n"
        "## Discussion\n\nMore generic words.\n"
    )
    res = section_substantiveness(tmp_path)
    assert res["status"] == "error"
    assert res["blockers"]
