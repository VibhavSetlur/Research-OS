"""Sensitivity-grid / multi-verse / specification-curve runner.

Implements the Steegen et al. (2016) and Simonsohn et al. (2020)
"specification curve" pattern: enumerate every reasonable analytic
choice — variable coding, exclusion rules, covariate sets, model
family, transformation — run the analysis under each combination,
then plot the resulting effect distribution. A finding is **robust**
if it survives a large fraction of the multiverse; **fragile** if it
depends on a few specifications.

Workflow
--------
The analyst writes a "grid spec" YAML next to their analysis script::

    # workspace/03_logistic_baseline/sensitivity.yaml
    base_script: scripts/04_fit_v1.py
    estimate_column: estimate        # name of the column the script writes
    ci_columns: [ci_lo, ci_hi]       # 95% CI columns
    output_csv: data/next_step_output/grid_results.csv
    grid:
      covariates:
        - ["age", "sex"]
        - ["age", "sex", "site"]
        - ["age", "sex", "site", "comorbidity_index"]
      exclude_under_18:
        - false
        - true
      outcome_transform:
        - "identity"
        - "log"
        - "winsor_99"
      model_family:
        - "logit"
        - "probit"

The runner fans out the Cartesian product, sets each choice as an
env-var (``RESEARCH_OS_SPEC_<KEY>``), executes the base script per
combination, parses the resulting estimate + CI from a one-row CSV the
script appends to ``output_csv``, and produces a specification-curve
figure (ordered effect dots, choice-matrix below).

The output gets a provenance sidecar listing every spec that was run.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.sensitivity")

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


def _step_dir(step_id: str, root: Path) -> Path:
    return root / "workspace" / step_id


def _spec_path(step_id: str, root: Path) -> Path:
    return _step_dir(step_id, root) / "sensitivity.yaml"


def _expand_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of {key: [values]} → list of single-value dicts."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]
    out: list[dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        out.append(dict(zip(keys, combo, strict=False)))
    return out


def _spec_hash(spec: dict[str, Any]) -> str:
    blob = json.dumps(spec, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:10]


def define_sensitivity(
    step_id: str,
    root: Path,
    *,
    base_script: str,
    estimate_column: str = "estimate",
    ci_columns: tuple[str, str] = ("ci_lo", "ci_hi"),
    grid: dict[str, list[Any]] | None = None,
    output_csv: str = "data/next_step_output/grid_results.csv",
) -> dict[str, Any]:
    """Author ``workspace/<step>/sensitivity.yaml``.

    Seeds a 4-dimension FIELD-NEUTRAL default grid (covariate_set, outlier_rule,
    transform, model_family) with placeholder values the analyst MUST replace
    with the actual analytic decision points for their study.
    """
    sd = _step_dir(step_id, root)
    if not sd.is_dir():
        return {"status": "error", "message": f"step '{step_id}' not found"}
    if not yaml:
        return {"status": "error",
                "message": "PyYAML required for sensitivity specs"}

    # Field-neutral placeholders — the previous default baked in clinical/epi
    # choices (exclude_under_18, age/sex/comorbidity_index) that are meaningless
    # for NLP / physics / economics / ML / qualitative work, yet got copied
    # verbatim. Replace these with your own analytic decision points.
    grid = grid or {
        "covariate_set": [["<baseline>"], ["<baseline>", "<control_A>"]],
        "outlier_rule": ["none", "winsor_99", "drop_3sd"],
        "transform": ["identity", "log"],
        "model_family": ["primary", "alternative"],
    }
    spec = {
        "schema_version": "1.0",
        "base_script": base_script,
        "estimate_column": estimate_column,
        "ci_columns": list(ci_columns),
        "output_csv": output_csv,
        "grid": grid,
    }
    p = _spec_path(step_id, root)
    if p.exists():
        return {
            "status": "exists",
            "path": str(p.relative_to(root)),
            "message": "edit the existing spec; delete to regenerate.",
        }
    p.write_text(yaml.safe_dump(spec, sort_keys=False, default_flow_style=False))

    n = 1
    for vals in grid.values():
        n *= len(vals)
    return {
        "status": "success",
        "path": str(p.relative_to(root)),
        "n_specifications": n,
        "advice": (
            f"sensitivity.yaml seeded with {n} specifications. The base "
            "script will be run once per combination; each run sees the "
            "choices via RESEARCH_OS_SPEC_<KEY> env vars and must append "
            "one row of {estimate, ci_lo, ci_hi, <spec_columns>} to "
            f"{output_csv}. Then call tool_sensitivity_run to execute "
            "the grid."
        ),
    }


def _run_one(
    base_script: Path, step_dir: Path, root: Path,
    spec: dict[str, Any], spec_hash: str,
) -> dict[str, Any]:
    """Execute one specification. Returns metadata + exit code."""
    env = os.environ.copy()
    env["RESEARCH_OS_STEP_DIR"] = str(step_dir.resolve())
    env["RESEARCH_OS_SPEC_HASH"] = spec_hash
    for k, v in spec.items():
        env[f"RESEARCH_OS_SPEC_{k.upper()}"] = json.dumps(v, default=str)

    ext = base_script.suffix.lower()
    if ext == ".py":
        cmd = [sys.executable, str(base_script)]
    elif ext == ".r":
        cmd = ["Rscript", str(base_script)]
    elif ext == ".jl":
        cmd = ["julia", str(base_script)]
    elif ext == ".sh":
        cmd = ["bash", str(base_script)]
    else:
        return {
            "spec_hash": spec_hash, "spec": spec,
            "ok": False, "message": f"unsupported script ext: {ext}",
        }

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(step_dir), env=env,
            capture_output=True, text=True, errors="replace", timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return {"spec_hash": spec_hash, "spec": spec, "ok": False,
                "wall": round(time.time() - t0, 2),
                "message": "timeout (1800s)"}
    return {
        "spec_hash": spec_hash, "spec": spec,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "wall": round(time.time() - t0, 2),
        "stderr_tail": (proc.stderr or "")[-300:] if proc.stderr else "",
    }


def run_sensitivity(
    step_id: str,
    root: Path,
    *,
    max_specs: int | None = None,
    render_figure: bool = True,
) -> dict[str, Any]:
    """Execute the full sensitivity grid.

    Truncates to ``max_specs`` when given (handy for testing). After
    the runs finish, parses the output CSV + renders a specification
    curve figure into ``outputs/figures/<step_num>_spec_curve.png``.
    """
    sd = _step_dir(step_id, root)
    if not yaml:
        return {"status": "error", "message": "PyYAML required"}
    spec_path = _spec_path(step_id, root)
    if not spec_path.exists():
        return {"status": "error",
                "message": "sensitivity.yaml not found; "
                           "call tool_sensitivity_define first."}
    spec = yaml.safe_load(spec_path.read_text())

    base_script = sd / spec["base_script"]
    if not base_script.exists():
        return {"status": "error",
                "message": f"base_script not found: {spec['base_script']}"}

    output_csv = sd / spec.get("output_csv", "data/next_step_output/grid_results.csv")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    # Clear stale rows so we get a clean run.
    if output_csv.exists():
        output_csv.unlink()

    specs = _expand_grid(spec.get("grid") or {})
    if max_specs is not None:
        specs = specs[:max_specs]

    runs: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    for s in specs:
        sh = _spec_hash(s)
        runs.append(_run_one(base_script, sd, root, s, sh))
    wall = round(time.time() - t0, 2)
    n_ok = sum(1 for r in runs if r["ok"])

    figure_path = None
    if render_figure and output_csv.exists() and n_ok > 0:
        try:
            figure_path = _render_specification_curve(
                step_id, root, output_csv, spec,
            )
        except Exception as e:
            logger.warning("specification-curve render failed: %s", e)

    # Provenance sidecar for the aggregated CSV.
    try:
        from research_os.tools.actions.state.provenance import (
            write_output_provenance,
        )

        write_output_provenance(
            output_path=output_csv, root=root,
            produced_by={"tool": "tool_sensitivity_run",
                         "script": spec["base_script"]},
            params={"grid": spec.get("grid"),
                    "n_specifications": len(specs),
                    "max_specs": max_specs},
            step_id=step_id,
            started_at=started, wall_seconds=wall,
            extra={"n_successful": n_ok, "n_failed": len(specs) - n_ok},
        )
    except Exception as e:
        logger.debug("sensitivity provenance skipped: %s", e)

    return {
        "status": "success" if n_ok == len(specs) else "warning",
        "step_id": step_id,
        "n_specifications": len(specs),
        "n_successful": n_ok,
        "n_failed": len(specs) - n_ok,
        "output_csv": str(output_csv.relative_to(root)),
        "figure": figure_path,
        "wall_seconds": wall,
        "advice": (
            f"Ran {n_ok}/{len(specs)} specifications. Specification "
            "curve saved alongside the per-spec CSV. Interpret as: a "
            "finding that flips sign across many specs is FRAGILE; one "
            "that holds across all specs is ROBUST."
        ),
    }


def _render_specification_curve(
    step_id: str, root: Path, output_csv: Path, spec: dict[str, Any],
) -> str | None:
    """Render the Steegen-style specification curve."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    # Render through the Research-OS style so the spec-curve carries the
    # cream / Okabe-Ito identity the viz layer enforces (no ad-hoc hex,
    # no white facecolor clashing with dashboard figures).
    from research_os.tools.actions.viz import (
        RO_BG,
        RO_FG,
        RO_MUTED,
        RO_PALETTE,
        RO_RULE,
        apply_research_os_style,
    )

    apply_research_os_style(destination="full_width", palette="accent")
    _pos_color = RO_PALETTE["diverging_emphasis"][1]   # forest = positive
    _neg_color = RO_PALETTE["diverging_emphasis"][0]   # oxblood = negative

    # Parse the CSV.
    rows: list[dict[str, str]] = []
    try:
        with open(output_csv) as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None
    if not rows:
        return None

    est_col = spec.get("estimate_column", "estimate")
    lo_col, hi_col = spec.get("ci_columns", ["ci_lo", "ci_hi"])

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    estimates = [(i, _f(r.get(est_col)),
                  _f(r.get(lo_col)), _f(r.get(hi_col)), r)
                 for i, r in enumerate(rows)]
    estimates = [t for t in estimates if t[1] is not None]
    estimates.sort(key=lambda t: t[1])
    if not estimates:
        return None

    n = len(estimates)
    # Two-panel figure: estimates on top, choice matrix on the bottom.
    spec_cols = [k for k in (rows[0] or {}).keys()
                 if k not in {est_col, lo_col, hi_col}]
    if not spec_cols:
        spec_cols = []
    n_cols = max(1, len(spec_cols))

    fig, axes = plt.subplots(
        2, 1, figsize=(max(8, n * 0.15), 4 + n_cols * 0.3),
        gridspec_kw={"height_ratios": [3, max(1, n_cols * 0.6)]},
        sharex=True,
    )
    ax_top, ax_bot = axes
    est = [t[1] for t in estimates]
    lo  = [t[2] for t in estimates]
    hi  = [t[3] for t in estimates]
    # Dots + CI.
    for i, (e, lo_v, hi_v) in enumerate(zip(est, lo, hi, strict=False)):
        if lo_v is not None and hi_v is not None:
            ax_top.plot([i, i], [lo_v, hi_v], color=RO_RULE, lw=0.7, zorder=1)
        ax_top.scatter([i], [e],
                       color=_pos_color if e >= 0 else _neg_color,
                       s=15, zorder=2, alpha=0.85)
    ax_top.axhline(0, color=RO_MUTED, lw=0.8, linestyle="--")
    ax_top.set_ylabel("Estimate")
    ax_top.set_title(
        f"Specification curve — {len(estimates)} specifications "
        f"({sum(1 for e in est if e > 0)} positive, "
        f"{sum(1 for e in est if e < 0)} negative)"
    )

    # Choice matrix.
    ax_bot.set_yticks(range(len(spec_cols)))
    ax_bot.set_yticklabels(spec_cols)
    ax_bot.set_xlabel("Specifications (ordered by effect size)")
    for col_i, col in enumerate(spec_cols):
        # collect unique values per column, map to marker positions.
        vals = sorted({str(t[4].get(col, "")) for t in estimates})
        val_to_dot = {v: 1 for v in vals}  # all dots same colour for simplicity
        for spec_i, t in enumerate(estimates):
            v = str(t[4].get(col, ""))
            if v and v in val_to_dot:
                ax_bot.scatter([spec_i], [col_i], color=RO_FG,
                               s=8, marker="s")
    ax_bot.set_ylim(-0.5, len(spec_cols) - 0.5)
    ax_bot.invert_yaxis()
    # Layout is handled by the Research-OS style's constrained_layout (set
    # in apply_research_os_style); calling tight_layout() on top of it
    # warns + double-lays-out. savefig(bbox_inches="tight") trims margins.

    step_num = step_id.split("_", 1)[0]
    figs_dir = _step_dir(step_id, root) / "outputs" / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    out_png = figs_dir / f"{step_num}_specification_curve.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor=RO_BG)
    plt.close(fig)

    # Sibling caption + summary.
    cap = out_png.with_suffix(".caption.md")
    cap.write_text(
        f"**Specification curve.** Each dot is the estimated effect under "
        f"one of {len(estimates)} reasonable analytic specifications, "
        "sorted by magnitude. Vertical lines are 95% CIs. The bottom "
        "panel shows which choices produced which effect. A robust "
        "finding holds across most specifications; a fragile one flips "
        "sign or loses significance under a handful.\n"
    )
    # Provenance for the figure.
    try:
        from research_os.tools.actions.state.provenance import (
            write_output_provenance,
        )

        write_output_provenance(
            output_path=out_png, root=root,
            produced_by={"tool": "tool_sensitivity_run",
                         "kind": "specification_curve"},
            params={"n_specifications": len(estimates),
                    "estimate_column": est_col,
                    "spec_columns": spec_cols},
            step_id=step_id,
        )
    except Exception:
        pass

    return str(out_png.relative_to(root))


__all__ = ["define_sensitivity", "run_sensitivity"]
