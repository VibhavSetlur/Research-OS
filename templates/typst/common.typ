// Shared helpers used by every venue template.
//
// Each venue template imports this file, then composes a #show: <venue>.with()
// function that customises page geometry, fonts, heading rules, figure
// captions, and the bibliography style.
//
// Usage from a venue template:
//
//   #import "common.typ": author-block, abstract-block, default-figure-show
//
//   #let nature(title: "", authors: (), affiliations: (), abstract: "", body) = {
//     set page(...)
//     set text(...)
//     ...emit title + authors + abstract...
//     body
//   }

#let author-block(authors, affiliations) = {
  // Single-line authors when short; comma-separated.
  set text(size: 10pt, weight: "regular")
  align(center)[
    #authors.map(a => [#a]).join(", ")
  ]
  if affiliations.len() > 0 {
    v(2pt)
    align(center)[
      #set text(size: 8.5pt, style: "italic")
      #affiliations.map(a => [#a]).join("; ")
    ]
  }
}

#let abstract-block(abstract, kind: "block") = {
  if abstract == none or abstract == "" {
    return
  }
  if kind == "panel" {
    rect(
      stroke: (top: 0.5pt, bottom: 0.5pt),
      inset: (top: 6pt, bottom: 6pt, left: 0pt, right: 0pt),
      width: 100%,
    )[
      #set text(size: 9.5pt)
      *Abstract.* #abstract
    ]
  } else if kind == "structured" {
    text(size: 9.5pt)[
      *Background.* #abstract
    ]
  } else {
    text(size: 10pt)[
      *Abstract.* #abstract
    ]
  }
  v(8pt)
}

#let default-figure-show(it) = {
  align(center)[
    #it.body
    #v(4pt)
    #text(size: 9pt)[
      *#it.supplement #it.counter.display():* #it.caption.body
    ]
  ]
}
