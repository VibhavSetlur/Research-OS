"""Research OS custom exceptions.

Hierarchy
---------
ResearchOSError
├── ConfigError        — researcher_config.yaml problems
├── ScaffoldError      — workspace initialisation failures
├── StateError         — .os_state / ledger corruption
├── ToolError          — MCP tool execution failures
└── WriteProtectedError — write into inputs/ or .os_state/ forbidden
"""

from pathlib import Path
from typing import Optional


# ── Base ──────────────────────────────────────────────────────────────────────

class ResearchOSError(Exception):
    """Root exception for all Research OS errors."""


# ── Sub-classes ───────────────────────────────────────────────────────────────

class ConfigError(ResearchOSError):
    """Raised when researcher_config.yaml is missing, unreadable, or invalid."""

    def __init__(self, message: str, config_path: Optional[Path] = None):
        self.config_path = config_path
        hint = f" (path: {config_path})" if config_path else ""
        super().__init__(f"Config error{hint}: {message}")


class ScaffoldError(ResearchOSError):
    """Raised when workspace scaffolding fails."""

    def __init__(self, message: str, workspace: Optional[Path] = None):
        self.workspace = workspace
        hint = f" (workspace: {workspace})" if workspace else ""
        super().__init__(f"Scaffold error{hint}: {message}")


class StateError(ResearchOSError):
    """Raised when the .os_state ledger or manifest is corrupt or missing."""

    def __init__(self, message: str, state_path: Optional[Path] = None):
        self.state_path = state_path
        hint = f" (path: {state_path})" if state_path else ""
        super().__init__(f"State error{hint}: {message}")


class ToolError(ResearchOSError):
    """Raised when an MCP tool action fails during execution.

    Wraps the original exception so the server can return a uniform error
    response without losing the original traceback.
    """

    def __init__(self, tool_name: str, message: str, cause: Optional[Exception] = None):
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(f"Tool '{tool_name}' failed: {message}")


class WriteProtectedError(ResearchOSError):
    """Raised when a tool attempts to write to a protected directory.

    Currently enforced for:
      - inputs/        (immutable original data)
      - .os_state/     (internal OS state, should not be manually modified)
    """

    def __init__(self, path: "Path | str", message: str = ""):
        self.path = str(path)
        default = (
            f"Write protection violation: '{self.path}' is read-only. "
            "The `inputs/` directory contains immutable original data "
            "and must never be modified by tools. Write to `workspace/` instead."
        )
        super().__init__(message or default)


# ── Guard helpers ─────────────────────────────────────────────────────────────

PROTECTED_DIRECTORIES = {"inputs", ".os_state"}


def check_write_permitted(target_path: "str | Path") -> None:
    """Raise WriteProtectedError if *target_path* falls under a protected root."""
    p = Path(target_path).resolve()
    for part in p.parts:
        if part in PROTECTED_DIRECTORIES:
            raise WriteProtectedError(p)
