# Research-OS v2.0.0 — Handoff Plan

This document lists the 14 phases of the v2.0.0 release. v1.11.0 already
shipped phases 1, 2, and 3 from the original release spec; phases below
pick up from there.

Baseline at start of v2.0.0 work: version 1.11.0, 118 protocols, 344
tools, server.py 6813 lines, 5 in-tree packs (humanities, qualitative,
theory_math, wet_lab, engineering), 6 adapter packs (slurm, synapse,
cytoscape, nextflow, redcap, snakemake).

## Phases

1. Setup — version bump to 2.0.0-dev, CHANGELOG scaffold, handoff dir.
2. Server decomposition — split server.py into smaller modules.
3. Tool registry consolidation — single source of truth for tool defs.
4. Protocol loader hardening — strict validation + better errors.
5. Router v2 — multi-intent dispatch, ambiguity surface, transcript log.
6. Audit gate framework — pluggable gates with structured findings.
7. Provenance sidecar v2 — schema bump, signed manifests.
8. Adapter pack contract — formal interface, lifecycle hooks.
9. Pack discovery + install UX — `research-os pack add/remove/list`.
10. Wizard v2 — IDE-agnostic templates, per-pack onboarding.
11. Docs overhaul — researcher guide rewrite, migration guide for v1 → v2.
12. Test coverage push — integration tests for every pack, e2e smoke.
13. Release prep — version bump 2.0.0-dev → 2.0.0, CHANGELOG finalize.
14. Tag + publish — runbook only, no auto-push.
