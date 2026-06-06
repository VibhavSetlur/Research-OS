"""Audit foundation: structured finding dataclass, base class, and writer.

Every audit emits a list of :class:`AuditFinding` objects rather than
a free-form string. The shape is fixed by
``src/research_os/schemas/audit_finding.schema.json`` (JSON Schema
draft-07) and validated on the way in via :func:`validate_finding`.

Writing helpers fan one ``list[AuditFinding]`` out to three artefacts:

* ``workspace/<gate>_audit.md``     — human-readable, grouped by severity.
* ``workspace/<gate>_audit.json``   — schema-validated, machine-readable
  array of finding objects (overwritten on each run).
* ``workspace/logs/.audit_findings.jsonl`` — append-only one-JSON-per-line
  ledger across all audits, used by history queries.

The .md + .json files are idempotent (rewritten in place); the .jsonl
ledger is APPEND-ONLY so the historical record across reruns survives.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Locate the bundled JSON Schema for runtime validation. The file lives
# at ``src/research_os/schemas/audit_finding.schema.json``; we resolve
# the path via __file__ so it works both in an editable checkout and in
# an installed wheel (hatchling ships the .json with the package).
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "schemas"
    / "audit_finding.schema.json"
)

# Severity vocabulary stays small + closed so report grouping is stable
# and downstream dashboards can hard-code the colour map.
_ALLOWED_SEVERITIES = ("block", "warn", "info")

# Order severities for grouped output; "block" first so reviewers see
# the showstoppers before scrolling.
_SEVERITY_ORDER = ("block", "warn", "info")


def _ro_version() -> str:
    """Return ``research_os.__version__`` without forcing the parent
    package to be importable at module load time.

    A direct ``from research_os import __version__`` would cause a
    circular import if a future audit module is imported during
    ``research_os/__init__.py`` evaluation. Reading the attribute
    lazily inside this function keeps the import graph acyclic.
    """
    from research_os import __version__

    return __version__


def _now_iso() -> str:
    """UTC ISO-8601 timestamp with trailing 'Z' (schema 'date-time' shape)."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@dataclass
class AuditFinding:
    """One structured finding from an audit run.

    Mirrors ``audit_finding.schema.json`` exactly. Use the factory
    :meth:`new` for ergonomic construction with sane defaults for the
    auto-generated fields (id, generated_at, ro_version).
    """

    audit_name: str
    severity: str
    dimension: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_paths: list[str] = field(default_factory=list)
    suggested_fix: str = ""
    override_kwarg: str | None = None
    override_log_format: str | None = None
    generated_at: str = field(default_factory=_now_iso)
    ro_version: str = field(default_factory=_ro_version)

    @classmethod
    def new(
        cls,
        *,
        audit_name: str,
        severity: str,
        dimension: str,
        evidence_paths: list[str] | None = None,
        suggested_fix: str = "",
        override_kwarg: str | None = None,
        override_log_format: str | None = None,
    ) -> "AuditFinding":
        """Construct + validate in one call. Raises ValueError on bad input."""
        finding = cls(
            audit_name=audit_name,
            severity=severity,
            dimension=dimension,
            evidence_paths=list(evidence_paths or []),
            suggested_fix=suggested_fix,
            override_kwarg=override_kwarg,
            override_log_format=override_log_format,
        )
        # Re-validate via the schema path so the same checks apply to
        # both factory-built and round-tripped findings.
        validate_finding(finding.to_dict())
        return finding

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict matching the JSON Schema."""
        return asdict(self)


class AuditBase(ABC):
    """Abstract base for every audit.

    Subclasses implement :meth:`run`. Each audit is responsible for
    producing the list of findings; calling :func:`write_audit_outputs`
    is the orchestrator's job (typically the gate that invoked the
    audit), so a single workspace write covers multi-audit composite
    gates.
    """

    #: Stable identifier for this audit. Used as the ``audit_name``
    #: field on findings and as the default gate name for output
    #: filenames. Subclasses MUST override.
    name: str = ""

    @abstractmethod
    def run(self, root: Path, **kwargs: Any) -> list[AuditFinding]:
        """Execute the audit against ``root`` and return its findings."""
        ...


def _load_schema() -> dict[str, Any]:
    """Read the JSON Schema from disk. Cached on the function for cheapness."""
    cached = getattr(_load_schema, "_cache", None)
    if cached is not None:
        return cached
    schema = json.loads(_SCHEMA_PATH.read_text())
    _load_schema._cache = schema  # type: ignore[attr-defined]
    return schema


def _manual_validate(d: dict[str, Any], schema: dict[str, Any]) -> None:
    """Lightweight in-house validator covering everything the schema declares.

    We don't add ``jsonschema`` as a hard project dependency, so this
    fallback handles the subset of draft-07 the audit_finding schema
    actually uses: required + type + enum + pattern + minLength +
    additionalProperties=false. If a future schema needs broader
    coverage, swap in jsonschema (already importable in the dev env).
    """
    required = schema.get("required", [])
    props = schema.get("properties", {})
    allow_extra = schema.get("additionalProperties", True) is not False

    for key in required:
        if key not in d:
            raise ValueError(f"audit_finding missing required field: {key!r}")

    if not allow_extra:
        unknown = set(d) - set(props)
        if unknown:
            raise ValueError(
                f"audit_finding contains unknown field(s): {sorted(unknown)}"
            )

    for key, value in d.items():
        spec = props.get(key)
        if spec is None:
            continue
        types = spec.get("type")
        if types is not None:
            if isinstance(types, str):
                types = [types]
            if not _matches_type(value, types):
                raise ValueError(
                    f"audit_finding field {key!r} has type "
                    f"{type(value).__name__}, expected one of {types}"
                )
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(
                f"audit_finding field {key!r}={value!r} not in enum {spec['enum']}"
            )
        if "minLength" in spec and isinstance(value, str):
            if len(value) < spec["minLength"]:
                raise ValueError(
                    f"audit_finding field {key!r} shorter than minLength "
                    f"{spec['minLength']}"
                )
        if "pattern" in spec and isinstance(value, str):
            import re as _re

            if not _re.match(spec["pattern"], value):
                raise ValueError(
                    f"audit_finding field {key!r}={value!r} does not match "
                    f"pattern {spec['pattern']}"
                )
        # Array item types — the schema only uses ``items: {type: string}``
        # today, so we cover that case without recursing into nested objects.
        if types and "array" in types and isinstance(value, list):
            item_spec = spec.get("items") or {}
            item_types = item_spec.get("type")
            if item_types:
                if isinstance(item_types, str):
                    item_types = [item_types]
                for i, item in enumerate(value):
                    if not _matches_type(item, item_types):
                        raise ValueError(
                            f"audit_finding field {key!r}[{i}] has type "
                            f"{type(item).__name__}, expected one of "
                            f"{item_types}"
                        )


def _matches_type(value: Any, types: list[str]) -> bool:
    """Check value against the JSON Schema type-name list."""
    for t in types:
        if t == "string" and isinstance(value, str):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "null" and value is None:
            return True
    return False


def validate_finding(d: dict[str, Any]) -> AuditFinding:
    """Validate ``d`` against the JSON Schema and return an ``AuditFinding``.

    Prefers the ``jsonschema`` library when available (broader draft-07
    coverage) and falls back to the in-house validator above.
    """
    schema = _load_schema()
    try:
        import jsonschema  # type: ignore

        try:
            jsonschema.validate(instance=d, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"audit_finding schema violation: {exc.message}") from exc
    except ImportError:
        _manual_validate(d, schema)

    # Belt + braces: also enforce the closed severity vocabulary even if
    # the schema enum check is somehow bypassed.
    if d.get("severity") not in _ALLOWED_SEVERITIES:
        raise ValueError(
            f"audit_finding.severity={d.get('severity')!r} not in {_ALLOWED_SEVERITIES}"
        )

    return AuditFinding(
        audit_name=d["audit_name"],
        severity=d["severity"],
        dimension=d["dimension"],
        id=d["id"],
        evidence_paths=list(d.get("evidence_paths") or []),
        suggested_fix=d.get("suggested_fix") or "",
        override_kwarg=d.get("override_kwarg"),
        override_log_format=d.get("override_log_format"),
        generated_at=d["generated_at"],
        ro_version=d["ro_version"],
    )


def _render_markdown(findings: list[AuditFinding], gate_name: str) -> str:
    """Group findings by severity into a human-readable markdown report."""
    lines: list[str] = [
        f"# {gate_name} audit",
        "",
        f"- Total findings: **{len(findings)}**",
    ]
    by_sev: dict[str, list[AuditFinding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)
    for sev in _SEVERITY_ORDER:
        lines.append(f"- {sev}: {len(by_sev.get(sev, []))}")
    lines.append("")

    if not findings:
        lines.extend(["_No findings — gate passed cleanly._", ""])
        return "\n".join(lines)

    for sev in _SEVERITY_ORDER:
        group = by_sev.get(sev) or []
        if not group:
            continue
        icon = {"block": "🛑", "warn": "⚠️", "info": "ℹ️"}.get(sev, "•")
        lines.append(f"## {icon} {sev} ({len(group)})")
        lines.append("")
        for f in group:
            lines.append(f"### [{f.dimension}] {f.audit_name} — `{f.id}`")
            if f.suggested_fix:
                lines.append(f"- **Suggested fix:** {f.suggested_fix}")
            if f.evidence_paths:
                lines.append("- **Evidence:**")
                for ep in f.evidence_paths:
                    lines.append(f"  - `{ep}`")
            if f.override_kwarg:
                lines.append(
                    f"- **Override:** pass `{f.override_kwarg}=true` with a "
                    "rationale to bypass."
                )
            lines.append("")
    return "\n".join(lines)


def write_audit_outputs(
    findings: list[AuditFinding],
    gate_name: str,
    root: Path,
) -> dict[str, Path]:
    """Persist ``findings`` to the three audit artefacts.

    Returns a dict of {"md": Path, "json": Path, "jsonl": Path} pointing
    at the written files (relative to ``root``).
    """
    # Validate every finding before we touch disk. A single bad entry
    # fails the whole write so the JSON file on disk always satisfies
    # the schema.
    for f in findings:
        validate_finding(f.to_dict())

    workspace = root / "workspace"
    logs_dir = workspace / "logs"
    workspace.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    md_path = workspace / f"{gate_name}_audit.md"
    json_path = workspace / f"{gate_name}_audit.json"
    jsonl_path = logs_dir / ".audit_findings.jsonl"

    md_path.write_text(_render_markdown(findings, gate_name))
    json_path.write_text(
        json.dumps([f.to_dict() for f in findings], indent=2, sort_keys=True)
    )

    # Append-only ledger so reruns leave a historical trail. Use 'a'
    # explicitly; never truncate.
    with jsonl_path.open("a") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_dict(), sort_keys=True) + "\n")

    return {"md": md_path, "json": json_path, "jsonl": jsonl_path}
