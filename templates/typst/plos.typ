// PLOS ONE — single-column with abstract above.

#import "common.typ": author-block, abstract-block, default-figure-show

#let plos(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.2cm, bottom: 2.2cm, left: 2.0cm, right: 2.0cm),
  )
  set par(justify: true, leading: 0.6em)
  set text(font: ("Arial", "Helvetica"), size: 10pt, lang: "en")

  align(left)[
    #text(size: 18pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 12pt, weight: "bold", fill: rgb("#33526a"))[#it.body]
  show heading.where(level: 2): it => text(size: 11pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  body
}
