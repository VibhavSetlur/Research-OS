"""WHAT / WHY / NEXT structured-error primitive.

Every error visible to an AI or researcher carries three load-bearing
pieces of information:

* WHAT — the one-line description of what went wrong
* WHY  — the one-line description of why it happened
* NEXT — the one-line description of what the AI should do next

Raised as ``RoError(what, why, next_action)``. The server dispatcher
catches ``RoError`` and emits the error envelope (see
``research_os.server.envelopes._error``) so the WHAT / WHY / NEXT
land on ``payload.{what,why,next_action}`` AND ``next_action`` promotes
to envelope-level ``next_recommended_call``.

For ad-hoc inline errors that don't justify their own subclass, callers
can also pass kwargs directly to ``_error(what=..., why=..., next_action=...)``.
``RoError`` is the right primitive when an internal layer raises an
exception that an outer dispatcher will translate to an envelope.

Helpers:

``did_you_mean(target, candidates, *, n=3, cutoff=0.6)``
    Standard nearest-string-match suggestion list to attach to a
    FileNotFound-style WHY message. Pure stdlib; no external deps.
"""
from __future__ import annotations

import difflib
from typing import Iterable


class RoError(Exception):
    """WHAT/WHY/NEXT structured error.

    The dispatcher renders this as an error envelope. ``str(e)``
    is the composed sentence the user sees in plain-text contexts.
    """

    def __init__(
        self,
        what: str,
        why: str | None = None,
        next_action: str | None = None,
    ) -> None:
        self.what = what.rstrip(".")
        self.why = (why or "").rstrip(".") or None
        self.next_action = (next_action or "").rstrip(".") or None
        parts = [self.what]
        if self.why:
            parts.append(f"because {self.why}")
        if self.next_action:
            parts.append(f"next: {self.next_action}")
        super().__init__(". ".join(parts))

    def to_envelope_kwargs(self) -> dict:
        """Kwargs to splat into ``envelopes._error(...)``."""
        return {
            "what": self.what,
            "why": self.why,
            "next_action": self.next_action,
        }


_TOOL_NAMESPACES = ("sys_", "tool_", "mem_")


def did_you_mean(
    target: str,
    candidates: Iterable[str],
    *,
    n: int = 3,
    cutoff: float = 0.6,
    namespace_aware: bool = False,
) -> list[str]:
    """Return up to ``n`` nearest-match candidates for a missing ``target``.

    Uses ``difflib.get_close_matches`` so we stay pure-stdlib + zero-cost
    when called from a hot path. Filters out the exact ``target`` (which
    should never match its own missing self anyway) for defensiveness.

    When ``namespace_aware=True`` and ``target`` starts with one of the
    standard tool namespaces (``sys_``, ``tool_``, ``mem_``), candidates
    sharing the same namespace are scored first; if the in-namespace
    matches do not fill ``n`` slots, cross-namespace matches are appended.
    This closes FIX-16 (typing ``sys_X`` should prefer other ``sys_*``).
    """
    cleaned = [c for c in candidates if c != target]
    if namespace_aware:
        target_ns = next(
            (ns for ns in _TOOL_NAMESPACES if target.startswith(ns)), None
        )
        if target_ns is not None:
            in_ns = [c for c in cleaned if c.startswith(target_ns)]
            out_ns = [c for c in cleaned if not c.startswith(target_ns)]
            matches = difflib.get_close_matches(target, in_ns, n=n, cutoff=cutoff)
            if len(matches) < n:
                extra = difflib.get_close_matches(
                    target, out_ns, n=n - len(matches), cutoff=cutoff
                )
                for m in extra:
                    if m not in matches:
                        matches.append(m)
            return matches[:n]
    matches = difflib.get_close_matches(
        target, cleaned, n=n, cutoff=cutoff
    )
    return matches
