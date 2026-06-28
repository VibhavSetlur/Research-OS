# The Research OS setup prompt (copy, fill the blanks, paste)

This is the **one prompt** to start any Research OS project. You don't need to
learn the CLI or read the docs first — copy the whole block below, fill in the
blanks (everything in `‹ ›`), and paste it to your AI assistant **with the
project folder open**. It tells the AI exactly how to install Research OS, wire
up *your* IDE only, start the daemon, **test that everything actually works**,
and then onboard your project properly before any analysis begins.

Only three things are required: the **project name**, your **goal**, and the
**context block** (just dump your thoughts — the AI sorts it out). Leave any
other blank as `unsure` or `none yet` and the AI will ask or pick a sensible
default. There is nothing you can get "wrong" here — the prompt is built so the
AI fills the gaps with you.

---

## Copy from here ▼

```text
You are setting up a Research OS project for me in the folder that's open. Follow
these steps IN ORDER. Ask me ONE question at a time only when a REQUIRED field is
blank or genuinely ambiguous — otherwise pick a sensible default and tell me what
you picked. Do not start any analysis until setup is verified and I've restarted.

═══════════════════════════════════════════════════════════════════
PROJECT
  • Project name:        ‹ e.g. readmission-risk ›
  • One-line goal:       ‹ what do you want to find out / build? ›
  • Success looks like:  ‹ a paper? a dashboard? a working tool? a decision? — or "unsure" ›

CONTEXT BLOCK  (just type or paste your raw thoughts — messy is fine.
  Background, the question behind the question, hypotheses, prior work,
  constraints, deadlines, who the audience is, anything on your mind.
  The AI will turn this into a proper project frame.)
  ‹ ...dump everything here... ›

DATA / INPUTS
  • Where is your data / are your inputs?   ‹ a path, a URL, or "none yet" ›
  • Anything sensitive (PII, embargoed)?    ‹ yes / no / unsure ›

ENVIRONMENT
  • My AI IDE / agent:    ‹ Claude Code | Cursor | VS Code | Windsurf | OpenCode | Aider | other — pick ONE ›
  • OS:                   ‹ macOS | Linux | Windows | WSL | shared HPC node ›
  • Use Hermes on top?    ‹ yes (most robust: memory + skills + autonomous runs) | no | what's that? ›

WORKING STYLE  (optional — leave blank for defaults)
  • Mode:        ‹ analysis (default) | tool_build | exploration | notebook | hybrid | multi_study | unsure ›
  • Autonomy:    ‹ supervised | adaptive (default) | autopilot | unsure ›
═══════════════════════════════════════════════════════════════════

NOW DO THIS, IN ORDER:

1. INSTALL (if needed). Check Python ≥ 3.10. If `research-os` isn't installed,
   run `pip install research-os` (use a venv/conda env if I'm on a shared/HPC
   machine — on HPC, conda, NOT Docker). Verify with `research-os --help`.

2. SCAFFOLD. From the project folder run (note the explicit `.` so it scaffolds
   THIS folder and does NOT nest a subfolder):
      research-os init . --ide ‹my IDE› --workspace-mode ‹mode or omit for analysis› --question "‹my goal›"
   Use ONLY my one IDE for --ide — NEVER `--ide all` (it litters config for 8
   editors) and avoid `--ide auto` if my shell's IDE env is ambiguous (it can
   guess wrong). If unsure which IDE, ASK me.

3. BRING IN DATA. If I gave a data path/URL, place it under inputs/raw_data/
   (copy if small/portable, symlink if large/shared) and note where it came from.
   If "none yet", skip.

4. WIRE MCP + FIX THE PATH FOOTGUN. Confirm the Research OS MCP server is
   registered for my IDE (`research-os ide list`); if not, `research-os ide add
   ‹my IDE›`. THEN: if research-os is installed in a conda/venv, the generated
   MCP config uses a bare `command: "research-os"` that fails with `spawn
   research-os ENOENT` when my IDE launches it outside that env. Run `which
   research-os` and, if it's inside a conda/venv, replace `"command":
   "research-os"` with that ABSOLUTE path in the generated `.‹ide›/mcp.json` (or
   `.mcp.json` / `opencode.json`).

5. START THE DAEMON (per-project enforcement + watch + provenance). Run
   `research-os daemon start` (or tell me it's optional and what it adds if I
   said I don't want long/background runs). The daemon is per-project — stop it
   with `research-os daemon stop` without losing run history. On a SHARED/HPC
   node the default port may be taken; do NOT trust exit code 0 — verify with
   `research-os daemon status` (it should say serving: yes), and if it isn't,
   start with a free `--port`.
6. ⚠ RESTART. Tell me to FULLY RESTART my IDE / AI session in this folder now —
   the MCP server only loads on a fresh session, so the Research OS tools will
   NOT appear until I do. STOP HERE and wait for me to confirm I've restarted.
   Do not continue to step 7 until I say I have.

7. SELF-TEST (after I restart). Prove the setup works before any real work:
      • Confirm the `research-os` MCP tools are visible to you now.
      • Call sys_boot — it should return state + config + mode + next protocol.
      • Call tool_route on my goal — it should return a real protocol/route.
      • Run `research-os doctor` and show me the result.
   If ANY of these fail, diagnose + fix it before proceeding, and tell me plainly.

8. ONBOARD (don't jump into analysis). Using my CONTEXT BLOCK and goal: help me
   frame the research question + hypotheses, confirm the workspace mode and
   inputs/researcher_config.yaml, scan what's in inputs/, and ONLY THEN open the
   first numbered step. A few minutes here makes the whole project more robust.

9. IF I'M USING HERMES: on this first setup turn, read my project frame (goal,
   domain, mode, data) and pull the Hermes skills relevant to it (domain
   analysis, the language/stat stack I'll use, paper/figure work) so they're
   loaded before we start — don't wait for me to ask. ALSO run
   `research-os skills add-science-pack` to install the community K-Dense
   scientific-agent-skills library (140 MIT science skills — e.g. bulk-rnaseq,
   experimental-design, literature-review, rdkit) and wire it into Hermes;
   `sys_boot`'s recommended_skills tells you which ones match this project.

From here on: route EVERY request through Research OS (tool_route → a numbered
step), never write analysis files without routing first, and if a tool ever tells
you you've drifted off-protocol, correct it that same turn.
```

## ▲ Copy to here

---

## Why each part is there

- **Context block** — the single most useful thing you provide. The AI reads
  your raw thoughts and turns them into a framed question, hypotheses, and a
  mode; you don't have to pre-structure anything.
- **One IDE, not all** — pointing the AI at Research OS used to make it install
  config for every editor. The prompt pins it to *your* IDE.
- **The restart step** — the #1 reason "it didn't work": MCP servers load when a
  session starts, so the tools only appear after you reopen the project. The
  prompt makes the AI stop and wait for it.
- **The self-test** — setup that isn't verified isn't setup. Steps 7 makes the
  AI prove the MCP connection, `sys_boot`, routing, and `doctor` all work before
  touching your data.
- **Onboard before analysis** — jumping straight to "run the model" skips the
  framing that keeps a project honest. Step 8 does ingestion → framing → config →
  first step in order.
- **Hermes (optional, recommended)** — the agent layer that adds memory across
  projects, reusable skills, and autonomous long runs. Step 9 has it pull the
  skills your project needs up front.

See [START.md](START.md) for the full guided walkthrough and
[SETUP.md](SETUP.md) for per-IDE wiring details.
