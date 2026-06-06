Total elapsed: ~93 seconds (17:34:02 init → 17:35:35 doctor).

The task list reminder is noted but I'm running as a subagent under Phase 13 already; no new task tracking needed for my single delegated step. Here's the final report.

---

# Phase 13 CLI Validation — IDE=aider

## PASS/FAIL per step

| # | Step | Result | Notes |
|---|---|---|---|
| 1 | mkdir+clean /tmp/ro_v2_cli/aider | **PASS** | Empty dir created |
| 2 | cd to scratch | **PASS** | |
| 3 | conda activate research-os | **PASS** | python 3.11.15, CLI v2.0.0-dev |
| 4 | `research-os init . --ide aider --yes` | **PASS** | Exit 0; --yes is supported |
| 5 | Scaffold verification | **PASS** | workspace/, inputs/, docs/, .os_state/ all present; researcher_config.yaml has sensible defaults (project_name=aider, autonomy=supervised, model_profile=medium, etc.); `.aider.conf.yml` wired with `read: AGENTS.md` |
| 6 | `research-os start` in background → kill | **PASS** | Python proc PID 2048248 confirmed alive in CWD /tmp/ro_v2_cli/aider after 5s; stdio MCP server emits no startup banner by design — empty log is expected behavior |
| 7 | `ide list` → `ide remove aider` → `ide add aider` | **PASS** | All three subcommands exit 0; .aider.conf.yml correctly deleted on remove and recreated on add; list output reflects state correctly |
| 8 | `research-os doctor` | **PASS (with warnings)** | Exit code = **1**, summary "11 pass, 3 warn, 0 fail / OK with warnings". 0 hard failures. |

## `research-os doctor` exit code
**Exit 1** — corresponds to "warnings present, 0 failures". Three warnings (all environmental, none aider-specific):
- `embeddings_fresh` — STALE: router index edited since last build (dev-env artifact)
- `chromium_on_path` — no Chromium on PATH (optional dependency)
- `gitignore_covers_state` — .gitignore missing workspace/cache/ or workspace/scratch/

## IDE-specific MCP config landed at the expected path
**YES.** `.aider.conf.yml` written at `/tmp/ro_v2_cli/aider/.aider.conf.yml`. Aider auto-loads `.aider.conf.yml` from the project root on startup (per aider docs), so this is the canonical location. The file contains a `read: - AGENTS.md` directive that auto-injects RO operating rules into every aider chat, plus `auto-commits: false` to let RO own the state ledger.

**Note**: aider does NOT support MCP natively. The generated config explicitly documents this in its header comment ("Aider does NOT support MCP natively. You can still use Aider to author Research OS scripts, but you'll need to invoke Research OS tools by running `research-os start` in a separate terminal"). This is expected behavior — wiring aider is "rules injection" rather than "MCP wiring", and the CLI handles this correctly.

## Minor flag mismatch documented (not a bug)
- `research-os ide config-path aider` is NOT a valid subcommand. The `ide` group accepts only `list`, `add`, `remove`. The conventional path for aider is discovered via `research-os ide list` (which prints `.aider.conf.yml` next to the entry).

## Total elapsed time
**~93 seconds** (init.log 17:34:02 → doctor.log 17:35:35).

## Artifacts left in /tmp/ro_v2_cli/aider/
- `/tmp/ro_v2_cli/aider/init.log` — full init scaffold output
- `/tmp/ro_v2_cli/aider/start.log` — empty (expected for stdio MCP)
- `/tmp/ro_v2_cli/aider/doctor.log` — full doctor output
- Scaffold: AGENTS.md, GETTING_STARTED.md, README.md, STATE.md, .gitignore, CONTRIBUTORS.md, .aider.conf.yml, workspace/, inputs/, docs/, .os_state/, environment/, scripts/

## Overall verdict: **PASS** for IDE=aider on fresh install.
No code changes needed. No bugs filed. All 8 workflow steps succeed.