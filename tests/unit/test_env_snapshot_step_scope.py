"""Per-step environment snapshot is scoped to THAT step's imports.

Regression guard for the bug where a per-step snapshot (step_id given) pinned
the WHOLE project's imports into workspace/<step>/environment/requirements.txt,
over-broadening what a per-step Docker / daemon run needs.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.tools.actions.exec.environment import (
    _project_python_requirements,
    _scan_python_imports,
)


def _proj_two_steps() -> Path:
    root = Path(tempfile.mkdtemp())
    for step, imp in [("01_a", "import pandas"), ("02_b", "import numpy")]:
        d = root / "workspace" / step / "scripts"
        d.mkdir(parents=True)
        (d / "run.py").write_text(imp + "\nimport os\n")
    return root


def test_scan_imports_whole_project_sees_all():
    root = _proj_two_steps()
    mods = _scan_python_imports(root)
    assert "pandas" in mods and "numpy" in mods


def test_scan_imports_step_scoped():
    root = _proj_two_steps()
    a = _scan_python_imports(root, "01_a")
    b = _scan_python_imports(root, "02_b")
    assert "pandas" in a and "numpy" not in a
    assert "numpy" in b and "pandas" not in b


def test_requirements_step_scoped():
    root = _proj_two_steps()
    req_a = _project_python_requirements(root, "01_a")
    # pandas should be pinned for step 01_a; numpy (from 02_b) should not leak in
    assert "pandas" in req_a
    assert "numpy" not in req_a


def test_requirements_unscoped_is_superset():
    root = _proj_two_steps()
    req_all = _project_python_requirements(root)
    assert "pandas" in req_all and "numpy" in req_all


# ── Step-scoped Dockerfile generation ────────────────────────────────────


def test_docker_generate_step_scoped_writes_into_step_env():
    from research_os.tools.actions.exec.environment import env_docker_generate

    root = _proj_two_steps()
    step_env = root / "workspace" / "01_a" / "environment"
    step_env.mkdir(parents=True, exist_ok=True)
    (step_env / "requirements.txt").write_text("pandas==2.0\n")
    res = env_docker_generate(root, step_id="01_a")
    assert res["status"] == "success"
    assert res["scope"] == "step"
    df = step_env / "Dockerfile"
    assert df.exists()
    text = df.read_text()
    # Builds from the STEP's own requirements, context = the step dir.
    assert "environment/requirements.txt" in text
    assert "01_a" in text  # the header references the step
    assert res["build_context"] == "workspace/01_a"
    # A .dockerignore is written alongside so machine-state never bakes in.
    assert (root / "workspace" / "01_a" / ".dockerignore").exists()


def test_docker_generate_unknown_step_errors():
    from research_os.tools.actions.exec.environment import env_docker_generate

    root = _proj_two_steps()
    res = env_docker_generate(root, step_id="99_nope")
    assert res["status"] == "error"
    assert "not found" in res["message"]


def test_docker_generate_project_scope_unchanged():
    from research_os.tools.actions.exec.environment import env_docker_generate

    root = _proj_two_steps()
    (root / "environment").mkdir(parents=True, exist_ok=True)
    (root / "environment" / "requirements.txt").write_text("pandas==2.0\n")
    res = env_docker_generate(root)  # no step_id → project image
    assert res["status"] == "success"
    assert res["scope"] == "project"
    assert (root / "environment" / "Dockerfile").exists()
