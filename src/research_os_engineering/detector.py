"""Engineering domain detector."""
from __future__ import annotations

import re
from pathlib import Path

_CAD_EXTS = {".stp", ".step", ".iges", ".igs", ".sldprt", ".sldasm",
             ".dwg", ".dxf", ".f3d", ".prt", ".asm"}
_SIM_EXTS = {".out", ".odb", ".raw", ".cir", ".spi", ".sp"}
_CTRL_EXTS = {".plc", ".st", ".scl", ".gsd"}
_REQ_RE = re.compile(r"\b(?:SRS|SDD|REQ|FR|NFR|UC|TC)[-_]?\d{2,5}\b")
_ENG_TERMS = {
    "fmea", "fault tree", "failure mode", "rpn", "risk priority number",
    "requirements traceability", "srs", "sdd", "verification + validation",
    "v&v", "build test fix", "five whys", "5 whys", "fishbone",
    "ishikawa", "root cause", "test case", "regression test",
    "design iteration", "design review", "modbus", "scada", "plc",
    "control system", "embedded system",
}


def detect_engineering(inputs_dir: Path) -> dict:
    if not inputs_dir.exists():
        return {"pack": "engineering", "confidence": 0.0, "signals": []}
    signals: list[str] = []
    cad_files = 0
    sim_files = 0
    ctrl_files = 0
    req_hits = 0
    terms_seen: set[str] = set()
    for path in inputs_dir.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in _CAD_EXTS:
            cad_files += 1
        if ext in _SIM_EXTS:
            sim_files += 1
        if ext in _CTRL_EXTS:
            ctrl_files += 1
        if ext in {".md", ".txt", ".csv", ".yaml", ".yml"}:
            try:
                text = path.read_text(errors="ignore")
            except Exception as exc:
                import logging
                logging.getLogger("research_os_engineering.detector").debug(
                    "skip %s: %s", path, exc
                )
                continue
            req_hits += len(_REQ_RE.findall(text))
            for term in _ENG_TERMS:
                if term in text.lower():
                    terms_seen.add(term)
    if cad_files:
        signals.append(f"{cad_files} CAD file(s)")
    if sim_files:
        signals.append(f"{sim_files} simulation-output file(s)")
    if ctrl_files:
        signals.append(f"{ctrl_files} control-system file(s)")
    if req_hits:
        signals.append(f"{req_hits} requirement-ID reference(s) (SRS / REQ / FR / TC)")
    if terms_seen:
        signals.append(
            f"{len(terms_seen)} engineering term(s): "
            + ", ".join(sorted(terms_seen)[:6])
        )
    score = 0.0
    score += min(0.45, cad_files * 0.22)
    score += min(0.25, sim_files * 0.15)
    score += min(0.2, ctrl_files * 0.2)
    score += min(0.3, req_hits * 0.05)
    score += min(0.3, len(terms_seen) * 0.07)
    score = max(0.0, min(1.0, score))
    return {
        "pack": "engineering",
        "confidence": round(score, 3),
        "signals": signals,
    }
