Confirmed: `opencode.json` at project root is opencode's official convention (per opencode docs, opencode reads `opencode.json` or `opencode.jsonc` from the project root). The wiring is correct.

Total elapsed: ~3 minutes from start. Returning full report.

---

# Research-OS v2.0.0 — Phase 13 CLI Validation Report (IDE=opencode)

**Scratch dir:** `/tmp/ro_v2_cli/opencode/`
**Total elapsed:** ~3 minutes

## Step-by-step PASS/FAIL

| Step | Result | Notes |
|------|--------|-------|
| 1. Create + clean scratch dir | PASS | `/tmp/ro_v2_cli/opencode/` |
| 2. `cd` into scratch | PASS | |
| 3. Activate conda env `research-os` | PASS | |
| 4. `research-os init . --ide opencode --yes` | PASS | exit=0, 0s elapsed; 30 files / 12 directories; 6/6 smoke checks passed; log: `/tmp/ro_v2_cli/opencode/init.log` |
| 5. Verify scaffold | PASS | `workspace/` `inputs/` `docs/` `.os_state/` all exist; `inputs/researcher_config.yaml` has sensible defaults (`project_name: "opencode"`, supervised autonomy, etc.); IDE config landed at `/tmp/ro_v2_cli/opencode/opencode.json` (opencode's official convention — project-root `opencode.json` per opencode docs) |
| 6. `research-os start` (background, sleep 5, kill) | PASS | Verified with `timeout 4 research-os start < /dev/zero` → exit=124 (timeout-killed-while-alive). MCP stdio server is silent until RPC traffic arrives — empty log is normal/expected |
| 7a. `research-os ide list` | PASS | Shows `✓ opencode  opencode.json` (wired) |
| 7b. `research-os ide remove opencode` | PASS | exit=0; `opencode.json` deleted |
| 7c. `research-os ide add opencode` | PASS | exit=0; `opencode.json` regenerated with identical 282-byte content |
| 8. `research-os doctor` | PASS (with warnings) | **exit=1** (3 warnings, 0 failures) — exit=1 is by design when warnings present (`exit_code` property at `cli_doctor.py:86-92`: fail→2, warn→1, clean→0) |

## `research-os doctor` results — last 50 lines

```
Install checks
  ✓ python_version               Python 3.11.15 (>= 3.10)
  ✓ conda_active                 Conda env active: research-os
  ✓ version_consistency          All three agree on v2.0.0-dev
  ✓ in_tree_packs_registered     All 5 in-tree packs register cleanly
  ✓ external_pack_entrypoints    No external packs installed (this is fine)
  ⚠ embeddings_fresh             Embeddings are STALE: router index has been edited since the last build
      → fix: Rebuild embeddings: `python scripts/build_embeddings.py`
  ✓ typst_on_path                typst found on PATH
  ⚠ chromium_on_path             No Chromium on PATH (print-stylesheet audit unavailable)
      → fix: Install Chromium or set `pyppeteer` to download its own binary.

Workspace checks
  ✓ optional_deps                interactive_figures disabled; no extra deps required
  ✓ mcp_configs_wired            All declared IDEs wired (opencode)
  ✓ workspace_integrity          Workspace integrity OK
  ✓ disk_space                   Workspace size 0.00 GB (under 5.0 GB)
  ✓ git_clean                    Workspace is not a git repo; nothing to check
  ⚠ gitignore_covers_state       .gitignore missing entries: workspace/cache/ (or workspace/scratch/)
      → fix: Append the missing lines to .gitignore.

Summary: 11 pass, 3 warn, 0 fail
OK with warnings.
```

## IDE-specific MCP config location

**Landed correctly at `/tmp/ro_v2_cli/opencode/opencode.json`** — this is opencode's official convention (opencode reads `opencode.json` from the project root for MCP server configuration, similar to how cursor reads `.cursor/mcp.json`).

Config content (282 bytes):
```json
{
  "mcp": {
    "research-os": {
      "command": "research-os",
      "args": ["start"],
      "env": {"RESEARCH_OS_WORKSPACE": "${workspaceFolder}"}
    }
  },
  "system_prompt": "Read AGENTS.md at the project root before any research request."
}
```

The `mcp_configs_wired` doctor check also confirmed: `All declared IDEs wired (opencode)`.

## Warnings worth noting (not opencode-specific; affect all IDEs)

1. **`embeddings_fresh`** — repo-level: router index edited since last embedding build. Fix: `python scripts/build_embeddings.py` from the Research-OS repo (one-time before tagging release).
2. **`chromium_on_path`** — host-level: no Chromium on Poplar PATH; print-stylesheet audit unavailable. Environmental, not a code bug.
3. **`gitignore_covers_state`** — template gap: `.gitignore` written by `init` lacks `workspace/cache/` (or `workspace/scratch/`) entries. **Minor template fix candidate** — suspected location: the `.gitignore` template emitted during scaffold (search `templates/.gitignore` or wizard scaffold code in `src/research_os/wizard.py`). Suggested fix: append `workspace/cache/` and `workspace/scratch/` to the template `.gitignore`.

## Overall verdict

**PASS for IDE=opencode.** All 8 workflow steps succeeded. Doctor exit=1 is by design (warnings present, 0 failures). All warnings are global (host/repo-level), not opencode-wiring bugs. The opencode MCP config landed at the correct opencode-convention path (`opencode.json` at project root) and was correctly detected by `mcp_configs_wired`. Remove/re-add cycle is idempotent.