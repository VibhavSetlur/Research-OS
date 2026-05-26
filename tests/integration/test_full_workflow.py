import json
import pytest
from unittest import mock
from research_os.server import _handle_tool_call


@pytest.fixture
def workspace_root(tmp_path):
    root = tmp_path / "test_workspace"
    root.mkdir()
    # Write a dummy config
    inputs_dir = root / "inputs"
    inputs_dir.mkdir()
    config = 'researcher: {name: "Test"}\nmodel_profile: "large"'
    (inputs_dir / "researcher_config.yaml").write_text(config)

    # Write dummy CSV
    raw_dir = inputs_dir / "raw_data"
    raw_dir.mkdir()
    (raw_dir / "dummy.csv").write_text("x,y\n1,2\n3,4\n5,6")

    # Write dummy protocol
    proto_dir = root / "src" / "research_os" / "protocols"
    proto_dir.mkdir(parents=True, exist_ok=True)
    proto_content = "name: domain_analysis\ndescription: test\nsteps: []\n"
    (proto_dir / "domain_analysis.yaml").write_text(proto_content)

    return root


def test_full_workflow(workspace_root):
    root = workspace_root

    # 1. Initialize project
    res = _handle_tool_call(
        "sys.workspace.scaffold", {"project_name": "Test Project"}, root
    )
    assert "success" in res[0].text

    # 2. Get guidance
    res = _handle_tool_call(
        "sys.guidance.get", {"protocol_name": "domain_analysis"}, root
    )
    assert "success" in res[0].text

    # 3. Create experiment path using numbered experiment
    res = _handle_tool_call(
        "sys.path.create", {"name": "baseline", "hypothesis": "Test H"}, root
    )
    assert "success" in res[0].text

    # 4. Write script into the experiment path
    script_content = """import csv
import os
with open('../inputs/raw_data/dummy.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)
    total = sum(int(row[0]) + int(row[1]) for row in reader)
os.makedirs('data', exist_ok=True)
with open('data/result.txt', 'w') as f:
    f.write(str(total))
"""
    res = _handle_tool_call(
        "sys.file.write",
        {"filepath": "workspace/analysis.py", "content": script_content},
        root,
    )
    assert "success" in res[0].text

    # 5. Run script
    res = _handle_tool_call(
        "tool.python.exec", {"script_path": "workspace/analysis.py"}, root
    )
    assert "success" in res[0].text

    # 6. Log findings
    res = _handle_tool_call("mem.analysis.log", {"entry": "The sum is 21."}, root)
    assert "success" in res[0].text

    # 7. Synthesize paper
    paper_content = """# Title
Abstract
This is a test abstract.

Methods
Data was summed.

Results
The sum is 21.

Discussion
This proves our hypothesis. (Oops causal language)

References
[1] Smith et al.
"""
    res = _handle_tool_call(
        "sys.file.write",
        {"filepath": "synthesis/paper.md", "content": paper_content, "force": True},
        root,
    )
    assert "success" in res[0].text

    # 8. Audit synthesis
    res = _handle_tool_call(
        "tool.audit.synthesis", {"paper_path": "synthesis/paper.md"}, root
    )
    assert "warning" in res[0].text or "success" in res[0].text

    audit_data = json.loads(res[0].text)
    assert (
        len(
            audit_data.get("data", {})
            .get("report", {})
            .get("causal_language_found", [])
        )
        > 0
    )

def test_multi_lang_workflow_and_env(workspace_root):
    root = workspace_root
    
    # Write a dummy R script
    script_content = """
print("Multi-lang workflow test")
"""
    _handle_tool_call(
        "sys.file.write",
        {"filepath": "workspace/analysis.R", "content": script_content},
        root,
    )
    
    # Run the R script with a mock to avoid needing real R
    with mock.patch("shutil.which", return_value="/usr/bin/Rscript"), \
         mock.patch("subprocess.run") as mock_run:
        
        mock_res = mock.MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Multi-lang workflow test\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        res = _handle_tool_call(
            "tool.r.exec", {"script_path": "workspace/analysis.R"}, root
        )
        assert "success" in res[0].text
    
    # Test snapshot environment
    # Let's mock subprocess.run for pip freeze
    with mock.patch("subprocess.run") as mock_run_pip:
        mock_res = mock.MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "numpy==1.21.0\n"
        mock_run_pip.return_value = mock_res
        
        # Write dummy renv.lock to simulate R project
        (root / "renv.lock").write_text('{"R": {"Version": "4.1.0"}}')
        
        res = _handle_tool_call("sys.env.snapshot", {}, root)
        assert "success" in res[0].text
        
        # Verify snapshot files
        env_dir = root / "environment"
        assert (env_dir / "requirements.txt").exists()
        assert (env_dir / "renv.lock").exists()
        assert (env_dir / "session.yaml").exists()
        
        session_data = json.loads(res[0].text).get("data", {}).get("session", {})
        assert any(lang["name"] == "python" for lang in session_data.get("languages", []))
        assert any(lang["name"] == "R" for lang in session_data.get("languages", []))

def test_project_startup_protocol(workspace_root):
    root = workspace_root
    
    # 1. Initialize project
    res = _handle_tool_call(
        "sys.workspace.scaffold", {"project_name": "Test Project"}, root
    )
    assert "success" in res[0].text
    
    # Write a dummy protocol for project_startup
    proto_dir = root / "src" / "research_os" / "protocols" / "guidance"
    proto_dir.mkdir(parents=True, exist_ok=True)
    proto_content = """name: project_startup
version: 1.0.0
description: "First actions after the researcher has placed files in inputs/."
steps:
  - id: scan_inputs
    description: "List all files in inputs/ using sys.file.list."
  - id: create_baseline_path
    description: "Create the first experiment path with sys.path.create name='baseline_eda'."
"""
    (proto_dir / "project_startup.yaml").write_text(proto_content)
    
    # 2. Get the startup protocol
    res = _handle_tool_call(
        "sys.guidance.get", {"protocol_name": "project_startup"}, root
    )
    assert "success" in res[0].text
    data = json.loads(res[0].text)
    
    content = data.get("data", {}).get("content", "")
    assert "scan_inputs" in content
    assert "create_baseline_path" in content
    
    # Simulate step 1
    res = _handle_tool_call(
        "sys.file.list", {"directory": "inputs/"}, root
    )
    assert "success" in res[0].text
    
    # Simulate step 2
    res = _handle_tool_call(
        "sys.path.create", {"name": "baseline_eda"}, root
    )
    assert "success" in res[0].text
    path_data = json.loads(res[0].text)
    assert path_data.get("data", {}).get("path_id", "").startswith("01_")

