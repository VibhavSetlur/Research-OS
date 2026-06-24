# The Research OS daemon

The daemon is **optional**. Research OS works fully without it — every
`sys_*` / `tool_*` call runs in-process through your IDE's MCP connection,
and that's the right setup for most chat / IDE sessions. The daemon adds a
separate, persistent process that turns Research OS from a set of tools
into a small **operating layer** around your project. Start it when you
want any of:

- **Long jobs that don't block the chat** — kick off a fit / sweep /
  benchmark, get the turn back immediately, and be **notified when it
  finishes** (optionally straight to Slack / email / a webhook).
- **Run provenance + freshness** — every tracked run records its inputs,
  command, and outputs, so the daemon can tell you when a result has gone
  **stale** (an input changed underneath it) and rebuild exactly the
  affected sub-graph.
- **Hard gates you can't accidentally skip** — with a daemon present, the
  riskiest actions (compiling the final paper, a force-overwrite, a big
  job, scaffolding a paper before the work exists) require a **real,
  one-time, human-authorised approval** — not just the AI deciding it's
  fine.
- **A resource budget the machine enforces** — declare a memory / CPU /
  wallclock ceiling once and every run the daemon launches is held to it
  (a real `rlimit`, not a suggestion). Especially valuable on a shared
  cluster.

If you never start a daemon, none of this is in your way: gates fall back
to a simple confirmation, jobs run inline, nothing changes.

---

## Start / stop

```bash
research-os daemon start      # serve the localhost API + job queue
research-os daemon status     # is it running? what project is active?
```

The daemon binds `127.0.0.1` only (never a public port). One daemon serves
the project it's started in; it writes a small descriptor to
`.os_state/daemon.json` so your IDE's MCP session discovers it
automatically — the AI's `sys_daemon` tool reports it without any wiring.

---

## How the AI sees it

The AI doesn't import the daemon — it talks to it the same way you would,
over the local API, and only ever **reads** unless you authorise a change:

- **`sys_daemon`** — "is anything running in the background, what should I
  do next, what's the resource budget, were there undelivered
  notifications?" One call, the AI's situational awareness. When no daemon
  runs it returns `running:false` and the AI proceeds normally.
- **`sys_consent`** — the AI's side of the approval loop (below). It can
  *request* approval and *check* for a minted token, but it can never
  grant its own.

This is the deliberate split: the AI plans and reasons; the daemon holds
the things the AI must not be able to forge.

---

## The approval loop (hard gates)

With a daemon running, a floor gate doesn't accept the AI's own
"confirmed" — it requires a token only **you** can mint. The full loop:

1. The AI hits a gated action and is told `consent_required`, with the
   exact `gate_key` and a fingerprint of the specific arguments.
2. The AI calls `sys_consent(action='request', …)` and tells you what
   needs approval and why.
3. You review and decide:

   ```bash
   research-os daemon consent                 # list pending requests + active grants
   research-os daemon consent approve <id>    # mint a one-shot, argument-bound token
   research-os daemon consent deny <id>       # refuse
   ```

4. The AI fetches the minted token (`sys_consent(action='token', …)`) and
   retries. The token is **one-shot** — it clears exactly that one action
   and is burned, so one approval can't be replayed across many calls.

The approval is bound to the exact action you saw: a token for "compile
paper.typ" can't be reused to compile something else.

---

## Long jobs + notifications

```bash
research-os daemon run "<command>"   # run as a tracked job (provenance + artifacts)
research-os daemon runs              # list recorded runs
research-os daemon logs <run_id>     # a run's details + captured output
research-os daemon submit "<cmd>"    # submit to SLURM with full provenance
```

A tracked job records its inputs, command, and outputs. When it finishes,
the daemon emits a notification. To have notifications actually reach you,
set a delivery command (it receives the notification as JSON on stdin):

```yaml
# inputs/researcher_config.yaml
# (delivery is configured per-daemon, e.g. via the RESEARCH_OS_DAEMON_NOTIFY_CMD
#  env var pointing at a script that posts to Slack / sends mail / hits a webhook)
```

Review what was sent (and what delivery missed) any time:

```bash
research-os daemon notifications               # the outbox + delivery status
research-os daemon notifications --undelivered # only what didn't reach you
```

---

## Freshness + rebuild

Because runs are tracked, the daemon knows the dependency graph and can
tell when a result is stale:

```bash
research-os daemon lineage      # the run dependency graph
research-os daemon stale        # which runs are stale (input changed / upstream stale)
research-os daemon rebuild      # re-run only the stale sub-graph, in dependency order
research-os daemon reproduce <run_id>   # re-run one recorded run, check outputs still match
research-os daemon diff <a> <b>         # compare two runs: command, env, outputs
```

This is also a **safety gate**: with a daemon present, compiling the final
deliverable is blocked while results it depends on are stale — you can't
ship a paper built on data that changed underneath it without seeing the
warning and clearing it.

---

## Resource budget

Declare a ceiling once, under `runtime:` in your config — the daemon turns
it into a real `rlimit` on every run it launches:

```yaml
# inputs/researcher_config.yaml
runtime:
  resource_budget:
    memory_mb: 16384      # RLIMIT_AS  per run
    cpu_seconds: 7200     # RLIMIT_CPU per run
    wall_seconds: 7200    # wallclock kill
    file_size_mb: 51200   # RLIMIT_FSIZE
    open_files: 4096      # RLIMIT_NOFILE
```

A blank or `0` field means uncapped (the sandbox default applies). On a
shared HPC node this is how you keep a runaway job from hurting everyone
else. The AI sees the active budget via `sys_daemon` and is told to respect
and cite it before launching anything heavy.

---

## Other subcommands

```bash
research-os daemon domain        # detected research field + field-aware defaults
research-os daemon gateway       # OpenAI-compatible chat gateway status / mint a token
```

The **gateway** (`daemon gateway`) is an advanced, off-by-default surface:
an OpenAI-compatible `/v1/chat/completions` endpoint that routes a prompt
through the protocol router and executes Research OS tools, so a
non-MCP client can drive a project. It requires an explicit enable flag
and a per-session bearer token. Most researchers never need it.

---

## Mental model

| Layer | Who | Does |
|---|---|---|
| You | the researcher | drop files in `inputs/`, talk in natural language, **approve** gated actions |
| The AI | your IDE's model | plans, reasons, calls tools, requests approval |
| The MCP server | in-process | executes + records every research action |
| The daemon | optional process | runs long work, tracks provenance, **enforces** hard gates, notifies you |

The daemon never replaces the MCP server — it sits alongside it as the part
that persists, executes in the background, and holds the authority the AI
isn't allowed to hold itself. Start it when a project is big or long-lived
enough to want that; skip it for quick work.
