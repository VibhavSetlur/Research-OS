"""Shared paper-path resolution + dual-format (Markdown / Typst) parsing.

Synthesis deliverables are authored as Typst (``synthesis/paper.typ``)
but older / imported projects may still carry a Markdown draft
(``synthesis/paper.md`` or ``synthesis/report.md``). Every structural
auditor needs to (a) find whichever file is actually present and (b)
parse its sections, figures, and bibliography regardless of which
markup it uses. Centralising both concerns here keeps the per-audit
modules from re-implementing — and drifting on — the same logic.

Format detection is by file suffix: ``.typ`` is Typst, everything else
is treated as Markdown. The regexes below are deliberately permissive
so a paper that mixes the two (e.g. a Typst file with an ``![](…)``
left over from a converted draft) still surfaces its figures.

Heading equivalence
-------------------
Markdown IMRAD drafts use ``## Methods`` (level 2 under a ``#`` title).
Typst uses ``= Methods`` (level 1) because the document title is set in
the template ``conf``, not as body text. So a *named* section lookup
must match ``##`` in Markdown and ``=`` in Typst. The section helpers
below match a heading of ANY depth whose text is the section name, so
the same call works against either format.
"""

from __future__ import annotations

import re
from pathlib import Path

# Candidate paper locations, in preference order. The .typ form is the
# canonical authored deliverable; .md / report.md are legacy / imported.
PAPER_CANDIDATES: tuple[str, ...] = (
    "synthesis/paper.typ",
    "synthesis/paper.md",
    "synthesis/report.md",
)


def resolve_paper_path(root: Path) -> str:
    """Return the relative path of the first existing paper candidate.

    Falls back to the first candidate (``synthesis/paper.typ``) when
    none exist so callers get the canonical authored path as the
    default rather than the legacy Markdown name.
    """
    root = Path(root)
    for rel in PAPER_CANDIDATES:
        if (root / rel).is_file():
            return rel
    return PAPER_CANDIDATES[0]


def is_typst(path: str | Path) -> bool:
    """True when ``path`` is a Typst source file (by suffix)."""
    return str(path).lower().endswith(".typ")


# ---------------------------------------------------------------------------
# Figure references
# ---------------------------------------------------------------------------

# Markdown image:  ![alt](path)
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
# Typst:  #figure(image("path"  /  #image("path"
_TYP_IMG_RE = re.compile(r"#(?:figure\(\s*)?image\(\s*[\"']([^\"']+)[\"']")


def figure_refs(text: str, typst: bool) -> list[str]:
    """Extract figure path references from a paper body.

    Always scans the Markdown form too — a converted draft may carry a
    stray ``![](…)`` — so no figure is missed when the suffix says
    Typst but the body is mixed.
    """
    refs: list[str] = []
    for m in _MD_IMG_RE.finditer(text):
        refs.append(m.group(1).strip())
    if typst:
        for m in _TYP_IMG_RE.finditer(text):
            refs.append(m.group(1).strip())
    return refs


# ---------------------------------------------------------------------------
# Bibliography / references presence
# ---------------------------------------------------------------------------


def has_references(text: str, typst: bool) -> bool:
    """True when the paper carries a bibliography / references section.

    Markdown: a ``## References`` heading or a ``\\bibliography`` macro.
    Typst: a ``#bibliography(`` call OR a ``= References`` heading.
    """
    lower = text.lower()
    if "## references" in lower or "\\bibliography" in text:
        return True
    if typst:
        if "#bibliography(" in text:
            return True
        if re.search(r"^=+\s+references\s*$", text, re.MULTILINE | re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Named-section bodies
# ---------------------------------------------------------------------------


def section_body(text: str, section: str, typst: bool) -> str:
    """Return the body of a named IMRAD section, or "" if absent.

    Matches a heading of any depth (``#``…``######`` in Markdown,
    ``=``…``======`` in Typst) whose text equals ``section`` (case-
    insensitive). The captured body runs up to the next heading of the
    SAME-OR-SHALLOWER depth, so deeper sub-headings (e.g. a ``###
    Limitations`` block inside a ``## Discussion`` section) stay part of
    the parent body rather than truncating it.
    """
    marker = "=" if typst else "#"
    e = re.escape(marker)
    # Locate the heading and its depth (run-length of the marker).
    head = re.search(
        rf"^({e}{{1,6}})\s+{re.escape(section)}\s*$",
        text, re.MULTILINE | re.IGNORECASE,
    )
    if not head:
        return ""
    depth = len(head.group(1))
    rest = text[head.end():]
    # Stop at the next heading whose depth is <= this section's depth.
    nxt = re.search(rf"^{e}{{1,{depth}}}\s", rest, re.MULTILINE)
    body = rest[: nxt.start()] if nxt else rest
    return body.strip()


def has_section(text: str, section: str, typst: bool) -> bool:
    """True when a heading of any depth names ``section``."""
    marker = "=" if typst else "#"
    pat = rf"^{re.escape(marker)}{{1,6}}\s+{re.escape(section)}\s*$"
    return bool(re.search(pat, text, re.MULTILINE | re.IGNORECASE))


__all__ = [
    "PAPER_CANDIDATES",
    "resolve_paper_path",
    "is_typst",
    "figure_refs",
    "has_references",
    "section_body",
    "has_section",
]
