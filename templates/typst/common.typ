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

// ---------------------------------------------------------------------------
// Uniform venue-agnostic entry point.
//
// Every paper-style venue exports a `conf(..)` normaliser plus a `template`
// binding so a venue-independent file can do:
//
//   #import "_typst_templates/<venue>.typ": template, conf
//   #show: template.with(conf(title: [..], authors: (..), abstract: [..]))
//
// `conf` accepts the relaxed shapes a generic author file uses (authors as a
// list of `(name:, affiliation:)` dicts, a singular `author:`, a `subtitle:`,
// etc.) and returns ONLY the keys every venue function accepts — `title`,
// `authors` (strings), `affiliations` (strings), `abstract` — so the dict
// spreads cleanly onto any venue's main function.
// ---------------------------------------------------------------------------

#let conf(
  title: "Untitled",
  authors: ("Anonymous",),
  affiliations: (),
  abstract: "",
  // Relaxed aliases tolerated from generic author files; folded in below.
  author: none,
  subtitle: none,
) = {
  // Fold a singular `author:` into the authors list.
  let auths = authors
  if author != none {
    auths = if type(author) == array { author } else { (author,) }
  }

  // Authors may arrive as plain strings or as `(name:, affiliation:)` dicts.
  // Split into parallel name + affiliation lists; collect distinct, non-empty
  // affiliations so the venue's author-block renders them once.
  let names = ()
  let affs = if type(affiliations) == array { affiliations } else { (affiliations,) }
  for a in auths {
    if type(a) == dictionary {
      names.push(a.at("name", default: ""))
      let af = a.at("affiliation", default: "")
      if af != "" and not affs.contains(af) {
        affs.push(af)
      }
    } else {
      names.push(a)
    }
  }
  if names.len() == 0 {
    names = ("Anonymous",)
  }

  (
    title: title,
    authors: names,
    affiliations: affs,
    abstract: abstract,
  )
}

// Build a `template` binding for a venue from its main function. The returned
// value is used as `#show: template.with(conf(..))`: the normalised config
// dict spreads onto the venue function, then the document body follows.
#let make-template(venue-fn) = (config, body) => venue-fn(..config, body)
