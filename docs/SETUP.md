# Setup — install, MCP wiring, troubleshooting

This is the deep dive on getting Research OS installed and connected to
your AI IDE. For the 5-minute version, see [START.md](START.md).

---

## 1. Prerequisites

* Python 3.10 or newer.
* `pip` (or `uv` / `poetry` / `conda` — anything that installs a Python
  package).
* An AI IDE that supports MCP: Claude Code, OpenCode, Antigravity,
  Cursor, Claude Desktop, VS Code (with MCP extension), Windsurf,
  Continue, or Aider.

Optional system tools (only needed for specific features):

| Tool | Required for |
|---|---|
| Node.js + `@mermaid-js/mermaid-cli` | rendering `workflow.mermaid` → PNG |
| TeX Live (`pdflatex` + `bibtex`) | `paper.tex` → PDF, `poster.tex` → PDF |
| R (`Rscript`) | `tool_r_exec`, `tool_rmarkdown_render` for `.Rmd` |
| Julia | `tool_julia_exec` |
| Quarto | `tool_rmarkdown_render` for `.qmd` |
| Jupyter | `tool_notebook_exec` for `.ipynb` |
| Docker | `tool_audit_reproducibility` containerised re-run |

Nothing in the list above is required for basic research with Research
OS. Each tool degrades gracefully (the relevant tool returns a clear
error explaining what to install).

---

## 2. Install

### Default (recommended)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

The `all` extra pulls every optional Python dependency.

### Minimal

```bash
pip install "research-os @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Core only. Add extras later: `pip install 'research-os[viz,audit]'`.

### Virtualenv

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

### Conda

```bash
conda create -n research-os python=3.11 -y
conda activate research-os
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

### Verify

```bash
research-os --help
python -c "import research_os; print(research_os.__version__)"
```

---

## 3. Scaffold a workspace

```bash
mkdir my-project && cd my-project
research-os init
```

The CLI surface — two commands by design:

```
research-os init [DIRECTORY] [OPTIONS]
  --name NAME           Project name (default: directory name)
  --domain DOMAIN       Optional hint: clinical|finance|nlp|genomics|...
  --question STRING     Initial research question (AI refines later)
  --ide IDE             Comma-separated, default "all":
                        cursor|claude|antigravity|opencode|vscode|
                        windsurf|continue|aider
  --force               Re-scaffold an existing workspace (preserves data)

research-os start [OPTIONS]
  --workspace PATH      (Optional, back-compat) Pin the server to a
                        specific workspace path. Equivalent to setting
                        RESEARCH_OS_WORKSPACE. Omit for global mode —
                        one server serves all projects.
  --transport stdio|sse Default stdio (what most IDEs use).
```

### The server is GLOBAL

You install Research OS once. The SAME `research-os start` binary
serves every project. Each MCP request resolves the active project
per-call:

1. `RESEARCH_OS_WORKSPACE` env var (set by your IDE MCP config to
   `${workspaceFolder}` so each IDE project gets its own context).
2. The current working directory walked up to `.os_state/`.
3. The current working directory as a fallback.

You rarely run `research-os start` manually — the IDE auto-launches it.

---

## 4. Wire up your IDE

`init` automatically drops the right config file for every supported
IDE. **Restart your IDE** after `init` so it picks up the new MCP config.

### Claude Code

* File dropped: `CLAUDE.md` (root) + `.claude/mcp.json` +
  `.claude/commands/`.
* Claude Code auto-detects `CLAUDE.md` and the MCP server.

### OpenCode

* File dropped: `opencode.json` (root).
* `opencode` picks it up automatically.

### Antigravity

* File dropped: `.antigravity/mcp.json` +
  `.antigravity/rules/research-os.md`.

### Cursor

* File dropped: `.cursor/mcp.json` + `.cursor/rules/research-os.mdc`.

### Claude Desktop

* File dropped: `.claude/mcp.json` inside the project. Claude Desktop
  reads this when you "Open project".
* For global Claude Desktop config (typically
  `~/Library/Application Support/Claude/claude_desktop_config.json`
  on macOS), add this snippet — substitute the absolute project path:

  ```json
  {
    "mcpServers": {
      "research-os": {
        "command": "research-os",
        "args": ["start"],
        "env": {"RESEARCH_OS_WORKSPACE": "/abs/path/to/your-project"}
      }
    }
  }
  ```

### VS Code

* File dropped: `.vscode/mcp.json`. Requires an MCP-aware extension
  (e.g. the official MCP extension or Continue).

### Windsurf

* File dropped: `.windsurfrules` + `.windsurf/mcp.json` (when
  applicable).

### Continue

* File dropped: `.continuerules`.

### Aider

* File dropped: `.aider.conf.yml` + a rule snippet you can paste into
  the `--read AGENTS.md` flag.

### Any other IDE

* `AGENTS.md` is the canonical rule file at the project root. Any AI
  client that lets you set custom instructions can be pointed at it.
  Add to the system prompt:

  > "Before responding to any research request, read `AGENTS.md` in the
  > project root and follow it. All research actions go through the
  > `research-os` MCP server."

---

## 5. Install without starting a project

If you want Research OS installed and your IDE wired up BEFORE you
have a project in mind:

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Done — `research-os` is on your `PATH`. When you eventually have a
project:

```bash
cd path/to/wherever
research-os init       # scaffold + drop IDE configs
```

### Setup prompt — let an AI handle the install

Paste this into any AI chat (Claude, ChatGPT, Cursor inline, OpenCode,
Aider — anywhere) and let it walk you through the setup end-to-end.

> I want to install and configure **Research OS** on this machine.
> Research OS is an MCP-native research operating system hosted at
> <https://github.com/VibhavSetlur/Research-OS>. Please walk me through
> all of this, asking me ONE question at a time when you need input:
>
> 1. **Check Python ≥ 3.10.** If missing, suggest how to install for
>    my OS (macOS / Linux / Windows / WSL — ask which I'm on).
> 2. **Install with all optional extras**:
>    ```
>    pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
>    ```
>    Use a virtualenv if I tell you to; otherwise install with
>    `--user`.
> 3. **Verify**: run `research-os --help` and show me the output.
> 4. **Detect my AI IDE.** Ask which I'm using (Claude Code / OpenCode
>    / Antigravity / Cursor / Claude Desktop / VS Code with MCP /
>    Windsurf / Continue / Aider / other). For the chosen IDE, tell me
>    what file Research OS will drop on `init`. If it needs a global
>    config snippet, show it — DO NOT modify global configs without
>    my approval.
> 5. **Show me the two-command workflow**:
>    ```
>    mkdir my-project && cd my-project
>    research-os init     # scaffolds + drops IDE config
>    ```
>    Then open the IDE on the folder and chat. `research-os start` is
>    auto-launched by the IDE; I rarely run it manually.
> 6. **Show me 5 essential prompts** I'll use most often:
>    - "fill out the intake"
>    - "what should I do next?"
>    - "run a baseline EDA"
>    - "draft the paper for a journal submission"
>    - "make me a dashboard"
> 7. **Optional credentials**: Research OS does NOT manage LLM
>    provider keys — my IDE owns model access. Optional literature /
>    web search keys live in `inputs/researcher_config.yaml
>    api_keys.*`. Don't ask me for them now.
> 8. **Point me at the docs**:
>    - `docs/START.md` — install + first-hour walkthrough + cheatsheet
>    - `docs/RESEARCHER_GUIDE.md` — full workflow walkthrough
>    - `docs/USE_CASES.md` — role × goal × output map
>    - `docs/FAQ.md` — common questions

Power-user tips for the prompt:

* For a different install path: *"Install via uv instead of pip."*
* Shared HPC: *"I'm on a shared cluster; install into `~/.local` using
  `pip install --user`."*
* Skip IDE wiring: *"Just install Research OS, I'll handle IDE config
  myself."*

---

## 6. Researcher configuration

`inputs/researcher_config.yaml` is auto-created. **Every field is
optional** — blank fields get sensible defaults applied silently. The
file tells the AI **who it's working with** and **how you want it to
behave**. Domain / research question / hypotheses are NOT here — drop
data into `inputs/` and say "fill out the intake"; the AI writes those
to `inputs/intake.md` + `docs/research_overview.md`.

The minimal useful subset (ordered most → least important):

```yaml
researcher:
  name: ""                         # who AI is talking to
  institution: ""
  orcid: ""

project_name: ""                   # blank → uses directory name

research_goal:
  output_types: []                 # paper | abstract | poster | dashboard | report | exploratory
  target_venue: ""

interaction:
  autonomy_level: "supervised"     # manual | supervised | autopilot

model_profile: "medium"            # small | medium | large

runtime:
  shared_server: false             # set true on HPC / shared boxes
```

Full schema: [RESEARCHER_GUIDE.md § 8](RESEARCHER_GUIDE.md#8-configuration-inputsresearcher_configyaml).

### Pick the right `model_profile` for your AI

**This is the most important knob if you're not on a frontier model.**
The default is `medium` — change it the first time you set up if your
AI doesn't match.

| Set `model_profile:` to | If your IDE is using… |
|---|---|
| `small` | Claude **Haiku 4.5**, GPT-4o-mini, Gemini 2.5 Flash, Llama 3.3-70B, Mistral, Phi-4, any local model |
| `medium` *(default)* | Claude **Sonnet 4.5 / 4.6**, GPT-4o / GPT-4.1, Gemini 2.5 Pro, Llama 4 Maverick |
| `large` | Claude **Opus 4.x**, GPT-5 / o-series, Gemini 3 Pro |

What it actually changes:

* `small`  → 1 step/turn, summary-only protocol loads, prefers shortcut
  tools, skips optional audits. Designed to keep context lean.
* `medium` → 3 steps/turn, summary loads with drill-down, full audits.
* `large`  → 6 steps/turn, can pull full protocol loads, deeper
  multi-step plans.

Symptoms that mean you picked wrong:

* AI **runs out of context** mid-plan → drop to `small`.
* AI **hands off after every step** when you'd expect more progress →
  bump to `medium` or `large`.
* AI **skips an audit you wanted** → bump up.

### API keys (optional)

Research OS does NOT manage LLM provider keys — your IDE owns model
access. The credentials below are for literature / web search only.
Free public endpoints work without any keys.

```yaml
api_keys:
  semantic_scholar: ""             # https://www.semanticscholar.org/product/api
  pubmed: ""                       # NCBI eutils — https://www.ncbi.nlm.nih.gov/account/
  crossref: ""
  firecrawl: ""                    # https://firecrawl.io
  serpapi: ""                      # https://serpapi.com (web search fallback)
```

These are auto-exported as env vars (`SEMANTIC_SCHOLAR_API_KEY`, etc.)
when the server starts.

---

## 7. Verify everything works

In your IDE, in a fresh chat:

> "Read `AGENTS.md`. Call `sys_boot` and report what you see."

A healthy install returns project + config + state + dep inventory +
recommended next protocol in one short message.

Confirm which project the server resolved:

> "Call `sys_active_project` and tell me what it returned."

You should see `has_os_state: true` and a `resolved_via` field naming
either the env var or the cwd walk.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `research-os: command not found` | Add `~/.local/bin` (or the venv's `bin/`) to `PATH`. |
| IDE shows MCP error: `spawn research-os ENOENT` | The IDE can't find `research-os`. Use the absolute path in the MCP config, OR install Research OS into the env the IDE uses. |
| Tool calls hang silently | Your IDE may not be MCP-aware. Check the MCP panel for stderr. |
| `WriteProtectedError` when AI tries to write | Cannot write into `inputs/raw_data/` or `inputs/literature/`. Move to `workspace/` instead. |
| `Not a Research OS workspace` | Run `research-os init .` here, or open a folder that has been initialised. The server resolves per-request via env var or cwd. |
| `sys_active_project` returns `has_os_state: false` | The IDE opened a folder that hasn't been initialised. Run `research-os init` there. |
| State / dir look broken | Ask the AI: "Run `tool_workspace_repair`." Heals without deleting. |
| Citation tool returns 0 results | Check internet, optional API key, and the query string. Public endpoints have rate limits. |
| Mermaid PNG not rendering | `npm install -g @mermaid-js/mermaid-cli`. |
| `pdflatex not found` | Install TeX Live. The relevant tools fail gracefully without it. |
| `tool_audit_reproducibility` slow | It re-runs every script. Skip in autopilot unless explicitly asked. |

See also [FAQ.md](FAQ.md) for common questions.
