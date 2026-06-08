"""Generic Typst compiler for AI-authored synthesis files.

The AI authors `synthesis/paper.typ` (or `slides.typ` / `poster.typ` /
`essay.typ`) directly, following the design principles in the matching
synthesis protocol. This tool compiles whatever .typ source it points
at into a PDF.

If the .typ source imports bundled templates via
`#import "_typst_templates/<name>.typ"`, this tool copies the
referenced template files next to the source before compiling so the
import resolves.

Public surface: typst_compile(root, source, output, biblio) -> dict.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

from research_os.tools.actions.synthesis.typst import (
    _find_templates_dir,
    citations_md_to_hayagriva,
    compile_typst,
)

logger = logging.getLogger("research_os.tools.synthesis.typst_compile")


_SYNTHESIS_DEFAULTS = {
    "paper": ("synthesis/paper.typ", "synthesis/paper.pdf"),
    "slides": ("synthesis/slides.typ", "synthesis/slides.pdf"),
    "poster": ("synthesis/poster.typ", "synthesis/poster.pdf"),
    "handout": ("synthesis/handout.typ", "synthesis/handout.pdf"),
    "grant": ("synthesis/grant.typ", "synthesis/grant.pdf"),
    "essay": ("synthesis/essay.typ", "synthesis/essay.pdf"),
    "cover_letter": ("synthesis/cover_letter.typ", "synthesis/cover_letter.pdf"),
    "response": ("synthesis/response_to_reviewers.typ", "synthesis/response_to_reviewers.pdf"),
}


def _resolve_source(root: Path, source: str | None) -> Path:
    if source:
        p = Path(source)
        return p if p.is_absolute() else (root / p)
    for default_source, _ in _SYNTHESIS_DEFAULTS.values():
        candidate = root / default_source
        if candidate.exists():
            return candidate
    return root / "synthesis" / "paper.typ"


def _default_output_for(source: Path) -> Path:
    return source.with_suffix(".pdf")


_IMPORT_RE = re.compile(r'#import\s+"_typst_templates/([\w./-]+)"')


def _find_typst_packages_dir() -> Path | None:
    """Locate src/research_os/assets/typst_packages/ (in-package or repo-root).

    Mirrors _find_templates_dir's search-order convention.
    """
    here = Path(__file__).resolve()
    pkg_root = here.parents[3]  # .../research_os
    candidate = pkg_root / "assets" / "typst_packages"
    if candidate.exists():
        return candidate
    for n in (3, 4, 5, 6, 7):
        try:
            candidate = here.parents[n] / "src" / "research_os" / "assets" / "typst_packages"
        except IndexError:
            break
        if candidate.exists():
            return candidate
    return None


def _materialise_template_imports(source: Path) -> None:
    """Copy any bundled templates the .typ imports into _typst_templates/.

    The AI's authored .typ may reference a venue template via
    `#import "_typst_templates/<name>.typ"`. Pulls the matching files
    from the package data dir (or repo-root templates/typst/, OR
    assets/typst_packages/<name>/) and materialises them next to the
    source so the import resolves. Idempotent — files already present
    are not overwritten.
    """
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    refs = set(_IMPORT_RE.findall(text))
    if not refs:
        return
    venue_dir = _find_templates_dir()
    packages_dir = _find_typst_packages_dir()
    target_dir = source.parent / "_typst_templates"
    target_dir.mkdir(exist_ok=True)
    # Always include common.typ so the venue templates' shared helpers
    # resolve when one of them is imported.
    refs = refs | {"common.typ"}
    for name in refs:
        dst = target_dir / name
        if dst.exists():
            continue
        # Try the venue templates dir first (paper venues + common.typ).
        if venue_dir is not None:
            src_template = venue_dir / name
            if src_template.exists():
                shutil.copyfile(src_template, dst)
                continue
        # Then walk assets/typst_packages/* — each pkg has a .typ file
        # whose name matches one of the requested imports (touying-mini.typ
        # lives at touying-mini/touying-mini.typ; poster-mini ships poster.typ).
        if packages_dir is not None:
            stem = Path(name).stem
            for pkg in packages_dir.iterdir():
                if not pkg.is_dir():
                    continue
                # Match by file name OR by package dir name == stem.
                for cand in (pkg / name, pkg / f"{stem}.typ", pkg / "poster.typ"):
                    if cand.exists():
                        shutil.copyfile(cand, dst)
                        break
                if dst.exists():
                    break


def typst_compile(
    root: Path,
    source: str | None = None,
    output: str | None = None,
    biblio: str | None = None,
) -> dict[str, Any]:
    """Compile a Typst source file to PDF.

    Args:
      root: project root.
      source: path to .typ file (relative to root or absolute). Default
        picks the first existing of synthesis/{paper,slides,poster,essay}.typ.
      output: path to output PDF (defaults to source with .pdf extension).
      biblio: path to a Hayagriva biblio.yml. If omitted and
        workspace/citations.md exists, synthesises one at
        synthesis/biblio.yml so the AI's `#bibliography("biblio.yml")`
        call resolves.
    """
    src = _resolve_source(root, source)
    if not src.exists():
        return {
            "status": "error",
            "message": (
                f"Typst source not found: {src.relative_to(root) if src.is_relative_to(root) else src}. "
                "Author the .typ file first (see synthesis/synthesis_paper "
                "or sibling protocol)."
            ),
        }
    if src.suffix.lower() != ".typ":
        return {
            "status": "error",
            "message": f"Expected a .typ file, got {src.suffix}.",
        }

    if output:
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = root / out_path
    else:
        out_path = _default_output_for(src)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    biblio_path: Path | None = None
    if biblio:
        bp = Path(biblio)
        biblio_path = bp if bp.is_absolute() else (root / bp)
    else:
        citations_md = root / "workspace" / "citations.md"
        synth_biblio = src.parent / "biblio.yml"
        if not synth_biblio.exists() and citations_md.exists():
            yml = citations_md_to_hayagriva(citations_md)
            if yml:
                synth_biblio.write_text(yml, encoding="utf-8")
                biblio_path = synth_biblio
        elif synth_biblio.exists():
            biblio_path = synth_biblio

    _materialise_template_imports(src)

    res = compile_typst(src, out_path)

    page_count: int | None = None
    cite_count: int | None = None
    if res.get("status") == "success" and out_path.exists():
        try:
            data = out_path.read_bytes()
            page_count = data.count(b"/Type /Page") or data.count(b"/Page\n") or None
        except OSError:
            page_count = None
        try:
            typ_text = src.read_text(encoding="utf-8", errors="replace")
            cite_count = len(re.findall(r"#cite\(<|\[@[^\]]+\]", typ_text))
        except OSError:
            cite_count = None

    return {
        "status": res.get("status", "error"),
        "pdf_path": str(out_path) if out_path.exists() else None,
        "typst_path": str(src),
        "biblio_path": str(biblio_path) if biblio_path and biblio_path.exists() else None,
        "page_count": page_count,
        "citation_count": cite_count,
        "typst_warnings": res.get("warnings", []),
        "typst_errors": res.get("errors", []),
        "message": res.get("message"),
    }
