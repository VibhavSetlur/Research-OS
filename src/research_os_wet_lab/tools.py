"""Wet-Lab pack tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from research_os.plugins import register_tool


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


@register_tool(
    "tool_wet_lab_plate_map_render",
    schema={
        "type": "object",
        "properties": {
            "spec_path": {
                "type": "string",
                "description": "YAML file describing the plate layout (rows / columns / wells).",
            },
            "format": {
                "type": "string",
                "enum": ["png", "svg", "both"],
            },
        },
        "required": ["spec_path"],
    },
    description=(
        "Renders a 96- or 384-well plate layout as PNG and/or SVG "
        "from a YAML spec. Visual sanity check that controls (NTC, "
        "blank, positive ctrl) are placed correctly. If matplotlib "
        "isn't available, writes an ASCII grid fallback to "
        "workspace/figures/<stem>_ascii.txt instead."
    ),
)
def plate_map_render(name: str, arguments: dict, root: Path) -> Any:
    spec_path = (root / arguments["spec_path"]).resolve()
    fmt = arguments.get("format", "png")
    if not spec_path.exists():
        return _err(f"spec_path '{arguments['spec_path']}' not found")
    spec = yaml.safe_load(spec_path.read_text()) or {}
    rows = spec.get("rows") or list("ABCDEFGH")
    cols = spec.get("cols") or list(range(1, 13))
    wells = spec.get("wells") or {}
    fig_dir = root / "workspace" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = spec_path.stem
    paths: dict[str, str] = {}

    # Always write an ASCII grid (cheap fallback).
    ascii_lines = [
        "  " + "  ".join(f"{c:>2}" for c in cols)
    ]
    for r in rows:
        cells = []
        for c in cols:
            well_id = f"{r}{c}"
            content = wells.get(well_id, ".")
            cells.append(f"{str(content)[:2]:>2}")
        ascii_lines.append(f"{r} " + "  ".join(cells))
    ascii_path = fig_dir / f"{stem}_ascii.txt"
    ascii_path.write_text("\n".join(ascii_lines))
    paths["ascii"] = str(ascii_path.relative_to(root))

    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(max(8, len(cols)*0.5),
                                        max(4, len(rows)*0.5)))
        for ri, r in enumerate(rows):
            for ci, c in enumerate(cols):
                well_id = f"{r}{c}"
                content = wells.get(well_id, "")
                color = "#cccccc" if not content else "#88aaff"
                ax.add_patch(plt.Circle((ci, len(rows) - ri - 1),
                                        0.4, facecolor=color, edgecolor="black"))
                if content:
                    ax.text(ci, len(rows) - ri - 1, str(content)[:6],
                            ha="center", va="center", fontsize=6)
        ax.set_xlim(-0.7, len(cols) - 0.3)
        ax.set_ylim(-0.7, len(rows) - 0.3)
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([str(c) for c in cols])
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(list(reversed(rows)))
        ax.set_aspect("equal")
        ax.set_title(spec.get("title", stem))
        if fmt in {"png", "both"}:
            png_path = fig_dir / f"{stem}.png"
            fig.savefig(png_path, dpi=150, bbox_inches="tight")
            paths["png"] = str(png_path.relative_to(root))
        if fmt in {"svg", "both"}:
            svg_path = fig_dir / f"{stem}.svg"
            fig.savefig(svg_path, format="svg", bbox_inches="tight")
            paths["svg"] = str(svg_path.relative_to(root))
        plt.close(fig)
    except ImportError:
        pass
    return _ok({"paths": paths, "wells_filled": len(wells), "title": spec.get("title", stem)})


@register_tool(
    "tool_wet_lab_reagent_query",
    schema={
        "type": "object",
        "properties": {
            "supplier": {
                "type": "string",
                "enum": ["sigma_aldrich", "thermofisher", "biorad", "neb", "abcam", "generic"],
            },
            "catalog_number": {"type": "string"},
        },
        "required": ["supplier", "catalog_number"],
    },
    description=(
        "Returns a structured query plan + a write-into-reagents-yaml "
        "stub for one reagent. The pack does NOT hit live supplier "
        "APIs (auth varies wildly + would make the package depend on "
        "credentials); instead it writes a clearly-marked TODO entry "
        "to workspace/<step>/reagents.yaml that the researcher fills "
        "with the COA URL + lot number from the supplier's portal."
    ),
)
def reagent_query(name: str, arguments: dict, root: Path) -> Any:
    supplier = arguments["supplier"]
    cat = arguments["catalog_number"].strip()
    portal = {
        "sigma_aldrich": f"https://www.sigmaaldrich.com/US/en/product/sigma/{cat}",
        "thermofisher": f"https://www.thermofisher.com/order/catalog/product/{cat}",
        "biorad": f"https://www.bio-rad.com/en-us/product/{cat}",
        "neb": f"https://www.neb.com/products/{cat}",
        "abcam": f"https://www.abcam.com/products/primary-antibodies/{cat}.html",
        "generic": f"https://www.google.com/search?q={supplier}+{cat}+coa",
    }.get(supplier, "")
    reagent_dir = root / "workspace" / "reagents"
    reagent_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "supplier": supplier,
        "catalog_number": cat,
        "portal_url": portal,
        "lot_number": "TODO: copy from supplier portal",
        "coa_url": "TODO: link from supplier portal",
        "expiry_date": "TODO: YYYY-MM-DD",
        "received_date": "TODO: YYYY-MM-DD",
        "storage_conditions": "TODO",
        "handling_notes": "TODO",
    }
    entry_path = reagent_dir / f"{supplier}_{cat}.yaml"
    entry_path.write_text(yaml.safe_dump(entry, sort_keys=False))
    return _ok({
        "entry_path": str(entry_path.relative_to(root)),
        "portal_url": portal,
        "advice": (
            "Visit the supplier portal, download the COA, and update "
            "lot_number / coa_url / dates / handling_notes. The "
            "reagent_lot_tracking protocol expects all TODOs resolved "
            "before the assay is logged as reproducible."
        ),
    })


@register_tool(
    "tool_wet_lab_sample_lineage_export",
    schema={
        "type": "object",
        "properties": {
            "lineage_spec_path": {
                "type": "string",
                "description": "YAML file: list of {sample_id, parent_id?, kind, split_method?, derived_from?, assays?}.",
            },
        },
        "required": ["lineage_spec_path"],
    },
    description=(
        "Renders the parent→split→aliquot→readout tree as JSON and "
        "Mermaid. Sample lineage answers 'where did this reading "
        "come from' — every assay readout must trace upward to a "
        "single parent sample. Mermaid output lands at "
        "workspace/<step>/sample_lineage.mermaid."
    ),
)
def sample_lineage_export(name: str, arguments: dict, root: Path) -> Any:
    spec_path = (root / arguments["lineage_spec_path"]).resolve()
    if not spec_path.exists():
        return _err(f"lineage_spec_path '{arguments['lineage_spec_path']}' not found")
    data = yaml.safe_load(spec_path.read_text()) or {}
    if isinstance(data, dict):
        samples = data.get("samples", [])
    else:
        samples = list(data)
    out_dir = spec_path.parent
    json_out = out_dir / "sample_lineage.json"
    json_out.write_text(json.dumps({"samples": samples}, indent=2))
    lines = ["graph TD"]
    for s in samples:
        sid = str(s.get("sample_id", "")).replace("-", "_")
        kind = s.get("kind", "sample")
        lines.append(f'    {sid}["{sid}<br/>{kind}"]')
        parent = s.get("parent_id") or s.get("derived_from")
        if parent:
            pid = str(parent).replace("-", "_")
            lines.append(f"    {pid} --> {sid}")
        for assay in s.get("assays", []) or []:
            aid = f"{sid}_assay_{assay}".replace("-", "_").replace(" ", "_")
            lines.append(f'    {aid}{{{{"{assay}"}}}}')
            lines.append(f"    {sid} --> {aid}")
    mermaid_out = out_dir / "sample_lineage.mermaid"
    mermaid_out.write_text("\n".join(lines) + "\n")
    return _ok({
        "json_path": str(json_out.relative_to(root)),
        "mermaid_path": str(mermaid_out.relative_to(root)),
        "n_samples": len(samples),
    })
