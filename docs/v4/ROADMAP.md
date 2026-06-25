# Research OS v4 — The Multi-Protocol Gateway Daemon

> **This file is the canonical handoff document for the v4 overhaul.**
> Any agent or maintainer picking up this work reads this FIRST, top to
> bottom, before touching code. It carries the architecture, the
> invariants, the phase plan, and a running progress log so quality does
> not degrade across sessions. Update the Progress Log at the bottom of
> every working session.

---

## 0. Why this exists (the architectural problem)

Research OS today (3.x) is a **single, reactive, stdio MCP server**. It
is excellent at what it does, but the design has a structural ceiling:

- **MCP is reactive.** A server cannot do anything until a host client
  sends a request. Long-running research work (batch-fetching hundreds
  of papers, running a multi-hour simulation, a multi-step pipeline) has
  no home — there is no master loop that owns execution independently of
  whichever chat client happens to be connected.
- **It is bound to one transport.** stdio MCP means one client at a
  time, no shared state across clients, no way for a web UI and an IDE
  to observe the same project simultaneously.
- **Chat is the only surface.** Natural-language chat is a poor place to
  review a 200-row table, a citation graph, or a multi-page draft.
- **Execution is native.** Agent-written code runs on the host. That is
  a security and reproducibility liability.

The v4 model resolves this by making Research OS a **persistent headless
localhost daemon acting as a multi-protocol gateway**: one backend that
owns the master state machine and exposes standardized interfaces to any
client (Cursor, Open WebUI, Claude Desktop, Hermes, the CLI) at once.

```
              ┌────────────────────────────────────────┐
              │           FRONTEND CLIENTS              │
              │ (Cursor, Open WebUI, Claude, CLI, etc.) │
              └───────────────────┬────────────────────┘
                                  │
           ┌──────────────────────┴──────────────────────┐
           ▼                                             ▼
 [ OpenAI/Anthropic-compat API ]                      [ MCP ]
 (Completions & Agent Tool Hooks)          (Read-Only Sidecar Telemetry)
           │                                             │
           └──────────────────────┬──────────────────────┘
                                  ▼
              ┌────────────────────────────────────────┐
              │        RESEARCH OS CORE DAEMON          │
              │  (State Engine, Ledger, Sandbox, DAG)   │
              └───────────────────┬────────────────────┘
                                  ▼
              ┌────────────────────────────────────────┐
              │           PROJECT WORKSPACE             │
              │     (inputs, workspace, synthesis)      │
              └────────────────────────────────────────┘
```

The architecture diagram above is **intent, not spec**. We have free
rein to redesign for the best possible system. The diagram says
"SQLite / Docker"; the actual engine uses a JSON `ResearchLedger` and
native+cluster execution. We keep what works and add what's missing.

---

## 1. Hard invariants (never violate, every phase)

1. **Strangler-fig, not rewrite.** The daemon WRAPS the same engine
   functions the MCP handlers already call. We never re-implement
   routing, state, or protocol logic in a parallel codebase. One engine,
   many faces.
2. **The existing stdio MCP server keeps working until the very end.**
   Every phase ships additive and opt-in. `research-os start` (stdio)
   stays functional through the entire 3.x line. We only retire legacy
   paths at the deliberate 4.0.0 cut, and even then with migration notes.
3. **The release gate is sacred.** `python scripts/preflight.py` (33/33+)
   + `python -m pytest -q` (2200+ pass) + `ruff check src/ tests/
   scripts/` clean. No push / no tag / no version bump if any fails.
4. **Branch model unchanged.** feat/<slug> → dev (squash) → dev→main
   Release PR (squash) → tag from main triggers PyPI + GH release. See
   `docs/RELEASING.md` and CLAUDE.md.
5. **No new heavy hard dependency in core.** The daemon's web stack
   (HTTP server, etc.) goes in a new optional extra `[daemon]`, never in
   `dependencies`. Core must still boot with only the stdlib + current
   deps. The daemon imports its web libs lazily and degrades with a clear
   "install research-os[daemon]" message.
6. **Graceful degradation everywhere.** Vibhav's dev server has NO
   Docker. The sandbox MUST fall back to native execution (with a loud
   audit note) when no container runtime is present. The daemon must run
   without a sandbox, without a dashboard, without provider keys — each
   layer is independently optional.
7. **Tools never do the science.** The doctrine still holds (see
   `docs/PROTOCOL_DOCTRINE.md`): tools verify recorded work, gate, route,
   and manage state/provenance. The daemon orchestrates; it does not
   compute findings.
8. **Provider keys are the client's / user's, scoped to the daemon.**
   When the daemon forwards to a provider it uses the user's configured
   key, never bundles one. Research data-source keys keep their existing
   injection path (`server/entry.py:_inject_api_keys`).

---

## 2. The version stance for v4 — the build→judge→improve loop

**Execution model (Vibhav directive, 2026-06): do NOT release 4.0.0
early.** 4.0.0 is the destination, not a milestone we rush to. The plan
is a long iterative loop — on the order of **20–30 phases** (~10 to
*build* the architecture out, then ~20 to *judge → redesign → improve*)
— and we keep going until 4.0.0 is **the best possible system that could
exist**, not merely "feature complete."

What this means concretely:

- **Build phases** (roughly Phases 0–9): stand up each layer of the
  gateway daemon — skeleton, core loop + state bridge, OpenAI-compat
  gateway, MCP telemetry sidecar, sandbox, dashboard, and the
  cross-cutting concerns they expose (auth, multi-root, streaming,
  observability, persistence of long jobs).
- **Judge/improve phases** (roughly Phases 10–30): for each built layer,
  step back and critique it hard — security, ergonomics, performance,
  failure modes, API quality, test depth, docs — then redesign and
  re-implement the weak parts. Do NOT lock into the first design that
  works. Every judge phase should produce a written critique (in this
  doc's design-review log) and concrete improvement PRs.
- **Each phase still ships green on its own `feat/v4-<slug>` branch →
  dev.** The gate (preflight + pytest + ruff) is non-negotiable per
  phase. But the package **version stays pre-4.0.0** the whole way —
  intermediate phases land as MINOR/PATCH `3.x` releases (the daemon is
  opt-in, MCP untouched), and the **4.0.0 tag waits until the entire
  system is judged maximal**.
- A breaking change mid-stream that we are NOT ready to crown as 4.0.0
  gets the back-compat treatment (alias the old name, keep old schema
  accepting, default-off the new behaviour) and ships MINOR until the
  final 4.0.0 cut collects them.
- **4.0.0 is the deliberate final cut**: daemon is the proven primary
  surface, every layer has survived a judge pass, legacy paths retire
  with a `docs/v4/MIGRATION.md` + CHANGELOG Migration section.

The standing "under 4.0.0 forever" mandate is superseded **for this work
only**.

---

## 3. Engine reuse seams (the strangler-fig anchors)

The daemon is thin glue over these existing functions. Do NOT duplicate
their logic.

| Capability | Existing engine entry point |
|---|---|
| Route a prompt → protocol + plan | `tools/actions/router.py:route_request(prompt, root, persist_plan=)` |
| Read the active plan | `tools/actions/router.py:_load_active_plan(root)` |
| Progress digest | `tools/actions/research/planning.py:progress_digest(root)` |
| Master state ledger (atomic, file-locked) | `state/state_ledger.py:ResearchLedger` |
| Dispatch a tool call by name | `server/dispatch.py:_handle_tool_call(name, args, root)` |
| Tool catalogue + schemas | `server/registry.py:TOOL_DEFINITIONS`, `_HANDLERS` |
| Protocol load | `tools/actions/protocol.py` (loader) / `sys_protocol_get` handler |
| Autopilot floor gates | `server/autopilot_gate.py:enforce_autopilot_gate` |
| Project root resolution | `server/entry.py:_resolve_project_root` |
| Research-data API key injection | `server/entry.py:_inject_api_keys` |

**The key insight:** `_handle_tool_call(name, arguments, root)` is a
pure, transport-agnostic function. The stdio MCP server is just one
caller of it. The daemon's HTTP gateway becomes a second caller of the
exact same function. That is the whole strangler-fig in one sentence.

---

## 4. Phase plan

Each phase is a shippable release. Sub-tasks within a phase may be their
own PRs. "DoD" = Definition of Done (the gate for declaring the phase
complete).

### Phase 0 — Daemon skeleton (additive, no behaviour change)
- New package `src/research_os/daemon/` with `__init__.py`, a `Daemon`
  class stub that holds config + a reference to the resolved root, and a
  `research-os daemon` CLI subcommand group (`start`/`stop`/`status`)
  that currently just reports "not yet serving".
- New optional extra `[daemon]` in pyproject (web server lib TBD in
  Phase 2; Phase 0 adds the extra empty/with only what's needed).
- Lazy-import guard: importing `research_os.daemon` must not pull heavy
  web deps at module load.
- DoD: preflight+pytest+ruff green; `research-os daemon status` runs;
  zero change to any existing surface; new `tests/unit/test_daemon_*`.

### Phase 1 — Daemon core loop + state bridge (read path)
- A persistent process that holds the master loop and a read-only view
  over `ResearchLedger` + active plan + progress digest for one or more
  project roots.
- A localhost control socket / HTTP health endpoint (`/healthz`,
  `/v1/state`) — READ ONLY. No mutation yet.
- Background task queue abstraction (the "master loop owns execution"
  primitive) — enqueue a long-running job, run it off the request
  thread, expose status. Jobs call existing engine functions.
- DoD: daemon starts, serves read-only state for a real RO project,
  survives client disconnect; task queue runs a trivial job to
  completion and reports status.

### Phase 2 — OpenAI-compatible gateway (`/v1/chat/completions`)
- The interception pipeline: receive a chat request → resolve project
  root → `route_request` to pick the protocol → inject protocol
  constraints + directory context as system/context messages → forward
  to the user-configured provider → stream/return the completion.
- Tool-call hooking: when the upstream model emits a tool call, the
  daemon dispatches it through `_handle_tool_call` and feeds the result
  back across the API boundary (the agent loop).
- Provider abstraction (OpenAI / Anthropic / local) reusing the user's
  configured keys; no bundled key.
- DoD: a generic OpenAI client (e.g. `curl`, the `openai` python lib,
  Open WebUI pointed at `localhost`) can hold a research conversation
  that is protocol-constrained and can execute RO tools end-to-end.

### Phase 3 — Read-only MCP sidecar telemetry
- Re-expose the EXISTING MCP server in a read-only mode that reflects
  the running daemon's state (state, logs, task progress) so a chat
  client connected via MCP can observe what the daemon is doing.
- This is a thin re-projection, not a new server: same tools, filtered
  to the read-only/telemetry subset, pointed at the daemon's state view.
- DoD: with the daemon running, an MCP client sees live task/progress/
  state telemetry; write tools are absent or refuse in sidecar mode.

### Phase 4 — Ephemeral sandbox interface (Docker/Podman + native fallback)
- A standard sandbox interface: map `workspace/` as a bounded volume
  into a disposable container, run agent code, capture stdout/stderr to
  the audit trail, tear down.
- Runtime detection: Docker → Podman → native fallback (with a loud
  audit note that execution was unsandboxed). MUST work on a host with
  no container runtime (Vibhav's dev box).
- Wire into the existing exec tools (`tools/actions/exec/scripts.py`
  etc.) behind a config flag so native stays the default until proven.
- DoD: code runs in a container when one exists; falls back cleanly when
  not; audit trail records which mode was used and the full logs.

### Phase 5 — Read-only local web dashboard
- A lightweight, offline-safe, read-only dashboard served by the daemon:
  project execution step progress, interactive visualization trees,
  citation lists, file audit log. Mirrors the existing synthesis
  dashboard design tokens / a11y / offline-safety conventions.
- DoD: `localhost:<port>` shows live project status; no network
  requests; renders for a real project; updates as tasks progress.

### The 4.0.0 cut (after Phase 5 is proven)
- Make the daemon the default `research-os start` behaviour (stdio MCP
  becomes `research-os start --stdio` or a sidecar mode).
- Collect any deferred breaking renames.
- `docs/v4/MIGRATION.md` + CHANGELOG Migration section.
- Bump to 4.0.0, tag, release.

---

## 5. How to work this safely (process for every session)

1. Read this file. Read the Progress Log (section 7).
2. `source /scratch/vsetlur/anaconda3/etc/profile.d/conda.sh && conda
   activate research-os`. Confirm the baseline gate is green BEFORE
   starting (so you know any breakage is yours).
3. Work on a `feat/v4-<slug>` branch off `dev`. Small, reviewable PRs.
4. Re-run the full gate before every push.
5. For big design-heavy steps, dispatch parallel subagents to draft the
   design / explore options, synthesize into a spec, THEN implement.
6. Update the Progress Log at the bottom of this file before ending the
   session. Record: what shipped, what's half-done, the next concrete
   step, and any landmine discovered. This is the anti-degradation
   mechanism — be specific enough that a cold session can resume.
7. Keep memory (the Hermes memory store) in sync with the high-level
   status, but the DETAIL lives here in the repo where it's versioned.

---

## 6. Design decisions (resolve as we go, record the decision)

Decisions are append-only with a date + rationale. A judge phase may
REVISIT a decision — when it does, add a new dated entry that supersedes
the old one rather than editing history.

- **[RESOLVED 2026-06-23] Web framework for the gateway (Phase 1–2):**
  `starlette` + `uvicorn`, in the `[daemon]` optional extra, imported
  lazily. Rationale: Phase 2 needs SSE streaming for
  `/v1/chat/completions`, which stdlib `http.server` makes painful;
  starlette is a thin ASGI layer and uvicorn is the de-facto server.
  Mitigation for the "heavy dep" worry: it's opt-in (extra), lazy, and
  the daemon degrades with a clear "install research-os[daemon]" message
  when absent. The HTTP layer lives behind a thin `daemon/server.py` so
  the transport stays swappable if a judge phase wants to reconsider.
- **[RESOLVED 2026-06-23] Multi-project model:** ONE daemon, MANY roots
  keyed by absolute path. Rationale: the gateway already resolves root
  per-request (`_resolve_project_root`), so a root registry is the
  natural fit and avoids a port-per-project explosion. A `Workspace
  registry` maps root → cached engine handles (ledger view, last status).
- **[RESOLVED 2026-06-23] State backend:** keep JSON `ResearchLedger`
  (proven, file-locked, atomic, self-healing on corruption). Do NOT move
  to SQLite now. Revisit ONLY if concurrent multi-client writes prove the
  lock contention is real (a judge-phase candidate, not a build blocker).
- **[OPEN] Auth on localhost endpoints:** bind 127.0.0.1 only (done in
  DaemonConfig) + a per-session bearer token for any MUTATING endpoint.
  Read-only endpoints (Phase 1) are localhost-bind-only for now. DECIDE
  the token scheme before the first mutating endpoint (Phase 2 tool
  dispatch). Candidate: a token minted at daemon start, written to
  `.os_state/daemon_token` (0600), required as `Authorization: Bearer`.
- **[OPEN] Long-job persistence:** the Phase-1 task queue is in-memory.
  Decide whether jobs must survive a daemon restart (persist queue to
  `.os_state/`) — likely yes for the "master loop owns multi-hour work"
  promise. Judge-phase candidate once the queue has real jobs.

---

## 7. Progress log (append-only; newest at top)

### 2026-06-24/25 — Chat-first intake: fill the project without touching inputs/
Real onboarding UX gap: the whole intake flow assumed the researcher DROPS
FILES into inputs/, and tool_intake_autofill only inferred question/domain/
hypotheses from those files. Many researchers never edit inputs/ — they just
describe the project in chat. There was no smooth capture path, and
project_startup's scan_inputs DEAD-ENDED on empty inputs/.
- **tool_intake_autofill (`58bc343`)** gains question/domain/hypotheses/
  context_note params. Explicit chat values beat file inference, so an EMPTY
  inputs/ still yields a real intake; context_note joins the corpus so
  research_overview captures the framing verbatim. No-arg behaviour unchanged.
  Wired through tool def + handler.
- **project_startup**: scan_inputs no longer dead-ends — routes to the chat
  path when the researcher described the project conversationally, asks (one
  line, both paths offered) only when there's neither files nor a description.
  autofill_intake documents both paths.
- **inputs/intake.md template** now leads with 'just tell the AI in chat' as
  option 1. Carries a hidden ro:intake-template marker so intake_freshness
  still treats the unfilled scaffold as a stub (the richer template was being
  mis-read as filled); marker is gone once autofill writes the real intake.
- The principle: every input path works — chat-only, files-only, mixed, empty.
  Never force a researcher to write a file to start.
- Gate green: preflight 38/38, pytest 2749, ruff clean.

### 2026-06-24/25 — Mixed-mode layer made legible + skill-layer-first streamlining
With the RO MCP server now live (154 tools), exercised routing end-to-end and
improved the mixed-mode layer across all working modes plus the Hermes-skill
streamlining the user asked for.
- **Skill-layer-first tool discovery (`3169010`).** methodology/tool_discovery
  now consults the agent's domain skill layer (Hermes) FIRST: a skill already
  names the canonical library with validated params, so take it as the strong
  default + skip to install/log; fall through to the generic search reasoning
  only when no skill covers the task. The 'streamline where Hermes skills exist'
  pattern — keep the reasoning scaffold, defer how-to to the skill layer. Skill
  says HOW, RO confirms it FITS + records WHY.
- **Evaluate-loop mode-boost gap fixed (`3169010`).** build_evaluate (→
  build/tool_evaluation_loop, the evaluate→improve heartbeat) was in NO mode's
  boost set. Added it to tool_build (+2) and hybrid (+1) — it's a core build
  activity AND the heart of the hybrid loop. Verified live.
- **sys_boot now surfaces the mode (`71e9ea2`).** The deepest mixed-layer gap:
  workspace.mode silently biased routing but the AI never SAW it at boot, so it
  couldn't act mode-appropriately or notice when to switch. sys_boot now returns
  workspace_mode + a one-line mode_directive for all 6 modes, each with its
  behaviour + transition signal (analysis→hybrid when you need to build a tool,
  exploration→promote a probe, etc.). The mode is now a stated context the AI
  reasons about, not an invisible bias.
- Gate green: preflight 38/38, pytest 2747, ruff clean.

### 2026-06-24/25 — The layered-research-OS thesis: RO guidance + a self-improving agent layer
Researched the Hermes skills ecosystem online (hermes-agent.nousresearch.com/
docs) and acted on the architectural thesis it confirms: the best research
setup is RO (guidance + enforcement + provenance) UNDER a self-improving,
project-aware agent layer (Hermes as reference) that runs above any model.
Hermes skills are gateway-style — e.g. the Bioinformatics skill indexes 400+
external bioSkills/ClawBio skills fetched on demand — which is exactly RO's own
philosophy ('RO needn't contain everything'). The pairing existed in code
(`research-os hermes add`, the distill/promote skill registry, the RO SKILL.md)
but wasn't discoverable or guided.
- **guidance/agent_setup protocol (`6926263`).** Scaffolds architecting the AI
  layer for a project: assess current setup → name the capabilities a research
  agent layer needs (persistent memory, skill ecosystem, MCP, self-improvement,
  model-agnostic) → choose + wire the layer (Hermes ref via hermes add; other
  MCP clients via ide add; CLI path for chat-only) → tailor researcher_config →
  ALIGN skills with protocols (skills = tool/domain how-to; protocols = method
  choice + grounding + reproducibility; distill/promote so it compounds).
  Doctrine-correct: recommends Hermes but allows any layer, naming capabilities
  not mandating a product. 182 protocols.
- **Hermes as a first-class init step (`6926263`).** The wizard now offers
  Hermes (the self-improving layer) distinct from per-IDE wiring; detects an
  existing ~/.hermes, shows the install URL when absent, wires via
  hermes_integration.add() post-scaffold (best-effort), next-steps card points
  at agent_setup. New --hermes/--no-hermes flags. (Confirmed init already
  installs ONLY the IDEs the user selects — no over-install; that was already
  correct.)
- **The throughline going forward:** RO is the rigor/guidance substrate; the
  agent layer + its skills make the setup capable + self-improving + tailored.
  Future guidance work should keep teaching researchers to optimize their layer
  (any AI), not just use RO tools — the layered system is the product.
- Gate green: preflight 38/38, pytest 2745, ruff clean.

### 2026-06-24/25 — Deep-dive follow-through: connect verification to the agent's path
Two parallel deep-dive investigators (synthesis system + daemon↔MCP↔agent)
independently converged on ONE theme with my own trace: the enforcement +
verification machinery is sound but DISCONNECTED from the path an AI actually
walks. Three HIGH findings closed, all gate-green.
- **Staleness gate woken (`c4c55df`).** Both reports' #1: the no_stale_inputs
  floor gate reads a verdict that was ONLY written by an authenticated POST
  /v1/staleness/verdict — no run hook — so it never fired in normal use.
  RunJournal._on_transition now recomputes + persists the verdict after every
  terminal run (reusing the POST endpoint's assess+write_verdict),
  best-effort/isolated. Composes with POST /v1/jobs: agent runs now journal
  AND refresh freshness, so 'block a deliverable built on changed inputs'
  works end-to-end.
- **Synthesis verification made reachable (`e80b408`).** Synthesis report's #1
  + #4: (a) tool_synthesis_check never ran claim-grounding — ungrounded
  numbers only surfaced at the far-downstream ship gate; added mode='grounding'
  (in 'all') that runs audit_claims per check, WARN-level, during authoring.
  (b) The one HARD ship gate (tool_finalize_project) was referenced by NO
  synthesis protocol — an autopilot AI compiled a PDF and stopped, never
  hitting it; synthesis_paper's pre_submission step now runs
  finalize(check)→finalize explicitly.
- **POST /v1/jobs keystone (`a61ae58`, prior in this session).** The missing
  run-submit endpoint so agent execution shares the journal/provenance/lineage
  path (DESIGN_V4 §6.2). Lazy-starts the task queue (latent bug fixed).
- **Deferred, logged for next passes (corroborated by the reports):**
  (1) exec-tool delegation by-shape — needs a sync-wait mode on /v1/jobs first
  (async/sync mismatch); (2) sys_boot is daemon-blind — fold a best-effort
  daemon orient/jobs summary into it so every session inherits continuity
  (daemon report HIGH #2); (3) sys_daemon is a read-only peek — add action=
  verbs (lineage/runs/staleness) + a sys_job submit/poll tool (daemon MED);
  (4) no deliverable/output registry (synthesis MED #7 + 'remember outputs');
  (5) missing output-type protocols: registered_report, software_paper,
  data_paper, PRISMA, preprint_thread, policy_brief, notebook-deliverable
  (synthesis MED/LOW #8–12); (6) claim grounding is bag-of-numbers presence,
  not value↔named-source binding (synthesis HIGH #3); (7) /v1/consent/grants
  leaks token values to any localhost user on shared HPC (daemon LOW —
  require the bearer token on it too).
- Gate green: preflight 38/38, pytest 2744, ruff clean.

### 2026-06-24/25 — Deep-dive pass: closing the agent↔daemon execution gap
A fresh whole-system deep dive (synthesis system + daemon↔MCP↔agent layers +
routing), traced through real code, surfaced the system's deepest
architectural gap and several follow-ups.
- **THE finding — agent execution escapes the provenance spine.** The daemon
  has a full run lifecycle (journal/provenance/lineage/staleness/reproduce/
  rebuild) but ONLY the CLI fed it. MCP exec tools (tools/actions/exec/*.py)
  spawn inline subprocesses with no journal; even the daemon's own chat
  gateway routes tool calls through `_handle_tool_call` → those same inline
  subprocesses (gateway.py:382). So every run an AI drove bypassed provenance
  — breaking DESIGN_V4 §6.2 'one execution path' + feature #50. There was no
  run-submit HTTP endpoint at all; the daemon's only mutating surface was
  staleness-verdict/chat/consent.
- **SHIPPED (`a61ae58`) — POST /v1/jobs**, the missing keystone. Submits a
  command as a journaled background run through the same `core.run_command`
  lifecycle the CLI uses; any client (MCP agent via daemon_bridge.http_post
  by-shape, chat gateway, curl) can now route execution to one provenance
  path. Auth-gated; precise status codes; lazy-starts the task queue (fixed a
  latent 'submit() before start()' bug that contradicted the docstring). +4
  tests.
- **DEFERRED — exec-tool delegation by-shape (the agent side of the loop).**
  Rewiring tool_python_exec/tool_bash_exec/etc. to POST to /v1/jobs when a
  daemon is present (degrade to inline when not) is the natural follow-on, BUT
  the exec tools are SYNCHRONOUS (run → wait → return stdout in the envelope)
  while /v1/jobs is ASYNC (returns a job id; run happens in background).
  Naive delegation would break the synchronous contract every protocol depends
  on. DESIGN OPTIONS to weigh next: (a) add a sync-wait mode to the endpoint
  (?wait=N / "wait":true) that blocks until terminal and returns the result
  envelope — preserves the contract, gains the journal; (b) make delegation
  opt-in per call; (c) a hybrid: short runs sync-wait, long runs return a
  handle. Lands cleanly on the keystone now in place.
- **Other gaps logged for later:** (1) NO deliverable/output registry —
  synthesize_plan reports input-side readiness ('what's ready to write a paper
  FROM'), but nothing tracks which deliverables EXIST, their state
  (draft/compiled/submitted), and which workspace artefacts/runs each was
  built from. A `.os_state/deliverables.json` manifest would make 'remember
  the outputs' real and let the staleness gate know a deliverable is stale.
  (2) DEFERRED from last session: a drift guard for dangling PROSE protocol
  references (build/x mentioned in step text isn't checked, only routing
  targets are).
- Gate green: preflight 38/38, pytest 2742, ruff clean.

### 2026-06-24/25 — Protocol expansion: data prep, tool eval loop, voice calibration
Three new protocols filling real coverage gaps (181 protocols total), all
doctrine-correct scaffolds, each routed + wired + gate-green:
- **`methodology/data_preparation`** (`884ace3`): the biggest unscaffolded gap
  in the analysis path. data_quality_audit DIAGNOSES; nothing scaffolded the
  transforms that FIX (dedup, type, recode, join, reshape, outlier, filter) —
  the largest pool of undocumented researcher DoF. Raw immutable, every
  decision recorded + re-runnable, outliers vs impossibles split, CONSORT-style
  N accounting, missingness deferred to its own protocol.
- **`build/tool_evaluation_loop`** (`54c618f`): the evidence-driven
  evaluate→improve heartbeat for tool_build + hybrid — the "do research on your
  own tool, then come back to improvements" cycle benchmark_vs_baseline (one
  shot) + test_strategy (correctness) didn't cover. Hypothesise weak spots →
  fixed-condition evals → rank backlog by evidenced impact → feed top fix to
  implement_iteration → re-measure. Wired into hybrid_workflow's
  choose_next_increment. Also fixed a real dangling prose ref
  (build/implement_and_iterate → build/implement_iteration).
- **`writing/voice_calibration`** (`4eda3a4`): learn + apply the researcher's
  OWN writing voice (author-voice, not venue-voice) from their genuine samples
  into workspace/.style/voice_profile.md. Client-agnostic (on-disk). Wired into
  writing_core so every drafted section inherits it; hard venue/rigor rules win,
  voice owns the discretionary space, never touches claim grounding.
- **Preflight hardening**: the protocol tool-ref check is now protocol-ID-aware
  (auto-exempts tool_/sys_/mem_-prefixed protocol ids like tool_evaluation_loop)
  — kills a recurring hand-maintained-allowlist false-positive class, same
  lesson as the docs-xref guard fix.
- DEFERRED (logged): a drift guard for dangling PROSE protocol references
  (build/x, methodology/y mentioned in step text) — routing targets are
  checked, prose mentions are not; that's how the implement_and_iterate typo
  survived.
- Gate green throughout: preflight 38/38, pytest 2738, ruff clean.

### 2026-06-24/25 — Adaptivity (learn-the-user) + drift-guard precision + doctrine sweep
- **Drift guard made precise** (`c867b27`): the "Docs/code consistency"
  preflight check was emitting 13 false-positive WARNs (user-project paths
  mistaken for repo xrefs, plugin-authoring placeholder tools, protocol IDs
  that start with `tool_`). Tightened to real Markdown link targets + a
  PLUGIN_AUTHORING skip + protocol-ID awareness. Now clean — and tighter:
  the tightening immediately surfaced a real protocol-ID mismatch the loose
  regex had masked. A green that means something.
- **Learn-the-user loop closed** (`7d03874`): `interaction.agent_notes`
  existed as a store + was surfaced at boot, but had NO append mechanism
  (`set` clobbers) and the reconcile hint never told the AI to record
  corrections. Added `sys_config(operation='note')` → `append_agent_note()`
  (dated bullet, idempotent, ruamel-comment-preserving) wired through the
  full stack, and updated the boot reconcile hint to instruct recording a
  correction/standing preference so the next session inherits it. This is
  the write-on-correction loop the template always promised; composes with
  Hermes memory rather than duplicating it. +5 tests.
- **Doctrine sweep of the methodology cluster** (`ea807d5`): a full
  scaffold-not-script audit (subagent, all 142 protocols) found the library
  overwhelmingly clean — zero whole-protocol recipes. Fixed the 5 residual
  prescriptions: `inter_rater_reliability` (method-menu → dimensions +
  surface-via-tool; default libraries → runtime-sourced),
  `qualitative_quality_audit` (bare `≥0.7`/`≥10%` in the description that
  contradicted its own scaffolded step body → defer to
  inter_rater_reliability), `missing_data_strategy` (hardcoded `m=20;
  max_iter=10` worked example → justify-from-FMI placeholders),
  `power_analysis` (`alpha: typically 0.05` → cite the field/regulator
  level). Sidecars rebuilt; protocol versions bumped.
- **Investigated + cleared as no-bug:** the daemon↔MCP bridge (clean,
  precondition surfacing wired both tiers), and the prose-`prerequisites`
  vs `requires:` overlap (intentional per doctrine — prose carries the
  fuzzy ones, `requires:` the mechanical floor).
- Gate green throughout: preflight 38/38, pytest 2735 pass, ruff clean.

### 2026-06-23 — Session 2: Phase 1 core + Phase 1.5 event spine (JUDGE→IMPROVE)
- **Phase 1 BUILD shipped** (`2868a8d`): the daemon now actually serves.
  Three stdlib-only, import-cheap modules — `registry.py` (multi-root
  read views over engine helpers), `tasks.py` (bounded worker-pool task
  queue with cooperative cancel + history eviction), `server.py` (lazy
  starlette ASGI: `/healthz`, `/v1/state`, `/v1/jobs`, `/v1/jobs/{id}`).
  `daemon start` wired to serve with graceful degrade when the `[daemon]`
  extra is absent. 55 daemon tests green; ruff clean; preflight 33/33.
- **Two real bugs found + fixed during BUILD** (logged so we don't
  regress): (1) `Daemon.for_root` accepted `str` roots but `config
  resolution + status()` assumed `Path` → normalize to `Path` early.
  (2) Task-queue history eviction only ran at submit-time, when newer
  jobs were still QUEUED and thus non-evictable → completed jobs grew
  unbounded. Fixed by also evicting in the job's terminal `finally`.
- **Phase 1.5 IMPROVE — the event spine** (this session, judged in §8):
  added `events.py` — an append-only, bounded, thread-safe `EventBus`
  with monotonic seq, ring-buffer backfill, kind/root filtering, and
  fan-out to live subscribers (slow subscribers drop oldest, never
  block a job thread). The task queue now publishes
  `job.{submitted,started,succeeded,failed,cancelled}`. New SSE endpoint
  `GET /v1/events` (Last-Event-ID / `?after=` resume, `?kinds=` /
  `?root=` filters, 15s heartbeat) + poll-friendly `GET
  /v1/events/recent`. This is the substrate Phase 2 streaming, Phase 3
  telemetry, and Phase 5 dashboard all compose on.

### 2026-06-23 — Session 1: planning + baseline
- Established baseline understanding of the 3.12.0 architecture (single
  reactive stdio MCP, JSON ledger state, no HTTP, no Docker sandbox).
- Vibhav granted 4.0.0 for this overhaul (staged across many PRs).
- Wrote this ROADMAP as the canonical multi-session handoff doc.
- Confirmed the release gate is green on `main` @ 3.12.0 (preflight
  33/33; pytest + ruff verification in progress at time of writing).
- NEXT CONCRETE STEP: Phase 0 — scaffold `src/research_os/daemon/` +
  `research-os daemon` CLI subcommand group, additive and opt-in, with
  the lazy-import guard and a `[daemon]` extra. Branch
  `feat/v4-daemon-skeleton` off `dev`.

---

## 8. Design review (the JUDGE log — critique, then improve)

This section is the explicit build→judge→improve record. After each
BUILD phase we critique it against the end-state bar — **the best
possible research OS: any language, any research, any researcher, any
level, any AI** — log the gaps, and feed them back as the next IMPROVE.
4.0.0 ships only when this log has no open high-severity gaps.

### JUDGE-1 (2026-06-23) — critique of the Phase 1 core

Bar: not "a daemon with endpoints" but a universal research substrate.
Judged Phase 1 against that and found three gaps:

1. **[ADDRESSED in 1.5] Poll-only observability.** State was readable
   only by polling `/v1/state`. A research OS that owns multi-hour work
   must let any client *subscribe*. → Built the event spine (`events.py`
   + SSE `/v1/events`). This is now the spine every later streaming
   feature composes on, instead of each phase inventing its own.

2. **[OPEN — high] Python-callable-only execution.** `TaskQueue.submit`
   takes a `Callable`. That silently fails "any language": real research
   runs R, Julia, bash, Snakemake, Nextflow, and SLURM/scheduler
   submissions. The queue needs a **job-kind abstraction** —
   `python-callable | subprocess | scheduler-submit` — with a uniform
   lifecycle (stdout/stderr capture, exit code, streamed log lines as
   `job.log` events, artifact paths) so the daemon can drive the actual
   tools researchers use, not just in-process Python. This is the single
   biggest lever toward "any language / any work" and is the next BUILD
   (Phase 1.6, before the gateway): a `runners/` package behind the
   existing `submit` seam, additive, each runner emitting the same
   events. Native first; SLURM/snakemake/nextflow adapters follow; the
   sandbox (Phase 4) becomes just another runner.

3. **[OPEN — med] Non-durable jobs.** Queue is in-memory; a daemon
   restart loses job records and breaks the "owns multi-hour work"
   promise. Decide a `.os_state/jobs/` append-only journal (job spec +
   status transitions) so the queue rehydrates terminal/running history
   on restart. Pairs naturally with job-kinds (a subprocess job's PID +
   logfile are exactly what must persist). Judge again after 1.6.

Lower-severity notes carried forward: SSE backpressure is handled by
oldest-drop today (fine for tiles, revisit if a client needs lossless
log tailing — that wants the durable journal from gap 3, replayed via
`?after=`); `_jsonsafe` truncates non-primitive job results to a type
name (acceptable — results should be handles/paths, not blobs).

### JUDGE-2 (2026-06-23) — what a research OS needs *beyond* execution

Phase 1.6 made the daemon able to run anything. But a task runner is not
a research OS. The researcher's real lifecycle is: ask → run → **produce
artifacts** → **record provenance** → **reproduce** → **report**. Right
now everything after "run" evaporates when a job ends. Three gaps, and
they collapse into ONE primitive:

1. **[OPEN — high] No durable run journal.** (Carried from JUDGE-1 gap
   3.) Jobs live in memory; a restart loses all history and breaks the
   "owns multi-hour work" promise.

2. **[OPEN — high] No provenance / reproducibility.** This is the single
   most important property in research — a result you can't reproduce is
   worthless. We capture exit code + a log tail but NOT: the exact
   command, cwd, the project's git commit (dirty?), the environment
   (conda env name, python version, key package versions), input file
   hashes, output artifact hashes, and precise timestamps. Without this
   the daemon is a fancy `&`, not a research OS.

3. **[OPEN — med] No artifact tracking.** Runs produce files; nothing
   records what was produced or links it back to the run that made it.

**IMPROVE — the run journal as the provenance record (Phase 1.7, next
BUILD).** One primitive serves all three: each job persists to
`.os_state/runs/<job_id>/` a `run.json` manifest (spec + provenance +
status transitions + artifacts) plus a full `log.txt`. This makes jobs
survive restart (gap 1), makes every run reproducible (gap 2), and gives
the gateway/dashboard a queryable, durable history (gap 3) — three needs,
one file format. A `RunStore` reads/writes the journal; the queue writes
on each lifecycle transition; on daemon start the store rehydrates the
last N runs into the queue's history. New endpoints `GET /v1/runs` and
`GET /v1/runs/{id}` serve the durable record (the in-memory `/v1/jobs`
becomes the live view; runs are the permanent record). Provenance capture
is best-effort and never blocks a run (a missing git binary just omits
the commit). This is strictly additive — no existing behavior changes.

**SHIPPED (Phase 1.7, commit c1d1ffd).** `provenance.py` + `runstore.py`
(RunStore + RunJournal bridge off the event bus) + `/v1/runs[/{id}]`.
Gaps 1+2 closed; gap 1 also rehydrates orphaned runs to INTERRUPTED on
restart. Nonzero subprocess exit now reconciles to a FAILED run.

### JUDGE-3 (2026-06-23) — closing the provenance loop: artifacts

Phase 1.7 records inputs → command+env. The other half of
reproducibility is **outputs**: a run that says "here is exactly how I
was made" must also say "here is what I made." Gap 3 (artifact tracking)
is now the highest-leverage lever — it's universal (every run produces
files, regardless of language or where it ran) and it's what lets a
dashboard show "this figure ⇐ this run ⇐ this code@commit ⇐ these
inputs." It also composes forward: a SLURM/snakemake job (a later
job-kind) still produces artifacts the same way.

**IMPROVE — artifact detection by working-dir diff (Phase 1.8, next
BUILD).** Snapshot the run's cwd file fingerprints (path → mtime+size)
at job start; diff at job end; record created/modified files as
artifacts (path, size, sha256, mtime) on the run manifest. Bounded:
cap the artifact count, skip files over a size threshold (hash is
skipped, file still listed), ignore VCS/cache dirs (`.git`, `.os_state`,
`__pycache__`, `node_modules`, `.venv`). Best-effort, off the hot path,
never blocks or fails a run. Config knobs: max artifacts, max hash
bytes, ignore globs. Endpoint: artifacts ride inside the existing
`run.json`, so `GET /v1/runs/{id}` already surfaces them — no new route.
Strictly additive.

Deferred (logged, lower leverage right now): scheduler-aware job-kinds
(SLURM `sbatch`/`squeue` polling, snakemake/nextflow DAG awareness) —
valuable for HPC (the target deploy is a shared SLURM box) but it's a
narrower job-kind extension that builds cleanly on the SubprocessRunner
+ artifact tracking already in place. Revisit after 1.8.

### Phase log: 1.11 – 1.14 (2026-06-23) — the provenance & correctness arc

These four phases complete the single-run + chain story. Each shipped
green (ruff clean, preflight 34/34) on `feat/v4-daemon-core`.

* **1.11 — SLURM scheduler + `daemon submit`** (`298668d`). A
  `SchedulerRunner` fitting the same TaskQueue→RunResult seam: sbatch
  `--parsable` submit + sacct/squeue poll + scancel + artifact capture.
  Non-blocking (returns a daemon job id immediately; a worker thread
  owns the poll). `SchedulerAdapter` Protocol keeps PBS/LSF pluggable.
  Graceful degradation when `sbatch` is absent (this host has none) —
  clean exit-1, still records a daemon run. Verified via fake-SLURM
  adapter: PENDING→RUNNING→COMPLETED lifecycle, out.txt captured.

* **1.12 — run comparison `daemon diff` + shell-aware `daemon run`**
  (`7d16b61`). `compare_runs(a, b)` (pure stdlib) diffs three planes:
  command (cmd/cwd/scheduler/env), context (git commit+branch+dirty,
  conda env+python, input hashes, package versions), outputs (artifacts
  by sha256, reusing `compare_artifacts`). Also fixed a real bug: a
  single-token command with shell metacharacters (`|`, `>`, `&&`) now
  auto-routes through a shell (or `--shell`), so `daemon run "py x | tee
  log"` works. The exec form `daemon run -- python x.py` stays argv.

* **1.13 — content-addressed run lineage graph** (`deb009a`).
  `build_lineage(manifests)` builds the provenance DAG: run B depends on
  run A iff one of B's input hashes equals one of A's output artifact
  hashes — the edges fall out of data already captured, no manual
  declaration. `ancestors`/`descendants` answer "where did this come
  from?" (`--upstream`) and "what goes stale if I re-run this?"
  (`--downstream`). Added `daemon run --input PATH` so input hashes get
  recorded (the link key). Verified e2e on a 3-run A→B→C chain.

* **1.14 — staleness detection** (`ed67c1e`). `assess(manifests,
  hash_file)` (pure, injected hasher) turns the passive DAG into an
  active correctness tool: a run is **input-stale** when a recorded
  input now hashes differently on disk; **transitive-stale** when any
  lineage ancestor is stale. `daemon stale` exits 1 if anything is
  stale, showing the old→new hash and the stale-ancestor chain. This is
  the question that matters most to a computational scientist: "is this
  figure still valid, or was it built from data that has since changed?"
  Verified e2e: mutate an upstream input → its consumer goes input-stale
  and that consumer's consumer goes transitive-stale.

**Architecture invariant now enforced in CI** (`94d661f`): a new
preflight check fails the build if the reasoning layer (`server/`,
`tools/`, `protocols/`) ever imports the daemon. The dependency arrow
(daemon → server, never the reverse) is the spine of DESIGN_V4.md §6 and
can no longer silently reverse as the daemon grows.

**Run lifecycle is now complete for single runs + chains:**
`run`/`submit` → `track` → `journal` → `reproduce` → `diff` →
`lineage` → `stale`. Local and HPC unified through one path; every stage
is pure-stdlib-comparable and works without the daemon being up.

**Next BUILD candidates (DESIGN_V4.md):** the lineage + staleness pair
naturally sets up (a) **selective re-run** — given a stale set, re-run
only the affected sub-DAG in dependency order (a minimal make/snakemake
without the DSL, built on data we already have); and (b) the **read-only
HTTP surface** for lineage/staleness so a future dashboard can render
the DAG. Re-run leans on existing `reproduce_run`; it's the higher-value
of the two and keeps the build CLI-first before adding transports.

### Phase log: 1.15 (2026-06-23) — selective rebuild (the minimal make)

* **1.15 — `daemon rebuild`** (`1d26dd6`). Closes the correctness loop:
  detect stale → fix exactly what's stale, in order. `lineage.topo_order`
  (Kahn's algorithm, subset-restricted, deterministic tie-break) orders
  the stale set producers-first; `core.rebuild_stale` reproduces each in
  turn, **re-assessing freshness between steps** so fixing an upstream
  result clears its descendants' transitive staleness — a descendant only
  rebuilds if still stale when its turn comes. `--dry-run` previews the
  plan. This is a minimal `make`/snakemake built entirely on
  content-addressing — no DSL, no manual dependency graph; the DAG comes
  from input/output hashes already captured.

* **fix(reproduce) — reproduced runs stay in the provenance graph.**
  Found while building rebuild (exactly what JUDGE is for): `reproduce_run`
  (Phase 1.10) re-ran the recorded command but did NOT forward the
  original run's input paths, so every reproduced run recorded zero
  `provenance.inputs` and dropped out of lineage + freshness as "no
  recorded inputs". Now it propagates the original input paths (resolved
  to absolute against the run's cwd, then re-hashed fresh against current
  disk). Verified e2e: a rebuilt A→B→C chain produces a fresh, properly
  linked repro sub-DAG, and the new repro runs read each other's fresh
  outputs (repro-C consumes repro-B's new output, hash-matched → fresh).

**Run lifecycle is now a complete correctness loop:**
`run`/`submit` → `track` → `journal` → `reproduce` → `diff` →
`lineage` → `stale` → `rebuild`. A researcher edits a data file and
`daemon rebuild` re-runs precisely the affected downstream work in the
right order — the defining capability of a research *OS* over a job
runner. Next BUILD candidate: the read-only HTTP surface for
lineage/staleness/rebuild-plan (sets up the dashboard transport without
touching the CLI-first core).

### Phase log: 1.16 (2026-06-23) — domain profiles (field-awareness)

**Problem.** The protocol library is deliberately mostly `domain: [any]`
— broad, generic reasoning scaffolds. That breadth is a strength, but it
left the system field-agnostic: a chemist, an economist, and a historian
got identical defaults. Hand-authoring 50 protocols per field doesn't
scale and is the wrong abstraction.

**Decision — a daemon-level domain layer, not protocol sprawl.** Added
`daemon/domains.py`: a small declarative registry of research-field
profiles (8 built-ins spanning compbio, data/ML, physical sciences,
social sciences, qualitative, humanities, clinical/health, and
geo/environmental) plus a fallback. Each profile carries idiomatic
languages, the artifacts that are the *real* deliverables, what
reproducibility means in that field, and a one-line orientation for the
AI. One profile makes the ENTIRE existing protocol library field-aware
for that domain — the generic `[any]` protocols inherit sensible
defaults. Adding a field is a ~30-line entry, not 50 protocols.

* **Auto-detection** (`detect(root)`): declared `domain:` in
  researcher_config wins (confidence 1.0); otherwise score every profile
  by marker files (weight 3) + file-glob hits (capped) over a bounded
  4k-file scan, pick the best, confidence by signal share. Never raises;
  empty/unknown → neutral GENERIC fallback. Tolerant resolver matches by
  id, alias, or keyword substring.
* **Surfaced on every transport.** New `research-os daemon domain`
  (text + `--json` + `--list`) and a read-only `GET /v1/domain` endpoint
  (with `?root=` override) so the future gateway + dashboard get
  field-awareness for free. Strangler-fig respected: lives entirely in
  `daemon/`; reasoning layer never imports it (preflight invariant still
  green).
* **Tested** (`tests/unit/test_daemon_domains.py`, 16 cases): resolution
  by id/alias/keyword/fallback, file-signal detection, declared-override
  precedence, garbage-config robustness, serialization shape, frozen
  profiles. Verified e2e via CLI + Starlette TestClient.

This is the daemon getting smarter about *who it serves* — the
complement to the run-lifecycle work, which made it smarter about *what
it runs*. Next: the read-only HTTP surface for lineage/staleness so the
dashboard can render both the provenance DAG and the project's field.

### Phase log: 1.17 (2026-06-23) — read-only HTTP surface for lineage / staleness / rebuild-plan

**Problem.** The run-lifecycle correctness loop (lineage → stale →
rebuild, Phases 1.13–1.15) was CLI-only. The daemon already served
`/v1/state`, `/v1/runs`, `/v1/domain` — but the provenance DAG and the
freshness verdict, the most *visual* data in the system, had no
transport. The dashboard (Phase 5) and the gateway's context injection
(Phase 2) both need them.

**Decision — expose the SAME pure functions over HTTP, read-only.**
Added three GET endpoints to `daemon/server.py`, each a thin wrapper over
the existing pure logic (no new computation, no duplicated rules):

* `GET /v1/lineage` — the content-addressed dependency graph
  (`lineage.build_lineage`). `?run_id=` adds a `focus` block with that
  run's ancestors + descendants.
* `GET /v1/staleness` — the freshness verdict (`staleness.assess`): which
  results were built from inputs that have since changed on disk, with
  transitive propagation down the DAG.
* `GET /v1/rebuild/plan` — what a rebuild WOULD re-run, ordered
  producers-first (`lineage.topo_order` over the stale set). **Dry-run
  only by design** — the actual rebuild is a mutation and stays on the
  CLI / a future authenticated POST. The response says so explicitly.

All three accept an optional `?root=` override (multi-project daemon) and
a validated `?limit=` (400 on garbage), and degrade gracefully to
`{"available": false}` when no run journal is resolved — never a 500.

* **DRY refactor.** Extracted `provenance.hash_fn_for_root(root)` — the
  single source of truth for resolving a recorded (possibly relative)
  input path against the project root before re-hashing on-disk state.
  Both `daemon stale` (CLI) and `/v1/staleness` now share it, so their
  verdicts can never drift apart. CLI output verified byte-identical
  after the swap.
* **Tested** (`tests/unit/test_daemon_server.py`, +6 cases over a real
  2-run A→B chain built via `build_manifest`): graph counts, focus
  ancestors, staleness flagging (missing input → A input-stale → B
  transitive-stale), producers-first plan ordering, bad-limit 400, and
  the no-runstore `available:false` path. Verified e2e against a live
  mutated workspace via Starlette TestClient.

The reasoning layer still never imports the daemon (preflight invariant
green). Next BUILD candidate: Phase 2 — the OpenAI-compat
`/v1/chat/completions` gateway, the big AI-integration win, which can now
inject domain + lineage + freshness context into every conversation.

### Phase log: 2.0 (2026-06-23) — OpenAI-compatible chat-completions gateway

**The keystone.** Every prior phase made the daemon a better *backend* —
this one makes it an *AI endpoint*. `POST /v1/chat/completions` accepts an
OpenAI-format request from any client (the OpenAI SDK, Hermes, Claude
Code, Cursor, `curl`, a notebook), and turns it into a field-aware,
provenance-aware research agent without the client knowing anything about
Research-OS.

**The request lifecycle** (all in `daemon/gateway.py`, network-free core):

1. **Route.** The latest user turn goes through the existing protocol
   router (`route_request`) — same engine the MCP server uses. It picks
   the primary protocol, decomposition, and active tools.
2. **Inject context.** `build_context_block` assembles a system message
   from three live signals: the detected **research field** (domain
   profile + confidence), the **protocol guidance** (what good reasoning
   looks like for this intent), and **result freshness** (how many recorded
   results are stale vs. their inputs). This is the value-add: a generic
   LLM suddenly knows it's doing *this kind of research, in this field,
   against results in this state*.
3. **Advertise tools.** `TOOL_DEFINITIONS` (all engine tools) convert to
   OpenAI tool-schema and ride along, so the model can call them.
4. **Forward.** The enriched request goes to a configured upstream
   (any OpenAI-compatible server: OpenAI, vLLM, Ollama, a local model)
   via a swappable forwarder (`_make_upstream_forwarder`, urllib).
5. **Hook tool calls.** When the model returns `tool_calls` for
   Research-OS tools, the gateway executes them through the dispatch
   seam (`server/dispatch._handle_tool_call`) and loops — up to
   `gateway_max_tool_rounds` — until the model answers. The final
   response is stamped with `x_research_os` routing metadata.

**Security — mutating surface, so it's locked down by default.** The
gateway is OFF unless `enable_gateway` is set, and it REFUSES to serve
without a per-session bearer token (`RESEARCH_OS_GATEWAY_TOKEN`).
Status codes are precise: 503 disabled / 503 unconfigured-token / 401
bad token / 400 bad body / 502 upstream error / 200 success. Tokens and
the upstream API key live in **environment variables, never in config
files**.

**Config.** New `daemon:` knobs (project file + env, all validated):
`enable_gateway`, `gateway_upstream_base_url`, `gateway_upstream_model`,
`gateway_api_key_env`, `gateway_token_env`, `gateway_max_tool_rounds`,
`gateway_timeout`.

**CLI.** `research-os daemon gateway` prints a readiness checklist
(enabled / session token / upstream key set) with `--json`, and
`--mint-token` generates a strong token. `daemon status` already shows
`gateway: on/off`.

**Tested** (22 new, all green): `tests/unit/test_daemon_gateway.py` (14)
covers the context builder, tool-schema conversion, and the tool-call
loop with a fake upstream; `tests/unit/test_daemon_server.py` (+8) covers
the HTTP endpoint — auth gating, disabled/unconfigured, bad body, happy
path (with metadata stamped), and upstream error. The gateway module has
**zero top-level imports of the reasoning layer** (AST-verified +
preflight invariant green) — the strangler-fig arrow still points
daemon → server, never the reverse.

This is the moment Research-OS stops being "an MCP server you wire into
one IDE" and becomes "a localhost research brain any agent can call."
Next: the design-improvement pass — making the system the best possible
substrate for researchers and AI agents across every field, depth, and
mode of work.

### Phase log: 2.1 (2026-06-23) — `/v1/capabilities`, the agent front door

**Problem (JUDGE).** Phase 2 made the daemon callable, but an AI agent
arriving cold (Hermes, Claude Code, Cursor, a bare OpenAI client) had no
way to *orient* in one shot. "What is this? What field is my project?
What tools and protocols exist? Is my recorded work fresh or stale? Is
the chat endpoint even live?" — all of that was scattered across
`/v1/domain`, `/v1/state`, `/v1/staleness`, and tool-call trial-and-error.
Discoverability is the single highest-leverage ergonomics win for the
"any agent, any field" goal: an agent that can introspect the system uses
it correctly without a human pre-briefing it.

**Decision — one read-only, self-describing GET.** `GET /v1/capabilities`
returns a complete orientation snapshot, assembled by a new pure
`gateway.build_capabilities(daemon)`:

* **identity** — service, version, tagline, and the full endpoint map
  (so the agent learns every other route from this one call).
* **field** — the project's detected research domain + confidence +
  detection source + languages + deliverables (chemistry vs. history vs.
  ML get oriented differently).
* **tools** — a categorized inventory (counts + names by category;
  152 tools / 34 categories on this repo). Full OpenAI schemas ride along
  only with `?tools=full`, keeping the default payload cheap.
* **protocols** — counts of reasoning scaffolds grouped by category
  (142 / many categories), globbed straight from the protocol dir.
* **work_state** — recorded-result count + fresh/stale split, so the
  agent knows whether it's walking into clean or stale work.
* **gateway** — readiness booleans only (enabled / token_set /
  api_key_set / model). **No secret value ever appears in the payload.**

Every section is best-effort and degrades to `null` rather than raising —
orientation must never 500. `?root=` overrides for the multi-project
daemon. Like the rest of the daemon, `build_capabilities` does pure
read-only orchestration over engine + daemon public surfaces with
**zero top-level reasoning imports** (AST-verified, preflight green).

**Tested** (10 new): `test_daemon_gateway.py` (+4) covers no-root
self-description, field+state with a root, opt-in schemas, and the
no-secrets guarantee; `test_daemon_server.py` (+2) covers the endpoint
lean + `?tools=full`. Verified live against this repo (field=ML 0.31,
152 tools, 142 protocols, work-state fresh/stale split).

Why this first in the improvement pass: an agent that can *see* the whole
system is the precondition for everything else (streaming, sandboxing,
dashboards). Discoverability compounds.

### Phase log: 2.2 (2026-06-23) — streaming gateway (stream:true → SSE)

**Problem (JUDGE).** Phase 2's gateway only returned a single JSON blob.
Every modern chat UI and most agent runtimes (the OpenAI SDK, LangChain,
LiteLLM, Open WebUI) default to `stream:true` and expect a
`text/event-stream` of `chat.completion.chunk` frames. Without it, those
clients either error or hang — a hard blocker for "any agent can point at
the daemon."

**Decision — stream the resolved answer, honestly.** The gateway runs a
*multi-round tool-call loop* (it may call several Research-OS tools before
the model produces a final answer), so it cannot truthfully stream tokens
token-by-token mid-loop — there is no single upstream token stream to
relay. Rather than fake it, `gateway.to_stream_chunks(result)` runs the
loop to completion, then re-emits the final assistant message as the
standard OpenAI chunk sequence:

1. role-priming chunk (`delta={"role":"assistant"}`)
2. one content chunk with the full answer
3. a terminal chunk carrying `finish_reason` + the `x_research_os` routing
   metadata mirrored onto the chunk (streaming clients still see routing)
4. the `data: [DONE]` sentinel

`chat_completions` branches on `body.get("stream")`: truthy → a starlette
`StreamingResponse(media_type="text/event-stream")` with
`Cache-Control: no-cache` and `X-Accel-Buffering: no` (so reverse proxies
don't buffer); falsy → the existing `JSONResponse`. **Auth, enable-flag,
and body validation all run before any stream is opened** — error paths
stay JSON, never a half-open stream.

`to_stream_chunks` yields plain strings (pure, fully testable); only the
server wraps it in the ASGI response. No new top-level imports of the
reasoning layer; the strangler-fig invariant holds.

**Tested** (4 new): `test_daemon_gateway.py` (+2) covers the chunk shape
(4 frames: role / content / terminal-with-metadata / [DONE]) and the
empty-content case (content frame skipped); `test_daemon_server.py` (+2)
covers the live SSE endpoint (`text/event-stream`, chunks present, ends
with `[DONE]`) and that streaming still enforces auth (401 stays JSON).

With this, the daemon speaks the full OpenAI streaming contract — you can
point Open WebUI, the OpenAI SDK, or any streaming agent client straight
at it and watch field-aware, protocol-routed, tool-using answers stream
back.

### Phase log: 2.3 (2026-06-23) — /v1/orient, the "standup" endpoint

**Problem (JUDGE).** `/v1/capabilities` answers *"what can this system
do?"*. It does not answer the other half a returning researcher — or a
fresh agent picking up someone else's project — needs first: *"where are
we, and what should I do next?"* That state was reconstructable (field +
run journal + staleness all exist as separate endpoints), but only by an
agent that already knew to call three endpoints and synthesize them. The
single highest-leverage ergonomics win for **cross-session /
cross-agent continuity** is to do that synthesis server-side and hand back
a brief plus ONE concrete next step.

**Decision — synthesize, don't store.** New pure module `daemon/orient.py`
composes data that already exists into:

* **field** — detected research domain + confidence + source.
* **work** — run-journal activity: total, counts by status, the newest few.
* **freshness** — fresh/stale split over the lineage DAG, plus the
  dependency-ordered rebuild plan when anything is stale.
* **narrative** — one short human-readable paragraph ("This is a
  Data science / machine learning project with N recorded run(s); X fresh
  and Y stale…").
* **recommended_next_action** — a small, transparent decision tree (NOT a
  model call), in priority order: stale results → `rebuild_stale` (with
  the exact plan); a failed run → `investigate_failure`; empty journal →
  `record_first_result`; all clear → `proceed`. Each carries `why` + `how`
  so it's actionable or overridable.

`GET /v1/orient` exposes it (`?root=` overrides, `?limit=` caps the run
scan). Every section is best-effort and degrades to a sensible empty value
rather than raising — orientation must never 500. With no journal,
`available=false` but field + recommendation (`record_first_result`) are
still returned. `build_orientation` does pure read-only orchestration over
engine + daemon public surfaces with **zero top-level reasoning imports**
(AST-verified, preflight green).

**Tested** (7 new): `test_daemon_orient.py` (6) covers no-root
self-orientation, empty-journal → record-first, and each recommendation
branch (rebuild / investigate / proceed) plus JSON-serializability;
`test_daemon_server.py` (+1) covers the live endpoint. Verified live
against this repo (field = Data science / machine learning, 2 recorded
runs, correctly recommending investigation of the 2 failed runs). Fixed
one bug found in live verification: the detected field label is nested
under `profile` in `DetectionResult.as_dict()`, not flat.

The daemon now offers a clean arc for any caller: **discover**
(`/v1/capabilities`) → **orient** (`/v1/orient`) → **converse with tools**
(streaming gateway). That is the shape of a localhost research brain any
agent can walk up to cold and be productive in three calls.

### Phase log: 2.4 (2026-06-23) — /v1/workflows, pipeline DAG awareness

**Problem (JUDGE-7).** Real computational research is rarely one command;
it is a *pipeline* — a DAG of steps with file dependencies, driven by
Snakemake or Nextflow. The universal `SubprocessRunner` (runners.py) can
already *execute* `snakemake`/`nextflow` as ordinary commands, so the gap
was never execution. It was **awareness**: before launching a pipeline, a
researcher (or an agent driving the project) wants to know *what steps
exist and what would run* — the same read-only "show me the plan" insight
the daemon already gives for rebuilds (staleness), capabilities, and
orientation. A pipeline you can run but not inspect is a black box.

**Decision — detect always, introspect when possible.** New pure module
`daemon/workflows.py`, two read-only layers:

* `detect_workflows(root)` — filesystem-only. Finds `Snakefile`,
  `workflow/Snakefile`, `*.smk` (snakemake) and `main.nf`, `*.nf`,
  `nextflow.config` (nextflow), deduped by resolved path. Always works,
  even with no engine installed — and on a login node / shared host
  (this one included) the engines usually aren't.
* `introspect_workflow(root, engine, path)` — probes the driving binary;
  if present, runs the engine's native dry-run (`snakemake -n -q` /
  `nextflow run … -preview`, 30s cap) and parses the planned step list
  (rule/checkpoint names for snakemake, `process > NAME` for nextflow).
  If the binary is absent, degrades to detection-only with a clear,
  actionable install note. Never raises, never 500s, never blocks.

`survey_workflows(root, introspect=…)` ties them together for
`GET /v1/workflows` (`?root=` overrides, `?introspect=false` skips the
dry-run for a cheap detection-only read). Best-effort throughout;
`build`-invariant clean (zero top-level reasoning imports, AST-verified).

This mirrors the SLURM decision (schedulers.py): the same graceful-degrade
posture that keeps Research-OS honest on a host with no Docker and no
`sbatch` now extends to no `snakemake` / no `nextflow` — it tells you
exactly what it found and exactly what it would need to show you more,
rather than pretending or crashing.

**Tested** (12 new): `test_daemon_workflows.py` (11) covers detection of
both engines, `*.smk` glob, path dedup, empty/missing root, both step
parsers against captured dry-run samples, the engine-absent degrade path,
that detection-only never shells out, JSON-serializability, and
never-raises; `test_daemon_server.py` (+1) covers the live endpoint.
Verified live against a throwaway Snakefile (detected, degraded with the
correct install hint since snakemake is absent here). daemon slice 187
pass; ruff + preflight 34/34 green.

### Phase log: 3 (2026-06-23) — the MCP↔daemon bridge (`sys_daemon`)

**Problem.** Everything Phases 2.1–2.4 added — capabilities, orient,
workflows, lineage, staleness, the run journal — lives behind the
daemon's HTTP surface. A researcher working through MCP (Claude Code,
Cursor) got *none* of it: the MCP session was blind to a running daemon.
The two surfaces had diverged. Ask "is anything running in the
background, and what should I do next?" inside MCP and there was no
answer, even with a daemon actively serving the same project.

**Decision — a discovery handshake + a read-only bridge tool, with the
seam intact.** The daemon and an MCP session are separate processes, so
they need a rendezvous that does NOT couple the reasoning layer to the
daemon package (the preflight-enforced v4 invariant: `server/` + `tools/`
never import `daemon/`).

* **Writer (daemon side).** New stdlib-only `daemon/discovery.py`:
  `write_discovery()` does an atomic temp-then-`os.replace` write of
  `<root>/.os_state/daemon.json` (schema, host, port, pid, version,
  started_at, base_url) on `serve()` start; `clear_discovery()` removes
  it on clean exit; plus `read_discovery()` and `pid_alive()`.
* **Reader (MCP side).** New `sys_daemon` tool. Its handler lives in the
  reasoning layer, so it must not import the daemon — it re-implements the
  trivial descriptor read (same on-disk *shape*, no import) with stdlib
  `json`, confirms the advertised PID is alive (`os.kill(pid, 0)`), then
  GETs the daemon's read-only `/v1/orient` + `/v1/jobs` over localhost
  with stdlib `urllib`, treating the daemon as an opaque HTTP service
  exactly as any external client would. Returns compact telemetry
  (narrative, the ONE recommended next action, detected field, live job
  counts by status). Degrades across every failure mode: no descriptor →
  `running:false` + start hint; corrupt/non-dict → not running; **stale
  PID → not running + stale hint**; alive-but-HTTP-silent →
  `running:true, reachable:false`.

**Cleanup contract (a real finding, documented in code).** Live testing
showed uvicorn intercepts SIGTERM/SIGINT and exits the process *without*
unwinding back through `serve()`'s `finally` (and an `atexit` hook didn't
fire either) — so the descriptor can outlive the daemon, and SIGKILL can
always orphan it. Rather than fight uvicorn's signal machinery, the
design makes **the reader the source of truth**: a descriptor is only
ever a *hint*, and liveness is confirmed by checking the PID on every
read. This is exactly how `/var/run/*.pid` files work. A leftover file is
harmless — `sys_daemon` reports it stale.

The payoff: both surfaces now see the same world. An HTTP agent walks the
discover → orient → converse arc; an MCP session calls `sys_daemon` and
gets the same orientation + background-job awareness, inside the protocol
it already speaks. Cross-surface continuity, zero seam violation.

**Tested** (16 new): `test_daemon_discovery.py` (9) covers the
write/read round-trip, atomic-write (no `.tmp` left), idempotent clear,
missing/corrupt/non-dict reads, and PID-liveness (self alive, dead PID,
garbage). `test_sys_daemon_tool.py` (7) covers no-descriptor,
corrupt-descriptor, stale-PID, alive-but-unreachable, the full reachable
telemetry path, the jobs-count fallback when the daemon omits `counts`,
and timeout clamping. Verified **live end-to-end**: started a real daemon
→ confirmed `.os_state/daemon.json` written with the true PID → called
the `sys_daemon` handler against the live root → got `running:true,
reachable:true` with real `/v1/orient` telemetry (field, narrative,
`record_first_result` recommendation, job counts) → killed the daemon →
handler correctly reported `running:false` with the stale-descriptor
hint. daemon + bridge slice 203 pass; ruff + preflight 34/34 green;
seam check "server/ + tools/ never import daemon/" still green.

### Phase log: 4 (2026-06-23) — the tiered execution sandbox

**Problem.** The daemon runs untrusted-ish code on a researcher's behalf
— a downloaded analysis script, an LLM-generated snippet, a
collaborator's pipeline. It should bound the blast radius. The textbook
answer is "run it in an ephemeral Docker container," and the original
Phase 4 plan said exactly that: *Docker/Podman sandbox with native
fallback.* But probing the actual host this is built on (a shared
Argonne node, representative of the HPC/login boxes Research-OS targets)
killed that framing on contact: **docker is installed but its daemon is
unreachable/permission-denied, Podman/bwrap/nsjail are absent, and
unprivileged user namespaces are blocked** (`unshare --map-root-user` →
EPERM) despite permissive-looking sysctls. On a large fraction of real
research hosts the container path is simply not available, and
advertising a jail that doesn't exist is the same dishonesty
Research-OS refuses for no-sbatch / no-snakemake.

**Design.** `daemon/sandbox.py` (stdlib only) detects the strongest
isolation the host *actually* offers and degrades transparently through
three tiers, strongest first:

  1. **container** — a working docker/podman runtime (verified by probing
     `info`, not just `which`): ephemeral `--rm` container, `--network
     none`, `--memory`, volume-mounted workdir, configurable image
     (`$RESEARCH_OS_SANDBOX_IMAGE`).
  2. **namespace** — bwrap or `unshare` *with usable userns* (tested by
     actually attempting the uid-map, since sysctls lie): filesystem +
     network isolation, no runtime needed.
  3. **resource** — ALWAYS available on POSIX: hard rlimit caps
     (RLIMIT_AS / CPU / FSIZE / NOFILE) applied via a `preexec_fn` plus a
     wallclock `timeout` guard. No FS/net isolation, but a bounded blast
     radius even where everything else is denied.

`SandboxCapabilities.resolve_tier(requested)` degrades **down** to the
strongest supported tier ≤ requested, never silently **up**. The
detector is cached and never raises (a failed probe is a legitimate
"tier unavailable" answer). `SubprocessRunner` gained an opt-in
`sandbox=` policy: it wraps the argv per tier, applies the rlimit
preexec, and records the *effective* tier (which may be weaker than
requested) on `RunResult.sandbox`. New read-only `GET /v1/sandbox`
reports the host's tiers + default limits so an agent discovers
isolation *before* submitting work; also surfaced in `/v1/capabilities`
endpoints (alongside the previously-missing `orient` + `workflows`).

**Shared-host lesson (baked into the defaults).** The first live run
failed with `timeout: fork: Resource temporarily unavailable` — the
default RLIMIT_NPROC=256 counts *all of the user's* processes, not this
run's tree, so on a busy shared node the very fork that launches the
workload dies. RLIMIT_NPROC now defaults **OFF** (opt-in only on a
dedicated host); a footgun that's safe on a laptop is a denial-of-self
on HPC.

**Tested** (18 new — `test_sandbox.py` + 1 server test): tier
degrade-down/never-up logic, host-independent detection via mocked
probes (incl. the "docker installed but daemon dead → resource floor +
explanatory note" case), per-tier command wrapping, and a **genuine
end-to-end rlimit that bites** — a 512 MB allocation under a 128 MB
RLIMIT_AS cap is killed, proving the preexec is enforced not cosmetic.
Verified **live**: `GET /v1/sandbox` on this host returns `best_tier:
resource` with the honest container-unusable + userns-blocked notes and
`processes: null`. daemon slice green; ruff + preflight 34/34; seam
check still green (sandbox is daemon-side only — reasoning never imports
it).


### Phase log: enforcement-kernel arc (2026-06-24) — the daemon becomes a real authority layer

A reframe-driven arc (not a numbered phase): the daemon stops being a
read-only observability surface and becomes the **enforcement + execution
+ notification layer between the client and the work** — the role the
intent always described. Five commits, each green (pytest 0 / preflight
36 / ruff / seam clean), each mapping to a named researcher pain. Full
designs in `docs/v4/{UNSKIPPABLE_GATES,HYBRID_ARCHITECTURE,STALENESS_GATE,
NOTIFICATION_SPINE}.md`.

* **Un-skippable gates — daemon as consent authority** (`653f0a6`). The
  floor gates were enforced in-process via the agent's own
  `confirmed=true` — the lock's key taped to the door. Now when a daemon
  runs it is the consent AUTHORITY: clearing a gate needs a daemon-minted
  token (one-shot, TTL'd, bound to gate_key + arg fingerprint) the agent
  cannot forge. `server/consent.py` reads the daemon-owned ledger by
  shape; `daemon/consent.py` mints; gate burns the token (spent sidecar)
  so one approval clears exactly one action. No daemon → degrade to
  today's `confirmed=true`. Live-verified the full round trip; one-shot
  defect caught by live verification, not unit tests.

* **Hybrid gate layer — protocols declare, engine enforces** (`35378de`).
  Floor gates lived in two hand-synced sources (protocol prose +
  `autopilot_gate.py` Python). Now protocols DECLARE gates in an
  `enforcement.gates` YAML block; `scripts/build_gate_meta.py` compiles
  every block into `protocols/_gate_meta.json`; the engine derives its
  tables from it (legacy tables kept only as a sidecar-absent fallback).
  Preflight `check_gate_meta` guards prose↔code drift. Proven
  behaviour-preserving via a 108-cell autonomy×strictness×tool matrix
  (byte-identical). The partition (per PROTOCOL_DOCTRINE): keep reasoning
  soft, make system rules hard — never harden reasoning.

* **Staleness gate — block deliverables built on changed data**
  (`4ea3bed`). Generalises the gate from "is this action dangerous?" to
  "is the world safe for this action?" New `world_state: no_stale_inputs`
  predicate fires on `tool_typst_compile` when a daemon has determined
  results were built from inputs that changed on disk. Daemon writes a
  verdict sidecar (`POST /v1/staleness/verdict`); `server/staleness_state.py`
  reads it by shape with a freshness-of-the-freshness-check (a verdict
  older than the newest run is ignored). Fail-safe direction is
  *deliberately* toward NOT blocking when there is no current claim — no
  false positives for the default no-daemon flow.

* **Notification spine — tell the researcher when work finishes**
  (`a019c3b`). Intent #4 had no implementation: long jobs finished
  silently and `sys_notify` only appended to a log file. Now one durable
  append-only outbox (`.os_state/notifications/outbox.jsonl`) + a
  pluggable `notify_command` (researcher wires their own channel —
  Hermes→Slack, mailx, webhook). Terminal job events feed it; `sys_notify`
  also feeds it when a daemon is present (by shape, no daemon import).
  `GET /v1/notifications` + `research-os daemon notifications` surface it.
  Best-effort delivery, recorded per record, never breaks the job.

* **Drift guards + CLI parity** (`cc2ba83`, `3b66a13`). The daemon
  endpoint catalogue in the server docstring is now preflight-guarded
  (`check_daemon_endpoints_documented`) so docs can't drift from routes;
  the notification spine got a CLI surface matching `daemon stale` /
  `daemon lineage`.

The seam invariant held throughout: the reasoning layer (`server/`,
`tools/`) never imports `daemon/`; every cross-process contract is an
on-disk sidecar read by shape, fail-safe, with a legacy fallback. This is
the reusable pattern for any future daemon-enforced rule.


