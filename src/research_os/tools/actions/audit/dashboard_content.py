"""Dashboard content quality gates.

The companion to the existing dashboard renderer audit. The renderer
audit checks the dashboard renders; this module checks that the CONTENT
inside is grounded, accessible, palette-consistent, and shaped like
something a reviewer would actually read instead of skim past. Seven
sub-checks; one wrapper tool ``tool_audit_dashboard_content``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.audit.dashboard_content")


# Section heading patterns we expect in a dashboard.html. The renderer
# tags sections with <section id="..."> and an <h2> heading; we match
# either form.
#
# NOTE (3.2.8): ``per_step`` and ``audit`` were removed. They rewarded the
# exact per-step recap structure (one section per workspace step) that
# ``synthesis_dashboard`` / ``deliverable_design`` explicitly ban — a
# dashboard is organised by CLAIM / DECISION / COMPARISON, never by
# chronology. Looking for a ``per_step`` section taught the wrong shape;
# the ``per_step_recap_headings`` check below now actively flags it.
DASHBOARD_SECTIONS = (
    "abstract", "overview", "findings",
    "glossary", "references",
)


# Per-section substantiveness bars.
SECTION_BARS = {
    "abstract":   {"min_words": 150, "min_findings": 1, "min_methods": 1, "min_figs": 0},
    "overview":   {"min_words": 200, "min_hypotheses": 1, "min_figs": 0},
    "findings":   {"min_words": 300, "min_claims": 3, "min_figs": 1},
    "glossary":   {"min_entries": 3},
    "references": {"min_entries": 1},
}


_NUMBER_WITH_UNIT = re.compile(
    r"\b(\d+\.?\d*)\s*(%|years?|fold|mg|μg|ug|μm|um|nm|ml|mL|"
    r"L|kg|sec|seconds|min|minutes|hr|hours|days|weeks|months|"
    r"cells|samples|patients|subjects|points|dimensions|epochs|"
    r"std|sd|p|q|n)\b",
    re.IGNORECASE,
)
_NAKED_NUMBER = re.compile(r"(?<!\w)\d+\.?\d*(?!\w)")

# HTML comments: `<!-- ... -->`. Commented-out markup is inert and must
# not be counted by the alt-text / `<section>` / placeholder scans (the
# bundled dashboard scaffold otherwise trips its own audit).
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_html_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub("", text)


# ---------------------------------------------------------------------------
# 1. Numeric claim cross-check
# ---------------------------------------------------------------------------


def audit_numeric_grounding(
    dashboard_html: str, root: Path, *, tolerance_pct: float = 1.0,
) -> dict[str, Any]:
    """Every number in dashboard.html must appear in some workspace table
    or in workspace/citations.md (for cited statistics).

    Tolerance is ±1% for rounded numbers (so 1234.567 vs 1235 both OK).
    Returns blockers list of ungrounded numbers (with context).
    """
    # Strip <script>...</script> and <style>...</style> first. The
    # closing tag pattern uses `</script\b[^>]*>` so it tolerates any
    # whitespace / attribute garbage that a sloppy renderer might
    # emit — without it the strip leaks script source into the
    # numeric scan and CodeQL flags an incomplete-tag-sanitisation
    # hazard.
    body = re.sub(r"<script\b[^>]*>.*?</script\b[^>]*>", "", dashboard_html, flags=re.S | re.I)
    body = re.sub(r"<style\b[^>]*>.*?</style\b[^>]*>", "", body, flags=re.S | re.I)
    body_text = re.sub(r"<[^>]+>", " ", body)

    candidate_nums = []
    for m in _NUMBER_WITH_UNIT.finditer(body_text):
        candidate_nums.append((m.group(1), m.start()))
    # Don't flag tiny integers (year, page counts, etc.) without units.
    # We focus on UNITED numbers + standalone decimals.
    for m in _NAKED_NUMBER.finditer(body_text):
        token = m.group(0)
        if "." in token or len(token) >= 3:  # 0.234 or 234+ - likely a real claim
            candidate_nums.append((token, m.start()))

    # Build the source corpus.
    source_nums: set[float] = set()
    workspace = root / "workspace"
    if workspace.is_dir():
        for step in workspace.iterdir():
            if not step.is_dir() or not step.name[:2].isdigit():
                continue
            tables = step / "outputs" / "tables"
            if tables.is_dir():
                for tbl in tables.iterdir():
                    if tbl.suffix.lower() in {".csv", ".tsv", ".txt"}:
                        try:
                            txt = tbl.read_text(encoding="utf-8", errors="replace")
                            for tok in _NAKED_NUMBER.findall(txt):
                                try:
                                    source_nums.add(float(tok))
                                except ValueError:
                                    # Token wasn't a parseable float (e.g.
                                    # date fragment); skip it.
                                    continue
                        except OSError:
                            continue
            # Also pull from conclusions.md (the per-step source of truth).
            for fname in ("conclusions.md",):
                p = step / fname
                if p.exists():
                    try:
                        txt = p.read_text(encoding="utf-8", errors="replace")
                        for tok in _NAKED_NUMBER.findall(txt):
                            try:
                                source_nums.add(float(tok))
                            except ValueError:
                                # Token wasn't a parseable float; skip.
                                continue
                    except OSError:
                        continue

    cit = root / "workspace" / "citations.md"
    if cit.exists():
        try:
            txt = cit.read_text(encoding="utf-8", errors="replace")
            for tok in _NAKED_NUMBER.findall(txt):
                try:
                    source_nums.add(float(tok))
                except ValueError:
                    # Token wasn't a parseable float; skip.
                    continue
        except OSError:
            # citations.md unreadable — keep whatever the workspace
            # tables already contributed.
            pass

    tol = tolerance_pct / 100.0
    ungrounded: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for tok, pos in candidate_nums:
        if tok in seen_tokens:
            continue
        seen_tokens.add(tok)
        try:
            val = float(tok)
        except ValueError:
            continue
        # Skip pure integers below 10 and obvious page/year ids (1900-2100).
        if val == int(val) and val < 10:
            continue
        if 1900 <= val <= 2100 and val == int(val):
            continue
        # Tolerance check.
        ok = any(
            sv == 0 and val == 0
            or (sv != 0 and abs(sv - val) / max(abs(sv), abs(val)) <= tol)
            for sv in source_nums
        )
        if not ok:
            ctx_start = max(0, pos - 40)
            ctx_end = min(len(body_text), pos + 40)
            ungrounded.append({
                "value": tok,
                "context": body_text[ctx_start:ctx_end].strip(),
            })

    blockers = []
    if ungrounded:
        blockers.append(
            f"{len(ungrounded)} ungrounded number(s) in dashboard "
            f"(not found in workspace tables or citations).  "
            f"Examples: {', '.join(u['value'] for u in ungrounded[:5])}"
        )

    return {
        "ungrounded": ungrounded,
        "n_source_numbers": len(source_nums),
        "n_dashboard_numbers": len(seen_tokens),
        "blockers": blockers,
    }


# ---------------------------------------------------------------------------
# 2. Figure-to-text proximity
# ---------------------------------------------------------------------------


def audit_figure_proximity(dashboard_html: str) -> dict[str, Any]:
    """For each embedded figure, the surrounding ±2 paragraphs must
    mention it (by caption, alt, or 'Figure N' reference)."""
    figure_blocks = list(re.finditer(
        r'<figure[^>]*>(.*?)</figure>',
        dashboard_html, re.S | re.I,
    ))
    orphans: list[dict[str, Any]] = []
    for i, fig in enumerate(figure_blocks, start=1):
        # Look at ±2 paragraphs of HTML around the figure.
        start = max(0, fig.start() - 2000)
        end = min(len(dashboard_html), fig.end() + 2000)
        ctx = dashboard_html[start:end]
        figure_n = f"Figure {i}"
        # Pull the alt or figcaption to use as a stem to look for.
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig.group(0), re.S | re.I)
        stems: list[str] = [figure_n.lower(), f"fig {i}", f"fig. {i}"]
        if cap:
            cap_text = re.sub(r"<[^>]+>", "", cap.group(1)).strip().lower()
            if len(cap_text) > 20:
                first_phrase = cap_text.split(".")[0][:60]
                stems.append(first_phrase)
        ctx_lower = re.sub(r"<[^>]+>", " ", ctx).lower()
        if not any(s and s in ctx_lower for s in stems):
            orphans.append({"figure_index": i})
    warnings = []
    if orphans:
        warnings.append(
            f"{len(orphans)} figure(s) lack a nearby citation in body text "
            f"(within ±2 paragraphs)."
        )
    return {"orphan_figures": orphans, "n_figures": len(figure_blocks), "warnings": warnings}


# ---------------------------------------------------------------------------
# 3. Section substantiveness
# ---------------------------------------------------------------------------


_AI_CLICHE_PATTERNS = (
    "in this study, we investigate",
    "our results demonstrate",
    "future work should explore",
    "it is important to note that",
    "however, more research is needed",
    "this finding has important implications",
    "in conclusion,",
    "to the best of our knowledge",
)


def audit_section_substantiveness(dashboard_html: str) -> dict[str, Any]:
    """Per-section word floors + bar-specific content checks."""
    blockers: list[str] = []
    warnings: list[str] = []
    section_stats: dict[str, dict[str, Any]] = {}

    for section in DASHBOARD_SECTIONS:
        m = re.search(
            rf'<section[^>]*\bid=["\']{section}["\'][^>]*>(.*?)</section>',
            dashboard_html, re.S | re.I,
        )
        if not m:
            continue
        raw = m.group(1)
        text = re.sub(r"<[^>]+>", " ", raw).strip()
        words = text.split()
        n_words = len(words)
        bar = SECTION_BARS.get(section, {})
        s_stat: dict[str, Any] = {"words": n_words}
        if "min_words" in bar and n_words < bar["min_words"]:
            warnings.append(
                f"Dashboard section '{section}' is {n_words} words "
                f"(min {bar['min_words']})."
            )
        if section == "abstract":
            n_nums = sum(1 for _ in _NAKED_NUMBER.finditer(text))
            if n_nums < 1:
                blockers.append("Abstract has no numbers — quantify the finding.")
            s_stat["numbers"] = n_nums
        if section == "findings":
            # Claim heuristic: count sentences ending in a period that contain
            # both a digit and a verb-shaped word.
            sentences = re.split(r"(?<=[.!?])\s+", text)
            claims = [s for s in sentences if re.search(r"\d", s) and len(s.split()) >= 5]
            if len(claims) < bar.get("min_claims", 3):
                warnings.append(
                    f"Findings section has {len(claims)} quantitative claim(s) "
                    f"(target ≥ {bar['min_claims']})."
                )
            s_stat["claims"] = len(claims)
        cliche_hits = [c for c in _AI_CLICHE_PATTERNS if c in text.lower()]
        if cliche_hits:
            warnings.append(
                f"Dashboard section '{section}' contains AI-cliché phrases: "
                f"{', '.join(cliche_hits[:3])}"
            )
        s_stat["cliches"] = cliche_hits
        section_stats[section] = s_stat

    return {"section_stats": section_stats, "blockers": blockers, "warnings": warnings}


# ---------------------------------------------------------------------------
# 4. Accessibility (WCAG 2.2 AA, basics)
# ---------------------------------------------------------------------------


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return 0.5
    try:
        rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return 0.5
    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [_ch(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    lf = _relative_luminance(fg_hex)
    lb = _relative_luminance(bg_hex)
    light, dark = max(lf, lb), min(lf, lb)
    return (light + 0.05) / (dark + 0.05)


def audit_accessibility(dashboard_html: str) -> dict[str, Any]:
    """Heuristic WCAG 2.2 AA checks: contrast, alt-text, heading levels,
    button labels. Warnings only (don't block; surface in report)."""
    warnings: list[str] = []

    # Heading hierarchy: detect h1→h3 skips.
    levels = [int(m.group(1)) for m in re.finditer(r"<h([1-6])\b", dashboard_html, re.I)]
    last = 0
    for lvl in levels:
        if last and lvl > last + 1:
            warnings.append(f"Heading hierarchy skip detected: h{last} → h{lvl}.")
            break
        last = lvl

    # Images missing alt. The lookbehind `(?<![\w-])` keeps `data-alt=`
    # from satisfying the check.
    img_no_alt = re.findall(
        r"<img\b(?![^>]*(?<![\w-])alt=)[^>]*>", dashboard_html, re.I
    )
    if img_no_alt:
        warnings.append(f"{len(img_no_alt)} <img> tag(s) missing alt= attribute.")

    # Buttons / links missing accessible name.
    for tag in ("button", "a"):
        for m in re.finditer(
            rf"<{tag}\b([^>]*)>(.*?)</{tag}>", dashboard_html, re.S | re.I,
        ):
            attrs, inner = m.group(1), m.group(2)
            has_aria = re.search(r"aria-label\s*=", attrs, re.I)
            has_title = re.search(r"\btitle\s*=", attrs, re.I)
            inner_text = re.sub(r"<[^>]+>", "", inner).strip()
            if not (has_aria or has_title or inner_text):
                warnings.append(
                    f"<{tag}> element without accessible name "
                    f"(no aria-label / title / inner text)."
                )
                break

    # Contrast: pull foreground/background pairs from inline style or
    # the embedded <style> block.
    style_block = "\n".join(
        m.group(1)
        for m in re.finditer(r"<style[^>]*>(.*?)</style>", dashboard_html, re.S | re.I)
    )
    pairs = re.findall(
        r"color\s*:\s*(#[0-9a-fA-F]{3,6})[^}]*background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})",
        style_block,
    )
    low_contrast: list[tuple[str, str, float]] = []
    for fg, bg in pairs:
        ratio = _contrast_ratio(fg, bg)
        if ratio < 4.5:
            low_contrast.append((fg, bg, ratio))
    if low_contrast:
        warnings.append(
            f"{len(low_contrast)} CSS rule(s) with text contrast below WCAG AA (4.5:1)."
        )

    return {"warnings": warnings, "n_low_contrast": len(low_contrast)}


# ---------------------------------------------------------------------------
# 5. Print-friendly variant (heuristic — full pyppeteer pass is opt-in)
# ---------------------------------------------------------------------------


def audit_print_friendly(dashboard_html: str) -> dict[str, Any]:
    """Heuristic: scan the @media print block for red flags."""
    warnings: list[str] = []
    m = re.search(r"@media\s+print\s*\{(.+?)\}\s*</style>", dashboard_html, re.S | re.I)
    if not m:
        warnings.append("No @media print stylesheet detected — print variant unverified.")
        return {"warnings": warnings, "has_print_stylesheet": False}
    block = m.group(1)
    if re.search(r"figure\s*\{[^}]*display\s*:\s*none", block, re.I):
        warnings.append("Print stylesheet hides <figure> — figures will drop from PDF print.")
    if re.search(r"\.gallery\s*\{[^}]*display\s*:\s*none", block, re.I):
        warnings.append("Print stylesheet hides .gallery — review tile may disappear.")
    return {"warnings": warnings, "has_print_stylesheet": True}


# ---------------------------------------------------------------------------
# 6. Colour quality — restraint + no-neon (NOT a membership allow-list)
# ---------------------------------------------------------------------------
#
# Before 3.2.8 this check punished any colour outside a hardcoded Okabe-Ito /
# viridis / PuOr / RO-accent allow-list — which flagged a *custom-but-
# professional* palette (clinical slate-blue, an institution brand) as
# "wrong". That is membership policing, not a design judgement.
#
# The doctrine: the audit judges QUALITY, not conformity. A custom palette is
# fine if it shows restraint (few hues), survives colour-vision deficiency,
# and never uses neon. So this check now:
#   * BLOCKS on a NEON chart colour (electric / fluorescent = amateur), and
#   * WARNS when too many distinct off-(declared-)palette hues are present
#     (a restraint signal — rainbow accent roulette), reusing the shared
#     ``palettes.py`` colour science so chrome + figures + audit agree on
#     "is this professional?".
#
# Crucially it SCANS THE CHROME ``<style>`` block (the page's own palette
# tokens) but excludes ``<script>`` bodies (vendored JS hex literals are not
# design choices). The shared ``is_near_neutral`` excludes greys/hairlines.


_SCRIPT_BODY_RE = re.compile(r"<script\b[^>]*>.*?</script\b[^>]*>", re.DOTALL | re.I)


def audit_color_palette(
    dashboard_html: str, declared_palette: str | None = None,
) -> dict[str, Any]:
    """Judge the page's colour choices on QUALITY (restraint + no-neon),
    not membership.

    NEON chart colour → block. >3 distinct off-(declared-)palette,
    non-neutral hues → warn (a restraint / rainbow-roulette signal). A
    custom-but-professional palette (few restrained hues, no neon) PASSES
    even when it isn't one of the shipped sets.
    """
    from research_os.tools.actions.viz.palettes import (
        all_allowed_chart_hexes,
        extract_hexes,
        is_near_neutral,
        is_neon,
        palette_hexes,
    )

    # Scan chrome (incl. <style>) + inline styles, but NOT <script> bodies.
    scannable = _SCRIPT_BODY_RE.sub("", dashboard_html)
    colors = set(extract_hexes(scannable))

    # Chart-relevant colours: drop greys / near-neutral hairlines + text.
    chart_colors = {c for c in colors if not is_near_neutral(c)}

    # Restraint baseline = the declared palette's own hexes (if known) ∪ the
    # professional anchor sets. A colour outside ALL of these is "off-palette".
    allowed = all_allowed_chart_hexes()
    if declared_palette:
        allowed |= palette_hexes(declared_palette)
    off_palette = sorted(c for c in chart_colors if c not in allowed)
    neon = sorted(c for c in chart_colors if is_neon(c))

    blockers: list[str] = []
    warnings: list[str] = []
    if neon:
        blockers.append(
            f"{len(neon)} neon / fluorescent colour(s) in the dashboard "
            f"({', '.join(neon[:4])}). Electric colour reads as amateur; use a "
            "restrained professional palette (one ground + one primary + ≤3 "
            "semantic accents). See tool_figure_palette for CVD-safe sets."
        )
    # Restraint: a handful of off-palette hues is fine (a custom brand), but a
    # rainbow of them signals per-section accent roulette / >5 hues.
    if len(off_palette) > 3:
        warnings.append(
            f"{len(off_palette)} chart colour(s) outside the declared / "
            "professional palettes — restraint reads as credibility. Keep to "
            "one ground + one primary + ≤2-3 semantic accents (≤5 hues), where "
            "colour carries consistent meaning. A custom palette is fine if it "
            "stays restrained, AA-contrast, and CVD-safe."
        )

    return {
        "blockers": blockers,
        "warnings": warnings,
        "out_of_palette_count": len(off_palette),
        "neon_count": len(neon),
        "neon_colors": neon,
    }


def _is_grey(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return False
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    return max(r, g, b) - min(r, g, b) <= 10


# ---------------------------------------------------------------------------
# 7. Reviewer simulator: would a 5-min skim get the finding?
# ---------------------------------------------------------------------------


def reviewer_simulator(dashboard_html: str) -> dict[str, Any]:
    """Walks the dashboard top-to-bottom; decides whether a 5-minute
    skimmer would extract the core finding."""
    body_text = re.sub(r"<[^>]+>", " ", dashboard_html)
    first_200 = " ".join(body_text.split()[:200]).lower()
    has_number_in_lede = bool(_NAKED_NUMBER.search(first_200))
    has_finding_verb_in_lede = any(
        v in first_200 for v in ("found", "showed", "demonstrate", "indicate", "support")
    )

    # Look at the first <section> after the header.
    first_section = None
    for sec in DASHBOARD_SECTIONS:
        m = re.search(
            rf'<section[^>]*\bid=["\']{sec}["\']', dashboard_html, re.I,
        )
        if m:
            first_section = sec
            break

    skimmer_gets_finding = has_number_in_lede and has_finding_verb_in_lede

    # Find a candidate "which section buries the lede?" - the first
    # section with > 100 words but no numbers in its first 50.
    burying = None
    for sec in DASHBOARD_SECTIONS:
        m = re.search(
            rf'<section[^>]*\bid=["\']{sec}["\'][^>]*>(.*?)</section>',
            dashboard_html, re.S | re.I,
        )
        if not m:
            continue
        sec_text = re.sub(r"<[^>]+>", " ", m.group(1))
        words = sec_text.split()
        if len(words) >= 100 and not _NAKED_NUMBER.search(" ".join(words[:50])):
            burying = sec
            break

    suggested = None
    if not skimmer_gets_finding:
        suggested = (
            "Lead with the headline number + finding verb in the first "
            "two sentences. A reviewer who skims the first 200 words "
            "should leave knowing your one-sentence takeaway."
        )
    return {
        "would_5min_skimmer_get_finding": skimmer_gets_finding,
        "which_section_buries_the_lede": burying,
        "suggested_top_of_page_callout": suggested,
        "first_section_rendered": first_section,
    }


# ===========================================================================
# 8. Design audit (3.2.8) — reviews the deliverable's STYLISTIC choices
# ===========================================================================
#
# These checks judge the dashboard the way a design reviewer would: is the
# scroll bounded, does the first viewport answer the question, is the page
# self-contained, do figures interpret rather than dump, is the structure
# claim-driven (not a per-step recap), does it leak the workspace? They run on
# the comment-stripped HTML so the bundled scaffold's `<!-- AI: ... -->`
# authoring markers never trip the audit on inert text.
#
# Severity doctrine: a design lint must NEVER wrongly refuse a good
# deliverable, so most checks WARN. BLOCK is reserved for the failures the
# spec names explicitly (endless scroll over the hard cap, neon, per-step
# recap ≥3, workspace/tool leaks in visible text, buried lede, orphan/
# uncaptioned figures, network deps).


# Known dashboard layout archetypes (stamped by the scaffold into
# <body data-archetype="...">). Used by the budget + nav + consistency checks.
_DASH_ARCHETYPES = frozenset({
    "single-viewport-brief", "scroll-lite-narrative",
    "comparison-scorecard", "multi-panel-exploratory",
})

# Finding verbs a hero / caption uses to ASSERT a result (vs. pose a question).
_FINDING_VERBS = (
    "found", "show", "showed", "shows", "lifted", "lift", "raised",
    "reduced", "cut", "improved", "increased", "decreased", "ruled out",
    "rule out", "indicate", "indicates", "indicated", "support", "supports",
    "demonstrate", "demonstrates", "demonstrated", "outperform",
    "outperformed", "beat", "achieved", "reached", "confirms", "confirmed",
    "drops", "dropped", "gained", "rose", "fell",
)

# Generic container / chronology headings — the opposite of a claim heading.
_GENERIC_HEADINGS = (
    "overview", "results", "conclusion", "conclusions", "introduction",
    "background", "discussion", "summary", "analysis",
)

# Per-step / folder-shaped headings (chronology, not claims).
_STEP_HEADING_RE = re.compile(r"^\s*step\s*\d+", re.I)
_FOLDER_HEADING_RE = re.compile(r"^\s*\d{2}[_-]\w+", re.I)

# Visible-text internal reference leaks (paths, tool names, sidecar files).
_LEAK_RE = re.compile(
    r"(?:workspace/|inputs/|synthesis/|\bstep_summary\b|\bconclusions\.md\b|"
    r"\b(?:tool|sys|mem)_[a-z0-9_]+)",
    re.I,
)

# External-resource (network dependency) patterns — any one breaks offline.
_NETWORK_RES = (
    re.compile(r'<script[^>]+src\s*=\s*["\']https?:', re.I),
    re.compile(r'<link[^>]+href\s*=\s*["\']https?:', re.I),
    re.compile(r'@import\s+url\(\s*["\']?https?:', re.I),
    re.compile(r'src\s*:\s*url\(\s*["\']?https?:', re.I),
    re.compile(r'<img[^>]+src\s*=\s*["\']https?:', re.I),
)

_HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.S | re.I)


def _visible_text(html: str) -> str:
    """Comment + script/style stripped, tags removed — the words a reader sees."""
    body = re.sub(r"<script\b[^>]*>.*?</script\b[^>]*>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<style\b[^>]*>.*?</style\b[^>]*>", " ", body, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", body)


def _archetype(html: str) -> str | None:
    m = re.search(r'<body[^>]*\bdata-archetype\s*=\s*["\']([^"\']+)["\']', html, re.I)
    return m.group(1).strip().lower() if m else None


def scroll_budget_estimate(dashboard_html: str) -> dict[str, Any]:
    """Estimate page height + flag endless scroll.

    Height ≈ (top-level <section> × ~0.8vh) + (standalone <figure>/<img> ×
    ~0.4vh). The section-count budget is the robust signal (a clean
    scroll-lite scaffold sits at 6 sections / ~5vh = the edge of budget, not
    over it); the vh estimate is the secondary guard against figure dumps.

    * single-viewport-brief: >3 sections OR an in-page nav → block (those
      are the real "this is not a one-screen brief" tells; the bundled brief
      skeleton is hero + figure + context = 2 sections, inside budget).
    * General: >8 sections OR >~6vh → block (endless scroll); >6 sections OR
      >~5vh → warn (approaching budget).
    """
    sections = re.findall(r"<section\b", dashboard_html, re.I)
    figures = re.findall(r"<figure\b", dashboard_html, re.I)
    imgs = re.findall(r"<img\b", dashboard_html, re.I)
    n_sections = len(sections)
    # Count standalone images (not the ones already inside a <figure>).
    n_standalone = max(0, len(imgs) - len(figures))
    n_loose_figs = len(figures) + n_standalone
    # Figures inside a bounded .panel-grid pack into one compact viewport, so
    # they don't each add a screen of scroll — count the grid as ~one figure.
    grid_figs = 0
    for gm in re.finditer(r'class\s*=\s*["\'][^"\']*panel-grid[^"\']*["\'][^>]*>(.*?)</(?:div|section)>',
                          dashboard_html, re.S | re.I):
        grid_figs += len(re.findall(r"<figure\b|<img\b", gm.group(1), re.I))
    effective_figs = max(0, n_loose_figs - grid_figs) + (1 if grid_figs else 0)
    est_vh = n_sections * 0.8 + effective_figs * 0.4
    has_nav = bool(re.search(r"<nav\b", dashboard_html, re.I))
    arch = _archetype(dashboard_html)

    blockers: list[str] = []
    warnings: list[str] = []
    if arch == "single-viewport-brief":
        if n_sections > 3 or has_nav:
            blockers.append(
                f"Declared single-viewport-brief but the page has "
                f"{n_sections} sections{' + a nav' if has_nav else ''} — that "
                "archetype is one tight screen (hero + a focal figure + a "
                "compact footer), no nav. Trim to one finding or switch to "
                "scroll-lite-narrative."
            )
    elif n_sections > 8 or est_vh > 6.5:
        blockers.append(
            f"Dashboard is ~{est_vh:.1f} viewports / {n_sections} sections — "
            "endless scroll. Cap at ≤8 claim sections / ≤~5 viewports; curate "
            "to the figures + sections that move the argument."
        )
    elif n_sections > 6 or est_vh > 5.5:
        warnings.append(
            f"Dashboard is ~{est_vh:.1f} viewports / {n_sections} sections — "
            "approaching the scroll budget. Confirm every section earns its "
            "place (claim-driven, not a dump)."
        )
    return {
        "blockers": blockers,
        "warnings": warnings,
        "est_viewports": round(est_vh, 1),
        "section_count": n_sections,
        "archetype": arch,
    }


def in_page_nav_required(dashboard_html: str) -> dict[str, Any]:
    """A long *narrative* page needs in-page jump nav. WARN (the scroll-lite
    scaffold ships the nav, so a missing nav is an authoring slip, not a hard
    failure).

    Exempt: single-viewport-brief (one screen), comparison-scorecard and
    multi-panel-exploratory (bounded, skim-at-a-glance archetypes — the spec
    requires nav only for the multi-section narrative). An undeclared page with
    ≥4 sections is treated as a narrative and asked for nav.
    """
    arch = _archetype(dashboard_html)
    warnings: list[str] = []
    n_sections = len(re.findall(r"<section\b", dashboard_html, re.I))
    _nav_exempt = {"single-viewport-brief", "comparison-scorecard",
                   "multi-panel-exploratory"}
    if arch in _nav_exempt or n_sections < 4:
        return {"warnings": warnings, "section_count": n_sections, "anchors": 0}
    # Same-page anchors: href="#id" OR a <nav> wrapping jump links.
    anchors = re.findall(r'href\s*=\s*["\']#[A-Za-z][\w-]*["\']', dashboard_html, re.I)
    has_nav = bool(re.search(r"<nav\b", dashboard_html, re.I))
    if len(anchors) < 3 and not has_nav:
        warnings.append(
            f"{n_sections}-section dashboard with no in-page navigation "
            "(need ≥3 href=\"#id\" jump-links or a <nav>). A reader should "
            "never have to scroll blind — add a slim jump bar."
        )
    return {
        "warnings": warnings,
        "section_count": n_sections,
        "anchors": len(anchors),
        "has_nav": has_nav,
    }


def per_step_recap_headings(dashboard_html: str) -> dict[str, Any]:
    """Block a chronology / per-step recap; warn on generic container headings.

    ≥3 'Step NN' / folder-shaped headings → block (the banned per-step recap);
    1-2 → warn. Generic containers (Overview/Results/Conclusion) → warn.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    step_like: list[str] = []
    generic: list[str] = []
    for _lvl, raw in _HEADING_RE.findall(dashboard_html):
        text = re.sub(r"<[^>]+>", "", raw).strip()
        low = text.lower()
        if _STEP_HEADING_RE.match(text) or _FOLDER_HEADING_RE.match(text):
            step_like.append(text)
        elif low in _GENERIC_HEADINGS:
            generic.append(text)
    if len(step_like) >= 3:
        blockers.append(
            f"{len(step_like)} chronology / per-step headings "
            f"(e.g. {step_like[0]!r}). Dashboards are organised by CLAIM / "
            "decision / comparison, NOT by workspace step. Re-title each "
            "section as the thing it learned (\"Reranking lifted hits@10 by "
            "5.9pp\")."
        )
    elif step_like:
        warnings.append(
            f"{len(step_like)} 'Step NN' / folder-shaped heading(s) "
            f"({step_like[0]!r}). Prefer claim-driven headings so the reader "
            "navigates by argument, not chronology."
        )
    if generic:
        warnings.append(
            f"{len(generic)} generic container heading(s) "
            f"({', '.join(sorted(set(generic))[:3])}). A heading should state a "
            "claim (\"Reranking lifted hits@10\"), not a container (\"Results\")."
        )
    return {
        "blockers": blockers,
        "warnings": warnings,
        "step_headings": step_like,
        "generic_headings": generic,
    }


def workspace_path_and_tool_leaks(dashboard_html: str) -> dict[str, Any]:
    """Any workspace path / sidecar file / tool name in VISIBLE body text →
    block. The external reader has no workspace; these leaks are bugs."""
    visible = _visible_text(dashboard_html)
    hits = sorted(set(m.group(0) for m in _LEAK_RE.finditer(visible)))
    blockers: list[str] = []
    if hits:
        blockers.append(
            f"{len(hits)} internal reference(s) leak into visible text "
            f"({', '.join(hits[:5])}). The reader has no workspace — strip "
            "paths (workspace/ inputs/ synthesis/), sidecar filenames "
            "(conclusions.md), and tool names (tool_*/sys_*/mem_*)."
        )
    return {"blockers": blockers, "warnings": [], "leaks": hits}


def hero_answers_in_first_viewport(dashboard_html: str) -> dict[str, Any]:
    """The first section must be a hero/headline/TL;DR AND deliver, in its
    first ~200 visible words, BOTH a number and a finding verb (the answer,
    not the question). Buried lede → block."""
    blockers: list[str] = []
    # Find the first <section> with content.
    m = re.search(
        r"<section\b([^>]*)>(.*?)</section>", dashboard_html, re.S | re.I,
    )
    if not m:
        return {"blockers": [], "warnings": [], "has_hero_section": False}
    attrs, body = m.group(1), m.group(2)
    sec_id = ""
    id_m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
    if id_m:
        sec_id = id_m.group(1).lower()
    cls_m = re.search(r'\bclass\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
    sec_cls = cls_m.group(1).lower() if cls_m else ""
    heading_m = re.search(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", body, re.S | re.I)
    heading = re.sub(r"<[^>]+>", "", heading_m.group(1)).lower() if heading_m else ""
    hero_tokens = ("hero", "headline", "tl;dr", "tldr", "key finding",
                   "top-line", "topline", "summary", "at a glance")
    is_hero = any(
        t.replace(" ", s) in sec_id or t.replace(" ", s) in sec_cls or t in heading
        for t in hero_tokens for s in ("-", "", " ")
    )
    first_words = " ".join(_visible_text(body).split()[:200]).lower()
    has_number = bool(_NAKED_NUMBER.search(first_words))
    has_verb = any(v in first_words for v in _FINDING_VERBS)
    if not (is_hero and has_number and has_verb):
        missing = []
        if not is_hero:
            missing.append("a hero/headline section first")
        if not has_number:
            missing.append("a number")
        if not has_verb:
            missing.append("a finding verb")
        blockers.append(
            "First viewport buries the lede (missing: " + ", ".join(missing) +
            "). Lead with the answer — a number + a finding verb (\"reranking "
            "lifted hits@10 by 5.9pp\"), never the research question."
        )
    return {
        "blockers": blockers,
        "warnings": [],
        "has_hero_section": is_hero,
        "number_in_lede": has_number,
        "finding_verb_in_lede": has_verb,
    }


def section_count_and_density_budget(dashboard_html: str) -> dict[str, Any]:
    """Figure-dump budget. Warn if total figures >8, any section holds >3
    figures, or a findings/results section has zero figures + tables."""
    warnings: list[str] = []
    n_figs = len(re.findall(r"<figure\b", dashboard_html, re.I)) or \
        len(re.findall(r"<img\b", dashboard_html, re.I))
    if n_figs > 8:
        warnings.append(
            f"{n_figs} figures embedded — a dashboard curates ≤5-8 load-bearing "
            "figures, not an exhaustive gallery. Drop the ones that don't move "
            "the argument."
        )
    crowded: list[str] = []
    for sm in re.finditer(r"<section\b([^>]*)>(.*?)</section>", dashboard_html, re.S | re.I):
        attrs, body = sm.group(1), sm.group(2)
        sid = ""
        idm = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if idm:
            sid = idm.group(1)
        figs_here = len(re.findall(r"<figure\b", body, re.I)) or \
            len(re.findall(r"<img\b", body, re.I))
        # A bounded .panel-grid is an intentional small-multiples grid (the
        # multi-panel-exploratory archetype), not a crowded section — exempt it.
        is_panel_grid = bool(re.search(r'class\s*=\s*["\'][^"\']*panel-grid', body, re.I))
        if figs_here > 3 and not is_panel_grid:
            crowded.append(sid or "(unnamed)")
        # A findings/results-flavoured section with no figure AND no table.
        if re.search(r"finding|result|comparison", sid, re.I):
            has_tbl = bool(re.search(r"<table\b", body, re.I))
            if figs_here == 0 and not has_tbl:
                warnings.append(
                    f"Section '{sid}' reads as a findings section but has no "
                    "figure or table — quantify the claim with evidence."
                )
    if crowded:
        warnings.append(
            f"{len(crowded)} section(s) hold >3 figures ({', '.join(crowded[:3])}) "
            "— one section, one claim, 1-2 figures. Split or curate."
        )
    return {"warnings": warnings, "n_figures": n_figs, "crowded_sections": crowded}


_LABEL_ONLY_CAPTION_RE = re.compile(
    r"^\s*(?:fig(?:ure)?|table|panel)\s*\d*\s*[—:.\-]?\s*[\w\s]{0,40}$", re.I,
)


def uncaptioned_or_label_only_figures(dashboard_html: str) -> dict[str, Any]:
    """Every <figure>/standalone <img> must have an interpretive caption.
    No figcaption + no nearby interpretive sentence → block. figcaption that
    is too short or pure-label-shaped (no finding verb) → warn."""
    blockers: list[str] = []
    warnings: list[str] = []
    fig_blocks = list(re.finditer(r"<figure\b[^>]*>(.*?)</figure>", dashboard_html, re.S | re.I))
    n_uncaptioned = 0
    n_label_only = 0
    for fm in fig_blocks:
        inner = fm.group(1)
        cap_m = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", inner, re.S | re.I)
        if not cap_m:
            # No figcaption — allow a nearby interpretive sentence (±1 para).
            start = max(0, fm.start() - 600)
            end = min(len(dashboard_html), fm.end() + 600)
            near = _visible_text(dashboard_html[start:end])
            if len(near.split()) < 8 or not any(v in near.lower() for v in _FINDING_VERBS):
                n_uncaptioned += 1
            continue
        cap_text = re.sub(r"<[^>]+>", "", cap_m.group(1)).strip()
        words = cap_text.split()
        if not words:
            # An empty <figcaption> is an unfilled template, not a label-only
            # caption — that's the placeholder check's job (and would false-
            # trip the bundled scaffold). Skip it here.
            continue
        has_finding = any(v in cap_text.lower() for v in _FINDING_VERBS)
        # A caption that interprets (has a finding verb) is fine even if short;
        # warn only on a pure-label shape OR a very short caption that doesn't
        # interpret.
        if not has_finding and (len(words) < 8 or _LABEL_ONLY_CAPTION_RE.match(cap_text)):
            n_label_only += 1
    if n_uncaptioned:
        blockers.append(
            f"{n_uncaptioned} figure(s) have no caption and no nearby "
            "interpretation. Every figure needs a caption saying what to SEE "
            "and what it MEANS (finding-led)."
        )
    if n_label_only:
        warnings.append(
            f"{n_label_only} figure caption(s) are label-only / too short "
            "(\"Figure 3: accuracy\"). Lead with the finding the figure shows, "
            "not the chart mechanics."
        )
    return {
        "blockers": blockers,
        "warnings": warnings,
        "uncaptioned": n_uncaptioned,
        "label_only": n_label_only,
    }


def color_not_sole_channel(dashboard_html: str) -> dict[str, Any]:
    """Where up/down/positive/negative delta classes are used, colour must not
    be the only cue — require a redundant sign / arrow / word in the element.
    Colour-only deltas → warn (CVD)."""
    warnings: list[str] = []
    naked = 0
    for m in re.finditer(
        r'<[^>]*class\s*=\s*["\'][^"\']*\b(?:up|down|positive|negative)\b[^"\']*["\'][^>]*>(.*?)</\w+>',
        dashboard_html, re.S | re.I,
    ):
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        if not re.search(r"[+\-▲▼↑↓]|\b(up|down|better|worse|gain|loss|increase|decrease)\b", inner, re.I):
            naked += 1
    if naked:
        warnings.append(
            f"{naked} delta(s) encode direction with COLOUR only (a "
            "positive/negative class but no sign/arrow/word). Colour-blind "
            "readers can't see it — add a +/- sign, ▲/▼, or a word."
        )
    return {"warnings": warnings, "color_only_deltas": naked}


def self_contained_offline(dashboard_html: str) -> dict[str, Any]:
    """Any network dependency (external script/link/@import/font/img) → block.
    The deliverable must be a single portable file that prints + works offline."""
    blockers: list[str] = []
    hits: list[str] = []
    # Scan with comments stripped (a commented-out CDN link is inert).
    scan = _strip_html_comments(dashboard_html)
    for pat in _NETWORK_RES:
        if pat.search(scan):
            hits.append(pat.pattern)
    if hits:
        blockers.append(
            f"{len(hits)} network dependency pattern(s) — the dashboard loads "
            "external resources (script / stylesheet / @import / font / image "
            "over http). Inline or bundle everything; it must work offline and "
            "print clean."
        )
    return {"blockers": blockers, "warnings": [], "network_patterns": len(hits)}


def archetype_declared_and_consistent(dashboard_html: str) -> dict[str, Any]:
    """Require <body data-archetype="..."> and assert the measured shape
    roughly matches the declaration. Missing / unknown / mismatched → warn
    (a design-template smell, never a hard block)."""
    warnings: list[str] = []
    arch = _archetype(dashboard_html)
    if arch is None:
        warnings.append(
            "No <body data-archetype=\"...\"> stamp. Declare the layout "
            "archetype (single-viewport-brief / scroll-lite-narrative / "
            "comparison-scorecard / multi-panel-exploratory) so the design "
            "intent is explicit and verifiable."
        )
        return {"warnings": warnings, "archetype": None, "consistent": False}
    if arch not in _DASH_ARCHETYPES:
        warnings.append(
            f"data-archetype=\"{arch}\" is not a known archetype. Use one of: "
            f"{', '.join(sorted(_DASH_ARCHETYPES))}."
        )
        return {"warnings": warnings, "archetype": arch, "consistent": False}
    n_sections = len(re.findall(r"<section\b", dashboard_html, re.I))
    has_nav = bool(re.search(r"<nav\b", dashboard_html, re.I))
    has_cmp = bool(
        re.search(r'class\s*=\s*["\'][^"\']*scorecard', dashboard_html, re.I)
        or re.search(r"<table\b", dashboard_html, re.I)
    )
    has_grid = bool(re.search(r'class\s*=\s*["\'][^"\']*panel-grid', dashboard_html, re.I))
    consistent = True
    if arch == "single-viewport-brief" and (n_sections > 3 or has_nav):
        consistent = False
        warnings.append(
            "Declared single-viewport-brief but the page has many sections / a "
            "nav — that archetype is one tight viewport, no nav."
        )
    elif arch == "comparison-scorecard" and not has_cmp:
        consistent = False
        warnings.append(
            "Declared comparison-scorecard but no comparison table / small-"
            "multiples grid is present — the scorecard IS the page."
        )
    elif arch == "multi-panel-exploratory" and not has_grid:
        consistent = False
        warnings.append(
            "Declared multi-panel-exploratory but no .panel-grid is present — "
            "this archetype is a bounded grid on a shared scale."
        )
    return {"warnings": warnings, "archetype": arch, "consistent": consistent}


# ---------------------------------------------------------------------------
# Wrapper: audit_dashboard_content
# ---------------------------------------------------------------------------


def audit_dashboard_content(
    root: Path,
    dashboard_path: str = "synthesis/dashboard.html",
) -> dict[str, Any]:
    """Run all 7 sub-checks. Combined report shape:
        {status, blockers, warnings, sub_reports: {numeric, proximity, ...}}
    """
    dpath = root / dashboard_path
    if not dpath.exists():
        return {
            "status": "error",
            "message": f"{dashboard_path} not found. Run tool_dashboard_create first.",
            "blockers": [],
            "warnings": [],
        }
    html = dpath.read_text(encoding="utf-8", errors="replace")
    # Drop commented-out markup before the alt-text / <section> /
    # placeholder scans so the bundled scaffold doesn't trip its own
    # audit on inert HTML inside `<!-- ... -->`.
    html = _strip_html_comments(html)

    numeric = audit_numeric_grounding(html, root)
    proximity = audit_figure_proximity(html)
    substantive = audit_section_substantiveness(html)
    a11y = audit_accessibility(html)
    print_ok = audit_print_friendly(html)
    palette = audit_color_palette(html)
    reviewer = reviewer_simulator(html)

    # 3.2.8 design audit — stylistic-choice review.
    scroll = scroll_budget_estimate(html)
    nav = in_page_nav_required(html)
    recap = per_step_recap_headings(html)
    leaks = workspace_path_and_tool_leaks(html)
    hero = hero_answers_in_first_viewport(html)
    density = section_count_and_density_budget(html)
    figcaps = uncaptioned_or_label_only_figures(html)
    cvd = color_not_sole_channel(html)
    offline = self_contained_offline(html)
    archetype = archetype_declared_and_consistent(html)

    blockers: list[str] = []
    blockers.extend(numeric["blockers"])
    blockers.extend(substantive["blockers"])
    for d in (palette, scroll, recap, leaks, hero, figcaps, offline):
        blockers.extend(d.get("blockers", []))

    warnings: list[str] = []
    warnings.extend(proximity["warnings"])
    warnings.extend(substantive["warnings"])
    warnings.extend(print_ok["warnings"])
    warnings.extend(palette["warnings"])
    for d in (scroll, nav, recap, density, figcaps, cvd, archetype):
        warnings.extend(d.get("warnings", []))
    if not reviewer["would_5min_skimmer_get_finding"]:
        warnings.append(
            "Reviewer simulator: a 5-minute skimmer would miss the finding "
            "(no number + finding verb in the first 200 words)."
        )

    # contrast_and_alt_baseline: reuse audit_accessibility, but PROMOTE
    # missing-alt + low-contrast to BLOCK for a share-grade deliverable
    # (heading-skip / single-h1 stay warnings). The accessibility report
    # phrases these as warnings; re-classify here so a sharable dashboard
    # can't ship inaccessible.
    for w in a11y["warnings"]:
        lw = w.lower()
        if "missing alt" in lw or ("contrast" in lw and "below" in lw):
            blockers.append(w)
        else:
            warnings.append(w)

    status = "error" if blockers else "success"
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "sub_reports": {
            "numeric_grounding": numeric,
            "figure_proximity": proximity,
            "section_substantiveness": substantive,
            "accessibility": a11y,
            "print_friendly": print_ok,
            "color_palette": palette,
            "reviewer_simulator": reviewer,
            # 3.2.8 design audit
            "scroll_budget": scroll,
            "in_page_nav": nav,
            "per_step_recap": recap,
            "workspace_leaks": leaks,
            "hero_first_viewport": hero,
            "density_budget": density,
            "figure_captions": figcaps,
            "color_not_sole_channel": cvd,
            "self_contained_offline": offline,
            "archetype_consistency": archetype,
        },
    }
