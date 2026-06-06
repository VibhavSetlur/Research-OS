# Phase 8 — Audit gate firing matrix (v2.1.0)

Built by the Phase 8 Explore audit pass against `feat/v2.1.0` post-Wave-A.

## Executive summary

21 audit dimensions catalogued across `tool_audit(scope, dimension)` +
`tool_audit_quality_full`. Of those:

| Class | Count |
|---|---|
| `FIRES_IN_PROTOCOL` (at least one protocol triggers) | 16 |
| `FIRES_BY_PROXY` (only via `quality_full` master) | 1 |
| `WIRED_BUT_DEAD` (defined dimension, no protocol triggers) | 3 |
| `OPTIONAL_BY_DESIGN` (manual-only) | 2 |
| Total | 21 |

## Gate firing classification

| Dimension | Scope | Triggering protocols | Verdict | Recommendation |
|---|---|---|---|---|
| `figure_full` | step | 12 | FIRES_IN_PROTOCOL | KEEP |
| `claims` | project | 11 | FIRES_IN_PROTOCOL | KEEP |
| `completeness` | step | 6 | FIRES_IN_PROTOCOL | KEEP |
| `reproducibility` | step | 5 | FIRES_IN_PROTOCOL | KEEP |
| `prose` | project | 5 | FIRES_IN_PROTOCOL | KEEP |
| `citations` | project | 5 | FIRES_IN_PROTOCOL | KEEP |
| `figure` | step | 4 | FIRES_IN_PROTOCOL | KEEP |
| `literature` | step | 3 | FIRES_IN_PROTOCOL | KEEP |
| `code_quality` | step | 3 | FIRES_IN_PROTOCOL | KEEP |
| `assumptions` | step | 3 | FIRES_IN_PROTOCOL | KEEP |
| `version_coherence` | project | 2 | FIRES_IN_PROTOCOL | KEEP |
| `reviewer_responses` | synthesis | 2 | FIRES_IN_PROTOCOL | KEEP |
| `power` | step | 2 | FIRES_IN_PROTOCOL | KEEP |
| `figure_interactivity` | step | 2 | FIRES_IN_PROTOCOL | KEEP |
| `cliches` | project | 1 | FIRES_IN_PROTOCOL | KEEP |
| `coherence` | project | 1 | FIRES_IN_PROTOCOL | KEEP |
| `all` (audit_synthesis) | synthesis | (proxy via quality_full) | FIRES_BY_PROXY | KEEP |
| `cross_deliverable` | synthesis | 0 | WIRED_BUT_DEAD | ANNOTATE_OPTIONAL |
| `dashboard_content` | synthesis | 0 | WIRED_BUT_DEAD | ANNOTATE_OPTIONAL |
| `evalue` | step | 0 | WIRED_BUT_DEAD | WIRE |
| `figure_coverage` | synthesis | 0 | WIRED_BUT_DEAD | WIRE |

## Top WIRE recommendations (orphan gates to connect)

1. **`evalue`** — Statistical E-value for causal inference.
   Meaningful for epidemiological + biostatistical workflows but no
   protocol triggers it. Wire into: `causal_inference_deep` (primary),
   `clinical_trials`, `cox_ph_diagnostics`. Fires after study design is
   locked.

2. **`figure_coverage`** — Synthesis-level audit ensuring all workspace
   figures are referenced in the paper. Currently only manually
   invoked. Wire into `synthesis_paper` + `synthesis_dashboard` as a
   BLOCK gate at ≥70% coverage threshold.

3. **`cross_deliverable`** — Consistency audit across
   paper/slides/poster/dashboard. Defined as a manual deep-check;
   surface as `override_cross_deliverable=true` opt-in in
   `revise_and_resubmit` when researcher has all four deliverables.

## ANNOTATE_OPTIONAL recommendations

1. **`dashboard_content`** — Dashboard-specific validation
   (interactive elements, storytelling coherence). Add `# [OPTIONAL]`
   marker to the handler docstring. Manual-only via researcher request.

2. **`cliches`** — Content-depth scan for vague language. Single
   reference in `audit_and_validation`. Surface as `--lazy` option in
   `revise_and_resubmit` rather than auto-firing on every project audit.

## v2.1.0 action items (this phase)

Given scope + remaining time, the recommended fix surface is:

- [ ] Wire `evalue` into one statistical-causal protocol (smallest
  meaningful impact). DEFER to v2.1.x — needs domain reviewer input on
  threshold semantics.
- [ ] Wire `figure_coverage` into `synthesis_paper` with WARN (not
  BLOCK) at <70% coverage. DEFER to v2.1.x — schema for "figure is
  referenced" needs locking.
- [ ] Add `# [MANUAL_OPTIONAL]` annotation on `dashboard_content` and
  `cross_deliverable` handler docstrings so the AI knows they're not
  default-pipeline. **v2.1.0 scope** (low risk).

## Out of scope for v2.1.0

The two WIRE recommendations land as v2.1.1 patches once the domain
reviewer signs off on thresholds. No gate is deleted; the three
WIRED_BUT_DEAD entries remain available for manual invocation in
v2.1.0 + are annotated to mark intent in this minor cycle.
