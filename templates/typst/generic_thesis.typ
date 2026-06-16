// Generic thesis — single-column, TOC + chapter-style headings, generous
// margins (binding edge wide).

#import "common.typ": author-block, abstract-block, default-figure-show, conf, make-template

#let generic_thesis(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 1.0in, bottom: 1.0in, left: 1.5in, right: 1.0in),
    numbering: "1",
  )
  set par(justify: true, leading: 0.7em, first-line-indent: 1em)
  set text(font: ("Linux Libertine", "Times New Roman", "Times"), size: 11pt, lang: "en")

  align(center)[
    #v(2in)
    #text(size: 22pt, weight: "bold")[#title]
    #v(20pt)
  ]
  author-block(authors, affiliations)
  v(20pt)
  abstract-block(abstract, kind: "block")
  pagebreak()

  // Auto-generated TOC.
  outline(title: [Contents], indent: 0.5em, depth: 3)
  pagebreak()

  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    set text(size: 18pt, weight: "bold")
    it.body
    v(10pt)
  }
  show heading.where(level: 2): it => {
    set text(size: 13pt, weight: "bold")
    it.body
  }
  show figure: default-figure-show

  body
}


// Uniform venue-agnostic entry point. `conf` (re-exported from common.typ)
// normalises the config; `template` maps it onto generic_thesis above so a
// venue-independent author file can write
//   #import "_typst_templates/generic_thesis.typ": template, conf
//   #show: template.with(conf(..))
#let template = make-template(generic_thesis)
