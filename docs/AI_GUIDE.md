# AI Guide — how the AI should use Research OS

This document is for the AI driving Research OS, not the researcher.
The runtime equivalent of this is `sys_help` (always available as an
MCP tool). Read this on a cold start; consult `sys_help` mid-session.

---

## What Research OS is

An MCP server that scaffolds + audits research projects end-to-end
(data → publication) AND supports off-axis work (viz only / talks /
lay summaries / method consultation / reproduction / mid-pipeline
entry). One install, one **global** server, per-project init.

---

## The session pattern (every session, in order)

Every turn is triggered by a researcher message — you don't act before
one arrives. On the **first turn of a session**, fire two MCP calls
back-to-back before doing anything else:

1. **`sys_boot`** — your FIRST MCP call on the first turn of the
   session, regardless of what the researcher asked. Returns state +
   researcher config + protocol history tail + dep inventory +
   recommended next protocol + pause classification + any active plan
   from a previous turn.
   - Do **not** call `sys_state_get` / `sys_config_get` /
     `sys_protocol_history` / `sys_protocol_next` /
     `sys_dep_inventory` separately while `sys_boot`'s payload is
     fresh.
2. **`tool_route(prompt=<their verbatim message>)`** — your SECOND
   MCP call. Hierarchical L1 → L2 → L3 protocol picker. Returns
   `resolved_level`, `intent_class`, `sub_intent`, `primary_protocol`,
   `shortcut_tool`, `decomposition`, `complexity`, `ask_user`.
   - If `ask_user` is non-null, ask THAT one-sentence question and
     re-route. Never guess.
   - If `complexity == "high"`, the router persisted an `active_plan`
     to `.os_state/active_plan.json`.
3. **For `complexity: high`**: `tool_plan_turn` → execute every entry
   in `this_turn` in order; `tool_plan_advance` after each. If
   `chat_split_recommended` is true, hand off + tell the researcher
   to open a fresh chat.
4. **For `complexity: low`**: call the `shortcut_tool` directly OR
   load the protocol with `sys_protocol_get format='summary'`
   (~300 tokens) and execute.

On **subsequent turns** of the same session, skip `sys_boot` — its
payload is already in context — and go straight to `tool_route` (or
continue an in-flight `active_plan` via `tool_plan_advance`).

---

## Resolving the active project (the server is global)

The server is GLOBAL — one process serves multiple projects. Each
request resolves the project root via:

1. `RESEARCH_OS_WORKSPACE` env var (set by the IDE MCP config,
   typically to `${workspaceFolder}`)
2. The current working directory walked up to `.os_state/`
3. The current working directory as a last resort

When you're uncertain which project a request is operating on, call
`sys_active_project` — returns the resolved root + how it was
resolved. If `has_os_state` is False, tell the researcher to run
`research-os init` in that folder OR to open one that has been.

---

## Tool namespaces

- `sys_*` — system / workspace / state / files / paths / checkpoints
- `tool_*` — research work: search, exec, audit, synthesis, intake, plan
- `mem_*` — append-only memory: methods, citations, decisions, hypotheses

When you need a tool you haven't seen recently, call
`sys_tool_describe(tool_name)` — returns the full schema. To narrow
the working set for a protocol, call `sys_active_tools(protocol_name)`.

---

## `inputs/` directory conventions (read on cold-start)

The wizard always creates three canonical subdirectories under
`inputs/`. Some pack-specific protocols expect additional locations
that the wizard does NOT pre-create:

| Path | Created by wizard | Notes |
|---|---|---|
| `inputs/raw_data/` | yes | server-immutable; observational data |
| `inputs/literature/` | yes | server-immutable; PDFs |
| `inputs/context/` | yes | notes, drafts, prior reports — editable |
| `inputs/corpus/` | no | text corpus for humanities pack; `tool_intake_autofill` populates `corpus_manifest.csv` when present |
| `inputs/textual/passages/` | no | close-reading passages with edition pins (humanities) |
| `inputs/preliminaries.md` | no | definitions + cited prior results — **hard prerequisite** of `theory_math/method/proof_strategy_selection` |
| `inputs/context/code/` | no | source code under benchmark (engineering); kept editable so the researcher can iterate on the implementation |
| `inputs/context/instruments/` | no | IRB protocols, interview guides, consent forms (qualitative) |

When the researcher's prompt implies one of these (humanities corpus,
proof, benchmark, qualitative interviews), tell the researcher where to
drop the files BEFORE running `tool_intake_autofill` — the autofill
benefits from the right files being in the right place.

---

## Protocol categories (114 protocols, organised in 9)

| Category | What it covers |
|---|---|
| guidance | session + flow control (boot / resume / handoff / autopilot / casual / mid_entry / disagree / scope_clarification / revise) |
| discover | intake routing — `tool_intake_autofill` (a shortcut tool, not a YAML protocol) plus `guidance/scope_clarification`. There is no `protocols/discover/` directory; the category exists as a router intent_class, and `tool_route` returns `shortcut_tool=tool_intake_autofill` for it. |
| domain | domain classification + study design |
| methodology | method picking + per-method protocols (42 protocols, incl. **v1.4.0** `pick_tool_stack` + `mixed_language_orchestration`) |
| literature | search + systematic review + evidence synthesis + comparative review + **v1.4.0** `literature_per_step` (per-step findings_vs_literature.md loop) |
| writing | per-section drafting (methods / results / discussion / limitations / end_matter) |
| visualization | figures (rules / workflow / critique / multi-panel / arc / a11y / interactive) |
| synthesis | final deliverables (18 protocols: paper / abstract / poster / dashboard / slides / lay / handout / report / grant / progress / from_inputs / null / cover_letter / title / manuscript_outline / journal_selection / defense_prep / printable) |
| audit + reproducibility | quality audit + pre-submission checklist + provenance completeness + repro audit + **v1.4.0** `tool_audit_step_literature` gate |

If a category looks like it should have a folder but you can't find one
(`discover/` is the canonical example), it's because the category
resolves to a shortcut tool rather than a YAML protocol. Trust the
router — do not grep `src/` to verify; the protocol catalogue is
authoritative via `sys_protocol_list`.

For a category-specific orientation, call `sys_help(topic="<category>")`.
Useful operational topics that aren't categories:

* `topic="routing"` — the L1 → L2 → L3 decision tree + ambiguity rules
* `topic="iteration"` — bug-fix versioning vs. deliberate iteration
* `topic="overrides"` — when / how to bypass a quality gate safely
* `topic="recovery"` — when stuck (broken workspace, dead end, lost project)
* `topic="fields"` — how Research-OS stays field-agnostic; subfield pipelines
* `topic="depth"` — depth gradient (napkin → publication) + expertise levels

---

## Scaffold-not-script doctrine

Every protocol names the QUESTIONS the AI must answer + the GROUNDING
it must cite. Protocols do NOT name:

- the specific method
- the specific tool / library / CLI
- the specific threshold / cutoff / hyperparameter
- the specific step sequence

The AI fills the specifics per project, from the literature, never
from training memory. See `docs/PROTOCOL_DOCTRINE.md` for the full
principle.

This is also how the AI should behave: when a protocol step names a
question, the AI must surface a grounded answer (cite the paper /
the workspace artefact / the field convention), not assert from
prior knowledge.

---

## Anti-patterns

| Don't | Why |
|---|---|
| Call `sys_state_get + sys_config_get + sys_protocol_history` separately | `sys_boot` returns all of them in one call |
| Load full protocols with `sys_protocol_get format='full'` when summary suffices | Summary is ~300 tokens; full is 1.5-3K |
| One-shot 400-line scripts | `tool_plan_step` forces atomic sub-tasks; `pipeline.yaml` for >2-script steps |
| Invent citations | Synthesis tools VERIFY every citation against Crossref / Semantic Scholar / PubMed / arXiv |
| Pick a method from training memory | `tool_research_method` is mandatory before any method commit |
| Write under `inputs/raw_data` or `inputs/literature` | Server blocks it; these are immutable |
| Skip the `ask_user` from `tool_route` | Asking once costs less than picking wrong |
| Re-route after the researcher already picked one | Use `tool_plan_clear` if they pivoted |
| Submit without `audit/pre_submission_checklist` | The pre-submission gate catches what reviewers will catch |

---

## Quality gates that BLOCK synthesis

- `tool_audit_step_completeness` — every active step needs a focal
  figure + caption sidecars + non-stub conclusions
- `tool_audit_claims` — every number in synthesis traces to a
  workspace artefact (catches hallucination)
- `tool_audit_code_quality` — no bare-except / import-* / eval /
  exec / hardcoded paths / functions > 150 lines
- `tool_audit_prose` — flags hedging / vague quantifiers / causal
  language on observational designs
- `tool_citations_verify` — every citation must resolve online
- `tool_preregister_diff` — surfaces SAP drift if a preregistration
  exists

`tool_synthesize` calls `tool_audit_quality_full` as its FIRST gate.
Don't override the gate unless the researcher explicitly authorises
a partial deliverable.

## When the researcher EXPLICITLY overrides a gate

Quality gates can be bypassed — but only on explicit researcher
authorisation in their CURRENT message ("just draft it", "give me a
preview", "skip the audit"). The override path:

* `tool_synthesize(override_completeness_gate=true, override_rationale="<why>")`
* `tool_dashboard_create(override_completeness_gate=true, override_rationale="<why>")`
* `tool_plan_advance(override_gate=true, override_rationale="<why>")`

The rationale is mandatory; the override appends to
`workspace/logs/override_log.md`. `audit/pre_submission_checklist`
surfaces every bypass at publish time so the researcher confirms
each one was intentional.

The project-level posture lives at `interaction.quality_gate_policy`
in `inputs/researcher_config.yaml`:

* `enforce` (default) — AI refuses to bypass without explicit ask
* `allow_override` — AI may bypass when asked, logs the rationale
* `warn_only` — gate blockers become warnings (sandbox use only)

The AI never bypasses on its own. Hard rules (no fabricated
citations, no writes under `inputs/raw_data/`) are absolute — the
quality gate is the ONLY authorised escape hatch.

---

## When to override a gate (worked examples)

The override path is a researcher tool, not an AI tool. The AI never
bypasses a gate on its own — it requires an EXPLICIT authorisation in
the researcher's current message ("just draft it", "give me a
preview", "skip the lit check", "ship it now"). Five recurring shapes
this takes in practice:

### 1. Data-engineering step (no figure required)

Researcher: "step 02 is just the merge — no figure, advance the plan."

The step-completeness gate insists every step ships a focal figure.
For a pure ETL / data-engineering step that's noise. Bypass the plan
gate with a one-line rationale:

```python
tool_plan_advance(
    override_gate=True,
    override_rationale="step 02 is a data merge — no figure expected",
)
```

The override surfaces at `audit/pre_submission_checklist`; if the
final paper actually does need a Fig 2 the researcher catches it
there. Better long-term fix: declare `figure_required: false` in
`step_summary.yaml` so the gate skips this step natively (deferred
to v2 — see the smoke-gap list).

If the dashboard content gate (placeholder text, stub captions) is
the blocker rather than the warnings-panel gate, the dashboard takes
a separate kwarg:

```python
tool_dashboard_create(
    audience="executive",
    override_dashboard_content_gate=True,
    override_rationale="board update at 16:00; placeholder captions on Fig 4-5 acknowledged",
)
```

### 2. Literature is unreachable (offline / paywalled site is down)

Researcher: "Crossref is down, finalise the path anyway."

`tool_path_finalize` blocks if `findings_vs_literature.md` is missing
or DISAGREES verdicts lack coverage. Bypass with the literature gate
override:

```python
tool_path_finalize(
    path_name="03_pilot_grouping",
    override_literature_gate=True,
    override_rationale="Crossref + Semantic Scholar both 5xx as of 14:00 UTC; will reconcile after restore",
)
```

The bypass logs to `override_log.md`. The researcher's next session
should re-run `research/literature_per_step` once the upstream
recovers — the pre-submission checklist will flag the bypass until
the literature loop closes.

### 3. Methodology section pending (preview the rest)

Researcher: "draft the abstract + introduction so I can show my PI
this afternoon; methods isn't written yet."

Section-only synthesis still runs the step-completeness gate. If
methods.md is a stub, the bypass for the section call lets the
preview happen:

```python
tool_synthesize(
    output_type="paper",
    section="abstract",
    override_completeness_gate=True,
    override_rationale="3pm preview for PI; methods coming tonight",
)
tool_synthesize(
    output_type="paper",
    section="introduction",
    override_completeness_gate=True,
    override_rationale="3pm preview for PI; methods coming tonight",
)
```

Two entries land in `override_log.md`. When the methods section is
ready the full-doc synthesize call should NOT need the override —
the gate passes naturally and the audit trail shows a clean final
build with two preview bypasses earlier in the day.

### 4. Pre-publication final pass (gate passes — DO NOT override)

This is the case that demonstrates the override is NOT a "speed
boost" the AI reaches for. When the final manuscript is ready, the
researcher asks for the publish-ready PDF:

```python
tool_synthesize(output_type="paper")  # NO override
tool_audit_synthesis(paper_path="synthesis/paper.md")  # NO override
tool_paper_compile_typst()
```

If any of these BLOCK, the answer is to fix the underlying issue
(missing caption sidecar, uncovered verdict, stub conclusion), not to
add `override_*=true`. The pre-submission checklist counts every
entry in `override_log.md` and asks the researcher to confirm each
one before submission — bypasses are forensic evidence, not a
shortcut.

### 5. Researcher discretion (theory_math, no empirical PDFs)

Researcher: "this is a planar-graph-colouring proof — there are no
empirical PDFs to download; audit and finalise."

`tool_audit_synthesis` default-denies when zero PDFs are present
across literature-required steps. Theory papers cite earlier
theorems, not empirical results, so the deny is a false positive:

```python
tool_audit_synthesis(
    paper_path="synthesis/paper.md",
    override_no_pdfs=True,
    override_rationale="theory_math project — proof cites earlier theorems, no empirical PDFs",
)
```

Similarly, a `tool_writing_discussion` validate step that BLOCKS on
the discussion-coverage gate for a theory paper with no DISAGREES
verdicts:

```python
tool_discussion_coverage_audit(
    override_discussion_coverage=True,
    override_rationale="theory_math project — no empirical verdicts to cover",
)
```

The pre-submission checklist still surfaces both bypasses, which is
correct — a human should confirm "yes, this is a theory paper, the
no-PDF and no-verdict assumptions hold" before publishing.

### 6. Figure cross-references the AI must not rewrite

`tool_paper_figures_autoembed` calls `rewrite_figure_xrefs` after
auto-embedding when `researcher_config.synthesis.figure_xref_rewrite=true`
(the default). When the researcher has hand-tuned Pandoc
`\ref{fig:foo}` / `@fig:foo` cross-references in `synthesis/paper.md`
that should not be re-pointed, pass `override_xref_rewrite=true`:

```python
tool_paper_figures_autoembed(
    mode="append_to_section",
    override_xref_rewrite=True,
)
```

The flip is local (no `override_rationale` required) because no
quality gate is bypassed — the rewrite is a convenience pass, not a
deny. The auto-embed log still records that the rewrite was skipped.

### 7. Unresolved BLOCK findings in the audit ledger (Phase-4c)

**v2.0.0.** `tool_synthesize` also gates on
`workspace/logs/.audit_findings.jsonl` — the append-only ledger every
Phase-4 audit writes to via `write_audit_outputs`. The gate uses
latest-snapshot semantics: a BLOCK finding emitted on an earlier audit
run but absent from the most recent rerun for the same audit is treated
as resolved. Only currently-active BLOCKs stop synthesis.

If the researcher has explicitly authorised compiling with active BLOCK
findings on record (e.g. they accept a known prose-quality blocker for
a WIP review pass), bypass with rationale:

```python
tool_synthesize(
    output_type="paper",
    override_unresolved_blocks=True,
    override_rationale="reviewer wants the draft tonight; prose blockers known + queued for tomorrow",
)
```

The bypass appends to `workspace/logs/override_log.md` with the active
blocker ids so the pre-submission audit can re-surface them. Use
`tool_audit_findings_query(severity="block")` to list the current
active blockers and `tool_audit_findings_diff(timestamp_a, timestamp_b)`
to confirm a fix actually resolved a finding between two audit runs.

### 8. Cross-deliverable divergence the supervisor approved

`tool_audit_cross_deliverable_consistency` BLOCKs when the poster,
slides, dashboard, or paper disagree along the 5 dimensions (numeric
claims, figures, citations, top-line findings, reproducibility
footer). Sometimes the divergence is intentional — e.g. the
supervisor approved a simplified poster headline that drops the
exact effect size. Bypass with rationale:

```python
tool_audit_cross_deliverable_consistency(
    override_cross_deliverable=True,
    override_rationale="supervisor-approved poster simplification: headline drops the CI to fit the 40-char title rule",
)
```

The pre-submission audit still resurfaces this so the researcher
re-confirms before submission.

### The `override_rationale` rule

Under `interaction.quality_gate_policy=enforce` (the default in
`inputs/researcher_config.yaml`), `override_rationale` is MANDATORY.
A bypass kwarg without a non-empty rationale is rejected by the
server with a clear error — the bypass never executes. This is
deliberate. Silent bypasses are the exact failure mode the override
system exists to prevent; the rationale is the audit-trail anchor.

Other policies:

- `allow_override` — the AI may bypass on request with the rationale
  logged. The rationale is still required at the API level (silent
  bypasses are still disallowed); the difference is the AI has more
  latitude about when to ask.
- `warn_only` — sandbox / exploratory use. Blockers degrade to
  warnings. The override kwargs are still honoured (so explicit
  bypasses produce a log entry) but unset blockers no longer block.

### `workspace/logs/override_log.md` format (what the audit sees)

Each bypass appends one bullet:

```
- 2026-06-05T17:42:11Z · `tool_synthesize` · gate=quality_full · 3pm preview for PI · {"output_type": "paper", "section": "abstract", "blocker_count": 4}
```

`audit/pre_submission_checklist` reads this file and lists every
entry alongside the question "was this bypass intentional?" Treat
the log as forensic evidence — never hand-edit, never delete. If a
bypass was wrong, fix the underlying issue and re-run; the corrected
gate-passing call doesn't append a new entry, so the historical
bypass remains visible (a feature, not a bug).

See [TOOLS.md § Per-step audit overrides](TOOLS.md#per-step-audit-overrides)
for the full kwarg-by-tool table.

## Deliberate iteration vs bug fix

Two distinct modes for re-running a step:

* **Bug fix** — script has a defect. Bump `_v<n>`, re-run via
  `tool_step_pipeline_run`. The fingerprint cache invalidates the
  affected node automatically.
* **Deliberate iteration** — researcher wants a coordinated change
  (recolour Fig 2, tighten a cutoff, swap a model spec). FIRST call
  `tool_step_iterate(step_id, rationale=…)` to snapshot scripts +
  outputs + caption / summary / prov sidecars + conclusion into
  `.versions/v<n>/`. Live filenames stay stable so cross-step
  references don't rot. Then rename the live scripts per
  `next_script_paths` and re-run.

After iteration, run `tool_audit_version_coherence` to confirm every
output traces to the highest-version script on disk. Drift (a v2
figure produced by a v1 script) is flagged in
`workspace/logs/version_coherence.md`.

---

## When the AI's grounded evidence disagrees with the researcher

Load `guidance/constructive_disagreement`. The protocol enforces
structured pushback:

- Pushback is GROUNDED (cite source) and SPECIFIC (name the
  alternative + why)
- Severity is classified (BLOCKER / CAUTION / CONSIDERATION)
- After two rounds of disagreement on the same choice, the AI defers
  and logs the disagreement (synthesis surfaces it in Limitations
  later if the choice affected claims)

Don't push back on every choice. Push back when the choice affects
publishability, reproducibility, or claims AND the evidence for the
alternative is unambiguous.

---

## When the researcher arrives mid-pipeline

Load `guidance/mid_pipeline_entry`. The protocol classifies the
project into one of seven entry archetypes (DATA-READY / ANALYSES-READY
/ FIGURES-READY / SYNTHESIS-READY / PRIOR-RO-PROJECT / CONCEPTUAL /
MIXED) and routes to the right downstream protocol without forcing
redundant intake.

Record a PROVENANCE CEILING in `docs/entry_record.md` so downstream
audits know what was reasoned vs imported.

---

## When the researcher's intent is unclear or cross-disciplinary

Load `guidance/scope_clarification`. The protocol distinguishes five
sources of ambiguity:

* **Unclear intent** — researcher knows; the AI hasn't extracted it.
* **Unformed intent** — researcher hasn't decided. Routes to
  `methodology/methodological_consultation` (teach me) or
  `methodology/exploratory_data_analysis` (find a hypothesis).
* **Cross-disciplinary** — project spans two subfields. Runs
  `methodology/deep_domain_research` per subfield.
* **Wrong entrypoint** — researcher is asking RO for something it
  shouldn't drive. AI surfaces the closest in-scope option + defers
  the rest.
* **Too broad** — bundle's a whole project's worth of work. AI builds
  an `active_plan` via `tool_route`'s complexity=high path and walks
  per turn.

Pick the bucket, ask the SINGLE highest-leverage question, then
re-route on the narrowed prompt. The protocol intentionally never
locks in a downstream step — it hands control back to `tool_route`.

---

## Hand-off + resume

End of session — researcher says "wrap up" / "going to lunch":
1. `sys_checkpoint_create` — workspace snapshot
2. `sys_session_handoff` — writes the handoff doc with running tasks +
   hypotheses + dead-end lessons + resume prompt

Start of session — researcher says "pick up where we left off":
1. `sys_boot` (always — the pause_classification will say
   `ctx_exhaustion` because a handoff exists)
2. `tool_session_resume` — reconstructs intent + status in one call
3. `sys_protocol_next` — confirm the pipeline-recommended next step

For HUMAN collaborators (not the next AI), use
`guidance/collaboration_handoff` — writes a COLLABORATOR.md in their
vocabulary and packages a share-safe zip.

### When to proactively hand off

`tool_plan_turn` returns `chat_split_recommended: true` when the
remaining plan won't fit comfortably in the current chat. The
heuristic is approximately:

* `model_profile=small` — hand off after every 3 steps, or any single
  step expected to add >2K tokens of artefact-loading.
* `model_profile=medium` — hand off after ~5 steps finalized this
  conversation, or when the active plan still has >6 steps to walk.
* `model_profile=large` — hand off after ~8 steps finalized this
  conversation, or when context utilisation crosses ~70%.

`tool_step_revision_options.handoff_recommended` returns `true` on the
same logic at the per-step level. When EITHER signal fires, write the
handoff doc and tell the researcher to open a fresh chat — don't try
to push through. Continuing past `chat_split_recommended` is the most
common cause of mid-session context exhaustion that loses state.

---

## Per-section paper-writing protocols

Loaded by `synthesis/synthesis_paper` automatically; the AI can also
load them directly when the researcher wants to focus on one section:

- `writing/writing_methods` — Methods (mostly mechanical)
- `writing/writing_results` — Results (report numbers, defer interp)
- `writing/writing_discussion` — Discussion (the hardest section)
- `writing/writing_limitations` — Limitations (most-read by reviewers)
- `writing/writing_data_availability` — End matter (CRediT / data /
  code / funding / COI / ack)
- `writing/writing_core` — universal rules (loaded implicitly by all)

For the title and cover letter:
- `synthesis/synthesis_title_workshop` — generate / iterate / pick
- `synthesis/synthesis_cover_letter` — fit + significance + reviewers

Before submission:
- `audit/pre_submission_checklist` — final GREEN / YELLOW / RED gate

---

## Visualization protocol layering

The visualization category has 14 protocols for distinct needs:

| Protocol | Use when |
|---|---|
| `figure_guidelines` | You need the STYLE-AND-RULES reference (palettes, fonts, DPI, captions) |
| `visualization_workflow` | You're building a figure or figure deck without committing to full analysis_plan |
| `figure_critique` | Reviewing ONE figure (chart family / encoding / caption alignment) |
| `multi_panel_composition` | Composing Figure 2 = panels A / B / C / D |
| `figure_narrative_arc` | Ordering figures across a paper / talk / poster |
| `color_accessibility_audit` | Color-blind simulation + WCAG contrast + grayscale |
| `distribution_comparison` | Comparing distributions across groups — pick a chart family beyond bar-with-error-bar |
| `uncertainty_visualization` | Error bars, fan charts, calibration plots — making uncertainty legible |
| `interactive_figure_design` | One figure benefits from hover / brush / click (volcano, UMAP, heatmap) |
| `interactive_dashboard_design` | Multi-page interactive dashboard (next tier above single-file `synthesis_dashboard`) |
| `geospatial_visualization` | Data has a location dimension — choropleths, points, trajectories; map-projection pitfalls |
| `network_visualization` | Relationships > aggregates — co-authorship, gene regulatory, causal DAGs |
| `animation_design` | Change over time IS the story — training trajectories, epidemic spread, attention shifts |
| `showcase_visualization` | HCI / data-art / journalism explainers / journal covers — figure as primary artefact |

Research-OS does NOT ship a parametric chart-builder. You (the AI) write
the plotting script in the appropriate language — matplotlib / ggplot2 /
plotnine / Altair / d3 / plotly — guided by `figure_guidelines`. The
server enforces DPI, sidecars, palette via `tool_audit_figure_full` and
`tool_path_finalize`.

---

## Domain packs (theory_math, qualitative, humanities, engineering, wet_lab)

Five domain packs ship in the default wheel. They activate
automatically when their detectors fire (filename heuristics, intake
keywords, researcher_config domain tags) — you don't load them
explicitly.

### `theory_math` — proofs, formal verification, theorems

Fires when: researcher says "prove this" / "I have a conjecture" /
"draft a proof" / "iterate on the proof"; OR `.lean` / `.v` / `.tex`
proof drafts appear under `inputs/raw_data/`; OR
`inputs/preliminaries.md` lists definitions / lemmas the proofs use.

Pack ships 8 protocols + 3 tools (see TOOLS.md § Theory + math pack
and PROTOCOLS.md § Theory + math pack). The canonical workflow:

1. `theory_math/conjecture/conjecture_tracking` — register the open
   problem if you're not ready to tackle it yet
2. `theory_math/method/proof_strategy_selection` — choose between
   direct / contradiction / induction / contrapositive / construction
3. `theory_math/proof/proof_verification_workflow` — claim → strategy
   → draft → independent review (via `tool_redteam_review focus='proof'`)
   → optional formal check → publish
4. `theory_math/proof/lemma_library` and
   `theory_math/proof/theorem_dependency_graph` — maintain reusable
   lemmas + render the dependency DAG
5. `theory_math/formal/lean_integration` or
   `theory_math/formal/coq_integration` — formalise when the
   `formal_check_required_when` triggers fire (foundational claim /
   contradicts widely-believed conjecture / uses unusual axiom)
6. `theory_math/output/theory_paper_structure` — compile the theory
   paper (Theorem / Proof / References, NOT IMRAD)

The IMRAD assumptions baked into `synthesis/synthesis_paper` do not
apply — load `theory_paper_structure` instead. For citation style on
theory papers, set `researcher_config.citation_style: amsplain`
when the venue is a math journal.

### `qualitative`, `humanities`, `engineering`, `wet_lab`

Activated the same way (detector-driven). Each ships its own
protocols + a small toolkit; see TOOLS.md (Qualitative / Humanities /
Engineering / Wet-lab pack sections) and PROTOCOLS.md for the
catalogue.

---

## When in doubt

- `sys_help` → orientation block (this document, but always live)
- `sys_help(topic="synthesis")` → category-specific guidance
- `sys_active_project` → which project is this request operating on
- `tool_route(prompt)` → re-route on a new researcher message
- `sys_protocol_list` → all 114 protocols indexed
- `sys_tool_describe(tool_name)` → full schema for a tool
