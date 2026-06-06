# Research OS — documentation

This page is a **router**, not a content dump. Pick the line that
matches who you are; follow it to the doc that does the work.

---

## "I'm a researcher" — I want to use Research OS on my own project

Start at [**START.md**](START.md) — install, first project, cheatsheet
(~15 minutes). Then keep [**RESEARCHER_GUIDE.md**](RESEARCHER_GUIDE.md)
open as you work — it's the full workflow guide with mental model,
every protocol, real session transcripts, and troubleshooting.

Supporting docs:

* [USE_CASES.md](USE_CASES.md) — "I want to write a paper / build a
  poster / reproduce a result" → which protocol fires.
* [SETUP.md](SETUP.md) — per-IDE MCP wiring, troubleshooting installs.
* [FAQ.md](FAQ.md) — common questions.
* [CLI.md](CLI.md) — every `research-os` CLI sub-command.

---

## "I'm an AI agent" — I'm the model driving the MCP session

Start at [**AI_GUIDE.md**](AI_GUIDE.md) — the operating manual for the
AI on the other side of the MCP wire. Then [**TOOLS.md**](TOOLS.md) is
the full tool catalogue. At runtime, prefer the `sys_help` and
`sys_tool_describe` tools over reading the docs — they reflect what's
actually installed.

Supporting:

* [PROTOCOLS.md](PROTOCOLS.md) — every protocol, when each fires,
  quality bars enforced.
* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — the
  scaffold-not-script principle behind every protocol.

---

## "I'm a plugin author" — I want to ship a domain pack

Start at [**PLUGIN_AUTHORING.md**](PLUGIN_AUTHORING.md) — pack layout,
the `PackRegistration` dataclass, the `@register_tool` decorator,
router-entry conventions, and a worked example. The five in-tree
packs under `src/research_os_<pack>/` are full working templates.

Supporting:

* [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — protocols your pack
  ships must clear the same bar as core.
* [CONTRACT.md](CONTRACT.md) — pin against the right surface.

---

## "I'm a maintainer" — I work on this repo

Start at [**MAINTAINER_GUIDE.md**](MAINTAINER_GUIDE.md) — release
flow, CI overview, audit cadence, plugin-discovery internals, SemVer
gating, and CHANGELOG conventions. Then
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the contributor
workflow, and [RELEASING.md](RELEASING.md) for the long-form release
runbook.

Supporting:

* [`../CHANGELOG.md`](../CHANGELOG.md) — release history.
* [ROADMAP.md](ROADMAP.md) — what's coming.
* [RELIABILITY.md](RELIABILITY.md) — the audit + test posture.

---

## "I want to integrate" — embed Research OS in something else

Start at [**INTEGRATION.md**](INTEGRATION.md) — programmatic API for
embedding RO (import paths, MCP transport, headless invocation), with
a working code snippet. Then [**CONTRACT.md**](CONTRACT.md) — which
surfaces are stable enough to pin against.

Supporting:

* [ADAPTERS.md](ADAPTERS.md) — how the six adapter packs (`slurm`,
  `nextflow`, `snakemake`, `cytoscape`, `redcap`, `synapse`) bridge
  Research OS to external systems. Use these as integration templates.
* [SHARING.md](SHARING.md) — how researchers hand off a workspace
  (relevant if you're building a hand-off tool).
