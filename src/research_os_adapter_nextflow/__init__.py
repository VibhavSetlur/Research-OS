"""Nextflow workflow adapter.

Detects:
    * `*.nf` files (DSL1 / DSL2 pipeline scripts)
    * `main.nf` entrypoint
    * `nextflow.config` configuration file

Extracts:
    * Per process: name, inputs, outputs, script preview, container,
      conda env, cpus, memory, time, errorStrategy.
    * Pipeline config: executor (local / slurm / awsbatch / google /
      kubernetes), profiles, container engine (docker / singularity /
      podman / charliecloud), default resource directives.
    * List of `.nf` files scanned.

Limitations:
    Nextflow has no public Python parser (the official AST lives inside
    the Groovy/Java runtime via `nextflow inspect`). Extraction here is
    **regex-based** and best-effort: it will miss DSL2 workflow
    composition, dynamic process directives computed at runtime,
    `include { ... } from` re-exports, and closures whose body spans
    nested braces. For ground-truth provenance, run the optional
    `tool_nextflow_validate` tool (which shells out to `nextflow` if
    installed) or `nextflow inspect <pipeline>` manually.

Optional tools:
    * tool_nextflow_validate(pipeline_path)
      — runs `nextflow run <main.nf> --help` (or `nextflow inspect`)
      if the `nextflow` CLI is on PATH; degrades to a warning if not.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    err_envelope as _err,
    ok_envelope as _ok,
    register_adapter,
)


__version__ = "1.8.0"


# ── detection ─────────────────────────────────────────────────────────


_CONFIG_NAMES = {"nextflow.config"}
_ENTRY_NAMES = {"main.nf"}


# Vendor / VCS / cache dirs that may hold third-party *.nf files (e.g. a
# pinned nf-core module under .venv or node_modules). Pruning them stops a
# vendored pipeline from false-triggering the adapter on a non-Nextflow
# project, and avoids walking huge trees.
_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages", ".os_state", ".ipynb_checkpoints",
}


def _candidate_files(root: Path) -> list[Path]:
    """Return every .nf / nextflow.config / main.nf under root.

    Single pruned walk (skips dot/vendor dirs) — covers the project root,
    inputs/, and workspace/<step>/ in one pass without double-walking or
    descending into .git / .venv / node_modules.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    try:
        for base, dirs, names in os.walk(root):
            dirs[:] = [
                d for d in dirs
                if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            for name in names:
                low = name.lower()
                if low.endswith(".nf") or low in _CONFIG_NAMES or low in _ENTRY_NAMES:
                    p = Path(base) / name
                    resolved = p.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    files.append(p)
    except OSError:
        pass
    return files


def detect(root: Path) -> bool:
    """Filesystem-only detection — no network, no subprocess.

    Returns True if any `.nf`, `nextflow.config`, or `main.nf` is
    present in the project root or under `workspace/`.
    """
    for path in _candidate_files(root):
        return True
    return False


# ── extraction ────────────────────────────────────────────────────────


# Match `process NAME {` — directly captures the process name.
_PROCESS_HEAD_RE = re.compile(r"\bprocess\s+(\w+)\s*\{", re.MULTILINE)

# Directives inside a process block. Values are usually quoted but
# may be unquoted numerics, ternaries, or closures.
_CONTAINER_RE = re.compile(r"\bcontainer\s+['\"]([^'\"]+)['\"]")
_CONDA_RE = re.compile(r"\bconda\s+['\"]([^'\"]+)['\"]")
_CPUS_RE = re.compile(r"\bcpus\s+([^\n]+)")
_MEMORY_RE = re.compile(r"\bmemory\s+([^\n]+)")
_TIME_RE = re.compile(r"\btime\s+([^\n]+)")
_ERR_RE = re.compile(r"\berrorStrategy\s+['\"]([^'\"]+)['\"]")
_LABEL_RE = re.compile(r"\blabel\s+['\"]([^'\"]+)['\"]")
_TAG_RE = re.compile(r"\btag\s+['\"]([^'\"]+)['\"]")
_PUBLISH_RE = re.compile(r"\bpublishDir\s+['\"]([^'\"]+)['\"]")

# Input / output lines — we just capture the raw qualifier line; full
# parsing would need a real Groovy parser.
_INPUT_LINE_RE = re.compile(r"^\s*(val|path|file|tuple|each|env|stdin)\b[^\n]*", re.MULTILINE)
_OUTPUT_LINE_RE = re.compile(r"^\s*(val|path|file|tuple|stdout)\b[^\n]*", re.MULTILINE)

# script: / shell: / exec: heredoc block markers
_SCRIPT_HEAD_RE = re.compile(r"^\s*(script|shell|exec)\s*:\s*$", re.MULTILINE)

# Top-level config keys we want to surface.
_CFG_EXECUTOR_RE = re.compile(r"\bexecutor\s*\.?\s*name?\s*=\s*['\"]([^'\"]+)['\"]")
_CFG_EXECUTOR_BLOCK_RE = re.compile(r"executor\s*\{[^}]*?\bname\s*=\s*['\"]([^'\"]+)['\"]", re.DOTALL)
_CFG_DOCKER_RE = re.compile(r"\bdocker\s*\.\s*enabled\s*=\s*true\b")
_CFG_SINGULARITY_RE = re.compile(r"\bsingularity\s*\.\s*enabled\s*=\s*true\b")
_CFG_PODMAN_RE = re.compile(r"\bpodman\s*\.\s*enabled\s*=\s*true\b")
_CFG_CHARLIECLOUD_RE = re.compile(r"\bcharliecloud\s*\.\s*enabled\s*=\s*true\b")
_CFG_PROFILE_RE = re.compile(r"profiles\s*\{([^}]*)\}", re.DOTALL)
_CFG_PROFILE_NAME_RE = re.compile(r"^\s*(\w+)\s*\{", re.MULTILINE)


def _slice_process_block(text: str, start: int) -> str:
    """From the '{' after `process NAME`, walk braces and return body."""
    depth = 0
    i = start
    n = len(text)
    body_start = -1
    while i < n:
        ch = text[i]
        if ch == "{":
            if depth == 0:
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[body_start:i] if body_start >= 0 else ""
        i += 1
    # unterminated — return what we have
    return text[body_start:] if body_start >= 0 else ""


def _strip_inline_comment(v: str) -> str:
    """Drop an unquoted trailing `// …` or `/* … */` Groovy comment.

    `time = '2h'  // wall clock` must yield `2h`, not `2h'  // wall clock`.
    Quote-aware so a `//` inside a quoted value is preserved.
    """
    out: list[str] = []
    quote: str | None = None
    i, n = 0, len(v)
    while i < n:
        ch = v[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "/" and i + 1 < n and v[i + 1] == "/":
            break
        elif ch == "/" and i + 1 < n and v[i + 1] == "*":
            end = v.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    v = _strip_inline_comment(value).strip().rstrip(",").strip()
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
        v = v[1:-1]
    return v or None


def _extract_inputs(body: str) -> list[str]:
    # Slice the input: ... output: portion if present.
    m_in = re.search(r"^\s*input\s*:\s*$", body, re.MULTILINE)
    if not m_in:
        return []
    end_m = re.search(r"^\s*(output|when|script|shell|exec)\s*:\s*$", body[m_in.end():], re.MULTILINE)
    section = body[m_in.end():m_in.end() + end_m.start()] if end_m else body[m_in.end():]
    return [m.group(0).strip() for m in _INPUT_LINE_RE.finditer(section)]


def _extract_outputs(body: str) -> list[str]:
    m_out = re.search(r"^\s*output\s*:\s*$", body, re.MULTILINE)
    if not m_out:
        return []
    end_m = re.search(r"^\s*(when|script|shell|exec)\s*:\s*$", body[m_out.end():], re.MULTILINE)
    section = body[m_out.end():m_out.end() + end_m.start()] if end_m else body[m_out.end():]
    return [m.group(0).strip() for m in _OUTPUT_LINE_RE.finditer(section)]


def _extract_script_preview(body: str, max_chars: int = 400) -> str | None:
    m = _SCRIPT_HEAD_RE.search(body)
    if not m:
        return None
    tail = body[m.end():]
    # Strip leading triple-quoted markers + whitespace.
    tail = tail.lstrip()
    for quote in ('"""', "'''"):
        if tail.startswith(quote):
            end = tail.find(quote, len(quote))
            inner = tail[len(quote):end] if end != -1 else tail[len(quote):]
            inner = inner.strip()
            return inner[:max_chars] + ("…" if len(inner) > max_chars else "")
    # Otherwise just trim to first blank-line-ish boundary.
    snippet = tail.strip()
    return snippet[:max_chars] + ("…" if len(snippet) > max_chars else "")


def _parse_process_block(name: str, body: str) -> dict:
    return {
        "name": name,
        "inputs": _extract_inputs(body),
        "outputs": _extract_outputs(body),
        "script_preview": _extract_script_preview(body),
        "container": _strip(_CONTAINER_RE.search(body).group(1)) if _CONTAINER_RE.search(body) else None,
        "conda": _strip(_CONDA_RE.search(body).group(1)) if _CONDA_RE.search(body) else None,
        "cpus": _strip(_CPUS_RE.search(body).group(1)) if _CPUS_RE.search(body) else None,
        "memory": _strip(_MEMORY_RE.search(body).group(1)) if _MEMORY_RE.search(body) else None,
        "time": _strip(_TIME_RE.search(body).group(1)) if _TIME_RE.search(body) else None,
        "error_strategy": _strip(_ERR_RE.search(body).group(1)) if _ERR_RE.search(body) else None,
        "labels": [m.group(1) for m in _LABEL_RE.finditer(body)],
        "tag": _strip(_TAG_RE.search(body).group(1)) if _TAG_RE.search(body) else None,
        "publish_dir": _strip(_PUBLISH_RE.search(body).group(1)) if _PUBLISH_RE.search(body) else None,
    }


def _parse_nf_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return []
    processes: list[dict] = []
    for m in _PROCESS_HEAD_RE.finditer(text):
        # find the '{' that opens this process — _PROCESS_HEAD_RE already consumed it.
        brace_pos = m.end() - 1
        body = _slice_process_block(text, brace_pos)
        if not body:
            continue
        proc = _parse_process_block(m.group(1), body)
        try:
            proc["source_file"] = str(path)
        except Exception as exc:
            import logging
            logging.getLogger("research_os_adapter_nextflow").debug(
                "source_file annotation skipped: %s", exc
            )
        processes.append(proc)
    return processes


def _parse_config(path: Path) -> dict:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return {}
    executor: str | None = None
    m = _CFG_EXECUTOR_BLOCK_RE.search(text)
    if m:
        executor = m.group(1)
    else:
        m2 = _CFG_EXECUTOR_RE.search(text)
        if m2:
            executor = m2.group(1)
    engine: str | None = None
    if _CFG_DOCKER_RE.search(text):
        engine = "docker"
    elif _CFG_SINGULARITY_RE.search(text):
        engine = "singularity"
    elif _CFG_PODMAN_RE.search(text):
        engine = "podman"
    elif _CFG_CHARLIECLOUD_RE.search(text):
        engine = "charliecloud"
    profiles: list[str] = []
    pm = _CFG_PROFILE_RE.search(text)
    if pm:
        profiles = list(dict.fromkeys(_CFG_PROFILE_NAME_RE.findall(pm.group(1))))
    return {
        "executor": executor,
        "container_engine": engine,
        "profiles": profiles,
        "config_file": str(path),
    }


def extract(root: Path, step_id: str | None = None) -> dict:
    """Return the structured Nextflow payload (regex-based, best-effort)."""
    files = _candidate_files(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        files = [f for f in files if str(f.resolve()).startswith(str(step_prefix))]

    nf_files: list[Path] = []
    config_files: list[Path] = []
    for p in files:
        name = p.name.lower()
        if name in _CONFIG_NAMES:
            config_files.append(p)
        else:
            nf_files.append(p)

    processes: list[dict] = []
    for nf in nf_files:
        try:
            processes.extend(_parse_nf_file(nf))
        except Exception:
            # be lenient with broken files — skip + continue
            continue

    config: dict = {"executor": None, "container_engine": None, "profiles": []}
    for cfg in config_files:
        try:
            merged = _parse_config(cfg)
        except Exception:
            continue
        for k in ("executor", "container_engine"):
            if not config.get(k) and merged.get(k):
                config[k] = merged[k]
        for prof in merged.get("profiles") or []:
            if prof not in config["profiles"]:
                config["profiles"].append(prof)
        config.setdefault("config_files", []).append(merged.get("config_file"))

    return {
        "processes": processes,
        "process_count": len(processes),
        "config": config,
        "nextflow_files": [str(p) for p in nf_files],
        "config_files": [str(p) for p in config_files],
        "_notes": (
            "Extraction is regex-based — Nextflow has no public Python parser. "
            "DSL2 workflow composition, dynamic directives evaluated at runtime, "
            "and `include { ... } from` re-exports are NOT resolved. "
            "Use `tool_nextflow_validate` or `nextflow inspect` for ground truth."
        ),
    }


def describe() -> dict:
    return {
        "name": "nextflow",
        "version": __version__,
        "workflow_engine": "nextflow",
        "dsl_versions_supported": ["DSL1", "DSL2 (best-effort)"],
    }


# ── optional tools ────────────────────────────────────────────────────


# Envelope helpers (_ok / _err) are imported from research_os.adapters.


def _handle_validate(name: str, arguments: dict, root: Path) -> Any:
    """Run `nextflow run <pipeline> --help` if nextflow is on PATH.

    Heavy dep: optional. If nextflow isn't installed, returns a warning
    rather than failing — Research-OS adapters MUST degrade gracefully.
    """
    nextflow_bin = shutil.which("nextflow")
    if not nextflow_bin:
        return _ok({
            "status": "warning",
            "message": (
                "nextflow CLI not installed; cannot validate the pipeline. "
                "Install via `curl -s https://get.nextflow.io | bash` or "
                "`conda install -c bioconda nextflow`."
            ),
        })

    pipeline_arg = (arguments.get("pipeline_path") or "").strip()
    if pipeline_arg:
        pipeline = (root / pipeline_arg).resolve() if not Path(pipeline_arg).is_absolute() else Path(pipeline_arg)
    else:
        # Auto-detect main.nf in root or any workspace step.
        pipeline = None
        for candidate in _candidate_files(root):
            if candidate.name.lower() in _ENTRY_NAMES:
                pipeline = candidate
                break
        if pipeline is None:
            return _err(
                "No pipeline_path provided and no main.nf found in root or workspace/. "
                "Pass pipeline_path explicitly (e.g. 'workflows/rnaseq/main.nf')."
            )

    if not Path(pipeline).exists():
        return _err(f"Pipeline file not found: {pipeline}")

    cmd = [nextflow_bin, "run", str(pipeline), "--help"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        return _err("nextflow validation timed out after 60s")
    except FileNotFoundError:
        return _ok({
            "status": "warning",
            "message": "nextflow CLI vanished mid-call; skipping validation.",
        })

    success = proc.returncode == 0
    parse_errors: list[str] = []
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in combined.splitlines():
        low = line.lower()
        if any(tok in low for tok in ("error", "exception", "failed to", "unable to")):
            parse_errors.append(line.strip())

    return _ok({
        "tool": "nextflow",
        "pipeline": str(pipeline),
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "success": success,
        "parse_errors": parse_errors[:50],
        "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"process\s+(\w+)", "Nextflow process: {0}"),
    (r"container\s+[\"']([^\"']+)[\"']", "Nextflow container: {0}"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="nextflow",
        version=__version__,
        description="Nextflow (.nf / nextflow.config) workflow provenance extractor.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_nextflow_validate",
                handler=_handle_validate,
                schema={
                    "type": "object",
                    "properties": {
                        "pipeline_path": {
                            "type": "string",
                            "description": "Relative path to main.nf (auto-detected if omitted).",
                        },
                    },
                    "description": (
                        "Validate a Nextflow pipeline by running `nextflow run <main.nf> --help`. "
                        "Surfaces parse errors / missing config / DSL syntax issues that the "
                        "regex-based extractor cannot catch. Degrades to a warning if the "
                        "`nextflow` CLI is not installed on PATH."
                    ),
                },
            ),
        ),
    )
