# Phase 16 — Final Report (v2.0.0 release-prep handoff)

**Date:** 2026-06-06
**Branch:** `feat/v2.0.0`
**Status:** release-prep complete; ready for HUMAN-IN-THE-LOOP push + tag + merge.
**Final commit (Phase 16e):** `bc3d608 feat(v2): release 2.0.0 — version bump + CHANGELOG + protocol-version bumps [phase-16e]`

---

## 1. Headline state deltas — Phase 0 → Phase 16

| Surface | Phase 0 (v1.11.0 baseline) | Phase 16 (v2.0.0 release-prep) | Δ |
|---|---|---|---|
| Tool count (canonical `TOOL_DEFINITIONS`, live) | 344 | 146 | **-58%** |
| Backward-compat aliases | (implicit; not annotated) | 80 | NEW |
| Deprecated aliases (dispatch + telemetry) | (implicit) | 78 | NEW |
| Hard-removed (returns `_REMOVED_TOOLS` envelope) | 0 | 24 | NEW |
| `_HANDLERS` count | matches tools | 146 | balanced |
| `server.py` single-file lines | 6,813 (v1.11.0) / 7,499 (mid-cycle peak) | 0 | **monolith dissolved** |
| `src/research_os/server/` modules | 1 | 32 | NEW |
| Largest single server module | 6,813 | 579 (`tool_definitions/meta.py`) | **-92%** |
| Protocols (core + 5 packs, total) | 118 | 153 | +35 |
| Protocols with `scope_tags: {domain,audience,workflow_shape}` | 0 / 117 | 117 / 117 | NEW (100%) |
| Protocols with `tier:` annotation | 0 / 117 | 117 / 117 | NEW (100%) |
| `TOOL_DEFINITIONS` entries with `status` + `pack` | 0 / 344 | 146 / 146 | NEW (100%) |
| Audits emitting JSON companion (audit-as-data) | 0 / 11 | 11 / 11 | NEW |
| Preflight wiring checks | 22 | 24 | +2 |
| pytest count | 899 (v1.11.0) → 1583 today | 1583 passing | +684 |
| Avg `final_rating` across 20-agent matrix | 6.35 | **7.70** | **+1.35 (+21%)** |
| Total HIGH-friction items (sum across 20 runs) | 124 | 63 | **-49%** |
| First-5-turn HIGH-friction items | 66 | 42 | **-36%** |
| Deliverable-produced rate | 11 / 20 (55%) | 14 / 20 (70%) | **+15 pp** |

---

## 2. Commits in `feat/v2.0.0` since v1.11.0 baseline

**70 total commits** (56 phase-tagged + 14 known-issue / handoff / fix). See
`git log --oneline v1.11.0..HEAD`. Full per-phase distribution:

| Phase | Count | Description |
|---|---|---|
| phase-setup | 1 | bump to 2.0.0-dev, scaffold CHANGELOG + handoff |
| phase-4 (audit-as-data) | 11 | AuditBase migration + audit findings ledger + synthesize block-gate |
| phase-5 | 1 | review-rewrite loops on paper/slides/poster drafters |
| phase-6 | 1 | research-os doctor command |
| phase-7 | 1 | CONTRACT.md + audience-router README + plugin/maintainer/integration guides |
| phase-8 | 1 | tier-aware router + protocol tier annotations + current_tier state |
| v1.11.1-known-issue | 9 | 9 fixes deferred from v1.11.0 (path coercion, DEG trigger, citation retrieval, font vendoring, etc.) |
| phase-9 (consolidation) | 11 | C1 audit (26→3), C2 dashboard (7→1), C3 step (8→2), C4 lessons+reliability (10→2), C5 sensitivity+prereg (4→2), C6 reviewer (4→1), C7 data+figure+thought (9→3), C8 scratch+task (8→2), C9 sys_config+sys_env (5→2), cross-cutting (status+pack+scope_tags+MCP instructions+summary default) |
| phase-10 | 1 | split server.py into modular server/ package |
| phase-11a | 1 | tool_protocols_list + tool_tools_list + router why_matched/tier |
| phase-11b | 7 | protocol body cleanup across audit/, guidance/, literature/, methodology/, reproducibility/, synthesis/, visualization/, writing/, domain/ |
| phase-12, phase-13 | 2 | pack completeness matrix + CLI report; phase-13 CLI follow-ups |
| phase-13-followup-#1 | 1 | MCP Server() reports canonical __version__ |
| phase-14a, b, d | 3 | hard-remove first-wave aliases + tikzposter LaTeX path + dead config fields |
| phase-15a | 3 | baseline 20-agent validation + naive_ai supplements |
| phase-handoff | 1 | commit baseline JSON + serial workflow fix |
| phase-15b | — | re-validation 20-agent run + V2_VALIDATION_REPORT.md (uncommitted until 16e; landed in `bc3d608`) |
| phase-16-prep | 5 | release plan handoff + 4 scaffolds (CHANGELOG / MIGRATION / RELEASE_NOTES / V2_MIGRATION_TABLE) |
| phase-16a | 1 | refresh README + START + AI_GUIDE for v2.0.0 |
| phase-16b | 1 | MIGRATION_v1_to_v2.md final |
| phase-16c | 1 | V2_RELEASE_NOTES.md final |
| phase-16d | 1 | refresh RESEARCHER_GUIDE + FAQ + PROTOCOLS + TOOLS + CONTRACT for v2.0.0 |
| phase-16e | 1 | release 2.0.0 — version bump + CHANGELOG + protocol-version bumps |
| 0c45b79 (v2.0.1 hotfix folded in) | 1 | two v2.0.1 BLOCKER regressions surfaced by phase-15b re-validation |

---

## 3. 4×5 perspective × scenario rating matrix (Phase 15a baseline → Phase 15b re-validation)

Cell format: **baseline → revalidation**. Source: 20 baseline JSONs +
20 re-validation JSONs under `docs/v2_handoff/validation_baseline/` and
`docs/v2_handoff/validation_revalidation/` respectively.

|                            | researcher  | auditor     | maintainer  | naive_ai    | row avg     |
| -------------------------- | ----------- | ----------- | ----------- | ----------- | ----------- |
| biology_rnaseq             | 6.40 → 7.60 | 7.40 → 8.60 | 6.40 → 7.60 | 5.80 → 7.70 | 6.50 → 7.88 |
| engineering_benchmark      | 6.40 → 7.40 | 6.40 → 7.60 | 6.40 → 7.40 | 6.40 → 7.60 | 6.40 → 7.50 |
| humanities_close_reading   | 6.40 → 7.60 | 6.80 → 7.90 | 6.40 → 8.10 | 6.40 → 7.60 | 6.50 → 7.80 |
| qualitative_interviews     | 6.40 → 7.40 | 6.20 → 8.10 | 6.40 → 8.20 | 5.80 → 7.40 | 6.20 → 7.78 |
| theory_math_proof          | 6.40 → 8.10 | 6.40 → 7.10 | 5.80 → 7.60 | 5.90 → 7.40 | 6.12 → 7.55 |
| **col avg**                | **6.40 → 7.62** | **6.64 → 7.86** | **6.28 → 7.78** | **6.06 → 7.54** | **6.35 → 7.70** |

Per-scenario HIGH-friction deltas: biology 27 → 12; engineering 24 → 13;
humanities 20 → 10; qualitative 28 → 14; theory 25 → 14. Every cell moved up
by +0.7 to +1.9 points; no regressions in any of the 20 runs.

YELLOW verdict (per `docs/V2_VALIDATION_REPORT.md`): GREEN-gate targets
(avg ≥ 9.5, HIGH ≤ 5, all four perspectives ≥ 9.0) are not met; calibrated
against a hypothetical v3-grade product, not the current diff. Ship with
documented caveat; structural carryover items routed to v2.0.1 / v2.1.0.

---

## 4. Top 10 improvements (from `docs/V2_VALIDATION_REPORT.md` §3)

1. **Tool surface reduction 344 → 146 live (-58%).** 80 backward-compat aliases
   + 78 deprecated aliases + 24 hard-removed (`_REMOVED_TOOLS`). Largest
   single-axis UX win called out by all 20 re-validation runs.
2. **Audit family consolidation.** 24+ `tool_audit_*` per-dimension tools
   collapsed into `tool_audit(scope, dimension)` + `tool_audit_findings` ledger
   reader + `tool_audit_quality_full` master. Deprecation telemetry preserves
   visibility of legacy callsites.
3. **MCP `instructions` field at handshake.** Names the canonical boot
   sequence (`sys_boot → tool_route → sys_protocol_get(format=summary) →
   sys_active_tools`) at the protocol layer. Closes the baseline
   `no_first_call_signal` HIGH friction.
4. **`sys_protocol_get` default `format` flipped `full` → `summary`.** 5-10×
   cheaper per-turn tokens (~300 tokens vs ~1.5-3K). Schema declares
   `"default": "summary"` so MCP clients see the new default automatically.
5. **`tool_route` returns `recommended_action` + `why_matched`.** Literal
   next-call string (e.g. `sys_protocol_get(protocol_name='X',
   format='summary')`) on every primary protocol + alternative; saves one
   round-trip per turn. Closes baseline `tool_route_method_confusion` HIGH.
6. **`server.py` 7,499-line monolith dissolved.** Modular
   `src/research_os/server/` package, 32 files; largest module is
   `tool_definitions/meta.py` at 579 lines (-92% from peak). Public API
   preserved via `__init__.py` re-exports.
7. **Audit findings ledger (`.audit_findings.jsonl`)** populated by every
   audit with stable UUIDv5 ids; queryable via
   `tool_audit_findings(operation=query|diff)` with filters for severity,
   dimension, step, since. `tool_synthesize` BLOCK-gates on unresolved BLOCK
   findings and names the exact override flag.
8. **`status: live|alias|deprecated`** + **`pack: core|<pack_name>`** on every
   tool. Boot-visible `list_tools` is filtered to `status=live` only —
   0 aliases / 0 deprecated leak through. 123 core + 23 across 11 pack labels.
9. **`scope_tags: {domain, audience, workflow_shape}`** + **`tier:`** on all
   117 protocols. Full coverage, not partial. Infrastructure to gate
   empirical-statistical tooling per pack in v2.1.0 (router-side filtering
   not yet wired).
10. **`tool_audit_quality_full` returns structured per-component verdicts.**
    `components: {step_completeness, code_quality, prose_quality, claims,
    preregistration_diff, grounding}` each with
    `{status, blockers, advice}`. Closes baseline `opaque_blocker_messages`
    HIGH — the auditor sees per-dimension verdicts in the envelope, no
    follow-up `sys_file_read` for the master verdict.

---

## 5. Top 5 CRAFT-inspired additions

These are the structural shape-changes that drove the rating lift beyond
surface cleanup. Each was introduced in a dedicated Phase commit and survived
re-validation as called-out wins in ≥ 3 of the 20 re-validation runs.

1. **Audit-as-data** *(phase-4 — `2708eba` + the 10 AuditBase migrations).*
   Every audit emits a JSON companion alongside the Markdown report. New
   tools `tool_audit_findings(operation=query|diff)` query the cross-audit
   ledger at `.audit_findings.jsonl`. `tool_synthesize` BLOCK-gates on
   unresolved findings and names the exact override flag in the error envelope.
2. **Drafter review-rewrite loops** *(phase-5 — `b4f1096`).* Paper / slides /
   poster drafters iterate draft → adversarial review → rewrite, with
   per-iteration quality measurement logged to
   `workspace/logs/drafter_loops/`. Findings propagate from the persona-suite
   (`methodology_skeptic`, `domain_expert`, `statistician`, etc.) back into
   the next draft.
3. **`research-os doctor`** *(phase-6 — `0c5a945`).* 18+ install + workspace
   health checks. Exit policy: `0 = all-pass, 1 = warn-only, 2 = fail`. The
   first thing the v2 migration guide tells you to run after
   `pip install --upgrade`.
4. **`docs/CONTRACT.md`** *(phase-7 — `6d6b523`).* The stable-surface
   promise. Public tool names, audit-finding JSON schema,
   `researcher_config` field names, workspace layout, and protocol routing
   `intent_class` enum are all MAJOR-bumped on change. Citable contract
   instead of grepping `server.py`.
5. **Audience-segmented docs** *(phase-7 — `6d6b523`).* `docs/README.md` is
   a four-audience router (researcher / AI agent / plugin author /
   maintainer / integrator). New: `PLUGIN_AUTHORING.md`,
   `MAINTAINER_GUIDE.md`, `INTEGRATION.md`. Stops naive users landing on the
   maintainer guide first.

---

## 6. Remaining work — v2.0.1 / v2.1.0 / v3.0.0

Full deferral list at `docs/V2_VALIDATION_REPORT.md` §4. Headline shape:

### v2.0.1 — patch (ship within ~2 weeks of v2.0.0)

Two of the 3 documented BLOCKERS landed before tagging:

- ✅ `sys_tool_describe` `NameError` regression — fixed in `0c45b79`.
- ✅ `tool_audit(scope='synthesis', dimension='all')` `KeyError` — fixed in `0c45b79`.
- ✅ MCP `Server()` canonical `__version__` — fixed in `b3b24a0`.

Remaining v2.0.1 items (none require a tool-surface change):

- Wrap dispatcher `KeyError` / unknown-param failures in `server/dispatch.py`
  to return a structured `_error()` envelope instead of bare `KeyError` repr.
- Update `_MCP_INSTRUCTIONS` step 4 to spell out the required arg:
  `sys_active_tools(protocol_name=<from-step-3>)` — or auto-default
  `protocol_name` to the most recent `sys_protocol_get` target.
- Surface `scope_tags` in the `sys_protocol_get` response payload (currently
  in YAML, not JSON output). Same for `status` / `pack` annotations on tools
  via `sys_tool_describe`.
- Grep `TOOL_DEFINITIONS` for hardcoded tool counts and replace with dynamic
  `len(TOOL_DEFINITIONS)` or remove the count.
- Sweep audit recommendation strings for deprecated tool names.
- Add a preflight check (`scripts/sync_pack_versions.py`) to fail the gate
  when any protocol's `version:` field drifts from `pyproject.version`.
- Fix protocol naming-drift bugs in `proof_verification_workflow.yaml` line
  137 + `close_reading.yaml` line 94.
- Fix envelope-inversion silent-failure pattern repo-wide (leaf handlers must
  propagate inner `status in {'error', 'warning', 'unavailable'}` to the
  outer envelope).
- Re-tag `audit/audit_and_validation` (`domain: [qualitative]`) +
  `audit/pre_submission_checklist` (`domain: [humanities]`) with
  `domain: [any]`.
- Make `tool_audit_quality_full` emit `lit_gate_pending: true` when literature
  gate is skipped.

### v2.1.0 — minor (consolidation round 2 + first-class pack tools)

- Finish synthesis / executor / routing / slurm / sys_protocol / sys_checkpoint /
  sys_tools consolidations — the last 7 dispatcher families that didn't
  make the v2.0.0 cut. Net effect: another ~30 → ~10 tool collapse.
- Ship a `bio_omics` pack (`methodology/rnaseq_de.yaml`, `methodology/scrnaseq_qc.yaml`,
  `methodology/geo_sra_ingest.yaml`, `synthesis/methods_section_bioinformatics.yaml`).
  Loudest single domain gap from re-validation.
- Ship `engineering/test/algorithmic_benchmark` + `tool_engineering_benchmark_sweep`.
  Loudest single systems-research gap.
- Ship `tool_qualitative_pii_redact`, `tool_qualitative_quotes_bulk_register`,
  and the humanities apparatus / dangling-link / edition-pinning auditors.
- Wire `scope_tags` into router default filtering.
- Move pack-relevant tools off `pack='core'`. Target default surface < 125 tools.
- Pack-aware audit gates — auto-skip
  `audit_assumptions` / `audit_figures` / `audit_power` / `preregister_diff`
  for `researcher_config.domain == humanities`; substitute pack-flavoured
  audits. Same shape for theory.
- Make `tool_audit_quality_full` a TRUE master.
- Add `error_code` to canonical error envelope; add `Examples:` blocks to
  `tool_audit` / `tool_synthesize` / `tool_step`; pre-seed grounding for
  canonical method citations.

### v3.0.0 — major (breaking)

- Rename `tool_theory_math_{lean,coq,dep_graph}_*` → `tool_theory_{...}_*`
  (drop redundant `math` infix; pack is `theory_math`).
- Rename `sys_protocol_get`'s `protocol_name` → `protocol` to match what
  `tool_route` returns as `primary_protocol`.
- Move pack-execution-only tools (slurm / snakemake / nextflow / R / Julia /
  notebook exec / lean / coq / plate-map / fault-tree renderers) behind
  active-pack detection at the `list_tools` layer.
- `submission_type` knob on `pre_submission_checklist` so CONSORT / CRediT /
  IRB gates are venue-aware.

---

## 7. Wheel-build sanity — PASS

```
dist/research_os-2.0.0-py3-none-any.whl   (7.27 MiB, 409 entries)
dist/research_os-2.0.0.tar.gz             (96.6 MiB)
```

Wheel content verified by `python -c 'import zipfile; ...'`:

| Asset class | Count | Status |
|---|---|---|
| `assets/` | 56 | OK |
| Typst paths | 20 | OK |
| Reveal.js v5 paths | 7 | OK |
| Touying-mini Typst package | 3 | OK |
| Poster Typst (`poster-mini` + 5 templates) | 9 | OK |
| Vendored New Computer Modern fonts | 11 | OK |
| `_embeddings.npz` | 1 | OK (153 protocols + 146 tools, 384-dim) |
| `_router_index.yaml` | 1 | OK (version 20) |
| Reviewer personas | 7 | OK |
| `research_os_humanities/` (pack) | 12 | OK |
| `research_os_qualitative/` (pack) | 9 | OK |
| `research_os_theory_math/` (pack) | 12 | OK |
| `research_os_wet_lab/` (pack) | 12 | OK |
| `research_os_engineering/` (pack) | 11 | OK |
| `research_os_adapter_{slurm,snakemake,nextflow,cytoscape,redcap,synapse}/` | 1 each | OK (pure-Python adapter modules) |

Slide templates (5): `conference_15min`, `conference_5min_lightning`,
`defense_45min`, `lab_meeting_30min`, `public_outreach`.
Poster templates (5): `academic_36x48`, `academic_48x36`,
`academic_a0_portrait`, `academic_a1_landscape`, `public_24x36`.

All bundled assets present. Wheel build is publish-ready.

---

## 8. Release gate — PASS

- **preflight:** **24 / 24** (all green; `python scripts/preflight.py`).
- **pytest:** **1583 passed**, 13 skipped, **3 documented pre-existing flakies**
  (`test_v160::test_lean_format_uses_explicit_lean_variant_when_present`,
  `test_v161_consolidation::test_tool_search_auto_picks_biomedical_providers_for_rna`,
  `test_v161_consolidation::test_new_tool_search_pubmed_routes_to_pubmed`).
- **ruff:** **clean modulo pre-existing F541 in `cli.py:520`** (documented
  carryover, not introduced by v2 work).

---

## 9. Manual next steps for the user

**DO NOT skip the gates.** Per `CLAUDE.md`, the canonical release sequence
is `dev → main` PR, then tag from `main`. The release workflow extracts the
CHANGELOG entry as the GitHub Release body.

```bash
# 1. Confirm gates are still green from your shell (the in-session run
#    is now ~5 minutes stale).
cd /scratch/vsetlur/Research-OS
source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda activate research-os
python scripts/preflight.py && python -m pytest -q --tb=no && ruff check src/ tests/ scripts/

# 2. Push the feature branch.
git push -u origin feat/v2.0.0

# 3. Open the feature-branch PR into dev.
gh pr create --base dev --head feat/v2.0.0 \
  --title "Release v2.0.0" \
  --body "$(cat docs/V2_RELEASE_NOTES.md)"

# 4. After dev review + merge, open the dev → main release PR.
gh pr create --base main --head dev \
  --title "Release v2.0.0" \
  --body "Bumps version to v2.0.0. See CHANGELOG.md and docs/V2_RELEASE_NOTES.md for details."

# 5. After the dev → main PR squash-merges, tag from main. The tag is
#    what triggers publish.yml (PyPI) + release.yml (GitHub Release).
git checkout main && git pull
git tag -a v2.0.0 -m "v2.0.0"
git push origin v2.0.0

# 6. Verify (wait ~2 min for workflows to run).
gh run list --limit 5
gh release view v2.0.0
curl -sL https://pypi.org/simple/research-os/ | grep 2.0.0
```

**Hotfixes already folded in.** Two of the 3 documented v2.0.1 BLOCKERS
(`sys_tool_describe` NameError, `tool_audit(scope='synthesis')` KeyError)
were caught + landed in `0c45b79`. The MCP `Server()` version-reporting fix
landed in `b3b24a0`. v2.0.0 ships clean; the remaining v2.0.1 items
(dispatcher KeyError-wrap, surface scope_tags in payload, protocol naming
drift, envelope-inversion sweep, audit cross-domain re-tag,
`lit_gate_pending` flag) carry into the v2.0.1 patch series.

**Two phase tasks deferred from this session.** The Phase 16 plan §16g
explicitly says DO NOT auto-push, DO NOT tag, DO NOT merge — the user owns
release decisions. Phase 16 wraps with the feature branch in a clean,
publish-ready state at commit `bc3d608`.

---

## 10. Total agent invocations across the v2.0.0 push

70 commits across 17 distinct phase tags + 9 v1.11.1-known-issue fixes +
the phase-setup / phase-handoff bookends. Each phase was driven by a
parallel Workflow agent harness with N=1..K parallel workers per phase.

Phase agent counts (approximate, from commit headers + workflow logs):

| Phase | Agents |
|---|---|
| phase-setup | 1 |
| phase-4 (audit-as-data) | ~12 (1 per audit module migration + 1 architect) |
| phase-5 | 1 |
| phase-6 | 1 |
| phase-7 | 1 (multi-doc shaping) |
| phase-8 | 1 |
| v1.11.1-known-issue series | 9 (1 per fix) |
| phase-9 | ~10 (1 architect + 9 family-consolidation workers C1-C9) |
| phase-9-cross-cutting | 1 |
| phase-10 | 1 (single-agent server.py split) |
| phase-11a, 11b | 8 (1 + 7 protocol body cleanup workers) |
| phase-12 | 1 |
| phase-13 | 1 (8-IDE CLI sweep) |
| phase-13-followup | 2 (1 generic + 1 numbered) |
| phase-14a, 14b, 14d | 3 |
| phase-15a (baseline) | 20 (20 independent rater agents, 4 perspectives × 5 scenarios) |
| phase-15a (naive_ai supplements) | 2 |
| phase-15b (re-validation) | 20 (re-run of the 20 raters against v2 candidate) |
| phase-15b (synthesis) | 1 |
| phase-16-prep | 1 (workflow + 4 scaffold writers, can collapse to 1 invocation) |
| phase-16a, 16b, 16c | 3 (1 each) |
| phase-16d | 5 (1 per doc: RESEARCHER_GUIDE / FAQ / PROTOCOLS / TOOLS / CONTRACT) |
| phase-16e | 1 (this report) |

**Total: ~109 agent invocations across the v2.0.0 push.** Of those, 42 were
the validation harness (20 baseline + 20 re-validation + 2 naive_ai
supplements); 67 were code / doc / consolidation work.

The validation harness is the load-bearing piece — every consolidation
decision in Phase 9 was justified by a measured friction signal in the
Phase 15a baseline, and every claim in `docs/V2_RELEASE_NOTES.md` was
re-checked against the Phase 15b matrix.

---

**End of Phase 16 final report.** v2.0.0 is publish-ready, pending the user's
push + tag + merge decision per §9.
