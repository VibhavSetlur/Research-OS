"""Research OS custom exceptions.

Hierarchy
---------
ResearchOSError
└── WriteProtectedError — write into inputs/ or .os_state/ forbidden

Only ``ResearchOSError`` (root) and ``WriteProtectedError`` are part of
the live public taxonomy. Earlier drafts shipped ``ConfigError`` /
``ScaffoldError`` / ``StateError`` / ``ToolError`` but no code path
raised them; they were removed once the audit confirmed zero callers.
Re-add them only when there is a concrete handler ready to catch them.
"""

from pathlib import Path


# ── Base ──────────────────────────────────────────────────────────────────────

class ResearchOSError(Exception):
    """Root exception for all Research OS errors."""


class WriteProtectedError(ResearchOSError):
    """Raised when a tool attempts to write to a protected directory.

    Hard-locked (only ``.os_state/`` as of 3.2.2):
      - .os_state/     internal OS state — never hand-edited.

    NOTE: ``inputs/`` is **no longer** a hard-locked tree. It is the
    researcher's source-of-truth and the AI may legitimately maintain it
    (add context files, fix the intake, keep researcher_config.yaml in
    sync). The two ORIGINAL input trees — ``inputs/raw_data/`` and
    ``inputs/literature/`` — are *soft*-guarded at the sys_file_write
    layer (deliberate ``force=true`` + a confirm-with-researcher warning),
    NOT blocked here.
    """

    def __init__(self, path: "Path | str", message: str = ""):
        self.path = str(path)
        default = (
            f"Write protection violation: '{self.path}' is read-only. "
            "`.os_state/` holds internal Research-OS state and must never be "
            "edited by hand. Write to `workspace/` instead."
        )
        super().__init__(message or default)


# ── Guard helpers ─────────────────────────────────────────────────────────────

# Only .os_state is hard-locked. inputs/ relaxed to a soft guard in 3.2.2
# (see WriteProtectedError docstring + meta_workspace._handle_sys_file_write).
PROTECTED_DIRECTORIES = {".os_state"}


def check_write_permitted(
    target_path: "str | Path",
    root: "str | Path | None" = None,
) -> None:
    """Raise WriteProtectedError if *target_path* falls under a protected root.

    When *root* is provided, only the path components RELATIVE to *root* are
    inspected. This avoids false positives when the project itself happens
    to live inside a directory called ``inputs`` or ``.os_state`` somewhere
    in its ancestry (e.g. ``/home/u/.os_state/projects/foo``).

    When *root* is omitted, the legacy any-part-anywhere behavior is used
    for back-compat with callers that only have a relative path.
    """
    p = Path(target_path)
    if root is not None:
        root_resolved = Path(root).resolve()
        target_resolved = p if p.is_absolute() else (root_resolved / p)
        try:
            target_resolved = target_resolved.resolve()
        except OSError:
            pass
        try:
            rel = target_resolved.relative_to(root_resolved)
        except ValueError:
            # Outside the project root entirely — that's a separate
            # path-containment violation handled by _resolve_inside_root.
            return
        parts = rel.parts
    else:
        parts = Path(target_path).resolve().parts
    for part in parts:
        if part in PROTECTED_DIRECTORIES:
            raise WriteProtectedError(target_path)
