"""Tests for tool_intake_autofill."""

import yaml

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
