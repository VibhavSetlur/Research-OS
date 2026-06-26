"""Tiny synthesis starter scaffolds.

Writes a small skeleton file (≤80 lines) with section headers and
`// AI: author this section` markers. The AI fills the content
following the matching synthesis protocol. NOT a generator — refuses
to overwrite an existing file unless overwrite=true.

Public surface: synthesis_scaffold(root, kind, overwrite) -> dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_PAPER_TYP = """// synthesis/paper.typ — author this directly following synthesis/synthesis_paper.
// Compile with tool_typst_compile.

#import "_typst_templates/generic_two_column.typ": template, conf
#show: template.with(conf(
  title: [Your title — workshop via synthesis_title_workshop],
  authors: ((name: "Author Name", affiliation: "Institution"),),
  abstract: [
    // AI: author the abstract (200-300 words, structured if venue prefers).
  ],
))

= Introduction

// AI: 400-800 words. Open with the problem, situate in prior work
// (>=3 cited works), end with explicit "In this study, we ..." pivot.

= Methods

// AI: pull from workspace/methods.md verbatim. Every method block must
// name implementation + version + parameters + assumptions, with
// citations for non-trivial choices.

= Results

// AI: aggregate workspace/<step>/conclusions.md. Every effect estimate
// paired with 95% CI. Every figure cited and embedded as
// #figure(image("figures/figXX_*.png"), caption: [...]) <fig:slug>.

= Discussion

// AI: directly answer the research question. Mention limitations.
// Engage every non-AGREES verdict from findings_vs_literature.md.

= Conclusion

// AI: one paragraph. The single takeaway you want the reader to leave with.

#bibliography("biblio.yml")
"""

_SLIDES_TYP = """// synthesis/slides.typ — Touying presentation. Author following
// synthesis/synthesis_slides. Compile with tool_typst_compile.

#import "_typst_templates/touying-mini.typ": slides, slide, title-slide, section-slide, focus-slide, notes

#show: slides.with(
  title: "Talk title — short, claim-forward",
  subtitle: "One-line framing",
  author: "Author Name",
)

#title-slide()

#slide(title: "Question")[
  // AI: one slide. Why does this matter?
]

#slide(title: "Method (one slide)")[
  // AI: simplest possible diagram of the design.
]

#slide(title: "Result — headline claim")[
  // AI: one slide per claim. Figure readable at the back of the room.
  // #notes[What to say and what to point at.]
]

#slide(title: "Implication")[
  // AI: what does the audience leave with?
]

#section-slide("Backup slides")

#slide(title: "Backup: anticipated question 1")[
  // AI: one backup slide per anticipated Q&A question.
]
"""

_POSTER_CLASSIC = """// synthesis/poster.typ — conference poster (archetype: classic 3-column IMRaD,
// the safe default). Author following synthesis/deliverable_design +
// synthesis/printable. Compile with tool_typst_compile. Re-scaffold with
// archetype=billboard | hero | portrait for a different layout.

#import "_typst_templates/poster.typ": poster-classic, headline, block-section, poster-figure

#show: poster-classic.with(
  title: [Project title — short],
  authors: [Author Name],
  affiliation: [Institution],
  size: "36x48",                       // WxH inches; "48x36" for landscape
  palette: "__POSTER_PALETTE__",       // ro_house | okabe_ito | clinical | dark
  contact: "email · ORCID",
)

#headline[Headline finding as a plain-English sentence — across-the-room readable.]

#block-section(title: "Background")[
  // AI: the question, in one short paragraph.
]
#block-section(title: "Methods")[
  // AI: one diagram + a short paragraph.
]
#block-section(title: "Results")[
  // AI: focal figure + 1-2 supporting. #poster-figure(path: "figures/fig01.png",
  //     caption: "what to see + what it means.")
]
#block-section(title: "Implication")[
  // AI: one sentence the reader walks away with.
]
#block-section(title: "References")[
  // AI: <=8 citations.
]
"""

_POSTER_BILLBOARD = """// synthesis/poster.typ — conference poster (archetype: Better-Poster billboard).
// A big plain-English headline + a focal figure in a dominant CENTRE column,
// with a narrow SIDEBAR. Best for ONE clear result in a busy session.

#import "_typst_templates/poster.typ": poster-billboard, block-section, poster-figure, poster-stats

#show: poster-billboard.with(
  title: [Project title — short],
  authors: [Author Name],
  affiliation: [Institution],
  size: "48x36",                       // landscape suits the billboard
  palette: "__POSTER_PALETTE__",       // ro_house | okabe_ito | clinical | dark
  contact: "email · ORCID",
  headline: [Headline finding as a plain-English sentence.],
  sidebar: [
    #block-section(title: "Background")[
      // AI: the question, briefly.
    ]
    #block-section(title: "Methods")[
      // AI: the design, briefly.
    ]
    #block-section(title: "References")[
      // AI: <=6 citations.
    ]
  ],
)

// CENTRE billboard: the ONE focal figure + interpretive caption + key stats.
// AI: uncomment once your figure is rendered:
// #poster-figure(path: "figures/fig01_focal.png", caption: "what to see + what it means.")
#poster-stats((
  (label: "Headline metric", value: "N", delta: "+X better"),
  (label: "Second metric", value: "M", delta: ""),
))
"""

_POSTER_HERO = """// synthesis/poster.typ — conference poster (archetype: single-finding hero).
// ONE striking figure that speaks for itself; centre-weighted single column.

#import "_typst_templates/poster.typ": poster-hero, headline, block-section, poster-figure, poster-stats

#show: poster-hero.with(
  title: [Project title — short],
  authors: [Author Name],
  affiliation: [Institution],
  size: "48x36",
  palette: "__POSTER_PALETTE__",       // ro_house | okabe_ito | clinical | dark
  contact: "email · ORCID",
)

#headline[Headline finding — one sentence.]
#v(8mm)
// The ONE large focal figure — uncomment once rendered:
// #poster-figure(path: "figures/fig01_focal.png", caption: "what to see + what it means.")
#poster-stats((
  (label: "Headline metric", value: "N", delta: "+X"),
))
#block-section(title: "Methods & References")[
  // AI: compressed — one paragraph + <=6 citations.
]
"""

_POSTER_PORTRAIT = """// synthesis/poster.typ — conference poster (archetype: portrait 2-column).
// For tall boards (A0 portrait / 36×48 vertical).

#import "_typst_templates/poster.typ": poster-portrait, headline, block-section, poster-figure

#show: poster-portrait.with(
  title: [Project title — short],
  authors: [Author Name],
  affiliation: [Institution],
  size: "36x48",
  palette: "__POSTER_PALETTE__",       // ro_house | okabe_ito | clinical | dark
  contact: "email · ORCID",
)

#headline[Headline finding — one sentence.]

#block-section(title: "Background")[
  // AI: the question.
]
#block-section(title: "Methods")[
  // AI: the design.
]
#block-section(title: "Results")[
  // AI: focal figure + supporting.
]
#block-section(title: "Implication")[
  // AI: one sentence.
]
#block-section(title: "References")[
  // AI: <=8 citations.
]
"""

POSTER_ARCHETYPES: dict[str, str] = {
    "classic": _POSTER_CLASSIC,
    "billboard": _POSTER_BILLBOARD,
    "hero": _POSTER_HERO,
    "portrait": _POSTER_PORTRAIT,
}
_POSTER_DEFAULT_ARCHETYPE = "classic"


def _compose_poster(archetype: str | None = None, palette: str | None = None) -> str:
    """Assemble the poster .typ for the chosen layout archetype + palette name."""
    arch = archetype if archetype in POSTER_ARCHETYPES else _POSTER_DEFAULT_ARCHETYPE
    pal = palette if palette else "ro_house"
    return POSTER_ARCHETYPES[arch].replace("__POSTER_PALETTE__", pal)


# Back-compat default (classic) preserved under the original name.
_POSTER_TYP = _compose_poster(_POSTER_DEFAULT_ARCHETYPE)

_HANDOUT_TYP = """// synthesis/handout.typ — single-page A4 handout. Author following
// synthesis/printable (format=handout). Compile with tool_typst_compile.

#set page("a4", margin: 0.75in)
// "New Computer Modern Sans" is bundled (compile injects it via --font-path);
// an unbundled family like Inter would warn + silently fall back.
#set text(font: "New Computer Modern Sans", size: 11pt)

#align(center)[
  #text(size: 22pt, weight: 700)[Headline finding as a sentence.]
  #v(0.3em)
  #text(size: 12pt, fill: rgb("#6E665A"))[Author Name · Institution · date]
]

#v(1em)
== What we did
// AI: 1-3 sentences.

== What we found
// AI: 1-3 sentences. Embed the ONE headline figure here as
// #figure(image("figures/figXX.png", width: 80%), caption: [Finding.])

== Why it matters
// AI: 1-3 sentences. The implication for the audience.

== References
// AI: <=6 citations.

#align(bottom + right)[
  // AI: when you have a QR PNG, drop it next to this file and uncomment:
  // #image("handout_qr.png", width: 1.2in)
  Contact · email · ORCID
]
"""

_GRANT_TYP = """// synthesis/grant.typ — funder-tailored proposal. Author following
// synthesis/synthesis_grant. Compile with tool_typst_compile.

#import "_typst_templates/generic_two_column.typ": template, conf
#show: template.with(conf(
  title: [Project title — funder-appropriate],
  authors: ((name: "PI Name", affiliation: "Institution"),),
  abstract: [
    // AI: project abstract (lay summary if the funder requires one).
  ],
))

= Specific Aims (or funder-equivalent 1pg summary)
// AI: <=500 words. Lead with the problem + significance, name the
// long-term goal, state the central hypothesis, list 2-3 Aims.

= Significance
// AI: >=400 words. Why this matters.

= Innovation
// AI: >=300 words. What's new.

= Approach
// AI: >=1500 words. Per Aim — Premise + Rationale + Experimental
// Design + Expected Outcomes + Potential Pitfalls + Alternative
// Approaches. Include preliminary-data figures + timeline.

= Rigour and Reproducibility
// AI: statistical plan + sample-size justification + blinding +
// randomisation + biological variables + authentication of key resources.

#bibliography("biblio.yml")
"""

_ESSAY_TYP = """// synthesis/essay.typ — humanities essay. Author following
// synthesis/humanities_essay_structure. Compile with tool_typst_compile.

#import "_typst_templates/humanities_essay.typ": template, conf
#show: template.with(conf(
  title: [Essay title],
  author: [Author Name],
))

= Introduction and thesis
// AI: open with the question. Make the thesis one falsifiable sentence.

= Contextual framing
// AI: situate the text(s) historically and methodologically.

= Close reading 1
// AI: 3-5 close readings, each one tied to the thesis.

= Critical conversation
// AI: engage 5+ scholarly sources.

= Counter-argument and reply
// AI: state the strongest objection. Then answer it.

= Stakes
// AI: why does this argument matter?

#bibliography("biblio.yml")
"""

_DASHBOARD_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- synthesis/dashboard.html — author following synthesis/deliverable_design
     + synthesis/synthesis_dashboard. This is a CUSTOM, SHAREABLE deliverable
     for an external reader (peer / reviewer) who has NO workspace — design it
     to the argument, do not dump.
       - You chose a LAYOUT ARCHETYPE (data-archetype on <body>): single-
         viewport-brief | scroll-lite-narrative | comparison-scorecard |
         multi-panel-exploratory. Compose to that archetype's shape + budget.
       - Section headings name CLAIMS / DECISIONS ("Reranking lifted hits@10
         by 5.9pp"), never "Step NN", never bare containers (Results/Overview).
       - Hero answers the question in the first viewport: a number + a finding
         verb, never the question itself.
       - Embed only the 5-8 figures that MOVE the argument; caption each with
         what-to-see + what-it-means (finding-led, not "Figure 3: accuracy").
       - NO endless scroll. Respect the archetype's scroll budget; a multi-
         section page MUST carry the in-page <nav>.
       - NO workspace paths / step numbers / tool names / raw column names.
       - Single file, offline: no <script src="http", no <link href="http".
       - Every <img> has descriptive alt text; every <section> has an id.
     STYLE: pick ONE professional palette (the RO house cream/navy below is the
       default + cohesive with apply_research_os_style figures, but a custom-
       but-professional palette is fine — restraint, AA contrast, CVD-safe, no
       neon/rainbow, colour carries consistent MEANING). Whitespace + hairlines
       structure the page; no gradients, shadows, or decoration. -->
<title>Project title — single-line framing of the answer</title>
<style>
  /* Research-OS dashboard style — mirrors viz/style.py STYLE_RCPARAMS so
     embedded figures and the page chrome share one visual identity. */
__DASH_TOKENS__
  * { box-sizing: border-box; }
  /* Keyboard-focus ring + skip-link (a11y baseline). */
  .skip-link { position: absolute; left: -999px; top: 0;
               background: var(--accent); color: var(--bg);
               padding: 0.5rem 0.9rem; border-radius: 0 0 4px 0; z-index: 10; }
  .skip-link:focus { left: 0; }
  a:focus-visible, [tabindex]:focus-visible, button:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px; }
  /* Honour reduced-motion preference. */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
  }
  html { background: var(--bg); }
  body { font-family: var(--sans); margin: 0; color: var(--fg);
         background: var(--bg); line-height: 1.6;
         font-size: 15px; -webkit-font-smoothing: antialiased; }
  header { padding: 2.2rem 2.5rem 1.6rem;
           border-bottom: 1px solid var(--rule); }
  header .eyebrow { font-family: var(--serif); font-style: italic;
                    color: var(--muted); font-size: 0.92rem;
                    letter-spacing: 0.02em; margin: 0 0 0.4rem; }
  header h1 { font-family: var(--serif); font-style: italic;
              font-weight: 500; color: var(--accent);
              margin: 0; font-size: 1.8rem; letter-spacing: -0.005em; }
  header .tagline { font-family: var(--serif); font-style: italic;
                    color: var(--muted); margin: 0.45rem 0 0;
                    font-size: 1.02rem; max-width: 64ch; }
  main { max-width: 1100px; margin: 0 auto;
         padding: 1.8rem 2.5rem 3rem; }
  section { background: var(--card); border: 1px solid var(--rule);
            border-radius: 4px; padding: 1.5rem 1.8rem;
            margin-bottom: 1.4rem; }
  section.hero { border-left: 3px solid var(--accent-red);
                 padding-left: 1.6rem; }
  section h2 { font-family: var(--serif); font-style: italic;
               font-weight: 500; color: var(--accent);
               margin: 0 0 0.6rem; font-size: 1.35rem;
               letter-spacing: -0.005em; }
  section h3 { font-family: var(--serif); font-style: italic;
               color: var(--accent-gold); font-weight: 500;
               font-size: 1.08rem; margin: 1.2rem 0 0.4rem; }
  section p { margin: 0.5rem 0; }
  .lead { font-family: var(--serif); font-size: 1.12rem;
          color: var(--fg); line-height: 1.55; margin: 0.4rem 0 1rem; }
  .metric-grid { display: grid;
                 grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
                 gap: 0.9rem; margin: 1rem 0 0.6rem; }
  .metric-card { background: var(--bg);
                 border: 1px solid var(--rule);
                 border-radius: 3px; padding: 0.9rem 1rem; }
  .metric-card .label { color: var(--muted); font-size: 0.72rem;
                        text-transform: uppercase; letter-spacing: 0.08em;
                        font-weight: 600; }
  .metric-card .value { font-family: var(--serif);
                        font-size: 1.7rem; font-weight: 500;
                        color: var(--accent); margin: 0.35rem 0 0; }
  .metric-card .delta { font-family: var(--serif); font-style: italic;
                        color: var(--muted); font-size: 0.85rem;
                        margin-top: 0.2rem; }
  .metric-card .delta.up   { color: var(--accent-green); }
  .metric-card .delta.down { color: var(--accent-red); }
  figure { margin: 1.2rem 0; }
  figure img { max-width: 100%; height: auto;
               background: var(--bg);
               border: 1px solid var(--rule);
               border-radius: 3px; padding: 0.4rem; }
  figcaption { font-family: var(--serif); font-style: italic;
               font-size: 0.92rem; color: var(--muted);
               margin-top: 0.5rem; line-height: 1.55; max-width: 72ch; }
  table { border-collapse: collapse; width: 100%;
          font-size: 0.92rem; margin: 0.8rem 0; }
  th, td { padding: 0.55rem 0.75rem;
           border-bottom: 1px solid var(--rule); text-align: left; }
  th { font-family: var(--serif); font-style: italic; font-weight: 500;
       color: var(--accent); background: var(--bg);
       border-bottom: 1.5px solid var(--accent); }
  tr:last-child td { border-bottom: none; }
  a { color: var(--accent); text-decoration: none;
      border-bottom: 1px solid var(--rule); }
  a:hover { border-bottom-color: var(--accent); }
  code { font-family: "JetBrains Mono", "SF Mono", Consolas, monospace;
         font-size: 0.88em; background: var(--bg);
         padding: 0.1rem 0.35rem; border-radius: 2px;
         border: 1px solid var(--rule); }
  hr { border: none; border-top: 1px solid var(--rule);
       margin: 1.4rem 0; }
  ul, ol { padding-left: 1.4rem; }
  li { margin: 0.2rem 0; }
  /* In-page jump nav — REQUIRED by the scroll-lite-narrative archetype so a
     multi-section dashboard never forces endless scrolling to navigate. */
  nav.dash-nav { position: sticky; top: 0; z-index: 5;
                 display: flex; flex-wrap: wrap; gap: 1.1rem;
                 padding: 0.6rem 2.5rem; background: var(--card);
                 border-bottom: 1px solid var(--rule); font-size: 0.9rem; }
  nav.dash-nav a { border-bottom: none; color: var(--muted); }
  nav.dash-nav a:hover, nav.dash-nav a:focus-visible { color: var(--accent); }
  /* Bounded panel grid — multi-panel-exploratory archetype (shared scale). */
  .panel-grid { display: grid; gap: 1.2rem;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
  .panel { background: var(--card); border: 1px solid var(--rule);
           border-radius: 4px; padding: 1.1rem 1.3rem; margin: 0; }
  .panel figure { margin: 0; }
  /* Scorecard — comparison-scorecard archetype; adopted row reads at a glance
     via weight + a ✓ glyph, not colour alone. */
  table.scorecard tr.adopted td { font-weight: 600; color: var(--fg); }
  table.scorecard td.win { color: var(--accent-green); font-weight: 600; }
  table.scorecard td.lose { color: var(--accent-red); }
  @media print {
    html, body { background: #fff; color: #000; }
    nav.dash-nav { display: none; }
    section { break-inside: avoid; border: 1px solid #ccc;
              background: #fff; box-shadow: none; }
    a { color: #000; border-bottom: none; }
    figure img { background: #fff; }
  }
</style>
</head>
<body data-archetype="__DASH_ARCHETYPE__">

<a class="skip-link" href="#headline">Skip to main content</a>

<header>
  <p class="eyebrow"><!-- AI: project type · date · audience tag. e.g. "Research synthesis · 2026-06-10 · Internal review" --></p>
  <h1>Project title</h1>
  <p class="tagline"><!-- AI: ONE sentence framing the answer (not the question). --></p>
</header>

<main>
__DASH_MAIN__
</main>

</body>
</html>
"""


# Four composable dashboard layout archetypes — the AI picks ONE per project
# (driven by the research story) and fills the <main> body. These are OPTIONS,
# never a single fixed form. Each carries its design rule + scroll budget
# inline so the AI sees the constraints where it authors.

_DASH_SINGLE_VIEWPORT_BRIEF = """
<section class="hero" id="headline">
  <h2>Headline finding</h2>
  <p class="lead"><!-- AI: ONE sentence — number + finding verb. The single
       takeaway. NOT the research question. --></p>
  <div class="metric-grid">
    <!-- AI: 3-5 metric-cards. Each: <div class="metric-card"><p class="label">
         METRIC</p><p class="value">N</p><p class="delta up">+X (better)</p></div>.
         delta up=forest, down=oxblood — ALWAYS include a sign/word so colour
         is never the only cue. -->
  </div>
</section>

<figure>
  <!-- AI: the ONE focal figure (apply_research_os_style). -->
  <img src="figures/fig01_focal.png" alt="<AI: describe what the figure shows>">
  <figcaption><!-- AI: what to SEE + what it MEANS, finding-led. --></figcaption>
</figure>

<hr>

<section id="context">
  <h2>How &amp; caveats</h2>
  <p><!-- AI: 1-2 sentences — method pointer (→ paper.pdf) + the key limitation. --></p>
  <p class="muted"><!-- AI: data + code availability + how to cite, one line. --></p>
</section>
<!-- BUDGET: single-viewport-brief fits <=1.5 screens, NO nav. One finding,
     emailable. If you need more sections, switch to scroll-lite-narrative. -->
"""

_DASH_SCROLL_LITE_NARRATIVE = """
<nav class="dash-nav" aria-label="Sections">
  <!-- AI: REQUIRED for this archetype — a jump-link per section id below so the
       reader never has to scroll blindly. Keep labels to 1-2 words. -->
  <a href="#headline">Finding</a>
  <a href="#claim-1">Claim 1</a>
  <a href="#claim-2">Claim 2</a>
  <a href="#methods">Methods</a>
  <a href="#limitations">Limits</a>
</nav>

<section class="hero" id="headline">
  <h2>Headline finding</h2>
  <p class="lead"><!-- AI: ONE sentence — number + finding verb, not the question. --></p>
  <div class="metric-grid"><!-- AI: 3-5 metric-cards (label/value/delta + sign). --></div>
</section>

<section id="claim-1">
  <h2><!-- AI: claim AS A SENTENCE, e.g. "Reranking lifted hits@10 by 5.9pp" --></h2>
  <p><!-- AI: interpret the result. --></p>
  <figure><img src="figures/fig01.png" alt="<AI: describe>"><figcaption><!-- what to see + meaning --></figcaption></figure>
</section>

<section id="claim-2">
  <h2><!-- AI: next claim sentence --></h2>
  <p><!-- AI: interpret. --></p>
</section>
<!-- AI: 3-6 claim sections total (id="claim-N", add a matching nav link).
     BUDGET: <=8 sections, <=~5 viewports. Each section = ONE claim + 1-2
     figures + interpretation. Curated, not a dump. -->

<section id="methods">
  <h2>Methods</h2>
  <p><!-- AI: one short paragraph. Point to paper.pdf; do NOT restate methods.md. --></p>
</section>

<section id="limitations">
  <h2>Limitations + open questions</h2>
  <p><!-- AI: be honest — what this cannot claim + the next question. --></p>
</section>

<section id="references">
  <h2>References + how to cite</h2>
  <p><!-- AI: <=12 citations + data/code availability line. --></p>
</section>
"""

_DASH_COMPARISON_SCORECARD = """
<section class="hero" id="headline">
  <h2><!-- AI: the WINNING choice + the deciding metric, as a sentence. --></h2>
  <p class="lead"><!-- AI: why it won, in one line (number + verb). --></p>
</section>

<section id="scorecard">
  <h2>What we compared</h2>
  <table class="scorecard">
    <thead>
      <tr><th>Approach</th><th><!-- deciding metric --></th><th><!-- metric 2 --></th><th><!-- cost/notes --></th></tr>
    </thead>
    <tbody>
      <tr class="adopted"><td>&#10003; <!-- AI: adopted approach --></td><td class="win"><!-- best value --></td><td></td><td></td></tr>
      <tr><td><!-- AI: ruled-out candidate --></td><td><!-- value --></td><td></td><td><!-- why ruled out --></td></tr>
    </tbody>
  </table>
  <figcaption><!-- AI: what the scorecard shows + the deciding criterion.
       Mark the adopted row (class="adopted"); colour the deciding cell
       win/lose — but the &#10003; + weight already carry it without colour. --></figcaption>
</section>

<section id="why">
  <h2>Why this won</h2>
  <p><!-- AI: the decisive trade-off. Optionally ONE figure (e.g. the curve
       that separates the candidates). --></p>
</section>

<section id="methods">
  <h2>Methods</h2>
  <p><!-- AI: how the comparison was run + what was held constant. → paper.pdf. --></p>
</section>

<section id="limitations">
  <h2>Limitations + open questions</h2>
  <p><!-- AI: where the verdict might not hold. --></p>
</section>

<section id="references">
  <h2>References + how to cite</h2>
  <p><!-- AI: <=12 citations + data/code availability. --></p>
</section>
"""

_DASH_MULTI_PANEL_EXPLORATORY = """
<section class="hero" id="headline">
  <h2><!-- AI: the INTEGRATING takeaway across all facets, as a sentence. --></h2>
  <p class="lead"><!-- AI: what the panels jointly show — number + verb. --></p>
</section>

<section id="panels">
  <h2><!-- AI: what to read off the grid (the shared comparison). --></h2>
  <div class="panel-grid">
    <figure class="panel"><img src="figures/panel01.png" alt="<AI: describe>"><figcaption><!-- facet 1: what + meaning --></figcaption></figure>
    <figure class="panel"><img src="figures/panel02.png" alt="<AI: describe>"><figcaption><!-- facet 2 --></figcaption></figure>
    <figure class="panel"><img src="figures/panel03.png" alt="<AI: describe>"><figcaption><!-- facet 3 --></figcaption></figure>
    <figure class="panel"><img src="figures/panel04.png" alt="<AI: describe>"><figcaption><!-- facet 4 --></figcaption></figure>
  </div>
  <!-- AI: BUDGET <=6-8 panels, <=~2 viewports. ALL panels share ONE scale so
       the comparison is honest. If facets aren't comparable, this is the
       wrong archetype. -->
</section>

<section id="methods">
  <h2>Methods</h2>
  <p><!-- AI: one short paragraph. → paper.pdf. --></p>
</section>

<section id="limitations">
  <h2>Limitations + open questions</h2>
  <p><!-- AI: honest caveats. --></p>
</section>

<section id="references">
  <h2>References + how to cite</h2>
  <p><!-- AI: <=12 citations + data/code availability. --></p>
</section>
"""

DASHBOARD_ARCHETYPES: dict[str, str] = {
    "single-viewport-brief": _DASH_SINGLE_VIEWPORT_BRIEF,
    "scroll-lite-narrative": _DASH_SCROLL_LITE_NARRATIVE,
    "comparison-scorecard": _DASH_COMPARISON_SCORECARD,
    "multi-panel-exploratory": _DASH_MULTI_PANEL_EXPLORATORY,
}
_DASHBOARD_DEFAULT_ARCHETYPE = "scroll-lite-narrative"

# Shared font stacks (palette-independent; offline-safe fallbacks).
_DASH_SERIF = ('"EB Garamond", "Crimson Text", "Source Serif Pro", '
               '"Liberation Serif", Georgia, serif')
_DASH_SANS = ('"Inter", "Helvetica Neue", "Source Sans Pro", "Roboto", '
              '"Liberation Sans", Arial, sans-serif')


def _dashboard_tokens_css(palette: str | None = None) -> str:
    """Generate the :root token block (+ dark-scheme override) from one of the
    professional palettes in viz/palettes.py. Makes "pick a palette" real and
    keeps chrome colour in lockstep with the figure/audit palette source."""
    from research_os.tools.actions.viz.palettes import DEFAULT_PALETTE, PALETTES

    name = palette if palette in PALETTES else DEFAULT_PALETTE
    p = PALETTES[name]

    def block(scheme: dict) -> str:
        return (
            f"      --bg: {scheme['ground']}; --card: {scheme['card']};\n"
            f"      --fg: {scheme['fg']}; --muted: {scheme['muted']};\n"
            f"      --rule: {scheme['rule']};\n"
            f"      --accent: {scheme['primary']}; --accent-gold: {scheme['secondary']};\n"
            f"      --accent-green: {scheme['positive']}; --accent-red: {scheme['negative']};\n"
            f"      --accent-mustard: {scheme['fifth']};"
        )

    return (
        f"  /* Palette: {name} ({p['label']}) — mirrors viz/palettes.py so chrome,\n"
        f"     figures, and the design audit share ONE professional identity.\n"
        f"     Swap `palette=` to okabe_ito / clinical, or hand-edit these tokens\n"
        f"     for a custom-but-professional scheme (AA contrast, CVD-safe, no neon). */\n"
        f"  :root {{\n{block(p['light'])}\n"
        f"      --serif: {_DASH_SERIF};\n"
        f"      --sans: {_DASH_SANS};\n  }}\n"
        f"  /* Dark scheme — same semantic mapping, retuned for low light. */\n"
        f"  @media (prefers-color-scheme: dark) {{\n    :root {{\n{block(p['dark'])}\n    }}\n  }}"
    )


def _compose_dashboard(archetype: str | None = None, palette: str | None = None) -> str:
    """Assemble the shared dashboard shell (token base + a11y + chrome) with the
    chosen layout archetype's <main> body + a chosen professional palette. The
    archetype name is stamped into <body data-archetype=...> so the design audit
    can verify shape-vs-declared."""
    arch = archetype if archetype in DASHBOARD_ARCHETYPES else _DASHBOARD_DEFAULT_ARCHETYPE
    return (
        _DASHBOARD_SHELL
        .replace("__DASH_TOKENS__", _dashboard_tokens_css(palette))
        .replace("__DASH_ARCHETYPE__", arch)
        .replace("__DASH_MAIN__", DASHBOARD_ARCHETYPES[arch].strip("\n"))
    )


# Back-compat default (the scroll-lite narrative, RO house palette) — preserved
# as the name downstream tests + the SCAFFOLDS default import.
_DASHBOARD_HTML = _compose_dashboard(_DASHBOARD_DEFAULT_ARCHETYPE)


# ---------------------------------------------------------------------------
# Per-step report — the meeting-update artefact for a SINGLE analysis step.
# ---------------------------------------------------------------------------
#
# The whole-project dashboard / paper / poster answer "what did the project
# find?". They are the WRONG shape when a researcher is mid-flight on step 21
# and has a lab meeting in an hour: they need a self-contained, presentation-
# grade snapshot of ONE step's outputs. There is no per-step deliverable today.
#
# DESIGN STANCE (important): this scaffold gives the AI a SHELL, not a template.
# It guarantees the things that must be invariant for the artefact to be
# trustworthy and cohesive — the RO palette tokens, the accessibility baseline,
# and the offline/self-contained guarantee — and then GETS OUT OF THE WAY. The
# AI invents the entire layout, the sections, the order, and the visual rhythm
# to fit THIS step. A blocked debugging step, a breakthrough result, and a
# three-way method comparison should look nothing alike; freezing one section
# sequence into the seed would produce fill-in-the-blanks slop, which is exactly
# what the protocol doctrine forbids. The honesty + grounding + a11y bar is
# enforced downstream by synthesis_check, NOT by a mandated heading list here.
#
# Reusing the dashboard shell (same palette engine, same a11y baseline, same
# offline guarantee) means the chain of step reports reads as one cohesive
# project diary, and any single one is emailable / screen-shareable as a
# standalone .html with zero network requests.

# The seed <main> body is intentionally EMPTY of structure: it carries only an
# author brief (design intent + hard constraints) as comments and a couple of
# ready-to-use building blocks the AI may keep, reshape, or delete entirely.
# Everything visible in the final artefact is the AI's own custom composition.
_STEP_REPORT_MAIN = """
<!-- ===================================================================== -->
<!-- STEP REPORT — author brief (delete this whole comment when done).      -->
<!--                                                                        -->
<!-- WHAT THIS IS: a self-contained, presentation-grade page about ONE step -->
<!-- of this project, meant to be screen-shared or emailed at a meeting.    -->
<!--                                                                        -->
<!-- YOUR JOB: design the page THIS step deserves. There is no required     -->
<!-- structure, section list, or order. Invent the layout that communicates -->
<!-- this particular step's story fastest to a busy reader (often the PI).  -->
<!-- A blocked step, a clean win, and a messy diagnostic should each look   -->
<!-- different. Use as many or as few sections as the step needs.           -->
<!--                                                                        -->
<!-- THINGS A GOOD STEP UPDATE USUALLY ANSWERS (pick what's true here, in   -->
<!-- whatever shape fits — these are prompts, NOT a checklist to stamp out): -->
<!--   - In one breath: what changed / what we now know since last time?    -->
<!--   - The headline number(s), with an honest comparison or baseline.     -->
<!--   - The single most informative figure, read out loud in its caption.  -->
<!--   - What it means for the project + what it canNOT yet claim.          -->
<!--   - What's next, and any specific ask for the people in the room.      -->
<!--                                                                        -->
<!-- HARD CONSTRAINTS (these the check WILL enforce — everything else free): -->
<!--   * Every number/claim must come from THIS step's conclusions.md /     -->
<!--     outputs / tables. Never invent or round-trip a guess.              -->
<!--   * Figures: relative path under ./figures/ that travels with the file, -->
<!--     or base64-embedded. No network URLs (the file must work offline).  -->
<!--     Every <img> needs a real, descriptive alt.                         -->
<!--   * Never rely on colour alone to carry meaning — pair it with a word, -->
<!--     sign, or icon (accessibility + projector/print safety).            -->
<!--   * Use the palette tokens (var(--accent-green) etc.) so embedded      -->
<!--     figures and page chrome share one identity. Don't hardcode hexes.  -->
<!--   * No placeholder/lorem text, no AI throat-clearing, no "Results:"     -->
<!--     label headings — write findings as sentences.                       -->
<!--                                                                        -->
<!-- PALETTE TOKENS available from the shared shell:                        -->
<!--   var(--ink) var(--paper) var(--muted) var(--rule) var(--accent)       -->
<!--   var(--accent-green) var(--accent-gold) var(--accent-red)             -->
<!--   var(--serif) var(--sans)  + the .metric-grid/.metric-card helpers     -->
<!--   from the dashboard shell are available if you want them.             -->
<!-- ===================================================================== -->

<!-- Compose freely below. Everything here is a STARTING POINT you may keep, -->
<!-- restructure, or remove. The page is yours to design.                   -->

"""


def _compose_step_report(palette: str | None = None) -> str:
    """Assemble a step report from the shared dashboard shell (palette engine +
    a11y baseline + offline chrome). The ``<main>`` body is the empty author
    brief — the AI composes the actual page. ``data-archetype`` is stamped
    ``step-report`` so the check engine can route on kind without constraining
    the AI's layout."""
    return (
        _DASHBOARD_SHELL
        .replace("__DASH_TOKENS__", _dashboard_tokens_css(palette))
        .replace("__DASH_ARCHETYPE__", "step-report")
        .replace("__DASH_MAIN__", _STEP_REPORT_MAIN.strip("\n"))
    )


_STEP_REPORT_HTML = _compose_step_report()


SCAFFOLDS: dict[str, tuple[str, str]] = {
    "paper": ("synthesis/paper.typ", _PAPER_TYP),
    "slides": ("synthesis/slides.typ", _SLIDES_TYP),
    "poster": ("synthesis/poster.typ", _POSTER_TYP),
    "handout": ("synthesis/handout.typ", _HANDOUT_TYP),
    "grant": ("synthesis/grant.typ", _GRANT_TYP),
    "essay": ("synthesis/essay.typ", _ESSAY_TYP),
    "dashboard": ("synthesis/dashboard.html", _DASHBOARD_HTML),
    # Per-step meeting update. The path here is the FALLBACK; when a `step`
    # argument is supplied, synthesis_scaffold rewrites it to
    # synthesis/updates/step-<NN>-<slug>.html so the chain of updates lives
    # in one browsable folder (the project diary).
    "step_report": ("synthesis/updates/step-report.html", _STEP_REPORT_HTML),
}

# Composable layout archetypes per deliverable kind — the AI picks ONE; the
# scaffold validates against this menu and stamps the choice into the output.
ARCHETYPE_MENUS: dict[str, list[str]] = {
    "dashboard": list(DASHBOARD_ARCHETYPES),
    "poster": ["classic", "billboard", "hero", "portrait"],
}


def _step_report_slug(root: Path, step: str | None) -> str:
    """Resolve a step identifier into a stable filename stem for a step report.

    Accepts a bare number ("21"), a zero-padded number ("07"), a full step
    directory name ("21_baseline_eda"), or None. When the workspace has a
    matching step directory, its descriptive name is folded into the slug so
    the file reads as ``step-21-baseline-eda`` and sorts chronologically in
    ``synthesis/updates/``. Falls back to ``step-report`` when nothing matches.
    """
    import re

    if not step:
        return "step-report"
    raw = str(step).strip()
    # Pull a leading number if present (handles "21", "21_baseline_eda", "step21").
    num_match = re.search(r"(\d+)", raw)

    # Try to locate the real step directory so we can use its descriptive tail.
    descriptive_tail = ""
    workspace = root / "workspace"
    if num_match and workspace.is_dir():
        from research_os.project_ops import discover_step_dirs

        target_num = int(num_match.group(1))
        try:
            step_dirs = discover_step_dirs(workspace, include_dead=False)
        except Exception:
            step_dirs = []
        for d in step_dirs:
            dm = re.match(r"(\d+)[_-](.+)", d.name)
            if dm and int(dm.group(1)) == target_num:
                descriptive_tail = dm.group(2)
                break

    if num_match:
        num = num_match.group(1).zfill(2)
        tail = descriptive_tail
        if not tail:
            # No matching dir — keep any descriptive text the caller passed.
            rest = re.sub(r"^\D*\d+[_\-\s]*", "", raw)
            tail = rest
        slug = f"step-{num}"
        if tail:
            clean = re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
            if clean:
                slug = f"{slug}-{clean}"
        return slug
    # No number at all — slugify whatever was passed.
    clean = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return f"step-{clean}" if clean else "step-report"


def stage_step_figures(root: Path, step: str | None) -> dict[str, Any]:
    """Copy a step's figures into ``synthesis/updates/figures/`` so a step
    report can reference them with portable relative ``figures/...`` paths.

    A step report is meant to TRAVEL as a single self-contained file — so
    its images must live next to it, not point back into ``workspace/``.
    This helper resolves the step directory, copies every figure from its
    ``outputs/figures/`` into ``synthesis/updates/figures/`` (skipping
    unchanged files), and flags the focal figure (filename starting with
    the step number, else alphabetically first) so the AI knows which one
    leads. It NEVER edits the report HTML or invents a figure — it only
    stages what the step actually produced. Returns ``status='empty'``
    when the step has no figures (the report can still be authored).
    """
    import re
    import shutil

    figures_dir = root / "synthesis" / "updates" / "figures"
    workspace = root / "workspace"
    if not workspace.is_dir():
        return {"status": "empty", "staged": [], "reason": "no workspace/"}

    # Resolve the step directory (reuse the same matching as the slug helper).
    step_dir: Path | None = None
    if step:
        num_match = re.search(r"(\d+)", str(step))
        try:
            from research_os.project_ops import discover_step_dirs

            step_dirs = discover_step_dirs(workspace, include_dead=False)
        except Exception:
            step_dirs = []
        if num_match:
            target_num = int(num_match.group(1))
            for d in step_dirs:
                dm = re.match(r"(\d+)[_-](.+)", d.name)
                if dm and int(dm.group(1)) == target_num:
                    step_dir = d
                    break
        if step_dir is None:
            # Exact directory name passed?
            cand = workspace / str(step)
            if cand.is_dir():
                step_dir = cand
    if step_dir is None:
        return {
            "status": "empty",
            "staged": [],
            "reason": f"no step directory resolved for step={step!r}",
        }

    src_figs = step_dir / "outputs" / "figures"
    suffixes = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
    candidates = (
        [
            f for f in sorted(src_figs.iterdir())
            if f.is_file() and f.suffix.lower() in suffixes
        ]
        if src_figs.is_dir() else []
    )
    if not candidates:
        return {
            "status": "empty",
            "staged": [],
            "reason": f"{step_dir.name} has no figures in outputs/figures/",
        }

    step_num = step_dir.name.split("_", 1)[0]
    focal = next(
        (f for f in candidates if f.name.startswith(step_num + "_")),
        candidates[0],
    )

    figures_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []
    for f in candidates:
        dest = figures_dir / f.name
        try:
            if not dest.exists() or dest.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, dest)
        except OSError:
            continue
        staged.append({
            "filename": f.name,
            "rel_path": f"figures/{f.name}",
            "focal": (f == focal),
        })
    return {
        "status": "success" if staged else "empty",
        "staged": staged,
        "focal": (f"figures/{focal.name}" if staged else None),
        "figures_dir": str(figures_dir),
        "source_step": step_dir.name,
    }


def rebuild_updates_index(root: Path) -> dict[str, Any]:
    """(Re)generate ``synthesis/updates/index.html`` — the project's visual
    diary landing page that lists every step report in chronological order.

    This is a *navigation* helper, not a deliverable: it is fully derived
    from the step-report files already on disk, carries no claims of its
    own, embeds nothing, and makes zero network requests. It is safe to
    regenerate on every step-report write — it never invents content and
    is overwritten wholesale each time so it stays in sync with the folder.

    Returns ``status='empty'`` when no step reports exist yet (and removes
    a stale index if one is present), otherwise ``status='success'`` with
    the count of reports indexed.
    """
    import html
    import re as _re
    from datetime import date

    updates = root / "synthesis" / "updates"
    index_path = updates / "index.html"
    if not updates.is_dir():
        return {"status": "empty", "count": 0}

    # Collect step reports — every .html under updates/ except the index.
    # Row tuple: (sort_key, slug, title, filename, headline, datestr)
    reports: list[tuple[int, str, str, str, str, str]] = []
    for f in sorted(updates.glob("*.html")):
        if f.name == "index.html":
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Only index files that are actually step reports (stamped shell).
        if not _re.search(
            r'<body[^>]*\bdata-archetype\s*=\s*["\']step-report["\']', txt, _re.I
        ):
            continue
        # Title: prefer the authored <h1>, else fall back to the slug.
        m = _re.search(r"<h1[^>]*>(.*?)</h1>", txt, _re.I | _re.S)
        if m:
            title = _re.sub(r"<[^>]+>", "", m.group(1)).strip()
            title = html.unescape(_re.sub(r"\s+", " ", title))
        else:
            title = f.stem
        # Headline: first <p> AFTER the <h1> (the step's one-line takeaway).
        # Skip the author-brief comment block — search only authored body.
        headline = ""
        after = txt[m.end():] if m else txt
        pm = _re.search(r"<p[^>]*>(.*?)</p>", after, _re.I | _re.S)
        if pm:
            raw = _re.sub(r"<[^>]+>", "", pm.group(1))
            raw = html.unescape(_re.sub(r"\s+", " ", raw)).strip()
            if len(raw) > 160:
                raw = raw[:157].rstrip() + "…"
            headline = raw
        # Date: file modification time, ISO yyyy-mm-dd (best-effort).
        try:
            datestr = date.fromtimestamp(f.stat().st_mtime).isoformat()
        except OSError:
            datestr = ""
        # Sort by leading step number when present, else push to the end.
        num_m = _re.search(r"step-(\d+)", f.stem)
        sort_key = int(num_m.group(1)) if num_m else 10**6
        reports.append(
            (sort_key, f.stem, title or f.stem, f.name, headline, datestr)
        )

    if not reports:
        # Nothing to index — drop a stale index so the folder stays honest.
        if index_path.exists():
            index_path.unlink()
        return {"status": "empty", "count": 0}

    reports.sort(key=lambda r: (r[0], r[1]))

    def _row(title: str, fn: str, headline: str, datestr: str) -> str:
        date_html = (
            f'<span class="date">{html.escape(datestr)}</span>' if datestr else ""
        )
        head_html = (
            f'<span class="headline">{html.escape(headline)}</span>'
            if headline else ""
        )
        return (
            f'      <li><a href="{html.escape(fn)}">'
            f'<span class="t">{html.escape(title)}</span>'
            f"{date_html}{head_html}</a></li>"
        )

    rows = "\n".join(
        _row(title, fn, headline, datestr)
        for _sk, _slug, title, fn, headline, datestr in reports
    )
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Step reports</title>
<style>
  :root {{ --ink: #1a1a1a; --paper: #FBF8F3; --rule: #d8d2c6; --accent: #3a5a40; --muted: #5b5b5b; }}
  body {{ background: var(--paper); color: var(--ink); margin: 0;
         font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 46rem; margin: 0 auto; padding: 3rem 1.5rem; }}
  h1 {{ font-weight: 600; letter-spacing: -0.01em; margin: 0 0 0.25rem; }}
  p.sub {{ color: var(--muted); margin: 0 0 2rem; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ border-bottom: 1px solid var(--rule); }}
  li a {{ display: block; padding: 0.85rem 0.25rem; color: var(--accent);
          text-decoration: none; }}
  li a:hover, li a:focus {{ text-decoration: underline; }}
  .t {{ font-weight: 600; }}
  .date {{ color: var(--muted); font-size: 0.82rem; font-weight: 400;
           margin-left: 0.6rem; }}
  .headline {{ display: block; color: var(--ink); font-weight: 400;
               font-size: 0.92rem; margin-top: 0.15rem; }}
</style>
</head>
<body data-archetype="updates-index">
  <main>
    <h1>Step reports</h1>
    <p class="sub">{len(reports)} report(s) — the project's visual diary, newest design wins per step.</p>
    <ul>
{rows}
    </ul>
  </main>
</body>
</html>
"""
    updates.mkdir(parents=True, exist_ok=True)
    index_path.write_text(doc, encoding="utf-8")
    return {"status": "success", "count": len(reports), "path": str(index_path)}


def synthesis_scaffold(
    root: Path,
    kind: str = "paper",
    overwrite: bool = False,
    confirmed: bool = False,
    archetype: str | None = None,
    palette: str | None = None,
    step: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Write a tiny skeleton synthesis file.

    Returns status='exists' (idempotent) if the file is already present
    and overwrite=False. The AI is expected to author the content; this
    tool only seeds section headers and protocol-pointing comments.

    Recurring deliverables (``label``): a researcher makes MANY posters /
    slide decks / handouts / dashboards over a project's life — a lab-meeting
    update every week, a conference poster, a committee slide deck. Writing them
    all to the flat ``synthesis/poster.typ`` would overwrite each other and lose
    track of which file was for which event. Pass ``label`` (e.g.
    "2026-06-lab-meeting", "neurips-poster", "committee-update") for any such
    RECURRING / event-specific deliverable: the scaffold routes it to
    ``synthesis/deliverables/<label-slug>/<kind>.<ext>`` and drops a README
    stamping the event + date + purpose, so the chain of meeting artefacts lives
    in one browsable, documented folder (order in the chaos). OMIT ``label`` only
    for the project's single canonical deliverable (the paper). ``label`` does
    not apply to ``step_report`` (it already routes to synthesis/updates/).

    Output-types intent gate: if ``kind`` is NOT in the researcher's
    declared ``research_goal.output_types`` (and they HAVE declared
    something — empty list is treated as "open"), the scaffold returns
    status='ask' instead of writing. The AI is expected to surface the
    returned ``message`` to the researcher and re-call with
    ``confirmed=true`` only if the researcher actually wants this
    deliverable. This prevents the failure mode where the AI auto-creates
    a paper / dashboard / poster the user never asked for.
    """
    if kind not in SCAFFOLDS:
        return {
            "status": "error",
            "message": f"Unknown kind '{kind}'. Valid: {', '.join(sorted(SCAFFOLDS))}.",
        }

    # Validate the optional layout-archetype choice against the kind's menu.
    if archetype is not None:
        menu = ARCHETYPE_MENUS.get(kind)
        if menu is None:
            return {
                "status": "error",
                "message": (
                    f"kind '{kind}' has no layout archetypes. "
                    f"Archetypes apply to: {', '.join(sorted(ARCHETYPE_MENUS))}."
                ),
            }
        if archetype not in menu:
            return {
                "status": "error",
                "message": f"Unknown archetype '{archetype}' for {kind}. Valid: {', '.join(menu)}.",
            }

    # Validate the optional palette choice.
    if palette is not None:
        from research_os.tools.actions.viz.palettes import PALETTES

        if palette not in PALETTES:
            return {
                "status": "error",
                "message": f"Unknown palette '{palette}'. Valid: {', '.join(PALETTES)}.",
            }

    # Output-types intent gate. Skipped when the caller has already
    # confirmed with the researcher (confirmed=true) or is doing a
    # forced overwrite (overwrite=true implies prior confirmation).
    if not (confirmed or overwrite):
        # Local import to avoid pulling check.py at module load.
        from research_os.tools.actions.synthesis.check import output_types_gate

        gate = output_types_gate(root, kind)
        if gate.get("verdict") == "ask":
            return {
                "status": "ask",
                "kind": kind,
                "intent_gate": gate,
                "message": gate.get("message", "Confirm scaffold with the researcher first."),
            }

    rel_path, body = SCAFFOLDS[kind]
    # Compose the body for kinds that offer a layout-archetype design system.
    chosen_archetype: str | None = None
    if kind == "dashboard":
        chosen_archetype = (
            archetype if archetype in DASHBOARD_ARCHETYPES else _DASHBOARD_DEFAULT_ARCHETYPE
        )
        body = _compose_dashboard(chosen_archetype, palette)
    elif kind == "poster":
        chosen_archetype = archetype or "classic"
        body = _compose_poster(chosen_archetype, palette)
    elif kind == "step_report":
        # Re-compose with the chosen palette so embedded figures + chrome
        # share one identity, and route the file into synthesis/updates/
        # under a step-numbered name (the project diary).
        body = _compose_step_report(palette)
        slug = _step_report_slug(root, step)
        rel_path = f"synthesis/updates/{slug}.html"

    # Recurring / event-specific deliverable routing. When a label is given for
    # a non-paper, non-step_report deliverable, write it into its own
    # synthesis/deliverables/<slug>/ folder (keeps a chain of meeting/conf
    # artefacts from overwriting the flat synthesis/<kind> file).
    deliverable_dir: Path | None = None
    if label and kind not in ("paper", "step_report"):
        import re as _re
        from datetime import datetime, timezone

        lslug = _re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-") or "deliverable"
        ext = rel_path.rsplit(".", 1)[-1]
        rel_path = f"synthesis/deliverables/{lslug}/{kind}.{ext}"
        deliverable_dir = root / "synthesis" / "deliverables" / lslug
        # Document what this deliverable is for (order in the chaos).
        readme = deliverable_dir / "README.md"
        if not readme.exists():
            deliverable_dir.mkdir(parents=True, exist_ok=True)
            readme.write_text(
                f"# {label}\n\n"
                f"*Created: {datetime.now(timezone.utc).date().isoformat()}*\n\n"
                f"A **{kind}** deliverable for: {label}.\n\n"
                "This folder holds a recurring / event-specific synthesis "
                "artefact (a lab-meeting update, conference poster, committee "
                "deck, etc.) — distinct from the project's canonical paper in "
                "`synthesis/`. It may be a quick/throwaway artefact for one "
                "meeting, but it is still documented here so the project stays "
                "ordered: anyone can see which file was for which event.\n\n"
                "- What it's for: _(audience + occasion)_\n"
                "- Status: _draft | presented | superseded_\n"
                "- Source findings: _(which steps / paper sections it draws on)_\n",
                encoding="utf-8",
            )
    target = root / rel_path
    if target.exists() and not overwrite:
        return {
            "status": "exists",
            "path": str(target),
            "message": (
                f"{rel_path} already present — refusing to overwrite. "
                "Pass overwrite=true to replace, or edit the existing file."
            ),
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    result = {
        "status": "success",
        "path": str(target),
        "kind": kind,
        "byte_count": len(body),
        "message": (
            f"Wrote {rel_path}. Author the content directly. When ready, "
            "call tool_synthesis_check to validate, then tool_typst_compile "
            "(or open the HTML directly for dashboards)."
        ),
    }
    if chosen_archetype is not None:
        result["archetype"] = chosen_archetype
        result["available_archetypes"] = ARCHETYPE_MENUS.get(kind, [])
    if palette is not None:
        result["palette"] = palette
    if kind == "step_report":
        result["step"] = step
        # Stage this step's figures next to the report so it travels as one
        # self-contained file (relative figures/ paths, no workspace/ refs).
        staged = stage_step_figures(root, step)
        if staged.get("status") == "success":
            result["staged_figures"] = staged.get("staged")
            result["focal_figure"] = staged.get("focal")
        else:
            result["staged_figures"] = []
            result["figures_note"] = staged.get("reason", "")
        # Refresh the diary landing page so synthesis/updates/index.html
        # always lists the full chain of step reports. Pure navigation —
        # derived from disk, no claims of its own.
        idx = rebuild_updates_index(root)
        if idx.get("status") == "success":
            result["updates_index"] = idx.get("path")
            result["updates_index_count"] = idx.get("count")
        result["message"] = (
            f"Wrote {rel_path} — a shell only (RO palette, accessibility "
            "baseline, offline-safe). DESIGN the page this step deserves: "
            "there is no fixed structure. Read the author brief in the file, "
            "then compose the layout that tells THIS step's story fastest to a "
            "busy reader. Ground every number in the step's conclusions.md / "
            "outputs (never invent), keep figures local under "
            f"{Path(rel_path).parent}/figures/ so the file travels intact, and "
            "never let colour be the only cue. When ready, call "
            "tool_synthesis_check to validate, then open or screen-share the HTML."
        )
    return result
