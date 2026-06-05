// Cell Press — graphical-abstract-friendly two-column, IEEE citations.

#import "common.typ": author-block, abstract-block, default-figure-show

#let cell(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.0cm, bottom: 2.0cm, left: 1.8cm, right: 1.8cm),
  )
  set par(justify: true, leading: 0.55em)
  set text(font: ("Helvetica", "Arial"), size: 9.5pt, lang: "en")

  align(center)[
    #text(size: 17pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(8pt)
  abstract-block(abstract, kind: "panel")

  show heading.where(level: 1): it => text(size: 11pt, weight: "bold", fill: rgb("#1a5276"))[#upper(it.body)]
  show heading.where(level: 2): it => text(size: 10pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.7cm, body)
}
