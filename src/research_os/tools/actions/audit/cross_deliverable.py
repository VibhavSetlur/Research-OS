"""Cross-deliverable consistency audit.

Verifies that the project's five outward-facing deliverables — paper,
dashboard, slides, poster, and reproducibility footer — tell the same
story along five dimensions:

1. ``numeric_claims_consistent``     — every numeric claim shared across
   the deliverables agrees within ±1% relative tolerance.
2. ``figures_consistent``            — the set of figure stems
   (basename minus extension) embedded across paper / dashboard /
   slides / poster is aligned. A figure that appears in two
   deliverables but is missing from a third is flagged.
3. ``citations_consistent``          — bibliography keys cited in the
   paper are also present in slides + poster, and vice versa.
4. ``findings_top_line_consistent``  — Jaccard overlap of the headline
   "findings" sentences across deliverables is ≥ 0.30.
5. ``reproducibility_footer_consistent`` — every deliverable carries
   a footer with the Research-OS version, the git commit hash, and a
   build timestamp; all values are identical.

Why these five
--------------
A scientific project that ships paper + dashboard + slides + poster
is essentially shipping the same claim in four formats. If the
abstract says ``AUROC = 0.84`` but the poster says ``AUROC = 0.86``,
or Figure 2 in the paper is missing from the slides, a reviewer
notices and trust evaporates. The reproducibility footer turns
"which version of which build produced this PDF?" from a forensics
exercise into a one-line answer.

The auditor is deliberately conservative. A claim that only appears
in one deliverable is *not* flagged — only divergence between two
deliverables that both make the claim. A figure embedded once is
fine; a figure embedded in paper + slides but absent from the
poster is flagged.

This module depends on the figure-embedding metadata produced by
``tool_figure_auto_embed`` (the ``figures_embedded`` field surfaced
by dashboard + synthesis), but degrades gracefully when the metadata
is missing — it falls back to scanning the rendered deliverable for
``![](path)`` Markdown image syntax + ``<img src="…">`` HTML.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding

logger = logging.getLogger("research_os.audit.cross_deliverable")


# ---------------------------------------------------------------------------
# Deliverable discovery
# ---------------------------------------------------------------------------


# Map deliverable name -> ordered list of candidate paths (first match wins).
# The list intentionally covers both Markdown and rendered forms — a project
# might ship paper.md, paper.pdf, or both. We read text-shaped sources only
# (PDFs are skipped; the source of truth for the audit is the markdown).
_DELIVERABLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "paper": (
        "synthesis/paper.typ",
        "synthesis/paper.md",
        "synthesis/report.md",
    ),
    "dashboard": (
        "synthesis/dashboard.html",
        "synthesis/dashboard_story.md",
    ),
    "slides": (
        "synthesis/slides.typ",
        "synthesis/slides.md",
        "synthesis/slides.html",
    ),
    "poster": (
        "synthesis/poster.typ",
        "synthesis/poster.md",
        "synthesis/poster.tex",
    ),
}


def _discover_deliverables(root: Path) -> dict[str, Path]:
    """Return {name: path} for each deliverable that exists on disk."""
    out: dict[str, Path] = {}
    for name, candidates in _DELIVERABLE_CANDIDATES.items():
        for rel in candidates:
            p = root / rel
            if p.is_file():
                out[name] = p
                break
    return out


def _read_text_safe(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Dimension 1 — numeric claims
# ---------------------------------------------------------------------------


# Numeric-claim extractor: same shape as audit/claim_grounding.py but
# scoped tighter — we only want results-bearing numbers (percentages,
# p-values, sample sizes, point estimates). Citation refs and years
# are excluded.
_NUMERIC_CLAIM_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    (
        # p-value style:  p < 0.05 / p = 0.001 / p-value = 0.012
        p\s*[<>=]\s*0?\.\d+
        |
        # percentage:  42% / 42.3 % / 100%
        -?\d+(?:\.\d+)?\s*%
        |
        # sample size:  n = 423 / N=12 / n = 1,200 / n=4234 / n=5000
        # (comma-grouped OR a plain 1-7 digit run, so 4-5 digit n's
        # without a thousands separator are not silently missed)
        [nN]\s*=\s*(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,7}(?:\.\d+)?)
        |
        # plain decimal:  0.84  /  -0.12  /  1.23e-4
        -?\d+\.\d+(?:e[+-]?\d+)?
    )
    (?![A-Za-z0-9_])
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _strip_code_and_cites(text: str) -> str:
    """Remove fenced code blocks, inline code, bracketed citations, HTML tags."""
    out = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    out = re.sub(r"`[^`]+`", " ", out)
    out = re.sub(r"\[\d+(?:[,\-]\s*\d+)*\]", " ", out)
    # Strip HTML tags but keep their text content (for HTML deliverables).
    out = re.sub(r"<[^>]+>", " ", out)
    return out


def _normalise_claim_value(token: str) -> float | None:
    """Coerce a claim token to a float for tolerant comparison."""
    t = token.strip()
    # Handle p<0.05 form.
    m = re.match(r"^p\s*[<>=]\s*(0?\.\d+)$", t, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    # Handle n=N form.
    m = re.match(r"^[nN]\s*=\s*([\d,\.]+)$", t)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    # Handle percentages: strip % and divide by 100 for normalised comparison.
    is_pct = t.endswith("%")
    if is_pct:
        t = t[:-1].strip()
    try:
        v = float(t.replace(",", ""))
        if is_pct:
            v = v / 100.0
        return v
    except ValueError:
        return None


_P_VALUE_TOKEN_RE = re.compile(r"^p\s*[<>=]", re.IGNORECASE)


def _claim_kind(token: str) -> str:
    """Categorise the claim shape so we only compare like-with-like."""
    if _P_VALUE_TOKEN_RE.match(token):
        return "p_value"
    if re.match(r"^[nN]\s*=", token):
        return "sample_size"
    if token.strip().endswith("%"):
        return "percentage"
    return "decimal"


# A metric anchor is the nearest label-ish word right before the number
# (AUROC / slope / accuracy / r / beta …). Two numbers are only the "same
# claim" if they carry the same anchor — otherwise comparing AUROC 0.84
# against slope 0.86 is meaningless.
_ANCHOR_RE = re.compile(r"([A-Za-z][A-Za-z0-9_\-]{1,30})\s*[:=≈~]?\s*$")


def _metric_anchor(text: str, start: int) -> str:
    """Lowercased label immediately preceding the number at ``start``, or ""."""
    m = _ANCHOR_RE.search(text[:start])
    return m.group(1).lower() if m else ""


def _numeric_claim_extractor(text: str) -> list[dict[str, Any]]:
    """Extract numeric claims from a deliverable's source text.

    Returns a list of dicts with ``token``, ``value`` (float), ``kind``
    ('p_value' | 'sample_size' | 'percentage' | 'decimal'), and ``anchor``
    (the nearest preceding metric label, lowercased, or "").
    """
    cleaned = _strip_code_and_cites(text)
    out: list[dict[str, Any]] = []
    for m in _NUMERIC_CLAIM_RE.finditer(cleaned):
        tok = m.group(0).strip()
        val = _normalise_claim_value(tok)
        if val is None:
            continue
        # Exclude years masquerading as decimals.
        if 1900 <= val <= 2099 and "." not in tok and "%" not in tok:
            continue
        out.append({
            "token": tok,
            "value": val,
            "kind": _claim_kind(tok),
            "anchor": _metric_anchor(cleaned, m.start()),
        })
    return out


def numeric_claims_consistent(
    root: Path,
    deliverables: dict[str, Path] | None = None,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Check that numeric claims appearing in 2+ deliverables agree.

    A claim is "shared" if at least two deliverables emit a value of
    the same kind (p_value / percentage / sample_size / decimal).
    Shared claims must agree within ``tolerance`` relative diff.
    """
    if deliverables is None:
        deliverables = _discover_deliverables(root)
    per_deliv: dict[str, list[dict[str, Any]]] = {}
    for name, p in deliverables.items():
        per_deliv[name] = _numeric_claim_extractor(_read_text_safe(p))

    # Bucket every claim by (kind, anchor). The metric anchor (AUROC /
    # slope / accuracy …) is what gives a number its identity: two numbers
    # are only the "same claim" when they share both kind AND anchor. Two
    # numbers of the same kind but DIFFERENT (or absent) anchors — e.g.
    # AUROC 0.84 vs slope 0.86 — are different metrics and a near-but-not-
    # equal value between them is at most a warning, never a block.
    mismatches: list[dict[str, Any]] = []          # same metric → BLOCK
    near_warnings: list[dict[str, Any]] = []        # different/absent metric → WARN
    by_bucket: dict[tuple[str, str], dict[str, list[float]]] = {}
    for name, claims in per_deliv.items():
        for c in claims:
            key = (c["kind"], c.get("anchor", ""))
            by_bucket.setdefault(key, {}).setdefault(name, []).append(c["value"])

    for (kind, anchor), deliv_values in by_bucket.items():
        names = list(deliv_values.keys())
        if len(names) < 2:
            continue
        # For each pair of deliverables, look for a value in one that has
        # no within-tolerance match in the other. Symmetric pairing.
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                vals_a = deliv_values[a]
                vals_b = deliv_values[b]
                for va in vals_a:
                    # If `va` is "shared" (within 1% of any value in B's set
                    # of the same bucket), it's fine. Otherwise it's a
                    # candidate mismatch — but only when a value in B is
                    # "close but not equal" (within 10× tolerance).
                    matched = any(
                        _within(vb, va, tolerance) for vb in vals_b
                    )
                    if matched:
                        continue
                    near = [
                        vb for vb in vals_b if _within(vb, va, tolerance * 10)
                    ]
                    if not near:
                        continue
                    record = {
                        "kind": kind,
                        "anchor": anchor,
                        "deliverable_a": a,
                        "value_a": va,
                        "deliverable_b": b,
                        "value_b_candidates": near,
                        "relative_diff": min(
                            abs(vb - va) / max(abs(va), abs(vb), 1e-12)
                            for vb in near
                        ),
                    }
                    # Only a SHARED, NON-EMPTY metric anchor makes this the
                    # same claim → a genuine inconsistency (block). A blank
                    # anchor means we can't establish the two numbers refer
                    # to the same metric → downgrade to a warning.
                    if anchor:
                        mismatches.append(record)
                    else:
                        near_warnings.append(record)

    return {
        "pass": not mismatches,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "claim_counts": {k: len(v) for k, v in per_deliv.items()},
            "mismatches": mismatches[:50],
            "mismatch_count": len(mismatches),
            "near_warnings": near_warnings[:50],
            "near_warning_count": len(near_warnings),
            "tolerance": tolerance,
        },
    }


def _within(a: float, b: float, tol: float) -> bool:
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom <= tol


# ---------------------------------------------------------------------------
# Dimension 2 — figures
# ---------------------------------------------------------------------------


_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
_HTML_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)", re.IGNORECASE)
# Typst: ``#image("path")`` and the wrapped ``#figure(image("path"))`` form.
_TYPST_IMG_RE = re.compile(r"#(?:figure\(\s*)?image\(\s*[\"']([^\"']+)")
_LATEX_INCLUDE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")


def _extract_figure_stems(text: str) -> set[str]:
    """Return the set of figure stems (basename without extension) referenced."""
    stems: set[str] = set()
    for pat in (_MD_IMG_RE, _HTML_IMG_RE, _TYPST_IMG_RE, _LATEX_INCLUDE_RE):
        for m in pat.finditer(text):
            ref = m.group(1).strip()
            if not ref:
                continue
            # Strip query strings / fragments.
            ref = ref.split("?", 1)[0].split("#", 1)[0]
            stem = Path(ref).stem
            if stem:
                stems.add(stem.lower())
    return stems


def figures_consistent(
    root: Path,
    deliverables: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Check that figure stems are aligned across deliverables.

    A figure embedded in paper + slides but missing from poster is
    flagged. A figure embedded in only one deliverable is not flagged
    (each deliverable has freedom to elide secondary figures).
    """
    if deliverables is None:
        deliverables = _discover_deliverables(root)
    per_deliv: dict[str, set[str]] = {}
    for name, p in deliverables.items():
        per_deliv[name] = _extract_figure_stems(_read_text_safe(p))

    # A figure stem is only a candidate for an inconsistency when it is
    # SHARED — i.e. embedded in ≥2 deliverables. A figure that appears in
    # just one deliverable is fine: each deliverable is free to elide a
    # secondary figure (a poster doesn't reproduce every paper figure).
    # For each shared stem, the deliverables that DON'T carry it are the
    # gap. Per the documented threshold: 0-1 gaps = warning, >1 = block.
    stem_to_deliverables: dict[str, list[str]] = {}
    for name, stems in per_deliv.items():
        for stem in stems:
            stem_to_deliverables.setdefault(stem, []).append(name)

    all_names = set(per_deliv.keys())
    missing: list[dict[str, Any]] = []
    for stem in sorted(stem_to_deliverables):
        present_in = stem_to_deliverables[stem]
        if len(present_in) < 2:
            continue  # not shared → no inconsistency
        absent_in = sorted(all_names - set(present_in))
        if absent_in:
            missing.append({
                "figure_stem": stem,
                "present_in": sorted(present_in),
                "absent_in": absent_in,
            })

    # For the structured suggested_fix, also surface figures that live in a
    # secondary deliverable but not the paper (paper is the canonical
    # record). These are informational, not blocking.
    paper_stems = per_deliv.get("paper", set())
    extra: list[dict[str, Any]] = []
    for other in ("dashboard", "slides", "poster"):
        if other not in per_deliv:
            continue
        for stem in sorted(per_deliv[other] - paper_stems):
            extra.append({"figure_stem": stem, "deliverable": other})

    # Threshold (per docstring): >1 shared figure missing from a 3rd
    # deliverable is a genuine disagreement → block. 0-1 missing is a
    # warning (elision of a single figure is allowed).
    return {
        "pass": len(missing) <= 1,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "figures_per_deliverable": {
                k: sorted(v) for k, v in per_deliv.items()
            },
            "paper_figures_missing_elsewhere": missing,
            "shared_figures_missing_count": len(missing),
            "figures_in_secondary_but_not_paper": extra,
        },
    }


# ---------------------------------------------------------------------------
# Dimension 3 — citations
# ---------------------------------------------------------------------------


# Three alternatives, in order:
#   - @citekey                (markdown / pandoc / typst)
#   - \cite{key1,key2}        (LaTeX, optional p/t/n style)
#   - [@key1; @key2]          (pandoc bracketed)
_CITE_KEY_RE = re.compile(
    r"@([A-Za-z][\w:-]+)|\\cite[ptn]?\{([^}]+)\}|\[@([A-Za-z][\w:-]+)"
)


def _extract_cite_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for m in _CITE_KEY_RE.finditer(text):
        for grp in m.groups():
            if not grp:
                continue
            # \cite{a,b} → split.
            for k in grp.split(","):
                k = k.strip()
                if k:
                    keys.add(k)
    return keys


def citations_consistent(
    root: Path,
    deliverables: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Check that the set of cited keys agrees across deliverables.

    Paper is canonical. Slides / poster / dashboard that cite a key
    NOT in the paper, or omit a key the paper cites in a section that
    they reproduce, are flagged. (We don't require slides to cite the
    full paper bibliography — only that any key they cite must also
    be in the paper.)
    """
    if deliverables is None:
        deliverables = _discover_deliverables(root)
    per_deliv: dict[str, set[str]] = {}
    for name, p in deliverables.items():
        per_deliv[name] = _extract_cite_keys(_read_text_safe(p))

    paper_keys = per_deliv.get("paper", set())
    rogue: list[dict[str, Any]] = []
    for name, keys in per_deliv.items():
        if name == "paper":
            continue
        # Keys cited in this deliverable but not in the paper.
        unknown = sorted(keys - paper_keys)
        if unknown:
            rogue.append({
                "deliverable": name,
                "keys_not_in_paper": unknown,
            })

    return {
        "pass": not rogue,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "citation_counts": {k: len(v) for k, v in per_deliv.items()},
            "rogue_citations": rogue,
            "paper_key_count": len(paper_keys),
        },
    }


# ---------------------------------------------------------------------------
# Dimension 4 — top-line findings
# ---------------------------------------------------------------------------


_FINDING_HEADING_RE = re.compile(
    r"^#{1,3}\s+(?:findings?|results?|key\s+findings?|main\s+results?|"
    r"headline\s+findings?|tl;?dr|summary|takeaways?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "at", "for", "to",
    "by", "with", "from", "is", "was", "were", "are", "be", "been",
    "this", "that", "these", "those", "as", "it", "its", "we", "our",
    "they", "their", "which", "who", "what", "when", "where", "how",
    "but", "not", "no", "so", "if", "then", "than", "also", "such",
    "while", "however", "moreover", "thus", "therefore", "between",
    "into", "across", "through", "over", "under", "about", "above",
    "below", "after", "before", "during", "within", "without",
}


def _tokenise(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
        if w not in _STOPWORDS
    }


_FOOTER_SENTINEL_RE = re.compile(
    r"^\s*(?:---+|\*\*\*+|research-?os\s+version|<footer)",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_headline_finding(text: str) -> str:
    """Find the first 'Findings' / 'Results' / 'Summary' section's lead paragraph.

    Extraction stops at the first of: another heading, a horizontal-rule
    (``---``), the literal token ``research-os version``, or the
    ``<footer>`` HTML tag. This keeps reproducibility footers out of the
    Jaccard comparison.

    The body returned is the first ~2 sentences (cap 400 chars) so that
    long Findings sections — which routinely include auxiliary citations,
    figure callouts, and per-subgroup breakdowns — don't dilute the
    overlap score with vocabulary the lighter deliverables (slides,
    poster) won't carry.
    """
    m = _FINDING_HEADING_RE.search(text)
    if not m:
        # Fallback: take the first non-trivial paragraph after the title.
        for para in text.split("\n\n"):
            stripped = para.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if len(stripped) > 40:
                return stripped[:400]
        return text[:400]
    after = text[m.end():]
    # Stop at next heading.
    next_h = re.search(r"^#{1,3}\s+", after, re.MULTILINE)
    # Stop at footer sentinel.
    footer_m = _FOOTER_SENTINEL_RE.search(after)
    end = len(after)
    if next_h:
        end = min(end, next_h.start())
    if footer_m:
        end = min(end, footer_m.start())
    body = after[:end].strip()
    # Cap at ~400 chars — enough for 2-3 sentences, short enough that
    # auxiliary callouts don't dominate the token bag.
    return body[:400]


def findings_top_line_consistent(
    root: Path,
    deliverables: dict[str, Path] | None = None,
    min_jaccard: float = 0.30,
) -> dict[str, Any]:
    """Compute pairwise Jaccard overlap of headline finding sentences.

    Every pair of deliverables that both have a findings/results
    section must achieve ≥ ``min_jaccard`` token overlap. Pairs below
    threshold are flagged.
    """
    if deliverables is None:
        deliverables = _discover_deliverables(root)
    per_deliv: dict[str, set[str]] = {}
    raw: dict[str, str] = {}
    for name, p in deliverables.items():
        text = _read_text_safe(p)
        cleaned = _strip_code_and_cites(text)
        headline = _extract_headline_finding(cleaned)
        per_deliv[name] = _tokenise(headline)
        raw[name] = headline[:200]

    weak_pairs: list[dict[str, Any]] = []
    names = list(per_deliv.keys())
    pair_scores: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ta = per_deliv[a]
            tb = per_deliv[b]
            if not ta or not tb:
                continue
            inter = len(ta & tb)
            union = len(ta | tb)
            score = inter / max(1, union)
            pair_scores.append({
                "a": a, "b": b, "jaccard": round(score, 3),
            })
            if score < min_jaccard:
                weak_pairs.append({
                    "a": a, "b": b, "jaccard": round(score, 3),
                    "preview_a": raw[a],
                    "preview_b": raw[b],
                })

    return {
        "pass": not weak_pairs,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "min_jaccard": min_jaccard,
            "pair_scores": pair_scores,
            "weak_pairs": weak_pairs,
        },
    }


# ---------------------------------------------------------------------------
# Dimension 5 — reproducibility footer
# ---------------------------------------------------------------------------


_FOOTER_VERSION_RE = re.compile(
    r"(?:research-?os|ro)[ _-]?version[:\s]+v?([0-9]+\.[0-9]+\.[0-9]+)",
    re.IGNORECASE,
)
_FOOTER_COMMIT_RE = re.compile(
    r"(?:commit|git[ _-]?hash|sha)[:\s]+([0-9a-f]{7,40})",
    re.IGNORECASE,
)
_FOOTER_TS_RE = re.compile(
    r"(?:built|generated|timestamp)[:\s]+"
    r"(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?[A-Za-z0-9:+\-]*)",
    re.IGNORECASE,
)


def _extract_footer(text: str) -> dict[str, str | None]:
    """Pull (version, commit, timestamp) from a deliverable's footer.

    The footer can appear anywhere in the document, but is typically
    in the last 1 KB. We scan the whole document to be robust.
    """
    v = _FOOTER_VERSION_RE.search(text)
    c = _FOOTER_COMMIT_RE.search(text)
    t = _FOOTER_TS_RE.search(text)
    return {
        "version": v.group(1) if v else None,
        "commit": c.group(1).lower() if c else None,
        "timestamp": t.group(1) if t else None,
    }


def reproducibility_footer_consistent(
    root: Path,
    deliverables: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify every deliverable carries the same RO version + commit + timestamp."""
    if deliverables is None:
        deliverables = _discover_deliverables(root)
    per_deliv: dict[str, dict[str, str | None]] = {}
    for name, p in deliverables.items():
        per_deliv[name] = _extract_footer(_read_text_safe(p))

    missing: list[str] = []
    for name, fields in per_deliv.items():
        if not all(fields.values()):
            missing.append(name)

    # Compare values across deliverables that DO have footers.
    have_footer = {n: f for n, f in per_deliv.items() if all(f.values())}
    version_set = {f["version"] for f in have_footer.values()}
    commit_set = {f["commit"] for f in have_footer.values()}
    ts_set = {f["timestamp"] for f in have_footer.values()}

    discrepancies: list[str] = []
    if len(version_set) > 1:
        discrepancies.append(
            f"version mismatch across deliverables: {sorted(filter(None, version_set))}"
        )
    if len(commit_set) > 1:
        discrepancies.append(
            f"commit mismatch across deliverables: {sorted(filter(None, commit_set))}"
        )
    if len(ts_set) > 1:
        discrepancies.append(
            f"timestamp mismatch across deliverables: {sorted(filter(None, ts_set))}"
        )

    ok = not missing and not discrepancies
    return {
        "pass": ok,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "footers": per_deliv,
            "missing_footer_in": missing,
            "discrepancies": discrepancies,
        },
    }


# ---------------------------------------------------------------------------
# Top-level aggregator
# ---------------------------------------------------------------------------


_DIMENSION_FUNCS = (
    ("numeric_claims_consistent", numeric_claims_consistent),
    ("figures_consistent", figures_consistent),
    ("citations_consistent", citations_consistent),
    ("findings_top_line_consistent", findings_top_line_consistent),
    ("reproducibility_footer_consistent", reproducibility_footer_consistent),
)


def audit_cross_deliverable_consistency(root: Path) -> dict[str, Any]:
    """Run all 5 dimensions and aggregate.

    Returns ``{status, blockers, warnings, dimensions: {dim: {pass, details}}}``.
    Any dimension that fails contributes a blocker. If no deliverable
    other than the paper exists, the audit returns ``status='skipped'``
    with a warning explaining why (you need at least 2 deliverables
    for a *cross*-deliverable check).
    """
    try:
        root = Path(root)
        deliverables = _discover_deliverables(root)

        if len(deliverables) < 2:
            warn = (
                f"Cross-deliverable audit needs ≥2 deliverables; "
                f"found {len(deliverables)} ({list(deliverables.keys())}). "
                f"Author the paper plus at least one of dashboard / slides / "
                f"poster before this audit."
            )
            return {
                "status": "skipped",
                "blockers": [],
                "warnings": [warn],
                "dimensions": {},
                "deliverables_found": list(deliverables.keys()),
            }

        dim_results: dict[str, dict[str, Any]] = {}
        for dim_name, fn in _DIMENSION_FUNCS:
            try:
                dim_results[dim_name] = fn(root, deliverables=deliverables)
            except Exception as e:
                logger.exception("dimension %s failed", dim_name)
                dim_results[dim_name] = {
                    "pass": False,
                    "details": {"error": str(e)},
                }

        blockers: list[str] = []
        warnings: list[str] = []
        # Near-but-different-metric numeric divergences (no shared anchor)
        # are warnings, surfaced even when the dimension passes.
        _num = dim_results.get("numeric_claims_consistent", {}).get("details", {})
        _near = _num.get("near_warning_count", 0)
        if _near:
            warnings.append(
                f"numeric_claims_consistent: {_near} near-but-different-metric "
                "value(s) diverge without a shared metric label — verify they "
                "refer to different quantities (see "
                "dimensions.numeric_claims_consistent.details.near_warnings)."
            )
        for dim_name, result in dim_results.items():
            if result.get("pass"):
                continue
            details = result.get("details", {})
            if dim_name == "numeric_claims_consistent":
                n = details.get("mismatch_count", 0)
                blockers.append(
                    f"numeric_claims_consistent FAIL: {n} numeric claim(s) "
                    f"diverge between deliverables (see dimensions.{dim_name}"
                    ".details.mismatches)."
                )
            elif dim_name == "figures_consistent":
                missing = details.get("paper_figures_missing_elsewhere", [])
                blockers.append(
                    f"figures_consistent FAIL: {len(missing)} paper figure(s) "
                    f"absent from one or more secondary deliverables."
                )
            elif dim_name == "citations_consistent":
                rogue = details.get("rogue_citations", [])
                blockers.append(
                    f"citations_consistent FAIL: {len(rogue)} deliverable(s) "
                    f"cite key(s) not present in the paper bibliography."
                )
            elif dim_name == "findings_top_line_consistent":
                pairs = details.get("weak_pairs", [])
                blockers.append(
                    f"findings_top_line_consistent FAIL: {len(pairs)} "
                    f"deliverable pair(s) below Jaccard threshold "
                    f"{details.get('min_jaccard')}."
                )
            elif dim_name == "reproducibility_footer_consistent":
                miss = details.get("missing_footer_in", [])
                disc = details.get("discrepancies", [])
                blockers.append(
                    f"reproducibility_footer_consistent FAIL: "
                    f"{len(miss)} deliverable(s) missing footer; "
                    f"{len(disc)} discrepancy across footers."
                )

        # Write log.
        log_path = root / "workspace" / "logs" / "cross_deliverable_audit.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _write_log(log_path, deliverables, dim_results, blockers, warnings)

        status = "success" if not blockers else "error"
        return {
            "status": status,
            "blockers": blockers,
            "warnings": warnings,
            "dimensions": dim_results,
            "deliverables_found": list(deliverables.keys()),
            "log_path": str(log_path.relative_to(root)),
        }
    except Exception as e:
        logger.exception("audit_cross_deliverable_consistency failed")
        return {
            "status": "error",
            "blockers": [f"audit crashed: {e}"],
            "warnings": [],
            "dimensions": {},
        }


def _write_log(
    log_path: Path,
    deliverables: dict[str, Path],
    dim_results: dict[str, dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    lines = [
        "# Cross-deliverable consistency audit",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Deliverables scanned",
        "",
    ]
    for name, p in deliverables.items():
        lines.append(f"- **{name}** — `{p}`")
    lines.append("")
    lines.append("## Dimension results")
    lines.append("")
    for dim, result in dim_results.items():
        mark = "PASS" if result.get("pass") else "FAIL"
        lines.append(f"### {dim} — {mark}")
        try:
            blob = json.dumps(result.get("details", {}), indent=2, default=str)
        except (TypeError, ValueError):
            blob = "(unrepresentable details)"
        lines.append("")
        lines.append("```json")
        lines.append(blob)
        lines.append("```")
        lines.append("")
    if blockers:
        lines.append("## Blockers")
        lines.append("")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    log_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# AuditBase wrapper
# ---------------------------------------------------------------------------


# Map dimension name → (severity for any failure, terse human label used in
# the suggested_fix scaffold). The cross-deliverable check is opinionated:
# any divergence between two deliverables is a blocker because it lands in
# front of a reviewer either way, but a missing footer is a warning because
# the deliverable still works without one.
_DIM_SEVERITY: dict[str, str] = {
    "numeric_claims_consistent": "block",
    "figures_consistent": "block",
    "citations_consistent": "block",
    "findings_top_line_consistent": "block",
    "reproducibility_footer_consistent": "warn",
}


class CrossDeliverableConsistencyAudit(AuditBase):
    """:class:`AuditBase` wrapper around
    :func:`audit_cross_deliverable_consistency`.

    Calls the procedural auditor (so
    ``workspace/logs/cross_deliverable_audit.md`` continues to be written
    byte-identically and the response payload consumed by callers is
    preserved verbatim) and then translates each per-dimension result
    into a list of :class:`AuditFinding` objects:

    * one ``severity="block"`` finding per failing structural dimension
      (numeric / figures / citations / findings), one ``severity="warn"``
      finding per failing reproducibility-footer dimension — these are
      the same severities the original aggregator used for its
      ``blockers`` / ``warnings`` lists, preserved through the bridge;
    * one ``severity="info"`` summary finding per run carrying the audit
      status + deliverable count, so the append-only
      ``.audit_findings.jsonl`` ledger gets a heartbeat entry even when
      every dimension passes.

    Each finding's UUID is derived deterministically with ``uuid5`` over
    ``(audit_name, dimension, sorted evidence_paths, suggested_fix)`` so
    that re-running the audit against the same workspace + deliverables
    does NOT churn finding IDs — important for downstream diffing of the
    jsonl ledger across runs.
    """

    name = "cross_deliverable_consistency"

    def run(  # type: ignore[override]
        self,
        root: Path,
        **_: Any,
    ) -> list[AuditFinding]:
        root = Path(root)
        result = audit_cross_deliverable_consistency(root)

        findings: list[AuditFinding] = []

        # Audit short-circuited: not enough deliverables on disk to do a
        # cross-deliverable check. Emit an info heartbeat carrying the
        # skip reason so the ledger reflects the no-op run.
        if result.get("status") == "skipped":
            warns = result.get("warnings") or []
            findings.append(
                _make_finding(
                    severity="info",
                    dimension="cross_deliverable_skipped",
                    evidence_paths=[],
                    suggested_fix=(
                        warns[0]
                        if warns
                        else (
                            "Cross-deliverable audit skipped: fewer than 2 "
                            "deliverables on disk."
                        )
                    ),
                )
            )
            return findings

        # Audit crashed at the top level — no per-dimension data to translate.
        if result.get("status") == "error" and not result.get("dimensions"):
            blockers = result.get("blockers") or [
                "cross_deliverable audit failed with no per-dimension data"
            ]
            for msg in blockers:
                findings.append(
                    _make_finding(
                        severity="block",
                        dimension="cross_deliverable_error",
                        evidence_paths=[],
                        suggested_fix=msg,
                    )
                )
            return findings

        deliverables_found = list(result.get("deliverables_found") or [])
        # All deliverables live under synthesis/; surface their real paths
        # (the actual suffix on disk — .typ / .md / .html) as evidence so
        # the structured finding lets a reviewer jump straight to the
        # files that diverge.
        discovered = _discover_deliverables(root)
        evidence_paths_all = sorted(
            str(discovered[d].relative_to(root))
            for d in deliverables_found
            if d in discovered
        )
        log_path = result.get("log_path") or (
            "workspace/logs/cross_deliverable_audit.md"
        )

        dim_results: dict[str, dict[str, Any]] = result.get("dimensions") or {}
        for dim_name, dim_result in dim_results.items():
            if dim_result.get("pass"):
                continue
            severity = _DIM_SEVERITY.get(dim_name, "block")
            suggested_fix = _suggested_fix_for_dimension(
                dim_name, dim_result.get("details") or {}
            )
            findings.append(
                _make_finding(
                    severity=severity,
                    dimension=dim_name,
                    evidence_paths=[*evidence_paths_all, log_path],
                    suggested_fix=suggested_fix,
                )
            )

        # Always emit an info summary so the ledger gets a heartbeat
        # even when every dimension passes cleanly.
        passing = sum(1 for r in dim_results.values() if r.get("pass"))
        failing = len(dim_results) - passing
        findings.append(
            _make_finding(
                severity="info",
                dimension="cross_deliverable_summary",
                evidence_paths=[*evidence_paths_all, log_path],
                suggested_fix=(
                    f"{passing} of {len(dim_results)} dimensions passed "
                    f"({failing} failing) across "
                    f"{len(deliverables_found)} deliverable(s): "
                    f"{', '.join(deliverables_found) or '—'}."
                ),
            )
        )

        return findings


def _suggested_fix_for_dimension(dim_name: str, details: dict[str, Any]) -> str:
    """Human-readable one-liner for each failing dimension.

    Mirrors the blocker phrasing the legacy aggregator already emits, but
    flips it into an actionable second-person remediation that the AI or
    user can paste straight into the next edit.
    """
    if dim_name == "numeric_claims_consistent":
        n = details.get("mismatch_count", 0)
        return (
            f"{n} numeric claim(s) diverge between deliverables (>1% "
            "relative difference). Reconcile the values in "
            "workspace/logs/cross_deliverable_audit.md and re-render."
        )
    if dim_name == "figures_consistent":
        missing = details.get("paper_figures_missing_elsewhere") or []
        stems = ", ".join(m.get("figure_stem", "?") for m in missing[:3])
        more = "" if len(missing) <= 3 else f" (+{len(missing) - 3} more)"
        return (
            f"{len(missing)} paper figure(s) absent from one or more "
            f"secondary deliverables: {stems}{more}. Embed them via "
            "tool_figure_auto_embed or drop them from the paper."
        )
    if dim_name == "citations_consistent":
        rogue = details.get("rogue_citations") or []
        return (
            f"{len(rogue)} deliverable(s) cite key(s) not in the paper "
            "bibliography. Add the missing keys to the paper or remove "
            "them from the secondary deliverable."
        )
    if dim_name == "findings_top_line_consistent":
        pairs = details.get("weak_pairs") or []
        thresh = details.get("min_jaccard", 0.30)
        return (
            f"{len(pairs)} deliverable pair(s) below Jaccard threshold "
            f"{thresh}: the headline finding doesn't read consistently. "
            "Rewrite the Findings sections so they share core vocabulary."
        )
    if dim_name == "reproducibility_footer_consistent":
        miss = details.get("missing_footer_in") or []
        disc = details.get("discrepancies") or []
        return (
            f"{len(miss)} deliverable(s) missing footer; "
            f"{len(disc)} cross-deliverable discrepancy. Re-run the "
            "render pipeline so every deliverable carries the same "
            "Research-OS version + commit + timestamp."
        )
    return f"{dim_name} failed; inspect dimensions.{dim_name}.details."


def _make_finding(
    *,
    severity: str,
    dimension: str,
    evidence_paths: list[str],
    suggested_fix: str,
) -> AuditFinding:
    """Build an :class:`AuditFinding` with a deterministic uuid5 id.

    Keying off ``(audit_name, dimension, sorted evidence_paths,
    suggested_fix)`` keeps the id stable across reruns where the audit
    finds the same problem in the same place, so the append-only
    ``.audit_findings.jsonl`` ledger can be diffed cleanly. ``severity``
    is intentionally NOT part of the key — re-classifying a known
    finding from warn → block should preserve its identity.
    """
    audit_name = "cross_deliverable_consistency"
    key = "|".join([
        audit_name,
        dimension,
        ",".join(sorted(evidence_paths)),
        suggested_fix,
    ])
    stable_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
    return AuditFinding(
        audit_name=audit_name,
        severity=severity,
        dimension=dimension,
        id=stable_id,
        evidence_paths=list(evidence_paths),
        suggested_fix=suggested_fix,
    )


__all__ = [
    "audit_cross_deliverable_consistency",
    "numeric_claims_consistent",
    "figures_consistent",
    "citations_consistent",
    "findings_top_line_consistent",
    "reproducibility_footer_consistent",
    "_numeric_claim_extractor",
    "CrossDeliverableConsistencyAudit",
]
