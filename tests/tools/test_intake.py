"""Tests for tool_intake_autofill."""

from research_os.project_ops import load_state, scaffold_minimal_workspace
from research_os.tools.actions.data.intake import intake_autofill


def test_intake_autofill_with_only_data(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test Project")
    # Drop a CSV with clinical-sounding columns.
    (tmp_path / "inputs" / "raw_data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "raw_data" / "trial.csv").write_text(
        "patient_id,treatment,outcome,age\n1,A,1,55\n2,B,0,42\n"
    )
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    assert res["proposed_domain"] == "clinical"
    # Domain + research_question are persisted to STATE (and intake.md /
    # research_overview.md) — NOT to researcher_config.yaml. The config
    # is for who-and-how (researcher / interaction / model_profile);
    # domain / question are content the AI infers from inputs/.
    state = load_state(tmp_path)
    assert state.get("domain") == "clinical"
    rq_path = tmp_path / "docs" / "research_overview.md"
    assert rq_path.exists(), "intake_autofill should write research_overview.md"
    rq = rq_path.read_text()
    assert "(blank" not in rq


def test_intake_autofill_extracts_question_from_context(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    (tmp_path / "inputs" / "context").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "context" / "notes.md").write_text(
        "# Notes\n\nResearch question: Does sustained X exposure increase Y in cohort Z?\n"
        "\nH1: X is positively associated with Y.\n"
        "H2: Effect is mediated by Z.\n"
    )
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    assert "X exposure" in res["proposed_research_question"]
    assert len(res["proposed_hypotheses"]) >= 2


def test_intake_autofill_blank_inputs(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    # With no files we still get a coherent envelope; domain = general.
    assert res["proposed_domain"] in {"general", "clinical", "epidemiology", "nlp"}


def test_intake_autofill_respects_existing_state(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    # Pre-set a domain in STATE (this is where intake persists it now,
    # not researcher_config.yaml).
    from research_os.project_ops import save_state
    state = load_state(tmp_path)
    state["domain"] = "my_custom_domain"
    save_state(tmp_path, state)

    (tmp_path / "inputs" / "raw_data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "raw_data" / "trial.csv").write_text(
        "patient_id,treatment\n1,A\n"
    )
    res = intake_autofill(tmp_path)
    # Without overwrite=True, the existing domain in state is preserved.
    # The autofill may still propose a domain (returned for review) but
    # must not overwrite the persisted value.
    state2 = load_state(tmp_path)
    assert state2.get("domain") == "my_custom_domain"
    assert res.get("status") == "success"


def test_extract_named_papers_excludes_months_and_journals():
    """v1.3.1: regex must NOT match month names ("Nov 2014", "Mar 2015")
    or bare journal names ("Biology 2014", "Genet 2007"). These false
    matches surfaced in the v1.3.0 PI-level e2e and were noise."""
    from research_os.tools.actions.data.intake import _extract_named_papers
    text = (
        "Sarah pre-processed Himes-style bulk RNA-seq counts in Nov 2014 "
        "from Mar 2015. Cite Himes BE, et al. PLOS ONE 2014 - the canonical "
        "study. See Love MI, Huber W, Anders S. Genome Biology 2014 - DESeq2. "
        "Also Leek JT, Storey JD. PLoS Genet 2007 - SVA. "
        "Subramanian A, et al. PNAS 2005 - GSEA."
    )
    refs = _extract_named_papers(text)
    # Real refs MUST be there
    assert any("Himes" in r for r in refs), f"missed Himes — got {refs}"
    assert any("Subramanian" in r for r in refs), f"missed Subramanian — got {refs}"
    # False matches MUST be absent
    assert not any(r.startswith("Nov ") for r in refs), f"'Nov YYYY' matched: {refs}"
    assert not any(r.startswith("Mar ") for r in refs), f"'Mar YYYY' matched: {refs}"
    assert not any(r.startswith("Biology ") for r in refs), f"'Biology YYYY' matched: {refs}"
    assert not any(r.startswith("Genet ") for r in refs), f"'Genet YYYY' matched: {refs}"


def test_intake_empty_csv_reports_zero_rows_not_minus_one(tmp_path):
    """E7: a genuinely empty CSV must inventory as 0 rows, never -1."""
    scaffold_minimal_workspace(tmp_path, "Test")
    (tmp_path / "inputs" / "raw_data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inputs" / "raw_data" / "empty.csv").write_text("")
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    overview = (tmp_path / "docs" / "research_overview.md").read_text()
    assert "-1" not in overview
    # The empty.csv row must show 0 (or "?"), never -1.
    rows = [ln for ln in overview.splitlines() if "empty.csv" in ln]
    assert rows and ("| 0 |" in rows[0] or "| ? |" in rows[0]), rows


def test_intake_multiline_quoted_cell_row_count_is_accurate(tmp_path):
    """C6: a CSV with an embedded newline in a quoted cell must count rows via
    csv.reader (correct), not a naive line count (which over-reports)."""
    scaffold_minimal_workspace(tmp_path, "Test")
    (tmp_path / "inputs" / "raw_data").mkdir(parents=True, exist_ok=True)
    # 2 data rows; one cell contains an embedded newline. A naive line count
    # would report 3.
    (tmp_path / "inputs" / "raw_data" / "ml.csv").write_text(
        'id,note\n1,"line one\nline two"\n2,ok\n'
    )
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    overview = (tmp_path / "docs" / "research_overview.md").read_text()
    row = [ln for ln in overview.splitlines() if "ml.csv" in ln]
    assert row and "| 2 |" in row[0], row
