# The best Research-OS setup for your project

Research-OS is the **rigor + provenance + enforcement** layer for a research
project. It is deliberately not the agent, the model, or the editor. You get the
most out of it by pairing it with a capable **AI agent layer** above it and a
few **complementary MCP servers** beside it.

This guide gives concrete, copy-pasteable recommendations. The
`agent_setup` protocol walks you through tailoring it to your specific project;
this doc is the quick reference.

---

## The shape of a great setup

```
You ── AI agent layer (persistent memory · skills · self-improvement)
          │  drives the work, learns you + the project
          ▼
      Research-OS (MCP)  +  complementary MCP servers
          │  protocols · gates · ledger · synthesis        live docs · web · domain APIs
          ▼
      Your project workspace (inputs · workspace · synthesis)
```

Two ideas do all the work:

1. **The agent layer is the brain; RO is the organization.** RO doesn't try to
   reason for you — it turns soft, trusted prose into hard, verified structure
   (every number grounded, every step reproducible, every gate enforced). The
   agent reasons, pulls skills, and learns your conventions. RO keeps it honest.
2. **MCP servers compose.** RO is one server; run several. RO governs *whether*
   a method is sound and *demands the evidence*; other servers supply the *how*
   and the *live facts*.

---

## 1. Pick the agent layer

The agent layer should have, ideally, all of: **persistent memory** across
sessions, a **skill ecosystem** it can pull from and add to, **MCP support**,
and a **self-improvement loop** that turns recurring lessons into reusable
skills.

**Hermes** (Nous Research, <https://hermes-agent.nousresearch.com>) is the
reference fit — it has all four, RO ships a first-class integration, and it runs
above whatever model you prefer (no provider lock-in). It's the smoothest path,
and the one this project recommends.

Any MCP-capable client works too (Claude Code, Cursor, Codex, Antigravity,
Windsurf) — you just lean more on RO's own mechanisms (its skill registry,
`agent_notes`, protocols) for the capabilities the client lacks. A chat-only /
non-MCP setup works through the `research-os` CLI; RO's guidance still applies,
the agent just can't call RO tools directly.

### Wire RO into it

```bash
# Hermes (recommended) — registers the RO MCP server + installs the RO skill
research-os hermes add
research-os hermes status      # confirm, then restart Hermes

# Any other MCP client — drops per-IDE rules + MCP config
research-os ide add claude-code      # or: cursor / codex / antigravity / windsurf
```

Wire **only** the client(s) you actually use — extra configs are clutter.

---

## 2. Stack complementary MCP servers

RO + the right neighbors is where the setup gets powerful. Reason about what
your work needs; these are examples, not a mandate:

| Need | Server | Why it pairs well with RO |
|---|---|---|
| Current library / API docs | **context7** (or any live-docs MCP) | The agent pulls CURRENT signatures instead of hallucinating stale ones — huge for the **tool-build mode** and any coding-heavy analysis. |
| Literature + data discovery | a web / search MCP | Finds papers + datasets; RO grounds whatever comes back. |
| Domain actions | a field-specific MCP (bioinformatics, chem, data warehouse) | Domain how-to; RO protocols govern method choice + reproducibility around it. |

For **Hermes**, add MCP servers per its docs
(<https://hermes-agent.nousresearch.com/docs>). For another MCP client, add them
in that client's MCP config next to the RO server.

The division of labor never changes: **RO decides whether a method is sound and
demands the evidence; the other servers + the agent's skills supply the how and
the live facts.**

---

## 2b. Bring in domain science skills (the capability layer)

Research OS gives the AI the rigorous **workflow** — framing, provenance,
grounding, audits. It does not, by itself, know how to run a bulk-RNA-seq
pipeline, design a fractional-factorial experiment, or dock a ligand. That
**domain capability** comes from skills.

Install the community **K-Dense scientific-agent-skills** library — 140
MIT-licensed science skills in the open Agent-Skills standard (the same
standard Hermes and the per-IDE rules already use):

```bash
research-os skills add-science-pack        # clone + wire into Hermes
research-os skills list-science            # see the domain → skill map
```

This clones the library to a shared dir and registers it into Hermes
`skills.external_dirs`, so Hermes loads the right skill on demand alongside its
own + RO's. IDEs on the Agent-Skills standard can point at the same `skills/`
dir. RO's **`recommended_skills`** (surfaced by `sys_boot` on a fresh project)
names the specific skills that match your domain + mode — e.g.:

| Your project | Skills RO pulls |
|---|---|
| clinical | literature-review · experimental-design · statistical-power · scikit-survival |
| genomics | biopython · gget · bulk-rnaseq · pydeseq2 · scanpy |
| chemistry / drug discovery | rdkit · deepchem · diffdock · medchem |
| ML / NLP | scikit-learn · pytorch-lightning · transformers · shap |

**The split to remember:** Research OS = *how to do research right*
(provenance, accuracy, organization); science skills = *how to do this
field's methods*. Together the AI has both — which is the whole point.

---

## 3. Tailor RO to THIS project

A generic agent is worse than a tailored one. Set these in
`inputs/researcher_config.yaml` (RO reads them every session via `sys_boot`):

```yaml
ai:
  model_profile: medium        # match your model class — sizes protocol loads + steps/turn
interaction:
  autonomy_level: adaptive     # flows on cheap/reversible work, pauses on irreversible/expensive
  agent_notes: ""              # standing project preferences the agent must obey
research_goal:
  output_types: [paper]        # so synthesis builds the right deliverables, nothing extra
  target_venue: ""
runtime:
  compute_environment: conda   # conda | docker | native | venv
  shared_server: false         # true on a shared HPC node — bounds every run, no Docker assumption
  resource_budget:             # the hard ceiling per run (the dynamic limiter scales DOWN from here)
    memory_mb: 0               # 0 = uncapped ceiling; dynamic budgeting uses live free-RAM headroom
  dynamic_resources:
    enabled: true              # scale a run's memory to live host headroom (multi-gig on idle, backs off on busy)
    mem_fraction: 0.80         # max share of currently-free RAM a run may claim
    mem_reserve_mb: 2048       # always held back for other users
```

As you correct the agent, record the lesson with `sys_config(operation='note')`
— that's the learn-the-user loop. Where the agent layer has its own memory
(Hermes), durable cross-project facts live there; the project contract lives in
`researcher_config`. Keep both in sync.

---

## 4. Turn on the daemon for long / unattended work

The optional daemon is the execution + enforcement kernel. Turn it on when you
run long jobs or want unattended progress:

```bash
research-os daemon start
```

What it gives you:

- **Long jobs survive disconnect** — submit a multi-hour run, close your laptop,
  it keeps going and is journaled the whole way.
- **Dynamic, safe resource limits** — runs scale to live host headroom (big on
  an idle node, automatically smaller on a busy shared one), never starving
  other users; the declared ceiling is never exceeded.
- **Resumable runs** — if the box reboots mid-run, the daemon marks it
  interrupted, tells you, and `resume_run` continues it (checkpoint-aware jobs
  pick up where they left off via `RO_CHECKPOINT_DIR`).
- **Startup self-check** — on boot the daemon inspects the project and leaves AI
  notes (`.os_state/daemon_notes.md`) that `sys_boot` surfaces, so structure
  problems get fixed before you build on them.
- **Unattended safety** — consent + staleness gates hold even with no human
  present; an autonomous agent can't self-approve or ship stale results.
- **Autonomous continuation (opt-in)** — set `daemon.continue_command` to your
  agent and, after a long result lands, the daemon re-prompts it to continue
  toward your goal, hop-limited so it can never loop forever.

---

## 5. Recommended stacks by project type

**Data analysis (Python/R/Julia), solo researcher**
Hermes + RO + context7. Daemon on if any step runs more than a minute. Notebook
mode if you work in notebooks; numbered-step mode otherwise.

**Tool / method building**
Hermes + RO + context7 (live docs matter most here). Use the tool-build mode
(`describe a tool → plan → build → improve from results → version`), the inner
git repo for versioning + rollback, and `tool_judge_score` to gate "good enough."

**Shared HPC, long compute**
Hermes + RO, daemon on, `runtime.shared_server: true`, dynamic resources on.
Submit jobs through the daemon so they're bounded, journaled, and resumable.
Wire `notify_command` so you're paged when results land or a gate blocks.

**Bringing an existing messy project in**
Start with the `organize_existing_project` protocol: `tool_migrate_audit` →
review the plan → `tool_migrate_apply` (copy-only, your original untouched) →
`tool_structure_audit` to confirm it's sound. Then set up the agent layer as
above.

---

## Verify it works

One round-trip proves the wiring: ask the agent to route a request
(`tool_route`), read project state (`sys_boot`), and confirm the workspace
contract is respected. Record your chosen setup (agent layer, wired clients,
model profile) so a collaborator can reproduce it.

The throughline: **the agent layer + its skills make the setup capable and
self-improving; RO's protocols keep it rigorous and reproducible. The best
research happens when both are on.**
