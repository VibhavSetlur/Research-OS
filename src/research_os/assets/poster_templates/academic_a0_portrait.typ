// Research-OS poster template — academic A0 portrait (841 mm × 1189 mm).
// ISO standard for European / international conferences. 3 columns.

#import "../typst_packages/poster-mini/poster.typ": (
  poster-page, poster-header, poster-footer, poster-block,
  poster-figure, poster-bullets, poster-headline, resolve-palette,
)

#let academic-a0-portrait(
  title: "Untitled",
  subtitle: "",
  authors: "",
  affiliation: "",
  funding: "",
  contact: "",
  qr-image: none,
  qr-caption: "",
  theme: "light",
  body,
) = {
  let pal = resolve-palette(theme)
  poster-page(
    width: 841mm,
    height: 1189mm,
    columns-n: 3,
    palette: pal,
    margin: 20mm,
    header: poster-header(
      title: title, subtitle: subtitle,
      authors: authors, affiliation: affiliation,
      palette: pal,
    ),
    footer: poster-footer(
      funding: funding, contact: contact,
      qr-image: qr-image, qr-caption: qr-caption,
      palette: pal,
    ),
    body,
  )
}
