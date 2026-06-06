"""Dashboard v2 — humanities-pack section renderer.

Surfaces humanities-research artefacts on the v2 dashboard that the
generic STEM renderer doesn't know how to display:

* **Apparatus criticus table** — line / lemma / variant / witnesses /
  editorial decision, pulled from ``workspace/edition/apparatus.md``
  (or the close-reading apparatus under ``workspace/close_readings/``).
* **Close-reading anchors** — every interpretive claim with its line /
  folio / page locator, sourced from
  ``workspace/close_readings/<slug>_apparatus.md``.
* **Critical conversation map** — the secondary-criticism ledger:
  who has read this passage before, where, and where the current
  reading agrees or departs. Pulled from
  ``workspace/citations/chain_<slug>.md``.
* **Manuscript witness list** — sigla + repository + folios sourced
  from ``workspace/edition/stemma.md`` / ``collation_<work_id>.md``.

Every section degrades gracefully: missing artefacts produce a stub
that names the file the protocol would have written, so reviewers
see the slot exists. The renderer never raises — exceptions are
caught at the section level.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# HTML helpers
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
        f'<section class="ro-section" id="{anchor}" data-tags="humanities,{anchor}">'
        f'<h2>{_escape(title)}</h2>'
        f'<p><em>{_escape(note)}</em></p>'
        f'</section>'
    )


def _read_text_safe(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError as exc:
        logger.debug("humanities: read failed %s: %s", path, exc)
        return ""


# ──────────────────────────────────────────────────────────────────────
# Apparatus criticus parser
# ──────────────────────────────────────────────────────────────────────

# Apparatus markdown commonly uses one of two shapes:
#   1. A markdown table with headers like Line / Lemma / Variant / Witnesses.
#   2. Per-entry blocks: "**1.5** lemma] variant1 W1 W2; variant2 W3".
# We parse table rows when a table is present, else best-effort.

_MD_TABLE_ROW = re.compile(r"^\|(.+?)\|\s*$")
_MD_TABLE_SEP = re.compile(r"^\|[\s:|-]+\|\s*$")

# `1.5 lemma] var1 W1, W2 ; var2 W3`  (line, lemma, variants)
_LEMMA_BLOCK = re.compile(
    r"^\s*(?:[\*_]{0,2})\s*"
    r"(?P<line>\d+(?:[.:]\d+)?(?:[a-z])?)"
    r"(?:[\*_]{0,2})\s+"
    r"(?P<lemma>[^\]]+?)\]\s*(?P<variants>.+?)$",
    re.MULTILINE,
)


def _parse_apparatus_md(text: str) -> list[dict[str, str]]:
    """Best-effort apparatus parser. Returns a list of row dicts with
    keys ``line``, ``lemma``, ``variant``, ``witnesses``, ``decision``."""
    rows: list[dict[str, str]] = []
    if not text:
        return rows
    # 1. Markdown table mode
    lines = text.splitlines()
    in_table = False
    headers: list[str] = []
    for i, line in enumerate(lines):
        if _MD_TABLE_ROW.match(line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                # Possibly a header row; the next line should be a separator.
                if i + 1 < len(lines) and _MD_TABLE_SEP.match(lines[i + 1]):
                    headers = [c.lower() for c in cells]
                    in_table = True
                continue
            # Body row
            if _MD_TABLE_SEP.match(line):
                continue
            row = {}
            for h, v in zip(headers, cells):
                row[h] = v
            mapped = {
                "line": row.get("line") or row.get("loc") or row.get("anchor") or "",
                "lemma": row.get("lemma") or row.get("text") or "",
                "variant": row.get("variant") or row.get("reading") or row.get("variants") or "",
                "witnesses": row.get("witnesses") or row.get("sigla") or row.get("mss") or "",
                "decision": row.get("decision") or row.get("note") or row.get("editor") or "",
            }
            if any(mapped.values()):
                rows.append(mapped)
        else:
            in_table = False
    if rows:
        return rows
    # 2. Per-entry block mode
    for m in _LEMMA_BLOCK.finditer(text):
        variants_raw = m.group("variants").strip()
        # Try to split witnesses off the variant body by ALL-CAPS sigla.
        wit_match = re.search(r"\s+([A-Z][A-Z0-9.,\s]+)$", variants_raw)
        witnesses = wit_match.group(1).strip() if wit_match else ""
        variant = (variants_raw[:wit_match.start()].strip()
                   if wit_match else variants_raw)
        rows.append({
            "line": m.group("line"),
            "lemma": m.group("lemma").strip(),
            "variant": variant,
            "witnesses": witnesses,
            "decision": "",
        })
    return rows


def _find_apparatus_files(root: Path) -> list[Path]:
    """Locate apparatus files. Order: edition first, then close-readings."""
    out: list[Path] = []
    edition_app = root / "workspace" / "edition" / "apparatus.md"
    if edition_app.exists():
        out.append(edition_app)
    cr_dir = root / "workspace" / "close_readings"
    if cr_dir.is_dir():
        for p in sorted(cr_dir.iterdir()):
            if p.is_file() and p.name.endswith("_apparatus.md"):
                out.append(p)
    return out


def _build_apparatus_section(root: Path) -> str:
    files = _find_apparatus_files(root)
    if not files:
        return _stub_section(
            "hum-apparatus", "Apparatus criticus",
            "No workspace/edition/apparatus.md or close-reading apparatus "
            "files found. Complete humanities/output/scholarly_edition or "
            "humanities/textual/close_reading to produce one.",
        )
    blocks: list[str] = []
    total_rows = 0
    for ap in files:
        rows = _parse_apparatus_md(_read_text_safe(ap))
        if not rows:
            blocks.append(
                '<details><summary>'
                f'{_escape(ap.relative_to(root))}'
                ' <em>(no parseable entries)</em></summary>'
                '<pre style="white-space:pre-wrap;font-size:12px">'
                + _escape(_read_text_safe(ap, 4000)) +
                '</pre></details>'
            )
            continue
        total_rows += len(rows)
        headers = ["line", "lemma", "variant", "witnesses", "decision"]
        head_html = "".join(f"<th>{h}</th>" for h in headers)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{_escape(r.get(h, ''))}</td>"
                              for h in headers) + "</tr>"
            for r in rows
        )
        blocks.append(
            f'<h3>{_escape(ap.relative_to(root))} '
            f'<small class="muted">({len(rows)} entries)</small></h3>'
            f'<table class="ro-table-static apparatus-table">'
            f'<thead><tr>{head_html}</tr></thead>'
            f'<tbody>{body_html}</tbody></table>'
        )
    return (
        '<section class="ro-section" id="hum-apparatus" '
        'data-tags="humanities,apparatus">'
        f'<h2>Apparatus criticus '
        f'<small class="muted">({total_rows} entries across '
        f'{len(files)} file{"s" if len(files) != 1 else ""})</small></h2>'
        + "".join(blocks) +
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Close-reading anchors
# ──────────────────────────────────────────────────────────────────────

# Numbered claims with line anchors: "1. (1.5) The pattern enacts..."
# or                                  "1. [folio 12r] The marginalia..."
_ANCHOR_CLAIM = re.compile(
    r"^\s*(?P<num>\d+)\.\s*"
    r"(?:[\(\[])"
    r"(?P<anchor>[^\)\]]+)"
    r"(?:[\)\]])\s*"
    r"(?P<text>.+?)\s*$",
    re.MULTILINE,
)


def _build_close_reading_section(root: Path) -> str:
    cr_dir = root / "workspace" / "close_readings"
    if not cr_dir.is_dir():
        return _stub_section(
            "hum-close-reading", "Close-reading anchors",
            "No workspace/close_readings/ directory. Run "
            "humanities/textual/close_reading to produce annotation files.",
        )
    apparatus_files = sorted(
        p for p in cr_dir.iterdir()
        if p.is_file() and p.name.endswith("_apparatus.md")
    )
    if not apparatus_files:
        return _stub_section(
            "hum-close-reading", "Close-reading anchors",
            "Close-readings directory exists but no *_apparatus.md files "
            "found. The write_apparatus step of close_reading produces these.",
        )
    cards: list[str] = []
    for ap in apparatus_files:
        text = _read_text_safe(ap)
        claims = list(_ANCHOR_CLAIM.finditer(text))
        passage_slug = ap.stem.replace("_apparatus", "")
        if not claims:
            cards.append(
                '<div class="close-reading-card">'
                f'<h3>{_escape(passage_slug)}</h3>'
                '<p class="muted"><em>No numbered anchored claims parsed. '
                'Apparatus may not follow the "1. (line) text" shape.</em></p>'
                '</div>'
            )
            continue
        rows = "".join(
            "<tr>"
            f"<td>{_escape(m.group('num'))}</td>"
            f"<td>{_escape(m.group('anchor'))}</td>"
            f"<td>{_escape(m.group('text'))}</td>"
            "</tr>"
            for m in claims
        )
        cards.append(
            '<div class="close-reading-card" '
            f'id="hum-close-reading-{_slug(passage_slug)}">'
            f'<h3>{_escape(passage_slug)} '
            f'<small class="muted">({len(claims)} anchored claims)</small></h3>'
            '<table class="ro-table-static close-reading-anchors">'
            '<thead><tr><th>#</th><th>anchor</th><th>claim</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            '</div>'
        )
    return (
        '<section class="ro-section" id="hum-close-reading" '
        'data-tags="humanities,close-reading">'
        '<h2>Close-reading anchors</h2>'
        + "".join(cards) +
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Critical conversation map (citation chains)
# ──────────────────────────────────────────────────────────────────────

# Heading-extractor for chain files; chains use "## Reader", "## Source",
# "## Witness", "## Transformation" headings per the citation_chains
# protocol.
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _build_critical_conversation_section(root: Path) -> str:
    cit_dir = root / "workspace" / "citations"
    if not cit_dir.is_dir():
        return _stub_section(
            "hum-critical-conversation", "Critical conversation map",
            "No workspace/citations/ directory. Run "
            "humanities/citation/citation_chains or source_provenance "
            "to build the secondary-criticism ledger.",
        )
    chain_files = sorted(
        p for p in cit_dir.iterdir()
        if p.is_file() and p.name.startswith("chain_") and p.suffix == ".md"
    )
    if not chain_files:
        return _stub_section(
            "hum-critical-conversation", "Critical conversation map",
            "No chain_<slug>.md files found under workspace/citations/. "
            "Each load-bearing quotation should have a chain file.",
        )
    cards: list[str] = []
    for ch in chain_files:
        text = _read_text_safe(ch, 20_000)
        headings = [m.group(1).strip() for m in _H2.finditer(text)]
        slug = ch.stem.replace("chain_", "")
        # Surface first few paragraphs verbatim for context.
        snippet = text.strip()[:1500]
        head_html = ""
        if headings:
            head_html = (
                '<ul class="chain-headings">'
                + "".join(f"<li>{_escape(h)}</li>" for h in headings[:20])
                + '</ul>'
            )
        cards.append(
            '<div class="chain-card" '
            f'id="hum-chain-{_slug(slug)}">'
            f'<h3>{_escape(slug)}</h3>'
            + head_html +
            '<pre style="white-space:pre-wrap;font-size:12px">'
            + _escape(snippet) +
            '</pre></div>'
        )
    return (
        '<section class="ro-section" id="hum-critical-conversation" '
        'data-tags="humanities,citation-chains">'
        f'<h2>Critical conversation map '
        f'<small class="muted">({len(chain_files)} chains)</small></h2>'
        + "".join(cards) +
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Manuscript witness list
# ──────────────────────────────────────────────────────────────────────

# Sigla lines in stemma.md typically look like:
#   "A = Paris, BnF, MS lat. 1234 (s. xii)"
#   "B — London, BL, Harley 5678, ff. 1r–24v"
_SIGLA_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<siglum>[A-Z][A-Za-z0-9]?)\s*[=:—–-]\s*(?P<rest>.+?)\s*$",
    re.MULTILINE,
)


def _build_witness_section(root: Path) -> str:
    stemma = root / "workspace" / "edition" / "stemma.md"
    edition_dir = root / "workspace" / "edition"
    collation_files: list[Path] = []
    if edition_dir.is_dir():
        collation_files = sorted(
            p for p in edition_dir.iterdir()
            if p.is_file() and p.name.startswith("collation_")
            and p.suffix == ".md"
        )
    sources: list[Path] = []
    if stemma.exists():
        sources.append(stemma)
    sources.extend(collation_files)
    if not sources:
        return _stub_section(
            "hum-witnesses", "Manuscript witnesses",
            "No workspace/edition/stemma.md or collation_<work_id>.md. "
            "Run humanities/output/scholarly_edition to produce one.",
        )
    witnesses: list[tuple[str, str, str]] = []  # (siglum, description, source)
    seen_sigla: set[str] = set()
    for src in sources:
        text = _read_text_safe(src)
        for m in _SIGLA_LINE.finditer(text):
            siglum = m.group("siglum").strip()
            rest = m.group("rest").strip()
            if siglum in seen_sigla:
                continue
            seen_sigla.add(siglum)
            witnesses.append((siglum, rest, src.name))
    if not witnesses:
        return (
            '<section class="ro-section" id="hum-witnesses" '
            'data-tags="humanities,witnesses">'
            '<h2>Manuscript witnesses</h2>'
            '<p class="muted">Found edition files but no parseable sigla. '
            'Showing source contents instead.</p>'
            + "".join(
                f'<details><summary>{_escape(s.relative_to(root))}</summary>'
                '<pre style="white-space:pre-wrap;font-size:12px">'
                + _escape(_read_text_safe(s, 4000)) +
                '</pre></details>'
                for s in sources
            ) +
            '</section>'
        )
    headers = ["siglum", "description", "source"]
    head_html = "".join(f"<th>{h}</th>" for h in headers)
    body_html = "".join(
        f"<tr><td><strong>{_escape(s)}</strong></td>"
        f"<td>{_escape(d)}</td>"
        f"<td>{_escape(src)}</td></tr>"
        for s, d, src in witnesses
    )
    return (
        '<section class="ro-section" id="hum-witnesses" '
        'data-tags="humanities,witnesses">'
        f'<h2>Manuscript witnesses '
        f'<small class="muted">({len(witnesses)} sigla)</small></h2>'
        f'<table class="ro-table-static witness-table">'
        f'<thead><tr>{head_html}</tr></thead>'
        f'<tbody>{body_html}</tbody></table>'
        '</section>'
    )


# ──────────────────────────────────────────────────────────────────────
# Top-level renderer
# ──────────────────────────────────────────────────────────────────────


def render_humanities_section(
    root: Path,
    spec: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    """Return the concatenated humanities-pack HTML block."""
    root = Path(root)
    parts: list[str] = []
    for builder in (
        _build_apparatus_section,
        _build_close_reading_section,
        _build_critical_conversation_section,
        _build_witness_section,
    ):
        try:
            parts.append(builder(root))
        except Exception as exc:
            logger.exception("humanities section %s failed", builder.__name__)
            parts.append(
                '<section class="ro-section" '
                f'id="hum-error-{_slug(builder.__name__)}" '
                'data-tags="humanities,error">'
                f'<h2>{_escape(builder.__name__)}</h2>'
                f'<p><em>Renderer failed: {_escape(exc)}</em></p>'
                '</section>'
            )
    return "".join(parts)


__all__ = [
    "render_humanities_section",
    "_build_apparatus_section",
    "_build_close_reading_section",
    "_build_critical_conversation_section",
    "_build_witness_section",
]
