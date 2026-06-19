// poster-mini — minimal Typst poster helpers used by Research-OS poster
// templates. Each template (`academic_36x48`, `public_24x36`, ...) imports
// from this file and supplies page geometry + palette. Helpers are kept
// intentionally small so a researcher can read them at a glance and tweak
// the resulting .typ without learning a deep DSL.
//
// Public surface (all keyword-only where reasonable):
//
//   poster-page(width, height, columns, palette, body)   page set + column flow
//   poster-header(title, subtitle, authors, affiliation, palette)
//   poster-footer(funding, contact, qr, palette)
//   poster-block(title, body, palette)                   titled coloured block
//   poster-figure(path, caption)                         centred figure + cap
//   poster-bullets(items)                                tight bullet list
//   poster-headline(text, palette)                       Mike-Morrison-style
//                                                        plain-English headline
//
// Palette is a dict with at minimum:
//   (primary: rgb, accent: rgb, ink: rgb, paper: rgb, muted: rgb)

// Default palette mirrors RO_PALETTE in tools/actions/viz/style.py so an
// RO-styled figure embedded in the poster matches the panel chrome (one
// visual identity across figures, poster, slides, dashboard). Keep these
// hexes in sync when the figure palette changes.
#let palette-light = (
  primary: rgb("#1F4D7A"),   // RO navy
  accent:  rgb("#9B7E2D"),   // RO olive gold
  ink:     rgb("#3D3A35"),   // RO warm-dark foreground
  paper:   rgb("#FBF8F3"),   // RO cream
  muted:   rgb("#EDE6D9"),   // cream-toned panel fill that sits on the paper
)

#let palette-dark = (
  primary: rgb("#90CDF4"),
  accent:  rgb("#F6E05E"),
  ink:     rgb("#F7FAFC"),
  paper:   rgb("#1A202C"),
  muted:   rgb("#2D3748"),
)

#let palette-institution = (
  primary: rgb("#7B1F2B"),
  accent:  rgb("#B7791F"),
  ink:     rgb("#1A202C"),
  paper:   rgb("#FFFFFF"),
  muted:   rgb("#F1E5E7"),
)

#let resolve-palette(name) = {
  if name == "dark" {
    palette-dark
  } else if name == "institution_branded" {
    palette-institution
  } else {
    palette-light
  }
}

// Titled block — coloured header bar + body. Used for every poster panel.
#let poster-block(title: "", body, palette: palette-light) = {
  block(
    width: 100%,
    breakable: false,
    above: 6mm,
    below: 4mm,
    {
      block(
        fill: palette.primary,
        inset: (x: 8mm, y: 4mm),
        width: 100%,
        radius: (top-left: 3mm, top-right: 3mm),
        text(fill: palette.paper, weight: "bold", size: 22pt, title),
      )
      block(
        fill: palette.muted,
        inset: (x: 8mm, y: 6mm),
        width: 100%,
        radius: (bottom-left: 3mm, bottom-right: 3mm),
        text(fill: palette.ink, size: 16pt, body),
      )
    },
  )
}

// Plain-English headline — the Mike-Morrison "Better Poster" centerpiece.
#let poster-headline(headline, palette: palette-light) = {
  block(
    width: 100%,
    fill: palette.accent.lighten(70%),
    inset: 10mm,
    radius: 5mm,
    align(center, text(
      fill: palette.ink,
      weight: "bold",
      size: 48pt,
      headline,
    )),
  )
}

// Centered figure with optional caption. `path` is resolved relative to
// the compiling .typ file's working dir (Research-OS copies hero figures
// next to the poster).
#let poster-figure(path: "", caption: "", palette: palette-light) = {
  align(center, {
    image(path, width: 95%)
    if caption != "" {
      v(2mm)
      text(fill: palette.ink, size: 14pt, style: "italic", caption)
    }
  })
}

// Tight bullet list — slightly bigger than body text so it reads from
// a normal viewing distance for posters.
#let poster-bullets(items, palette: palette-light) = {
  set list(spacing: 4mm, marker: text(fill: palette.accent, "•"))
  for it in items [
    - #it
  ]
}

// Header: title + subtitle + authors + affiliation. Sits at the top
// of the poster page; templates call this once before the column flow.
#let poster-header(
  title: "Untitled",
  subtitle: "",
  authors: "",
  affiliation: "",
  palette: palette-light,
) = {
  block(
    width: 100%,
    fill: palette.primary,
    inset: (x: 12mm, y: 10mm),
    {
      align(center, text(fill: palette.paper, weight: "bold", size: 56pt, title))
      if subtitle != "" {
        v(3mm)
        align(center, text(fill: palette.paper, style: "italic", size: 26pt, subtitle))
      }
      v(5mm)
      if authors != "" {
        align(center, text(fill: palette.paper, size: 22pt, authors))
      }
      if affiliation != "" {
        v(2mm)
        align(center, text(fill: palette.paper, size: 18pt, style: "italic", affiliation))
      }
    },
  )
}

// Footer: funding + contact line + optional QR code. QR is an arbitrary
// image path (PNG) supplied by Python.
#let poster-footer(
  funding: "",
  contact: "",
  qr-image: none,
  qr-caption: "",
  palette: palette-light,
) = {
  block(
    width: 100%,
    fill: palette.primary,
    inset: (x: 12mm, y: 6mm),
    grid(
      columns: (1fr, auto),
      gutter: 8mm,
      align: (left + horizon, right + horizon),
      {
        if funding != "" {
          text(fill: palette.paper, size: 14pt, weight: "bold", funding)
          linebreak()
        }
        if contact != "" {
          text(fill: palette.paper, size: 14pt, contact)
        }
      },
      {
        if qr-image != none {
          align(right, {
            image(qr-image, width: 30mm)
            if qr-caption != "" {
              v(1mm)
              text(fill: palette.paper, size: 10pt, qr-caption)
            }
          })
        }
      },
    ),
  )
}

// Page set + column flow. Templates call this with the right width /
// height / column count. `body` is the column flow; `header` and
// `footer` are rendered outside the columns so they span full width.
#let poster-page(
  width: 36in,
  height: 48in,
  columns-n: 3,
  palette: palette-light,
  margin: 18mm,
  header: none,
  footer: none,
  body,
) = {
  set page(
    width: width,
    height: height,
    margin: margin,
    fill: palette.paper,
  )
  // Sans body: posters are read across a room, where a humanist sans is
  // more legible at distance than a serif. Ragged-right (justify: false)
  // avoids the rivers justified text opens up in wide poster columns.
  set text(
    font: "New Computer Modern Sans",
    fill: palette.ink,
    size: 16pt,
  )
  set par(justify: false, leading: 0.65em)

  if header != none {
    header
    v(6mm)
  }

  columns(columns-n, gutter: 10mm, body)

  if footer != none {
    v(6mm)
    footer
  }
}

// ---------------------------------------------------------------------------
// Uniform scaffold-facing entry point.
//
// The venue-independent poster scaffold imports a small, stable surface:
//
//   #import "_typst_templates/poster.typ": poster, headline, block-section
//   #show: poster.with(title: [..], authors: [..], affiliation: [..], size: "36x48")
//   #headline[..]
//   #block-section(title: "Background")[..]
//
// These are thin convenience wrappers over the poster-* helpers above; a
// researcher who needs finer control can drop down to poster-page /
// poster-header / poster-block / poster-headline directly.
// ---------------------------------------------------------------------------

// Parse a "WxH" size string (inches) into a (width, height) pair. Falls back
// to 36x48 for unrecognised input.
#let _parse-poster-size(size) = {
  let parts = if type(size) == str { size.split("x") } else { () }
  if parts.len() == 2 {
    let w = float(parts.at(0).trim())
    let h = float(parts.at(1).trim())
    (w * 1in, h * 1in)
  } else {
    (36in, 48in)
  }
}

// Show-rule entry: sets the poster page geometry + header from a compact
// keyword surface, then flows the body in columns.
#let poster(
  title: "Untitled",
  authors: "",
  affiliation: "",
  subtitle: "",
  size: "36x48",
  columns-n: 3,
  palette: palette-light,
  funding: "",
  contact: "",
  body,
) = {
  let dims = _parse-poster-size(size)
  poster-page(
    width: dims.at(0),
    height: dims.at(1),
    columns-n: columns-n,
    palette: palette,
    header: poster-header(
      title: title,
      subtitle: subtitle,
      authors: authors,
      affiliation: affiliation,
      palette: palette,
    ),
    footer: if funding != "" or contact != "" {
      poster-footer(funding: funding, contact: contact, palette: palette)
    } else { none },
    body,
  )
}

// Plain-English centrepiece headline — alias for poster-headline.
#let headline(body, palette: palette-light) = poster-headline(body, palette: palette)

// Titled coloured panel — alias for poster-block.
#let block-section(title: "", body, palette: palette-light) = {
  poster-block(title: title, body, palette: palette)
}
