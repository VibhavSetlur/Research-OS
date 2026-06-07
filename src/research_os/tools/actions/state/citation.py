"""CITATION.cff emitter for scaffolded research projects.

When ``research-os init`` creates a new project the wizard already knows
the researcher's name / ORCID / project name. ``emit_project_citation_cff``
writes a pre-filled CITATION.cff at the project root so the project is
citable from day one (GitHub renders a "Cite this repository" button as
soon as one is present at repo root).

The emitted file conforms to Citation File Format 1.2.0 and validates
with cffconvert.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

__all__ = ["emit_project_citation_cff"]


def _normalize_orcid(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith("http://") or v.startswith("https://"):
        return v
    return f"https://orcid.org/{v}"


def emit_project_citation_cff(root: Path,
                               project_name: str = "",
                               researcher: dict[str, Any] | None = None,
                               overwrite: bool = False) -> Path:
    """Write CITATION.cff at *root*. Returns the path written.

    Skips writing when the file already exists unless ``overwrite=True``.
    Pulls author identity from *researcher* (dict with name / orcid /
    email / institution); falls back to "Anonymous Researcher" when
    nothing is supplied.
    """
    root = Path(root)
    out = root / "CITATION.cff"
    if out.exists() and not overwrite:
        return out

    researcher = researcher or {}
    name = str(researcher.get("name") or "").strip()
    orcid = _normalize_orcid(str(researcher.get("orcid") or ""))
    email = str(researcher.get("email") or "").strip()
    institution = str(researcher.get("institution") or "").strip()
    project_name = (project_name or root.name or "research-project").strip()

    if " " in name:
        given, family = name.split(" ", 1)
    elif name:
        given, family = name, ""
    else:
        given, family = "Anonymous", "Researcher"

    today = _dt.date.today().isoformat()

    lines: list[str] = [
        'cff-version: 1.2.0',
        'message: "If you use this project, please cite it as below."',
        'type: dataset',
        f'title: "{project_name}"',
        'authors:',
        f'  - family-names: "{family}"',
        f'    given-names: "{given}"',
    ]
    if orcid:
        lines.append(f'    orcid: "{orcid}"')
    if email:
        lines.append(f'    email: "{email}"')
    if institution:
        lines.append(f'    affiliation: "{institution}"')
    lines += [
        f'date-released: {today}',
        'keywords:',
        '  - research-data-management',
        '  - reproducibility',
        '  - FAIR',
    ]

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
