"""Research OS shared response types.

All tool functions return a dict for MCP compatibility, but the canonical
structure is captured here via ToolResponse so callers can rely on a
well-typed contract.  Use ``ToolResponse.from_dict()`` to normalise any
legacy ``{"status": ...}`` dict into a typed value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResponse:
    """Uniform return type for every MCP tool action.

    Attributes:
        success: True when the tool completed without error.
        message: Human-readable summary (shown to the IDE / researcher).
        data:    Optional structured payload (tool-specific).
        error:   Machine-readable error code or traceback fragment when
                 ``success`` is False.
    """

    success: bool
    message: str
    data: Any = None
    error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Convenience constructors                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def ok(cls, message: str, data: Any = None) -> "ToolResponse":
        """Return a successful response."""
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, error: Optional[str] = None) -> "ToolResponse":
        """Return a failure response."""
        return cls(success=False, message=message, error=error)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolResponse":
        """Normalise a legacy ``{"status": "success"|"error", ...}`` dict."""
        ok = d.get("status") == "success"
        msg = d.get("message", "OK" if ok else "Unknown error")
        err = d.get("message") if not ok else None
        data = {k: v for k, v in d.items() if k not in {"status", "message"}} or None
        return cls(success=ok, message=msg, data=data, error=err)

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialisation."""
        out: dict = {
            "status": "success" if self.success else "error",
            "message": self.message,
        }
        if self.data is not None:
            out["data"] = self.data
        if self.error is not None:
            out["error"] = self.error
        return out

    def __bool__(self) -> bool:
        return self.success
