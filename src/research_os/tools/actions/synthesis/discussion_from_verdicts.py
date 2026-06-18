"""Discussion-from-verdicts synthesizer.

Each step's ``literature/findings_vs_literature.md`` records per-claim
verdicts (AGREES | DISAGREES | EXTENDS | DEFERRED) plus a "Discussion
implication" block — without this synthesizer nothing piped those
implications into ``synthesis/discussion.md``, leaving the literature
loop write-only.

This module reads every step's verdict file, emits one Discussion
paragraph per non-AGREES verdict citing the contested literature, and
appends to ``synthesis/discussion.md`` under a clearly-marked
auto-generated section. The Discussion section can then BLOCK if any
non-AGREES verdict is missing its paragraph (enforced via
``audit_synthesis_discussion_coverage``).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.discussion_from_verdicts")


_CLAIM_BLOCK_RE = re.compile(
    r"^##\s+Claim:\s*(?P<claim>.+?)\n(?P<body>.+?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_VERDICT_RE = re.compile(
    r"\*\*Verdict:\*\*\s*(?P<verdict>AGREES|DISAGREES|EXTENDS|DEFERRED)",
    re.IGNORECASE,
)
_DISCUSSION_RE = re.compile(
    r"\*\*Discussion implication:\*\*\s*(?P<body>.+?)(?=\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_CITATION_RE = re.compile(
    r"\*\*(?:Citation|Cited|Source|Citation key):\*\*\s*(?P<body>.+?)(?=\n|\Z)",
    re.IGNORECASE,
)

_AUTO_SECTION_HEADER = "## Discussion — literature-verdict implications (auto-derived)"
_AUTO_SECTION_FOOTER = (
    "<!-- /ro:discussion_from_verdicts -->"
)
_AUTO_SECTION_TOP_MARKER = "<!-- ro:discussion_from_verdicts -->"


def _step_dirs(root: Path) -> list[Path]:
    from research_os.project_ops import discover_step_dirs
    return discover_step_dirs(root / "workspace", include_dead=False)


def _collect_verdicts(root: Path) -> list[dict[str, Any]]:
    """Return list of {step, claim, verdict, citation, discussion_implication}."""
    out: list[dict[str, Any]] = []
    for step_dir in _step_dirs(root):
        fvl = step_dir / "literature" / "findings_vs_literature.md"
        if not fvl.exists():
            continue
        try:
            text = fvl.read_text()
        except Exception:
            continue
        for m in _CLAIM_BLOCK_RE.finditer(text):
            claim = m.group("claim").strip()
            body = m.group("body")
            v = _VERDICT_RE.search(body)
            verdict = v.group("verdict").upper() if v else "UNSPECIFIED"
            d = _DISCUSSION_RE.search(body)
            disc = d.group("body").strip() if d else ""
            c = _CITATION_RE.search(body)
            cite = c.group("body").strip() if c else ""
            out.append({
                "step": step_dir.name,
                "claim": claim,
                "verdict": verdict,
                "citation": cite,
                "discussion_implication": disc,
            })
    return out


def discussion_coverage_audit(root: Path) -> dict[str, Any]:
    """Audit whether synthesis/discussion.md has a paragraph per non-AGREES verdict.

    Used by tool_audit_synthesis (called from writing_discussion's
    validate step). BLOCKS synthesis if any non-AGREES verdict has no
    corresponding text in synthesis/discussion.md.

    Override handling (override_discussion_coverage + override_rationale)
    is wired in ``server._handle_tool_discussion_coverage_audit`` — this
    function only computes coverage and returns the canonical result
    shape, leaving policy/log_override decisions to the handler.
    """
    try:
        records = _collect_verdicts(root)
        non_agrees = [r for r in records if r["verdict"] not in {"AGREES", "DEFERRED", "UNSPECIFIED"}]
        if not non_agrees:
            return {
                "status": "success",
                "non_agrees_count": 0,
                "covered_count": 0,
                "uncovered": [],
                "message": "No non-AGREES verdicts to cover.",
            }

        disc_path = root / "synthesis" / "discussion.md"
        disc_text = ""
        if disc_path.exists():
            try:
                disc_text = disc_path.read_text().lower()
            except Exception:
                disc_text = ""

        uncovered: list[dict[str, Any]] = []
        covered: list[dict[str, Any]] = []
        for r in non_agrees:
            # Word-boundary regex match. A plain substring `in
            # disc_text` would over-credit stem-prefix words ('expr'
            # hits 'expression'). Also: when a claim has <=2 keywords,
            # require ALL of them — `max(2, ...)` would make short
            # claims like "BMI rises" or "Cox PH fits" unprovably
            # uncovered.
            claim_words = [
                w.lower() for w in re.findall(r"[A-Za-z]{4,}", r["claim"])
            ][:6]
            if not claim_words:
                uncovered.append(r)
                continue
            hit_count = sum(
                1
                for w in claim_words
                if re.search(rf"\b{re.escape(w)}\b", disc_text)
            )
            if len(claim_words) <= 2:
                threshold = len(claim_words)
            else:
                threshold = max(2, len(claim_words) // 2)
            if hit_count >= threshold:
                covered.append(r)
            else:
                uncovered.append(r)

        status = "error" if uncovered else "success"
        blockers: list[str] = []
        if uncovered:
            blockers.append(
                f"{len(uncovered)} non-AGREES verdict(s) lack a Discussion "
                f"paragraph. Run tool_writing_discussion_from_verdicts to "
                "auto-draft, or write them by hand."
            )
        return {
            "status": status,
            "non_agrees_count": len(non_agrees),
            "covered_count": len(covered),
            "uncovered_count": len(uncovered),
            "uncovered": [
                {"step": u["step"], "claim": u["claim"][:120], "verdict": u["verdict"]}
                for u in uncovered[:20]
            ],
            "blockers": blockers,
        }
    except Exception as e:
        logger.exception("discussion_coverage_audit failed")
        return {"status": "error", "message": str(e)}


def emit_discussion_paragraphs(root: Path) -> dict[str, Any]:
    """Append one paragraph per non-AGREES verdict to synthesis/discussion.md.

    Idempotent — uses HTML-comment markers to find and replace the
    previously-generated section. Researcher's hand-written content
    outside the markers is preserved untouched.
    """
    try:
        records = _collect_verdicts(root)
        non_agrees = [
            r for r in records
            if r["verdict"] in {"DISAGREES", "EXTENDS"}
            and r["discussion_implication"]
        ]
        if not non_agrees:
            return {
                "status": "success",
                "appended_paragraphs": 0,
                "message": "No DISAGREES/EXTENDS verdicts with implications to append.",
            }

        disc_path = root / "synthesis" / "discussion.md"
        disc_path.parent.mkdir(parents=True, exist_ok=True)
        original = disc_path.read_text() if disc_path.exists() else ""

        paragraphs: list[str] = [
            _AUTO_SECTION_TOP_MARKER,
            _AUTO_SECTION_HEADER,
            "",
            (
                "_The following paragraphs were auto-drafted from per-step "
                "`literature/findings_vs_literature.md` verdicts. Each "
                "addresses a finding that DISAGREES with or EXTENDS prior "
                "literature. Edit in-place — re-running the generator "
                "preserves your edits within the markers only if the "
                "claim is unchanged._"
            ),
            "",
        ]
        for r in non_agrees:
            cite_block = f" ({r['citation']})" if r['citation'] else ""
            paragraphs.append(
                f"**Step {r['step']} — {r['verdict']}.** "
                f"Our finding that *{r['claim']}* engages with prior "
                f"literature{cite_block}. "
                f"{r['discussion_implication']}"
            )
            paragraphs.append("")
        paragraphs.append(_AUTO_SECTION_FOOTER)

        body = "\n".join(paragraphs).strip() + "\n"

        if _AUTO_SECTION_TOP_MARKER in original and _AUTO_SECTION_FOOTER in original:
            pattern = re.compile(
                re.escape(_AUTO_SECTION_TOP_MARKER)
                + r".*?"
                + re.escape(_AUTO_SECTION_FOOTER),
                re.DOTALL,
            )
            new_text = pattern.sub(body.strip(), original)
        else:
            sep = "\n\n" if (original and not original.endswith("\n\n")) else ""
            new_text = (original or "") + sep + body

        disc_path.write_text(new_text)
        return {
            "status": "success",
            "appended_paragraphs": len(non_agrees),
            "discussion_path": str(disc_path.relative_to(root)),
            "verdicts_covered": [
                {"step": r["step"], "verdict": r["verdict"], "claim": r["claim"][:100]}
                for r in non_agrees
            ],
        }
    except Exception as e:
        logger.exception("emit_discussion_paragraphs failed")
        return {"status": "error", "message": str(e)}
