# Research OS — maintainer guide

This is the running guide for people working on the Research OS repo
itself. New-contributor onboarding lives in
[`../CONTRIBUTING.md`](../CONTRIBUTING.md); the long-form release
runbook lives in [RELEASING.md](RELEASING.md); the API contract for
integrators lives in [CONTRACT.md](CONTRACT.md). This page is the
glue: what the maintainer day looks like, in what order, with the
why.

---

## Release flow at a glance

Three branches:

```
main ← protected, every commit a release candidate.
└── dev ← integration. PRs land here first.
    └── feat/<slug> | fix/<slug> | docs/<slug>
```

Releases go `dev → main` via PR, then a tag on `main` triggers PyPI +
GitHub Release. The detailed runbook is in
[RELEASING.md](RELEASING.md) — re-read it before every cut, because
the version number lives in **three files** (`pyproject.toml`,
`src/research_os/__init__.py`, `CITATION.cff`) and CI fails loudly
if any of the three drift.

The single most common release bug is "I bumped on dev and merged to
main but forgot to tag." **The tag is the release.** No tag → no PyPI
upload → no GitHub Release.

For MAJOR or MINOR cuts, also bump the `version:` field on every
protocol YAML to match. Reuse the one-liner in `RELEASING.md` rather
than hand-editing 118 files.

---

## CI overview

Five workflows in `.github/workflows/`:

* **`test.yml`** — runs on every push and PR. Pytest (≈900 tests),
  `ruff check`, `python scripts/preflight.py` (22 wiring checks).
  This is the release gate. Don't bypass it.
* **`codeql.yml`** — static analysis on PRs to main.
* **`stress.yml`** — long-running multi-domain stress scenarios.
  Triggered on demand + nightly on main.
* **`publish.yml`** — fires on tag push (`v*`). Builds the wheel +
  sdist, runs `twine check`, uploads to PyPI via trusted publishing.
* **`release.yml`** — fires on tag push. Extracts the matching
  `## [<version>]` section from `CHANGELOG.md` and posts it as the
  GitHub Release body. If the section is missing, the release body
  is an ugly fallback — always edit `CHANGELOG.md` **before** tagging.

Branch protection on `main` requires `test.yml`, `codeql.yml`, and
the publish dry-run to be green before a PR can merge.

---

## Audit cadence

Research OS earns its keep by auditing the work product the AI
generates. Three audit families ship in `src/research_os/tools/actions/audit/`:

* **Synthesis audits** — block bad papers / posters / slides before
  they ship. Run on every `tool_synthesize` call.
* **Prose-quality audits** — wording, AI-tone smell, hedge density.
  Run as a phase of synthesis.
* **Coherence audits** — version drift between scripts, outputs, and
  conclusions. Runs on `tool_audit_version_coherence`.

Per release line, run the full multi-domain stress audit (humanities
+ wet-lab + qualitative + engineering + theory-math) before tagging a
MINOR. Per dev cycle (≈ weekly), run `tool_audit_full` against the
test fixture projects under `tmp/` and triage any new findings.
Findings are persisted under `workspace/logs/audit_findings/` and
schema-validated against
`src/research_os/schemas/audit_finding.schema.json` — the same schema
external integrators consume (see [CONTRACT.md](CONTRACT.md) § A.2).

---

## Plugin discovery internals

The pack subsystem lives in `src/research_os/plugins/`:

* `pack_api.py` — `PackRegistration`, `PackTool`, `register_tool`
  decorator. **This is the stable surface** pack authors import.
  Anything they import from outside this module is fair game to
  break in a MINOR; anything they import from here is contract.
* `loader.py` — walks the `research_os.protocol_pack` Python
  entry-point group at server startup, validates namespacing
  (`tool_<pack>_*`, `<pack>/<...>`), and merges the pack into core
  `TOOL_DEFINITIONS`, `_HANDLERS`, the router index, and the
  protocol loader's directory list.

Per-pack errors are **isolated**: a misbehaving pack logs its
traceback to `workspace/logs/pack_errors.log`, gets skipped, and
the server keeps booting. `sys_packs_installed` surfaces both the
successful packs and the errors so the AI can tell the researcher
which pack failed.

Five packs ship in-tree (`research_os_humanities`,
`research_os_qualitative`, `research_os_theory_math`,
`research_os_wet_lab`, `research_os_engineering`) and six adapter
packs ship in-tree (`slurm`, `nextflow`, `snakemake`, `cytoscape`,
`redcap`, `synapse`). They register through the same entry-point
mechanism as external packs — they're worked examples, not
hard-coded specials.

---

## SemVer gating

Decision table (full contract: [CONTRACT.md](CONTRACT.md)):

| Change | Bump |
|---|---|
| Bug fix / doc fix / dep bump / internal refactor | **PATCH** |
| New protocol, new tool, new optional config field, new audit gate | **MINOR** |
| Renamed tool, removed protocol, changed required input schema, workspace-layout change, new `intent_class` value | **MAJOR** |

When unsure between PATCH and MINOR: anything that adds **new trigger
phrases, new protocols, or new tools** is MINOR. Pure fixes + docs
are PATCH. When unsure between MINOR and MAJOR: ask yourself "would
an existing client that pins on `~=X.Y` still work?" If no — MAJOR.

The `CONTRACT.md` STABLE section is itself part of the contract —
changing it requires a MAJOR bump.

---

## CHANGELOG conventions

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com).
Newest version at the top. Each release has one section:

```
## [1.11.0] — 2026-06-03

### Added
- New protocol `engineering/benchmark` …
- New tool `tool_engineering_benchmark_run` …

### Improved
- `tool_route` …

### Fixed
- `sys_state_get` …

### Bumped
- `mcp` 1.4.0 → 1.5.0
```

Rules:

* **Never edit a published section.** The published section is what
  was actually released — if you got it wrong, add a `### Fixed` in
  the next PATCH instead.
* `## [Unreleased]` is allowed as a working buffer; the release PR
  renames it to the version being cut.
* The release workflow (`release.yml`) extracts the matching section
  as the GitHub Release body. Missing or malformed section → ugly
  fallback. Always preview the section locally with
  `git diff CHANGELOG.md` before merging the release PR.

---

## Common foot-guns

* **Bumping `pyproject.toml` without `__init__.py` + `CITATION.cff`.**
  Test in `tests/unit/test_version_consistency.py` will fail; fix all
  three at once.
* **Touching `_router_index.yaml` without bumping its `version:` at
  the top.** Readers (and the router cache) can't tell the index
  changed.
* **Adding a protocol but forgetting the router-index entry.**
  Preflight fails. Always run `python scripts/preflight.py` after
  protocol edits.
* **Forgetting to activate the conda env.** System Python doesn't
  have `pytest`/`ruff`. Always
  `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os`.
* **Calling a real LLM from inside an RO tool.** RO doesn't manage
  models. Audits use deterministic checks; the IDE drives the LLM.
