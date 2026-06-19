// PLOS ONE — single-column with abstract above.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template, ro-navy

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
  set text(font: "New Computer Modern Sans", size: 10pt, lang: "en")

  align(left)[
    #text(size: 18pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 12pt, weight: "bold", fill: ro-navy)[#it.body]
  show heading.where(level: 2): it => text(size: 11pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  body
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto plos above so a
// venue-independent author file can write
//   #import "_typst_templates/plos.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(plos)
