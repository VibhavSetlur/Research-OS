# FAQ

## Setup

### Do I need a Claude / OpenAI / Anthropic API key?

**No.** Research OS does NOT manage LLM provider keys. Your AI client
(Claude Code, OpenCode, Antigravity, Cursor, Claude Desktop, VS Code,
Windsurf, Continue, Aider, …) owns model access. Whatever you're already
paying for or using, Research OS sits behind it as an MCP server.

The only optional credentials Research OS uses are for literature / web
search providers (Semantic Scholar, PubMed, Crossref, Firecrawl, SerpAPI).
Public endpoints work without any keys — keys just raise rate limits.

### Does it work with `<my-AI-IDE>`?

If your IDE supports the Model Context Protocol (MCP) — yes.
`research-os init` drops a pre-wired config for Claude Code, OpenCode,
Antigravity, Cursor, Claude Desktop, VS Code, Windsurf, Continue, and
Aider. For anything else, point your IDE's system prompt at the
`AGENTS.md` file dropped at the project root and configure the MCP server
manually (see [SETUP.md § 4](SETUP.md)).

### Can I install Research OS now and start a project later?

Yes. `pip install` puts `research-os` on your PATH; nothing happens until
you `cd` somewhere and run `research-os init`. The
[SETUP.md § 5](SETUP.md) ships a "Setup Prompt" you can paste into
any AI chat to walk through install + IDE wiring without needing a
project at all.

### Does it work on a shared server / HPC cluster?

Yes. Set `runtime.shared_server: true` in `inputs/researcher_config.yaml`.
The protocols will automatically background long jobs via `tool_task_run`
(real `subprocess.Popen`) and warn before allocating heavy resources.

---

## Setup & configuration

### How do I add an API key later?

Edit `inputs/researcher_config.yaml` under the `api_keys:` block. The
file is created with `chmod 600` (owner read/write only) so secrets are
not world-readable. Example:

```yaml
api_keys:
  semantic_scholar: "s2_..."
  serpapi: "..."
  firecrawl: "fc_..."
```

You can leave any key blank. Research OS falls back to keyless public
endpoints (Crossref, PubMed, arXiv) automatically and only enables the
paid / rate-limited search backend when its key is present. No restart
needed — the server re-reads the file each session.

### Do I have to read all 110 protocols to know which to use?

No. You never browse protocols. You speak in plain English; `tool_route`
maps your message to the right protocol. As of v1.2.0 it tries
**semantic search first** (local BGE-small embeddings — no network,
no LLM API keys) and falls back to a hierarchical L1 → L2 → L3
trigger picker for unmatched / unavailable cases. "make me a dashboard
for executives", "fit a logistic regression", "tear apart this paper
as a tough reviewer" all resolve to one protocol with no menu surfing
on your end.

If you *want* to browse — for example to scope what Research OS can do
before committing a project — open [USE_CASES.md](USE_CASES.md). It is
the role × goal × output map (PI vs grad student vs reviewer × explore
vs publish vs teach × paper / poster / dashboard / lay summary). It
points each row at the protocol that will fire, so you can read the
catalogue from the outside-in instead of YAML-by-YAML.

### How do I add another AI IDE later?

```bash
research-os ide add <name>     # e.g. windsurf, continue, aider
research-os ide list           # see what's wired
research-os ide remove <name>  # tear out one config
```

This drops only the new IDE's MCP config; nothing else in the workspace
changes, no `--force` needed, and a row is appended to `CONTRIBUTORS.md`
so the project's history shows who wired what.

---

## Workflow

### I just want to dump files and have the AI figure out the rest. Possible?

Yes. After `research-os init`, drop your data / PDFs / notes anywhere in
`inputs/raw_data` / `inputs/literature` / `inputs/context`, then say:

> "fill out the intake"

`tool_intake_autofill` reads everything, classifies the domain, extracts
your research question + hypotheses from context notes, and writes them
into `inputs/intake.md` + `docs/research_overview.md` (with the
hypothesis ledger persisted to `.os_state/state.json`). Domain / research
question / hypotheses are intentionally NOT in `researcher_config.yaml`
— that file is reserved for fields a researcher actively chooses.

### Do I have to use the 10-stage pipeline?

No. The pipeline is the DEFAULT path `sys_protocol_next` recommends. You
can override at any time:

* "Iterate with me, what's next?" → loads `guidance/iterative_planning`.
* "Write the paper" / "Make a poster" → jumps straight to synthesis.
* "This experiment isn't working" → `guidance/dead_end_routing`.
* "Run a custom analysis I'm designing" → `guidance/analysis_plan` with
  `mem_methods_append implementation="custom"`.

### My AI keeps writing 400-line mega-scripts. How do I stop that?

The `guidance/analysis_plan` protocol (loaded on every analysis step)
forbids this. It mandates `tool_plan_step` for any non-trivial scope (>3
methods OR multiple subgroups OR custom pipelines), which forces a
breakdown into atomic versioned sub-tasks BEFORE any code is written.

If the AI ignores it, set `interaction.autonomy_level: manual` for a few
turns — you'll see exactly when it tries to mega-shot and can redirect.

### The AI keeps hallucinating citations. Help.

By construction, **citations in final synthesis outputs cannot be
hallucinated**. `tool_synthesize` pulls every citation from real providers
(Crossref / Semantic Scholar / PubMed / arXiv), drops any entry without a
DOI/URL, and verifies online. Unverified entries never make it into
`paper.md` / `abstract.md` / `poster.tex`.

For audit on demand: `tool_citations_verify` re-verifies every key in
`workspace/citations.md` and reports which fail.

### What if the right tool is a website / GUI / paid service the AI can't run?

Call `tool_external_tool_instructions`. It writes a `WORKSHEET.md` in the
current experiment folder explaining exactly what the researcher must do
(URL, inputs, parameters, where to drop outputs). The AI then resumes from
the dropped outputs once the researcher signals completion.

### Can I run multiple parallel experiments?

Yes. `sys_path_create` adds the next numbered folder. Multiple active
paths coexist (e.g. `02_logistic_baseline` AND `03_random_forest`). Use
`tool_branch_recommendation` if you're not sure whether to branch or
extend the current path.

### How do I track multiple hypotheses?

`mem_hypothesis_add` to register one (auto-assigned H1, H2, … or you pick
the ID), `mem_hypothesis_update` to log evidence + change status
(testing / supported / refuted / inconclusive), `mem_hypothesis_list` to
see the ledger. Every experiment step is asked which hypothesis IDs it
touches.

---

## Outputs

### Are dashboards / posters / papers actually publication-quality?

They aim to be. Each synthesis protocol declares explicit `quality_bar`
minimums:

* `synthesis_paper`: abstract 200-300 words, methods ≥400 words, ≥1 figure,
  ≥8 verified citations, zero causal language for observational designs.
* `synthesis_poster`: ≥2 figures ≥300 DPI, ≤6 citations, font ≥24pt,
  one headline message.
* `synthesis_dashboard`: single-file offline HTML, sortable tables,
  lightbox gallery, light/dark, print stylesheet, ≥3 sections.
* `synthesis_grant`: Specific Aims ≤500 words (1 page), Approach ≥1500
  words, every Aim has milestones + pitfalls + alternatives, ≥15
  citations.

The AI is told not to mark synthesis "done" until the quality bar passes.

### Can I customise the look of outputs?

* **Paper** — pick `target_venue: journal | conference | preprint |
  dissertation | report` in researcher_config; each gets its own structure
  + length band.
* **Poster** — pick `poster.audience: academic_conference | symposium |
  industry | teaching` (asked at synthesis time).
* **Dashboard** — pick `audience: academic | executive | technical |
  teaching` (asked at synthesis time).
* **Grant** — pick `funder: nih_r01 | nsf | wellcome | erc | doe |
  industry`.
* **Report** — pick `audience: internal_team | client | technical_audit |
  policy_brief`.

For deeper customisation (cover page templates, journal-specific BibTeX
style), edit `synthesis/paper.tex` (or `poster.tex`) after generation and
re-compile with `tool_latex_compile`.

---

## State / robustness

### My workspace looks broken.

> "Run `tool_workspace_repair`."

It detects missing directories, corrupted state ledgers, stale path entries,
and broken symlinks; recreates / regenerates / backs up corrupted files.
NEVER deletes — corrupted state ledgers are renamed
`state_ledger.broken_<timestamp>.json` before a fresh default is written.

### I accidentally deleted some files. Can I get them back?

`sys_checkpoint_list` shows snapshots; `sys_checkpoint_rollback <id>`
restores. Research OS auto-snapshots at every protocol boundary.

### The AI is hallucinating tool names that don't exist.

The dispatcher accepts three forms (`sys_state_get`, `sys.state.get`,
legacy `sys_guidance_get`) and rewrites them to canonical underscore form.
If the AI still hits "Unknown tool", ask: "Call `sys_protocol_list` and
tell me what's actually available." All tool names are listed.

### The AI keeps re-doing what I already did.

`sys_protocol_next` checks BOTH the execution log AND on-disk artifacts.
If both say "this stage is done", the AI moves on. If you migrated the
project from outside Research OS, `tool_workspace_repair` rebuilds the
expected metadata from the files already present.

---

## Power users

### Can I add a custom protocol?

Yes. Drop a YAML at
`src/research_os/protocols/<category>/<my_protocol>.yaml` (see
[CONTRIBUTING.md](../CONTRIBUTING.md) for the schema). The loader picks
it up automatically; no code changes needed. The standard
`protocol_completion` step is injected by the loader.

### Can I add a custom MCP tool?

Yes. Implement the function in `src/research_os/tools/actions/<group>/<file>.py`,
add a JSON schema to `TOOL_DEFINITIONS` in `src/research_os/server.py`, register
the handler in `_HANDLERS`. Reference the new tool from at least one
protocol so it doesn't become dead code. See
[CONTRIBUTING.md](../CONTRIBUTING.md).

### Can I run Research OS without the synthesis features?

Yes. Skip `pip install 'research-os[viz,literature]'`. Synthesis tools
that need an absent dependency will return a clear error explaining what
to install. The core pipeline works without any optional extras.

### My research has multiple papers / projects sharing data. Tips?

Two patterns:

* **Symlink shared data**: `ln -s /path/to/shared/raw inputs/raw_data`.
  Research OS treats it as immutable, same as a local copy.
* **Separate Research OS workspaces per paper**: each gets its own
  `inputs/`, `workspace/`, `synthesis/`. Use `inputs/context/` to drop
  pointers to the sibling project.

---

## Anything else?

Open an issue: <https://github.com/VibhavSetlur/Research-OS/issues>.
