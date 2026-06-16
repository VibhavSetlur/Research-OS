# /start-session

Run the Research OS session-start sequence (two MCP calls, then route):

1. `sys_boot` — one call returns state + config + history + dep inventory
   + recommended next protocol + pause classification + any active plan.
2. Reply with ONE short boot summary: project name, pipeline stage,
   active path, autonomy mode, expertise, model profile, and the
   recommended next protocol. Then WAIT for the researcher's message.
3. When they speak, `tool_route(prompt=<their verbatim message>)`. If
   `ask_user` is non-null, ASK that question and re-route.
4. If `complexity: high`: `tool_plan(operation="turn")` for the batch,
   then walk it with `tool_plan(operation="advance")`. If
   `complexity: low`: call the shortcut tool OR load the primary
   protocol with `sys_protocol_get format='summary'`.

Do NOT call `sys_state_get`, `sys_config_get`, `sys_protocol_history`,
`sys_protocol_next`, or `sys_dep_inventory` separately — `sys_boot`
returns the union.
