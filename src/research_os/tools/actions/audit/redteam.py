"""Red-team / hostile-reviewer scaffolding.

Produces a structured reviewer-style report against the project's own
paper. The AI fills it in by walking each claim against the workspace
outputs, the literature, and a fixed list of "devil's advocate"
questions. The scaffold mirrors the structure of a real journal
referee report so the output reads as a critique a reviewer would
actually write — not as a generic "any concerns?" sweep.

Sections produced
-----------------
* **Reviewer summary** — one paragraph in the reviewer's own words
  (proves the model read the paper).
* **Overall recommendation** — accept / minor revision / major
  revision / reject.
* **Major comments (M1, M2, ...)** — claim-by-claim challenges,
  ranked by severity. Each comment has: claim quoted from the paper,
  the concern, the evidence the concern rests on, the requested
  mitigation, line reference.
* **Minor comments (m1, m2, ...)** — small fixes, wording, missing
  references.
* **Threats to validity** — internal, external, construct,
  statistical conclusion validity, with one paragraph per dimension.
* **Devil's-advocate questions** — what would change my mind? What's
  the strongest opposing position? Which assumption fails first?

The output file is ``workspace/reviews/redteam_<iso>.md``. The model
that ran the audit is responsible for filling the headings with
concrete content; this module produces the SCAFFOLD plus an inventory
of materials the model should consult.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.audit.redteam")


_DEVIL_QS = [
    "What is the most likely alternative explanation for the headline result?",
    "Which assumption, if violated, would invalidate the main finding?",
    "What is the strongest version of the opposing position?",
    "If a colleague tried to replicate this and failed, where would the "
    "first failure point be?",
    "What evidence would update me toward rejecting the headline result?",
    "Is the effect size practically meaningful, independent of statistical "
    "significance?",
    "How would the finding look if the worst-case missing-data assumption "
    "were true?",
    "What is the most likely confound the design doesn't fully control for?",
    "Are the reported precision (CI / SE) and effective sample size honest "
    "given the analytic complexity?",
    "Does the conclusion overshoot what the analysis actually warrants?",
]


_VALIDITY_DIMENSIONS = [
    ("internal", "Does the design rule out alternative explanations for "
     "the observed relationship? Confounding, selection, measurement bias?"),
    ("external", "How far do the findings generalise beyond the sample, "
     "setting, time, and operationalisation studied?"),
    ("construct", "Do the measures actually capture the constructs the paper "
     "claims to be about, or do they capture something narrower / broader?"),
    ("statistical", "Are the inferential tests appropriate, the assumptions "
     "satisfied, the multiplicity handled, the power adequate?"),
]


def _inventory(root: Path) -> dict[str, Any]:
    """List everything the reviewer should know about for grounding."""
    inv: dict[str, Any] = {
        "paper": None,
        "abstract": None,
        "dashboard": None,
        "completeness_report": None,
        "claim_grounding_report": None,
        "prose_audit": None,
        "code_quality": None,
        "preregistration": None,
        "active_hypotheses": [],
        "step_count": 0,
        "figure_count": 0,
    }
    paper = root / "synthesis" / "paper.md"
    if paper.exists():
        inv["paper"] = str(paper.relative_to(root))
    for fname, key in [
        ("synthesis/abstract.md", "abstract"),
        ("synthesis/dashboard.html", "dashboard"),
        ("workspace/logs/step_completeness.md", "completeness_report"),
        ("workspace/logs/claim_grounding.md", "claim_grounding_report"),
        ("workspace/logs/prose_audit.md", "prose_audit"),
        ("workspace/logs/code_quality.md", "code_quality"),
    ]:
        p = root / fname
        if p.exists():
            inv[key] = fname

    # preregistration
    prereg_dir = root / "workspace" / ".preregistration"
    if prereg_dir.exists():
        files = sorted(prereg_dir.glob("prereg_*.md"))
        if files:
            inv["preregistration"] = str(files[-1].relative_to(root))

    # state
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        inv["active_hypotheses"] = state.get("active_hypotheses") or []
        inv["project_name"] = state.get("project_name", "Research Project")
    except Exception:
        inv["project_name"] = "Research Project"

    # steps + figures
    ws = root / "workspace"
    if ws.exists():
        for d in sorted(ws.iterdir()):
            if d.is_dir() and re.match(r"^\d{2,3}_", d.name):
                inv["step_count"] += 1
        for f in (root / "synthesis" / "figures").glob("*.png") \
                if (root / "synthesis" / "figures").exists() else []:
            inv["figure_count"] += 1

    return inv


def redteam_scaffold(
    root: Path,
    *,
    persona: str = "methodological_skeptic",
) -> dict[str, Any]:
    """Write a reviewer-report scaffold for the AI to fill in.

    persona:
        ``methodological_skeptic`` (default) — focuses on assumptions,
            confounding, generalisability;
        ``statistical_referee`` — focuses on test choice, power,
            multiple comparisons;
        ``sympathetic_peer`` — focuses on whether the paper IS the
            best version of what it could be (constructive).
    """
    inv = _inventory(root)
    if not inv.get("paper"):
        return {
            "status": "error",
            "message": (
                "no synthesis/paper.md to review. Run tool_synthesize "
                "first."
            ),
        }

    reviews_dir = root / "workspace" / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = reviews_dir / f"redteam_{persona}_{ts}.md"

    persona_blurb = {
        "methodological_skeptic": (
            "Read this as if you are convinced the design has a subtle "
            "flaw. Your job is to find it. Be specific."
        ),
        "statistical_referee": (
            "Read this as if you serve on the journal's statistical "
            "review board. Your job is to find inferential errors."
        ),
        "sympathetic_peer": (
            "Read this as a colleague who wants the paper to be the "
            "strongest version of itself. Your comments should sharpen, "
            "not dismantle."
        ),
    }.get(persona,
          "Read this critically. Your job is to find what the authors missed.")

    lines: list[str] = []
    lines.append(f"# Red-team review — {inv.get('project_name')}")
    lines.append(f"*Persona: {persona}  ·  Generated: "
                 f"{datetime.now(timezone.utc).isoformat()}*")
    lines.append("")
    lines.append("> **Instructions for the reviewer model.** "
                 f"{persona_blurb}")
    lines.append("")
    lines.append("## 1. Reviewer summary (one paragraph)")
    lines.append("*Re-state the paper's argument in your own words. This "
                 "proves you read it. Include the headline finding, the "
                 "design, and the main analytic strategy.*")
    lines.append("")
    lines.append("## 2. Overall recommendation")
    lines.append("☐ Accept   ☐ Minor revision   ☐ Major revision   ☐ Reject")
    lines.append("")
    lines.append("*One sentence justifying the choice.*")
    lines.append("")
    lines.append("## 3. Major comments")
    lines.append("")
    # Pre-seed M1-M5 with explicit instructions per slot.
    for i in range(1, 6):
        lines.append(f"### M{i}. *(claim under challenge)*")
        lines.append("- **Paper quote**: \"…\" (line / section)")
        lines.append("- **Concern**: ")
        lines.append("- **Evidence**: which workspace output / external "
                     "reference grounds the concern")
        lines.append("- **Requested mitigation**: ")
        lines.append("")
    lines.append("## 4. Minor comments")
    lines.append("- m1. …")
    lines.append("- m2. …")
    lines.append("- m3. …")
    lines.append("")
    lines.append("## 5. Threats to validity")
    lines.append("")
    for dim, prompt in _VALIDITY_DIMENSIONS:
        lines.append(f"### {dim.capitalize()} validity")
        lines.append(f"*{prompt}*")
        lines.append("")
        lines.append("**Assessment**: ")
        lines.append("")
    lines.append("## 6. Devil's-advocate questions")
    lines.append("")
    for q in _DEVIL_QS:
        lines.append(f"- **{q}**")
        lines.append("  - Answer: ")
    lines.append("")
    lines.append("## 7. Inventory the reviewer consulted")
    lines.append("")
    for k, v in inv.items():
        if v in (None, [], 0):
            continue
        lines.append(f"- **{k}**: {v if not isinstance(v, list) else len(v)}")
    lines.append("")
    lines.append("---")
    lines.append("*Response-to-reviewers template:* "
                 "Copy each numbered comment into a new "
                 "`synthesis/response_to_reviewers.md`, paste the response "
                 "beneath each one with explicit line references to the "
                 "revised paper.")
    out.write_text("\n".join(lines) + "\n")

    return {
        "status": "success",
        "review_path": str(out.relative_to(root)),
        "persona": persona,
        "inventory": inv,
        "advice": (
            "Scaffold written. The reviewer model should now fill in each "
            "section using ONLY the inventory listed at the bottom — no "
            "external speculation. The headline output is the M1-M5 chain "
            "(concrete challenges grounded in the paper's own analysis)."
        ),
    }


def write_response_template(
    root: Path, review_path: str | None = None,
) -> dict[str, Any]:
    """Produce a response-to-reviewers template paired with the latest review.

    Format: alternating italic reviewer comments + roman responses with
    line refs into the revised paper.
    """
    if review_path is None:
        reviews = sorted(
            (root / "workspace" / "reviews").glob("redteam_*.md"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        ) if (root / "workspace" / "reviews").exists() else []
        if not reviews:
            return {"status": "error",
                    "message": "no redteam review found; run tool_redteam_review."}
        review_path = str(reviews[0].relative_to(root))

    review_text = (root / review_path).read_text()
    out = root / "synthesis" / "response_to_reviewers.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Extract M1-M5 / m1-m5 headings to paste as anchors.
    major = re.findall(r"^###\s+(M\d+\..*)$", review_text, flags=re.MULTILINE)
    minor = re.findall(r"^-\s+(m\d+\..*)$", review_text, flags=re.MULTILINE)

    lines = [
        "# Response to reviewers",
        "",
        f"*Responding to: `{review_path}`*",
        "",
        "We thank the reviewer for the careful read. Each comment is "
        "addressed below; revised passages are referenced by section "
        "and line number in the resubmitted manuscript.",
        "",
        "## Major comments",
        "",
    ]
    for m in major[:10] or ["M1. *(reviewer comment placeholder)*"]:
        lines.append(f"### {m}")
        lines.append("")
        lines.append(f"> *{m}*")
        lines.append("")
        lines.append("**Response.** _(How the manuscript was changed, with "
                     "section + line reference.)_")
        lines.append("")
    lines.append("## Minor comments")
    lines.append("")
    for m in minor[:20] or ["m1. *(reviewer comment placeholder)*"]:
        lines.append(f"- *{m}* — **Response**: …")
    lines.append("")
    out.write_text("\n".join(lines) + "\n")
    return {
        "status": "success",
        "response_path": str(out.relative_to(root)),
        "major_comments": len(major),
        "minor_comments": len(minor),
    }


__all__ = ["redteam_scaffold", "write_response_template"]
