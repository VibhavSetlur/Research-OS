"""Humanities domain detector.

Scans `inputs/` for signals that the project is humanities-shaped:
TEI files, XML manuscript markup, large prose text corpora with no
tabular data, archival metadata, theological / historical / literary
terminology. Returns a confidence score; called from
`tool_intake_autofill` when the core detector is uncertain.
"""
from __future__ import annotations

import re
from pathlib import Path

_HUMANITIES_TERMS = {
    # Manuscript / archival
    "manuscript", "codex", "folio", "incunabul", "marginalia",
    "palimpsest", "apparatus criticus", "scholia", "rubric",
    # Hermeneutic / theology / philosophy
    "hermeneutic", "exegesis", "patristic", "scholastic", "summa",
    "midrash", "talmud", "tafsir", "haggadah", "ecclesial",
    # Literary
    "intertextual", "stylometr", "narratolog", "philolog", "prosody",
    "verse", "stanza", "meter", "ekphrasis",
    # Historical methods
    "historiograph", "annales", "longue durée", "microhistory",
    # Translation / edition
    "critical edition", "diplomatic edition", "translator's note",
    "stemma codicum", "recensio", "collation",
    # DH
    "tei", "epub", "iiif", "transkribus", "voyant",
    "topic model", "stylometry",
}
_HUMANITIES_EXTENSIONS = {".tei", ".xml", ".tex", ".epub"}
_TABULAR_EXTENSIONS = {".csv", ".tsv", ".parquet", ".xlsx", ".feather"}


def detect_humanities(inputs_dir: Path) -> dict:
    """Inspect `inputs/` for humanities signals.

    Returns ``{"pack": "humanities", "confidence": float in [0,1], "signals": [...]}``.
    Confidence of 0.5+ is "probably humanities"; 0.7+ is strong.
    """
    if not inputs_dir.exists():
        return {"pack": "humanities", "confidence": 0.0, "signals": []}

    signals: list[str] = []
    tei_or_xml_count = 0
    tabular_count = 0
    prose_byte_total = 0
    terms_seen: set[str] = set()

    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in _HUMANITIES_EXTENSIONS:
            tei_or_xml_count += 1
            if suffix == ".tei" or _is_tei_xml(path):
                signals.append(f"TEI/XML manuscript markup: {path.name}")
        if suffix in _TABULAR_EXTENSIONS:
            tabular_count += 1
        # Prose-corpus heuristic: .txt / .md / .tex bodies
        if suffix in {".txt", ".md", ".tex"}:
            try:
                prose_byte_total += path.stat().st_size
                text = path.read_text(errors="ignore").lower()
                for term in _HUMANITIES_TERMS:
                    if term in text:
                        terms_seen.add(term)
            except Exception as exc:
                import logging
                logging.getLogger("research_os_humanities.detector").debug(
                    "skip %s: %s", path, exc
                )

    if tei_or_xml_count:
        signals.append(f"{tei_or_xml_count} TEI / XML file(s)")
    if terms_seen:
        signals.append(
            f"{len(terms_seen)} humanities-domain term(s): "
            + ", ".join(sorted(terms_seen)[:6])
        )
    if prose_byte_total and not tabular_count:
        signals.append(
            f"{prose_byte_total // 1024} KiB of prose / markup with NO tabular files"
        )
    if tabular_count:
        signals.append(f"{tabular_count} tabular file(s) (depresses confidence)")

    # Score: TEI files are the strongest positive; humanities terms add weight;
    # tabular files subtract.
    score = 0.0
    score += min(0.5, tei_or_xml_count * 0.25)
    score += min(0.4, len(terms_seen) * 0.08)
    if prose_byte_total and not tabular_count:
        score += 0.2
    score -= min(0.3, tabular_count * 0.1)
    score = max(0.0, min(1.0, score))
    return {
        "pack": "humanities",
        "confidence": round(score, 3),
        "signals": signals,
    }


def _is_tei_xml(path: Path) -> bool:
    """Cheap content sniff: does the first 4 KiB contain a <TEI> tag?"""
    try:
        head = path.read_text(errors="ignore")[:4096]
        return bool(re.search(r"<TEI\b|xmlns=\"http://www\.tei-c\.org", head))
    except Exception:
        return False
