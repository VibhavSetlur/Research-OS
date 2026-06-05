// Research-OS poster template — public 24" × 36" community-event sized.
// Plain-English first: larger headline, fewer columns, friendlier palette.

#import "../typst_packages/poster-mini/poster.typ": (
  poster-page, poster-header, poster-footer, poster-block,
  poster-figure, poster-bullets, poster-headline, resolve-palette,
)

#let public-24x36(
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
    width: 24in,
    height: 36in,
    columns-n: 2,
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
