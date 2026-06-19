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

_POSTER_TYP = """// synthesis/poster.typ — conference poster. Author following
// synthesis/synthesis_poster. Compile with tool_typst_compile.

#import "_typst_templates/poster.typ": poster, headline, block-section

#show: poster.with(
  title: [Headline finding as a sentence],
  authors: [Author Name],
  affiliation: [Institution],
  size: "36x48",
)

#headline[Headline finding as a sentence — across-the-room readable.]

#block-section(title: "Background")[
  // AI: one paragraph. The question.
]

#block-section(title: "Methods")[
  // AI: one diagram + one paragraph.
]

#block-section(title: "Results")[
  // AI: the focal figure plus 1-2 supporting figures. Caption each.
]

#block-section(title: "Implication")[
  // AI: one sentence the reader walks away with.
]

#block-section(title: "References")[
  // AI: <=8 citations.
]
"""

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

_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- synthesis/dashboard.html — author following synthesis/synthesis_dashboard.
     AI: this is a CUSTOM, STORY-DRIVEN dashboard, NOT a per-step recap.
       - Section headings name CLAIMS / DECISIONS, never "Step NN".
       - Hero section delivers the top-line finding in the first viewport.
       - Embed only the 5-8 figures that move the argument; not all of them.
       - Captions interpret figures (what to see + why it matters), not label them.
       - Single file: no <script src="http", no <link href="http".
       - Every <img> has alt text; every <section> has an id.
     STYLE: matches the Research-OS reference figures — cream background,
       italic serif accents, muted navy / olive / forest / oxblood
       palette, generous whitespace, no gradients or shadows. The figures
       you embed should use research_os.tools.actions.viz.apply_research_os_style()
       so the colour identity is consistent throughout. -->
<title>Project title — single-line framing of the answer</title>
<style>
  /* Research-OS dashboard style — mirrors viz/style.py STYLE_RCPARAMS so
     embedded figures and the page chrome share one visual identity. */
  :root {
    --bg: #FBF8F3;          /* cream page */
    --card: #FFFDF8;        /* near-white card on cream */
    --fg: #3D3A35;          /* warm dark grey foreground */
    --muted: #6E665A;       /* muted secondary text — AA-safe (>=4.5:1) on --bg/--card */
    --rule: #D6CFC2;        /* hairline rule on cream */
    --accent: #1F4D7A;      /* navy — primary */
    --accent-gold: #9B7E2D; /* olive gold — secondary */
    --accent-green: #3F6049;/* forest — positive deltas */
    --accent-red: #9B3737;  /* oxblood — emphasis / negative deltas */
    --accent-mustard: #C3A14E; /* fifth accent */
    --serif: "EB Garamond", "Crimson Text", "Source Serif Pro",
             "Liberation Serif", Georgia, serif;
    --sans: "Inter", "Helvetica Neue", "Source Sans Pro", "Roboto",
            "Liberation Sans", Arial, sans-serif;
  }
  /* Dark-scheme tokens — same identity, retuned for low-light environments. */
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1C1A17; --card: #24221E; --fg: #E8E3D8; --muted: #A89E8E;
      --rule: #3A372F; --accent: #7FA8D4; --accent-gold: #C3A14E;
      --accent-green: #6FA07C; --accent-red: #C97A7A; --accent-mustard: #C3A14E;
    }
  }
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
  @media print {
    html, body { background: #fff; color: #000; }
    section { break-inside: avoid; border: 1px solid #ccc;
              background: #fff; box-shadow: none; }
    a { color: #000; border-bottom: none; }
    figure img { background: #fff; }
  }
</style>
</head>
<body>

<a class="skip-link" href="#headline">Skip to main content</a>

<header>
  <p class="eyebrow"><!-- AI: project type · date · audience tag. e.g. "Research synthesis · 2026-06-10 · Internal review" --></p>
  <h1>Project title</h1>
  <p class="tagline"><!-- AI: ONE sentence framing the answer (not the question). --></p>
</header>

<main>

<section class="hero" id="headline">
  <h2>Headline finding</h2>
  <p class="lead">
    <!-- AI: ONE sentence — the single most important thing the reader
         should take away. Lead with a number + finding verb. -->
  </p>
  <div class="metric-grid">
    <!-- AI: 3-6 <div class="metric-card"> with label / value / delta.
         Use class="delta up" or "delta down" for direction-coloured
         deltas (forest for up, oxblood for down). -->
  </div>
  <!-- AI: optional — embed the single most important figure here, with a
       caption that names what to see + what it means. Use a figure
       generated via research_os.tools.actions.viz.apply_research_os_style()
       so its palette matches the dashboard chrome. -->
</section>

<section id="key-findings">
  <h2>Key findings</h2>
  <!-- AI: 3-6 sub-sections (h3), each tied to ONE supported claim or
       decision. Organise by hypothesis or argument, NOT by workspace
       step number. Each finding: claim sentence + supporting figure or
       table + interpretive caption. Skip findings that don't move the
       argument; this is curated, not exhaustive. -->
</section>

<section id="comparison">
  <h2>What we tried (adopted vs ruled out)</h2>
  <!-- AI: when the project tested multiple paths / candidates / variants,
       surface the comparison here — scorecard table, before/after, or
       ablation. Skip this section if a single approach was tested. -->
</section>

<section id="methods">
  <h2>Methods</h2>
  <!-- AI: one short paragraph. Point readers at synthesis/paper.pdf for
       full detail. Do NOT duplicate workspace/methods.md. -->
</section>

<section id="limitations">
  <h2>Limitations + open questions</h2>
  <!-- AI: be honest. What this dashboard CANNOT claim. What the next
       investigation should answer. -->
</section>

<section id="references">
  <h2>References + how to cite</h2>
  <!-- AI: ≤12 citations. Data + code availability line. Link to the
       paper / preprint when available. -->
</section>

</main>

</body>
</html>
"""


SCAFFOLDS: dict[str, tuple[str, str]] = {
    "paper": ("synthesis/paper.typ", _PAPER_TYP),
    "slides": ("synthesis/slides.typ", _SLIDES_TYP),
    "poster": ("synthesis/poster.typ", _POSTER_TYP),
    "handout": ("synthesis/handout.typ", _HANDOUT_TYP),
    "grant": ("synthesis/grant.typ", _GRANT_TYP),
    "essay": ("synthesis/essay.typ", _ESSAY_TYP),
    "dashboard": ("synthesis/dashboard.html", _DASHBOARD_HTML),
}


def synthesis_scaffold(
    root: Path,
    kind: str = "paper",
    overwrite: bool = False,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Write a tiny skeleton synthesis file.

    Returns status='exists' (idempotent) if the file is already present
    and overwrite=False. The AI is expected to author the content; this
    tool only seeds section headers and protocol-pointing comments.

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
    return {
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
