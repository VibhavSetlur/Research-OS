// Chicago notes + bibliography thesis — single-column, chapter-style
// headings, generous binding-edge margin, footnotes as the primary
// citation form (Chicago 17 notes & bibliography style).
//
// Pairs with citation_style: chicago_notes_bib.
//
// Conventions baked in:
//   - 1.5" binding-edge (left) + 1.0" other margins, US-letter.
//   - 12pt serif body, double-leaded (2.0 line height) — thesis
//     convention; many graduate schools mandate.
//   - Chapter headings on a new page, numbered "Chapter N".
//   - Footnotes 10pt, separator rule, footnote-marker as Arabic
//     numerals restarting each chapter (Chicago convention).
//   - Block quote: single-leaded, indented 0.5", no quote marks
//     (Chicago: long quotes "set off" without surrounding marks).
//   - TOC auto-generated. Subsequent front-matter sections
//     (Acknowledgements, Abstract, List of Figures) are added by
//     the user with #heading(level: 1) markers BEFORE the first
//     #show: chicago_thesis.with(...) chapter.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let chicago_thesis(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 1.0in, bottom: 1.0in, left: 1.5in, right: 1.0in),
    numbering: "1",
    number-align: center + bottom,
  )

  // Body type — 12pt serif, double-leaded.
  set text(font: ("Linux Libertine", "EB Garamond", "Times New Roman", "Times"),
           size: 12pt, lang: "en")
  set par(justify: true, leading: 1.0em, first-line-indent: 1.5em)

  // Footnotes — Chicago notes style. 10pt, separator rule, restart
  // numbering per chapter.
  set footnote(numbering: "1")
  set footnote.entry(
    separator: line(length: 30%, stroke: 0.4pt),
    gap: 0.5em,
    indent: 0pt,
  )
  show footnote.entry: set text(size: 10pt)

  // Block quote — single-leaded, indented, slightly smaller text.
  show quote.where(block: true): it => {
    set par(leading: 0.7em, first-line-indent: 0em)
    set text(size: 11pt)
    pad(left: 0.5in, right: 0.5in, top: 0.5em, bottom: 0.5em, it.body)
  }

  // Title page.
  align(center)[
    #v(2in)
    #text(size: 22pt, weight: "bold")[#title]
    #v(40pt)
    #text(size: 13pt)[#authors.map(a => [#a]).join(", ")]
    #if affiliations.len() > 0 {
      v(8pt)
      text(size: 11pt, style: "italic")[#affiliations.map(a => [#a]).join("; ")]
    }
  ]
  pagebreak()

  // Optional abstract page (Chicago thesis convention: abstract on
  // its own front-matter page when present).
  if abstract != none and abstract != "" {
    align(center)[#text(size: 14pt, weight: "bold")[Abstract]]
    v(15pt)
    abstract
    pagebreak()
  }

  // Auto-generated TOC.
  outline(title: [Contents], indent: 0.5em, depth: 3)
  pagebreak()

  // Chapter heading — pagebreak, "Chapter N" line, then the title.
  // Counter resets footnote numbering per Chicago convention.
  let chapter-counter = counter("chapter")
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    chapter-counter.step()
    align(center)[
      #text(size: 14pt)[Chapter #context chapter-counter.display()]
      #v(4pt)
      #text(size: 18pt, weight: "bold")[#it.body]
    ]
    v(20pt)
  }
  show heading.where(level: 2): it => {
    set text(size: 14pt, weight: "bold")
    v(1em, weak: true)
    it.body
    v(0.5em, weak: true)
  }
  show heading.where(level: 3): it => {
    set text(size: 12pt, weight: "bold", style: "italic")
    v(0.7em, weak: true)
    it.body
    v(0.3em, weak: true)
  }

  show figure: default-figure-show

  body
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto chicago_thesis above so a
// venue-independent author file can write
//   #import "_typst_templates/chicago_thesis.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(chicago_thesis)
