# Lens 07 — researcher_config.yaml schema integrity (v1.9.1 → v1.9.2)

Scope: every field in `templates/researcher_config.yaml` vs. every config
read across `src/`, plus the parallel in-code `CONFIG_TEMPLATE` constant
in `src/research_os/tools/actions/state/config.py` (which is what the
wizard actually writes — `templates/researcher_config.yaml` is NOT the
file copied by `research-os init`).

There are effectively **three** sources of truth competing:

1. `templates/researcher_config.yaml` — on-disk reference template; the
   file the README + RESEARCHER_GUIDE.md tell users to inspect.
2. `CONFIG_TEMPLATE` constant inside
   `src/research_os/tools/actions/state/config.py` — what
   `research-os init` actually writes to a new project.
3. `docs/RESEARCHER_GUIDE.md` §8 — what the docs claim the schema is.

All three disagree. This is the headline finding.

---

## A. Wizard / template / docs disagreement (HIGH)

`templates/researcher_config.yaml` has 9 keys that the wizard never
emits. Diff of leaf-paths:

```
in templates/researcher_config.yaml only (vs CONFIG_TEMPLATE):
  gate_strictness
  project_tier
  tool_stack
  tool_stack.allow_mixed_language_steps
  tool_stack.cite_field_practice_when_choosing
  tool_stack.field_practice_overrides_preference
  tool_stack.preferred_languages
  writing_preferences.pdf_compile_engine
  writing_preferences.venue_template
```

`docs/RESEARCHER_GUIDE.md` §8 (lines 388–448) documents the
intersection minus `gate_strictness` and `project_tier` and
`venue_template` and `pdf_compile_engine` and `tool_stack`. So the
RESEARCHER_GUIDE schema sample is closer to the in-code wizard output
than to the on-disk template, but still drops fields the wizard could
support.

The narrative line in RESEARCHER_GUIDE.md:443 — "There is ONE template:
`templates/researcher_config.yaml`" — is **false**. The wizard ignores
it. New projects never see `gate_strictness`, `project_tier`,
`tool_stack.*`, `venue_template`, or `pdf_compile_engine` unless the
researcher hand-adds them.

Severity HIGH because users who read the on-disk template believe
those knobs exist + are set to documented defaults. They aren't.
Suggested target: v1.9.3.

---

## B. Critical config-path bug — `gate_strictness` + `project_tier` never read in real projects (CRITICAL)

Three code paths look for `researcher_config.yaml` at the **project
root** instead of `inputs/researcher_config.yaml` (where the wizard
puts it):

| File | Line | Symbol |
|---|---|---|
| `src/research_os/tools/actions/state/rigor_signals.py` | 229 | `resolve_gate_strictness` |
| `src/research_os/tools/actions/state/quick_mode.py` | 206 | `project_tier_strictness` |
| `src/research_os/tools/actions/state/reliability.py` | 52 | `_read_model_profile` |

Every other reader (config.py, exec/tasks.py, exec/cluster.py,
search/search.py, synthesis/latex.py, synthesis/dashboard.py,
synthesis/typst.py, synthesis/preview.py, audit/preregistration.py,
audit/prose_quality.py) uses `root / "inputs" / "researcher_config.yaml"`.

The 3 broken paths use `root / "researcher_config.yaml"`. In a real
project initialised via `research-os init`, the file lives at
`inputs/researcher_config.yaml`, so:

1. `resolve_gate_strictness` always falls through to the auto/default
   trust-score branch — the researcher's explicit
   `gate_strictness: light|normal|strict` is **ignored**.
2. `project_tier_strictness` always returns `production → strict` —
   `project_tier: throwaway` is **ignored**.
3. `_read_model_profile` always returns `"unknown"` for reliability
   telemetry, masking what model the researcher actually ran on.

Tests pass because `tests/tools/test_v1_5_1.py:101` and
`tests/unit/test_v151.py:200` write the config to `tmp_path/researcher_config.yaml`
(project root), not `tmp_path/inputs/researcher_config.yaml` (the
real layout). The tests test the bug, not the contract.

Compare server.py:6253 which gets this right with a dual-path
fallback:

```python
cfg_path = root / "inputs" / "researcher_config.yaml"
if not cfg_path.exists():
    cfg_path = root / "researcher_config.yaml"
```

Fix: change the 3 buggy sites to use `_config_path(root)` from
`tools/actions/state/config.py`, or the same dual-path fallback as
server.py:6253. Then either fix the two tests to use `inputs/` (best),
or add a second test case that exercises the real layout.

Severity CRITICAL — these are top-level v1.5.1 features that have
silently been broken since they shipped. Suggested target: v1.9.3.

---

## C. Dead template fields (consumed nowhere in src/, MEDIUM)

Fields present in `templates/researcher_config.yaml` with no consumer
anywhere in `src/`:

| Template path | Used in src/? | Notes |
|---|---|---|
| `research_goal.poster_dimensions` | NO | mentioned only in CONFIG_TEMPLATE comment + template. `_handle_tool_poster_create` doesn't read this. |
| `research_goal.target_venue` | NO (echoed only) | `interaction.py:137` includes it in a status summary; never branches on it. |
| `research_goal.output_types` | NO (validated only) | `validate_config` checks presence; nothing reads it to drive behavior. |
| `interaction.ambiguity_posture` | NO branch | `get_interaction_policy` returns it but no caller acts on it (`grep -r ask_when_uncertain\|take_best_default` in src/ confirms zero branch sites outside config.py). |
| `writing_preferences.citation_style` | NO | `synthesize.py:678` takes a hard-coded default `"vancouver"` from its function signature; never reads from researcher_config. |
| `writing_preferences.language` | NO (echoed only) | `interaction.py:135` echoes it in a status summary. Typst / LaTeX writers don't apply it. |
| `writing_preferences.pdf_compile_engine` | NO | template advertises `typst | latex | both`. No code reads it; no engine-router switches on it. |
| `runtime.default_n_for_sampling` | NO | `tool_data_profile` does not honour it. |
| `tool_stack.preferred_languages` | NO | template comment claims "Read by `methodology/pick_tool_stack`" but the protocol YAML never references the field, and no Python reader exists. |
| `tool_stack.allow_mixed_language_steps` | NO | same. |
| `tool_stack.field_practice_overrides_preference` | NO | same. |
| `tool_stack.cite_field_practice_when_choosing` | NO | same. |
| `interaction.autonomy_level: coaching` (enum value) | NO branch | `coaching` appears only in template comments and tool descriptions. No code does `autonomy == "coaching"`. Server.py:2326 says `sys_coaching_replay` is "Designed for autonomy_level='coaching'" but it's available to every autonomy mode; nothing gates on it. |

Recommendation: pick one of:

- (a) Wire each field (best) — e.g. make `synthesize.py` read
  `writing_preferences.citation_style` as the default, make
  `pdf_compile_engine` actually choose between typst/latex,
  thread `default_n_for_sampling` through `tool_data_profile`.
- (b) Move dead fields to a `# v2 candidates — not yet wired` block
  in the template so users understand they're aspirational.
- (c) Delete them (NOT recommended — `tool_stack.*` is a v1.4.0
  doctrine field; deleting would be a MAJOR bump).

Severity MEDIUM — silent misconfiguration; users set knobs that do
nothing. Suggested target: v1.11.0 to wire; v1.9.4 to add a "not yet
wired" comment in the template.

---

## D. Missing template fields (read by src/, never in template, HIGH)

Fields actively consumed by `src/` code that **never appear** in the
template OR in `docs/RESEARCHER_GUIDE.md` §8:

| Template path | Reader | Behavior when blank |
|---|---|---|
| `researcher.affiliation` | `synthesis/latex.py:172` | Poster author block left empty. (Note: template has `researcher.institution` instead — see §F type/name drift.) |
| `researcher.expertise_level` | `router.py:341`, `server.py:2643` | Defaults to `"intermediate"`. No way for the researcher to set it without hand-editing — wizard doesn't ask. |
| `runtime.cluster_defaults` | `exec/cluster.py:64`, `server.py:1555-1556` | `sys_cluster_submit` requires this for SLURM jobs; entire SLURM surface is undocumented in the template. |
| `runtime.allow_arbitrary` | `exec/tasks.py:116` | bool default false. |
| `runtime.command_allowlist` | `exec/tasks.py:118` | list default empty. |
| `runtime.allow_shell_meta` | `exec/tasks.py:130` | bool default false. |
| `runtime.max_cpu_seconds` | `exec/tasks.py:176` | int default None (no limit). |
| `runtime.max_memory_mb` | `exec/tasks.py:177` | int default None. |
| `runtime.max_file_size_mb` | `exec/tasks.py:178` | int default None. |
| `research_goal.primary_question` | `audit/preregistration.py:208`, `synthesis/dashboard.py:751,779,1344` | Falls back to `research_question` (also undocumented) or `""`. |
| `research_goal.design` | `audit/preregistration.py:211`, `audit/prose_quality.py:423` | `"(unset)"`. |
| `research_goal.background` | `synthesis/latex.py:207`, `synthesis/dashboard.py:772` | placeholder text. |
| `research_goal.measurement_instrument` | `audit/preregistration.py:236` | empty. |
| top-level `domain` | `router.py:334`, `prose_quality.py:422` | `""`. |
| top-level `research_question` | `router.py:336-337`, `audit/preregistration.py:207` | `""`. |
| top-level `authors` | `state/config.py:368` | empty list — written by `collab.py` but undocumented for users editing by hand. |

The `runtime.*` exec safety fields are the most consequential. The
template silently invites a researcher to do `python_exec` /
`shell_exec` work without surfacing that there are CPU / memory /
allowlist guardrails they could (and probably should) tune.

Severity HIGH because (a) `runtime.command_allowlist` is a safety
surface and users who don't know about it can't tighten it; (b) the
`research_goal.*` extension fields are read by audits + synthesis but
researchers have no way to know to set them. Suggested target:
v1.9.3 for documenting in the template + RESEARCHER_GUIDE, v1.11.0
for any new validation.

---

## E. Enum unreachable / undocumented values

| Field | Template enum | Code-handled values | Notes |
|---|---|---|---|
| `interaction.autonomy_level` | `manual | supervised | autopilot | coaching` | `manual | supervised | autopilot` (no branch on `coaching`) | `coaching` is in the template + START.md doesn't list it. Either wire it (gate `sys_coaching_replay` to coaching mode) or remove from template. |
| `interaction.quality_gate_policy` | `enforce | allow_override | warn_only` | all 3 handled | OK |
| `interaction.ambiguity_posture` | `ask_when_uncertain | take_best_default` | parsed but no caller branches on it | unreachable behaviour — no code reads the returned `ambiguity_posture` from `get_interaction_policy`. |
| `gate_strictness` | `light | normal | strict | auto` | all 4 handled in `resolve_gate_strictness` | OK in isolation, but the path bug (§B) means it's never reached. |
| `project_tier` | `throwaway | sketch | production` | all 3 handled in `project_tier_strictness` | path bug (§B). |
| `model_profile` | `small | medium | large` | all 3 handled (`router.py:1290-1292`) | OK. `_read_model_profile` reliability path is broken (§B). |
| `writing_preferences.citation_style` | `apa | vancouver | acm | ieee | nature` | none read from config | `synthesize.py` hard-codes `"vancouver"` as the function default. The template's `apa` default is never applied. |
| `writing_preferences.venue_template` | `nature | science | nejm | cell | ieee_conf | neurips | acl | plos | generic_two_column | generic_thesis` | all 10 handled (`typst.py:166-167` whitelist) | OK. Falls back to `generic_two_column` if unknown. |
| `writing_preferences.pdf_compile_engine` | `typst | latex | both` | none read | dead enum. |
| `research_goal.output_types` | `paper | abstract | poster | dashboard | report | exploratory` | none read | dead enum. |

Severity MEDIUM. Suggested target: v1.9.3 for doc fix (remove
`coaching` until wired, document `ambiguity_posture` as advisory-only
or delete), v1.11.0 to wire the dead enums.

---

## F. Type drift + naming drift

| Field | Template | Code expects |
|---|---|---|
| `researcher.institution` | `str ""` | Template uses `institution`, but `synthesis/latex.py:172` reads `researcher.affiliation`. The poster author affiliation always renders blank for the average user. |
| `runtime.shared_server` | `bool False` | matches |
| `tool_stack.preferred_languages` | `list ["python", "R"]` | unused, but type would be `list[str]` |
| `api_keys.*` | `str ""` | matches; consumers tolerate empty |
| `research_goal.output_types` | `list []` | matches type expectation in `validate_config` (truthy check) |

No bracket-access (`config["foo"]`) crashes were found — every reader
uses `.get()` with `{} or {}` fallback, so absent fields don't blow
up. The only type-shaped bug is the `institution` vs. `affiliation`
field-name drift.

Severity LOW. Suggested target: v1.9.3 — rename `affiliation` to
`institution` in `latex.py:172` (one-line fix) OR add an
`institution` fallback so both work.

---

## G. Cross-field interactions not enforced

Template comments + RESEARCHER_GUIDE imply several relationships
between fields. None are enforced.

1. **`project_tier=throwaway` → `gate_strictness=light`**: template
   comment lines 62–63 promise this mapping is automatic. It's not.
   `project_tier_strictness()` returns the mapping, but no caller
   uses it to override `gate_strictness`. Researchers must set both
   knobs in lockstep, defeating the point of the tier abstraction.
   (Compounded by §B path bug.)
2. **`autonomy_level=coaching` → surface coaching artifacts**: template
   comment lines 31–36 say coaching mode triggers pedagogical preludes
   + `sys_coaching_replay` per session. No code branches on the value.
   `sys_coaching_replay` is always available regardless of autonomy.
3. **`gate_strictness=auto` + `tool_rigor_signals_scan`**: documented
   pathway works (in `resolve_gate_strictness`), but path bug §B
   means the `auto` branch is the *only* one ever reached, since
   the config never loads.
4. **`pdf_compile_engine=both`**: template advertises a `both` value
   that would compile via both engines for cross-check. No code reads
   the field, so `both` is just an aspirational comment.
5. **`runtime.shared_server=true` → background-task preference**: read
   by `router.py:344` into the routing context, but only echoed back;
   I could not find a downstream consumer that gates execution
   strategy on it. `runtime.long_running_threshold_seconds` is also
   only echoed.
6. **`validate_config` (sys_config_validate)** checks **presence** of
   5 fields but not enum membership for any of them, so a researcher
   typing `model_profile: medium-plus` will pass validation and
   silently fall back to `medium`.

Severity MEDIUM. Suggested target: v1.9.3 to either wire the
documented behaviours or strip the misleading comments; v1.11.0 to
extend `validate_config` to check enum membership.

---

## H. Trivial fixes applied

None applied — every finding here touches semantics (path corrections,
test fixtures that codify a bug, doc claims about wiring that doesn't
exist). Per audit rules I do not modify production code logic; doc-only
edits would have to either (a) admit the wiring is missing or (b)
lie. Neither is suitable as a one-line trivial fix.

The two test files at `tests/tools/test_v1_5_1.py:101` and
`tests/unit/test_v151.py:200` should grow assertions for the real
`inputs/researcher_config.yaml` path once §B is fixed. Listed here as
follow-up, not applied.

---

## Summary tally

| Severity | Count | Areas |
|---|---|---|
| CRITICAL | 1 | §B — 3 file paths broken; v1.5.1 features silently inert |
| HIGH | 2 | §A wizard/template/docs disagree; §D undocumented runtime/research_goal extension fields |
| MEDIUM | 4 | §C dead template fields; §E unreachable enums; §G cross-field interactions not enforced; §F minor type/name drift |
| LOW | 0 | — |

Net: the researcher_config schema is the most drifted surface this
audit touched. The template, the wizard, the docs, and the consumers
each tell a different story; the v1.5.1 tier/strictness features ship
broken in real projects (only the test fixtures look correct because
they sidestep the layout). Fixing §B is a 3-line patch that recovers
behaviour for every project initialised since v1.5.1.
