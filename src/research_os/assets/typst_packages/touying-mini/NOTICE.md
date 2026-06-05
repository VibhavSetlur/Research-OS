# touying-mini

A minimal Typst slides template shipped inside Research-OS for the
`compile_slides(engine="touying")` path.

* License: MIT (see ./LICENSE)
* API surface: Touying-compatible subset (`slides`, `slide`,
  `title-slide`, `section-slide`, `focus-slide`, `notes`).
* Not a fork of upstream Touying — no source files are copied. Written
  from scratch to match Touying's call signatures so projects can
  migrate to full Touying without rewriting slide content.

When richer features are needed (stepwise reveals, transitions, full
theme catalogue), install upstream Touying via `typst init @preview/touying`
and swap the `#import` line in `synthesis/slides.typ`.
