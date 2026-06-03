"""Tests for tool_workflow_dag."""

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.state.path import workflow_dag


def test_dag_with_no_steps_returns_empty(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Empty DAG Test")
    res = workflow_dag(tmp_path)
    assert res["status"] == "success"
    assert res["nodes"] == 0
    assert res["edges"] == 0


def test_dag_writes_mermaid_with_one_step(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Single Step DAG")
    create_numbered_experiment(tmp_path, "baseline_eda", hypothesis="H0", enforce_predecessor_finalized=False)
    res = workflow_dag(tmp_path)
    assert res["status"] == "success"
    assert res["nodes"] == 1
    mmd = tmp_path / res["mermaid_path"]
    assert mmd.exists()
    body = mmd.read_text()
    assert "graph TD" in body
    assert "01_baseline_eda" in body
    # Default node colour class.
    assert "classDef" in body
    assert ":::active" in body or ":::completed" in body


def test_dag_derives_edges_from_data_input_symlinks(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Edges DAG")
    create_numbered_experiment(tmp_path, "data_prep", hypothesis="", enforce_predecessor_finalized=False)
    # Step 2 omits from_step → create_numbered_experiment auto-links
    # data/input to step 1's data/output. That symlink is what
    # workflow_dag walks to derive the edge.
    create_numbered_experiment(tmp_path, "modeling", hypothesis="", enforce_predecessor_finalized=False)
    res = workflow_dag(tmp_path)
    assert res["status"] == "success"
    assert res["nodes"] == 2
    assert res["edges"] >= 1
    mmd = (tmp_path / res["mermaid_path"]).read_text()
    assert "01_data_prep" in mmd
    assert "02_modeling" in mmd


def test_dag_auto_refreshes_on_path_create(tmp_path):
    """create_numbered_experiment should now write the DAG file too."""
    scaffold_minimal_workspace(tmp_path, "Auto-refresh DAG")
    create_numbered_experiment(tmp_path, "first_step", hypothesis="", enforce_predecessor_finalized=False)
    dag = tmp_path / "docs" / "workflow_dag.mermaid"
    assert dag.exists()
    assert "01_first_step" in dag.read_text()
