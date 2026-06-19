// touying-mini.typ
//
// Minimal Touying-compatible Typst slides template shipped with Research-OS.
// Supports the API surface needed by compile_slides(engine="touying"):
//
//   #import "touying-mini.typ": slides, slide, title-slide, section-slide, focus-slide, big-number-slide, quote-slide, two-column-slide, image-full-slide, notes
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
//   #big-number-slide("+5.9pp", label: "hits@10 after reranking")
//   #quote-slide[We never saw the regression coming.][Reviewer 2]
//   #two-column-slide(title: "Adopted vs ruled out")[Left col][Right col]
//   #image-full-slide("figures/hero.png", caption: "Throughput vs latency")
//   #notes[Speaker notes — printed only on handout.]
//
// Per-slide LAYOUT archetypes (pick the one that fits the slide's job; the
// arc is set by the audience, the look by the archetype):
//   slide            titled content slide (the workhorse)
//   section-slide    a divider — section title, centred
//   focus-slide      one big sentence on a full-bleed accent panel
//   big-number-slide one dominant statistic + a label (the result slide)
//   quote-slide      a centred pull-quote + attribution
//   two-column-slide left/right compare-and-contrast via a grid
//   image-full-slide a full-bleed figure with a minimal overlay caption
//
// Two compile modes:
//   * default — 16:9 slide deck
//   * handout — pass `handout: true` to `slides`; compresses to 2-up A4 print.
//
// This is intentionally small. It does NOT implement Touying transitions,
// stepwise reveals, or themes beyond white/black. A project that outgrows
// it can migrate to upstream Touying without rewriting slide bodies.

// Theme colours mirror RO_PALETTE (tools/actions/viz/style.py): the white
// theme is the RO cream identity so an embedded RO-styled figure matches the
// deck; the dark theme lightens the navy so it reads on near-black. Keep the
// accent navy in sync with the figure/poster/dashboard palette.
#let _theme-colors(theme) = if theme == "black" {
  (bg: rgb("#0b0b0b"), fg: rgb("#f4f4f4"), accent: rgb("#7FA8D4"))
} else {
  (bg: rgb("#FBF8F3"), fg: rgb("#3D3A35"), accent: rgb("#1F4D7A"))
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
    let c = _theme-colors(state("touying.theme").get())
    page[
      #align(center + horizon)[
        #text(size: 36pt, weight: "bold", fill: c.accent)[#title]
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

#let slide(title: none, body) = context {
  let c = _theme-colors(state("touying.theme").get())
  page[
    #if title != none [
      #text(size: 26pt, weight: "bold", fill: c.accent)[#title]
      #v(0.4em)
      #line(length: 100%, stroke: 1pt + c.accent)
      #v(0.6em)
    ]
    #body
  ]
}

#let section-slide(title) = context {
  let c = _theme-colors(state("touying.theme").get())
  page[
    #align(center + horizon)[
      #text(size: 32pt, weight: "bold", fill: c.accent)[#title]
    ]
  ]
}

// Focus slide — one big sentence on a full-bleed accent panel (the deck's
// punctuation mark), paper-coloured text for maximum contrast.
#let focus-slide(body) = context {
  let c = _theme-colors(state("touying.theme").get())
  page(fill: c.accent)[
    #align(center + horizon)[
      #text(size: 28pt, weight: "bold", fill: c.bg)[#body]
    ]
  ]
}

// Big-number slide — one dominant statistic + a label underneath. The
// result slide: the number does the talking, the label says what it is.
// `number` is the dominant stat (e.g. "+5.9pp", "0.91", "3.2×"); `label`
// is the supporting one-liner; optional `caption` adds a smaller gloss.
#let big-number-slide(number, label: "", caption: "") = context {
  let c = _theme-colors(state("touying.theme").get())
  page[
    #align(center + horizon)[
      #text(size: 96pt, weight: "bold", fill: c.accent)[#number]
      #if label != "" [
        #v(0.3em)
        #text(size: 26pt, fill: c.fg)[#label]
      ]
      #if caption != "" [
        #v(0.6em)
        #text(size: 16pt, style: "italic", fill: c.fg.lighten(20%))[#caption]
      ]
    ]
  ]
}

// Quote slide — a centred pull-quote with attribution. Positional args:
// the quote body, then the attribution (e.g. a person / source). The
// attribution renders smaller, right-aligned under the quote.
#let quote-slide(body, attribution) = context {
  let c = _theme-colors(state("touying.theme").get())
  page[
    #align(center + horizon)[
      #block(width: 80%)[
        #text(size: 30pt, style: "italic", fill: c.fg)[
          \u{201C}#body\u{201D}
        ]
        #if attribution != none and attribution != "" [
          #v(0.8em)
          #align(right)[
            #text(size: 18pt, fill: c.accent)[— #attribution]
          ]
        ]
      ]
    ]
  ]
}

// Two-column slide — left/right compare-and-contrast via a grid. Optional
// `title` heads the slide; `left` and `right` are the two columns (equal
// width, a gutter between). Use for adopted-vs-ruled-out, before-vs-after,
// claim-vs-evidence.
#let two-column-slide(left, right, title: none) = context {
  let c = _theme-colors(state("touying.theme").get())
  page[
    #if title != none [
      #text(size: 26pt, weight: "bold", fill: c.accent)[#title]
      #v(0.3em)
      #line(length: 100%, stroke: 1pt + c.accent)
      #v(0.6em)
    ]
    #grid(
      columns: (1fr, 1fr),
      gutter: 1.2em,
      block(width: 100%)[#left],
      block(width: 100%)[#right],
    )
  ]
}

// Image-full slide — a full-bleed figure with a minimal overlay caption in
// the lower-left. `path` is the image; `caption` (optional) is a short
// gloss. The figure fills the page; the caption sits on a translucent
// scrim so it stays legible over any image.
#let image-full-slide(path, caption: "") = context {
  let c = _theme-colors(state("touying.theme").get())
  page(margin: 0pt, fill: c.bg)[
    #place(top + left)[
      #image(path, width: 100%, height: 100%, fit: "cover")
    ]
    #if caption != "" [
      #place(bottom + left, dx: 0pt, dy: 0pt)[
        #block(
          fill: c.bg.transparentize(15%),
          inset: (x: 18pt, y: 12pt),
          width: 100%,
        )[
          #text(size: 16pt, fill: c.fg)[#caption]
        ]
      ]
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
