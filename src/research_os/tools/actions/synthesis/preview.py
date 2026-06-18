"""Synthesis preview: cheap, deterministic dry-run of tool_synthesize.

Reads the same source data tool_synthesize reads but does NOT draft
prose. Predicts word counts per section, page count, figures to embed,
citations to cite, and detected gaps. Lets the researcher approve
the shape before the AI spends tokens generating it.

Public surface: synthesis_preview(root, target, venue, mode).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PAPER_SECTIONS = ("abstract", "introduction", "methods", "results", "discussion")

# Rough word floors (used to estimate how much new prose synthesize will
# emit per section if the source has any content at all).
WORDS_PER_SECTION_BUDGET = {
    "abstract": 200,
    "introduction": 400,
    "methods": 500,
    "results": 500,
    "discussion": 400,
}

WORDS_PER_PAGE_BY_VENUE = {
    "nature": 650,
    "science": 650,
    "nejm": 600,
    "cell": 600,
    "ieee_conf": 800,
    "neurips": 700,
    "acl": 700,
    "plos": 600,
    "generic_two_column": 700,
    "generic_thesis": 350,
}


def _step_dirs(root: Path) -> list[Path]:
    from research_os.project_ops import discover_step_dirs
    return discover_step_dirs(root / "workspace", include_dead=False)


def _per_step_conclusions(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in _step_dirs(root):
        conc = d / "conclusions.md"
        flit = d / "literature" / "findings_vs_literature.md"
        # conclusions.md is the methods source of truth (step_summary.yaml
        # was retired in 3.2). A step "has methods" when its conclusions.md
        # carries a non-stub Methods section.
        has_methods = False
        if conc.exists():
            ctxt = conc.read_text(encoding="utf-8", errors="replace")
            mm = re.search(
                r"^##\s+Methods.*?\n(.*?)(?=^##\s|\Z)",
                ctxt, re.MULTILINE | re.DOTALL,
            )
            body = (mm.group(1).strip() if mm else "")
            has_methods = bool(body) and not body.startswith(("*(", "_("))
        entry: dict[str, Any] = {
            "step_id": d.name,
            "has_conclusions": conc.exists() and conc.stat().st_size > 100,
            "conclusion_words": (
                len(conc.read_text(encoding="utf-8", errors="replace").split())
                if conc.exists() else 0
            ),
            "has_methods": has_methods,
            "has_findings_vs_literature": flit.exists(),
            "verdicts": [],
        }
        if flit.exists():
            text = flit.read_text(encoding="utf-8", errors="replace").lower()
            for v in ("agrees", "disagrees", "extends", "partially supports"):
                if v in text:
                    entry["verdicts"].append(v)
        # Focal figure detection.
        figs_dir = d / "outputs" / "figures"
        entry["figures"] = (
            [str(f.relative_to(root)) for f in figs_dir.iterdir() if f.suffix.lower() in {".png", ".svg", ".pdf"}]
            if figs_dir.is_dir() else []
        )
        out.append(entry)
    return out


def _all_citation_keys(root: Path) -> list[str]:
    citations = root / "workspace" / "citations.md"
    if not citations.exists():
        return []
    text = citations.read_text(encoding="utf-8", errors="replace")
    keys = re.findall(r"@([A-Za-z][\w:.-]+)", text)
    # Heuristic fallback: leading-line bare keys.
    if not keys:
        for ln in text.splitlines():
            m = re.match(r"^[*-]?\s*([A-Za-z][\w:.-]+)\s*[:.]", ln)
            if m:
                keys.append(m.group(1))
    return sorted(set(keys))


def _detect_gaps(steps: list[dict[str, Any]], target: str) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    n_with_concl = sum(1 for s in steps if s["has_conclusions"])
    if n_with_concl < len(steps):
        gaps.append({
            "section": "results",
            "gap_type": "missing_step_conclusions",
            "description": (
                f"{len(steps) - n_with_concl} of {len(steps)} step(s) lack "
                "substantive conclusions.md; Results will under-cover those steps."
            ),
        })
    n_with_methods = sum(1 for s in steps if s["has_methods"])
    if n_with_methods < len(steps):
        gaps.append({
            "section": "methods",
            "gap_type": "missing_step_methods",
            "description": (
                f"{len(steps) - n_with_methods} of {len(steps)} step(s) lack "
                "a Methods section in conclusions.md; Methods will be thin "
                "on those steps."
            ),
        })
    has_disagree = any("disagrees" in s["verdicts"] for s in steps)
    if target in {"paper", "dashboard"} and not has_disagree:
        gaps.append({
            "section": "discussion",
            "gap_type": "no_disagree_verdicts",
            "description": (
                "No DISAGREES verdicts found in any step's "
                "findings_vs_literature.md; Discussion section's "
                "literature-disagreement paragraph will be empty."
            ),
        })
    n_figs = sum(len(s["figures"]) for s in steps)
    if target == "paper" and n_figs < 2:
        gaps.append({
            "section": "results",
            "gap_type": "few_figures",
            "description": (
                f"Only {n_figs} figure(s) detected across all steps; "
                "papers typically benefit from ≥ 3 focal figures."
            ),
        })
    return gaps


def synthesis_preview(
    root: Path,
    target: str = "paper",
    venue: str | None = None,
    mode: str = "fresh",
) -> dict[str, Any]:
    """Predict what tool_synthesize will produce without actually drafting it."""
    target = (target or "paper").lower()
    mode = (mode or "fresh").lower()
    if not venue:
        try:
            from research_os.tools.actions.state.config import get_research_config

            cfg = get_research_config(root) or {}
            venue = (cfg.get("writing_preferences", {}) or {}).get(
                "venue_template", "generic_two_column"
            )
        except Exception:
            venue = "generic_two_column"

    steps = _per_step_conclusions(root)
    citations = _all_citation_keys(root)

    # Predict section word counts.
    section_words: dict[str, int] = {}
    if target == "paper":
        for sec in PAPER_SECTIONS:
            base = WORDS_PER_SECTION_BUDGET.get(sec, 300)
            if sec == "results" and steps:
                # Scale by how many steps have substantive conclusions.
                section_words[sec] = base + 100 * sum(
                    1 for s in steps if s["has_conclusions"]
                )
            elif sec == "methods" and steps:
                section_words[sec] = base + 80 * len(steps)
            elif sec == "discussion":
                # Discussion grows with the number of disagree verdicts.
                disagrees = sum(1 for s in steps if "disagrees" in s["verdicts"])
                section_words[sec] = base + 150 * disagrees
            else:
                section_words[sec] = base
        total_words = sum(section_words.values())
    elif target == "dashboard":
        section_words = {"abstract": 200, "findings": 400, "per_step": 100 * len(steps)}
        total_words = sum(section_words.values())
    elif target == "slides":
        section_words = {"slides": 60 * (5 + len(steps))}
        total_words = section_words["slides"]
    elif target == "poster":
        section_words = {"title": 20, "abstract": 100, "findings": 200, "limitations": 80}
        total_words = sum(section_words.values())
    elif target == "grant":
        section_words = {
            "specific_aims": 350, "significance": 600, "innovation": 400,
            "approach": 1500, "preliminary_data": 600,
        }
        total_words = sum(section_words.values())
    else:  # report
        section_words = {"summary": 250, "approach": 400, "results": 600, "next_steps": 200}
        total_words = sum(section_words.values())

    page_count = None
    slide_count = None
    if target in {"paper", "poster", "grant", "report"}:
        wpp = WORDS_PER_PAGE_BY_VENUE.get(venue, 700)
        page_count = max(1, round(total_words / wpp))
    elif target == "slides":
        slide_count = 5 + len(steps)

    figures = [f for s in steps for f in s["figures"]]

    # Steps drawn from per section (just lists by step_id).
    steps_per_section = {
        "methods": [s["step_id"] for s in steps if s["has_methods"]],
        "results": [s["step_id"] for s in steps if s["has_conclusions"]],
        "discussion": [s["step_id"] for s in steps if s["verdicts"]],
    }

    gaps = _detect_gaps(steps, target)

    # Estimated render time: heuristic 0.5s per 100 words + 1s per figure.
    est_seconds = total_words / 200.0 + len(figures) * 1.0

    payload: dict[str, Any] = {
        "target": target,
        "venue": venue,
        "mode": mode,
        "predicted_word_count_per_section": section_words,
        "predicted_total_word_count": total_words,
        "predicted_page_count": page_count,
        "predicted_slide_count": slide_count,
        "predicted_figures_embedded": figures,
        "predicted_citations": citations,
        "predicted_steps_drawn_from": steps_per_section,
        "detected_gaps": gaps,
        "estimated_render_time_seconds": round(est_seconds, 1),
    }

    if mode == "diff":
        # Compare against the existing deliverable on disk.
        existing_path = {
            "paper": root / "synthesis" / "paper.md",
            "dashboard": root / "synthesis" / "dashboard.html",
        }.get(target)
        if existing_path and existing_path.exists():
            existing_text = existing_path.read_text(encoding="utf-8", errors="replace")
            existing_words = len(existing_text.split())
            existing_figs = set(re.findall(
                r"!\[[^\]]*\]\(([^)]+\.(?:png|svg|pdf|jpg))\)", existing_text,
            )) if target == "paper" else set()
            existing_cites = set(re.findall(r"@([A-Za-z][\w:.-]+)", existing_text))
            payload["diff_mode"] = {
                "what_would_change": {
                    sec: (
                        "rewritten" if section_words.get(sec, 0) > 0 else "untouched"
                    ) for sec in section_words
                },
                "net_word_delta": total_words - existing_words,
                "figures_added": [f for f in figures if f not in existing_figs],
                "figures_removed": sorted(existing_figs - set(figures)),
                "citations_added": [c for c in citations if c not in existing_cites],
                "citations_removed": sorted(existing_cites - set(citations)),
            }
        else:
            payload["diff_mode"] = {
                "what_would_change": {sec: "new" for sec in section_words},
                "net_word_delta": total_words,
                "figures_added": figures,
                "figures_removed": [],
                "citations_added": citations,
                "citations_removed": [],
            }
    return payload
