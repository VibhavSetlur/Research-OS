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
    # The scaffold authors posters with typst functions — #headline[...] and
    # #block-section(title: "..."). Recognise those first; fall back to typst/
    # markdown headings (= / #) for a hand-rolled poster. (The old check only
    # counted = / # headings and so false-BLOCKED every scaffolded poster.)
    headlines = (
        len(re.findall(r"#headline\b", text))
        + len(re.findall(r"#poster-headline\b", text))
    )
    block_sections = len(re.findall(r"#block-section\b", text))
    heading_sections = (
        len(re.findall(r"^=\s+", text, re.M)) or len(re.findall(r"^#\s+", text, re.M))
    )
    sections = block_sections or heading_sections
    has_title_field = bool(re.search(r"^#?title:|title:", text, re.I))
    if headlines < 1 and not has_title_field:
        # WARN, not BLOCK: a hand-rolled poster may carry its headline as a
        # large heading or a template title arg we can't see. The structural
        # requirement (>=3 sections, below) stays a blocker.
        warnings.append(
            "No #headline[...] detected — a Better-Poster reads best with one "
            "across-the-room-readable headline sentence. Confirm one is present."
        )
    if sections < 3:
        blockers.append(
            f"{sections} content section(s) detected. A poster needs at least "
            "Background / Methods / Results / Implication (#block-section(...))."
        )
    cites = len(re.findall(r"#cite\(<|\[@[^\]]+\]", text))
    if cites > 8:
        warnings.append(f"{cites} citations — posters usually keep ≤ 8.")
    return {
        "blockers": blockers,
        "warnings": warnings,
        "section_count": sections,
        "headline_count": headlines,
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
# Per-step recap antipattern: dashboards organised as "Step 01 / Step 02 /
# ..." with one section per workspace step are bookkeeping leaks, not
# narrative artefacts. We tolerate up to 3 such headings (a "comparison"
# block referencing 2-3 specific steps is fine); >3 is the failure mode
# synthesis_dashboard exists to prevent.
_STEP_HEADING_RE = re.compile(
    r"<h[1-4][^>]*>\s*Step\s+\d{1,3}\b[^<]*</h[1-4]>", re.I,
)
# Hero / TL;DR / headline anchor: the first viewport must deliver the
# top-line finding. We accept any of these tokens in a heading or
# section id.
_HERO_HINTS = (
    "headline", "tl;dr", "tldr", "hero", "key finding", "key findings",
    "top-line", "topline", "bottom line", "summary", "at a glance",
)
_HERO_HEADING_RE = re.compile(
    r"<h[1-3][^>]*>\s*([^<]{1,80})</h[1-3]>", re.I,
)
_HERO_SECTION_ID_RE = re.compile(
    r"<section[^>]*\bid\s*=\s*[\"']([^\"']{1,40})[\"']", re.I,
)

# Strip <script>...</script> and <style>...</style> bodies so vendored
# JS / CSS libraries don't trip placeholder + path-leak regexes.
# Close-tag pattern `</script[^>]*>` matches every HTML5-legal close
# form: `</script>`, `</script >`, `</script\nfoo>`, `</SCRIPT bar>`.
# The naive `</script>` form would miss whitespace + attribute variants
# (CodeQL flags the narrower pattern as Bad-HTML-filtering-regexp).
_SCRIPT_BODY_RE = re.compile(
    r"<script\b[^>]*>.*?</script[^>]*>",
    re.DOTALL | re.I,
)
_STYLE_BODY_RE = re.compile(
    r"<style\b[^>]*>.*?</style[^>]*>",
    re.DOTALL | re.I,
)


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
    # Per-step recap antipattern. A dashboard with 4+ `Step NN` headings
    # is the bookkeeping-leak structure synthesis_dashboard explicitly
    # forbids. Tolerate 3 (a comparison block referencing specific
    # steps is fine); reject more.
    step_headings = _STEP_HEADING_RE.findall(text)
    if len(step_headings) >= 4:
        blockers.append(
            f"Dashboard has {len(step_headings)} 'Step NN' section headings. "
            "Dashboards are organised by claim / decision / hypothesis, NOT "
            "by workspace step. Re-group sections by what was learned (e.g. "
            "'What lifted accuracy', 'Ruled out', 'Where the ceiling sits') "
            "and embed only the figures that move the argument."
        )
    elif len(step_headings) >= 2:
        warnings.append(
            f"Dashboard has {len(step_headings)} 'Step NN' section headings. "
            "Prefer claim-driven headings (e.g. 'Headline finding', 'What "
            "lifted accuracy') so the reader navigates by argument, not "
            "by chronology."
        )
    # Hero / TL;DR section — the first viewport must deliver the
    # top-line finding. Look for a heading or a section id containing
    # one of the hero hints.
    headings_lower = [
        m.lower() for m in _HERO_HEADING_RE.findall(text)
    ]
    section_ids_lower = [
        m.lower() for m in _HERO_SECTION_ID_RE.findall(text)
    ]
    has_hero = any(
        any(hint in h for hint in _HERO_HINTS) for h in headings_lower
    ) or any(
        any(hint.replace(" ", "-") in s or hint.replace(" ", "") in s
            for hint in _HERO_HINTS)
        for s in section_ids_lower
    )
    if not has_hero:
        warnings.append(
            "Dashboard has no hero / TL;DR / headline-finding section. "
            "The first viewport should deliver the project's top-line "
            "result so a reader who never scrolls still gets the point."
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

    # Synthesis + workspace hygiene run alongside every per-file check
    # so a single tool_synthesis_check call surfaces both deliverable-
    # specific blockers AND repository-shape drift (non-canonical
    # filenames, loose files at workspace root).
    hygiene_synth = synthesis_hygiene(root)
    if hygiene_synth.get("renames_needed"):
        warnings.extend(hygiene_synth["renames_needed"])
    hygiene_ws = workspace_hygiene(root)
    if hygiene_ws.get("relocations_needed"):
        warnings.extend(hygiene_ws["relocations_needed"])

    # Output-types intent gate: warn (don't block) if the AI is
    # auditing a synthesis file whose kind isn't in the researcher's
    # declared output_types. Educates without breaking projects that
    # haven't filled out the wizard's output_types field.
    gate = output_types_gate(root, kind)
    if gate.get("verdict") == "ask" and gate.get("message"):
        warnings.append(gate["message"])

    return {
        "status": "error" if blockers else "success",
        "kind": kind,
        "file": str(target),
        "mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "details": sub,
        "hygiene": {
            "synthesis": hygiene_synth,
            "workspace": hygiene_ws,
        },
        "intent_gate": gate,
    }


# ---------------------------------------------------------------------------
# Synthesis-directory hygiene — flag non-canonical files that the AI may
# author when it improvises filenames outside the supported synthesis
# protocols. Caught here so a single per-file synthesis_check call also
# surfaces "you authored synthesis/paper-lay.md but the canonical name
# is synthesis/lay_summary.md".
# ---------------------------------------------------------------------------


# Canonical names downstream tools (preview, cross-deliverable audit,
# share-archive bundler) recognise.
_CANONICAL_SYNTHESIS_FILES = frozenset({
    # AI-authored deliverables (one per supported synthesis protocol).
    "paper.typ", "paper.pdf", "paper.md", "paper.tex",
    "essay.typ", "essay.pdf",
    "slides.typ", "slides.pdf", "slides.html",
    "poster.typ", "poster.pdf", "poster_qr.png",
    "handout.typ", "handout.pdf", "handout_qr.png",
    "grant.typ", "grant.pdf",
    "dashboard.html",
    "lay_summary.md", "lay_summary.typ", "lay_summary.pdf",
    "abstract.md", "abstract.typ",
    "cover_letter.md", "cover_letter.typ", "cover_letter.pdf",
    "title_workshop.md",
    "report.typ", "report.pdf", "report.md",
    "progress_update.md", "progress_update.typ",
    "null_findings.md",
    # Bibliography + spec files (tool-managed).
    "biblio.yml", "biblio.bib", "biblio.json",
    "synthesis_spec.yaml",
    # Lit-review intermediates (literature/evidence_synthesis protocol).
    "evidence_table.md", "contradictions.md",
    # Figure-narrative brief (visualization/figure_narrative_arc protocol).
    "figure_brief.md",
    # README is project convention; archive holds prior versions.
    "README.md",
})

# Common AI-improvised names → canonical name the protocol expects.
_RENAME_HINTS: dict[str, str] = {
    "paper-lay.md": "lay_summary.md",
    "paper_lay.md": "lay_summary.md",
    "lay.md": "lay_summary.md",
    "summary.md": "lay_summary.md",
    "LAY.md": "lay_summary.md",
    "PRESS_RELEASE.md": "lay_summary.md",
    "REPRODUCIBILITY.md": (
        "[delete] reproducibility belongs in paper.typ Methods/Data "
        "Availability + workspace/logs/reproducibility_report.md"
    ),
    "reproducibility.md": (
        "[delete] reproducibility belongs in paper.typ Methods/Data "
        "Availability + workspace/logs/reproducibility_report.md"
    ),
    "METHODS.md": "[delete] update workspace/methods.md; render into paper.typ",
    "Methods.md": "[delete] update workspace/methods.md; render into paper.typ",
    "CITATIONS.md": "[delete] update workspace/citations.md; render into paper.typ References",
    "Citations.md": "[delete] update workspace/citations.md; render into paper.typ References",
    "Bibliography.md": "[delete] update workspace/citations.md; render into paper.typ References",
    "results.md": "[delete] render into paper.typ Results from workspace/<step>/conclusions.md",
    "discussion.md": "[delete] render into paper.typ Discussion",
    "introduction.md": "[delete] render into paper.typ Introduction",
}

# Subdirectories that are expected to live under synthesis/ — never
# flag these as non-canonical files.
_CANONICAL_SYNTHESIS_DIRS = frozenset({
    "figures", "scripts", "tables", "archive",
    "_typst_templates", "dashboard_data",
})


# Canonical workspace-root files (the rolling logs + tool-managed
# artefacts). Anything else loose at workspace root is hygiene noise.
_CANONICAL_WORKSPACE_FILES = frozenset({
    "analysis.md",
    "methods.md",
    "citations.md",
    "researcher_certifications.yaml",
})

# Workspace-root subdirectories Research-OS itself uses.
_CANONICAL_WORKSPACE_DIRS = frozenset({
    "logs", "scratch", "archive",
    ".preregistration",
})


def workspace_hygiene(root: Path) -> dict[str, Any]:
    """Walk workspace/ for loose-at-root files outside the canonical set.

    Research-OS keeps workspace/ disciplined:
      * Numbered step folders ``NN_<slug>/`` hold per-step state.
      * Rolling logs ``methods.md`` / ``analysis.md`` / ``citations.md``
        plus ``researcher_certifications.yaml`` live at workspace root.
      * ``scratch/`` holds ad-hoc work; ``logs/`` holds audit reports;
        ``archive/`` holds retired material.

    Anything ELSE at workspace root (planning docs, hand-rolled
    audits, .mermaid diagrams, agent briefs, version notes) is clutter
    that should live in ``scratch/`` or ``archive/``. We surface a
    rename / relocate hint for each offender. Hidden files and
    canonical subdirectories are ignored.
    """
    ws = root / "workspace"
    if not ws.exists():
        return {"relocations_needed": [], "offenders": []}

    relocations_needed: list[str] = []
    offenders: list[dict[str, str]] = []
    for entry in sorted(ws.iterdir()):
        name = entry.name
        if name.startswith("."):
            continue
        if entry.is_dir():
            if name in _CANONICAL_WORKSPACE_DIRS:
                continue
            # Numbered step folders are canonical.
            if _STEP_DIR_LIKE.match(name):
                continue
            # Anything else loose at workspace root is clutter (e.g.
            # an ad-hoc `planning/` dir).
            relocations_needed.append(
                f"workspace/{name}/ — loose subdirectory at workspace root. "
                "Move under workspace/scratch/ if it's ad-hoc, or rename "
                "to NN_<slug>/ if it's an analysis step."
            )
            offenders.append({"name": name, "kind": "dir"})
            continue
        if name in _CANONICAL_WORKSPACE_FILES:
            continue
        relocations_needed.append(
            f"workspace/{name} — loose file at workspace root. "
            "Move to workspace/scratch/ (planning notes, briefs), "
            "workspace/logs/ (audits, reports), or "
            "workspace/archive/ (retired material). The canonical "
            "rolling logs at workspace root are methods.md, "
            "analysis.md, citations.md, "
            "researcher_certifications.yaml."
        )
        offenders.append({"name": name, "kind": "file"})
    return {"relocations_needed": relocations_needed, "offenders": offenders}


# Numbered step folder pattern (NN_slug / NNN_slug). Compiled once at
# module load so workspace_hygiene's walk stays cheap.
_STEP_DIR_LIKE = re.compile(r"^\d{2,3}_[A-Za-z0-9]")


# ---------------------------------------------------------------------------
# Output-types gate — every synthesis protocol consults this before
# scaffolding or compiling. The researcher's wizard answer
# (researcher_config.yaml#research_goal.output_types) is the contract
# the AI must honour; auto-creating deliverables outside that contract
# wastes context and produces material the user didn't ask for.
# ---------------------------------------------------------------------------


# File-kind detected by _file_kind() → canonical output_types keyword. Used
# by output_types_gate() so the gate can be invoked with the same kind
# string check.py already uses for per-file linting.
_KIND_TO_OUTPUT_TYPE: dict[str, str] = {
    "paper": "paper",
    "essay": "essay",
    "slides": "slides",
    "poster": "poster",
    "dashboard": "dashboard",
    "report": "report",
    "grant": "grant",
    "lay_summary": "lay_summary",
    "handout": "handout",
    "abstract": "abstract",
}


def output_types_gate(
    root: Path, kind: str, *, autonomy: str | None = None
) -> dict[str, Any]:
    """Return a verdict on whether this synthesis kind matches the
    researcher's declared output_types.

    Verdicts:
      - ``proceed``: declared output_types is empty (no preference yet),
        OR the kind is in the declared set. The AI may scaffold /
        compile without confirmation.
      - ``ask``: declared output_types is non-empty and the kind is NOT
        in the set. The AI MUST confirm with the researcher before
        scaffolding. The returned ``message`` is a one-line prompt the
        AI can lift verbatim.
      - ``skip``: only returned when the researcher has explicitly
        opted this kind out (currently surfaced via
        ``research_goal.output_types`` containing ``not_<kind>`` /
        ``no_<kind>``; reserved for future use).

    Empty output_types is treated as "open" so the gate teaches new
    projects rather than blocking them. Once the wizard's defaults
    seed a non-empty list (the maintainer's intended path), the gate
    becomes load-bearing automatically.

    The ``autonomy`` arg is reserved for callers that want the gate to
    also enforce the autonomy ladder (manual / supervised → ask even
    on a match; autopilot → proceed silently). Defaults to None, in
    which case only output_types membership is checked.
    """
    # Local import to avoid a circular dep — protocol.py uses helpers
    # from this module's neighbours during preflight.
    try:
        from research_os.tools.actions.protocol import (
            _declared_output_types,
            _normalise_output_kind,
        )
    except Exception:
        return {
            "verdict": "proceed",
            "declared_outputs": [],
            "message": "",
            "kind": kind,
        }

    declared = _declared_output_types(root)
    target = _KIND_TO_OUTPUT_TYPE.get(_normalise_output_kind(kind)) or _normalise_output_kind(kind)

    if not declared:
        return {
            "verdict": "proceed",
            "declared_outputs": [],
            "message": "",
            "kind": target,
        }
    if target in declared:
        # Autonomy-mode soft gate: in manual / supervised we still ask
        # if the caller passed an autonomy hint and it's not autopilot,
        # because the wizard's "I want a paper" is a far-future intent
        # — confirming the AI should start authoring NOW is courteous.
        if autonomy and autonomy.lower() in {"manual", "supervised", "coaching"}:
            return {
                "verdict": "ask",
                "declared_outputs": declared,
                "message": (
                    f"You declared `{target}` as a research goal — "
                    f"start scaffolding `synthesis/{target}` now? "
                    "(say `yes` to proceed, `not yet` to defer)."
                ),
                "kind": target,
            }
        return {
            "verdict": "proceed",
            "declared_outputs": declared,
            "message": "",
            "kind": target,
        }
    # Mismatch: declared outputs don't include this kind.
    return {
        "verdict": "ask",
        "declared_outputs": declared,
        "message": (
            f"Heads up: you declared `output_types: {declared}` in "
            f"`inputs/researcher_config.yaml` but are about to scaffold "
            f"`synthesis/{target}`. Was that intended? Say `yes, add "
            f"{target}` to add it to your goals (recommended), `skip` "
            "to abort, or `just this once` to scaffold without "
            "updating the config."
        ),
        "kind": target,
    }


def synthesis_hygiene(root: Path) -> dict[str, Any]:
    """Walk synthesis/ for non-canonical files the AI may have authored
    when it improvised filenames outside the supported protocols.

    Reports:
      - ``renames_needed``: list of human-readable rename / delete hints
        (one per offending file).
      - ``offenders``: structured list of ``{name, suggested}`` entries
        so callers can act programmatically.

    Designed to be cheap (one scandir pass) and side-effect-free.
    """
    sdir = root / "synthesis"
    if not sdir.exists():
        return {"renames_needed": [], "offenders": []}

    renames_needed: list[str] = []
    offenders: list[dict[str, str]] = []
    for entry in sorted(sdir.iterdir()):
        if entry.is_dir():
            # Don't audit subdirectories — figures/, archive/, etc.
            continue
        name = entry.name
        if name in _CANONICAL_SYNTHESIS_FILES:
            continue
        # Hidden files (.DS_Store, .gitkeep) are ignored.
        if name.startswith("."):
            continue
        suggested = _RENAME_HINTS.get(name)
        if suggested:
            renames_needed.append(
                f"synthesis/{name} → {suggested} "
                "(non-canonical filename; downstream synthesis tools "
                "do not recognise this name)."
            )
            offenders.append({"name": name, "suggested": suggested})
        else:
            # Unknown but not hint-recognised — soft warning.
            renames_needed.append(
                f"synthesis/{name} — non-canonical synthesis artefact "
                "(downstream tools may not pick it up). Move to "
                "synthesis/archive/ if you need to keep it, or fold its "
                "content into the canonical paper.typ / dashboard.html / "
                "lay_summary.md deliverable."
            )
            offenders.append({"name": name, "suggested": "archive_or_fold"})
    return {"renames_needed": renames_needed, "offenders": offenders}
