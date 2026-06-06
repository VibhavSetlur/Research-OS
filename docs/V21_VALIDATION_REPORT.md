# Research-OS v2.1.0 Validation Report

**Branch:** feat/v2.1.0
**Date:** 2026-06-06
**Validation pass:** 10 perspectives × full envelope/protocol/router audit + 20-prompt random-routing matrix
**Author of synthesis:** validation harness

---

## 1. Executive Summary

### 1.1 Headline numbers

| Metric | Value | v2.1.0 GREEN target | Status |
|---|---|---|---|
| Average final_rating across 10 perspectives | **5.54 / 10** | ≥ 8.5 | **FAIL** |
| Worst perspective (pi_review on theory_math_proof) | **5.0 / 10** | ≥ 7.5 | **FAIL** |
| Naive-AI perspective | **5.5 / 10** | ≥ 8.0 | **FAIL** |
| Avg system-consistency rating | **4.9 / 10** | ≥ 9.0 | **FAIL** |
| Random-prompt routing accuracy (quality ≥ 7) | **65%** (13/20) | ≥ 90% | **FAIL** |

**Verdict:** v2.1.0 is NOT release-ready against the GREEN gate. The envelope shape ships but is structurally hollow on the success path; routing misfires on canonical phrases the docs themselves recommend; the version was never bumped, so `ro_version` is a lie.

### 1.2 10 × 6 grade matrix

| Perspective | ai_tool_clarity | ai_routing | ai_error_quality | ai_envelope_consistency | researcher_onboarding | researcher_iteration |
|---|---|---|---|---|---|---|
| naive_ai (biology_rnaseq) | 6 | 7 | 6 | 4 | 7 | 6 |
| experienced_ai (humanities) | 7 | 6 | 7 | 4 | 7 | 6 |
| undergrad (qualitative) | 5 | 8 | 4 | 3 | 8 | 5 |
| grad_dissertation (engineering) | 6 | 5 | 7 | 4 | 7 | 6 |
| postdoc_audit (flawed biology) | 6 | 5 | 8 | 4 | 7 | 6 |
| pi_review (theory_math) | 6 | 6 | 4 | 3 | 5 | 5 |
| industry (rapid prototyping) | 6 | 4 | 6 | 3 | 7 | 5 |
| methodology_auditor (biology) | 6 | 6 | 5 | 4 | 7 | 7 |
| reproducibility (engineering) | 6 | 8 | 5 | 4 | 7 | 6 |
| maintainer (core API trace) | 7 | 8 | 5 | 4 | 8 | 7 |
| **Column average** | **6.1** | **6.3** | **5.7** | **3.7** | **7.0** | **5.9** |

**Per-perspective final ratings:** 5.5 / 6.0 / 5.5 / 5.8 / 5.5 / 5.0 / 5.5 / 5.5 / 5.8 / 5.5 → **avg 5.54**.

System-consistency ratings: 5 / 5 / 5 / 5 / 5 / 4 / 5 / 5 / 5 / 5 → **avg 4.9 / 10**.

### 1.3 Top 20 friction points by frequency (≥2 perspectives)

Counting perspectives that flagged the same root issue (regardless of file path).

| Rank | Issue | # of perspectives | Severity (max across perspectives) |
|---|---|---|---|
| 1 | `__version__` still `2.0.0`; `ro_version` envelope lies on every response | **10/10** | block / critical |
| 2 | v2.1.0 envelope fields (`next_recommended_call`, `tier_transition`, `tokens_estimate`, `audit_findings`) defaulted but never populated by handlers | **10/10** | block / critical |
| 3 | Error `next_action` strings reference non-existent tool names (`sys_tools_list`, `sys_protocols_list`) | **9/10** | block / critical |
| 4 | `--ide none` is silently rejected and falls back to `claude` with a warning | **9/10** | low / minor |
| 5 | `templates/AGENTS.md` teaches legacy `tool_plan_turn` / `tool_plan_advance` / `tool_plan_clear` names | **8/10** | high / warn |
| 6 | `tier_transition` shape contradiction: contract says string `"tier_a -> tier_b"`, code returns dict `{from, to}` | **7/10** | high |
| 7 | Handler-level `except Exception: return _error(str(e))` swallows typed exceptions, leaving `why=null` and `next_action=null` on common errors (e.g. protocol-not-found) | **7/10** | high |
| 8 | dashboard_v2 → dashboard_app rename is half-done: `renderer:'v2'` in payload, `<meta ro-renderer content='v2'>` in HTML, `MANIFEST.json` and tool description still say v2 | **6/10** | medium |
| 9 | Pack tools (engineering / humanities / qualitative / wet_lab / theory_math) use local `_ok()`/`_err()` that return the v2.0 `{status, data}` shape, bypassing the v2.1.0 envelope contract entirely | **5/10** | high |
| 10 | Did-you-mean ranking is purely difflib-based (no namespace prefix boost), suggests semantically wrong neighbors | **5/10** | medium |
| 11 | Router misroutes prompts the docs themselves recommend (`fix my workspace`, `is this paper ready`, `pick a method`, generic "draft the paper" in humanities) | **5/10** | high / block |
| 12 | `tool_route` handler doesn't promote `recommended_action` to envelope `next_recommended_call` (the field's biggest natural producer) | **5/10** | high |
| 13 | `tool_protocols_list` returns `tier: null` for all 153 protocols (Phase-8 placeholder still in `protocol.py:630, 698`) | **3/10** | high |
| 14 | Causal-language detector in `audit/prose_quality.py` defaults `is_observational=False`, so RNA-seq papers with "this proves X causes Y" pass `ok:true` | **2/10** (postdoc + methodology_auditor) | block |
| 15 | `tool_synthesize(output_type='paper')` on empty workspace returns `status='success'` with fabricated citations because step-completeness vacuously passes on zero steps | **2/10** (naive_ai + undergrad) | critical |
| 16 | `coaching` autonomy mode documented in `templates/AGENTS.md` and `researcher_config.yaml` but ZERO branching code (only `autopilot` is implemented) | **2/10** | high |
| 17 | `pre_submission_checklist` hardcodes empirical-paper assumptions (CRediT / ARRIVE / IRB / DPI / `synthesis/paper.md`), breaks for theory_math + humanities | **2/10** | critical |
| 18 | `sys_active_tools(<protocol>)` returns only generic core tools; doesn't surface pack-specific tools or prerequisite-protocol shortcuts | **3/10** | high |
| 19 | `RoError` defined as the v2.1.0 WHAT/WHY/NEXT primitive but raised by ZERO callers under `src/` — dispatcher only catches it for `KeyError`/`TypeError`/`FileNotFoundError` | **3/10** | high |
| 20 | `complexity: quick` mode documented in `TOOLS.md` but absent from `AI_GUIDE.md` and `RESEARCHER_GUIDE.md` — the cheap-throwaway lever is invisible | **2/10** | major |

### 1.4 Top 20 consistency findings by frequency

| Rank | Finding | # perspectives | Kind |
|---|---|---|---|
| 1 | `__version__` 2.0.0 on v2.1.0 branch; envelope `ro_version` lies | 10 | envelope |
| 2 | v2.1.0 envelope fields never populated by handlers | 10 | envelope |
| 3 | `sys_tools_list` / `sys_protocols_list` referenced in error/help/advice strings but not registered | 9 | tool_ref |
| 4 | `templates/AGENTS.md` ships deprecated `tool_plan_turn` / `tool_plan_advance` / `tool_plan_clear` | 8 | tool_ref / naming |
| 5 | `tier_transition` type contradiction (contract string vs implementation dict vs envelope null) | 7 | envelope |
| 6 | Handler-level broad `except Exception` swallows typed errors before dispatcher catches | 7 | error |
| 7 | dashboard_v2 → dashboard_app rename half-done across `renderer`, HTML meta, MANIFEST, tool desc | 6 | naming |
| 8 | Pack tools return v2.0 envelope shape `{status, data}` — entire pack surface bypasses v2.1.0 contract | 5 | envelope |
| 9 | Router decompositions / tool descriptions still publish legacy tool names (`tool_audit_synthesis`, `tool_audit_step_literature`, etc.) | 5 | tool_ref |
| 10 | Router misroutes canonical doc-recommended phrases | 5 | protocol_ref |
| 11 | `tool_route` doesn't lift `recommended_action` to envelope `next_recommended_call` | 5 | envelope |
| 12 | `--ide none` silently coerces to `claude` | 9 | workspace |
| 13 | `tool_protocols_list` always returns `tier: null` despite YAML carrying tier | 3 | protocol_ref |
| 14 | `payload.status` duplicates envelope-level `status`; `payload.tier_transition` duplicates envelope `tier_transition` (both null) | 3 | envelope |
| 15 | Pack protocols mis-scope-tagged (`pre_submission_checklist` = humanities, `audit_and_validation` = qualitative, `clinical_trials` = qualitative, `data_management_plan` = qualitative) | 2 | protocol_ref |
| 16 | `audit_findings` duplicated as envelope field AND payload field (different namespace, same data) | 2 | envelope |
| 17 | Protocol count drift (88 / 114 / 117 / 118 / 153 — five different numbers across docs, code, memory) | 2 | protocol_ref |
| 18 | docs/AI_GUIDE.md has zero "v2.1" mentions; new envelope fields invisible to the AI that reads it | 4 | naming / docs |
| 19 | `tool_route alternatives[]` returns entries with `primary_protocol: null`, only `why_matched` populated | 2 | envelope |
| 20 | `assets/js/MANIFEST.json` still references `dashboard_v2` (2 places) | 5 | naming |

### 1.5 Random-prompt routing accuracy

20 prompts tested across all 10 L1 intent classes.

| Quality bucket | Count | % | Examples |
|---|---|---|---|
| 9-10 (bullseye) | 6 | 30% | "write the methods section", "systematic review of papers on glycolysis", "what should I do next?", "make me a paper", "make a slide", "systematic review of nursing methodology" |
| 7-8 (good with minor friction) | 7 | 35% | "RNA-seq DGE 4-vs-8", "I have data, help" (correct ask_user), "How do I write the paper part", "Can you make the chart look better", "compare 3 ML algos on MNIST", "How do I cite a paper I haven't verified", "I don't know how to start" |
| 5-6 (mediocre — wrong protocol or major friction) | 0 | 0% | — |
| 3-4 (bad — dead-end or misroute) | 5 | 25% | "Fix the bug", "Run the analysis", "Where do I put my Excel sheet", "Make me a poster" (routed to paper), "I'm reviewing a paper for a journal" |
| 1-2 (broken) | 2 | 10% | "I have lab notebook PDFs from 2018-2022, can you help me find the right ones" (no match), "I want to fork an existing pipeline a former student left" (no match) |

**Pass rate (≥7):** 13/20 = **65%**. Target was ≥90%. **FAIL.**

### 1.6 Worst-3 prompts

| Prompt | Quality | Failure mode |
|---|---|---|
| "I'm reviewing a paper for a journal, walk me through structured feedback" | **2/10** | guidance/quick_paper_review is a perfect fit with `tool_quick_review` shortcut, but trigger-substring matching misses the phrase. Router returns null and asks a wrong disambiguation ("Final deliverables vs Methodology choice") that doesn't relate to peer review. |
| "I have lab notebook PDFs from 2018-2022, can you help me find the right ones" | **3/10** | Semantic top-pick `wet_lab/audit/wet_lab_reproducibility_audit` is rejected by router-index allowlist, then trigger fallback finds nothing. The right target is discover/intake or literature/search; researcher gets the generic 10-class L1 menu. |
| "I want to fork an existing pipeline a former student left" | **3/10** | `guidance/mid_pipeline_entry` is the semantic fit but its trigger list misses "fork", "inherit", "former student", "took over". Router returns no match, AI dead-ends into generic L1 disambiguation. |
| (4-way tie) "Where do I put my Excel sheet" / "Make me a poster" / "Fix the bug" / "Run the analysis" | **3-4/10** | "Make me a poster" routed to `synthesis_paper` over `synthesis_poster` despite the word "poster" appearing literally (semantic 0.6758 vs 0.6722 margin). The others surface ask_user but with too much menu noise for very short prompts. |

---

## 2. Per-perspective distillation

**naive_ai (biology_rnaseq) — 5.5/10.** First-time AI client can boot, route, and walk canonical bio prompts; new envelope keys are present. But naive-AI confidence drops fast: `ro_version` reports 2.0.0, `tier_transition`/`tokens_estimate` never populated, `tier_transition` shape disagrees with contract, `tool_synthesize` on empty workspace fabricates 36 citation keys with `status='success'`, dashboard rename is half-done, templates/AGENTS.md teaches legacy names. Worst friction: synthesize-on-empty-workspace silently producing hallucinated artifact endorsed by `status:success` — exactly the failure mode RO exists to prevent.

**experienced_ai (humanities_close_reading) — 6.0/10.** Envelope SHAPE ships but CONTENT mostly doesn't. `ro_version='2.0.0'`, `tokens_estimate` always 0, `next_recommended_call` null even on tool_route. Every domain pack returns v2.0 `{status, data}`. Routing fails for humanities: "draft the paper" → IMRAD synthesis_paper, "explicate this poem" → resolved_level=0 despite verbatim trigger. dashboard rename half-done. AGENTS.md teaches legacy plan API. Did-you-mean works well; humanities essay scaffold + typst PDF both produce correctly when routing happens to land. Foundation is sound; the work to fill fields is mechanical not architectural.

**undergrad (qualitative_interviews) — 5.5/10.** Init wizard is genuinely good — scaffolded folders, AGENTS.md, GETTING_STARTED.md, `tool_intake_autofill` all work; semantic routing maps "I have 4 interview transcripts" to qualitative_research correctly. But: `ro_version='2.0.0'`; new envelope fields vestigial; structured WHAT/WHY/NEXT bypassed by 7+ handlers; dispatcher's own NEXT directives reference non-existent `sys_tools_list`/`sys_protocols_list`; `sys_active_tools(qualitative_research)` returns ZERO pack tools; `coaching` autonomy mode (literally targeted at undergrads) is vaporware with zero branching code. The scaffolding works but the moment they hit any error the system promises better than it delivers.

**grad_dissertation (engineering_benchmark) — 5.8/10.** Pre-registration freeze + sha256 + OSF handoff is genuinely dissertation-grade. WHAT/WHY/NEXT through dispatcher exceptions is excellent. But: envelope flagship fields empty; `ro_version` lies; engineering pack ships its own `_ok/_err` bypassing v2.1.0; AGENTS.md teaches deprecated plan API; routing fails for natural "compare merge sort vs quicksort" despite literal trigger; sys_protocols_list/sys_tools_list ghost references; engineering pipeline never auto-invokes reproducibility audit.

**postdoc_audit (flawed_biology_fixture) — 5.5/10.** Catches lab-bookkeeping flaws (stub READMEs, ungrounded numbers, missing figures). Misses inferential flaws a real postdoc would catch first: causal-language detector defaults `is_observational=False`, so "this proves treatment X causes tumor suppression" passes `ok:true`. Selection bias has no protocol. Outer envelope `status:success` masks `payload.status:error` from audits. `audit_findings:[]` stays empty when findings exist. Useful as bookkeeper, unsafe as methodology gatekeeper.

**pi_review (theory_math_proof) — 5.0/10.** Lowest score. Semantic router gets "is this ready to submit?" to pre_submission_checklist correctly — but that protocol is hardwired to empirical-paper assumptions (CRediT, ARRIVE, figure DPI, IRB, `synthesis/paper.md` prereq); theory_paper_structure writes to `workspace/papers/<slug>/*.tex` and is terminal, so no bridge. Walking the gate produces 70% YELLOW items that are category errors, training the PI to ignore the verdict. theory_math pack protocol references list non-existent tool names (`tool_theory_lean_check` vs real `tool_theory_math_lean_check`). Bones are there; integration polish is not.

**industry (rapid_prototyping) — 5.5/10.** v2.1.0 changes land structurally — dashboard_app rename clean in user-facing docs, envelope helper exists, dispatcher catches produce WHAT/WHY/NEXT. For a time-constrained industry researcher: 15+ live tools bypass the envelope via `return _text(raw_dict)`; new fields never populated by ANY handler; `ro_version='2.0.0'`; router misroutes "fix my workspace" (verbatim from GETTING_STARTED.md!) to writing/writing_citations; `complexity: quick` is undocumented in the guides researchers actually read. Hitting one of the misroutes burns the time advantage you came for.

**methodology_auditor (biology) — 5.5/10.** Strong protocol library for biology rigor; WHAT/WHY/NEXT is the right shape. But: `ro_version='2.0.0'`; `tool_route` doesn't lift tier_transition/next_recommended_call to envelope; `tier_transition` documented as string but code returns dict; error WHY/NEXT null on protocol-not-found; suggestions reference ghost tools `sys_protocols_list`/`sys_tools_list`. Several biology protocols mis-scope-tagged (`pre_submission_checklist` = humanities, `audit_and_validation` = qualitative). Common auditor opening lines fail to route. Wet_lab pack reproducibility audit doesn't get reached for natural prompts.

**reproducibility (read_p4_engineering) — 5.8/10.** Surface routing + pack composition work; new dispatcher error envelope is a clear improvement. For a repro reviewer trying to verify "can someone redo this?": ro_version lies; envelope-level audit_findings/next_recommended_call/tier_transition/tokens_estimate stay null even when matching payload data is present; pack tools bypass envelope; dispatcher's WHAT/WHY/NEXT next_action strings point at two tools that do not exist. Engineering pipeline lacks any wired reproducibility audit. A reviewer cannot mechanically validate v2.1.0 contract compliance from the responses — the property repro reviewers care about most.

**maintainer (trace_core_api_refactor) — 5.5/10.** The v2.1.0 envelope shape and tool_route signature are named in CONTRACT.md A.6.1/A.7, but the implementation, the contract, and the consumer-facing docs each describe a different v2.1.0. Reproduced infinite-loop trap: call `tool_audt` → "did you mean... Call `sys_tools_list`" → unknown tool → suggests `sys_tools_list` again. v2.1.0 envelope regression test green-lights `tool_route` called with wrong kwarg (`request=` vs `prompt=`) and non-existent `sys_protocols_list` because it only checks key presence. AI_GUIDE/TOOLS/RESEARCHER_GUIDE have zero "v2.1" mentions — the entire AI-DX value-add is invisible to the AI driving the system. tool_route's signature has exactly one in-tree caller plus 4 tests so a refactor there is locally safe; the bigger surprise is that the contract-stable envelope shape is, at runtime, a contract-stable set of default values.

---

## 3. Cross-perspective themes (findings in ≥3 perspectives)

### Theme 1: The envelope is a Potemkin village (10/10 perspectives)

`ro_version` reports `"2.0.0"` because `src/research_os/__init__.py`, `pyproject.toml`, and `CITATION.cff` were never bumped. CONTRACT.md A.6.1 promises `ro_version` matches `__version__`. `research-os doctor` cheerfully reports "All three agree on v2.0.0" — the version-consistency gate enforces "they say the same number" not "they say the right number".

The four new MAJOR-stable envelope fields (`next_recommended_call`, `tier_transition`, `tokens_estimate`, `audit_findings`) are added with defaults in `envelopes.py` but NO handler ever populates them above defaults. Grep confirms zero `tokens_estimate=`, `next_recommended_call=`, `tier_transition=` call sites outside `envelopes.py` itself, plus one in `audit_gates.py`. The router computes `tier_transition` as `{from, to}` dict and writes it to `payload.tier_transition`, while CONTRACT advertises envelope-level `tier_transition` as a string `"tier_execute -> tier_synthesize"` — three incompatible shapes for one field.

A v2.1-aware client (AI or human) reads the new envelope fields and sees null/empty/0 on every call. The v2.1.0 wire format is bigger; the v2.1.0 semantics are not actually present.

### Theme 2: Ghost tools in the recovery path (9/10 perspectives)

The dispatcher's own WHAT/WHY/NEXT recovery hints reference tools that do not exist:
- `src/research_os/server/dispatch.py:115` → `sys_tools_list` (real: `tool_tools_list`)
- `src/research_os/server/dispatch.py:160` → `sys_protocols_list` (real: `sys_protocol_list`)
- `src/research_os/server/envelopes.py:127` (docstring) → `sys_protocols_list`
- `src/research_os/tools/actions/protocol.py:358` → `sys_protocols_list`

An AI obediently calling these suggestions hits a second unknown-tool error pointing at the same dead name. The maintainer perspective reproduced an infinite loop. The investment in WHAT/WHY/NEXT is undone by a 4-line typo.

### Theme 3: Pack tools live outside the contract (5/10 perspectives)

Every domain pack (`research_os_humanities`, `research_os_qualitative`, `research_os_wet_lab`, `research_os_theory_math`, `research_os_engineering`) defines local `_ok()`/`_err()` helpers that return the v2.0 `{status, data}` shape. None include `payload`, `audit_findings`, `next_recommended_call`, `tier_transition`, `tokens_estimate`, or `ro_version`. CONTRACT.md A.6.1 makes envelope shape MAJOR-stable; 13+ pack tools across 5 packs silently violate it. Phase-2 audit explicitly scoped only the 13 core handler files (212 handlers); pack tools were left out of the migration.

### Theme 4: Handler-level broad except swallows typed errors (7/10 perspectives)

`_handle_sys_protocol_get` and ~6 sibling handlers wrap their bodies in `except Exception as e: return _text(_error(str(e)))`. This swallows `FileNotFoundError`/`KeyError`/`TypeError` BEFORE the dispatcher's typed catches at `dispatch.py:121-169` can render structured WHAT/WHY/NEXT. Result: a typoed protocol name returns the full message jammed into `payload.what` with `payload.why=None` and `payload.next_action=None`. The Phase-3 RoError primitive is bypassed for the most common errors a beginner hits.

### Theme 5: Routing misfires on canonical doc-recommended phrasing (5/10 perspectives)

The router fails for prompts the docs explicitly recommend:
- `"fix my workspace"` (verbatim from GETTING_STARTED.md "When things go wrong" table) → `writing/writing_citations`. Probable cause: trigger-substring matching breaks because `my` between `fix` and `workspace` isn't in the literal trigger list.
- `"is this paper ready"` (literal trigger of `audit/audit_and_validation` per `_router_index.yaml:1142`) → `guidance/session_boot`
- `"pick a method"` / `"choose a method"` → `guidance/analysis_plan` (not `methodology/research_method` — defeats the mandatory anti-pattern)
- `"explicate this poem"` (verbatim trigger of humanities/close_reading) → resolved_level=0
- `"compare merge sort vs quicksort"` (literal `compare X vs Y` trigger) → primary_protocol=None
- "draft the paper" in humanities-tagged project → IMRAD `synthesis/synthesis_paper` (router has no pack-context bias)
- "make me a poster" → `synthesis_paper` not `synthesis_poster` (0.0036 semantic margin despite literal word match)

### Theme 6: `templates/AGENTS.md` teaches deprecated names (8/10 perspectives)

The wizard's `templates/AGENTS.md` — copied into every new project — instructs the AI to call `tool_plan_turn` / `tool_plan_advance` / `tool_plan_clear` (lines 53, 55, 63, 134, 175, 212). `docs/AI_GUIDE.md` / `CONTRACT.md` / `TOOLS.md` all say the canonical names are `tool_plan(operation='turn'|'advance'|'clear')`. Aliases still dispatch, but every new project's resident AI prompt teaches the deprecated form first. The AI loads this file every turn — the contradiction is constantly reinforced.

### Theme 7: `--ide none` is rejected (9/10 perspectives)

`research-os init --ide none` is silently rejected with `Unknown IDE(s): none. Falling back to 'claude'.` and writes a Claude MCP config anyway. A user explicitly opting out of IDE wiring (CI, headless, multi-user HPC, reproducibility baseline) gets opt-in IDE wiring. Cosmetic but universally noticed and impossible to work around without manually deleting files after init.

### Theme 8: dashboard_v2 → dashboard_app rename is half-done (6/10 perspectives)

Module renamed, function renamed, internal docs swept. But:
- `dashboard_app.py:1247` docstring still says `renderer='v2' discriminator`
- `dashboard_app.py:1347` HTML `<meta name='ro-renderer' content='v2'>`
- `dashboard_app.py:1372` payload returns `renderer: 'v2'`
- `dashboard_app.py:1388` error fallback `renderer='v2'`
- `assets/js/MANIFEST.json:2,12` says "inlined by dashboard_v2"
- `server/tool_definitions/synthesis.py` `tool_dashboard.description` says "v2 single-page-app"
- 13 archived docs in `docs/v2_handoff/` and `docs/audit_v1.9.2/` still reference `dashboard_v2`

Pick one: rename the discriminator everywhere or drop the rename advertising from the v2.1.0 prelude.

---

## 4. v2.1.0 fix list (Phase 14 — must ship before tagging)

Ordered by severity × cross-perspective frequency. These items block v2.1.0 GREEN.

### FIX-1: Bump `__version__` to 2.1.0 (or 2.1.0-dev) [10/10 perspectives, BLOCK]
- **Where:** `src/research_os/__init__.py:8`, `pyproject.toml:7`, `CITATION.cff:7`
- **Fix:** Bump all three files in one commit per CLAUDE.md hard invariant #3. Add a CI/preflight check that asserts CHANGELOG.md's top version header matches `__version__`. Add a doctor check that warns when running from a `feat/vX.Y.*` branch with `__version__ < X.Y.0`.
- **Sources:** all 10 perspectives

### FIX-2: Wire envelope-level fields in core handlers [10/10, BLOCK]
- **Where:** every `_success(res)` call site, especially `meta_routing.py:_handle_tool_route` / `_handle_sys_boot` / `_handle_sys_protocol_get`; `audit_core.py:_handle_tool_audit_quality_full`
- **Fix:**
  - `tool_route`: pass `next_recommended_call=res['recommended_action']`, `tier_transition=_to_string(res['tier_transition'])` (serialize dict to `"from -> to"` string at envelope boundary)
  - `audit_quality_full`: branch on `legacy.status` — return `_error(...)` when blockers present; populate `audit_findings = legacy['blockers'] + legacy['warnings']`; set `next_recommended_call = legacy['advice']`
  - `sys_boot`: populate `tier_transition` from state, `tokens_estimate` from `len(json.dumps(payload))//4`
  - Add a dispatcher post-hook OR a transparent lifter inside `_success`: if payload contains `recommended_action`, mirror to envelope `next_recommended_call`; if payload contains `tier_transition`, serialize and lift
- **Sources:** all 10 perspectives
- **Add regression test:** assert non-default values on the canonical happy path of each high-traffic handler

### FIX-3: Replace ghost tool references in error/help/advice strings [9/10, BLOCK]
- **Where:** `dispatch.py:115` (`sys_tools_list` → `tool_tools_list`), `dispatch.py:160` (`sys_protocols_list` → `sys_protocol_list`), `envelopes.py:127` (docstring), `protocol.py:358`, `tests/unit/test_v210_envelope_shape.py:46,52`, `tests/unit/test_server.py:69`
- **Fix:** `sed -i 's/sys_tools_list/tool_tools_list/g; s/sys_protocols_list/sys_protocol_list/g'`. Add a preflight check that every tool name appearing in an error/advice string must be a registered key in `_HANDLERS` or `_DEPRECATED_ALIASES`.
- **Sources:** 9 perspectives

### FIX-4: Resolve `tier_transition` shape contradiction [7/10, HIGH]
- **Where:** `docs/CONTRACT.md:189` vs `src/research_os/tools/actions/router.py:266` vs `state/tier_state.py:114-128` vs envelopes.py default
- **Fix:** Pick one shape. Recommendation: emit string `"from -> to"` at envelope-level (matches contract); keep dict shape on payload for structured callers and document it in CONTRACT.md. Align tests.
- **Sources:** 7 perspectives

### FIX-5: Update `templates/AGENTS.md` to canonical v2 tool names [8/10, HIGH]
- **Where:** `templates/AGENTS.md:53, 55, 63, 134, 175, 212`
- **Fix:** Replace `tool_plan_turn` → `tool_plan(operation='turn')`, `tool_plan_advance` → `tool_plan(operation='advance')`, `tool_plan_clear` → `tool_plan(operation='clear')`. Also replace `tool_dashboard_create` → `tool_dashboard(operation='create')`, `tool_audit_step_completeness` → `tool_audit(scope='step', dimension='completeness')`. Add a v2.1.0 envelope-fields subsection naming `audit_findings` / `next_recommended_call` / `tier_transition` / `tokens_estimate` / `ro_version` so the AI knows to parse them. Add a CI lint that fails the build when `templates/AGENTS.md` mentions any tool name in `_DEPRECATED_ALIASES`.
- **Sources:** 8 perspectives

### FIX-6: Narrow or remove handler-level `except Exception` [7/10, HIGH]
- **Where:** `server/handlers/meta_routing.py:96-97, 130-131`, plus ~5 sibling handlers (grep `except Exception as e:.*_error`)
- **Fix:** Remove the broad catch so `FileNotFoundError`/`KeyError`/`TypeError` bubble to `dispatch.py:121-169`. Where handlers genuinely need their own try/except, raise `RoError(what, why, next_action)` explicitly instead of `_error(str(e))`. Add a unit test asserting `payload.why` and `payload.next_action` are non-null on a protocol-name typo.
- **Sources:** 7 perspectives

### FIX-7: Migrate pack tools to the v2.1.0 envelope [5/10, HIGH]
- **Where:** `src/research_os_humanities/tools.py:26`, `src/research_os_qualitative/tools.py`, `src/research_os_wet_lab/tools.py`, `src/research_os_theory_math/tools.py`, `src/research_os_engineering/tools.py:11-46`
- **Fix:** Export `_success` / `_error` from `research_os.server.envelopes` as a stable plugin surface; have each pack import and use them in place of local `_ok` / `_err`. Add a registry-walking test that dispatches every registered tool with dummy args and asserts the envelope keys exist.
- **Sources:** 5 perspectives

### FIX-8: Complete dashboard_v2 → dashboard_app rename [6/10, MED]
- **Where:** `dashboard_app.py:1247, 1347, 1372, 1388` (renderer literal, HTML meta, payload, fallback), `assets/js/MANIFEST.json:2, 12`, `server/tool_definitions/synthesis.py` (tool_dashboard description)
- **Fix:** Replace `'v2'` renderer literal with `'app'` (document the discriminator change in `MIGRATION_v2_0_to_v2_1.md`) OR keep `'v2'` and drop the rename advertising from CHANGELOG/CONTRACT. Either way: sweep `dashboard_app.py` for literal `'v2'` strings and update MANIFEST.json. Pick one — current state is the worst of both.
- **Sources:** 6 perspectives

### FIX-9: Fix `tool_protocols_list` tier field [3/10, HIGH]
- **Where:** `src/research_os/tools/actions/protocol.py:630, 698`
- **Fix:** Both sites contain literal `# Phase 8 will populate` placeholders that hardcode `tier=None`. Replace with `proto_data.get('tier')`. Add a test that at least 100 protocols return a non-null `tier` in `tool_protocols_list` output.
- **Sources:** 3 perspectives (high severity)

### FIX-10: Add user-facing docs for v2.1.0 envelope fields [4/10, MED]
- **Where:** `docs/AI_GUIDE.md`, `docs/TOOLS.md`, `docs/RESEARCHER_GUIDE.md`
- **Fix:** Add a "v2.1.0 response envelope" subsection to `AI_GUIDE.md` right after the session-pattern section. Document: which fields appear on every response, when to consume `next_recommended_call` vs re-route, how to handle `tier_transition`. Add a "WHAT/WHY/NEXT errors" subsection naming `RoError` and the `payload.{what, why, next_action}` shape. Add a "Quick mode" subsection covering `complexity: quick` trigger phrases.
- **Sources:** 4 perspectives (the AI/researcher-facing docs that the AI actually reads have zero "v2.1" mentions)

### FIX-11: Fix v2.1.0 envelope-shape regression test [maintainer, HIGH]
- **Where:** `tests/unit/test_v210_envelope_shape.py:46, 52`; `tests/unit/test_server.py:69-75`
- **Fix:** The test calls `tool_route` with kwarg `request=` (live handler reads `prompt=`) and references `sys_protocols_list` (non-existent). Both produce error envelopes with the right shape so the test passes — but it's not actually exercising the success path of those tools and shouldn't be cited as Wave-A coverage. Fix to use `prompt=` and `sys_protocol_list`; assert `env['status']=='success'` for representative calls; parametrize over live `_HANDLERS` keys so a typo in a test name fails fast.
- **Sources:** maintainer perspective (high impact — regression suite has a silent bug)

### FIX-12: Add pack-context bias to router scoring [5/10, HIGH]
- **Where:** `src/research_os/tools/actions/router.py` (semantic scoring)
- **Fix:** When `researcher_config.domain` (or detected pack) matches a candidate protocol's `scope_tags.domain`, boost score by ~10%. Add a fallback: when semantic top-1 confidence is below ~0.75 AND a literal trigger phrase from a candidate's `trigger:` block appears in the prompt, prefer the trigger match. This fixes "draft the paper" → IMRAD in humanities-tagged projects, "compare merge sort vs quicksort" misroute, "make me a poster" tying paper > poster on a 0.0036 margin.
- **Sources:** 5 perspectives

### FIX-13: Add missing router triggers for canonical doc-recommended phrases [5/10, BLOCK]
- **Where:** `src/research_os/protocols/_router_index.yaml`
- **Fix:** Add or normalize triggers so the following all resolve:
  - `"fix my workspace"` / `"fix this workspace"` / `"workspace is broken"` → `tool_workspace_repair` (normalize determiners `my`/`the`/`this`/`our` before trigger lookup)
  - `"is this paper ready"` / `"is this ready"` → `audit/audit_and_validation` (currently routes to `session_boot`)
  - `"pick a method"` / `"choose a method"` / `"which method"` → `methodology/research_method`
  - `"explicate this poem"` / `"explicate this stanza"` → `humanities/textual/close_reading` (verbatim trigger fails)
  - `"compare X vs Y"` / `"horse race between X and Y"` → `methodology/method_comparison`
  - `"fork a pipeline"` / `"inherited"` / `"took over from"` / `"former student"` → `guidance/mid_pipeline_entry`
  - `"reviewing a paper"` / `"journal review"` / `"structured feedback"` → `guidance/quick_paper_review`
  - `"lab notebook"` / `"pdfs from"` / `"find the right ones"` → `discover/intake` or `literature/search`
  - `"transcribe"` / `"find in archive"` / `"manuscript"` → `archival_research`
- **Sources:** 5 perspectives + 5 worst-of-20 prompts

### FIX-14: Strengthen empty-workspace gate on `tool_synthesize` [2/10, CRITICAL]
- **Where:** `tool_synthesize` handler
- **Fix:** Add `min_finalized_steps >= 1` precondition; if 0 finalized steps exist, raise `RoError(what='no steps to synthesize', why='workspace has zero finalized steps', next_action='run a step via tool_plan or tool_step_pipeline first')`. Or downgrade `status` to `'warning'` when `claim_grounding.status=='error'`. As shipped, calling `tool_synthesize(output_type='paper')` on a brand-new init returns `status='success'` with 36 fabricated citation keys and 137 ungrounded claims because step_completeness vacuously passes on zero steps.
- **Sources:** naive_ai, undergrad (critical severity)

### FIX-15: Causal-language detector defaults [2/10, BLOCK]
- **Where:** `src/research_os/tools/actions/audit/prose_quality.py:299` (`is_observational=False` default), `:461-490` (auto-detect only via "observational"/"cohort"/"epidem")
- **Fix:** Flip default to `is_observational=True`, OR run the causal scan unconditionally and only suppress when project_design is a pre-registered RCT. Add `"rna-seq"`, `"omics"`, `"pilot study"`, `"in vitro"` to the auto-detect keyword list. As shipped, a 4-vs-4 RNA-seq paper that literally says "this proves treatment X causes tumor suppression" returns `ok:true`, contradicting AGENTS.md Hard Rule #3.
- **Sources:** postdoc_audit, methodology_auditor (block severity for any methodology-audit use case)

### FIX-16: Improve did-you-mean ranking [5/10, MED]
- **Where:** `src/research_os/server/dispatch.py:103` (`did_you_mean(resolved, list(_HANDLERS.keys()), n=3)`); plus per-handler kwarg fallback
- **Fix:** Boost candidates that share a namespace prefix (`tool_audit_*` should beat `tool_step_*` for `tool_audit_completness` typo); filter difflib candidates to same-prefix family first. Also apply did-you-mean to kwarg names: if a handler's inputSchema lists `tool_name=` and the caller passed `name=`, suggest "did you mean `tool_name=`?". Currently `tool_audit_completness` → `tool_step_complete, tool_latex_compile, tool_paper_compile_typst` with no audit candidate.
- **Sources:** 5 perspectives

### FIX-17: Re-tag biology-relevant protocols' `scope_tags.domain` [2/10, MED]
- **Where:** `protocols/audit/pre_submission_checklist.yaml:7` (currently `[humanities]` only), `audit/audit_and_validation.yaml:7` (currently `[qualitative]`), `methodology/clinical_trials.yaml:7` (currently `[qualitative]`), `methodology/data_management_plan.yaml:7` (currently `[qualitative]`)
- **Fix:** Re-tag `pre_submission_checklist`, `audit_and_validation`, `data_management_plan` as `[any]`. Re-tag `clinical_trials` as `[biology, medicine]`. Add a preflight check that pre-submission/master-audit protocols must include `any` since they're generic gates.
- **Sources:** methodology_auditor, undergrad

### FIX-18: Accept `--ide none` as a first-class opt-out [9/10, MINOR]
- **Where:** `src/research_os/cli.py:57`, `_ide_choice` helper, `wizard.py`
- **Fix:** Treat `--ide none` as a sentinel meaning "skip IDE wiring entirely" — no MCP config dropped, no CLAUDE.md/`.claude/` written. Document in `research-os init --help` and `docs/CLI.md`. If the value is genuinely invalid, exit non-zero with a clear `"use --ide none to skip IDE wiring"` message instead of silent fallback.
- **Sources:** 9 perspectives (low severity but universal)

---

## 5. v2.1.x patch list (small follow-ups after Phase 14)

These don't block the GREEN tag but should land in a 2.1.x patch.

| Item | Where | Sources |
|---|---|---|
| Sweep router decompositions for legacy tool names (5 sites in `_router_index.yaml`: 987-988, 1119, 1144-1146, 1272, 1661, 1695, 1939-1941) | `_router_index.yaml` | postdoc_audit, pi_review, methodology_auditor |
| Sweep `tool_definitions/audit.py:101, 210` for legacy `tool_audit_step_literature` in tool descriptions | `server/tool_definitions/audit.py` | postdoc_audit, pi_review |
| Sweep `project_ops.py:1762` helper text ("Audit with tool_audit_figure") | `project_ops.py` | postdoc_audit |
| Fix protocol-count drift in docs (88 / 114 / 117 / 118 / 153 — 5 different numbers across docs, CLAUDE.md, project memory, source). Pick one — preferably `len(list_protocols())` at runtime — and have docs reference it | `docs/AI_GUIDE.md:198, 810`, `RESEARCHER_GUIDE.md`, CLAUDE.md, memory | undergrad, postdoc_audit, pi_review |
| Fix `tool_route alternatives[]` populating `primary_protocol:None` (drop unresolved entries OR populate every field) | `tools/actions/router.py` `_build_alternatives` | naive_ai, undergrad |
| Decide on `data` alias removal: document wire-cost in MIGRATION_v2_0_to_v2_1.md; add env-var opt-out `RO_ENVELOPE_OMIT_DATA_ALIAS=1` for token-conscious clients (sys_protocol_get summary doubles from ~3K to ~6K because of duplication) | `envelopes.py:88-93` | experienced_ai |
| Update archived docs in `docs/v2_handoff/` and `docs/audit_v1.9.2/` (13 files reference `dashboard_v2`). Either bulk-rewrite or add a HISTORICAL banner at the top of each | `docs/v2_handoff/`, `docs/audit_v1.9.2/` | undergrad, industry, methodology_auditor, maintainer |
| Strip Markdown numbered-list prefixes (`^\d+\.\s`) in claim-grounding scan so reference numbers `1.` and `2.` aren't flagged as ungrounded claims | `audit/claim_grounding.py` | postdoc_audit |
| Wire `audit_citations` into `audit_quality_full` chain so fake-citation gate fires on the master audit (currently only fires when separately invoked) | `audit_core.py` | postdoc_audit |
| Strip `status` from inner payload dict before assigning to envelope to prevent drift (currently both layers carry duplicate `status:'success'`) | `envelopes.py:_success` wrapping | grad_dissertation |
| Rename theory pack tool references in protocol: `tool_theory_lean_check` → `tool_theory_math_lean_check`, `tool_theory_coq_check` → `tool_theory_math_coq_check` | `src/research_os_theory_math/protocols/proof/proof_verification_workflow.yaml:137` | pi_review |
| Make `sys_help(topic=...)` error on unknown topics instead of silently returning the default routing payload | `server/handlers/meta_routing.py` (sys_help handler) | undergrad |
| Fix Python operator-precedence-fragile expression in `dispatch.py:140` — wrap `("missing" in msg and "required" in msg)` in parens for readability | `dispatch.py:140` | pi_review |
| Fix WHAT/WHY/NEXT punctuation in envelope-rendered error sentence (double period + em-dash reads ungrammatically) | `envelopes.py:135-154` | pi_review |
| `cli_doctor.py` should warn when running on `feat/vX.Y.*` branch with `__version__ < X.Y.0` | `cli_doctor.py:206` | methodology_auditor |
| Fix `check_in_tree_packs_registered` doctor check to call `discover_packs` and verify no collisions, not just `register()` callable | `cli_doctor.py:244` | pi_review |
| Decide on plural-vs-singular tool naming: either remove `sys_protocols_list`/`sys_tools_list` from advice strings entirely, or add canonical aliases in `server/aliases.py` | `server/aliases.py` | methodology_auditor |

---

## 6. v2.2.0+ future work (MINOR scope)

| Item | Rationale | Sources |
|---|---|---|
| **Implement `coaching` autonomy mode** | Documented for undergrads + new PIs in `templates/AGENTS.md` and `researcher_config.yaml` but ZERO branching code exists. Either ship the implementation (surface `pedagogical_prelude` before tool calls; explain WHY on gate-block; auto-invoke `tool_lessons(mistake_replay)` on session boot) or remove `coaching` from the docs/template until shipped. | undergrad, grad_dissertation |
| **Add per-pack `pre_submission_checklist` variants** | `pre_submission_checklist` hardcodes empirical-paper assumptions (CRediT, ARRIVE, IRB, figure DPI, `synthesis/paper.md` prereq). Running on theory_math produces 70% YELLOW category errors. Either add `theory_math/audit/proof_submission_checklist` (theorem-dep-graph, preliminaries cited, formal-check-waiver justified, no figure checks) and route via pack-context, OR generalize the prereq to a `paper_path` parameter with per-check `applies_when_pack_in: [...]` gates. | pi_review, methodology_auditor |
| **Add `methodology/selection_bias` protocol** | Selection bias is canonical for methodology auditing but has no dedicated protocol. `tool_route("check for selection bias")` routes to `methodology/multiple_comparisons` (which is about FDR). Cover post-hoc exclusion, survivorship, ascertainment, confounding by indication; wire into `audit/audit_and_validation` decomposition. | postdoc_audit |
| **Add reproducibility audit to engineering pack pipeline** | `engineering` pack ships 7 protocols; ZERO trigger `tool_audit(scope='step', dimension='reproducibility')` or `sys_env(operation='snapshot')`. An engineering project running the documented happy path never lands on the repro audit unless `pre_submission_checklist` is also invoked. Add env-snapshot + output-hashing post-green-cycle in `build_test_fix_loop` and a Verification-section link from `engineering_report_structure`. | reproducibility, grad_dissertation |
| **Per-pack workspace scaffold variants** | Workspace scaffold is empirical-research-first end-to-end. A project named `theory_math_proof` still gets EDA / logistic regression / NIH R01 example prompts in GETTING_STARTED.md. Add `--domain theory_math|wet_lab|engineering|...` flag to `research-os init`; render pack-tailored GETTING_STARTED.md from `templates/packs/<pack>/` snippets; pre-seed pack-specific inputs paths (e.g. `inputs/preliminaries.md` for theory). | pi_review, undergrad |
| **Heuristic `tokens_estimate`** | Either implement a cheap `len(json.dumps(payload))//4` heuristic inside `_envelope_base`, or downgrade the contract claim to "reserved for future use; currently always 0". | maintainer, reproducibility, naive_ai |
| **`sys_active_tools` pack-aware surface** | `sys_active_tools(<methodology protocol>)` returns 13 generic core tools and ZERO pack-specific tools, even when the protocol's sub_intent matches a pack domain. Surface pack tools (e.g. `tool_qualitative_codebook_diff`, `tool_qualitative_quote_provenance`) when protocol intent matches a pack. Surface prerequisite-protocol shortcut_tools (e.g. `qualitative_pii_redaction` when raw transcripts present without redacted counterpart). | undergrad |
| **Migrate `_DEPRECATED_ALIASES` to actually deprecate** | `_DEPRECATED_ALIASES` exists but the canonical AI guide / templates / router decompositions still use the legacy names — so deprecation warnings never fire because nobody actually consumes the canonical form. Once FIX-5 lands and templates use canonical names, log a deprecation warning when an alias is invoked. | methodology_auditor, grad_dissertation |
| **Audit-time pack-context bias for synthesize intents** | "Draft the paper" in a humanities project routes to IMRAD `synthesis_paper` not `humanities_essay_structure`. Beyond FIX-12's pack-affinity boost, consider a pack-aware shim that explicitly maps generic synthesize intents to pack-specific protocols when the pack is active. | experienced_ai, pi_review |
| **`audit_findings` namespace consolidation** | Same conceptual list appears as envelope-level `audit_findings` AND inside `payload.findings` (audit_findings_query). Two namespaces for one value confuses naive AIs. Document in CONTRACT.md A.6.1 that envelope `audit_findings` is canonical and payload may include a scoped list with a different name (`ledger_entries`), or unify. | naive_ai |

---

## 7. v3.0.0 architectural ideas (out of scope; logged for visibility)

These would require a MAJOR bump and explicit migration; not v2.x territory.

| Idea | Why it would help |
|---|---|
| **Pack-first contract surface** | Move `_success`/`_error` envelope helpers into a stable plugin SDK (e.g. `research_os.plugin`) so pack authors are forced through the envelope by import path, not by convention. Treat envelope-shape conformance as a pack-registration precondition. Today's issue (pack tools live outside the contract) is a recurring v2.x maintenance burden every time the envelope evolves. |
| **Single source of truth for tool/protocol counts and tier metadata** | Move every count from docs/CLAUDE.md/memory into runtime-computed values surfaced via `sys_tool_describe` / `sys_protocol_list`. Doc-build pipeline asserts no static count appears in markdown. Today's drift (88 / 114 / 117 / 118 / 153 in different surfaces) is structural, not editorial. |
| **Trigger-as-test discipline** | Every YAML protocol's first `trigger:` phrase must round-trip through `tool_route` and resolve to itself in CI. The verbatim-trigger misses (`explicate this poem`, `is this paper ready`, `compare X vs Y`) are evidence that trigger ingestion into `_router_index` / embeddings is broken in ways unit tests don't catch. |
| **Router context awareness** | A v3 router could read project metadata (pack, tier, prior protocols invoked, recent files dropped) as scoring context, not just the prompt string. Today's pack-blind routing is a recurring source of misroutes in 5/10 perspectives. |
| **Pluggable autonomy modes as middleware** | `coaching` / `autopilot` / others should be pluggable response decorators that intercept tool calls and inject pedagogical text, gate explanations, or mistake replays. Today's "documented mode with no branching code" is the failure mode of in-place if-elif autonomy. |
| **Native multimodal audit primitives** | Causal-language detection, selection-bias scanning, and methodology-flaw catching are currently heuristic string matches. v3 could expose these as LLM-backed validators with calibrated confidence — pricier but more accurate than the `is_observational` switch. |
| **Deprecation lifecycle as first-class CI gate** | Currently `_DEPRECATED_ALIASES` exists but nothing fires deprecation warnings (because canonical surfaces still publish the deprecated names). v3 could enforce: an alias is in `_DEPRECATED_ALIASES` iff no canonical surface publishes it; CI fails if both publish the same name simultaneously. |

---

## Appendix A: Methodology

Validation pass:
- **10 perspectives** scaffolded scratch workspaces under `/tmp/ro_v21_validation/<perspective>__<scenario>/` via `research-os init --yes --ide none` (which silently fell back to `claude`, see FIX-18).
- Each perspective ran ~14-32 turns of envelope/protocol/router probing and authored consistency findings + ranked frictions.
- **20 random-routing prompts** spanning all 10 L1 intent classes were dispatched against the live router; each scored on routing_quality_1_10 and first_response_quality_1_10 with a friction_count and qualitative notes.

Validation pass did NOT:
- Run `preflight.py` or `pytest` to verify release-gate parity (out of scope for shape-level validation; the maintainer perspective did confirm 1599+ tests pass and 24/24 preflight green — but neither catches the envelope plumbing gaps documented here).
- Execute end-to-end full project runs (intake → step → synthesize → audit → dashboard) for most perspectives.
- Inspect performance regressions on the new envelope's wire-size increase (the `payload`/`data` duplication issue noted in v2.1.x list).
