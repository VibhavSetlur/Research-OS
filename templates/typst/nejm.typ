// New England Journal of Medicine — structured abstract, Vancouver citations.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let nejm(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.5cm, bottom: 2.5cm, left: 2.0cm, right: 2.0cm),
  )
  set par(justify: true, leading: 0.65em, first-line-indent: 1em)
  set text(font: ("Times New Roman", "Times"), size: 10pt, lang: "en")

  align(center)[
    #text(size: 16pt, weight: "bold")[#title]
  ]
  v(8pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "structured")

  show heading.where(level: 1): it => text(size: 12pt, weight: "bold")[#upper(it.body)]
  show heading.where(level: 2): it => text(size: 11pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  body
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto nejm above so a
// venue-independent author file can write
//   #import "_typst_templates/nejm.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(nejm)
