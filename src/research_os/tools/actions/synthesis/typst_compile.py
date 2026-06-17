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
                # Match by exact file name OR by package dir name == stem.
                # Both forms already resolve every bundled package
                # (touying-mini.typ -> touying-mini/touying-mini.typ;
                # poster.typ -> poster-mini/poster.typ), so no greedy
                # filename fallback that could copy the wrong package's
                # file under a different requested name.
                for cand in (pkg / name, pkg / f"{stem}.typ"):
                    if cand.exists():
                        shutil.copyfile(cand, dst)
                        break
                if dst.exists():
                    break


# Fixed-format targets that MUST render to a single page — a page count
# above this is a strong signal that content overflowed the canvas (the
# user's "overlapping / overflowing" pain in posters + one-pagers).
_SINGLE_PAGE_TARGETS = {"poster", "cover_letter"}


def _target_kind(src: Path) -> str:
    """Map a source filename back to its deliverable kind (paper/poster/…)."""
    stem = src.stem.lower()
    for kind, (rel_src, _rel_out) in _SYNTHESIS_DEFAULTS.items():
        if Path(rel_src).stem.lower() == stem:
            return kind
    return stem


def typst_compile(
    root: Path,
    source: str | None = None,
    output: str | None = None,
    biblio: str | None = None,
    archive_prior: bool = True,
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
      archive_prior: when True (default), an existing good render is copied to
        synthesis/archive/<name>_<timestamp>.pdf before being overwritten — so
        a recompile never silently loses the previous deliverable.
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

    # A freshly scaffolded source references `#bibliography("biblio.yml")`
    # before the author has added any citations. Ensure a minimal valid
    # Hayagriva file exists so the skeleton compiles out of the box (the
    # author overwrites it once citations.md is populated). Mirrors the
    # placeholder the markdown synthesis path has always written.
    try:
        src_text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        src_text = ""
    if "#bibliography(" in src_text:
        referenced = src.parent / "biblio.yml"
        if not referenced.exists():
            referenced.write_text(
                'placeholder:\n  type: misc\n  title: "No citations yet"\n',
                encoding="utf-8",
            )
            if biblio_path is None:
                biblio_path = referenced

    _materialise_template_imports(src)

    # Output versioning: archive the prior good render before overwriting it,
    # so a recompile never silently discards the previous deliverable. We keep
    # ONE canonical name (paper.pdf) and a timestamped history in archive/.
    archived_to: str | None = None
    if archive_prior and out_path.exists() and out_path.stat().st_size > 0:
        try:
            from datetime import datetime, timezone

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            archive_dir = out_path.parent / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / f"{out_path.stem}_{stamp}{out_path.suffix}"
            shutil.copy2(out_path, dest)
            archived_to = str(dest)
        except Exception as exc:
            logger.debug("prior-render archive skipped: %s", exc)

    res = compile_typst(src, out_path)

    page_count: int | None = None
    cite_count: int | None = None
    layout_warnings: list[str] = []
    if res.get("status") == "success" and out_path.exists():
        try:
            data = out_path.read_bytes()
            # Count page objects (/Type /Page) without counting the page-tree
            # node (/Type /Pages) — the old grep over-counted by one.
            page_count = len(re.findall(rb"/Type\s*/Page(?![s])", data)) or None
        except OSError:
            page_count = None
        try:
            typ_text = src.read_text(encoding="utf-8", errors="replace")
            cite_count = len(re.findall(r"#cite\(<|\[@[^\]]+\]", typ_text))
        except OSError:
            cite_count = None
        # Overflow signal: a single-page target that rendered to >1 page means
        # content overflowed the canvas (poster columns, one-pager letter).
        kind = _target_kind(src)
        if kind in _SINGLE_PAGE_TARGETS and (page_count or 1) > 1:
            layout_warnings.append(
                f"{kind} rendered to {page_count} pages but must fit ONE — content "
                "overflowed the canvas. Trim text / shrink figures / reduce font "
                "size, then recompile. (Overlapping or clipped text usually shows "
                "here.)"
            )

    status = res.get("status", "error")
    return {
        "status": status,
        "pdf_path": str(out_path) if out_path.exists() else None,
        "typst_path": str(src),
        "biblio_path": str(biblio_path) if biblio_path and biblio_path.exists() else None,
        "page_count": page_count,
        "citation_count": cite_count,
        "archived_prior_to": archived_to,
        "layout_warnings": layout_warnings,
        "typst_warnings": res.get("warnings", []),
        "typst_errors": res.get("errors", []),
        "message": res.get("message"),
    }
