"""Quality checks for AI-authored synthesis files.

Tools validate, the AI authors. This module audits an AI-written
synthesis file (paper.typ, slides.typ, poster.typ, dashboard.html,
essay.typ) against the standards expected for that artefact. It
does NOT generate content — only reports blockers + warnings the
AI can act on before compile/share.

Public surface: synthesis_check(root, file, mode) -> dict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit.content_depth import (
    audit_abstract,
    audit_cliches,
    audit_discussion,
    audit_introduction,
    audit_methods,
    audit_references_present,
    audit_results,
)


# ---------------------------------------------------------------------------
# File-type detection + section extraction
# ---------------------------------------------------------------------------


_SLIDES_HTML_MARKERS = (
    "reveal.js",
    "Reveal.initialize",
    "data-state=\"reveal",
    "marp-",
    "<!-- marp",
    "class=\"reveal",
    "touying",
)


def _file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.stem.lower()
    if suffix == ".html":
        # An HTML file is usually a dashboard but can be a slide deck
        # (Reveal.js / Marp / Touying export). Sniff the content to
        # distinguish; otherwise the slides validation path is
        # unreachable and the dashboard checks run on something that
        # isn't a dashboard.
        if "slide" in name:
            return "slides"
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            head = ""
        if any(marker in head for marker in _SLIDES_HTML_MARKERS):
            return "slides"
        return "dashboard"
    if suffix in {".typ", ".md", ".tex"}:
        if "slide" in name:
            return "slides"
        if "poster" in name:
            return "poster"
        if "essay" in name:
            return "essay"
        return "paper"
    return "unknown"


def _section_text_universal(text: str, section: str) -> str:
    """Extract a section's body, supporting both Markdown and Typst headings."""
    # Markdown: ## Section, ### Section
    m = re.search(
        rf"^#{{2,3}}\s+{section}\s*\n(.+?)(?=^#{{2,3}}\s|\Z)",
        text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Typst: = Section, == Section
    m = re.search(
        rf"^={{1,2}}\s+{section}\s*\n(.+?)(?=^={{1,2}}\s|\Z)",
        text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return (m.group(1) if m else "").strip()


# ---------------------------------------------------------------------------
# Paper / essay / report checks (run on the unified text, detecting headings)
# ---------------------------------------------------------------------------


def _check_paper(text: str, root: Path) -> dict[str, Any]:
    sub_reports = {
        "abstract": audit_abstract(_section_text_universal(text, "abstract")),
        "introduction": audit_introduction(_section_text_universal(text, "introduction")),
        "methods": audit_methods(_section_text_universal(text, "methods"), root),
        "results": audit_results(_section_text_universal(text, "results"), root),
        "discussion": audit_discussion(_section_text_universal(text, "discussion"), root),
        "references": audit_references_present(text),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    for name, r in sub_reports.items():
        for b in r.get("blockers", []):
            blockers.append(f"[{name}] {b}")
        for w in r.get("warnings", []):
            warnings.append(f"[{name}] {w}")
    methods_uncov = sub_reports["methods"].get("uncovered_steps", [])
    results_unref = sub_reports["results"].get("figures_unreferenced", [])
    if len(methods_uncov) >= 2 and len(results_unref) >= 2:
        blockers.append(
            f"Per-step coverage failure: {len(methods_uncov)} step(s) missing "
            f"from Methods AND {len(results_unref)} focal figure(s) missing "
            "from Results."
        )
    return {"blockers": blockers, "warnings": warnings, "sub_reports": sub_reports}


# ---------------------------------------------------------------------------
# Slides checks (claim-per-slide, citation cap, no path leaks)
# ---------------------------------------------------------------------------


def _check_slides(text: str) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    # Slide counts — Touying uses #slide[…], Marp uses --- separators,
    # Reveal.js HTML uses <section> elements with .slides parent.
    slide_count = (
        len(re.findall(r"#slide\b", text))
        + len(re.findall(r"^==\s+", text, re.M))
        + len(re.findall(r"^---\s*$", text, re.M))
        + len(re.findall(r"<section\b", text, re.I))
    )
    if slide_count < 4:
        blockers.append(
            f"Only {slide_count} slide(s) detected. A real talk has at least 8."
        )
    elif slide_count > 60:
        warnings.append(f"{slide_count} slides — likely over budget for any audience.")
    # Speaker notes. Touying: #notes[...] | Reveal HTML: <aside class="notes">
    # | Marp: <!-- notes -->.
    note_count = (
        len(re.findall(r"#notes\b", text))
        + len(re.findall(r"<aside[^>]*class\s*=\s*[\"']notes[\"']", text, re.I))
        + len(re.findall(r"<!--\s*notes", text, re.I))
    )
    if note_count == 0:
        warnings.append(
            "No speaker notes detected. Each slide should carry ≥1 sentence of "
            "what to say."
        )
    elif slide_count > 0 and note_count < slide_count // 2:
        warnings.append(
            f"Only {note_count} speaker notes for {slide_count} slides — most "
            "slides have no notes."
        )
    # Citation cap.
    cites = len(re.findall(r"#cite\(<|\[@[^\]]+\]", text))
    if cites > 12:
        warnings.append(f"{cites} citations — slides usually need ≤ 12.")
    # Path leaks (forbidden in deck-visible text).
    path_leaks = re.findall(r"workspace/[\w/.-]+\.\w+", text)
    if path_leaks:
        warnings.append(
            f"{len(path_leaks)} filesystem path(s) visible in the deck: "
            f"{path_leaks[0]}. Audiences should not see file paths."
        )
    return {
        "blockers": blockers,
        "warnings": warnings,
        "slide_count": slide_count,
        "speaker_notes_count": note_count,
        "citation_count": cites,
    }


# ---------------------------------------------------------------------------
# Poster checks (single headline, ≤8 cites, figure DPI)
# ---------------------------------------------------------------------------


def _check_poster(text: str) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not re.search(r"^#?title:|title:", text, re.I):
        warnings.append("No title declared — posters need one headline sentence.")
    sections = len(re.findall(r"^=\s+", text, re.M)) or len(re.findall(r"^#\s+", text, re.M))
    if sections < 3:
        blockers.append(
            f"{sections} section(s) detected. A poster needs at least Background "
            "/ Methods / Results / Implication."
        )
    cites = len(re.findall(r"#cite\(<|\[@[^\]]+\]", text))
    if cites > 8:
        warnings.append(f"{cites} citations — posters usually keep ≤ 8.")
    return {
        "blockers": blockers,
        "warnings": warnings,
        "section_count": sections,
        "citation_count": cites,
    }


# ---------------------------------------------------------------------------
# Dashboard (HTML) checks — engineering invariants, NOT structure
# ---------------------------------------------------------------------------


_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|TBD|Lorem ipsum|PLACEHOLDER|AI: author)\b", re.I)
# Unfilled template tokens like {project_title} that slip through into
# slide titles + dashboard body text — the clearest sign the AI never
# substituted the scaffold placeholder.
_TOKEN_RE = re.compile(r"\{[a-z][a-z0-9_]{2,40}\}")
# Headings that look like raw workspace directory names. Real authored
# content never uses `01_baseline_eda` as a heading.
_DIR_DUMP_HEADING_RE = re.compile(
    r"<h[1-3][^>]*>\s*\d{2,3}_[a-z][a-z0-9_]*\s*</h[1-3]>", re.I,
)

# Strip <script>...</script> and <style>...</style> bodies so vendored
# JS / CSS libraries don't trip placeholder + path-leak regexes.
_SCRIPT_BODY_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.I)
_STYLE_BODY_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.I)


def _strip_script_style(text: str) -> str:
    text = _SCRIPT_BODY_RE.sub("", text)
    text = _STYLE_BODY_RE.sub("", text)
    return text


def _check_dashboard(text: str, root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    visible = _strip_script_style(text)
    byte_count = len(text)

    # Engineering invariant: offline (no http: scripts/links).
    if re.search(r'<script[^>]+src\s*=\s*"http', text, re.I):
        blockers.append("Dashboard loads external script(s). Must be offline.")
    if re.search(r'<link[^>]+href\s*=\s*"http', text, re.I):
        warnings.append("Dashboard references external stylesheet(s).")
    # Accessibility: alt-text on every image.
    imgs = re.findall(r"<img[^>]+>", text, re.I)
    missing_alt = [i for i in imgs if not re.search(r'\balt\s*=\s*["\']', i)]
    if missing_alt:
        blockers.append(
            f"{len(missing_alt)}/{len(imgs)} <img> tag(s) missing alt text. "
            "Every image needs alt text for accessibility."
        )
    # Semantic structure: every <section> has an id.
    sections = re.findall(r"<section[^>]*>", text, re.I)
    sections_no_id = [s for s in sections if not re.search(r'\bid\s*=\s*["\']', s)]
    if sections_no_id and len(sections_no_id) >= 2:
        warnings.append(
            f"{len(sections_no_id)} <section> tag(s) lack an id attribute. "
            "Add ids so anchors and TOCs work."
        )
    # Headings: at least one h1 and the structure isn't flat.
    h1s = re.findall(r"<h1\b", text, re.I)
    h2s = re.findall(r"<h2\b", text, re.I)
    if len(h1s) == 0:
        warnings.append("Dashboard has no <h1>. Add a top-level heading.")
    if len(h2s) < 2:
        warnings.append(f"Dashboard has {len(h2s)} <h2>. Use sections to organise content.")
    # Placeholders (search the VISIBLE text only — vendored JS may contain
    # the words 'TODO' / 'Lorem ipsum' in license comments without being
    # authored placeholders).
    placeholders = _TODO_RE.findall(visible)
    if placeholders:
        blockers.append(
            f"Dashboard contains {len(placeholders)} placeholder marker(s) "
            f"(e.g. {placeholders[0]!r}). Replace before sharing."
        )
    # Unfilled `{token}` substitutions in visible text.
    tokens = _TOKEN_RE.findall(visible)
    if tokens:
        warnings.append(
            f"Dashboard has {len(tokens)} unfilled token(s) in body text "
            f"(e.g. {tokens[0]!r}). These look like un-substituted templates."
        )
    # Directory-dump headings — the fingerprint of auto-generated trash.
    dir_dump = _DIR_DUMP_HEADING_RE.findall(text)
    if dir_dump:
        blockers.append(
            f"Dashboard has {len(dir_dump)} heading(s) that are raw workspace "
            "directory names (e.g. '01_baseline_eda'). Use descriptive prose "
            "headings — readers don't navigate by step number."
        )
    # Path leaks (filesystem paths visible in body text, not script comments).
    path_leaks = re.findall(r"workspace/[\w/.-]+\.\w+", visible)
    if path_leaks:
        warnings.append(
            f"{len(path_leaks)} filesystem path(s) in body text. Reader should "
            "not see workspace paths."
        )
    # Bundle size — dashboards over 2MB are almost certainly hoarding
    # base64 figures or vendored libs they don't need.
    mb = byte_count / (1024 * 1024)
    if mb > 5:
        blockers.append(
            f"Dashboard is {mb:.1f}MB. >5MB is too large to email; either "
            "downsample figures or drop unused vendored libraries."
        )
    elif mb > 2:
        warnings.append(
            f"Dashboard is {mb:.1f}MB. Consider downsampling embedded "
            "figures or pruning unused vendored libraries."
        )
    return {
        "blockers": blockers,
        "warnings": warnings,
        "img_count": len(imgs),
        "section_count": len(sections),
        "byte_count": byte_count,
        "mb": round(mb, 2),
    }


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


def synthesis_check(
    root: Path,
    file: str | None = None,
    mode: str = "all",
) -> dict[str, Any]:
    """Quality-check an AI-authored synthesis file.

    Args:
      root: project root.
      file: synthesis file path (relative or absolute). Default: first
        existing of synthesis/{paper,slides,poster,essay}.typ or
        synthesis/dashboard.html.
      mode: 'all' (default), 'substantiveness', 'structure',
        'accessibility', 'cliches'. 'all' runs every check appropriate
        to the file type.
    """
    if file:
        target = Path(file)
        target = target if target.is_absolute() else (root / target)
    else:
        candidates = (
            "synthesis/paper.typ",
            "synthesis/essay.typ",
            "synthesis/grant.typ",
            "synthesis/slides.typ",
            "synthesis/poster.typ",
            "synthesis/handout.typ",
            "synthesis/dashboard.html",
            "synthesis/slides.html",
            "synthesis/paper.md",
        )
        target = None
        for c in candidates:
            cp = root / c
            if cp.exists():
                target = cp
                break
        if target is None:
            return {
                "status": "error",
                "message": (
                    "No synthesis file found. Expected one of "
                    f"{', '.join(candidates)}."
                ),
            }

    if not target.exists():
        return {
            "status": "error",
            "message": f"{target.relative_to(root) if target.is_relative_to(root) else target} not found.",
        }

    text = target.read_text(encoding="utf-8", errors="replace")
    kind = _file_kind(target)

    blockers: list[str] = []
    warnings: list[str] = []
    sub: dict[str, Any] = {}

    if kind in ("paper", "essay"):
        if mode in ("all", "substantiveness", "structure"):
            r = _check_paper(text, root)
            blockers.extend(r["blockers"])
            warnings.extend(r["warnings"])
            sub["sections"] = r["sub_reports"]
        if mode in ("all", "cliches"):
            c = audit_cliches(
                str(target.relative_to(root)) if target.is_relative_to(root) else str(target),
                root,
            )
            warnings.extend(c.get("warnings", []))
            sub["cliches"] = c
    elif kind == "slides":
        r = _check_slides(text)
        blockers.extend(r["blockers"])
        warnings.extend(r["warnings"])
        sub["slides"] = r
    elif kind == "poster":
        r = _check_poster(text)
        blockers.extend(r["blockers"])
        warnings.extend(r["warnings"])
        sub["poster"] = r
    elif kind == "dashboard":
        r = _check_dashboard(text, root)
        blockers.extend(r["blockers"])
        warnings.extend(r["warnings"])
        sub["dashboard"] = r
    else:
        return {
            "status": "error",
            "message": f"Unsupported file type: {target.suffix}",
        }

    return {
        "status": "error" if blockers else "success",
        "kind": kind,
        "file": str(target),
        "mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "details": sub,
    }
