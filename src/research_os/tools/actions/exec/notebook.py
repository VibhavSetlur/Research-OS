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


def execute_notebook(
    notebook_path: str,
    root: Path,
    *,
    timeout: int = 1800,
    kernel: str = "python3",
    parameters: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Execute a Jupyter notebook with optional parameter injection.

    Two modes:
      * **Papermill-aware** (when `papermill` is installed) — accepts
        a ``parameters`` dict that gets injected into the notebook's
        ``# parameters``-tagged cell. The result is written to
        ``output_path`` (default: a sibling
        ``runs/<stem>_<param-hash>.ipynb`` so multiple parameterised
        runs don't clobber each other) and a ``.prov.json`` sidecar
        records the input notebook, parameters, and runtime.
      * **Fallback** — when papermill is absent, falls back to
        ``jupyter nbconvert --execute --inplace`` (the previous
        behaviour). Parameters dict is ignored with a warning.
    """
    p = root / notebook_path
    if not p.exists() or p.suffix.lower() != ".ipynb":
        return {"status": "error",
                "message": f"Notebook not found or wrong type: {notebook_path}"}

    # Papermill path — preferred when available + parameters given.
    if shutil.which("papermill") or _has_papermill_module():
        return _execute_with_papermill(
            p, root, timeout=timeout, kernel=kernel,
            parameters=parameters, output_path=output_path,
        )

    if parameters:
        logger.warning(
            "papermill not installed; parameters dict ignored. "
            "Install with: pip install papermill"
        )
    if not shutil.which("jupyter"):
        return {
            "status": "error",
            "message": "neither papermill nor jupyter CLI found. "
                       "Install: pip install papermill (preferred) "
                       "or pip install jupyter nbconvert",
        }
    cmd = [
        "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
        f"--ExecutePreprocessor.timeout={timeout}",
        f"--ExecutePreprocessor.kernel_name={kernel}",
        str(p),
    ]
    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True,
            timeout=timeout + 60,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error",
                "message": f"Notebook execution timed out after {timeout}s"}

    _log_execution(root, p.stem, cmd, res)
    status = "success" if res.returncode == 0 else "error"
    return {
        "status": status,
        "notebook_path": notebook_path,
        "backend": "nbconvert",
        "stdout": res.stdout[-2000:],
        "stderr": res.stderr[-2000:],
        "code": res.returncode,
        "message": "Notebook executed in place." if status == "success"
                   else "Notebook failed.",
    }


def _has_papermill_module() -> bool:
    try:
        import papermill  # noqa: F401
        return True
    except ImportError:
        return False


def _execute_with_papermill(
    nb_path: Path,
    root: Path,
    *,
    timeout: int,
    kernel: str,
    parameters: dict[str, Any] | None,
    output_path: str | None,
) -> dict[str, Any]:
    """Run a notebook via papermill, writing one output notebook per
    parameter set with a provenance sidecar."""
    import hashlib

    parameters = parameters or {}
    # Hash the parameter dict so multiple runs land in distinct files.
    param_blob = __import__("json").dumps(
        parameters, sort_keys=True, default=str,
    )
    phash = hashlib.sha256(param_blob.encode()).hexdigest()[:10]

    if output_path:
        out_nb = root / output_path
    else:
        runs_dir = nb_path.parent / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        out_nb = runs_dir / f"{nb_path.stem}_{phash}.ipynb"
    out_nb.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    import time as _t

    t0 = _t.time()
    try:
        import papermill as pm  # type: ignore

        pm.execute_notebook(
            str(nb_path), str(out_nb),
            parameters=parameters,
            kernel_name=kernel,
            request_save_on_cell_execute=True,
            execution_timeout=timeout,
            log_output=False,
        )
        wall = round(_t.time() - t0, 2)
        # Provenance sidecar for the output notebook.
        try:
            from research_os.tools.actions.state.provenance import (
                write_output_provenance,
            )

            # Map the Jupyter kernel to its language so the sidecar's
            # software block reflects the real runtime (an R/Julia kernel
            # must not record a Python-only stack).
            kl = (kernel or "").lower()
            if kl == "ir" or kl.startswith("r"):
                nb_language = "r"
            elif kl.startswith("julia"):
                nb_language = "julia"
            else:
                nb_language = "python"
            write_output_provenance(
                output_path=out_nb, root=root,
                produced_by={"tool": "tool_notebook_exec",
                             "backend": "papermill",
                             "input_notebook": str(nb_path.relative_to(root))},
                inputs={"input_notebook": nb_path},
                params=parameters,
                rng_seed=parameters.get("seed") or parameters.get("rng_seed"),
                started_at=started_at,
                wall_seconds=wall,
                language=nb_language,
            )
        except Exception as e:
            logger.debug("notebook provenance skipped: %s", e)
        return {
            "status": "success",
            "backend": "papermill",
            "input_notebook": str(nb_path.relative_to(root)),
            "output_notebook": str(out_nb.relative_to(root)),
            "parameters": parameters,
            "param_hash": phash,
            "wall_seconds": wall,
            "advice": (
                "Notebook executed via papermill. The executed notebook is "
                "itself the provenance record (inputs, outputs, and "
                "intermediate plots are captured inline)."
            ),
        }
    except Exception as e:
        logger.exception("papermill execution failed")
        return {
            "status": "error",
            "backend": "papermill",
            "input_notebook": str(nb_path.relative_to(root)),
            "message": f"papermill: {e}",
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
            # FIXED R code; the path + output_format are passed as argv
            # (commandArgs) NOT interpolated into the code, so a crafted
            # doc_path / output_format cannot break out of render(...) and
            # execute arbitrary R -> shell. render() validates the format.
            "rmarkdown::render(commandArgs(TRUE)[1], output_format=commandArgs(TRUE)[2])",
            str(p),
            output_format,
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
