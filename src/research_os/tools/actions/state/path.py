"""Experiment-path management.

A *path* is a numbered experiment folder under ``workspace/``. Paths are the
chronological backbone of the project — every meaningful analysis lives in one.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.path")


def create_path(name: str, root: Path, hypothesis: str = "") -> dict[str, Any]:
    """Create the next numbered experiment folder.

    Delegates to :func:`project_ops.create_numbered_experiment` so that state,
    manifest, and mermaid diagram are updated atomically.
    """
    from research_os.project_ops import create_numbered_experiment

    try:
        return {"status": "success", **create_numbered_experiment(root, name, hypothesis=hypothesis)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception("create_path failed")
        return {"status": "error", "message": str(e)}


def abandon_path(path_name: str, rationale: str, root: Path) -> dict[str, Any]:
    """Rename a path to ``<name>__DEAD_END`` and log the rationale."""
    from research_os.project_ops import (
        _update_manifest,
        _update_workflow_mermaid,
        load_state,
        now_iso,
        save_state,
    )

    workspace_dir = root / "workspace"
    target_dir = workspace_dir / path_name
    if not target_dir.exists() or not target_dir.is_dir():
        return {"status": "error", "message": f"Path '{path_name}' not found in workspace/"}
    if not re.match(r"^\d{2}_", path_name):
        return {"status": "error", "message": f"'{path_name}' is not a numbered experiment path"}

    dead_end_name = f"{path_name}__DEAD_END"
    dead_end_dir = workspace_dir / dead_end_name
    if dead_end_dir.exists():
        shutil.rmtree(dead_end_dir, ignore_errors=True)
    target_dir.rename(dead_end_dir)

    analysis_path = root / "workspace" / "analysis.md"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    with open(analysis_path, "a") as f:
        f.write(
            f"\n## Abandoned `{path_name}` ({now_iso()})\n\n"
            f"**Rationale:** {rationale}\n\n"
        )

    state = load_state(root)
    paths = state.setdefault("paths", {})
    if path_name in paths:
        paths[path_name]["status"] = "dead_end"
        paths[path_name]["abandoned_at"] = now_iso()
        paths[path_name]["abandon_rationale"] = rationale
    dead_ends = state.setdefault("dead_ends", [])
    if path_name not in dead_ends:
        dead_ends.append(path_name)
    if state.get("current_path") == path_name:
        # Roll back to most recent active path, or 'main'.
        remaining = [
            p for p, info in paths.items()
            if info.get("status") == "active" and p != path_name
        ]
        state["current_path"] = remaining[-1] if remaining else "main"
    save_state(root, state)

    _update_workflow_mermaid(root)
    _update_manifest(root)
    # Refresh DAG best-effort.
    try:
        workflow_dag(root)
    except Exception:
        pass

    return {
        "status": "success",
        "original_path": path_name,
        "renamed_to": dead_end_name,
        "rationale": rationale,
        "files_preserved": True,
    }


def workflow_dag(
    root: Path,
    *,
    render_png: bool = False,
    output_dir: str = "docs",
) -> dict[str, Any]:
    """Build a dependency DAG of all numbered steps.

    Walks each step's ``data/input`` symlink to derive ancestor edges.
    Writes ``<output_dir>/workflow_dag.mermaid``. If ``render_png=True``
    AND ``mmdc`` (Mermaid CLI) is on PATH, also writes
    ``<output_dir>/workflow_dag.png``.

    A step's status (active | completed | dead_end) decides its node
    colour so the diagram is readable at a glance.
    """
    try:
        import shutil as _shutil
        import subprocess as _subprocess

        workspace_dir = root / "workspace"
        if not workspace_dir.exists():
            return {"status": "error", "message": "workspace/ not found"}

        steps = list_paths(root).get("paths", []) or []
        if not steps:
            return {
                "status": "success",
                "nodes": 0,
                "edges": 0,
                "message": "No numbered steps yet — DAG is empty.",
            }

        # Map path_id → node label (short).
        nodes: dict[str, dict[str, str]] = {}
        for s in steps:
            pid = s["path_id"]
            nodes[pid] = {
                "label": pid.replace("__DEAD_END", "")[:36],
                "status": s["status"],
                "full_id": pid,
            }

        # Derive edges from data/input symlinks: each step's
        # data/input may be a symlink to either inputs/raw_data or
        # another step's data/output.
        edges: list[tuple[str, str]] = []
        for s in steps:
            step_path = Path(s["experiment_dir"])
            data_in = step_path / "data" / "input"
            if not data_in.exists():
                continue
            # Could be a single symlink or a directory of symlinks; check both.
            link_targets: list[Path] = []
            if data_in.is_symlink():
                try:
                    link_targets.append(data_in.resolve())
                except OSError:
                    pass
            elif data_in.is_dir():
                for child in data_in.iterdir():
                    if child.is_symlink():
                        try:
                            link_targets.append(child.resolve())
                        except OSError:
                            pass
            for target in link_targets:
                # If target lives under another step's data/output,
                # add an edge from that step → this step.
                try:
                    rel = target.relative_to(workspace_dir)
                except ValueError:
                    continue
                parts = rel.parts
                if not parts or not re.match(r"^\d{2,3}_", parts[0]):
                    continue
                ancestor = parts[0]
                if ancestor in nodes and ancestor != s["path_id"]:
                    edge = (ancestor, s["path_id"])
                    if edge not in edges:
                        edges.append(edge)

        # Build mermaid.
        out_dir = root / output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        mermaid_lines = [
            "graph TD",
            "    classDef active fill:#fff3cd,stroke:#856404,color:#333",
            "    classDef completed fill:#d4edda,stroke:#28a745,color:#155724",
            "    classDef dead_end fill:#f8d7da,stroke:#dc3545,color:#721c24",
        ]
        # Stable iteration order (numbered).
        for pid in sorted(nodes):
            node = nodes[pid]
            safe_id = re.sub(r"[^A-Za-z0-9_]", "_", pid)
            mermaid_lines.append(
                f'    {safe_id}["{node["label"]}"]:::{node["status"]}'
            )
        if not edges:
            # Show ingest from inputs/raw_data for the first step at least.
            first = sorted(nodes)[0]
            safe_first = re.sub(r"[^A-Za-z0-9_]", "_", first)
            mermaid_lines.append("    raw[\"inputs/raw_data\"]")
            mermaid_lines.append(f"    raw --> {safe_first}")
        else:
            for src, dst in edges:
                src_safe = re.sub(r"[^A-Za-z0-9_]", "_", src)
                dst_safe = re.sub(r"[^A-Za-z0-9_]", "_", dst)
                mermaid_lines.append(f"    {src_safe} --> {dst_safe}")

        mmd_path = out_dir / "workflow_dag.mermaid"
        mmd_path.write_text("\n".join(mermaid_lines) + "\n")

        png_path: str | None = None
        png_renderer = None  # mmdc | matplotlib | None
        if render_png:
            png_target = out_dir / "workflow_dag.png"
            # Prefer mmdc (faithful mermaid rendering); fall back to a
            # matplotlib PNG so a PNG is ALWAYS available regardless of npm.
            if _shutil.which("mmdc"):
                try:
                    res = _subprocess.run(
                        ["mmdc", "-i", str(mmd_path), "-o", str(png_target),
                         "-b", "transparent"],
                        capture_output=True, text=True, timeout=30,
                    )
                    if res.returncode == 0:
                        png_path = str(png_target.relative_to(root))
                        png_renderer = "mmdc"
                except (OSError, _subprocess.TimeoutExpired):
                    pass
            if not png_path:
                try:
                    step_meta = _collect_step_metadata(workspace_dir, root)
                    _render_workflow_png_matplotlib(
                        nodes, edges, png_target, step_meta=step_meta,
                    )
                    png_path = str(png_target.relative_to(root))
                    png_renderer = "matplotlib"
                except Exception as e:
                    logger.warning("matplotlib workflow render failed: %s", e)

        # Also copy a publishable PNG into synthesis/figures so the dashboard
        # picks it up as the workflow figure without extra wiring.
        if png_path:
            try:
                syn_fig = root / "synthesis" / "figures"
                syn_fig.mkdir(parents=True, exist_ok=True)
                target = syn_fig / "fig00_workflow_diagram.png"
                src = root / png_path
                if not target.exists() or target.stat().st_mtime < src.stat().st_mtime:
                    _shutil.copy2(src, target)
                cap = target.with_suffix(".caption.md")
                if not cap.exists():
                    cap.write_text(
                        "**Analytical workflow.** Each box is one numbered "
                        "analysis step. The header bar summarises overall "
                        "progress; arrows show data-dependency between "
                        "steps. Each box surfaces the hypotheses the step "
                        "touched (H-prefix), figure/table counts, and the "
                        "step's headline finding so the diagram doubles as "
                        "a project-at-a-glance summary. Colour encodes "
                        "status (green = completed, amber = active, red = "
                        "dead-end, preserved). Steps with no inbound arrows "
                        "read from the project inputs directly. The ★ marker "
                        "indicates a focal figure named after the step "
                        "number; ⚠ flags an outstanding artefact.\n"
                    )
                # Also write a plain-English summary sibling for the dashboard.
                sumf = target.with_suffix(".summary.md")
                if not sumf.exists():
                    sumf.write_text(
                        "**What it shows.** The full path of the analysis: "
                        "every numbered step, what depends on what, and how "
                        "far along each one is.\n\n"
                        "**How to read it.** Start at the top, follow the "
                        "arrows. Green = done. Amber = in progress. Red = "
                        "abandoned but kept on the record. Each box lists "
                        "the hypotheses that step tested and its headline "
                        "result.\n\n"
                        "**Why it matters.** Lets a reader trust that the "
                        "conclusion didn't appear out of nowhere — every "
                        "step is traceable to its inputs and to the next "
                        "step that consumed its output.\n"
                    )
            except Exception as e:
                logger.debug("workflow figure copy to synthesis/figures failed: %s", e)

        return {
            "status": "success",
            "mermaid_path": str(mmd_path.relative_to(root)),
            "png_path": png_path,
            "png_renderer": png_renderer,
            "nodes": len(nodes),
            "edges": len(edges),
            "has_mmdc": bool(_shutil.which("mmdc")),
            "advice": (
                "PNG rendered via matplotlib. For a mermaid-faithful render, "
                "install mmdc with `npm install -g @mermaid-js/mermaid-cli`."
                if png_renderer == "matplotlib"
                else "PNG rendered via mmdc."
                if png_renderer == "mmdc"
                else (
                    "PNG not produced. Install either matplotlib "
                    "(`pip install matplotlib`) for an in-Python render OR "
                    "mmdc (`npm install -g @mermaid-js/mermaid-cli`) for the "
                    "faithful mermaid render, then re-run with render_png=true."
                )
            ),
        }
    except Exception as e:
        logger.exception("workflow_dag failed")
        return {"status": "error", "message": str(e)}


def _collect_step_metadata(workspace: Path, root: Path) -> dict[str, dict[str, Any]]:
    """For every numbered step, harvest the hypotheses it touched and a
    one-line headline finding (so the diagram can show H-badges + the
    actual result, not just a slug)."""
    meta: dict[str, dict[str, Any]] = {}
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        hyps = state.get("active_hypotheses") or []
        # step → set of H-IDs (from each hypothesis's evidence list)
        step_to_hyps: dict[str, set[str]] = {}
        for h in hyps:
            hid = h.get("id", "?")
            for ev in (h.get("evidence") or []):
                sid = ev.get("step")
                if sid:
                    step_to_hyps.setdefault(sid, set()).add(hid)
        # statement per hypothesis (for tooltips later)
        h_statements = {h.get("id"): (h.get("statement") or "")[:80] for h in hyps}
    except Exception:
        step_to_hyps = {}
        h_statements = {}

    for p in workspace.iterdir():
        if not (p.is_dir() and re.match(r"^\d{2,3}_", p.name)):
            continue
        info: dict[str, Any] = {
            "hypotheses": sorted(step_to_hyps.get(p.name, set())),
            "h_statements": h_statements,
            "headline": "",
            "has_focal_figure": False,
            "n_figures": 0,
            "n_tables": 0,
        }
        # Headline from conclusions.md Findings.
        conc = p / "conclusions.md"
        if conc.exists():
            try:
                txt = conc.read_text()
                m = re.search(
                    r"##\s*Findings\s*\n(.+?)(?:\n##|\Z)",
                    txt, flags=re.DOTALL | re.IGNORECASE,
                )
                if m:
                    for line in m.group(1).splitlines():
                        line = line.strip()
                        if line.startswith(("-", "*")):
                            info["headline"] = line.lstrip("-* ").strip()[:100]
                            break
            except Exception:
                pass
        figs_dir = p / "outputs" / "figures"
        if figs_dir.exists():
            num = p.name.split("_", 1)[0]
            figures = [
                f for f in figs_dir.iterdir()
                if f.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
            ]
            info["n_figures"] = len(figures)
            info["has_focal_figure"] = any(
                f.name.startswith(f"{num}_") for f in figures
            )
        tables_dir = p / "outputs" / "tables"
        if tables_dir.exists():
            info["n_tables"] = sum(
                1 for f in tables_dir.iterdir() if f.is_file()
                and f.suffix.lower() in {".csv", ".tsv", ".md"}
            )
        meta[p.name] = info
    return meta


def _render_workflow_png_matplotlib(
    nodes: dict[str, dict[str, str]],
    edges: list[tuple[str, str]],
    target: Path,
    *,
    step_meta: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Render the workflow DAG as a polished PNG using matplotlib only.

    Layout: numbered steps stack top-to-bottom along the chronological
    axis; each step is a rounded box coloured by status. Edges are drawn
    as arrows connecting boxes. Includes hypothesis badges per node, a
    small "missing focal figure" annotation, a chronological timeline
    bar at the top, and a legend.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    step_meta = step_meta or {}
    ordered_ids = sorted(nodes.keys())
    n = len(ordered_ids)
    if n == 0:
        return

    # Map node -> (col, row). Default everything in column 0; if two siblings
    # share a parent we split them into columns to avoid line crossings.
    parent_of: dict[str, str | None] = {p: None for p in ordered_ids}
    children: dict[str, list[str]] = {p: [] for p in ordered_ids}
    for src, dst in edges:
        if src in parent_of and dst in parent_of:
            parent_of[dst] = src
            children[src].append(dst)

    # Topological row assignment based on depth.
    depth: dict[str, int] = {}
    for pid in ordered_ids:
        d = 0
        cursor = pid
        while parent_of.get(cursor):
            cursor = parent_of[cursor]
            d += 1
            if d > 50:
                break
        depth[pid] = d
    max_depth = max(depth.values()) if depth else 0

    # Column assignment: siblings spread horizontally.
    col: dict[str, int] = {pid: 0 for pid in ordered_ids}
    for parent, kids in children.items():
        if len(kids) <= 1:
            continue
        kids_sorted = sorted(kids)
        for i, kid in enumerate(kids_sorted):
            col[kid] = i - (len(kids_sorted) - 1) / 2
        for kid in kids_sorted:
            stack = list(children.get(kid, []))
            base = col[kid]
            while stack:
                cur = stack.pop()
                col[cur] = base
                stack.extend(children.get(cur, []))

    max_col = max(col.values(), default=0)
    min_col = min(col.values(), default=0)
    width_cols = max(2, (max_col - min_col) + 1)

    # A taller box accommodates the H-badge + headline annotation.
    box_w, box_h = 3.2, 1.10
    fig_w = max(9.5, width_cols * 3.6)
    fig_h = max(5.5, (max_depth + 1) * 1.9 + 2.5)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-0.5, width_cols + 0.5)
    ax.set_ylim(-1.3, max_depth + 2.3)
    ax.invert_yaxis()
    ax.axis("off")

    status_colors = {
        "completed": ("#d4edda", "#1a7f37"),
        "active":    ("#fff3cd", "#856404"),
        "dead_end":  ("#f8d7da", "#9b2c2c"),
        "missing_on_disk": ("#edf2f7", "#718096"),
    }

    # ----- Timeline bar at the very top -----
    n_steps_done = sum(
        1 for pid in ordered_ids if nodes[pid]["status"] == "completed"
    )
    n_steps_active = sum(
        1 for pid in ordered_ids if nodes[pid]["status"] == "active"
    )
    n_steps_dead = sum(
        1 for pid in ordered_ids if nodes[pid]["status"] == "dead_end"
    )
    bar_y = -1.0
    bar_w = width_cols
    bar_h = 0.25
    # Background track.
    ax.add_patch(Rectangle((0, bar_y), bar_w, bar_h,
                           facecolor="#edf2f7", edgecolor="#cbd5e1", lw=0.8))
    # Completed slice.
    if n > 0:
        done_w = bar_w * (n_steps_done / n)
        active_w = bar_w * (n_steps_active / n)
        ax.add_patch(Rectangle((0, bar_y), done_w, bar_h,
                               facecolor="#1a7f37", edgecolor="none"))
        ax.add_patch(Rectangle((done_w, bar_y), active_w, bar_h,
                               facecolor="#d29922", edgecolor="none"))
    ax.text(
        bar_w / 2, bar_y - 0.15,
        f"Progress: {n_steps_done} completed · {n_steps_active} active · "
        f"{n_steps_dead} dead-end · {n} total",
        ha="center", va="bottom",
        fontsize=9.5, color="#4a5568",
    )

    coords: dict[str, tuple[float, float]] = {}
    for pid in ordered_ids:
        x = col[pid] - min_col + (width_cols - 1 - (max_col - min_col)) / 2.0
        y = depth[pid]
        coords[pid] = (x, y)
        fg = status_colors.get(nodes[pid]["status"], status_colors["completed"])
        ax.add_patch(FancyBboxPatch(
            (x - box_w / 2, y - box_h / 2), box_w, box_h,
            boxstyle="round,pad=0.06,rounding_size=0.18",
            facecolor=fg[0], edgecolor=fg[1], linewidth=1.4,
        ))

        # Step label (top line of the box).
        label = nodes[pid]["label"]
        ax.text(x, y - box_h / 2 + 0.22, label,
                ha="center", va="center",
                fontsize=10.5, fontweight="semibold", color="#1a202c")

        # Hypothesis badges + figure/table counts (middle line).
        meta = step_meta.get(pid, {})
        badges: list[str] = []
        for hid in meta.get("hypotheses", []):
            badges.append(hid)
        meta_line_parts = []
        if badges:
            meta_line_parts.append("H: " + ", ".join(badges))
        if meta.get("n_figures"):
            mark = "★" if meta.get("has_focal_figure") else "•"
            meta_line_parts.append(f"{mark} {meta['n_figures']} fig")
        if meta.get("n_tables"):
            meta_line_parts.append(f"⊞ {meta['n_tables']} tab")
        if meta_line_parts:
            ax.text(x, y, " · ".join(meta_line_parts),
                    ha="center", va="center",
                    fontsize=8.5, color="#4a5568")

        # Headline finding (bottom line, italic).
        headline = meta.get("headline", "")
        if headline:
            # Truncate to fit the box width.
            max_chars = 42
            if len(headline) > max_chars:
                headline = headline[:max_chars - 1] + "…"
            ax.text(x, y + box_h / 2 - 0.22, headline,
                    ha="center", va="center",
                    fontsize=8.0, fontstyle="italic", color="#2d3748")
        elif not meta.get("has_focal_figure") and nodes[pid]["status"] != "dead_end":
            ax.text(x, y + box_h / 2 - 0.22,
                    "⚠ no focal figure yet",
                    ha="center", va="center",
                    fontsize=8.0, fontstyle="italic", color="#9b2c2c")

    for src, dst in edges:
        if src not in coords or dst not in coords:
            continue
        x1, y1 = coords[src]
        x2, y2 = coords[dst]
        ax.annotate(
            "", xy=(x2, y2 - box_h / 2), xytext=(x1, y1 + box_h / 2),
            arrowprops=dict(arrowstyle="-|>", color="#3a4661",
                            lw=1.6, shrinkA=2, shrinkB=2,
                            connectionstyle="arc3,rad=0.05"),
        )

    # ----- Legend -----
    legend_y = max_depth + 1.5
    legend_items = [
        ("completed", "Completed"),
        ("active", "Active"),
        ("dead_end", "Dead-end (preserved)"),
    ]
    for i, (key, label) in enumerate(legend_items):
        bg, bd = status_colors[key]
        lx = -0.2 + i * 2.5
        ax.add_patch(FancyBboxPatch(
            (lx, legend_y), 0.45, 0.32,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=bg, edgecolor=bd, linewidth=1.0,
        ))
        ax.text(lx + 0.55, legend_y + 0.16, label,
                fontsize=9.0, va="center", color="#3a4661")
    # Inline legend key for badges.
    ax.text(0, legend_y + 0.7,
            "★ focal figure · H: hypothesis touched · ⚠ outstanding artefact",
            fontsize=8.5, color="#4a5568")

    ax.set_title("Analytical workflow", fontsize=14,
                 fontweight="bold", color="#1a202c", pad=18)
    plt.tight_layout()
    fig.savefig(target, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


_DEC_HEADER_RE = re.compile(r"^###\s+Decision\s*[·-]", re.MULTILINE)


def _extract_step_decisions(root: Path, branch_id: str) -> list[str]:
    """Pull decision-log entries from workspace/analysis.md that reference
    this step. A block matches if it mentions the full branch_id
    (``03_replicate_attitude_demographics``) or the step number with a
    word-ish boundary (``Step 03`` / ``step=03``)."""
    analysis = root / "workspace" / "analysis.md"
    if not analysis.exists():
        return []
    text = analysis.read_text()
    blocks = _DEC_HEADER_RE.split(text)
    step_num = branch_id.split("_", 1)[0]  # e.g. "03"
    needle_re = re.compile(
        rf"(?:{re.escape(branch_id)}|[Ss]tep[ =]{step_num}\b|`{step_num}_)",
    )
    hits: list[str] = []
    for block in blocks[1:]:
        if needle_re.search(block):
            hits.append("### Decision ·" + block.strip())
    return hits


_FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".webp"}
_TABLE_EXTS = {".csv", ".tsv", ".parquet", ".feather", ".xlsx"}
_REPORT_EXTS = {".md", ".txt", ".html", ".rst"}


def _figure_table_inventory(exp_dir: Path) -> dict[str, list[str]]:
    """Inventory of REAL artefacts under outputs/{figures,tables,reports}.

    Filter by extension so caption / summary / prov sidecars don't
    pollute the figure list — without this, READMEs would report a step
    with 16 figures when it actually had 4 figures plus 12 metadata
    files for them.
    """
    bucket_exts = {
        "figures": _FIGURE_EXTS,
        "tables": _TABLE_EXTS,
        "reports": _REPORT_EXTS,
    }
    out: dict[str, list[str]] = {"figures": [], "tables": [], "reports": []}
    for sub, exts in bucket_exts.items():
        d = exp_dir / "outputs" / sub
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            if f.name.startswith(".") or f.name == "README.md":
                continue
            if f.suffix.lower() not in exts:
                # Sidecar / metadata file — skip it; the figure / table
                # / report it accompanies is the actual artefact.
                continue
            # Defensive: ignore the SVG companion when its PNG sibling
            # is also present (we count one logical figure, not two).
            if sub == "figures" and f.suffix.lower() == ".svg":
                if (d / (f.stem + ".png")).exists():
                    continue
            out[sub].append(f.name)
    return out


def finalize_path(
    path_name: str | None,
    root: Path,
) -> dict[str, Any]:
    """Rewrite a step's README + subfolder READMEs from what actually got
    produced. Idempotent — safe to call repeatedly.

    Behaviour:
      * Step `README.md`: fills the Methods / Outputs / Decision sections
        from `conclusions.md` headings + the per-step decision-log entries
        in `workspace/analysis.md` if those sections were left as stubs.
      * `environment/README.md`: if folder is empty → notes that the
        project-global environment was used. If snapshot exists → notes
        bespoke env + lists tracked files.
      * `literature/README.md`: if folder is empty → notes the project-
        global corpus was used + extracts any literature-tagged decisions
        from analysis.md as evidence chain. If sidecar PDFs/notes present
        → lists them.
      * `context/README.md`: if folder has only the seed template → notes
        nothing prose-specific was needed. If `notes.md` was filled in,
        surfaces the plain-language summary into the step README.
      * `data/README.md` + `data/output/README.md`: lists every artefact
        actually written + which downstream step (per workflow DAG) reads it.
      * For every figure missing a `.summary.md` plain-language sidecar,
        invokes the caption synthesiser so the dashboard / paper can
        embed an accessible description alongside the technical caption.
    """
    from research_os.project_ops import load_state

    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    if path_name is None:
        state = load_state(root)
        path_name = state.get("current_path")
        if not path_name or not (workspace / path_name).is_dir():
            return {
                "status": "error",
                "message": "No path_name given and current_path is unset.",
            }

    exp_dir = workspace / path_name
    if not exp_dir.is_dir():
        return {"status": "error", "message": f"Path '{path_name}' not found"}

    changes: list[str] = []

    # ---- 1. Per-folder normalisation ----
    env_dir = exp_dir / "environment"
    env_files = [
        p for p in env_dir.iterdir()
        if env_dir.exists() and p.name not in {"README.md", ".gitkeep"}
    ] if env_dir.exists() else []
    if not env_files:
        (env_dir / "README.md").parent.mkdir(parents=True, exist_ok=True)
        (env_dir / "README.md").write_text(
            f"# `{path_name}` — environment\n\n"
            "**Used the project-global environment** "
            "(`environment/requirements.txt`). No step-specific snapshot "
            "needed — analysis ran with the same package versions as every "
            "other step. Reproduce by recreating the global env.\n\n"
            "If you later add a step-specific requirement, run "
            "`sys_env_snapshot` and re-run `tool_path_finalize` to refresh "
            "this note.\n"
        )
        changes.append("environment/README.md → global-env note")
    else:
        lines = "\n".join(f"- `{p.name}`" for p in env_files)
        (env_dir / "README.md").write_text(
            f"# `{path_name}` — environment\n\n"
            "**Step-specific environment** captured here (differs from "
            "project global):\n\n"
            f"{lines}\n\n"
            "Recreate with `pip install -r requirements.txt` from this folder.\n"
        )
        changes.append("environment/README.md → bespoke-env listing")

    lit_dir = exp_dir / "literature"
    # Auto-populate the step's literature/key_papers.md from the
    # `## References to ground` section the AI wrote in conclusions.md.
    # Otherwise this file stays as a seed template for every step
    # because the AI rarely opens it to manually fill it in.
    _early_conc_path = exp_dir / "conclusions.md"
    if _early_conc_path.exists() and lit_dir.exists():
        try:
            conc_full = _early_conc_path.read_text()
            m = re.search(
                r"##\s*References?\s+to\s+ground\s*\n(.+?)(?=^##|\Z)",
                conc_full, re.MULTILINE | re.DOTALL | re.IGNORECASE,
            )
            if m:
                refs_block = m.group(1).strip()
                ref_lines = [
                    ln.strip().lstrip("-*+ ").strip()
                    for ln in refs_block.splitlines()
                    if ln.strip().startswith(("-", "*", "+"))
                ]
                ref_lines = [r for r in ref_lines if len(r) >= 5]
                if ref_lines:
                    kp = lit_dir / "key_papers.md"
                    kp_body = (
                        f"# `{path_name}` — key papers\n\n"
                        "Auto-extracted from `conclusions.md` "
                        "`## References to ground` at finalize time. "
                        "Drop the PDFs into `inputs/literature/` (project-wide) "
                        "or this folder (step-specific); verify via "
                        "`tool_citations_verify`.\n\n"
                    )
                    for r in ref_lines:
                        kp_body += f"- {r}\n"
                    kp.write_text(kp_body)
                    changes.append(
                        f"{lit_dir.relative_to(exp_dir)}/key_papers.md ← "
                        f"{len(ref_lines)} ref(s) from conclusions.md"
                    )
        except Exception as e:
            logger.debug("key_papers.md auto-fill skipped: %s", e)

    lit_files = [
        p for p in lit_dir.iterdir()
        if lit_dir.exists() and p.name not in {"README.md", ".gitkeep"}
    ] if lit_dir.exists() else []
    decisions = _extract_step_decisions(root, path_name)
    if not lit_files:
        body = (
            f"# `{path_name}` — literature\n\n"
            "No step-specific PDFs / notes — this step relied on the "
            "**project-global literature corpus** (`inputs/literature/`) "
            "and on transparent methodological reasoning rather than "
            "citation-specific support.\n"
        )
        if decisions:
            body += (
                "\n## Methodological decisions made here (from analysis.md)\n\n"
                + "\n\n".join(decisions[-5:])
                + "\n"
            )
        else:
            body += (
                "\nNo methodological decisions captured for this step. "
                "If a non-trivial choice was made, log it with "
                "`mem_decision_log` so the reasoning is preserved.\n"
            )
        (lit_dir / "README.md").parent.mkdir(parents=True, exist_ok=True)
        (lit_dir / "README.md").write_text(body)
        changes.append("literature/README.md → global-corpus note + decisions")
    else:
        lines = "\n".join(f"- `{p.name}`" for p in lit_files)
        body = (
            f"# `{path_name}` — literature\n\n"
            "**Step-specific literature** (used to justify methodological "
            "choices below):\n\n"
            f"{lines}\n"
        )
        if decisions:
            body += (
                "\n## Decisions these sources informed\n\n"
                + "\n\n".join(decisions[-5:])
                + "\n"
            )
        (lit_dir / "README.md").write_text(body)
        changes.append("literature/README.md → sources + linked decisions")

    # ---- 1c. Context folder (narrative scratchpad) ----
    ctx_dir = exp_dir / "context"
    ctx_files = [
        p for p in ctx_dir.iterdir()
        if ctx_dir.exists() and p.name not in {"README.md", ".gitkeep"}
    ] if ctx_dir.exists() else []
    plain_summary_from_context = ""
    notes_path = ctx_dir / "notes.md"
    # Scan both context/notes.md AND conclusions.md for the
    # plain-language summary block — an AI that wrote the summary
    # inside conclusions.md (the natural place) should not be flagged
    # as missing it. Accept several heading variants the AI is likely
    # to use.
    summary_pat = re.compile(
        r"##\s*(?:Plain[- ]language\s+summary|Plain[- ]English\s+summary|TL;DR|Lay\s+summary)\s*\n(.+?)(?=^##|\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    for path in (notes_path, exp_dir / "conclusions.md"):
        if plain_summary_from_context:
            break
        if not path.exists():
            continue
        try:
            txt = path.read_text()
            m = summary_pat.search(txt)
            if m:
                body = m.group(1).strip()
                if body and not body.startswith("_If you"):
                    plain_summary_from_context = body
        except Exception:
            pass
    if not ctx_files or (
        len(ctx_files) == 1 and ctx_files[0].name == "notes.md"
        and not plain_summary_from_context
    ):
        (ctx_dir / "README.md").parent.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "README.md").write_text(
            f"# `{path_name}` — context\n\n"
            "No prose context was needed for this step — the README + "
            "conclusions captured the relevant narrative. The "
            "`notes.md` template is preserved if a later analyst wants to "
            "add commentary.\n"
        )
        changes.append("context/README.md → no-context note")
    else:
        bullet_files = [f for f in ctx_files if f.name != "README.md"]
        listing = "\n".join(f"- `{p.name}`" for p in bullet_files)
        body = (
            f"# `{path_name}` — context\n\n"
            "Prose / narrative material accompanying this step:\n\n"
            f"{listing}\n"
        )
        if plain_summary_from_context:
            body += (
                "\n## Plain-language summary (lifted from notes.md)\n\n"
                f"{plain_summary_from_context}\n"
            )
        (ctx_dir / "README.md").write_text(body)
        changes.append("context/README.md → narrative inventory + summary")

    # ---- 2. Data folder + downstream consumer map ----
    consumers = _downstream_consumers(workspace, path_name)
    out_dir = exp_dir / "data" / "output"
    out_files = []
    if out_dir.exists():
        for f in sorted(out_dir.iterdir()):
            if f.name in {"README.md", ".gitkeep"}:
                continue
            if f.is_file():
                out_files.append(f.name)
    out_body = (
        f"# `{path_name}/data/output` — artefacts\n\n"
    )
    if out_files:
        out_body += "Persisted files:\n\n" + "\n".join(
            f"- `{name}`" for name in out_files
        ) + "\n"
    else:
        out_body += (
            "No persisted artefacts yet. If this step intentionally "
            "produces no downstream data (e.g. it's a pure synthesis or "
            "audit step), that's fine — note it in `conclusions.md`.\n"
        )
    if consumers:
        out_body += "\n## Downstream consumers\n\n" + "\n".join(
            f"- `{c}` reads this folder via `data/input` symlink." for c in consumers
        ) + "\n"
    else:
        out_body += (
            "\nNo downstream step currently consumes these outputs.\n"
        )
    (out_dir / "README.md").parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "README.md").write_text(out_body)
    changes.append("data/output/README.md → artefacts + consumer map")

    # ---- 3. Outputs inventory + step README finalize ----
    inv = _figure_table_inventory(exp_dir)
    out_readme = exp_dir / "outputs" / "README.md"
    out_readme.parent.mkdir(parents=True, exist_ok=True)
    out_readme.write_text(
        f"# `{path_name}` — outputs inventory\n\n"
        f"- **Figures:** {len(inv['figures'])}"
        + (": " + ", ".join(f"`{n}`" for n in inv['figures']) if inv['figures'] else "")
        + "\n"
        f"- **Tables:** {len(inv['tables'])}"
        + (": " + ", ".join(f"`{n}`" for n in inv['tables']) if inv['tables'] else "")
        + "\n"
        f"- **Reports:** {len(inv['reports'])}"
        + (": " + ", ".join(f"`{n}`" for n in inv['reports']) if inv['reports'] else "")
        + "\n\n"
        "Pair each figure / table with a sibling `<name>.caption.md` so the "
        "synthesis dashboard can embed the explanation inline.\n"
    )
    changes.append("outputs/README.md → produced-artefact inventory")

    # ---- 4. Step README: only fill stub sections; never overwrite real text ----
    step_readme = exp_dir / "README.md"
    conc_path = exp_dir / "conclusions.md"
    if step_readme.exists() and conc_path.exists():
        readme_text = step_readme.read_text()
        conc_text = conc_path.read_text()
        new_readme = _finalize_step_readme(
            readme_text, conc_text, decisions, inv, path_name,
            plain_summary=plain_summary_from_context,
            exp_dir=exp_dir,
        )
        if new_readme != readme_text:
            step_readme.write_text(new_readme)
            changes.append("README.md → stub sections populated")

    # ---- 5. Auto-synthesise plain-English summaries for figures ----
    summaries_written: list[str] = []
    figs_dir = exp_dir / "outputs" / "figures"
    if figs_dir.exists():
        try:
            from research_os.tools.actions.viz import caption_synthesise

            for f in sorted(figs_dir.iterdir()):
                if f.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
                    continue
                if f.with_suffix(".summary.md").exists():
                    continue
                rel = f.relative_to(root).as_posix()
                res = caption_synthesise(figure_path=rel, root=root)
                if res.get("status") == "success" and not res.get("already_exists"):
                    summaries_written.append(f.name)
        except Exception as e:
            logger.debug("plain-English summary synthesis skipped: %s", e)
        if summaries_written:
            changes.append(
                f"plain-English summaries → {len(summaries_written)} figure(s)"
            )

    # ---- 6. Stub detection — surface as warnings so the AI knows
    #         what's still empty before walking off the step. We do NOT
    #         block: a researcher / autopilot AI may genuinely have
    #         decided some sections aren't applicable. The warnings
    #         themselves are the audit trail.
    warnings: list[str] = []
    if conc_path.exists():
        conc_text_now = conc_path.read_text()
        for hdr in ("Findings", "Decision"):
            if _is_stub_section(conc_text_now, hdr):
                warnings.append(
                    f"conclusions.md > {hdr} is still a stub — fill it before "
                    "the next step or before synthesis (gate will block there)."
                )
        if _is_stub_section(conc_text_now, "Plain-language summary"):
            warnings.append(
                "conclusions.md > Plain-language summary is still a stub — "
                "the dashboard's executive / teaching views will fall back to "
                "the technical text."
            )

    # ---- 7. Per-step → project-scope file refresh.
    #         Finalize touches workspace/methods.md, analysis.md, and
    #         citations.md idempotently. Without this, a step's work
    #         never reaches the project's running record (the finalize
    #         is otherwise purely observational).
    project_updates: list[str] = []

    # 7a. workspace/analysis.md — append a step-complete heading + the
    #     headline finding extracted from conclusions.md. Idempotent: we
    #     only append if there isn't already a heading for this step.
    analysis_md = root / "workspace" / "analysis.md"
    if conc_path.exists() and analysis_md.exists():
        try:
            existing = analysis_md.read_text()
            marker = f"\n### Step `{path_name}` finalized"
            if marker not in existing:
                headline = _headline_from_findings(conc_path.read_text())
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                entry = (
                    f"\n### Step `{path_name}` finalized — {stamp}\n\n"
                    f"- **Headline:** {headline or '(no findings recorded)'}\n"
                    f"- **Outputs:** {len(inv['figures'])} figure(s), "
                    f"{len(inv['tables'])} table(s), "
                    f"{len(inv['reports'])} report(s).\n"
                    f"- **Decisions linked:** {len(decisions)} entries in "
                    f"`mem_decision_log` (see `literature/README.md`).\n"
                )
                analysis_md.write_text(existing.rstrip() + "\n" + entry)
                project_updates.append("workspace/analysis.md ← step entry")
        except OSError as e:
            logger.debug("analysis.md append skipped: %s", e)

    # 7b. workspace/methods.md — if conclusions.md has a `## Methods`
    #     (or `## Methods (full detail)`) section, mirror its content into
    #     a step-tagged subsection in the project-scope log. Idempotent
    #     on the heading marker.
    methods_md = root / "workspace" / "methods.md"
    if conc_path.exists() and methods_md.exists():
        try:
            conc_full = conc_path.read_text()
            methods_body = _section(conc_full, "Methods (full detail)") or \
                _section(conc_full, "Methods")
            if methods_body:
                existing_m = methods_md.read_text()
                marker = f"\n### Step `{path_name}` — methods\n"
                if marker not in existing_m:
                    methods_md.write_text(
                        existing_m.rstrip() + "\n"
                        + f"\n### Step `{path_name}` — methods\n\n"
                        + methods_body.strip()
                        + "\n"
                    )
                    project_updates.append("workspace/methods.md ← step methods")
        except OSError as e:
            logger.debug("methods.md append skipped: %s", e)

    # 7c. workspace/citations.md — regenerate from the union of
    #     inputs/literature_index.yaml + every per-step literature
    #     .meta.yaml sidecar. Idempotent (full rewrite).
    try:
        from research_os.project_ops import generate_citations_md
        citations_path = generate_citations_md(root)
        if citations_path:
            project_updates.append("workspace/citations.md ← regenerated")
    except Exception as e:
        logger.debug("citations.md regen skipped: %s", e)

    # 7c-0. Anti-hallucination: if conclusions.md cites references but
    #       the project's searches.log has NO `tool_search_*` entries,
    #       warn loudly. Researcher needs to know the citations weren't
    #       grounded in actual lookups.
    if conc_path.exists():
        try:
            conc_full_for_lit = conc_path.read_text()
            cites_refs = bool(
                re.search(
                    r"##\s*References?\s+to\s+ground\s*\n.+?(?:\b\d{4}\b|doi\.org)",
                    conc_full_for_lit, re.DOTALL | re.IGNORECASE,
                )
            )
            if cites_refs:
                searches_log = root / "workspace" / "logs" / "searches.log"
                search_count = 0
                if searches_log.exists():
                    search_count = sum(
                        1 for line in searches_log.read_text().splitlines()
                        if line.strip()
                    )
                if search_count == 0:
                    warnings.append(
                        "conclusions.md cites references but NO `tool_search_*` "
                        "calls have been logged in workspace/logs/searches.log. "
                        "The citations may be from training memory, not verified "
                        "literature. Run `tool_search_semantic_scholar` / "
                        "`tool_search_pubmed` / `tool_literature_search_and_save` "
                        "to ground the cited references — required before any "
                        "synthesis deliverable."
                    )
        except Exception as e:
            logger.debug("search-grounding check skipped: %s", e)

    # 7c-i. Mirror conclusions.md's `## Decision` block into
    #       workspace/analysis.md as a formal decision-log entry via
    #       `log_decision`. Otherwise the AI has to call
    #       mem_decision_log manually and rarely does; the decision
    #       text is in conclusions.md regardless.
    DECISION_VERBS = {"PROCEED", "BRANCH", "DEAD-END", "DEAD_END", "HOLD", "ABANDON"}
    if conc_path.exists():
        try:
            conc_full = conc_path.read_text()
            m = re.search(
                r"##\s*Decision\s*\n(.+?)(?=^##|\Z)",
                conc_full, re.MULTILINE | re.DOTALL | re.IGNORECASE,
            )
            if m:
                body = m.group(1).strip()
                # Skip if it's still the seed placeholder.
                if body and not body.startswith("*(") and not body.startswith("_("):
                    first_line = body.splitlines()[0].strip().lstrip("-*+ ").strip()
                    # Try to extract the verb (first word, normalised).
                    verb = first_line.split()[0].upper().rstrip(":,.") if first_line else ""
                    if verb in DECISION_VERBS:
                        # Idempotency: skip if an existing analysis.md decision
                        # for this step already exists.
                        analysis_md_path = root / "workspace" / "analysis.md"
                        existing_a = analysis_md_path.read_text() if analysis_md_path.exists() else ""
                        marker_d = f"step={path_name}; verb={verb}"
                        if marker_d not in existing_a:
                            from research_os.project_ops import log_decision
                            log_decision(
                                context=f"Finalize of {path_name} (mirrored from conclusions.md)",
                                selected=f"{verb} ({marker_d})",
                                rationale=first_line[len(verb):].strip(" :—-") or body,
                                root=root,
                            )
                            project_updates.append(
                                f"mem_decision_log ← {verb} from {path_name}"
                            )
        except Exception as e:
            logger.debug("decision mirror skipped: %s", e)

    # 7c-ii. workspace/tools.md — append a step-tagged section listing the
    #        Research-OS tools used, 3rd-party packages, external services,
    #        and any custom scripts the step depends on. Idempotent on the
    #        per-step heading marker.
    tools_md = root / "workspace" / "tools.md"
    if conc_path.exists() and tools_md.exists():
        try:
            conc_full = conc_path.read_text()
            existing_t = tools_md.read_text()
            marker = f"\n### Step `{path_name}` — tools used\n"
            if marker not in existing_t:
                # Extract from conclusions.md: Methods section + any explicit
                # `## Tools` or `## Software` section.
                tools_body = (
                    _section(conc_full, "Tools used")
                    or _section(conc_full, "Tools")
                    or _section(conc_full, "Software")
                    or ""
                ).strip()
                # Fall back to scanning the step tree via the multi-language
                # extractor pipeline. Captures Python + R + Bash modules +
                # Node + Rust + Julia + adapter-contributed patterns
                # (Slurm partitions, Snakemake rules, Nextflow processes,
                # HPC modules, etc).
                if not tools_body:
                    STDLIB_SKIP = {
                        "abc", "argparse", "ast", "asyncio", "base64", "collections",
                        "contextlib", "copy", "csv", "datetime", "decimal", "enum",
                        "errno", "fnmatch", "functools", "gc", "glob", "gzip",
                        "hashlib", "heapq", "html", "http", "importlib", "inspect",
                        "io", "ipaddress", "itertools", "json", "logging", "math",
                        "mimetypes", "operator", "os", "pathlib", "pickle", "pprint",
                        "queue", "random", "re", "secrets", "shlex", "shutil",
                        "signal", "socket", "sqlite3", "statistics", "string",
                        "struct", "subprocess", "sys", "tempfile", "textwrap",
                        "threading", "time", "tomllib", "traceback", "typing",
                        "unicodedata", "unittest", "urllib", "uuid", "warnings",
                        "weakref", "xml", "zipfile", "zlib", "__future__",
                    }
                    ENGLISH_STOPWORDS = {
                        "the", "a", "an", "and", "or", "of", "for", "to",
                        "in", "on", "at", "by", "as", "is", "it", "be",
                        "we", "i", "this", "that", "with", "from", "into",
                        "import", "uses", "use",
                    }
                    try:
                        from research_os.tools.actions.state.extractors import (
                            extract_from_tree,
                        )
                        tuples = extract_from_tree(root, step_id=path_name)
                    except Exception as exc:
                        logger.debug("extractors fell through: %s", exc)
                        tuples = []
                    bullets: list[str] = []
                    seen: set[tuple] = set()
                    for kind, name, ver in tuples:
                        key = (kind, name)
                        if key in seen:
                            continue
                        # Filter Python noise: stdlib, English words, single letters.
                        if kind == "python_import":
                            base = name.split(".")[0]
                            if (
                                not base
                                or len(base) <= 1
                                or base.lower() in STDLIB_SKIP
                                or base.lower() in ENGLISH_STOPWORDS
                                or base.startswith("_")
                            ):
                                continue
                            seen.add(key)
                            bullets.append(f"- `{base}` — Python package")
                        elif kind in {"r_library", "r_bioc_install", "r_renv", "r_description"}:
                            seen.add(key)
                            label = {
                                "r_library": "R library",
                                "r_bioc_install": "Bioconductor package",
                                "r_renv": "renv-pinned R package",
                                "r_description": "DESCRIPTION-declared R dep",
                            }[kind]
                            v = f" ({ver})" if ver else ""
                            bullets.append(f"- `{name}` — {label}{v}")
                        elif kind == "bash_module":
                            seen.add(key)
                            bullets.append(f"- `{name}` — HPC module load")
                        elif kind == "bash_env":
                            seen.add(key)
                            bullets.append(f"- `{name}` — shell environment activation")
                        elif kind in {"node_dep", "node_import"}:
                            seen.add(key)
                            label = "Node dep" if kind == "node_dep" else "Node import"
                            v = f" ({ver})" if ver else ""
                            bullets.append(f"- `{name}` — {label}{v}")
                        elif kind in {"rust_dep", "rust_use"}:
                            seen.add(key)
                            label = "Rust crate" if kind == "rust_dep" else "Rust use"
                            v = f" ({ver})" if ver else ""
                            bullets.append(f"- `{name}` — {label}{v}")
                        elif kind in {"julia_dep", "julia_using"}:
                            seen.add(key)
                            label = "Julia dep" if kind == "julia_dep" else "Julia using"
                            v = f" ({ver})" if ver else ""
                            bullets.append(f"- `{name}` — {label}{v}")
                        elif kind == "adapter_pattern":
                            seen.add(key)
                            bullets.append(f"- {ver} _(via {name} adapter)_")
                    bullets = sorted(set(bullets))[:60]
                    if bullets:
                        tools_body = "\n".join(bullets)
                    else:
                        tools_body = (
                            "_(No third-party packages or infra detected in this "
                            "step's scripts beyond the Python stdlib + "
                            "Research-OS internals. Verify the step's "
                            "scripts exist + run if this is unexpected.)_"
                        )
                if tools_body:
                    tools_md.write_text(
                        existing_t.rstrip() + "\n"
                        + f"\n### Step `{path_name}` — tools used\n\n"
                        + tools_body
                        + "\n"
                    )
                    project_updates.append("workspace/tools.md ← step tools")
        except OSError as e:
            logger.debug("tools.md append skipped: %s", e)

    # 7d. Per-step environment snapshot — if outputs/figures, tables, or
    #     reports exist (i.e. work happened) the step's runtime stack
    #     MUST be captured. Auto-snapshot the project-global env if
    #     requirements.txt is still the comment-only template; warn if
    #     even that fails or if a per-step environment would have been
    #     more appropriate (different lang stack than the project
    #     default).
    work_happened = bool(inv["figures"] or inv["tables"] or inv["reports"])
    project_req = root / "environment" / "requirements.txt"
    is_template_empty = (
        project_req.exists()
        and "# Project-global Python packages" in project_req.read_text()
        and "\n" in project_req.read_text()
        and not any(
            ln.strip() and not ln.strip().startswith("#")
            for ln in project_req.read_text().splitlines()
        )
    )
    if work_happened and (is_template_empty or not project_req.exists()):
        try:
            from research_os.tools.actions.exec.environment import env_snapshot

            # Pass `scope='project'` explicitly so the snapshot lands
            # in the project-global environment/ folder. The auto-
            # target rule for no-args lands in the most-recent active
            # step's folder, NOT project-global — that's the wrong
            # target when finalize is updating the GLOBAL
            # requirements.txt.
            snap = env_snapshot(root, scope="project")
            if snap.get("status") == "success":
                project_updates.append(
                    "environment/requirements.txt ← auto-snapshot at finalize"
                )
            else:
                warnings.append(
                    "Auto-env-snapshot at finalize failed: "
                    + snap.get("message", "unknown error")
                    + ". Call `sys_env_snapshot` manually."
                )
        except Exception as e:
            warnings.append(
                f"Auto-env-snapshot at finalize raised {type(e).__name__}: {e}. "
                "Call `sys_env_snapshot` manually."
            )
    # 7d-ii. Flip this step's state-ledger status to "completed" +
    #        regenerate STATE.md so the project front page shows ✓
    #        instead of → after finalize. Otherwise a fully-finalized
    #        step keeps status="active" until next sys_path_create
    #        flips it as a side effect, leaving STATE.md misleading
    #        between steps.
    try:
        from research_os.project_ops import load_state, save_state
        s = load_state(root)
        paths_state = s.get("paths") or {}
        if path_name in paths_state and paths_state[path_name].get("status") != "completed":
            paths_state[path_name]["status"] = "completed"
            paths_state[path_name]["completed_at"] = (
                datetime.now(timezone.utc).isoformat()
            )
            save_state(root, s)
            project_updates.append("STATE.md ← step status flipped to ✓")
    except Exception as e:
        logger.debug("STATE.md status flip skipped: %s", e)

    if work_happened and not env_files and (root / "environment" / "requirements.txt").exists():
        # Per-step env folder still empty even after the project-global
        # snapshot — only worth flagging if the step uses a bespoke stack.
        warnings.append(
            f"`workspace/{path_name}/environment/` is empty. If this step "
            f"uses a different package stack than the project default, "
            f"call `sys_env_snapshot step_id='{path_name}'` for a "
            f"per-step capture."
        )

    # 7e. Per-figure quality audit gate.
    #     Every figure that landed in outputs/figures/ is run through
    #     the same DPI / dimension / sidecar / aspect-ratio checks the
    #     pre-submission audit uses. Blockers and warnings surface here
    #     so the AI sees them now, not at synthesis time. Audits
    #     visualizations at the per-step gate.
    figure_audit: dict[str, dict[str, list[str]]] = {}
    if inv["figures"]:
        try:
            from research_os.tools.actions.viz.figures import (
                audit_figure_quality,
            )
        except Exception:
            audit_figure_quality = None
        if audit_figure_quality is not None:
            for fig_name in inv["figures"]:
                rel = (exp_dir / "outputs" / "figures" / fig_name
                       ).relative_to(root).as_posix()
                try:
                    fr = audit_figure_quality(rel, root)
                except Exception as e:
                    fr = {"status": "error", "message": str(e)}
                fblockers = fr.get("blockers", []) or []
                fwarn = fr.get("warnings", []) or []
                figure_audit[fig_name] = {
                    "blockers": fblockers, "warnings": fwarn,
                }
                for b in fblockers:
                    warnings.append(f"figure `{fig_name}` BLOCKER: {b}")
                for w in fwarn:
                    warnings.append(f"figure `{fig_name}` warning: {w}")

    # 7f. Emit step_summary.yaml — structured machine-readable mirror
    #     of conclusions.md the synthesis pipeline consumes
    #     deterministically (no NLP parsing required to compose the
    #     paper / abstract / dashboard).
    try:
        if conc_path.exists():
            conc_text = conc_path.read_text()
            # Prefer the explicit `## Headline finding` block when the AI
            # wrote one; fall back to first-bullet-from-Findings extraction.
            explicit_headline = (_section(conc_text, "Headline finding") or "").strip()
            headline_for_summary = (
                explicit_headline
                or _headline_from_findings(conc_text)
                or ""
            )
            summary_payload: dict[str, Any] = {
                "step_id": path_name,
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "headline": headline_for_summary,
                "methods_block": (_section(conc_text, "Methods (full detail)") or _section(conc_text, "Methods") or "").strip(),
                "plain_language_summary": (_section(conc_text, "Plain-language summary") or _section(conc_text, "Plain-English summary") or "").strip(),
                "findings": _bullet_lines(_section(conc_text, "Findings")),
                "decision": (_section(conc_text, "Decision") or "").strip(),
                "limitations": _bullet_lines(_section(conc_text, "Limitations")),
                "references_to_ground": _bullet_lines(_section(conc_text, "References to ground")),
                "figures": [
                    {
                        "name": fig_name,
                        "path": f"workspace/{path_name}/outputs/figures/{fig_name}",
                        "caption_path": f"workspace/{path_name}/outputs/figures/{Path(fig_name).stem}.caption.md",
                        "summary_path": f"workspace/{path_name}/outputs/figures/{Path(fig_name).stem}.summary.md",
                        "audit": figure_audit.get(fig_name, {}),
                    }
                    for fig_name in inv["figures"]
                ],
                "tables": [
                    f"workspace/{path_name}/outputs/tables/{t}" for t in inv["tables"]
                ],
                "reports": [
                    f"workspace/{path_name}/outputs/reports/{r}" for r in inv["reports"]
                ],
                "warnings": list(warnings),
            }
            try:
                import yaml as _yaml
                (exp_dir / "step_summary.yaml").write_text(
                    _yaml.dump(summary_payload, sort_keys=False, default_flow_style=False)
                )
                project_updates.append(
                    "workspace/<step>/step_summary.yaml ← structured sidecar for synthesis"
                )
            except Exception as e:
                logger.debug("step_summary.yaml emit skipped: %s", e)
    except Exception as e:
        logger.debug("step_summary build skipped: %s", e)

    # 7g. Per-step retrospective — append "Anticipated reviewer
    #     questions" section to conclusions.md so the AI's own self-
    #     critique is on record. Idempotent on the marker.
    try:
        if conc_path.exists():
            conc_text = conc_path.read_text()
            retro_marker = "## Anticipated reviewer questions"
            if retro_marker not in conc_text:
                questions = _anticipated_reviewer_questions(
                    headline=_headline_from_findings(conc_text) or "",
                    limitations=_section(conc_text, "Limitations") or "",
                    methods=_section(conc_text, "Methods (full detail)") or "",
                    n_figures=len(inv["figures"]),
                    n_tables=len(inv["tables"]),
                )
                retro_block = (
                    "\n\n" + retro_marker + "\n\n"
                    + "*Auto-generated by `tool_path_finalize`. The AI's "
                    "self-critique scaffold — questions a reviewer would "
                    "ask given this step's findings + limitations. Address "
                    "each before synthesis.*\n\n"
                    + "\n".join(f"- {q}" for q in questions)
                    + "\n"
                )
                conc_path.write_text(conc_text.rstrip() + retro_block)
                project_updates.append(
                    "conclusions.md ← Anticipated reviewer questions appended"
                )
    except Exception as e:
        logger.debug("retrospective append skipped: %s", e)

    return {
        "status": "success",
        "path_name": path_name,
        "changes": changes,
        "project_updates": project_updates,
        "warnings": warnings,
        "figure_audit": figure_audit,
        "decisions_linked": len(decisions),
        # `output_files` was ambiguous (counted data/output/ only,
        # while researchers expected the total of outputs/figures +
        # tables + reports + data/output). Both kept for back-compat;
        # the count fields now read more naturally.
        "data_output_files": len(out_files),
        "output_files": len(out_files),
        "figures": len(inv["figures"]),
        "tables": len(inv["tables"]),
        "reports": len(inv["reports"]),
        "total_user_visible_artefacts": (
            len(out_files) + len(inv["figures"]) + len(inv["tables"]) + len(inv["reports"])
        ),
        "plain_english_summary_present": bool(plain_summary_from_context),
        "figure_summaries_synthesised": summaries_written,
    }


def _downstream_consumers(workspace: Path, path_name: str) -> list[str]:
    """Steps whose data/input symlink resolves under <path_name>/data/output."""
    self_out = (workspace / path_name / "data" / "output").resolve()
    consumers: list[str] = []
    for p in sorted(workspace.iterdir()):
        if not (p.is_dir() and re.match(r"^\d{2,3}_", p.name)) or p.name == path_name:
            continue
        inp = p / "data" / "input"
        if not inp.exists():
            continue
        try:
            if inp.is_symlink() and inp.resolve() == self_out:
                consumers.append(p.name)
            elif inp.is_dir():
                for child in inp.iterdir():
                    if child.is_symlink() and child.resolve() == self_out:
                        consumers.append(p.name)
                        break
        except OSError:
            continue
    return consumers


_STUB_MARKERS = (
    "*(list inputs used)*",
    "*(list methods/models)*",
    "*(describe expected outputs)*",
    "*(proceed | branch | dead-end)*",
    "*(One paragraph. Imagine",
    "*(the single most important result",
    "*(name the method;",
    "*(figures / tables / reports produced)*",
)


def _section(text: str, header: str) -> str:
    """Extract a markdown section under ``## <header>`` until the next ## or EOF."""
    pat = re.compile(
        rf"^##\s+{re.escape(header)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _bullet_lines(section_text: str) -> list[str]:
    """Pull `- bullet` / `* bullet` / `+ bullet` lines from a section.

    If no bullets are found but the section IS non-empty (prose-led
    or table-led Findings), fall back to sentence-split so the
    structured ``step_summary.yaml.findings`` is never silently empty
    (a prose Findings or a table-led Findings would otherwise come out
    as ``findings: []``).
    """
    if not section_text:
        return []
    out: list[str] = []
    for ln in section_text.splitlines():
        s = ln.strip()
        if s.startswith(("-", "*", "+")) and len(s) > 2:
            out.append(s.lstrip("-*+ ").strip())
    if out:
        return out
    # No bullets — fall back to sentence-split on the prose body.
    # Strip markdown table rows entirely; keep the prose around them.
    prose_lines = [
        ln for ln in section_text.splitlines()
        if ln.strip() and not ln.strip().startswith("|") and not ln.strip().startswith("---")
    ]
    if not prose_lines:
        return []
    prose = " ".join(prose_lines)
    import re as _re_mod
    sentences = [
        s.strip()
        for s in _re_mod.split(r"(?<=[.!?])\s+(?=[A-Z(`])", prose)
        if len(s.strip()) > 20
    ]
    return sentences[:8] or [prose[:500]]
    return out


def _anticipated_reviewer_questions(
    *,
    headline: str,
    limitations: str,
    methods: str,
    n_figures: int,
    n_tables: int,
) -> list[str]:
    """Scaffolded reviewer-perspective self-critique questions.

    Generic patterns + content-aware variants. The AI rewrites these
    in its own voice; we just guarantee the section is there.
    """
    qs: list[str] = []
    # Universal reviewer questions, always applicable.
    qs.append(
        "What's the effect size + its 95% CI, and does the CI exclude the "
        "null in a way that's not artefact of the sample size?"
    )
    qs.append(
        "Did the analysis pre-specify the model or was it picked after seeing "
        "the data? If post-hoc, what's the multiple-comparisons correction?"
    )
    qs.append(
        "What's the sensitivity to the analytic choices (model family, "
        "outlier handling, multiple-testing cutoff)? Does the headline survive?"
    )
    # Content-aware additions based on the methods + limitations text.
    methods_l = (methods or "").lower()
    if "negative-binomial" in methods_l or "deseq2" in methods_l or "glm" in methods_l:
        qs.append(
            "On n=12 (or other small-n) how reliable are the dispersion "
            "estimates? Did you report empirical-Bayes-shrunk vs unshrunk SEs?"
        )
    if "pca" in methods_l:
        qs.append(
            "What fraction of variance is captured by PC1-PC4? Is the "
            "clustering robust to the choice of variance filter?"
        )
    if "enrichment" in methods_l or "gsea" in methods_l or "ora" in methods_l:
        qs.append(
            "What's the gene-set library version + size? Is the multiple-"
            "testing correction across-pathways or within-pathway?"
        )
    if "blocking" in methods_l or "batch" in methods_l:
        qs.append(
            "Are the blocking / batch variables truly orthogonal to the "
            "treatment, or is the design partially confounded?"
        )
    # Limitations-driven question: phrase the limitation back as a query.
    lim_first = (limitations or "").splitlines()
    for ln in lim_first[:3]:
        s = ln.strip().lstrip("-*+ ").strip()
        if s and len(s) > 20:
            qs.append(
                f"You acknowledge: '{s[:100]}{'...' if len(s) > 100 else ''}' "
                "— how does this affect the headline's interpretation?"
            )
            break
    if n_figures < 2:
        qs.append(
            f"This step produced only {n_figures} figure(s) — what additional "
            "visualization would help a reader follow the result?"
        )
    if n_tables == 0:
        qs.append(
            "There's no tabular output for this step — are the headline "
            "numbers reproducible from the workspace?"
        )
    return qs[:8]


def _replace_section(text: str, header: str, new_body: str) -> str:
    pat = re.compile(
        rf"(^##\s+{re.escape(header)}\s*\n)(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if not pat.search(text):
        return text + f"\n## {header}\n{new_body}\n"
    return pat.sub(lambda m: m.group(1) + new_body.rstrip() + "\n\n", text)


def _is_stub_section(text: str, header: str) -> bool:
    """A section counts as a stub if it's empty OR contains any stub marker."""
    body = _section(text, header)
    if not body:
        return True
    return any(marker in body for marker in _STUB_MARKERS)


def _shorten(body: str, max_chars: int = 800) -> str:
    body = body.strip()
    if len(body) <= max_chars:
        return body
    cut = body[:max_chars].rsplit(". ", 1)[0]
    return cut + ". …"


def _headline_from_findings(conclusions: str) -> str:
    """Pull the most quotable headline from the conclusions' Findings.

    Rules:
      * Joins continuation lines under the first bullet (markdown
        bullets often wrap; cutting at the first newline produces
        fragments like 'n = 334 retained from 337 raw rows;').
      * Cuts at the first sentence end (period/semicolon) AFTER a
        minimum length so the headline is one sentence, not a paragraph.
      * Strips markdown emphasis (`**bold**`) from the headline.
    """
    body = _section(conclusions, "Findings")
    if not body:
        return ""

    # Walk lines; collect the first bullet + any continuation lines
    # (indented, not starting a new bullet, not a section).
    lines = body.splitlines()
    first_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith(("-", "*")):
            first_idx = i
            break
    if first_idx is None:
        # No bullets — fall back to first non-empty paragraph.
        for line in lines:
            line = line.strip()
            if line:
                bullet_text = line
                break
        else:
            return ""
    else:
        # Strip the leading list marker (- or *) ONCE, plus surrounding
        # whitespace. Using `lstrip("-* ")` would eat markdown bold's
        # opening `**` too, leaving the closing `**` orphaned and
        # ineligible for the emphasis-strip regex below.
        raw = lines[first_idx]
        m = re.match(r"^\s*[-*+]\s+", raw)
        bullet_text = raw[m.end():] if m else raw.strip()
        for j in range(first_idx + 1, len(lines)):
            nxt = lines[j]
            stripped = nxt.strip()
            if not stripped:
                break
            if stripped.startswith(("-", "*", "#")):
                break
            # Continuation — single-space join.
            bullet_text = bullet_text.rstrip() + " " + stripped
    # Clean up: strip markdown emphasis + collapse whitespace.
    bullet_text = re.sub(r"\*\*?(.+?)\*\*?", r"\1", bullet_text)
    bullet_text = re.sub(r"`(.+?)`", r"\1", bullet_text)
    bullet_text = re.sub(r"\s+", " ", bullet_text).strip()
    # First sentence: stop at . ? ! that's followed by whitespace +
    # capital, OR end-of-string. Don't break on ; (mid-clause).
    m = re.search(r"^(.{30,200}?[.!?])(\s+[A-Z(]|$)", bullet_text)
    if m:
        return m.group(1).strip()
    # If the bullet is shorter than the floor, just return it whole.
    return bullet_text[:200]


def _input_inventory_for_readme(exp_dir: Path) -> str:
    """Best-effort inventory of this step's inputs for the README.

    Scans `data/input/` symlinks (each one usually points at the prior
    step's `data/output/<file>`) and falls back to listing files
    referenced from the cleaning pipeline script(s) when no symlinks
    exist yet.
    """
    inp_dir = exp_dir / "data" / "input"
    items: list[str] = []
    if inp_dir.is_dir():
        for entry in sorted(inp_dir.iterdir()):
            if entry.name in {"README.md", "_input_readme.md", ".gitkeep"}:
                continue
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                    items.append(
                        f"- `data/input/{entry.name}` → "
                        f"`{target.relative_to(exp_dir.parent.parent)}`"
                    )
                    continue
                except (OSError, ValueError):
                    pass
            items.append(f"- `data/input/{entry.name}`")
    # Also surface raw_data references found in pipeline.yaml so the
    # very-first step (no symlinks yet) doesn't read as "no inputs".
    pipeline_yaml = exp_dir / "pipeline.yaml"
    if pipeline_yaml.exists():
        try:
            text = pipeline_yaml.read_text()
            raw_refs = sorted(set(re.findall(r"inputs/raw_data/[^\s\"']+", text)))
            for r in raw_refs:
                line = f"- `{r}` (project-scope raw input)"
                if line not in items:
                    items.append(line)
        except OSError:
            pass
    return "\n".join(items)


def _finalize_step_readme(
    readme: str,
    conclusions: str,
    decisions: list[str],
    inv: dict[str, list[str]],
    path_name: str,
    *,
    plain_summary: str = "",
    exp_dir: Path | None = None,
) -> str:
    """Backfill stub README sections from conclusions + decisions + outputs.

    The README is the 60-second OVERVIEW; the per-section behaviour is:

    * **In plain English** ← `context/notes.md` Plain-language summary OR
      `conclusions.md`'s "Plain-language summary" section.
    * **Methods (one line each)** ← `conclusions.md`'s Methods section,
      truncated to ~800 chars.
    * **Headline finding** ← first bullet of `conclusions.md` Findings.
    * **Outputs** ← inventory of figures / tables / reports.
    * **Decision** ← `conclusions.md`'s Decision section.
    """
    text = readme

    # Plain-English overview: context > conclusions > skip.
    if _is_stub_section(text, "In plain English"):
        body = plain_summary or _section(
            conclusions, "Plain-language summary"
        )
        if body:
            text = _replace_section(text, "In plain English", _shorten(body, 700))

    # Input data — list data/input/ symlinks + raw_data refs found in
    # pipeline.yaml. The "Input data" stub used to stay un-backfilled
    # because the original finalize never wrote it; now it does.
    if exp_dir is not None and _is_stub_section(text, "Input data"):
        inventory = _input_inventory_for_readme(exp_dir)
        if inventory:
            text = _replace_section(text, "Input data", inventory)

    # Methods (one-line each).
    if _is_stub_section(text, "Methods (one line each)") or _is_stub_section(text, "Methods"):
        method_src = _section(conclusions, "Methods (full detail)") or _section(
            conclusions, "Methods"
        ) or _section(conclusions, "Method")
        if not method_src and decisions:
            method_src = "Decisions logged for this step:\n\n" + "\n\n".join(
                d[:600] for d in decisions[-3:]
            )
        if method_src:
            header = (
                "Methods (one line each)"
                if "Methods (one line each)" in text
                else "Methods"
            )
            text = _replace_section(text, header, _shorten(method_src, 800))

    # Headline finding.
    if _is_stub_section(text, "Headline finding"):
        headline = _headline_from_findings(conclusions)
        if headline:
            text = _replace_section(text, "Headline finding", headline)

    # Outputs.
    if _is_stub_section(text, "Outputs"):
        lines = []
        if inv["figures"]:
            lines.append("**Figures**: " + ", ".join(f"`{n}`" for n in inv["figures"]))
        if inv["tables"]:
            lines.append("**Tables**: " + ", ".join(f"`{n}`" for n in inv["tables"]))
        if inv["reports"]:
            lines.append("**Reports**: " + ", ".join(f"`{n}`" for n in inv["reports"]))
        if not lines:
            lines.append("_(no figures, tables, or reports produced — pure routing / synthesis step)_")
        text = _replace_section(text, "Outputs", "\n".join(lines))

    # Decision.
    if _is_stub_section(text, "Decision"):
        dec_src = _section(conclusions, "Decision")
        if dec_src:
            text = _replace_section(text, "Decision", dec_src)

    return text


def list_paths(root: Path) -> dict[str, Any]:
    """List every numbered experiment path with status and metadata."""
    workspace_dir = root / "workspace"
    paths: list[dict[str, Any]] = []
    if not workspace_dir.exists():
        return {"status": "success", "paths": paths, "paths_count": 0}

    for p in sorted(workspace_dir.iterdir()):
        if not p.is_dir():
            continue
        m = re.match(r"^(\d{2,3})_(.+?)(__DEAD_END)?$", p.name)
        if not m:
            continue
        number = int(m.group(1))
        name = m.group(2)
        is_dead = m.group(3) is not None

        if is_dead:
            status = "dead_end"
        else:
            conc = p / "conclusions.md"
            has_conclusions = conc.exists() and conc.stat().st_size > 100
            has_outputs = any(
                (p / "outputs" / sub).exists()
                and any((p / "outputs" / sub).iterdir())
                for sub in ("reports", "figures", "tables")
                if (p / "outputs" / sub).exists()
            )
            status = "completed" if (has_conclusions and has_outputs) else "active"

        paths.append(
            {
                "path_id": p.name,
                "number": number,
                "name": name,
                "status": status,
                "experiment_dir": str(p.absolute()),
                "has_readme": (p / "README.md").exists(),
                "has_conclusions": (p / "conclusions.md").exists(),
            }
        )

    return {"status": "success", "paths": paths, "paths_count": len(paths)}
