"""R / Julia / Bash / Python executor tests.

Most cases mock subprocess; the python-handler + non-UTF-8 cases run a
real child so they actually exercise return-code surfacing and the
``errors="replace"`` decode path.
"""

import json
from unittest import mock

import pytest

from research_os.server.handlers.research_exec import _handle_tool_python_exec
from research_os.tools.actions.exec.scripts import (
    execute_bash_script,
    execute_julia_script,
    execute_r_script,
)


def _payload(envelope):
    """Decode the JSON payload from a ``_text([...])`` handler return."""
    return json.loads(envelope[0].text)


@pytest.fixture
def workspace_root(tmp_path):
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    return tmp_path


def test_r_script_success(workspace_root):
    p = workspace_root / "script.R"
    p.write_text('print("hello")')
    with mock.patch("shutil.which", return_value="/usr/bin/Rscript"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="hello\n", stderr="")
        res = execute_r_script("script.R", workspace_root)
    assert res["status"] == "success"
    assert res["stdout"] == "hello\n"


def test_julia_script_success(workspace_root):
    p = workspace_root / "script.jl"
    p.write_text('println("hello")')
    with mock.patch("shutil.which", return_value="/usr/bin/julia"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="hello\n", stderr="")
        res = execute_julia_script("script.jl", workspace_root)
    assert res["status"] == "success"


def test_bash_script_success(workspace_root):
    p = workspace_root / "script.sh"
    p.write_text('echo "hello"')
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="hello\n", stderr="")
        res = execute_bash_script("script.sh", workspace_root)
    assert res["status"] == "success"


def test_missing_script(workspace_root):
    res = execute_r_script("ghost.R", workspace_root)
    assert res["status"] == "error"


def test_missing_binary(workspace_root):
    p = workspace_root / "script.R"
    p.write_text('print("hello")')
    with mock.patch("shutil.which", return_value=None):
        res = execute_r_script("script.R", workspace_root)
    assert res["status"] == "error"


def test_bash_script_nonzero_exit_is_error(workspace_root):
    """Previously execute_bash_script returned status=success for any completed
    run regardless of exit code; downstream tools then reported a working
    pipeline when the script had crashed. Regression test."""
    p = workspace_root / "script.sh"
    p.write_text('exit 1')
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(
            returncode=2, stdout="", stderr="boom\n"
        )
        res = execute_bash_script("script.sh", workspace_root)
    assert res["status"] == "error"
    assert res["exit_code"] == 2
    assert res["code"] == 2  # legacy alias preserved
    assert "boom" in res.get("message", "")


# ── tool_python_exec parity (E1 / E2) ────────────────────────────────


def test_python_exec_crash_reports_error(workspace_root):
    """E1: tool_python_exec must report status=error on a non-zero exit,
    matching its R/Julia/Bash siblings (it previously returned success)."""
    s = workspace_root / "crash.py"
    s.write_text("import sys\nsys.exit(3)\n")
    env = _handle_tool_python_exec(
        "tool_python_exec", {"script_path": "crash.py"}, workspace_root
    )
    p = _payload(env)
    assert p["status"] == "error"
    # run streams stay in the payload so the AI can debug
    assert p["payload"]["code"] == 3
    assert p["payload"]["exit_code"] == 3


def test_python_exec_success_unchanged(workspace_root):
    """The success-path envelope shape is unchanged (status=success +
    stdout/stderr/code)."""
    s = workspace_root / "ok.py"
    s.write_text("print('hi')\n")
    env = _handle_tool_python_exec(
        "tool_python_exec", {"script_path": "ok.py"}, workspace_root
    )
    p = _payload(env)
    assert p["status"] == "success"
    assert p["payload"]["code"] == 0
    assert "hi" in p["payload"]["stdout"]


def test_python_exec_missing_script_includes_path(workspace_root):
    """E2: the 'not found' error must echo the resolved path (siblings do)."""
    env = _handle_tool_python_exec(
        "tool_python_exec", {"script_path": "ghost.py"}, workspace_root
    )
    p = _payload(env)
    assert p["status"] == "error"
    assert "ghost.py" in p["error"]


# ── non-UTF-8 child output must not crash (C2) ────────────────────────


def test_python_exec_non_utf8_output_does_not_crash(workspace_root):
    """C2: a child that flushes invalid UTF-8 to stdout then exits 0 must
    still report success (errors='replace'), not bubble a UnicodeDecodeError
    that the dispatcher renders as an 'unexpected exception'."""
    s = workspace_root / "badbytes.py"
    s.write_text("import os, sys\nos.write(1, b'\\xff\\xfe bad')\nsys.exit(0)\n")
    env = _handle_tool_python_exec(
        "tool_python_exec", {"script_path": "badbytes.py"}, workspace_root
    )
    p = _payload(env)
    assert p["status"] == "success"
    assert p["payload"]["code"] == 0


def test_bash_script_non_utf8_output_does_not_crash(workspace_root):
    """C2 sibling: bash progress bars / locale bytes must not be mis-reported
    as an execution error for a script that exited 0."""
    p = workspace_root / "bad.sh"
    p.write_text("printf '\\xff\\xfe'\nexit 0\n")
    res = execute_bash_script("bad.sh", workspace_root)
    assert res["status"] == "success"
    assert res["exit_code"] == 0
