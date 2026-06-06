"""Response envelope helpers used by every handler.

Every handler returns a JSON envelope of the shape::
    {"status": "success"|"error", "data": {...}, "error": "..."}
Errors are caught at the dispatcher; handlers may raise freely.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


try:
    from mcp.types import TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

    @dataclass
    class TextContent:  # type: ignore[no-redef]
        type: str
        text: str


def _success(data: Any = None) -> dict:
    return {"status": "success", "data": data or {}}


def _error(message: str) -> dict:
    return {"status": "error", "error": message}


def _text(payload: Any) -> list[TextContent]:
    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]
