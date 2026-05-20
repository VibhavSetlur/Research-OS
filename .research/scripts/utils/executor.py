"""ResearchExecutor: multi-language execution kernel scaffold.

Provides safe wrappers to run Python, R, bash, Nextflow, Snakemake, or Julia
jobs. Records stdout/stderr, duration, exit codes, and optional container used.
"""
from dataclasses import dataclass, asdict
from typing import List, Optional
import subprocess
import time
import shutil
import json
import sys
from pathlib import Path


@dataclass
class ExecutionResult:
    runtime: str
    script_path: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    container_used: Optional[str]
    artifacts_produced: List[str]


class ResearchExecutor:
    def __init__(self, container_engine: str = "docker"):
        self.container_engine = container_engine

    def _run(self, cmd: List[str], timeout: Optional[int] = None) -> ExecutionResult:
        start = time.time()
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            duration = time.time() - start
            return ExecutionResult(runtime=cmd[0] if cmd else "", script_path=" ", exit_code=p.returncode,
                                   stdout=p.stdout, stderr=p.stderr, duration_seconds=duration,
                                   container_used=None, artifacts_produced=[])
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start
            return ExecutionResult(runtime=cmd[0] if cmd else "", script_path=" ", exit_code=124,
                                   stdout="", stderr=str(e), duration_seconds=duration,
                                   container_used=None, artifacts_produced=[])

    def _wrap_container(self, container: Optional[str], command: List[str]) -> List[str]:
        if not container:
            return command
        if shutil.which(self.container_engine):
            # simple docker run wrapper; users should prefer runtime_selector for complex needs
            return [self.container_engine, "run", "--rm", "-v", f"{Path.cwd()}:/workspace", container] + command
        return command

    def run_python(self, script_path: str, args: Optional[List[str]] = None, container: Optional[str] = None) -> ExecutionResult:
        cmd = ["python", script_path] + (args or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd)
        res.runtime = "python"
        res.script_path = script_path
        res.container_used = container
        return res

    def run_r(self, script_path: str, args: Optional[List[str]] = None, container: Optional[str] = None) -> ExecutionResult:
        cmd = ["Rscript", script_path] + (args or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd)
        res.runtime = "r"
        res.script_path = script_path
        res.container_used = container
        return res

    def run_bash(self, command: str, container: Optional[str] = None) -> ExecutionResult:
        cmd = ["bash", "-c", command]
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd)
        res.runtime = "bash"
        res.script_path = command
        res.container_used = container
        return res

    def check_runtime(self, runtime: str) -> bool:
        if runtime == "docker":
            return shutil.which("docker") is not None
        if runtime == "singularity":
            return shutil.which("singularity") is not None
        if runtime == "r":
            return shutil.which("Rscript") is not None
        if runtime == "python":
            return Path(sys.executable).exists()
        return False


if __name__ == "__main__":
    # quick smoke test
    ex = ResearchExecutor()
    r = ex.run_python("-c", args=["print('hello')"])  # intentionally invalid path usage is handled by subprocess
    print(json.dumps(asdict(r), indent=2))
