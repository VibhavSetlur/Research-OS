# Daemon as enforcement layer — un-skippable gates (researcher pain #1)

Status: design / in progress
Branch: feat/v4-daemon-core
Date: 2026-06-23

## The pain (concrete, named)

Research-OS protocols already define which actions are dangerous and must
stop — the 8 floor gates in `guidance/autopilot.yaml`, enforced by
`server/autopilot_gate.py::enforce_autopilot_gate`, wired into the one
seam every tool call funnels through (`server/dispatch.py::_handle_tool_call`,
line 102).

But the enforcement is SOFT in the way that matters: the gate raises a
`RoError` telling the agent "call again with `confirmed=true` only if the
researcher authorized." The *agent* then decides whether to set
`confirmed=true`. The flag the gate checks is written by the very actor
the gate is supposed to constrain. Under deep context / code-gen
pressure the agent can — and eventually will — set `confirmed=true`
itself to force a green exit. The lock's key is taped to the door.

This is the system's "soft prompt fragility" failure mode showing up one
layer below the prompt: even the *server-side* gate ultimately trusts the
agent's self-report.

## The fix (one sentence)

Move the **consent authority** out of the agent's process into the
daemon, so passing a floor gate requires a **consent token the daemon
minted** after a real authorization — a value the agent cannot fabricate
because it lives in a file the daemon owns and the agent's tools can't
write.

This makes the daemon a genuine middle layer between the
agent and the dangerous action (the Hermes/Headroom-style key layer the
user described), instead of the agent grading its own homework.

## Hard constraints (must not violate)

1. SEAM: `server/` and `tools/` must NEVER `import research_os.daemon`
   (preflight-enforced, DESIGN_V4 #1). The gate talks to the daemon ONLY
   through an on-disk contract — same pattern `meta_workspace.py` already
   uses to read daemon discovery by SHAPE without importing it.
2. ADDITIVE / BACKWARD-COMPATIBLE: when no daemon is running, behaviour
   must DEGRADE to exactly today's flow (agent-supplied `confirmed=true`
   still works). We are not allowed to brick stdio-only users who never
   start a daemon. The daemon HARDENS the gate when present; it does not
   become a hard dependency.
3. FAIL-SAFE: any error reading the consent ledger → treat as "no valid
   consent" → gate stays closed (never fail OPEN).
4. The token must be UNFORGEABLE by the agent: the agent can call MCP
   tools (which run in-process and could in principle write files), so
   the consent file must live where a legitimate tool call has no reason
   or path to write, and the token must be a high-entropy value the agent
   never sees until the daemon grants it.

## Mechanism — the consent ledger

A small JSON ledger the DAEMON owns and writes; the GATE (in-process,
reasoning side) only READS it:

  .os_state/consent/granted.json   (daemon-written, gate-read)

Shape (one record per granted consent):

  {
    "grants": [
      {
        "token": "<32-byte urlsafe, daemon-minted>",
        "gate_key": "tool_audit:reproducibility",   # which floor gate
        "tool": "tool_audit",
        "arg_fingerprint": "<sha256 of canonicalized gated args>",
        "granted_at": "2026-06-23T...Z",
        "expires_at": "2026-06-23T...Z",   # short TTL (minutes)
        "consumed": false,                 # one-shot
        "granted_by": "researcher|policy", # provenance
        "reason": "human typed yes in client X"
      }
    ]
  }

Flow:

  1. Agent calls a floor-gated tool (no token).
  2. Gate sees: floor gate fires, no valid consent token in args.
     - If a daemon is running (discovery file present): the gate REFUSES
       and the error tells the agent to REQUEST consent from the daemon
       (POST /v1/consent/request) — the agent cannot self-confirm.
     - If NO daemon: degrade to today — `confirmed=true` from the agent
       is accepted (stdio-only users unaffected).
  3. The consent REQUEST goes to the daemon (out of band of the agent's
     own arg-writing): the daemon surfaces it to the human (or applies a
     policy), and on approval MINTS a one-shot, TTL'd, arg-bound token
     into the ledger.
  4. Agent retries the tool call WITH the token. The gate validates:
     token exists, not expired, not consumed, gate_key matches, AND the
     arg_fingerprint matches THIS call's args (so a token granted for
     action A can't be replayed on action B). On success the daemon marks
     it consumed (gate signals consumption via a consume request, or the
     gate writes a consumed-marker the daemon reconciles — TBD: keep the
     WRITE on the daemon side to preserve the seam; gate asks daemon to
     consume).

Why this is unforgeable by the agent:
  - The token is 32 bytes of os.urandom the agent never sees until the
    daemon returns it from an authorized grant.
  - It's bound to (gate_key + arg_fingerprint) so it can't be reused for
    a different dangerous action.
  - It's one-shot + short-TTL so a leaked token is useless quickly.
  - The ledger is daemon-written; the agent's legitimate tool surface
    has no writer for `.os_state/consent/`.

## What gets built (smallest first slice)

Slice A (reasoning side, in-process, NO daemon import):
  - `server/consent.py`: pure-stdlib reader/validator of the consent
    ledger by SHAPE (mirror of the meta_workspace discovery-by-shape
    pattern). Functions:
      * `arg_fingerprint(tool, args) -> str`  (canonical sha256)
      * `find_valid_grant(root, gate_key, fingerprint) -> grant|None`
      * `daemon_present(root) -> bool`  (reads discovery file by shape)
  - Patch `autopilot_gate.enforce_autopilot_gate`: before raising, if a
    daemon is present, require a daemon-minted token instead of accepting
    `confirmed=true`; if absent, keep today's behaviour. Emit a
    next_action pointing at the daemon consent endpoint.

Slice B (daemon side):
  - `daemon/consent.py`: the ledger WRITER + token minter + TTL/consume
    logic (atomic writes, the daemon owns this file).
  - `POST /v1/consent/request` and `POST /v1/consent/consume` endpoints
    (gated like other mutating endpoints; localhost bind).
  - Wire a human-surfacing hook (start with: log + return pending; the
    actual "ask the human" channel is the client's job — daemon exposes
    the pending queue read-only so a client/Hermes can prompt).

Slice A is the security-critical half and is independently testable with
a hand-written ledger fixture (no running daemon needed). Build + prove A
first, then B.

## Tests (Slice A)
  - fingerprint is stable + canonical (arg order independent).
  - no daemon present → `confirmed=true` still passes (degrade path).
  - daemon present + no token → gate REFUSES even with confirmed=true
    (the whole point: agent self-confirm no longer suffices when a daemon
    is enforcing).
  - daemon present + valid matching token → passes.
  - token for gate_key A rejected on gate_key B.
  - token with mismatched arg_fingerprint rejected (no replay on diff args).
  - expired token rejected. consumed token rejected.
  - unreadable/garbage ledger → fail-safe closed.

## Open question for the human
  - When a daemon IS present, should `confirmed=true` from the agent be
    FULLY disabled (pure token), or still honored at the lightest
    strictness? Default proposal: when daemon present, agent self-confirm
    is disabled for the gate set at/above the project's strictness floor;
    below-floor gates keep flowing as today. This preserves adaptive's
    "rigorous project earns flow" while making the gates that DO fire
    truly un-self-confirmable.
