Doctor returned exit 1 because of warnings, but reports "OK with warnings." All 3 warnings are environmental (stale embeddings, no chromium, gitignore minor) — not VSCode-specific failures. The `mcp_configs_wired` check confirms VSCode wiring is correct.

I'll note the doctor exit-code-1-on-warnings as a potential issue worth flagging but not VSCode-specific.

---

# REPORT: Phase 13 CLI Validation — IDE=vscode

**Total elapsed: ~30 seconds of CLI work**

## PASS / FAIL per step

| # | Step | Result |
|---|------|--------|
| 1 | Prep scratch dir `/tmp/ro_v2_cli/vscode/` | PASS |
| 2 | `cd` to scratch | PASS |
| 3 | conda activate `research-os` | PASS |
| 4 | `research-os init . --ide vscode --yes` | PASS (exit 0, 0.12s, 30 files / 13 dirs, smoke 6/6) |
| 5 | Scaffold verification (workspace/, inputs/, docs/, .os_state/, researcher_config.yaml, `.vscode/mcp.json`) | PASS |
| 6 | `research-os start` background, sleep 5, kill | PASS (stays alive on open stdin; clean exit 0 on stdin close — correct MCP stdio behavior) |
| 7 | `ide list` → `ide remove vscode` → `ide add vscode` | PASS (file removed and re-created idempotently) |
| 8 | `research-os doctor` | EXIT 1 with "OK with warnings" — 11 pass / 3 warn / 0 fail |

## Doctor exit code
**1** — but human-readable summary says "OK with warnings" and zero hard fails. The 3 warnings are env-level, not VSCode-specific:
- `embeddings_fresh` — router index stale (dev-tree artifact)
- `chromium_on_path` — chromium missing (optional, audit-only)
- `gitignore_covers_state` — `.gitignore` missing `workspace/cache/` (minor scaffold gap)

## VSCode MCP config landing
Lands at `/tmp/ro_v2_cli/vscode/.vscode/mcp.json` — this is the conventional VSCode workspace path. Content:
```json
{
  "mcpServers": {
    "research-os": {
      "command": "research-os",
      "args": ["start"],
      "env": { "RESEARCH_OS_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```
VSCode (1.86+) reads `.vscode/mcp.json` for project-scoped MCP servers — correct location.

## Suggested fixes (not VSCode-blocking)
1. `gitignore_covers_state` warn — `research-os init` should write `workspace/cache/` and `workspace/scratch/` into the scaffolded `.gitignore`. Likely in the init scaffolder template.
2. `doctor` returning exit 1 on warn-only state is arguable — if intentional for CI strictness, document it; otherwise exit 0 on warnings, exit 1 only on fails.

## Bug summary: NONE for VSCode wiring
All VSCode-specific paths work. The 3 warnings are global env state and would surface for any IDE.

## Artifacts
- `/tmp/ro_v2_cli/vscode/init.log`
- `/tmp/ro_v2_cli/vscode/start.log` (empty — stdio server behavior)
- `/tmp/ro_v2_cli/vscode/doctor.log`
- `/tmp/ro_v2_cli/vscode/.vscode/mcp.json`

**Overall: VSCode IDE flow is GREEN.**