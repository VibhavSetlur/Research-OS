// Research-OS poster template — academic 36" × 48" (US standard portrait).
// Page is the US conference modal: 36in wide, 48in tall, 3 columns.

#import "../typst_packages/poster-mini/poster.typ": (
  poster-page, poster-header, poster-footer, poster-block,
  poster-figure, poster-bullets, poster-headline, resolve-palette,
)

#let academic-36x48(
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
    width: 36in,
    height: 48in,
    columns-n: 3,
    palette: pal,
    margin: 18mm,
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
