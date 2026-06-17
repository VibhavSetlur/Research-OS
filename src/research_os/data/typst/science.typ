// Science magazine — two-column, condensed serif body, condensed title.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let science(
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
  set text(font: "New Computer Modern", size: 9pt, lang: "en")

  align(center)[
    #text(size: 16pt, weight: "bold")[#title]
  ]
  v(5pt)
  author-block(authors, affiliations)
  v(8pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 11pt, weight: "bold")[#it.body]
  show heading.where(level: 2): it => text(size: 10pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.6cm, body)
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto science above so a
// venue-independent author file can write
//   #import "_typst_templates/science.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(science)
