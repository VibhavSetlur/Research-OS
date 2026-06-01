# Setup — install, MCP wiring, troubleshooting

This is the deep dive on getting Research OS installed and connected to
your AI IDE. For a 5-minute version, see [QUICKSTART.md](QUICKSTART.md).

---

## 1. Prerequisites

* Python 3.10 or newer.
* pip (or `uv` / `poetry` / `conda` — anything that can install a Python
  package).
* An AI IDE that supports MCP: Claude Code, OpenCode, Antigravity, Cursor,
  Claude Desktop, VS Code (with MCP extension), Windsurf, Continue, or Aider.

Optional system tools (only needed for specific features):

| Tool | Required for |
|---|---|
| Node.js + `@mermaid-js/mermaid-cli` | rendering workflow.mermaid → PNG |
| TeX Live (pdflatex + bibtex) | paper.tex → PDF, poster.tex → PDF |
| R (Rscript) | `tool_r_exec`, `tool_rmarkdown_render` for .Rmd |
| Julia | `tool_julia_exec` |
| Quarto | `tool_rmarkdown_render` for .qmd |
| Jupyter | `tool_notebook_exec` for .ipynb |
| Docker | `tool_audit_reproducibility` containerised re-run |

Nothing in the list above is required to do basic research with Research OS.
Each tool degrades gracefully (the relevant tool returns a clear error
explaining what to install).

---

## 2. Install

### Default (recommended)

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

The `all` extra pulls every optional Python dependency the tools may use.

### Minimal

```bash
pip install "research-os @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Core only — search + literature + viz + execution + audit extras are not
installed. You can add them later (`pip install 'research-os[viz,audit]'`).

### Inside a virtualenv

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

### Conda (server / shared environments)

```bash
conda create -n research-os python=3.11 -y
conda activate research-os
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Verify:

```bash
research-os --help
```

---

## 3. Scaffold a workspace

```bash
mkdir my-project && cd my-project
research-os init
```

The two CLI commands:

```
research-os init [DIRECTORY] [OPTIONS]
  --name NAME           Project name (default: directory name)
  --domain DOMAIN       Optional hint: clinical|finance|nlp|genomics|...
  --question STRING     Initial research question (AI refines later)
  --ide IDE             Comma-separated, default "all":
                        cursor|claude|antigravity|opencode|vscode|windsurf|continue|aider
  --force               Re-scaffold an existing workspace (preserves data)

research-os start [OPTIONS]
  --workspace PATH      (Optional, back-compat) Pin the server to a
                        specific workspace path. Equivalent to setting
                        RESEARCH_OS_WORKSPACE. Omit for global mode —
                        one server serves all projects.
  --transport stdio|sse Default stdio (what most IDEs use)
```

You can pass `--name "Cohort 2024"` to set the project name; everything else
is optional. The AI fills the rest later.

**The server is global.** Install once with `pip install research-os`;
the SAME `research-os start` binary serves every project. Each MCP
request resolves the active project per call via:
  1. `RESEARCH_OS_WORKSPACE` env var (set by IDE MCP config to
     `${workspaceFolder}` so each IDE project gets its own context)
  2. The current working directory walked up to `.os_state/`
  3. The current working directory as a fallback

---

## 4. Wire up your IDE

`init` automatically drops the right config file for every supported IDE.
You typically need to **restart the IDE** so it picks up the new file.

### Claude Code

* File dropped: `CLAUDE.md` (root) + `.claude/mcp.json` + `.claude/commands/`.
* Claude Code auto-detects `CLAUDE.md` and the MCP server.

### OpenCode

* File dropped: `opencode.json` (root).
* `opencode` picks it up automatically.

### Antigravity

* File dropped: `.antigravity/mcp.json` + `.antigravity/rules/research-os.md`.

### Cursor

* File dropped: `.cursor/mcp.json` + `.cursor/rules/research-os.mdc`.

### Claude Desktop

* File dropped: `.claude/mcp.json` inside the project (Claude Desktop reads
  this when you "Open project").
* If you use Claude Desktop globally, copy this snippet into
  `~/Library/Application Support/Claude/claude_desktop_config.json`
  (macOS) — substitute `/abs/path/to/your-project`:

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

* File dropped: `.windsurfrules` + `.windsurf/mcp.json` (when applicable).

### Continue

* File dropped: `.continuerules`.

### Aider

* File dropped: `.aider.conf.yml` + a rule snippet you can paste into
  `--read AGENTS.md` flag.

### Any other IDE

* `AGENTS.md` is the canonical rule file at the project root. Any AI client
  that lets you set custom instructions can be pointed at it. Add this to
  the system prompt:

  > "Before responding to any research request, read `AGENTS.md` in the
  > project root and follow it. All research actions go through the
  > `research-os` MCP server."

---

## 5. Install without starting a project

If you want Research OS installed and your IDE wired up BEFORE you have
a project in mind:

```bash
pip install "research-os[all] @ git+https://github.com/VibhavSetlur/Research-OS.git"
```

Done — `research-os` is on your PATH. When you eventually have a project:

```bash
cd path/to/wherever
research-os init       # scaffold now
```

Want an AI to handle the install + IDE setup for you? Paste the
[Setup Prompt](SETUP_PROMPT.md) into any AI chat (Claude, ChatGPT, Cursor,
Aider — anything). It walks the install end-to-end for your IDE.

---

## 6. Researcher configuration

`inputs/researcher_config.yaml` is auto-created. **Every field is optional**
— blank fields get sensible defaults applied silently by `session_boot`.

The minimal useful subset:

```yaml
interaction:
  autonomy_level: "supervised"     # manual | supervised | autopilot

model_profile: "medium"            # small | medium | large

runtime:
  shared_server: false             # set true on HPC / shared boxes
```

Want to set up everything? See [GUIDE.md § 8](GUIDE.md) for the full schema.

### API keys (optional)

Research OS does NOT manage LLM provider keys — your IDE owns model access.
The credentials below are for literature / web search only. Free public
endpoints work without any keys.

```yaml
api_keys:
  semantic_scholar: ""             # https://www.semanticscholar.org/product/api
  pubmed: ""                       # NCBI eutils — https://www.ncbi.nlm.nih.gov/account/
  crossref: ""
  firecrawl: ""                    # https://firecrawl.io
  serpapi: ""                      # https://serpapi.com (web search fallback)
```

These are auto-exported as env vars (`SEMANTIC_SCHOLAR_API_KEY`, etc.) when
the server starts.

---

## 7. Verify everything works

In your IDE, in a fresh chat:

> "Read `AGENTS.md`. Call `sys_boot` and report what you see."

A healthy install returns project + config + state + dep inventory +
recommended next protocol in one short message.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `research-os: command not found` | Add `~/.local/bin` (or the venv's `bin/`) to PATH. |
| IDE shows MCP error: "spawn research-os ENOENT" | The IDE can't find `research-os`. Use the absolute path in the MCP config, OR install Research OS into the env the IDE uses. |
| Tool calls hang silently | Your IDE may not be MCP-aware. Check the MCP panel for stderr. |
| `WriteProtectedError` when AI tries to write | Cannot write into `inputs/raw_data/` or `inputs/literature/`. Move to `workspace/` instead. |
| "Not a Research OS workspace" | Run `research-os init .` here, or open a folder that has been `init`'d. The server resolves per-request via env var or cwd. |
| State / dir look broken | Ask the AI: "Run `tool_workspace_repair`." It heals without deleting. |
| Citation tool returns 0 results | Check internet, optional API key, and the query string. Public endpoints have rate limits. |
| Mermaid PNG not rendering | `npm install -g @mermaid-js/mermaid-cli`. |
| `pdflatex not found` | Install TeX Live. The relevant tools fail gracefully without it. |
| `tool_audit_reproducibility` slow | It re-runs every script. Skip in autopilot unless explicitly asked. |

See also [FAQ.md](FAQ.md) for common questions.
