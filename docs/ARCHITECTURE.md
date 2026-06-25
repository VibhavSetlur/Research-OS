# Research OS — Architecture

> **The system's architecture and design rationale.** What the MCP server
> is, what the daemon is, what moves and what stays, where protocols live,
> and the design principles that hold the line. Read alongside
> [`ROADMAP.md`](ROADMAP.md) (the build log + design history) — this is the
> *why* and the *what*; the roadmap is the *when*.

---

## 1. The system as it actually is today

Two numbers frame everything:

| Surface | Size | Role |
|---|---|---|
| `server/` (MCP) | the tool surface, 15 handler modules | The reasoning engine. Tools + protocols + router + ledger. |
| `daemon/` | execution + transport spine | Runs, schedulers, journal, provenance, recovery. |
| `protocols/` | the protocol library, 14 categories | Scaffolds for reasoning — the "how to think" layer. |

The critical property of this split: there is **exactly one seam** between
them, and it is clean.

```python
# server/dispatch.py
def _handle_tool_call(name: str, arguments: dict, root: Path) -> list[TextContent]:
    # rate-limit -> resolve alias -> autopilot gate -> _HANDLERS[name](...) -> normalize envelope
```

Every one of the tools is reachable through this single function. The
router (`router.route_request`) and the state engine (`ResearchLedger`,
JSON under `.os_state/`) sit *behind* it. This is what makes the
strangler-fig viable: **the daemon never reimplements a tool. It fronts
`_handle_tool_call` and inherits all of them for free.**

---

## 2. The architectural thesis: FRONT, don't MOVE

The instinct "move tools to the daemon" is wrong. Here is the correct
decomposition, by layer:

### Layer A — Reasoning (STAYS in `server/`, unchanged)
The tools and protocols are *pure functions over project state*.
They take `(name, args, root)` and return an envelope. They have no
concept of transport, sessions, or concurrency. **They should never learn
about HTTP or daemons.** Moving them into the daemon would couple
reasoning to transport — the exact mistake v4 exists to undo.

- Tools stay where they are. The daemon imports `_handle_tool_call`.
- Protocols stay as YAML under `protocols/`. They are read by the router,
  which the daemon also fronts.
- `ResearchLedger` stays the source of truth for project state.

### Layer B — Execution (LIVES in `daemon/`, already built)
Anything with a *lifecycle* — something that starts, runs over time,
produces artifacts, can fail, can be reproduced — belongs to the daemon.
This is what 1.7–1.12 built: runners, schedulers, journal, provenance,
artifacts, reproduce, compare. The MCP `exec` tools should eventually
*delegate* to the daemon's runners instead of spawning subprocesses
inline (so an agent-initiated run and a CLI-initiated run share one
lifecycle, one journal, one reproduce path).

### Layer C — Transport / Gateway (LIVES in `daemon/`, partly built)
The multi-protocol front: OpenAI-compat completions, MCP sidecar, HTTP
read API, SSE event stream, web dashboard. These translate external
protocols into `_handle_tool_call` + daemon-execution calls. **This is
the only layer that should know about wire formats.**

### The one real migration
The MCP `exec`/run tools (`tool_exec_*`) currently spawn subprocesses
directly. They should be rewired to call `daemon.run_command` so that:
- agent-run code and human-run code share the journal + provenance,
- reproduce/diff work on agent runs too,
- there is one execution audit trail, not two.

That is the *only* thing that "moves." Everything else *fronts*.

---

## 2a. Background-safety guarantees (what the daemon actually promises)

The daemon's reason to exist is that research jobs are long and people walk
away from them. So the execution spine ships with a concrete safety
contract — these are guarantees, not aspirations, and each maps to a
running piece of `daemon/`:

| Guarantee | Mechanism | Where |
|---|---|---|
| **Long jobs survive disconnect** | the daemon owns the process, not the IDE's MCP session; closing the chat doesn't kill the run | `runners`, `tasks` |
| **Everything that runs is journaled** | inputs/command/outputs + artifact hashes recorded per run; lineage DAG linked by content hash | `runstore`, `provenance`, `lineage` |
| **Runaway jobs are bounded** | per-run `rlimit`s (mem/CPU/wall/fsize/nofile) from `runtime.resource_budget`; a real kernel ceiling on a shared node | `resource_budget`, `sandbox` |
| **Consent gates hold unattended** | a floor gate needs a one-shot, argument-bound token only a human can mint; the AI can request but never grant | `consent` |
| **Stale results can't ship** | freshness verdict over the lineage DAG; compiling the final deliverable is blocked while inputs it depends on have changed | `staleness`, `lineage` |
| **You find out what happened** | every run-finish / interrupt emits a notification, delivered via `notify_command` or held in the outbox | `notifications`, `events` |
| **Interrupted runs recover** | on start, any run whose last persisted status was non-terminal is rehydrated as `INTERRUPTED`, the researcher is notified, and *orient* recommends `resume_interrupted` | `core` (rehydrate), `runstore` (`mark_interrupted`), `orient` |

### The interrupted-run recovery path (the "box rebooted" case)

This is the newest of the seven and the one that makes "walk away" safe.
The flow is entirely server-side and needs no client present:

```
daemon start
   └─ runstore.recent_manifests()            # read the run journal
        └─ any run with non-terminal status?  # it looked live; the daemon is fresh ⇒ it died mid-run
             └─ runstore.mark_interrupted(id) # rewrite manifest status → INTERRUPTED (+ transition)
                  └─ notifications.emit_runs_interrupted(ids)   # push or outbox
                       └─ orient: action="resume_interrupted"   # surfaced FIRST among run states
```

Rehydration is idempotent and best-effort — a failure to rehydrate logs at
debug level and never blocks startup. The *orient* logic deliberately ranks
an interrupted run **above** a failed one: a half-finished job that *looks*
complete is the most dangerous thing a returning researcher can build on,
so the AI is told about it first and steered to finish it before proceeding.

---

## 3. Where protocols live, and how they get better

Protocols stay as YAML. But today they are **only reachable reactively**
— the router picks one when a tool call arrives. The daemon unlocks three
new modes:

1. **Proactive protocol execution.** The daemon can *drive* a protocol as
   a long-running plan: step through a multi-stage methodology, parking
   between steps, surviving client disconnects. Today a protocol is a
   suggestion the agent may ignore; the daemon can make it a *tracked
   workflow* with state.
2. **Protocol-as-DAG.** A protocol's `decomposition` is implicitly a
   dependency graph. The daemon can compile it into an executable DAG
   (run step 3 only after 1+2 succeed) — this is the snakemake/nextflow
   convergence point, done natively.
3. **Protocol provenance.** Every protocol step that touches execution
   gets journaled, so "which protocol produced this figure" is answerable.

The improvement: protocols evolve from *static reasoning scaffolds* into
*resumable, audited, partially-executable workflows* — without rewriting
a single YAML, because the daemon reads the same files.

---

## 4. The 50 features — a roadmap toward the maximal research OS

Grouped by the value they deliver to a researcher. Each is sized to be a
single BUILD phase. ✅ = already shipped (1.7–1.12).

### A. Run lifecycle & reproducibility (the foundation)
1. ✅ Durable run journal + provenance capture
2. ✅ Artifact tracking (cwd-diff, sha256)
3. ✅ Human CLI surface (run/runs/logs)
4. ✅ Reproduce-a-run (byte-level verdict)
5. ✅ HPC scheduler runner (SLURM submit/poll/cancel)
6. ✅ Run comparison / experiment diff
7. **Run lineage graph** — "this figure came from run B, which used the
   output of run A" — a DAG of runs linked by artifact-hash provenance.
8. **Re-run with overrides** — `daemon run --from <id> --set SEED=42` to
   fork an experiment changing one variable, lineage preserved.
9. **Artifact garbage collection** — content-addressed artifact store with
   dedup + retention policy (shared-disk hygiene: a real need here).
10. **Run tagging & search** — tag runs (`--tag baseline`), query
    `daemon runs --tag baseline --since 7d --status ok`.
11. **Snakemake/Nextflow adapters** — workflow engines as run-kinds, so a
    pipeline gets one journal entry with per-rule sub-runs.
12. **Input registry** — hash + register input datasets so reproduce can
    verify inputs didn't drift, not just outputs.

### B. The gateway (multi-client, multi-protocol)
13. **OpenAI-compat `/v1/chat/completions`** — route → inject protocol +
    project context → forward to a backend model → hook tool calls back
    through `_handle_tool_call`. The headline feature.
14. **Anthropic-compat `/v1/messages`** — same, Claude-shaped.
15. **MCP sidecar (read-only telemetry)** — expose live daemon state
    (current runs, ledger) to any MCP host as resources.
16. **MCP sidecar (active)** — the full tool surface over MCP-against-daemon, so
    the daemon becomes the MCP server, shareable across clients.
17. **Per-session tokens & auth** — scoped session tokens; localhost-only
    by default, opt-in bind.
18. **Streaming over the event bus** — SSE/WebSocket stream of run output,
    state transitions, tool calls — one bus, many subscribers.
19. **Multi-workspace serving** — one daemon fronting several projects,
    routed by workspace id.
20. **Client session continuity** — a Cursor session and a CLI session
    observe the *same* project state simultaneously.

### C. Execution safety & environments
21. **Native execution sandbox** — resource limits (cpu/mem/walltime),
    no Docker (shared-server reality), via cgroups/ulimit.
22. **Conda env capture & restore** — record the exact env; reproduce can
    rebuild it (`conda env export` → lockfile in the manifest).
23. **Ephemeral env per run** — optional fresh env from a lockfile so runs
    can't pollute each other.
24. **Secret redaction in journals** — scrub tokens/keys from captured
    logs before they hit `.os_state/`.
25. **Dry-run / plan mode** — show what a run *would* do (command, env,
    expected artifacts) without executing.

### D. The research workflow itself (the point of it all)
26. **Proactive protocol driver** — daemon steps through a methodology
    protocol as a tracked, resumable plan.
27. **Protocol-as-DAG executor** — compile a protocol decomposition into a
    dependency graph and run independent steps in parallel.
28. **Experiment tracking dashboard** — read-only web UI: runs table,
    artifact previews, diff viewer, lineage graph.
29. **Literature ingestion pipeline** — long-running batch fetch of N
    papers as a daemon job (the canonical "MCP can't do this" case).
30. **Citation graph builder** — build + serve a citation network from the
    project's literature, queryable.
31. **Notebook execution as runs** — execute a `.ipynb` as a tracked run,
    artifacts = output cells + figures.
32. **Hypothesis ledger** — register hypotheses, link runs as evidence
    for/against, track the research narrative.
33. **Auto-provenance for figures** — every figure written during a run is
    stamped with the run id + git commit in its metadata.
34. **Result freshness checks** — daemon periodically re-reproduces key
    runs and flags any that have drifted (CI for science).
35. **Data versioning** — DVC-style content-addressed dataset tracking
    integrated with the input registry (#12).

### E. Observability & operations
36. **Structured metrics** — Prometheus-style `/metrics` (run counts,
    durations, failure rates, queue depth).
37. **Run timeline / Gantt** — visualize concurrent runs over wall-clock.
38. **Health & self-diagnosis** — `daemon doctor` checks scheduler
    availability, disk, env, port, ledger integrity.
39. **Log aggregation & tail** — `daemon logs --follow` live-tail any run,
    `daemon logs --grep`.
40. **Crash recovery** — ✅ interrupted-run rehydration shipped (daemon
    restart marks orphaned non-terminal runs `INTERRUPTED`, notifies, and
    *orient* recommends `resume_interrupted`). Still to do: re-attach to
    in-flight SLURM jobs by recorded scheduler job id instead of orphaning
    them.

### F. Collaboration & sharing
41. **Run export / import** — bundle a run (manifest + artifacts + env) as
    a portable archive for a colleague to reproduce.
42. **Shareable reproduce reports** — a self-contained HTML reproduce
    verdict (for a paper's supplement).
43. **Project snapshot** — freeze the whole project state (ledger +
    runs + artifacts) at a tag.
44. **Read-only share link** — serve a project dashboard read-only to a
    collaborator on the same network.
45. **Audit log export** — full chronological event log of every action
    for a methods section.

### G. Intelligence & ergonomics
46. **Smart run suggestions** — "you changed `train.py`; re-run the 3 runs
    that depend on it?" (uses lineage graph).
47. **Failure triage** — on a failed run, surface the error + the diff vs
    the last successful run of the same command.
48. **Cost/resource accounting** — track cpu-hours / SLURM allocation per
    project, per experiment.
49. **Natural-language run query** — "show me the run that produced
    fig3.png" answered from provenance.
50. **The completion loop** — the OpenAI gateway + protocol driver +
    execution + reproduce all wired so an AI client can run an entire
    research methodology end-to-end, tracked and reproducible, from a
    single chat — the thing no current tool does.

---

## 5. Build order (dependency-aware)

The features aren't independent. The critical path:

```
[done] run lifecycle (1–6)
   │
   ├─ 7 lineage ─ 8 re-run-overrides ─ 46 suggestions ─ 49 NL query
   ├─ 12 input registry ─ 35 data versioning ─ 34 freshness
   ├─ 22 env capture ─ 23 ephemeral env ─ 21 sandbox
   │
   ├─ 18 event-bus streaming ─┬─ 13 OpenAI gateway ─ 14 Anthropic ─ 50 loop
   │                          ├─ 15/16 MCP sidecar
   │                          └─ 28 dashboard ─ 37 timeline ─ 44 share
   │
   └─ 11 workflow adapters ─ 27 protocol-DAG ─ 26 protocol driver
```

**Next three BUILD phases (recommended):**
- **1.13 — Run lineage graph (#7).** Cheap now (artifacts already hashed);
  unlocks suggestions, NL query, re-run-overrides, freshness. Highest
  leverage per LOC.
- **1.14 — Re-run with overrides (#8).** The natural follow-on; turns the
  journal from a record into an *experiment-forking* tool.
- **Phase 2 — OpenAI-compat gateway (#13).** The headline transport
  feature; everything in group B flows from the event bus + this.

After these, JUDGE pass on the whole execution layer before group C/D.

---

## 6. What "better" means concretely

Three principles to hold the line on through every phase:

1. **The reasoning layer stays pure.** No tool, no protocol ever imports
   from `daemon/`. The dependency arrow points one way: daemon → server,
   never back. (Enforce with a preflight check: grep `tool_definitions/`
   and `protocols/` for daemon imports → fail if found.)
2. **One execution path.** Agent-initiated and human-initiated runs go
   through the same `daemon.run_command`. No second subprocess spawner.
3. **Everything that runs is reproducible.** If it has a lifecycle, it
   gets a manifest. No "quick" untracked execution path that escapes
   provenance.

That is the whole design: a pure reasoning core (the MCP tools + protocols) fronted by a transport gateway and grounded by a reproducible
execution spine. Build outward from the spine; never let transport leak
into reasoning.
