# Research OS — CLI reference

`research-os` ships four top-level commands. Three set up + run the
MCP server; the fourth diagnoses health.

| Command            | What it does                                         |
| ------------------ | ---------------------------------------------------- |
| `research-os init` | Scaffold a workspace ready for any AI IDE.           |
| `research-os ide`  | Add / remove / list AI IDE MCP configs.              |
| `research-os start`| Run the MCP server (your IDE auto-launches it).      |
| `research-os doctor` | Diagnose install + workspace health (this page).   |

See `research-os <command> --help` for full flag reference.

---

## `research-os doctor`

Runs a battery of health checks against the install and (if invoked
inside a workspace) the workspace itself. Modelled on `brew doctor` /
`rustup doctor` — every check returns one of three statuses:

| Status | Meaning                                                       |
| ------ | ------------------------------------------------------------- |
| pass   | Everything looks correct.                                     |
| warn   | Non-fatal: the user should know, but the install is usable.   |
| fail   | Something is genuinely broken and will bite at runtime.       |

### Exit codes

| Code | Condition                          |
| ---- | ---------------------------------- |
| 0    | All checks pass (no warnings).     |
| 1    | At least one warn, no fail.        |
| 2    | At least one fail.                 |

### Flags

| Flag              | Meaning                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `--verbose`       | Show fix hints even for passing checks.                              |
| `--workspace-only`| Skip install checks; only run workspace checks.                      |
| `--workspace PATH`| Explicit workspace path (default: walk up from CWD).                 |
| `--json`          | Emit machine-readable JSON instead of the human report.              |
| `--no-color`      | Disable ANSI styling (auto-disabled when `NO_COLOR` is set).         |

### What gets checked

#### Install-level (always)

| Check                       | Purpose                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------- |
| `python_version`            | Python >= 3.10 (matches `pyproject.toml`'s `requires-python`).                         |
| `conda_active`              | Warns if `CONDA_DEFAULT_ENV` is unset.                                                 |
| `version_consistency`       | `pyproject.toml`, `__init__.py`, `CITATION.cff` agree on the same version string.     |
| `in_tree_packs_registered`  | All 5 bundled packs (humanities, qualitative, theory_math, wet_lab, engineering) import and register cleanly. |
| `external_pack_entrypoints` | Lists external packs declared under the `research_os.protocol_pack` / `research_os.packs` entry-point groups. |
| `embeddings_fresh`          | `_embeddings.npz` mtime >= `_router_index.yaml` mtime — otherwise the semantic router is stale. |
| `typst_on_path`             | `typst` CLI for poster + PDF synthesis.                                                |
| `chromium_on_path`          | Optional: headless Chromium for the print-stylesheet audit.                            |

#### Workspace-level (only when inside a workspace)

| Check                       | Purpose                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------- |
| `optional_deps`             | If `synthesis.interactive_figures` is enabled, `pyvis` must be importable.             |
| `mcp_configs_wired`         | Each declared IDE has its primary MCP config file.                                     |
| `workspace_integrity`       | No orphan figures, no stale `step_summary.yaml`, no unresolved BLOCK gates in the audit ledger. |
| `disk_space`                | Workspace size under 5 GB (warns above).                                               |
| `git_clean`                 | Working tree clean (skipped when the workspace isn't a git repo).                      |
| `gitignore_covers_state`    | `.gitignore` mentions `.os_state/` and either `workspace/cache/` or `workspace/scratch/`. |

### Examples

```bash
# Full report — install + workspace if cwd is inside one.
research-os doctor

# Just JSON (for CI / scripts).
research-os doctor --json | jq .summary

# Show fix hints even for passing checks.
research-os doctor --verbose

# Only check this workspace (skip install).
cd /path/to/my-research && research-os doctor --workspace-only

# Explicit workspace path.
research-os doctor --workspace /path/to/my-research
```

### JSON shape

```json
{
  "checks": [
    {"name": "python_version", "status": "pass",
     "message": "Python 3.11.15 (>= 3.10)", "scope": "install"},
    ...
  ],
  "summary": {"pass": 6, "warn": 2, "fail": 0},
  "exit_code": 1
}
```

Every check entry has `name`, `status`, `message`, and `scope`
(`install` or `workspace`). When a check produced a fix hint, the
entry also carries a `fix` field.
