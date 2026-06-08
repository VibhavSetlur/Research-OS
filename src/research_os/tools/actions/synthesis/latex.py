"""LaTeX paper compile (pdflatex × bibtex × pdflatex × pdflatex).

Kept for journals that require .tex submission. For the modern
authoring path the AI writes synthesis/paper.typ directly and compiles
via tool_typst_compile.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.latex")


def latex_compile(root: Path) -> dict[str, Any]:
    """Compile ``synthesis/paper.tex`` to PDF."""
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
