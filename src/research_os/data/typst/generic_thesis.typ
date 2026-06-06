// Generic thesis — single-column, TOC + chapter-style headings, generous
// margins (binding edge wide).

#import "common.typ": author-block, abstract-block, default-figure-show

#let generic_thesis(
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
  )
  set par(justify: true, leading: 0.7em, first-line-indent: 1em)
  // Body font: bundled NCM serif. Fallbacks (Linux Libertine, Times) are
  // omitted to avoid Typst font-cascade warnings on systems where those
  // families are not installed; the bundled NCM is always present via
  // the --font-path injected by compile_typst().
  set text(font: "New Computer Modern", size: 11pt, lang: "en")

  align(center)[
    #v(2in)
    #text(size: 22pt, weight: "bold")[#title]
    #v(20pt)
  ]
  author-block(authors, affiliations)
  v(20pt)
  abstract-block(abstract, kind: "block")
  pagebreak()

  // Auto-generated TOC.
  outline(title: [Contents], indent: 0.5em, depth: 3)
  pagebreak()

  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    set text(size: 18pt, weight: "bold")
    it.body
    v(10pt)
  }
  show heading.where(level: 2): it => {
    set text(size: 13pt, weight: "bold")
    it.body
  }
  show figure: default-figure-show

  body
}
