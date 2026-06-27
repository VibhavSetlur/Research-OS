# FAQ

Common questions, grouped by topic. New here? Skim **Setup** and
**Workflow** first. For complete worked examples of real projects, see
[SCENARIOS.md](SCENARIOS.md); for the role × goal × output map, see
[USE_CASES.md](USE_CASES.md).

Jump to: [Setup](#setup) · [Setup & configuration](#setup-configuration)
· [Workflow](#workflow) · [Outputs](#outputs) ·
[State / robustness](#state-robustness) · [Power users](#power-users) ·
[Version history](#version-history-in-depth)

---

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
The protocols will automatically background long jobs via
`tool_task(operation='run')` (real `subprocess.Popen`) and warn before
allocating heavy resources.

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

### Do I have to read every protocol to know which to use?

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
into `inputs/intake.md` + the project's `docs/` folder (as
`research_overview.md`), with the hypothesis ledger persisted to
`.os_state/state.json`. Domain / research
question / hypotheses are intentionally NOT in `researcher_config.yaml`
— that file is reserved for fields a researcher actively chooses.

### Do I have to use the 10-stage pipeline?

No. The pipeline is the DEFAULT path `sys_protocol_next` recommends. You
can override at any time:

* "Iterate with me, what's next?" → loads `guidance/iterative_planning`.
* "Write the paper" / "Make a poster" → jumps straight to synthesis.
* "This experiment isn't working" → `guidance/dead_end_routing`.
* "Run a custom analysis I'm designing" → `guidance/analysis_plan` with
  `mem_log(kind='methods', implementation='custom', ...)`.

### My AI keeps writing 400-line mega-scripts. How do I stop that?

The `guidance/analysis_plan` protocol (loaded on every analysis step)
forbids this. It mandates `tool_plan_step` for any non-trivial scope (>3
methods OR multiple subgroups OR custom pipelines), which forces a
breakdown into atomic versioned sub-tasks BEFORE any code is written.

If the AI ignores it, set `interaction.autonomy_level: manual` for a few
turns — you'll see exactly when it tries to mega-shot and can redirect.

### How does the AI know my field's specific methods?

Through **skills** — on-demand know-how documents in the open agentskills.io
standard that the AI loads when it needs them. It pulls from three sources via
one index: its own (Nous) skills, the **K-Dense science pack** (140 deep
science skills — install with `research-os skills add-science-pack`), and any
external Agent Skills library. On a fresh project, `sys_boot` names the skills
that match your domain + mode (e.g. genomics → biopython, gget, bulk-rnaseq)
and the AI loads them before starting, so it uses *your field's* methods with
validated parameters instead of guessing. Run `research-os skills list-science`
to see the domain → skill map. The system also learns: it distills lessons from
your projects into new skills and carries the durable ones forward.

### The AI keeps hallucinating citations. Help.

By construction, **citations in final synthesis outputs cannot be
hallucinated**. `tool_citations_verify` pulls every citation from real
providers (Crossref / Semantic Scholar / PubMed / arXiv), drops any
entry without a DOI/URL, and verifies online. `tool_synthesis_check`
surfaces any unresolved citation key in `paper.typ` / `essay.typ`
before compile so the AI fixes the source.

### What if the right tool is a website / GUI / paid service the AI can't run?

Call `tool_external_tool_instructions`. It writes a `WORKSHEET.md` in the
current experiment folder explaining exactly what the researcher must do
(URL, inputs, parameters, where to drop outputs). The AI then resumes from
the dropped outputs once the researcher signals completion.

### Can I run multiple parallel experiments?

Yes. `sys_path(operation='create')` adds the next numbered folder.
Multiple active paths coexist (e.g. `02_logistic_baseline` AND
`03_random_forest`). Use `tool_branch_recommendation` if you're not
sure whether to branch or extend the current path.

(The legacy `sys_path_create` / `sys_path_abandon` / `sys_path_list` names were hard-removed
in v2.0.0 — call `sys_path(operation=...)` with the matching
`operation`. The `_REMOVED_TOOLS` error envelope names the canonical
entry point if a stale caller hits the old name.)

### How do I track multiple hypotheses?

`mem_hypothesis_add` to register one (auto-assigned H1, H2, … or you
pick the ID), `mem_log(kind='hypothesis', hypothesis_id='H01',
status='supported', evidence='...')` to log evidence + change status
(testing / supported / refuted / inconclusive), `mem_hypothesis_list`
to see the ledger. Every experiment step is asked which hypothesis IDs
it touches. (The legacy `mem_hypothesis_update` name was hard-removed
in v2.0.0 — call `mem_log(kind='hypothesis', ...)`.)

### I have a text corpus / interview transcripts / a theorem to prove. Where do my files go?

The wizard creates `inputs/{raw_data, literature, context}/` by
default. Some packs and protocols expect additional subfolders:

* **Text corpus (humanities)** — `inputs/corpus/` for the full corpus,
  `inputs/textual/passages/` for hand-picked close-reading passages
  with edition pins.
* **Interview transcripts (qualitative)** — `inputs/raw_data/` is
  fine. Drop IRB protocols and interview guides in
  `inputs/context/instruments/`.
* **A theorem to prove (theory_math)** — write
  `inputs/preliminaries.md` defining every object in your claim and
  citing key prior results. This is a **hard prerequisite** of
  `theory_math/method/proof_strategy_selection`; the protocol blocks
  if it's missing.
* **Code under benchmark (engineering)** — `inputs/context/code/` for
  the source you're measuring (not your analysis scripts). Keeping it
  here instead of `raw_data/` makes it editable so you can iterate on
  the implementation.

The full table is in [START.md § Bring in your project](START.md#bring-in-your-project--chat-or-files-1-min)
and [AI_GUIDE.md § inputs/ directory conventions](AI_GUIDE.md#inputs-directory-conventions-read-on-cold-start).
Just `mkdir` whichever subfolder you need; the immutability guarantee
only applies to `inputs/raw_data/` and `inputs/literature/`.

### Does Research OS support theory / pure-math projects?

Yes — there's a dedicated `theory_math` pack with 8 protocols
(conjecture tracking, proof strategy selection, proof verification
workflow, lemma library, theorem dependency graph, formal-check
decision, theory paper structure, citation chains for theory). The
trigger phrases that route into it include "prove this", "I have a
claim I need to prove", "proof verification", "theorem", and
"conjecture". The pack uses `inputs/preliminaries.md` instead of
`inputs/raw_data/` as the load-bearing input.

For the validated end-to-end recipe (conjecture → strategy → lemmas →
main theorem → theory paper → PDF), start by saying:

> "I have a conjecture: <statement>. Help me prove it and write it up
> as a theory paper."

### Does Research OS support humanities / literary / textual analysis?

Yes — there's a humanities pack with field-true protocols
(`archival_research`, `source_provenance`, `citation_chains`,
`digital_humanities_workflow`, `hermeneutic_method`,
`scholarly_edition`, `close_reading`, `distant_reading`). The pack
treats interpretive claims with the same
rigor as quantitative ones: every claim is anchored to a line/page
number, every passage is edition-pinned, every reading declares its
critical tradition, and every cluster requires a counter-pattern.

Drop your corpus in `inputs/corpus/` and your close-reading passages
in `inputs/textual/passages/`, then say:

> "I have <N> texts in inputs/ — test whether <stylistic claim>."

Note: foundational humanities monographs (Princeton UP, Cornell UP,
Oxford UP) often lack Crossref DOIs, so the citation-verify gate may
flag them on first pass. That's a known last-mile gap — drop the PDFs
in `inputs/literature/` and the verifier will accept the local copies.

### Does Research OS support qualitative / interview research?

Yes — `methodology/qualitative_research` is the entry point, and the
end-to-end chain is:

1. `methodology/qualitative_research` — interview protocol design,
   transcript ingestion, open + axial coding, theme synthesis,
   trustworthiness statement.
2. `methodology/coding_scheme_development` — codebook construction
   (inductive / deductive / hybrid).
3. `methodology/qualitative_quality_audit` — saturation evidence,
   reflexivity statement, intercoder agreement, member-checking,
   quote anonymisation, audit-trail check.
4. `audit/audit_and_validation` — master quality audit.
5. `synthesis/synthesis_paper` — IMRAD-flavoured paper assembly.
6. `synthesis/synthesis_dashboard` — story-mode dashboard.

Sample-size justification for qualitative work routes through
SATURATION evidence (Guest, Bunce, Johnson 2006), not power analysis.
Don't call `tool_audit_power` on a qualitative step — the right
answer is the saturation curve produced by
`qualitative_quality_audit::saturation_evidence_check`.

---

## Trust & provenance

### How do I know the numbers in my writeup are real, not made up?

When you write up results, **claim grounding** extracts every quantitative
claim in the prose and checks each one traces to a real artifact on disk — a
table cell, a figure's underlying data, a recorded statistic. A number that
can't be traced is flagged before a reviewer (or your PI) sees it. The rule
that makes this work: write the prose *from* your artifacts, then run
grounding — don't paste numbers from memory. Ask *"ground every claim in the
results section."*

### How do I know a result is still valid after I changed the input?

Every output the AI produces through a step gets a `.prov.json` sidecar
recording its exact inputs (by content hash), the script, the parameters, the
seed, the software versions, and the git commit. The **provenance-integrity
check** re-hashes those recorded inputs and flags any output whose input has
changed since it was built — a *stale* result. Run it before any milestone:
*"check provenance integrity across the project."* The optional daemon also
watches for this automatically, and a step won't quietly "complete" over a
stale output without telling you.

### What's the single best habit for trustworthy results?

Let the AI do real computation **through steps and scripts**, not as one-off
calculations in chat. Only work that runs through a step leaves a provenance
sidecar, gets claim-grounded, and shows up in the audit trail. Improvised
chat math is invisible to all three guards. See
[HOW_IT_WORKS.md](HOW_IT_WORKS.md) for the full picture of how provenance,
accuracy, and organization compound into a result you can defend.

### Can I show a reviewer exactly how a figure was made?

Yes — that's what the sidecar is for. Open the figure's `.prov.json`: it names
the script, the inputs (with hashes), the seed, and the environment. Combined
with the versioned scripts (`_v1 → _v2 → _v3`) and `conclusions.md`, the whole
path from data to figure is on disk, not in your memory.

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
legacy `sys_state_summary`) and rewrites them to canonical underscore form.
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
add a JSON schema to `TOOL_DEFINITIONS` in the matching
`src/research_os/server/tool_definitions/*.py` module, and register the
handler in the matching `src/research_os/server/handlers/*.py` module's
`HANDLERS` map. Reference the new tool from at least one protocol so it
doesn't become dead code. See
[CONTRIBUTING.md](../CONTRIBUTING.md).

### Can I run Research OS without the synthesis features?

Yes. The whole analysis pipeline — data, figures, stats, literature search —
ships in the base install and works on its own. The only synthesis step with
an external dependency is PDF compilation: `tool_typst_compile` needs the
`typst` CLI on your PATH. If it's absent, the AI still authors the `.typ`
source and tells you exactly how to install `typst` to render it — nothing
silently fails.

### My research has multiple papers / projects sharing data. Tips?

Two patterns:

* **Symlink shared data**: `ln -s /path/to/shared/raw inputs/raw_data`.
  Research OS treats it as immutable, same as a local copy.
* **Separate Research OS workspaces per paper**: each gets its own
  `inputs/`, `workspace/`, `synthesis/`. Use `inputs/context/` to drop
  pointers to the sibling project.

---

## Version history (in depth)

> Historical reference. These entries explain features introduced in
> earlier major versions (still current behaviour unless a later
> CHANGELOG entry says otherwise). For the live release history, see
> [`../CHANGELOG.md`](../CHANGELOG.md).

### What changed in v2.0.0?

The headline shape change was a **tool surface consolidation
(344 → 144 live)** plus a flip of `sys_protocol_get` to default
`format='summary'`. Both were breaking on paper but **every legacy
tool name still dispatches via alias** — most projects upgraded with
zero call-site edits. After `pip install --upgrade research-os`, run
**`research-os doctor`** for an install + workspace health report
(exit 0 = all pass, 1 = warn-only, 2 = fail). See `CHANGELOG.md [2.0.0]`
for the full upgrade recipe. Other v2.0.0 highlights: the MCP
`instructions` field on the initialize handshake (names the canonical
boot ritual), `tool_route.recommended_action` + `why_matched`,
audit-as-data (the `.audit_findings.jsonl` ledger), `tier:` +
`scope_tags` on every protocol, and the `tool_protocols_list` /
`tool_tools_list` discovery tools. v2.3.0 added AI-direct synthesis
authoring (the AI writes `synthesis/paper.typ` etc. directly; the rigid
auto-generators were retired).

## v2.0.0 — new features (in depth)

### What is `research-os doctor`?

A CLI sub-command introduced in v2.0.0 that runs 20+ install +
workspace health checks. Exit policy: 0 = all-pass, 1 = warn-only,
2 = fail. The first thing the v2 migration guide tells you to run
after `pip install --upgrade research-os`.

```bash
research-os doctor                    # full human-readable report
research-os doctor --json             # machine-readable
research-os doctor --verbose          # show fix hints for passing checks
research-os doctor --workspace-only   # skip install checks
research-os doctor --workspace .      # explicit workspace path
```

Checks include python version, conda env consistency, package version
coherence (`pyproject.toml` vs `__init__.py` vs `CITATION.cff`), pack
registration, embeddings freshness, IDE wiring, disk usage, git
cleanliness, etc.

### Why did `sys_protocol_get` get cheaper?

The schema default flipped from `format='full'` to `format='summary'`
in v2.0.0 — the single biggest token-cost win identified in the
Phase 15a baseline. Summary view is ~3K chars (~300 tokens) vs
~12-25K chars (1.5-3K tokens) for the full body. The response
payload now carries a `_load_hint` field guiding the AI to drill
into `format='step' | 'full' | 'lean' | 'dryrun'` only when needed.
Per-turn token cost is 5-10× cheaper.

Old callers that explicitly passed `format='full'` continue to work
unchanged. If your AI client honours MCP `inputSchema` defaults, it
sees the new default automatically.

### What is the audit findings ledger?

A new v2.0.0 surface that turns audit output into structured data.
Every audit emits a JSON companion alongside the Markdown report
and appends rows to the project-level append-only ledger at
`workspace/logs/.audit_findings.jsonl`. Each row carries `id` (stable
UUIDv5), `audit_name`, `severity` (`block | warn | info`),
`dimension`, `evidence_paths`, `suggested_fix`, `ro_version`,
`generated_at`.

Query with `tool_audit_findings`:

```python
# List current active blockers (latest snapshot per stable id)
tool_audit_findings(operation='query', severity='block')

# Filter by dimension + step
tool_audit_findings(
    operation='query',
    dimension='claims',
    step='03_de_analysis',
)

# Confirm a fix actually resolved a BLOCK finding between two runs
tool_audit_findings(
    operation='diff',
    timestamp_a='2026-06-05T10:00:00Z',
    timestamp_b='2026-06-06T15:30:00Z',
)
```

`tool_synthesis_check` surfaces unresolved BLOCKs in the ledger
as blockers on the AI's synthesis file; the AI fixes the source
.typ / .html before compiling.

### Where did tool_synthesize / tool_dashboard / tool_slides_create / tool_poster_create go? (removed)

Retired in v2.3.0. The auto-generators produced rigid, low-quality
output (the dashboard was a 3MB monolithic HTML; the paper was a
markdown intermediate, not a publishable artefact). v2.3.0 hands
authoring to the AI: write `synthesis/paper.typ` /
`synthesis/slides.typ` / `synthesis/poster.typ` /
`synthesis/dashboard.html` directly, following the matching
synthesis protocol. Tools validate (`tool_synthesis_check`) and
compile (`tool_typst_compile`).

Calling a removed tool returns a friendly redirect message naming
the protocol and the surviving tools. See CHANGELOG `[2.3.0]` for
the full migration.

### What is `tool_route.recommended_action`?

A new v2.0.0 field on the `tool_route` return envelope: a literal
next-call string the AI executes verbatim, e.g.
`sys_protocol_get(protocol_name='methodology/qualitative_research',
format='summary')`. Removes the "what do I call next" guess that
burned a turn in the v1 baseline. The router also returns
`why_matched` (semantic similarity score + matched triggers + tier)
and `tier` (one of `intake | plan | execute | ground | synthesize |
review | finalize`) so the AI can rank alternatives without
re-routing.

### My AI keeps calling the old `tool_audit_step_completeness`. Should I fix it?

Not urgent. The legacy name still dispatches via `_ALIASES` +
`_ALIAS_PARAM_INJECTION` through the v2.0.x runway — you'll see a
deprecation warning logged to `.os_state/deprecations.log` but
behaviour is identical. Sweep your call sites before v2.1.0 (the
hard-removal target). `tool_deprecations_summary` aggregates the log
for a quick view of which deprecated aliases your project still hits.

The canonical v2 name is `tool_audit(scope='step',
dimension='completeness')`. The full old → new mapping is at
`CHANGELOG.md [2.0.0]`.

### What if my AI invents a tool name that doesn't exist?

If the AI calls a name that's in `_REMOVED_TOOLS` (24 names
hard-removed in v2.0.0 — see Phase 14a in
`CHANGELOG.md [2.0.0]`), Research-OS returns
a friendly error naming the canonical v2 entry point. Example:

> `tool_search_pubmed` was renamed to `tool_search` in v1.6.1 and
> removed in v2.0.0; call `tool_search(query='...', source='pubmed')`
> instead.

For genuinely unknown names, the dispatcher returns "Unknown tool".
The AI's self-recovery path is: `sys_tool_describe(name)` first; if
that fails, `tool_tools_list(scope='all')` (or
`sys_semantic_tool_search`) to browse the catalogue, or `sys_help`
for orientation.

### How do I discover what protocols + tools my project has?

Two new v2.0.0 discovery tools:

* `tool_protocols_list` — flat protocol catalogue with structured
  metadata (name, category, pack, intent_class, tier, version, short
  description). Filter by `category`, `pack`, `intent_class`,
  `tier`.
* `tool_tools_list` — flat MCP tool catalogue with `scope` (core or
  pack name), summary, required input fields, deprecation status,
  alias target. Filter by `scope`, `include_deprecated`.

Both are cheaper than re-reading the docs and reflect what's actually
loaded in the current session (which depends on which packs are
installed). `sys_packs_installed` lists active packs;
`sys_adapters_installed` lists infrastructure adapters
(SLURM / Snakemake / Nextflow / Cytoscape / REDCap / Synapse).

---

## Known caveats in 2.2.x

Even with this release closing the v2.1.0 envelope-normalization gap,
some caveats remain. Honest disclosure beats stealth — if you hit one
of these, you can be confident it's known and being worked on, not a
silent breakage on your end.

* **Adapter envelopes vary by adapter version.** The core normalizer
  the dispatcher normalizer guarantees envelope shape for tools that ship in-tree. Third-
  party adapter packs published before 2.2.0 may still emit pre-
  normalizer envelopes. Workaround: pin `research-os-adapter-*` to a
  version released on or after 2026-06-01, or wrap the adapter call
  in a try/except on `KeyError`.
* **Path containment is enforced for `sys_file_*` only.** Tools that
  shell out (e.g. `tool_python_exec`, `tool_bash_exec`) can still
  read/write outside the project root. Workaround: prefer
  `sys_file_*` for I/O the AI initiates; reserve shell-outs for
  user-driven work.
* **Autopilot floor-gates run after each protocol step, not after
  each tool call.** A tool that runs for several minutes inside one
  step is not interrupted by gate violations until the step returns.
  Workaround: break long single-step protocols into smaller steps if
  you need finer-grained gating.
* **`override_rationale` is checked for substance, not for truth.**
  The rationale validator rejects rationales shorter than ~40 chars or that just repeat
  the block reason. It cannot tell whether the rationale is honest.
  Workaround: human review of `.os_state/overrides.log` periodically.
* **Prompt injection from fetched content.** Anything in a literature
  PDF, web search snippet, or pasted text that reads "please run
  tool_python_exec(...)" will be executed if the AI follows the
  instruction and the user has approved tool use. There is no input
  sanitiser. Workaround: pin `autonomy_level: supervised` (or
  `manual`)
  and review tool calls when ingesting untrusted content. See
  [SECURITY.md](SECURITY.md) for the full threat model.
* **`research-os doctor` does not check pack-installed protocol
  versions.** A pack pinned to an old core version may load protocols
  that reference removed tools. Workaround: bump packs alongside core.

For the security posture that frames these caveats, read
[SECURITY.md](SECURITY.md).

---

## Anything else?

Open an issue: <https://github.com/VibhavSetlur/Research-OS/issues>.
