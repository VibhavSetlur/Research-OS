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
    register_adapter,
)


__version__ = "1.8.0"


# ── detection ─────────────────────────────────────────────────────────


_SBATCH_RE = re.compile(r"^\s*#\s*SBATCH\b", re.MULTILINE)
_PBS_RE = re.compile(r"^\s*#\s*PBS\b", re.MULTILINE)
_INLINE_RE = re.compile(r"\b(?:sbatch|qsub|squeue|qstat)\b")


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
# --key=value | -k value | --flag
_KV_RE = re.compile(r"--([A-Za-z][\w-]*)(?:=(\S+))?|(?:^|\s)-([A-Za-z])\s+(\S+)")


def _parse_directives(text: str) -> tuple[str, dict]:
    """Return (scheduler, {key: value}) from a script's header directives."""
    scheduler = "unknown"
    kv: dict[str, str] = {}
    for m in _DIRECTIVE_RE.finditer(text[:8192]):
        scheduler = "slurm" if m.group(1) == "SBATCH" else "pbs"
        body = m.group(2)
        for kvm in _KV_RE.finditer(body):
            if kvm.group(1):
                kv[kvm.group(1)] = kvm.group(2) or "true"
            elif kvm.group(3):
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
        jobs.append({
            "script": str(rel),
            "scheduler": sched if sched != "unknown" else scheduler,
            "partition": kv.get("partition") or kv.get("queue") or kv.get("q"),
            "time": kv.get("time") or kv.get("walltime"),
            "nodes": kv.get("nodes") or kv.get("N"),
            "ntasks": kv.get("ntasks") or kv.get("n"),
            "cpus_per_task": kv.get("cpus-per-task") or kv.get("c"),
            "mem": kv.get("mem") or kv.get("mem-per-cpu") or kv.get("l"),
            "gres": kv.get("gres"),
            "output": kv.get("output") or kv.get("o"),
            "error": kv.get("error") or kv.get("e"),
            "job_name": kv.get("job-name") or kv.get("J") or kv.get("N"),
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


def _ok(data: dict) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]


def _err(message: str) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]


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


def _parse_mem_gb(mem: str | None) -> float:
    if not mem:
        return 0.0
    m = re.match(r"^\s*(\d+(?:\.\d+)?)([KMG]?)\s*$", mem.upper())
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "K":
        return val / (1024 * 1024)
    if unit == "M":
        return val / 1024
    if unit == "G" or unit == "":
        return val
    return val


def _parse_time_hours(time_str: str | None) -> float:
    if not time_str:
        return 0.0
    parts = time_str.split("-", 1)
    days = 0.0
    if len(parts) == 2:
        days = float(parts[0])
        rest = parts[1]
    else:
        rest = parts[0]
    hms = rest.split(":")
    hms = [float(p) for p in hms]
    while len(hms) < 3:
        hms.insert(0, 0.0)
    h, m, s = hms[-3], hms[-2], hms[-1]
    return days * 24 + h + m / 60 + s / 3600


def _handle_estimate_cost(name: str, arguments: dict, root: Path) -> Any:
    step_id = arguments.get("step_id")
    cost_per_node_hour = float(arguments.get("cost_per_node_hour") or 0.10)
    payload = extract(root, step_id=step_id)
    total_node_hours = 0.0
    per_job = []
    for j in payload["jobs"]:
        nodes = int(j.get("nodes") or 1)
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
