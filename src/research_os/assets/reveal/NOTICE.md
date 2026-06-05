# Vendored: reveal.js

* Project: [reveal.js](https://github.com/hakimel/reveal.js) by Hakim El Hattab + contributors
* Version: 5.x (CDN: cdn.jsdelivr.net/npm/reveal.js@5)
* License: MIT (see ./LICENSE)
* Files vendored:
  - `reveal.js` — core presentation runtime
  - `reveal.css` — base stylesheet
  - `theme-white.css`, `theme-black.css` — two stock themes
  - `notes.js` — speaker-notes plugin

Vendored for offline single-file presentation rendering by
`research_os.tools.actions.synthesis.slides.compile_slides(engine="reveal")`.

No modifications. Patches, if any, must be documented here.

When the CDN is unreachable during a fresh install, slides.py falls back
to a hand-authored vanilla-JS arrow-key navigator (`_FALLBACK_REVEAL_HTML`
in slides.py) which is dependency-free.
