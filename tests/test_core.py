import tempfile
from pathlib import Path


from research_os.project_ops import (
    scaffold_minimal_workspace,
    load_state,
    create_numbered_experiment,
    log_decision,
)


def test_scaffold_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        scaffold_minimal_workspace(root, "Test Project")

        assert (root / ".os_state").exists()
        assert (root / "docs").exists()
        assert (root / "inputs").exists()
        assert (root / "workspace").exists()
        assert (root / "synthesis").exists()
        assert (root / "environment").exists()
        assert (root / "workspace" / "workflow.mermaid").exists()
        assert not (root / "workspace" / "01_experiment_baseline").exists()
        assert (root / "inputs" / "researcher_config.yaml").exists()

        state = load_state(root)
        assert state["project_name"] == "Test Project"
        assert state["current_path"] == "main"
        assert "main" in state["paths"]


def test_path_create():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        scaffold_minimal_workspace(root, "Test Project")

        res = create_numbered_experiment(
            root, "data_preparation", hypothesis="Clean data"
        )
        assert "data_preparation" in res["path_id"]
        assert res["path_id"].startswith("01_")
        assert (root / "workspace" / res["path_id"]).exists()
        assert (root / "workspace" / res["path_id"] / "data").exists()
        assert (root / "workspace" / res["path_id"] / "scripts").exists()
        assert (root / "workspace" / res["path_id"] / "README.md").exists()
        assert (root / "workspace" / res["path_id"] / "conclusions.md").exists()

        state = load_state(root)
        assert res["path_id"] in state["paths"]
        assert state["current_path"] == res["path_id"]


def test_path_create_auto_numbers():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        scaffold_minimal_workspace(root, "Test")

        r1 = create_numbered_experiment(root, "first")
        assert r1["path_id"] == "01_first"

        r2 = create_numbered_experiment(root, "second")
        assert r2["path_id"] == "02_second"


def test_path_create_unique_per_number():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        scaffold_minimal_workspace(root, "Test")
        r1 = create_numbered_experiment(root, "test_path")
        r2 = create_numbered_experiment(root, "test_path")
        assert r1["path_id"] == "01_test_path"
        assert r2["path_id"] == "02_test_path"
        assert r1["experiment_number"] + 1 == r2["experiment_number"]


def test_log_decision():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        scaffold_minimal_workspace(root, "Test Project")

        log_decision("Choosing test", "Mann-Whitney U", "Data is skewed", root=root)

        analysis_path = root / "workspace" / "analysis.md"
        assert analysis_path.exists()
        content = analysis_path.read_text()
        assert "Mann-Whitney U" in content
        assert "Data is skewed" in content
