"""REDCap clinical data capture export adapter.

Detects:
    * CSV exports with a ``record_id`` column plus any of
      ``redcap_event_name`` / ``redcap_repeat_instrument`` /
      ``redcap_repeat_instance`` (the longitudinal / repeating-instrument
      shape that REDCap stamps onto every row).
    * Data dictionary CSVs whose header includes the canonical REDCap
      columns ``Variable / Field Name``, ``Form Name``, ``Field Type``,
      ``Choices, Calculations, OR Slider Labels``, ``Identifier?``,
      ``Text Validation Type OR Show Slider Number`` etc.

Extracts:
    * The data dictionary file path + the export file path (if both shapes
      are present).
    * ``longitudinal`` (bool) inferred from the presence of
      ``redcap_event_name`` in the export.
    * Distinct event count + instrument count.
    * Per-field metadata: ``name``, ``label``, ``type``, ``required``,
      ``identifier`` (PHI flag), ``validation``, ``branching``, ``choices``.
    * Sample N (distinct ``record_id`` count in the export).
    * ``phi_warnings`` — one entry per field marked ``Identifier? = y``,
      so downstream audits can refuse to ship raw data without a DUA.

Optional tools:
    * tool_redcap_schema_describe(step_id) — renders the extracted schema
      as a human-readable Markdown summary at
      ``workspace/<step>/data/redcap_schema_summary.md``.

Limitations (also surfaced in the returned payload under ``_notes``):
    * Detection is filesystem-only and header-only — we sniff the first
      line of each CSV; we do not stream the full file at detect() time.
    * Choices are parsed with the canonical REDCap ``|``-separated
      ``code, label`` shape; non-standard separators (semicolons,
      embedded newlines mid-cell) may be approximated.
    * Branching logic is captured verbatim as a string; we do NOT
      evaluate the expression.
    * If only an export is present (no dictionary), per-field ``label`` /
      ``validation`` / ``branching`` / ``choices`` will be empty and
      ``type`` will be inferred as ``unknown``.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    register_adapter,
)


__version__ = "1.8.0"


# ── detection ─────────────────────────────────────────────────────────


# Export-shape signals: a row-stamping column REDCap adds to every export.
_EXPORT_SIGNAL_COLUMNS = {
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
}

# Dictionary-shape signals: canonical column headers from a REDCap
# data dictionary CSV. We accept the minimal pair (variable + form)
# to tolerate exports that drop the trailing optional columns.
_DICT_REQUIRED_COLUMNS = {
    "variable / field name",
    "form name",
}
_DICT_BONUS_COLUMNS = {
    "field type",
    "field label",
    "choices, calculations, or slider labels",
    "identifier?",
    "text validation type or show slider number",
    "required field?",
    "branching logic (show field only if...)",
}


def _candidate_csvs(root: Path) -> list[Path]:
    """Return CSV files in workspace/ and the project root worth sniffing."""
    csvs: list[Path] = []
    workspace = root / "workspace"
    seen: set[Path] = set()
    for d in (workspace, root / "inputs", root):
        if not d.exists():
            continue
        if d == root:
            # Project root: only scan top-level, not recursively (would
            # pull in node_modules / .venv / etc.).
            iterator = (p for p in d.iterdir() if p.is_file())
        else:
            iterator = d.rglob("*")
        for p in iterator:
            if not p.is_file():
                continue
            if p.suffix.lower() != ".csv":
                continue
            resolved = p.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            csvs.append(p)
    return csvs


def _read_header(path: Path) -> list[str] | None:
    """Read just the header row. Return None on any read failure."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
            reader = csv.reader(fh)
            return next(reader, None)
    except Exception:
        return None


def _classify_csv(path: Path) -> str | None:
    """Return 'export' | 'dictionary' | None."""
    header = _read_header(path)
    if not header:
        return None
    lowered = {h.strip().lower() for h in header if h}
    if "record_id" in lowered and lowered & _EXPORT_SIGNAL_COLUMNS:
        return "export"
    if _DICT_REQUIRED_COLUMNS.issubset(lowered):
        return "dictionary"
    return None


def detect(root: Path) -> bool:
    for path in _candidate_csvs(root):
        if _classify_csv(path) is not None:
            return True
    return False


# ── extraction ────────────────────────────────────────────────────────


_TRUE_TOKENS = {"y", "yes", "true", "1"}


def _is_truthy(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() in _TRUE_TOKENS


def _parse_choices(raw: str | None) -> list[dict[str, str]]:
    """Parse REDCap-style ``code, label | code, label`` strings."""
    if not raw:
        return []
    choices: list[dict[str, str]] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:
            code, label = chunk.split(",", 1)
            choices.append({"code": code.strip(), "label": label.strip()})
        else:
            choices.append({"code": chunk, "label": chunk})
    return choices


def _parse_dictionary(path: Path) -> list[dict[str, Any]]:
    """Parse a REDCap data dictionary CSV into per-field metadata."""
    fields: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
            reader = csv.DictReader(fh)
            # Build a case-insensitive lookup for column names — REDCap
            # exports vary in capitalisation across versions.
            if not reader.fieldnames:
                return []
            col_map = {(c or "").strip().lower(): c for c in reader.fieldnames}

            def col(*aliases: str) -> str | None:
                for a in aliases:
                    if a in col_map:
                        return col_map[a]
                return None

            c_name = col("variable / field name", "variable/field name")
            c_form = col("form name")
            c_label = col("field label")
            c_type = col("field type")
            c_choices = col(
                "choices, calculations, or slider labels",
                "choices, calculations, or slider labels ",
            )
            c_validation = col(
                "text validation type or show slider number",
                "text validation type",
            )
            c_required = col("required field?", "required field")
            c_identifier = col("identifier?", "identifier")
            c_branching = col(
                "branching logic (show field only if...)",
                "branching logic",
            )

            for row in reader:
                if not row:
                    continue
                name = (row.get(c_name) or "").strip() if c_name else ""
                if not name:
                    continue
                fields.append({
                    "name": name,
                    "form": (row.get(c_form) or "").strip() if c_form else "",
                    "label": (row.get(c_label) or "").strip() if c_label else "",
                    "type": (row.get(c_type) or "").strip().lower() if c_type else "unknown",
                    "validation": (row.get(c_validation) or "").strip() if c_validation else "",
                    "required": _is_truthy(row.get(c_required)) if c_required else False,
                    "identifier": _is_truthy(row.get(c_identifier)) if c_identifier else False,
                    "branching": (row.get(c_branching) or "").strip() if c_branching else "",
                    "choices": _parse_choices(row.get(c_choices)) if c_choices else [],
                })
    except Exception:
        return fields
    return fields


def _summarise_export(path: Path) -> dict[str, Any]:
    """Pull longitudinal flag, event/instrument counts, sample N from an export."""
    longitudinal = False
    events: set[str] = set()
    instruments: set[str] = set()
    record_ids: set[str] = set()
    columns: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return {
                    "longitudinal": False,
                    "events": [],
                    "instruments": [],
                    "sample_n": 0,
                    "columns": [],
                }
            columns = list(reader.fieldnames)
            lowered = {(c or "").strip().lower(): c for c in columns}
            longitudinal = "redcap_event_name" in lowered
            c_event = lowered.get("redcap_event_name")
            c_instr = lowered.get("redcap_repeat_instrument")
            c_record = lowered.get("record_id")
            for row in reader:
                if c_record:
                    rid = (row.get(c_record) or "").strip()
                    if rid:
                        record_ids.add(rid)
                if c_event:
                    ev = (row.get(c_event) or "").strip()
                    if ev:
                        events.add(ev)
                if c_instr:
                    inst = (row.get(c_instr) or "").strip()
                    if inst:
                        instruments.add(inst)
    except Exception:
        pass
    return {
        "longitudinal": longitudinal,
        "events": sorted(events),
        "instruments": sorted(instruments),
        "sample_n": len(record_ids),
        "columns": columns,
    }


def extract(root: Path, step_id: str | None = None) -> dict:
    csvs = _candidate_csvs(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        csvs = [c for c in csvs if str(c.resolve()).startswith(str(step_prefix))]

    dictionary_path: Path | None = None
    export_path: Path | None = None
    for path in csvs:
        kind = _classify_csv(path)
        if kind == "dictionary" and dictionary_path is None:
            dictionary_path = path
        elif kind == "export" and export_path is None:
            export_path = path
        if dictionary_path and export_path:
            break

    if not dictionary_path and not export_path:
        return {
            "data_dictionary_file": None,
            "export_file": None,
            "longitudinal": False,
            "events": [],
            "instruments": [],
            "fields": [],
            "sample_n": 0,
            "phi_warnings": [],
            "_notes": [
                "No REDCap-shaped CSV found at extract() time.",
            ],
        }

    fields_full: list[dict[str, Any]] = []
    if dictionary_path:
        fields_full = _parse_dictionary(dictionary_path)

    export_summary = (
        _summarise_export(export_path)
        if export_path
        else {"longitudinal": False, "events": [], "instruments": [], "sample_n": 0, "columns": []}
    )

    # If only an export is present, synthesise minimal field stubs from
    # the export column header.
    if not fields_full and export_summary["columns"]:
        reserved = {"record_id", *_EXPORT_SIGNAL_COLUMNS}
        for c in export_summary["columns"]:
            cl = (c or "").strip()
            if not cl or cl.lower() in reserved:
                continue
            fields_full.append({
                "name": cl,
                "form": "",
                "label": "",
                "type": "unknown",
                "validation": "",
                "required": False,
                "identifier": False,
                "branching": "",
                "choices": [],
            })

    # If dictionary supplied forms but the export did not provide an
    # instruments column, fall back to the distinct ``form`` values.
    instruments = export_summary["instruments"]
    if not instruments and fields_full:
        instruments = sorted({(f.get("form") or "") for f in fields_full if f.get("form")})

    phi_warnings: list[dict[str, str]] = []
    for f in fields_full:
        if f.get("identifier"):
            phi_warnings.append({
                "field": f["name"],
                "form": f.get("form", ""),
                "label": f.get("label", ""),
                "warning": "Field flagged Identifier=y in REDCap dictionary — likely PHI; do not share raw export without DUA / IRB review.",
            })

    # Project the spec's per-field surface (name/type/required/identifier).
    # We also keep the rich metadata under ``fields_detail`` for the
    # optional describe tool — the YAML payload stays compact for the
    # runner but downstream tools get the full picture.
    fields_summary = [
        {
            "name": f["name"],
            "type": f.get("type", "unknown"),
            "required": bool(f.get("required", False)),
            "identifier": bool(f.get("identifier", False)),
        }
        for f in fields_full
    ]

    notes: list[str] = []
    if export_path and not dictionary_path:
        notes.append(
            "Export found without data dictionary — field labels, types, "
            "validation, branching, choices, and identifier flags could not "
            "be recovered. PHI warnings under-report."
        )
    if dictionary_path and not export_path:
        notes.append(
            "Data dictionary found without an export — sample_n is 0 and "
            "longitudinal/instrument counts reflect the dictionary, not "
            "observed data."
        )
    notes.append(
        "Detection is filesystem + header-only; no REDCap API calls are made. "
        "Choices parsed as ``code, label`` pairs separated by ``|``."
    )
    notes.append(
        "Branching logic is captured verbatim; the expression is NOT evaluated."
    )

    return {
        "data_dictionary_file": str(dictionary_path.relative_to(root)) if dictionary_path else None,
        "export_file": str(export_path.relative_to(root)) if export_path else None,
        "longitudinal": export_summary["longitudinal"],
        "events": export_summary["events"],
        "instruments": instruments,
        "fields": fields_summary,
        "fields_detail": fields_full,
        "sample_n": export_summary["sample_n"],
        "phi_warnings": phi_warnings,
        "_notes": notes,
    }


def describe() -> dict:
    return {
        "name": "redcap",
        "version": __version__,
        "shapes_supported": ["data_dictionary_csv", "longitudinal_export_csv", "cross_sectional_export_csv"],
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


def _render_markdown(payload: dict) -> str:
    lines: list[str] = ["# REDCap schema summary", ""]
    lines.append(f"- Data dictionary: `{payload.get('data_dictionary_file') or '—'}`")
    lines.append(f"- Export file: `{payload.get('export_file') or '—'}`")
    lines.append(f"- Longitudinal: **{payload.get('longitudinal')}**")
    lines.append(f"- Distinct events: {len(payload.get('events') or [])}")
    lines.append(f"- Distinct instruments: {len(payload.get('instruments') or [])}")
    lines.append(f"- Sample N (distinct record_id): {payload.get('sample_n', 0)}")
    lines.append(f"- Field count: {len(payload.get('fields') or [])}")
    lines.append("")

    events = payload.get("events") or []
    if events:
        lines.append("## Events")
        for ev in events:
            lines.append(f"- {ev}")
        lines.append("")

    instruments = payload.get("instruments") or []
    if instruments:
        lines.append("## Instruments")
        for inst in instruments:
            lines.append(f"- {inst}")
        lines.append("")

    phi = payload.get("phi_warnings") or []
    if phi:
        lines.append("## PHI warnings")
        lines.append("")
        lines.append("Fields flagged `Identifier? = y` in the REDCap data dictionary. "
                     "Do NOT share raw export without DUA / IRB review.")
        lines.append("")
        lines.append("| Field | Form | Label |")
        lines.append("|---|---|---|")
        for w in phi:
            lines.append(f"| `{w['field']}` | {w.get('form', '')} | {w.get('label', '')} |")
        lines.append("")

    fields_detail = payload.get("fields_detail") or payload.get("fields") or []
    if fields_detail:
        lines.append("## Fields")
        lines.append("")
        lines.append("| Name | Type | Required | Identifier | Validation | Form | Choices |")
        lines.append("|---|---|---|---|---|---|---|")
        for f in fields_detail:
            choices = f.get("choices") or []
            choices_str = ", ".join(c.get("label", c.get("code", "")) for c in choices) if choices else ""
            # Trim very long choice lists for readability.
            if len(choices_str) > 80:
                choices_str = choices_str[:77] + "…"
            lines.append(
                f"| `{f.get('name', '')}` | {f.get('type', '')} | "
                f"{'yes' if f.get('required') else ''} | "
                f"{'yes' if f.get('identifier') else ''} | "
                f"{f.get('validation', '')} | {f.get('form', '')} | {choices_str} |"
            )
        lines.append("")

    notes = payload.get("_notes") or []
    if notes:
        lines.append("## Notes / limitations")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines)


def _handle_schema_describe(name: str, arguments: dict, root: Path) -> Any:
    step_id = (arguments.get("step_id") or "").strip() or None
    payload = extract(root, step_id=step_id)
    if not payload.get("data_dictionary_file") and not payload.get("export_file"):
        return _ok({
            "status": "warning",
            "message": "No REDCap dictionary or export found; nothing to describe.",
        })

    # Decide where to write the summary. If step_id is supplied, use the
    # step's data/ dir; otherwise fall back to workspace/redcap/.
    if step_id:
        out_dir = root / "workspace" / step_id / "data"
    else:
        out_dir = root / "workspace" / "redcap"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return _err(f"Cannot create output directory {out_dir}: {e}")

    out_path = out_dir / "redcap_schema_summary.md"
    md = _render_markdown(payload)
    try:
        out_path.write_text(md, encoding="utf-8")
    except Exception as e:
        return _err(f"Failed to write {out_path}: {e}")

    return _ok({
        "summary_path": str(out_path.relative_to(root)),
        "longitudinal": payload.get("longitudinal"),
        "field_count": len(payload.get("fields") or []),
        "phi_field_count": len(payload.get("phi_warnings") or []),
        "events": payload.get("events") or [],
        "instruments": payload.get("instruments") or [],
        "sample_n": payload.get("sample_n", 0),
        "note": "Rendered the REDCap schema as Markdown at the path above. "
                "Pair with a PHI-handling review before sharing the underlying export.",
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (re.compile(r"redcap"), "REDCap export present"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="redcap",
        version=__version__,
        description="REDCap clinical data capture export + dictionary provenance extractor.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_redcap_schema_describe",
                handler=_handle_schema_describe,
                schema={
                    "type": "object",
                    "properties": {
                        "step_id": {
                            "type": "string",
                            "description": "Optional step_id to scope extraction to workspace/<step_id>/.",
                        },
                    },
                    "description": "Render the detected REDCap schema (events, instruments, fields, PHI warnings) as a human-readable Markdown summary written to workspace/<step>/data/redcap_schema_summary.md (or workspace/redcap/ if no step_id is supplied). Filesystem-only; never calls the REDCap API.",
                },
            ),
        ),
    )
