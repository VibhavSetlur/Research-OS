"""Cross-step coherence audit (v1.5.0 — Theme 11).

Verifies every paragraph in ``synthesis/paper.md`` maps back to a step's
``conclusions.md`` via key-phrase overlap. Flags orphan paragraphs —
text that was likely carried over from a prior chat about a step that
was later abandoned, or text invented during synthesis without grounding.

Uses a deterministic lightweight matcher (no embedding model):
  - tokenise each paragraph into noun-phrase-ish 3-5 word shingles
  - score per-paragraph by best Jaccard overlap against any step's
    conclusions.md text
  - paragraphs scoring < 0.10 with no step support are flagged orphan
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.audit.coherence")


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


def _normalise(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _shingles(words: list[str], k: int = 3) -> set[str]:
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


_NUMBERED_LIST_RE = re.compile(r"^\d+\.\s")
_BULLET_LIST_RE = re.compile(r"^[-*+]\s")
_CODE_FENCE_RE = re.compile(r"^\s*```")


def _paragraphs(text: str) -> list[tuple[str, str]]:
    """Return (section, paragraph) pairs. Section is the most-recent ## heading.

    Filters: ATX headings, blank lines, image refs, bullet/numbered-list
    items (any digit prefix, not just '1.'), table rows, and fenced code
    block content (tracks in_code state — v1.5.0 stress audit caught the
    bug where only the fence line was skipped while body became orphans).
    """
    out: list[tuple[str, str]] = []
    current_section = "preamble"
    para_lines: list[str] = []
    in_code = False

    def _flush():
        nonlocal para_lines
        if para_lines:
            joined = "\n".join(para_lines).strip()
            if joined and len(joined) > 30:
                out.append((current_section, joined))
            para_lines = []

    for line in text.splitlines():
        if _CODE_FENCE_RE.match(line):
            _flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith("## "):
            _flush()
            current_section = line[3:].strip().lower()
            continue
        if line.startswith("#"):
            _flush()
            continue
        if not line.strip():
            _flush()
            continue
        if line.startswith("!["):
            continue
        stripped = line.lstrip()
        if (
            _BULLET_LIST_RE.match(stripped)
            or _NUMBERED_LIST_RE.match(stripped)
            or stripped.startswith("|")
        ):
            continue
        para_lines.append(line)
    _flush()
    return out


def audit_coherence(root: Path, paper_path: str = "synthesis/paper.md") -> dict[str, Any]:
    """Audit cross-step coherence in the paper."""
    try:
        p = root / paper_path
        if not p.exists() or not p.is_file():
            return {
                "status": "error",
                "message": f"Paper not found: {paper_path}",
            }

        text = p.read_text()
        paragraphs = _paragraphs(text)

        step_corpus: dict[str, set[str]] = {}
        workspace = root / "workspace"
        if workspace.is_dir():
            for step_dir in sorted(workspace.iterdir()):
                if not (
                    step_dir.is_dir()
                    and step_dir.name[:2].isdigit()
                    and not step_dir.name.endswith("__DEAD_END")
                ):
                    continue
                conc = step_dir / "conclusions.md"
                if not conc.exists():
                    continue
                try:
                    body = conc.read_text()
                except Exception:
                    continue
                step_corpus[step_dir.name] = _shingles(_normalise(body))

        orphan: list[dict[str, Any]] = []
        matched: list[dict[str, Any]] = []
        per_paragraph: list[dict[str, Any]] = []

        for section, para in paragraphs:
            words = _normalise(para)
            if len(words) < 5:
                continue
            p_sh = _shingles(words)
            if not p_sh:
                continue
            best_step = ""
            best_score = 0.0
            for step, s_sh in step_corpus.items():
                if not s_sh:
                    continue
                inter = len(p_sh & s_sh)
                union = len(p_sh | s_sh)
                score = inter / max(1, union)
                if score > best_score:
                    best_score = score
                    best_step = step
            entry = {
                "section": section,
                "preview": para[:120].replace("\n", " ") + ("..." if len(para) > 120 else ""),
                "best_step": best_step,
                "score": round(best_score, 3),
            }
            per_paragraph.append(entry)
            if best_score < 0.05 and section in {
                "results", "discussion", "introduction", "conclusion", "conclusions",
            }:
                orphan.append(entry)
            else:
                matched.append(entry)

        coverage = len(matched) / max(1, len(per_paragraph))

        log_path = root / "workspace" / "logs" / "coherence_audit.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Cross-step coherence audit",
            "",
            f"- Paper: `{paper_path}`",
            f"- Steps with conclusions: {len(step_corpus)}",
            f"- Paragraphs scored: {len(per_paragraph)}",
            f"- Matched (score ≥ 0.05): {len(matched)}",
            f"- Orphan (score < 0.05 in Results/Discussion/Intro/Conclusion): {len(orphan)}",
            f"- Coverage: {coverage:.2f}",
            "",
            "## Orphan paragraphs",
            "",
        ]
        if orphan:
            for o in orphan[:30]:
                lines.append(
                    f"- `{o['section']}` — score {o['score']} — "
                    f"\"{o['preview']}\""
                )
        else:
            lines.append("_None_")
        log_path.write_text("\n".join(lines) + "\n")

        status = "warning" if orphan else "success"
        return {
            "status": status,
            "paper_path": paper_path,
            "paragraphs_scored": len(per_paragraph),
            "orphan_count": len(orphan),
            "coverage": round(coverage, 3),
            "orphan_paragraphs": orphan[:30],
            "step_count": len(step_corpus),
            "log_path": str(log_path.relative_to(root)),
        }
    except Exception as e:
        logger.exception("audit_coherence failed")
        return {"status": "error", "message": str(e)}
