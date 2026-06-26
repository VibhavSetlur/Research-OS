"""Provenance-aware git + build/test/lint tools for tool_build workspace mode.

These are the tool_build analog of the analysis-side exec tools. In
``workspace.mode == 'tool_build'`` the actual tool being built lives in an
inner git repository (``workspace.inner_repo``, default ``project``) that is
SEPARATE from the Research OS governance workspace. The build/* protocols
previously drove git / build / test purely through ``tool_bash_exec``; these
two tools give them first-class, machine-readable, path-contained entry points.

``tool_git`` wraps the common git verbs (init / status / commit / branch /
tag / log / diff) and is HARD-SCOPED to the inner-repo path — it refuses to
operate on any directory outside ``<root>/<inner_repo>`` so a stray operation
can never touch the governance workspace or a parent repo. Commits accept an
optional ``step_id`` so the commit links back to the RO unit of work
(provenance).

``tool_build`` shells a per-operation command the researcher declares in
``researcher_config.yaml`` under ``workspace.commands.{build,test,lint}``. It
returns pass/fail plus a captured-output tail; if no command is configured it
returns a clear "configure workspace.commands.<op>" message instead of
crashing.

Both degrade gracefully: git absent, not-a-repo, missing inner dir, and
unconfigured commands all map to a structured envelope, never an exception.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_os.tools.actions.state.config import (
    get_inner_repo_dir,
    get_research_config,
    get_workspace_mode,
)

logger = logging.getLogger("research_os.tools.build_tools")


# Verbs tool_git knows how to run. Kept small + closed: everything here is a
# read or an append-only write scoped to the inner repo. Destructive verbs
# (reset --hard, clean, push) are intentionally NOT exposed — the AI runs
# those, when truly needed, through tool_bash_exec with explicit researcher
# confirmation.
_GIT_OPERATIONS = ("init", "status", "commit", "branch", "tag", "log", "diff", "restore")

# How many trailing lines of captured output tool_build keeps. The full
# stream is logged to workspace/logs/; the envelope carries only the tail so
# a green run doesn't flood the model context.
_OUTPUT_TAIL_LINES = 40

# Default per-op timeout (seconds) for build/test/lint shell commands.
_BUILD_TIMEOUT = 1800


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _inner_repo_path(root: Path) -> Path:
    """Absolute, resolved path to the inner repo dir (may not yet exist)."""
    return (Path(root) / get_inner_repo_dir(Path(root))).resolve()


def _is_contained(child: Path, parent: Path) -> bool:
    """True iff ``child`` is ``parent`` or lives beneath it (path-containment)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _tail(text: str, n: int = _OUTPUT_TAIL_LINES) -> str:
    """Return the last ``n`` non-empty-trimmed lines of ``text``."""
    if not text:
        return ""
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def _git_available() -> bool:
    return shutil.which("git") is not None


def _is_git_repo(path: Path) -> bool:
    """True iff ``path`` is inside a git work-tree (cheap, no exception)."""
    if not _git_available() or not path.exists():
        return False
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def _run_git(repo: Path, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run ``git <args>`` in ``repo`` and return the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _current_branch(repo: Path) -> str | None:
    try:
        res = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        # No git / not a repo yet → no branch to report.
        pass
    return None


def _head_sha(repo: Path) -> str | None:
    try:
        res = _run_git(repo, ["rev-parse", "HEAD"])
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        # No git / no commits yet → no HEAD sha to report.
        pass
    return None


# ---------------------------------------------------------------------------
# tool_git
# ---------------------------------------------------------------------------


def git_op(
    root: Path,
    operation: str,
    *,
    message: str | None = None,
    step_id: str | None = None,
    name: str | None = None,
    paths: list[str] | None = None,
    all_changes: bool = True,
    max_count: int = 20,
    annotated: bool = True,
) -> dict[str, Any]:
    """Run a path-contained git operation in the tool_build inner repo.

    operation ∈ {init, status, commit, branch, tag, log, diff}. Every
    operation is scoped to ``<root>/<inner_repo>``; this function NEVER runs
    git outside that directory. Returns a machine-readable envelope:
    ``{status, operation, repo, branch?, sha?, changed_files?, ...}``.

    Graceful on: git binary absent, inner dir missing, not-a-repo (every
    non-init op), and bad args — all map to ``status='error'`` with a
    message, never an exception.
    """
    root = Path(root)
    operation = (operation or "").strip()
    if operation not in _GIT_OPERATIONS:
        return {
            "status": "error",
            "message": (
                f"tool_git: unknown operation '{operation}'. "
                f"Valid: {', '.join(_GIT_OPERATIONS)}."
            ),
        }

    if not _git_available():
        return {
            "status": "error",
            "operation": operation,
            "message": "git binary not found on PATH. Install git to use tool_git.",
        }

    repo = _inner_repo_path(root)
    # Path-containment: the resolved repo MUST live under the project root.
    # A configured inner_repo that escapes (via symlink / traversal) is
    # refused outright. get_inner_repo_dir already collapses to a single safe
    # segment, but resolve()+contains is the belt-and-braces guard.
    root_resolved = root.resolve()
    if not _is_contained(repo, root_resolved):
        return {
            "status": "error",
            "operation": operation,
            "message": (
                f"tool_git refuses to operate outside the project root. "
                f"Resolved inner repo {repo} is not under {root_resolved}."
            ),
        }

    # --- init -----------------------------------------------------------
    if operation == "init":
        repo.mkdir(parents=True, exist_ok=True)
        if _is_git_repo(repo):
            return {
                "status": "success",
                "operation": "init",
                "repo": str(repo.relative_to(root_resolved)),
                "already_initialised": True,
                "branch": _current_branch(repo),
            }
        try:
            res = _run_git(repo, ["init"])
        except Exception as e:  # pragma: no cover - defensive
            return {"status": "error", "operation": "init", "message": str(e)}
        if res.returncode != 0:
            return {
                "status": "error",
                "operation": "init",
                "message": f"git init failed: {_tail(res.stderr or res.stdout)}",
            }
        return {
            "status": "success",
            "operation": "init",
            "repo": str(repo.relative_to(root_resolved)),
            "already_initialised": False,
            "branch": _current_branch(repo),
        }

    # Every non-init op requires an existing repo.
    if not _is_git_repo(repo):
        return {
            "status": "error",
            "operation": operation,
            "message": (
                f"{repo} is not a git repository. "
                "Run tool_git(operation='init') first "
                "(or check workspace.inner_repo in researcher_config.yaml)."
            ),
        }

    try:
        # --- status -----------------------------------------------------
        if operation == "status":
            res = _run_git(repo, ["status", "--porcelain"])
            changed = [
                line[3:] for line in res.stdout.splitlines() if line.strip()
            ]
            return {
                "status": "success",
                "operation": "status",
                "branch": _current_branch(repo),
                "head": _head_sha(repo),
                "clean": not changed,
                "changed_files": changed,
                "changed_count": len(changed),
            }

        # --- commit -----------------------------------------------------
        if operation == "commit":
            if not message or not str(message).strip():
                return {
                    "status": "error",
                    "operation": "commit",
                    "message": "tool_git(operation='commit') requires a non-empty message.",
                }
            # Stage: explicit paths if given, else everything (-A).
            if paths:
                add_res = _run_git(repo, ["add", "--", *paths])
            elif all_changes:
                add_res = _run_git(repo, ["add", "-A"])
            else:
                add_res = subprocess.CompletedProcess([], 0, "", "")
            if add_res.returncode != 0:
                return {
                    "status": "error",
                    "operation": "commit",
                    "message": f"git add failed: {_tail(add_res.stderr or add_res.stdout)}",
                }
            # Provenance: link the commit to the RO step that produced it.
            full_message = str(message).strip()
            if step_id and str(step_id).strip():
                full_message += f"\n\nResearch-OS-Step: {str(step_id).strip()}"
            res = _run_git(repo, ["commit", "-m", full_message])
            if res.returncode != 0:
                tail = _tail(res.stdout or res.stderr)
                # "nothing to commit" is a benign no-op, not a hard failure.
                if "nothing to commit" in (res.stdout + res.stderr).lower():
                    return {
                        "status": "noop",
                        "operation": "commit",
                        "message": "nothing to commit (working tree clean).",
                        "branch": _current_branch(repo),
                        "head": _head_sha(repo),
                    }
                return {
                    "status": "error",
                    "operation": "commit",
                    "message": f"git commit failed: {tail}",
                }
            return {
                "status": "success",
                "operation": "commit",
                "branch": _current_branch(repo),
                "sha": _head_sha(repo),
                "step_id": str(step_id).strip() if step_id else None,
            }

        # --- branch -----------------------------------------------------
        if operation == "branch":
            if name and str(name).strip():
                res = _run_git(repo, ["checkout", "-b", str(name).strip()])
                if res.returncode != 0:
                    return {
                        "status": "error",
                        "operation": "branch",
                        "message": f"git checkout -b failed: {_tail(res.stderr or res.stdout)}",
                    }
                return {
                    "status": "success",
                    "operation": "branch",
                    "created": str(name).strip(),
                    "branch": _current_branch(repo),
                }
            # No name → list branches.
            res = _run_git(repo, ["branch", "--list"])
            branches = [
                line.lstrip("* ").strip()
                for line in res.stdout.splitlines()
                if line.strip()
            ]
            return {
                "status": "success",
                "operation": "branch",
                "branch": _current_branch(repo),
                "branches": branches,
            }

        # --- tag --------------------------------------------------------
        if operation == "tag":
            if name and str(name).strip():
                tag_name = str(name).strip()
                tag_args = ["tag"]
                if annotated:
                    tag_args += ["-a", tag_name, "-m", message or tag_name]
                else:
                    tag_args += [tag_name]
                res = _run_git(repo, tag_args)
                if res.returncode != 0:
                    return {
                        "status": "error",
                        "operation": "tag",
                        "message": f"git tag failed: {_tail(res.stderr or res.stdout)}",
                    }
                return {
                    "status": "success",
                    "operation": "tag",
                    "created": tag_name,
                    "annotated": bool(annotated),
                    "sha": _head_sha(repo),
                }
            # No name → list tags.
            res = _run_git(repo, ["tag", "--list"])
            tags = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return {
                "status": "success",
                "operation": "tag",
                "tags": tags,
            }

        # --- restore (rollback to a known-good version) -----------------
        if operation == "restore":
            # Path-contained rollback: restore the working tree (or specific
            # paths) to a named tag/commit WITHOUT moving HEAD or discarding
            # history — the reverted-from state stays recoverable (it's still
            # in the reflog + any later tags). This is the safe "go back to the
            # version the eval blessed" lever for build/versioning_and_rollback.
            ref = (name or "").strip()
            if not ref:
                return {
                    "status": "error",
                    "operation": "restore",
                    "message": (
                        "restore needs name=<tag-or-commit> to roll back to. "
                        "Use operation='tag' (no name) to list blessed versions."
                    ),
                }
            # Verify the ref exists before touching the tree.
            check = _run_git(repo, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
            if check.returncode != 0:
                return {
                    "status": "error",
                    "operation": "restore",
                    "message": f"unknown tag/commit '{ref}' — nothing restored.",
                }
            # Snapshot current HEAD so the response tells the AI exactly what it
            # rolled back FROM (so it can roll forward again if needed).
            from_sha = _head_sha(repo)
            target_paths = list(paths) if paths else ["."]
            res = _run_git(repo, ["checkout", ref, "--", *target_paths])
            if res.returncode != 0:
                return {
                    "status": "error",
                    "operation": "restore",
                    "message": f"git restore failed: {_tail(res.stderr or res.stdout)}",
                }
            return {
                "status": "success",
                "operation": "restore",
                "restored_to": ref,
                "rolled_back_from": from_sha,
                "paths": target_paths,
                "note": (
                    "Working tree restored to '%s'. HEAD did not move and no "
                    "history was lost — commit the restored state to make it "
                    "current, or roll forward to %s to undo this." % (ref, from_sha)
                ),
            }

        # --- log --------------------------------------------------------
        if operation == "log":
            n = max(1, int(max_count or 20))
            res = _run_git(
                repo,
                ["log", f"-n{n}", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=iso"],
            )
            if res.returncode != 0:
                # Empty repo (no commits yet) is not an error.
                if "does not have any commits" in (res.stderr or "").lower():
                    return {
                        "status": "success",
                        "operation": "log",
                        "commits": [],
                        "branch": _current_branch(repo),
                    }
                return {
                    "status": "error",
                    "operation": "log",
                    "message": f"git log failed: {_tail(res.stderr or res.stdout)}",
                }
            commits = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\x1f")
                if len(parts) == 4:
                    commits.append({
                        "sha": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3],
                    })
            return {
                "status": "success",
                "operation": "log",
                "branch": _current_branch(repo),
                "commits": commits,
                "commit_count": len(commits),
            }

        # --- diff -------------------------------------------------------
        if operation == "diff":
            args = ["diff", "--stat"]
            if paths:
                args += ["--", *paths]
            res = _run_git(repo, args)
            if res.returncode not in (0, 1):
                return {
                    "status": "error",
                    "operation": "diff",
                    "message": f"git diff failed: {_tail(res.stderr or res.stdout)}",
                }
            return {
                "status": "success",
                "operation": "diff",
                "branch": _current_branch(repo),
                "diffstat": res.stdout.strip(),
                "has_changes": bool(res.stdout.strip()),
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "operation": operation,
            "message": f"git {operation} timed out.",
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("tool_git %s failed", operation)
        return {"status": "error", "operation": operation, "message": str(e)}

    # Unreachable — every operation returns above.
    return {"status": "error", "operation": operation, "message": "unhandled git operation"}


# ---------------------------------------------------------------------------
# tool_build
# ---------------------------------------------------------------------------


_BUILD_OPERATIONS = ("build", "test", "lint")


def _configured_command(root: Path, operation: str) -> str | None:
    """Return ``workspace.commands.<operation>`` from researcher_config, or None."""
    cfg = get_research_config(Path(root)) or {}
    workspace = cfg.get("workspace") or {}
    if not isinstance(workspace, dict):
        return None
    commands = workspace.get("commands") or {}
    if not isinstance(commands, dict):
        return None
    cmd = commands.get(operation)
    if isinstance(cmd, str) and cmd.strip():
        return cmd.strip()
    return None


def build_op(
    root: Path,
    operation: str,
    *,
    timeout: int = _BUILD_TIMEOUT,
) -> dict[str, Any]:
    """Run the researcher-declared build/test/lint command in the inner repo.

    operation ∈ {build, test, lint}. The command is read from
    ``researcher_config.yaml#workspace.commands.<operation>`` and executed via
    the shell with cwd = the inner repo dir. Returns
    ``{status, operation, passed, exit_code, command, output_tail, ...}``.

    No command configured → a clear ``status='error'`` message telling the
    researcher exactly which key to set (NOT a crash). The full output is
    written to ``workspace/logs/build_<operation>.log``; the envelope carries
    only the tail.
    """
    root = Path(root)
    operation = (operation or "").strip()
    if operation not in _BUILD_OPERATIONS:
        return {
            "status": "error",
            "message": (
                f"tool_build: unknown operation '{operation}'. "
                f"Valid: {', '.join(_BUILD_OPERATIONS)}."
            ),
        }

    command = _configured_command(root, operation)
    if not command:
        return {
            "status": "error",
            "operation": operation,
            "configured": False,
            "message": (
                f"No command configured for tool_build(operation='{operation}'). "
                f"Set workspace.commands.{operation} in "
                "inputs/researcher_config.yaml (e.g. "
                f"workspace.commands.{operation}: \"pytest -q\")."
            ),
        }

    repo = _inner_repo_path(root)
    root_resolved = root.resolve()
    if not _is_contained(repo, root_resolved):
        return {
            "status": "error",
            "operation": operation,
            "message": (
                f"tool_build refuses to run outside the project root. "
                f"Resolved inner repo {repo} is not under {root_resolved}."
            ),
        }
    if not repo.exists():
        return {
            "status": "error",
            "operation": operation,
            "message": (
                f"Inner repo dir {repo.name}/ does not exist yet. "
                "Create it (tool_git(operation='init')) before running builds."
            ),
        }

    try:
        res = subprocess.run(
            command,
            cwd=str(repo),
            shell=True,  # noqa: S602 — researcher-declared command, intentional
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "operation": operation,
            "command": command,
            "message": f"command timed out after {timeout}s.",
        }
    except Exception as e:  # pragma: no cover - defensive
        return {
            "status": "error",
            "operation": operation,
            "command": command,
            "message": str(e),
        }

    # Persist the full transcript; envelope keeps only the tail.
    try:
        log_dir = root / "workspace" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"build_{operation}.log").write_text(
            f"$ {command}\n(cwd: {repo})\nexit: {res.returncode}\n\n"
            f"STDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}\n"
        )
    except Exception:  # pragma: no cover - logging best effort
        pass

    passed = res.returncode == 0
    combined = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
    return {
        "status": "success" if passed else "error",
        "operation": operation,
        "configured": True,
        "passed": passed,
        "exit_code": res.returncode,
        "command": command,
        "output_tail": _tail(combined),
        "log_path": f"workspace/logs/build_{operation}.log",
    }


# ---------------------------------------------------------------------------
# Mode-awareness helper (shared by the scope='tool' audits)
# ---------------------------------------------------------------------------


def is_tool_build_mode(root: Path) -> bool:
    """True iff workspace.mode == 'tool_build' for this project."""
    return get_workspace_mode(Path(root)) == "tool_build"
