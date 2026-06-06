"""LaTeX paper compile + high-quality HTML dashboard generation.

Posters are rendered by ``synthesis/poster_typst.py`` (Typst engine).

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
import shutil
import subprocess
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
