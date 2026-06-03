"""Per-step sub-task pipeline runner — a small Snakemake/Nextflow.

Replaces the "AI writes one 400-line mega-script per step" anti-pattern
with a declarative, content-hashed, topologically-ordered runner that
treats each numbered analysis step as a DAG of atomic scripts. The
canonical sub-task chain for a quantitative analysis is::

    ingest → validate → clean → featurize → split → fit → diagnose
                                            ↘ visualize → report

Each node is a small, single-purpose script (≤150 lines is the soft
limit) declaring its inputs and outputs. The runner:

  * builds the DAG from output→input matching;
  * walks it in topological order;
  * skips nodes whose inputs + params + script are content-hash matched
    against a previous successful run (cached re-execution);
  * captures wall time, stderr tail, and exit code per node;
  * emits a per-file provenance sidecar (see ``state/provenance.py``)
    for every output the node writes;
  * appends an entry to ``workspace/<step>/.pipeline_run/run_<ts>.json``
    so reviewers can see exactly which subset re-ran on each invocation.

The pipeline spec lives at ``workspace/<step>/pipeline.yaml``. Minimal
example::

    name: baseline_logistic
    description: |
      Logistic baseline + calibration on the cleaned cohort.
    nodes:
      - id: ingest
        script: scripts/01_ingest_v1.py
        inputs: ["data/input/raw.csv"]
        outputs: ["data/output/loaded.parquet"]
      - id: validate
        script: scripts/02_validate_v1.py
        inputs: ["data/output/loaded.parquet"]
        outputs: ["data/output/validated.parquet",
                  "outputs/reports/02_data_quality.md"]
        params: {schema: schemas/cohort.yaml}
      - id: clean
        script: scripts/03_clean_v1.py
        inputs: ["data/output/validated.parquet"]
        outputs: ["data/output/clean.parquet"]
      - id: fit
        script: scripts/04_fit_v1.py
        inputs: ["data/output/clean.parquet"]
        outputs: ["data/output/model.pkl",
                  "data/output/residuals.csv"]
        params: {seed: 42, alpha: 0.05}
      - id: diagnose
        script: scripts/05_diagnose_v1.py
        inputs: ["data/output/residuals.csv", "data/output/model.pkl"]
        outputs: ["outputs/figures/03_residuals.png",
                  "outputs/figures/03_qq.png",
                  "outputs/figures/03_calibration.png"]
      - id: report
        script: scripts/06_report_v1.py
        inputs: ["outputs/figures/03_residuals.png", "data/output/model.pkl"]
        outputs: ["outputs/reports/03_results.md"]

Why this matters for "national-lab" rigour
------------------------------------------
* **No mega-scripts.** The AI is forced to decompose into focused
  modules. ``tool_audit_step_completeness`` BLOCKS when a step has
  >2 scripts and no pipeline.yaml.
* **Partial re-runs.** A change to the clean script only re-runs
  clean → fit → diagnose → report. Ingest + validate are cached.
* **Reviewable.** The .pipeline_run/run_*.json trace shows exactly
  what ran, what was cached, with what input hashes.
* **Reproducible.** Every output the runner produces gets a provenance
  sidecar (input hashes + params + seed + versions + wall time).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.step_pipeline")

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


# ---------------------------------------------------------------------------
# Spec helpers
# ---------------------------------------------------------------------------


def _step_dir(step_id: str, root: Path) -> Path:
    return root / "workspace" / step_id


def _spec_path(step_id: str, root: Path) -> Path:
    return _step_dir(step_id, root) / "pipeline.yaml"


def _run_log_dir(step_id: str, root: Path) -> Path:
    return _step_dir(step_id, root) / ".pipeline_run"


def _load_spec(step_id: str, root: Path) -> dict[str, Any]:
    p = _spec_path(step_id, root)
    if not p.exists():
        return {}
    if not yaml:
        raise RuntimeError("PyYAML required to read pipeline.yaml")
    return yaml.safe_load(p.read_text()) or {}


def _save_spec(spec: dict[str, Any], step_id: str, root: Path) -> None:
    if not yaml:
        raise RuntimeError("PyYAML required to write pipeline.yaml")
    p = _spec_path(step_id, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(spec, sort_keys=False, default_flow_style=False))


def _file_sha(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def _node_fingerprint(
    node: dict[str, Any], step_dir: Path,
) -> str:
    """Stable content hash of a node's inputs + script + params.

    Two runs with identical fingerprints can reuse cached outputs.
    """
    h = hashlib.sha256()
    # script source
    script = step_dir / node.get("script", "")
    if script.exists():
        try:
            h.update(b"script:")
            h.update(script.read_bytes())
        except OSError:
            pass
    # params (canonical JSON)
    h.update(b"|params:")
    h.update(json.dumps(node.get("params", {}), sort_keys=True, default=str).encode())
    # inputs (hashes of file contents)
    h.update(b"|inputs:")
    for rel in sorted(node.get("inputs") or []):
        p = step_dir / rel
        s = _file_sha(p)
        h.update(f"{rel}={s}".encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# DAG construction
# ---------------------------------------------------------------------------


def _topo_order(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topologically sort nodes by output→input matching.

    A node B depends on a node A if any of B's inputs appears in A's
    outputs. Independent nodes keep their declaration order so the spec
    is reviewable in the order the analyst wrote it.
    """
    produces: dict[str, str] = {}      # rel_path → node_id
    for n in nodes:
        for o in n.get("outputs") or []:
            produces[o] = n["id"]
    deps: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for n in nodes:
        for i in n.get("inputs") or []:
            owner = produces.get(i)
            if owner and owner != n["id"]:
                deps[n["id"]].add(owner)

    # Kahn's algorithm.
    order: list[str] = []
    pending = {n["id"]: set(deps[n["id"]]) for n in nodes}
    ready = [n["id"] for n in nodes if not pending[n["id"]]]
    by_id = {n["id"]: n for n in nodes}
    while ready:
        # Preserve declaration order among siblings.
        ready.sort(key=lambda nid: list(by_id).index(nid))
        nid = ready.pop(0)
        order.append(nid)
        for other, blocked in pending.items():
            if nid in blocked:
                blocked.remove(nid)
                if not blocked and other not in order and other not in ready:
                    ready.append(other)
    if len(order) != len(nodes):
        cycle = [nid for nid, blocked in pending.items() if blocked]
        raise ValueError(
            "pipeline cycle / unsatisfiable dependency among nodes: "
            + ", ".join(sorted(cycle))
        )
    return [by_id[nid] for nid in order]


# ---------------------------------------------------------------------------
# Public API — define, run, status
# ---------------------------------------------------------------------------


_DEFAULT_TEMPLATE_NODES = [
    {"id": "ingest",
     "purpose": "Load raw inputs, validate schema, freeze a versioned snapshot.",
     "inputs":  ["data/input/<raw>"],
     "outputs": ["data/output/loaded.parquet"]},
    {"id": "clean",
     "purpose": "Apply documented transforms; log every drop / impute.",
     "inputs":  ["data/output/loaded.parquet"],
     "outputs": ["data/output/clean.parquet"]},
    {"id": "validate",
     "purpose": "Schema check, range check, missingness report.",
     "inputs":  ["data/output/clean.parquet"],
     "outputs": ["outputs/reports/<NN>_data_quality.md"]},
    {"id": "fit",
     "purpose": "Estimate the primary model. RNG seed mandatory.",
     "inputs":  ["data/output/clean.parquet"],
     "outputs": ["data/output/model.pkl",
                 "data/output/residuals.csv",
                 "data/output/coefficients.csv"]},
    {"id": "diagnose",
     "purpose": "Residual diagnostics, calibration, robustness.",
     "inputs":  ["data/output/residuals.csv", "data/output/model.pkl"],
     "outputs": ["outputs/figures/<NN>_residual_diagnostics.png",
                 "outputs/figures/<NN>_calibration.png"]},
    {"id": "visualize",
     "purpose": "Publication-grade figures — AI writes the script (matplotlib / ggplot2 / Altair / d3); load visualization/figure_guidelines for the chart-chooser + palette + pre-publish self-review checklist.",
     "inputs":  ["data/output/model.pkl", "data/output/coefficients.csv"],
     "outputs": ["outputs/figures/<NN>_focal.png"]},
    {"id": "report",
     "purpose": "Assemble a markdown report; numbers must trace to outputs.",
     "inputs":  ["outputs/figures/<NN>_focal.png", "data/output/coefficients.csv"],
     "outputs": ["outputs/reports/<NN>_results.md"]},
]


def define_pipeline(
    step_id: str,
    root: Path,
    *,
    name: str | None = None,
    description: str = "",
    nodes: list[dict[str, Any]] | None = None,
    template: str = "default",
) -> dict[str, Any]:
    """Author / refresh ``workspace/<step>/pipeline.yaml``.

    When ``nodes`` is not given, a 7-node template (ingest → clean →
    validate → fit → diagnose → visualize → report) is seeded with
    ``<NN>`` placeholders for the analyst to fill in. Idempotent —
    re-running on an existing spec keeps the analyst's edits unless
    ``overwrite=True``.

    Returns the spec dict + path.
    """
    sd = _step_dir(step_id, root)
    if not sd.is_dir():
        return {"status": "error",
                "message": f"Step '{step_id}' not found at workspace/{step_id}/"}

    if not nodes:
        step_num = step_id.split("_", 1)[0]
        nodes = [
            {**n,
             "outputs": [o.replace("<NN>", step_num) for o in n["outputs"]]}
            for n in _DEFAULT_TEMPLATE_NODES
        ]

    spec = {
        "name": name or step_id,
        "description": description.strip() or (
            "Multi-stage analysis pipeline. Each node is a small, focused "
            "script. The runner walks the DAG, caches by content hash, and "
            "writes a provenance sidecar for every output."
        ),
        "schema_version": "1.0",
        "nodes": nodes,
    }
    p = _spec_path(step_id, root)
    if p.exists():
        return {
            "status": "exists",
            "message": (
                f"pipeline.yaml already at workspace/{step_id}/. Edit it "
                "directly; tool_step_pipeline_run reads from there. To "
                "regenerate from the template, delete the file first."
            ),
            "path": str(p.relative_to(root)),
        }
    _save_spec(spec, step_id, root)
    return {
        "status": "success",
        "path": str(p.relative_to(root)),
        "nodes": len(nodes),
        "template": template,
        "advice": (
            "pipeline.yaml seeded. Edit each node's `script` and `params` "
            "to match the actual analysis, then call tool_step_pipeline_run. "
            "Each node should be a small, single-purpose script — the "
            "runner walks them in topological order and caches by content "
            "hash."
        ),
    }


def _cache_key(node: dict[str, Any], step_dir: Path) -> str:
    return _node_fingerprint(node, step_dir)


def _load_cache(step_id: str, root: Path) -> dict[str, str]:
    """Map node_id → fingerprint of the last successful run."""
    log_dir = _run_log_dir(step_id, root)
    if not log_dir.exists():
        return {}
    runs = sorted(log_dir.glob("run_*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        return {}
    try:
        latest = json.loads(runs[0].read_text())
        return {
            nr["node_id"]: nr.get("fingerprint", "")
            for nr in latest.get("nodes", [])
            if nr.get("status") == "success" and nr.get("fingerprint")
        }
    except Exception:
        return {}


def _run_node(
    node: dict[str, Any], step_dir: Path, root: Path,
) -> dict[str, Any]:
    """Execute one node and write provenance sidecars for its outputs."""
    nid = node["id"]
    script = node.get("script")
    if not script:
        return {
            "node_id": nid, "status": "error",
            "message": "node has no `script` field",
        }
    script_path = step_dir / script
    if not script_path.exists():
        return {
            "node_id": nid, "status": "error",
            "message": f"script not found: {script}",
        }

    inputs = node.get("inputs") or []
    params = node.get("params") or {}

    # Validate that all declared inputs exist before running.
    missing = [
        rel for rel in inputs
        if not (step_dir / rel).exists()
    ]
    if missing:
        return {
            "node_id": nid, "status": "skipped_missing_inputs",
            "missing": missing,
            "message": f"upstream inputs not yet produced: {missing}",
        }

    # Track runtime + execute.
    from research_os.tools.actions.state.provenance import (
        track_runtime, write_output_provenance,
    )

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    env = os.environ.copy()
    # Make the step folder importable and pass params through env.
    env["RESEARCH_OS_STEP_DIR"] = str(step_dir.resolve())
    env["RESEARCH_OS_PARAMS"] = json.dumps(params, default=str)

    ext = script_path.suffix.lower()
    if ext == ".py":
        cmd = [sys.executable, str(script_path)]
    elif ext == ".r":
        cmd = ["Rscript", str(script_path)]
    elif ext == ".jl":
        cmd = ["julia", str(script_path)]
    elif ext == ".sh":
        cmd = ["bash", str(script_path)]
    else:
        return {
            "node_id": nid, "status": "error",
            "message": f"unsupported script extension: {ext}",
        }

    try:
        proc = subprocess.run(
            cmd, cwd=str(step_dir), env=env,
            capture_output=True, text=True, timeout=node.get("timeout", 1800),
        )
    except subprocess.TimeoutExpired:
        return {
            "node_id": nid, "status": "timeout",
            "wall_seconds": round(time.time() - t0, 2),
            "message": "node exceeded timeout",
        }
    wall = round(time.time() - t0, 4)

    if proc.returncode != 0:
        return {
            "node_id": nid, "status": "error",
            "exit_code": proc.returncode,
            "wall_seconds": wall,
            "stderr_tail": (proc.stderr or "")[-1500:],
            "message": f"script exited with code {proc.returncode}",
        }

    # Verify declared outputs were produced.
    outputs = node.get("outputs") or []
    produced: list[str] = []
    not_produced: list[str] = []
    for rel in outputs:
        p = step_dir / rel
        if p.exists():
            produced.append(rel)
        else:
            not_produced.append(rel)

    # Drop provenance sidecars for produced outputs.
    sidecars: list[str] = []
    for rel in produced:
        try:
            sidecar = write_output_provenance(
                output_path=step_dir / rel,
                root=root,
                produced_by={
                    "tool": "tool_step_pipeline_run",
                    "script": script,
                    "wf_node": nid,
                },
                inputs={i: step_dir / i for i in inputs},
                params=params,
                rng_seed=params.get("seed") or params.get("rng_seed"),
                started_at=started,
                wall_seconds=wall,
                step_id=step_dir.name,
            )
            sidecars.append(str(sidecar.relative_to(root)))
        except Exception as e:
            logger.warning("provenance sidecar failed for %s: %s", rel, e)

    return {
        "node_id": nid,
        "status": "success" if not not_produced else "missing_outputs",
        "exit_code": proc.returncode,
        "wall_seconds": wall,
        "produced": produced,
        "missing_outputs": not_produced,
        "stderr_tail": (proc.stderr or "")[-400:] if proc.stderr else "",
        "stdout_tail": (proc.stdout or "")[-400:] if proc.stdout else "",
        "sidecars": sidecars,
    }


def run_pipeline(
    step_id: str,
    root: Path,
    *,
    only: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the step's sub-task DAG.

    Parameters
    ----------
    step_id:
        Numbered step folder.
    only:
        Restrict execution to this set of node IDs (and their upstream
        dependencies). Useful for "just rerun the report" workflows.
    force:
        Skip the content-hash cache and re-run every node.
    dry_run:
        Walk the DAG without executing anything. Returns the plan.
    """
    sd = _step_dir(step_id, root)
    if not sd.is_dir():
        return {"status": "error", "message": f"step '{step_id}' not found"}
    spec = _load_spec(step_id, root)
    if not spec:
        return {
            "status": "error",
            "message": (
                f"No pipeline.yaml at workspace/{step_id}/. "
                "Call tool_step_pipeline_define first."
            ),
        }
    nodes = spec.get("nodes") or []
    if not nodes:
        return {"status": "error", "message": "pipeline has no nodes"}

    try:
        ordered = _topo_order(nodes)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    # Filter to `only` + transitive deps.
    if only:
        keep: set[str] = set(only)
        # walk upstream deps repeatedly
        produces = {o: n["id"] for n in nodes for o in (n.get("outputs") or [])}
        by_id = {n["id"]: n for n in nodes}
        changed = True
        while changed:
            changed = False
            for nid in list(keep):
                if nid not in by_id:
                    continue
                for inp in by_id[nid].get("inputs") or []:
                    owner = produces.get(inp)
                    if owner and owner not in keep:
                        keep.add(owner)
                        changed = True
        ordered = [n for n in ordered if n["id"] in keep]

    cache = {} if force else _load_cache(step_id, root)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()

    node_results: list[dict[str, Any]] = []
    for n in ordered:
        nid = n["id"]
        fp = _cache_key(n, sd)
        if not force and cache.get(nid) == fp:
            node_results.append({
                "node_id": nid, "status": "cached",
                "fingerprint": fp,
                "message": "inputs + params + script unchanged; reused cached outputs",
            })
            continue
        if dry_run:
            node_results.append({
                "node_id": nid, "status": "dry_run",
                "fingerprint": fp,
                "would_run_script": n.get("script"),
            })
            continue
        res = _run_node(n, sd, root)
        res["fingerprint"] = fp
        node_results.append(res)
        # Hard-stop on first failure so we don't waste work on stale state.
        if res["status"] in {"error", "timeout", "missing_outputs",
                             "skipped_missing_inputs"}:
            logger.warning(
                "pipeline %s stopped at node %s (%s)",
                step_id, nid, res["status"],
            )
            break

    wall = round(time.time() - t0, 2)
    n_success = sum(1 for r in node_results if r["status"] == "success")
    n_cached  = sum(1 for r in node_results if r["status"] == "cached")
    n_failed  = sum(1 for r in node_results if r["status"] in {
        "error", "timeout", "missing_outputs", "skipped_missing_inputs"})

    record = {
        "step_id": step_id,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": wall,
        "dry_run": dry_run,
        "force": force,
        "filter_only": only,
        "nodes": node_results,
        "summary": {
            "success": n_success,
            "cached": n_cached,
            "failed": n_failed,
            "skipped": len(node_results) - n_success - n_cached - n_failed,
        },
    }
    log_dir = _run_log_dir(step_id, root)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (log_dir / f"run_{ts}.json").write_text(
        json.dumps(record, indent=2, default=str) + "\n"
    )

    # Trim run logs — keep the last 12 runs.
    runs = sorted(log_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime)
    for old in runs[:-12]:
        try:
            old.unlink()
        except OSError:
            pass

    return {
        "status": "success" if n_failed == 0 else "error",
        "step_id": step_id,
        "nodes_total": len(ordered),
        "nodes_ran": n_success,
        "nodes_cached": n_cached,
        "nodes_failed": n_failed,
        "wall_seconds": wall,
        "node_results": node_results,
        "run_log": str((log_dir / f"run_{ts}.json").relative_to(root)),
        "advice": (
            f"Pipeline {'failed' if n_failed else 'completed'}. "
            f"{n_cached} node(s) reused cached outputs, "
            f"{n_success} re-ran, {n_failed} failed. "
            "Inspect the run_log for per-node detail."
        ),
    }


def pipeline_status(step_id: str, root: Path) -> dict[str, Any]:
    """Return the DAG, latest run timestamps, and per-node staleness."""
    sd = _step_dir(step_id, root)
    if not sd.is_dir():
        return {"status": "error", "message": f"step '{step_id}' not found"}
    spec = _load_spec(step_id, root)
    if not spec:
        return {
            "status": "not_initialised",
            "message": (
                f"No pipeline.yaml at workspace/{step_id}/. "
                "Call tool_step_pipeline_define."
            ),
            "advice": (
                "A multi-script step without a pipeline declaration is "
                "harder to re-run, review, and reproduce. Define one."
            ),
        }

    cache = _load_cache(step_id, root)
    nodes_status = []
    for n in spec["nodes"]:
        nid = n["id"]
        fp = _cache_key(n, sd)
        cached_fp = cache.get(nid)
        if cached_fp == fp:
            state = "fresh"
        elif cached_fp:
            state = "stale"
        else:
            state = "never_run"
        nodes_status.append({
            "id": nid,
            "script": n.get("script"),
            "inputs": n.get("inputs", []),
            "outputs": n.get("outputs", []),
            "state": state,
            "fingerprint": fp,
            "cached_fingerprint": cached_fp,
        })

    log_dir = _run_log_dir(step_id, root)
    runs = sorted(log_dir.glob("run_*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True) if log_dir.exists() else []
    return {
        "status": "success",
        "step_id": step_id,
        "name": spec.get("name"),
        "nodes": nodes_status,
        "n_nodes": len(nodes_status),
        "n_fresh": sum(1 for n in nodes_status if n["state"] == "fresh"),
        "n_stale": sum(1 for n in nodes_status if n["state"] == "stale"),
        "n_never_run": sum(1 for n in nodes_status if n["state"] == "never_run"),
        "last_run": str(runs[0].relative_to(root)) if runs else None,
        "total_runs": len(runs),
    }


def render_pipeline_diagram(step_id: str, root: Path) -> dict[str, Any]:
    """Render the step's sub-task DAG as a Mermaid diagram + PNG.

    Writes ``workspace/<step>/pipeline.mermaid`` + (when matplotlib is
    available) ``workspace/<step>/pipeline.png`` so the dashboard's
    per-step appendix can embed it.
    """
    sd = _step_dir(step_id, root)
    if not sd.is_dir():
        return {"status": "error", "message": f"step '{step_id}' not found"}
    spec = _load_spec(step_id, root)
    if not spec:
        return {"status": "error", "message": "pipeline.yaml not found"}

    nodes = spec["nodes"]
    produces = {o: n["id"] for n in nodes for o in (n.get("outputs") or [])}
    edges: list[tuple[str, str]] = []
    for n in nodes:
        for inp in n.get("inputs") or []:
            owner = produces.get(inp)
            if owner and owner != n["id"]:
                edges.append((owner, n["id"]))

    lines = ["graph LR",
             "    classDef pure fill:#d4edda,stroke:#1a7f37,color:#155724",
             "    classDef compute fill:#fff3cd,stroke:#856404,color:#5c4a05",
             "    classDef report fill:#cce5ff,stroke:#2c5282,color:#1a365d"]
    for n in nodes:
        nid = re.sub(r"[^A-Za-z0-9_]", "_", n["id"])
        label = n["id"]
        # Tag node class by name heuristics.
        cls = "pure"
        if any(t in n["id"].lower() for t in ("fit", "train", "model")):
            cls = "compute"
        elif any(t in n["id"].lower() for t in ("report", "visualize",
                                                  "summarize", "publish")):
            cls = "report"
        lines.append(f'    {nid}["{label}"]:::{cls}')
    for src, dst in edges:
        s = re.sub(r"[^A-Za-z0-9_]", "_", src)
        d = re.sub(r"[^A-Za-z0-9_]", "_", dst)
        lines.append(f"    {s} --> {d}")

    mmd_path = sd / "pipeline.mermaid"
    mmd_path.write_text("\n".join(lines) + "\n")

    return {
        "status": "success",
        "mermaid_path": str(mmd_path.relative_to(root)),
        "nodes": len(nodes),
        "edges": len(edges),
    }


__all__ = [
    "define_pipeline",
    "pipeline_status",
    "render_pipeline_diagram",
    "run_pipeline",
]
