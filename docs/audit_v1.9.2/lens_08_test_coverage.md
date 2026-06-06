# LENS 8 — Test Coverage & Brittleness

**Scope:** v1.9.1 baseline. 872 tests pass, ruff clean, preflight 13/13.
**Headline:** `pytest --cov` reports **55% line coverage** across
`src/research_os/` (18,238 stmts / 8,263 uncovered). Suite is fast
(<60 s) and almost entirely hermetic (network calls are all mocked
via `urllib.request.urlopen` patches), but the **`init`-time user
surface (`cli.py`, `wizard.py`, `tui.py`, `verify.py`, `logo.py`,
`collab.py`, `inputs/*`)** has **0% coverage** — that's 3,057 LOC
of user-facing code with no test exercising any line. This is the
single biggest brittleness risk for v1.9.2.

---

## Coverage summary (header → key buckets)

Top-level numbers: **18,238 stmts, 8,263 uncovered, 55% cover**.

| Bucket | Avg cover | Worst module |
|---|---|---|
| `research_os/*` top-level (cli/wizard/tui/etc.) | 7% (skewed by 0% modules) | `cli.py` 0% / 359 stmts |
| `tools/actions/audit/*` | 65% | `md_audit.py` 12% / 49 stmts |
| `tools/actions/data/*` | 56% | `data.py` 7% / 147 stmts |
| `tools/actions/exec/*` | 53% | `cluster.py` 19%, `sensitivity.py` 26% |
| `tools/actions/research/*` | 64% | `research.py` 39% / 355 stmts |
| `tools/actions/search/*` | 39% | `literature.py` 28% / 224 stmts |
| `tools/actions/state/*` | 71% | `interaction.py` 8% / 103 stmts |
| `tools/actions/synthesis/*` | 60% | `synthesize.py` 7% / 551 stmts, `latex.py` 11% / 148 stmts |
| `tools/actions/viz/*` | 46% | `figures.py` 38% / 167 stmts |
| `adapters/*` | 79% | `runner.py` 67% |
| `plugins/*` | 84% | `loader.py` 79% |

---

## 0% coverage modules (highest priority)

All of these are runtime code shipped to users. No test loads them.

| Module | Stmts | Notes |
|---|---|---|
| `cli.py` | 359 | The `research-os` entry-point (`init`, `ide add/remove/list`). Every PyPI user touches this first. Zero coverage. |
| `wizard.py` | 369 | Interactive scaffolder used by `research-os init`. Zero coverage of the wizard's logic — but `tests/integration/test_init.py` does exercise the `--yes` path through `subprocess.run`, so the *CLI surface* is partially tested even though the line counter shows 0% (subprocess invocations aren't measured). |
| `tui.py` | 455 | Optional TUI surface. Zero coverage. |
| `verify.py` | 88 | Post-scaffold smoke check (`cli.py init --verify`). Zero coverage. |
| `logo.py` | 40 | ASCII banner — cosmetic; OK at 0%. |
| `collab.py` | 94 | Multi-author collab utility. Zero coverage. Risk: silent breakage on the collab surface no one tests. |
| `inputs/papers.py` | 150 | Paper-URL ingester used by wizard's "drop paper URLs" loop. Zero coverage. |
| `inputs/paste.py` | 108 | Slack/email paste-bin parser used by wizard. Zero coverage. |

**Total 0%-coverage LOC: 1,663 statements (~9% of codebase) on the
*user entry path*.** Two of these (`wizard.py`, `cli.py`) are exercised
end-to-end by `test_init.py` via `subprocess.run`, so the real
unmonitored surface is closer to `tui.py + verify.py + collab.py +
inputs/*` (~895 stmts).

**Recommendation (v1.9.3+, no test additions for v1.9.2):** add at
least one `pytest`-internal call (not subprocess) into `cli.py` and
`verify.py` so coverage reports stop flat-lining at 0% even when the
behavior is exercised.

---

## <50% coverage modules (regression-risk hotspots)

Sorted by *uncovered LOC* (impact-weighted, not percent-weighted —
a 7%-covered 551-line module hides more risk than a 38%-covered
40-line module).

| Module | Stmts | Miss | Cover | Risk |
|---|---|---|---|---|
| `tools/actions/synthesis/synthesize.py` | 551 | 514 | **7%** | Highest absolute uncovered LOC in the codebase. Paper-synthesis is the *terminal* user-visible output. A regression here ships broken papers. |
| `tools/actions/audit/audit.py` | 709 | 369 | 48% | Audit-master orchestrator. 360 uncovered lines on the gate that decides "ship vs not". |
| `tools/actions/state/path.py` | 910 | 353 | 61% | Largest single file. State-path resolution; cross-cutting. |
| `tools/actions/synthesis/dashboard.py` | 593 | 275 | 54% | Legacy dashboard (`dashboard.py`) — note `dashboard_v2.py` is at 91%. |
| `tools/actions/state/extractors.py` | 406 | 143 | 65% | Extractors feed the audit; partial coverage acceptable. |
| `tools/actions/research/research.py` | 355 | 217 | 39% | Research-grounding orchestrator. |
| `tools/actions/search/literature.py` | 224 | 162 | 28% | Literature search (Semantic Scholar / web). Network paths skipped — see "Network-dependent" below. |
| `tools/actions/search/search.py` | 313 | 149 | 52% | Same area; partial. |
| `tools/actions/exec/cluster.py` | 165 | 133 | **19%** | Cluster/Slurm path. Hard to test locally — acceptable but flag. |
| `tools/actions/exec/sensitivity.py` | 184 | 136 | **26%** | Sensitivity sweeps; same difficulty. |
| `tools/actions/audit/prose_quality.py` | 218 | 111 | 49% | Used by every paper audit. |
| `tools/actions/state/interaction.py` | 103 | 95 | **8%** | Almost-zero coverage on the interaction-log surface. |
| `tools/actions/audit/code_quality.py` | 167 | 91 | 46% | |
| `tools/actions/synthesis/latex.py` | 148 | 132 | **11%** | LaTeX export path; very low. |
| `tools/actions/data/data.py` | 147 | 137 | **7%** | Data-action surface. |
| `tools/actions/viz/figures.py` | 167 | 104 | 38% | |
| `tools/actions/viz/dashboard_tests.py` | 90 | 42 | 53% | |
| `tools/actions/audit/md_audit.py` | 49 | 43 | **12%** | Tiny module, almost untested. |
| `tools/actions/exec/notebook.py` | 88 | 36 | 59% | |
| `tools/actions/state/repair.py` | 96 | 38 | 60% | |
| `tools/actions/state/freshness.py` | 67 | 25 | 63% | |
| `utils/asset_manager.py` | 96 | 59 | 39% | |
| `utils/common.py` | 70 | 47 | 33% | |
| `errors.py` | 34 | 16 | 53% | Exception class — tested when raised. |
| `state/state_ledger.py` | 438 | 243 | 45% | Core ledger; only half-covered is a yellow flag. |

`server.py` (1,595 stmts, 40% cover) is large and dispatcher-heavy;
40% on a router-shaped file is common. The actual handlers are
exercised through the action modules, which are individually
tracked above.

---

## Vacuous tests

Grep for `assert True`, bare `pass`, and `# TODO/FIXME/XXX`:

| File | Line | Issue |
|---|---|---|
| `tests/unit/test_v171_three_packs.py` | 51-59 | `test_pack_to_pack_namespace_isolation` opens with a 3-line block that walks `installed_packs()`, iterates over a 1-tuple `pack["name"],` (effectively one string), and `pass`es. Dead loop with a misleading `# noqa: B007` comment. **The test as a whole still asserts meaningfully** via the `_DISCOVERED_PACKS` walk on lines 61-79. Recommendation: delete lines 56-59 — they do nothing and confuse readers. (Severity: LOW.) |

No other `assert True` patterns. No `# TODO/FIXME/XXX` comments in
`tests/`. Test suite is honest.

---

## Network-dependent tests

`grep -rn` shows no test actually opens a real socket. Every
`urlopen` reference in tests is wrapped in `@patch("urllib.request.urlopen")`:

- `tests/unit/test_search.py` lines 14, 35, 46 — all `@patch`ed
- `tests/unit/test_actions.py` lines 58, 108, 115 — all `@patch`ed

URLs like `https://elsevier.example.com/...` and
`https://example.com/paywalled.pdf` (in `test_v150.py`,
`test_v1_5_0.py`) are *strings passed to paywall-detection logic*
and never fetched.

**Verdict: suite is hermetic. No external-service dependency.** Good.

---

## Home-path hardcoded tests

Only two hits, both benign:

- `tests/integration/test_init.py:298` — docstring mentions
  `~/.config/research-os/profile.yaml`. Test body itself uses
  `tmp_path` / a monkeypatched `HOME`.
- `tests/fixtures/projects/slurm_snakemake/inputs/scripts/run_pipeline.sh:14`
  — bash comment about `~/.config/snakemake/slurm/`. Fixture data,
  not test code.

**Verdict: no `/home/<user>` or `/Users/<user>` hardcoding. Portable.**

---

## Slow tests (>5 s)

`pytest --durations=20` reports **zero tests over 1 s**. Slowest:

| Time | Test |
|---|---|
| 0.77 s | `tests/tools/test_router.py::test_route_intake_prompt` |
| 0.60 s | `tests/tools/test_tasks.py::test_task_status_transitions_to_finished` |
| 0.59 s | `tests/tools/test_semantic_routing.py::test_semantic_route_top1_accuracy` |
| 0.59 s | `tests/tools/test_semantic_routing.py::test_expected_protocol_always_in_top3` |
| 0.53 s | `tests/integration/test_full_workflow.py::test_legacy_tool_name_alias` |
| 0.51 s | `tests/tools/test_tasks.py::test_task_kill_terminates_process` |

All sub-1-second. Full suite runs in ~37 s wall-clock. **Suite is
fast — no CI bloat risk.**

Real `time.sleep` usage:
- `tests/unit/test_provenance.py:66` — `time.sleep(0.02)` to force
  a clock tick. Fine.
- `tests/tools/test_tasks.py:28, 37` — `time.sleep(0.6)` and `0.1`
  to wait for subprocess lifecycle. The 0.6 s sleep is the dominant
  cost in two of the top-six slowest tests; acceptable.

---

## Stale fixtures

`tests/fixtures/projects/` ships **13 reference projects**, each
with a `manifest.yaml` listing `protocols_expected`,
`gates_expected_pass`, `artifacts_required`, and (for runnable
fixtures) `canned_responses`.

I verified every referenced protocol path exists in the codebase:

| Fixture | Protocols referenced | Status |
|---|---|---|
| biology_genomics_mini | `guidance/project_startup`, `methodology/exploratory_data_analysis`, `audit/audit_and_validation` | OK |
| engineering_fmea_simple | `engineering/design/requirements_traceability`, `engineering/safety/fmea_protocol` | OK (in `src/research_os_engineering/protocols/`) |
| humanities_ms_review | `humanities/archival/archival_research`, `humanities/archival/source_provenance`, `humanities/output/scholarly_edition` | OK (in `src/research_os_humanities/protocols/`) |
| mid_pipeline_handoff | `guidance/session_resume`, `guidance/mid_pipeline_entry` | OK |
| nextflow_chipseq | `guidance/project_startup`, `methodology/exploratory_data_analysis` | OK |
| paper_nature_minimal | `guidance/project_startup`, `methodology/exploratory_data_analysis`, `audit/audit_and_validation`, `synthesis/synthesis_paper` | OK |
| paper_thin_content | `guidance/project_startup`, `synthesis/synthesis_paper`, `audit/audit_and_validation` | OK |
| qualitative_interviews | `qualitative/coding/coding_scheme_iteration`, `qualitative/method/thematic_analysis_braun_clarke`, `qualitative/output/qualitative_report_format` | OK (in `src/research_os_qualitative/protocols/`) |
| quick_plot_throwaway | `guidance/casual_exploration` | OK |
| redcap_longitudinal | `guidance/project_startup`, `methodology/exploratory_data_analysis` | OK |
| slurm_snakemake | `guidance/project_startup`, `methodology/exploratory_data_analysis`, `audit/audit_and_validation` | OK |
| theory_math_short_proof | `theory_math/output/theory_paper_structure`, `theory_math/proof/lemma_library`, `theory_math/proof/proof_verification_workflow` | OK (in `src/research_os_theory_math/protocols/`) |
| wet_lab_qpcr_run | `wet_lab/protocol/reagent_lot_tracking`, `wet_lab/protocol/plate_map_provenance`, `wet_lab/protocol/instrument_run_log` | OK (in `src/research_os_wet_lab/protocols/`) |

**No stale fixture references. All 13 reference projects point at
live protocols.**

Note: `expected_pack: humanities | qualitative | wet_lab | engineering`
in those manifests matches the actual pack names registered by the
five plugin packs in `src/research_os_*/`.

---

## Reference projects status

The `tests/fixtures/projects/` directory IS the reference-project
fleet (no top-level `references/` directory exists). Coverage of each:

| Fixture | Has `canned_responses` (CI-runnable) | Likely exercised by |
|---|---|---|
| biology_genomics_mini | – | `test_full_workflow.py` (core protocol path) |
| engineering_fmea_simple | – | `test_v171_three_packs.py` (pack loading) |
| humanities_ms_review | – | `test_v171_three_packs.py` |
| mid_pipeline_handoff | – | `test_init.py` resume path |
| nextflow_chipseq | – | `test_v180_adapters_extractors.py` (nextflow adapter) |
| paper_nature_minimal | – | `test_v190_*` synthesis tests |
| paper_thin_content | – | `test_v190_content_depth.py` |
| qualitative_interviews | – | `test_v171_three_packs.py` |
| quick_plot_throwaway | – | quick-mode tests in `test_state.py` / `test_branch_paths.py` |
| redcap_longitudinal | yes | `test_v180_adapters_extractors.py` (redcap adapter) |
| slurm_snakemake | yes | `test_v180_adapters_extractors.py` (slurm + snakemake) |
| theory_math_short_proof | – | `test_v171_three_packs.py` |
| wet_lab_qpcr_run | yes | `test_v171_three_packs.py` |

Three fixtures (`slurm_snakemake`, `redcap_longitudinal`,
`wet_lab_qpcr_run`) ship `canned_responses` keyed by step_id — these
look like they were designed for a stress-runner harness
(`research_os/testing/stress_runner.py` at 66% cover), but I see no
test that actually loops through `tests/fixtures/projects/` running
each one end-to-end with the mock model. The fixtures are
*inventoried* (used for adapter and protocol-loading tests) but
**not run as end-to-end reference workflows.** This is a documented
testing-surface gap — see Top Findings.

---

## Other observations

- **Vulture** (`--min-confidence 80`) reports a single dead
  variable: `src/research_os/tools/actions/router.py:540` —
  `unused variable 'state_hint' (100% confidence)`. One-line dead
  code; logging as a finding (LOW). Lens rules forbid me from
  deleting it.

- **Test file count: 56** under `tests/`, split unit/integration/tools.
  Healthy ratio for a 18k-LOC codebase.

- **`pytest-cov` is NOT in `requirements*.txt` or `pyproject.toml`
  optional-deps.** I `pip install`ed it ad-hoc per task instructions.
  If maintainers want CI to publish a coverage badge, this will need
  to be added to `[project.optional-dependencies].dev` (out of scope
  for this lens).

---

## Trivial fixes applied

None. The vacuous loop in `test_v171_three_packs.py:56-59` *would*
qualify, but the lens rules say "DO NOT delete code, even if dead."
Logged as a finding instead.

---

## Top findings (severity-ordered)

1. **HIGH / DOC_GAP — `cli.py` + `wizard.py` show 0% coverage despite being exercised by `test_init.py`.** Subprocess-spawned `research-os init` runs through `cli.py` and `wizard.py` but coverage.py can't see it. Recommend a single in-process pytest that calls the CLI's `main()` function directly so the coverage report stops underselling the suite. (`src/research_os/cli.py`, `src/research_os/wizard.py`)

2. **HIGH / DEAD_CODE — Three CI-runnable reference fixtures (`slurm_snakemake`, `redcap_longitudinal`, `wet_lab_qpcr_run`) ship `canned_responses` keyed by step_id but no test harness loops through them.** `stress_runner.py` (66% cover) looks like the intended runner but it's not wired to enumerate `tests/fixtures/projects/*/manifest.yaml`. Either delete the canned_responses (orphaned) or wire a meta-test that runs each fixture end-to-end. (`tests/fixtures/projects/`, `src/research_os/testing/stress_runner.py`)

3. **HIGH / FRICTION — `synthesize.py` (551 stmts, 7% cover) is the largest under-tested module on the user-facing output path.** A regression in paper synthesis ships broken papers. `dashboard.py` (54%) is similarly under-tested but `dashboard_v2.py` (91%) is the active surface — confirm `dashboard.py` is still live or mark for removal in 2.0.0. (`src/research_os/tools/actions/synthesis/synthesize.py`, `tools/actions/synthesis/dashboard.py`)

4. **MEDIUM / FRICTION — `inputs/papers.py` + `inputs/paste.py` (258 stmts combined, 0% cover) are entry-points called from the interactive wizard.** Any user pasting a Slack snippet or dropping a paper URL hits untested code. (`src/research_os/inputs/papers.py`, `src/research_os/inputs/paste.py`)

5. **MEDIUM / FRICTION — `state/interaction.py` (8% cover) and `data/data.py` (7% cover) are near-zero coverage on small, live modules.** Easy wins for v1.9.3 — these are not huge files. (`src/research_os/tools/actions/state/interaction.py`, `src/research_os/tools/actions/data/data.py`)

6. **MEDIUM / FRICTION — `synthesis/latex.py` (11% cover) is a 148-stmt output path used by the LaTeX export.** If anyone is using LaTeX export downstream of synthesis, it's almost entirely untested. (`src/research_os/tools/actions/synthesis/latex.py`)

7. **LOW / DEAD_CODE — `tests/unit/test_v171_three_packs.py` lines 56-59 contain a no-op `for pack in installed_packs(): for t in pack["name"], : pass` block** that does nothing — the real assertion is below. The `# noqa: B007` comment is misleading; B007 is about unused loop variables, not this. Recommend deletion in v1.9.3. (`tests/unit/test_v171_three_packs.py:56-59`)

8. **LOW / DEAD_CODE — `src/research_os/tools/actions/router.py:540` has an unused `state_hint` variable** (vulture, 100% confidence). One-line fix, but lens rules forbid me from removing it. (`src/research_os/tools/actions/router.py:540`)
