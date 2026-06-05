# poster-mini

Minimal Typst helpers used by the Research-OS poster templates. Each
template under `assets/poster_templates/*.typ` imports from `poster.typ`
in this directory and supplies its own page geometry, palette, and
column count.

If you want to author a custom poster for a venue Research-OS doesn't
ship a template for, copy any of the templates as a starting point —
all the heavy lifting (titled blocks, headline, figures, header/footer)
is in `poster.typ` and stays the same.
