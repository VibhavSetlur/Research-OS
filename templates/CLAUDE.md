# Research OS workspace — Claude Code

This is a Research OS workspace. **Read `AGENTS.md` at the project root
first** — it contains the canonical operating rules.

You only act AFTER a researcher message arrives. On the **first turn
of a session**, fire two MCP calls back-to-back before doing anything
else:

1. `sys_boot` — your FIRST MCP call. Returns project state + researcher
   config + protocol history + dep inventory + recommended next protocol
   + pause classification + any active plan. Do NOT call the individual
   `sys_state_get` / `sys_config` / `sys_protocol_next` /
   `sys_dep_inventory` / `sys_protocol_history` calls separately.
2. `tool_route(prompt=<their verbatim message>)` — your SECOND MCP
   call. Picks the right protocol via a hierarchical L1 (`intent_class`)
   → L2 (`sub_intent`) → L3 (protocol) walk. If `ask_user` is non-null,
   ASK that one-sentence question and re-route — never guess.
3. For `complexity: high`, the router persisted an `active_plan`.
   Call `tool_plan(operation="turn")` to get the batch sized to your
   `model_profile` (small=1, medium=3, large=6 steps per turn, weighted
   for heavy tools). Execute every entry in `this_turn` IN ORDER. After
   each one, call `tool_plan(operation="advance")`. If
   `chat_split_recommended` is true, hand off and tell the researcher to
   open a fresh chat.
4. For `complexity: low`, call the shortcut tool directly OR load the
   primary protocol with `sys_protocol_get format='summary'` (~300
   tokens), then `format='step' + step_id='<id>'` when ready to execute.

Tools use underscores (`sys_state_get`, `tool_data`, `mem_log`). Dot
notation and legacy names auto-rewrite. Need the full description of a
tool? `sys_tool_describe(tool_name)`.

Treat `inputs/raw_data/` + `inputs/literature/` as source-of-truth: edit only with `force=true` + researcher OK (soft guard). `inputs/context/` is a free drop-zone. `.os_state/` is never hand-edited.
All workspace I/O goes through `sys_file_*` so provenance is captured.

**Workspace modes.** `sys_boot` reports `workspace_mode` (analysis /
tool_build / exploration). In **tool_build** mode Research OS governs a
software build from above (`spec/`, `decisions/`, `eval/`) while the tool
lives in an inner git repo; route to the `build/*` protocols, drive the
inner repo with `tool_git` + `tool_build`, gate via
`tool_audit(scope='tool')`, and remember "done" = tests / build / eval
pass, not figures. See the Workspace modes section in `AGENTS.md`.

Research OS does NOT manage LLM provider keys — Claude Code owns model
access. The only credentials Research OS uses are for literature / web
search providers (all optional).
