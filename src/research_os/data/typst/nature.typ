// Nature journal — 3-column, sans-serif body, abstract in a top panel.
// Title is enforced ≤ 140 characters at compile (paragraph error).

#import "common.typ": author-block, abstract-block, default-figure-show

#let nature(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "a4",
    margin: (top: 2.2cm, bottom: 2.2cm, left: 1.8cm, right: 1.8cm),
    columns: 1,
  )
  set par(justify: true, leading: 0.55em, first-line-indent: 0pt)
  set text(font: "New Computer Modern Sans", size: 9.5pt, lang: "en")

  // Title block (single column).
  align(center)[
    #text(size: 18pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "panel")

  // Body: two columns from here.
  show heading.where(level: 1): it => {
    set text(size: 11pt, weight: "bold")
    upper(it.body)
    v(2pt)
  }
  show heading.where(level: 2): it => {
    set text(size: 10pt, weight: "bold")
    it.body
    v(1pt)
  }
  show heading.where(level: 3): it => {
    set text(size: 9.5pt, weight: "bold", style: "italic")
    it.body
  }
  show figure: default-figure-show

  columns(2, gutter: 0.7cm, body)
}
