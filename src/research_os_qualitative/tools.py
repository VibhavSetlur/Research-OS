"""Qualitative pack tools.

Two tools:
    * tool_qualitative_codebook_diff       — versioned codebook diff + Cohen's kappa per code
    * tool_qualitative_quote_provenance    — quote → participant ID + timestamp + interview line
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _load_codebook(path: Path) -> dict:
    """Parse a codebook from YAML or JSON. Return {code_id: {...}}."""
    if not path.exists():
        return {}
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text) or {}
    elif path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported codebook format: {path.suffix}")
    if isinstance(data, list):
        # list-of-dicts → keyed by 'id'
        return {entry.get("id", f"row_{i}"): entry for i, entry in enumerate(data)}
    if isinstance(data, dict):
        if "codes" in data and isinstance(data["codes"], list):
            return {
                c.get("id", f"row_{i}"): c
                for i, c in enumerate(data["codes"])
            }
        return data
    return {}


def _cohens_kappa(p_o: float, p_e: float) -> float:
    """Cohen's kappa from observed and expected agreement."""
    if 1 - p_e == 0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


@register_tool(
    "tool_qualitative_codebook_diff",
    schema={
        "type": "object",
        "properties": {
            "codebook_v1": {
                "type": "string",
                "description": "Path under workspace/codebooks/ to the earlier codebook (YAML or JSON).",
            },
            "codebook_v2": {
                "type": "string",
                "description": "Path under workspace/codebooks/ to the later codebook.",
            },
            "applied_codes_v1": {
                "type": "string",
                "description": "Optional: path to a JSON file of {segment_id: [code_id,...]} for round 1 coding (for kappa).",
            },
            "applied_codes_v2": {
                "type": "string",
                "description": "Optional: path to a JSON file of {segment_id: [code_id,...]} for round 2 coding.",
            },
        },
        "required": ["codebook_v1", "codebook_v2"],
    },
    description=(
        "Diff two versions of a qualitative codebook + (optionally) "
        "compute per-code Cohen's kappa from two rounds of applied "
        "coding. Reports added / removed / renamed / merged / split "
        "codes; flags codes whose kappa dropped below 0.60. Writes "
        "workspace/codebooks/diff_v{N}_to_v{M}.md."
    ),
)
def codebook_diff(name: str, arguments: dict, root: Path) -> Any:
    v1 = _load_codebook(root / arguments["codebook_v1"])
    v2 = _load_codebook(root / arguments["codebook_v2"])
    added = sorted(set(v2) - set(v1))
    removed = sorted(set(v1) - set(v2))
    kept = sorted(set(v1) & set(v2))
    renamed: list[tuple[str, str, str]] = []  # (code_id, v1.label, v2.label)
    for code_id in kept:
        l1 = (v1[code_id].get("label") if isinstance(v1[code_id], dict) else None)
        l2 = (v2[code_id].get("label") if isinstance(v2[code_id], dict) else None)
        if l1 and l2 and l1 != l2:
            renamed.append((code_id, l1, l2))

    kappas: dict[str, float] = {}
    low_kappa: list[str] = []
    if arguments.get("applied_codes_v1") and arguments.get("applied_codes_v2"):
        a1 = json.loads((root / arguments["applied_codes_v1"]).read_text())
        a2 = json.loads((root / arguments["applied_codes_v2"]).read_text())
        all_segments = sorted(set(a1) | set(a2))
        for code_id in kept:
            agree = total = 0
            v1_yes = v2_yes = 0
            for seg in all_segments:
                in1 = code_id in (a1.get(seg) or [])
                in2 = code_id in (a2.get(seg) or [])
                v1_yes += int(in1)
                v2_yes += int(in2)
                if in1 == in2:
                    agree += 1
                total += 1
            if total == 0:
                continue
            p_o = agree / total
            p_yes1 = v1_yes / total
            p_yes2 = v2_yes / total
            p_e = p_yes1 * p_yes2 + (1 - p_yes1) * (1 - p_yes2)
            kappa = round(_cohens_kappa(p_o, p_e), 3)
            kappas[code_id] = kappa
            if kappa < 0.60:
                low_kappa.append(code_id)

    out_dir = root / "workspace" / "codebooks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "diff_v1_to_v2.md"
    added_lines = [f"- `{c}`" for c in added] or ["_(none)_"]
    removed_lines = [f"- `{c}`" for c in removed] or ["_(none)_"]
    renamed_lines = (
        [f"- `{c}`: '{l1}' → '{l2}'" for c, l1, l2 in renamed]
        or ["_(none)_"]
    )
    lines = [
        "# Codebook diff — v1 → v2",
        "",
        f"- v1: `{arguments['codebook_v1']}` ({len(v1)} codes)",
        f"- v2: `{arguments['codebook_v2']}` ({len(v2)} codes)",
        "",
        "## Added",
        "",
        *added_lines,
        "",
        "## Removed",
        "",
        *removed_lines,
        "",
        "## Renamed",
        "",
        *renamed_lines,
        "",
    ]
    if kappas:
        lines += ["## Per-code Cohen's κ (v1 vs v2 applied codings)", ""]
        for c, k in sorted(kappas.items(), key=lambda x: x[1]):
            flag = "  ⚠ <0.60" if k < 0.60 else ""
            lines.append(f"- `{c}`: κ={k}{flag}")
        lines.append("")
    out_path.write_text("\n".join(lines))
    return _ok({
        "diff_path": str(out_path.relative_to(root)),
        "added": added,
        "removed": removed,
        "renamed": [{"id": c, "v1": l1, "v2": l2} for c, l1, l2 in renamed],
        "kappas": kappas,
        "low_kappa_codes": low_kappa,
        "advice": (
            "Codes with κ<0.60 need either a clearer definition "
            "(rewrite the inclusion / exclusion criteria) OR a third "
            "round of coding by an additional rater."
            if low_kappa else
            "All retained codes hit κ≥0.60. Safe to proceed to selective coding."
        ),
    })


@register_tool(
    "tool_qualitative_quote_provenance",
    schema={
        "type": "object",
        "properties": {
            "quote": {"type": "string"},
            "participant_id": {"type": "string"},
            "transcript_path": {"type": "string"},
            "line_range": {
                "type": "string",
                "description": "Inclusive line range, e.g. '42-47'. Optional if transcript_path is supplied.",
            },
            "timestamp": {
                "type": "string",
                "description": "Optional video / audio timestamp, e.g. '00:12:34'.",
            },
        },
        "required": ["quote", "participant_id"],
    },
    description=(
        "Register a participant quote in workspace/quotes/registry.jsonl "
        "with its full provenance: participant_id, transcript path, "
        "line range, optional timestamp. The qualitative_report_format "
        "protocol consumes this registry to verify every quote in the "
        "final report has a recoverable source."
    ),
)
def quote_provenance(name: str, arguments: dict, root: Path) -> Any:
    import datetime as _dt
    registry_dir = root / "workspace" / "quotes"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry = registry_dir / "registry.jsonl"
    entry = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "quote": arguments["quote"],
        "participant_id": arguments["participant_id"],
        "transcript_path": arguments.get("transcript_path", ""),
        "line_range": arguments.get("line_range", ""),
        "timestamp": arguments.get("timestamp", ""),
    }
    with open(registry, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return _ok({
        "registry_path": str(registry.relative_to(root)),
        "entry": entry,
        "advice": (
            "Every quote in the final report must appear in this "
            "registry. The qualitative_report_format protocol audits "
            "the report against this file."
        ),
    })


# ── AUDIT-026: COREQ / SRQR standard selector ────────────────────────
import shutil as _shutil_audit026  # noqa: E402

def _err(message: str) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "message": message}, indent=2
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "error", "message": message}, indent=2
        ))]


# Methods that drive the COREQ choice. Anything not in this set defaults
# to SRQR (the broader standard).
_COREQ_METHODS = frozenset({
    "interview", "interviews",
    "focus_group", "focus_groups", "focus-group", "focus-groups",
    "interview_and_focus_groups", "interviews_and_focus_groups",
})

_STANDARD_ITEM_COUNTS = {"coreq": 32, "srqr": 21}


def _find_checklists_dir() -> Path | None:
    """Locate the bundled checklist templates directory."""
    here = Path(__file__).resolve()
    # In-package: src/research_os/data/checklists/
    for n in (2, 3, 4, 5, 6, 7):
        try:
            cand = here.parents[n] / "research_os" / "data" / "checklists"
        except IndexError:
            break
        if cand.exists():
            return cand
    # Source checkout: walk up to <repo>/templates/checklists.
    for n in (2, 3, 4, 5, 6, 7):
        try:
            cand = here.parents[n] / "templates" / "checklists"
        except IndexError:
            break
        if cand.exists():
            return cand
    return None


def _pick_standard_from_design(design_path: Path) -> tuple[str, str]:
    if not design_path.exists():
        return "srqr", (
            f"{design_path.name} not found; defaulting to SRQR (broader "
            "standard, covers ethnography / document analysis / mixed)."
        )
    try:
        import yaml
        design = yaml.safe_load(design_path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        return "srqr", (
            f"Could not parse {design_path.name} ({exc}); defaulting to SRQR."
        )
    method = str(design.get("method", "")).strip().lower()
    if not method:
        return "srqr", (
            f"{design_path.name} has no 'method' field; defaulting to SRQR."
        )
    if method in _COREQ_METHODS:
        return "coreq", (
            f"study_design.method='{method}' matches COREQ scope "
            "(interviews and/or focus groups)."
        )
    return "srqr", (
        f"study_design.method='{method}' is outside COREQ's interview/focus-group "
        "scope; SRQR is the appropriate standard."
    )


def _next_coverage_version(out_dir: Path, standard: str) -> int:
    existing = list(out_dir.glob(f"{standard}_coverage_v*.yaml"))
    versions = []
    for p in existing:
        stem = p.stem
        suffix = stem.rsplit("_v", 1)[-1]
        try:
            versions.append(int(suffix))
        except ValueError:
            continue
    return (max(versions) + 1) if versions else 1


@register_tool(
    "tool_qualitative_select_standard",
    schema={
        "type": "object",
        "properties": {
            "standard": {
                "type": "string",
                "enum": ["coreq", "srqr", "auto"],
                "description": (
                    "Reporting standard to use. 'auto' (default) reads "
                    "workspace/study_design.yaml and picks COREQ for "
                    "interview/focus-group studies, SRQR otherwise."
                ),
                "default": "auto",
            },
            "study_design_path": {
                "type": "string",
                "description": (
                    "Path under the project root to the study-design YAML. "
                    "Defaults to 'workspace/study_design.yaml'."
                ),
                "default": "workspace/study_design.yaml",
            },
        },
        "required": [],
    },
    description=(
        "Pick COREQ vs SRQR for a qualitative manuscript and copy the "
        "matching checklist template (32-item COREQ or 21-item SRQR) "
        "into workspace/checklists/<standard>_coverage_v<N>.yaml so "
        "the walk_checklist step has a populated file to mark up. "
        "Step 1 of the qualitative_report_format protocol."
    ),
)
def select_standard(name: str, arguments: dict, root: Any) -> Any:
    root = Path(root)
    requested = str(arguments.get("standard", "auto")).lower()
    design_path = root / str(
        arguments.get("study_design_path", "workspace/study_design.yaml")
    )

    if requested in {"coreq", "srqr"}:
        standard = requested
        reason = f"Caller specified standard='{requested}'."
    elif requested == "auto":
        standard, reason = _pick_standard_from_design(design_path)
    else:
        return _err(
            f"Unknown standard '{requested}'. Use one of: coreq, srqr, auto."
        )

    item_count = _STANDARD_ITEM_COUNTS[standard]
    src_dir = _find_checklists_dir()
    if src_dir is None:
        return _err(
            "Bundled checklist templates not found. Expected "
            "templates/checklists/ in source checkout or "
            "research_os/data/checklists/ in installed wheel."
        )
    src_file = src_dir / f"{standard}_{item_count}items.yaml"
    if not src_file.exists():
        return _err(
            f"Checklist template missing: {src_file}. "
            "Reinstall research-os or restore the templates/checklists/ dir."
        )

    out_dir = root / "workspace" / "checklists"
    out_dir.mkdir(parents=True, exist_ok=True)
    version = _next_coverage_version(out_dir, standard)
    dest = out_dir / f"{standard}_coverage_v{version}.yaml"
    _shutil_audit026.copyfile(src_file, dest)

    return _ok({
        "standard": standard.upper(),
        "reason": reason,
        "item_count": item_count,
        "source_template": str(src_file),
        "coverage_path": str(dest.relative_to(root)),
        "version": version,
        "next_step": (
            f"Walk every item in {dest.relative_to(root)} and mark "
            "status: present | partial | absent for each, citing the "
            "manuscript section in the 'location' field."
        ),
    })
