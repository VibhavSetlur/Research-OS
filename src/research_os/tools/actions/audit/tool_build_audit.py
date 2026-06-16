"""scope='tool' audit family — the tool_build analog of the analysis gates.

In ``workspace.mode == 'tool_build'`` the deliverable is a working tool, not
a paper. The figure / literature / completeness gates that govern analysis
steps do not apply; the gate is "does it build, do the tests pass, is the
inner repo's history honest". These three dimensions provide that gate:

* ``tests``        — run the configured test command (via tool_build) and
  block on failure OR on a suite that ran zero tests (a green run that
  proved nothing is not evidence — the tool_build analog of the
  "figure with no underlying analysis" blocker).
* ``git_hygiene``  — the inner repo has no uncommitted changes, HEAD is a
  real commit, and recent commit subjects aren't WIP/fixup/squash markers
  left lying around (the analog of "un-snapshotted analysis state").
* ``build``        — the configured build command succeeds.

Every dimension is MODE-AWARE: outside tool_build it is a clean no-op with a
clear message, never a blocker — so these audits can be wired into the shared
dispatch table without firing on classic analysis projects.

Each function returns the standard audit envelope
``{status, blockers, warnings, ...}`` so it composes with the rest of the
audit system (``status='error'`` when there are blockers, matching
step_literature / step_completeness).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_os.tools.actions.exec.build_tools import (
    build_op,
    git_op,
    is_tool_build_mode,
)
from research_os.tools.actions.state.config import get_workspace_mode

# Commit-subject markers that signal a not-yet-finished commit accidentally
# left in history. Warned-on (not blocked) — they're a smell, not a
# correctness failure, and a researcher may legitimately keep a "wip:" tip.
_WIP_MARKERS = ("wip", "fixup!", "squash!", "tmp", "temp", "do not merge", "dnm")

# Number of recent commits whose subjects we scan for WIP markers.
_HYGIENE_SCAN_COMMITS = 10


def _not_applicable(dimension: str, root: Path) -> dict[str, Any]:
    """Clean no-op envelope for a scope='tool' audit outside tool_build mode."""
    return {
        "status": "success",
        "dimension": dimension,
        "applicable": False,
        "blockers": [],
        "warnings": [],
        "message": (
            f"scope='tool' dimension='{dimension}' only applies in "
            "workspace.mode='tool_build'. This project's mode is "
            f"'{get_workspace_mode(Path(root))}'; no-op."
        ),
    }


def _envelope(
    dimension: str,
    blockers: list[str],
    warnings: list[str],
    **extra: Any,
) -> dict[str, Any]:
    status = "error" if blockers else ("warning" if warnings else "success")
    out: dict[str, Any] = {
        "status": status,
        "dimension": dimension,
        "applicable": True,
        "blockers": blockers,
        "warnings": warnings,
    }
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# dimension='tests'
# ---------------------------------------------------------------------------


def _looks_like_zero_tests(output_tail: str) -> bool:
    """Heuristically detect a test run that collected/ran zero tests.

    A passing command that exercised nothing is not evidence. We can't know
    every framework's phrasing, so this is a best-effort smell check across
    the common runners (pytest / unittest / go test / cargo / jest / npm).
    """
    low = (output_tail or "").lower()
    zero_signals = (
        "no tests ran",
        "no tests found",
        "collected 0 items",
        "ran 0 tests",
        "0 passed",
        "0 tests",
        "no test files",
        "0 total",
    )
    return any(sig in low for sig in zero_signals)


def audit_tool_tests(root: Path) -> dict[str, Any]:
    """scope='tool' dimension='tests' — run the configured test command.

    Blocks when the suite fails, when no test command is configured, or when
    the run reports zero tests executed. Mode-aware no-op outside tool_build.
    """
    root = Path(root)
    if not is_tool_build_mode(root):
        return _not_applicable("tests", root)

    res = build_op(root, "test")
    blockers: list[str] = []
    warnings: list[str] = []

    if not res.get("configured", False):
        blockers.append(
            "No test command configured — set workspace.commands.test in "
            "researcher_config.yaml so the test gate has something to run."
        )
        return _envelope("tests", blockers, warnings, build_result=res)

    if not res.get("passed", False):
        tail = res.get("output_tail", "")
        blockers.append(
            f"Test suite failed (exit {res.get('exit_code')}). Fix before "
            f"committing/releasing. Tail:\n{tail}"
        )
    elif _looks_like_zero_tests(res.get("output_tail", "")):
        blockers.append(
            "Test command succeeded but appears to have run ZERO tests — a "
            "green run that proved nothing. Confirm the suite is wired and "
            "actually exercises the increment."
        )

    return _envelope("tests", blockers, warnings, build_result=res)


# ---------------------------------------------------------------------------
# dimension='git_hygiene'
# ---------------------------------------------------------------------------


def audit_tool_git_hygiene(root: Path) -> dict[str, Any]:
    """scope='tool' dimension='git_hygiene' — inner-repo history is honest.

    Blocks on: not-a-repo, no commit at HEAD, uncommitted changes.
    Warns on: recent commit subjects that look like WIP/fixup leftovers.
    Mode-aware no-op outside tool_build.
    """
    root = Path(root)
    if not is_tool_build_mode(root):
        return _not_applicable("git_hygiene", root)

    blockers: list[str] = []
    warnings: list[str] = []

    status = git_op(root, "status")
    if status.get("status") == "error":
        blockers.append(
            f"Inner repo is not in a clean git state: {status.get('message')}"
        )
        return _envelope("git_hygiene", blockers, warnings, git_status=status)

    if not status.get("head"):
        blockers.append(
            "Inner repo has no commit at HEAD — nothing committed yet. "
            "Commit the work (tool_git(operation='commit')) before this gate "
            "can pass."
        )

    if not status.get("clean", True):
        changed = status.get("changed_files") or []
        blockers.append(
            f"Inner repo has {len(changed)} uncommitted change(s): "
            f"{', '.join(changed[:10])}"
            + (" ..." if len(changed) > 10 else "")
            + ". Commit or stash before tagging/releasing."
        )

    # WIP-subject scan over recent history (warning only).
    log = git_op(root, "log", max_count=_HYGIENE_SCAN_COMMITS)
    flagged: list[str] = []
    if log.get("status") == "success":
        for commit in log.get("commits") or []:
            subject = (commit.get("subject") or "").strip().lower()
            if any(subject.startswith(m) or m in subject for m in _WIP_MARKERS):
                flagged.append(
                    f"{commit.get('sha', '')[:8]} {commit.get('subject', '')}"
                )
    if flagged:
        warnings.append(
            "Recent commit subject(s) look like WIP/fixup leftovers — "
            "consider squashing/rewording before release: "
            + "; ".join(flagged)
        )

    return _envelope(
        "git_hygiene",
        blockers,
        warnings,
        git_status=status,
        wip_commits=flagged,
    )


# ---------------------------------------------------------------------------
# dimension='build'
# ---------------------------------------------------------------------------


def audit_tool_build(root: Path) -> dict[str, Any]:
    """scope='tool' dimension='build' — the configured build command succeeds.

    Blocks when the build fails or no build command is configured.
    Mode-aware no-op outside tool_build.
    """
    root = Path(root)
    if not is_tool_build_mode(root):
        return _not_applicable("build", root)

    res = build_op(root, "build")
    blockers: list[str] = []
    warnings: list[str] = []

    if not res.get("configured", False):
        blockers.append(
            "No build command configured — set workspace.commands.build in "
            "researcher_config.yaml so the build gate has something to run."
        )
        return _envelope("build", blockers, warnings, build_result=res)

    if not res.get("passed", False):
        tail = res.get("output_tail", "")
        blockers.append(
            f"Build failed (exit {res.get('exit_code')}). Tail:\n{tail}"
        )

    return _envelope("build", blockers, warnings, build_result=res)
