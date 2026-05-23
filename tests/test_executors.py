import pytest
from unittest import mock
from research_os.tools.actions.execution import execute_r_script, execute_julia_script, execute_bash_script

@pytest.fixture
def workspace_root(tmp_path):
    w = tmp_path / "test_workspace"
    w.mkdir()
    (w / "workspace" / "logs").mkdir(parents=True)
    return w

def test_execute_r_script_success(workspace_root):
    script_path = "script.R"
    p = workspace_root / script_path
    p.write_text('print("hello")')

    with mock.patch("shutil.which", return_value="/usr/bin/Rscript"), \
         mock.patch("subprocess.run") as mock_run:
         
        mock_res = mock.MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        res = execute_r_script(script_path, workspace_root)
        
        assert res["status"] == "success"
        assert res["stdout"] == "hello\n"
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["Rscript", str(p)]

def test_execute_julia_script_success(workspace_root):
    script_path = "script.jl"
    p = workspace_root / script_path
    p.write_text('println("hello")')

    with mock.patch("shutil.which", return_value="/usr/bin/julia"), \
         mock.patch("subprocess.run") as mock_run:
         
        mock_res = mock.MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        res = execute_julia_script(script_path, workspace_root)
        
        assert res["status"] == "success"
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0][0] == "julia"
        assert args[0][-1] == str(p)

def test_execute_bash_script_success(workspace_root):
    script_path = "script.sh"
    p = workspace_root / script_path
    p.write_text('echo "hello"')

    with mock.patch("subprocess.run") as mock_run:
        mock_res = mock.MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        res = execute_bash_script(script_path, workspace_root)
        
        assert res["status"] == "success"
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["/bin/bash", "-e", str(p)]

def test_missing_script(workspace_root):
    res = execute_r_script("missing.R", workspace_root)
    assert res["status"] == "error"
    assert "Script not found" in res["message"] or "command not found" in res["message"]

def test_missing_binary(workspace_root):
    script_path = "script.R"
    p = workspace_root / script_path
    p.write_text('print("hello")')

    with mock.patch("shutil.which", return_value=None):
        res = execute_r_script(script_path, workspace_root)
        assert res["status"] == "error"
        assert "command not found" in res["message"]
