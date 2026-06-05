# V2 Tool Consolidation Plan

**Status:** Phase 9a (scaffold) committed. Phase 9b agents populate
clusters in parallel against `src/research_os/consolidation_registry.py`.

**Inputs:** `docs/v2_handoff/never_called_candidates.json` (204
candidates flagged as never-called across ≥1 of the 20 baseline runs;
33 flagged in ≥10/20 runs). See also `docs/v2_handoff/PHASE_9_PLAN.md`
for the full friction breakdown.

**Baseline:** v1.11.0 — 118 protocols, 344 tools, server.py 6813 lines.
**Target:** v2.0.0 — ~120 canonical tool names, legacy aliases continue
to dispatch silently for one MINOR cycle, hard-remove in v2.1.0.

---

## Registry shape

The registry lives at `src/research_os/consolidation_registry.py`. Three
top-level objects:

* `CONSOLIDATED_TOOLS: dict[new_name, spec]` — each spec has
  `old_names`, `arg_transform`, `schema`, `handler`.
* `REMOVED_TOOLS: dict[tool_name, user_message]` — hard-removed in
  v2.0.0. Invariant: must have been deprecated for ≥3 MINOR cycles.
* Helpers: `register_consolidated`, `register_removed`, `bind_handler`,
  `resolve_alias`, `apply_transform`, `all_aliases`,
  `consolidated_names`, `removed_names`.

The orchestrator's brief asked for the module at
`src/research_os/server/consolidation_registry.py`. That subpackage
cannot exist alongside the current `src/research_os/server.py` file
without first refactoring `server.py` into a package — out of scope for
Phase 9a. The sibling-module placement preserves the intent (one
canonical registry) without breaking the import surface.

---

## Cluster catalog

Each cluster below has a target new name, the old names it absorbs, and
the dispatch kwarg(s) that the `arg_transform` injects. Counts are
approximate at scaffold time and will be confirmed by the Phase 9b
agent that owns the cluster.

### Cluster 1 — `tool_audit` (≈26 → 1, already partially landed in v1.x)

Per-step audits, project-wide audits, and synthesis-side audits all
collapse onto a single `tool_audit(scope, dimension, ...)` entry point.
The dispatcher routes on (scope ∈ {step, project, synthesis}, dimension
∈ {completeness, literature, code_quality, prose, claims, figure,
figure_full, figure_interactivity, figure_coverage, citations,
assumptions, power, reproducibility, evalue, cliches, coherence,
version_coherence, cross_deliverable, reviewer_responses,
dashboard_content, statistical_power, all}).

A second consolidation, `tool_audit_findings(operation=query|diff)`,
collapses the findings ledger pair.

Old names already migrated (see `_ALIASES` in server.py):
`tool_audit_assumptions`, `tool_audit_code_quality`, `tool_audit_evalue`,
`tool_audit_figure`, `tool_audit_figure_full`, `tool_audit_figure_interactivity`,
`tool_audit_power`, `tool_audit_reproducibility`, `tool_audit_step_completeness`,
`tool_audit_step_literature`, `tool_audit_citations`, `tool_audit_claims`,
`tool_audit_cliches`, `tool_audit_coherence`,
`tool_audit_cross_deliverable_consistency`, `tool_audit_prose`,
`tool_audit_version_coherence`, `tool_audit_synthesis`,
`tool_audit_dashboard_content`, `tool_audit_figure_coverage`,
`tool_audit_reviewer_responses`, `tool_audit_findings_query`,
`tool_audit_findings_diff`, `tool_audit_figure_quality`,
`tool_audit_statistical_power`.

Phase 9b-C1 agent: lift these into `register_consolidated('tool_audit', ...)`
in the registry; leave server.py's `_ALIASES` populated as a fallback
until Phase 11 wiring sweep retires the duplicate.

### Cluster 2 — `tool_viz_figure` (≈8 → 1)

`tool_viz_figure(type, ...)` absorbs the visualization family:
`tool_figure_palette`, `tool_figure_interactive_autogen`,
`tool_figure_caption_synthesise`, `tool_paper_figures_autoembed`,
`tool_poster_create`, `tool_slides_create`, plus the never-called
`tool_dashboard_*` figure-adjacent helpers identified in
`never_called_candidates.json`.

Dispatch kwarg: `type ∈ {palette, interactive, caption, embed, poster, slides}`.

### Cluster 3 — `tool_export` (≈5 → 1)

`tool_export(format, ...)` absorbs the document-export family:
`tool_paper_compile_typst`, `tool_latex_compile`, `tool_rmarkdown_render`,
`tool_notebook_exec` (notebook-as-export variants),
`tool_response_to_reviewers` (export-style PDF render).

Dispatch kwarg: `format ∈ {typst, latex, rmarkdown, notebook, reviewer_response}`.

### Cluster 4 — `tool_step` (≈10 → 2)

`tool_step(action, ...)` for per-step lifecycle (create, complete,
iterate, iterations_list, revision_options, env_lock, promote_to_step,
…) and `tool_step_pipeline(action, ...)` for cross-step pipeline ops
(define, run, status, diagram) — the pipeline-* never-called set in
the candidates JSON.

### Cluster 5 — Already-landed clusters (per v1.11.0 CHANGELOG)

These were consolidated in v1.x and are listed here for completeness:

* `tool_search` (5 → 1) — semantic_scholar, pubmed, crossref, arxiv, web.
* `tool_plan` (3 → 1) — turn, advance, clear.
* `tool_ground` / `tool_verify` (4 → 2) — register, from_context,
  claim_verify, grounding_verify.
* `tool_lessons` (2 → 1) — record, consult.
* `sys_path` (3 → 1) — create, abandon, list.
* `mem_log` (4 → 1) — methods_append, decision_log, hypothesis_update,
  analysis_log.

Phase 9b need not re-touch these unless extending dispatch (e.g.
adding `replay` to `tool_lessons`).

### Cluster 6 — `tool_reviewer` (≈4 → 1)

`tool_reviewer(operation, ...)` absorbs `tool_reviewer_simulate`,
`tool_response_to_reviewers`, `tool_rebuttal_draft`,
`tool_reviewer_response_compile`. Dispatch kwarg:
`operation ∈ {simulate, rebuttal, compile, summarize}`.

### Cluster 7 — `tool_sensitivity` (2 → 1), `tool_preregister` (2 → 1)

Two small two-into-one consolidations. `tool_sensitivity(operation=define|run)`,
`tool_preregister(operation=freeze|diff)`. Pulled out of cluster 4
because their handlers are independent and Phase 9b can ship them in
one agent.

### Cluster 8 — Adapter packs (`tool_slurm` 4 → 1, etc.)

`tool_slurm(operation=submit|fetch|status|list)` lives in the slurm
adapter pack, not the core. Phase 9b agent must register against the
adapter's own consolidation registry (one per pack) so the core stays
adapter-agnostic.

Similar treatment for any adapter pack that ships >2 sibling tools.

---

## Per-cluster agent contract

The Phase 9b agent for cluster `<N>`:

1. Reads the legacy `_handle_*` functions in `server.py` for the
   cluster's old names.
2. Designs a unified handler that dispatches on the new kwarg.
3. Calls `register_consolidated(new_name, old_names, arg_transform,
   schema, handler=None)` in the registry module.
4. Adds a `bind_handler(new_name, _handle_<new_name>)` call from
   server.py after defining `_handle_<new_name>`.
5. Appends rows to `docs/V2_MIGRATION_TABLE.md` — one per old name —
   showing `old_name → new_name(kwarg=value)`.
6. Runs `python scripts/preflight.py && python -m pytest -q -k
   '<cluster_keyword>'` and reports PASS/FAIL.
7. Commits with `feat(v2): consolidate <family> [phase-9-c<N>]`.

---

## Hard-removed tools (REMOVED_TOOLS)

Phase 9a leaves `REMOVED_TOOLS` empty. The release-prep audit (Phase 16)
walks `_DEPRECATED_ALIASES` and the v1.8.x / v1.9.x / v1.10.x changelogs
to identify the ≥3-cycle-deprecated set. Only those names move into
`REMOVED_TOOLS` with a user-facing migration message pointing at the
replacement.

Current `server.py._REMOVED_TOOLS` already holds `tool_figure_create`
(removed v1.6.x) and will be merged into the registry's `REMOVED_TOOLS`
during the Phase 11 wiring sweep.

---

## Done-criteria for Phase 9 (overall)

* Every cluster registered via `register_consolidated`.
* `consolidation_registry.all_aliases()` matches the consolidation
  subset of `server.py._ALIASES` exactly (preflight check).
* `consolidation_registry.removed_names()` matches `server.py._REMOVED_TOOLS`.
* `docs/V2_MIGRATION_TABLE.md` has one row per old name.
* Test suite green (`python -m pytest -q`).
* Tool surface count (canonical names) ≤ 130.
