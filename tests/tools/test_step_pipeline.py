"""Sub-task pipeline runner tests."""

from pathlib import Path

from research_os.project_ops import (
    create_numbered_experiment,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.exec.step_pipeline import (
    define_pipeline,
    pipeline_status,
    render_pipeline_diagram,
    run_pipeline,
)


def _scaffold(tmp_path: Path):
    scaffold_minimal_workspace(tmp_path, project_name="T", git_init=False, ide_flags=[])
    create_numbered_experiment(tmp_path, "baseline", enforce_predecessor_finalized=False)


def test_define_pipeline_seeds_template(tmp_path: Path):
    _scaffold(tmp_path)
    r = define_pipeline("01_baseline", tmp_path, name="Baseline")
    assert r["status"] == "success"
    assert (tmp_path / "workspace" / "01_baseline" / "pipeline.yaml").exists()


def test_define_pipeline_is_idempotent(tmp_path: Path):
    _scaffold(tmp_path)
    define_pipeline("01_baseline", tmp_path)
    r2 = define_pipeline("01_baseline", tmp_path)
    assert r2["status"] == "exists"


def test_pipeline_status_reports_never_run(tmp_path: Path):
    _scaffold(tmp_path)
    define_pipeline("01_baseline", tmp_path)
    s = pipeline_status("01_baseline", tmp_path)
    assert s["status"] == "success"
    assert s["n_nodes"] == 7   # default 7-node template
    assert s["n_never_run"] == 7


def test_run_pipeline_executes_real_script(tmp_path: Path):
    _scaffold(tmp_path)
    define_pipeline("01_baseline", tmp_path)
    # Replace the template with a minimal 2-node pipeline that actually runs.
    import yaml

    spec = {
        "name": "minimal",
        "schema_version": "1.0",
        "nodes": [
            {"id": "make_input",
             "script": "scripts/make_input.py",
             "inputs": [],
             "outputs": ["data/next_step_output/a.txt"],
             "params": {"seed": 1}},
            {"id": "transform",
             "script": "scripts/transform.py",
             "inputs": ["data/next_step_output/a.txt"],
             "outputs": ["data/next_step_output/b.txt"],
             "params": {"factor": 2}},
        ],
    }
    pp = tmp_path / "workspace" / "01_baseline" / "pipeline.yaml"
    pp.write_text(yaml.safe_dump(spec))
    # Write the scripts.
    sd = tmp_path / "workspace" / "01_baseline" / "scripts"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "make_input.py").write_text(
        '"""Make input."""\n'
        "from pathlib import Path\n"
        "Path('data/next_step_output').mkdir(parents=True, exist_ok=True)\n"
        "Path('data/next_step_output/a.txt').write_text('hello')\n"
    )
    (sd / "transform.py").write_text(
        '"""Transform input."""\n'
        "from pathlib import Path\n"
        "Path('data/next_step_output/b.txt').write_text(\n"
        "    Path('data/next_step_output/a.txt').read_text().upper()\n"
        ")\n"
    )

    r = run_pipeline("01_baseline", tmp_path)
    assert r["status"] == "success", r
    assert r["nodes_total"] == 2
    assert r["nodes_failed"] == 0
    assert (tmp_path / "workspace" / "01_baseline" / "data" / "next_step_output" / "b.txt").exists()


def test_pipeline_caches_on_rerun(tmp_path: Path):
    _scaffold(tmp_path)
    # Reuse the previous test's setup pattern compactly.
    test_run_pipeline_executes_real_script(tmp_path)
    r2 = run_pipeline("01_baseline", tmp_path)
    assert r2["nodes_cached"] >= 1, r2  # at least one node should be cached


def test_render_pipeline_diagram(tmp_path: Path):
    _scaffold(tmp_path)
    define_pipeline("01_baseline", tmp_path)
    r = render_pipeline_diagram("01_baseline", tmp_path)
    assert r["status"] == "success"
    assert (tmp_path / "workspace" / "01_baseline" / "pipeline.mermaid").exists()
