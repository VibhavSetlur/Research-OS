"""Tests for tool_step_env_lock."""

import yaml as _yaml

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.exec import step_env_lock


def test_step_env_lock_writes_requirements_and_pin(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Step Env Lock Test")
    step = create_numbered_experiment(tmp_path, "baseline", hypothesis="", enforce_predecessor_finalized=False)
    res = step_env_lock(tmp_path, step_id=step["path_id"])
    assert res["status"] == "success"
    env_dir = tmp_path / "workspace" / step["path_id"] / "environment"
    assert (env_dir / "requirements.txt").exists()
    assert (env_dir / "python_version.txt").exists()
    assert (env_dir / "session.yaml").exists()
    # python_version.txt is non-empty.
    assert (env_dir / "python_version.txt").read_text().strip()
    assert res["python_version"] == (
        (env_dir / "python_version.txt").read_text().strip()
    )


def test_step_env_lock_missing_step_returns_error(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Missing Step Test")
    res = step_env_lock(tmp_path, step_id="99_ghost")
    assert res["status"] == "error"
    assert "not found" in res["message"].lower()


def test_step_env_lock_defaults_with_warning(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Default Step Test")
    create_numbered_experiment(tmp_path, "baseline", hypothesis="", enforce_predecessor_finalized=False)
    res = step_env_lock(tmp_path)  # no step_id
    assert res["status"] == "success"
    assert "warning" in res
    assert "step_id omitted" in res["warning"]


def test_step_env_lock_writes_conda_yaml(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Conda Spec Test")
    step = create_numbered_experiment(tmp_path, "baseline", hypothesis="", enforce_predecessor_finalized=False)
    res = step_env_lock(
        tmp_path, step_id=step["path_id"], write_conda_yaml=True
    )
    assert res["status"] == "success"
    conda_path = (
        tmp_path / "workspace" / step["path_id"] / "environment" / "conda.yaml"
    )
    assert conda_path.exists()
    spec = _yaml.safe_load(conda_path.read_text())
    assert spec["name"].startswith("research-os-")
    assert any(
        isinstance(d, str) and d.startswith("python=") for d in spec["dependencies"]
    )


def test_step_env_lock_writes_dockerfile(tmp_path):
    scaffold_minimal_workspace(tmp_path, "Dockerfile Test")
    step = create_numbered_experiment(tmp_path, "baseline", hypothesis="", enforce_predecessor_finalized=False)
    res = step_env_lock(
        tmp_path, step_id=step["path_id"], write_dockerfile=True
    )
    assert res["status"] == "success"
    dockerfile = (
        tmp_path / "workspace" / step["path_id"] / "environment" / "Dockerfile"
    )
    assert dockerfile.exists()
    body = dockerfile.read_text()
    assert "FROM python:" in body
    assert "pip install" in body
