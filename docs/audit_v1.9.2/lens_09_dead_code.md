# Lens 9 — Dead Code + Orphan Modules

Audit date: 2026-06-05
Repo state: v1.9.1 (114 protocols, 212 tools, 872 tests, ruff clean)
Tools: `vulture` (min-confidence 60 and 80), grep cross-reference into
`src/`, `tests/`, `scripts/` (excludes `templates/` and `scratch/`).

---

## Headline

The codebase is in good shape. After fixing one trivial dead-branch
finding inline, **vulture at min-confidence 80 reports a single
remaining hit** (an unused keyword argument on a public router API).
At min-confidence 60 there are 64 hits; almost all are public-API
holdovers, test hooks, or false positives.

**No orphan Python modules.** All 103 modules in `src/research_os/`
are referenced by short name somewhere in `src/`, `tests/`, or
`scripts/`.

**No unused vendored assets.** All 7 `.min.js` bundles in
`src/research_os/assets/js/` are referenced by code under
`tools/actions/audit/figure_interactivity.py` or
`tools/actions/synthesis/dashboard_v2.py`.

---

## Vulture findings (categorized)

### Truly dead (safe to delete in v1.9.3 or later)

| Location | Finding | Notes |
|---|---|---|
| `src/research_os/tools/actions/state/path.py:1568` | unreachable `return out` after a `return sentences[...]` (100%) | **FIXED inline in this audit.** Pure dead line; the variable `out` was already returned at line 1551 in the early-exit path. |
| `src/research_os/tools/actions/router.py:540` | `state_hint: dict | None = None` keyword-only param never read in `route_request` (100%) | **API smell, not just dead var.** The router accepts the kwarg, has no callers passing it anywhere in the repo, and silently ignores it. Either wire it through (M-task) or drop it on the next MAJOR. Worth filing as a HIGH inconsistency — public function signature lies about what it uses. |
| `src/research_os/inputs/papers.py:250` `fetch_many(tokens, dest)` | no callers anywhere in repo | Convenience wrapper around `fetch_one`. CLI uses `fetch_one` directly in a loop. Safe to drop in v1.9.3 or document as a public helper for downstream users. |
| `src/research_os/testing/stress_runner.py:314` `run_matrix(...)` | no callers | The module is exercised via `load_reference_project` + `StressResult` from `__init__.py`; `run_matrix` was apparently a never-finished matrix-runner entry-point. Safe to drop or document. |
| `src/research_os/testing/stress_runner.py:84` `expected_pack` property on `ReferenceProject` | no callers | The manifest YAML files (`tests/fixtures/projects/**/manifest.yaml`) all carry `expected_pack:` keys, but no Python code ever reads the property. The data flows in but never gets validated. Probable LOW pack-validation regression. |
| `src/research_os/plugins/loader.py:148` `pack_domain_detectors()` | no callers | Helper used to enumerate domain-detector callables from packs. Currently dead. |
| `src/research_os/plugins/loader.py:153` `write_pack_errors_log(root)` | no callers | Helper to persist plugin load errors; dead. |
| `src/research_os/project_ops.py:231-241` `read_yaml`, `write_yaml` | no callers | Generic YAML helpers; superseded by ruamel-direct calls elsewhere. |
| `src/research_os/project_ops.py:506` `compute_input_hashes(root)` | one comment reference in `state_ledger.py:201` but no real call | The comment claims it returns "the live view on demand" — but nothing calls it. Either wire it from `state_ledger.input_hashes` or delete. |
| `src/research_os/project_ops.py:527` `write_readme(path, title, body)` | no callers | Generic README writer; project-specific READMEs are built inline elsewhere. |
| `src/research_os/project_ops.py:2444` `state_diff_log_path(root)` | no callers | Helper for a "state diff log" feature that never landed. |
| `src/research_os/tools/actions/audit/dashboard_content.py:297` `_yiq_brightness(hex_color)` | no callers | Private helper; presumably stranded after a contrast-detection refactor. |
| `src/research_os/tools/actions/synthesis/typst.py:50` `_escape_typst_text(text)` | no callers | Private helper. |
| `src/research_os/tools/actions/synthesis/typst.py:512` `_prefer_vector_figure(path)` | no callers | Private helper. |
| `src/research_os/tools/actions/synthesis/typst.py:522` `_maybe_convert_svg_to_pdf(svg_path)` | no callers | Private helper. The Typst module clearly had a vector-figure conversion pipeline that was either rolled back or never finished. |
| `src/research_os/tui.py:228` `_term_width()` | no callers | Private helper; presumably superseded by `shutil.get_terminal_size`. |
| `src/research_os/utils/asset_manager.py:102` `iter_files`, `:126` `copy_asset_tree` | no callers | Public methods on `AssetManager`; only `find_project_root` is used externally. |
| `src/research_os/verify.py:62` `_dir_exists(root, rel)` | no callers | Private helper; the verify module checks dirs inline now. |

### Public API kept for back-compat (document, keep until v2.0.0)

| Location | Finding | Notes |
|---|---|---|
| `src/research_os/errors.py:25-52` `ConfigError`, `ScaffoldError`, `StateError`, `ToolError` | All 4 are defined and named in the module docstring tree but **never raised, never caught, never imported** | The errors module's docstring promises a 5-class taxonomy (`ResearchOSError` + 4 children + `WriteProtectedError`). Reality: only `ResearchOSError` and `WriteProtectedError` are used. Either start raising them in the relevant code paths (preferred — they're documented as the public exception surface) or strip the 4 ghosts and update the docstring. Worth a MEDIUM doc-gap finding. |
| `src/research_os/tools/actions/router.py:66` `reload_index()` | no callers in `src/`, `tests/`, `scripts/` | Marked as "test hook" in its own docstring. Either tests stopped calling it, or it's reserved for plugin reload. Document the intent or remove. |
| `src/research_os/tools/actions/semantic.py:492` `reset_caches()` | called from `tests/tools/test_semantic_routing.py` (4 sites) | **Tests-only.** Kept; documented intent ("call after rebuilding"). |
| `src/research_os/tools/actions/state/path.py:19` `create_path` | re-exported from `tools/actions/state/__init__.py:22`; also lazy-imported in `server.py:103` | **Public API.** Vulture false positive (re-export pattern). |
| `src/research_os/tools/actions/state/paywall_memory.py:125` `step_summary_failures` | re-exported from `tools/actions/state/__init__.py:49` | **Public API.** Vulture false positive. |
| `src/research_os/config.py` `FIRECRAWL`, `SERPAPI`, `SEMANTIC_SCHOLAR_API_KEY`, etc. | flagged as unused class attributes (60%) | All consumed at runtime via `os.environ`/`_env()` in `tools/actions/search/search.py`. The pydantic-Settings model attributes mirror env-var names, so `getattr` and direct env reads both work. **False positives.** |

### Tests-only (fine to keep)

| Location | Notes |
|---|---|
| `state/state_ledger.py` methods (lines 229-532): `set_phase`, `complete_phase`, `add_hypothesis`, `add_dead_end`, `add_error`, `track_tokens`, `add_loaded_data`, `save_ctm`, `get_latest_ctm`, `get_all_ctms`, `add_dag_node`, `update_dag_node_output_hashes`, `get_dag` | Each of these is exercised by `tests/unit/test_state.py` (verified for `set_phase`/`complete_phase`/`add_hypothesis`/`add_dead_end`). Vulture can't see through the test fixture pattern. **Fine — public ledger API.** Some may genuinely be unused by production tools, but the test contract pins them. |
| `src/research_os/tools/actions/semantic.py:492 reset_caches` | Already covered above. |

### False positives (vulture misclassified)

| Location | Why |
|---|---|
| `src/research_os/tools/actions/audit/audit.py:620` `f_p`, `f_stat` | Tuple-unpack discard from `het_breuschpagan(resid, X)` (statsmodels returns 4 values; we use 2). Replace with `_` if cosmetic. |
| `src/research_os/tools/actions/audit/content_depth.py:244,258` `referenced` | Set + incremented but never returned. Looks like leftover instrumentation — only `missing` is returned. LOW: either return the count or drop the counter. |
| `src/research_os/inputs/paste.py:45` `line_count` | `@dataclass` field; set at construction (line 218). The field IS the storage; vulture can't see external consumers of dataclass attrs. False positive. |
| `src/research_os/logo.py:94` `PLAIN_LOGO` | Module-level constant; only `logo.render()` is called externally. Truly unused module constant — either document as exported (ASCII fallback for log streams) or delete. LOW. |
| `src/research_os/tui.py:84` `INVERT` | Part of a string-building idiom (line 89 lists it among `("RED","MAGENTA",...,"INVERT")`); `INVERT` is referenced by name in that list to drive `setattr(self, name, ...)`. **False positive** — name-as-string usage. |
| `src/research_os/tools/actions/state/config.py:32` `preserve_quotes` | Attribute being SET on a ruamel-YAML loader instance — the loader reads it. False positive. |
| `src/research_os/utils/asset_manager.py:28` `local_path` | Field on a dataclass set at line 120; consumed by AssetRef readers. False positive. |
| `src/research_os/server.py:103` `create_path` | Lazy-import binding; passed to `_lazy_import` and registered. False positive. |
| `src/research_os/wizard.py:418` `IMAGE_EXTENSIONS` | Re-exported from `cli.py:120` (`from research_os.wizard import IMAGE_EXTENSIONS  # noqa: F401`). Public surface. False positive. |
| `src/research_os/inputs/papers.py` `SECTION_BUILDERS_KEYS` and friends | Module-level tuples used in tests or doc; treat as data. |

---

## Orphan module candidates

**None.** Cross-referenced all 103 `.py` modules in `src/research_os/`
against the union of `src/**.py`, `tests/**.py`, `scripts/**.py`. Every
short module name appears in at least one importer or test.

---

## Unused vendored assets

**None.** `src/research_os/assets/` contains only `js/` (7 minified
libraries + license texts + a `MANIFEST.json`). All 7 bundles are
referenced:

| Asset | Loader |
|---|---|
| `mermaid.min.js` | `synthesis/dashboard_v2.py:53` (`has_mermaid` flag) |
| `minisearch.min.js` | `synthesis/dashboard_v2.py:48` (`_ALWAYS_BUNDLES`) |
| `plotly.min.js` | `synthesis/dashboard_v2.py:52` (`has_plotly` flag) |
| `vega.min.js` / `vega-lite.min.js` / `vega-embed.min.js` | `_ALWAYS_BUNDLES` + `audit/figure_interactivity.py:455-457` |
| `vis-network.min.js` | `audit/figure_interactivity.py:435` + `dashboard_v2.py:54` |

Licenses, `NOTICE.md`, and `MANIFEST.json` are static documentation —
correct to bundle.

---

## Unused imports (F401)

Project ruff config (`pyproject.toml`) intentionally ignores `F401`
because `__init__.py` re-exports rely on it. Default `ruff check` is
clean. When F401 is forced on, **20 unused-import sites** are
reported across non-`__init__` modules. Notable concentrations:

| File:line | Import |
|---|---|
| `src/research_os/cli.py:23` | `import json` |
| `src/research_os/collab.py:23` | `from dataclasses import dataclass, field` (field unused) |
| `src/research_os/collab.py:26` | `from typing import Iterable` |
| `src/research_os/project_ops.py:21` | `import uuid` |
| `src/research_os/tools/actions/audit/audit.py:1172` | `import hashlib` (inside a try block) |
| `src/research_os/tools/actions/audit/claim_grounding.py:43` | `from collections import Counter` |
| `src/research_os/tools/actions/audit/dashboard_content.py:14` | unused `json` import |
| `src/research_os/tools/actions/audit/preregistration.py:39` | unused `research_os.project_ops.compute_file_hash` |
| `src/research_os/tools/actions/audit/redteam.py:35` | unused `shutil` |
| `src/research_os/tools/actions/data/intake.py:295` | unused `research_os.tools.actions.state.provenance.track_runtime` |
| `src/research_os/tools/actions/exec/step_pipeline.py:82,388` | unused `Iterable`, unused `re` |
| `src/research_os/tools/actions/research/grounding.py:47` | unused `os` |
| `src/research_os/tools/actions/state/reliability.py:22` | unused `json` |
| `src/research_os/tools/actions/state/repair.py:18` | unused `base64` |
| `src/research_os/tools/actions/synthesis/dashboard.py:33` | unused `datetime.datetime`, `datetime.timezone` |
| `src/research_os/tools/actions/synthesis/dashboard_v2.py:30` | unused `pathlib.Path` |
| `src/research_os/tools/actions/synthesis/latex.py:19` | unused `json`, `re` |
| `src/research_os/tui.py:30` | unused `Iterable` |

**Recommendation:** because the project deliberately ignores F401 (for
`__init__.py` re-export hygiene), do NOT bulk-fix these — that change
would slip if/when re-exports are added. Instead, consider:

1. Switching `ignore = ["F401"]` to a per-file `[tool.ruff.lint.per-file-ignores]`
   keyed on `"src/research_os/**/__init__.py"`, then auto-fix the rest.
   That's a v1.9.3 cleanup.
2. Adding `# noqa: F401  (re-export)` markers where unused imports
   ARE intentional, matching the pattern already used at
   `src/research_os/cli.py:33` and `src/research_os/cli.py:120`.

This is a MEDIUM polish task. Not blocking release.

---

## Dead branches

Vulture's "unreachable code" detector reports **one site, now fixed**:
`src/research_os/tools/actions/state/path.py:1568` had a `return out`
immediately after a `return sentences[:8] or [prose[:500]]`. The
`return out` was reachable only via a removed early-exit path; `out`
contained an earlier-built bullet list that was already returned at
line 1551 for the bullet-found case. Fixed inline.

No other dead branches (impossible if-conditions, always-false guards)
at confidence ≥ 80.

---

## Trivial fixes applied this audit

1. `src/research_os/tools/actions/state/path.py:1568` — removed
   unreachable `return out` line immediately after the function's
   real return. Pure dead code, no behavior change.

Verified post-fix:
- `vulture src/research_os/ --min-confidence 80` now shows only the
  `state_hint` finding (was 2 hits, now 1).
- `ruff check src/ tests/ scripts/` still **All checks passed!**

---

## Recommended follow-ups (not applied — read-only audit)

| # | Severity | Target | Suggestion |
|---|---|---|---|
| 1 | HIGH | v1.9.3 | `route_request(state_hint=...)` lies — either wire `state_hint` into the router scoring or drop the parameter. Public API surface should not silently ignore kwargs. |
| 2 | MEDIUM | v1.9.3 | `errors.py` docstring promises `ConfigError`/`ScaffoldError`/`StateError`/`ToolError` but the codebase never raises them. Either start raising (preferred — they're a clean public taxonomy) or remove and update the docstring. Affects external integrators reading the module. |
| 3 | MEDIUM | v1.9.3 | `ReferenceProject.expected_pack` is read from manifest YAML files but never validated. Either drop the YAML key or wire stress-runner to assert the loaded pack matches. Bug hiding here. |
| 4 | MEDIUM | v1.9.3 | Audit/Typst dead helpers (`_yiq_brightness`, `_escape_typst_text`, `_prefer_vector_figure`, `_maybe_convert_svg_to_pdf`) suggest a vector-figure pipeline that was rolled back. Decide: delete, or finish wiring. |
| 5 | LOW | v1.9.3 | Drop `fetch_many`, `run_matrix`, `read_yaml`/`write_yaml`, `compute_input_hashes`, `write_readme`, `state_diff_log_path`, `_term_width`, `_dir_exists`, `iter_files`/`copy_asset_tree`, `PLAIN_LOGO`. None are referenced; all are private helpers or convenience wrappers. |
| 6 | LOW | v1.9.4 | Migrate `pyproject.toml` `ignore = ["F401"]` to a per-file pattern targeting `__init__.py` only, then `ruff --fix --select F401` the rest. |
| 7 | LOW | v1.9.3 | `tools/actions/audit/content_depth.py:244` `referenced` counter is set but never returned — either return it in the dict or drop. Cosmetic. |
