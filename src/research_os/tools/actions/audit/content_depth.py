"""Content depth enforcement.

Goes beyond word-count gates to check that each IMRAD section actually
SAYS something: numbers in the abstract, citations in the intro, every
step covered in methods, statistics in results, limitations + future
work in discussion. Also flags AI-cliché phrases that pad without
adding information, and per-step coverage in Methods/Results.

Public surface:
  * section_substantiveness(root, paper_path) -> dict
  * audit_cliches(paper_path, root) -> dict
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PAPER_SECTIONS = ("abstract", "introduction", "methods", "results", "discussion", "references")


# ---------------------------------------------------------------------------
# AI cliché bank (each = a WARNING with a replacement hint).
# ---------------------------------------------------------------------------


CLICHES: tuple[tuple[str, str], ...] = (
    (
        "in this study, we investigate",
        "Lead with the SPECIFIC finding, not the meta-statement.",
    ),
    (
        "our results demonstrate that",
        "Just state the finding. 'X correlates with Y (r = .42)' beats 'Our results demonstrate that...'",
    ),
    (
        "future work should explore",
        "Name a concrete next experiment with its constraint and expected signal.",
    ),
    (
        "it is important to note that",
        "Banned filler phrase. Cut it; the next sentence carries the load.",
    ),
    (
        "however, more research is needed",
        "Be specific: what experiment, with what design, would answer the open question?",
    ),
    (
        "this finding has important implications for",
        "Name the implication. Don't promise; deliver.",
    ),
    (
        "to the best of our knowledge",
        "Cite the contemporary work you searched against. 'To the best of our knowledge' is unverifiable.",
    ),
    (
        "in conclusion,",
        "Don't announce the conclusion. Just write it.",
    ),
    (
        "plays a crucial role in",
        "Cliché. Replace with what the role specifically IS.",
    ),
    (
        "shed light on",
        "Cliché. Describe the actual mechanism / finding.",
    ),
)


# ---------------------------------------------------------------------------
# Section extractor
# ---------------------------------------------------------------------------


def _section_text(paper_text: str, section: str) -> str:
    m = re.search(
        rf"^##\s+{section}\s*\n(.+?)(?=^##\s|\Z)",
        paper_text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return (m.group(1) if m else "").strip()


def _step_dirs(root: Path) -> list[Path]:
    workspace = root / "workspace"
    if not workspace.exists():
        return []
    return sorted(
        d for d in workspace.iterdir()
        if d.is_dir() and d.name[:2].isdigit() and not d.name.endswith("__DEAD_END")
    )


# ---------------------------------------------------------------------------
# Per-section audits
# ---------------------------------------------------------------------------


_NUMBER_RE = re.compile(
    # number followed by optional space + unit. The unit set ends with
    # word units (cells, samples, ...) where a trailing word-boundary
    # is meaningful, AND with non-word units (%) where it isn't —
    # so we don't put `\b` after the alternation group.
    r"\b\d+\.?\d*\s*(?:%|years?|fold|mg|μg|ug|μm|um|nm|ml|mL|L|kg|"
    r"sec|seconds|min|minutes|hr|hours|days|weeks|months|cells|samples|"
    r"patients|subjects|points|epochs|p|q|n)"
    r"|(?<!\d)\d+\.\d+(?!\d)|(?<!\d)\d{3,}(?!\d)",
    re.IGNORECASE,
)

_CONCLUSION_VERBS = (
    "found", "showed", "demonstrate", "demonstrated", "indicate",
    "indicated", "suggest", "suggested", "support", "supported",
    "reveal", "revealed", "confirm", "confirmed",
)


def audit_abstract(text: str) -> dict[str, Any]:
    """Abstract bar: ≥1 number, ≥1 method, ≥1 conclusion verb."""
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        blockers.append("Abstract missing entirely.")
        return {"blockers": blockers, "warnings": warnings}
    n_nums = len(_NUMBER_RE.findall(text))
    if n_nums == 0:
        blockers.append("Abstract has no quantitative claim. Add at least one number with units.")
    has_verb = any(v in text.lower() for v in _CONCLUSION_VERBS)
    if not has_verb:
        blockers.append(
            "Abstract has no conclusion verb (found/showed/demonstrate/indicate/suggest/support)."
        )
    # Method-name detection: capitalised proper noun followed by lowercase word
    # OR a "we (used|applied|fit|ran|conducted) X" pattern.
    has_method = bool(re.search(
        r"\bwe\s+(used|applied|fit|ran|conducted|performed|computed|estimated|trained)\s+\w+",
        text, re.I,
    )) or bool(re.search(r"\b[A-Z][a-z]{3,}\s+(model|test|regression|analysis|method)", text))
    if not has_method:
        warnings.append("Abstract names no method by name. Add: 'We applied X' or '<Method>'.")
    return {"blockers": blockers, "warnings": warnings, "n_numbers": n_nums}


def audit_introduction(text: str) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        blockers.append("Introduction missing entirely.")
        return {"blockers": blockers, "warnings": warnings}
    citations_pandoc = re.findall(r"\[@[^\]]+\]|\\cite\{[^}]+\}", text)
    citations_authoryear = re.findall(
        r"\(([A-Z][a-zA-Z\-]+(?:\s+et\s+al\.?)?(?:\s*&\s*[A-Z][a-zA-Z\-]+)?(?:\s*,)?\s+(?:19|20)\d{2}[a-z]?)\)",
        text,
    )
    n_cites = len(citations_pandoc) + len(set(citations_authoryear))
    if n_cites < 3:
        blockers.append(
            f"Introduction cites {n_cites} prior work(s); need ≥ 3 to motivate the study."
        )
    has_pivot = bool(re.search(
        r"\b(in this study,?\s+we|here,?\s+we|we\s+report|we\s+present)\b",
        text, re.I,
    ))
    if not has_pivot:
        blockers.append(
            "Introduction has no 'in this study, we…' / 'here, we…' pivot to the contribution."
        )
    return {"blockers": blockers, "warnings": warnings, "n_citations": n_cites}


def audit_methods(text: str, root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        blockers.append("Methods missing entirely.")
        return {"blockers": blockers, "warnings": warnings, "step_coverage_pct": 0}
    steps = _step_dirs(root)
    n_steps = len(steps)
    if n_steps == 0:
        return {"blockers": blockers, "warnings": warnings, "step_coverage_pct": 100}
    covered = 0
    text_lower = text.lower()
    uncovered: list[str] = []
    for d in steps:
        slug = d.name.lower()
        slug_stem = re.sub(r"^\d+_+", "", slug)
        primary_tool = ""
        summary_path = d / "step_summary.yaml"
        if summary_path.exists():
            try:
                yml = summary_path.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"primary_tool:\s*['\"]?([\w_.-]+)", yml, re.I)
                if m:
                    primary_tool = m.group(1).lower()
            except OSError:
                # step_summary unreadable — skip the primary_tool hint
                # and fall back to the slug-only match below.
                pass
        if slug in text_lower or slug_stem in text_lower or (primary_tool and primary_tool in text_lower):
            covered += 1
        else:
            uncovered.append(d.name)
    coverage_pct = round(100 * covered / n_steps)
    if coverage_pct < 50:
        blockers.append(
            f"Methods covers only {coverage_pct}% of workspace steps "
            f"({covered}/{n_steps}). Add: {', '.join(uncovered[:3])}."
        )
    elif coverage_pct < 80:
        warnings.append(
            f"Methods covers {coverage_pct}% of workspace steps "
            f"({covered}/{n_steps}). Consider naming: {', '.join(uncovered[:3])}."
        )
    return {
        "blockers": blockers, "warnings": warnings,
        "step_coverage_pct": coverage_pct, "uncovered_steps": uncovered,
    }


_STATISTIC_RE = re.compile(
    r"\b(?:p\s*[=<>≤≥]\s*\d|95%\s*CI|HR\s*=\s*\d|OR\s*=\s*\d|RR\s*=\s*\d|"
    r"r\s*=\s*\d|t\s*\(\s*\d+\s*\)\s*=\s*\d|F\s*\(\s*\d+\s*,\s*\d+\s*\)\s*=\s*\d|"
    r"χ2|chi-?square|β\s*=\s*\d|d\s*=\s*\d|η\s*=\s*\d|η²)",
    re.IGNORECASE,
)


def audit_results(text: str, root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        blockers.append("Results missing entirely.")
        return {"blockers": blockers, "warnings": warnings}
    stats = _STATISTIC_RE.findall(text)
    if not stats:
        warnings.append(
            "Results has no inferential statistics (p value, CI, effect size). "
            "Add ≥ 1 per primary finding."
        )
    # Per-step focal figure references.
    steps = _step_dirs(root)
    referenced = 0
    missing: list[str] = []
    for d in steps:
        figs = d / "outputs" / "figures"
        if not figs.is_dir():
            continue
        focal = None
        for f in figs.iterdir():
            if f.suffix.lower() in {".png", ".pdf", ".svg", ".jpg"}:
                focal = f
                break
        if focal is None:
            continue
        if focal.stem in text or str(focal.relative_to(root)) in text:
            referenced += 1
        else:
            missing.append(str(focal.relative_to(root)))
    if missing and len(missing) >= 2:
        warnings.append(
            f"{len(missing)} step focal figure(s) not referenced in Results: "
            f"{', '.join(missing[:3])}."
        )
    return {
        "blockers": blockers, "warnings": warnings,
        "n_statistics": len(stats),
        "figures_referenced": referenced,
        "figures_unreferenced": missing,
    }


def audit_discussion(text: str, root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        blockers.append("Discussion missing entirely.")
        return {"blockers": blockers, "warnings": warnings}
    # Limitations paragraph: heading OR ≥3 hedging phrases.
    has_limits_heading = bool(re.search(r"^###?\s+limit", text, re.M | re.I))
    hedging = sum(1 for h in (
        "limitation", "caveat", "however,", "we cannot",
        "may not", "should not", "is limited", "unable to",
    ) if h in text.lower())
    if not has_limits_heading and hedging < 3:
        blockers.append(
            "Discussion has no Limitations paragraph (heading or ≥ 3 hedging phrases)."
        )
    has_future = any(p in text.lower() for p in ("future work", "further studies", "next step", "future research"))
    if not has_future:
        blockers.append("Discussion has no future-work direction.")
    # Disagreement coverage from findings_vs_literature.md.
    disagrees: list[str] = []
    for d in _step_dirs(root):
        fvl = d / "outputs" / "reports" / "findings_vs_literature.md"
        if fvl.exists():
            if "disagrees" in fvl.read_text(encoding="utf-8", errors="replace").lower():
                disagrees.append(d.name)
    if disagrees:
        # Heuristic: a "DISAGREES" paragraph mentions disagree / contrary / contrast.
        n_disagree_paras = len(re.findall(
            r"(?:disagree|contrary|contrast|inconsistent\s+with)",
            text, re.I,
        ))
        if n_disagree_paras < 1:
            warnings.append(
                f"{len(disagrees)} step(s) have DISAGREES literature verdicts; "
                "Discussion includes no paragraph addressing them."
            )
    return {
        "blockers": blockers, "warnings": warnings,
        "has_limitations": has_limits_heading or hedging >= 3,
        "has_future_work": has_future,
    }


def audit_references_present(text: str) -> dict[str, Any]:
    """Every cited key must appear in the References section."""
    blockers: list[str] = []
    warnings: list[str] = []
    if not text:
        return {"blockers": blockers, "warnings": warnings}
    cited = set(re.findall(r"@([A-Za-z][\w:.-]+)", text))
    refs_section_match = re.search(
        r"^##\s+references\s*\n(.+?)(?=^##\s|\Z)",
        text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    bib_text = refs_section_match.group(1) if refs_section_match else ""
    bib_keys = set(re.findall(r"@?([A-Za-z][\w:.-]+)", bib_text))
    missing = sorted(cited - bib_keys)
    if missing:
        blockers.append(
            f"{len(missing)} cited key(s) missing from References: "
            f"{', '.join(missing[:5])}."
        )
    unused = sorted(bib_keys - cited - {"References"})
    if unused and len(unused) >= 3:
        warnings.append(
            f"{len(unused)} References entry/entries are never cited "
            f"in the body."
        )
    return {"blockers": blockers, "warnings": warnings}


# ---------------------------------------------------------------------------
# Cliché detection (banned phrases + replacement hints)
# ---------------------------------------------------------------------------


def audit_cliches(paper_path: str, root: Path) -> dict[str, Any]:
    p = root / paper_path
    if not p.exists():
        return {"status": "error", "message": f"{paper_path} not found.", "hits": []}
    text = p.read_text(encoding="utf-8", errors="replace")
    text_lower = text.lower()
    hits: list[dict[str, str]] = []
    for cliche, hint in CLICHES:
        for m in re.finditer(re.escape(cliche), text_lower):
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(text_lower), m.end() + 30)
            hits.append({
                "cliche": cliche,
                "context": text[ctx_start:ctx_end].strip(),
                "hint": hint,
            })
    return {
        "status": "warning" if hits else "success",
        "hits": hits,
        "n_hits": len(hits),
        "warnings": [f"AI-cliché: '{h['cliche']}' — {h['hint']}" for h in hits],
    }


# ---------------------------------------------------------------------------
# Top-level wrapper
# ---------------------------------------------------------------------------


def section_substantiveness(root: Path, paper_path: str = "synthesis/paper.md") -> dict[str, Any]:
    p = root / paper_path
    if not p.exists():
        return {"status": "error", "message": f"{paper_path} not found.", "blockers": [], "warnings": []}
    text = p.read_text(encoding="utf-8", errors="replace")

    sub_reports = {
        "abstract":     audit_abstract(_section_text(text, "abstract")),
        "introduction": audit_introduction(_section_text(text, "introduction")),
        "methods":      audit_methods(_section_text(text, "methods"), root),
        "results":      audit_results(_section_text(text, "results"), root),
        "discussion":   audit_discussion(_section_text(text, "discussion"), root),
        "references":   audit_references_present(text),
    }
    cliche = audit_cliches(paper_path, root)

    blockers: list[str] = []
    warnings: list[str] = []
    for name, r in sub_reports.items():
        for b in r.get("blockers", []):
            blockers.append(f"[{name}] {b}")
        for w in r.get("warnings", []):
            warnings.append(f"[{name}] {w}")
    for w in cliche.get("warnings", []):
        warnings.append(w)

    # Per-step coverage promotion: 2+ uncovered steps in BOTH methods AND
    # results = BLOCKER for uneven paper.
    methods_uncov = sub_reports["methods"].get("uncovered_steps", [])
    results_unref = sub_reports["results"].get("figures_unreferenced", [])
    if len(methods_uncov) >= 2 and len(results_unref) >= 2:
        blockers.append(
            f"Per-step coverage failure: {len(methods_uncov)} step(s) missing "
            f"from Methods AND {len(results_unref)} focal figure(s) missing from "
            "Results. Paper is uneven."
        )

    return {
        "status": "error" if blockers else "success",
        "blockers": blockers,
        "warnings": warnings,
        "sub_reports": sub_reports,
        "cliches": cliche,
    }
