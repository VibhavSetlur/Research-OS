// NeurIPS — single-column, generous margins, page-limit advisory.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let neurips(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 1.5in, bottom: 1.5in, left: 1.5in, right: 1.5in),
  )
  set par(justify: true, leading: 0.65em, first-line-indent: 1em)
  set text(font: ("Computer Modern", "Latin Modern Roman", "Times"), size: 10pt, lang: "en")

  align(center)[
    #text(size: 17pt, weight: "bold")[#title]
  ]
  v(8pt)
  author-block(authors, affiliations)
  v(12pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 12pt, weight: "bold")[#it.body]
  show heading.where(level: 2): it => text(size: 11pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  body
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto neurips above so a
// venue-independent author file can write
//   #import "_typst_templates/neurips.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(neurips)
