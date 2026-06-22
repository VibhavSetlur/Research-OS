# Project layout

This is the canonical reference for the directory layout Research-OS
builds inside your project. It is the **single source of truth** for what
lives where — the wizard, `sys_boot`, and the in-project READMEs all derive
from the same definition (`LAYOUT_SPEC` in `research_os/project_ops.py`), so
this document and the folders on disk can't drift apart.

If you only read one section, read [The safety backbone](#the-safety-backbone):
those folders mean the same thing in every project, regardless of mode.

---

## The safety backbone

Every project — whatever its workspace mode — is built on the same
mode-agnostic backbone. These directories carry the same contract
everywhere:

| Directory | What it's for | Who writes it |
|---|---|---|
| `.os_state/` | Provenance + state (the audit ledger, step graph, config). The **only hard-locked tree**. | Research-OS only — never edit by hand. |
| `docs/` | Project overview + glossary. | You + the AI. |
| `inputs/` | Your source-of-truth drops. See below. | You (drops); AI may annotate. |
| `inputs/raw_data/` | The raw data you bring to the project. **Soft-guarded** — overwrites are flagged. | You. |
| `inputs/literature/` | The formal sources you bring (PDFs, papers). **Soft-guarded**. | You. |
| `inputs/context/` | Free-form context: methodology notes, meeting takeaways, "if a new analyst opened this folder today, what would they need to know." AI-writable. | You + the AI. |
| `workspace/` | The work surface — where the actual analysis / build happens. | The AI (governed by gates). |
| `workspace/logs/` | The audit + override trail. | Research-OS. |
| `workspace/scratch/` | The AI sandbox: throwaway probes, scratch code, intermediate junk. No gates here. | The AI, freely. |
| `environment/` | Reproducibility: environment exports, lockfiles, the "how to re-run this" record. | The AI. |

Two rules worth internalising:

* **`inputs/` is yours, `workspace/` is the AI's.** You stage source
  material in `inputs/`; the AI does its work in `workspace/` and writes
  conclusions to `synthesis/`. `inputs/raw_data` and `inputs/literature`
  are soft-guarded so the AI can't silently clobber what you dropped.
* **`.os_state/` is off-limits.** It is the provenance ledger. Editing it
  by hand breaks the audit guarantees that make the project trustworthy.

---

## Eager vs lazy

Folders are created in one of two ways:

* **Eager** — created at `research-os init`, always present, each seeded
  with a tiny README so an empty folder is never a dead end.
* **Lazy** — created only when the first artefact actually lands in them
  (tools call `ensure_lazy_dir` first). This keeps a fresh project from
  showing empty folders for work that hasn't started yet — e.g.
  `synthesis/` doesn't appear until there's something to synthesise.

---

## Workspace modes

The backbone is constant; the **work surface** between `inputs/` and the
final write-up is shaped by your project's *workspace mode*. You pick the
mode at init (or let the wizard infer it). Each mode only adds a small set
of mode-specific folders — nothing about the safety backbone changes.

### `analysis` (default)

The classic linear, numbered-step model. Work proceeds as
`workspace/01_*`, `workspace/02_*`, … and the paper lands in `synthesis/`.
`literature/` at the top level is the project-wide corpus of record
(aggregated from every step, distinct from your `inputs/literature/` drops).

* **Adds:** `literature/`, `synthesis/` (lazy)

### `tool_build`

Research-OS sits *above* your tool as a governance layer. The tool itself
lives in an **inner project directory** that gets its own `git init`; the
outer Research-OS project tracks *why* and *whether it's done*:

* `spec/` — what you're building + the design.
* `decisions/` — Architecture Decision Records (ADRs).
* `eval/` — the benchmark / eval harness that defines "done".

* **Adds:** `spec/`, `decisions/`, `eval/`
* **No `synthesis/`** — the deliverable is the tool, not a paper.

### `exploration`

Scratch-first. `workspace/scratch/` is your home base; gates are light.
The numbered-step + log surface materialises only once a probe earns
promotion to a real step.

* **Adds:** nothing up front.
* **Lazy:** `workspace/logs/`, `synthesis/` (appear on promote).

### `notebook`

Jupyter-first. The unit of work is a notebook, not a numbered step.

* `notebooks/` — your notebooks (the unit of work).
* `data/` — inputs the notebooks read.
* `outputs/` — what they emit (figures, tables, exports).

* **Adds:** `notebooks/`, `data/`, `outputs/`

### `multi_study`

A program / portfolio layout for work that spans several sub-studies.

* `studies/` — each sub-study (itself a small project surface).
* `shared/` — the program-wide commons: codebook, preregistration, the
  governing protocol every study inherits.
* `roll_up/` — cross-study synthesis + meta-analysis.

* **Adds:** `studies/`, `shared/`, `roll_up/`

### `hybrid` (research + software)

Reuses the `analysis` layout. Any software lives in its own inner repo /
package, auto-detected by Research-OS (`detect_software_components`) and
surfaced in the workflow DAG + `sys_boot` rather than scaffolded as a
fixed folder.

* **Adds:** `literature/`, `synthesis/` (lazy) — same as `analysis`.

---

## Mode reference table

What each mode creates at init (eager) versus on first use (lazy). The
backbone (`.os_state`, `docs`, `inputs/*`, `workspace`, `workspace/logs`,
`workspace/scratch`, `environment`) is present in every mode.

| Mode | Mode-specific dirs | `synthesis/` | Lazy |
|---|---|---|---|
| `analysis` | `literature/` | yes (lazy) | `synthesis` |
| `tool_build` | `spec/` `decisions/` `eval/` | no | (none) |
| `exploration` | (none up front) | yes (lazy) | `workspace/logs`, `synthesis` |
| `notebook` | `notebooks/` `data/` `outputs/` | yes (lazy) | `synthesis` |
| `multi_study` | `studies/` `shared/` `roll_up/` | yes (lazy) | `synthesis` |
| `hybrid` | `literature/` | yes (lazy) | `synthesis` |

---

## For maintainers

This document is generated from one definition. To change the layout:

1. Edit `LAYOUT_SPEC` in `src/research_os/project_ops.py` — declare only
   the mode's `work` surface, whether it has `synthesis`, and its `lazy`
   set. The composer (`_compose_layout`) builds the three directory tuples
   (`top_level_dirs` / `eager_dirs` / `lazy_dirs`) deterministically.
2. `SCAFFOLD_PROFILES` and the back-compat constants (`TOP_LEVEL_DIRS`
   etc.) derive automatically, so the safety backbone can never drift
   between modes.
3. Update this doc's mode table to match. `describe_layout(mode)` renders
   the per-mode eager/lazy breakdown if you want to confirm.

Never re-list directory names inline elsewhere in the codebase or docs —
read `LAYOUT_SPEC` / `SCAFFOLD_PROFILES` / `describe_layout()` instead.
