"""Foreign-language script executors (R, Julia, Bash).

These all share the same envelope:
- ``status``: "success" iff the interpreter ran AND returncode == 0
- ``exit_code``: the underlying interpreter exit code
- ``stdout``/``stderr``: captured streams (truncated by caller if needed)

Previously execute_bash_script and friends returned ``status: success`` for
any completed run regardless of exit code, which caused downstream tools to
report a working pipeline when the script had actually crashed.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_os.project_ops import now_iso


def _log_execution(
    root: Path, step_name: str, cmd: list, res: subprocess.CompletedProcess
) -> None:
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    exec_log_path = log_dir / f"{step_name}_exec.log"

    with open(exec_log_path, "a") as f:
        f.write(
            f"--- Executed at {now_iso()} ---\n"
            f"Command: {' '.join(cmd)}\n"
            f"Return Code: {res.returncode}\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}\n\n"
        )


def _envelope(
    res: subprocess.CompletedProcess, *, runner: str
) -> dict[str, Any]:
    ok = res.returncode == 0
    out = {
        "status": "success" if ok else "error",
        "exit_code": res.returncode,
        "code": res.returncode,  # legacy alias
        "stdout": res.stdout,
        "stderr": res.stderr,
    }
    if not ok:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-5:]
        out["message"] = f"{runner} exited with code {res.returncode}: " + " | ".join(tail)
    return out


def execute_r_script(script_path: str, root: Path, timeout: int = 300) -> dict[str, Any]:
    if not shutil.which("Rscript"):
        return {"status": "error", "message": "Rscript command not found. Ensure R is installed."}

    p = root / script_path
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": f"Script not found at {script_path}"}

    # renv auto-activates via .Rprofile if present; no manual setup needed.
    cmd = ["Rscript", str(p)]
    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True, errors="replace", timeout=timeout
        )
        _log_execution(root, p.stem, cmd, res)
        return _envelope(res, runner="Rscript")
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Execution timed out after {timeout} seconds."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_julia_script(script_path: str, root: Path, timeout: int = 300) -> dict[str, Any]:
    if not shutil.which("julia"):
        return {"status": "error", "message": "julia command not found. Ensure Julia is installed."}

    p = root / script_path
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": f"Script not found at {script_path}"}

    cmd = ["julia"]
    if (p.parent / "Project.toml").exists():
        cmd.append("--project=" + str(p.parent))
    elif (root / "environment" / "Project.toml").exists():
        cmd.append("--project=" + str(root / "environment"))
    cmd.append(str(p))

    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True, errors="replace", timeout=timeout
        )
        _log_execution(root, p.stem, cmd, res)
        return _envelope(res, runner="julia")
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Execution timed out after {timeout} seconds."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_bash_script(script_path: str, root: Path, timeout: int = 300) -> dict[str, Any]:
    p = root / script_path
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": f"Script not found at {script_path}"}

    cmd = ["/bin/bash", "-e", str(p)]
    try:
        res = subprocess.run(
            cmd, cwd=str(p.parent), capture_output=True, text=True, errors="replace", timeout=timeout
        )
        _log_execution(root, p.stem, cmd, res)
        return _envelope(res, runner="bash")
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Execution timed out after {timeout} seconds."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
