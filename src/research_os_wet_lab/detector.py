"""Wet-lab domain detector."""
from __future__ import annotations

import re
from pathlib import Path

_INSTRUMENT_EXTS = {".fcs", ".qpcr", ".czi", ".raw", ".tiff", ".tif",
                    ".lsm", ".nd2", ".oib", ".oif", ".lif", ".vsi",
                    ".mzml", ".mzxml", ".d", ".wiff"}
_CAT_PATTERN = re.compile(r"\b(?:cat|catalog)[\s.#:-]*([A-Z0-9-]{4,})", re.IGNORECASE)
_WET_LAB_TERMS = {
    "facs", "flow cytometry", "qpcr", "rt-pcr", "elisa",
    "western blot", "immunoprecipitation", "co-ip",
    "plate map", "plate layout", "96-well", "384-well",
    "antibody", "primer", "vector", "plasmid", "transfection",
    "knock-out", "knockout", "knock-in", "knockin", "crispr",
    "sop", "standard operating procedure", "reagent",
    "coa", "certificate of analysis", "biosafety", "ibc",
    "cell line", "passage number", "mycoplasma",
}


def detect_wet_lab(inputs_dir: Path) -> dict:
    if not inputs_dir.exists():
        return {"pack": "wet_lab", "confidence": 0.0, "signals": []}
    signals: list[str] = []
    instrument_files = 0
    cat_hits = 0
    terms_seen: set[str] = set()
    has_protocols_dir = (inputs_dir / "protocols").exists()
    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in _INSTRUMENT_EXTS:
            instrument_files += 1
        if ext in {".md", ".txt", ".csv", ".yaml", ".yml"}:
            try:
                text = path.read_text(errors="ignore")
            except Exception as exc:
                import logging
                logging.getLogger("research_os_wet_lab.detector").debug(
                    "skip %s: %s", path, exc
                )
                continue
            for term in _WET_LAB_TERMS:
                if term in text.lower():
                    terms_seen.add(term)
            cat_hits += len(_CAT_PATTERN.findall(text))
    if instrument_files:
        signals.append(f"{instrument_files} instrument-output file(s)")
    if has_protocols_dir:
        signals.append("inputs/protocols/ subdirectory present")
    if cat_hits:
        signals.append(f"{cat_hits} catalog-number reference(s)")
    if terms_seen:
        signals.append(
            f"{len(terms_seen)} wet-lab term(s): "
            + ", ".join(sorted(terms_seen)[:6])
        )
    score = 0.0
    score += min(0.5, instrument_files * 0.25)
    score += 0.2 if has_protocols_dir else 0.0
    score += min(0.25, cat_hits * 0.08)
    score += min(0.35, len(terms_seen) * 0.08)
    score = max(0.0, min(1.0, score))
    return {
        "pack": "wet_lab",
        "confidence": round(score, 3),
        "signals": signals,
    }
