// Research-OS poster template — academic A1 landscape (841 mm × 594 mm).
// Smaller European format; common for departmental poster days. 3 columns.

#import "../typst_packages/poster-mini/poster.typ": (
  poster-page, poster-header, poster-footer, poster-block,
  poster-figure, poster-bullets, poster-headline, resolve-palette,
)

#let academic-a1-landscape(
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
    height: 594mm,
    columns-n: 3,
    palette: pal,
    margin: 14mm,
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
