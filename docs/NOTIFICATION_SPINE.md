# Notification spine — the daemon tells the researcher when work finishes

Status: design / implementing
Branch: feat/v4-daemon-core
Date: 2026-06-23

## The pain (concrete, named)

Daemon intent #4: "notify the researcher on completion (incl. via
Hermes)." Today this does not exist. Two concrete failures:

1. The daemon runs a long job (a 40-minute fit, a batch sweep) off the
   request thread — exactly so the AI doesn't sit blocked. But when it
   finishes, **nothing tells the researcher**. The job result lands in the
   run journal and an internal event fires on the bus, but the human who
   walked away never learns it's done. They come back hours later and
   poll manually. The "fire-and-return so the AI doesn't wait" primitive
   is only half-built: it returns, but never calls back.

2. `sys_notify` — the tool the AI uses to page the researcher at a gate —
   only **appends a line to `workspace/logs/notifications.log`**. Unless
   the researcher is tailing that file, an `action_required` notification
   is invisible. The universal "halt + show me" handshake the autopilot
   protocol promises is a no-op in practice.

So the system has no way to reach the researcher out-of-band. On a shared
server where the researcher closes their laptop and the daemon keeps
working, that is the difference between "useful autonomous assistant" and
"thing I have to babysit."

## The fix (one sentence)

Give the daemon a single notification SPINE: a durable, append-only outbox
every notification flows through, plus a pluggable delivery hook the
researcher configures once (a shell command) so completions and gate-pages
reach them on whatever channel they already use — Hermes→Slack, email,
a webhook, anything.

## Design

### One outbox, append-only

  .os_state/notifications/outbox.jsonl   (daemon-written, anyone-read)

One JSON object per line, append-only (atomic via O_APPEND on small
writes; each record is independent so a torn final line never corrupts
prior records). Shape:

```json
{
  "id": "ntfy_<8hex>",
  "ts": "2026-06-23T...Z",
  "kind": "job.succeeded" | "job.failed" | "gate.blocked" | "staleness" | "info",
  "level": "info" | "action_required" | "warn",
  "title": "Job 'fit_model' finished",
  "body": "run_07 succeeded in 38m. Result: ...",
  "context": {"job_id": "...", "root": "...", ...},
  "delivered": false,
  "delivery": {"attempted": false, "ok": null, "detail": ""}
}
```

This is durable: a researcher (or the AI, or a CLI) can always read the
outbox and see what happened, even if live delivery failed or was never
configured. The outbox is the source of truth; delivery is best-effort on
top.

### Pluggable delivery — one config knob

`DaemonConfig.notify_command` (default ""): a shell command the daemon
runs once per new notification, with the notification JSON on **stdin**.
Empty → persist-only (outbox still written; no push). This is the honest,
composable design for a shared server where the researcher already has a
delivery channel wired:

```yaml
# inputs/researcher_config.yaml
daemon:
  notify_command: "/home/me/.local/bin/ro-notify"   # reads JSON on stdin
```

The researcher's script decides the channel (Hermes CLI → Slack, mailx,
curl to a webhook…). Research-OS does not hardcode Slack/email/Hermes — it
hands the notification to whatever the researcher configured. Delivery is:

* best-effort: a non-zero exit or a missing command marks
  `delivery.ok=false` with the detail, but NEVER fails the job or the
  emit. The outbox record persists regardless.
* bounded: a short timeout so a hung delivery command can't wedge the
  worker thread.
* recorded: the outbox line is updated with the delivery outcome so the
  researcher can see "tried to push, channel was down" vs "never tried".

Security: `notify_command` is read from the project config / env, runs as
the daemon's own user, localhost context. It is the researcher's own
command — same trust level as the scripts the daemon already runs. It is
NOT taken from any agent-writable surface at request time.

### Wiring — completions + pages feed the same spine

1. JobQueue terminal events (`job.succeeded` / `job.failed`) → a
   notification on the spine (the daemon already has the job's root, name,
   status, result/error at `tasks.py` `_emit`). The researcher learns the
   long job finished without polling.
2. `sys_notify` (the AI's page-the-researcher tool) → when a daemon is
   present, also drop the message onto the spine so it actually reaches
   the researcher, not just the log file. (Seam: the tool can't import the
   daemon; it writes to the SAME on-disk outbox by shape, exactly like the
   consent ledger. The daemon's delivery loop picks it up.)
3. `gate.blocked` / `staleness` notifications can be emitted by the daemon
   when it detects an unattended block — future, but the spine is ready.

### Read surface

`GET /v1/notifications` (read-only, like telemetry): returns recent outbox
records (optionally `?undelivered=true`). Lets a client/dashboard/AI
surface what the researcher missed.

## Backward compatibility

* No `notify_command` configured → outbox is written, nothing is pushed.
  Identical to today for anyone who doesn't opt in, plus a durable record
  they can read.
* No daemon → `sys_notify` keeps logging to the notifications.log file
  exactly as today (the outbox write is daemon-present-only, by shape).
* Purely additive config field; existing daemons unaffected.

## Build order

1. This doc.
2. `daemon/notifications.py`: `emit(root, kind, title, body, level,
   context, notify_command)` — append outbox record, attempt delivery,
   update record with outcome. Stdlib only. Plus `read_outbox(root,
   undelivered=False, limit=...)`.
3. `DaemonConfig.notify_command` field + env/project-file resolution.
4. Wire `tasks.py` `_emit` terminal events → `notifications.emit`.
5. `server/notify_sink.py` (reasoning side, no daemon import): when a
   daemon is present, `sys_notify` also appends to the outbox by shape.
6. `GET /v1/notifications` endpoint.
7. Tests + live round-trip (emit → outbox → fake delivery command runs).
```
