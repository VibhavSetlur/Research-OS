# Contributing to Research OS

Thanks for being interested. Research OS is small on purpose — only
contribute changes that keep the surface small and the protocols sharp.

## Architecture in one paragraph

The AI IDE is the brain (Cursor / Claude Code / Claude Desktop /
OpenCode / Antigravity / VS Code / Windsurf / Continue / Aider).
Research OS is the body: 140 MCP tools and 82 YAML protocols, plus a
hierarchical L1 → L2 → L3 router that turns a user prompt into a
protocol pick + planned tool sequence without loading every YAML. It
enforces immutability (`inputs/raw_data/`, `inputs/literature/`) and
provenance (`workspace/methods.md`, `workspace/analysis.md`,
`.os_state/protocol_execution_log.jsonl`, `.os_state/active_plan.json`).
It never calls an LLM itself.

The server is **global** — install once with `pip install research-os`;
the SAME `research-os start` binary serves every project. Each MCP
request resolves the active project per call via the
`RESEARCH_OS_WORKSPACE` env var (set by the IDE MCP config to
`${workspaceFolder}`), or by walking up the current working directory
for `.os_state/`.

## Development setup

```bash
git clone https://github.com/VibhavSetlur/Research-OS.git
cd Research-OS
pip install -e ".[ci,dev]"           # lean install used by CI
# or pip install -e ".[all,dev]"     # everything except R / Julia / Docker
pytest                                # ~376 tests, ~8s
ruff check src/ tests/ scripts/
python scripts/preflight.py           # 13 wiring checks
```

## Adding or modifying a protocol

**Read [`docs/PROTOCOL_DOCTRINE.md`](docs/PROTOCOL_DOCTRINE.md) first.**
Every protocol must be a SCAFFOLD for reasoning, never a SCRIPT to
execute. The doctrine names the patterns that count as prescription
(specific tools, specific thresholds, finite menus of methods, canned
step sequences) and the patterns that count as scaffolding (questions
to ask, dimensions to reason over, demands for grounding). Reviews
reject prescriptive protocols on sight.

Each protocol lives at `src/research_os/protocols/<category>/<name>.yaml`.
Keep the schema tight:

```yaml
id: <protocol_id>
name: <Human Name>
version: '1.0.0'
schema_version: '2.0'
description: One-line summary.
trigger: When the AI should run this.
prerequisites:
  - state field or file
steps:
  - id: step_id
    name: Step Name
    description: |
      Concrete tool calls (underscore form), one numbered action per step.
expected_outputs:
  - path/to/file
quality_bar: |
  Pass/fail bullets that gate completion.
next_protocol: category/next_one      # null if terminal
on_failure: guidance/dead_end_routing # null if no fallback
```

* The loader injects the standard `protocol_completion` step — do NOT add it.
* `next_protocol` must point at a real protocol or `null`. Verify no cycles.
* **REQUIRED**: add an entry for the new protocol to
  `src/research_os/protocols/_router_index.yaml` with `intent_class`,
  `sub_intent`, `summary`, and `triggers`. Preflight will fail if you
  forget. Optionally add `shortcut_tool`, `token_estimate`, and a
  `decomposition` list.
* Add to `PIPELINE` in `src/research_os/tools/actions/protocol.py` only
  if it's part of the main pipeline ordering.

## Adding a new tool

1. Implement the action in `src/research_os/tools/actions/<category>/<file>.py`
   (state/, data/, exec/, search/, research/, audit/, synthesis/,
   memory/). Cross-cutting modules — `protocol.py` and `router.py` —
   live flat at `tools/actions/`. Return a dict with
   `status="success"|"error"` plus either `data` or `message`.
2. Add an entry to `TOOL_DEFINITIONS` in `src/research_os/server.py`
   with `short` (≤160 chars) + full `description` + `category` +
   `inputSchema`. Use underscore naming (`sys_X_Y`, `tool_X_Y`, `mem_X_Y`).
3. Add a handler `_handle_<name>(name, arguments, root)` and register it
   in the `_HANDLERS` dict at the bottom of `server.py`.
4. If the tool is something `tool_route` should know about, add it to
   `_router_index.yaml` either as a `decomposition` entry in an existing
   protocol or as a `shortcut_intents` entry.
5. If you're replacing an old tool name, add the alias to `_ALIASES`
   so older protocols keep working.
6. Reference the tool from at least one protocol or shortcut — orphaned
   tools become dead code and will be removed in the next cleanup.

## Testing

Tests live in `tests/{unit,integration,tools}/`. Run a focused subset:

```bash
pytest tests/tools/test_router.py -v
pytest tests/unit/test_protocols.py::TestProtocolLoading
```

Add tests for any new tool's success + error paths in
`tests/tools/test_<area>.py`. Router or protocol changes should ship
with at least one test that exercises the new behaviour end-to-end.

## Style

* Ruff defaults; line length 100.
* Type hints required on new functions.
* One short module docstring at the top of every new file.
* No emojis in source or markdown unless an existing convention requires it.
* No backwards-compat shims for code that hasn't shipped. We're at 1.0.0;
  breaking internal refactors are OK as long as the MCP surface
  (`_HANDLERS` keys + JSON schemas) stays stable or has aliases.

## Reporting issues

Use the GitHub issue templates. Include the version
(`pip show research-os`), the OS, the steps to reproduce, the full
traceback, and any relevant log excerpt from `workspace/logs/`.
