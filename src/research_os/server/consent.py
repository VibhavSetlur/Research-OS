"""Consent-token validation for the un-skippable floor gates.

This module is the READER half of the daemon-enforced consent layer. It
lives on the reasoning side (``server/``) and therefore MUST NOT import
``research_os.daemon`` — the preflight-enforced seam (ARCHITECTURE #1). It
talks to the daemon ONLY through an on-disk contract, exactly as
``handlers/meta_workspace.py`` reads the daemon discovery descriptor by
SHAPE without importing the daemon package.

Why this exists
---------------
``server/autopilot_gate.py`` enforces the floor gates declared in
``guidance/autopilot.yaml``. Historically a gate was cleared by the agent
passing ``confirmed=true`` in its own arguments — but that flag is written
by the very actor the gate constrains. Under context pressure an agent can
set ``confirmed=true`` itself to force past the gate. The lock's key was
taped to the door.

When a daemon is running it becomes the consent AUTHORITY: it mints a
one-shot, TTL'd, argument-bound token into a ledger IT owns
(``.os_state/consent/granted.json``) only after a real authorization. The
gate then requires that token instead of trusting the agent's self-report.
The agent cannot forge the token: it is high-entropy, it never sees the
value until the daemon returns it from an authorized grant, and it is
bound to the exact (gate_key, argument-fingerprint) so it cannot be
replayed on a different dangerous action.

Fail-safe posture
-----------------
Every read path here fails CLOSED: a missing, unreadable, or malformed
ledger yields "no valid grant", never an accidental pass. The only path
that intentionally relaxes is the DEGRADE path in the gate itself (no
daemon present → fall back to today's ``confirmed=true`` behaviour so
stdio-only users are unaffected); that decision lives in the gate, keyed
off ``daemon_present`` here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


# A burned token is kept in the spent log only until this long PAST its own
# expiry, then pruned: an expired grant already fails find_valid_grant's TTL
# check, so recording it further adds no security and only grows the file.
# The grace window absorbs clock skew between the daemon (minter) and the
# gate (burner) so a token is never pruned while it could still validate.
_SPENT_GRACE_SECONDS = 3600


def _consent_path(root: Path) -> Path:
    """Path to the daemon-owned consent ledger for this project."""
    from . import daemon_bridge as _bridge

    return _bridge.state_path(root, _bridge.CONSENT_GRANTED)


def _daemon_descriptor_path(root: Path) -> Path:
    """Path to the daemon self-advertised descriptor (canonical: daemon_bridge)."""
    from . import daemon_bridge as _bridge

    return _bridge.descriptor_path(root)


def _canonical_args(arguments: dict) -> dict:
    """Return args stripped of fields that must NOT bind the token.

    ``confirmed`` and ``consent_token`` are control-plane fields, not part
    of the action's identity — including them would make the fingerprint
    depend on the very token we're validating (circular) or on the legacy
    self-confirm flag. Everything else identifies WHAT the agent is about
    to do and so binds the grant.
    """
    args = dict(arguments or {})
    args.pop("confirmed", None)
    args.pop("consent_token", None)
    return args


def arg_fingerprint(tool_name: str, arguments: dict) -> str:
    """Stable sha256 over (tool, canonicalized args).

    Order-independent: keys are sorted via ``json.dumps(sort_keys=True)``.
    Binds a consent grant to the EXACT action, so a token granted for
    action A cannot be replayed on action B with different arguments.
    """
    payload = {
        "tool": tool_name,
        "args": _canonical_args(arguments),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def daemon_present(root: Path) -> bool:
    """True iff a daemon is running for this project (descriptor + live PID).

    Delegates to the canonical ``daemon_bridge.daemon_present`` — one
    definition of "is the daemon here?" shared across every reasoning-side
    reader. No import of the daemon package. Any error → False (degrade to
    today's in-process behaviour, never block stdio-only users).
    """
    from . import daemon_bridge as _bridge

    return _bridge.daemon_present(root)


def _parse_iso(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp (with trailing Z) to aware UTC, or None."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_grants(root: Path) -> list[dict]:
    """Read the consent ledger's grants list. Fail CLOSED to []."""
    path = _consent_path(root)
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    grants = data.get("grants")
    if not isinstance(grants, list):
        return []
    return [g for g in grants if isinstance(g, dict)]


def _spent_path(root: Path) -> Path:
    """Path to the gate-owned spent-token log (single-use enforcement).

    The daemon OWNS ``granted.json`` (it mints grants); the gate must not
    write that file or it would no longer be the daemon's sole authority.
    But single-use can't be left to the agent voluntarily calling
    ``/v1/consent/consume`` — the agent is the actor we don't trust. So the
    gate records spent tokens in its OWN sidecar here, and treats any token
    already listed as invalid. Daemon mints; gate burns. Both halves are
    needed for a token to be one-shot AND un-forgeable.
    """
    return Path(root) / ".os_state" / "consent" / "spent.json"


def _load_spent(root: Path) -> dict[str, str | None]:
    """Read the spent-token map ``{token: expires_at|None}``. Fail CLOSED-ish.

    A missing/garbage spent log must not let a token pass twice in the common
    case, but it also must not crash the gate. We return an empty map on read
    failure; the WRITE side (``_mark_spent``) is what actually enforces
    single-use, and it is best-effort atomic.

    Back-compat: the historical on-disk shape was ``{"spent": [token, ...]}``
    (a bare list, no expiry). That form still loads — each legacy token maps
    to ``None`` (unknown expiry), which is NEVER pruned, so an old log keeps
    enforcing single-use exactly as before. The new shape is
    ``{"spent": {token: expires_at_iso_or_null}}`` so dead tokens can be
    pruned (an expired grant already fails the TTL check in
    :func:`find_valid_grant`, so keeping it adds no security, only disk).
    """
    path = _spent_path(root)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    tokens = data.get("spent")
    if isinstance(tokens, dict):
        return {
            t: (e if isinstance(e, str) else None)
            for t, e in tokens.items()
            if isinstance(t, str)
        }
    if isinstance(tokens, list):  # legacy list shape → unknown expiry
        return {t: None for t in tokens if isinstance(t, str)}
    return {}


def _spent_tokens(root: Path) -> set[str]:
    """Just the burned token strings (for membership checks)."""
    return set(_load_spent(root).keys())


def _prune_spent(
    spent: dict[str, str | None], now: datetime
) -> dict[str, str | None]:
    """Drop tokens whose grant expired more than the grace window ago.

    A token with no known expiry (``None`` — e.g. a legacy entry) is KEPT:
    we can't prove it is safe to forget, so single-use enforcement wins over
    disk thrift (fail-safe). Only tokens we KNOW are long-dead are pruned —
    an expired grant already fails find_valid_grant's TTL check, so the
    spent record adds nothing but bytes once the grace window has passed.
    """
    cutoff = now - timedelta(seconds=_SPENT_GRACE_SECONDS)
    out: dict[str, str | None] = {}
    for token, exp_iso in spent.items():
        exp = _parse_iso(exp_iso) if isinstance(exp_iso, str) else None
        if exp is not None and exp < cutoff:
            continue
        out[token] = exp_iso
    return out


def _mark_spent(root: Path, token: str, expires_at: str | None = None) -> None:
    """Atomically record ``token`` as burned (single-use), self-pruning.

    Best-effort: written via temp-file + ``os.replace`` so a concurrent
    reader never sees a half-written file. ``expires_at`` (the grant's TTL,
    when known) lets the log prune the token once it is long dead — without
    it, on a long-lived shared-HPC project the spent log would grow without
    bound. Failure to write is swallowed — the grant's own ``expires_at`` TTL
    is the backstop so a token can't be replayed even if the burn momentarily
    fails.
    """
    path = _spent_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        spent = _prune_spent(_load_spent(root), now)
        spent[token] = expires_at
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(
            json.dumps({"spent": spent}, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError:
        pass


def find_valid_grant(
    root: Path,
    gate_key: str,
    fingerprint: str,
    token: str | None,
    *,
    now: datetime | None = None,
) -> dict | None:
    """Return the matching un-consumed, un-expired grant, or None.

    A grant matches when ALL hold:
      * its ``token`` equals the presented ``token`` (constant-time compare),
      * its ``gate_key`` equals ``gate_key`` (no cross-gate reuse),
      * its ``arg_fingerprint`` equals ``fingerprint`` (no cross-action replay),
      * the daemon hasn't flagged it ``consumed`` (authority-side one-shot),
      * the gate hasn't already burned it via ``_spent_path`` (gate-side
        one-shot — the part the agent cannot skip),
      * ``expires_at`` is absent OR in the future (short TTL).

    Returns the grant dict (so the caller can read its id/expiry); None on
    any miss or on a malformed ledger (fail-safe closed). This function is
    READ-ONLY; the caller must call :func:`consume_grant` to burn the token
    once the gated action is authorized to proceed.
    """
    if not token:
        return None
    now = now or datetime.now(timezone.utc)
    if token in _spent_tokens(root):
        return None
    for grant in _load_grants(root):
        gtoken = grant.get("token")
        if not isinstance(gtoken, str):
            continue
        # Constant-time compare to avoid leaking token bytes via timing.
        if not _ct_eq(gtoken, token):
            continue
        if grant.get("gate_key") != gate_key:
            continue
        if grant.get("arg_fingerprint") != fingerprint:
            continue
        if grant.get("consumed") is True:
            continue
        exp = _parse_iso(grant.get("expires_at", ""))
        if exp is not None and exp <= now:
            continue
        return grant
    return None


def consume_grant(
    root: Path, token: str, *, expires_at: str | None = None
) -> None:
    """Burn a token so it cannot clear a second gate (one-shot enforcement).

    Called by the gate immediately after a grant validates and the action
    is cleared to run. Records the token in the gate-owned spent log; the
    next :func:`find_valid_grant` for the same token returns None.

    Pass the grant's ``expires_at`` (available from the dict
    :func:`find_valid_grant` returns) so the spent log can prune the token
    once it is long dead — otherwise the log grows unbounded on a
    long-lived project. Omitting it is safe (the token is just kept
    forever, the historical behaviour).
    """
    if token:
        _mark_spent(root, token, expires_at=expires_at)


def _ct_eq(a: str, b: str) -> bool:
    """Constant-time string equality (avoid token timing side-channel)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
