"""Engineering pack tools."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

from research_os.plugins import pack_err as _err, pack_ok as _ok, register_tool


_FMEA_COLUMNS = [
    "id", "function", "failure_mode", "effect", "cause",
    "severity", "occurrence", "detection", "rpn", "mitigation",
]


@register_tool(
    "tool_engineering_fmea_render",
    schema={
        "type": "object",
        "properties": {
            "spec_path": {
                "type": "string",
                "description": "YAML with `items: [...]` where each item has the FMEA columns.",
            },
            "output_stem": {"type": "string"},
        },
        "required": ["spec_path"],
    },
    description=(
        "Renders an FMEA (Failure Mode and Effects Analysis) table "
        "from a YAML spec to CSV + Markdown (+ optional .xlsx if "
        "openpyxl is installed). Computes RPN = severity × occurrence "
        "× detection per row, sorts by RPN descending, flags rows "
        "with RPN >= 100 as high-priority. Output stem defaults to "
        "the spec_path basename."
    ),
)
def fmea_render(name: str, arguments: dict, root: Path) -> Any:
    spec_path = (root / arguments["spec_path"]).resolve()
    if not spec_path.exists():
        return _err(f"spec_path '{arguments['spec_path']}' not found")
    data = yaml.safe_load(spec_path.read_text()) or {}
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return _err("FMEA spec must contain a list of items")
    for it in items:
        try:
            rpn = int(it.get("severity", 0)) * int(it.get("occurrence", 0)) * int(it.get("detection", 0))
        except (TypeError, ValueError):
            rpn = 0
        it["rpn"] = rpn
    items.sort(key=lambda x: -int(x.get("rpn", 0)))

    stem = (arguments.get("output_stem") or spec_path.stem).strip()
    out_dir = root / "workspace" / "engineering" / "fmea"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{stem}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FMEA_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for it in items:
            w.writerow(it)

    md_lines = [f"# FMEA — {stem}", "", "| " + " | ".join(_FMEA_COLUMNS) + " |",
                "|" + "|".join(["---"] * len(_FMEA_COLUMNS)) + "|"]
    for it in items:
        high = int(it.get("rpn", 0)) >= 100
        # High-priority rows render every cell bold. The old single-row
        # `.replace("|", ...)` corrupted the leading pipe (both replaces hit
        # it); build the bolded row from cell values instead.
        cells = [str(it.get(c, "")) for c in _FMEA_COLUMNS]
        if high:
            cells = [f"**{c}**" for c in cells]
        md_lines.append("| " + " | ".join(cells) + " |")
    md_path = out_dir / f"{stem}.md"
    md_path.write_text("\n".join(md_lines) + "\n")

    xlsx_path: Path | None = None
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FMEA"
        ws.append(_FMEA_COLUMNS)
        for it in items:
            ws.append([it.get(c, "") for c in _FMEA_COLUMNS])
        xlsx_path = out_dir / f"{stem}.xlsx"
        wb.save(xlsx_path)
    except ImportError as exc:
        import logging
        logging.getLogger("research_os_engineering.tools").debug(
            "openpyxl unavailable; skipping .xlsx: %s", exc
        )

    high_priority = [it for it in items if int(it.get("rpn", 0)) >= 100]
    paths = {"csv": str(csv_path.relative_to(root)),
             "md": str(md_path.relative_to(root))}
    if xlsx_path is not None:
        paths["xlsx"] = str(xlsx_path.relative_to(root))
    return _ok({
        "paths": paths,
        "n_items": len(items),
        "high_priority_count": len(high_priority),
        "high_priority_ids": [it.get("id", "") for it in high_priority],
    })


@register_tool(
    "tool_engineering_fault_tree_render",
    schema={
        "type": "object",
        "properties": {
            "spec_path": {
                "type": "string",
                "description": "YAML: {top_event, nodes: [{id, label, kind: 'and'|'or'|'basic', children?: [id]}]}",
            },
        },
        "required": ["spec_path"],
    },
    description=(
        "Renders a fault tree as Mermaid + (optionally) SVG. "
        "Top event + AND/OR gates + basic events. Used in safety "
        "analyses to decompose a top-level failure into contributing "
        "events. Each node is one of: 'and' (all children must "
        "occur), 'or' (any child suffices), 'basic' (leaf failure)."
    ),
)
def fault_tree_render(name: str, arguments: dict, root: Path) -> Any:
    spec_path = (root / arguments["spec_path"]).resolve()
    if not spec_path.exists():
        return _err(f"spec_path '{arguments['spec_path']}' not found")
    spec = yaml.safe_load(spec_path.read_text()) or {}
    top = spec.get("top_event") or "top"
    nodes = spec.get("nodes") or []
    out_dir = root / "workspace" / "engineering" / "fta"
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = ["graph TD"]
    lines.append(f'    TOP(["{top}"])')
    for node in nodes:
        nid = node.get("id", "")
        label = node.get("label", nid)
        kind = node.get("kind", "basic")
        if kind == "and":
            lines.append(f'    {nid}[/AND<br/>{label}\\]')
        elif kind == "or":
            lines.append(f'    {nid}{{OR<br/>{label}}}')
        else:
            lines.append(f'    {nid}(({label}))')
        for child in node.get("children", []) or []:
            lines.append(f"    {child} --> {nid}")
    # Wire top-event to root nodes (those without parents).
    parented = {
        c for node in nodes for c in (node.get("children", []) or [])
    }
    for node in nodes:
        if node.get("id", "") not in parented:
            lines.append(f"    {node.get('id', '')} --> TOP")
    mermaid_path = out_dir / f"{spec_path.stem}.mermaid"
    mermaid_path.write_text("\n".join(lines) + "\n")
    return _ok({
        "mermaid_path": str(mermaid_path.relative_to(root)),
        "n_nodes": len(nodes),
        "top_event": top,
    })


@register_tool(
    "tool_engineering_requirements_matrix",
    schema={
        "type": "object",
        "properties": {
            "spec_path": {
                "type": "string",
                "description": "YAML: {requirements: [{id, text, design_elements: [...], test_cases: [...]}], test_results: {test_id: 'pass'|'fail'|'pending'}}",
            },
        },
        "required": ["spec_path"],
    },
    description=(
        "Bidirectional requirements traceability matrix: "
        "requirements ↔ design elements ↔ test cases ↔ test results. "
        "Outputs Markdown + (optionally) Excel. Flags any "
        "requirement not linked to a test case, or any test case "
        "not linked to a requirement (orphan tests)."
    ),
)
def requirements_matrix(name: str, arguments: dict, root: Path) -> Any:
    spec_path = (root / arguments["spec_path"]).resolve()
    if not spec_path.exists():
        return _err(f"spec_path '{arguments['spec_path']}' not found")
    spec = yaml.safe_load(spec_path.read_text()) or {}
    reqs = spec.get("requirements") or []
    results = spec.get("test_results") or {}

    out_dir = root / "workspace" / "engineering" / "traceability"
    out_dir.mkdir(parents=True, exist_ok=True)

    orphan_reqs = [r.get("id", "") for r in reqs if not r.get("test_cases")]
    all_test_ids: set = set()
    for r in reqs:
        for tc in r.get("test_cases", []) or []:
            all_test_ids.add(tc)
    orphan_tests = sorted(set(results) - all_test_ids)

    md = io.StringIO()
    md.write(f"# Requirements traceability matrix — {spec_path.stem}\n\n")
    md.write("| Req ID | Requirement | Design elements | Test cases | Results |\n")
    md.write("|---|---|---|---|---|\n")
    for r in reqs:
        ds = ", ".join(r.get("design_elements", []) or []) or "_(none)_"
        tcs = r.get("test_cases", []) or []
        tc_str = ", ".join(tcs) if tcs else "_(none)_"
        res_str = ", ".join(f"{tc}:{results.get(tc, 'pending')}" for tc in tcs) if tcs else "—"
        md.write(f"| {r.get('id','')} | {r.get('text','')} | {ds} | {tc_str} | {res_str} |\n")
    md.write("\n## Orphans\n\n")
    md.write(f"- Requirements with no test case: {orphan_reqs or '_(none)_'}\n")
    md.write(f"- Tests not linked to any requirement: {orphan_tests or '_(none)_'}\n")
    md_path = out_dir / f"{spec_path.stem}.md"
    md_path.write_text(md.getvalue())

    xlsx_path: Path | None = None
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Traceability"
        ws.append(["Req ID", "Requirement", "Design elements", "Test cases", "Results"])
        for r in reqs:
            tcs = r.get("test_cases", []) or []
            ws.append([
                r.get("id", ""), r.get("text", ""),
                ", ".join(r.get("design_elements", []) or []),
                ", ".join(tcs),
                ", ".join(f"{tc}:{results.get(tc, 'pending')}" for tc in tcs),
            ])
        xlsx_path = out_dir / f"{spec_path.stem}.xlsx"
        wb.save(xlsx_path)
    except ImportError as exc:
        import logging
        logging.getLogger("research_os_engineering.tools").debug(
            "openpyxl unavailable; skipping .xlsx: %s", exc
        )

    paths = {"md": str(md_path.relative_to(root))}
    if xlsx_path is not None:
        paths["xlsx"] = str(xlsx_path.relative_to(root))
    return _ok({
        "paths": paths,
        "n_requirements": len(reqs),
        "n_test_results": len(results),
        "orphan_requirements": orphan_reqs,
        "orphan_tests": orphan_tests,
    })
