# Research OS — documentation

This page routes by audience. Pick the line that matches who you are; follow it to the doc that does the work. CHANGELOG.md at the repo root has the full release history.

---

## For researchers

You're using Research OS on your own research project.

Start at [**START.md**](START.md) — install, first project, cheatsheet (~15 minutes). Then keep [**RESEARCHER_GUIDE.md**](RESEARCHER_GUIDE.md) open as you work — the full workflow guide with mental model, every protocol, real session transcripts, and troubleshooting.

Supporting:

- [USE_CASES.md](USE_CASES.md) — "I want to write a paper / build a poster / reproduce a result" → which protocol fires.
- [SETUP.md](SETUP.md) — per-IDE MCP wiring, troubleshooting installs.
- [FAQ.md](FAQ.md) — common questions.
- [CLI.md](CLI.md) — every `research-os` CLI sub-command.
- [SHARING.md](SHARING.md) — how to hand off a workspace to a collaborator.

---

## For AI agents + plugin authors

You're either the model driving an MCP session, or you're shipping a domain pack.

**AI agents:** start at [**AI_GUIDE.md**](AI_GUIDE.md) — the operating manual for the AI on the other side of the MCP wire. At runtime, prefer `sys_help` and `sys_tool_describe` over the docs — they reflect what's actually installed.

**Plugin authors:** start at [**PLUGIN_AUTHORING.md**](PLUGIN_AUTHORING.md) — pack layout, the `PackRegistration` dataclass, the `@register_tool` decorator, router-entry conventions, a worked example. The in-tree packs under `src/research_os_<pack>/` are working templates.

Shared supporting docs:

- [TOOLS.md](TOOLS.md) — full tool catalogue.
- [PROTOCOLS.md](PROTOCOLS.md) — every protocol, when each fires, quality bars enforced.
- [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — the scaffold-not-script principle behind every protocol.
- [PAPER_PIPELINE.md](PAPER_PIPELINE.md) — the canonical `paper.md` → `paper.typ`/`paper.tex` → `paper.pdf` flow.
- [VENUE_TEMPLATES.md](VENUE_TEMPLATES.md) — venue-specific configuration.
- [ADAPTERS.md](ADAPTERS.md) — how the six adapter packs (`slurm`, `nextflow`, `snakemake`, `cytoscape`, `redcap`, `synapse`) bridge to external systems.
- [RELIABILITY.md](RELIABILITY.md) — the audit + test posture.

---

## For maintainers + integrators

You work on this repo, or you're embedding Research OS in something else.

**Maintainers:** start at [**MAINTAINER_GUIDE.md**](MAINTAINER_GUIDE.md) — release flow, CI overview, audit cadence, plugin-discovery internals, SemVer gating, CHANGELOG conventions. Then [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the contributor workflow and [RELEASING.md](RELEASING.md) for the long-form release runbook.

**Integrators:** start at [**INTEGRATION.md**](INTEGRATION.md) — programmatic API for embedding RO (import paths, MCP transport, headless invocation), with a working code snippet. Then [**CONTRACT.md**](CONTRACT.md) — which surfaces are stable enough to pin against.

Shared supporting docs:

- [`../CHANGELOG.md`](../CHANGELOG.md) — release history.
- [ROADMAP.md](ROADMAP.md) — what's coming.
