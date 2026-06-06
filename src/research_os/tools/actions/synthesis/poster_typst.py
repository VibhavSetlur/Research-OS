"""Typst-native poster compilation.

The only poster engine for ``tool_poster_create``. The ``synthesis.poster_engine``
config field is pinned to ``"typst"`` and rejects any other value.

Public surface:
  * compile_poster(root, template, theme, qr_url, handout_pdf) -> dict
  * SUPPORTED_TEMPLATES — registry consulted by router + config validator.

Pipeline:
  1. Load synthesis spec (title / subtitle / abstract / findings /
     limitations) via the same _load_spec helper the paper + dashboard
     builders share. No fields are invented; missing ones are simply
     omitted from the poster.
  2. Pick hero figures by ``poster_priority`` (lower = higher priority)
     from each ``<stem>.caption.md`` frontmatter under synthesis/figures/.
     Top 3 land on the poster, ranked.
  3. Render the QR code as PNG via a pure-Python encoder when qr_url
     is provided. If the encoder import fails (truly minimal install),
     the QR is omitted and a warning is logged — never a hard error.
  4. Bundle the chosen template + the poster-mini package next to the
     emitted poster.typ so Typst's relative imports resolve without
     needing ``--root /``.
  5. ``typst compile`` → synthesis/poster.pdf. handout_pdf=True also
     compiles a US-letter text-only condensed PDF.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.poster_typst")


SUPPORTED_TEMPLATES: dict[str, dict[str, Any]] = {
    "academic_36x48": {
        "file": "academic_36x48.typ",
        "func": "academic-36x48",
        "size": "36in x 48in",
        "page_w_in": 36.0,
        "page_h_in": 48.0,
        "columns": 3,
    },
    "academic_48x36": {
        "file": "academic_48x36.typ",
        "func": "academic-48x36",
        "size": "48in x 36in",
        "page_w_in": 48.0,
        "page_h_in": 36.0,
        "columns": 4,
    },
    "academic_a0_portrait": {
        "file": "academic_a0_portrait.typ",
        "func": "academic-a0-portrait",
        "size": "A0 portrait (841mm x 1189mm)",
        "page_w_in": 33.11,
        "page_h_in": 46.81,
        "columns": 3,
    },
    "academic_a1_landscape": {
        "file": "academic_a1_landscape.typ",
        "func": "academic-a1-landscape",
        "size": "A1 landscape (841mm x 594mm)",
        "page_w_in": 33.11,
        "page_h_in": 23.39,
        "columns": 3,
    },
    "public_24x36": {
        "file": "public_24x36.typ",
        "func": "public-24x36",
        "size": "24in x 36in (community-event)",
        "page_w_in": 24.0,
        "page_h_in": 36.0,
        "columns": 2,
    },
}


# Hard cap on hero figure count. The "Better Poster" + every survey of
# poster comprehension lands in the 3-5 range; 3 is the default.
_MAX_HERO_FIGURES = 3


# ---------------------------------------------------------------------------
# Spec + frontmatter helpers
# ---------------------------------------------------------------------------


def _project_name(root: Path) -> str:
    try:
        from research_os.project_ops import load_state

        return (load_state(root) or {}).get("project_name") or "Research Project"
    except Exception:
        return "Research Project"


def _load_researcher(root: Path) -> dict[str, Any]:
    cfg_path = root / "inputs" / "researcher_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}


def _parse_caption_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text). Accepts both YAML front
    matter delimited by ``---`` lines and a bare ``key: value`` head
    block (lenient — captions are author-written and uneven)."""
    if not text:
        return {}, ""
    fm: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            try:
                import yaml

                fm = yaml.safe_load(head) or {}
            except Exception:
                fm = {}
            return fm, body
    return fm, body


def _hero_figures(root: Path, limit: int = _MAX_HERO_FIGURES) -> list[dict[str, Any]]:
    """Pick top-N hero figures by ``poster_priority`` frontmatter.

    Each entry: {path, caption, summary, priority}. Figures without a
    ``.caption.md`` sidecar get priority 999 (sorted to the back) but
    still surface so a fresh project isn't blank.
    """
    fig_dir = root / "synthesis" / "figures"
    if not fig_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for f in sorted(fig_dir.iterdir()):
        if not (f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg"}):
            continue
        cap = f.with_suffix(".caption.md")
        fm: dict[str, Any] = {}
        body = ""
        if cap.exists():
            try:
                fm, body = _parse_caption_frontmatter(cap.read_text())
            except Exception:
                fm, body = {}, ""
        priority = fm.get("poster_priority")
        try:
            priority = float(priority) if priority is not None else 999.0
        except (TypeError, ValueError):
            priority = 999.0
        # Caption: first paragraph of body, stripped of markdown emphasis.
        cap_first = body.strip().split("\n\n")[0] if body else ""
        cap_first = re.sub(r"\*\*([^*]+)\*\*", r"\1", cap_first)[:240]
        entries.append({
            "path": f,
            "caption": cap_first,
            "summary": (fm.get("summary") or "").strip(),
            "priority": priority,
        })
    entries.sort(key=lambda e: (e["priority"], e["path"].name))
    return entries[:limit]


# ---------------------------------------------------------------------------
# QR code rendering (pure-Python; optional)
# ---------------------------------------------------------------------------


def _render_qr_png(url: str, out_path: Path) -> bool:
    """Render `url` to a PNG at `out_path`. Returns True on success.

    Tries the ``qrcode`` library first (pure-Python encoder, PIL
    output). Falls back gracefully to False if neither qrcode nor PIL
    is installed; caller logs a warning and proceeds without the QR.
    """
    try:
        import qrcode  # type: ignore
    except Exception:
        logger.warning("qrcode library not installed; omitting QR code")
        return False
    try:
        img = qrcode.make(url)
        img.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:
        logger.warning("QR render failed: %s; omitting QR", e)
        return False


# ---------------------------------------------------------------------------
# Asset staging
# ---------------------------------------------------------------------------


def _assets_root() -> Path:
    """Locate src/research_os/assets/ relative to this module."""
    # poster_typst.py lives at .../tools/actions/synthesis/
    return Path(__file__).resolve().parents[3] / "assets"


def _stage_assets(synthesis_dir: Path, template_key: str) -> Path:
    """Copy the chosen template + poster-mini package into the project's
    synthesis/ dir so Typst's relative imports resolve. Returns the
    staged template path."""
    assets = _assets_root()
    src_template = assets / "poster_templates" / SUPPORTED_TEMPLATES[template_key]["file"]
    src_package = assets / "typst_packages" / "poster-mini"

    dst_template_dir = synthesis_dir / "_poster_assets" / "poster_templates"
    dst_package_dir = synthesis_dir / "_poster_assets" / "typst_packages"
    dst_template_dir.mkdir(parents=True, exist_ok=True)
    dst_package_dir.mkdir(parents=True, exist_ok=True)

    dst_template = dst_template_dir / src_template.name
    shutil.copy2(src_template, dst_template)
    dst_pkg = dst_package_dir / "poster-mini"
    if dst_pkg.exists():
        shutil.rmtree(dst_pkg)
    shutil.copytree(src_package, dst_pkg)
    return dst_template


# ---------------------------------------------------------------------------
# Typst source emission
# ---------------------------------------------------------------------------


def _typst_escape(text: str) -> str:
    r"""Escape Typst special characters that would otherwise mangle the
    rendered string. Typst is far gentler than LaTeX — only ``\``, ``#``,
    ``$``, and ``@`` are markup-active in inline text."""
    if not text:
        return ""
    return (text
            .replace("\\", r"\\")
            .replace("#", r"\#")
            .replace("$", r"\$")
            .replace("@", r"\@")
            .replace("<", r"\<")
            .replace(">", r"\>"))


def _emit_poster_typst(
    *,
    template_key: str,
    title: str,
    subtitle: str,
    authors: str,
    affiliation: str,
    funding: str,
    contact: str,
    headline: str,
    background: str,
    methods: list[str],
    findings: list[dict[str, Any]],
    limitations: list[str],
    hero_figures: list[dict[str, Any]],
    qr_path: Path | None,
    qr_caption: str,
    theme: str,
    rel_template_path: str,
    rel_package_path: str,
) -> str:
    """Build the poster.typ source string."""
    tmeta = SUPPORTED_TEMPLATES[template_key]
    func_name = tmeta["func"]

    lines: list[str] = []
    lines.append(f'#import "{rel_template_path}": {func_name}')
    lines.append(f'#import "{rel_package_path}": poster-block, poster-headline, poster-bullets, poster-figure')
    lines.append("")
    lines.append(f"#show: {func_name}.with(")
    lines.append(f'  title: "{_typst_escape(title)}",')
    if subtitle:
        lines.append(f'  subtitle: "{_typst_escape(subtitle)}",')
    if authors:
        lines.append(f'  authors: "{_typst_escape(authors)}",')
    if affiliation:
        lines.append(f'  affiliation: "{_typst_escape(affiliation)}",')
    if funding:
        lines.append(f'  funding: "{_typst_escape(funding)}",')
    if contact:
        lines.append(f'  contact: "{_typst_escape(contact)}",')
    if qr_path is not None:
        lines.append(f'  qr-image: "{qr_path.name}",')
        if qr_caption:
            lines.append(f'  qr-caption: "{_typst_escape(qr_caption)}",')
    lines.append(f'  theme: "{theme}",')
    lines.append(")")
    lines.append("")

    if headline:
        lines.append(f"#poster-headline[{_typst_escape(headline)}]")
        lines.append("")

    if background:
        lines.append('#poster-block(title: "Background")[')
        lines.append(f"  {_typst_escape(background)}")
        lines.append("]")
        lines.append("")

    if methods:
        lines.append('#poster-block(title: "Methods")[')
        lines.append("  #poster-bullets((")
        for m in methods[:5]:
            lines.append(f"    [{_typst_escape(m)}],")
        lines.append("  ))")
        lines.append("]")
        lines.append("")

    if hero_figures:
        lines.append('#poster-block(title: "Key results")[')
        for fig in hero_figures:
            cap = fig["caption"]
            # image() in poster-mini/poster.typ resolves relative to
            # the helper file. Stage the figure inside the helper dir
            # at staging time and reference it by bare name here.
            lines.append(
                f'  #poster-figure(path: "{fig["path"].name}", '
                f'caption: "{_typst_escape(cap)}")'
            )
        lines.append("]")
        lines.append("")

    if findings:
        lines.append('#poster-block(title: "Findings")[')
        lines.append("  #poster-bullets((")
        for f in findings[:5]:
            name = f.get("name") or f.get("id", "")
            text = (f.get("finding") or "").split("\n")[0]
            verdict = (f.get("verdict") or "").upper()
            tag = f" [{verdict}]" if verdict else ""
            line_txt = f"*{_typst_escape(name)}*{tag}: {_typst_escape(text)}"
            lines.append(f"    [{line_txt}],")
        lines.append("  ))")
        lines.append("]")
        lines.append("")

    if limitations:
        lines.append('#poster-block(title: "Limitations")[')
        lines.append("  #poster-bullets((")
        for lim in limitations[:4]:
            lines.append(f"    [{_typst_escape(lim)}],")
        lines.append("  ))")
        lines.append("]")
        lines.append("")

    return "\n".join(lines) + "\n"


def _emit_handout_typst(
    *,
    title: str,
    subtitle: str,
    authors: str,
    affiliation: str,
    background: str,
    methods: list[str],
    findings: list[dict[str, Any]],
    limitations: list[str],
    qr_caption: str,
    qr_path: Path | None,
) -> str:
    """Single-page US-letter text handout — companion to the wall poster.
    Self-contained: no imports needed, plain Typst markup."""
    parts: list[str] = []
    parts.append('#set page(paper: "us-letter", margin: 0.75in)')
    parts.append('#set text(font: ("Linux Libertine", "New Computer Modern", "Times New Roman", "Times"), size: 10pt)')
    parts.append('#set par(justify: true, leading: 0.55em)')
    parts.append('')
    parts.append(f'#align(center, text(size: 16pt, weight: "bold")[{_typst_escape(title)}])')
    if subtitle:
        parts.append(f'#align(center, text(size: 11pt, style: "italic")[{_typst_escape(subtitle)}])')
    if authors:
        parts.append(f'#align(center, text(size: 10pt)[{_typst_escape(authors)}])')
    if affiliation:
        parts.append(f'#align(center, text(size: 9pt, style: "italic")[{_typst_escape(affiliation)}])')
    parts.append('#v(8pt)')

    if background:
        parts.append('== Background')
        parts.append(_typst_escape(background))
        parts.append('')

    if methods:
        parts.append('== Methods')
        for m in methods[:5]:
            parts.append(f"- {_typst_escape(m)}")
        parts.append('')

    if findings:
        parts.append('== Findings')
        for f in findings[:5]:
            name = f.get("name") or f.get("id", "")
            text = (f.get("finding") or "").split("\n")[0]
            verdict = (f.get("verdict") or "").upper()
            tag = f" *[{verdict}]*" if verdict else ""
            parts.append(f"- *{_typst_escape(name)}*{tag}: {_typst_escape(text)}")
        parts.append('')

    if limitations:
        parts.append('== Limitations')
        for lim in limitations[:4]:
            parts.append(f"- {_typst_escape(lim)}")
        parts.append('')

    if qr_path is not None:
        parts.append('#v(8pt)')
        # QR PNG lives inside _poster_assets/typst_packages/poster-mini/
        # (staged there for the main poster). The handout.typ sits at
        # synthesis/, so the relative path walks down into the helper dir.
        qr_rel = "_poster_assets/typst_packages/poster-mini/" + qr_path.name
        parts.append(f'#align(center, image("{qr_rel}", width: 1.2in))')
        if qr_caption:
            parts.append(f'#align(center, text(size: 8pt)[{_typst_escape(qr_caption)}])')

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Compile + size validation
# ---------------------------------------------------------------------------


def _typst_compile(src: Path, out: Path) -> dict[str, Any]:
    """Invoke ``typst compile`` and return a structured result."""
    typst_bin = shutil.which("typst")
    if not typst_bin:
        return {
            "status": "error",
            "message": (
                "typst not found. Install via `cargo install --locked typst-cli` "
                "or your package manager."
            ),
        }
    from research_os.tools.actions.synthesis.typst import _typst_compile_argv
    proc = subprocess.run(
        _typst_compile_argv(typst_bin, src.name, out.name),
        cwd=str(src.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    warnings = [ln for ln in proc.stderr.splitlines() if ln.startswith("warning:")]
    if proc.returncode != 0 or not out.exists():
        return {
            "status": "error",
            "message": "typst compile failed",
            "stderr": proc.stderr[-2000:],
            "warnings": warnings,
        }
    return {"status": "success", "warnings": warnings}


# Soft cap — flagged in the returned dict, not enforced (the researcher
# may legitimately want a larger PDF for a giant poster).
_POSTER_SIZE_SOFT_CAP_BYTES = 6 * 1024 * 1024


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def compile_poster(
    root: Path,
    *,
    template: str = "academic_36x48",
    theme: str = "light",
    qr_url: str | None = None,
    handout_pdf: bool = True,
) -> dict[str, Any]:
    """Generate ``synthesis/poster.pdf`` (and optional handout) from the
    curated synthesis spec via the Typst engine.

    Parameters
    ----------
    root : Path
        Project root.
    template : str
        One of ``SUPPORTED_TEMPLATES`` keys. Default ``academic_36x48``.
    theme : str
        ``light`` | ``dark`` | ``institution_branded``.
    qr_url : str | None
        If set, render a QR PNG and place it in the footer.
    handout_pdf : bool
        If True (default), also emit ``synthesis/poster.handout.pdf`` —
        a US-letter text-only condensed companion.

    Returns
    -------
    dict with keys:
        status, success, pdf_path, handout_pdf_path, template, theme,
        hero_figures (list of stems used), qr_included (bool),
        size_bytes, size_warning, warnings, message?
    """
    root = Path(root)
    if template not in SUPPORTED_TEMPLATES:
        return {
            "status": "error",
            "success": False,
            "message": (
                f"unknown poster template '{template}'. Supported: "
                f"{', '.join(sorted(SUPPORTED_TEMPLATES))}"
            ),
        }
    if theme not in ("light", "dark", "institution_branded"):
        return {
            "status": "error",
            "success": False,
            "message": (
                f"unknown poster theme '{theme}'. Supported: "
                "light, dark, institution_branded"
            ),
        }

    # ── load spec + state ────────────────────────────────────────────
    from research_os.tools.actions.synthesis.dashboard import _load_spec

    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)

    spec = _load_spec(root)
    cfg = _load_researcher(root)

    title = (spec.get("title") or _project_name(root)).strip()
    subtitle = (spec.get("subtitle") or "").strip()
    researcher = cfg.get("researcher") or {}
    authors = researcher.get("name", "")
    affiliation = researcher.get("institution") or researcher.get("affiliation") or ""
    funding = (spec.get("funding") or researcher.get("funding") or "").strip()
    contact = researcher.get("email", "")

    headline = (spec.get("poster_headline") or "").strip()
    if not headline and spec.get("findings"):
        first = spec["findings"][0]
        headline = (first.get("plain_english") or first.get("finding") or "").strip()
    if not headline:
        headline = (spec.get("title") or "").strip()

    background = (
        (spec.get("overview") or {}).get("background")
        or spec.get("abstract")
        or ""
    ).strip()
    methods = spec.get("methods_bullets") or []
    findings = spec.get("findings") or []
    limitations = spec.get("limitations") or []

    # ── stage template + package (needed before figures so the
    #    helper dir exists for image staging) ──────────────────────
    staged_template = _stage_assets(synthesis_dir, template)
    helper_dir = synthesis_dir / "_poster_assets" / "typst_packages" / "poster-mini"

    # ── hero figures ─────────────────────────────────────────────────
    # Typst's image() resolves paths relative to the file the call
    # textually appears in. The call lives in poster-mini/poster.typ,
    # so figures must be staged there.
    heroes = _hero_figures(root)
    staged_heroes: list[dict[str, Any]] = []
    for h in heroes:
        dst = helper_dir / h["path"].name
        try:
            if not dst.exists() or dst.stat().st_mtime < h["path"].stat().st_mtime:
                shutil.copy2(h["path"], dst)
        except Exception:
            continue
        staged_heroes.append({**h, "path": dst})

    # Stage QR PNG (also referenced via image()) into the helper dir.

    # ── QR ──────────────────────────────────────────────────────────
    # QR also lives in the helper dir so image() resolves correctly.
    qr_path: Path | None = None
    qr_included = False
    if qr_url:
        qr_path_candidate = helper_dir / "poster_qr.png"
        if _render_qr_png(qr_url, qr_path_candidate):
            qr_path = qr_path_candidate
            qr_included = True
        else:
            logger.info("QR omitted; qrcode library unavailable or render failed")

    # Relative paths from synthesis/poster.typ → assets.
    rel_template_path = (
        f"_poster_assets/poster_templates/{SUPPORTED_TEMPLATES[template]['file']}"
    )
    rel_package_path = "_poster_assets/typst_packages/poster-mini/poster.typ"

    # ── emit + compile poster.typ ───────────────────────────────────
    poster_typ = synthesis_dir / "poster.typ"
    poster_pdf = synthesis_dir / "poster.pdf"
    poster_typ.write_text(_emit_poster_typst(
        template_key=template,
        title=title,
        subtitle=subtitle,
        authors=authors,
        affiliation=affiliation,
        funding=funding,
        contact=contact,
        headline=headline,
        background=background,
        methods=list(methods),
        findings=list(findings),
        limitations=list(limitations),
        hero_figures=staged_heroes,
        qr_path=qr_path,
        qr_caption="Project page",
        theme=theme,
        rel_template_path=rel_template_path,
        rel_package_path=rel_package_path,
    ))
    # staged_template path is used implicitly by the relative import
    # inside poster.typ; reference it so static analysers see the link.
    _ = staged_template

    compile_res = _typst_compile(poster_typ, poster_pdf)
    if compile_res["status"] != "success":
        return {
            "status": "error",
            "success": False,
            "message": compile_res.get("message", "typst compile failed"),
            "stderr": compile_res.get("stderr", ""),
            "warnings": compile_res.get("warnings", []),
            "tex_path": None,
            "typ_path": str(poster_typ.relative_to(root)),
        }

    size_bytes = poster_pdf.stat().st_size
    size_warning: str | None = None
    if size_bytes > _POSTER_SIZE_SOFT_CAP_BYTES:
        size_warning = (
            f"poster.pdf is {size_bytes / 1024 / 1024:.1f} MB, above the "
            f"{_POSTER_SIZE_SOFT_CAP_BYTES // 1024 // 1024} MB soft cap. "
            "Consider down-sampling hero figures to PNG ≤ 300 dpi."
        )

    # ── handout PDF ─────────────────────────────────────────────────
    handout_path: Path | None = None
    handout_warnings: list[str] = []
    if handout_pdf:
        handout_typ = synthesis_dir / "poster.handout.typ"
        handout_pdf_path = synthesis_dir / "poster.handout.pdf"
        handout_typ.write_text(_emit_handout_typst(
            title=title,
            subtitle=subtitle,
            authors=authors,
            affiliation=affiliation,
            background=background,
            methods=list(methods),
            findings=list(findings),
            limitations=list(limitations),
            qr_caption=qr_url or "",
            qr_path=qr_path,
        ))
        h_res = _typst_compile(handout_typ, handout_pdf_path)
        if h_res["status"] == "success":
            handout_path = handout_pdf_path
            handout_warnings = h_res.get("warnings", [])
        else:
            handout_warnings = [
                f"handout failed: {h_res.get('message', '')}"
            ]

    return {
        "status": "success",
        "success": True,
        "engine": "typst",
        "template": template,
        "theme": theme,
        "pdf_path": str(poster_pdf.relative_to(root)),
        "typ_path": str(poster_typ.relative_to(root)),
        "handout_pdf_path": (
            str(handout_path.relative_to(root)) if handout_path else None
        ),
        "hero_figures": [h["path"].name for h in staged_heroes],
        "qr_included": qr_included,
        "qr_url": qr_url if qr_included else None,
        "page_size": SUPPORTED_TEMPLATES[template]["size"],
        "size_bytes": size_bytes,
        "size_warning": size_warning,
        "warnings": compile_res.get("warnings", []) + handout_warnings,
    }
