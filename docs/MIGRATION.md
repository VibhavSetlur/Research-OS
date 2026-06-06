# Migration guide

This document tracks the consolidation migrations introduced in
Research-OS. Old names continue to work as deprecated aliases /
redirect stubs until the next MAJOR release (when they are removed).

Audit which deprecated names a project still relies on:

```text
tool_deprecations_summary
```

It reads `.os_state/deprecations.log` (written automatically every
time an alias is invoked or a redirect stub is loaded) and returns
aggregated counts by `kind` / `source` / `target`.

---

## Tool consolidations

The five clusters below were merged behind one canonical tool each.
Calling the OLD name still works (the dispatcher injects the
implied operation / kind / source for back-compat); a hit is logged
to `.os_state/deprecations.log`.

### Search cluster (5 → 1)

| Old name                       | New invocation                                            |
|--------------------------------|-----------------------------------------------------------|
| `tool_search_semantic_scholar` | `tool_search(query=..., source='semantic_scholar')`       |
| `tool_search_pubmed`           | `tool_search(query=..., source='pubmed')`                 |
| `tool_search_crossref`         | `tool_search(query=..., source='crossref')`               |
| `tool_search_arxiv`            | `tool_search(query=..., source='arxiv')`                  |
| `tool_search_web`              | `tool_search(query=..., source='web')`                    |

`tool_search(query=..., source='auto')` (the default) picks providers
based on the query's domain:

* biomedical (rna / gene / clinical / disease …) → semantic_scholar + pubmed
* ML / methods (transformer / embedding / diffusion …) → semantic_scholar + arxiv
* social / behavioural (psychometric / survey / qualitative …) → crossref + semantic_scholar
* geoscience (climate / geology / ocean …) → crossref + arxiv
* generic → web

### Plan cluster (3 → 1)

| Old name              | New invocation                                |
|-----------------------|-----------------------------------------------|
| `tool_plan_turn`      | `tool_plan(operation='turn')`                 |
| `tool_plan_advance`   | `tool_plan(operation='advance')`              |
| `tool_plan_clear`     | `tool_plan(operation='clear')`                |

`tool_plan_step_grounded` stays standalone — distinct purpose (planner
with ReAct + CoVe scaffold).

### Path cluster (3 → 1)

| Old name             | New invocation                                            |
|----------------------|-----------------------------------------------------------|
| `sys_path_create`    | `sys_path(operation='create', name=..., hypothesis=...)`  |
| `sys_path_abandon`   | `sys_path(operation='abandon', path_name=..., rationale=...)` |
| `sys_path_list`      | `sys_path(operation='list')`                              |

### Grounding cluster (4 → 2)

| Old name                  | New invocation                                                       |
|---------------------------|----------------------------------------------------------------------|
| `tool_grounding_register` | `tool_ground(mode='explicit', claim=..., sources=[...])`             |
| `tool_ground_from_context`| `tool_ground(mode='from_context', claim=..., context_paths=[...])`   |
| `tool_claim_verify`       | `tool_verify(scope='claim', claim=..., verifications=[...])`         |
| `tool_grounding_verify`   | `tool_verify(scope='project')`                                       |

### Lessons cluster (2 → 1)

| Old name                | New invocation                                          |
|-------------------------|---------------------------------------------------------|
| `tool_lessons_record`   | `tool_lessons(operation='record', outcome=..., ...)`    |
| `tool_lessons_consult`  | `tool_lessons(operation='consult', task=...)`           |

### Memory cluster (4 → 1)

| Old name                  | New invocation                                                 |
|---------------------------|----------------------------------------------------------------|
| `mem_methods_append`      | `mem_log(kind='methods', method=..., ...)`                     |
| `mem_decision_log`        | `mem_log(kind='decision', context=..., selected=..., rationale=...)` |
| `mem_hypothesis_update`   | `mem_log(kind='hypothesis', hypothesis_id=..., status=...)`    |
| `mem_analysis_log`        | `mem_log(kind='analysis', entry=...)`                          |

### New utility tool

| New tool                      | Purpose                                                                             |
|-------------------------------|-------------------------------------------------------------------------------------|
| `tool_deprecations_summary`   | Aggregate counts from `.os_state/deprecations.log` (alias + redirect-stub hits).    |

---

## Protocol consolidations

Old protocol YAMLs that were merged into a consolidated form are now
**redirect stubs**: the file body is reduced to a `redirect_to:`
field (and optional `redirect_params:`). The protocol loader follows
the redirect and returns the consolidated body, with
`_redirected_from` + `_redirect_params` annotations so the AI can
condition behaviour on the requested variant.

### Synthesis printable (2 → 1)

| Old protocol                  | New invocation                                                        |
|-------------------------------|-----------------------------------------------------------------------|
| `synthesis/synthesis_handout` | `synthesis/printable` with `redirect_params: {format: handout}`       |
| `synthesis/synthesis_poster`  | `synthesis/printable` with `redirect_params: {format: poster}`        |

The unified `synthesis/printable` protocol takes `format='poster' |
'handout' | 'one_pager'` (with `one_pager` aliased to `handout`).
Quality-bar tables, audience profiles, and steps branch on `format`.

---

## Infrastructure

Two new pieces of infrastructure underpin the consolidation:

1. **Protocol loader `redirect_to:`** — a stub YAML may carry
   `redirect_to: <protocol_name>` and an optional
   `redirect_params: {...}` mapping. The loader detects the field,
   recursively loads the target, attaches
   `_redirected_from` + `_redirect_params` to the result, and logs the
   redirect to `.os_state/deprecations.log`. Cycles are detected
   across the whole chain. Stubs must NOT carry `steps:` (preflight
   enforces).
2. **Dispatcher alias telemetry** — invocations of any name in
   `_DEPRECATED_ALIASES` log to `.os_state/deprecations.log` with
   `kind='tool_alias'`, plus a back-compat parameter is injected
   (`operation` / `kind` / `source` / `mode` / `scope` as appropriate)
   so the legacy call shape keeps working without the caller supplying
   the consolidation parameter.

Preflight now includes two additional checks:

* **Alias table complete (handlers + param injection)** — every
  `_ALIASES` entry resolves to a registered handler; every
  `_DEPRECATED_ALIASES` entry has a corresponding
  `_ALIAS_PARAM_INJECTION` row.
* **Redirect-stub targets resolve** — every YAML with `redirect_to:`
  points at an existing protocol; no stub carries both `redirect_to:`
  and `steps:`.

---

## Timeline

Aliases and redirect stubs ship in the current MINOR release and stay
for the lifetime of the current MAJOR. They will be **removed** in
the next MAJOR release. The deprecation log + summary tool exist to
help projects migrate before the hard removal.
