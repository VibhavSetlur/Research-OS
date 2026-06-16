// Generic two-column journal fallback. The default if researcher_config
// doesn't pick a venue. Clean, conservative, prints well.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

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
  set text(font: "New Computer Modern", size: 10pt, lang: "en")

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


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto generic_two_column above so a
// venue-independent author file can write
//   #import "_typst_templates/generic_two_column.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(generic_two_column)
