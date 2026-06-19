// Generic two-column journal fallback. The default if researcher_config
// doesn't pick a venue. Clean, conservative, prints well.

// Consume the shared RO design tokens (ro-fonts / ro-typescale / ro-navy)
// from common.typ so the paper reads as ONE document with the figures,
// poster, slides, and dashboard. Sizes resolve to the same values they were
// hardcoded to (title 16pt, h1 12pt, body 10pt); H1 headings now carry the
// RO navy accent instead of plain black (the deliberate cohesion change).
#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template, ro-fonts, ro-typescale, ro-navy

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
  set text(font: ro-fonts.serif, size: ro-typescale.body, lang: "en")

  align(center)[
    #text(size: ro-typescale.title-compact, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: ro-typescale.h1, weight: "bold", fill: ro-navy)[#it.body]
  show heading.where(level: 2): it => text(size: ro-typescale.h2, weight: "bold", style: "italic")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.7cm, body)
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto generic_two_column above so a
// venue-independent author file can write
//   #import "_typst_templates/generic_two_column.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(generic_two_column)
