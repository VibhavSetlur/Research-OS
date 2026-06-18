# Sharing this project

**What this is for.** Two safe ways to send this project to a
collaborator (or your PI / advisor / Argonne team) without leaking
AI-internal config or large raw data. Both excludes `.os_state/`,
the IDE MCP configs, `AGENTS.md`, and `CLAUDE.md` by default — what
your collaborator opens looks like a finished research workspace,
not an in-progress AI session.

Pick the one that matches how you collaborate:

* **Option 1** — bundle a zip you can email or upload anywhere.
  No git knowledge required.
* **Option 2** — push to a private GitHub repo so your team can
  pull, contribute, and see the project's `CONTRIBUTORS.md` history.

---

## Option 1 — Zip archive

In your AI client, ask:

> "export a share archive of this project"

The AI will call the `sys_export_share_archive` tool (see
[`TOOLS.md`](TOOLS.md)) which writes
`workspace/exports/<timestamp>.zip` in the project root.

What's included: `inputs/` (minus raw data unless you ask the AI to
include raw inputs), `workspace/`, `synthesis/`, `docs/`,
`environment/`, and a top-level `README.md` if present.

What's excluded (always): `AGENTS.md`, `CLAUDE.md`, `GETTING_STARTED.md`,
`.os_state/`, `.claude/`, `.cursor/`, `.vscode/`, `.antigravity/`,
`.opencode/`, MCP configs, `__pycache__/`, virtualenvs, `node_modules/`.

For a citable, archival-quality bundle (RO-Crate metadata,
checksums, DOI-ready), ask the AI to "export an RO-Crate of this
project" instead — see the RO-Crate exporter docs.

## Option 2 — GitHub repo

Use the [GitHub CLI](https://cli.github.com/) directly. From the
project root:

```sh
gh repo create $(basename $PWD) --private --source=. --push
```

That one command initialises git if needed, creates the GitHub repo
named after the current folder, sets it as `origin`, and pushes the
first commit.

**Security note.** Default to `--private`. Only flip to `--public`
after confirming `inputs/` contains no sensitive data (PHI, embargoed
results, unpublished collaborator data, API keys). See the
`confidentiality_level` field documented for the project audit
metadata before publishing.

Requires `gh auth login` to be done once. Before running the command,
review your `.gitignore` to make sure AI-internal files
(`.os_state/`, `.claude/`, MCP configs) are excluded — the `init`
wizard adds these by default.

## What collaborators get

A clean research workspace they can read without any Research-OS context:

* `synthesis/dashboard.html` — the polished single-file dashboard
  (open in any browser; self-contained).
* `synthesis/figures/` — every curated figure with its caption sidecar.
* `synthesis/REPORT.md` / `synthesis/paper.typ` — the narrative deliverable.
* `workspace/NN_*/conclusions.md` — the per-step reasoning chain.
* `workspace/NN_*/scripts/` — the actual analysis code (reproducible).
* `workspace/NN_*/data/next_step_output/` — derived artefacts each step persisted.
* `docs/` — research question, glossary, workflow diagram.

The AI-side configuration is intentionally excluded, so the share
reads as a finished research project, not an in-progress AI workspace.
