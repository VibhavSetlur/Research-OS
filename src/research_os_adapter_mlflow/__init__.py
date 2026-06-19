"""MLflow + Weights & Biases experiment-tracking adapter.

Almost all ML / NLP / CV / RL research records runs in an experiment
tracker, and the core machine-learning / hyperparameter-search / ablation
protocols already presume one. This adapter captures that provenance so a
tracked run is traceable from a Research-OS step.

Detects:
    * an `mlruns/` tracking dir (MLflow's default local store)
    * a `wandb/` run dir (Weights & Biases)
    * an `MLproject` file
    * `import mlflow` / `import wandb` (or `mlflow.`/`wandb.` calls) in scripts

Extracts (no network, filesystem-only):
    * MLflow: per-run id / experiment / status / start-end / params / final
      metrics / tags, parsed from mlruns/<exp>/<run>/{meta.yaml,params,metrics,tags}
    * W&B: per-run id + config + summary, from wandb/run-*/files/

This adapter contributes NO MCP tools (provenance is surfaced via the core
tool_adapter_extract / tool_adapters_run_all) — keeping the tool catalog lean.
"""
from __future__ import annotations

import re
from pathlib import Path

from research_os.adapters import AdapterRegistration, register_adapter

__version__ = "1.0.0"


# ── detection ─────────────────────────────────────────────────────────


_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(?:mlflow|wandb)\b", re.MULTILINE)
_CALL_RE = re.compile(r"\b(?:mlflow|wandb)\.\w+\s*\(")
_CODE_EXTS = {".py", ".ipynb", ".r", ".R", ".sh", ".bash"}
_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "site-packages",
    ".os_state", ".ipynb_checkpoints",
}


def _tracking_dirs(root: Path) -> dict:
    """Locate mlruns/ + wandb/ dirs (root or under workspace), non-recursively
    deep — we only need their presence + a shallow walk for runs."""
    found = {"mlruns": [], "wandb": []}
    bases = [root, root / "workspace"]
    seen: set[Path] = set()
    for base in bases:
        if not base.exists():
            continue
        try:
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                if d.name == "mlruns":
                    found["mlruns"].append(d)
                elif d.name == "wandb":
                    found["wandb"].append(d)
        except OSError:
            continue
        # one level into workspace/<step>/ too
        if base.name == "workspace":
            try:
                for step in base.iterdir():
                    if not step.is_dir() or step.name in _SKIP_DIRS:
                        continue
                    for sub in ("mlruns", "wandb"):
                        cand = step / sub
                        if cand.is_dir() and cand not in seen:
                            seen.add(cand)
                            found[sub].append(cand)
            except OSError:
                pass
    return found


def _code_mentions_tracker(root: Path) -> bool:
    for base in (root / "workspace", root / "scripts", root):
        if not base.exists():
            continue
        try:
            walker = base.rglob("*") if base.name != root.name else base.iterdir()
        except OSError:
            continue
        for p in walker:
            try:
                if not p.is_file() or p.suffix.lower() not in _CODE_EXTS:
                    continue
                head = p.read_text(errors="ignore")[:8192]
            except Exception:
                continue
            if _IMPORT_RE.search(head) or _CALL_RE.search(head):
                return True
    return False


def detect(root: Path) -> bool:
    dirs = _tracking_dirs(root)
    if dirs["mlruns"] or dirs["wandb"] or (root / "MLproject").is_file():
        return True
    return _code_mentions_tracker(root)


# ── extraction ────────────────────────────────────────────────────────


_MAX_RUNS = 200  # bound the scan; large sweeps can have thousands of runs


def _read_kv_dir(d: Path) -> dict:
    """MLflow stores each param/tag as a file whose name is the key and whose
    first line is the value."""
    out: dict[str, str] = {}
    if not d.is_dir():
        return out
    try:
        for f in d.iterdir():
            if f.is_file():
                try:
                    out[f.name] = f.read_text(errors="ignore").splitlines()[0].strip()
                except (OSError, IndexError):
                    out[f.name] = ""
    except OSError:
        pass
    return out


def _read_metrics_dir(d: Path) -> dict:
    """Each metric file has lines `<timestamp> <value> <step>`; keep the last."""
    out: dict[str, float] = {}
    if not d.is_dir():
        return out
    try:
        for f in d.iterdir():
            if not f.is_file():
                continue
            try:
                lines = f.read_text(errors="ignore").splitlines()
                if lines:
                    parts = lines[-1].split()
                    if len(parts) >= 2:
                        out[f.name] = float(parts[1])
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return out


def _parse_meta_yaml(meta: Path) -> dict:
    """Minimal flat-YAML reader for mlruns meta.yaml (avoids a yaml dep here)."""
    info: dict[str, str] = {}
    try:
        for line in meta.read_text(errors="ignore").splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition(":")
                info[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return info


def _extract_mlflow(mlruns: Path) -> list[dict]:
    runs: list[dict] = []
    try:
        exp_dirs = [e for e in mlruns.iterdir() if e.is_dir() and e.name != ".trash"]
    except OSError:
        return runs
    for exp in exp_dirs:
        try:
            run_dirs = [r for r in exp.iterdir() if r.is_dir() and (r / "meta.yaml").exists()]
        except OSError:
            continue
        for run in run_dirs:
            if len(runs) >= _MAX_RUNS:
                return runs
            meta = _parse_meta_yaml(run / "meta.yaml")
            runs.append({
                "tracker": "mlflow",
                "experiment_id": exp.name,
                "run_id": meta.get("run_id") or run.name,
                "run_name": meta.get("run_name", ""),
                "status": meta.get("status", ""),
                "start_time": meta.get("start_time", ""),
                "end_time": meta.get("end_time", ""),
                "params": _read_kv_dir(run / "params"),
                "metrics": _read_metrics_dir(run / "metrics"),
                "tags": _read_kv_dir(run / "tags"),
            })
    return runs


def _extract_wandb(wandb_dir: Path) -> list[dict]:
    runs: list[dict] = []
    try:
        run_dirs = [d for d in wandb_dir.iterdir()
                    if d.is_dir() and d.name.startswith(("run-", "offline-run-"))]
    except OSError:
        return runs
    for run in run_dirs:
        if len(runs) >= _MAX_RUNS:
            break
        files = run / "files"
        config_present = (files / "config.yaml").exists()
        runs.append({
            "tracker": "wandb",
            "run_id": run.name,
            "has_config": config_present,
            "has_summary": (files / "wandb-summary.json").exists(),
            "has_metadata": (files / "wandb-metadata.json").exists(),
        })
    return runs


def extract(root: Path, step_id: str | None = None) -> dict:
    scope = root
    if step_id:
        cand = root / "workspace" / step_id
        if cand.exists():
            scope = cand
    dirs = _tracking_dirs(scope if step_id else root)
    runs: list[dict] = []
    trackers: set[str] = set()
    for ml in dirs["mlruns"]:
        got = _extract_mlflow(ml)
        if got:
            trackers.add("mlflow")
        runs.extend(got)
    for wb in dirs["wandb"]:
        got = _extract_wandb(wb)
        if got:
            trackers.add("wandb")
        runs.extend(got)
    return {
        "trackers": sorted(trackers),
        "mlproject_present": (root / "MLproject").is_file(),
        "runs_found": len(runs),
        "truncated": len(runs) >= _MAX_RUNS,
        "runs": runs,
    }


def describe() -> dict:
    return {
        "name": "mlflow",
        "version": __version__,
        "trackers_supported": ["mlflow", "wandb"],
    }


# ── registration ──────────────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"(?i)\bimport\s+mlflow\b", "MLflow experiment tracking"),
    (r"(?i)\bimport\s+wandb\b", "Weights & Biases experiment tracking"),
    (r"mlflow\.set_tracking_uri", "MLflow tracking server configured"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="mlflow",
        version=__version__,
        description="MLflow + Weights & Biases experiment-tracking provenance extractor.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
    )
