# FAQ

Common questions, grouped by topic. New here? Skim **Setup** and
**Workflow** first. For worked examples see [SCENARIOS.md](SCENARIOS.md);
for the "I want to X → what to say" map, see [USE_CASES.md](USE_CASES.md).

Jump to: [Setup](#setup) · [Workflow](#workflow) ·
[Skills & the Hermes layer](#skills--the-hermes-layer) ·
[Trust & provenance](#trust--provenance) · [Outputs](#outputs) ·
[State / robustness](#state--robustness) · [Power users](#power-users) ·
[Version history](#version-history-in-depth)

---

## Setup

### Do I need a Claude / OpenAI / Anthropic API key?

**No.** Research OS does NOT manage LLM provider keys. Your AI client
(Claude Code, OpenCode, Antigravity, Cursor, Claude Desktop, VS Code,
Windsurf, Continue, Aider, …) owns model access. Research OS sits behind
it as an MCP server.

The only optional credentials are for literature / web search providers
(Semantic Scholar, PubMed, Crossref, Firecrawl, SerpAPI). Public
endpoints work without keys — keys just raise rate limits.

### The Research OS tools don't show up in my IDE chat. Why?

Almost always: **you didn't restart the IDE after `research-os init .`**.
The MCP server only loads on a fresh IDE session. Fully restart the IDE
(or reload the window), then check the MCP panel for `research-os
connected`. If `research-os doctor` reports the IDE *is* wired but the
tools still don't appear, the restart is the missing step.

### I ran `research-os init` and it made a nested folder. What happened?

`research-os init my-project` creates a *new* `my-project/` inside the
current directory. To scaffold the folder you're **already in**, use the
dot: `research-os init .`. Easiest habit: `cd` into the project folder
first, then `research-os init .`.

### Does it work with `<my-AI-IDE>`?

If your IDE speaks the Model Context Protocol (MCP) — yes. `research-os
init .` drops a pre-wired config for Claude Code, OpenCode, Antigravity,
Cursor, Claude Desktop, VS Code, Windsurf, Continue, and Aider. For
anything else, point the IDE's system prompt at the `AGENTS.md` at the
project root and configure the MCP server manually (see
[SETUP.md § 4](SETUP.md)).

### Can I install now and start a project later?

Yes. `pip install` puts `research-os` on your PATH; nothing happens until
you `cd` somewhere and run `research-os init .`.

### Does it work on a shared server / HPC cluster?

Yes. Set `runtime.shared_server: true` in `inputs/researcher_config.yaml`
so the AI warns before allocating heavy resources. For long jobs, use the
per-project daemon: `research-os daemon run -- <cmd>`, `daemon docker
IMAGE -- <cmd>`, or `daemon submit job.sbatch` for SLURM. Every run is
journaled and provenanced and survives the IDE closing.

### How do I add an API key later?

Edit `inputs/researcher_config.yaml` under the `api_keys:` block (created
`chmod 600` so secrets aren't world-readable):

```yaml
api_keys:
  semantic_scholar: "s2_..."
  serpapi: "..."
  firecrawl: "fc_..."
```

Leave any key blank — Research OS falls back to keyless public endpoints
(Crossref, PubMed, arXiv). No restart needed; the server re-reads the
file each session.

### How do I add another AI IDE later?

```bash
research-os ide add <name>     # e.g. windsurf, continue, aider
research-os ide list           # see what's wired
research-os ide remove <name>  # tear out one config
```

This drops only the new IDE's MCP config; nothing else changes.

---

## Workflow

### I just want to dump files and have the AI figure it out. Possible?

Yes. After `research-os init .`, drop your data / PDFs / notes into
`inputs/raw_data` / `inputs/literature` / `inputs/context`, then say
**"onboard me"** or **"fill out the intake."** `tool_intake_autofill`
reads everything, classifies the domain, extracts your question +
hypotheses, and writes them into `inputs/intake.md` and the project's
`docs/`. (Domain / question / hypotheses are intentionally *not* in
`researcher_config.yaml` — that file is reserved for fields you actively
choose.)

### Why onboard before analyzing — can't I just say "fit a model"?

You can, but you'll get a more robust project if onboarding runs first.
On a fresh project the AI walks `session_boot` → `project_startup`: scan
`inputs/`, fill + freshness-check the intake, bring external data in with
provenance, profile the data, snapshot the environment, do a **mandatory
literature pass**, and ground the framing. A few minutes here is the
difference between a defensible project and a messy one. Say *"onboard
me"* and let it walk the steps.

### Do I have to use the default pipeline?

No. It's the DEFAULT path the AI recommends. Override any time: *"iterate
with me, what's next?"* (`guidance/iterative_planning`), *"write the
paper"* (jumps to synthesis), *"this isn't working"*
(`guidance/dead_end_routing`).

### My AI keeps writing 400-line mega-scripts. How do I stop that?

The `guidance/analysis_plan` protocol (loaded on every analysis step)
forbids it. Any non-trivial scope (>3 methods, multiple subgroups, or
custom pipelines) must be broken into atomic versioned sub-tasks *before*
code is written. If the AI ignores it, set `interaction.autonomy_level:
manual` for a few turns and redirect when it tries to mega-shot.

### The AI keeps hallucinating citations. Help.

By construction, **citations in final synthesis outputs cannot be
hallucinated.** `tool_citations_verify` pulls every citation from real
providers (Crossref / Semantic Scholar / PubMed / arXiv), drops any entry
without a DOI/URL, and verifies online. `tool_synthesis_check` surfaces
any unresolved citation key before render so the AI fixes the source.

### What if the right tool is a website / GUI / paid service the AI can't run?

The AI writes a `WORKSHEET.md` in the current experiment folder
explaining exactly what you must do (URL, inputs, parameters, where to
drop outputs), then resumes from the dropped outputs once you signal
completion.

### Can I run multiple parallel experiments?

Yes. Multiple active numbered paths coexist (e.g. `02_logistic_baseline`
*and* `03_random_forest`). Use `tool_branch_recommendation` if you're not
sure whether to branch or extend.

### Where do my files go for a corpus / transcripts / a theorem?

The wizard creates `inputs/{raw_data, literature, context}/`. Some packs
expect more:

- **Text corpus (humanities)** — `inputs/corpus/`; close-reading passages
  in `inputs/textual/passages/`.
- **Interview transcripts** — `inputs/raw_data/` is fine; IRB / guides in
  `inputs/context/`.
- **A theorem to prove** — write `inputs/preliminaries.md` defining every
  object in your claim. **Hard prerequisite** of
  `theory_math/method/proof_strategy_selection`; the protocol blocks
  without it.
- **Code under benchmark** — `inputs/context/code/` (not your analysis
  scripts).

Just `mkdir` whichever you need — the immutability guarantee only applies
to `inputs/raw_data/` and `inputs/literature/`.

### Does Research OS support theory / humanities / qualitative work?

Yes — dedicated packs for each:

- **theory_math** — conjecture → strategy → proof verification → lemma
  library → dependency graph → formal check (Lean/Coq) → theory paper.
  Uses `inputs/preliminaries.md`. Trigger with "prove this", "I have a
  conjecture", "proof verification".
- **humanities** — archival research, source provenance, close + distant
  reading, scholarly edition. Every interpretive claim is anchored to a
  line/page, every passage edition-pinned. Drop your corpus in
  `inputs/corpus/`. (Foundational monographs without Crossref DOIs may
  flag on verify — drop the PDF in `inputs/literature/` and the verifier
  accepts the local copy.)
- **qualitative** — `methodology/qualitative_research` →
  `coding_scheme_development` → `qualitative_quality_audit` →
  `audit_and_validation` → `synthesis_paper` (+ dashboard). Sample-size
  justification routes through **saturation evidence**, not power
  analysis — so a qualitative step is audited for saturation, not a
  power calculation.

### How do I get the AI to do exactly what I want?

Describe the goal in plain language. You don't call tools or memorize
protocol names; `tool_route` matches your **intent**, not keywords, so
"head-to-head", "bake-off", and "horse race" all land on the same place.
For reliable phrasings, what each request does behind the scenes, and the
verification steps that confirm it actually happened, see
[PROMPTING.md](PROMPTING.md), the prompt phrasebook. The short version:
name the audience and the one takeaway for any deliverable, say "just
this step" vs "the whole project" for scope, and ask for verification
("ground every number", "check the citations resolve") to trigger the
real gates.

### Can I containerize just one step instead of the whole project?

Yes. Say *"dockerize this step."* The AI pins that step's exact packages
and writes a step-scoped `workspace/<step>/environment/Dockerfile` built
from that step's own requirements, so the single step is independently
reproducible. Its scripts, data, and pinned environment travel together,
and `docker build` from the step folder reproduces just that step, not
the whole project. Say "for the whole project" to get a project-level
image at `environment/Dockerfile` instead.

---

## Skills & the Hermes layer

### How does the AI know my field's specific methods?

Through **skills** — on-demand know-how documents in the open Agent Skills
standard that the AI loads only when relevant. Research OS pulls from
three sources through one index:

| Source | What | How to get it |
|---|---|---|
| **Hermes skills** | The agent's own library at `~/.hermes/skills` | Ships with Hermes |
| **K-Dense science pack** | 140 MIT-licensed deep-science skills (bulk-rnaseq, rdkit, experimental-design, …) | `research-os skills add-science-pack` |
| **Native Agent Skills** | Any external Agent-Skills library | Point your IDE at the `skills/` dir |

**You don't pick skills by hand.** On a fresh project,
`sys_boot.recommended_skills` matches your domain + workspace mode and
surfaces the right skills (e.g. genomics → biopython, gget, bulk-rnaseq);
the AI loads them *before* starting, so it uses your field's methods with
validated parameters instead of guessing. Run `research-os skills
list-science` for the domain → skill map. The system also learns —
distilling durable lessons from your projects into new skills.

### What is the "Hermes layer" and do I need it?

Research OS gives the AI **structure and tools**. The optional **Hermes
layer** adds **know-how and stamina**: reusable skills, memory across
projects, and the ability to drive long autonomous loops (plan deeply →
execute toward a goal → score → re-plan), pulling relevant skills each
cycle and notifying you at decision points. You don't need it to use
Research OS, but it makes the AI sharper in your field. Wire it with
`research-os hermes add`; docs at
<https://hermes-agent.nousresearch.com>.

---

## Trust & provenance

The three questions a reviewer (or your PI, or future-you) will ask.

### How do I know the numbers in my writeup are real, not made up?

**Claim grounding.** When you write up results, the AI extracts every
quantitative claim in the prose and checks each one traces to a real
artifact on disk — a table cell, a figure's underlying data, a recorded
statistic. A number that can't be traced is flagged *before* a reviewer
sees it. The habit that makes this work: write prose *from* your
artifacts, then ground — don't paste numbers from memory. Say *"ground
every claim in the results section."*

### Is this result stale? I changed an input — is the figure still valid?

**Provenance re-hash.** Every output produced through a step gets a
`.prov.json` sidecar recording its exact inputs (by content hash), the
script, the parameters, the seed, the software versions, and the git
commit. The provenance-integrity check **re-hashes those recorded inputs**
and flags any output whose input has changed since it was built — a
*stale* result. Run it before any milestone: *"check provenance integrity
across the project."* A step won't quietly "complete" over a stale output,
and the optional daemon watches for this automatically.

### Can I show a reviewer exactly how a figure was made?

Yes — that's what the sidecar is for. Open the figure's `.prov.json`: it
names the **script**, the **inputs (with hashes)**, the **seed**, and the
**environment**. Combined with the **versioned scripts** (`_v1 → _v2 →
_v3`) and `conclusions.md`, the whole path from data to figure is on disk
— not in your memory. Hand the reviewer the `.prov.json` plus the versioned
script and the figure is fully reconstructible.

### What's the single best habit for trustworthy results?

Let the AI do real computation **through steps and scripts**, not as
one-off math in chat. Only work that runs through a step leaves a
provenance sidecar, gets claim-grounded, and shows up in the audit trail.
Improvised chat math is invisible to all three guards. See
[HOW_IT_WORKS.md](HOW_IT_WORKS.md) for the full picture.

---

## Outputs

### What exactly does Research OS produce — a finished PDF?

Research OS provides **structure, not a fixed template.** A synthesis
protocol assembles a content-grounded **outline** of your deliverable —
the right sections, the figures and numbers to feature, the narrative
order — tailored to your audience and venue, for *you* to render. It does
not hand you a canned palette to fill in. It will author the source for a
render and tell you how to compile it, but the value is the
*structure assembled from your grounded results*, not a one-click PDF.

### Are dashboards / posters / papers actually publication-quality?

They aim to be. Each synthesis protocol declares explicit `quality_bar`
minimums the AI must clear before marking the work "done" — e.g. a paper:
abstract 200–300 words, methods ≥400 words, ≥1 figure, ≥8 verified
citations, zero causal language for observational designs; a poster: ≥2
figures ≥300 DPI, font ≥24 pt, one headline message.

### Can I customise the look of outputs?

Yes — via audience/venue knobs the AI asks about at synthesis time:
`target_venue` for papers (journal / conference / preprint /
dissertation / report), `poster.audience`, dashboard `audience`, grant
`funder`, report `audience`. Each shapes the structure and length band.
You then render the assembled source.

### Can I run Research OS without the synthesis features?

Yes. The whole analysis pipeline — data, figures, stats, literature
search — ships in the base install and works on its own. The only
synthesis step with an external dependency is PDF compilation
(`tool_typst_compile` needs the `typst` CLI). If it's absent the AI still
authors the source and tells you how to install `typst` — nothing
silently fails.

---

## State / robustness

### My workspace looks broken.

> "Run `tool_workspace_repair`."

It detects missing directories, corrupted state ledgers, stale path
entries, and broken symlinks; recreates / regenerates / backs up
corrupted files. **It never deletes** — corrupted ledgers are renamed
`*.broken_<timestamp>.json` before a fresh default is written.

### I accidentally deleted files. Can I get them back?

`sys_checkpoint_list` shows snapshots; `sys_checkpoint_rollback <id>`
restores. Research OS auto-snapshots at every protocol boundary.

### The AI is hallucinating tool names that don't exist.

The dispatcher accepts three forms (`sys_state_get`, `sys.state.get`,
legacy `sys_state_summary`) and rewrites to canonical underscore form. If
it still hits "Unknown tool", ask: *"call `sys_protocol_list` and tell me
what's actually available."*

### The AI keeps re-doing what I already did.

`sys_protocol_next` checks both the execution log AND on-disk artifacts.
If both say a stage is done, it moves on. If you migrated the project from
outside Research OS, `tool_workspace_repair` rebuilds the expected
metadata from the files already present.

---

## Power users

### Can I add a custom protocol?

Yes. Drop a YAML at
`src/research_os/protocols/<category>/<my_protocol>.yaml` (schema in
[CONTRIBUTING.md](../CONTRIBUTING.md)). The loader picks it up
automatically; no code changes needed.

### Can I add a custom MCP tool?

Yes. Implement the function under `src/research_os/tools/actions/`, add a
JSON schema to `TOOL_DEFINITIONS`, and register the handler in the
matching `HANDLERS` map. Reference it from at least one protocol so it
isn't dead code. See [CONTRIBUTING.md](../CONTRIBUTING.md).

### My research has multiple papers sharing data. Tips?

Two patterns:

- **Symlink shared data:** `ln -s /path/to/shared/raw inputs/raw_data`.
  Research OS treats it as immutable, same as a local copy.
- **Separate workspaces per paper:** each gets its own `inputs/`,
  `workspace/`, `synthesis/`. Use `inputs/context/` for pointers to the
  sibling project.

---

## Version history (in depth)

> Historical reference — these explain features from earlier major
> versions (still current behaviour unless a later CHANGELOG entry says
> otherwise). For the live release history, see
> [`../CHANGELOG.md`](../CHANGELOG.md).

### What changed in v2.0.0?

The headline change was a **tool surface consolidation (344 → 144 live)**
plus a flip of `sys_protocol_get` to default `format='summary'`. Both were
breaking on paper but **every legacy tool name still dispatches via
alias** — most projects upgraded with zero call-site edits. After `pip
install --upgrade research-os`, run **`research-os doctor`** for an install
+ workspace health report (exit 0 = pass, 1 = warn, 2 = fail). Other
highlights: `tool_route.recommended_action` + `why_matched`, audit-as-data
(the `.audit_findings.jsonl` ledger), `tier:` + `scope_tags` on every
protocol, and the `tool_protocols_list` / `tool_tools_list` discovery
tools. v2.3.0 then handed synthesis authoring to the AI directly (the
rigid auto-generators were retired in favour of content-grounded
structure the AI assembles).

### What is `research-os doctor`?

A CLI sub-command that runs 20+ install + workspace health checks (python
version, conda env, package-version coherence, pack registration,
embeddings freshness, IDE wiring, disk usage, git cleanliness, …). Exit
0 = pass, 1 = warn-only, 2 = fail.

```bash
research-os doctor                    # full report
research-os doctor --json             # machine-readable
research-os doctor --verbose          # fix hints for passing checks too
research-os doctor --workspace-only   # skip install checks
research-os doctor --workspace .      # explicit workspace path
```

### Why did `sys_protocol_get` get cheaper?

The schema default flipped from `format='full'` to `format='summary'` in
v2.0.0 — the biggest token-cost win in the Phase 15a baseline. Summary is
~3K chars vs ~12–25K for the full body; a `_load_hint` field guides the AI
to drill into `format='step' | 'full' | 'lean' | 'dryrun'` only when
needed. Old callers that passed `format='full'` still work.

### What is the audit findings ledger?

Every audit emits a JSON companion plus rows in the append-only ledger at
`workspace/logs/.audit_findings.jsonl`. Each row carries `id` (stable
UUIDv5), `audit_name`, `severity` (`block | warn | info`), `dimension`,
`evidence_paths`, `suggested_fix`, `ro_version`, `generated_at`. Query
with `tool_audit_findings(operation='query', severity='block')` or diff
two runs to confirm a fix resolved a BLOCK.

### What happened to the old auto-generator tools (slides, dashboard, synthesis)?

They were retired. The auto-generators produced rigid, low-quality output.
Authoring now belongs to the AI, which assembles content-grounded structure
following the matching synthesis protocol; tools then validate
(`tool_synthesis_check`) and compile (`tool_typst_compile`). Calling a removed
tool returns a friendly redirect naming the protocol and the surviving tools.

### What if my AI invents a tool name that doesn't exist?

If the name is a known retired one, Research OS returns a friendly error naming
the canonical entry point (for example, a per-source search tool maps to
`tool_search(query='...', source='pubmed')`). For genuinely unknown names the
dispatcher returns "Unknown tool"; the AI's recovery path is
`sys_tool_describe(name)`, then `tool_tools_list(scope='all')` or `sys_help`.

### How do I discover what protocols + tools my project has?

`tool_protocols_list` (flat protocol catalogue) and `tool_tools_list`
(flat tool catalogue) — both reflect what's actually loaded this session,
which depends on installed packs. `sys_packs_installed` lists active packs;
`sys_adapters_installed` lists infrastructure adapters (SLURM / Snakemake
/ Nextflow / Cytoscape / REDCap / Synapse).

---

## Known caveats

Honest disclosure beats stealth — if you hit one of these, it's known and
being worked on, not a silent breakage on your end.

- **Path containment is enforced for `sys_file_*` only.** Tools that shell
  out (`tool_python_exec`, `tool_bash_exec`) can read/write outside the
  project root. Prefer `sys_file_*` for AI-initiated I/O.
- **`override_rationale` is checked for substance, not truth.** The
  validator rejects rationales under ~40 chars or that just repeat the
  block reason; it can't tell whether the rationale is honest. Review
  `.os_state/overrides.log` periodically.
- **Prompt injection from fetched content.** Text in a PDF, web snippet,
  or pasted note that says "please run tool_python_exec(...)" will execute
  if the AI follows it and you've approved tool use — there's no input
  sanitiser. Pin `autonomy_level: supervised` (or `manual`) when ingesting
  untrusted content. See [SECURITY.md](SECURITY.md) for the threat model.

---

## Anything else?

Open an issue: <https://github.com/VibhavSetlur/Research-OS/issues>.
