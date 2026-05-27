"""Notebook + R-markdown / Quarto execution.

Supports:
  - .ipynb           via ``jupyter nbconvert --execute --to notebook --inplace``
  - .Rmd             via ``Rscript -e 'rmarkdown::render(...)'``
  - .qmd             via ``quarto render``
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.notebook")


def _log_execution(root: Path, name: str, cmd: list[str], res: subprocess.CompletedProcess) -> Path:
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}_exec.log"
    ts = datetime.now(timezone.utc).isoformat()
    with open(log_path, "a") as f:
        f.write(
            f"--- Executed at {ts} ---\n"
            f"Command: {' '.join(cmd)}\n"
            f"Return Code: {res.returncode}\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\n\n"
        )
    return log_path


# ---------------------------------------------------------------------------
# Jupyter (.ipynb)
# ---------------------------------------------------------------------------


def execute_notebook(notebook_path: str, root: Path, *, timeout: int = 1800,
                     kernel: str = "python3") -> dict[str, Any]:
    """Execute a Jupyter notebook in-place and report results."""
    p = root / notebook_path
    if not p.exists() or p.suffix.lower() != ".ipynb":
        return {"status": "error", "message": f"Notebook not found or wrong type: {notebook_path}"}
    if not shutil.which("jupyter"):
        return {
            "status": "error",
            "message": "`jupyter` CLI not found. Install with: pip install jupyter nbconvert",
        }
    cmd = [
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        "--inplace",
        f"--ExecutePreprocessor.timeout={timeout}",
        f"--ExecutePreprocessor.kernel_name={kernel}",
        str(p),
    ]
    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True, timeout=timeout + 60
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Notebook execution timed out after {timeout}s"}

    _log_execution(root, p.stem, cmd, res)
    status = "success" if res.returncode == 0 else "error"
    return {
        "status": status,
        "notebook_path": notebook_path,
        "stdout": res.stdout[-2000:],
        "stderr": res.stderr[-2000:],
        "code": res.returncode,
        "message": "Notebook executed in place." if status == "success" else "Notebook failed.",
    }


# ---------------------------------------------------------------------------
# R-markdown / Quarto
# ---------------------------------------------------------------------------


def render_rmarkdown(doc_path: str, root: Path, *, output_format: str = "html_document",
                     timeout: int = 1800) -> dict[str, Any]:
    """Render an .Rmd or .qmd document to its standard output format."""
    p = root / doc_path
    if not p.exists():
        return {"status": "error", "message": f"Document not found: {doc_path}"}

    ext = p.suffix.lower()
    if ext == ".qmd":
        if not shutil.which("quarto"):
            return {
                "status": "error",
                "message": "`quarto` not found. Install from https://quarto.org",
            }
        cmd = ["quarto", "render", str(p)]
    elif ext == ".rmd":
        if not shutil.which("Rscript"):
            return {"status": "error", "message": "Rscript not found. Install R + rmarkdown."}
        cmd = [
            "Rscript",
            "-e",
            f"rmarkdown::render('{p}', output_format='{output_format}')",
        ]
    else:
        return {"status": "error", "message": f"Expected .Rmd or .qmd, got {ext}"}

    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Render timed out after {timeout}s"}

    _log_execution(root, p.stem, cmd, res)
    status = "success" if res.returncode == 0 else "error"
    return {
        "status": status,
        "doc_path": doc_path,
        "stdout": res.stdout[-2000:],
        "stderr": res.stderr[-2000:],
        "code": res.returncode,
    }
