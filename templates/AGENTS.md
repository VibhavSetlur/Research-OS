# Research OS — AI Operating Rules

You are connected to the **Research OS MCP server**. This file is loaded
every prompt — keep it short. Step-by-step "how to do X" lives in the
**protocols** you load on demand.

For your full operating guide, call `sys_help` — it returns
the in-server orientation (routing pattern, namespaces, protocol
categories, anti-patterns). The fuller human-readable version is at
<https://github.com/VibhavSetlur/Research-OS/blob/main/docs/AI_GUIDE.md>.

---

## Small model quickstart

If you're a small model (Haiku, GPT-4o-mini, Gemini Flash, Llama
3.3-70B, local 7B–13B), do these five things first:

* **Set the profile once.** `sys_config(operation='set',
  key='ai.model_profile', value='small')` — makes `sys_protocol_get`
  default to `format='lean'`.
* **Always pass `format='lean'`** to `sys_protocol_get` explicitly.
* **Prefer `shortcut_tool` over `decomposition`** when `tool_route`
  returns one — skip the protocol load.
* **Call `sys_active_tools(protocol_name=…)` after every routing
  decision** to scope your working tool set to ~10-15 tools.
* **Use the `compare_to:` field in every tool description** to pick
  the lightest tool for the task.

---

## Mental model

* **You** plan and reason.
* **Research OS** executes, records, enforces. Every research action goes
  through `sys_*` / `tool_*` / `mem_*` tools.
* **The researcher** drops files in `inputs/`, talks to you in natural
  language, approves checkpoints.

If `sys_*` tools aren't visible, the MCP server isn't connected. The
server is **global** — one `research-os start` process serves every
project. The IDE auto-launches it via the project's MCP config; if
it's not connected, tell the researcher to restart their IDE.

Need to confirm which project the server resolved for THIS request?
Call `sys_active_project` — it returns the resolved root + how it
was resolved (env var / cwd walk / fallback).

---

## Every session — boot in two MCP calls (first turn only)

Every turn starts when a researcher message arrives — you don't act
before one. On the **first turn of a session**, fire two MCP calls
back-to-back before doing anything else:

1. `sys_boot` → state + config + history + dep inventory + next protocol
   + pause + any active plan. Your FIRST MCP call. Replaces 4-5
   separate calls.
2. `tool_route(prompt=<their verbatim message>)` → hybrid router.
   Your SECOND MCP call. Tries SEMANTIC search first (local BGE-small
   embeddings, no network) and falls back to the hierarchical L1→L2→L3
   trigger picker when semantic confidence is low / unavailable.
   Returns `primary_protocol`, `shortcut_tool`, `decomposition`,
   `complexity`, `ask_user`, `method` (`semantic`|`trigger`),
   `confidence`. If `ask_user` is non-null, ASK that one sentence then
   re-route. Never guess. Need to inspect ranked alternatives directly?
   Call `tool_semantic_route` — it returns the top-k candidates with
   cosine scores. Need to find a tool by what it does? Call
   `sys_semantic_tool_search(query=…)`.
3. `complexity="high"` → `tool_plan(operation="turn")` to batch by `model_profile`
   (small=1 step/turn, medium=3, large=6), execute in order, call
   `tool_plan(operation="advance")` after each. If `chat_split_recommended`, run
   `sys_session_handoff`.
4. `complexity="low"` → call `shortcut_tool` directly OR load the
   protocol via `sys_protocol_get format='summary'` (~300 tokens),
   drill in with `format='step' step_id=<id>` when ready.

On **subsequent turns** of the same session, skip `sys_boot` (its
payload is still in context) and go straight to `tool_route` — or
continue an in-flight `active_plan` via `tool_plan(operation="advance")`.

Use `sys_protocol_get format='summary'` — never `format='full'` just to
list steps. Use `sys_tool_describe(name)` instead of re-listing all tools.
Use `sys_active_tools(protocol_name)` to scope your working tool set
to the protocol's decomposition.

**Pick `format` by `model_profile`:**
- `small` → `format='lean'` (cap 3 steps, 200-char descriptions, drops
  optional sub-steps). Drill in with `format='step'` on demand.
- `medium` → `format='summary'` first, then `format='step'` for the
  step you're about to execute.
- `large` → `format='summary'` is still preferred; reach for
  `format='full'` only when the protocol's reasoning genuinely needs
  the long-form examples block.

**Preview before commit (supervised / coaching modes).** Call
`tool_dry_run(protocol_name)` to see the protocol's full tool-call
sequence with predicted args without executing. Useful for review
before running a heavy pipeline.

**End-of-step bundling.** Instead of calling `tool_path_finalize`,
`tool_audit(scope="step", dimension="completeness")`, `tool_audit(scope="step", dimension="literature")`, and
`tool_step(operation="revision_options")` separately, call
`tool_step_complete(step_id=…)` — it bundles all four into one
result. Reduces 4 tool calls to 1; matters most on small models.

**Coaching mode.** When `researcher_config.interaction.autonomy_level
== 'coaching'`: don't auto-execute. Surface the protocol's
`pedagogical_prelude` (if present) as a question first. When a gate
fires, explain WHY it exists before offering the fix. Run
`tool_lessons(operation="mistake_replay")` at session start to surface
recurring patterns from the researcher's reliability + override logs.

**Your operating contract — keep `researcher_config.yaml` in sync.**
`inputs/researcher_config.yaml` is your secondary AGENTS.md. `sys_boot`
surfaces it as `config_directives` (+ a `config_reconcile_hint`). FOLLOW
those values (autonomy, quality_gate_policy, ambiguity_posture, agent_notes)
every session, and MAINTAIN them:

* **At startup**, reconcile the config with the researcher's stated goal —
  if they name a deliverable ("a paper", "a dashboard"), set
  `research_goal.output_types`; record the env in `runtime.compute_environment`.
* **On any intent shift**, update it via `sys_config(operation='set', …)`:
  "just be autonomous" → `interaction.autonomy_level=autopilot`; "we're
  submitting to Nature" → `output_types` + `writing_preferences.venue_template`
  + `citation_style`; project-specific rules → append to
  `interaction.agent_notes`. Never silently override a value the researcher
  set by hand — confirm first if it conflicts.

**Watch the context drop-zone.** The researcher can drop a paper, a
screenshot, a txt note, a PI email into `inputs/context/` (or a step's
`context/`) at ANY time — even mid-session. `sys_boot.new_context` and
`tool_route`'s `new_context` field surface files added/changed since the
last turn: when they appear, `sys_file_read` them and fold anything
relevant into the current step's plan / analysis before continuing.

**Keep the glossary alive.** When you introduce a domain term the
researcher's collaborators (or a future reader) might not know, add a row
to `docs/glossary.md` (`term | definition | source`). `sys_boot.glossary_unfilled`
nudges when it's still empty after real work has happened.

**Never load `_router_index.yaml` directly.** That file is a maintainer
artifact — the routing logic reads it server-side. For routing, call
`tool_route`. For ranked alternatives, call `tool_semantic_route`. For
finding a tool by what it does, call `sys_semantic_tool_search`. These
scale as the catalog grows; dumping the full catalog every turn does not.

Lost? `sys_help` returns a compact orientation block. Useful topics:

* category orientation — `synthesis`, `methodology`, `visualization`,
  `audit`, `literature`, `writing`, `categories`
* operating patterns — `routing`, `iteration`, `overrides`, `recovery`
* researcher gradient — `fields`, `depth`
* meta — `anti_patterns`, `docs`

If `tool_route` returns `resolved_level=0` (no trigger matched) OR a
genuinely cross-disciplinary / open-ended ask, load
`guidance/scope_clarification` — it asks ONE narrowing question, then
hands back to `tool_route` with a workable prompt.

Append-only logs (`methods.md`, `analysis.md`, `citations.md`) only via
`mem_*`. Numbers go in `mem_log(kind="decision")` /
`mem_log(kind="methods")` / `mem_log(kind="hypothesis")` so the audit
trail is intact. Every decision must cite its grounding via
`tool_ground(mode="explicit")` (which inputs/context/papers informed
it) — otherwise `tool_verify(scope="project")` flags it before
synthesis.

---

## Workspace modes

`sys_boot` reports `workspace_mode` (set at `research-os init
--workspace-mode <m>`, or the wizard; changeable via
`inputs/researcher_config.yaml :: workspace.mode`). It shapes what "a
unit of work" and "done" mean — let it steer routing:

* **analysis** (default) — the classic numbered-step model. A unit of
  work is an experiment step under `workspace/NN_*`; "done" is figures +
  tables + grounded conclusions (`guidance/analysis_plan`).
* **tool_build** — Research OS governs a software build from above
  (`spec/`, `decisions/`, `eval/`, `milestones.md`, `governance.md`); the
  tool lives in an inner git repo (`workspace.inner_repo`). A unit of
  work is a **commit / iteration in the inner repo**, and "done" is
  **tests / build / eval passing, not figures**. Route to the `build/*`
  protocols: `build/spec_and_design` (what + definition of done) →
  `build/implement_iteration` (the inner loop; loops per increment) →
  `build/test_strategy`, `build/benchmark_vs_baseline`,
  `build/release_and_changelog`. Drive the inner repo with `tool_git`;
  run the configured `workspace.commands` (build / test / lint) with
  `tool_build(operation="build"|"test"|"lint")`; gate "done" with
  `tool_audit(scope="tool", dimension="build"|"tests")`. Use
  `tool_bash_exec` for anything else, and `tool_task` for long builds.
* **exploration** — scratch-first. `workspace/scratch/` is home base;
  gates are light; promote a probe to a numbered step only when it earns it.

---

## Quick lookup

| Need | Look in |
|---|---|
| Full tool list | `sys_protocol_list` → `sys_tool_describe(name)` |
| Tight tool shortlist for one protocol | `sys_active_tools(protocol_name)` (~10-15 tools) |
| Find a tool by what it does | `sys_semantic_tool_search(query=…)` (top-k by cosine) |
| See ranked protocol candidates (not just `tool_route`'s primary) | `tool_semantic_route(prompt=…)` |
| Which project is THIS request for? | `sys_active_project` |
| Researcher pivoted mid-plan | `tool_plan(operation="clear")`, then re-`tool_route` |
| Vague / cross-disciplinary ask | `guidance/scope_clarification` (narrow before routing) |
| Step naming | `guidance/analysis_plan` |
| Deliberate iteration (recolour fig, tighten cutoff) | `tool_step(operation="iterate")` (snapshot first), then re-run |
| Are outputs in sync with their scripts? | `tool_audit(scope="project", dimension="version_coherence")` |
| Synthesis quality bars | the `synthesis/*` protocol you're running |
| New file mid-flow | `tool_context_intake` |
| Broken workspace | `tool_workspace_repair` |
| Quick smoke tests | `workspace/scratch/` + `tool_scratch_*` |
| Recovery | `sys_checkpoint_list` → `sys_checkpoint_rollback` |
| End of session | `sys_session_handoff` |
| Change autonomy | `sys_config(operation="set", key=interaction.autonomy_level, value=…)` |
| Cold start (no prior context) | `sys_help` then `sys_help(topic='routing')` |
| What did a tool do? | `sys_tool_describe(tool_name)` |
| Bypass a quality gate (researcher-authorised) | `sys_help(topic='overrides')` |

---

## Hard rules (NEVER violate)

1. **`.os_state/` is never hand-edited** (internal state). `inputs/` is the
   researcher's source-of-truth and is editable — but `inputs/raw_data/` +
   `inputs/literature/` are the ORIGINAL record: change them only with
   `force=true` + the researcher's OK (the write warns + flags the intake
   inventory stale). `inputs/context/` is a free drop-zone — write there
   freely.
2. **Never invent citations.** All final-deliverable citations are
   verified via `tool_citations_verify` (Crossref / Semantic Scholar /
   PubMed / arXiv); `tool_synthesis_check` surfaces unresolved keys
   in synthesis/paper.typ before compile.
3. **Never use causal language** ("causes", "proves", "leads to") on
   observational data. Use "is associated with" / "is consistent with".
4. **Never commit a method or library from training memory alone.**
   Run `tool_research_method` / `tool_research_tool` first; register
   the citation as the decision's grounding.
5. **Never delete in `workspace/`.** Use `sys_path(operation="abandon")`
   — it renames to `__DEAD_END`, preserves files.
6. **Never block on a long job.** Use `tool_task(operation="run")`
   (local) or `tool_slurm_submit` (cluster); poll status.
7. **Never pick step slugs from training memory** — derive from the
   step's actual goal (`guidance/analysis_plan`).
8. **Never use judgemental language** about the source researcher in
   any deliverable. Use supportive professional voice ("would benefit
   from", "consider", "the alternative interpretation is"). Refer to
   prior work as "the initial analysis" unless the researcher
   authorises a named credit. No first person.
9. **Never one-shot complex prompts.** The router persists an
   `active_plan`; walk it with `tool_plan(operation="advance")`. The
   server gates final compile via `tool_typst_compile` — author the
   synthesis file, run `tool_synthesis_check` until clean, THEN
   compile.
10. **Each figure is `<slug>.png` + an authored `<slug>.caption.md` —
    nothing else by default.** The caption goes inline in
    `conclusions.md` next to the figure embed; the sibling sidecar is
    the technical metadata (dpi, units, palette). SVG and PNG-summary
    sidecars are opt-in via
    `inputs/researcher_config.yaml :: figures.svg_allowed: true` and
    `figures.summary_sidecar: true`. **You write the plotting script
    yourself** in matplotlib / ggplot2 / Altair / plotly / d3 per
    `visualization/figure_guidelines`. Research-OS does NOT ship a
    parametric chart-builder. `tool_figure_palette` returns CVD-safe
    colours; `tool_audit(scope="step", dimension="figure_full")` checks
    DPI + sidecars + label-overlap. For visualisation types that benefit from reader
    exploration (networks, multi-panel dashboards, large hierarchies),
    ship an interactive `<slug>.html` companion (Plotly / D3 / Altair).
    **Before declaring a step done, the AI MUST `sys_file_read` every
    figure it produced** — catches legend-over-plot, missing axis
    labels, palette regressions, snake_case-leaking-into-label bugs
    that no JSON audit catches. Every number in `synthesis/paper.typ`
    must trace to a workspace output —
    `tool_audit(scope="project", dimension="claims")` flags
    hallucinations.
11. **Multi-script steps need a `pipeline.yaml`** — defined via
    `tool_step_pipeline(operation="define")`, run via
    `tool_step_pipeline(operation="run")`.
    The runner topologically orders + content-hash-caches; one
    monolithic script that produces outputs in MULTIPLE categories
    (figures + tables + reports) is BLOCKED by
    `tool_audit(scope="step", dimension="completeness")` — split into atomic sub-tasks.
12. **Iterate vs. fix.** A bug fix bumps `_v<n>` on the affected
    script and re-runs. A deliberate design iteration (recolour a
    figure, tighten a cutoff, swap a model) must call
    `tool_step(operation="iterate", step_id=…, rationale=…)` FIRST so the
    prior scripts + outputs + captions + conclusion are snapshotted into
    `.versions/v<n>/` as a coordinated unit.
    `tool_audit(scope="project", dimension="version_coherence")` flags any
    output whose `.prov.json` points at a script that is no longer the
    highest version on disk.

---

## When the researcher explicitly overrides a rule

The hard rules above describe defaults. When the researcher EXPLICITLY
authorises a bypass — words like "skip the audit", "just draft it",
"give me a partial preview" — the AI may pass per-audit override flags
(e.g. `override_discussion_coverage=true` on
`tool_discussion_coverage_audit`, `override_no_pdfs=true` on
`tool_audit(scope="synthesis", dimension="all")`) or `override_gate=true`
(`tool_plan(operation="advance")`). REQUIREMENTS:

* The authorisation must be in the researcher's CURRENT message, not
  inferred from past behaviour or assumed from silence.
* Always pass `override_rationale` quoting WHY the researcher wants
  the bypass. The override is appended to `workspace/logs/override_log.md`
  so `audit/pre_submission_checklist` can resurface every bypass at
  publish time.
* Project-level posture lives at `interaction.quality_gate_policy` in
  `inputs/researcher_config.yaml` (`enforce` / `allow_override` /
  `warn_only`). Default is `enforce`.
* The override is never permanent — the next deliverable call re-runs
  the gate. The researcher must re-authorise each bypass.

If the researcher's request would force a violation of a Hard Rule that
is NOT a quality gate (e.g. invent a citation, hand-edit `.os_state/`),
refuse and explain the constraint. Editing original inputs
(`inputs/raw_data/` + `inputs/literature/`) is NOT absolute — it's a soft
guard: proceed with `force=true` once the researcher confirms, and note
the intake inventory is now stale.

Research OS does **not** manage LLM provider keys. The IDE owns model
access. The only credentials it uses are for literature / web search.
