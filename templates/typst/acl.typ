// ACL / EMNLP — two-column, ACL anthology style.

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let acl(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.0cm, bottom: 2.0cm, left: 1.7cm, right: 1.7cm),
  )
  set par(justify: true, leading: 0.55em)
  set text(font: ("Times New Roman", "Times"), size: 10pt, lang: "en")

  align(center)[
    #text(size: 16pt, weight: "bold")[#title]
  ]
  v(6pt)
  author-block(authors, affiliations)
  v(10pt)
  abstract-block(abstract, kind: "block")

  show heading.where(level: 1): it => text(size: 11pt, weight: "bold")[#it.body]
  show heading.where(level: 2): it => text(size: 10pt, weight: "bold")[#it.body]
  show figure: default-figure-show

  columns(2, gutter: 0.6cm, body)
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto acl above so a
// venue-independent author file can write
//   #import "_typst_templates/acl.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(acl)
