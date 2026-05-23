"""Standalone implementations for all §4.2 missing MCP tools.

Each function is self-contained and can be called directly from server.py handlers.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("research.tools")


# ---------------------------------------------------------------------------
# tool.latex.compile
# ---------------------------------------------------------------------------


def latex_compile(root: Path) -> dict:
    """Run pdflatex + bibtex on synthesis/paper.tex.

    Runs: pdflatex → bibtex → pdflatex (×2) for proper cross-referencing.
    Returns dict with 'pdf_path', 'log', 'success', and optional 'warning'.
    """
    tex_path = root / "synthesis" / "paper.tex"
    if not tex_path.exists():
        return {
            "pdf_path": None,
            "success": False,
            "log": "",
            "warning": "synthesis/paper.tex not found",
        }

    pdflatex = shutil.which("pdflatex")
    bibtex = shutil.which("bibtex")
    if not pdflatex:
        return {
            "pdf_path": None,
            "success": False,
            "log": "",
            "warning": "pdflatex not found. Install TeX Live.",
        }

    synthesis_dir = tex_path.parent
    log_lines: list[str] = []
    success = True

    def _run_pdflatex() -> bool:
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=str(synthesis_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        log_lines.append(
            result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        )
        return result.returncode == 0

    def _run_bibtex() -> bool:
        if not bibtex:
            log_lines.append(
                "[WARN] bibtex not found — skipping bibliography compilation"
            )
            return True
        aux = tex_path.with_suffix(".aux")
        if not aux.exists():
            return True
        result = subprocess.run(
            [bibtex, aux.name],
            cwd=str(synthesis_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        log_lines.append(
            result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout
        )
        return True

    # Run 1: pdflatex
    if not _run_pdflatex():
        success = False
        log_lines.append("[ERROR] First pdflatex run failed")

    if success:
        _run_bibtex()

    # Run 2: pdflatex
    if success and not _run_pdflatex():
        success = False
        log_lines.append("[ERROR] Second pdflatex run failed")

    # Run 3: pdflatex (resolve all cross-refs)
    if success and not _run_pdflatex():
        success = False
        log_lines.append("[ERROR] Third pdflatex run failed")

    pdf_path = tex_path.with_suffix(".pdf")
    return {
        "pdf_path": str(pdf_path.absolute()) if pdf_path.exists() else None,
        "success": success,
        "log": "\n".join(log_lines[-50:]),
        "warning": None
        if success
        else "LaTeX compilation failed — see log for details",
    }


def create_poster(root: Path) -> dict:
    """Create a professional LaTeX poster in synthesis/poster.pdf using tikzposter."""
    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)
    poster_tex = synthesis_dir / "poster.tex"

    from research_os.state.state_ledger import ResearchLedger
    ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
    state = ledger.get()
    title = state.get("project", "Research Poster")

    workspace_dir = root / "workspace"
    figures = []
    if workspace_dir.exists():
        for f in workspace_dir.rglob("*.png"):
            # Copy figure to synthesis dir to avoid complex path issues in LaTeX
            dest = synthesis_dir / f.name
            if not dest.exists():
                import shutil
                shutil.copy2(f, dest)
            figures.append(f.name)

    tex_content = r"""\documentclass[20pt, a0paper, portrait]{tikzposter}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}

\title{""" + title + r"""}
\author{Autonomous Research System}
\institute{Research OS}

\usetheme{Board}

\begin{document}
\maketitle

\begin{columns}

\column{0.5}
\block{Introduction}{
    \vspace{1cm}
    This poster presents the automated findings.
    \vspace{1cm}
}

\block{Methods}{
    \vspace{1cm}
    \begin{itemize}
        \item Automated data analysis
        \item Statistical modeling
        \item Literature review
    \end{itemize}
    \vspace{1cm}
}

\column{0.5}
\block{Results}{
    \vspace{1cm}
"""

    if figures:
        tex_content += r"    \begin{center}" + "\n"
        for fig in figures[:2]:
            tex_content += f"        \\includegraphics[width=0.8\\linewidth]{{{fig}}}\n"
            tex_content += r"        \vspace{1cm}" + "\n"
        tex_content += r"    \end{center}" + "\n"
    else:
        tex_content += r"    \textit{No figures generated yet.}" + "\n"

    tex_content += r"""
    \vspace{1cm}
}

\block{Conclusions}{
    \vspace{1cm}
    Results indicate successful execution of the automated pipeline.
    \vspace{1cm}
}

\block{References}{
    \vspace{1cm}
    \bibliographystyle{plain}
    \textit{References will be populated here.}
    \vspace{1cm}
}

\end{columns}
\end{document}
"""
    poster_tex.write_text(tex_content)

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return {
            "pdf_path": None,
            "success": False,
            "log": "",
            "warning": "pdflatex not found. Install TeX Live.",
        }

    log_lines: list[str] = []
    success = True
    
    result = subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error", poster_tex.name],
        cwd=str(synthesis_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    log_lines.append(result.stdout)
    if result.returncode != 0:
        success = False
        log_lines.append("[ERROR] pdflatex run failed")

    pdf_path = poster_tex.with_suffix(".pdf")
    return {
        "pdf_path": str(pdf_path.absolute()) if pdf_path.exists() else None,
        "success": success,
        "log": "\n".join(log_lines[-50:]),
        "warning": None if success else "LaTeX compilation failed — see log for details",
    }
