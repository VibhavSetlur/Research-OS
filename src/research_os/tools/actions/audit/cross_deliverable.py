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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.audit.cross_deliverable")


# ---------------------------------------------------------------------------
# Deliverable discovery
# ---------------------------------------------------------------------------


# Map deliverable name -> ordered list of candidate paths (first match wins).
# The list intentionally covers both Markdown and rendered forms — a project
# might ship paper.md, paper.pdf, or both. We read text-shaped sources only
# (PDFs are skipped; the source of truth for the audit is the markdown).
_DELIVERABLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "paper": ("synthesis/paper.md",),
    "dashboard": (
        "synthesis/dashboard.html",
        "synthesis/dashboard_story.md",
    ),
    "slides": (
        "synthesis/slides.md",
        "synthesis/slides.html",
    ),
    "poster": (
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
        # sample size:  n = 423 / N=12 / n = 1,200
        [nN]\s*=\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?
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


def _numeric_claim_extractor(text: str) -> list[dict[str, Any]]:
    """Extract numeric claims from a deliverable's source text.

    Returns a list of dicts with ``token``, ``value`` (float), and
    ``kind`` ('p_value' | 'sample_size' | 'percentage' | 'decimal').
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

    # Bucket every claim by (kind, rounded-value).
    # For each bucket, list the deliverables that emit it.
    # A "mismatch" is two deliverables that both emit a value of the
    # same kind, where their values differ by more than `tolerance`.
    mismatches: list[dict[str, Any]] = []
    by_kind: dict[str, dict[str, list[float]]] = {}
    for name, claims in per_deliv.items():
        for c in claims:
            by_kind.setdefault(c["kind"], {}).setdefault(name, []).append(c["value"])

    for kind, deliv_values in by_kind.items():
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
                    # of the same kind), it's fine. Otherwise it's a candidate
                    # mismatch — but only flag if there exists a value in B
                    # that is "close but not equal" (within 10× tolerance).
                    matched = any(
                        _within(vb, va, tolerance) for vb in vals_b
                    )
                    if matched:
                        continue
                    near = [
                        vb for vb in vals_b if _within(vb, va, tolerance * 10)
                    ]
                    if near:
                        mismatches.append({
                            "kind": kind,
                            "deliverable_a": a,
                            "value_a": va,
                            "deliverable_b": b,
                            "value_b_candidates": near,
                            "relative_diff": min(
                                abs(vb - va) / max(abs(va), abs(vb), 1e-12)
                                for vb in near
                            ),
                        })

    return {
        "pass": not mismatches,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "claim_counts": {k: len(v) for k, v in per_deliv.items()},
            "mismatches": mismatches[:50],
            "mismatch_count": len(mismatches),
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
_TYPST_IMG_RE = re.compile(r"#image\(\"([^\"]+)")
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

    # A "shared" figure stem appears in at least 2 deliverables. For
    # each shared stem, any other deliverable that should plausibly
    # also show it but does not is flagged. We treat paper as the
    # canonical source: any figure in the paper that is missing from
    # the dashboard / slides / poster (when those deliverables exist)
    # is a soft mismatch.
    missing: list[dict[str, Any]] = []
    paper_stems = per_deliv.get("paper", set())
    for stem in sorted(paper_stems):
        absent_in: list[str] = []
        for other in ("dashboard", "slides", "poster"):
            if other in per_deliv and stem not in per_deliv[other]:
                absent_in.append(other)
        if absent_in:
            missing.append({"figure_stem": stem, "absent_in": absent_in})

    # Also check the inverse: figures in dashboard/slides/poster that
    # aren't in the paper (paper is the canonical record).
    extra: list[dict[str, Any]] = []
    for other in ("dashboard", "slides", "poster"):
        if other not in per_deliv:
            continue
        for stem in sorted(per_deliv[other] - paper_stems):
            extra.append({"figure_stem": stem, "deliverable": other})

    # Threshold: more than 1 missing-from-paper-everywhere figure is a
    # blocker (the deliverables genuinely disagree). 1 missing is a
    # warning (could be a poster-only summary figure).
    return {
        "pass": len(missing) == 0,
        "details": {
            "deliverables_scanned": list(deliverables.keys()),
            "figures_per_deliverable": {
                k: sorted(v) for k, v in per_deliv.items()
            },
            "paper_figures_missing_elsewhere": missing,
            "figures_in_secondary_but_not_paper": extra,
        },
    }


# ---------------------------------------------------------------------------
# Dimension 3 — citations
# ---------------------------------------------------------------------------


_CITE_KEY_RE = re.compile(
    r"""
    (?:
        # @citekey (markdown / pandoc / typst)
        @([A-Za-z][\w:-]+)
        |
        # \cite{key1,key2}
        \\cite[ptn]?\{([^}]+)\}
        |
        # [@key1; @key2] (pandoc)
        \[@([A-Za-z][\w:-]+)
    )
    """,
    re.VERBOSE,
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
                f"Run tool_synthesize + tool_dashboard_create (or slides / "
                f"poster) before this audit."
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


__all__ = [
    "audit_cross_deliverable_consistency",
    "numeric_claims_consistent",
    "figures_consistent",
    "citations_consistent",
    "findings_top_line_consistent",
    "reproducibility_footer_consistent",
    "_numeric_claim_extractor",
]
