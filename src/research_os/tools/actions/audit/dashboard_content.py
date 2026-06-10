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
DASHBOARD_SECTIONS = (
    "abstract", "overview", "findings", "per_step", "audit",
    "glossary", "references",
)


# Per-section substantiveness bars.
SECTION_BARS = {
    "abstract":   {"min_words": 150, "min_findings": 1, "min_methods": 1, "min_figs": 0},
    "overview":   {"min_words": 200, "min_hypotheses": 1, "min_figs": 0},
    "findings":   {"min_words": 300, "min_claims": 3, "min_figs": 1},
    "per_step":   {"min_words": 100},
    "audit":      {"min_words": 100},
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
            # Also pull from conclusions.md + step_summary.yaml.
            for fname in ("conclusions.md", "step_summary.yaml"):
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

    # Images missing alt.
    img_no_alt = re.findall(r"<img\b(?![^>]*\balt=)[^>]*>", dashboard_html, re.I)
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
# 6. Color palette consistency (heuristic)
# ---------------------------------------------------------------------------


# Known "good" palettes (representative anchor colors).
OKABE_ITO = {"#000000", "#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00", "#cc79a7"}
VIRIDIS_KEYS = {"#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"}
PUOR_KEYS = {"#b35806", "#e08214", "#fdb863", "#fee0b6", "#d8daeb", "#b2abd2", "#8073ac", "#542788"}
# Research-OS dashboard accent palette (matches viz/style.py RO_PALETTE).
# The five accent colours are perceptually distinct under deuteranopia /
# protanopia simulation, and the warm dark grey + cream rule colours
# match the page chrome so dashboards generated from the bundled
# scaffold + figures generated through apply_research_os_style() share
# one allowed-palette set.
RESEARCH_OS_ACCENT = {
    "#1f4d7a",  # navy — primary
    "#9b7e2d",  # olive gold — secondary
    "#3f6049",  # forest — positive deltas
    "#9b3737",  # oxblood — emphasis / negative deltas
    "#c3a14e",  # mustard — fifth accent
    "#3d3a35",  # warm dark grey foreground
    "#7c7468",  # muted secondary text
    "#d6cfc2",  # hairline rule on cream
    "#fbf8f3",  # cream background
    "#fffdf8",  # near-white card on cream
}


def audit_color_palette(dashboard_html: str) -> dict[str, Any]:
    """Pull every `#rrggbb` from the page; check whether it belongs to
    an allowed palette."""
    colors = set(m.group(0).lower() for m in re.finditer(r"#[0-9a-f]{6}\b", dashboard_html, re.I))
    # We only care about chart-area colors, not chrome (text, borders);
    # heuristic: ignore pure black/white/grey.
    chart_colors = {
        c for c in colors
        if c not in {"#000000", "#ffffff"} and not _is_grey(c)
    }
    allowed = OKABE_ITO | VIRIDIS_KEYS | PUOR_KEYS | RESEARCH_OS_ACCENT
    out_of_palette = [c for c in chart_colors if c not in allowed]
    warnings: list[str] = []
    if len(out_of_palette) > 5:
        warnings.append(
            f"{len(out_of_palette)} chart color(s) not in the Okabe-Ito / "
            f"viridis / PuOr palettes — palette may be inconsistent across figures."
        )
    return {"warnings": warnings, "out_of_palette_count": len(out_of_palette)}


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

    numeric = audit_numeric_grounding(html, root)
    proximity = audit_figure_proximity(html)
    substantive = audit_section_substantiveness(html)
    a11y = audit_accessibility(html)
    print_ok = audit_print_friendly(html)
    palette = audit_color_palette(html)
    reviewer = reviewer_simulator(html)

    blockers: list[str] = []
    blockers.extend(numeric["blockers"])
    blockers.extend(substantive["blockers"])

    warnings: list[str] = []
    warnings.extend(proximity["warnings"])
    warnings.extend(substantive["warnings"])
    warnings.extend(a11y["warnings"])
    warnings.extend(print_ok["warnings"])
    warnings.extend(palette["warnings"])
    if not reviewer["would_5min_skimmer_get_finding"]:
        warnings.append(
            "Reviewer simulator: a 5-minute skimmer would miss the finding "
            "(no number + finding verb in the first 200 words)."
        )

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
        },
    }
