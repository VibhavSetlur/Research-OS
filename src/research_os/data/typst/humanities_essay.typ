// Humanities essay — single-column, generous margins, footnote-friendly.
// Pairs with citation_style: mla | chicago_author_date | chicago_notes_bib.
//
// Conventions baked in:
//   - 1.25" margins all around (comfortable for long-form prose).
//   - 12pt serif, double-leaded (1.5 line height) — the body-text
//     density humanities reviewers expect.
//   - Footnotes in 10pt with a thin separator rule.
//   - Block-quote (set with #quote(block: true)) is single-leaded,
//     indented 0.5" left + right.
//   - Section headings are unnumbered by default (Chicago + MLA
//     prefer untyped section headings in essays — number only when
//     the work is long enough to be a thesis; for that, use
//     chicago_thesis.typ).
//   - Page numbers bottom-centre (MLA / Chicago default for essays).

#import "common.typ": author-block, abstract-block, default-figure-show

#let humanities_essay(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: 1.25in,
    numbering: "1",
    number-align: center + bottom,
  )

  // Body type: 12pt serif, 1.5 leading. Slight first-line indent for
  // paragraphs (the humanities-essay default, distinct from the
  // block-paragraph style scientific journals use).
  set text(font: ("Linux Libertine", "EB Garamond", "Times New Roman", "Times"),
           size: 12pt, lang: "en")
  set par(justify: true, leading: 0.85em, first-line-indent: 1.5em)

  // Footnotes — 10pt, marker as Arabic numerals, thin separator rule.
  set footnote.entry(
    separator: line(length: 30%, stroke: 0.4pt),
    gap: 0.5em,
    indent: 0pt,
  )
  show footnote.entry: set text(size: 10pt)

  // Block quote — single-leaded, indented, smaller text (humanities
  // convention: long quotation set off without quotation marks).
  show quote.where(block: true): it => {
    set par(leading: 0.7em, first-line-indent: 0em)
    set text(size: 11pt)
    pad(left: 0.5in, right: 0.5in, top: 0.5em, bottom: 0.5em, it.body)
  }

  // Unnumbered section headings (MLA / Chicago essay convention).
  show heading.where(level: 1): it => {
    set text(size: 14pt, weight: "bold")
    v(1em, weak: true)
    it.body
    v(0.5em, weak: true)
  }
  show heading.where(level: 2): it => {
    set text(size: 12pt, weight: "bold", style: "italic")
    v(0.7em, weak: true)
    it.body
    v(0.3em, weak: true)
  }

  // Title block — centred, no abstract by default. Pass abstract=""
  // when the venue is a short essay (most are). When the venue
  // requires an abstract (some humanities journals do), pass it and
  // it renders as a single italic paragraph below the byline.
  align(center)[
    #v(1.5in)
    #text(size: 18pt, weight: "bold")[#title]
    #v(0.6em)
  ]
  author-block(authors, affiliations)
  v(20pt)

  if abstract != none and abstract != "" {
    pad(left: 0.5in, right: 0.5in)[
      #set text(size: 10.5pt, style: "italic")
      #abstract
    ]
    v(15pt)
  }

  show figure: default-figure-show

  body
}
