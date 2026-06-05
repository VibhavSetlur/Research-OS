# V2 IDE Validation Report (Phase 13)

Built from `docs/v2_handoff/phase_13_ides/<ide>.md`.

| IDE | PASS | FAIL | Suggested fix |
|-----|-----:|-----:|---------------|
| cursor | 10 | 0 | Suggested fix (1-line):** If desired, add a `config-path` subcommand alias that prints just the expected path for one ID... |
| claude | 11 | 2 | FAIL):** server.py reports version `1.27.1` in MCP `initialize` response while `research-os --version` reports `2.0.0-de... |
| antigravity | 8 | 0 | Suggested fix (1-line): drop `config-path` from any user-facing docs; rely on `ide list`. |
| opencode | 12 | 1 | Suggested fix: append `workspace/cache/` and `workspace/scratch/` to the template `.gitignore`. |
| vscode | 8 | 1 | — |
| windsurf | 11 | 0 | — |
| continue | 9 | 1 | — |
| aider | 10 | 1 | — |

Full per-IDE reports under `docs/v2_handoff/phase_13_ides/`.