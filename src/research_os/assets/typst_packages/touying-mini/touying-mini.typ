// touying-mini.typ
//
// Minimal Touying-compatible Typst slides template shipped with Research-OS.
// Supports the API surface needed by compile_slides(engine="touying"):
//
//   #import "touying-mini.typ": slides, slide, title-slide, section-slide, focus-slide, notes
//
//   #show: slides.with(
//     title: "My Talk",
//     subtitle: "...",
//     author: "Vibhav Setlur",
//     date: "2026-06-05",
//     theme: "white",  // "white" | "black"
//   )
//
//   #title-slide()
//   #slide(title: "Motivation")[ ... ]
//   #section-slide("Method")
//   #focus-slide[ One big sentence. ]
//   #notes[Speaker notes — printed only on handout.]
//
// Two compile modes:
//   * default — 16:9 slide deck
//   * handout — pass `handout: true` to `slides`; compresses to 2-up A4 print.
//
// This is intentionally small. It does NOT implement Touying transitions,
// stepwise reveals, or themes beyond white/black. A project that outgrows
// it can migrate to upstream Touying without rewriting slide bodies.

#let _theme-colors(theme) = if theme == "black" {
  (bg: rgb("#0b0b0b"), fg: rgb("#f4f4f4"), accent: rgb("#36c"))
} else {
  (bg: rgb("#ffffff"), fg: rgb("#111111"), accent: rgb("#36c"))
}

#let slides(
  title: "Untitled Talk",
  subtitle: "",
  author: "",
  affiliation: "",
  date: "",
  venue: "",
  theme: "white",
  handout: false,
  body,
) = {
  let c = _theme-colors(theme)
  set document(title: title, author: author)
  set page(
    paper: if handout { "a4" } else { "presentation-16-9" },
    margin: if handout { (x: 0.75in, y: 0.6in) } else { (x: 0.6in, y: 0.5in) },
    fill: c.bg,
  )
  set text(font: "New Computer Modern Sans", fill: c.fg, size: if handout { 11pt } else { 22pt })
  set par(justify: false, leading: 0.65em)
  // expose meta to inner slides
  state("touying.title").update(title)
  state("touying.subtitle").update(subtitle)
  state("touying.author").update(author)
  state("touying.affiliation").update(affiliation)
  state("touying.date").update(date)
  state("touying.venue").update(venue)
  state("touying.theme").update(theme)
  state("touying.handout").update(handout)
  body
}

#let title-slide() = {
  context {
    let title = state("touying.title").get()
    let subtitle = state("touying.subtitle").get()
    let author = state("touying.author").get()
    let affiliation = state("touying.affiliation").get()
    let date = state("touying.date").get()
    let venue = state("touying.venue").get()
    page[
      #align(center + horizon)[
        #text(size: 36pt, weight: "bold")[#title]
        #if subtitle != "" [
          #v(0.4em)
          #text(size: 20pt)[#subtitle]
        ]
        #v(1em)
        #text(size: 18pt)[#author]
        #if affiliation != "" [ \ #text(size: 14pt)[#affiliation] ]
        #if venue != "" [ \ #v(0.5em) #text(size: 14pt, style: "italic")[#venue] ]
        #if date != "" [ \ #v(0.5em) #text(size: 14pt)[#date] ]
      ]
    ]
  }
}

#let slide(title: none, body) = {
  page[
    #if title != none [
      #text(size: 26pt, weight: "bold")[#title]
      #v(0.4em)
      #line(length: 100%, stroke: 0.5pt)
      #v(0.6em)
    ]
    #body
  ]
}

#let section-slide(title) = {
  page[
    #align(center + horizon)[
      #text(size: 32pt, weight: "bold")[#title]
    ]
  ]
}

#let focus-slide(body) = {
  page[
    #align(center + horizon)[
      #text(size: 28pt, weight: "bold")[#body]
    ]
  ]
}

// Speaker notes — hidden in slide mode, rendered as small grey block
// under the slide title in handout mode.
#let notes(body) = {
  context {
    let handout = state("touying.handout").get()
    if handout {
      block(fill: luma(240), inset: 8pt, radius: 4pt, width: 100%)[
        #text(size: 9pt, style: "italic", fill: luma(70))[Speaker notes:]
        #v(0.3em)
        #text(size: 9pt, fill: luma(70))[#body]
      ]
    }
  }
}
