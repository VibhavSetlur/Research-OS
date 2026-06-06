The reminder is about the parent task tracker, not new work to do — my task is read-only validation per the constraints. Returning the report.

---

# Phase 13 — IDE=cursor CLI fresh-install validation

**Result: PASS (all functional steps)**

## Per-step results

| Step | Status | Notes |
|------|--------|-------|
| 1. Scratch dir prep `/tmp/ro_v2_cli/cursor/` | PASS | Cleaned and empty |
| 2. cd + conda activate `research-os` | PASS | CLI on PATH, version `2.0.0-dev` |
| 3. `research-os init . --ide cursor --yes` | PASS | Exit 0, 32 files / 14 directories, smoke check 6/6 |
| 4. Scaffold verification | PASS | `workspace/`, `inputs/`, `docs/`, `.os_state/` all present; `researcher_config.yaml` valid; `project_name: "cursor"` |
| 5. Cursor MCP config wired | PASS | `.cursor/mcp.json` + `.cursor/rules/research-os.mdc` (correct Cursor project-local convention) |
| 6. `research-os start` (5s + kill) | PASS | Stdio server stayed alive 5s (timeout 124), no stderr output |
| 7a. `research-os ide list` | PASS | Shows `cursor` as wired (✓), other 7 IDEs as available (·) |
| 7b. `research-os ide remove cursor` | PASS | Exit 0; `.cursor/mcp.json` and `.cursor/rules` both deleted |
| 7c. `research-os ide add cursor` | PASS | Exit 0; both files recreated identically |
| 8. `research-os doctor` | **Exit 1 (by design)** | 11 pass, 3 warn, 0 fail. `mcp_configs_wired` ✓ for cursor |

## Doctor exit code

**Exit 1 is intentional**, per `/scratch/vsetlur/Research-OS/src/research_os/cli_doctor.py:11-14` and `:86-92`: `0=all pass`, `1=≥1 warn`, `2=≥1 fail`. The 3 warnings are environment-level, not cursor-specific:
- `embeddings_fresh` — STALE (router index edited since last build)
- `chromium_on_path` — no Chromium installed
- `gitignore_covers_state` — `.gitignore` missing `workspace/cache/` or `workspace/scratch/`

## Cursor-specific MCP config landing

Wired to `/tmp/ro_v2_cli/cursor/.cursor/mcp.json` — this is Cursor's documented per-project MCP convention. Config contents:
```json
{"mcpServers":{"research-os":{"command":"research-os","args":["start"],"env":{"RESEARCH_OS_WORKSPACE":"${workspaceFolder}"}}}}
```
Companion rules file at `.cursor/rules/research-os.mdc` with `alwaysApply: true` frontmatter. Doctor's `mcp_configs_wired` check confirms both land in the right spot.

## Minor finding (not a failure)

`research-os ide` subcommands are `{list, add, remove}` only — there is no `ide config-path <ide>` subcommand. The workflow instructions hinted it might exist; `ide list` is the right way to see per-IDE config paths. Not a bug — just a doc/instruction nit. **Suggested fix (1-line):** If desired, add a `config-path` subcommand alias that prints just the expected path for one IDE (one-line `print(REGISTRY[name].path)`).

## Artifacts

- `/tmp/ro_v2_cli/cursor/init.log` — init output
- `/tmp/ro_v2_cli/cursor/start.log` — empty (stdio server, no stderr emitted in 5s)
- `/tmp/ro_v2_cli/cursor/doctor.log` — full doctor output (28 lines)

## Total elapsed: ~120s