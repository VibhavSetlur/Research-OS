# Paper compilation pipeline

The canonical model for how a Research-OS project goes from "AI has
written some prose" to "researcher opens a PDF". One pipeline, one
canonical intermediate format, two compile backends.

## The pipeline

```
                    ┌─────────────────────────────┐
                    │  AI-facing intermediate     │
                    │  synthesis/paper.md         │  ← AI writes / edits here
                    └──────────┬──────────────────┘
                               │  tool_paper_compile
                               │  (auto on every synthesis save;
                               │   manual via the tool)
                               ▼
        ┌──────────────────────┴─────────────────────────┐
        │                                                │
        ▼                                                ▼
┌──────────────────────┐                  ┌──────────────────────┐
│  Typst backend       │                  │  LaTeX backend       │
│  paper.md → paper.typ│                  │  paper.md → paper.tex│
│  typst compile       │                  │  pdflatex            │
└─────────┬────────────┘                  └─────────┬────────────┘
          │                                         │
          └──────────────┬──────────────────────────┘
                         ▼
        ┌─────────────────────────────────────┐
        │  Researcher-facing artifact         │
        │  synthesis/paper.pdf                │  ← researcher reads / shares
        └─────────────────────────────────────┘
```

## Format conventions

| Concern | Where it lives |
|---|---|
| AI writes prose | `synthesis/paper.md` (CommonMark with research-os extensions: cite-keys, figure refs, table refs, theorem blocks) |
| Backend-rendered intermediate | `synthesis/paper.typ` (default) or `synthesis/paper.tex` (when `pdf_compile_engine: latex`) |
| Final artifact | `synthesis/paper.pdf` |
| Dashboard preview | `synthesis/paper.pdf` (embedded as `<embed>`); `synthesis/paper.md` available via "View source" |
| Researcher edits | `synthesis/paper.md` (re-compiles on save via `tool_paper_compile`) |
| Bibliography source | `synthesis/refs.bib` (BibTeX, both backends accept) OR `workspace/citations.md` (markdown, auto-converted) |

## Choosing the backend

The default is **Typst**. Reasoning:

* Fast incremental compile (~50ms for a 30-page paper vs ~5s for LaTeX)
* Better default typography for screen reading
* Simpler markup; AI errors are caught by the type checker
* Math + figures + bibliography + cross-refs all built-in

LaTeX is opt-in via:

```yaml
# inputs/researcher_config.yaml
writing_preferences:
  pdf_compile_engine: latex
```

Use LaTeX when:

* The target venue requires `.tex` submission (most physics, math, CS)
* You need a venue-specific class file (`elsarticle.cls`, `revtex4-2.cls`, etc.) for which no Typst equivalent yet exists
* You're collaborating with a co-author who only edits LaTeX

Use Typst when:

* You're drafting from scratch
* The target venue accepts PDF (most humanities, qualitative, biology, …)
* You want fast preview cycles

## What "edits the paper" means

Three places to write paper prose, in order of frequency:

1. **AI writes most prose.** `mem_methods_append`, `mem_decision_log`,
   `tool_drafter_loop` etc. write into per-step `conclusions.md` and
   `methods.md`; `tool_paper_drafter` weaves them into
   `synthesis/paper.md`.

2. **Researcher patches `synthesis/paper.md` directly.** This is the
   expected friction-low edit mode — open it in your editor, change
   prose, save. `tool_paper_compile` re-runs the backend and refreshes
   `paper.pdf`.

3. **Researcher edits the rendered `.typ` / `.tex`.** Discouraged
   except for backend-specific layout tweaks (custom title page, journal-
   specific section breaks). The intermediate is overwritten on every
   markdown re-compile, so backend-only changes get lost unless
   captured in a `synthesis/_template_overrides/` overlay (see
   `docs/RESEARCHER_GUIDE.md § Paper layout overrides`).

## Tools surface

| Tool | What it does |
|---|---|
| `tool_paper_drafter` | Walks workspace, writes `synthesis/paper.md` (review-rewrite loop with persona judges) |
| `tool_paper_compile` | Runs the backend (typst by default, latex if configured) and emits `synthesis/paper.pdf` |
| `tool_paper_review` | Adversarial review of the current `paper.md` + verdicts on each section |
| `tool_drafter_loop` | Generic review-rewrite shell that backs `tool_paper_drafter`, `tool_slides_drafter`, etc. |

## Per-pack overrides

Each domain pack ships a `paper_sections: (str, ...)` tuple via its
`PackRegistration` that says which sections appear in
`synthesis/paper.md` for projects of that pack:

| Pack | Section ordering |
|---|---|
| `wet_lab` / `engineering` / `theory_math` | IMRaD (intro, methods, results, discussion) + appendix |
| `humanities` | Six interpretive headings (thesis, contextual framing, close-readings, critical conversation, conclusion + stakes, references) |
| `qualitative` | Background, study design, themes, voices, theoretical contribution, references |

The compile pipeline is identical across packs; only the section
template differs.

## File-format invariants (stable across v2.x)

* `synthesis/paper.md` IS canonical (intermediate). Removing or
  renaming this path is MAJOR-breaking.
* `synthesis/paper.pdf` IS the final researcher-facing artifact.
  Removing or renaming is MAJOR-breaking.
* `synthesis/paper.typ` and `synthesis/paper.tex` are backend-
  intermediates. Their existence + content shape are stable but their
  exact contents are MINOR-mutable as backend rendering improves.
