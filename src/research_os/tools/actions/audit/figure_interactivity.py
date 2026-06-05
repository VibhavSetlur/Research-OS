"""Per-figure interactive-companion enforcement.

A figure that visualises >200 marks (scatter/volcano/UMAP), >50x50 cell
heatmaps, networks, or long time series IS interactive on the web — a
flat PNG hides the structure. The visualization/interactive_figure_design
protocol documents WHEN to make an interactive companion; this module
turns that guidance into a gate:

* :func:`audit_figure_interactivity` walks ``workspace/<step>/outputs/
  figures/`` and reports BLOCKER (strict) or WARN (normal/light) for
  every figure that should have an HTML companion but doesn't.

* :func:`figure_interactive_autogen` writes a Vega-Lite / vis-network /
  pyvis-fallback companion next to a static figure when the researcher
  hasn't authored one. Tagged via ``<meta name="ro-auto-generated">``
  so the researcher knows they can replace it.

The gate strictness comes from ``state.rigor_signals.resolve_gate_strictness``;
researchers opt out per figure via a ``<!-- ro:interactive-not-applicable,
reason: ... -->`` line in the ``<stem>.caption.md`` sidecar.

The static PNG remains the headline artifact (the paper PDF embeds
the PNG, not the HTML). The companion is what the v2 dashboard wires
into ``<ro-figure-toggle>``.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Naming-pattern → kind. Conservative: we only flag figures we're
# confident benefit from interactivity. A figure named "barchart" with
# no companion data file is not flagged.
_NAME_PATTERNS = (
    (re.compile(r"volcano",  re.I), "scatter"),
    (re.compile(r"\bumap\b", re.I), "scatter"),
    (re.compile(r"\btsne\b", re.I), "scatter"),
    (re.compile(r"scatter", re.I), "scatter"),
    (re.compile(r"heatmap", re.I), "heatmap"),
    (re.compile(r"network", re.I), "network"),
    (re.compile(r"graph",   re.I), "network"),
    (re.compile(r"timeseries|time_series", re.I), "timeseries"),
)

OVERRIDE_PATTERN = re.compile(
    r"<!--\s*ro:interactive-not-applicable(?:\s*,\s*reason:\s*(.+?))?\s*-->",
    re.IGNORECASE,
)


def _detect_kind(fig: Path) -> str:
    """Decide the kind of figure based on naming + companion sidecars.

    Returns one of: ``"scatter"``, ``"heatmap"``, ``"network"``,
    ``"timeseries"``, or ``"other"``.
    """
    stem = fig.stem
    parent = fig.parent
    # Companion-data heuristics dominate naming heuristics so a renamed
    # figure with the right data file still gets caught.
    if (parent / f"{stem}.graphml").exists():
        return "network"
    matrix = parent / f"{stem}_matrix.csv"
    if matrix.exists() and _csv_shape_at_least(matrix, rows=50, cols=50):
        return "heatmap"
    series = parent / f"{stem}_series.csv"
    if series.exists() and _csv_rows(series) > 1000:
        return "timeseries"
    data = parent / f"{stem}_data.csv"
    if data.exists() and _csv_rows(data) > 200:
        return "scatter"
    for pat, kind in _NAME_PATTERNS:
        if pat.search(stem):
            # Naming hit but no data file → still flag (with lower
            # confidence). The autogen path will only fire when a
            # data file IS present, so naming-only matches surface as
            # WARN-not-autogenable.
            return kind
    return "other"


def _csv_rows(p: Path) -> int:
    try:
        with p.open(newline="") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except OSError:
        return 0


def _csv_shape_at_least(p: Path, rows: int, cols: int) -> bool:
    try:
        with p.open(newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                return False
            ncols = len(header)
            if ncols < cols:
                return False
            for i, _ in enumerate(reader, start=1):
                if i >= rows:
                    return True
        return False
    except OSError:
        return False


def _override_reason(caption_md: Path) -> str | None:
    """Return the researcher's not-applicable reason, or None."""
    if not caption_md.exists():
        return None
    try:
        m = OVERRIDE_PATTERN.search(caption_md.read_text())
        if not m:
            return None
        return (m.group(1) or "").strip() or "(no reason given)"
    except OSError:
        return None


def _walk_figures(root: Path):
    """Yield every static figure under workspace/<step>/outputs/figures/."""
    ws = root / "workspace"
    if not ws.is_dir():
        return
    for step in sorted(ws.iterdir()):
        figs = step / "outputs" / "figures"
        if not figs.is_dir():
            continue
        for f in sorted(figs.iterdir()):
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}:
                yield f


def audit_figure_interactivity(root: Path, strictness: str | None = None,
                                autogen: bool | None = None) -> dict[str, Any]:
    """Run the interactivity gate.

    Args:
        root: project root.
        strictness: explicit override (light | normal | strict). When
            None, :func:`resolve_gate_strictness` is consulted.
        autogen: when True, the gate writes auto-generated companions
            for missing flagged figures. When None, autogen=True iff
            strictness == "normal".

    Returns a dict with ``status`` ("success"/"error"), ``blockers``,
    ``warnings``, ``passes``, and ``overrides`` lists. Also writes a
    human-readable ``workspace/logs/figure_interactivity_audit.md``.
    """
    try:
        if strictness is None:
            from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness
            strictness = resolve_gate_strictness(root).get("resolved", "normal")
        if autogen is None:
            autogen = (strictness == "normal")

        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        passes: list[dict[str, Any]] = []
        overrides: list[dict[str, Any]] = []
        autogen_log: list[dict[str, Any]] = []

        for fig in _walk_figures(root):
            stem = fig.stem
            companion = fig.with_suffix(".html")
            kind = _detect_kind(fig)
            cap = fig.with_suffix(".caption.md")
            reason = _override_reason(cap)
            if reason:
                overrides.append({"figure": str(fig.relative_to(root)),
                                  "reason": reason})
                continue
            if kind == "other":
                passes.append({"figure": str(fig.relative_to(root)),
                               "kind": kind, "companion": companion.exists()})
                continue
            if companion.exists():
                passes.append({"figure": str(fig.relative_to(root)),
                               "kind": kind, "companion": True})
                continue
            # Missing companion + flagged kind.
            entry = {
                "figure": str(fig.relative_to(root)),
                "kind": kind,
                "stem": stem,
            }
            if strictness == "strict":
                blockers.append(entry)
                continue
            warnings.append(entry)
            if autogen:
                gen = figure_interactive_autogen(fig, root)
                autogen_log.append({"figure": entry["figure"],
                                    "status": gen.get("status"),
                                    "path": gen.get("path", "")})

        _write_audit_log(root, strictness, blockers, warnings,
                         passes, overrides, autogen_log)

        return {
            "status": "success",
            "strictness": strictness,
            "autogen": autogen,
            "blockers": blockers,
            "warnings": warnings,
            "passes": passes,
            "overrides": overrides,
            "autogen_log": autogen_log,
        }
    except Exception as e:
        logger.exception("audit_figure_interactivity failed")
        return {"status": "error", "message": str(e)}


def _write_audit_log(root: Path, strictness: str,
                     blockers: list[dict[str, Any]],
                     warnings: list[dict[str, Any]],
                     passes: list[dict[str, Any]],
                     overrides: list[dict[str, Any]],
                     autogen_log: list[dict[str, Any]]) -> None:
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# Figure interactivity audit ({strictness})",
        f"_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"Blockers: {len(blockers)} · Warnings: {len(warnings)} · "
        f"Passes: {len(passes)} · Overrides: {len(overrides)}",
        "",
    ]
    if blockers:
        lines.append("## Blockers")
        for b in blockers:
            lines.append(f"- {b['figure']} ({b['kind']}) — no interactive companion")
        lines.append("")
    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w['figure']} ({w['kind']}) — no interactive companion")
        lines.append("")
    if autogen_log:
        lines.append("## Auto-generated companions")
        for a in autogen_log:
            lines.append(f"- {a['figure']} → {a['path']} ({a['status']})")
        lines.append("")
    if overrides:
        lines.append("## Researcher overrides")
        for o in overrides:
            lines.append(f"- {o['figure']} — {o['reason']}")
        lines.append("")
    (logs / "figure_interactivity_audit.md").write_text("\n".join(lines))


# ──────────────────────────────────────────────────────────────────────
# Auto-generation
# ──────────────────────────────────────────────────────────────────────


def figure_interactive_autogen(fig: Path, root: Path) -> dict[str, Any]:
    """Write an interactive companion next to ``fig``.

    The companion file is ``<stem>.html`` and is fully offline-capable:
    Vega-Lite / vis-network are inlined from the vendored bundles
    (rather than fetched from a CDN). If neither a usable data file
    nor a graphml is present, returns ``status="skipped"``.
    """
    try:
        kind = _detect_kind(fig)
        if kind == "other":
            return {"status": "skipped", "reason": "kind=other"}
        stem = fig.stem
        out = fig.with_suffix(".html")
        if out.exists():
            return {"status": "exists", "path": str(out.relative_to(root))}
        if kind == "scatter":
            html = _autogen_scatter_html(fig, stem)
        elif kind == "heatmap":
            html = _autogen_heatmap_html(fig, stem)
        elif kind == "timeseries":
            html = _autogen_timeseries_html(fig, stem)
        elif kind == "network":
            html = _autogen_network_html(fig, stem)
        else:
            return {"status": "skipped", "reason": f"unknown kind {kind}"}
        if not html:
            return {"status": "skipped", "reason": "no data file"}
        out.write_text(html)
        return {"status": "success", "kind": kind,
                "path": str(out.relative_to(root))}
    except Exception as e:
        logger.exception("figure_interactive_autogen failed for %s", fig)
        return {"status": "error", "message": str(e)}


def _vendored(name: str) -> str:
    """Read a vendored JS bundle, raising ImportError if missing.

    Used by autogen so the produced HTML is offline-capable. The
    dashboard renderer itself uses a softer ``_read_bundle`` that
    degrades silently; here we want a clear failure mode because a
    missing bundle means the companion can't actually run.
    """
    p = (Path(__file__).resolve().parents[3] / "assets" / "js" / name)
    if not p.exists():
        raise ImportError(f"vendored JS bundle missing: {name}")
    return p.read_text(encoding="utf-8", errors="ignore")


def _autogen_scatter_html(fig: Path, stem: str) -> str:
    data_csv = fig.parent / f"{stem}_data.csv"
    if not data_csv.exists():
        return ""
    rows = _csv_to_records(data_csv, max_rows=10000)
    if not rows:
        return ""
    cols = list(rows[0].keys())
    x = cols[0]
    y = cols[1] if len(cols) > 1 else cols[0]
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Auto-generated interactive companion for {stem}",
        "data": {"values": rows},
        "mark": {"type": "point", "filled": True, "size": 40},
        "encoding": {
            "x": {"field": x, "type": "quantitative"},
            "y": {"field": y, "type": "quantitative"},
            "tooltip": [{"field": c, "type": _vl_type(rows, c)} for c in cols[:8]],
        },
        "selection": {"brush": {"type": "interval"}},
        "width": 600, "height": 400,
    }
    return _wrap_vega_html(stem, spec)


def _autogen_heatmap_html(fig: Path, stem: str) -> str:
    matrix_csv = fig.parent / f"{stem}_matrix.csv"
    if not matrix_csv.exists():
        return ""
    # Reshape wide matrix → long {row, col, value}
    try:
        with matrix_csv.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            col_names = header[1:]
            long_rows: list[dict[str, Any]] = []
            for raw in reader:
                if not raw:
                    continue
                rname = raw[0]
                for cidx, val in enumerate(raw[1:]):
                    try:
                        v = float(val)
                    except (ValueError, TypeError):
                        continue
                    long_rows.append({"row": rname, "col": col_names[cidx], "value": v})
    except OSError:
        return ""
    if not long_rows:
        return ""
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Auto-generated interactive companion for {stem}",
        "data": {"values": long_rows},
        "mark": "rect",
        "encoding": {
            "x": {"field": "col", "type": "nominal"},
            "y": {"field": "row", "type": "nominal"},
            "color": {"field": "value", "type": "quantitative", "scale": {"scheme": "viridis"}},
            "tooltip": [{"field": "row"}, {"field": "col"}, {"field": "value"}],
        },
        "width": 600, "height": 400,
    }
    return _wrap_vega_html(stem, spec)


def _autogen_timeseries_html(fig: Path, stem: str) -> str:
    series_csv = fig.parent / f"{stem}_series.csv"
    if not series_csv.exists():
        return ""
    rows = _csv_to_records(series_csv, max_rows=50000)
    if not rows:
        return ""
    cols = list(rows[0].keys())
    x = cols[0]
    y = cols[1] if len(cols) > 1 else cols[0]
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Auto-generated interactive companion for {stem}",
        "data": {"values": rows},
        "mark": "line",
        "encoding": {
            "x": {"field": x, "type": "temporal"},
            "y": {"field": y, "type": "quantitative"},
            "tooltip": [{"field": c} for c in cols[:6]],
        },
        "selection": {"brush": {"type": "interval", "encodings": ["x"]}},
        "width": 700, "height": 280,
    }
    return _wrap_vega_html(stem, spec)


def _autogen_network_html(fig: Path, stem: str) -> str:
    gml = fig.parent / f"{stem}.graphml"
    if not gml.exists():
        return ""
    # Parse the graphml into a vis-network nodes+edges list.
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(gml)
        root_el = tree.getroot()
        nodes = [{"id": n.get("id")} for n in root_el.iter("{http://graphml.graphdrawing.org/xmlns}node")]
        edges = [{"from": e.get("source"), "to": e.get("target")}
                 for e in root_el.iter("{http://graphml.graphdrawing.org/xmlns}edge")]
        if not nodes:
            # Try without namespace (some graphml files skip it)
            nodes = [{"id": n.get("id")} for n in root_el.iter("node")]
            edges = [{"from": e.get("source"), "to": e.get("target")}
                     for e in root_el.iter("edge")]
    except (ET.ParseError, FileNotFoundError):
        return ""
    if not nodes:
        return ""
    try:
        vis = _vendored("vis-network.min.js")
    except ImportError:
        return ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='ro-auto-generated' content='true'>"
        f"<title>{stem} (interactive)</title>"
        f"<script>{vis}</script>"
        "<style>html,body,#net{height:100%;margin:0;}</style>"
        "</head><body><div id='net'></div><script>"
        f"const nodes = new vis.DataSet({json.dumps(nodes)});"
        f"const edges = new vis.DataSet({json.dumps(edges)});"
        "new vis.Network(document.getElementById('net'), {nodes, edges}, "
        "{interaction:{hover:true, zoomView:true}});"
        "</script></body></html>"
    )


def _wrap_vega_html(stem: str, spec: dict[str, Any]) -> str:
    try:
        vega = _vendored("vega.min.js")
        vlite = _vendored("vega-lite.min.js")
        embed = _vendored("vega-embed.min.js")
    except ImportError:
        return ""
    spec_json = json.dumps(spec).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='ro-auto-generated' content='true'>"
        f"<title>{stem} (interactive)</title>"
        f"<script>{vega}</script><script>{vlite}</script>"
        f"<script>{embed}</script>"
        "<style>body{font:14px system-ui;margin:16px}</style>"
        f"</head><body><div id='vis'></div><script>"
        f"const spec = {spec_json};"
        "vegaEmbed('#vis', spec, {actions: false});"
        "</script></body></html>"
    )


def _csv_to_records(p: Path, max_rows: int = 10000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with p.open(newline="") as f:
            reader = csv.DictReader(f)
            for i, r in enumerate(reader):
                if i >= max_rows:
                    break
                # Coerce numeric-looking values for nicer Vega-Lite
                # type inference; leave strings alone.
                coerced = {}
                for k, v in r.items():
                    try:
                        coerced[k] = float(v) if v not in ("", None) else None
                    except (TypeError, ValueError):
                        coerced[k] = v
                rows.append(coerced)
    except OSError:
        return []
    return rows


def _vl_type(rows: list[dict[str, Any]], col: str) -> str:
    for r in rows:
        v = r.get(col)
        if v is None:
            continue
        return "quantitative" if isinstance(v, (int, float)) else "nominal"
    return "nominal"


__all__ = [
    "audit_figure_interactivity",
    "figure_interactive_autogen",
]
