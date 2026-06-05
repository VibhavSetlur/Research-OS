# Venue templates (Typst)

Research OS ships ten venue templates for Typst-based PDF compilation
via `tool_paper_compile_typst`. Each template imports `common.typ`
and exposes a `#show: <venue>.with(title:, authors:, affiliations:,
abstract:, ...)` function that the generated `synthesis/paper.typ`
calls into.

Pick the venue via `researcher_config.yaml`:

```yaml
writing_preferences:
  venue_template: "nature"         # see table below
  pdf_compile_engine: "typst"
```

or override at compile time:

```
tool_paper_compile_typst(venue="nature")
```

## Available templates

| Template | Layout | Body font | Paper | Citation style | Notes |
|---|---|---|---|---|---|
| `nature` | 2-column inside one A4 page, abstract panel | Helvetica 9.5pt | A4 | `nature` | Helvetica title, ALL-CAPS section headings. |
| `science` | 2-column US-letter | Times 9pt | US-letter | `ieee` | Condensed serif. |
| `nejm` | Single-column US-letter, structured abstract | Times 10pt | US-letter | `vancouver` | Wider margins, first-line indent. |
| `cell` | 2-column US-letter, abstract panel | Helvetica 9.5pt | US-letter | `ieee` | Blue (#1a5276) section headings. |
| `ieee_conf` | 2-column US-letter | Times 10pt | US-letter | `ieee` | IEEE-style centered ALL-CAPS section headings. |
| `neurips` | Single-column US-letter, 1.5″ margins | Computer Modern 10pt | US-letter | `apa` | Generous margins match the LaTeX class. |
| `acl` | 2-column US-letter | Times 10pt | US-letter | `apa` | ACL-anthology look. |
| `plos` | Single-column US-letter, left-aligned title | Arial 10pt | US-letter | `ieee` | Slate-blue section headings. |
| `generic_two_column` | 2-column US-letter | Linux Libertine 10pt | US-letter | `apa` | Default fallback. |
| `generic_thesis` | Single-column, TOC, chapter headings | Linux Libertine 11pt | US-letter | `apa` | Auto outline, page numbering, generous binding-edge margin. |

## How rendering works

1. `tool_paper_compile_typst` reads `synthesis/paper.md`.
2. `md_to_typst()` translates Markdown → Typst (headings, bold/italic,
   code, links, images, tables, lists, footnotes, Pandoc-style
   citations).
3. The chosen venue template + `common.typ` are copied into
   `synthesis/_typst_templates/` so the generated `paper.typ` can
   `#import` them with a relative path that survives editing.
4. `workspace/citations.md` → `synthesis/biblio.yml` via Hayagriva
   (forgiving parser: each paragraph is one entry with `@key` plus
   `title:`, `author:`, `year:`, `journal:`, `doi:`, etc.).
5. `typst compile synthesis/paper.typ synthesis/paper.pdf` runs;
   warnings + parsed errors are surfaced in the tool's return value.

## Customising a template

Each template is a small `.typ` file in `templates/typst/` (source
checkout) or `src/research_os/data/typst/` (installed package).
A template is just a `#let venue(...)` function — the structure
mirrors `generic_two_column.typ`:

```typst
#import "common.typ": author-block, abstract-block, default-figure-show

#let my_venue(title: "Untitled", authors: ("Anonymous",), affiliations: (),
              abstract: "", body) = {
  set page(paper: "us-letter", margin: 2cm)
  set par(justify: true, leading: 0.6em)
  set text(font: "Times New Roman", size: 10pt)
  align(center)[#text(size: 16pt, weight: "bold")[#title]]
  author-block(authors, affiliations)
  abstract-block(abstract)
  show heading.where(level: 1): it => text(weight: "bold")[#it.body]
  show figure: default-figure-show
  body
}
```

To add a new venue, drop a `.typ` file into `templates/typst/`,
add its slug to `VENUE_TEMPLATES` in
`src/research_os/tools/actions/synthesis/typst.py`, and optionally
map it to a citation style in `VENUE_CITATION_STYLE`. Rebuild
embeddings (`python scripts/build_embeddings.py`) so the router
picks up the new option.

## Falling back to LaTeX

The LaTeX path (`tool_latex_compile`) is preserved for venues that
require `.tex` submission. Set `pdf_compile_engine: "latex"` in
`researcher_config.yaml` to make `tool_synthesize` emit the LaTeX
target alongside the Markdown.
