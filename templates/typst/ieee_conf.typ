// IEEE conference — IEEEtran-style two-column, Times Roman.

#import "common.typ": author-block, abstract-block, default-figure-show

#let ieee_conf(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.0cm, bottom: 2.0cm, left: 1.6cm, right: 1.6cm),
  )
  set par(justify: true, leading: 0.5em)
  set text(font: ("Times New Roman", "Times"), size: 10pt, lang: "en")

  align(center)[
    #text(size: 18pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => align(center)[
    #text(size: 11pt, weight: "bold")[#upper(it.body)]
  ]
  show heading.where(level: 2): it => text(size: 10.5pt, weight: "bold", style: "italic")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.6cm, body)
}
