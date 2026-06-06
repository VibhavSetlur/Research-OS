# Research OS — integration guide

For developers embedding Research OS in something else: a custom MCP
client, a CI bot, a lab IDE, a hosted notebook, a one-shot batch
auditor. If you're a researcher just trying to use RO from your IDE,
this isn't the doc you want — read [START.md](START.md) instead.

Pair this with [CONTRACT.md](CONTRACT.md), which pins which surfaces
are stable enough to depend on.

---

## The three integration shapes

There are three ways code-outside-RO talks to code-inside-RO. Pick
based on your runtime.

| Shape | Use when | Stability |
|---|---|---|
| **MCP over stdio** | You have an MCP-speaking client (any IDE with MCP support). | Highest — this is the canonical interface. |
| **Headless dispatcher** | You're inside a Python process and want to call tools without spinning up an MCP transport (CI bot, audit-only batch run, embedded notebook). | High — `_handle_tool_call` is the same entry point the MCP server calls. |
| **Direct Python imports** | You want to use a specific action module (`audit`, `synthesis`, `viz`) on a workspace without touching the tool dispatcher. | Limited — re-exports from `research_os.plugins` are stable; everything else is internal. |

---

## Shape 1: MCP over stdio (the canonical integration)

Research OS ships a single console script:

```bash
pip install research-os                       # core
research-os start                             # launch the MCP server over stdio
```

Project resolution is **per-request**, not per-server. Set the env
var to tell RO which workspace each call belongs to:

```bash
RESEARCH_OS_WORKSPACE=/path/to/project research-os start
```

Most IDEs do this automatically by mapping `${workspaceFolder}` to
the env var in their MCP client config. A minimal client config (the
exact path and JSON shape varies per IDE — see
[SETUP.md](SETUP.md)):

```json
{
  "mcpServers": {
    "research-os": {
      "command": "research-os",
      "args": ["start"],
      "env": {
        "RESEARCH_OS_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

Once connected, your client sees `sys_*`, `tool_*`, and `mem_*` tools
(see [CONTRACT.md](CONTRACT.md) § A.1) plus `tool_<pack>_*` from any
installed packs. The first thing your client should do on session
start is call `sys_boot` — it returns project state, researcher
config, dep inventory, recommended next protocol, and any active
plan in a single round-trip.

---

## Shape 2: Headless dispatcher (Python-in-Python)

If you're already inside a Python process — a CI runner, a one-shot
batch auditor, an embedded notebook — bypass the MCP transport and
call the dispatcher directly. This is what the MCP server itself
does internally.

```python
from pathlib import Path
import json

import research_os.server as srv

# Workspace MUST exist on disk with .os_state/ already scaffolded.
# Use the wizard once, then point at it for every subsequent call:
#   from research_os.wizard import init_project
#   init_project(root=Path("/tmp/my_project"), interactive=False)

project = Path("/tmp/my_project").resolve()

# Every public tool is reachable via _handle_tool_call(name, args, root).
# It returns a list of MCP TextContent objects; .text is the JSON envelope.
result = srv._handle_tool_call(
    "sys_boot",
    {},
    project,
)
payload = json.loads(result[0].text)
assert payload["status"] == "success"
state = payload["data"]
print("next protocol:", state["next_protocol"]["id"])

# Route a researcher prompt to a protocol:
result = srv._handle_tool_call(
    "tool_route",
    {"prompt": "I want to write a methods section for my RNA-seq run"},
    project,
)
print(json.loads(result[0].text)["data"]["primary_protocol"])

# Run an audit (deterministic — no LLM call):
result = srv._handle_tool_call(
    "tool_audit_full",
    {},
    project,
)
findings = json.loads(result[0].text)["data"]["findings"]
# `findings` validates against
# src/research_os/schemas/audit_finding.schema.json
```

Key invariants:

* The dispatcher accepts both underscore (`sys_state_get`) and dot
  (`sys.state.get`) tool names and rewrites internally.
* Every handler returns a JSON envelope:
  `{"status": "success"|"error", "data": {...}, "error": "..."}`.
* The dispatcher **never raises** — errors are caught and returned
  as `{"status": "error", "error": "..."}`.
* You can call it concurrently across different project roots; do
  not call it concurrently against the same root (filesystem writes
  are not internally locked).

This is the right shape for a CI bot that runs `tool_audit_full` on
every PR and posts findings as comments.

---

## Shape 3: Direct Python imports

The stable Python re-exports live under `research_os.plugins`:

```python
from research_os.plugins import (
    PackRegistration, PackTool,
    register_tool, captured_tools,
    discover_packs, installed_packs,
)
```

These are the same names listed in `research_os/plugins/__init__.py`'s
`__all__` and are part of the contract (`CONTRACT.md` § A). Anything
else inside `research_os.*` is internal and may move under PATCH.

---

## Errors, status, and observability

* On a non-success envelope, `error` is human-readable and
  `data.code` (when present) is a stable machine code (`E_NO_PROJECT`,
  `E_MISSING_INPUT`, `E_GATE_BLOCKED`).
* `sys_dep_inventory` reports which optional integrations are
  installed (`[semantic]`, `[viz]`, `[audit]`, etc.) so your client
  can fail fast on missing deps instead of debugging tool-by-tool.
* `sys_packs_installed` reports the packs the server discovered at
  startup plus any pack-load errors (see
  `workspace/logs/pack_errors.log` for tracebacks).

---

## What you should NOT do

* Don't parse `AuditFinding.message` or `suggested_fix` with regex
  — those fields are MINOR-mutable (see CONTRACT.md § B). Group on
  the stable `audit_name + dimension + severity` tuple instead.
* Don't reach into `.os_state/*.json` — that's engine-internal.
  Read state through `sys_state_get` and `sys_protocol_history`.
* Don't try to drive an LLM from inside RO — Research OS does not
  manage providers, and the headless dispatcher will not call one
  for you. The IDE or your own orchestration code holds model
  access.
* Don't pin against `research_os.server` import paths or the
  `tools.actions.*` tree — those move under PATCH. Pin against
  tool names + `research_os.plugins` re-exports.
