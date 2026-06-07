"""RO-Crate 1.1 Lightweight Profile + CodeMeta 2.0 emitters.

Open-science manifests for share-safe archives:

* ``build_ro_crate(root)``  — writes ``ro-crate-metadata.json`` at *root*,
  populated from ``inputs/researcher_config.yaml``, ``inputs/intake.md``,
  and ``hasPart`` entries walked from ``synthesis/`` + ``workspace/*/outputs/``
  plus every ``*.prov.json`` sidecar. Conforms to JSON-LD with
  ``@context: https://w3id.org/ro/crate/1.1/context``.
* ``build_codemeta(root)`` — writes ``codemeta.json`` at *root* using
  CodeMeta 2.0 (``@context: https://doi.org/10.5063/schema/codemeta-2.0``),
  populated from ``researcher_config.yaml`` + ``environment/``.

These are intentionally dependency-free (no ``rocrate`` PyPI package
required) so ``sys_export_share_archive`` can emit them inside the zip
without forcing a runtime dep on collaborators.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

__all__ = [
    "build_ro_crate",
    "build_codemeta",
    "sys_export_ro_crate",
]


_RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
_CODEMETA_CONTEXT = "https://doi.org/10.5063/schema/codemeta-2.0"

_LICENSE_URL = {
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "MIT": "https://spdx.org/licenses/MIT.html",
    "Apache-2.0": "https://spdx.org/licenses/Apache-2.0.html",
    "BSD-3-Clause": "https://spdx.org/licenses/BSD-3-Clause.html",
    "GPL-3.0": "https://spdx.org/licenses/GPL-3.0.html",
}


def _load_researcher_config(root: Path) -> dict[str, Any]:
    """Best-effort read of inputs/researcher_config.yaml."""
    try:
        from research_os.tools.actions.state.config import get_research_config

        return get_research_config(root) or {}
    except Exception:
        return {}


def _normalize_orcid(value: str) -> str:
    """Coerce an ORCID into the URI form RO-Crate expects."""
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith("http://") or v.startswith("https://"):
        return v
    return f"https://orcid.org/{v}"


def _intake_description(root: Path) -> str:
    """First sentence-y blob of inputs/intake.md, or empty string."""
    intake = root / "inputs" / "intake.md"
    if not intake.exists():
        return ""
    try:
        text = intake.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Strip markdown noise: the first non-heading, non-blank chunk.
    chunks: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            if chunks:
                break
            continue
        chunks.append(s)
        if sum(len(c) for c in chunks) > 600:
            break
    return " ".join(chunks).strip()


def _iter_has_part(root: Path) -> list[Path]:
    """Files that should appear in the crate's hasPart list."""
    parts: list[Path] = []
    for sub in ("synthesis", "workspace"):
        base = root / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            # Only emit user-facing outputs + prov sidecars; skip
            # caches + AI internals.
            rel_parts = p.relative_to(root).parts
            if any(seg in {"__pycache__", ".pytest_cache",
                           ".os_state", "scratch"} for seg in rel_parts):
                continue
            if sub == "workspace" and "outputs" not in rel_parts \
                    and not p.name.endswith(".prov.json"):
                continue
            parts.append(p)
    return sorted(parts)


def build_ro_crate(root: Path) -> dict[str, Any]:
    """Emit ro-crate-metadata.json at *root*. Returns the manifest dict.

    Idempotent — rewrites in place each call so the crate reflects the
    latest workspace state at export time.
    """
    root = Path(root)
    cfg = _load_researcher_config(root)
    researcher = (cfg.get("researcher") or {}) if isinstance(cfg, dict) else {}
    licenses = (cfg.get("licenses") or {}) if isinstance(cfg, dict) else {}
    project_name = cfg.get("project_name") or root.name

    author_orcid = _normalize_orcid(str(researcher.get("orcid") or ""))
    author_name = str(researcher.get("name") or "").strip()
    author_email = str(researcher.get("email") or "").strip()
    author_aff = str(researcher.get("institution") or "").strip()

    data_license = str(licenses.get("data") or "CC-BY-4.0").strip()
    description = _intake_description(root) or f"Research project: {project_name}"

    today = _dt.date.today().isoformat()

    graph: list[dict[str, Any]] = []

    # 1. RO-Crate descriptor — always at the head.
    graph.append({
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
        "about": {"@id": "./"},
    })

    # 2. Root dataset.
    root_entity: dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "name": project_name,
        "description": description,
        "datePublished": today,
        "license": {"@id": _LICENSE_URL.get(data_license, data_license)},
    }
    if author_orcid or author_name:
        root_entity["author"] = {"@id": author_orcid or f"#author-{(author_name or 'anon').replace(' ', '-')}"}

    parts = _iter_has_part(root)
    if parts:
        root_entity["hasPart"] = [{"@id": p.relative_to(root).as_posix()} for p in parts]
    graph.append(root_entity)

    # 3. Author Person entity.
    if author_orcid or author_name:
        person: dict[str, Any] = {
            "@id": author_orcid or f"#author-{(author_name or 'anon').replace(' ', '-')}",
            "@type": "Person",
        }
        if author_name:
            person["name"] = author_name
        if author_email:
            person["email"] = author_email
        if author_aff:
            person["affiliation"] = author_aff
        graph.append(person)

    # 4. License entity.
    graph.append({
        "@id": _LICENSE_URL.get(data_license, data_license),
        "@type": "CreativeWork",
        "name": data_license,
    })

    # 5. hasPart file entries — type=File for plain outputs, the prov
    #    sidecar gets a SoftwareApplication-ish hint via additionalType.
    for p in parts:
        rel = p.relative_to(root).as_posix()
        entry: dict[str, Any] = {
            "@id": rel,
            "@type": "File",
            "name": p.name,
        }
        if p.name.endswith(".prov.json"):
            entry["encodingFormat"] = "application/json"
            entry["additionalType"] = "ProvenanceSidecar"
        graph.append(entry)

    manifest = {
        "@context": _RO_CRATE_CONTEXT,
        "@graph": graph,
    }

    out = root / "ro-crate-metadata.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n",
                   encoding="utf-8")
    return manifest


def build_codemeta(root: Path) -> dict[str, Any]:
    """Emit codemeta.json at *root* (CodeMeta 2.0). Returns the dict."""
    root = Path(root)
    cfg = _load_researcher_config(root)
    researcher = (cfg.get("researcher") or {}) if isinstance(cfg, dict) else {}
    licenses = (cfg.get("licenses") or {}) if isinstance(cfg, dict) else {}
    project_name = cfg.get("project_name") or root.name

    author_orcid = _normalize_orcid(str(researcher.get("orcid") or ""))
    author_name = (str(researcher.get("name") or "").strip()
                   or "Anonymous Researcher")
    author_email = str(researcher.get("email") or "").strip()
    author_aff = str(researcher.get("institution") or "").strip()

    code_license = str(licenses.get("code") or "MIT").strip()
    today = _dt.date.today().isoformat()

    # Runtime hint from environment/requirements.txt (count of pinned deps).
    req_path = root / "environment" / "requirements.txt"
    runtime_deps: list[str] = []
    if req_path.exists():
        try:
            for line in req_path.read_text(encoding="utf-8",
                                            errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                runtime_deps.append(s)
        except OSError:
            pass

    author: dict[str, Any] = {
        "@type": "Person",
        "givenName": author_name.split(" ", 1)[0],
        "familyName": author_name.split(" ", 1)[1] if " " in author_name else "",
        "name": author_name,
    }
    if author_orcid:
        author["@id"] = author_orcid
    if author_email:
        author["email"] = author_email
    if author_aff:
        author["affiliation"] = {"@type": "Organization", "name": author_aff}

    codemeta: dict[str, Any] = {
        "@context": _CODEMETA_CONTEXT,
        "@type": "SoftwareSourceCode",
        "name": project_name,
        "description": _intake_description(root)
                        or f"Research project: {project_name}",
        "license": _LICENSE_URL.get(code_license, code_license),
        "datePublished": today,
        "author": [author],
        "programmingLanguage": "Python",
    }
    if runtime_deps:
        codemeta["softwareRequirements"] = runtime_deps[:50]

    out = root / "codemeta.json"
    out.write_text(json.dumps(codemeta, indent=2, sort_keys=False) + "\n",
                   encoding="utf-8")
    return codemeta


def sys_export_ro_crate(root: Path | str,
                         operation: str = "build") -> dict[str, Any]:
    """Public entry point — supports operation='build' (default) and 'preview'.

    Returns a status envelope:
      {"status": "success", "manifest_path": "ro-crate-metadata.json",
       "codemeta_path": "codemeta.json", "has_part_count": N}

    For operation='preview' the manifest is returned but NOT written.
    """
    root = Path(root)
    if operation not in {"build", "preview"}:
        return {"status": "error",
                "message": f"unknown operation '{operation}'; "
                           "expected 'build' or 'preview'"}

    if operation == "preview":
        # Generate but don't write — caller wants to inspect first.
        cfg = _load_researcher_config(root)
        researcher = (cfg.get("researcher") or {}) if isinstance(cfg, dict) else {}
        return {
            "status": "success",
            "operation": "preview",
            "would_emit": ["ro-crate-metadata.json", "codemeta.json"],
            "author": researcher.get("name") or "(unset)",
            "orcid": researcher.get("orcid") or "(unset)",
            "has_part_count": len(_iter_has_part(root)),
        }

    manifest = build_ro_crate(root)
    codemeta = build_codemeta(root)
    return {
        "status": "success",
        "operation": "build",
        "manifest_path": "ro-crate-metadata.json",
        "codemeta_path": "codemeta.json",
        "has_part_count": sum(
            1 for entity in manifest.get("@graph", [])
            if entity.get("@type") == "File"
        ),
        "codemeta_authors": len(codemeta.get("author") or []),
    }
