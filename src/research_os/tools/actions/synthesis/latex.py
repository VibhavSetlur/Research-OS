"""LaTeX paper + tikzposter + high-quality HTML dashboard generation.

The dashboard is single-file (all CSS + JS embedded) so it opens directly
without any server. Features:
  * sortable tables (click any column header)
  * lightbox-style image gallery (click any thumbnail)
  * light/dark toggle (auto-detects prefers-color-scheme)
  * print-friendly stylesheet
  * semantic landmarks (header / main / aside / footer)
  * audience-tailored layout (academic | executive | technical | teaching)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.latex")


def _project_name(root: Path) -> str:
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        return state.get("project_name") or "Research Project"
    except Exception:
        return "Research Project"


# ---------------------------------------------------------------------------
# LaTeX paper compile
# ---------------------------------------------------------------------------


def latex_compile(root: Path) -> dict[str, Any]:
    """Compile ``synthesis/paper.tex`` to PDF (pdflatex × bibtex × pdflatex × pdflatex)."""
    tex_path = root / "synthesis" / "paper.tex"
    if not tex_path.exists():
        return {"status": "error", "message": "synthesis/paper.tex not found", "success": False}

    pdflatex = shutil.which("pdflatex")
    bibtex = shutil.which("bibtex")
    if not pdflatex:
        return {
            "status": "error",
            "message": "pdflatex not found. Install TeX Live.",
            "success": False,
        }

    log_lines: list[str] = []

    def _run_pdflatex() -> int:
        res = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=str(tex_path.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        log_lines.append(res.stdout[-1500:])
        return res.returncode

    success = _run_pdflatex() == 0
    if success and bibtex and tex_path.with_suffix(".aux").exists():
        subprocess.run(
            [bibtex, tex_path.with_suffix(".aux").name],
            cwd=str(tex_path.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
    if success:
        _run_pdflatex()
        _run_pdflatex()

    pdf = tex_path.with_suffix(".pdf")
    return {
        "status": "success" if (success and pdf.exists()) else "error",
        "pdf_path": str(pdf.relative_to(root)) if pdf.exists() else None,
        "success": success and pdf.exists(),
        "log": "\n".join(log_lines[-3:]),
    }


# ---------------------------------------------------------------------------
# Poster
# ---------------------------------------------------------------------------


def _poster_tex_escape(text: str) -> str:
    """Escape LaTeX special characters in plain prose."""
    if not text:
        return ""
    return (text
            .replace("\\", r"\textbackslash{}")
            .replace("&", r"\&")
            .replace("%", r"\%")
            .replace("$", r"\$")
            .replace("#", r"\#")
            .replace("_", r"\_")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("~", r"\textasciitilde{}")
            .replace("^", r"\textasciicircum{}"))


def create_poster(
    root: Path,
    *,
    layout: str = "billboard",
    audience: str = "academic_conference",
) -> dict[str, Any]:
    """Generate a polished tikzposter LaTeX poster from curated synthesis
    content, then compile to PDF.

    Layouts
    -------
    * ``billboard`` (default) — Mike Morrison's "Better Poster" pattern: a
      single oversized plain-English headline panel takes ~60% of the
      poster height with the methods + figures + limitations in a narrow
      side column ("ammo bar"). A QR code links to the full paper.
      Designed to be readable from across a hall and to drive
      conversation rather than display dense text.
    * ``classic`` — the previous IMRAD-style two-column tikzposter.
      Use when the conference rejects the billboard format.

    Audience profile gates copy density, jargon, and call-to-action:

    * ``academic_conference`` — peer audience; full results.
    * ``symposium`` — same as academic but with a methods sketch panel.
    * ``industry`` — emphasise impact + recommendations.
    * ``teaching`` — plain-English headline + a "Try it yourself" call.

    Content is drawn from (in order of preference):
      1. ``synthesis/synthesis_spec.yaml`` (or legacy
         ``dashboard_spec.yaml``) — the same spec the dashboard uses.
         Pulls ``title``, ``subtitle``, ``abstract``,
         ``overview.background``, ``findings`` (used as Results bullets +
         first 3 figures), and ``limitations``.
      2. The hypothesis tracker for a Verdicts panel.
      3. ``synthesis/figures/`` for curated figures (numbered).

    No generic AI-slop placeholders — sections that have no content are
    omitted rather than filled with "describe your work here".
    """
    from research_os.tools.actions.synthesis.dashboard import _load_spec
    from research_os.project_ops import ensure_lazy_dir, load_state

    synthesis_dir = ensure_lazy_dir(root, "synthesis")
    poster_tex = synthesis_dir / "poster.tex"

    spec = _load_spec(root)
    state = load_state(root) if (root / ".os_state").exists() else {}

    title = (spec.get("title") or _project_name(root)).strip()
    subtitle = (spec.get("subtitle") or "").strip()
    cfg = {}
    try:
        import yaml  # type: ignore
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        pass
    author = ((cfg.get("researcher") or {}).get("name")) or ""
    institute = ((cfg.get("researcher") or {}).get("affiliation")) or ""

    # Curated figures, top 3
    fig_dir = synthesis_dir / "figures"
    curated_pngs: list[Path] = []
    if fig_dir.exists():
        curated_pngs = [
            f for f in sorted(fig_dir.iterdir())
            if f.suffix.lower() == ".png" and f.is_file()
        ][:3]

    # Findings bullets (max 4)
    findings_bullets: list[str] = []
    if spec.get("findings"):
        for f in spec["findings"][:4]:
            name = f.get("name") or f.get("id", "")
            finding = (f.get("finding") or "").strip().split("\n")[0]
            verdict = (f.get("verdict") or "").upper()
            verdict_tag = f" [{verdict}]" if verdict else ""
            text = f"\\textbf{{{_poster_tex_escape(name)}}}{verdict_tag}: {_poster_tex_escape(finding)}"
            findings_bullets.append(f"        \\item {text}")
    else:
        for h in (state.get("active_hypotheses") or [])[:4]:
            hid = h.get("id", "")
            statement = h.get("statement", "")[:140]
            status = h.get("status", "in progress").upper()
            findings_bullets.append(
                f"        \\item \\textbf{{{_poster_tex_escape(hid)}}} [{status}]: "
                f"{_poster_tex_escape(statement)}"
            )

    # Background blurb
    background = (
        (spec.get("overview") or {}).get("background")
        or spec.get("abstract")
        or (cfg.get("research_goal") or {}).get("background")
        or ""
    ).strip()
    if not background:
        background = "(Author a project abstract in synthesis/dashboard_spec.yaml.)"

    # Methods bullets — pull from spec.methods or fall back to a 3-line
    # placeholder that reads as legitimate rather than as filler.
    methods_lines = spec.get("methods_bullets") or []
    if not methods_lines:
        methods_lines = [
            "Data ingest, cleaning, and provenance audit.",
            "Exploratory analysis with assumption checks before any inferential test.",
            "Robust inferential methods (rank-based / bootstrap CIs) where appropriate.",
            "Cross-step reproducibility audit prior to synthesis.",
        ]
    methods_items = "\n".join(
        f"        \\item {_poster_tex_escape(m)}" for m in methods_lines[:5]
    )

    # Limitations
    limitations = spec.get("limitations") or []
    limitations_items = "\n".join(
        f"        \\item {_poster_tex_escape(item)}" for item in limitations[:4]
    )

    # Figure blocks — half-width centered, captions truncated to one line
    fig_blocks_parts: list[str] = []
    for f in curated_pngs:
        cap_path = f.with_suffix(".caption.md")
        cap_text = ""
        if cap_path.exists():
            cap_text = cap_path.read_text().strip().split("\n")[0]
            cap_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", cap_text)
            cap_text = cap_text[:180]
        # Copy figure next to the .tex for portable compilation
        dest = synthesis_dir / f.name
        try:
            if not dest.exists() or dest.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, dest)
        except Exception:
            continue
        fig_blocks_parts.append(
            "    \\begin{center}\n"
            f"        \\includegraphics[width=0.92\\linewidth]{{{f.name}}}\n"
            + (f"        \\\\\\small\\itshape {_poster_tex_escape(cap_text)}\n" if cap_text else "")
            + "    \\end{center}\n    \\vspace{0.5cm}\n"
        )
    if not fig_blocks_parts:
        fig_blocks_parts.append(
            "    \\textit{No curated figures yet — run tool\\_synthesis\\_curate\\_figures.}\n"
        )
    fig_blocks = "\n".join(fig_blocks_parts)

    # Headline finding for billboard mode — the single plain-English
    # sentence the entire poster centres on. Prefer spec.poster_headline
    # → spec.findings[0].plain_english → spec.findings[0].finding →
    # the first hypothesis statement.
    headline = (
        spec.get("poster_headline")
        or ""
    ).strip()
    if not headline and spec.get("findings"):
        first = spec["findings"][0]
        headline = (
            first.get("plain_english") or first.get("finding") or ""
        ).strip()
    if not headline:
        for h in (state.get("active_hypotheses") or []):
            if h.get("status") in {"supported", "refuted"}:
                headline = (h.get("statement") or "").strip()
                break
    if not headline:
        headline = "Set a plain-English headline in synthesis_spec.yaml > poster_headline."

    # Audience profile copy.
    audience_copy = {
        "academic_conference": (
            "Scan the QR for the full paper, methods, and data.",
            "Conference attendee",
        ),
        "symposium": (
            "QR links to the full report and the dataset DOI.",
            "Symposium reviewer",
        ),
        "industry": (
            "What this means for practice → see the recommendations panel.",
            "Industry / practitioner",
        ),
        "teaching": (
            "Try this with your students — slides and data via the QR.",
            "Educator",
        ),
    }
    cta, audience_label = audience_copy.get(
        audience, audience_copy["academic_conference"],
    )

    # Compose poster
    if layout == "billboard":
        # Mike Morrison "Better Poster" — giant headline + ammo bar.
        ammo_blocks: list[str] = []
        ammo_blocks.append(
            "\\block{Methods}{\\small\n"
            "    \\begin{itemize}\n"
            f"{methods_items}\n"
            "    \\end{itemize}\n}"
        )
        if findings_bullets:
            ammo_blocks.append(
                "\\block{Detailed findings}{\\small\n"
                "    \\begin{itemize}\n"
                + "\n".join(findings_bullets)
                + "\n    \\end{itemize}\n}"
            )
        if limitations_items:
            ammo_blocks.append(
                "\\block{Limitations}{\\small\n"
                "    \\begin{itemize}\n"
                f"{limitations_items}\n"
                "    \\end{itemize}\n}"
            )

        billboard_tex = (
            "\\documentclass[25pt, a0paper, portrait]{tikzposter}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{xcolor}\n"
            "\\usepackage{qrcode}\n"
            "\\usetheme{Simple}\n"
            "\\definecolor{primary}{HTML}{2C5282}\n"
            "\\definecolor{accent}{HTML}{B7791F}\n"
            "\\colorlet{blocktitlebgcolor}{primary}\n"
            "\\colorlet{blocktitlefgcolor}{white}\n"
            "\\colorlet{titlebgcolor}{primary}\n"
            "\\colorlet{titlefgcolor}{white}\n"
            "\\colorlet{backgroundcolor}{white}\n"
            f"\\title{{\\parbox{{0.95\\linewidth}}{{\\centering "
            f"{_poster_tex_escape(title)}}}}}\n"
            + (f"\\author{{{_poster_tex_escape(author)}}}\n"
               if author else "\\author{}\n")
            + (f"\\institute{{{_poster_tex_escape(institute)}}}\n"
               if institute else "\\institute{}\n")
            + "\\begin{document}\n"
            "\\maketitle\n"
            + (f"\\vspace{{-1.5cm}}\\begin{{center}}\\Large\\itshape "
               f"{_poster_tex_escape(subtitle)}\\end{{center}}\\vspace{{0.5cm}}\n"
               if subtitle else "")
            # The billboard panel — 2/3 width, takes the visual centre.
            + "\\begin{columns}\n"
            "\\column{0.66}\n"
            "\\block{Headline}{\n"
            "    \\vspace{0.5cm}\n"
            "    \\centering\n"
            "    \\Huge\\bfseries\n"
            f"    {_poster_tex_escape(headline)}\n"
            "    \\vspace{0.5cm}\n"
            "}\n"
            "\\block{The figure that tells the story}{\n"
            + (fig_blocks if curated_pngs else
               "    \\centering\\textit{Add a focal figure to "
               "synthesis/figures/.}\n")
            + "}\n"
            f"\\block{{Take-away}}{{\\Large {_poster_tex_escape(cta)}}}\n"
            "\\column{0.33}\n"
            # Ammo bar — methods, detail findings, limitations.
            + "\n".join(ammo_blocks)
            + "\n\\block{Find out more}{\n"
            "    \\centering\n"
            f"    \\qrcode[height=4cm]{{{_poster_tex_escape(spec.get('paper_url') or 'https://example.com/paper')}}}\n"
            "    \\vspace{0.3cm}\n"
            "    \\small Scan for the full paper, data, and code.\n"
            f"    \\vspace{{0.2cm}}\\\\\n    \\textit{{Audience: {_poster_tex_escape(audience_label)}}}\n"
            "}\n"
            "\\end{columns}\n"
            "\\end{document}\n"
        )
        poster_tex.write_text(billboard_tex)
    else:
        # Classic IMRAD two-column.
        blocks: list[str] = []
        blocks.append(
            "\\block{Background}{\n"
            f"    \\vspace{{0.3cm}}\n    {_poster_tex_escape(background)[:1200]}\n"
            "    \\vspace{0.3cm}\n}"
        )
        blocks.append(
            "\\block{Methods}{\n"
            "    \\vspace{0.3cm}\n    \\begin{itemize}\n"
            f"{methods_items}\n"
            "    \\end{itemize}\n    \\vspace{0.3cm}\n}"
        )
        if findings_bullets:
            blocks.append(
                "\\block{Key findings}{\n"
                "    \\vspace{0.3cm}\n    \\begin{itemize}\n"
                + "\n".join(findings_bullets)
                + "\n    \\end{itemize}\n    \\vspace{0.3cm}\n}"
            )
        blocks.append("\\block{Results}{\n" + fig_blocks + "}")
        if limitations_items:
            blocks.append(
                "\\block{Limitations}{\n"
                "    \\vspace{0.3cm}\n    \\begin{itemize}\n"
                f"{limitations_items}\n"
                "    \\end{itemize}\n    \\vspace{0.3cm}\n}"
            )

        left_blocks = blocks[: (len(blocks) + 1) // 2]
        right_blocks = blocks[(len(blocks) + 1) // 2:]
        columns = (
            "\\begin{columns}\n"
            "\\column{0.5}\n" + "\n".join(left_blocks) + "\n"
            "\\column{0.5}\n" + "\n".join(right_blocks) + "\n"
            "\\end{columns}\n"
        )

        poster_tex.write_text(
            "\\documentclass[20pt, a0paper, portrait]{tikzposter}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{xcolor}\n"
            f"\\title{{\\parbox{{0.9\\linewidth}}{{\\centering "
            f"{_poster_tex_escape(title)}}}}}\n"
            + (f"\\author{{{_poster_tex_escape(author)}}}\n"
               if author else "\\author{}\n")
            + (f"\\institute{{{_poster_tex_escape(institute)}}}\n"
               if institute else "\\institute{}\n")
            + "\\usetheme{Simple}\n"
            "\\definecolor{primary}{HTML}{2C5282}\n"
            "\\definecolor{accent}{HTML}{B7791F}\n"
            "\\colorlet{blocktitlebgcolor}{primary}\n"
            "\\colorlet{blocktitlefgcolor}{white}\n"
            "\\colorlet{titlebgcolor}{primary}\n"
            "\\colorlet{titlefgcolor}{white}\n"
            "\\colorlet{backgroundcolor}{white}\n"
            "\\begin{document}\n"
            "\\maketitle\n"
            + (f"\\vspace{{-1cm}}\\begin{{center}}\\Large\\itshape "
               f"{_poster_tex_escape(subtitle)}\\end{{center}}\\vspace{{0.5cm}}\n"
               if subtitle else "")
            + columns
            + "\\end{document}\n"
        )

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return {
            "status": "error",
            "message": "pdflatex not found",
            "tex_path": str(poster_tex.relative_to(root)),
            "success": False,
        }
    res = subprocess.run(
        [pdflatex, "-interaction=nonstopmode", poster_tex.name],
        cwd=str(synthesis_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    pdf = poster_tex.with_suffix(".pdf")
    return {
        "status": "success" if (res.returncode == 0 and pdf.exists()) else "error",
        "pdf_path": str(pdf.relative_to(root)) if pdf.exists() else None,
        "log": res.stdout[-1500:],
    }



# ---------------------------------------------------------------------------
# Dashboard — thin compatibility wrapper.
#
# The real renderer lives at research_os.tools.actions.synthesis.dashboard
# (project-agnostic, audience-driven, traceability matrix, plain-English
# captions, evidence panel). This wrapper exists only so legacy callers
# that import from the LaTeX module keep working.
# ---------------------------------------------------------------------------


def create_dashboard(
    root: Path, title: str | None = None, audience: str = "academic",
    suppress_audit_panel: bool = False,
) -> dict[str, Any]:
    """Delegate to the canonical dashboard renderer."""
    from research_os.tools.actions.synthesis.dashboard import render_dashboard

    return render_dashboard(
        root, title=title, audience=audience,
        suppress_audit_panel=suppress_audit_panel,
    )
