"""Aggregated TOOL_DEFINITIONS — merges every domain module."""
from __future__ import annotations

from typing import Any


from .meta import META_TOOL_DEFINITIONS  # noqa: E501
from .research import RESEARCH_TOOL_DEFINITIONS  # noqa: E501
from .audit import AUDIT_TOOL_DEFINITIONS  # noqa: E501
from .synthesis import SYNTHESIS_TOOL_DEFINITIONS  # noqa: E501
from .methodology import METHODOLOGY_TOOL_DEFINITIONS  # noqa: E501
from .grounding import GROUNDING_TOOL_DEFINITIONS  # noqa: E501
from .build import BUILD_TOOL_DEFINITIONS  # noqa: E501
from .gradient import GRADIENT_TOOL_DEFINITIONS  # noqa: E501

TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    **META_TOOL_DEFINITIONS,
    **RESEARCH_TOOL_DEFINITIONS,
    **AUDIT_TOOL_DEFINITIONS,
    **SYNTHESIS_TOOL_DEFINITIONS,
    **METHODOLOGY_TOOL_DEFINITIONS,
    **GROUNDING_TOOL_DEFINITIONS,
    **BUILD_TOOL_DEFINITIONS,
    **GRADIENT_TOOL_DEFINITIONS,
}
