"""Qualitative-research domain detector.

Scans `inputs/` for interview-transcript patterns, qualitative-tool
metadata (NVivo / Atlas.ti / MAXQDA / Dedoose project files), IRB
artefacts, and small-N demographic data.
"""
from __future__ import annotations

import re
from pathlib import Path

_INTERVIEW_HINT_EXTS = {".vtt", ".otr", ".docx", ".rtf", ".txt", ".md"}
_QUAL_TOOL_HINTS = {
    "nvivo", "atlas.ti", "atlas_ti", "maxqda", "dedoose",
    "transana", "quirkos", "taguette",
}
_IRB_PATTERNS = re.compile(
    r"\b(irb|institutional review board|informed consent|protocol \#)\b",
    re.IGNORECASE,
)
_SPEAKER_TURN_RE = re.compile(
    # Single-letter speaker labels (I/P/R) must NOT carry the colon here —
    # the trailing [:.)] consumes it. Including it (i:|p:|r:) made the
    # pattern require a *second* delimiter, so "I: ...", "R: ..." (the most
    # common transcript convention) never matched.
    r"^\s*(?:p\d+|participant|interviewer|i|p|r)\s*[:\.\)]\s*\S",
    re.IGNORECASE | re.MULTILINE,
)


def detect_qualitative(inputs_dir: Path) -> dict:
    """Inspect `inputs/` for qualitative signals."""
    if not inputs_dir.exists():
        return {"pack": "qualitative", "confidence": 0.0, "signals": []}

    signals: list[str] = []
    interview_files = 0
    qual_tool_files = 0
    irb_hits = 0
    small_n_demographics = 0
    speaker_turn_files = 0

    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        name = path.name.lower()
        if ext in _INTERVIEW_HINT_EXTS:
            interview_files += 1
        if any(tool in name for tool in _QUAL_TOOL_HINTS):
            qual_tool_files += 1
            signals.append(f"qualitative-tool artefact: {path.name}")
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        if _IRB_PATTERNS.search(text):
            irb_hits += 1
        # Speaker-turn pattern: lines like "P1:" or "Interviewer:" or "P:"
        # A 12-person study often ships short transcripts (3–4 turns each),
        # so the threshold is ≥3 matches; a single transcript with that
        # many speaker turns is already a strong qualitative signal.
        if ext in {".txt", ".md", ".docx", ".vtt", ".rtf"}:
            matches = _SPEAKER_TURN_RE.findall(text)
            if len(matches) >= 3:
                speaker_turn_files += 1
                signals.append(
                    f"speaker-turn pattern ({len(matches)} turns) in {path.name}"
                )
        # Small-N demographic CSV
        if ext == ".csv":
            try:
                rows = sum(1 for _ in text.splitlines())
                if 5 <= rows <= 100:
                    head = text.splitlines()[0].lower() if text else ""
                    if any(
                        h in head
                        for h in ("participant", "age", "gender", "ethnicity",
                                  "occupation", "consent")
                    ):
                        small_n_demographics += 1
                        signals.append(
                            f"small-N (N={rows}) demographic CSV: {path.name}"
                        )
            except Exception as exc:
                import logging
                logging.getLogger("research_os_qualitative.detector").debug(
                    "skip %s: %s", path, exc
                )

    if interview_files:
        signals.append(f"{interview_files} interview-hint file(s)")
    if irb_hits:
        signals.append(f"IRB / informed-consent references in {irb_hits} file(s)")

    # Speaker-turn pattern is the strongest single signal; one transcript
    # with 5+ turns is enough to flag the project as probably qualitative.
    score = 0.0
    score += min(0.6, speaker_turn_files * 0.35)
    score += min(0.3, interview_files * 0.1)
    score += min(0.25, qual_tool_files * 0.15)
    score += min(0.2, irb_hits * 0.1)
    score += min(0.15, small_n_demographics * 0.1)
    score = max(0.0, min(1.0, score))
    return {
        "pack": "qualitative",
        "confidence": round(score, 3),
        "signals": signals,
    }
