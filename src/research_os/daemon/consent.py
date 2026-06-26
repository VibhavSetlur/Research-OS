"""Daemon-side consent authority (writer half of the un-skippable gates).

This is the WRITER counterpart to ``server/consent.py`` (the reader). When
a daemon runs for a project it becomes the authority that decides whether a
floor gate may be crossed: it mints one-shot, TTL'd, argument-bound consent
tokens into a ledger the reasoning layer can only READ.

The two halves share an on-disk CONTRACT, not code (the seam forbids the
reasoning layer from importing the daemon). The ledger shape written here
is exactly what ``server/consent.py:find_valid_grant`` validates:

    .os_state/consent/granted.json   { "grants": [ {grant}, ... ] }
    .os_state/consent/pending.json   { "requests": [ {request}, ... ] }

Why a separate pending queue: the agent REQUESTS consent (it cannot mint
it). The daemon records the request as pending and exposes it read-only so
a human-facing client (Hermes, an IDE, the CLI) can surface it and collect
a real yes/no. Approval moves a pending request into a minted grant. This
keeps the authority — "did a human actually say yes" — in a process the
agent does not control.

Atomic writes (temp + os.replace), stdlib only. No locking beyond atomic
rename; the daemon is the single writer.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Token lifetime once minted. Short by design: a leaked token is useless
# quickly, and consent should be fresh relative to the action.
DEFAULT_TTL_SECONDS = 300

# How long an un-actioned pending request lingers before it is considered
# stale (so the queue self-prunes if a human never answers).
PENDING_TTL_SECONDS = 3600


def _consent_dir(root: Path) -> Path:
    return Path(root) / ".os_state" / "consent"


def _granted_path(root: Path) -> Path:
    return _consent_dir(root) / "granted.json"


def _pending_path(root: Path) -> Path:
    return _consent_dir(root) / "pending.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically (temp sibling + os.replace). Mirrors runstore."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read_list(path: Path, key: str) -> list[dict]:
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    items = data.get(key)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _parse_iso(ts: str) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ConsentStore:
    """Daemon's consent authority for one project root.

    Single-writer: only the running daemon constructs this. The reasoning
    layer never imports it — it reads the resulting files by shape.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    # ── request (agent asks; cannot self-grant) ─────────────────────────
    def request(
        self,
        *,
        gate_key: str,
        tool: str,
        arg_fingerprint: str,
        reason: str = "",
    ) -> dict:
        """Record a pending consent request. Returns the pending record.

        This does NOT grant anything — it queues a request for a human (or
        a configured policy) to approve. The agent calls this; the agent
        cannot move it to granted.
        """
        req = {
            "id": secrets.token_urlsafe(12),
            "gate_key": gate_key,
            "tool": tool,
            "arg_fingerprint": arg_fingerprint,
            "reason": reason or "",
            "requested_at": _iso(_now()),
            "status": "pending",
        }
        pending = self._live_pending()
        pending.append(req)
        _atomic_write_json(self._pending_path(), {"requests": pending})
        return req

    # ── approve (authority says yes; mints the token) ───────────────────
    def approve(
        self,
        request_id: str,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        granted_by: str = "researcher",
    ) -> dict | None:
        """Approve a pending request → mint a grant. Returns the grant.

        Returns None if the request id is unknown or already resolved. The
        minted grant is bound to the request's (gate_key, arg_fingerprint),
        so it can only clear the exact action that was requested.
        """
        pending = self._live_pending()
        match = None
        remaining = []
        for r in pending:
            if r.get("id") == request_id and r.get("status") == "pending":
                match = r
            else:
                remaining.append(r)
        if match is None:
            return None

        now = _now()
        grant = {
            "token": secrets.token_urlsafe(32),
            "gate_key": match["gate_key"],
            "tool": match.get("tool", ""),
            "arg_fingerprint": match["arg_fingerprint"],
            "granted_at": _iso(now),
            "expires_at": _iso(now + timedelta(seconds=ttl_seconds)),
            "consumed": False,
            "granted_by": granted_by,
            "request_id": request_id,
            "reason": match.get("reason", ""),
        }
        grants = self._live_grants()
        grants.append(grant)
        _atomic_write_json(self._granted_path(), {"grants": grants})
        _atomic_write_json(self._pending_path(), {"requests": remaining})
        return grant

    def deny(self, request_id: str) -> bool:
        """Drop a pending request without minting. True if one was removed."""
        pending = self._live_pending()
        remaining = [r for r in pending if r.get("id") != request_id]
        if len(remaining) == len(pending):
            return False
        _atomic_write_json(self._pending_path(), {"requests": remaining})
        return True

    # ── consume (one-shot: mark a token spent) ──────────────────────────
    def consume(self, token: str) -> bool:
        """Mark a grant consumed so it can't be reused. True if it existed."""
        grants = self._live_grants()
        found = False
        for g in grants:
            if g.get("token") == token and g.get("consumed") is not True:
                g["consumed"] = True
                g["consumed_at"] = _iso(_now())
                found = True
        if found:
            _atomic_write_json(self._granted_path(), {"grants": grants})
        return found

    # ── read surfaces (for clients to display) ──────────────────────────
    def list_pending(self) -> list[dict]:
        return self._live_pending()

    def list_grants(self, *, include_spent: bool = False) -> list[dict]:
        grants = self._live_grants()
        if include_spent:
            return grants
        now = _now()
        live = []
        for g in grants:
            if g.get("consumed") is True:
                continue
            exp = _parse_iso(g.get("expires_at", ""))
            if exp is not None and exp <= now:
                continue
            live.append(g)
        return live

    # ── internals: prune-on-read so files self-clean ────────────────────
    def _live_grants(self) -> list[dict]:
        """All grants, dropping ones expired AND consumed long ago.

        We keep consumed/expired grants briefly for auditability but prune
        the truly dead ones so the file doesn't grow unbounded.
        """
        now = _now()
        out = []
        for g in _read_list(self._granted_path(), "grants"):
            exp = _parse_iso(g.get("expires_at", ""))
            # Drop grants expired more than one TTL ago (dead + auditless).
            if exp is not None and exp + timedelta(
                seconds=DEFAULT_TTL_SECONDS
            ) <= now:
                continue
            out.append(g)
        return out

    def _live_pending(self) -> list[dict]:
        now = _now()
        out = []
        for r in _read_list(self._pending_path(), "requests"):
            req_at = _parse_iso(r.get("requested_at", ""))
            if req_at is not None and req_at + timedelta(
                seconds=PENDING_TTL_SECONDS
            ) <= now:
                continue
            out.append(r)
        return out

    def _granted_path(self) -> Path:
        return _granted_path(self.root)

    def _pending_path(self) -> Path:
        return _pending_path(self.root)
