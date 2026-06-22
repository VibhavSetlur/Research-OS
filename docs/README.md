# Research OS — documentation

This page routes by audience. CHANGELOG.md at the repo root has the full release history.

---

## For researchers

You're using Research OS on your own research project.

Start at [**START.md**](START.md) — install, first project, cheatsheet (~15 minutes). Then keep [**RESEARCHER_GUIDE.md**](RESEARCHER_GUIDE.md) open as you work — the full workflow guide.

New here and want to see what a real project looks like? Read [**SCENARIOS.md**](SCENARIOS.md) — seven complete worked examples (messy CSV → paper, reproducing a paper, prepping an R01, benchmarking your own tool, interview transcripts → publication), with the exact prompts and what lands on disk.

Supporting:

- [SCENARIOS.md](SCENARIOS.md) — seven end-to-end worked examples: a named researcher, real data, the words they typed, what Research OS produced.
- [GLOSSARY.md](GLOSSARY.md) — the vocabulary: step, path, PATH container, plan.md, conclusions.md, the data folders, the literature corpus, audit.md, and more.
- [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) — the canonical directory layout: the safety backbone (`.os_state`, `inputs/`, `workspace/`, …) and what each workspace mode adds. The single source of truth for what lives where.
- [USE_CASES.md](USE_CASES.md) — "I want to write a paper / build a poster / reproduce a result" → which protocol fires.
- [TOOL_BUILDER.md](TOOL_BUILDER.md) — building software, not analysing data? The **tool_build** workspace mode: spec → implement → test → ship.
- [SETUP.md](SETUP.md) — per-IDE MCP wiring, troubleshooting installs.
- [FAQ.md](FAQ.md) — common questions.
- [CLI.md](CLI.md) — every `research-os` CLI sub-command.
- [SHARING.md](SHARING.md) — how to hand off a workspace to a collaborator.

---

## For AI agents + plugin authors

**AI agents:** start at [**AI_GUIDE.md**](AI_GUIDE.md). At runtime, prefer `sys_help` and `sys_tool_describe` over the docs — they reflect what's actually installed.

**Plugin authors:** start at [**PLUGIN_AUTHORING.md**](PLUGIN_AUTHORING.md). The in-tree packs under `src/research_os_<pack>/` are working templates.

Shared:

- [TOOLS.md](TOOLS.md) — full tool catalogue.
- [PROTOCOLS.md](PROTOCOLS.md) — every protocol, when each fires, quality bars enforced.
- [PROTOCOL_DOCTRINE.md](PROTOCOL_DOCTRINE.md) — the scaffold-not-script principle behind every protocol.
- [RELIABILITY.md](RELIABILITY.md) — audit + test posture (auto-generated).

---

## For maintainers + integrators

- [**CONTRACT.md**](CONTRACT.md) — which surfaces are stable enough to pin against. Read this if you're embedding RO programmatically.
- [**RELEASING.md**](RELEASING.md) — release runbook.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contributor workflow + branch model + test conventions.
- [`../CHANGELOG.md`](../CHANGELOG.md) — release history.
