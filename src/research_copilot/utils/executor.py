"""ResearchExecutor: multi-language execution kernel scaffold.

Provides safe wrappers to run Python, R, bash, Nextflow, Snakemake, or Julia
jobs. Records stdout/stderr, duration, exit codes, and optional container used.

Pandas masking: every Python execution is prefixed with a safety preamble that
caps DataFrame display rows to 10, preventing accidental context-window blowouts
from large DataFrames printed to stdout.
"""
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import subprocess
import tempfile
import time
import shutil
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Data Pointer Injection — Pandas Display Masking
# ---------------------------------------------------------------------------
# This preamble is prepended to every Python script before execution.
# It enforces safe display limits so agents never accidentally dump a full
# DataFrame to stdout and blow up the context window.
# Agents are instructed (via their system prompts) to:
#   - Save data to files and output only the path.
#   - Use .info() or .shape instead of printing DataFrames.
# ---------------------------------------------------------------------------
PANDAS_DISPLAY_PREAMBLE = """# [rcp-injected safety preamble — do not remove]
try:
    import pandas as pd
    pd.options.display.max_rows = 10
    pd.options.display.max_columns = 20
    pd.options.display.max_colwidth = 80
    pd.options.mode.chained_assignment = None  # silence SettingWithCopyWarning
except ImportError:
    pass
# [end preamble]
"""

DATA_POINTER_SYSTEM_HINT = (
    "IMPORTANT: Do NOT print DataFrames or large arrays to stdout. "
    "Instead: (1) save data to a file and print only the file path, "
    "(2) use df.info() or df.shape to describe data, "
    "(3) print only scalar metrics or summary statistics."
)

try:
    import yaml
except ImportError:
    yaml = None


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
    tool_ids: List[str]
    domain: Optional[str]


def _find_project_root() -> Path:
    """Find project root by looking for .research directory."""
    from research_copilot.utils.common import find_project_root
    return find_project_root()


def _load_config(root: Path) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(root / ".research" / "config.yaml") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class ResearchExecutor:
    def __init__(self, root: Optional[Path] = None, container_engine: Optional[str] = None, log_path: Optional[Path] = None):
        self.root = root or _find_project_root()
        config = _load_config(self.root)
        exec_cfg = config.get("execution", {}) if isinstance(config, dict) else {}
        self.container_engine = container_engine or exec_cfg.get("container_engine", "docker")
        log_default = exec_cfg.get("executor_log", ".research/cache/execution_log.jsonl")
        self.log_path = Path(log_path) if log_path else (self.root / log_default)

    def _run(self, cmd: List[str], timeout: Optional[int] = None,
             tool_ids: Optional[List[str]] = None, domain: Optional[str] = None) -> ExecutionResult:
        start = time.time()
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            duration = time.time() - start
            return ExecutionResult(runtime=cmd[0] if cmd else "", script_path=" ", exit_code=p.returncode,
                                   stdout=p.stdout, stderr=p.stderr, duration_seconds=duration,
                                   container_used=None, artifacts_produced=[],
                                   tool_ids=tool_ids or [], domain=domain)
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start
            return ExecutionResult(runtime=cmd[0] if cmd else "", script_path=" ", exit_code=124,
                                   stdout="", stderr=str(e), duration_seconds=duration,
                                   container_used=None, artifacts_produced=[],
                                   tool_ids=tool_ids or [], domain=domain)

    def _wrap_container(self, container: Optional[str], command: List[str]) -> List[str]:
        if not container:
            return command
        if shutil.which(self.container_engine):
            # simple docker run wrapper; users should prefer runtime_selector for complex needs
            return [self.container_engine, "run", "--rm", "-v", f"{Path.cwd()}:/workspace", container] + command
        return command

    def _make_node_id(self, script_path: str, iteration_id: Optional[str]) -> str:
        base = Path(script_path).name.split()[0] if script_path else "command"
        stem = Path(base).stem or "command"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{stem}_{iteration_id or 'base'}_{ts}"

    def _log_execution(self, result: ExecutionResult, metadata: Dict[str, Any]) -> None:
        entry = asdict(result)
        entry.update(metadata)
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _update_dag(self, result: ExecutionResult, metadata: Dict[str, Any]) -> None:
        try:
            from research_copilot.utils.dag_manager import ExecutionDAGManager
        except ImportError:
            return

        node_id = metadata.get("node_id") or self._make_node_id(result.script_path, metadata.get("iteration_id"))
        input_files = metadata.get("input_files") or []
        output_files = metadata.get("output_files") or []
        depends_on = metadata.get("depends_on") or []
        iteration_id = metadata.get("iteration_id")
        status = "complete" if result.exit_code == 0 else "failed"

        dag = ExecutionDAGManager(self.root)
        dag.add_node(node_id, result.script_path, input_files, output_files,
                     depends_on=depends_on, iteration_id=iteration_id, status=status,
                     runtime=result.runtime, container=result.container_used,
                     tool_ids=result.tool_ids, domain=result.domain,
                     exit_code=result.exit_code, duration=result.duration_seconds)
        if output_files:
            dag.update_output_hashes(node_id)

    def _post_process(self, result: ExecutionResult, metadata: Dict[str, Any]) -> ExecutionResult:
        self._log_execution(result, metadata)
        self._update_dag(result, metadata)
        return result

    def _inject_preamble(self, script_path: str) -> str:
        """Prepend PANDAS_DISPLAY_PREAMBLE to *script_path* and return a temp file path.

        The caller is responsible for deleting the temp file after execution.
        """
        try:
            with open(script_path) as f:
                original = f.read()
        except OSError:
            return script_path  # can't read — skip injection, run original

        fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="rcp_exec_")
        try:
            with open(fd, "w") as f:
                f.write(PANDAS_DISPLAY_PREAMBLE + original)
        except Exception:
            import os
            os.unlink(tmp_path)
            return script_path
        return tmp_path

    def run_python(
        self,
        script_path: str,
        args: Optional[List[str]] = None,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        import os
        wrapped_path = self._inject_preamble(script_path)
        cmd = [sys.executable, wrapped_path] + (args or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "python"
        res.script_path = script_path  # report original path, not temp
        res.container_used = container
        if wrapped_path != script_path:
            try:
                os.unlink(wrapped_path)
            except OSError:
                pass
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def run_r(
        self,
        script_path: str,
        args: Optional[List[str]] = None,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        cmd = ["Rscript", script_path] + (args or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "r"
        res.script_path = script_path
        res.container_used = container
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def run_bash(
        self,
        command: str,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        cmd = ["bash", "-c", command]
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "bash"
        res.script_path = command
        res.container_used = container
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def run_nextflow(
        self,
        pipeline: str,
        params: Optional[List[str]] = None,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        cmd = ["nextflow", "run", pipeline] + (params or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "nextflow"
        res.script_path = pipeline
        res.container_used = container
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def run_snakemake(
        self,
        snakefile: str,
        config: Optional[List[str]] = None,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        cmd = ["snakemake", "-s", snakefile] + (config or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "snakemake"
        res.script_path = snakefile
        res.container_used = container
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def run_julia(
        self,
        script_path: str,
        args: Optional[List[str]] = None,
        container: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        iteration_id: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[int] = None,
        tool_ids: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> ExecutionResult:
        cmd = ["julia", script_path] + (args or [])
        cmd = self._wrap_container(container, cmd)
        res = self._run(cmd, timeout=timeout, tool_ids=tool_ids, domain=domain)
        res.runtime = "julia"
        res.script_path = script_path
        res.container_used = container
        return self._post_process(res, {
            "input_files": input_files or [],
            "output_files": output_files or [],
            "depends_on": depends_on or [],
            "iteration_id": iteration_id,
            "node_id": node_id,
        })

    def check_runtime(self, runtime: str) -> bool:
        if runtime == "docker":
            return shutil.which("docker") is not None
        if runtime == "singularity":
            return shutil.which("singularity") is not None
        if runtime == "podman":
            return shutil.which("podman") is not None
        if runtime == "r":
            return shutil.which("Rscript") is not None
        if runtime == "python":
            return Path(sys.executable).exists()
        if runtime == "julia":
            return shutil.which("julia") is not None
        if runtime == "nextflow":
            return shutil.which("nextflow") is not None
        if runtime == "snakemake":
            return shutil.which("snakemake") is not None
        if runtime == "bash":
            return shutil.which("bash") is not None
        return False


# ---------------------------------------------------------------------------
# Template-Based Execution (Item 7)
# ---------------------------------------------------------------------------
# LLMs hallucinate complex library syntax. Instead of asking them to write
# code from scratch, skill templates embed {{PLACEHOLDER}} variables.
# The LLM's only job is to output a JSON dict of variable values.
# The TemplateExecutor maps the JSON → template, generates the script, and
# runs it — guaranteeing syntactically correct code every time.
# ---------------------------------------------------------------------------

import re as _re
import os as _os


class TemplateExecutor:
    """Fill-in-the-blanks template execution engine.

    Templates are ``.py.template`` files containing ``{{VARIABLE}}``
    placeholders.  The LLM outputs a JSON dict of variable values; this class
    renders the template and executes the resulting Python script.

    Template search order (first match wins):
      1. ``<project_root>/.research/templates/``  (user overrides)
      2. ``<assets_dir>/skills/<category>/templates/``  (bundled)
      3. Any absolute path passed directly.

    Example template file (``t_test.py.template``)::

        import pandas as pd
        from scipy import stats

        df = pd.read_csv("{{INPUT_FILE}}")
        group_col = "{{GROUP_COL}}"
        value_col = "{{VALUE_COL}}"
        groups = df[group_col].unique()
        a = df.loc[df[group_col] == groups[0], value_col]
        b = df.loc[df[group_col] == groups[1], value_col]
        t, p = stats.ttest_ind(a, b, equal_var=False)
        print(f"t={t:.4f}, p={p:.4f}")

    Example LLM JSON output::

        {
            "INPUT_FILE": "data/clean.csv",
            "GROUP_COL": "treatment",
            "VALUE_COL": "score"
        }
    """

    PLACEHOLDER_RE = _re.compile(r"\{\{([A-Z0-9_]+)\}\}")

    def __init__(self, root: Optional[Path] = None):
        self.root = root or _find_project_root()
        self._executor = ResearchExecutor(root=self.root)

    # ------------------------------------------------------------------
    # Template discovery
    # ------------------------------------------------------------------

    def _find_template(self, template_name: str) -> Path:
        """Locate a ``.py.template`` file by name.

        Args:
            template_name: Bare name (e.g. ``t_test``) or absolute path.

        Returns:
            Path to the template file.

        Raises:
            FileNotFoundError: If the template cannot be found.
        """
        # Direct absolute/relative path.
        p = Path(template_name)
        if p.exists():
            return p

        # Normalise — add extension if missing.
        name = template_name if template_name.endswith(".py.template") else f"{template_name}.py.template"

        # 1. User override templates.
        user_dir = self.root / ".research" / "templates"
        candidate = user_dir / name
        if candidate.exists():
            return candidate

        # 2. Bundled assets under skills/**/templates/.
        assets_dir = Path(__file__).parent.parent / "assets" / "skills"
        for tmpl in assets_dir.rglob(name):
            return tmpl

        raise FileNotFoundError(
            f"Template '{template_name}' not found.  "
            f"Searched: {user_dir}, {assets_dir}/**/templates/"
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, template_name: str, variables: Dict[str, Any]) -> str:
        """Render a template by substituting ``{{VARIABLE}}`` placeholders.

        Args:
            template_name: Template file name or path.
            variables:     Dict mapping placeholder names to values.

        Returns:
            Rendered Python source code string.

        Raises:
            ValueError: If required placeholders are missing from *variables*.
        """
        tmpl_path = self._find_template(template_name)
        source = tmpl_path.read_text()

        # Check for missing variables.
        required = set(self.PLACEHOLDER_RE.findall(source))
        provided = {k.upper() for k in variables}
        missing = required - provided
        if missing:
            raise ValueError(
                f"Template '{template_name}' requires variables not provided: {missing}"
            )

        # Substitute all placeholders.
        def _sub(match: _re.Match) -> str:
            key = match.group(1)
            val = variables.get(key) or variables.get(key.lower(), "")
            return str(val)

        return self.PLACEHOLDER_RE.sub(_sub, source)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute_template(
        self,
        template_name: str,
        variables: Dict[str, Any],
        *,
        timeout: Optional[int] = 300,
        node_id: Optional[str] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
    ) -> "ExecutionResult":
        """Render *template_name* with *variables* and execute the result.

        Args:
            template_name: Template identifier (name or path).
            variables:     JSON-sourced variable dict from the LLM.
            timeout:       Subprocess timeout in seconds.
            node_id:       DAG node ID for logging.
            input_files:   Input files for DAG tracking.
            output_files:  Output files for DAG tracking.

        Returns:
            ExecutionResult from the subprocess run.
        """
        rendered = self.render(template_name, variables)

        fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="rcp_tmpl_")
        try:
            with _os.fdopen(fd, "w") as f:
                f.write(rendered)

            result = self._executor.run_python(
                script_path=tmp_path,
                timeout=timeout,
                node_id=node_id,
                input_files=input_files or [],
                output_files=output_files or [],
            )
        finally:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass

        result.script_path = f"<template:{template_name}>"
        return result

    def list_templates(self) -> List[Dict[str, str]]:
        """Return all discoverable templates with their paths and placeholders."""
        results: List[Dict[str, str]] = []
        search_dirs: List[Path] = [
            self.root / ".research" / "templates",
            Path(__file__).parent.parent / "assets" / "skills",
        ]
        for d in search_dirs:
            if not d.exists():
                continue
            for tmpl in sorted(d.rglob("*.py.template")):
                source = tmpl.read_text()
                placeholders = sorted(set(self.PLACEHOLDER_RE.findall(source)))
                results.append({
                    "name": tmpl.stem.replace(".py", ""),
                    "path": str(tmpl),
                    "placeholders": ", ".join(placeholders),
                })
        return results


if __name__ == "__main__":
    ex = ResearchExecutor()
    r = ex.run_python("-c", args=["print('hello')"], node_id="executor_smoke")
    print(json.dumps(asdict(r), indent=2))
