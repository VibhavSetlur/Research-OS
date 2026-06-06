# Phase 1 — Source-file rename registry (v2.1.0)

**Scope:** rename source files in `src/research_os/` with version suffixes
or other non-canonical names. Tests are intentionally excluded — the
`tests/unit/test_v<N>.py` convention encodes when each test was first added
and serves as historical record, not naming drift.

**Inventory cutoff:** 2026-06-06, branch `feat/v2.0.0` (pre-v2.0.0 ship).

## Decision matrix

| Current path | Proposed new path | Decision | Reason | # source callers | # tests | Migration alias |
|---|---|---|---|---|---|---|
| `src/research_os/tools/actions/synthesis/dashboard_v2.py` | `src/research_os/tools/actions/synthesis/dashboard_app.py` (or consolidate into `dashboard.py`) | **NEEDS_DECISION** | v2 is the live SPA renderer; legacy `dashboard.py` is the long-scroll fallback accessed via `dashboard_legacy=true` flag. Two living renderers → rename for clarity rather than collide. | 2 internal | 2 (`test_v191_dashboard_v2`, `test_v191_story_mode`) | `dashboard_v2` ↦ re-export from new path |
| `src/research_os/tools/actions/synthesis/dashboard_v2_humanities.py` | `src/research_os/tools/actions/synthesis/dashboard_humanities.py` | **RENAME** | Domain renderer for the SPA; the `_v2` prefix mirrors its sibling and adds no info. | 1 (dashboard_v2) | 1 (`test_dashboard_v2_humanities`) | yes |
| `src/research_os/tools/actions/synthesis/dashboard_v2_qualitative.py` | `src/research_os/tools/actions/synthesis/dashboard_qualitative.py` | **RENAME** | Same reason as above. | 1 (dashboard_v2) | 1 (`test_dashboard_v2_qualitative`) | yes |
| `src/research_os/tools/actions/synthesis/humanities_essay_scaffold.py` | (no change) | **KEEP** | `_scaffold` is a functional descriptor (the module produces an essay scaffold), not a version suffix. No sibling `humanities_essay.py` exists. | 2 | 2 | n/a |

## Judgement calls the researcher should weigh in on

1. **dashboard_v2 vs dashboard collision.** Two coexisting renderers (legacy long-scroll + new SPA). Options:
   - **(a)** Rename legacy `dashboard.py` → `dashboard_legacy.py`, then `dashboard_v2.py` → `dashboard.py`. Cleanest namespace; biggest churn.
   - **(b)** Rename `dashboard_v2.py` → `dashboard_app.py` (or `dashboard_spa.py`); keep legacy `dashboard.py` as-is. Lowest churn; namespace stays slightly redundant.
   - **(c)** Delete legacy `dashboard.py` if no live caller invokes it; collapse v2 into base. Requires confirming no `dashboard_legacy=true` callers.
   - Recommendation: **(a)** if we commit to SPA as canonical. **(b)** if we want a slow runway.

2. **Pack dashboard variants.** `dashboard_v2_humanities.py` + `dashboard_v2_qualitative.py` use `_v2` only because the base file does. Rename in lockstep with whatever decision above lands.

3. **Test-file naming.** v2.1.0 leaves `tests/unit/test_v<N>.py` filenames intact; the prompt explicitly told us not to touch them. The 2 dashboard-v2 tests stay (`test_v191_dashboard_v2.py`, `test_dashboard_v2_humanities.py`, `test_dashboard_v2_qualitative.py`) — their import paths change to track the rename.

## Migration alias mechanism

For each renamed module, leave a 3-line shim at the old path:

```python
"""Migration alias — re-exports from canonical path. Removed in v2.2.0."""
from research_os.tools.actions.synthesis.<new_module> import *  # noqa: F401,F403
```

Routes any external caller's `from research_os.tools.actions.synthesis.dashboard_v2 import X` through to the canonical module for one minor cycle. `MIGRATION_v2_0_to_v2_1.md` documents the removal date.

## What's NOT in scope for Phase 1

- Renaming protocols (Phase 5 handles taxonomy)
- Renaming tools (would be MAJOR-breaking; deferred to v3.0.0)
- Test filename version suffixes (historical record)
- Renaming `__init__.py`, `_router_index.yaml`, `_handlers_runtime.py` etc. — leading-underscore modules are by-convention internal
