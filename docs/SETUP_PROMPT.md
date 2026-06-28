# The Research OS Setup Prompt

**One prompt starts any Research OS project.** You do not need to read the docs,
learn the CLI, or structure your thoughts first. Open your project folder in your
AI assistant, copy the block below, fill in the brackets, and paste it.

The prompt tells the AI how to install Research OS, wire up **your** editor (only
yours), start the daemon, **verify it actually works**, and then **onboard your
project properly** — framing the question, ingesting your inputs, grounding in
real literature — *before any analysis begins*. Onboarding is the most important
step. Skipping it is how projects drift.

Only three fields are truly required: **project name**, **goal**, and the
**context block**. Everything else can be `unsure` — the AI will pick a sensible
default and tell you what it chose. You cannot fill this in "wrong."

---

## ▼ Copy from here

```text
You are setting up a Research OS project for me in the folder that is open.
Work through the steps IN ORDER. Ask me ONE question at a time, and only when a
REQUIRED field is blank or genuinely ambiguous — otherwise pick a sensible
default and tell me what you picked. Do NOT begin any analysis until setup is
verified and I have restarted my editor.

────────────────────────────  MY PROJECT  ────────────────────────────
[project name]   = e.g. airway-inflammation-rnaseq
[goal]           = in one line, what I want to find out or build
[success]        = a paper? a dashboard? a tool? a decision for the lab? (or: unsure)

[context]        = Just talk. Paste anything — messy is fine. Background, the
                   question behind the question, what I already tried, prior
                   results, who the audience is, deadlines, constraints, lab
                   politics, half-formed ideas. The AI will read this and turn
                   it into a real project frame. The more you dump, the better.

[hypotheses]     = one per line if you have them, else: none yet
                   - H1: ...
                   - H2: ...

[data]           = where my inputs live: a path, a URL, or "none yet"
[sensitive]      = any PII / embargoed / restricted data? yes / no / unsure

──────────────────────────  MY ENVIRONMENT  ──────────────────────────
[editor]         = pick ONE: Claude Code | Cursor | VS Code | Windsurf |
                   OpenCode | Aider | other
[os]             = macOS | Linux | Windows | WSL | shared HPC login node
[hermes]         = use the Hermes agent layer on top? yes (recommended) | no | what is that?

────────────────────  HOW I WANT TO WORK (optional)  ─────────────────
[mode]           = analysis (default) | tool_build | exploration |
                   notebook | hybrid | multi_study | unsure
[autonomy]       = supervised | adaptive (default) | autopilot | unsure
──────────────────────────────────────────────────────────────────────

NOW DO THIS, IN ORDER. Tell me what you did after each step.

1. INSTALL — Check Python ≥ 3.10. If `research-os` is not installed, run
   `pip install research-os` inside a venv or conda env (on a shared/HPC node
   use conda, never Docker). Verify with `research-os --help`.

2. SCAFFOLD — From the project folder, run (the explicit `.` scaffolds THIS
   folder and avoids nesting a subfolder):
     research-os init . --ide [editor] --workspace-mode [mode or omit] --question "[goal]"
   Use ONLY my one [editor] for --ide. Never `--ide all`. If [editor] is unclear,
   ask me — do not guess.

3. BRING IN DATA — If [data] is a path or URL, place it under inputs/raw_data/
   (copy if small/portable, symlink if large/shared) and record where it came
   from in the intake. If "none yet", skip.

4. WIRE MCP + FIX THE PATH FOOTGUN — Confirm the MCP server is registered
   (`research-os ide list`); if not, `research-os ide add [editor]`. Then: if
   research-os lives in a conda/venv, the generated config uses a bare
   `command: "research-os"` that fails with `spawn research-os ENOENT` when the
   editor launches it outside that env. Run `which research-os`; if it is inside
   a conda/venv, replace `"command": "research-os"` with that ABSOLUTE path in
   the generated `.[editor]/mcp.json` (or `.mcp.json` / `opencode.json`).

5. START THE DAEMON — `research-os daemon start`. The daemon is per-project and
   adds enforcement, a background watch, long/Docker job tracking, and
   provenance. On a shared/HPC node the default port may be taken; do NOT trust
   exit code 0 — verify with `research-os daemon status` (serving: yes), and if
   not, start with a free `--port`. (If I said I never want background/long runs,
   tell me the daemon is optional and what I lose without it.)

6. ⚠ RESTART — Tell me to FULLY restart my editor / AI session in this folder
   now. The MCP server only loads on a fresh session, so the Research OS tools
   will NOT appear until I do. STOP HERE and wait for me to confirm. Do not
   continue until I say I have restarted.

7. SELF-TEST (after I restart) — Prove the setup works before any real work:
     • Confirm the research-os MCP tools are visible to you now.
     • Call sys_boot — it should return state, config, mode, and the next protocol.
     • Call tool_route on [goal] — it should return a real protocol / route.
     • Run `research-os doctor` and show me the result.
   If any of these fail, diagnose and fix it before continuing, and tell me plainly.

8. ONBOARD — THIS IS THE IMPORTANT PART. Do not jump into analysis. Using my
   [context], [goal], and [hypotheses]:
     • Frame the research question and hypotheses with me, and register them.
     • Confirm the workspace [mode] and inputs/researcher_config.yaml.
     • Scan inputs/ (raw_data, literature, context) and profile any datasets.
     • Run a real literature pass — search for CURRENT papers on my topic and
       save the relevant ones into inputs/literature/. If I named papers in
       [context], fetch those. Do NOT rely on your training memory for what is
       published; check.
     • Show me the framed question + hypotheses + what you found, and ask me to
       approve or refine. ONLY THEN open the first numbered step.

9. IF I CHOSE HERMES — On this first turn, read my project frame (goal, domain,
   mode, data) and pull the Hermes skills relevant to it (my domain, my
   language/stat stack, paper/figure work) so they are loaded before we start;
   do not wait for me to ask. Also run `research-os skills add-science-pack` to
   install the K-Dense scientific-agent-skills library (community MIT science
   skills) and wire it into Hermes — `sys_boot`'s recommended_skills tells you
   which match this project.

FROM HERE ON: route EVERY request through Research OS (tool_route → a numbered
step), never write analysis files without routing first, and if a tool tells you
that you have drifted off-protocol, correct it that same turn.
```

## ▲ Copy to here

---

## Why each part matters

| Part | Why it is there |
|---|---|
| **`[context]`** | The single most valuable thing you give. The AI reads your raw thoughts and produces a framed question, hypotheses, and mode. You never pre-structure anything. |
| **One editor, not all** | Pointing an AI at Research OS used to wire config for eight editors. The prompt pins it to yours. |
| **The restart (step 6)** | The #1 reason "it didn't work." MCP servers load when a session starts, so the tools only appear after you reopen the project. |
| **The self-test (step 7)** | Setup that is not verified is not setup. The AI proves the MCP link, `sys_boot`, routing, and `doctor` before touching your data. |
| **Onboard before analysis (step 8)** | Jumping to "run the model" skips the framing and the literature grounding that keep a project honest and reproducible. This is where Research OS earns its keep. |
| **Hermes (step 9)** | The agent layer that adds cross-project memory, reusable skills, and autonomous long runs — and pulls the skills your project needs up front. See [the Hermes layer](START.md#the-hermes-layer). |

**Next:** [START.md](START.md) for the full guided walkthrough · [SCENARIOS.md](SCENARIOS.md)
to watch two real projects run end to end · [HOW_IT_WORKS.md](HOW_IT_WORKS.md)
for the concepts behind it.
