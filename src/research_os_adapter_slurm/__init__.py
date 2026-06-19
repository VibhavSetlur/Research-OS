"""Slurm (and PBS/Torque) HPC scheduler adapter.

Detects:
    * `#SBATCH` directives in script headers
    * `#PBS` directives (Torque / OpenPBS)
    * Inline `sbatch ` / `qsub ` / `squeue ` invocations in any script

Extracts per-script: scheduler, partition/queue, time, nodes,
cpus-per-task, memory, GPU resources, output/error paths, job name,
account, array spec, and dependency chain.

Optional tools:
    * tool_slurm_job_status(job_id)       — runs squeue/qstat
    * tool_slurm_estimate_cost(step_id)   — multiplies resources × $/h
"""
from __future__ import annotations

import json
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


_SBATCH_RE = re.compile(r"^\s*#\s*SBATCH\b", re.MULTILINE)
_PBS_RE = re.compile(r"^\s*#\s*PBS\b", re.MULTILINE)
# Inline submit at a command position only: line start (indented ok) or
# after a shell separator / command substitution. Anchoring this way stops
# `# sbatch …` comments and `echo "submit with sbatch"` from false-firing
# the adapter on non-HPC projects. Query commands (squeue/qstat) are NOT a
# submit signal, so they're excluded.
_INLINE_RE = re.compile(r"(?m)(?:^|[;&|`]|\$\()\s*(?:sbatch|qsub|srun)\b")


def _candidate_scripts(root: Path) -> list[Path]:
    scripts: list[Path] = []
    workspace = root / "workspace"
    for d in (workspace, root / "scripts"):
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".sh", ".bash", ".slurm", ".sbatch"}:
                scripts.append(p)
    return scripts


def detect(root: Path) -> bool:
    for path in _candidate_scripts(root):
        try:
            head = path.read_text(errors="ignore")[:8192]
        except Exception:
            continue
        if _SBATCH_RE.search(head) or _PBS_RE.search(head) or _INLINE_RE.search(head):
            return True
    return False


# ── extraction ────────────────────────────────────────────────────────


_DIRECTIVE_RE = re.compile(r"^\s*#\s*(SBATCH|PBS)\s+(.+?)\s*$", re.MULTILINE)
# --key=value | --key value | --flag | -k value. The value form excludes a
# leading '-' so a bare boolean flag (`--exclusive --next`) doesn't swallow
# the following option as its value.
_KV_RE = re.compile(
    r"--([A-Za-z][\w-]*)(?:[=\s]+([^-\s]\S*))?"
    r"|(?:^|\s)-([A-Za-z])\s+([^-\s]\S*)"
)
# PBS resource lists: `-l nodes=2:ppn=8,walltime=01:00:00`.
_PBS_L_RE = re.compile(r"-l\s+(\S+)")
# Resource keys whose value is a colon-chunked spec (nodes=2:ppn=8:gpus=1).
# walltime / cput etc. keep their HH:MM:SS colons.
_PBS_NODE_KEYS = {"nodes", "select"}


def _parse_directives(text: str) -> tuple[str, dict]:
    """Return (scheduler, {key: value}) from a script's header directives."""
    scheduler = "unknown"
    kv: dict[str, str] = {}
    for m in _DIRECTIVE_RE.finditer(text[:8192]):
        scheduler = "slurm" if m.group(1) == "SBATCH" else "pbs"
        body = m.group(2)
        # Expand PBS `-l` resource lists first so nodes/ppn/walltime/mem land
        # directly in kv (the old code dropped all of them into kv['l']).
        for lm in _PBS_L_RE.finditer(body):
            for seg in lm.group(1).split(","):
                if "=" not in seg:
                    continue
                k, v = seg.split("=", 1)
                k, v = k.strip(), v.strip()
                if k in _PBS_NODE_KEYS and ":" in v:
                    head, *rest = v.split(":")
                    kv.setdefault(k, head.strip())
                    for sub in rest:
                        if "=" in sub:
                            sk, sv = sub.split("=", 1)
                            kv.setdefault(sk.strip(), sv.strip())
                else:
                    kv.setdefault(k, v)
        for kvm in _KV_RE.finditer(body):
            if kvm.group(1):
                kv[kvm.group(1)] = kvm.group(2) or "true"
            elif kvm.group(3) and kvm.group(3) != "l":
                # '-l <list>' already expanded above; skip the raw capture.
                kv[kvm.group(3)] = kvm.group(4)
    return scheduler, kv


def _modules(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\s*module\s+load\s+(\S+)", text, re.MULTILINE)]


def extract(root: Path, step_id: str | None = None) -> dict:
    scripts = _candidate_scripts(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        scripts = [s for s in scripts if str(s.resolve()).startswith(str(step_prefix))]
    jobs: list[dict] = []
    scheduler = "unknown"
    for path in scripts:
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        sched, kv = _parse_directives(text)
        if sched == "unknown" and not _INLINE_RE.search(text[:8192]):
            continue
        if sched != "unknown":
            scheduler = sched
        rel = path.relative_to(root)
        is_pbs = sched == "pbs"
        # `-N` is nodes in Slurm but the JOB NAME in PBS — disambiguate by
        # scheduler instead of blindly aliasing it to nodes (which crashed
        # the cost estimator on `int('jobname')`).
        nodes_val = kv.get("nodes") or kv.get("select")
        if nodes_val is None and not is_pbs:
            nodes_val = kv.get("N")
        job_name = (
            kv.get("job-name") or kv.get("J")
            or (kv.get("N") if is_pbs else None)
        )
        jobs.append({
            "script": str(rel),
            "scheduler": sched if sched != "unknown" else scheduler,
            "partition": kv.get("partition") or kv.get("queue") or kv.get("q"),
            "time": kv.get("time") or kv.get("walltime"),
            "nodes": nodes_val,
            "ntasks": kv.get("ntasks") or kv.get("n"),
            "cpus_per_task": kv.get("cpus-per-task") or kv.get("c") or kv.get("ppn"),
            "mem": kv.get("mem") or kv.get("mem-per-cpu") or kv.get("pmem"),
            "gres": kv.get("gres"),
            "output": kv.get("output") or kv.get("o"),
            "error": kv.get("error") or kv.get("e"),
            "job_name": job_name,
            "account": kv.get("account") or kv.get("A"),
            "array_spec": kv.get("array"),
            "depends_on": [
                token.split(":", 1)[1] if ":" in token else token
                for token in (kv.get("dependency") or "").split(",") if token
            ],
            "modules_loaded": _modules(text),
        })
    return {
        "scheduler": scheduler,
        "scripts_scanned": len(scripts),
        "jobs": jobs,
    }


def describe() -> dict:
    return {
        "name": "slurm",
        "version": __version__,
        "schedulers_supported": ["slurm", "pbs"],
    }


# ── optional tools ────────────────────────────────────────────────────


def _handle_job_status(name: str, arguments: dict, root: Path) -> Any:
    job_id = (arguments.get("job_id") or "").strip()
    if not job_id:
        return _err("job_id is required")
    squeue = shutil.which("squeue")
    qstat = shutil.which("qstat")
    bin_ = None
    if squeue:
        cmd = [squeue, "-j", job_id, "--json"]
        bin_ = "squeue"
    elif qstat:
        cmd = [qstat, "-f", job_id]
        bin_ = "qstat"
    else:
        return _ok({
            "status": "warning",
            "message": "Neither squeue nor qstat detected on PATH; cannot query.",
        })
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return _err(f"{bin_} timed out after 20s")
    parsed: Any = None
    if bin_ == "squeue":
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None
    return _ok({
        "tool": bin_,
        "job_id": job_id,
        "returncode": proc.returncode,
        "parsed": parsed,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    })


def _parse_time_hours(time_str: str | None) -> float:
    """Convert a Slurm/PBS walltime string to hours.

    Slurm accepts: ``minutes``, ``minutes:seconds``, ``hours:minutes:seconds``,
    ``days-hours``, ``days-hours:minutes``, ``days-hours:minutes:seconds``.
    The dash matters: a bare ``30`` is 30 MINUTES, but the value AFTER a dash
    is hours-first. The old parser treated bare values as seconds and dropped
    the days component — both produced large under-estimates.
    """
    if not time_str:
        return 0.0
    s = str(time_str).strip()
    try:
        days = 0.0
        if "-" in s:
            d, _, s = s.partition("-")
            days = float(d) if d else 0.0
            parts = [float(p) for p in s.split(":")] if s else [0.0]
            while len(parts) < 3:
                parts.append(0.0)
            h, m, sec = parts[0], parts[1], parts[2]
        else:
            parts = [float(p) for p in s.split(":")]
            if len(parts) == 1:        # bare minutes
                h, m, sec = 0.0, parts[0], 0.0
            elif len(parts) == 2:      # MM:SS
                h, m, sec = 0.0, parts[0], parts[1]
            else:                      # HH:MM:SS (extra fields ignored)
                h, m, sec = parts[0], parts[1], parts[2]
    except (TypeError, ValueError):
        return 0.0
    return days * 24 + h + m / 60 + sec / 3600


def _handle_estimate_cost(name: str, arguments: dict, root: Path) -> Any:
    step_id = arguments.get("step_id")
    cost_per_node_hour = float(arguments.get("cost_per_node_hour") or 0.10)
    payload = extract(root, step_id=step_id)
    total_node_hours = 0.0
    per_job = []
    for j in payload["jobs"]:
        # Defensive: nodes may be a range ("1-4"), a PBS jobname misread, or
        # the "true" sentinel from a boolean flag — never crash the estimate.
        nodes_raw = j.get("nodes")
        m_nodes = re.search(r"\d+", str(nodes_raw)) if nodes_raw is not None else None
        nodes = int(m_nodes.group(0)) if m_nodes else 1
        hours = _parse_time_hours(j.get("time"))
        node_hours = nodes * hours
        total_node_hours += node_hours
        per_job.append({
            "script": j["script"],
            "nodes": nodes,
            "hours": round(hours, 2),
            "node_hours": round(node_hours, 2),
            "estimated_usd": round(node_hours * cost_per_node_hour, 2),
        })
    return _ok({
        "total_node_hours": round(total_node_hours, 2),
        "total_estimated_usd": round(total_node_hours * cost_per_node_hour, 2),
        "cost_per_node_hour": cost_per_node_hour,
        "per_job": per_job,
        "note": "Estimate assumes wall-time × node count at the supplied $/node-hour. "
                "Real bills depend on queue priority, GPU surcharges, and minimum-charge rules.",
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"^\s*#\s*SBATCH\s+--partition=(\S+)", "Slurm partition: {0}"),
    (r"^\s*#\s*SBATCH\s+--gres=(\S+)", "Slurm gres: {0}"),
    (r"^\s*#\s*PBS\s+-q\s+(\S+)", "PBS queue: {0}"),
    (r"^\s*module\s+load\s+(\S+)", "HPC module: {0}"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="slurm",
        version=__version__,
        description="Slurm + PBS/Torque HPC scheduler provenance extractor.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_slurm_job_status",
                handler=_handle_job_status,
                schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                    "description": "Query Slurm (squeue --json) or PBS (qstat -f) for a job's status. Returns parsed JSON when the scheduler supports it, otherwise the raw stdout/stderr tail. No-op if neither binary is on PATH.",
                },
            ),
            AdapterTool(
                name="tool_slurm_estimate_cost",
                handler=_handle_estimate_cost,
                schema={
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "cost_per_node_hour": {"type": "number"},
                    },
                    "description": "Estimate compute cost for a step's Slurm/PBS jobs from #SBATCH walltime + node count × supplied $/node-hour. Real bills depend on queue priority + GPU surcharges + minimum-charge rules; treat output as a sanity-check ballpark.",
                },
            ),
        ),
    )
