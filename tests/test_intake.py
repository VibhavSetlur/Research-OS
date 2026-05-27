"""Tests for tool_intake_autofill."""

import yaml

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.intake import intake_autofill


def test_intake_autofill_with_only_data(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test Project")
    # Drop a CSV with clinical-sounding columns.
    (tmp_path / "inputs" / "raw_data" / "trial.csv").write_text(
        "patient_id,treatment,outcome,age\n1,A,1,55\n2,B,0,42\n"
    )
    res = intake_autofill(tmp_path)
    assert res["status"] == "success"
    assert res["proposed_domain"] == "clinical"
    cfg = yaml.safe_load((tmp_path / "inputs" / "researcher_config.yaml").read_text())
    assert cfg["domain"] == "clinical"
    # research_question.md should no longer look like the placeholder.
    rq = (tmp_path / "docs" / "research_question.md").read_text()
    assert "(blank" not in rq


def test_intake_autofill_extracts_question_from_context(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
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


def test_intake_autofill_respects_existing_config(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    cfg_path = tmp_path / "inputs" / "researcher_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["domain"] = "my_custom_domain"
    cfg_path.write_text(yaml.dump(cfg, sort_keys=False))

    (tmp_path / "inputs" / "raw_data" / "trial.csv").write_text(
        "patient_id,treatment\n1,A\n"
    )
    res = intake_autofill(tmp_path)
    # Without overwrite=True, existing domain is preserved.
    cfg2 = yaml.safe_load(cfg_path.read_text())
    assert cfg2["domain"] == "my_custom_domain"
    assert "domain" not in res["config_fields_updated"]
