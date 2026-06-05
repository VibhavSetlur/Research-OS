# Lens 01 — Biology / snRNA-seq End-to-End Stress

Fresh-agent dry-run of the FULL Research-OS workflow on a hypothetical
mouse-brain snRNA-seq project. **Hypothesis:** *Does LPS treatment
induce IL-6 / TNF expression in microglia of mouse brain snRNA-seq?*

Method: simulated by reading protocols + TOOL_DEFINITIONS + tool action
modules + running the live router (`route_request`) on representative
prompts. No project was created on disk.

Repo state checked: 212 tools in `TOOL_DEFINITIONS`, 114 protocols
under `src/research_os/protocols/**.yaml` (excluding `_router_index`).

---

## Trace

| # | Stage                                  | Tool / Protocol                                                                                  | Outcome                                                                                                                                                                                                                            |
|---|----------------------------------------|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | Boot                                   | `sys_boot` (NOT `bootstrap_check` — the prompt-given name does not exist as a tool)              | Returns state + config + history + dep inventory + pause + next_protocol + active_plan. Single call replaces 4–5 sister calls. Solid contract.                                                                                       |
| 2 | First-message routing                  | `tool_route(prompt="…microglia…snRNA-seq?")`                                                     | Live test → `methodology/deep_domain_research`, L3, semantic, high. Reasonable for a domain-orientation ask.                                                                                                                       |
| 3 | Workspace scaffold                      | `sys_workspace_scaffold` (only on re-scaffold; init handles it)                                  | OK. Creates standard layout (`inputs/{raw_data,literature,context}`, `workspace/`, etc.).                                                                                                                                          |
| 4 | Config bootstrap                       | `inputs/researcher_config.yaml` (template) — interaction.autonomy_level, model_profile, etc.     | Default template is comprehensive (writing prefs, gate_strictness, language stack, API keys). Sound.                                                                                                                              |
| 5 | Intake autofill                        | `tool_intake_autofill`                                                                            | Reads `inputs/` → writes `inputs/intake.md` + `docs/research_overview.md` + registers hypotheses to state. Schema documented in tool description.                                                                                  |
| 6 | Hypothesis registration                | `mem_hypothesis_add` (auto via intake) + `mem_hypothesis_list` / `mem_hypothesis_update`         | OK. H1 = "LPS → IL-6/TNF↑ in microglia". `mem_log` legacy dispatch also routes correctly.                                                                                                                                          |
| 7 | Methodology decision: pick_tool_stack  | `methodology/pick_tool_stack`                                                                     | YAML explicitly calls out single-cell → scanpy (Python) + DE → R Bioconductor (DESeq2/edgeR/limma). Excellent biology-aware doctrine — strongest piece of the workflow for this scenario.                                          |
| 8 | Per-step loop entry                    | `guidance/analysis_plan`                                                                          | Live router: "run a baseline EDA" → analysis_plan, L3. "next experiment: DESeq2" → analysis_plan, L3. Works.                                                                                                                       |
| 9 | Step folder                            | `sys_path_create name="01_qc_libsize" hypothesis="H1: …"`                                         | Creates `workspace/NN_<slug>/{scripts,literature,data/{input,output},outputs/{reports,figures,tables},environment}`. Spec is consistent with `analysis_plan.create_step_folder`.                                                  |
| 10 | Per-step pipeline DAG                 | `tool_step_pipeline_define` → `tool_step_pipeline_run`                                            | DAG = 7-node template (ingest→validate→clean→featurize→split→fit→diagnose→visualize→report). Required for >2 scripts — hard gate via `tool_audit_step_completeness`.                                                              |
| 11 | Lit-ground methods (HARD GATE)        | `tool_research_method` + `tool_literature_search_and_save` + `tool_search_pubmed/semantic`        | Per-step methods grounding is mandatory; `tool_path_finalize` BLOCKS if `conclusions.md` cites references but `workspace/logs/searches.log` shows no `tool_search_*` calls. Aggressive in a good way.                              |
| 12 | mem_methods_append + mem_decision_log | `mem_methods_append` + `mem_decision_log`                                                          | Both required by analysis_plan; both wired with clear schemas.                                                                                                                                                                     |
| 13 | Script execution (Python + R + bash)   | `tool_python_exec` / `tool_r_exec` / `tool_bash_exec` / `tool_rmarkdown_render`                   | Per-language separation respects pick_tool_stack output. Long-running paths (>60s OR shared_server=true) MUST use `tool_task_run` + `tool_task_status` — analysis_plan documents this.                                            |
| 14 | Per-step outputs                       | reports/ + tables/ + figures/ (focal `<NN>_<slug>.png`)                                            | Three categories enforced; missing focal figure = HARD FAIL via `tool_audit_step_completeness`. Sidecars `<name>.caption.md` + `<name>.summary.md` required.                                                                       |
| 15 | conclusions.md + hypothesis evidence   | `mem_hypothesis_update H1 status=…`                                                               | Documented sections: Plain-language summary / Findings / Hypothesis evidence / Methods / Limitations / Decision / Next steps. Required by spec.                                                                                    |
| 16 | Lit-ground findings (per step)         | `literature/literature_per_step` → `tool_audit_step_literature`                                   | 7-step inner loop: extract claims → build queries → search → download top-3 PDFs → write `findings_vs_literature.md` (AGREES\|DISAGREES\|EXTENDS\|DEFERRED) → register grounding → CoVe verify top-3 claims. Comprehensive.        |
| 17 | Per-step env snapshot                  | `sys_env_snapshot step_id=…` OR `tool_step_env_lock`                                              | step_env_lock is the publication-grade variant; supports conda + dockerfile + apptainer + entrypoint.                                                                                                                              |
| 18 | Step bundle close                      | `tool_step_complete` (one call = finalize + completeness + lit + revision_options)                | Bundles `tool_path_finalize` + `tool_audit_step_completeness` + `tool_audit_step_literature` + `tool_step_revision_options`. Reduces 4 calls to 1.                                                                                |
| 19 | Repeat steps 8–18 × 6–10               | qc → norm → integrate → cluster → marker → DE (DESeq2 in R) → GO enrich → plotting                | Each step opens its own folder; cross-step provenance via `.prov.json` + workflow_dag (`tool_workflow_dag`).                                                                                                                       |
| 20 | Master quality audit                  | `tool_audit_quality_full` (the prompt's "tool_audit_master" — that name does not exist)            | Runs step_completeness + code_quality + prose + claims + preregistration_diff. Writes `workspace/logs/audit_master.md`. Called by `tool_synthesize` automatically.                                                                |
| 21 | Synthesis plan                         | `tool_synthesize_plan` + `synthesis/synthesis_paper`                                              | Multi-turn enforcement: refuses to chain >1 section per turn (anti-one-shot). Per-section drafting via `writing/writing_methods`, `writing/writing_results`, etc.                                                                  |
| 22 | Citation verification                  | `tool_citations_verify`                                                                            | HARD gate in `tool_synthesize` final_assembly; blocks until pending citations resolve through Crossref/S2/PubMed/arXiv.                                                                                                            |
| 23 | Typst PDF                              | `tool_paper_compile_typst`                                                                        | Reads `synthesis/paper.md` → emits `synthesis/paper.typ` + `synthesis/biblio.yml` (Hayagriva) → runs `typst compile`. Resolves venue from `writing_preferences.venue_template`. Clean handoff.                                     |
| 24 | Dashboard v2                           | `tool_dashboard_create` (default = `render_dashboard_v2`, legacy switch `dashboard_legacy=true`)  | v2 = single-page-app (sidebar nav + MiniSearch + filter chips + Story/Explore toggle, fully offline). Audience-tailored. Step-completeness gate is soft (warnings).                                                               |
| 25 | Cross-checks                           | `tool_audit_quality_full` (re-run) + `tool_audit_version_coherence` + `audit/pre_submission_checklist` | Pre-submission gate is the final blocker. Version coherence catches outputs whose `.prov.json` points at a stale script.                                                                                                          |

**Net assessment:** the full pipeline (intake → 6–10 steps → synthesis → Typst PDF → v2 dashboard → final audit) is wired end-to-end. Every gate has a documented bypass (`override_completeness_gate`, `override_literature_gate`) routed to `workspace/logs/override_log.md`. Tool contracts are clear; dependencies between tools are explicit; the AI is told *what to do next* at every step via the `analysis_plan` and `synthesis_paper` protocol bodies.

---

## Bugs found

### BUG/MINOR — `sys_help` stale category counts surface wrong picture to AI
- `src/research_os/server.py:4878` previously read `"methodology": "method picking + per-method protocols (29)"` — actual count is 42. **Fixed in this lens.**
- `src/research_os/server.py:4882` previously read `"synthesis": "final deliverables (14: …)"` — actual count is 18. **Fixed in this lens.**
- Impact: when an AI calls `sys_help topic="categories"` to orient, it gets the wrong sizes — minor but easy to mistrust the orientation block.

### BUG/MINOR — `sys_active_tools` description hardcodes stale tool count
- `src/research_os/server.py:1675` previously read `"…instead of triaging all 143 tools per turn."` — actual count is 212. **Fixed in this lens.**
- This is an AI-facing description; small-model agents do read it.

### BUG/MINOR — `tool_audit_master` references to a non-existent tool name
- The current canonical name is `tool_audit_quality_full`. References to the old name remain in:
  - `docs/ROADMAP.md:252` (Theme 15 "Audit family bundle") — **fixed in this lens** (renamed to `tool_audit_quality_full`).
  - `src/research_os/tools/actions/audit/step_literature.py:9` (module docstring) — **fixed in this lens**.
- If a researcher (or an AI) greps for `tool_audit_master` they get bad pointers.

### BUG/MINOR — Router-index hierarchy gap for two L2 sub_intents
File: `src/research_os/protocols/_router_index.yaml`. Two protocols declare an `intent_class + sub_intent` pair that does NOT exist in the `hierarchy:` map:
- `literature/literature_per_step` → `literature.per_step_grounding` (not in `hierarchy.literature.sub_intents`).
- `synthesis/printable` → `synthesize.printable` (not in `hierarchy.synthesize.sub_intents`).

Consequence: at L2 ambiguity, the router falls back to ask-the-user with a sub-intent label that has no human-readable summary. Not a runtime crash but a routing-experience papercut. Trivial fix would be to add two lines to the hierarchy block — NOT applied because the project rule says "no logic changes / no new protocols / no new index keys without explicit approval."

### BUG/MINOR — Semantic router miscarries `DESeq2 differential expression`
Live router test (`route_request`):

```
"fit a DESeq2 differential expression model"  → methodology/bayesian_analysis  L=3 semantic HIGH
"do a DESeq2 DE"                              → None                            L=0
"DESeq2 contrast LPS vs control"              → None                            L=0
"scRNA-seq QC and normalization"              → methodology/deep_domain_research L=3 semantic
"single-cell clustering with leiden"          → methodology/deep_domain_research L=3 semantic
```

Root cause: `methodology/bayesian_analysis`'s YAML mentions "posterior" / "Bayesian Workflow" / DE-adjacent terms; its semantic embedding wins over the generic `guidance/analysis_plan` for an embedding cosine-similarity match on "DESeq2 … model". For domain-classic biology phrasings ("do a DESeq2 DE"), the semantic confidence drops below the floor and there is NO trigger fallback for DESeq2 — so the AI gets an `ask_user` with no helpful candidate list.

Impact in a real biology project: the AI loads the WRONG protocol (Bayesian workflow) and starts asking for prior elicitation when the user wanted frequentist DE testing.

Severity: MEDIUM at the user-experience level (silent wrong protocol). Suggested target v1.9.3 — add `"DESeq2"`, `"differential expression"`, `"DEG"`, `"scRNA-seq QC"`, `"single-cell clustering"`, `"library size normalization"`, etc. as **explicit triggers** on `guidance/analysis_plan` (or a dedicated `methodology/methodology_selection` entry) so the trigger fallback wins when semantic confidence is low.

### REGRESSION risk — `synthesis_paper` router decomposition omits the Typst compile step
`synthesis/synthesis_paper` decomposition in `_router_index.yaml`:
```
- tool: tool_synthesize_plan
- tool: tool_audit_synthesis
- tool: tool_audit_citations
- tool: tool_synthesize  args: {output_type: paper}
```
Missing: `tool_paper_compile_typst`. The protocol body's *turn 7* (assemble + compile to PDF) covers it, but a small-model agent walking the persisted active_plan via `tool_plan_advance` will NEVER fire the Typst compile unless the researcher explicitly asks. The PDF deliverable is the actual *paper*; markdown is the intermediate.

---

## Friction

### FRICTION/HIGH — Doc-vs-code count mismatch in 7 user-facing places
The MEMORY-banked maintainer guidance ("Writing docs that reference tool counts — they go stale fast") is being violated in production docs:
- `docs/README.md:19` — "all 113 protocols" (actual 114).
- `docs/README.md:20` — "all 146 MCP tools" (actual 212).
- `docs/START.md:133` — "113 protocols".
- `docs/START.md:141` — "146 MCP tools".
- `docs/AI_GUIDE.md:84` — "113 protocols, organised in 9".
- `docs/AI_GUIDE.md:91` — "methodology (42 protocols, incl. **v1.4.0** …)" — correct count.
- `docs/AI_GUIDE.md:95` — "synthesis (17 protocols)" — actual 18.
- `docs/AI_GUIDE.md:336` — "all 113 protocols indexed".
- `docs/PROTOCOLS.md:3` and `:20` — "113 YAML protocols", "**Total** | **113**" + per-category row counts that should be re-summed (synthesis row says 17, actual 18).
- `docs/TOOLS.md:3` — "146 MCP tools".
- `docs/FAQ.md:61` — "Do I have to read all 113 protocols".
- `docs/RESEARCHER_GUIDE.md:6` — "all 113 protocols and 146 MCP tools".
- `docs/ROADMAP.md:35`, `:43`, `:120`, `:127`, `:133`, `:482`, `:484`, `:496`, `:497` — repeated.
- `CLAUDE.md:180` — "Protocols (88)" — VERY stale.

Severity HIGH because (a) these are user-facing docs that "lie" to the reader, (b) it's exactly the anti-pattern the maintainer CLAUDE.md warns against, and (c) fixing means picking a discipline (omit count, or git-grep-bump-on-release). The CHANGELOG.md historical entries are immutable per release process — not fixed here. I did NOT mass-rewrite these because the policy is "fix typos / stale counts" but the volume crosses my one-line trivial threshold for several files; this is a v1.9.3 cleanup PR worth its own commit.

### FRICTION/HIGH — `synthesis_paper` is 10 turns mandatory
The protocol enforces "ONE section per researcher prompt", even in autopilot. For a coaching researcher this is a feature; for a researcher who already has a polished draft and just wants the final assembly, this is 10 round-trips minimum. There is no `auto_proceed=true` knob exposed on `tool_synthesize` to short-circuit the multi-turn loop, even though autopilot mode permits it in spec.

### FRICTION/MEDIUM — `DESeq2`/`scRNA-seq` semantic miss requires `ask_user`
See BUG above. The user-facing friction is two extra round-trips (router returns L=0, asks the user, re-routes). For a biology researcher this is mildly annoying because the field-classic phrasing isn't a trigger.

### FRICTION/MEDIUM — `tool_audit_quality_full` skips `tool_audit_step_literature`
`tool_audit_quality_full` runs step_completeness + code_quality + prose + claims + preregistration_diff but NOT `tool_audit_step_literature`. The step-literature gate is run by `tool_step_complete` (per-step) and by `tool_audit_synthesis` (synthesis-time), but the "master" audit doesn't include it. A researcher who calls `tool_audit_quality_full` between steps and gets a clean report may be surprised when `tool_audit_synthesis` blocks them later for missing per-step literature.

### FRICTION/MEDIUM — `synthesis_paper.decomposition` ends at `tool_synthesize`
See REGRESSION above. The decomposition feeds `tool_plan_advance`; if a small-model agent walks the plan, it stops at the markdown. The protocol body covers compile_typst, but the decomposition is what the active_plan replays.

### FRICTION/LOW — `synthesis_paper` prerequisites assume `inputs/literature_index.yaml ≥ 3 entries`
That file is optional and not part of intake autofill. A researcher who only put PDFs in `inputs/literature/` (not the index YAML) gets a hard prereq fail at synthesis time. The fix is either to derive entries from on-disk PDFs (via `.meta.yaml` sidecars) automatically, or relax the prereq.

---

## Doc–code mismatches

| Doc / line | Claim | Reality |
|---|---|---|
| `docs/PROTOCOLS.md:3, :20` | 113 protocols | 114 (+1 since the doc was last bumped). Per-category row 13 (synthesis) says 17, actual 18. |
| `docs/TOOLS.md:3` | 146 MCP tools | 212. |
| `docs/AI_GUIDE.md:84, :95, :336` | 113 protocols / 17 synthesis | 114 / 18. |
| `docs/START.md:133, :141` | 113 protocols / 146 tools | 114 / 212. |
| `docs/README.md:19, :20` | 113 / 146 | 114 / 212. |
| `docs/FAQ.md:61` | "all 113 protocols" | 114. |
| `docs/RESEARCHER_GUIDE.md:6` | "113 protocols and 146 MCP tools" | 114 / 212. |
| `docs/ROADMAP.md` (multiple) | 113 / 146 | 114 / 212. |
| `CLAUDE.md:180` | Protocols (88) | 114. |
| `src/research_os/server.py` (was `:4878`) | sys_help: methodology (29) | 42. **Fixed in this lens.** |
| `src/research_os/server.py` (was `:4882`) | sys_help: synthesis (14) | 18. **Fixed in this lens.** |
| `src/research_os/server.py` (was `:1675`) | sys_active_tools description: "all 143 tools" | 212. **Fixed in this lens.** |
| `docs/ROADMAP.md:252` (Theme 15) | `tool_audit_master` is the audit family bundle | Actual tool: `tool_audit_quality_full`. **Fixed in this lens.** |
| `src/research_os/tools/actions/audit/step_literature.py:9` | "the caller (typically `tool_audit_master`)" | Actual: `tool_audit_quality_full`. **Fixed in this lens.** |
| Prompt-given workflow stage names | `bootstrap_check` / `tool_audit_master` | Actual: `sys_boot` / `tool_audit_quality_full`. Not a code bug — calling out for the synthesis report so the audit-report wording uses the real names. |

---

## Missing AI guidance

1. **No "next step" after `tool_paper_compile_typst` finishes.** The tool returns `pdf_path`, `page_count`, `citation_count`, `typst_warnings`, `typst_errors` — but there is no `next_steps` / `advice` field telling the AI "now run `audit/pre_submission_checklist` before the researcher submits." A fresh agent has to know.
2. **No bridge from `analysis_plan.create_step_folder` to `methodology/methodology_selection`.** The protocol body lists naming conventions across domains (genomics: `deseq2_de`, `gsea_pathway`, ...) but never tells the AI *when to invoke `methodology/methodology_selection` first*. For a researcher whose hypothesis demands picking between Wald-test DESeq2 vs LRT-DESeq2 vs limma-voom, the AI is on its own.
3. **`tool_synthesize` decomposition stops at the markdown.** See REGRESSION above. Decomposition should include `tool_paper_compile_typst` (when `pdf_compile_engine=typst`) or `tool_latex_compile` (when `latex`).
4. **`tool_audit_quality_full` doesn't tell the AI it skips the per-step literature gate.** A small-model agent reading the description sees "Master auditor" and "Runs … tool_preregister_diff in one shot; aggregates the blocker set" but no "NB: per-step literature gate is separate; call `tool_audit_step_literature` per step OR rely on `tool_step_complete` to have caught it."
5. **No guidance on what to do when router returns L=0 for a domain-classic phrasing.** A biology researcher who says "do a DESeq2 DE" gets an `ask_user` block — the AI should know to suggest `guidance/analysis_plan` as a fallback by default. The current `ask_user` text is generic ("I couldn't match your prompt to a protocol — please pick one of L1 buckets").
6. **`pick_tool_stack` is excellent but not auto-invoked.** `analysis_plan.scope_step` says "LANGUAGE/TOOL-STACK SUB-STEP: if the step's method choice is non-trivial … invoke `methodology/pick_tool_stack` … BEFORE writing code". This is doctrine, not enforcement — no audit gate verifies `scratch/stack_plan.md` was written before `tool_python_exec`/`tool_r_exec`. A small model will skip it.
7. **`dashboard_v2`'s soft completeness gate** — description says "Step-completeness gate is soft (warnings only)". A researcher running the dashboard as their FINAL deliverable may not realize the gate is soft + miss a real completeness blocker. The advice field on warnings is good but could be louder.

---

## What I confirmed worked end-to-end

- Boot → route → protocol load chain via `sys_boot` + `tool_route` + `sys_protocol_get format='summary'` is sound.
- Per-step folder lifecycle from `sys_path_create` through `tool_step_pipeline_define` / `tool_step_pipeline_run` to `tool_step_complete` is consistent and well-documented.
- The per-step literature loop (`literature/literature_per_step` → `tool_audit_step_literature`) is a strong gate — comprehensive, well-doctrinated.
- `pick_tool_stack` is the strongest piece of biology-aware doctrine I found: it explicitly tells the AI scanpy for scRNA-seq, DESeq2/edgeR/limma in R for bulk DE, Seurat for sc when upstream is R-only.
- `tool_paper_compile_typst` has a clean contract (input = `synthesis/paper.md`, output = pdf_path) with venue auto-resolution from `researcher_config.writing_preferences.venue_template`.
- `tool_dashboard_create` correctly defaults to v2 renderer with explicit `dashboard_legacy=true` fallback.
- `tool_audit_quality_full` writes `workspace/logs/audit_master.md` and is auto-called by `tool_synthesize` (described in tool docs + verified in handler code).

---

## Trivial fixes applied in this lens

1. `src/research_os/server.py:4878` — `sys_help` methodology count `(29)` → `(42)`.
2. `src/research_os/server.py:4882` — `sys_help` synthesis count `(14: …)` → `(18: …)`.
3. `src/research_os/server.py:1675` — `sys_active_tools` description "all 143 tools" → "all 212 tools".
4. `docs/ROADMAP.md:252` — stale tool name `tool_audit_master` → `tool_audit_quality_full`.
5. `src/research_os/tools/actions/audit/step_literature.py:9` — module docstring `tool_audit_master` → `tool_audit_quality_full`.
