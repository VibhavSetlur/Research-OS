"""Tests for the mem_hypothesis_* tools."""

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.memory import (
    hypothesis_add,
    hypothesis_list,
    hypothesis_update,
)


def test_hypothesis_add_auto_ids(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    a = hypothesis_add("Treatment improves outcome", tmp_path)
    b = hypothesis_add("Effect is mediated by Z", tmp_path)
    assert a["status"] == "success"
    assert a["hypothesis"]["id"] == "H1"
    assert b["hypothesis"]["id"] == "H2"


def test_hypothesis_add_custom_id(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    a = hypothesis_add("X", tmp_path, hypothesis_id="HA", status="testing")
    assert a["hypothesis"]["id"] == "HA"


def test_hypothesis_update_status_and_evidence(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    hypothesis_add("Treatment improves outcome", tmp_path)
    upd = hypothesis_update(
        "H1", tmp_path, status="supported", evidence="effect 0.5 (95% CI 0.2-0.8)",
        step="03_logistic",
    )
    assert upd["status"] == "success"
    assert upd["hypothesis"]["status"] == "supported"
    assert len(upd["hypothesis"]["evidence"]) == 1


def test_hypothesis_list_returns_all(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Test")
    hypothesis_add("X", tmp_path)
    hypothesis_add("Y", tmp_path)
    lst = hypothesis_list(tmp_path)
    assert lst["status"] == "success"
    assert lst["count"] == 2
