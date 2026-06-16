# Research OS workspace

This is a Research OS workspace. Full operating rules live in `AGENTS.md`
at the project root — read it first.

**Every session — two MCP calls on the first turn, then hierarchical
routing.** The AI only ever acts AFTER a researcher message arrives;
the two calls below fire back-to-back on the first turn before anything
else.

1. `sys_boot` — your FIRST MCP call (first turn only). Returns state +
   config + history + dep inventory + next protocol + pause
   classification + active plan. Never call `sys_state_get` /
   `sys_config_get` / `sys_protocol_history` / `sys_protocol_next`
   separately while sys_boot's payload is fresh.
2. `tool_route(prompt=<their verbatim message>)` — your SECOND MCP
   call. Hierarchical L1→L2→L3 picker. Returns `resolved_level`,
   `intent_class`, `sub_intent`, `primary_protocol`, `shortcut_tool`,
   `decomposition`, `complexity`, `ask_user`. If `ask_user` is
   non-null, ASK that question and re-route.
3. For `complexity: high`, `tool_route` persists an `active_plan` to
   `.os_state/active_plan.json`. Call `tool_plan(operation="turn")` to
   get the batch for this turn (sized to your `model_profile`). Walk it
   with `tool_plan(operation="advance")` after each step. If
   `chat_split_recommended` is true, hand off + tell the researcher to
   open a fresh chat.
4. For `complexity: low`, call the shortcut tool directly OR load the
   primary protocol with `sys_protocol_get format='summary'` (~300
   tokens), then `format='step' + step_id='<id>'` when ready to execute.

On **subsequent turns** of the same session, skip `sys_boot` — its
payload is still in context — and go straight to `tool_route` (or
continue an in-flight plan via `tool_plan(operation="advance")`).

Tools use underscores: `sys_state_get`, `tool_data_profile`,
`mem_log`. Dot notation + legacy aliases auto-rewrite.

Never write to `inputs/raw_data/` or `inputs/literature/` (immutable).
All workspace I/O goes through MCP tools.

When the researcher EXPLICITLY authorises a quality-gate bypass,
pass the relevant per-audit override (e.g.
`override_discussion_coverage=true` + `override_rationale=…` on
`tool_discussion_coverage_audit`, or `override_gate=true` +
`override_rationale=…` on `tool_plan(operation="advance")`). The override is
appended to `workspace/logs/override_log.md`; the pre-submission audit
resurfaces every bypass.

For DELIBERATE iteration of a step (recolour figure, tighten cutoff,
swap a model) call `tool_step_iterate(step_id, rationale=…)` BEFORE
editing — it snapshots scripts + outputs + captions + conclusion as
a coordinated `.versions/v<n>/`. `tool_audit_version_coherence` flags
outputs whose `.prov.json` points at a script that's no longer the
highest version on disk.
