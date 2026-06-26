---
name: research-os
description: >-
  Drive a Research-OS project: rigorous, reproducible computational
  research with adaptive autonomy and a self-improving skill registry.
  Use whenever the user does computational research, literature review,
  data analysis, experiment design, or writes a scientific paper or
  technical report and a Research-OS workspace is (or should be) present.
---

# Research-OS

Research-OS (RO) is an MCP server that turns a general agent into a
disciplined research collaborator. It ships a protocol router, rigor and
reproducibility audits, a synthesis/typesetting pipeline, and a
self-improving skill registry. When this skill is active and the RO MCP
server is connected, prefer RO tools over ad-hoc shell work.

**Division of labor — read this first.** RO does NOT try to be the brain.
You (Hermes) are the agent: you reason, you pull and apply skills, you
learn the user. RO provides the *organization in the research chaos* — the
protocols that scaffold sound reasoning, the gates that enforce rigor, and
the ledger that records provenance. The best results come from using BOTH:
your skills carry the domain how-to, RO's protocols govern whether it's the
right method and demand the evidence.

## Use your Nous skill ecosystem — RO tells you WHEN, your skills carry HOW

When a request needs domain or tool know-how, pull the matching Nous skill
from your skill ecosystem (the bioinformatics / drug-discovery /
domain-intel / OSINT and other libraries Nous has built, plus any you've
learned) and apply it WITHIN the RO protocol the router returns:

- The RO protocol says WHAT to think about, WHAT to ground, and WHAT to
  record. Your skill says HOW to actually run the tool / library / pipeline.
- Concretely: `tool_route` returns the method-level protocol (e.g. an
  RNA-seq differential-expression workflow); you then pull your
  bioinformatics skill for the exact DESeq2 invocation + flags, run it, and
  let the RO protocol enforce the grounding, the figure provenance, and the
  reproducibility audit around it.
- Prefer a relevant Nous skill over re-deriving tool usage from scratch or a
  generic web search — the skill is validated know-how. RO's
  `methodology/tool_discovery` protocol explicitly says: consult your skill
  layer FIRST, then apply RO's reasoning to confirm fit and record why.
- If no skill covers the task, do the work, then run RO's self-improving
  registry (`distill`) so the lesson becomes a reusable skill next time.

## When to use

- The user is doing computational research, a literature review, data
  analysis, experiment design, or writing a paper/report.
- There is a Research-OS workspace nearby (an `inputs/` dir with
  `researcher_config.yaml`, plus `.os_state/`). If not, offer to scaffold
  one with `research-os init`.

## The workspace contract (do not violate)

- `inputs/` is the immutable source of truth. `inputs/raw_data/` and
  `inputs/literature/` are soft-locked (only overwrite with explicit
  intent; `literature_index.yaml` is never overwritten). The rest of
  `inputs/` is AI-writable but is the project's ground truth: edit
  deliberately.
- `synthesis/` holds generated deliverables. Force-overwriting an
  EXISTING synthesis file is a gated action (it auto-archives the prior
  version first).
- `.os_state/` is RO-managed state: never hand-edit it.

## Autonomy (adaptive)

RO runs adaptively. It proceeds automatically on cheap, reversible
actions and pauses for confirmation only on actions that are
irreversible, expensive, or carry external/real-money cost — and it
tightens or relaxes that bar as the project earns rigor (trust score):

- strict (new / messy project): every floor gate fires.
- normal: irreversible + expensive actions gate.
- light (rigorous, trusted project): only truly irreversible / paid
  actions gate (path abandon, package install, paid tools, checkpoint
  rollback).

When RO returns an `autopilot_gate_blocked` envelope, surface the one
decision it needs, then re-issue the call with `confirmed=true` once the
user agrees.

## Workflow

1. Route first. Send the user's request through the RO protocol router;
   it returns the matching protocol and a decomposition. Follow the
   protocol as a reasoning scaffold, not a rigid script.
2. Ground claims. Use the grounding/verification tools before asserting
   results; cite sources via the bibliography tooling.
3. Audit before declaring done. Run the reproducibility / completeness
   audits the protocol calls for.
4. Synthesize. Write deliverables into `synthesis/`; compile with the
   typst pipeline when a PDF is requested.
5. Learn. After a milestone, run the self-improving skill registry:
   `distill` crystallizes recurring lessons into reusable SKILL.md cards,
   then `promote` lifts durable, cross-project lessons into your profile
   so RO gets better at *this user's* work over time.

## Working autonomously toward a goal

When the user wants you to keep building toward a goal with minimal
hand-holding (deep iterative research, an overnight build, an unattended
loop), run a disciplined loop — never an open-ended spin:

1. **Plan, then roadmap.** Use the deep-planning protocols to decompose the
   goal into a branchable roadmap before executing. Capture it durably so you
   (or a fresh session) can resume against it.
2. **Read the daemon's notes first, every turn.** `sys_boot` surfaces
   `daemon_notes` — the daemon's startup self-check (structure drift,
   interrupted runs, unframed intake). Address any BLOCK item before building
   on the project. This is how nothing gets lost across sessions.
3. **Execute one step, record the result.** Submit long compute through the
   daemon (it bounds + journals + can resume it). Ground every claim.
4. **Judge honestly with `tool_judge_score`.** Score the work (dimensions +
   limitations + improvements + verdict). `iterate`/`redo` → re-plan and
   continue; `ship` → the goal may be met, verify and stop the loop. The
   scorecard is what keeps the loop from stopping too early OR spinning
   forever.
5. **Re-plan from evidence.** Reshape the roadmap and open/close analysis
   paths (branches) based on what the results showed. The plan is a living
   thing, not frozen.
6. **Improve yourself as you go.** When you hit a recurring lesson mid-loop,
   `distill` it into a skill immediately so the rest of the loop (and the next
   project) benefits — self-improvement is part of the loop, not just an
   end-of-milestone chore.

Unattended autonomy never bypasses the kernel: consent + staleness gates still
hold, and you must not self-approve an irreversible/expensive action. If a gate
blocks while the user is away, the daemon pages them — let it.

Opt-in continuation: if the user set `daemon.continue_command`, the daemon will
re-prompt you to continue after a long result lands. It's hop-limited, so a
goal can't loop forever; when you judge the goal met, call the daemon to stop
the loop.

## If the RO server is not connected

Tell the user to run `research-os hermes add` (wires the MCP server +
this skill into `~/.hermes/config.yaml`) and restart Hermes. Then
`research-os hermes status` confirms the wiring.
