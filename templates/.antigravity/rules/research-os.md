# Research OS workspace

This is a Research OS workspace. Full operating rules live in `AGENTS.md`
at the project root — read it first.

**Every session — two MCP calls, then hierarchical routing.**

1. `sys_boot` — one call returns state + config + history + dep inventory
   + next protocol + pause classification + active plan. Never call
   `sys_state_get` / `sys_config_get` / `sys_protocol_history` /
   `sys_protocol_next` separately while sys_boot's payload is fresh.
2. (await researcher's message)
3. `tool_route(prompt=<their message>)` — hierarchical L1→L2→L3 picker.
   Returns `resolved_level`, `intent_class`, `sub_intent`,
   `primary_protocol`, `shortcut_tool`, `decomposition`, `complexity`,
   `ask_user`. If `ask_user` is non-null, ASK that question and re-route.
4. For `complexity: high`, `tool_route` persists an `active_plan` to
   `.os_state/active_plan.json`. Call `tool_plan_turn` to get the batch
   for this turn (sized to your `model_profile` — small=1 step/turn,
   medium=3, large=6; heavyweight tools count for more). Walk it with
   `tool_plan_advance` after each step. Use `tool_plan_clear` if the
   researcher pivots. If `chat_split_recommended` is true, hand off +
   tell the researcher to open a fresh chat.
5. For `complexity: low`, call the shortcut tool directly OR load the
   primary protocol with `sys_protocol_get format='summary'` (~300
   tokens), then `format='step' + step_id='<id>'` when ready to execute.

Tools use underscores: `sys_state_get`, `tool_data_profile`,
`mem_analysis_log`. Dot notation + legacy aliases auto-rewrite.

Never write to `inputs/raw_data/` or `inputs/literature/` (immutable).
All workspace I/O goes through MCP tools.
