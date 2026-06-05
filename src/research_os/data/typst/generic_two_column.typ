// Generic two-column journal fallback. The default if researcher_config
// doesn't pick a venue. Clean, conservative, prints well.

#import "common.typ": author-block, abstract-block, default-figure-show

#let generic_two_column(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.2cm, bottom: 2.2cm, left: 1.8cm, right: 1.8cm),
  )
  set par(justify: true, leading: 0.6em)
  set text(font: ("Linux Libertine", "Times New Roman", "Times"), size: 10pt, lang: "en")

  align(center)[
    #text(size: 16pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 11pt, weight: "bold")[#it.body]
  show heading.where(level: 2): it => text(size: 10.5pt, weight: "bold", style: "italic")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.7cm, body)
}
