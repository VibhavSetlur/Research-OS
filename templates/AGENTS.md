# Research OS — AI Operating Rules

You are connected to the **Research OS MCP server**. This file is loaded
every prompt — keep it short. Step-by-step "how to do X" lives in the
**protocols** you load on demand.

For your full operating guide, call `sys_help` — it returns
the in-server orientation (routing pattern, namespaces, protocol
categories, anti-patterns). The fuller human-readable version is at
<https://github.com/VibhavSetlur/Research-OS/blob/main/docs/AI_GUIDE.md>.

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

## Every session — boot in two MCP calls

1. `sys_boot` → state + config + history + dep inventory + next protocol
   + pause + any active plan. Replaces 4-5 separate calls.
2. (await researcher's message)
3. `tool_route(prompt=…)` → hierarchical L1→L2→L3 picker. Returns
   `primary_protocol`, `shortcut_tool`, `decomposition`, `complexity`,
   `ask_user`. If `ask_user` is non-null, ASK that one sentence then
   re-route. Never guess.
4. `complexity="high"` → `tool_plan_turn` to batch by `model_profile`
   (small=1 step/turn, medium=3, large=6), execute in order, call
   `tool_plan_advance` after each. If `chat_split_recommended`, run
   `sys_session_handoff`.
5. `complexity="low"` → call `shortcut_tool` directly OR load the
   protocol via `sys_protocol_get format='summary'` (~300 tokens),
   drill in with `format='step' step_id=<id>` when ready.

Use `sys_protocol_get format='summary'` — never `format='full'` just to
list steps. Use `sys_tool_describe(name)` instead of re-listing all tools.
Use `sys_active_tools(protocol_name)` to scope your working tool set
to the protocol's decomposition.

Lost? `sys_help` returns a compact orientation block; pass
`topic="<category>"` (e.g. `synthesis`, `methodology`, `visualization`,
`audit`) for category-specific guidance.

Append-only logs (`methods.md`, `analysis.md`, `citations.md`) only via
`mem_*`. Numbers go in `mem_decision_log` / `mem_methods_append` /
`mem_hypothesis_update` so the audit trail is intact. Every decision
must cite its grounding via `tool_grounding_register` (which
inputs/context/papers informed it) — otherwise `tool_grounding_verify`
flags it before synthesis.

---

## Quick lookup

| Need | Look in |
|---|---|
| Full tool list | `sys_protocol_list` → `sys_tool_describe(name)` |
| Step naming | `guidance/analysis_plan` |
| Synthesis quality bars | the `synthesis/*` protocol you're running |
| New file mid-flow | `tool_context_intake` |
| Broken workspace | `tool_workspace_repair` |
| Quick smoke tests | `workspace/scratch/` + `tool_scratch_*` |
| Recovery | `sys_checkpoint_list` → `sys_checkpoint_rollback` |
| End of session | `sys_session_handoff` |
| Change autonomy | `sys_config_set key=interaction.autonomy_level value=…` |

---

## Hard rules (NEVER violate)

1. **Never write to `inputs/raw_data/` or `inputs/literature/`** — immutable.
2. **Never invent citations.** All final-deliverable citations come
   from `tool_synthesize` (verified online) or workspace literature
   sidecars.
3. **Never use causal language** ("causes", "proves", "leads to") on
   observational data. Use "is associated with" / "is consistent with".
4. **Never commit a method or library from training memory alone.**
   Run `tool_research_method` / `tool_research_tool` first; register
   the citation as the decision's grounding.
5. **Never delete in `workspace/`.** Use `sys_path_abandon` — it
   renames to `__DEAD_END`, preserves files.
6. **Never block on a long job.** Use `tool_task_run` (local) or
   `tool_slurm_submit` (cluster); poll status.
7. **Never pick step slugs from training memory** — derive from the
   step's actual goal (`guidance/analysis_plan`).
8. **Never use judgemental language** about the source researcher in
   any deliverable. Use supportive professional voice ("would benefit
   from", "consider", "the alternative interpretation is"). Refer to
   prior work as "the initial analysis" unless `synthesis_spec.yaml`
   authorises a named credit. No first person.
9. **Never one-shot complex prompts.** The router persists an
   `active_plan`; walk it with `tool_plan_advance`. The server BLOCKS
   advance into `tool_synthesize` / `tool_dashboard_create` /
   `tool_poster_create` when `tool_audit_quality_full` finds blockers.
10. **Every figure carries four sidecars** — `.caption.md` (technical),
    `.summary.md` (plain-English), `.prov.json` (provenance), and an
    SVG companion. PREFER `tool_figure_create`, which writes all of
    them in one call across 25+ publication-grade chart kinds (ROC,
    PR, calibration, QQ, residual diagnostics, forest, dot-and-
    whisker, raincloud, posterior, …). Every number in
    `synthesis/paper.md` must trace to a workspace output —
    `tool_audit_claims` flags hallucinations.
11. **Multi-script steps need a `pipeline.yaml`** — defined via
    `tool_step_pipeline_define`, run via `tool_step_pipeline_run`.
    The runner topologically orders + content-hash-caches; one-script
    mega-files are flagged by `tool_audit_step_completeness`.

Research OS does **not** manage LLM provider keys. The IDE owns model
access. The only credentials it uses are for literature / web search.
