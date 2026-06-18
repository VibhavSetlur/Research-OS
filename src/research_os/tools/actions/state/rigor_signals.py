"""Rigor signal scan + adaptive gate strictness.

The MCP can read project files and infer rigor signals — methods.md
substantiveness, citation density in prose, version-control state,
preregistration artifacts, well-commented scripts, prior step_summary
quality. The score (0-100) lets audits scale their strictness:

  trust_score >= 75  → "light"   (most gates become notes)
  trust_score >= 50  → "normal"  (today's behavior)
  trust_score <  50  → "strict"  (every gate full enforcement)

Researcher can override via ``researcher_config.gate_strictness:
light | normal | strict | auto`` — ``auto`` follows trust_score.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.rigor_signals")


def _score_methods_md(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-20 based on methods.md substantiveness."""
    methods_path = root / "workspace" / "methods.md"
    if not methods_path.exists():
        return 0, {"present": False}
    text = methods_path.read_text()
    cleaned = re.sub(r"^#.*$", "", text, flags=re.MULTILINE).strip()
    chars = len(cleaned)
    bullet_count = len(re.findall(r"^[-*]\s+", text, flags=re.MULTILINE))
    citation_hits = len(re.findall(r"\[@[^\]]+\]|\([A-Z][a-z]+\s+\d{4}\)", text))
    score = 0
    if chars >= 200:
        score += 5
    if chars >= 800:
        score += 5
    if bullet_count >= 5:
        score += 5
    if citation_hits >= 3:
        score += 5
    return min(20, score), {
        "present": True,
        "chars": chars,
        "bullet_count": bullet_count,
        "citation_hits": citation_hits,
    }


def _score_citations(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-20 based on citation density in any prose."""
    citations_md = root / "workspace" / "citations.md"
    score = 0
    info: dict[str, Any] = {}
    if citations_md.exists():
        text = citations_md.read_text()
        entry_count = len(re.findall(r"^\s*-\s+\S", text, flags=re.MULTILINE))
        score += min(10, entry_count // 2)
        info["citations_md_entries"] = entry_count
    pdf_dir = root / "inputs" / "literature"
    # Count only magic-validated PDFs so a folder of renamed error pages
    # can't inflate the grounding-richness signal.
    from research_os.tools.actions.search.literature import count_valid_pdfs
    pdf_count = count_valid_pdfs(pdf_dir)
    info["project_pdf_count"] = pdf_count
    score += min(10, pdf_count)
    return min(20, score), info


def _score_version_control(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-15 based on .git presence + commit count."""
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return 0, {"git_initialised": False}
    score = 10
    head = git_dir / "HEAD"
    if head.exists():
        score = 15
    return score, {"git_initialised": True}


def _score_preregistration(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-10 based on preregistration artifact presence."""
    candidates = [
        "preregistration.md",
        "preregistration.yaml",
        "PROTOCOL.md",
        "study_protocol.md",
    ]
    for c in candidates:
        if (root / c).exists() or (root / "workspace" / c).exists():
            return 10, {"preregistration_file": c}
    if (root / "workspace" / "preregistration").is_dir():
        return 10, {"preregistration_dir": "workspace/preregistration"}
    return 0, {"preregistration_file": None}


def _score_scripts(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-15 based on script comment density across workspace."""
    workspace = root / "workspace"
    if not workspace.is_dir():
        return 0, {"scripts_scanned": 0}
    total_lines = 0
    comment_lines = 0
    scripts_scanned = 0
    from research_os.project_ops import discover_step_dirs
    for step_dir in discover_step_dirs(workspace):
        scripts = step_dir / "scripts"
        if not scripts.is_dir():
            continue
        for script in scripts.iterdir():
            if script.suffix.lower() not in {".py", ".r", ".jl", ".sh"}:
                continue
            try:
                text = script.read_text()
            except Exception:
                continue
            scripts_scanned += 1
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                total_lines += 1
                if stripped.startswith(("#", "//", "--")):
                    comment_lines += 1
    if total_lines == 0:
        return 0, {"scripts_scanned": scripts_scanned}
    ratio = comment_lines / total_lines
    info = {
        "scripts_scanned": scripts_scanned,
        "comment_ratio": round(ratio, 3),
        "total_code_lines": total_lines,
    }
    if ratio >= 0.20:
        return 15, info
    if ratio >= 0.10:
        return 10, info
    if ratio >= 0.05:
        return 5, info
    return 0, info


def _score_prior_step_summaries(root: Path) -> tuple[int, dict[str, Any]]:
    """Score 0-15 on the quality of prior steps' conclusions.md.

    step_summary.yaml was retired in 3.2; conclusions.md is the source of
    truth. A step counts as *substantive* when its Findings or Decision
    section has real content (≥50 non-stub chars) and as *grounded* when it
    carries a literature/findings_vs_literature.md verdict file.
    """
    import re as _re

    workspace = root / "workspace"
    if not workspace.is_dir():
        return 0, {"summaries_scanned": 0}

    def _section(text: str, header: str) -> str:
        m = _re.search(
            rf"^##\s+{_re.escape(header)}\s*\n(.*?)(?=^##\s|\Z)",
            text, _re.MULTILINE | _re.DOTALL,
        )
        body = (m.group(1).strip() if m else "")
        # A stub section (only an italic placeholder) doesn't count.
        if body.startswith("*(") or body.startswith("_("):
            return ""
        return body

    summaries = 0
    substantive = 0
    has_literature = 0
    from research_os.project_ops import discover_step_dirs
    for step_dir in discover_step_dirs(workspace):
        conc = step_dir / "conclusions.md"
        if not conc.exists():
            continue
        summaries += 1
        try:
            txt = conc.read_text()
        except OSError:
            continue
        if len(_section(txt, "Findings")) >= 50 or len(_section(txt, "Decision")) >= 50:
            substantive += 1
        if (step_dir / "literature" / "findings_vs_literature.md").exists():
            has_literature += 1
    if summaries == 0:
        return 0, {"summaries_scanned": 0}
    sub_ratio = substantive / summaries
    lit_ratio = has_literature / summaries
    score = int(min(10, 10 * sub_ratio)) + int(min(5, 5 * lit_ratio))
    return min(15, score), {
        "summaries_scanned": summaries,
        "substantive_ratio": round(sub_ratio, 3),
        "with_literature_ratio": round(lit_ratio, 3),
    }


def rigor_signals_scan(root: Path) -> dict[str, Any]:
    """Compute trust_score (0-100) + per-signal breakdown."""
    try:
        m_score, m_info = _score_methods_md(root)
        c_score, c_info = _score_citations(root)
        g_score, g_info = _score_version_control(root)
        p_score, p_info = _score_preregistration(root)
        s_score, s_info = _score_scripts(root)
        ss_score, ss_info = _score_prior_step_summaries(root)
        total = m_score + c_score + g_score + p_score + s_score + ss_score
        if total >= 75:
            recommended_strictness = "light"
        elif total >= 50:
            recommended_strictness = "normal"
        else:
            recommended_strictness = "strict"
        return {
            "status": "success",
            "trust_score": total,
            "max_possible": 100,
            "recommended_strictness": recommended_strictness,
            "signals": [
                {"signal": "methods.md substantiveness", "score": m_score, "max": 20, "info": m_info},
                {"signal": "citation density + PDFs", "score": c_score, "max": 20, "info": c_info},
                {"signal": "version control", "score": g_score, "max": 15, "info": g_info},
                {"signal": "preregistration", "score": p_score, "max": 10, "info": p_info},
                {"signal": "script comments", "score": s_score, "max": 15, "info": s_info},
                {"signal": "prior step summaries", "score": ss_score, "max": 15, "info": ss_info},
            ],
        }
    except Exception as e:
        logger.exception("rigor_signals_scan failed")
        return {"status": "error", "message": str(e)}


def resolve_gate_strictness(root: Path) -> dict[str, Any]:
    """Resolve gate_strictness from researcher_config + trust_score.

    Reads ``inputs/researcher_config.yaml`` (wizard-canonical path); falls back
    to a legacy ``researcher_config.yaml`` at the project root for older
    projects that pre-date the wizard's move under ``inputs/``.

    Resolution order:
      1. explicit ``gate_strictness`` (light/normal/strict) → ``source=config``
      2. ``project_tier`` is set to a non-default value (throwaway/sketch) →
         tier mapping wins over ``auto`` so the documented cross-field
         interaction (throwaway → light, sketch → normal) actually fires
         even when ``gate_strictness`` is left at the ``auto`` default.
         ``source=project_tier``
      3. ``gate_strictness: auto`` or unset → trust-score auto-pick
         (``source=auto|default``)

    Returns ``{"resolved": "light|normal|strict", "source": "config|project_tier|auto|default"}``.
    """
    try:
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if not cfg_path.exists():
            legacy = root / "researcher_config.yaml"
            if legacy.exists():
                cfg_path = legacy
        config_value: str | None = None
        tier_value: str | None = None
        if cfg_path.exists():
            try:
                import yaml  # type: ignore
                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                config_value = cfg.get("gate_strictness")
                tier_value = cfg.get("project_tier")
            except Exception:
                config_value = None
                tier_value = None

        if config_value in {"light", "normal", "strict"}:
            return {"resolved": config_value, "source": "config"}
        tier_map = {
            "throwaway": "light",
            "sketch": "normal",
            "production": "strict",
        }
        # The documented cross-field interaction (templates/researcher_config.yaml)
        # says project_tier sets the *default* gate_strictness. Honour it when
        # gate_strictness is unset OR left at the "auto" default and the tier is
        # NOT "production" (production = strict = same as auto's strict floor,
        # so let auto's trust-score scan refine it).
        if isinstance(tier_value, str) and tier_value in tier_map:
            if config_value is None or (
                config_value == "auto" and tier_value != "production"
            ):
                return {
                    "resolved": tier_map[tier_value],
                    "source": "project_tier",
                    "project_tier": tier_value,
                }
        if config_value == "auto" or config_value is None:
            scan = rigor_signals_scan(root)
            if scan.get("status") == "success":
                return {
                    "resolved": scan["recommended_strictness"],
                    "source": "auto" if config_value == "auto" else "default",
                    "trust_score": scan["trust_score"],
                }
        return {"resolved": "normal", "source": "default"}
    except Exception as e:
        logger.exception("resolve_gate_strictness failed")
        return {"resolved": "normal", "source": "error", "error": str(e)}
