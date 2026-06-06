"""Canonical TOOL_DEFINITIONS + _HANDLERS registry.

Combines the per-domain dicts from ``tool_definitions/`` and ``handlers/``
into a single map, then lets pack/adapter discovery further mutate them.
The top-level ``research_os.server`` re-exports the result.
"""
from __future__ import annotations

from .handlers import _HANDLERS  # noqa: F401
from .tool_definitions import TOOL_DEFINITIONS  # noqa: F401


__all__ = ["TOOL_DEFINITIONS", "_HANDLERS"]
