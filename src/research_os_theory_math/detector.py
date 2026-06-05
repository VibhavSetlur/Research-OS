"""Theory/Math domain detector."""
from __future__ import annotations

import re
from pathlib import Path

_THEORY_EXTS = {".lean", ".v", ".agda", ".thy", ".ott"}
_LATEX_PROOF_RE = re.compile(
    r"\\begin\{(proof|theorem|lemma|corollary|proposition|definition)\}",
    re.IGNORECASE,
)
_MATHLIB_RE = re.compile(r"\bMathlib\b|^\s*import\s+Mathlib", re.MULTILINE)
_THEORY_TERMS = {
    "theorem", "lemma", "proof", "corollary", "proposition",
    "axiom", "qed", "induction", "contradiction", "contrapositive",
    "isomorphism", "homomorphism", "functor", "monad", "category",
    "smash product", "cohomology", "manifold", "lie algebra",
    "set theory", "category theory", "type theory",
}


def detect_theory_math(inputs_dir: Path) -> dict:
    if not inputs_dir.exists():
        return {"pack": "theory_math", "confidence": 0.0, "signals": []}
    signals: list[str] = []
    proof_files = 0
    latex_proof_files = 0
    mathlib_hits = 0
    terms_seen: set[str] = set()
    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in _THEORY_EXTS:
            proof_files += 1
            signals.append(f"formal-proof file: {path.name}")
        if ext in {".tex", ".bib"}:
            try:
                text = path.read_text(errors="ignore")
            except Exception as exc:
                import logging
                logging.getLogger("research_os_theory_math.detector").debug(
                    "skip %s: %s", path, exc
                )
                continue
            if _LATEX_PROOF_RE.search(text):
                latex_proof_files += 1
            if _MATHLIB_RE.search(text):
                mathlib_hits += 1
        if ext in {".md", ".tex", ".txt"}:
            try:
                text = path.read_text(errors="ignore").lower()
            except Exception:
                continue
            for term in _THEORY_TERMS:
                if term in text:
                    terms_seen.add(term)
    if latex_proof_files:
        signals.append(f"{latex_proof_files} LaTeX file(s) with proof / theorem envs")
    if mathlib_hits:
        signals.append("Mathlib references present")
    if terms_seen:
        signals.append(
            f"{len(terms_seen)} theory term(s): "
            + ", ".join(sorted(terms_seen)[:6])
        )
    score = 0.0
    score += min(0.6, proof_files * 0.3)
    score += min(0.35, latex_proof_files * 0.18)
    score += min(0.25, mathlib_hits * 0.2)
    score += min(0.3, len(terms_seen) * 0.07)
    score = max(0.0, min(1.0, score))
    return {
        "pack": "theory_math",
        "confidence": round(score, 3),
        "signals": signals,
    }
