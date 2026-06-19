"""Typst-native PDF compilation for synthesis/paper.md.

Markdown → Typst translation + venue-specific template injection + Hayagriva
citations. Typst is the recommended PDF path; the LaTeX path
(`tool_latex_compile`) is preserved for journals that require .tex.

Public surface:
  * md_to_typst(text, venue_template) -> str
  * citations_md_to_hayagriva(path) -> str
  * compile_typst(typst_path, pdf_path) -> dict
  * paper_compile_typst(root, paper_path, venue, output) -> dict
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.typst")


VENUE_TEMPLATES = (
    "nature", "science", "nejm", "cell", "ieee_conf",
    "neurips", "acl", "plos", "generic_two_column", "generic_thesis",
    "humanities_essay", "chicago_thesis",
)

# Map venue template → Typst built-in bibliography style identifier.
# Typst uses CSL identifiers with hyphens (e.g. "chicago-notes", NOT
# "chicago_notes_bib"); the researcher-facing config carries the
# pretty underscore form (chicago_notes_bib) and this map translates.
VENUE_CITATION_STYLE = {
    "nature": "nature",
    "science": "ieee",
    "nejm": "vancouver",
    "cell": "ieee",
    "ieee_conf": "ieee",
    "neurips": "apa",
    "acl": "apa",
    "plos": "ieee",
    "generic_two_column": "apa",
    "generic_thesis": "apa",
    # Humanities templates. Footnote-citation thesis defaults to
    # Chicago notes; the generic humanities essay defaults to MLA
    # (the modal humanities convention).
    "humanities_essay": "modern-language-association",
    "chicago_thesis": "chicago-notes",
}

# Researcher-facing citation_style → Typst CSL identifier. Used when
# the researcher sets writing_preferences.citation_style explicitly
# AND the venue template doesn't pin one.
CITATION_STYLE_TO_TYPST = {
    "apa": "apa",
    "vancouver": "vancouver",
    "acm": "ieee",                      # ACM ≅ IEEE numeric for Typst
    "ieee": "ieee",
    "nature": "nature",
    "mla": "modern-language-association",
    "chicago_author_date": "chicago-author-date",
    "chicago_notes_bib": "chicago-notes",
    # Mathematical sciences: Typst doesn't ship AMS / SIAM CSL out of
    # the box; the closest accepted built-in is springer-basic-
    # author-date for SIAM-flavoured author-date numerics, and a
    # numeric fallback for AMS plain.
    "amsplain": "ieee",
    "siam": "springer-basic-author-date",
}


# ---------------------------------------------------------------------------
# Markdown → Typst conversion
# ---------------------------------------------------------------------------


_TYPST_SPECIALS = "\\#$*_@<>[]`~"
_TYPST_ESCAPE_RE = re.compile("([" + re.escape(_TYPST_SPECIALS) + "])")


def _typst_escape(text: str) -> str:
    """Backslash-escape Typst markup specials for safe insertion into a
    content block (``[...]``).

    Title / author / affiliation / abstract values are dropped verbatim
    into ``#show: venue.with(title: [...], ...)`` content blocks. A raw
    ``$ # % @ _ *`` or an unbalanced ``[ ]`` there breaks compilation
    with a cryptic .typ error, so every Typst markup special is
    backslash-escaped here (matching how the body escapes specials).
    """
    return _TYPST_ESCAPE_RE.sub(r"\\\1", text)


def _inline_md_to_typst(text: str) -> str:
    """Convert inline markdown constructs in a single paragraph.

    Handles in order: code spans (verbatim, protected from further
    transforms), bold, italics, links, Pandoc cites, footnote refs.
    """
    # 1. Protect inline code first.
    code_spans: list[str] = []

    def _protect_code(m: re.Match[str]) -> str:
        code_spans.append(m.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _protect_code, text)

    # 2. Markdown images: ![alt](path).
    def _img(m: re.Match[str]) -> str:
        alt = m.group(1).strip()
        path = m.group(2).strip()
        cap = f", caption: [{alt}]" if alt else ""
        return f'#figure(image("{path}", width: 80%){cap})'

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img, text)

    # 3. Markdown links: [label](url).
    def _link(m: re.Match[str]) -> str:
        label = m.group(1)
        url = m.group(2)
        return f'#link("{url}")[{label}]'

    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", _link, text)

    # 4. Pandoc citations: [@key1; @key2] and [@key].
    def _multi_cite(m: re.Match[str]) -> str:
        keys = re.findall(r"@([A-Za-z0-9_:-]+)", m.group(0))
        return "".join(f"#cite(<{k}>)" for k in keys)

    text = re.sub(r"\[@[^\]]+\]", _multi_cite, text)

    # 5. Footnote references: [^N] → #footnote[N].
    text = re.sub(r"\[\^([^\]]+)\]", r"#footnote[\1]", text)

    # 6. Bold: **text** → sentinel-marked *text* so the italic pass doesn't touch it.
    bold_spans: list[str] = []

    def _protect_bold(m: re.Match[str]) -> str:
        bold_spans.append(m.group(1))
        return f"\x00BOLD{len(bold_spans) - 1}\x00"

    text = re.sub(r"\*\*([^*]+)\*\*", _protect_bold, text)

    # 7. Italics: *text* → _text_ (works because bold spans are sentinels now).
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"_\1_", text)

    # 8. Restore bold as Typst's *text*.
    def _restore_bold(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return f"*{bold_spans[idx]}*"

    text = re.sub(r"\x00BOLD(\d+)\x00", _restore_bold, text)

    # 9. Restore code spans LAST.
    def _restore_code(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return f"`{code_spans[idx]}`"

    text = re.sub(r"\x00CODE(\d+)\x00", _restore_code, text)

    return text


def _convert_table(table_lines: list[str]) -> str:
    """Convert a GitHub-style markdown table to Typst #table()."""
    rows: list[list[str]] = []
    for line in table_lines:
        line = line.strip().strip("|")
        if re.match(r"^[\s\-:|]+$", line):
            continue
        cells = [c.strip() for c in line.split("|")]
        rows.append(cells)
    if not rows:
        return ""
    n_cols = max(len(r) for r in rows)
    cell_strs: list[str] = []
    for r in rows:
        padded = r + [""] * (n_cols - len(r))
        cell_strs.extend(f"[{_inline_md_to_typst(c)}]" for c in padded)
    return f"#table(\n  columns: {n_cols},\n  " + ", ".join(cell_strs) + ",\n)"


def md_to_typst(markdown_text: str, venue_template: str = "generic_two_column",
                 researcher_orcid: str = "") -> str:
    """Convert a paper.md document to a Typst source string.

    The output starts with a `#import` of the chosen venue template and
    a `#show: <venue>.with(...)` setup, followed by the converted body.
    Math (`$...$`) is passed through verbatim — Typst's math syntax
    overlaps with LaTeX for common cases and errors gracefully on
    unsupported constructs.

    *researcher_orcid* (when supplied) is emitted as a Typst comment +
    metadata block above the venue setup so downstream tooling (and the
    rendered PDF metadata) carries the ORCID URI alongside the author.
    """
    if venue_template not in VENUE_TEMPLATES:
        venue_template = "generic_two_column"

    lines = markdown_text.splitlines()
    title = ""
    authors_raw = ""
    affiliations_raw = ""
    abstract = ""

    # Strip optional YAML frontmatter.
    if lines and lines[0].strip() == "---":
        end_idx = next(
            (i for i in range(1, len(lines)) if lines[i].strip() == "---"),
            None,
        )
        if end_idx is not None:
            fm = lines[1:end_idx]
            for fl in fm:
                if fl.lower().startswith("title:"):
                    title = fl.split(":", 1)[1].strip().strip('"').strip("'")
                elif fl.lower().startswith("author"):
                    authors_raw = fl.split(":", 1)[1].strip().strip('"').strip("'")
                elif fl.lower().startswith("affiliation"):
                    affiliations_raw = fl.split(":", 1)[1].strip().strip('"').strip("'")
                elif fl.lower().startswith("abstract:"):
                    abstract = fl.split(":", 1)[1].strip().strip('"').strip("'")
            lines = lines[end_idx + 1:]

    # The H1 (if any) supplies the title if frontmatter didn't.
    body_buf: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    para_buf: list[str] = []

    def _flush_para() -> None:
        if not para_buf:
            return
        joined = " ".join(s.strip() for s in para_buf if s.strip())
        if joined:
            body_buf.append(_inline_md_to_typst(joined))
            body_buf.append("")
        para_buf.clear()

    while i < len(lines):
        ln = lines[i]

        # Code block toggle.
        m_code = re.match(r"^```(\w*)\s*$", ln)
        if m_code and not in_code:
            _flush_para()
            in_code = True
            code_lang = m_code.group(1) or ""
            code_buf = []
            i += 1
            continue
        if in_code:
            if ln.strip() == "```":
                src = "\n".join(code_buf).replace('"', '\\"')
                lang_arg = f', lang: "{code_lang}"' if code_lang else ""
                body_buf.append(f'#raw("{src}"{lang_arg}, block: true)')
                body_buf.append("")
                in_code = False
                code_lang = ""
            else:
                code_buf.append(ln)
            i += 1
            continue

        # Blank line ends a paragraph.
        if not ln.strip():
            _flush_para()
            i += 1
            continue

        # Headings.
        m_h = re.match(r"^(#{1,6})\s+(.+?)\s*$", ln)
        if m_h:
            _flush_para()
            level = len(m_h.group(1))
            txt = _inline_md_to_typst(m_h.group(2))
            if level == 1 and not title:
                title = m_h.group(2).strip()
            elif level == 1:
                body_buf.append(f"= {txt}")
                body_buf.append("")
            else:
                body_buf.append("=" * level + " " + txt)
                body_buf.append("")
            i += 1
            continue

        # Block quote.
        if ln.startswith(">"):
            _flush_para()
            quoted = []
            while i < len(lines) and lines[i].startswith(">"):
                quoted.append(lines[i].lstrip(">").strip())
                i += 1
            body_buf.append(f"#quote[{_inline_md_to_typst(' '.join(quoted))}]")
            body_buf.append("")
            continue

        # Tables: line starts with | and next line is separator.
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(
            r"^\s*\|?[\s\-:|]+\|?\s*$", lines[i + 1]
        ):
            _flush_para()
            tbl: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            body_buf.append(_convert_table(tbl))
            body_buf.append("")
            continue

        # Bulleted / numbered list — Typst native syntax overlaps.
        if re.match(r"^\s*[-*+]\s+", ln):
            _flush_para()
            body_buf.append(_inline_md_to_typst(re.sub(r"^\s*[-*+]\s+", "- ", ln)))
            i += 1
            continue
        if re.match(r"^\s*\d+\.\s+", ln):
            _flush_para()
            body_buf.append(_inline_md_to_typst(re.sub(r"^\s*\d+\.\s+", "+ ", ln)))
            i += 1
            continue

        para_buf.append(ln)
        i += 1

    _flush_para()

    # Detect author-year prose form to preserve at the body level (no
    # conversion needed — Hayagriva renders the bibliography; the
    # in-line prose stays as it appeared in paper.md).

    body = "\n".join(body_buf).rstrip() + "\n"

    # Escape Typst markup specials — these values land RAW inside `[...]`
    # content blocks, so an unescaped `$ # @ _ *` or unbalanced `[ ]`
    # breaks compilation with a cryptic .typ error.
    title_arg = _typst_escape(title or "Untitled")
    authors_arg = _typst_escape(authors_raw or "Anonymous")
    affiliations_arg = _typst_escape(affiliations_raw or "")
    abstract_arg = _typst_escape(abstract or "")

    bibliography_style = VENUE_CITATION_STYLE.get(venue_template, "apa")
    # ORCID preamble — emitted only when researcher_config supplies one.
    # Normalised to the canonical https://orcid.org/<id> URI form so it
    # is dereferenceable from the PDF metadata + share-archive crawls.
    orcid_uri = (researcher_orcid or "").strip()
    if orcid_uri and not orcid_uri.startswith("http"):
        orcid_uri = f"https://orcid.org/{orcid_uri}"
    orcid_preamble = (
        f'// ORCID: {orcid_uri}\n'
        f'#metadata((orcid: "{orcid_uri}")) <author-orcid>\n\n'
        if orcid_uri else ""
    )
    header = (
        f'{orcid_preamble}'
        f'#import "../templates/typst/{venue_template}.typ": {venue_template}\n\n'
        f'#show: {venue_template}.with(\n'
        f'  title: [{title_arg}],\n'
        f'  authors: ([{authors_arg}],),\n'
        f'  affiliations: ([{affiliations_arg}],),\n'
        f'  abstract: [{abstract_arg}],\n'
        f')\n\n'
    )
    bibliography = (
        f'\n#bibliography("biblio.yml", style: "{bibliography_style}")\n'
    )
    return header + body + bibliography


# ---------------------------------------------------------------------------
# Citations: workspace/citations.md → Hayagriva YAML
# ---------------------------------------------------------------------------


def citations_md_to_hayagriva(citations_md_path: Path) -> str:
    """Parse workspace/citations.md → Hayagriva YAML string.

    Accepts a forgiving format: each entry is a paragraph starting
    with a citation key (either `@key` or `[@key]` or `<key>` or bare
    `key:` on its own line), followed by free-form metadata lines:
        title: ...
        author: ...
        year: 2024
        journal: ...
        doi: ...
        url: ...

    Entries that can't be parsed are skipped (logged).
    """
    if not citations_md_path.exists():
        return ""
    text = citations_md_path.read_text(encoding="utf-8", errors="replace")

    # Block separator: two or more newlines, or a leading "## " heading.
    raw_blocks: list[list[str]] = []
    cur: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("## "):
            if cur:
                raw_blocks.append(cur)
            cur = []
            continue
        if not line.strip():
            if cur:
                raw_blocks.append(cur)
                cur = []
            continue
        cur.append(line.rstrip())
    if cur:
        raw_blocks.append(cur)

    entries: list[str] = []
    seen_keys: set[str] = set()
    for block in raw_blocks:
        key = None
        meta: dict[str, str] = {}
        for j, ln in enumerate(block):
            if j == 0:
                # First line: try to extract a citation key.
                m = re.search(r"@([A-Za-z][\w:.-]+)", ln)
                if not m:
                    m = re.match(r"^\s*([A-Za-z][\w:.-]+)\s*[:.]?\s*", ln)
                if m:
                    key = m.group(1)
                # Pull any inline title from the rest of the line.
                rest = re.sub(r"^[#*]?\s*[\[(<]?@?[A-Za-z][\w:.-]+[\])>]?\s*[:.]?\s*", "", ln).strip()
                if rest and "title" not in meta:
                    meta["title"] = rest.rstrip(".")
                continue
            m_kv = re.match(r"^\s*([A-Za-z_-]+)\s*[:=]\s*(.+?)\s*$", ln)
            if m_kv:
                meta[m_kv.group(1).lower()] = m_kv.group(2)

        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        # Build a Hayagriva YAML block.
        lines_out = [f"{key}:"]
        ctype = meta.get("type", "article")
        lines_out.append(f"  type: {ctype}")
        if "title" in meta:
            lines_out.append(f'  title: "{_yaml_escape(meta["title"])}"')
        if "author" in meta:
            authors = [a.strip() for a in re.split(r"\s+and\s+|\s*;\s*", meta["author"]) if a.strip()]
            lines_out.append("  author:")
            for a in authors:
                lines_out.append(f'    - "{_yaml_escape(a)}"')
        if "year" in meta or "date" in meta:
            raw_date = str(meta.get("date", meta.get("year")) or "").strip()
            date_yaml = _hayagriva_date(raw_date)
            if date_yaml is not None:
                lines_out.append(f"  date: {date_yaml}")
        parent_title = meta.get("journal") or meta.get("conference") or meta.get("publisher")
        if parent_title:
            lines_out.append("  parent:")
            ptype = "periodical" if meta.get("journal") else (
                "conference" if meta.get("conference") else "publisher"
            )
            lines_out.append(f"    type: {ptype}")
            lines_out.append(f'    title: "{_yaml_escape(parent_title)}"')
            if "volume" in meta:
                lines_out.append(f'    volume: {meta["volume"]}')
            if "issue" in meta:
                lines_out.append(f'    issue: {meta["issue"]}')
        else:
            # No parent block — emit volume/issue at the top level so they
            # aren't silently dropped.
            if "volume" in meta:
                lines_out.append(f'  volume: {meta["volume"]}')
            if "issue" in meta:
                lines_out.append(f'  issue: {meta["issue"]}')
        if "page" in meta or "pages" in meta:
            lines_out.append(f'  page-range: {meta.get("pages", meta.get("page"))}')
        if "doi" in meta:
            lines_out.append(f'  doi: "{meta["doi"]}"')
        if "url" in meta:
            lines_out.append(f'  url: "{meta["url"]}"')
        entries.append("\n".join(lines_out))

    return ("\n".join(entries) + "\n") if entries else ""


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _hayagriva_date(raw: str) -> str | None:
    """Render a citation date for Hayagriva YAML.

    Hayagriva expects ``date:`` to be a bare year (``2024``) or an ISO
    date (``2024-05-01``). A non-numeric value like ``in press`` parses
    as garbage and corrupts the bibliography entry, so:
      * a plausible year / ISO value is emitted unquoted,
      * any other non-empty string is quoted (kept as a note rather
        than mis-parsed as a date),
      * an empty value is skipped (returns None).
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", raw):
        return raw
    return f'"{_yaml_escape(raw)}"'


# ---------------------------------------------------------------------------
# Typst compilation
# ---------------------------------------------------------------------------


def bundled_font_path() -> Path | None:
    """Locate the directory holding the bundled font OTF files.

    Search order: in-package ``src/research_os/assets/fonts`` (always
    present in the wheel), then walk up from the module file to find
    a repo-root copy (editable install / source checkout).

    Returns None when no bundled-font directory can be found — callers
    skip the ``--font-path`` flag in that case so Typst still works
    with whatever system fonts are installed.
    """
    here = Path(__file__).resolve()
    # In-package: src/research_os/assets/fonts (shipped in the wheel).
    pkg_root = here.parents[3]
    candidate = pkg_root / "assets" / "fonts"
    if candidate.exists() and any(candidate.glob("*.otf")):
        return candidate
    return None


def _typst_compile_argv(typst_bin: str, src: str, dst: str) -> list[str]:
    """Assemble the ``typst compile`` argv, injecting --font-path when
    the bundled NCM fonts are present. Centralised here so paper,
    poster, and slide compile paths all benefit.
    """
    argv = [typst_bin, "compile"]
    font_dir = bundled_font_path()
    if font_dir is not None:
        argv += ["--font-path", str(font_dir)]
    argv += [src, dst]
    return argv


def compile_typst(typst_source_path: Path, output_pdf_path: Path) -> dict[str, Any]:
    """Run ``typst compile <src> <pdf>``.

    Returns a structured dict with stdout/stderr + parsed errors on
    failure. Does NOT raise; callers inspect ``status``.
    """
    typst_bin = shutil.which("typst")
    if not typst_bin:
        return {
            "status": "error",
            "message": (
                "typst not found. Install via your package manager or "
                "`curl -fsSL https://typst.community/install.sh | sh`."
            ),
            "errors": [],
        }
    if not typst_source_path.exists():
        return {
            "status": "error",
            "message": f"typst source not found: {typst_source_path}",
            "errors": [],
        }

    proc = subprocess.run(
        _typst_compile_argv(typst_bin, str(typst_source_path), str(output_pdf_path)),
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(typst_source_path.parent),
    )
    parsed_errors = _parse_typst_errors(proc.stderr)
    warnings = [ln for ln in proc.stderr.splitlines() if ln.startswith("warning:")]
    if proc.returncode != 0 or not output_pdf_path.exists():
        return {
            "status": "error",
            "message": "typst compile failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
            "stdout": proc.stdout[-2000:],
            "errors": parsed_errors,
            "warnings": warnings,
        }
    return {
        "status": "success",
        "pdf_path": str(output_pdf_path),
        "warnings": warnings,
        "errors": parsed_errors,
        "stderr_tail": proc.stderr[-500:],
    }


def _parse_typst_errors(stderr: str) -> list[dict[str, Any]]:
    """Pull (line, message) pairs out of ``typst compile`` stderr."""
    out: list[dict[str, Any]] = []
    for line in stderr.splitlines():
        m = re.search(r"error:\s*(.+)", line)
        if m:
            out.append({"message": m.group(1).strip(), "line": None})
            continue
        m = re.search(r"┌─\s*(.+?):(\d+):(\d+)", line)
        if m and out:
            out[-1]["file"] = m.group(1)
            out[-1]["line"] = int(m.group(2))
            out[-1]["col"] = int(m.group(3))
    return out


# ---------------------------------------------------------------------------
# Top-level orchestration: tool_paper_compile_typst
# ---------------------------------------------------------------------------


def paper_compile_typst(
    root: Path,
    paper_path: str = "synthesis/paper.md",
    venue: str | None = None,
    output: str = "synthesis/paper.pdf",
) -> dict[str, Any]:
    """End-to-end: paper.md → paper.typ + biblio.yml → paper.pdf.

    `venue` overrides researcher_config.writing_preferences.venue_template
    when given. Defaults to ``generic_two_column`` if no config value
    is set either.
    """
    paper = root / paper_path
    if not paper.exists():
        return {
            "status": "error",
            "message": f"{paper_path} not found. Run tool_synthesize first.",
        }

    # Resolve venue + researcher ORCID from researcher_config. The ORCID
    # flows into the generated paper.typ as a #metadata block so the PDF
    # author field carries the dereferenceable ORCID URI.
    researcher_orcid = ""
    try:
        from research_os.tools.actions.state.config import get_research_config

        cfg = get_research_config(root) or {}
        if not venue:
            venue = (cfg.get("writing_preferences", {}) or {}).get(
                "venue_template", "generic_two_column"
            )
        researcher_orcid = str(
            ((cfg.get("researcher") or {}) if isinstance(cfg, dict) else {})
            .get("orcid") or ""
        ).strip()
    except Exception:
        if not venue:
            venue = "generic_two_column"
    if venue not in VENUE_TEMPLATES:
        return {
            "status": "error",
            "message": (
                f"Unknown venue '{venue}'. Known: {', '.join(VENUE_TEMPLATES)}"
            ),
        }

    synthesis_dir = root / "synthesis"
    synthesis_dir.mkdir(parents=True, exist_ok=True)

    # Templates: copy to <synthesis>/../templates/typst/ relative path
    # used inside the generated .typ so the import resolves. We resolve
    # it by copying the chosen template (and any shared helpers) into
    # <synthesis>/_typst_templates/ next to paper.typ; the generated
    # source imports from ../../templates/typst/<venue>.typ when the
    # package install has it, OR from ./_typst_templates/<venue>.typ
    # when generated standalone.
    templates_src = _find_templates_dir()
    local_templates = synthesis_dir / "_typst_templates"
    local_templates.mkdir(exist_ok=True)
    if templates_src is not None:
        for name in (f"{venue}.typ", "common.typ"):
            src = templates_src / name
            if src.exists():
                shutil.copyfile(src, local_templates / name)

    md_text = paper.read_text(encoding="utf-8", errors="replace")
    typst_text = md_to_typst(md_text, venue_template=venue,
                              researcher_orcid=researcher_orcid)
    # Rewrite the import path to point at the local templates we just copied.
    typst_text = typst_text.replace(
        f'#import "../templates/typst/{venue}.typ":',
        f'#import "_typst_templates/{venue}.typ":',
    )
    typst_path = synthesis_dir / "paper.typ"
    typst_path.write_text(typst_text, encoding="utf-8")

    # Hayagriva citations.
    citations_path = root / "workspace" / "citations.md"
    biblio_yaml = citations_md_to_hayagriva(citations_path) if citations_path.exists() else ""
    if not biblio_yaml:
        biblio_yaml = "placeholder:\n  type: misc\n  title: \"No citations\"\n"
    (synthesis_dir / "biblio.yml").write_text(biblio_yaml, encoding="utf-8")

    output_pdf = root / output
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    res = compile_typst(typst_path, output_pdf)

    # Count Pandoc citations (a count audit gates uses).
    cite_count = len(re.findall(r"\[@[^\]]+\]|#cite\(<", typst_text))

    page_count = None
    if res.get("status") == "success" and output_pdf.exists():
        # Heuristic: rough page count from PDF stream — best effort.
        try:
            data = output_pdf.read_bytes()
            page_count = data.count(b"/Type /Page") or data.count(b"/Page\n")
        except OSError:
            page_count = None

    return {
        "status": res.get("status", "error"),
        "pdf_path": str(output_pdf) if output_pdf.exists() else None,
        "typst_path": str(typst_path),
        "biblio_path": str(synthesis_dir / "biblio.yml"),
        "venue": venue,
        "page_count": page_count,
        "citation_count": cite_count,
        "typst_warnings": res.get("warnings", []),
        "typst_errors": res.get("errors", []),
        "message": res.get("message"),
    }


def _find_templates_dir() -> Path | None:
    """Locate the bundled typst templates directory.

    Search order: in-package data dir (always present in wheel),
    then walk up from the module file to find the repo-root copy
    (editable install / source checkout, where templates/typst/ also
    exists and the package-data copy may be missing during dev).
    """
    here = Path(__file__).resolve()
    # In-package: src/research_os/data/typst/ (shipped in the wheel).
    pkg_root = here.parents[3]  # .../research_os
    candidate = pkg_root / "data" / "typst"
    if candidate.exists():
        return candidate
    # Source checkout: walk up to find <repo>/templates/typst.
    for n in (3, 4, 5, 6, 7):
        try:
            candidate = here.parents[n] / "templates" / "typst"
        except IndexError:
            break
        if candidate.exists():
            return candidate
    return None
