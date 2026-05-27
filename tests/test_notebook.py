"""Tests for tool_notebook_exec + tool_rmarkdown_render."""

from unittest import mock

from research_os.tools.actions.notebook import execute_notebook, render_rmarkdown


def test_notebook_not_found(tmp_path):
    res = execute_notebook("workspace/missing.ipynb", tmp_path)
    assert res["status"] == "error"


def test_notebook_wrong_extension(tmp_path):
    p = tmp_path / "script.py"
    p.write_text("print('x')")
    res = execute_notebook("script.py", tmp_path)
    assert res["status"] == "error"


def test_notebook_missing_jupyter_binary(tmp_path):
    p = tmp_path / "nb.ipynb"
    p.write_text("{}")
    with mock.patch("shutil.which", return_value=None):
        res = execute_notebook("nb.ipynb", tmp_path)
    assert res["status"] == "error"


def test_notebook_runs_with_mock_subprocess(tmp_path):
    p = tmp_path / "nb.ipynb"
    p.write_text("{}")
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    with mock.patch("shutil.which", return_value="/usr/bin/jupyter"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="ok", stderr="")
        res = execute_notebook("nb.ipynb", tmp_path)
    assert res["status"] == "success"


def test_rmd_wrong_extension(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("html")
    res = render_rmarkdown("x.html", tmp_path)
    assert res["status"] == "error"


def test_qmd_missing_quarto(tmp_path):
    p = tmp_path / "x.qmd"
    p.write_text("---\ntitle: test\n---")
    with mock.patch("shutil.which", return_value=None):
        res = render_rmarkdown("x.qmd", tmp_path)
    assert res["status"] == "error"


def test_rmd_runs_with_mock_subprocess(tmp_path):
    p = tmp_path / "x.Rmd"
    p.write_text("---\ntitle: t\n---\n# hi")
    (tmp_path / "workspace" / "logs").mkdir(parents=True)
    with mock.patch("shutil.which", return_value="/usr/bin/Rscript"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="ok", stderr="")
        res = render_rmarkdown("x.Rmd", tmp_path)
    assert res["status"] == "success"
