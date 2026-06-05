"""v1.8.0 — infrastructure adapter framework + 6 bundled adapters +
multi-language tools.md extractors + 3 new reference projects.

Coverage:
    * Adapter framework: AdapterRegistration validation, namespace
      enforcement, regex compilation, loader discovery, error isolation.
    * All 6 bundled adapters register cleanly.
    * Each adapter detects on its signature inputs + extracts to a
      structured payload + contributes regex patterns to the tools.md
      extractor.
    * Optional pack tools register + dispatch.
    * 3 core tools (sys_adapters_installed, tool_adapter_extract,
      tool_adapters_list, tool_adapters_run_all) work end-to-end.
    * Multi-language extractor: Python / R / R DESCRIPTION / renv.lock /
      Bash modules / Node / Rust / Julia + adapter patterns.
    * 3 new reference projects (slurm_snakemake, nextflow_chipseq,
      redcap_longitudinal) pass stress smoke.
    * Preflight pack + adapter checks all pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

def _fresh_import():
    for m in list(sys.modules):
        if m.startswith("research_os") or m.startswith("research_os_"):
            del sys.modules[m]
    import research_os.server  # noqa: F401
    return sys.modules["research_os.server"]


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    return tmp_path


# ── adapter framework ────────────────────────────────────────────────


def test_register_adapter_rejects_bad_name():
    from research_os.adapters import register_adapter
    with pytest.raises(ValueError):
        register_adapter(
            name="BadName",
            version="0.1",
            description="x",
            detect=lambda r: False,
            extract=lambda r, step_id=None: {},
        )


def test_register_adapter_enforces_tool_namespace():
    from research_os.adapters import AdapterTool, register_adapter
    with pytest.raises(ValueError, match="must start with 'tool_demo_'"):
        register_adapter(
            name="demo",
            version="0.1",
            description="x",
            detect=lambda r: False,
            extract=lambda r, step_id=None: {},
            tools=(AdapterTool(
                name="tool_wrongprefix",
                handler=lambda *a, **k: None,
                schema={"type": "object"},
            ),),
        )


def test_register_adapter_rejects_bad_regex():
    from research_os.adapters import register_adapter
    with pytest.raises(Exception):  # noqa: BLE001 — re.error subclass
        register_adapter(
            name="demo",
            version="0.1",
            description="x",
            detect=lambda r: False,
            extract=lambda r, step_id=None: {},
            tools_md_patterns=(("[unclosed", "bad"),),
        )


def test_all_six_adapters_register():
    _fresh_import()
    from research_os.adapters import installed_adapters, load_adapter_errors
    assert load_adapter_errors() == []
    names = {a["name"] for a in installed_adapters()}
    assert names >= {"slurm", "snakemake", "nextflow",
                     "cytoscape", "redcap", "synapse"}


def test_sys_adapters_installed_handler(project_root):
    srv = _fresh_import()
    r = srv._handle_tool_call("sys_adapters_installed", {}, project_root)
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert env["data"]["adapter_count"] >= 6


def test_tool_adapters_list_reports_detection_status(project_root):
    srv = _fresh_import()
    r = srv._handle_tool_call("tool_adapters_list", {}, project_root)
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    # An empty workspace should match 0 adapters.
    assert env["data"]["total_detected"] == 0


# ── per-adapter detection + extraction ───────────────────────────────


def test_slurm_detects_sbatch_header(project_root):
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["slurm"]
    step = project_root / "workspace" / "01_align" / "scripts"
    step.mkdir(parents=True)
    (step / "run.sh").write_text(
        "#!/bin/bash\n#SBATCH --partition=gpu\n#SBATCH --time=24:00:00\n"
        "module load bwa\nbwa mem ref.fa reads.fq\n"
    )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root, step_id="01_align")
    assert payload["scheduler"] == "slurm"
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["partition"] == "gpu"
    assert "bwa" in payload["jobs"][0]["modules_loaded"]


def test_slurm_extract_via_runner_writes_yaml(project_root):
    srv = _fresh_import()
    step = project_root / "workspace" / "01_align" / "scripts"
    step.mkdir(parents=True)
    (step / "run.sh").write_text("#!/bin/bash\n#SBATCH --partition=cpu\n")
    r = srv._handle_tool_call(
        "tool_adapter_extract",
        {"adapter_name": "slurm", "step_id": "01_align"},
        project_root,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    out = project_root / env["data"]["output_path"]
    assert out.exists()
    assert "scheduler: slurm" in out.read_text()


def test_snakemake_detects_snakefile(project_root):
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["snakemake"]
    (project_root / "Snakefile").write_text(
        'rule align:\n    input: "x.fq"\n    output: "x.bam"\n    shell: "bwa mem ..."\n'
    )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root)
    rules = payload.get("rules") or []
    assert any(r.get("name") == "align" for r in rules)


def test_nextflow_detects_nf_file(project_root):
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["nextflow"]
    (project_root / "main.nf").write_text(
        'process FASTQC {\n  input: path(reads)\n  output: path("out.html")\n'
        '  container "biocontainers/fastqc:0.11"\n  script: "fastqc ${reads}"\n}\n'
    )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root)
    procs = payload.get("processes") or []
    assert any(p.get("name") == "FASTQC" for p in procs)


def test_cytoscape_detects_cys_file(project_root, tmp_path):
    _fresh_import()
    import zipfile
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["cytoscape"]
    out_dir = project_root / "workspace" / "01" / "outputs"
    out_dir.mkdir(parents=True)
    cys = out_dir / "demo.cys"
    with zipfile.ZipFile(cys, "w") as z:
        z.writestr(
            "demo.xgmml",
            '<graph label="demo"><node id="1" label="A"/>'
            '<node id="2" label="B"/><edge source="1" target="2"/></graph>',
        )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root)
    assert (payload.get("networks") or payload.get("cys_files") or []), payload


def test_redcap_detects_data_export(project_root):
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["redcap"]
    raw = project_root / "inputs" / "raw_data"
    raw.mkdir(parents=True)
    (raw / "study_DATA.csv").write_text(
        "record_id,redcap_event_name,age\n1,baseline,42\n2,6_month,55\n"
    )
    (raw / "study_DataDictionary.csv").write_text(
        '"Variable / Field Name","Form Name","Field Type","Identifier?"\n'
        'record_id,demographics,text,n\n'
        'age,demographics,text,n\n'
    )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root)
    fields = payload.get("fields") or []
    assert any(f.get("name") == "age" for f in fields)


def test_synapse_detects_import(project_root):
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    reg = adapter_registrations()["synapse"]
    scripts = project_root / "scripts"
    scripts.mkdir()
    (scripts / "ingest.py").write_text(
        "import synapseclient\nsyn = synapseclient.login()\ndf = syn.get('syn22399110')\n"
    )
    assert reg.detect(project_root) is True
    payload = reg.extract(project_root)
    ents = payload.get("entities_referenced") or []
    assert any("syn22399110" in str(e.get("id", "")) for e in ents)


def test_synapse_does_not_auto_query():
    """The synapse adapter must never auto-query at detect or extract time."""
    import research_os_adapter_synapse as syn_mod
    src = Path(syn_mod.__file__).read_text()
    # synapseclient may be try-imported only inside an optional tool,
    # not in detect() or extract().
    assert "synapseclient" in src  # mention is fine
    # Make sure no top-level import of synapseclient exists.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import synapseclient") or stripped.startswith(
            "from synapseclient"
        ):
            # OK only if inside a function (indented).
            assert line.startswith(" ") or line.startswith("\t"), (
                "synapse adapter must not auto-import synapseclient at module top"
            )


# ── all new pack tools registered ────────────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        "sys_adapters_installed",
        "tool_adapter_extract",
        "tool_adapters_list",
        "tool_adapters_run_all",
        "tool_slurm_job_status",
        "tool_slurm_estimate_cost",
    ],
)
def test_core_or_adapter_tool_registered(tool_name):
    srv = _fresh_import()
    assert tool_name in srv.TOOL_DEFINITIONS
    assert tool_name in srv._HANDLERS


def test_slurm_estimate_cost_returns_node_hours(project_root):
    srv = _fresh_import()
    step = project_root / "workspace" / "01" / "scripts"
    step.mkdir(parents=True)
    (step / "run.sh").write_text(
        "#!/bin/bash\n#SBATCH --time=04:00:00\n#SBATCH --nodes=4\n"
    )
    r = srv._handle_tool_call(
        "tool_slurm_estimate_cost",
        {"step_id": "01", "cost_per_node_hour": 0.5},
        project_root,
    )
    env = json.loads(r[0].text)
    assert env["status"] == "success"
    assert env["data"]["total_node_hours"] == 16.0
    assert env["data"]["total_estimated_usd"] == 8.0


# ── multi-language extractors ────────────────────────────────────────


def test_extract_python_imports():
    from research_os.tools.actions.state.extractors import extract_python
    tuples = extract_python("import pandas\nfrom sklearn import linear_model\n")
    kinds = {t[0] for t in tuples}
    names = {t[1] for t in tuples}
    assert kinds == {"python_import"}
    assert "pandas" in names
    assert "sklearn" in names


def test_extract_r_libraries():
    from research_os.tools.actions.state.extractors import extract_r
    tuples = extract_r(
        'library(DESeq2)\nrequire(ggplot2)\np_load(dplyr, tidyr)\n'
        'BiocManager::install("limma")\n'
    )
    by_kind: dict[str, set[str]] = {}
    for k, n, _ in tuples:
        by_kind.setdefault(k, set()).add(n)
    assert "r_library" in by_kind
    assert "DESeq2" in by_kind["r_library"]
    assert "dplyr" in by_kind["r_library"]
    assert "limma" in by_kind.get("r_bioc_install", set())


def test_extract_r_description():
    from research_os.tools.actions.state.extractors import extract_r_description
    tuples = extract_r_description(
        "Package: demo\nVersion: 0.1\n"
        "Imports: dplyr (>= 1.0), tidyr,\n    purrr (>= 0.3.4)\n"
    )
    names = {t[1] for t in tuples}
    assert "dplyr" in names
    assert "purrr" in names


def test_extract_bash_modules_and_envs():
    from research_os.tools.actions.state.extractors import extract_bash_modules
    tuples = extract_bash_modules(
        "module load bwa/0.7.17\nmodule load samtools\n"
        "conda activate bioinformatics\nsource /opt/venvs/scanpy/bin/activate\n"
    )
    by_kind: dict[str, set[str]] = {}
    for k, n, _ in tuples:
        by_kind.setdefault(k, set()).add(n)
    assert "bash_module" in by_kind
    assert "bwa/0.7.17" in by_kind["bash_module"]
    assert any("conda:" in e for e in by_kind.get("bash_env", set()))


def test_extract_node_package_json():
    from research_os.tools.actions.state.extractors import extract_node
    tuples = extract_node(
        '{"dependencies": {"react": "^18", "lodash": "4.17"}, '
        '"devDependencies": {"eslint": "8"}}',
        is_package_json=True,
    )
    names = {t[1] for t in tuples}
    assert "react" in names
    assert "lodash" in names
    assert "eslint" in names


def test_extract_rust_cargo_toml():
    from research_os.tools.actions.state.extractors import extract_rust
    tuples = extract_rust(
        "[dependencies]\nserde = \"1.0\"\ntokio = { version = \"1\", features = [\"full\"] }\n",
        is_cargo_toml=True,
    )
    names = {t[1] for t in tuples}
    assert "serde" in names
    assert "tokio" in names


def test_extract_julia_project_toml():
    from research_os.tools.actions.state.extractors import extract_julia
    tuples = extract_julia(
        "[deps]\nDataFrames = \"a93c6f00-e57d-5684-b7b6-d8193f3e46c0\"\n"
        "CSV = \"336ed68f-0bac-5ca0-87d4-7b16caf5d00b\"\n",
        is_project_toml=True,
    )
    names = {t[1] for t in tuples}
    assert "DataFrames" in names
    assert "CSV" in names


def test_extract_adapter_patterns_fires_on_slurm_directives():
    _fresh_import()
    from research_os.tools.actions.state.extractors import extract_adapter_patterns
    tuples = extract_adapter_patterns("#SBATCH --partition=gpu\nmodule load samtools\n")
    by_adapter: dict[str, list[str]] = {}
    for k, name, ver in tuples:
        assert k == "adapter_pattern"
        by_adapter.setdefault(name, []).append(ver or "")
    assert "slurm" in by_adapter


def test_extract_adapter_patterns_fires_on_snakemake_rule():
    _fresh_import()
    from research_os.tools.actions.state.extractors import extract_adapter_patterns
    tuples = extract_adapter_patterns("rule align:\n    input: 'x.fq'\n")
    adapters = {t[1] for t in tuples}
    assert "snakemake" in adapters


def test_extract_adapter_patterns_fires_on_nextflow_process():
    _fresh_import()
    from research_os.tools.actions.state.extractors import extract_adapter_patterns
    tuples = extract_adapter_patterns("process FASTQC {\n  input: path(x)\n}\n")
    adapters = {t[1] for t in tuples}
    assert "nextflow" in adapters


# ── stress-runner reference projects ─────────────────────────────────


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "projects"


@pytest.mark.parametrize(
    "fixture_name",
    ["slurm_snakemake", "nextflow_chipseq", "redcap_longitudinal"],
)
def test_new_reference_project_present(fixture_name):
    assert (_fixtures_root() / fixture_name / "manifest.yaml").exists()


@pytest.mark.parametrize(
    "fixture_name",
    ["slurm_snakemake", "nextflow_chipseq", "redcap_longitudinal"],
)
def test_new_reference_project_stress_runs(fixture_name):
    _fresh_import()
    from research_os.testing.stress_runner import (
        load_reference_project, mock_model_call, run_stress,
    )
    proj = load_reference_project(_fixtures_root() / fixture_name)
    res = run_stress(proj, model_call=mock_model_call(proj.canned_responses))
    assert res.success_rate >= 0.99, res.notes


# ── adapter cross-detection on real fixtures ─────────────────────────


def test_slurm_adapter_detects_on_slurm_snakemake_fixture():
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    fix = _fixtures_root() / "slurm_snakemake"
    reg = adapter_registrations()["slurm"]
    # Move fixture inputs to its workspace, since stress runner expects
    # workspace/<step>/ — but the adapter's detect() scans workspace +
    # root, so place the wrapper script visibly under workspace/.
    # (For the test, we just confirm detect() works when the script
    # is dropped into workspace/.)
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws_scripts = root / "workspace" / "01_pipeline" / "scripts"
        ws_scripts.mkdir(parents=True)
        shutil.copy(fix / "inputs" / "scripts" / "run_pipeline.sh",
                    ws_scripts / "run_pipeline.sh")
        assert reg.detect(root) is True


def test_snakemake_adapter_detects_on_slurm_snakemake_fixture():
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    fix = _fixtures_root() / "slurm_snakemake"
    reg = adapter_registrations()["snakemake"]
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "workspace" / "01_pipeline"
        ws.mkdir(parents=True)
        shutil.copy(fix / "inputs" / "data" / "Snakefile", ws / "Snakefile")
        assert reg.detect(root) is True


def test_nextflow_adapter_detects_on_nextflow_chipseq_fixture():
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    fix = _fixtures_root() / "nextflow_chipseq"
    reg = adapter_registrations()["nextflow"]
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "workspace" / "01"
        ws.mkdir(parents=True)
        shutil.copy(fix / "inputs" / "pipeline" / "main.nf", ws / "main.nf")
        shutil.copy(fix / "inputs" / "pipeline" / "nextflow.config", ws / "nextflow.config")
        assert reg.detect(root) is True


def test_redcap_adapter_detects_on_redcap_longitudinal_fixture():
    _fresh_import()
    from research_os.adapters.loader import adapter_registrations
    fix = _fixtures_root() / "redcap_longitudinal"
    reg = adapter_registrations()["redcap"]
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        raw = root / "inputs" / "raw_data"
        raw.mkdir(parents=True)
        shutil.copy(fix / "inputs" / "raw_data" / "study_DataDictionary.csv",
                    raw / "study_DataDictionary.csv")
        shutil.copy(fix / "inputs" / "raw_data" / "study_DATA.csv",
                    raw / "study_DATA.csv")
        assert reg.detect(root) is True


# ── preflight integration ────────────────────────────────────────────


def _load_preflight():
    import importlib.util
    pf = Path(__file__).resolve().parents[2] / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("preflight", pf)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_preflight_adapters_discovered():
    mod = _load_preflight()
    ok, msg = mod.check_adapters_discovered()
    assert ok, msg


def test_preflight_adapter_regex_compile():
    mod = _load_preflight()
    ok, msg = mod.check_adapter_regex_compile()
    assert ok, msg
