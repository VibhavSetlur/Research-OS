"""Researcher self-certifications + per-step skip annotations.

A researcher with deep expertise in a domain or method can self-certify
they've done the equivalent work outside RO. Audits honor active
certifications by downgrading their corresponding blockers to notes.

Storage: ``workspace/researcher_certifications.yaml`` (persists across
sessions, gitignored by default).

Per-step skip annotations: ``<!-- ro:skip lit_loop, reason: ... -->``
in ``conclusions.md`` honoured by audits — caller passes the gate name
they want to skip, returns whether the step has an active skip.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.certifications")


_VALID_DOMAINS = {
    "literature_loop",
    "stack_plan",
    "preregistration",
    "sensitivity_analysis",
    "code_review",
    "reproducibility",
    "lit_loop",  # alias
}


def _cert_path(root: Path) -> Path:
    return root / "workspace" / "researcher_certifications.yaml"


class _CertParseError(Exception):
    """Raised when the on-disk certifications file is unparseable."""


def _load(root: Path) -> dict[str, Any]:
    """Read certifications. Distinguishes missing from corrupted —
    a parse failure raises so callers don't silently wipe data on save."""
    path = _cert_path(root)
    if not path.exists():
        return {"version": "1.5.2", "certifications": []}
    try:
        import yaml  # type: ignore
        text = path.read_text()
        data = yaml.safe_load(text)
        if data is None:
            return {"version": "1.5.2", "certifications": []}
        if not isinstance(data, dict):
            raise _CertParseError(
                "certifications file is not a YAML mapping"
            )
        data.setdefault("certifications", [])
        return data
    except _CertParseError:
        raise
    except Exception as e:
        raise _CertParseError(
            f"certifications file exists but is unparseable: {e}"
        ) from e


def _save(root: Path, data: dict[str, Any]) -> None:
    path = _cert_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    except Exception:
        import json
        path.write_text(json.dumps(data, indent=2))


def self_certify(
    root: Path,
    *,
    domain: str,
    scope: str,
    rationale: str,
) -> dict[str, Any]:
    """Persist a self-certification.

    Parameters
    ----------
    domain : str
        One of literature_loop, stack_plan, preregistration,
        sensitivity_analysis, code_review, reproducibility.
    scope : str
        What it applies to. Examples: "all steps", "step 03", "DESeq2
        method selection", "all literature claims in step 02".
    rationale : str
        Why the researcher is asserting equivalent work was done
        outside RO. Recorded; surfaced in audit reports.
    """
    try:
        if domain not in _VALID_DOMAINS:
            return {
                "status": "error",
                "message": (
                    f"Unknown domain '{domain}'. Allowed: "
                    f"{sorted(_VALID_DOMAINS)}"
                ),
            }
        if not scope.strip() or not rationale.strip():
            return {
                "status": "error",
                "message": "scope and rationale are required.",
            }
        try:
            data = _load(root)
        except _CertParseError as e:
            return {
                "status": "error",
                "message": (
                    f"Refusing to overwrite a corrupted "
                    f"researcher_certifications.yaml — {e}. Hand-edit "
                    "or delete the file first."
                ),
            }
        cert = {
            "domain": "literature_loop" if domain == "lit_loop" else domain,
            "scope": scope.strip(),
            "rationale": rationale.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data["certifications"].append(cert)
        _save(root, data)
        return {
            "status": "success",
            "certification": cert,
            "active_count": len(data["certifications"]),
        }
    except Exception as e:
        logger.exception("self_certify failed")
        return {"status": "error", "message": str(e)}


def list_certifications(root: Path) -> dict[str, Any]:
    """List active certifications."""
    try:
        try:
            data = _load(root)
        except _CertParseError as e:
            return {"status": "error", "message": str(e)}
        return {
            "status": "success",
            "count": len(data.get("certifications", [])),
            "certifications": data.get("certifications", []),
        }
    except Exception as e:
        logger.exception("list_certifications failed")
        return {"status": "error", "message": str(e)}


def has_active_certification(root: Path, domain: str, *, step_id: str = "") -> dict[str, Any]:
    """Return whether an active certification covers (domain, step_id)."""
    try:
        try:
            data = _load(root)
        except _CertParseError:
            return {"active": False, "error": "certifications file unparseable"}
        if domain == "lit_loop":
            domain = "literature_loop"
        for cert in data.get("certifications", []):
            if cert.get("domain") != domain:
                continue
            scope = (cert.get("scope") or "").lower()
            if "all" in scope:
                return {"active": True, "certification": cert}
            if step_id and step_id.lower() in scope:
                return {"active": True, "certification": cert}
        return {"active": False}
    except Exception as e:
        logger.exception("has_active_certification failed")
        return {"active": False, "error": str(e)}


_SKIP_RE = re.compile(
    r"<!--\s*ro:skip\s+(?P<gate>[a-zA-Z_]+)(?:\s*,\s*reason:\s*(?P<reason>[^>]+?))?\s*-->",
    re.IGNORECASE,
)


def step_has_skip_annotation(
    root: Path,
    step_id: str,
    gate_name: str,
) -> dict[str, Any]:
    """Check whether conclusions.md in step has ``<!-- ro:skip gate_name ... -->``."""
    try:
        conc = root / "workspace" / step_id / "conclusions.md"
        if not conc.exists():
            return {"has_skip": False, "reason": "no conclusions.md"}
        text = conc.read_text()
        for m in _SKIP_RE.finditer(text):
            if m.group("gate").lower() == gate_name.lower():
                return {
                    "has_skip": True,
                    "reason": (m.group("reason") or "").strip() or "(no reason)",
                }
        return {"has_skip": False}
    except Exception as e:
        logger.exception("step_has_skip_annotation failed")
        return {"has_skip": False, "error": str(e)}
