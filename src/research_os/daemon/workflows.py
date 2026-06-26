"""Workflow-engine awareness — pipeline DAG introspection (JUDGE-7).

Real computational research is rarely one command; it is a *pipeline* —
a DAG of steps with file dependencies, run by Snakemake or Nextflow. The
``SubprocessRunner`` (runners.py) can already *execute* ``snakemake`` or
``nextflow`` as ordinary commands, so this module is deliberately NOT
another runner. The gap it closes is **awareness**: before launching a
pipeline a researcher (or an agent driving the project) wants to know
*what steps exist, what is already done, and what would run* — the same
read-only "show me the plan" insight the daemon already gives for rebuilds
(staleness.py), capabilities, and orientation.

Two layers, both read-only:

  detect_workflows(root)      pure, filesystem-only — find Snakefile /
                              *.smk / main.nf / *.nf / nextflow.config.
                              Always works, even with no engine installed.

  introspect_workflow(...)    probe the engine binary; if present, run its
                              native dry-run (``snakemake -n`` /
                              ``nextflow ... -preview``) and parse the
                              planned step list. If the binary is absent
                              (the common case on a login node / shared
                              host) degrade to detection-only with a clear,
                              actionable note — never crash, never 500.

stdlib only (pathlib, shutil, subprocess, re). No top-level imports of the
reasoning layer; the strangler-fig invariant holds.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Engine -> the binary that drives it.
_ENGINE_BIN = {"snakemake": "snakemake", "nextflow": "nextflow"}

# Filename signals that identify a pipeline definition for each engine.
# (glob pattern, engine, the "entrypoint" flag a dry-run would need)
_SIGNALS: list[tuple[str, str]] = [
    ("Snakefile", "snakemake"),
    ("workflow/Snakefile", "snakemake"),
    ("*.smk", "snakemake"),
    ("main.nf", "nextflow"),
    ("nextflow.config", "nextflow"),
    ("*.nf", "nextflow"),
]

_DRYRUN_TIMEOUT_S = 30


def detect_workflows(root: str | Path | None) -> list[dict]:
    """Find pipeline definitions under ``root`` (pure, filesystem-only).

    Returns one entry per detected definition file, newest signal first,
    deduped by resolved path. Never raises; an unreadable root yields [].
    """
    base = Path(root) if root else None
    if base is None or not base.exists():
        return []
    found: dict[str, dict] = {}
    for pattern, engine in _SIGNALS:
        try:
            if "/" in pattern or "*" in pattern:
                matches = base.glob(pattern)
            else:
                p = base / pattern
                matches = [p] if p.exists() else []
        except OSError:
            continue
        for m in matches:
            if not m.is_file():
                continue
            key = str(m.resolve())
            if key in found:
                continue
            try:
                rel = str(m.relative_to(base))
            except ValueError:
                rel = m.name
            found[key] = {
                "engine": engine,
                "path": rel,
                "name": m.name,
            }
    return list(found.values())


def engine_available(engine: str) -> bool:
    """True if the engine's driving binary is on PATH."""
    binary = _ENGINE_BIN.get(engine)
    return bool(binary) and shutil.which(binary) is not None


def _snakemake_steps(lines: list[str]) -> list[str]:
    """Parse rule names from ``snakemake -n`` output.

    The dry-run prints a job table; rule names appear in the ``rule X:``
    lines and the trailing ``Job stats`` table. We pull the distinct rule
    names from the ``rule <name>:`` markers, preserving first-seen order.
    """
    steps: list[str] = []
    seen: set[str] = set()
    for line in lines:
        m = re.match(r"\s*(?:rule|checkpoint)\s+([A-Za-z_][\w-]*):", line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            steps.append(m.group(1))
    return steps


def _nextflow_steps(lines: list[str]) -> list[str]:
    """Parse process names from ``nextflow ... -preview`` output.

    Nextflow preview lists processes as ``[xx/yyyyyy] process > NAME``.
    Pull distinct NAMEs in first-seen order.
    """
    steps: list[str] = []
    seen: set[str] = set()
    for line in lines:
        m = re.search(r"process\s*>\s*([\w:.\-]+)", line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            steps.append(m.group(1))
    return steps


def _dryrun_cmd(engine: str, path: str) -> list[str] | None:
    if engine == "snakemake":
        # -n dry-run, -q quiet noise down; --snakefile points at the file.
        return ["snakemake", "-n", "-q", "--snakefile", path]
    if engine == "nextflow":
        return ["nextflow", "run", path, "-preview"]
    return None


def introspect_workflow(
    root: str | Path | None,
    engine: str,
    path: str,
    *,
    timeout_s: int = _DRYRUN_TIMEOUT_S,
) -> dict[str, Any]:
    """Read-only dry-run introspection of one pipeline definition.

    Returns a structured, JSON-serializable report. If the engine binary
    is absent, returns ``available=False`` with a clear note and the
    detection still intact — the caller (endpoint/CLI) shows the plan when
    possible and the install hint when not. Never raises.
    """
    report: dict[str, Any] = {
        "engine": engine,
        "path": path,
        "available": False,
        "steps": [],
        "step_count": 0,
    }
    if not engine_available(engine):
        binary = _ENGINE_BIN.get(engine, engine)
        report["note"] = (
            f"{engine} not installed ({binary} not on PATH); "
            "showing detection only. Install it to preview the DAG."
        )
        return report

    cmd = _dryrun_cmd(engine, path)
    if cmd is None:
        report["note"] = f"no dry-run command known for engine {engine!r}"
        return report

    base = str(root) if root else None
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd,
            cwd=base,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        report["note"] = f"{engine} disappeared from PATH during introspection"
        return report
    except subprocess.TimeoutExpired:
        report["note"] = f"{engine} dry-run exceeded {timeout_s}s; skipped"
        return report
    except OSError as exc:  # pragma: no cover - defensive
        report["note"] = f"{engine} dry-run failed: {exc}"
        return report

    out_lines = (proc.stdout or "").splitlines() + (proc.stderr or "").splitlines()
    if engine == "snakemake":
        steps = _snakemake_steps(out_lines)
    elif engine == "nextflow":
        steps = _nextflow_steps(out_lines)
    else:  # pragma: no cover
        steps = []

    report["available"] = True
    report["returncode"] = proc.returncode
    report["steps"] = steps
    report["step_count"] = len(steps)
    if proc.returncode != 0 and not steps:
        # Dry-run errored (bad pipeline, missing inputs) — surface a tail.
        report["note"] = "dry-run returned non-zero; pipeline may be incomplete"
        report["stderr_tail"] = (proc.stderr or "").splitlines()[-10:]
    return report


def survey_workflows(
    root: str | Path | None,
    *,
    introspect: bool = True,
    timeout_s: int = _DRYRUN_TIMEOUT_S,
) -> dict[str, Any]:
    """Detect every pipeline under ``root`` and (optionally) introspect each.

    The endpoint/CLI entry point. ``introspect=False`` returns detection
    only (cheap, never shells out). Best-effort throughout: never raises.
    """
    definitions = detect_workflows(root)
    engines_present = {
        e: engine_available(e) for e in sorted({d["engine"] for d in definitions})
    }
    workflows: list[dict] = []
    for d in definitions:
        if introspect:
            workflows.append(
                introspect_workflow(root, d["engine"], d["path"], timeout_s=timeout_s)
            )
        else:
            workflows.append({**d, "available": engines_present.get(d["engine"], False)})
    return {
        "service": "research-os",
        "root": str(root) if root else None,
        "detected": len(definitions),
        "engines_present": engines_present,
        "workflows": workflows,
    }
