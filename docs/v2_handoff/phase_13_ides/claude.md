# Phase 13 — CLI fresh-install validation: IDE=claude

**Total elapsed:** 142s (~2m 22s)
**Scratch dir:** `/tmp/ro_v2_cli/claude/`
**research-os version:** 2.0.0-dev (server reports 1.27.1 in JSON-RPC initialize — minor metadata drift, not blocking)

## PASS / FAIL per workflow step

| # | Step | Result | Notes |
|---|------|--------|-------|
| 1 | Scratch dir setup | **PASS** | `/tmp/ro_v2_cli/claude/` cleaned + recreated |
| 2 | cd to scratch | **PASS** | |
| 3 | conda activate research-os | **PASS** | Python 3.11.15, env active |
| 4 | `research-os init . --ide claude --yes` | **PASS** | Exit 0; "33 files · 15 directories"; "Wired 1 AI IDE config(s): claude"; "6/6 checks passed" |
| 5 | Scaffold verification | **PASS** | `workspace/`, `inputs/`, `docs/`, `.os_state/` all present; `inputs/researcher_config.yaml` has sensible defaults (project_name="claude", autonomy_level="supervised", etc.); `.claude/mcp.json` wired |
| 6 | `research-os start` background + kill | **PASS** | stdio MCP server; verified by sending JSON-RPC `initialize` → got valid `{"protocolVersion":"2024-11-05","capabilities":{...},"serverInfo":{"name":"research-os","version":"1.27.1"}}` |
| 7a | `research-os ide list` | **PASS** | Shows `✓ claude .claude/mcp.json` (wired marker) plus 7 unwired IDEs |
| 7b | `research-os ide remove claude` | **PASS** | Removed `.claude/mcp.json, .claude/rules, .claude/commands, CLAUDE.md` |
| 7c | `research-os ide add claude` | **PASS** | Re-wired all four artifacts; list confirms `✓ claude` |
| 8 | `research-os doctor` | **PASS** | Exit code **1** = "OK with warnings" (intentional per `cli_doctor.py:737-738`); 11 pass, 3 warn, 0 fail |

## `research-os doctor` exit code

**Exit code: 1** (intentional — "OK with warnings"; not a failure)

3 warnings (all expected on a fresh scaffold, none claude-specific):
- `embeddings_fresh` — STALE router index (dev-env artifact, not user-facing)
- `chromium_on_path` — no Chromium (optional, only needed for print-stylesheet audit)
- `gitignore_covers_state` — `.gitignore` missing `workspace/cache/` / `workspace/scratch/` entries

## IDE-specific MCP config landing

**YES** — landed exactly where claude expects:

- **Path:** `/tmp/ro_v2_cli/claude/.claude/mcp.json` (project-local; matches Claude Code's project-scoped MCP convention)
- **Content:** valid `mcpServers.research-os` entry with `command: research-os`, `args: ["start"]`, `env.RESEARCH_OS_WORKSPACE: ${workspaceFolder}`
- **Companion artifacts:** `.claude/rules/research-os.md`, `.claude/commands/start-session.md`, top-level `CLAUDE.md`, `AGENTS.md`

## No FAILs

No bugs found. All four CLI surfaces (`init`, `start`, `ide ...`, `doctor`) work for IDE=claude from an empty directory. Recommend proceeding to the remaining 7 IDEs.

**Minor observation (not a FAIL):** server.py reports version `1.27.1` in MCP `initialize` response while `research-os --version` reports `2.0.0-dev`. Worth aligning before v2.0.0 release tag, but not blocking for Phase 13.

Relevant files:
- `/tmp/ro_v2_cli/claude/init.log`
- `/tmp/ro_v2_cli/claude/doctor.log`
- `/tmp/ro_v2_cli/claude/.claude/mcp.json`
- `/scratch/vsetlur/Research-OS/src/research_os/cli_doctor.py` (line 737 — exit-1-on-warn is intentional)