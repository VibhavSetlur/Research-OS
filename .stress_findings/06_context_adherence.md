# Stress Test 06 — Context-Integrity & Protocol-Adherence

**Target:** Research-OS v4.0.0 (branch `dev`, commit v3.12.0-110-g9cd9754), `/scratch/vsetlur/Research-OS`
**Promise under test:** "protocols + tools will be FOLLOWED by the AI and nothing gets lost."
**Method:** Read `router.py::sys_boot` + helpers and `protocol.py` (completion block, log fn, pipeline predicates, get_next_protocol); scaffolded two live test projects under `/tmp/ro_stress` and ran real `sys_boot` / `log_protocol_execution` / `get_next_protocol` calls to confirm behaviour empirically.
**Verdict:** The promise is **partially upheld for the linear analysis pipeline but materially broken for (a) completion enforcement, (b) the roadmap/autonomous-loop, and (c) daemon BLOCK escalation.** A naive AI can lose the thread, skip required steps, fast-forward the pipeline by logging, and build on a flagged-stale workspace. Findings below with severity, location, why it's lost, and fix.

---

## CRITICAL findings

### C1 — `protocol_completion` is advisory text with ZERO programmatic enforcement; "completed" can be logged with no outputs, no verify, no grounding, no audit
- **Where:** `protocol.py::_PROTOCOL_COMPLETION_BLOCK` (L261–294) + `log_protocol_execution` (L81–95).
- **Empirical proof:** `log_protocol_execution(root, "synthesis/synthesis_paper", "completed", ...)` returned `{"status":"success"}` with **no `synthesis/paper.md` on disk**, no `tool_verify` call, no grounding check, no override-log check. The completion block is a *step description string* appended to every protocol; nothing reads it or gates on it.
- **Why it's lost:** The block is the entire mechanism that's supposed to "force the AI to finish (audits, grounding) before declaring done." It is pure prose. A model under context pressure that skips the last step — or that calls `sys_protocol_log` directly (it's in `_ESSENTIAL_TOOLS`, always available) — bypasses output-existence, grounding, checkpoint, override-log, and the next-protocol pointer with no friction and no warning.
- **Fix:** Make `sys_protocol_log(status="completed")` a gate, not a sink. On `completed`: (1) auto-run `validate_protocol`/`tool_verify(scope='outputs')` for the protocol's `expected_outputs` and **refuse** (return `status="blocked"`) if any are missing/empty unless `override_completeness_gate=True` is passed (which then auto-appends to `override_log.md`); (2) check the searches.log grounding signal for methodology protocols and warn-or-block; (3) record whether the completion block's sub-steps actually ran. At minimum, `log_protocol_execution` should reject `completed` for a protocol whose declared outputs are absent.

### C2 — The roadmap (`inputs/research_plan.md`) and its iteration log are INVISIBLE to `sys_boot`; a fresh AI resuming a roadmap loop is actively mis-routed away from it
- **Where:** `router.py::sys_boot` (L998–1073) — `next_protocol` comes from `get_next_protocol` (the linear `_ANALYSIS_PIPELINE`, L809–856), which **does not contain `guidance/roadmap_execution`**. `sys_boot` never reads, mentions, or points at `inputs/research_plan.md`. The `active_plan` field is the *tactical route decomposition* (`.os_state/active_plan.json`), NOT the durable roadmap.
- **Empirical proof:** Scaffolded a project with `inputs/research_plan.md` + a logged `guidance/roadmap_execution` `started` entry (simulating mid-loop /compact). `sys_boot` returned:
  - `pause_classification: mid_step`
  - `advice: "Previous session left work in-flight — call tool_session_resume."` (generic; roadmap-unaware)
  - `next_protocol: guidance/project_startup` (**WRONG** — pos 2/10; the linear pipeline thinks the project hasn't even started, because roadmap_execution leaves no pipeline artefacts)
  - `active_plan: None`
  - `"research_plan" in boot == False` (the only "roadmap" hit was the mode_directive boilerplate string).
- **Why it's lost:** After a /compact or fresh session, the AI's single orientation call gives it no pointer to the roadmap that IS the thread, and its `next_protocol` tells it to go do `project_startup` — abandoning the in-flight autonomous build. The protocol's own `load_thread` step *does* tell the AI to re-read `research_plan.md`, but ONLY if the AI re-loads `roadmap_execution` — and nothing in boot tells it to. The autonomous loop does NOT reliably survive a restart; the plan can be silently lost the moment context resets.
- **Fix:** (1) Have `sys_boot` detect `inputs/research_plan.md` and surface a `roadmap` block: `{present, path, last_logged_protocol, advice:"An autonomous roadmap is in progress — re-load guidance/roadmap_execution and re-read inputs/research_plan.md before anything else"}`. (2) When the last logged protocol is `roadmap_execution` (or tier `plan`), `next_protocol`/`advice` must point back to `roadmap_execution`, not the linear pipeline. (3) `_classify_pause` / `_boot_advice` should special-case an in-flight roadmap.

### C3 — The pipeline pointer can be fast-forwarded purely by LOGGING completions, with no artefacts on disk — required steps silently skipped
- **Where:** `_ANALYSIS_PIPELINE` predicates (L809–856) are `_protocol_completed(r, X) OR _has(file)`. `_protocol_completed` (L746) just scans the log for a `completed` entry.
- **Empirical proof:** Logged `completed` (log-only, no artefacts) for project_startup→domain_analysis→research_design→methodology_selection→literature_search→reproducibility→audit. `get_next_protocol` jumped from **pos 2 to pos 7/10**, skipping domain/research_design/methodology/literature with **no `docs/domain_summary.md`, no real `methods.md` content, no `citations.md`** on disk. `sys_boot.next_protocol` then reflects this fake progress.
- **Why it's lost:** Combined with C1 (logging is ungated), a naive AI that logs "completed" optimistically — or that completed a step in a prior session that produced nothing durable — convinces `get_next_protocol` (and therefore `sys_boot`) that required research stages are done. Downstream steps build on stages that never produced real outputs. "Nothing gets lost" fails: the *evidence* a step was supposed to create is gone, but the system reports the step done.
- **Fix:** For pipeline "done" predicates, prefer artefact-existence as the authority and treat a `completed` log without the artefact as a **mismatch warning surfaced in sys_boot** ("step X logged completed but its hallmark output is missing — re-run or it will surface RED at audit"). Don't let a bare log satisfy the predicate for steps that have a declared artefact.

---

## HIGH findings

### H1 — Daemon BLOCK-level guidance is buried (field 30/39) and is NOT escalated into the primary `advice` line the AI acts on
- **Where:** `sys_boot` returns `daemon_notes` (L1043) and `advice` (L1072) as separate fields; `_boot_advice` (L1279–1300) **never consults daemon_notes**.
- **Empirical proof:** Wrote a daemon_notes.json with `counts.block=2` (interrupted run; input data changed since a step consumed it). `sys_boot` surfaced `daemon_notes.hint="...address them before building"` correctly — but the top-level `advice` field said `"Fresh project... call tool_route"`, ignoring the 2 blocks entirely. `daemon_notes` sits at index 30 of 39 keys; `advice` at 38.
- **Why it's lost:** A naive/context-pressed AI keys off the single `advice` line (and `next_protocol`). The BLOCK warning is real but un-prioritised — it competes with 38 other fields and is contradicted by `advice`. The force is insufficient to guarantee action before building.
- **Fix:** When `daemon_notes.counts.block > 0`, `_boot_advice` must lead with the block: `advice = "⛔ Daemon found N BLOCK-level integrity issues — run tool_workspace_repair/tool_structure_audit and resolve them BEFORE any other action."` Optionally add a top-level `must_address_first` boolean so it's unmissable.

### H2 — Freshness/staleness only covers 3 narrow signals; it does NOT detect changed INPUT DATA that finalized steps were built on
- **Where:** `state/freshness.py::state_freshness_check` (L26–144). Signals: (1) state-ledger mtime > 30d, (2) `citations.md` older than newest `inputs/literature/*.pdf`, (3) orphan provenance (script deleted).
- **Why it's lost:** If `inputs/data.csv` (or any non-PDF input a step consumed) is modified after a step finalized its result, **nothing flags it.** The AI happily builds on / synthesizes results derived from inputs that have since changed. Provenance sidecars are only checked for *missing scripts*, not for *input hash/mtime drift*. The daemon may note an input change (see H1's example), but core freshness doesn't, and the daemon note is buried (H1).
- **Fix:** Extend freshness to compare each step's provenance-recorded input mtimes/hashes against the live `inputs/`; emit a `is_stale` signal "step NN consumed inputs/X which changed on <date> — its result may be stale, re-run before building on it." This is the exact "build on stale state" gap the promise should close.

### H3 — Required v4 steps (deep_planning capture, judge, path_finalize) are NOT reminded by sys_boot OR the completion block — droppable
- **Where:** `_PROTOCOL_COMPLETION_BLOCK` (L261–294) mentions only verify/log/checkpoint/next/grounding/override. `grep` confirms **no reference to `judge`, `path_finalize`, or `deep_planning`** in `protocol.py` or in `sys_boot`/`_boot_advice`. `roadmap_execution` and `deep_planning` instruct `tool_path_finalize` and iteration-log appends, but only as in-protocol prose.
- **Why it's lost:** These steps live entirely inside protocol bodies. If the AI doesn't load (or finish) the protocol, or compacts mid-protocol, the generic completion block won't remind it to finalize the path or capture the roadmap, and boot won't either. `deep_planning::capture_roadmap` writes `inputs/research_plan.md` via instruction with **no tool that enforces the write** — combined with C2, the roadmap can be never-written or lost with no trace.
- **Fix:** (1) Add an artefact-aware nudge to `sys_boot` (and/or the completion block): if paths exist with `status != completed` and missing READMEs/figures, remind `tool_path_finalize`; `paths_summary` already computes `missing_focal_figure`/`missing_captions` but nothing converts them into an `advice`. (2) Give `deep_planning` a verifiable `expected_output: inputs/research_plan.md` gate so capture can't be silently skipped.

---

## MEDIUM findings

### M1 — `_load_active_plan` auto-archives an in-progress plan after 7 days → on a paused long project, the tactical plan vanishes silently
- **Where:** `router.py::_load_active_plan` (L2277–2314): a plan `>7 days` old with `status="in_progress"` is renamed into `handoffs/` and `sys_boot` returns `active_plan: None`.
- **Why it's lost:** A researcher who returns to a project after a 10-day gap gets `active_plan: None` and no surfaced notice that a plan WAS archived. The advice falls back to generic "wait for message." Reasonable for abandonment, but the archival is invisible — combine with C2 and a paused roadmap project loses both its tactical plan AND has no roadmap pointer.
- **Fix:** When auto-archiving, set a `recently_archived_plan` breadcrumb in sys_boot ("an in-progress plan from N days ago was archived to handoffs/X — re-confirm intent or resume it").

### M2 — `daemon_notes.findings` truncated to 8 (`msgs[:8]`) with no "+N more" indicator
- **Where:** `_boot_daemon_notes` (L1109–1112): `[...][:8]`. If a daemon finds >8 issues, the rest are silently dropped from boot.
- **Fix:** Append a `"...and N more — see .os_state/daemon_notes.md"` sentinel when truncated.

### M3 — `pause_classification` cannot distinguish a mid-roadmap pause from a mid-analysis-step pause
- **Where:** `_classify_pause` (L1244–1276) returns `mid_step` for any `status=="started"`. A roadmap loop and a single analysis step both look identical → the same generic "call tool_session_resume" advice, which doesn't reconstruct the roadmap thread (see C2).
- **Fix:** Inspect the last entry's protocol/tier; emit a distinct `mid_roadmap` class that drives roadmap-aware advice.

---

## What IS solid (promise upheld here)
- `active_plan.json` is written atomically (`save_json_atomic`, L2270) so an interrupted route can't truncate the tactical plan.
- `sys_boot` is genuinely comprehensive for the **linear analysis pipeline**: pipeline_stage, next_protocol, config_directives, freshness scaffold, handoff_hint at ≥5 finalized steps, paths_summary with figure/caption gaps — a fresh AI on a normal analysis project resumes well.
- `synthesis_*` predicates correctly use **file existence** (not the completion log), so a fake "completed" synthesis log does NOT fool the *terminal* pipeline check (it fooled the analysis-prefix predicates only — C3).
- `daemon_notes` does reach the AI with a correct `hint` string when blocks exist — it's just not escalated (H1).

## Priority order for fixes
1. **C1** (gate completion logging) — without it the central promise "audits/grounding before done" is unenforced.
2. **C2 + C3** (roadmap visibility in boot; don't let log-only fast-forward the pipeline) — the autonomous-loop durability + "nothing skipped" promise.
3. **H1** (escalate daemon blocks into `advice`).
4. **H2** (input-data freshness), **H3** (remind judge/finalize/capture).
5. Medium items as polish.
