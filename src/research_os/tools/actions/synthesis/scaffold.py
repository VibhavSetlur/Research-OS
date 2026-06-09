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
#set text(font: "Inter", size: 11pt)

#align(center)[
  #text(size: 22pt, weight: 700)[Headline finding as a sentence.]
  #v(0.3em)
  #text(size: 12pt, fill: rgb("#666"))[Author Name · Institution · date]
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
  #image("handout_qr.png", width: 1.2in)
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
       - Every <img> has alt text; every <section> has an id. -->
<title>Project title — single-line framing of the answer</title>
<style>
  :root { --fg:#1a1a1a; --muted:#555; --accent:#0f3460; --bg:#fafafa;
          --card:#fff; --line:#e0e0e0; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0;
         color: var(--fg); background: var(--bg); line-height: 1.55; }
  header { background: var(--accent); color: #fff; padding: 1.2rem 2rem; }
  header h1 { margin: 0; font-size: 1.4rem; }
  header p { margin: 0.3rem 0 0; color: #d0d8e0; font-size: 0.9rem; }
  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem 2rem; }
  section { background: var(--card); border: 1px solid var(--line);
            border-radius: 6px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem; }
  section.hero { border-left: 4px solid #e94560; }
  section h2 { margin-top: 0; color: var(--accent); }
  .metric-grid { display: grid;
                 grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                 gap: 0.6rem; margin: 0.8rem 0; }
  .metric-card { background: #f7fafc; border: 1px solid var(--line);
                 border-radius: 4px; padding: 0.6rem 0.8rem; }
  .metric-card .label { color: var(--muted); font-size: 0.75rem;
                        text-transform: uppercase; letter-spacing: 0.05em; }
  .metric-card .value { font-size: 1.6rem; font-weight: 600;
                        color: var(--accent); margin: 0.2rem 0; }
  figure { margin: 1rem 0; }
  figure img { max-width: 100%; height: auto; border: 1px solid var(--line);
               border-radius: 4px; }
  figcaption { font-size: 0.88rem; color: var(--muted); margin-top: 0.3rem; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
  th, td { padding: 0.4rem 0.6rem; border: 1px solid var(--line); text-align: left; }
  th { background: #f0f4f8; }
</style>
</head>
<body>

<header>
  <h1>Project title</h1>
  <p><!-- AI: ONE sentence framing the answer (not the question). --></p>
</header>

<main>

<section class="hero" id="headline">
  <h2>Headline finding</h2>
  <!-- AI: ONE sentence — the single most important thing the reader
       should take away. Then 3-6 metric cards with the numbers behind it. -->
  <div class="metric-grid">
    <!-- AI: 3-6 <div class="metric-card"> with label / value / delta. -->
  </div>
  <!-- AI: optional — embed the single most important figure here, with a
       caption that names what to see + what it means. -->
</section>

<section id="key-findings">
  <h2>Key findings</h2>
  <!-- AI: 3-6 sub-sections, each tied to ONE supported claim / decision.
       Organise by hypothesis or argument, NOT by workspace step number.
       Each finding: claim sentence + supporting figure or table + caption
       that interprets the evidence. Skip findings that don't move the
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
) -> dict[str, Any]:
    """Write a tiny skeleton synthesis file.

    Returns status='exists' (idempotent) if the file is already present
    and overwrite=False. The AI is expected to author the content; this
    tool only seeds section headers and protocol-pointing comments.
    """
    if kind not in SCAFFOLDS:
        return {
            "status": "error",
            "message": f"Unknown kind '{kind}'. Valid: {', '.join(sorted(SCAFFOLDS))}.",
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
