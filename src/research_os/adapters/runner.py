"""Orchestrates adapter extract() calls + serialises provenance YAML.

Three public functions, each backing one of the core tools registered
in server.py:

    * run_extract(adapter_name, step_id)   ← tool_adapter_extract
    * list_adapters(root)                  ← tool_adapters_list
    * run_all(root, step_id)               ← tool_adapters_run_all
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from research_os.adapters.loader import (
    adapter_registrations,
    installed_adapters,
)

logger = logging.getLogger("research_os.adapters.runner")


def _step_provenance_dir(root: Path, step_id: str | None) -> Path:
    """Resolve `workspace/<step>/provenance/` for step_id (or workspace root)."""
    workspace = root / "workspace"
    if step_id:
        return workspace / step_id / "provenance"
    return workspace / "provenance"


def _serialise(payload: Any) -> str:
    """YAML-dump with stable key order and block style."""
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def run_extract(
    root: Path,
    adapter_name: str,
    step_id: str | None = None,
) -> dict:
    """Run a single adapter's extract() and persist the result.

    Returns
    -------
    dict with `status`, `adapter`, `step_id`, `output_path`, `summary`
    (a small subset of the extract for the caller's response envelope).
    """
    adapters = adapter_registrations()
    if adapter_name not in adapters:
        return {
            "status": "error",
            "message": f"Adapter '{adapter_name}' not installed. "
                       f"Available: {sorted(adapters)}",
        }
    rec = adapters[adapter_name]
    try:
        payload = rec.extract(root, step_id=step_id)
    except Exception as exc:
        return {
            "status": "error",
            "adapter": adapter_name,
            "message": f"extract() raised: {exc}",
        }
    out_dir = _step_provenance_dir(root, step_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{adapter_name}.yaml"
    try:
        out_path.write_text(_serialise(payload))
    except Exception as exc:
        return {
            "status": "error",
            "adapter": adapter_name,
            "message": f"could not write provenance YAML: {exc}",
        }
    summary = _summarise(payload)
    # Mirror the data_convert idiom: a symlinked workspace or odd step_id can
    # make out_path resolve outside root, where relative_to() raises — fall
    # back to the absolute path rather than crashing after the YAML is written.
    try:
        rel = str(out_path.relative_to(root))
    except ValueError:
        rel = str(out_path)
    return {
        "status": "success",
        "adapter": adapter_name,
        "step_id": step_id,
        "output_path": rel,
        "summary": summary,
    }


def list_adapters(root: Path) -> dict:
    """Return installed adapters + detection status for the project."""
    out: list[dict] = []
    for entry in installed_adapters():
        name = entry["name"]
        rec = adapter_registrations().get(name)
        detected = False
        detect_error: str | None = None
        if rec is not None:
            try:
                detected = bool(rec.detect(root))
            except Exception as exc:
                detect_error = str(exc)
        out.append({
            **entry,
            "detected_in_project": detected,
            "detect_error": detect_error,
        })
    return {
        "adapters": out,
        "total_installed": len(out),
        "total_detected": sum(1 for a in out if a["detected_in_project"]),
    }


def run_all(root: Path, step_id: str | None = None) -> dict:
    """Run every detected adapter's extract() across the project."""
    results: list[dict] = []
    for entry in installed_adapters():
        name = entry["name"]
        rec = adapter_registrations().get(name)
        if rec is None:
            continue
        try:
            if not rec.detect(root):
                continue
        except Exception as exc:
            results.append({
                "adapter": name,
                "status": "skipped",
                "reason": f"detect() raised: {exc}",
            })
            continue
        results.append(run_extract(root, name, step_id=step_id))
    # total_attempted counts only records produced by run_extract (which
    # always returns 'success' or 'error'); detect()-raised 'skipped' records
    # are reported separately via total_skipped so the name isn't misleading.
    return {
        "results": results,
        "total_attempted": sum(
            1 for r in results if r.get("status") in ("success", "error")
        ),
        "total_succeeded": sum(1 for r in results if r.get("status") == "success"),
        "total_skipped": sum(1 for r in results if r.get("status") == "skipped"),
    }


def _summarise(payload: Any) -> dict:
    """Tiny envelope summary — just key cardinalities to avoid bloating tool replies."""
    if not isinstance(payload, dict):
        return {"kind": type(payload).__name__}
    summary: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, list):
            summary[f"{k}_count"] = len(v)
        elif isinstance(v, dict):
            summary[f"{k}_keys"] = list(v.keys())[:8]
        else:
            summary[k] = v if not isinstance(v, str) or len(v) <= 80 else v[:80] + "…"
    return summary
