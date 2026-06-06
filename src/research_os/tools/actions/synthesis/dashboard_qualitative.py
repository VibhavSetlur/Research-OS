"""Dashboard v2 — qualitative-pack section renderer.

Surfaces qualitative-research artefacts on the v2 dashboard that the
generic STEM-shaped renderer doesn't know how to display:

* **Codebook table** — one row per code with definition / inclusion /
  exclusion / applied_count / Cohen's kappa. Pulled from the most
  recent ``workspace/codebooks/codebook_v<N>.yaml``.
* **Themes hierarchy** — final themes + subthemes from
  ``workspace/themes/final_themes.yaml`` (or candidate themes if final
  isn't authored yet).
* **Saturation grid** — per-transcript new-code counts that show when
  the corpus stops yielding novel codes. Reads
  ``workspace/coding/initial_codes.yaml`` if present, falls back to a
  saturation curve image if one exists.
* **Member-checking log** — round-by-round summary built from
  ``workspace/member_checks/round_<N>/`` directories
  (contact_log.md, divergences.md, per-participant responses).

Every section degrades gracefully: if the artefact is missing, the
section emits a small "not yet authored" stub so reviewers know the
slot exists rather than silently hiding it. The renderer never
raises — exceptions are caught at the section level and an inline
warning replaces the section body.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# HTML helpers (local — kept in sync with dashboard_app._escape / _slug)
# ──────────────────────────────────────────────────────────────────────

def _escape(text: Any) -> str:
    s = "" if text is None else str(text)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "section"


def _stub_section(anchor: str, title: str, note: str) -> str:
    return (
        f'<section class="ro-section" id="{anchor}" data-tags="qualitative,{anchor}">'
        f'<h2>{_escape(title)}</h2>'
        f'<p><em>{_escape(note)}</em></p>'
        f'</section>'
    )


def _safe_yaml_load(path: Path) -> Any:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        logger.debug("qualitative: yaml load failed for %s: %s", path, e)
        return None


# ──────────────────────────────────────────────────────────────────────
# Codebook table
# ──────────────────────────────────────────────────────────────────────

_CODEBOOK_RE = re.compile(r"codebook_v(\d+)\.ya?ml$", re.IGNORECASE)


def _latest_codebook(root: Path) -> Path | None:
    """Return the highest-numbered codebook_v<N>.yaml under
    ``workspace/codebooks/``, or None if none exist."""
    cb_dir = root / "workspace" / "codebooks"
    if not cb_dir.is_dir():
        return None
    candidates: list[tuple[int, Path]] = []
    for p in cb_dir.iterdir():
        if not p.is_file():
            continue
        m = _CODEBOOK_RE.search(p.name)
        if m:
            try:
                candidates.append((int(m.group(1)), p))
            except ValueError:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


def _build_codebook_section(root: Path) -> str:
    cb_path = _latest_codebook(root)
    if cb_path is None:
        return _stub_section(
            "qual-codebook",
            "Codebook",
            "No workspace/codebooks/codebook_v<N>.yaml found. "
            "Run qualitative/coding/coding_scheme_iteration to build one.",
        )
    data = _safe_yaml_load(cb_path)
    if not isinstance(data, dict):
        return _stub_section(
            "qual-codebook",
            "Codebook",
            f"Codebook {cb_path.name} is malformed or empty.",
        )
    codes = data.get("codes") or data.get("entries") or []
    if not isinstance(codes, list) or not codes:
        return _stub_section(
            "qual-codebook",
            "Codebook",
            f"Codebook {cb_path.name} carries no codes yet.",
        )
    headers = ["code", "definition", "inclusion", "exclusion",
               "applied_count", "kappa"]
    head_html = "".join(f"<th>{_escape(h)}</th>" for h in headers)
    rows_html: list[str] = []
    for entry in codes:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code") or entry.get("id") or entry.get("name") or ""
        definition = entry.get("definition") or entry.get("description") or ""
        inclusion = entry.get("inclusion") or entry.get("inclusion_criteria") or ""
        exclusion = entry.get("exclusion") or entry.get("exclusion_criteria") or ""
        applied = entry.get("applied_count")
        if applied is None:
            applied = entry.get("count") or entry.get("frequency") or ""
        kappa = entry.get("kappa")
        if kappa is None:
            kappa = entry.get("cohens_kappa") or entry.get("agreement") or ""
        cells = [code, definition, inclusion, exclusion, applied, kappa]
        rows_html.append(
            "<tr>" + "".join(f"<td>{_escape(c)}</td>" for c in cells) + "</tr>"
        )
    if not rows_html:
        return _stub_section(
            "qual-codebook",
            "Codebook",
            f"Codebook {cb_path.name} has entries but none match the expected shape.",
        )
    table = (
        f'<table class="ro-table-static codebook-table">'
        f'<thead><tr>{head_html}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table>'
    )
    return (
        '<section class="ro-section" id="qual-codebook" '
        'data-tags="qualitative,codebook">'
        f'<h2>Codebook <small class="muted">({_escape(cb_path.name)})</small></h2>'
        f'<p class="muted">{len(rows_html)} codes</p>'
        f'{table}'
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Themes hierarchy
# ──────────────────────────────────────────────────────────────────────

def _build_themes_section(root: Path) -> str:
    themes_path = root / "workspace" / "themes" / "final_themes.yaml"
    candidate_md = root / "workspace" / "memos" / "candidate_themes_v1.md"
    if not themes_path.exists():
        if candidate_md.exists():
            try:
                preview = candidate_md.read_text(encoding="utf-8",
                                                 errors="ignore")[:4000]
            except OSError:
                preview = ""
            return (
                '<section class="ro-section" id="qual-themes" '
                'data-tags="qualitative,themes">'
                '<h2>Themes (candidates)</h2>'
                '<p class="muted">No <code>workspace/themes/final_themes.yaml</code> yet — '
                'showing <code>candidate_themes_v1.md</code> instead.</p>'
                '<pre style="white-space:pre-wrap;font-family:var(--mono,monospace);'
                'font-size:13px">'
                + _escape(preview) +
                '</pre></section>'
            )
        return _stub_section(
            "qual-themes", "Themes",
            "No themes file yet. Complete thematic analysis phase 5 to "
            "write workspace/themes/final_themes.yaml.",
        )
    data = _safe_yaml_load(themes_path)
    themes = None
    if isinstance(data, dict):
        themes = data.get("themes") or data.get("final_themes") or []
    elif isinstance(data, list):
        themes = data
    if not isinstance(themes, list) or not themes:
        return _stub_section(
            "qual-themes", "Themes",
            f"{themes_path.name} loaded but contains no themes.",
        )
    items: list[str] = []
    for theme in themes:
        if not isinstance(theme, dict):
            items.append(f"<li>{_escape(theme)}</li>")
            continue
        name = theme.get("name") or theme.get("title") or theme.get("id") or "Theme"
        concept = theme.get("central_organising_concept") or theme.get("concept") or ""
        definition = theme.get("definition") or theme.get("description") or ""
        subthemes = theme.get("subthemes") or theme.get("sub_themes") or []
        block = [f'<li><strong>{_escape(name)}</strong>']
        if concept:
            block.append(f' <em>— {_escape(concept)}</em>')
        if definition:
            block.append(f'<div class="theme-def">{_escape(definition)}</div>')
        if isinstance(subthemes, list) and subthemes:
            block.append('<ul class="subthemes">')
            for sub in subthemes:
                if isinstance(sub, dict):
                    sub_name = sub.get("name") or sub.get("title") or "Subtheme"
                    sub_def = sub.get("definition") or sub.get("description") or ""
                    block.append(f'<li><strong>{_escape(sub_name)}</strong>')
                    if sub_def:
                        block.append(f' — {_escape(sub_def)}')
                    block.append('</li>')
                else:
                    block.append(f'<li>{_escape(sub)}</li>')
            block.append('</ul>')
        block.append('</li>')
        items.append("".join(block))
    return (
        '<section class="ro-section" id="qual-themes" '
        'data-tags="qualitative,themes">'
        f'<h2>Themes <small class="muted">({len(items)})</small></h2>'
        f'<ul class="themes-tree">{"".join(items)}</ul>'
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Saturation grid
# ──────────────────────────────────────────────────────────────────────

def _build_saturation_section(root: Path) -> str:
    """Render a per-transcript new-codes grid and, if available, embed
    the saturation_curve.png the protocol writes at phase 6."""
    initial = root / "workspace" / "coding" / "initial_codes.yaml"
    curve_png = root / "workspace" / "figures" / "saturation_curve.png"
    rows: list[tuple[str, int, int]] = []  # (transcript_id, new_codes, cumulative)
    seen: set[str] = set()
    if initial.exists():
        data = _safe_yaml_load(initial)
        codes_iter: list[dict[str, Any]] = []
        if isinstance(data, dict):
            maybe = data.get("codes") or data.get("entries") or []
            if isinstance(maybe, list):
                codes_iter = [c for c in maybe if isinstance(c, dict)]
        elif isinstance(data, list):
            codes_iter = [c for c in data if isinstance(c, dict)]
        # Tally by transcript: codes carry `first_seen_in` or `transcripts`
        # depending on the researcher's authoring style; we accept both.
        per_transcript_new: dict[str, list[str]] = {}
        for entry in codes_iter:
            code_id = entry.get("code") or entry.get("id") or entry.get("name")
            if not code_id:
                continue
            first = entry.get("first_seen_in") or entry.get("origin_transcript")
            if not first:
                origins = entry.get("transcripts") or entry.get("sources") or []
                if isinstance(origins, list) and origins:
                    first = origins[0]
            if not first:
                continue
            per_transcript_new.setdefault(str(first), []).append(str(code_id))
        # Order transcripts lexicographically — close enough for a v2 grid.
        for t in sorted(per_transcript_new):
            novel = [c for c in per_transcript_new[t] if c not in seen]
            seen.update(novel)
            rows.append((t, len(novel), len(seen)))
    blocks: list[str] = []
    if rows:
        head = "<tr><th>transcript</th><th>new codes</th><th>cumulative</th></tr>"
        body = "".join(
            f"<tr><td>{_escape(t)}</td><td>{n}</td><td>{c}</td></tr>"
            for t, n, c in rows
        )
        blocks.append(
            f'<table class="ro-table-static saturation-grid">'
            f'<thead>{head}</thead><tbody>{body}</tbody></table>'
        )
    if curve_png.exists():
        try:
            rel = curve_png.relative_to(root / "synthesis").as_posix()
        except ValueError:
            try:
                import os as _os
                rel = _os.path.relpath(curve_png, root / "synthesis").replace("\\", "/")
            except Exception:
                rel = str(curve_png)
        blocks.append(
            f'<figure class="saturation-curve">'
            f'<img src="{_escape(rel)}" alt="saturation curve">'
            f'<figcaption>Per-transcript saturation curve.</figcaption></figure>'
        )
    if not blocks:
        return _stub_section(
            "qual-saturation", "Saturation",
            "No saturation evidence yet. Author workspace/coding/initial_codes.yaml "
            "with first_seen_in / origin_transcript fields, or render "
            "workspace/figures/saturation_curve.png.",
        )
    return (
        '<section class="ro-section" id="qual-saturation" '
        'data-tags="qualitative,saturation">'
        '<h2>Saturation</h2>'
        + "".join(blocks) +
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Member-checking log
# ──────────────────────────────────────────────────────────────────────

_ROUND_RE = re.compile(r"round_(\d+)$", re.IGNORECASE)


def _build_member_check_section(root: Path) -> str:
    base = root / "workspace" / "member_checks"
    if not base.is_dir():
        return _stub_section(
            "qual-member-checks", "Member checking",
            "No workspace/member_checks/round_<N>/ directories yet. "
            "Run qualitative/validity/member_checking to log a round.",
        )
    rounds: list[tuple[int, Path]] = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        m = _ROUND_RE.search(child.name)
        if m:
            try:
                rounds.append((int(m.group(1)), child))
            except ValueError:
                continue
    if not rounds:
        return _stub_section(
            "qual-member-checks", "Member checking",
            "Found workspace/member_checks/ but no round_<N>/ subdirectories.",
        )
    rounds.sort(key=lambda t: t[0])
    cards: list[str] = []
    for n, rdir in rounds:
        contact_log = rdir / "contact_log.md"
        divergences = rdir / "divergences.md"
        participant_count = sum(
            1 for p in rdir.iterdir() if p.is_dir()
        )
        divergence_preview = ""
        if divergences.exists():
            try:
                divergence_preview = divergences.read_text(
                    encoding="utf-8", errors="ignore"
                )[:1500]
            except OSError:
                divergence_preview = ""
        contact_preview = ""
        if contact_log.exists():
            try:
                contact_preview = contact_log.read_text(
                    encoding="utf-8", errors="ignore"
                )[:1000]
            except OSError:
                contact_preview = ""
        body = [
            f'<h3>Round {n} <small class="muted">'
            f'({participant_count} participant dir{"s" if participant_count != 1 else ""})'
            f'</small></h3>'
        ]
        if contact_preview:
            body.append('<h4>Contact log</h4>'
                        f'<pre style="white-space:pre-wrap;font-size:12px">'
                        f'{_escape(contact_preview)}</pre>')
        if divergence_preview:
            body.append('<h4>Divergences</h4>'
                        f'<pre style="white-space:pre-wrap;font-size:12px">'
                        f'{_escape(divergence_preview)}</pre>')
        if not contact_preview and not divergence_preview:
            body.append('<p class="muted">No contact_log.md or divergences.md '
                        'in this round.</p>')
        cards.append(
            '<div class="member-check-round" '
            f'id="qual-member-check-round-{n}">'
            + "".join(body) +
            '</div>'
        )
    return (
        '<section class="ro-section" id="qual-member-checks" '
        'data-tags="qualitative,member-checking">'
        '<h2>Member checking</h2>'
        + "".join(cards) +
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Top-level renderer
# ──────────────────────────────────────────────────────────────────────


def render_qualitative_section(
    root: Path,
    spec: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    """Return the concatenated qualitative-pack HTML block.

    ``spec`` and ``state`` are accepted for parity with future
    section renderers that may want them; the current implementation
    reads directly from the workspace.
    """
    root = Path(root)
    parts: list[str] = []
    for builder in (
        _build_codebook_section,
        _build_themes_section,
        _build_saturation_section,
        _build_member_check_section,
    ):
        try:
            parts.append(builder(root))
        except Exception as exc:
            logger.exception("qualitative section %s failed", builder.__name__)
            parts.append(
                '<section class="ro-section" '
                f'id="qual-error-{_slug(builder.__name__)}" '
                'data-tags="qualitative,error">'
                f'<h2>{_escape(builder.__name__)}</h2>'
                f'<p><em>Renderer failed: {_escape(exc)}</em></p>'
                '</section>'
            )
    return "".join(parts)


__all__ = [
    "render_qualitative_section",
    "_build_codebook_section",
    "_build_themes_section",
    "_build_saturation_section",
    "_build_member_check_section",
]
