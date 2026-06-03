"""Publication-grade figure builder.

Replaces ad-hoc matplotlib calls in analysis scripts. The goal is that
*every* figure that ends up in the synthesis dashboard, paper, or poster
clears the figure_guidelines bar without the analyst having to remember
every rule.

Design
------
* **Style first**: applies a stylesheet derived from SciencePlots
  (``science`` + ``nature`` if available, else a built-in fallback).
* **Palette enforcement**: Okabe-Ito qualitative (colour-blind safe);
  viridis sequential; PuOr diverging.
* **Mandatory annotations**: figure title, axis labels with units,
  inline sample-size annotation, error bars / CI band when an
  ``error`` column is provided.
* **Dual export**: ``<name>.png`` at 300 DPI (or 400 DPI when
  ``figsize<=4``) + ``<name>.svg`` for vector embedding.
* **Caption + summary sidecars**: writes a ``<name>.caption.md`` (the
  technical caption the analyst supplies) and a ``<name>.summary.md``
  (a short plain-language description for accessibility) so the
  dashboard / paper / poster can pull either form on demand.

The wrapper supports the chart families enumerated in
``figure_guidelines.chart_chooser``:

* ``bar`` (vertical + horizontal)
* ``line``
* ``scatter`` (with optional regression band)
* ``hist`` (histogram + KDE overlay)
* ``box`` / ``violin``
* ``heatmap``
* ``forest`` (effect-size forest plot with CI bars)

Optional backends
-----------------
* **SciencePlots** — Nature/IEEE-style sheet (``pip install SciencePlots``).
* **Plotnine** — grammar-of-graphics path for layered geoms
  (``pip install plotnine``). Used when ``backend="plotnine"``.
* **Plotly** — HTML interactive companion (``pip install plotly``).
  Used when ``backend="plotly"`` or ``interactive=True``.

When an optional backend is missing the wrapper falls back to matplotlib
silently; the returned dict records which backend actually rendered.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("research_os.tools.viz")


# ---------------------------------------------------------------------------
# Palettes — colour-blind safe by default.
# ---------------------------------------------------------------------------

# Okabe-Ito 8-colour palette: distinguishable for all common colour-vision
# deficiencies (CVD). The canonical reference for accessible discrete
# categorical encoding in scientific figures.
OKABE_ITO = [
    "#000000",  # black
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
]

# A polished primary/accent pair derived from the dashboard CSS so figures
# share a visual identity with the deliverable they ship inside.
ACCENT_PRIMARY = "#2C5282"
ACCENT_GOLD = "#B7791F"
ACCENT_GREEN = "#276749"
ACCENT_RED = "#9B2C2C"


def palette_for(kind: str, n: int = 8) -> list[str]:
    """Return a recommended colour list for ``kind``.

    ``kind`` is one of:

    * ``"qualitative"`` — Okabe-Ito 8 (default; CVD-safe).
    * ``"sequential"``  — viridis sampled at ``n`` evenly-spaced points.
    * ``"diverging"``   — PuOr (purple → orange) sampled at ``n``.
    * ``"accent"``      — the dashboard primary/gold/green/red set.
    """
    kind = (kind or "qualitative").lower()
    if kind == "qualitative":
        return list((OKABE_ITO * ((n + 7) // 8))[:n])
    if kind == "accent":
        return [ACCENT_PRIMARY, ACCENT_GOLD, ACCENT_GREEN, ACCENT_RED][:n]
    try:
        import matplotlib  # type: ignore
        import numpy as np  # type: ignore

        cmap_name = {"sequential": "viridis", "diverging": "PuOr"}.get(
            kind, "viridis"
        )
        cmap = matplotlib.colormaps.get(cmap_name)
        rgba = cmap(np.linspace(0.05, 0.95, max(2, n)))
        return [
            "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))
            for r, g, b, _ in rgba
        ]
    except Exception:
        # Fallback when matplotlib/numpy are missing.
        return list((OKABE_ITO * ((n + 7) // 8))[:n])


# ---------------------------------------------------------------------------
# Stylesheet — applied at the start of every figure_create() call.
# ---------------------------------------------------------------------------


def _apply_publication_style(style: str = "default") -> dict[str, Any]:
    """Apply a publication-grade rcParams stack.

    Order of preference:

    1. SciencePlots stylesheet (``science`` + ``nature`` or ``ieee``) if
       installed — closest to what high-impact journals print.
    2. Built-in rcParams stack tuned for the same legibility targets:
       12-pt axis labels, 10-pt ticks, sans-serif title, thin grey
       gridlines, no top/right spines.

    Returns metadata about which path was taken so callers can record it.
    """
    import matplotlib  # type: ignore

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore

    plt.rcdefaults()

    used = "builtin"
    style_name = (style or "default").lower()

    try:
        import scienceplots  # noqa: F401  -- registers the SciencePlots stylesheets

        target = {
            "default": ["science"],
            "nature": ["science", "nature"],
            "ieee": ["science", "ieee"],
            "notebook": ["science", "notebook"],
            "no_latex": ["science", "no-latex"],
        }.get(style_name, ["science", "no-latex"])
        plt.style.use(target)
        used = f"scienceplots:{','.join(target)}"
    except ImportError:
        # Built-in fallback — replicates the most important SciencePlots
        # decisions (sans-serif titles, 12pt labels, no top/right spines,
        # thin grey grid, tight legend) so figures still look polished.
        plt.rcParams.update(
            {
                "font.family": "sans-serif",
                "font.sans-serif": [
                    "Inter", "Helvetica Neue", "Arial",
                    "DejaVu Sans", "sans-serif",
                ],
                "font.size": 11,
                "axes.titlesize": 13,
                "axes.titleweight": "semibold",
                "axes.labelsize": 11,
                "axes.labelweight": "regular",
                "axes.spines.top": False,
                "axes.spines.right": False,
                "axes.grid": True,
                "axes.axisbelow": True,
                "grid.color": "#E2E8F0",
                "grid.linewidth": 0.6,
                "xtick.labelsize": 10,
                "ytick.labelsize": 10,
                "xtick.direction": "out",
                "ytick.direction": "out",
                "legend.fontsize": 10,
                "legend.frameon": False,
                "figure.facecolor": "white",
                "axes.facecolor": "white",
                "savefig.facecolor": "white",
                "figure.dpi": 200,
                "savefig.dpi": 300,
            }
        )

    return {"style": style_name, "applied": used}


# ---------------------------------------------------------------------------
# Data loaders — accept inline list, dict, or a CSV/Parquet path.
# ---------------------------------------------------------------------------


def _load_data(data: Any, root: Path) -> list[dict[str, Any]]:
    """Coerce ``data`` to a list-of-row-dicts the chart builders can consume.

    Accepted shapes:

    * ``list[dict]``  — used as-is.
    * ``dict[str, list]`` — column-oriented; transposed to rows.
    * ``str`` ending in ``.csv``/``.tsv`` — file path, parsed with stdlib csv.
    * ``str`` ending in ``.json`` — file path, expects list[dict] or
      column-oriented dict.
    * ``str`` ending in ``.parquet``/``.feather`` — read via pandas if
      installed.
    """
    if isinstance(data, list):
        return [dict(r) for r in data]

    if isinstance(data, dict):
        # Column-oriented dict.
        cols = list(data.keys())
        if not cols:
            return []
        n = len(data[cols[0]])
        return [{c: data[c][i] for c in cols} for i in range(n)]

    if isinstance(data, str):
        p = root / data if not data.startswith("/") else Path(data)
        if not p.exists():
            raise FileNotFoundError(f"viz data file not found: {data}")
        suffix = p.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            sep = "," if suffix == ".csv" else "\t"
            with open(p, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=sep)
                return list(reader)
        if suffix == ".json":
            payload = json.loads(p.read_text())
            return _load_data(payload, root)
        if suffix in {".parquet", ".feather"}:
            try:
                import pandas as pd  # type: ignore

                df = pd.read_parquet(p) if suffix == ".parquet" else pd.read_feather(p)
                return df.to_dict(orient="records")
            except ImportError as e:
                raise RuntimeError(
                    f"Reading {suffix} requires pandas: pip install pandas pyarrow"
                ) from e

    raise TypeError(
        "Unsupported data input. Pass a list of dicts, column-dict, or a "
        "path to a CSV/TSV/JSON/Parquet file."
    )


def _to_float(value: Any) -> float | None:
    """Best-effort float cast; returns ``None`` for blanks."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _column(rows: list[dict[str, Any]], key: str) -> list[Any]:
    return [r.get(key) for r in rows]


def _numeric_column(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [v for v in (_to_float(r.get(key)) for r in rows) if v is not None]


# ---------------------------------------------------------------------------
# Caption + summary sidecar helpers.
# ---------------------------------------------------------------------------


def _write_caption_sidecars(
    dest_png: Path,
    technical_caption: str,
    plain_english: str | None,
) -> tuple[Path, Path | None]:
    """Drop ``<name>.caption.md`` (technical) and ``<name>.summary.md``
    (accessible plain-language)."""
    cap_path = dest_png.with_suffix(".caption.md")
    summary_path = dest_png.with_suffix(".summary.md")
    technical = technical_caption.strip() or (
        f"**Figure — {dest_png.stem.replace('_', ' ')}.** "
        "_Caption pending. Lead with the substantive finding the figure shows; "
        "name the unit on each axis; call out one specific feature the reader "
        "should look for._"
    )
    if not cap_path.exists() or cap_path.stat().st_size == 0:
        cap_path.write_text(technical + "\n")
    summary_written = None
    if plain_english:
        summary_path.write_text(plain_english.strip() + "\n")
        summary_written = summary_path
    return cap_path, summary_written


# ---------------------------------------------------------------------------
# Chart family renderers.
# ---------------------------------------------------------------------------


def _render_bar(
    ax,
    rows: list[dict[str, Any]],
    *,
    x: str,
    y: str,
    error: str | None,
    palette: list[str],
    horizontal: bool,
) -> None:
    cats = _column(rows, x)
    vals = [(_to_float(v) or 0.0) for v in _column(rows, y)]
    errs = [_to_float(v) for v in _column(rows, error)] if error else None
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    if horizontal:
        ax.barh(cats, vals, color=colors,
                xerr=errs, capsize=4, error_kw={"elinewidth": 1.1})
    else:
        ax.bar(cats, vals, color=colors,
               yerr=errs, capsize=4, error_kw={"elinewidth": 1.1})


def _render_line(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, color_by: str | None, error: str | None,
    palette: list[str],
) -> None:
    if color_by:
        # Group by category, plot one line per group.
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(str(r.get(color_by, "")), []).append(r)
        for i, (label, group_rows) in enumerate(sorted(groups.items())):
            xs = _column(group_rows, x)
            ys = [(_to_float(v) or 0.0) for v in _column(group_rows, y)]
            color = palette[i % len(palette)]
            ax.plot(xs, ys, label=label, color=color, lw=1.8, marker="o", ms=4)
            if error:
                errs = [(_to_float(v) or 0.0) for v in _column(group_rows, error)]
                ax.fill_between(
                    xs,
                    [yv - e for yv, e in zip(ys, errs)],
                    [yv + e for yv, e in zip(ys, errs)],
                    color=color, alpha=0.18,
                )
        ax.legend(loc="best")
    else:
        xs = _column(rows, x)
        ys = [(_to_float(v) or 0.0) for v in _column(rows, y)]
        ax.plot(xs, ys, color=palette[0], lw=2.0, marker="o", ms=4)
        if error:
            errs = [(_to_float(v) or 0.0) for v in _column(rows, error)]
            ax.fill_between(
                xs,
                [yv - e for yv, e in zip(ys, errs)],
                [yv + e for yv, e in zip(ys, errs)],
                color=palette[0], alpha=0.18,
            )


def _render_scatter(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, color_by: str | None, regression: bool,
    palette: list[str],
) -> None:
    if color_by:
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(str(r.get(color_by, "")), []).append(r)
        for i, (label, group_rows) in enumerate(sorted(groups.items())):
            xs = [_to_float(v) for v in _column(group_rows, x)]
            ys = [_to_float(v) for v in _column(group_rows, y)]
            pairs = [(xv, yv) for xv, yv in zip(xs, ys) if xv is not None and yv is not None]
            if not pairs:
                continue
            xs2, ys2 = zip(*pairs, strict=False)
            ax.scatter(xs2, ys2, label=label, color=palette[i % len(palette)],
                       alpha=0.7, edgecolors="white", linewidth=0.5)
        ax.legend(loc="best")
    else:
        xs = [_to_float(v) for v in _column(rows, x)]
        ys = [_to_float(v) for v in _column(rows, y)]
        pairs = [(xv, yv) for xv, yv in zip(xs, ys) if xv is not None and yv is not None]
        if pairs:
            xs2, ys2 = zip(*pairs, strict=False)
            ax.scatter(xs2, ys2, color=palette[0], alpha=0.65,
                       edgecolors="white", linewidth=0.5)
            if regression and len(xs2) >= 3:
                try:
                    import numpy as np  # type: ignore

                    x_arr = np.asarray(xs2, dtype=float)
                    y_arr = np.asarray(ys2, dtype=float)
                    slope, intercept = np.polyfit(x_arr, y_arr, 1)
                    x_line = np.linspace(x_arr.min(), x_arr.max(), 100)
                    y_line = slope * x_line + intercept
                    # 95% confidence band via residual standard error.
                    residuals = y_arr - (slope * x_arr + intercept)
                    sigma = float(np.sqrt(np.sum(residuals ** 2) / max(1, len(x_arr) - 2)))
                    ax.plot(x_line, y_line, color=ACCENT_PRIMARY,
                            lw=1.6, label=f"OLS: y={slope:.3f}x+{intercept:.3f}")
                    ax.fill_between(
                        x_line, y_line - 1.96 * sigma, y_line + 1.96 * sigma,
                        color=ACCENT_PRIMARY, alpha=0.15,
                    )
                    ax.legend(loc="best")
                except Exception as e:
                    logger.debug("regression overlay failed: %s", e)


def _render_hist(
    ax, rows: list[dict[str, Any]], *,
    x: str, bins: int, palette: list[str], kde: bool,
) -> None:
    vals = _numeric_column(rows, x)
    if not vals:
        return
    ax.hist(vals, bins=bins, color=palette[0],
            edgecolor="white", linewidth=0.5, alpha=0.85)
    if kde:
        try:
            import numpy as np  # type: ignore
            from scipy.stats import gaussian_kde  # type: ignore

            arr = np.asarray(vals, dtype=float)
            kde_f = gaussian_kde(arr)
            xs = np.linspace(arr.min(), arr.max(), 200)
            ys = kde_f(xs) * len(arr) * (arr.max() - arr.min()) / bins
            ax.plot(xs, ys, color=ACCENT_PRIMARY, lw=1.6, label="KDE")
            ax.legend(loc="best")
        except Exception:
            pass


def _render_box(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, palette: list[str], violin: bool,
) -> None:
    groups: dict[str, list[float]] = {}
    for r in rows:
        cat = str(r.get(x, ""))
        v = _to_float(r.get(y))
        if v is not None:
            groups.setdefault(cat, []).append(v)
    cats = sorted(groups.keys())
    data = [groups[c] for c in cats]
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    if violin:
        parts = ax.violinplot(data, showmeans=False, showmedians=True)
        for i, body in enumerate(parts["bodies"]):
            body.set_facecolor(colors[i])
            body.set_alpha(0.6)
            body.set_edgecolor("white")
        ax.set_xticks(range(1, len(cats) + 1))
        ax.set_xticklabels(cats)
    else:
        bp = ax.boxplot(
            data, patch_artist=True, tick_labels=cats,
            medianprops={"color": "white", "linewidth": 1.5},
        )
        for patch, color in zip(bp["boxes"], colors, strict=False):
            patch.set_facecolor(color)
            patch.set_edgecolor("#1a202c")


def _render_heatmap(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, z: str, palette_kind: str,
) -> None:
    try:
        import matplotlib  # type: ignore
        import numpy as np  # type: ignore

        xs = sorted({r.get(x) for r in rows})
        ys = sorted({r.get(y) for r in rows})
        grid = np.full((len(ys), len(xs)), np.nan)
        for r in rows:
            xi = xs.index(r.get(x))
            yi = ys.index(r.get(y))
            v = _to_float(r.get(z))
            if v is not None:
                grid[yi, xi] = v
        cmap = matplotlib.colormaps.get(
            {"diverging": "PuOr", "sequential": "viridis"}.get(palette_kind, "viridis")
        )
        im = ax.imshow(grid, cmap=cmap, aspect="auto",
                       interpolation="nearest")
        ax.set_xticks(range(len(xs)))
        ax.set_xticklabels(xs, rotation=45, ha="right")
        ax.set_yticks(range(len(ys)))
        ax.set_yticklabels(ys)
        ax.figure.colorbar(im, ax=ax, shrink=0.85)
    except Exception as e:
        logger.warning("heatmap render failed: %s", e)


def _render_forest(
    ax, rows: list[dict[str, Any]], *,
    label_col: str, effect_col: str, ci_lo_col: str, ci_hi_col: str,
    null_at: float | None,
) -> None:
    """Forest plot: one row per study with effect estimate + 95% CI."""
    n = len(rows)
    if n == 0:
        return
    ys = list(range(n, 0, -1))
    labels = [str(r.get(label_col, "")) for r in rows]
    effects = [(_to_float(r.get(effect_col)) or 0.0) for r in rows]
    los = [(_to_float(r.get(ci_lo_col)) or 0.0) for r in rows]
    his = [(_to_float(r.get(ci_hi_col)) or 0.0) for r in rows]
    for yv, e, lo, hi in zip(ys, effects, los, his, strict=False):
        ax.errorbar(e, yv, xerr=[[max(0.0, e - lo)], [max(0.0, hi - e)]],
                    fmt="o", color=ACCENT_PRIMARY, capsize=3,
                    elinewidth=1.4, markersize=6)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    if null_at is not None:
        ax.axvline(null_at, color="#9b2c2c", linestyle="--", lw=1.0,
                   label=f"Null (={null_at})")
        ax.legend(loc="best")


# ---------------------------------------------------------------------------
# Diagnostic + ML renderers (the "national lab needs these" set).
# ---------------------------------------------------------------------------


def _render_roc(
    ax, rows: list[dict[str, Any]], *,
    y_true: str, y_score: str, color_by: str | None, palette: list[str],
) -> None:
    """ROC curve(s) with AUC annotation. Requires sklearn."""
    from sklearn.metrics import auc, roc_curve  # type: ignore

    groups = _maybe_group(rows, color_by)
    for i, (label, grp) in enumerate(groups):
        yt = [_to_float(r.get(y_true)) for r in grp]
        ys = [_to_float(r.get(y_score)) for r in grp]
        pairs = [(t, s) for t, s in zip(yt, ys) if t is not None and s is not None]
        if len(pairs) < 5:
            continue
        ts, ss = zip(*pairs, strict=False)
        fpr, tpr, _ = roc_curve(ts, ss)
        a = auc(fpr, tpr)
        color = palette[i % len(palette)]
        lbl = f"{label} (AUC = {a:.3f})" if label else f"AUC = {a:.3f}"
        ax.plot(fpr, tpr, color=color, lw=2.0, label=lbl)
    ax.plot([0, 1], [0, 1], color="#6b7280", lw=1.0, linestyle="--",
            label="Chance")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend(loc="lower right")
    ax.set_aspect("equal", adjustable="box")


def _render_pr(
    ax, rows: list[dict[str, Any]], *,
    y_true: str, y_score: str, color_by: str | None, palette: list[str],
) -> None:
    """Precision-Recall curve(s) — preferred over ROC under class imbalance."""
    from sklearn.metrics import average_precision_score, precision_recall_curve  # type: ignore

    groups = _maybe_group(rows, color_by)
    for i, (label, grp) in enumerate(groups):
        yt = [_to_float(r.get(y_true)) for r in grp]
        ys = [_to_float(r.get(y_score)) for r in grp]
        pairs = [(t, s) for t, s in zip(yt, ys) if t is not None and s is not None]
        if len(pairs) < 5:
            continue
        ts, ss = zip(*pairs, strict=False)
        precision, recall, _ = precision_recall_curve(ts, ss)
        ap = average_precision_score(ts, ss)
        color = palette[i % len(palette)]
        lbl = f"{label} (AP = {ap:.3f})" if label else f"AP = {ap:.3f}"
        ax.step(recall, precision, color=color, lw=2.0, where="post", label=lbl)
    # Baseline = class-positive rate.
    yt_all = [_to_float(r.get(y_true)) for r in rows]
    base = sum(1 for v in yt_all if v == 1) / max(1, len(yt_all))
    ax.axhline(base, color="#6b7280", lw=1.0, linestyle="--",
               label=f"Baseline ({base:.3f})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.legend(loc="best")


def _render_calibration(
    ax, rows: list[dict[str, Any]], *,
    y_true: str, y_score: str, palette: list[str], n_bins: int = 10,
) -> None:
    """Reliability diagram (predicted vs. observed in equal-frequency bins)."""
    import numpy as np  # type: ignore

    yt = [_to_float(r.get(y_true)) for r in rows]
    ys = [_to_float(r.get(y_score)) for r in rows]
    pairs = [(t, s) for t, s in zip(yt, ys) if t is not None and s is not None]
    if len(pairs) < n_bins * 2:
        return
    ts, ss = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    edges = np.quantile(ss, np.linspace(0, 1, n_bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    bin_ids = np.digitize(ss, edges) - 1
    mean_pred = []
    mean_obs = []
    counts = []
    for b in range(n_bins):
        mask = bin_ids == b
        if mask.sum() < 2:
            continue
        mean_pred.append(ss[mask].mean())
        mean_obs.append(ts[mask].mean())
        counts.append(int(mask.sum()))
    sizes = [20 + 200 * (c / max(counts)) for c in counts]
    ax.plot([0, 1], [0, 1], color="#6b7280", lw=1.0, linestyle="--",
            label="Perfectly calibrated")
    ax.scatter(mean_pred, mean_obs, s=sizes, color=palette[0],
               alpha=0.85, edgecolors="white", linewidth=1.0,
               label="Model (size = bin n)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed positive rate")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper left")


def _render_qq(
    ax, rows: list[dict[str, Any]], *,
    x: str, palette: list[str],
) -> None:
    """Q-Q plot against a normal distribution — the residual diagnostic standard."""
    import numpy as np  # type: ignore
    from scipy import stats as sst  # type: ignore

    vals = np.array(_numeric_column(rows, x))
    if len(vals) < 5:
        return
    sst.probplot(vals, dist="norm", plot=ax)
    # Recolour matplotlib's default red+blue to our palette.
    lines = ax.get_lines()
    if len(lines) >= 2:
        lines[0].set_color(palette[0])
        lines[0].set_markersize(4)
        lines[0].set_alpha(0.75)
        lines[1].set_color(ACCENT_PRIMARY)
        lines[1].set_linewidth(1.4)
    ax.set_title("")  # we set the title elsewhere
    ax.set_xlabel("Theoretical quantiles")
    ax.set_ylabel("Sample quantiles")


def _render_residual_diagnostics(
    fig, rows: list[dict[str, Any]], *,
    residual: str, fitted: str, palette: list[str],
) -> None:
    """4-panel residual diagnostics (residuals vs fitted, Q-Q, scale-location, ACF)."""
    import numpy as np  # type: ignore
    from scipy import stats as sst  # type: ignore

    res = np.array(_numeric_column(rows, residual))
    fit = np.array(_numeric_column(rows, fitted))
    if len(res) < 5 or len(fit) < 5 or len(res) != len(fit):
        return

    fig.clf()
    fig.set_size_inches(10, 8)
    axs = fig.subplots(2, 2)
    color = palette[0]

    # (1) Residuals vs fitted
    axs[0, 0].scatter(fit, res, color=color, alpha=0.6, s=18,
                      edgecolors="white", linewidth=0.4)
    axs[0, 0].axhline(0, color="#6b7280", lw=0.8, linestyle="--")
    # LOWESS-like running mean.
    try:
        order = np.argsort(fit)
        fit_s = fit[order]
        res_s = res[order]
        w = max(5, len(res_s) // 10)
        smoothed = np.convolve(res_s, np.ones(w) / w, mode="same")
        axs[0, 0].plot(fit_s, smoothed, color=ACCENT_PRIMARY, lw=1.5)
    except Exception:
        pass
    axs[0, 0].set_title("Residuals vs fitted")
    axs[0, 0].set_xlabel("Fitted")
    axs[0, 0].set_ylabel("Residual")

    # (2) Q-Q
    sst.probplot(res, dist="norm", plot=axs[0, 1])
    axs[0, 1].set_title("Normal Q-Q")
    for ln, c in zip(axs[0, 1].get_lines(),
                     [color, ACCENT_PRIMARY], strict=False):
        ln.set_color(c)
        if hasattr(ln, "set_markersize"):
            ln.set_markersize(4)

    # (3) Scale-location: sqrt(|standardised residuals|) vs fitted
    sd = res.std() or 1.0
    sr = np.sqrt(np.abs(res / sd))
    axs[1, 0].scatter(fit, sr, color=color, alpha=0.6, s=18,
                      edgecolors="white", linewidth=0.4)
    axs[1, 0].set_title("Scale-location")
    axs[1, 0].set_xlabel("Fitted")
    axs[1, 0].set_ylabel(r"$\sqrt{|standardised\ residuals|}$")

    # (4) ACF (autocorrelation) — useful for time-series residuals.
    lag_max = min(40, len(res) // 4)
    acf_vals = [1.0]
    mean = res.mean()
    var = ((res - mean) ** 2).sum() or 1.0
    for k in range(1, lag_max + 1):
        cov = ((res[k:] - mean) * (res[:-k] - mean)).sum()
        acf_vals.append(cov / var)
    axs[1, 1].stem(range(lag_max + 1), acf_vals, linefmt=color,
                   markerfmt="o", basefmt=" ")
    ci = 1.96 / np.sqrt(len(res))
    axs[1, 1].axhline(ci, color="#9b2c2c", lw=0.8, linestyle="--")
    axs[1, 1].axhline(-ci, color="#9b2c2c", lw=0.8, linestyle="--")
    axs[1, 1].set_title("Residual ACF")
    axs[1, 1].set_xlabel("Lag")
    axs[1, 1].set_ylabel("ACF")
    fig.tight_layout()


def _render_dot_whisker(
    ax, rows: list[dict[str, Any]], *,
    label_col: str, effect_col: str, ci_lo_col: str, ci_hi_col: str,
    palette: list[str], null_at: float | None = 0.0,
    color_by: str | None = None,
) -> None:
    """Regression-coefficient plot. Like a forest plot but for one model."""
    n = len(rows)
    if n == 0:
        return
    ys = list(range(n, 0, -1))
    if color_by:
        cats = sorted({str(r.get(color_by, "")) for r in rows})
        cat_color = {c: palette[i % len(palette)] for i, c in enumerate(cats)}
        colors = [cat_color[str(r.get(color_by, ""))] for r in rows]
    else:
        colors = [palette[0]] * n
    for yv, r, c in zip(ys, rows, colors, strict=False):
        e = _to_float(r.get(effect_col)) or 0.0
        lo = _to_float(r.get(ci_lo_col)) or 0.0
        hi = _to_float(r.get(ci_hi_col)) or 0.0
        ax.errorbar(e, yv, xerr=[[max(0.0, e - lo)], [max(0.0, hi - e)]],
                    fmt="o", color=c, capsize=3, elinewidth=1.2,
                    markersize=6)
    ax.set_yticks(ys)
    ax.set_yticklabels([str(r.get(label_col, "")) for r in rows])
    if null_at is not None:
        ax.axvline(null_at, color="#9b2c2c", linestyle="--", lw=1.0,
                   alpha=0.7, label=f"Null (={null_at})")
        ax.legend(loc="best")


def _render_ridgeline(
    ax, rows: list[dict[str, Any]], *,
    group: str, value: str, palette: list[str],
) -> None:
    """Joyplot — one KDE per group, stacked vertically."""
    import numpy as np  # type: ignore
    from scipy.stats import gaussian_kde  # type: ignore

    groups: dict[str, list[float]] = {}
    for r in rows:
        c = str(r.get(group, ""))
        v = _to_float(r.get(value))
        if v is not None:
            groups.setdefault(c, []).append(v)
    cats = sorted(groups.keys())
    n = len(cats)
    if n == 0:
        return
    all_vals = [v for vs in groups.values() for v in vs]
    if not all_vals:
        return
    x = np.linspace(min(all_vals), max(all_vals), 200)
    height = 1.0
    for i, c in enumerate(cats):
        arr = np.asarray(groups[c])
        if arr.size < 3:
            continue
        kde = gaussian_kde(arr)
        y = kde(x)
        y = y / y.max() * height * 0.95
        baseline = (n - 1 - i) * height
        color = palette[i % len(palette)]
        ax.fill_between(x, baseline, baseline + y, color=color, alpha=0.6,
                        edgecolor="white", linewidth=0.6)
        ax.plot(x, baseline + y, color=color, lw=1.0)
    ax.set_yticks([(n - 1 - i) * height + height * 0.45 for i in range(n)])
    ax.set_yticklabels(cats)
    ax.spines["left"].set_visible(False)


def _render_raincloud(
    ax, rows: list[dict[str, Any]], *,
    group: str, value: str, palette: list[str],
) -> None:
    """Raincloud = half-violin + boxplot + jittered points."""
    import numpy as np  # type: ignore

    groups: dict[str, list[float]] = {}
    for r in rows:
        c = str(r.get(group, ""))
        v = _to_float(r.get(value))
        if v is not None:
            groups.setdefault(c, []).append(v)
    cats = sorted(groups.keys())
    if not cats:
        return
    rng = __import__("random").Random(7)
    for i, c in enumerate(cats):
        arr = np.asarray(groups[c])
        x_center = i + 1
        color = palette[i % len(palette)]
        # Half-violin on the left of the centre.
        try:
            from scipy.stats import gaussian_kde  # type: ignore

            kde = gaussian_kde(arr)
            ys = np.linspace(arr.min(), arr.max(), 100)
            xs = -kde(ys)
            xs = xs / abs(xs).max() * 0.35
            ax.fill_betweenx(ys, x_center + xs, x_center, color=color,
                             alpha=0.55, edgecolor="white", linewidth=0.6)
        except Exception:
            pass
        # Boxplot in the middle.
        bp = ax.boxplot(
            [arr], positions=[x_center], widths=0.08,
            patch_artist=True, showfliers=False,
            medianprops={"color": "white", "linewidth": 1.5},
        )
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_edgecolor("#1a202c")
        # Jittered points to the right.
        jitter = [x_center + 0.18 + rng.uniform(-0.05, 0.05) for _ in arr]
        ax.scatter(jitter, arr, s=12, color=color, alpha=0.55,
                   edgecolors="white", linewidth=0.4)
    ax.set_xticks(range(1, len(cats) + 1))
    ax.set_xticklabels(cats)


def _render_hexbin(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, gridsize: int = 30, palette_kind: str = "sequential",
) -> None:
    """2D density plot via hexagonal binning — alternative to overplotted scatter."""
    import matplotlib  # type: ignore

    xs = [_to_float(r.get(x)) for r in rows]
    ys = [_to_float(r.get(y)) for r in rows]
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    if not pairs:
        return
    xa, ya = zip(*pairs, strict=False)
    cmap = matplotlib.colormaps.get("viridis" if palette_kind != "diverging" else "PuOr")
    hb = ax.hexbin(xa, ya, gridsize=gridsize, cmap=cmap, mincnt=1)
    cb = ax.figure.colorbar(hb, ax=ax, shrink=0.85)
    cb.set_label("Count")


def _render_slope(
    ax, rows: list[dict[str, Any]], *,
    label_col: str, before_col: str, after_col: str, palette: list[str],
) -> None:
    """Tufte's slope chart — preferred for "before vs after" with many items."""
    for i, r in enumerate(rows):
        label = str(r.get(label_col, ""))
        before = _to_float(r.get(before_col))
        after = _to_float(r.get(after_col))
        if before is None or after is None:
            continue
        color = palette[i % len(palette)]
        ax.plot([0, 1], [before, after], color=color, lw=1.4, alpha=0.85)
        ax.scatter([0, 1], [before, after], color=color, s=30, zorder=5,
                   edgecolors="white", linewidth=0.6)
        # Labels at both ends.
        ax.annotate(f"{label} ({before:.2f})", xy=(0, before),
                    xytext=(-6, 0), textcoords="offset points",
                    ha="right", va="center", fontsize=8.5, color="#2d3748")
        ax.annotate(f"({after:.2f})", xy=(1, after),
                    xytext=(6, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=8.5, color="#2d3748")
    ax.set_xlim(-0.4, 1.4)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([before_col, after_col])
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_yticks([])


def _render_posterior(
    ax, rows: list[dict[str, Any]], *,
    x: str, palette: list[str],
    rope: tuple[float, float] | None = None,
) -> None:
    """Bayesian posterior density with HDI + optional ROPE band."""
    import numpy as np  # type: ignore
    from scipy.stats import gaussian_kde  # type: ignore

    arr = np.array(_numeric_column(rows, x))
    if arr.size < 5:
        return
    kde = gaussian_kde(arr)
    xs = np.linspace(arr.min(), arr.max(), 400)
    ys = kde(xs)
    ax.plot(xs, ys, color=palette[0], lw=2.0)
    ax.fill_between(xs, 0, ys, color=palette[0], alpha=0.25)
    # 94% HDI (Kruschke default).
    sorted_arr = np.sort(arr)
    n = sorted_arr.size
    width = int(0.94 * n)
    diffs = sorted_arr[width:] - sorted_arr[: n - width]
    idx = int(np.argmin(diffs))
    hdi_lo, hdi_hi = sorted_arr[idx], sorted_arr[idx + width]
    ax.axvspan(hdi_lo, hdi_hi, color=palette[0], alpha=0.15,
               label=f"94% HDI [{hdi_lo:.3f}, {hdi_hi:.3f}]")
    ax.axvline(arr.mean(), color=ACCENT_PRIMARY, lw=1.4,
               label=f"Mean = {arr.mean():.3f}")
    if rope is not None:
        ax.axvspan(rope[0], rope[1], color="#9b2c2c", alpha=0.18,
                   label=f"ROPE [{rope[0]:.3f}, {rope[1]:.3f}]")
    ax.set_xlabel(x)
    ax.set_ylabel("Density")
    ax.legend(loc="best")


def _render_var_importance(
    ax, rows: list[dict[str, Any]], *,
    label_col: str, importance_col: str, palette: list[str],
    error: str | None = None,
) -> None:
    """Horizontal variable-importance bar chart, sorted descending."""
    pairs = [
        (str(r.get(label_col, "")),
         _to_float(r.get(importance_col)) or 0.0,
         _to_float(r.get(error)) if error else None)
        for r in rows
    ]
    pairs.sort(key=lambda t: t[1], reverse=True)
    labels = [p[0] for p in pairs]
    vals = [p[1] for p in pairs]
    errs = [p[2] for p in pairs] if error else None
    ys = list(range(len(labels), 0, -1))
    color = palette[0]
    if errs:
        ax.barh(ys, vals, color=color, xerr=errs, capsize=3,
                edgecolor="white", linewidth=0.5,
                error_kw={"elinewidth": 1.0})
    else:
        ax.barh(ys, vals, color=color, edgecolor="white", linewidth=0.5)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()


def _render_funnel(
    ax, rows: list[dict[str, Any]], *,
    effect_col: str, se_col: str, palette: list[str],
) -> None:
    """Publication-bias funnel plot: effect vs precision; pyramid = unbiased."""
    import numpy as np  # type: ignore

    effects = [_to_float(r.get(effect_col)) for r in rows]
    ses     = [_to_float(r.get(se_col))     for r in rows]
    pairs = [(e, s) for e, s in zip(effects, ses)
             if e is not None and s is not None and s > 0]
    if not pairs:
        return
    es, ss = zip(*pairs, strict=False)
    ax.scatter(es, ss, color=palette[0], alpha=0.7, s=22,
               edgecolors="white", linewidth=0.4)
    # Funnel boundaries: meta-mean ± 1.96 * SE
    mean = sum(es) / len(es)
    ax.axvline(mean, color=ACCENT_PRIMARY, lw=1.2,
               label=f"Mean effect = {mean:.3f}")
    se_max = max(ss) * 1.05
    se_range = np.linspace(0, se_max, 50)
    ax.plot(mean - 1.96 * se_range, se_range,
            color="#6b7280", lw=0.9, linestyle="--",
            label="±1.96 SE (95% CI)")
    ax.plot(mean + 1.96 * se_range, se_range,
            color="#6b7280", lw=0.9, linestyle="--")
    ax.invert_yaxis()  # by convention, small SE (precise) at top
    ax.set_xlabel(effect_col)
    ax.set_ylabel("Standard error")
    ax.legend(loc="best")


def _render_alluvial(
    ax, rows: list[dict[str, Any]], *,
    source: str, target: str, value: str, palette: list[str],
) -> None:
    """Sankey/alluvial — flow between two categorical variables."""
    import numpy as np  # type: ignore

    flows: dict[tuple[str, str], float] = {}
    for r in rows:
        s = str(r.get(source, ""))
        t = str(r.get(target, ""))
        v = _to_float(r.get(value)) if value else 1.0
        if v is None:
            v = 1.0
        flows[(s, t)] = flows.get((s, t), 0.0) + v
    sources = sorted({s for s, _ in flows})
    targets = sorted({t for _, t in flows})

    src_totals = {s: sum(v for (a, _), v in flows.items() if a == s) for s in sources}
    tgt_totals = {t: sum(v for (_, b), v in flows.items() if b == t) for t in targets}
    total = sum(src_totals.values()) or 1.0

    # y-positions for source + target boxes (proportional to totals).
    def _positions(totals_dict, order):
        y = 0.0
        out = {}
        for k in order:
            h = totals_dict[k] / total
            out[k] = (y, y + h)
            y += h + 0.02
        return out

    src_pos = _positions(src_totals, sources)
    tgt_pos = _positions(tgt_totals, targets)

    # Draw boxes.
    for s, (y0, y1) in src_pos.items():
        ax.fill_between([-0.02, 0.0], y0, y1,
                        color="#cbd5e1", edgecolor="#1a202c", linewidth=0.6)
        ax.text(-0.04, (y0 + y1) / 2, s, ha="right", va="center", fontsize=9)
    for t, (y0, y1) in tgt_pos.items():
        ax.fill_between([1.0, 1.02], y0, y1,
                        color="#cbd5e1", edgecolor="#1a202c", linewidth=0.6)
        ax.text(1.04, (y0 + y1) / 2, t, ha="left", va="center", fontsize=9)

    # Draw flows as cubic ribbons.
    src_cursor = {s: src_pos[s][0] for s in sources}
    tgt_cursor = {t: tgt_pos[t][0] for t in targets}
    for i, ((s, t), v) in enumerate(sorted(flows.items())):
        h = v / total
        y_s = src_cursor[s]
        src_cursor[s] += h
        y_t = tgt_cursor[t]
        tgt_cursor[t] += h
        # Bezier-ish: 4 control points, fill the band between top + bottom curves.
        N = 50
        xs = np.linspace(0, 1, N)
        # smoothstep for both top + bottom.
        ss = xs ** 2 * (3 - 2 * xs)
        top    = y_s + h + (y_t - y_s) * ss
        bottom = y_s     + (y_t - y_s) * ss
        ax.fill_between(xs, bottom, top,
                        color=palette[i % len(palette)], alpha=0.55,
                        edgecolor="white", linewidth=0.2)
    ax.set_xlim(-0.2, 1.2)
    ax.set_ylim(-0.05, max(
        max(y1 for _, y1 in src_pos.values()),
        max(y1 for _, y1 in tgt_pos.values()),
    ) + 0.05)
    ax.invert_yaxis()
    ax.axis("off")


def _render_hierarchical_heatmap(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, z: str, palette_kind: str = "sequential",
) -> None:
    """Heatmap with hierarchical row + column clustering (dendrogram)."""
    try:
        import matplotlib  # type: ignore
        import numpy as np  # type: ignore
        from scipy.cluster.hierarchy import dendrogram, linkage  # type: ignore
        from scipy.spatial.distance import pdist  # type: ignore
    except ImportError:
        # fall back to regular heatmap
        _render_heatmap(ax, rows, x=x, y=y, z=z, palette_kind=palette_kind)
        return

    xs = sorted({r.get(x) for r in rows})
    ys = sorted({r.get(y) for r in rows})
    grid = np.full((len(ys), len(xs)), np.nan)
    for r in rows:
        try:
            xi = xs.index(r.get(x))
            yi = ys.index(r.get(y))
            v = _to_float(r.get(z))
            if v is not None:
                grid[yi, xi] = v
        except Exception:
            continue
    # Mask + cluster rows + cols.
    np.nan_to_num(grid, copy=False)
    try:
        row_order = dendrogram(linkage(pdist(grid)),
                               no_plot=True)["leaves"]
        col_order = dendrogram(linkage(pdist(grid.T)),
                               no_plot=True)["leaves"]
        grid = grid[np.ix_(row_order, col_order)]
        ys = [ys[i] for i in row_order]
        xs = [xs[i] for i in col_order]
    except Exception:
        pass
    cmap = matplotlib.colormaps.get("viridis" if palette_kind != "diverging" else "PuOr")
    im = ax.imshow(grid, cmap=cmap, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=45, ha="right")
    ax.set_yticks(range(len(ys)))
    ax.set_yticklabels(ys)
    ax.figure.colorbar(im, ax=ax, shrink=0.85)


def _render_partial_dependence(
    ax, rows: list[dict[str, Any]], *,
    x: str, y: str, color_by: str | None, palette: list[str],
) -> None:
    """Marginal prediction curve — like line, but with a transparent rug at bottom."""
    import numpy as np  # type: ignore

    groups = _maybe_group(rows, color_by)
    for i, (label, grp) in enumerate(groups):
        xs = [_to_float(r.get(x)) for r in grp]
        ys = [_to_float(r.get(y)) for r in grp]
        pairs = sorted(
            [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None],
            key=lambda t: t[0],
        )
        if not pairs:
            continue
        xa, ya = zip(*pairs, strict=False)
        color = palette[i % len(palette)]
        ax.plot(xa, ya, color=color, lw=2.0,
                label=label if label else None)
    # rug
    all_x = [_to_float(r.get(x)) for r in rows]
    all_x = [v for v in all_x if v is not None]
    if all_x:
        y0 = ax.get_ylim()[0]
        rug_y = y0 + (ax.get_ylim()[1] - y0) * 0.01
        for v in all_x:
            ax.plot([v, v], [y0, rug_y], color="#6b7280", alpha=0.3, lw=0.5)
    ax.set_xlabel(x)
    ax.set_ylabel(f"Partial dependence on {y}")
    if any(label for label, _ in groups):
        ax.legend(loc="best")


def _render_consort_flow(
    fig, rows: list[dict[str, Any]], *,
    palette: list[str],
) -> None:
    """CONSORT-style enrolment / allocation / follow-up / analysis flow diagram.

    Expects rows = [{stage: str, n: int, note: str}] where stage is one of
    enrolment, allocation, follow-up, analysis (case-insensitive).
    """
    import matplotlib.patches as patches  # type: ignore

    fig.clf()
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")
    # Group rows by stage in CONSORT order.
    order = ["enrolment", "allocation", "follow-up", "follow up",
             "analysis"]
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = str(r.get("stage", "")).lower()
        by_stage.setdefault(key, []).append(r)
    # Draw one box per stage, vertically.
    y = 11
    color = palette[0]
    for stage in order:
        if stage not in by_stage:
            continue
        items = by_stage[stage]
        box_h = max(1.2, 0.8 * len(items) + 0.4)
        ax.add_patch(patches.FancyBboxPatch(
            (1.5, y - box_h), 7, box_h,
            boxstyle="round,pad=0.1,rounding_size=0.2",
            facecolor="#f7fafc", edgecolor=color, linewidth=1.4))
        ax.text(5.0, y - 0.3, stage.title(),
                ha="center", fontsize=11, fontweight="semibold",
                color=color)
        inner = y - 0.7
        for it in items:
            n = it.get("n")
            note = it.get("note", "")
            ax.text(5.0, inner, f"n = {n} — {note}",
                    ha="center", fontsize=9, color="#2d3748")
            inner -= 0.6
        # arrow to next stage
        if stage != order[-1]:
            ax.annotate("", xy=(5.0, y - box_h - 0.55),
                        xytext=(5.0, y - box_h - 0.05),
                        arrowprops=dict(arrowstyle="-|>", color="#3a4661",
                                        lw=1.4))
        y -= box_h + 0.7


# ---------------------------------------------------------------------------
# Helpers shared by the new renderers
# ---------------------------------------------------------------------------


def _maybe_group(rows: list[dict[str, Any]], color_by: str | None,
                 ) -> list[tuple[str, list[dict[str, Any]]]]:
    if not color_by:
        return [("", list(rows))]
    g: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        g.setdefault(str(r.get(color_by, "")), []).append(r)
    return sorted(g.items())


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


_SUPPORTED_KINDS = {
    # Basic charts.
    "bar", "barh", "line", "scatter", "hist", "box", "violin",
    "heatmap", "forest",
    # Diagnostic + ML charts — the "national lab needs these" set.
    "roc", "pr", "calibration", "qq", "residual_diagnostics",
    "dot_whisker", "ridgeline", "raincloud", "hexbin", "slope",
    "posterior", "var_importance", "funnel", "alluvial",
    "hierarchical_heatmap", "partial_dependence", "consort_flow",
}


def figure_create(
    *,
    step_id: str,
    name: str,
    kind: str,
    data: Any,
    root: Path,
    x: str | None = None,
    y: str | None = None,
    z: str | None = None,
    error: str | None = None,
    color_by: str | None = None,
    bins: int = 30,
    regression: bool = False,
    palette: str = "qualitative",
    style: str = "default",
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    caption: str = "",
    plain_english: str | None = None,
    figsize: tuple[float, float] = (7.0, 4.5),
    interactive: bool = False,
    backend: str = "matplotlib",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a publication-grade figure for a numbered analysis step.

    Writes:

    * ``workspace/<step_id>/outputs/figures/<name>.png`` (≥300 DPI)
    * ``workspace/<step_id>/outputs/figures/<name>.svg``
    * ``workspace/<step_id>/outputs/figures/<name>.caption.md`` (technical)
    * ``workspace/<step_id>/outputs/figures/<name>.summary.md`` (plain-English)

    The naming convention enforces ``<step_number>_<descriptor>.png`` so the
    file becomes the step's focal figure (picked up by
    ``tool_synthesis_curate_figures``).

    Parameters
    ----------
    step_id:
        Numbered experiment folder, e.g. ``03_logistic_baseline``.
    name:
        Short descriptor. If it does not start with the step number, the
        step number is prepended automatically.
    kind:
        ``bar`` | ``barh`` | ``line`` | ``scatter`` | ``hist`` | ``box`` |
        ``violin`` | ``heatmap`` | ``forest``.
    data:
        See ``_load_data`` for accepted shapes (list of dicts, column-dict,
        or path to CSV/TSV/JSON/Parquet).
    x / y / z:
        Column names. ``z`` is required for ``heatmap``.
    error:
        Column with one-sided error (bar charts) or radius (line bands).
    color_by:
        Optional grouping column for ``line`` and ``scatter``.
    palette:
        ``qualitative`` (Okabe-Ito, default), ``sequential`` (viridis),
        ``diverging`` (PuOr), ``accent`` (dashboard primary/gold/etc).
    style:
        ``default`` | ``nature`` | ``ieee`` | ``notebook``.
    caption:
        Author-supplied technical caption written to ``<name>.caption.md``.
    plain_english:
        Plain-language description written to ``<name>.summary.md`` for
        accessibility / non-expert audiences. If omitted, no summary file
        is written (call ``tool_figure_caption_synthesise`` later).
    interactive:
        If true AND plotly is installed, ALSO writes an
        ``<name>.html`` interactive companion.
    backend:
        ``matplotlib`` (default), ``plotnine`` (declarative grammar),
        or ``plotly`` (interactive). Unknown backends fall back silently
        to matplotlib.
    """
    kind = (kind or "").lower()
    if kind not in _SUPPORTED_KINDS:
        return {
            "status": "error",
            "message": (
                f"Unsupported chart kind '{kind}'. "
                f"Allowed: {sorted(_SUPPORTED_KINDS)}."
            ),
        }

    # 1. Resolve target directory.
    step_dir = root / "workspace" / step_id
    if not step_dir.is_dir():
        return {
            "status": "error",
            "message": (
                f"Step '{step_id}' not found at workspace/{step_id}/. "
                "Create it with sys_path_create first."
            ),
        }
    figures_dir = step_dir / "outputs" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 2. Enforce <step_number>_<descriptor>.png naming.
    step_num = step_id.split("_", 1)[0]
    safe_name = name.strip().replace(" ", "_")
    if not safe_name.startswith(f"{step_num}_"):
        safe_name = f"{step_num}_{safe_name}"
    if safe_name.endswith((".png", ".svg")):
        safe_name = safe_name.rsplit(".", 1)[0]
    dest_png = figures_dir / f"{safe_name}.png"
    dest_svg = figures_dir / f"{safe_name}.svg"

    # 3. Load + validate data.
    try:
        rows = _load_data(data, root)
    except Exception as e:
        return {"status": "error", "message": f"Data load failed: {e}"}
    if not rows:
        return {"status": "error", "message": "Data is empty — nothing to plot."}

    # 4. Style + palette.
    style_meta = _apply_publication_style(style)
    palette_colors = palette_for(palette, n=8)

    # 5. Render via the selected backend (fallback chain).
    rendered_with = "matplotlib"
    try:
        if backend == "plotnine":
            ok = _render_plotnine(
                kind, rows, dest_png=dest_png, x=x, y=y, color_by=color_by,
                palette=palette_colors, title=title, xlabel=xlabel,
                ylabel=ylabel, figsize=figsize,
            )
            if ok:
                rendered_with = "plotnine"
            else:
                _render_matplotlib(
                    kind, rows, dest_png=dest_png, dest_svg=dest_svg,
                    x=x, y=y, z=z, error=error, color_by=color_by, bins=bins,
                    regression=regression, palette_colors=palette_colors,
                    palette_kind=palette, title=title, xlabel=xlabel,
                    ylabel=ylabel, figsize=figsize, extra=extra,
                )
        else:
            _render_matplotlib(
                kind, rows, dest_png=dest_png, dest_svg=dest_svg,
                x=x, y=y, z=z, error=error, color_by=color_by, bins=bins,
                regression=regression, palette_colors=palette_colors,
                palette_kind=palette, title=title, xlabel=xlabel,
                ylabel=ylabel, figsize=figsize, extra=extra,
            )
    except Exception as e:
        logger.exception("figure_create render failed")
        return {"status": "error", "message": f"Render failed: {e}"}

    # 6. Optional interactive HTML companion.
    html_path = None
    if interactive or backend == "plotly":
        try:
            html_path = _render_plotly_html(
                kind, rows, dest_html=dest_png.with_suffix(".html"),
                x=x, y=y, z=z, color_by=color_by, title=title,
            )
        except Exception as e:
            logger.debug("plotly interactive render skipped: %s", e)

    # 7. Caption sidecars.
    cap_path, summary_path = _write_caption_sidecars(
        dest_png, caption, plain_english,
    )

    # 8. Provenance sidecar — PROV-O record of how the figure was produced.
    prov_path = None
    try:
        from research_os.tools.actions.state.provenance import (
            write_output_provenance,
        )

        prov_path = write_output_provenance(
            output_path=dest_png,
            root=root,
            produced_by={
                "tool": "tool_figure_create",
                "kind": kind,
                "backend": rendered_with,
                "style": style_meta.get("applied"),
            },
            inputs=(
                {"data_file": data}
                if isinstance(data, str)
                else {"data": "inline"}
            ),
            params={
                "x": x, "y": y, "z": z, "error": error, "color_by": color_by,
                "bins": bins, "regression": regression,
                "palette": palette, "style": style,
                "title": title, "xlabel": xlabel, "ylabel": ylabel,
                "figsize": list(figsize),
                "extra": extra or {},
            },
            rng_seed=None,
            step_id=step_id,
            extra={
                "axes": {
                    "x": {"label": xlabel or x, "kind": kind},
                    "y": {"label": ylabel or y, "kind": kind},
                },
                "n_observations": len(rows),
                "has_error_bars": bool(error) or (
                    kind == "scatter" and regression
                ),
            },
        )
    except Exception as e:
        logger.debug("provenance sidecar skipped: %s", e)

    return {
        "status": "success",
        "figure_png": str(dest_png.relative_to(root)),
        "figure_svg": str(dest_svg.relative_to(root)) if dest_svg.exists() else None,
        "figure_html": str(html_path.relative_to(root)) if html_path else None,
        "caption_path": str(cap_path.relative_to(root)),
        "summary_path": str(summary_path.relative_to(root)) if summary_path else None,
        "provenance_path": (
            str(prov_path.relative_to(root)) if prov_path else None
        ),
        "kind": kind,
        "palette": palette,
        "style": style_meta,
        "rendered_with": rendered_with,
        "rows": len(rows),
        "step_id": step_id,
        "advice": (
            "Pair the figure with a caption that LEADS with the substantive "
            "finding. Call tool_figure_caption_synthesise to produce a plain-"
            "English summary for non-expert readers."
            if not plain_english
            else "Plain-English summary written alongside the technical caption."
        ),
    }


def _render_matplotlib(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    dest_png: Path,
    dest_svg: Path,
    x: str | None,
    y: str | None,
    z: str | None,
    error: str | None,
    color_by: str | None,
    bins: int,
    regression: bool,
    palette_colors: list[str],
    palette_kind: str,
    title: str,
    xlabel: str,
    ylabel: str,
    figsize: tuple[float, float],
    extra: dict[str, Any] | None,
) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    fig, ax = plt.subplots(figsize=figsize)

    if kind in {"bar", "barh"}:
        if not (x and y):
            raise ValueError("bar chart requires both `x` and `y` columns")
        _render_bar(ax, rows, x=x, y=y, error=error,
                    palette=palette_colors, horizontal=(kind == "barh"))
    elif kind == "line":
        if not (x and y):
            raise ValueError("line chart requires both `x` and `y` columns")
        _render_line(ax, rows, x=x, y=y, color_by=color_by, error=error,
                     palette=palette_colors)
    elif kind == "scatter":
        if not (x and y):
            raise ValueError("scatter requires both `x` and `y` columns")
        _render_scatter(ax, rows, x=x, y=y, color_by=color_by,
                        regression=regression, palette=palette_colors)
    elif kind == "hist":
        if not x:
            raise ValueError("hist requires an `x` column")
        _render_hist(ax, rows, x=x, bins=bins, palette=palette_colors,
                     kde=(extra or {}).get("kde", True))
    elif kind in {"box", "violin"}:
        if not (x and y):
            raise ValueError(f"{kind} requires both `x` and `y` columns")
        _render_box(ax, rows, x=x, y=y, palette=palette_colors,
                    violin=(kind == "violin"))
    elif kind == "heatmap":
        if not (x and y and z):
            raise ValueError("heatmap requires `x`, `y`, and `z` columns")
        _render_heatmap(ax, rows, x=x, y=y, z=z, palette_kind=palette_kind)
    elif kind == "forest":
        label_col = (extra or {}).get("label_col", "label")
        effect_col = (extra or {}).get("effect_col", "effect")
        ci_lo_col = (extra or {}).get("ci_lo_col", "ci_lo")
        ci_hi_col = (extra or {}).get("ci_hi_col", "ci_hi")
        null_at = (extra or {}).get("null_at", 0.0)
        _render_forest(ax, rows, label_col=label_col, effect_col=effect_col,
                       ci_lo_col=ci_lo_col, ci_hi_col=ci_hi_col,
                       null_at=null_at)
    elif kind == "roc":
        if not (x and y):
            raise ValueError("roc requires y_true=`x` and y_score=`y` cols")
        _render_roc(ax, rows, y_true=x, y_score=y,
                    color_by=color_by, palette=palette_colors)
    elif kind == "pr":
        if not (x and y):
            raise ValueError("pr requires y_true=`x` and y_score=`y` cols")
        _render_pr(ax, rows, y_true=x, y_score=y,
                   color_by=color_by, palette=palette_colors)
    elif kind == "calibration":
        if not (x and y):
            raise ValueError("calibration requires y_true=`x` and y_score=`y` cols")
        n_bins = (extra or {}).get("n_bins", 10)
        _render_calibration(ax, rows, y_true=x, y_score=y,
                            palette=palette_colors, n_bins=n_bins)
    elif kind == "qq":
        if not x:
            raise ValueError("qq requires `x` column")
        _render_qq(ax, rows, x=x, palette=palette_colors)
    elif kind == "residual_diagnostics":
        residual = (extra or {}).get("residual_col") or x
        fitted   = (extra or {}).get("fitted_col") or y
        if not (residual and fitted):
            raise ValueError(
                "residual_diagnostics requires residual_col + fitted_col "
                "(or x = residual, y = fitted)"
            )
        _render_residual_diagnostics(fig, rows, residual=residual,
                                      fitted=fitted, palette=palette_colors)
    elif kind == "dot_whisker":
        label_col = (extra or {}).get("label_col", "label")
        effect_col = (extra or {}).get("effect_col", "effect")
        ci_lo_col = (extra or {}).get("ci_lo_col", "ci_lo")
        ci_hi_col = (extra or {}).get("ci_hi_col", "ci_hi")
        null_at = (extra or {}).get("null_at", 0.0)
        _render_dot_whisker(ax, rows, label_col=label_col, effect_col=effect_col,
                            ci_lo_col=ci_lo_col, ci_hi_col=ci_hi_col,
                            palette=palette_colors, null_at=null_at,
                            color_by=color_by)
    elif kind == "ridgeline":
        if not (x and y):
            raise ValueError("ridgeline requires group=`x` and value=`y`")
        _render_ridgeline(ax, rows, group=x, value=y, palette=palette_colors)
    elif kind == "raincloud":
        if not (x and y):
            raise ValueError("raincloud requires group=`x` and value=`y`")
        _render_raincloud(ax, rows, group=x, value=y, palette=palette_colors)
    elif kind == "hexbin":
        if not (x and y):
            raise ValueError("hexbin requires `x` and `y` columns")
        gs = (extra or {}).get("gridsize", 30)
        _render_hexbin(ax, rows, x=x, y=y, gridsize=gs,
                       palette_kind=palette_kind)
    elif kind == "slope":
        label_col = (extra or {}).get("label_col", "label")
        before_col = (extra or {}).get("before_col") or x
        after_col  = (extra or {}).get("after_col")  or y
        if not (before_col and after_col):
            raise ValueError("slope requires before_col and after_col")
        _render_slope(ax, rows, label_col=label_col,
                      before_col=before_col, after_col=after_col,
                      palette=palette_colors)
    elif kind == "posterior":
        if not x:
            raise ValueError("posterior requires `x` (the posterior sample column)")
        rope = (extra or {}).get("rope")
        _render_posterior(ax, rows, x=x, palette=palette_colors,
                          rope=tuple(rope) if rope else None)
    elif kind == "var_importance":
        label_col = (extra or {}).get("label_col", "feature")
        imp_col   = (extra or {}).get("importance_col") or y or "importance"
        err_col   = (extra or {}).get("error_col") or error
        _render_var_importance(ax, rows, label_col=label_col,
                               importance_col=imp_col, palette=palette_colors,
                               error=err_col)
    elif kind == "funnel":
        effect_col = (extra or {}).get("effect_col") or x or "effect"
        se_col     = (extra or {}).get("se_col") or y or "se"
        _render_funnel(ax, rows, effect_col=effect_col, se_col=se_col,
                       palette=palette_colors)
    elif kind == "alluvial":
        if not (x and y):
            raise ValueError("alluvial requires source=`x` and target=`y`")
        val_col = (extra or {}).get("value_col")
        _render_alluvial(ax, rows, source=x, target=y,
                         value=val_col, palette=palette_colors)
    elif kind == "hierarchical_heatmap":
        if not (x and y and z):
            raise ValueError("hierarchical_heatmap requires x, y, z")
        _render_hierarchical_heatmap(ax, rows, x=x, y=y, z=z,
                                      palette_kind=palette_kind)
    elif kind == "partial_dependence":
        if not (x and y):
            raise ValueError("partial_dependence requires x + y")
        _render_partial_dependence(ax, rows, x=x, y=y,
                                    color_by=color_by, palette=palette_colors)
    elif kind == "consort_flow":
        _render_consort_flow(fig, rows, palette=palette_colors)

    if title:
        ax.set_title(title, pad=8)
    if xlabel:
        ax.set_xlabel(xlabel)
    elif x:
        ax.set_xlabel(x)
    if ylabel:
        ax.set_ylabel(ylabel)
    elif y:
        ax.set_ylabel(y)

    # v1.3.0: chart-kind-aware spine + grid cleanup. The default
    # rcParams turn the grid on for every chart; that reads as noisy
    # ggplot-grade output on scatter / forest / dot_whisker / slope /
    # raincloud where gridlines compete with the marks themselves.
    # Categorical + distribution charts keep a light grid because it
    # helps the eye land on a value.
    _grid_off_kinds = {
        "scatter", "forest", "dot_whisker", "raincloud", "slope",
        "alluvial", "consort_flow", "funnel", "calibration",
    }
    if kind in _grid_off_kinds:
        ax.grid(False)
    else:
        ax.yaxis.grid(True, color="#E5E7EB", linewidth=0.5, alpha=0.8)
        ax.xaxis.grid(False)

    # Inline sample-size annotation. Researchers want to see n at a
    # glance. v1.3.0: lighter footprint — no box, just light grey text.
    n_annotation = f"n = {len(rows)}"
    ax.text(0.99, 0.02, n_annotation,
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#9ca3af")

    plt.tight_layout()
    fig.savefig(dest_png, dpi=300, bbox_inches="tight", facecolor="white")
    try:
        fig.savefig(dest_svg, format="svg", bbox_inches="tight",
                    facecolor="white")
    except Exception:
        pass
    plt.close(fig)


def _render_plotnine(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    dest_png: Path,
    x: str | None,
    y: str | None,
    color_by: str | None,
    palette: list[str],
    title: str,
    xlabel: str,
    ylabel: str,
    figsize: tuple[float, float],
) -> bool:
    """Optional plotnine path — returns False if plotnine isn't installed."""
    try:
        import pandas as pd  # type: ignore
        from plotnine import (  # type: ignore
            aes,
            ggplot,
            geom_bar,
            geom_line,
            geom_point,
            labs,
            scale_color_manual,
            theme,
            theme_minimal,
        )
    except ImportError:
        return False

    df = pd.DataFrame(rows)
    if not (x and y):
        return False
    aesthetic = aes(x=x, y=y, color=color_by) if color_by else aes(x=x, y=y)
    p = ggplot(df, aesthetic)

    if kind in {"bar", "barh"}:
        p = p + geom_bar(stat="identity")
    elif kind == "line":
        p = p + geom_line(size=1.0) + geom_point(size=2.0)
    elif kind == "scatter":
        p = p + geom_point(alpha=0.7, size=2.4)
    else:
        return False  # fall back to matplotlib for other kinds

    p = p + theme_minimal() + theme(figure_size=figsize) + labs(
        title=title or "",
        x=xlabel or x,
        y=ylabel or y,
    )
    if color_by:
        n_groups = df[color_by].nunique() if color_by in df.columns else 1
        p = p + scale_color_manual(values=palette[: max(2, n_groups)])

    p.save(str(dest_png), dpi=300, verbose=False)
    return True


def _render_plotly_html(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    dest_html: Path,
    x: str | None,
    y: str | None,
    z: str | None,
    color_by: str | None,
    title: str,
) -> Path | None:
    """Optional interactive companion via plotly.express."""
    try:
        import pandas as pd  # type: ignore
        import plotly.express as px  # type: ignore
    except ImportError:
        return None

    if not (x and y):
        return None
    df = pd.DataFrame(rows)
    fn = {
        "bar": px.bar,
        "barh": px.bar,
        "line": px.line,
        "scatter": px.scatter,
        "hist": px.histogram,
        "box": px.box,
        "violin": px.violin,
        "heatmap": px.imshow,
    }.get(kind, px.scatter)
    if fn is px.imshow and z:
        fig = px.imshow(
            df.pivot_table(index=y, columns=x, values=z).values,
            title=title,
        )
    else:
        kwargs: dict[str, Any] = {"x": x, "y": y, "title": title}
        if color_by:
            kwargs["color"] = color_by
        fig = fn(df, **kwargs)
    dest_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(dest_html), include_plotlyjs="cdn", full_html=True)
    return dest_html


# ---------------------------------------------------------------------------
# Plain-English caption synthesiser.
# ---------------------------------------------------------------------------


def caption_synthesise(
    *,
    figure_path: str,
    root: Path,
    technical_caption: str | None = None,
    findings_context: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate a 2-3 sentence plain-language ``.summary.md`` next to a figure.

    The summary follows the W3C two-part guidance: a short alt-text-style
    opener ("Bar chart of …") and a 1-2 sentence description of the
    structure / trend / takeaway. It is **deliberately heuristic** — the
    LLM in the IDE produces the polished version; this function provides
    a competent starting point derived from the figure name, filename
    pattern, and (when supplied) the step's Findings text.

    Parameters
    ----------
    figure_path:
        Path relative to project root, e.g.
        ``workspace/03_logistic_baseline/outputs/figures/03_calibration.png``.
    technical_caption:
        The figure's existing technical caption. If absent, read from the
        ``<name>.caption.md`` sidecar.
    findings_context:
        Optional bullet text from the step's ``conclusions.md`` Findings
        section to ground the summary in the substantive result.
    overwrite:
        If false (default), leaves any existing ``.summary.md`` untouched.
    """
    p = root / figure_path
    if not p.exists():
        return {"status": "error", "message": f"Figure not found: {figure_path}"}

    summary_path = p.with_suffix(".summary.md")
    if summary_path.exists() and not overwrite:
        return {
            "status": "success",
            "summary_path": str(summary_path.relative_to(root)),
            "already_exists": True,
            "advice": "Pass overwrite=true to replace the existing summary.",
        }

    cap_path = p.with_suffix(".caption.md")
    caption = technical_caption or (
        cap_path.read_text().strip() if cap_path.exists() else ""
    )

    # Infer chart family from filename, e.g. "03_calibration_curve.png".
    name = p.stem
    descriptor = name.split("_", 1)[1] if "_" in name else name
    descriptor_phrase = descriptor.replace("_", " ")

    # Read sibling Findings if available + not provided.
    if findings_context is None:
        step_dir = p.parent.parent.parent  # outputs/figures → outputs → step
        conc = step_dir / "conclusions.md"
        if conc.exists():
            txt = conc.read_text()
            import re

            m = re.search(r"##\s*Findings\s*\n(.+?)(?:\n##|\Z)",
                          txt, flags=re.DOTALL | re.IGNORECASE)
            if m:
                findings_context = m.group(1).strip()

    parts: list[str] = []
    parts.append(
        f"**What it shows.** This figure presents the {descriptor_phrase} "
        f"for the analytical step `{p.parent.parent.parent.name}`."
    )
    if caption:
        # Trim the caption to one sentence for the "how to read" cue.
        first_sentence = caption.split(". ")[0].strip().rstrip(".") + "."
        parts.append(f"**How to read it.** {first_sentence}")
    if findings_context:
        bullets = [
            ln.strip().lstrip("-* ").strip()
            for ln in findings_context.splitlines()
            if ln.strip().startswith(("-", "*"))
        ]
        if bullets:
            parts.append(
                "**Why it matters.** " + bullets[0].rstrip(".") + "."
            )
    if len(parts) == 1:
        # No caption and no findings — emit an honest placeholder so the
        # researcher knows a real summary is still needed.
        parts.append(
            "**How to read it.** _Plain-language description pending — "
            "add a 1-2 sentence cue here so non-expert readers can follow "
            "the figure without statistical training._"
        )

    summary_path.write_text("\n\n".join(parts) + "\n")
    return {
        "status": "success",
        "summary_path": str(summary_path.relative_to(root)),
        "characters": sum(len(s) for s in parts),
        "used_findings": bool(findings_context),
        "used_caption": bool(caption),
    }


# ---------------------------------------------------------------------------
# Quality audit — extends the existing DPI check.
# ---------------------------------------------------------------------------


def audit_figure_quality(
    figure_path: str, root: Path,
) -> dict[str, Any]:
    """Deeper figure audit. Checks DPI, dimensions, accessibility,
    sidecar presence, and basic accessibility metadata.

    Complements ``tool_audit_figure`` (DPI / size only) — this one flags:

    * Missing ``<name>.caption.md`` sidecar.
    * Missing ``<name>.summary.md`` (plain-English) sidecar.
    * PNG without an accompanying SVG (limits later editability).
    * Aspect ratio close to 1:1 when the file name suggests a time series
      (line / trend → wider aspect recommended).
    """
    p = root / figure_path
    if not p.exists():
        return {"status": "error", "message": f"Figure not found: {figure_path}"}

    warnings: list[str] = []
    blockers: list[str] = []
    report: dict[str, Any] = {"path": figure_path}

    try:
        from PIL import Image  # type: ignore

        with Image.open(p) as img:
            dpi = img.info.get("dpi", (72, 72))
            w, h = img.size
            report.update({
                "format": img.format,
                "size_px": [w, h],
                "dpi": list(dpi) if isinstance(dpi, tuple) else dpi,
            })
            if isinstance(dpi, tuple) and dpi[0] < 200:
                blockers.append(f"DPI {dpi[0]} below the 200 publication floor.")
            elif isinstance(dpi, tuple) and dpi[0] < 300:
                warnings.append(
                    f"DPI {dpi[0]} acceptable for screen; aim for ≥300 for print."
                )
            if min(w, h) < 600:
                warnings.append(
                    f"Smallest dimension {min(w, h)}px small for paper inclusion."
                )
            aspect = w / max(h, 1)
            if "trend" in p.stem.lower() or "time" in p.stem.lower():
                if 0.85 <= aspect <= 1.15:
                    warnings.append(
                        "Aspect ratio near 1:1 — time-series plots read better "
                        "at a wider ratio (e.g. 16:9)."
                    )
    except ImportError:
        warnings.append(
            "Pillow not installed; install with `pip install Pillow` for DPI checks."
        )

    cap = p.with_suffix(".caption.md")
    summary = p.with_suffix(".summary.md")
    if not cap.exists():
        blockers.append(
            f"Missing technical caption — write `{cap.name}` next to the figure."
        )
    if not summary.exists():
        warnings.append(
            f"Missing plain-English summary — call tool_figure_caption_synthesise "
            f"or write `{summary.name}` directly."
        )
    svg_sibling = p.with_suffix(".svg")
    if p.suffix.lower() == ".png" and not svg_sibling.exists():
        warnings.append(
            "PNG without SVG companion — editorial edits will be harder later."
        )

    report["caption_present"] = cap.exists()
    report["summary_present"] = summary.exists()
    report["svg_present"] = svg_sibling.exists()

    if blockers:
        status = "error"
        message = (
            f"{len(blockers)} blocker(s): "
            + "; ".join(blockers)
        )
    elif warnings:
        status = "warning"
        message = f"{len(warnings)} warning(s)."
    else:
        status = "success"
        message = "Figure passes the publication quality bar."

    return {
        "status": status,
        "message": message,
        "blockers": blockers,
        "warnings": warnings,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Convenience: figure inventory for a step (used by the audit gate).
# ---------------------------------------------------------------------------


def step_figure_inventory(step_id: str, root: Path) -> dict[str, Any]:
    """Inventory every figure for ``step_id``, classifying caption + summary
    presence so the audit gate can BLOCK on missing material."""
    step_dir = root / "workspace" / step_id
    figures_dir = step_dir / "outputs" / "figures"
    if not figures_dir.exists():
        return {
            "status": "warning",
            "step_id": step_id,
            "figures": [],
            "missing_focal_figure": True,
            "missing_captions": [],
            "missing_summaries": [],
        }
    out: list[dict[str, Any]] = []
    missing_caps: list[str] = []
    missing_sums: list[str] = []
    for f in sorted(figures_dir.iterdir()):
        if f.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
            continue
        cap = f.with_suffix(".caption.md")
        sum_ = f.with_suffix(".summary.md")
        if not cap.exists():
            missing_caps.append(f.name)
        if not sum_.exists():
            missing_sums.append(f.name)
        out.append({
            "name": f.name,
            "caption_present": cap.exists(),
            "summary_present": sum_.exists(),
        })

    missing_focal = not any(
        f["name"].startswith(step_id.split("_", 1)[0] + "_") for f in out
    ) if out else True
    return {
        "status": "success" if (out and not missing_focal) else "warning",
        "step_id": step_id,
        "figures": out,
        "missing_focal_figure": missing_focal or not out,
        "missing_captions": missing_caps,
        "missing_summaries": missing_sums,
    }


# Backwards-compatible aliases (kept short so server wiring is light).
__all__ = [
    "OKABE_ITO",
    "audit_figure_quality",
    "caption_synthesise",
    "figure_create",
    "palette_for",
    "step_figure_inventory",
]
