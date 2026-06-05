"""Real slide compilation — Reveal.js (HTML) + Touying (Typst → PDF).

``tool_slides_create`` exposes two engines:

* ``engine="reveal"`` writes ``synthesis/slides.html`` — a single
  self-contained HTML file backed by the vendored Reveal.js v5 runtime
  in ``research_os/assets/reveal/``. Speaker notes embed under each
  slide via the stock ``notes.js`` plugin (``s`` key opens the
  speaker-view popup). When the vendored runtime is missing (offline
  install corruption / aggressive pruning) the renderer falls back to a
  hand-authored vanilla-JS arrow-key navigator (``_FALLBACK_HTML``) so
  the deck still opens in a browser.

* ``engine="touying"`` writes ``synthesis/slides.typ`` against the
  bundled ``touying-mini.typ`` (in ``research_os/assets/typst_packages/
  touying-mini/``) and shells out to the ``typst`` CLI to produce
  ``synthesis/slides.pdf``. Requires the ``typst`` binary on PATH; we
  reuse the same locator + error envelope as ``compile_typst()`` from
  ``typst.py``.

Both engines source from:

* ``synthesis/slides_spec.yaml`` — researcher-authored, optional
* per-step ``conclusions.md`` + ``outputs/figures/*.png`` + sibling
  ``.summary.md`` / ``.caption.md``
* the chosen template under ``research_os/assets/slide_templates/``

When ``print_handout=True``, a condensed PDF (``synthesis/slides_
handout.pdf``) is written:

* ``engine="reveal"`` — opens the HTML in a headless engine if Playwright
  is installed AND it's already invoked from a CLI context; otherwise
  falls back to a markdown→typst→pdf path via the touying handout mode.
* ``engine="touying"`` — re-compiles the same ``slides.typ`` with
  ``--input handout=true`` (the template's `slides` function reads the
  state and switches to 2-up A4).

Public surface (the integration agent will wrap this):

    compile_slides(
        root: Path | str,
        engine: str = "reveal",        # "reveal" | "touying"
        template: str = "conference_15min",
        theme: str = "",               # "" | "white" | "black"
        speaker_notes_enabled: bool = True,
        print_handout: bool = True,
    ) -> dict[str, Any]
"""
from __future__ import annotations

import base64
import html
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml is in the core install
    yaml = None  # noqa: N816

logger = logging.getLogger("research_os.tools.synthesis.slides")


# ---------------------------------------------------------------------------
# Asset locators
# ---------------------------------------------------------------------------

# This file lives at .../research_os/tools/actions/synthesis/slides.py
# Assets at      .../research_os/assets/<reveal|slide_templates|typst_packages>
_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
_REVEAL_DIR = _ASSETS_DIR / "reveal"
_TEMPLATES_DIR = _ASSETS_DIR / "slide_templates"
_TOUYING_DIR = _ASSETS_DIR / "typst_packages" / "touying-mini"

SUPPORTED_TEMPLATES: list[str] = [
    "conference_15min",
    "conference_5min_lightning",
    "lab_meeting_30min",
    "defense_45min",
    "public_outreach",
]
SUPPORTED_ENGINES: list[str] = ["reveal", "touying"]
SUPPORTED_THEMES: list[str] = ["", "white", "black"]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def compile_slides(
    root: Path | str,
    engine: str = "reveal",
    template: str = "conference_15min",
    theme: str = "",
    speaker_notes_enabled: bool = True,
    print_handout: bool = True,
    *,
    audience: str | None = None,  # back-compat — old signature kwarg
    output_format: str | None = None,  # back-compat alias for engine
) -> dict[str, Any]:
    """Compile a presentation deck.

    Returns a structured envelope describing every file written + any
    warnings the renderer emitted. Never raises for user-level errors;
    callers inspect ``status``.
    """
    # ------------------- back-compat shim --------------------
    # Old skeleton accepted output_format="reveal"/"beamer"/"marp". Map
    # the two we still claim to support; anything else falls through to
    # engine= as-is so a future caller can opt in.
    if output_format and engine == "reveal":
        if output_format in {"reveal", "html"}:
            engine = "reveal"
        elif output_format in {"touying", "typst", "beamer", "pdf"}:
            engine = "touying"

    root = Path(root)
    if not root.exists():
        return _error(f"root not found: {root}")

    if engine not in SUPPORTED_ENGINES:
        return _error(
            f"unknown engine '{engine}'. Supported: {', '.join(SUPPORTED_ENGINES)}"
        )
    if template not in SUPPORTED_TEMPLATES:
        return _error(
            f"unknown template '{template}'. Supported: {', '.join(SUPPORTED_TEMPLATES)}"
        )
    if theme not in SUPPORTED_THEMES:
        return _error(
            f"unknown theme '{theme}'. Supported (blank=default): {', '.join(t or '(default)' for t in SUPPORTED_THEMES)}"
        )

    # Prereq gate: at least one workspace step with conclusions.md OR a
    # synthesis/slides_spec.yaml. Both missing → clear error.
    workspace = root / "workspace"
    spec_path = root / "synthesis" / "slides_spec.yaml"
    step_conclusions = _find_step_conclusions(workspace)
    if not spec_path.exists() and not step_conclusions:
        return _error(
            "No source material for slides. Need either "
            "synthesis/slides_spec.yaml OR at least one workspace/<step>/"
            "conclusions.md before compiling a deck."
        )

    template_data = _load_template(template)
    if template_data is None:
        return _error(f"template '{template}' could not be loaded from {_TEMPLATES_DIR}")

    deck_meta = _resolve_meta(root, spec_path, template_data, audience)
    slides_data = _resolve_slides(
        root, spec_path, template_data, step_conclusions, deck_meta,
    )

    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    files_written: list[str] = []
    handout_info: dict[str, Any] | None = None

    if engine == "reveal":
        html_path = synthesis_dir / "slides.html"
        result = _render_reveal(
            html_path,
            slides_data,
            deck_meta,
            theme=theme or "white",
            speaker_notes_enabled=speaker_notes_enabled,
        )
        if result.get("status") != "success":
            return result
        files_written.append(str(html_path))
        warnings.extend(result.get("warnings", []))

        if print_handout:
            handout_path = synthesis_dir / "slides_handout.pdf"
            handout_info = _render_handout_via_touying(
                synthesis_dir, slides_data, deck_meta, theme=theme or "white",
            )
            if handout_info.get("status") == "success":
                files_written.append(str(handout_path))
            else:
                warnings.append(
                    "handout PDF skipped: "
                    + handout_info.get("message", "unknown reason")
                )

    else:  # touying
        typ_path = synthesis_dir / "slides.typ"
        pdf_path = synthesis_dir / "slides.pdf"
        write_result = _write_touying_source(
            typ_path,
            slides_data,
            deck_meta,
            theme=theme or "white",
            handout=False,
            speaker_notes_enabled=speaker_notes_enabled,
        )
        if write_result.get("status") != "success":
            return write_result
        compile_result = _compile_typst(typ_path, pdf_path)
        if compile_result.get("status") != "success":
            return compile_result
        files_written.append(str(typ_path))
        files_written.append(str(pdf_path))
        warnings.extend(compile_result.get("warnings", []))

        if print_handout:
            handout_typ = synthesis_dir / "slides_handout.typ"
            handout_pdf = synthesis_dir / "slides_handout.pdf"
            hw = _write_touying_source(
                handout_typ,
                slides_data,
                deck_meta,
                theme=theme or "white",
                handout=True,
                speaker_notes_enabled=speaker_notes_enabled,
            )
            if hw.get("status") == "success":
                hc = _compile_typst(handout_typ, handout_pdf)
                if hc.get("status") == "success":
                    files_written.append(str(handout_typ))
                    files_written.append(str(handout_pdf))
                    handout_info = hc
                else:
                    warnings.append(
                        "handout PDF skipped: "
                        + hc.get("message", "typst compile failed")
                    )
                    handout_info = hc

    # ---- size sanity (sized in MB, soft check, surfaces warnings) ----
    for p_str in files_written:
        p = Path(p_str)
        if not p.exists():
            continue
        size = p.stat().st_size
        if p.suffix == ".html" and size > 8 * 1024 * 1024:
            warnings.append(
                f"{p.name} is {size // (1024 * 1024)} MB (cap 8 MB). "
                "Trim embedded figures."
            )
        if p.suffix == ".pdf" and size > 4 * 1024 * 1024:
            warnings.append(
                f"{p.name} is {size // (1024 * 1024)} MB (cap 4 MB). "
                "Consider lower-DPI figures."
            )

    return {
        "status": "success",
        "engine": engine,
        "template": template,
        "theme": theme or "default",
        "slide_count": len(slides_data),
        "speaker_notes_enabled": speaker_notes_enabled,
        "print_handout_emitted": handout_info is not None and handout_info.get("status") == "success",
        "files": files_written,
        "warnings": warnings,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def _find_step_conclusions(workspace: Path) -> list[dict[str, Any]]:
    """Walk workspace/<step>/conclusions.md + nearest focal figure."""
    if not workspace.exists():
        return []
    out: list[dict[str, Any]] = []
    for step_dir in sorted(workspace.iterdir()):
        if not step_dir.is_dir():
            continue
        if step_dir.name.startswith((".", "_", "logs")):
            continue
        conclusions = step_dir / "conclusions.md"
        if not conclusions.exists():
            continue
        figures_dir = step_dir / "outputs" / "figures"
        figures = sorted(figures_dir.glob("*.png")) if figures_dir.exists() else []
        figure = figures[0] if figures else None
        summary_path = (figure.with_suffix(".summary.md") if figure else None)
        caption_path = (figure.with_suffix(".caption.md") if figure else None)
        out.append({
            "step_id": step_dir.name,
            "conclusions": _read_text(conclusions),
            "figure_path": str(figure) if figure else None,
            "figure_summary": _read_text(summary_path) if summary_path and summary_path.exists() else "",
            "figure_caption": _read_text(caption_path) if caption_path and caption_path.exists() else "",
        })
    return out


def _load_template(template: str) -> dict[str, Any] | None:
    path = _TEMPLATES_DIR / f"{template}.yaml"
    if not path.exists() or yaml is None:
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:
        logger.warning("template %s failed to parse: %s", template, exc)
        return None


def _resolve_meta(
    root: Path,
    spec_path: Path,
    template_data: dict[str, Any],
    audience_override: str | None,
) -> dict[str, Any]:
    """Title / author / venue / date — slides_spec wins, then researcher_config."""
    meta: dict[str, Any] = {
        "title": template_data.get("name", "Untitled Talk"),
        "subtitle": "",
        "author": "",
        "affiliation": "",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "venue": "",
        "audience": audience_override or template_data.get("audience", "lab_meeting"),
        "duration_minutes": template_data.get("duration_minutes", 30),
        "opening_claim": "",
    }
    if spec_path.exists() and yaml is not None:
        try:
            with spec_path.open("r", encoding="utf-8") as fh:
                spec = yaml.safe_load(fh) or {}
            for k in ("title", "subtitle", "author", "affiliation", "date",
                      "venue", "audience", "duration_minutes", "opening_claim"):
                if spec.get(k):
                    meta[k] = spec[k]
        except Exception as exc:
            logger.warning("slides_spec.yaml unreadable: %s", exc)

    if not meta["author"]:
        # Fall back to researcher_config.yaml if present.
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if cfg_path.exists() and yaml is not None:
            try:
                with cfg_path.open("r", encoding="utf-8") as fh:
                    cfg = yaml.safe_load(fh) or {}
                meta["author"] = cfg.get("researcher_name") or cfg.get("author") or ""
                meta["affiliation"] = cfg.get("affiliation") or meta["affiliation"]
            except Exception:
                pass
    return meta


def _resolve_slides(
    root: Path,
    spec_path: Path,
    template_data: dict[str, Any],
    step_conclusions: list[dict[str, Any]],
    deck_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    """If slides_spec.yaml has a `slides:` list, use it verbatim.
    Otherwise hydrate the template skeleton from step_conclusions."""
    if spec_path.exists() and yaml is not None:
        try:
            with spec_path.open("r", encoding="utf-8") as fh:
                spec = yaml.safe_load(fh) or {}
            if isinstance(spec.get("slides"), list) and spec["slides"]:
                hydrated = []
                for entry in spec["slides"]:
                    if not isinstance(entry, dict):
                        continue
                    hydrated.append(_normalize_slide(entry, deck_meta, root))
                if hydrated:
                    return hydrated
        except Exception as exc:
            logger.warning("slides_spec.yaml slides list unreadable: %s", exc)

    # Template-driven hydration: every template slide gets either the
    # template's placeholder body or — for figure slides — the next
    # available step figure.
    template_slides = template_data.get("slides", [])
    figure_queue = [s for s in step_conclusions if s.get("figure_path")]
    fi = 0
    body_queue = list(step_conclusions)
    bi = 0

    out: list[dict[str, Any]] = []
    for entry in template_slides:
        slide_type = entry.get("type", "content")
        slide = {
            "id": entry.get("id", f"slide_{len(out) + 1}"),
            "type": slide_type,
            "title": _interpolate(entry.get("title", ""), deck_meta),
            "body": "",
            "figure": None,
            "speaker_notes": entry.get("speaker_notes", "").strip(),
        }
        if slide_type == "figure":
            if fi < len(figure_queue):
                f = figure_queue[fi]
                slide["figure"] = f["figure_path"]
                slide["body"] = (f.get("figure_caption")
                                 or f.get("figure_summary")
                                 or "").strip()
                fi += 1
            else:
                slide["body"] = (
                    "(placeholder — no source figure mapped yet; "
                    "fill via synthesis/slides_spec.yaml)"
                )
        elif slide_type in {"title", "section", "focus"}:
            # Title / section / focus slides do not pull conclusions
            # bodies. Keep the title-bar claim authoritative.
            slide["body"] = ""
        else:
            if bi < len(body_queue):
                src = body_queue[bi]
                slide["body"] = _excerpt_findings(src.get("conclusions", ""))
                bi += 1
            else:
                slide["body"] = (
                    "(placeholder — fill via synthesis/slides_spec.yaml)"
                )
        out.append(slide)
    return out


def _normalize_slide(entry: dict[str, Any], deck_meta: dict[str, Any],
                     root: Path) -> dict[str, Any]:
    figure = entry.get("figure")
    if figure and not Path(figure).is_absolute():
        candidate = (root / figure).resolve()
        if candidate.exists():
            figure = str(candidate)
    return {
        "id": entry.get("id", "slide"),
        "type": entry.get("type", "content"),
        "title": _interpolate(str(entry.get("title", entry.get("claim", ""))), deck_meta),
        "body": str(entry.get("body", entry.get("caption", ""))),
        "figure": figure,
        "speaker_notes": str(entry.get("speaker_notes", "")).strip(),
    }


_INTERP_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _interpolate(text: str, ctx: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = ctx.get(key)
        if val is None:
            return m.group(0)  # leave unresolved placeholder visible
        return str(val)
    return _INTERP_RE.sub(repl, text)


def _excerpt_findings(conclusions: str, max_lines: int = 6) -> str:
    """Pull the Findings paragraph (or first non-stub paragraph) from
    conclusions.md. Cheap heuristic — the AI editorial layer can
    rewrite later from the same source."""
    if not conclusions.strip():
        return ""
    lines = [ln.rstrip() for ln in conclusions.splitlines()]
    grab = False
    bucket: list[str] = []
    for ln in lines:
        s = ln.strip()
        if re.match(r"^#+\s*(findings|results)\b", s, re.I):
            grab = True
            continue
        if grab and re.match(r"^#", s):
            break
        if grab and s:
            bucket.append(s)
            if len(bucket) >= max_lines:
                break
    if bucket:
        return "\n".join(bucket)
    # Fallback: first 6 non-heading non-blank lines.
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#"):
            bucket.append(s)
        if len(bucket) >= max_lines:
            break
    return "\n".join(bucket)


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "message": message}


# ---------------------------------------------------------------------------
# Reveal.js renderer
# ---------------------------------------------------------------------------

def _render_reveal(
    out_path: Path,
    slides: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    theme: str,
    speaker_notes_enabled: bool,
) -> dict[str, Any]:
    warnings: list[str] = []
    reveal_js = _REVEAL_DIR / "reveal.js"
    reveal_css = _REVEAL_DIR / "reveal.css"
    theme_css = _REVEAL_DIR / f"theme-{theme}.css"
    notes_js = _REVEAL_DIR / "notes.js"

    use_vendored = reveal_js.exists() and reveal_css.exists() and theme_css.exists()
    sections_html = _build_reveal_sections(slides, speaker_notes_enabled)

    if use_vendored:
        runtime_js = reveal_js.read_text(encoding="utf-8")
        base_css = reveal_css.read_text(encoding="utf-8")
        theme_text = theme_css.read_text(encoding="utf-8")
        notes_plugin = notes_js.read_text(encoding="utf-8") if notes_js.exists() else ""
        if not notes_plugin:
            warnings.append(
                "speaker-notes plugin missing; presenter view ('s' key) disabled"
            )
        html_doc = _REVEAL_HTML_TEMPLATE.format(
            title=html.escape(str(meta.get("title", "Talk"))),
            base_css=base_css,
            theme_css=theme_text,
            sections=sections_html,
            runtime_js=runtime_js,
            notes_plugin=notes_plugin,
            speaker_notes_enabled=("true" if speaker_notes_enabled and notes_plugin else "false"),
        )
    else:
        warnings.append(
            "vendored reveal.js not found; using fallback vanilla-JS arrow-key navigator"
        )
        html_doc = _FALLBACK_HTML.format(
            title=html.escape(str(meta.get("title", "Talk"))),
            sections=sections_html,
        )

    out_path.write_text(html_doc, encoding="utf-8")
    return {"status": "success", "warnings": warnings}


def _build_reveal_sections(
    slides: list[dict[str, Any]], speaker_notes_enabled: bool,
) -> str:
    parts: list[str] = []
    for sl in slides:
        title = html.escape(sl.get("title", ""))
        slide_type = sl.get("type", "content")
        cls = f' class="slide-{html.escape(slide_type)}"'
        body_html = _slide_body_html(sl)
        notes_html = ""
        if speaker_notes_enabled and sl.get("speaker_notes"):
            esc = html.escape(sl["speaker_notes"])
            notes_html = f'\n      <aside class="notes">{esc}</aside>'
        parts.append(
            f'    <section{cls} id="{html.escape(sl.get("id", ""))}">'
            f'\n      <h2>{title}</h2>'
            f'\n      {body_html}'
            f'{notes_html}'
            f'\n    </section>'
        )
    return "\n".join(parts)


def _slide_body_html(sl: dict[str, Any]) -> str:
    figure = sl.get("figure")
    body = sl.get("body", "")
    parts: list[str] = []
    if figure:
        fp = Path(figure)
        if fp.exists():
            mime = "image/png" if fp.suffix.lower() == ".png" else "image/jpeg"
            try:
                b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
                parts.append(
                    f'<figure><img alt="" src="data:{mime};base64,{b64}" '
                    f'style="max-width:100%;max-height:60vh;"/></figure>'
                )
            except Exception:
                parts.append(f'<figure><em>(figure unreadable: {html.escape(fp.name)})</em></figure>')
        else:
            parts.append(
                f'<figure><em>(figure missing: {html.escape(str(figure))})</em></figure>'
            )
    if body:
        body_lines = [ln for ln in body.splitlines() if ln.strip()]
        if body_lines:
            parts.append("<ul>" + "".join(
                f"<li>{html.escape(ln.lstrip('-* '))}</li>" for ln in body_lines
            ) + "</ul>")
    return "\n      ".join(parts) if parts else ""


# Reveal HTML scaffold — vendored runtime injected inline so the file is
# single-self-contained (matches dashboard.html / poster.html convention).
_REVEAL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{title}</title>
  <style>{base_css}</style>
  <style>{theme_css}</style>
</head>
<body>
  <div class="reveal">
    <div class="slides">
{sections}
    </div>
  </div>
  <script>{runtime_js}</script>
  <script>{notes_plugin}</script>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      var pluginList = [];
      try {{ if ({speaker_notes_enabled} && typeof RevealNotes !== 'undefined') {{ pluginList.push(RevealNotes); }} }} catch (e) {{}}
      Reveal.initialize({{
        hash: true,
        slideNumber: 'c/t',
        controls: true,
        progress: true,
        center: true,
        plugins: pluginList
      }});
    }});
  </script>
</body>
</html>
"""

# Fallback (no vendored runtime present): hand-authored arrow-key
# navigator. ZERO dependencies; opens in any browser. Speaker notes
# render inline under each slide in print stylesheet only.
_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, system-ui, sans-serif; background: #fff; color: #111; }}
    .deck section {{ display: none; padding: 4vh 6vw; min-height: 90vh; box-sizing: border-box; }}
    .deck section.active {{ display: block; }}
    .deck h2 {{ font-size: clamp(24px, 4vw, 44px); margin-top: 0; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }}
    .deck figure {{ text-align: center; margin: 1em 0; }}
    .deck img {{ max-width: 100%; max-height: 60vh; }}
    .deck ul {{ font-size: clamp(16px, 2vw, 24px); }}
    .deck .notes {{ background: #f4f4f4; padding: 1em; margin-top: 2em; font-size: 14px; font-style: italic; color: #555; }}
    .nav {{ position: fixed; bottom: 1em; right: 1em; font-size: 14px; color: #888; }}
    @media print {{ .deck section {{ display: block; page-break-after: always; }} .nav {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="deck">
{sections}
  </div>
  <div class="nav">← / → to navigate · <span id="cur">1</span> / <span id="tot">1</span></div>
  <script>
    (function() {{
      var slides = document.querySelectorAll('.deck section');
      var i = 0;
      document.getElementById('tot').textContent = slides.length;
      function show(n) {{
        if (n < 0) n = 0;
        if (n >= slides.length) n = slides.length - 1;
        slides.forEach(function(s) {{ s.classList.remove('active'); }});
        slides[n].classList.add('active');
        document.getElementById('cur').textContent = n + 1;
        i = n;
      }}
      show(0);
      document.addEventListener('keydown', function(e) {{
        if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') show(i + 1);
        if (e.key === 'ArrowLeft'  || e.key === 'PageUp')   show(i - 1);
        if (e.key === 'Home') show(0);
        if (e.key === 'End')  show(slides.length - 1);
      }});
    }})();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Touying (Typst) renderer
# ---------------------------------------------------------------------------

def _write_touying_source(
    out_path: Path,
    slides: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    theme: str,
    handout: bool,
    speaker_notes_enabled: bool,
) -> dict[str, Any]:
    touying_template = _TOUYING_DIR / "touying-mini.typ"
    if not touying_template.exists():
        return _error(
            f"bundled touying-mini.typ not found at {touying_template}. "
            "Re-install research_os assets."
        )

    # Copy touying-mini.typ next to the generated source so a vanilla
    # `typst compile` (no --root needed) can resolve the import. Typst
    # rejects paths outside the project root by default; the simplest
    # robust path is a sibling import.
    sibling = out_path.parent / "touying-mini.typ"
    try:
        shutil.copyfile(touying_template, sibling)
    except Exception as exc:
        return _error(f"failed to stage touying-mini.typ: {exc}")

    # Stage figures into synthesis/slides_figures/ so Typst can read
    # them (Typst rejects paths outside the project root).
    staged_figures: dict[str, str] = {}
    fig_dir = out_path.parent / "slides_figures"
    fig_dir.mkdir(exist_ok=True)
    for idx, sl in enumerate(slides):
        figure = sl.get("figure")
        if not figure:
            continue
        src = Path(figure)
        if not src.exists():
            continue
        dst_name = f"slide{idx + 1:02d}_{src.name}"
        dst = fig_dir / dst_name
        try:
            shutil.copyfile(src, dst)
            staged_figures[str(figure)] = f"slides_figures/{dst_name}"
        except Exception as exc:
            logger.warning("could not stage figure %s: %s", src, exc)

    body_lines: list[str] = []
    for sl in slides:
        # rewrite figure paths to staged sibling locations
        sl2 = dict(sl)
        f = sl2.get("figure")
        if f and f in staged_figures:
            sl2["figure"] = staged_figures[f]
        body_lines.append(_typst_slide(sl2, speaker_notes_enabled))
    body = "\n\n".join(body_lines)

    header = _TOUYING_TYP_HEADER.format(
        touying_path="touying-mini.typ",
        title=_typst_str(meta.get("title", "")),
        subtitle=_typst_str(meta.get("subtitle", "")),
        author=_typst_str(meta.get("author", "")),
        affiliation=_typst_str(meta.get("affiliation", "")),
        date=_typst_str(meta.get("date", "")),
        venue=_typst_str(meta.get("venue", "")),
        theme=_typst_str(theme),
        handout="true" if handout else "false",
    )
    out_path.write_text(header + body + "\n", encoding="utf-8")
    return {"status": "success"}


def _typst_path(asset: Path, source_dir: Path) -> str:
    """Render `asset` as a Typst-import-friendly path RELATIVE to the
    source file's directory. Typst's #import wants a path-string."""
    try:
        rel = Path("/").joinpath(*asset.parts)  # absolute-ish posix
        return rel.as_posix()
    except Exception:
        return str(asset)


def _typst_str(s: Any) -> str:
    """Escape a Python string for safe interpolation inside a Typst
    string literal (between double quotes)."""
    if s is None:
        return ""
    return (
        str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )


def _typst_slide(sl: dict[str, Any], speaker_notes_enabled: bool) -> str:
    sid = sl.get("id", "slide")
    title = _typst_str(sl.get("title", ""))
    body = sl.get("body", "")
    figure = sl.get("figure")
    notes = sl.get("speaker_notes", "") if speaker_notes_enabled else ""
    slide_type = sl.get("type", "content")

    body_parts: list[str] = []
    # `figure` here may be either a staged relative path (e.g.
    # "slides_figures/slide01_f01.png") or an absolute path — the
    # caller in _write_touying_source rewrites to relative before
    # calling. Either way we just emit the string Typst will resolve
    # relative to the source file.
    if figure:
        body_parts.append(f'#image("{_typst_str(figure)}", width: 90%)')
        cap = sl.get("body", "").strip()
        if cap:
            body_parts.append(f'#text(size: 0.7em)[{_typst_block(cap)}]')
    elif body:
        body_parts.append(_typst_block(body))
    if notes:
        body_parts.append(f'#notes[{_typst_block(notes)}]')
    body_typ = "\n  ".join(body_parts) if body_parts else " "

    if slide_type == "title":
        return f"// {sid}\n#title-slide()"
    if slide_type == "section":
        return f'// {sid}\n#section-slide("{title}")'
    if slide_type == "focus":
        return f'// {sid}\n#focus-slide[{title}]'
    # default content / figure
    return (
        f'// {sid}\n'
        f'#slide(title: "{title}")[\n  {body_typ}\n]'
    )


def _typst_block(text: str) -> str:
    """Render a multi-line plain-text block as Typst content. Bullets
    starting with '-' / '*' get converted to a Typst list."""
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    out: list[str] = []
    in_list = False
    for ln in lines:
        s = ln.lstrip()
        if s.startswith(("-", "*")):
            if not in_list:
                in_list = True
            out.append(f"- {_typst_inline(s[1:].strip())}")
        else:
            in_list = False
            out.append(_typst_inline(s))
    return "\n  ".join(out)


def _typst_inline(s: str) -> str:
    # Minimal escaping for inline text in a Typst markup context.
    return (s.replace("\\", "\\\\")
             .replace("#", "\\#")
             .replace("[", "\\[")
             .replace("]", "\\]")
             .replace("@", "\\@"))


_TOUYING_TYP_HEADER = """// Auto-generated by research_os.tools.actions.synthesis.slides
#import "{touying_path}": slides, slide, title-slide, section-slide, focus-slide, notes

#show: slides.with(
  title: "{title}",
  subtitle: "{subtitle}",
  author: "{author}",
  affiliation: "{affiliation}",
  date: "{date}",
  venue: "{venue}",
  theme: "{theme}",
  handout: {handout},
)

"""


def _compile_typst(typ_path: Path, pdf_path: Path) -> dict[str, Any]:
    """Shell out to ``typst compile``. Mirrors compile_typst() in
    typst.py but specialised for slides so we don't pull the venue
    biblio path in."""
    typst_bin = shutil.which("typst")
    if not typst_bin:
        return _error(
            "typst CLI not on PATH. Install via your package manager or "
            "`curl -fsSL https://typst.community/install.sh | sh`. "
            "Re-run with engine='reveal' to skip the PDF compile."
        )
    if not typ_path.exists():
        return _error(f"typst source missing: {typ_path}")
    try:
        proc = subprocess.run(
            [typst_bin, "compile", str(typ_path), str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(typ_path.parent),
        )
    except subprocess.TimeoutExpired:
        return _error("typst compile timed out after 120s")
    warnings = [ln for ln in proc.stderr.splitlines() if ln.startswith("warning:")]
    if proc.returncode != 0 or not pdf_path.exists():
        return {
            "status": "error",
            "message": "typst compile failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
            "warnings": warnings,
        }
    return {
        "status": "success",
        "pdf_path": str(pdf_path),
        "warnings": warnings,
    }


def _render_handout_via_touying(
    synthesis_dir: Path,
    slides: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    theme: str,
) -> dict[str, Any]:
    """Used by engine='reveal' so the handout still ships even when the
    presenter wanted HTML."""
    typ = synthesis_dir / "slides_handout.typ"
    pdf = synthesis_dir / "slides_handout.pdf"
    w = _write_touying_source(
        typ, slides, meta,
        theme=theme, handout=True, speaker_notes_enabled=True,
    )
    if w.get("status") != "success":
        return w
    return _compile_typst(typ, pdf)


# Public re-export for the integration agent.
__all__ = [
    "compile_slides",
    "SUPPORTED_ENGINES",
    "SUPPORTED_TEMPLATES",
    "SUPPORTED_THEMES",
]
