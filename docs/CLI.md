# Research OS — CLI reference

`research-os` ships these top-level commands. Three set up + run the
MCP server; the others diagnose health and emit shell completions.

| Command            | What it does                                         |
| ------------------ | ---------------------------------------------------- |
| `research-os init` | Scaffold a workspace ready for any AI IDE.           |
| `research-os ide`  | Add / remove / list AI IDE MCP configs.              |
| `research-os mcp`  | Compose third-party MCP servers into IDE configs.    |
| `research-os api-key` | Manage api_keys in `inputs/researcher_config.yaml`. |
| `research-os start`| Run the MCP server (your IDE auto-launches it).      |
| `research-os doctor` | Diagnose install + workspace health (this page).   |
| `research-os completion` | Print a sourceable shell-completion script.    |

See `research-os <command> --help` for full flag reference.

---

## `research-os init`

Scaffolds a Research OS workspace ready for any AI IDE. Interactive by default; pass `--yes` for non-interactive / scripted use.

```bash
# Interactive 7-step arrow-key wizard (default).
research-os init

# Non-interactive / CI / scripted — wires only Claude Code, no prompts.
research-os init . --yes --name "my-project" --ide claude

# Wire all supported IDEs.
research-os init . --yes --ide all

# Skip IDE wiring entirely (e.g. for headless / CI / multi-user HPC).
research-os init . --yes --ide none

# Comma-separated list of specific IDEs.
research-os init . --yes --ide cursor,vscode,windsurf
```

### `--ide` values

`cursor`, `claude`, `antigravity`, `opencode`, `vscode`, `windsurf`, `continue`, `aider` — plus the sentinels:

- `all` — wire every supported IDE (drops MCP config files in each).
- `none` — first-class opt-out; no MCP config written.

Unknown values exit non-zero with a message listing valid options.

---

## `research-os ide add | remove | list`

Wires / unwires / inspects AI IDE MCP configs in an existing workspace without re-running `init`. Use this when you start using a new IDE on a project that's already initialized.

```bash
research-os ide add cursor              # add Cursor MCP config to this workspace
research-os ide remove vscode           # remove VS Code's
research-os ide list                    # which IDEs are wired here
research-os ide config-path claude      # print the absolute path of the config file
```

---

## `research-os mcp add | list | remove | template`

Composes **other** MCP servers (Slack, GitHub, Postgres, Filesystem,
Memory, Notion, ...) into the IDE configs Research-OS already manages,
so your AI IDE picks them up alongside the RO server.

Additive to `research-os ide add`, which wires the RO server itself.

```bash
# Drop a vetted snippet for a known server (with ${TOKEN} placeholders).
# Known templates: slack, github, postgres, notion, filesystem, memory.
research-os mcp template slack

# Roll your own — adds to every wired IDE config by default.
research-os mcp add my-server --command npx --args=-y,@scope/server-name

# Restrict to specific IDEs (cursor, claude, antigravity, vscode, opencode).
research-os mcp add my-server --command npx --args=-y,@x --ide cursor,claude

# Inspect every wired server across IDEs.
research-os mcp list

# Remove (idempotent — no-op if not present).
research-os mcp remove my-server
```

Note: only IDEs with JSON `mcpServers` (or `mcp` for OpenCode) blocks
can be composed this way. Windsurf / Continue / Aider use their own
rule files and are not supported here.

---

## `research-os api-key add | list | rotate | remove | test`

Manages the `api_keys:` block of `inputs/researcher_config.yaml`.
Hidden input via `getpass` so secrets never echo; `chmod 600` is
re-applied after every write.

```bash
# Hidden prompt (getpass) — value is read interactively, not from argv.
research-os api-key add semantic_scholar

# CI-friendly: read from an env var so the secret never appears in a
# shell-history file or a CI log.
research-os api-key add openai --from-env OPENAI_API_KEY

# Show every configured provider with masked previews (abcd…wxyz).
research-os api-key list

# Replace an existing key (same as `add`; just clearer naming).
research-os api-key rotate pubmed

# 1-token round-trip against the provider to verify the key works.
# Reports "OK" or "FAIL <reason>". Known: semantic_scholar, pubmed, crossref.
research-os api-key test pubmed

# Clear a key (sets the value to "").
research-os api-key remove crossref
```

Exit codes: `0` on success / OK; `1` on FAIL; `2` on bad usage (no
provider given, etc.).

---

## `research-os start`

Runs the MCP server. Your AI IDE auto-launches this; you rarely call it directly.

```bash
research-os start                       # uses current directory as workspace
research-os start --workspace /path/to/project
```

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
| `workspace_integrity`       | No orphan figures, no unresolved BLOCK gates in the audit ledger. |
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

---

## `research-os completion`

Print a sourceable shell-completion script. Supports **bash**, **zsh**, and
**fish**. After sourcing the output, `research-os <TAB>` completes
subcommand names and `research-os init --ide <TAB>` completes IDE names.

```bash
# Install into your shell rc file (one-liner):
eval "$(research-os completion zsh)"     # zsh — add to ~/.zshrc
eval "$(research-os completion bash)"    # bash — add to ~/.bashrc
research-os completion fish | source     # fish — for current shell
research-os completion fish \
  > ~/.config/fish/completions/research-os.fish   # fish — persistent
```

For richer dynamic completion in bash/zsh (subcommand-aware flags),
install the `completion` extra so [argcomplete](https://pypi.org/project/argcomplete/)
backs the generated script:

```bash
pip install "research-os[completion]"
```

Without that extra, a smaller hand-rolled fallback is emitted — TAB
still completes top-level subcommands and `--ide` values.
