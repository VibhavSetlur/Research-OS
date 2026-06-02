<!-- Thanks for the contribution! Fill in what's relevant; delete what isn't. -->

## Summary

<!-- One sentence: what does this change do? -->

## Type of change

- [ ] Bug fix (non-breaking; fixes an issue)
- [ ] New feature (non-breaking; adds capability)
- [ ] Breaking change (existing tools / protocols / schemas change behaviour)
- [ ] Protocol change (new protocol OR modification — see PROTOCOL_DOCTRINE.md)
- [ ] Tool change (new MCP tool OR schema change)
- [ ] Documentation only
- [ ] Refactor (no functional change)
- [ ] CI / repo infrastructure

## Motivation

<!-- Why is this change needed? Link the issue if one exists. -->

Fixes #

## Changes

<!-- Bullet list of what actually changed. Reference file paths + line numbers when useful. -->

-
-
-

## Protocol checklist (skip if not a protocol change)

- [ ] Protocol follows the **scaffold-not-script** doctrine
      ([PROTOCOL_DOCTRINE.md](../docs/PROTOCOL_DOCTRINE.md)) — no
      hardcoded method names, thresholds, or step sequences
- [ ] Added an entry in `_router_index.yaml` with `intent_class`,
      `sub_intent`, `summary`, and `triggers`
- [ ] `next_protocol` + `on_failure` point at real protocols (or `null`)
- [ ] Added a `tests/tools/test_router.py` case for at least one trigger
      phrase
- [ ] Protocol version bumped to current package version

## Tool checklist (skip if not a tool change)

- [ ] Added entry to `TOOL_DEFINITIONS` with `short`, `description`,
      `category`, `inputSchema`
- [ ] Registered handler in `_HANDLERS`
- [ ] Referenced from at least one protocol's `decomposition` OR a
      `shortcut_intents` entry (orphaned tools get removed)
- [ ] Added unit + error-path tests under `tests/tools/`

## Test plan

- [ ] `python scripts/preflight.py` — all checks pass
- [ ] `pytest -q` — full suite passes
- [ ] `ruff check src/ tests/ scripts/` — clean

<!-- Anything reviewers should manually verify? Screenshots, before/after, etc. -->

## Breaking changes

<!-- If you ticked "breaking change" above, list them here and tell
     users how to migrate. -->

N/A

## Linked issues / discussions

<!-- e.g. Closes #123, Related to #456 -->
