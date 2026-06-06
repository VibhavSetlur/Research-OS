# Phase 13 Follow-ups (CLI cleanups for v2.0.0 prep)

All 8 IDEs validated GREEN in Phase 13. The minor cleanups below should land before v2.0.0 tag:

## Required fixes

1. **Version mismatch in MCP initialize response** (claude report)
   - `server.py` reports version `1.27.1` to MCP initialize handshake
   - `research-os --version` reports `2.0.0-dev`
   - Fix: ensure MCP server reads its version from `__version__` / pyproject, not a hard-coded string
   - Likely at: `src/research_os/server.py` around the `Server(name="research-os", version=...)` instantiation

2. **`.gitignore` template missing entries** (opencode, vscode, multiple)
   - `research-os init` scaffolds a `.gitignore` that does not include `workspace/cache/` or `workspace/scratch/`
   - Fix: append both lines to the template in `src/research_os/cli.py` or `templates/.gitignore`

3. **`research-os ide config-path <ide>` subcommand** (cursor, continue)
   - Not implemented; only `list / add / remove` exist
   - Workflow-of-validation surfaced it as expected; minor convenience
   - Either implement (one-line `print(REGISTRY[name].path)`) or document `ide list | grep <ide>` as the canonical way
   - Recommend: implement, it's tiny

4. **`doctor` exit code policy** (multiple)
   - Currently exits 1 on warnings, 2 on failures
   - Reported as a minor confusion in 5+ IDE reports
   - Either: rename "warnings" to "notes" + exit 0 (more conventional), OR document the 0/1/2 policy at top of `doctor` output
   - Recommend: document the policy in `doctor` header line

## Environment-level warnings (NOT fixes, just FYI for users)
- `embeddings_fresh` STALE — every YAML edit triggers this; user runs `python scripts/build_embeddings.py`
- `chromium_on_path` not installed — print-stylesheet audit unavailable; only needed for that one feature
- `gitignore_covers_state` (see #2 above)

## All-green verdict

All 8 IDEs (cursor, claude, antigravity, opencode, vscode, windsurf, continue, aider) had:
- `research-os init` scaffolds correctly
- IDE-specific MCP config wired to the right path
- `research-os start` launches the MCP server
- `research-os ide list / add / remove` cycles work
- `research-os doctor` runs

Per-IDE reports at `docs/v2_handoff/phase_13_ides/<ide>.md`.
