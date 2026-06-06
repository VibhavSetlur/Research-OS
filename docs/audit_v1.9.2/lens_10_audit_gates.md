# Lens 10: Audit Gates Audit

Discovery sprint v1.9.1 → v1.9.2.
Focus: auditing the audit machinery itself for consistency, completeness,
override discipline, and master-aggregator coverage.

## 1. Inventory of audit gates

### 1a. Tool-definition layer (`server.py` TOOL_DEFINITIONS)

20 audit-prefixed tools registered:

| Tool name                              | Action module                                              | Handler line |
|----------------------------------------|------------------------------------------------------------|--------------|
| `tool_audit_synthesis`                 | `audit.audit_synthesis`                                    | 3557 |
| `tool_audit_power`                     | `audit.audit_power`                                        | 3571 |
| `tool_audit_assumptions`               | `audit.audit_assumptions`                                  | 3586 |
| `tool_audit_figure`                    | `audit.audit_figure` (lighter, DPI-only)                   | 3595 |
| `tool_audit_citations`                 | `audit.audit_citations`                                    | 3604 |
| `tool_audit_reproducibility`           | `audit.audit_reproducibility_full`                         | 3613 |
| `tool_audit_step_completeness`         | `audit.audit_step_completeness`                            | 3985 |
| `tool_audit_step_literature`           | `audit.step_literature.audit_step_literature`              | 3993 |
| `tool_audit_version_coherence`         | `state.iteration.audit_version_coherence`                  | 4040 |
| `tool_audit_figure_full`               | `viz.figures.audit_figure_quality`                         | 4063 |
| `tool_audit_code_quality`              | `audit.code_quality.audit_code_quality`                    | 4278 |
| `tool_audit_prose`                     | `audit.prose_quality.audit_prose`                          | 4289 |
| `tool_audit_claims`                    | `audit.claim_grounding.audit_claims`                       | 4299 |
| `tool_audit_evalue`                    | `audit.audit_evalue`                                       | 4309 |
| `tool_audit_quality_full`              | `audit.audit_quality_full` (master)                        | 4408 |
| `tool_audit_coherence`                 | `audit.coherence.audit_coherence`                          | 5219 |
| `tool_audit_figure_interactivity`      | `audit.figure_interactivity.audit_figure_interactivity`    | 3812 |
| `tool_audit_dashboard_content`         | `audit.dashboard_content.audit_dashboard_content`          | 3843 |
| `tool_audit_cliches`                   | `audit.content_depth.audit_cliches`                        | 3904 |
| `tool_discussion_coverage_audit`       | `synthesis.discussion_from_verdicts.discussion_coverage_audit` | 5268 |

Aliases (`server.py` line 5829-...) include `tool_audit_figure_quality →
tool_audit_figure_full` and `tool_audit_statistical_power → tool_audit_power`.

Note: there is NO `tool_audit_master`. The master is `tool_audit_quality_full`;
the `audit_master` token survives only as the protocol step id and the report
filename `workspace/logs/audit_master.md`. One stale reference in code
(see HIGH finding "Stale tool_audit_master in docstring").

### 1b. Protocol layer (`protocols/audit/*.yaml`)

3 audit protocols:
* `audit/audit_and_validation.yaml` — wraps the master + per-area audits.
* `audit/pre_submission_checklist.yaml` — final pre-publication walk.
* `audit/provenance_completeness.yaml` — output inventory + provenance map.

## 2. Severity inconsistencies (gates blocking vs warning on the SAME condition)

### HIGH: `tool_audit_figure` vs `tool_audit_figure_full` disagree on DPI severity

`audit_figure` (audit/audit.py:1035) treats DPI < 150 as WARN and the
status is at worst `warning` (never `error`).

`audit_figure_quality` (viz/figures.py:211, exposed via
`tool_audit_figure_full`) treats DPI < 200 as a BLOCKER (`blockers.append`,
status becomes `error`).

Same PNG, two tools:
* DPI 180 PNG → `tool_audit_figure` says `warning`, but
  `tool_audit_figure_full` says BLOCKER.
* Sidecar `.caption.md` missing → `tool_audit_figure` does not check it;
  `tool_audit_figure_full` says BLOCKER.

The audit_and_validation protocol routes researchers to
`tool_audit_figure_full` for the gate (audit_and_validation.yaml:77) and
keeps `tool_audit_figure` as a "cheaper intra-step spot check" — but
nothing in the descriptions warns that severities differ. A researcher
who runs `tool_audit_figure` and sees clean output will be surprised by
BLOCKERs from the final-gate run.

### MEDIUM: `audit_step_completeness` accepts a single figure with no sidecar — `audit_figure_quality` blocks at the same condition

`audit_step_completeness` (audit/audit.py:1596) walks each figure and
calls into `_step_completeness` (which checks for sibling `.caption.md`
+ `.summary.md`). `audit_figure_quality` re-runs that same check but
also flags missing summary as a *warning* rather than BLOCKER. The two
checks are not pulled from a shared definition; future drift is easy.

### LOW: `audit_synthesis` over-strict zero-PDF gate but no equivalent in `audit_quality_full`

`audit_synthesis` (audit/audit.py:55) default-denies when zero PDFs are
present across literature-required steps (per the docstring and tool
description, line 1017 server.py). It honours `override_no_pdfs`.
`audit_quality_full` (the master) never invokes `audit_synthesis`, so
the same project that passes the master gate would still fail
`audit_synthesis`. The two enforcement paths are not coordinated.

## 3. Override mechanism inconsistencies

### Overrides found and their keyword names

| Override kwarg                    | Honoured at                                  | Logs to override_log.md? |
|-----------------------------------|----------------------------------------------|--------------------------|
| `override_completeness_gate`      | `tool_synthesize`, `tool_dashboard_create`   | yes (log_override) |
| `override_gate`                   | `tool_plan_advance` (via `tool_plan_actions`)| yes |
| `override_literature_gate`        | `tool_path_finalize`                         | yes |
| `override_no_pdfs`                | `tool_audit_synthesis`                       | NO — handler at server.py:3557 forwards to audit_synthesis but does not call log_override |
| `override_dashboard_content_gate` | `tool_audit_dashboard_content`               | yes |
| `override_discussion_coverage`    | DOCUMENTED but UNIMPLEMENTED (see CRITICAL)  | n/a |

### CRITICAL: `override_discussion_coverage` is fiction

`tool_discussion_coverage_audit` description (server.py:2222) and
`writing_discussion.yaml:153` both tell the AI to pass
`override_discussion_coverage=true` to bypass the gate. But:
* `tool_discussion_coverage_audit` inputSchema is `{}` empty
  (server.py:2225). The MCP layer will accept the kwarg silently but
  the handler ignores it.
* `_handle_tool_discussion_coverage_audit` (server.py:5268) discards
  arguments entirely: `return _text(discussion_coverage_audit(root))`
  with no override threading.
* `discussion_coverage_audit` (synthesis/discussion_from_verdicts.py:93)
  has no override parameter.

Net effect: any AI/researcher trying to bypass this gate will see the
gate still firing and have no way to proceed except deleting the
verdicts. Documentation lies to the user.

### HIGH: `override_no_pdfs` does not write to override_log.md

`_handle_tool_audit_synthesis` (server.py:3557) forwards override_no_pdfs
to `audit_synthesis`, but never calls `log_override`. The
pre_submission_checklist protocol relies on `override_log.md` to surface
"every time the researcher bypassed a gate" — this bypass is invisible.
Every other gate-bypass logs (search server.py for `log_override(` —
six callsites, all but this one cover override usage).

### HIGH: `tool_audit_step_literature` cannot be overridden directly

`tool_audit_step_literature` handler (server.py:3993) only forwards
`step_id`. Its description (server.py:1087) says blockers are hard stops
for `tool_path_finalize` "unless `override_literature_gate=true` is
passed." But that override is only honoured by `tool_path_finalize`
(server.py:3118-3149). A researcher who calls the AUDIT TOOL DIRECTLY
to re-confirm the gate state cannot get a clean pass; they have to call
`tool_path_finalize` instead. The error message inside
`tool_path_finalize` tells them to pass `override_literature_gate` —
but it doesn't tell them to a) the audit alone won't accept it, and
b) finalize is the only path. This is a usability cliff for
"I just want to verify the override is recorded" workflows.

### MEDIUM: override_rationale field handling differs

* `tool_synthesize` (server.py:3655-3659): in `enforce` policy, requires
  non-empty rationale; rejects bypass without it.
* `tool_audit_synthesis`: accepts empty rationale silently
  (`str(arguments.get("override_rationale", ""))` is forwarded as `""`).
* `tool_audit_dashboard_content` (server.py:3851-3856): same enforce
  policy as synthesize.
* `tool_path_finalize` (server.py:3128-3135): refuses unless rationale
  is non-empty regardless of policy.
* `tool_plan_advance`: doesn't check rationale at all.

So the same override kwarg in the same policy gets enforced or not
depending on which tool the AI happens to use.

### LOW: log_override `<no rationale provided — flag in audit>` placeholder

`project_ops.log_override` (project_ops.py:163) writes a placeholder
when rationale is empty: `"<no rationale provided — flag in audit>"`.
But the placeholder is never *flagged* by any subsequent audit. Search
for "flag in audit" returns only this string. The pre-submission audit
reads override_log.md but does not differentiate placeholder rationales
from real ones. Either: a) honour the comment (have
`pre_submission_check` warn on placeholders), or b) tighten the
placeholder text to remove the false promise.

## 4. Output-format inconsistencies

### MEDIUM: Audit report filenames follow three competing naming patterns

Walking the audit modules, output filenames are:

`<name>_audit.md`:
* `step_literature_audit.md`
* `figure_interactivity_audit.md`
* `coherence_audit.md`
* `causal_language_audit.md` (protocol-written)
* `prose_audit.md`
* `synthesis_audit.md`
* `citation_audit.md`
* `grounding_audit.md`
* `provenance_audit.md` (protocol-written)
* `figure_audit_<stem>.md`
* `figure_audit_summary.md` (protocol-written)
* `audit_report.md` (protocol-written)
* `audit_master.md`

`<name>_report.md`:
* `power_report.md`
* `assumption_report.md`
* `evalue_report.md`
* `reproducibility_report.md`

Bare `<name>.md`:
* `step_completeness.md`
* `code_quality.md`
* `claim_grounding.md`
* `preregistration_diff.md`
* `version_coherence.md`
* `code_lint.md` (protocol-written)

Three competing conventions. The task prompt explicitly expected
`<gate_name>_audit.md` for all of them. A researcher hunting in
`workspace/logs/` for "the prose audit" doesn't know whether it's
`prose_audit.md` (yes) or `prose_report.md` (no, but plausible).

### HIGH: `audit_figure` and `audit_synthesis` route to step folder instead of workspace/logs/

`_report_path` (audit/audit.py:43) returns
`workspace/<current_step>/outputs/reports/<filename>` when a step is
active, else `workspace/logs/<filename>`. Audits that go through
`_report_path` (audit_synthesis, audit_power, audit_assumptions,
audit_evalue, audit_figure, audit_citations,
audit_reproducibility_full) split across two locations depending on
project state. Audits that bypass `_report_path` (step_completeness,
code_quality, prose_quality, claim_grounding, preregistration,
figure_interactivity, coherence, audit_master) ALWAYS go to
`workspace/logs/`.

This is invisible drift. The audit_master report references each
sub-audit's `report_path`, so it survives, but:
* The audit_and_validation protocol writes one consolidated
  `workspace/logs/audit_report.md` — when step routing is active the
  sub-audits are scattered across step folders and the protocol writer
  cannot find them all under `workspace/logs/`.
* The pre_submission_checklist (line 27) reads
  `workspace/logs/audit_report.md` directly. Sub-audits routed to step
  folders never reach this consolidation step.

### MEDIUM: `audit_dashboard_content` and `audit_cliches` write NO report

`audit_dashboard_content` (audit/dashboard_content.py:518) returns
status/blockers/warnings/sub_reports but does not write any markdown
report (grep `logs / ` in the file → 0 hits).

`audit_cliches` (audit/content_depth.py:349) likewise returns hits but
writes no file.

Other audits write `workspace/logs/<name>.md` so the dashboard's
audit-trail panel can surface what's still owed. For these two, the
trail is lost as soon as the response message scrolls.

### LOW: Return-shape inconsistency

Most audits return:
```
{"status": "success|warning|error", "blockers": [...], "warnings": [...],
 "report_path": "workspace/logs/...md"}
```
But:
* `audit_dashboard_content` omits `report_path` (no file written).
* `audit_cliches` returns `{"hits": [...], "n_hits": N}` with warnings
  but no `blockers` field at all.
* `audit_coherence` returns `{"status": "warning|success", "orphan":
  [...], "matched": [...]}` — no `blockers` key (uses `orphan` and
  `matched` instead).
* `audit_version_coherence` returns per-step records keyed differently.

`audit_quality_full` walks each sub-result looking for `.get("status")
== "error"` + `.get("blockers", [])`. Sub-audits without that shape are
silently dropped from the aggregated blocker count.

## 5. `audit_quality_full` (master) coverage

### What the master ACTUALLY runs (audit/audit.py:876-1023)

1. `audit_step_completeness`
2. `audit_code_quality`
3. `audit_prose`
4. `audit_claims`
5. `diff_preregistration`
6. `grounding_verify` (from `research.grounding`)

### What the docs CLAIM it runs

Tool description (server.py:1544): "Runs tool_audit_step_completeness +
tool_audit_code_quality + tool_audit_prose + tool_audit_claims +
tool_preregister_diff" — 5 audits.

audit_and_validation.yaml:21-37 echoes the same five.

### HIGH: Master runs 6 gates but description advertises 5

`grounding_verify` is invoked silently (audit/audit.py:973-985). It can
add blockers without the description acknowledging the gate exists.
Researchers debugging a blocker that says `[grounding] N decision(s)
without grounding records` will hunt the docs in vain — neither the
tool description nor the protocol mentions this gate.

Fix: update server.py:1544 and audit_and_validation.yaml:21-37 to
include the grounding gate, OR remove the call from audit_quality_full
and surface it as a separate tool.

### HIGH: Master skips 12 audits

The master does not invoke: `audit_synthesis`, `audit_power`,
`audit_assumptions`, `audit_figure` / `audit_figure_quality`,
`audit_citations`, `audit_reproducibility_full`,
`audit_step_literature`, `audit_coherence`,
`audit_version_coherence`, `audit_figure_interactivity`,
`audit_dashboard_content`, `audit_cliches`,
`discussion_coverage_audit`, `audit_evalue`.

Of these, the ones that should arguably be in the master:
* `audit_step_literature` — already gated by `tool_path_finalize`, so
  technically a step gate, not a synthesis gate; but the master runs
  before `tool_synthesize` and step_literature has the same per-step
  granularity as `audit_step_completeness` (which IS in the master).
* `audit_coherence` — flags orphan paragraphs in synthesis/paper.md.
  `tool_synthesize` writes synthesis/paper.md; the master gate fires
  BEFORE synthesize so paper.md may not exist. But the second-pass
  `audit_claims` already runs AFTER synthesize (server.py:3736-3756) —
  add `audit_coherence` to that same post-pass.
* `audit_citations` — citation verification is a precondition for
  synthesizing; the master is the natural place.
* `audit_dashboard_content` — only relevant when a dashboard exists;
  a conditional invocation (only if `synthesis/dashboard.html` exists)
  would make sense.

### Master ordering

Sequential (no parallelism). Ordering:
step_completeness → code_quality → prose_quality → claims →
preregistration_diff → grounding.

The task prompt asked: "Does the ordering make sense
(literature_per_step before cross_deliverable_consistency)?"
There is no `literature_per_step` or `cross_deliverable_consistency`
inside the master. The closest analogues are `step_completeness` (which
runs first — sensible) and the missing `audit_coherence`. So the
ordering question is partly N/A.

### Aggregate vs stop-on-first-block

Master runs all 6 gates regardless of which fail; collects blockers
into `all_blockers`; returns at the end. So it aggregates. That matches
researcher expectations (one report, all problems visible).

### Output format consistency

Master writes `workspace/logs/audit_master.md` with per-gate icons +
combined blocker section. Sub-audit detail paths surface via
`r.get("report_path")`. Audits that don't produce `report_path` (e.g.
`audit_dashboard_content`) would not surface a link if added later —
return-shape work needed before extending coverage.

## 6. Strictness propagation issues

### CRITICAL: `project_tier` is computed but never consumed by any audit

`project_tier_strictness` (state/quick_mode.py:203) maps
`researcher_config.project_tier` to a default gate_strictness:
throwaway → light, sketch → normal, production → strict.
`tool_project_tier_strictness` exposes this as a callable.

But `resolve_gate_strictness` (state/rigor_signals.py:223) — which is
the actual function consulted by audits — never reads `project_tier`.
It reads `researcher_config.gate_strictness` only. If the researcher
sets `project_tier: throwaway` and leaves `gate_strictness` unset, the
fallback is "default" via the rigor_signals_scan trust_score — NOT
the `light` value `project_tier_strictness` would have returned.

So: setting `project_tier: throwaway` in `researcher_config.yaml` does
absolutely nothing to actual gate behaviour. The tool description
(server.py:2290) claims "throwaway → light, sketch → normal, production
→ strict" but no audit reads that mapping.

Fix: `resolve_gate_strictness` should consult `project_tier_strictness`
as the default when `gate_strictness` is unset (instead of falling
through to rigor_signals).

### HIGH: Only 1 of 20 audit gates actually reads `gate_strictness`

`figure_interactivity` is the only audit that calls
`resolve_gate_strictness` (audit/figure_interactivity.py:163). Every
other audit ignores it. The task prompt asked whether `gate_strictness
("auto" | "light" | "normal" | "strict")` is "honored consistently
across every gate." The answer is no — it is honoured by exactly one
gate.

Audits that should plausibly honour strictness (and do not):
* `audit_figure` / `audit_figure_quality` — DPI thresholds and sidecar
  presence are obvious candidates (strict → blocker on missing summary,
  normal → warning).
* `audit_prose` — hedging count thresholds.
* `audit_code_quality` — complexity / line-length thresholds.
* `audit_step_completeness` — focal figure absence severity.
* `audit_citations` — unresolved citation severity (some unresolved
  preprints are intentional).

This is a significant policy gap: researchers can set
`gate_strictness: light` to soften the gates and only the figure
interactivity gate actually softens. The rest still BLOCK.

### MEDIUM: `recommended_strictness` cutoffs differ from `project_tier` mapping

`rigor_signals_scan` (state/rigor_signals.py:200-205):
* trust_score ≥ 75 → light
* trust_score ≥ 50 → normal
* otherwise → strict

`project_tier_strictness`:
* production → strict
* sketch → normal
* throwaway → light

The semantics are inverted — high trust_score (well-rigored project)
gets LIGHT gates, but production tier (also a serious project) gets
STRICT gates. If both signals are present the researcher will get
contradictory recommendations. Currently this is masked because no
audit consumes either — but if Theme-13 adaptive friction lands
properly, the two should be reconciled (probably: rigor_signals
recommends WHEN to loosen, project_tier recommends OVERALL stance).

### LOW: `auto` source value can be wrong

`resolve_gate_strictness` (state/rigor_signals.py:240-246) returns
`source="auto" if config_value == "auto" else "default"` when
falling through to `rigor_signals_scan`. But it returns the
same `recommended_strictness` either way. So a researcher who explicitly
configured `gate_strictness: auto` and one who left it unset both end
up at the rigor_score recommendation; the only difference is the
returned `source` label. That label feeds nowhere — not into any
audit, not into any log. Cosmetic, but the label is wrong: explicitly
choosing auto vs leaving it default are semantically different
intentions.

## 7. Stale-docs / dead references

### HIGH: Stale `tool_audit_master` in docstring

`audit/step_literature.py:9` says "the caller (typically
`tool_path_finalize` or `tool_audit_master`) treats blockers as a hard
stop." There is no `tool_audit_master`; the tool is
`tool_audit_quality_full`. Plus, `audit_quality_full` does NOT invoke
`audit_step_literature` (see section 5). So the docstring is doubly
wrong: it names a non-existent tool, and even the real master doesn't
call this gate.

Same pattern: `docs/ROADMAP.md:252` references `tool_audit_master`.

### LOW: `audit_evalue` is reachable as a tool but absent from every protocol

`tool_audit_evalue` exists (server.py:1438, handler 4309), but no
protocol references it. The pre_submission_checklist, audit_and_validation,
synthesis_paper protocols all skip it. The tool is dead-ish — works,
returns a report, but nothing in the workflow tells the researcher to
call it.

## Summary

The audit-gate machinery is functional but the integration layer is
incoherent. The master gate (`tool_audit_quality_full`) covers only
6 of 20 gates and silently invokes one (`grounding_verify`) that no
documentation mentions. Override discipline varies per-tool:
`override_discussion_coverage` is documented but not implemented,
`override_no_pdfs` skips the log_override audit trail, and
`override_literature_gate` only works through one specific tool
(tool_path_finalize) even though three places talk about it. Strictness
propagation is the worst hole: `project_tier` flows nowhere, and only
one of 20 gates actually honours `gate_strictness`. Output naming
follows three conventions (`*_audit.md`, `*_report.md`, `*.md`) and two
audits (`dashboard_content`, `cliches`) write no report at all. Report
routing splits between `workspace/logs/` and step-specific
`outputs/reports/` paths depending on whether a step is active.
