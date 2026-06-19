"""Wet-Lab pack tools."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from research_os.plugins import pack_err as _err, pack_ok as _ok, register_tool


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
    except ImportError as exc:
        import logging
        logging.getLogger("research_os_wet_lab.tools").debug(
            "matplotlib unavailable; ASCII fallback only: %s", exc
        )
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
        "Returns a structured query plan + appends a write-into-reagents "
        "stub for one reagent into the accumulating ledger "
        "workspace/reagents/reagents.yaml (keyed by supplier:catalog). "
        "The pack does NOT hit live supplier APIs (auth varies wildly + "
        "would make the package depend on credentials); instead each "
        "entry carries clearly-marked TODOs the researcher fills with "
        "the COA URL + lot number from the supplier's portal."
    ),
)
def reagent_query(name: str, arguments: dict, root: Path) -> Any:
    supplier = (arguments.get("supplier") or "").strip()
    cat = (arguments.get("catalog_number") or "").strip()
    if not supplier:
        return _err("supplier is required")
    if not cat:
        return _err("catalog_number is required")
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
    # Accumulate into one ledger keyed by supplier:catalog. Avoids the old
    # per-reagent <supplier>_<cat>.yaml filename (which broke when a catalog
    # number contained '/'), and matches the reagent_lot_tracking protocol's
    # "one accumulating reagents.yaml" model. The key holds the raw catalog
    # number verbatim — no path is ever built from it.
    ledger_path = reagent_dir / "reagents.yaml"
    ledger: dict = {}
    if ledger_path.exists():
        try:
            loaded = yaml.safe_load(ledger_path.read_text())
            if isinstance(loaded, dict):
                ledger = loaded
        except Exception as exc:
            import logging
            logging.getLogger("research_os_wet_lab.tools").debug(
                "could not parse existing reagents.yaml; starting fresh: %s", exc
            )
    key = f"{supplier}:{cat}"
    ledger[key] = entry
    ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False))
    return _ok({
        "ledger_path": str(ledger_path.relative_to(root)),
        "reagent_key": key,
        "portal_url": portal,
        "n_reagents": len(ledger),
        "advice": (
            "Visit the supplier portal, download the COA, and update "
            "lot_number / coa_url / dates / handling_notes for this entry. "
            "The reagent_lot_tracking protocol expects all TODOs resolved "
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
        "single parent sample. Output lands in "
        "workspace/lineage/sample_lineage.{json,mermaid}."
    ),
)
def sample_lineage_export(name: str, arguments: dict, root: Path) -> Any:
    spec_rel = (arguments.get("lineage_spec_path") or "").strip()
    if not spec_rel:
        return _err("lineage_spec_path is required")
    spec_path = (root / spec_rel).resolve()
    if not spec_path.exists():
        return _err(f"lineage_spec_path '{spec_rel}' not found")
    data = yaml.safe_load(spec_path.read_text()) or {}
    if isinstance(data, dict):
        samples = data.get("samples", [])
    else:
        samples = list(data)
    # Write to a deterministic workspace location, not the spec's parent —
    # otherwise a spec under inputs/ would land its output under inputs/.
    out_dir = root / "workspace" / "lineage"
    out_dir.mkdir(parents=True, exist_ok=True)
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


# Per-instrument-family parameter skeletons for the run log. The values are
# TODO placeholders the operator fills; the KEYS are the reproducibility floor
# the instrument_run_log protocol + reproducibility audit expect.
_FAMILY_PARAM_FIELDS = {
    "cytometry": ["pmt_voltages", "threshold", "compensation_matrix_ref",
                  "sample_flow_rate", "events_to_acquire", "stopping_gate"],
    "qpcr": ["cycle_program", "reference_dye", "baseline_method",
             "threshold_method", "plate_map_version"],
    "sequencing": ["read_length", "flowcell_id", "kit_lot",
                   "loading_concentration", "phix_spike_pct",
                   "cluster_density_or_pore_occupancy"],
    "mass_spec": ["method_file_sha256", "scan_range_mz", "resolution",
                  "collision_energy", "lock_mass", "column_id",
                  "mobile_phase_lot", "gradient_program"],
    "microscopy": ["objective", "NA", "immersion", "exposure_per_channel",
                   "laser_power_per_channel", "pinhole_au", "z_step_um",
                   "pixel_size_um", "tile_overlap_pct"],
    "plate_reader": ["read_mode", "wavelengths", "gain", "read_height",
                     "shake_protocol", "plate_map_version"],
}


@register_tool(
    "tool_wet_lab_run_log_init",
    schema={
        "type": "object",
        "properties": {
            "instrument_family": {
                "type": "string",
                "enum": ["cytometry", "qpcr", "sequencing", "mass_spec",
                         "microscopy", "plate_reader"],
            },
            "step_id": {
                "type": "string",
                "description": "Optional NN_<slug> step; defaults to a top-level runs/ dir.",
            },
            "run_label": {"type": "string", "description": "Short human label for the run."},
        },
        "required": ["instrument_family"],
    },
    description=(
        "Stub a structured instrument run-log YAML for the given instrument "
        "family at workspace/<step>/runs/<family>_<run_label>.yaml (or a "
        "top-level runs/ dir). Pre-fills the family-appropriate parameter "
        "field set + capture timestamp with TODO placeholders the operator "
        "fills. Step 1 of the instrument_run_log protocol."
    ),
)
def run_log_init(name: str, arguments: dict, root: Path) -> Any:
    import datetime as _dt
    family = (arguments.get("instrument_family") or "").strip()
    if family not in _FAMILY_PARAM_FIELDS:
        return _err(
            f"instrument_family must be one of {sorted(_FAMILY_PARAM_FIELDS)}; got {family!r}"
        )
    step_id = (arguments.get("step_id") or "").strip()
    label = (arguments.get("run_label") or "").strip()
    safe_label = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{family}_{safe_label or ts}"
    base = root / "workspace"
    runs_dir = (base / step_id / "runs") if step_id else (base / "runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / f"{stem}.yaml"
    stub = {
        "instrument_family": family,
        "run_label": label or stem,
        "logged_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "operator_initials": "TODO",
        "logged_by": "TODO",
        "instrument_id": "TODO",
        "last_calibration_date": "TODO: YYYY-MM-DD or 'skipped' + reason",
        "last_qc_pass_date": "TODO: YYYY-MM-DD or 'skipped' + reason",
        "parameter_block": {f: "TODO" for f in _FAMILY_PARAM_FIELDS[family]},
        "raw_files": [],
        "sample_ids": [],
        "operator_notes": "",
        "qc_summary": {"status": "TODO: pass/warn/fail"},
    }
    log_path.write_text(yaml.safe_dump(stub, sort_keys=False))
    return _ok({
        "run_log_path": str(log_path.relative_to(root)),
        "instrument_family": family,
        "fields_to_fill": _FAMILY_PARAM_FIELDS[family],
        "advice": (
            "Fill every TODO while the run is fresh. Register each raw file "
            "with tool_wet_lab_checksum_raw. Family-specific post-run QC "
            "(bead CV, NTC, Q30, lock-mass, focus drift) stays a manual step — "
            "parse the instrument's own QC output into qc_summary."
        ),
    })


@register_tool(
    "tool_wet_lab_checksum_raw",
    schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Raw output file to checksum."},
            "run_log_path": {
                "type": "string",
                "description": "Optional run-log YAML to append the raw_files entry to.",
            },
        },
        "required": ["file_path"],
    },
    description=(
        "Compute the SHA-256 + size of a raw instrument output file (never "
        "trust an operator-typed checksum) and, if run_log_path is given, "
        "append the {path, sha256, size_bytes} entry to that run log's "
        "raw_files list. Streams the file so large sequencing/imaging outputs "
        "don't load into memory."
    ),
)
def checksum_raw(name: str, arguments: dict, root: Path) -> Any:
    file_rel = (arguments.get("file_path") or "").strip()
    if not file_rel:
        return _err("file_path is required")
    target = (root / file_rel).resolve()
    if not target.exists() or not target.is_file():
        return _err(f"file_path '{file_rel}' not found")
    h = hashlib.sha256()
    size = 0
    try:
        with target.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
                size += len(chunk)
    except OSError as exc:
        return _err(f"could not read '{file_rel}': {exc}")
    entry = {
        "raw_file_path": file_rel,
        "raw_file_sha256": h.hexdigest(),
        "raw_file_size_bytes": size,
        "raw_file_format": target.suffix.lstrip(".").lower() or "unknown",
    }
    log_rel = (arguments.get("run_log_path") or "").strip()
    appended_to = None
    if log_rel:
        log_path = (root / log_rel).resolve()
        if not log_path.exists():
            return _err(f"run_log_path '{log_rel}' not found")
        try:
            log = yaml.safe_load(log_path.read_text()) or {}
        except Exception as exc:
            return _err(f"could not parse run log '{log_rel}': {exc}")
        if not isinstance(log, dict):
            return _err(f"run log '{log_rel}' is not a mapping")
        raws = log.get("raw_files")
        if not isinstance(raws, list):
            raws = []
        # de-dup by path: replace any existing entry for the same file
        raws = [r for r in raws if not (isinstance(r, dict) and r.get("raw_file_path") == file_rel)]
        raws.append(entry)
        log["raw_files"] = raws
        log_path.write_text(yaml.safe_dump(log, sort_keys=False))
        appended_to = log_rel
    return _ok({**entry, "appended_to": appended_to})
