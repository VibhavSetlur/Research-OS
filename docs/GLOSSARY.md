# Glossary

The vocabulary Research OS uses for a project's structure. This is the
repo-level reference; each generated *project* also gets its own
domain glossary (a `glossary.md` under its `docs/`, a table the AI fills
with the domain terms it meets in your data and literature).

## Project structure

| Term | What it is |
|---|---|
| **workspace mode** | The shape of a project: `analysis` (numbered steps → synthesis, the default), `tool_build` (governs a software build), `exploration` (scratch-first), `notebook`, `multi_study`. Reported by `sys_boot`. |
| **step** (a.k.a. **path**) | One numbered unit of analysis: `workspace/NN_<slug>/`. The chronological backbone — every meaningful analysis lives in one. Created with `sys_path(operation='create')`. |
| **PATH container** | `workspace/<descriptive>_PATH_<k>/` — a folder that *groups* a run of steps that explored one direction. Created with `sys_path(operation='group', name=, steps=[…])`. Step numbering stays **continuous** across containers (path 2 keeps going at step 06; it never resets), so steps can be moved or merged without renumbering. |
| **dead-end** | A step abandoned but preserved on the record (`sys_path(operation='abandon')`). |

## Per-step files

| File | What it is |
|---|---|
| **plan.md** | Written at step creation, **before** any code: the pre-step plan (prior-step recap + this step's design + open questions for the researcher). Co-scientist-style iterative planning — propose → critique → refine, then build. |
| **README.md** | The 60-second plain-English overview: goal, inputs, methods (one line each), headline, outputs, decision. `## In plain English` is the canonical plain-language summary. Auto-filled by `tool_path_finalize`. |
| **conclusions.md** | The deep report: findings, hypothesis evidence, full methods, limitations, and the **decision with lineage** (how the previous step led here + what changed across this step's own iterations). The per-step source of truth. |
| **data/** | `project_inputs/` (symlink → `inputs/raw_data/`), `past_step_input/` (symlink → the previous step's `next_step_output/`), `next_step_output/` (what the next step consumes), and `share/` (a curated dataset you package to hand to a collaborator). |
| **outputs/** | `figures/` + `tables/` (analysis outputs, each with a `.caption.md` + `.prov.json`) and `reports/` (optional *snapshot presentation* artefacts — a one-off dashboard/slide/diagram, not where findings live). |
| **literature/** | The step's papers (`<key>.pdf` + `.meta.yaml`) and `findings_vs_literature.md` (this step's claims debated against the sources, with citation keys). |
| **environment/**, **scripts/**, **context/** | Reproducibility snapshot, runnable analysis scripts, and free-form prose notes / hand-overs. |

> Each figure ships exactly three sidecars: the image, a `.prov.json`
> provenance record, and a `.caption.md`. The plain-English
> interpretation lives inline in `conclusions.md` next to the embed
> (the old per-figure `.summary.md` sidecar was retired in 3.2, as was
> the derived per-step `step_summary.yaml`).

## Project-level

| Term | What it is |
|---|---|
| **inputs/** | Immutable: `raw_data/`, `literature/`, `context/`, plus `researcher_config.yaml`, `intake.md`, and `research_plan.md`. The AI reads but never modifies these. |
| **research_plan.md** | `inputs/research_plan.md` — the living whole-project plan (question, hypotheses, planned step sequence, iteration log) the AI and researcher refine together. The arc each step's `plan.md` fits into. |
| **literature/** (root) | The project **corpus of record**: every paper used anywhere — `inputs/literature/` → `literature/inputs/`, and each step's papers → `literature/steps/<NN_slug>/`. Auto-aggregated at finalize; feeds `workspace/citations.md`. |
| **workspace/** | `analysis.md` (narrative decision log), `methods.md`, `tools.md`, `citations.md` (auto-bibliography), `audit.md` (project-end meta-review), `logs/` (audit detail), `scratch/`, plus the numbered steps. |
| **audit.md** | `workspace/audit.md` — the single human-facing meta-review, written at the ship gate: per-step concerns with evidence paths, content hashes, and suggested fixes. The per-gate machine detail lives in `workspace/logs/audits/`. |
| **synthesis/** | The deliverables (paper / poster / slides / dashboard) — created only when the researcher asks. |
| **STATE.md** | Project-root status file a fresh AI session reads first. |

## Reasoning units

| Term | What it is |
|---|---|
| **hypothesis** | A registered testable claim (`H1`, `H2`, …) tracked across steps (`mem_hypothesis_add`). |
| **finding** | A quantitative result in a step's `## Findings`. |
| **decision** | The PROCEED / BRANCH / DEAD-END call closing a step, logged to `analysis.md`. |
| **grounding** | Tying a claim to evidence — a workspace output or a cited paper — so numbers in the paper trace to where they came from. |
| **audit gate** | A quality check (completeness, claims, prose, literature, …). Most are advisory; the **ship gate** (`tool_finalize_project`) is the one that can refuse "done". |
