"""Core project_ops smoke tests — scaffold, numbered experiments, decision log."""

import tempfile
from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    load_state,
    log_decision,
    scaffold_minimal_workspace,
)


def test_scaffold_creates_complete_workspace():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(root, "Test Project")

        for top in (".os_state", "docs", "inputs", "workspace", "synthesis", "environment"):
            assert (root / top).exists(), top
        assert (root / "workspace" / "workflow.mermaid").exists()
        assert (root / "inputs" / "researcher_config.yaml").exists()
        assert (root / "AGENTS.md").exists()
        # No pre-baked synthesis output.
        assert not (root / "synthesis" / "paper.md").exists()

        state = load_state(root)
        assert state["project_name"] == "Test Project"
        assert state["current_path"] == "main"
        assert "main" in state["paths"]


def test_path_create_creates_full_subtree():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(root, "Test Project")

        res = create_numbered_experiment(root, "data_preparation", hypothesis="Clean data")
        assert "data_preparation" in res["path_id"]
        assert res["path_id"].startswith("01_")
        exp = root / "workspace" / res["path_id"]
        assert exp.exists()
        for sub in ("scripts", "data/input", "data/output", "outputs/reports",
                    "outputs/figures", "outputs/tables", "environment"):
            assert (exp / sub).exists(), sub
        assert (exp / "README.md").exists()
        assert (exp / "conclusions.md").exists()


def test_path_create_auto_numbers():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(root, "Test")
        r1 = create_numbered_experiment(root, "first")
        r2 = create_numbered_experiment(root, "second")
        assert r1["path_id"] == "01_first"
        assert r2["path_id"] == "02_second"


def test_log_decision_writes_analysis_md():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(root, "Test Project")

        log_decision("Choosing test", "Mann-Whitney U", "Data is skewed", root=root)

        content = (root / "workspace" / "analysis.md").read_text()
        assert "Mann-Whitney U" in content
        assert "Data is skewed" in content
