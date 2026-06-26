"""Tool definitions for the tool_build domain (git + build/test/lint)."""
from __future__ import annotations

from typing import Any


BUILD_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tool_git": {
        "short": "Provenance-aware git for the tool_build inner repo. operation=init|status|commit|branch|tag|log|diff.",
        "do_not": "Only operates inside workspace.inner_repo; refuses paths outside the project root. For destructive verbs (reset/clean/push) use tool_bash_exec with researcher confirmation.",
        "description": "First-class git for tool_build mode, hard-scoped to the inner project repo (workspace.inner_repo, default 'project'). operation='init' git-inits the inner dir (idempotent); 'status' returns branch + HEAD + clean + changed_files; 'commit' stages (-A by default, or explicit paths=) and commits message= — pass step_id= to stamp a 'Research-OS-Step:' trailer linking the commit to the RO unit of work (provenance); 'branch' creates name= (checkout -b) or lists branches; 'tag' creates an annotated tag name= on HEAD (annotated=false for lightweight) or lists tags; 'log' returns the last max_count= commits as {sha, author, date, subject}; 'diff' returns a --stat summary; 'restore' rolls the working tree (or paths=) back to a known-good tag/commit name= WITHOUT moving HEAD or losing history (the safe 'go back to the version the eval blessed' lever — commit the restored state to make it current). Every operation is path-contained to <root>/<inner_repo> and NEVER runs git elsewhere. Graceful (status='error' with a message, never a crash) when git is absent, the dir isn't a repo, or args are bad. The build/* protocols use this for per-increment commits + release tags + rollback.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["init", "status", "commit", "branch", "tag", "log", "diff", "restore"],
                    "description": "Which git verb to run, scoped to the inner repo.",
                },
                "message": {
                    "type": "string",
                    "description": "operation='commit' — REQUIRED commit message. operation='tag' — annotation message (defaults to the tag name).",
                },
                "step_id": {
                    "type": "string",
                    "description": "operation='commit' — optional RO step the commit advances; recorded as a 'Research-OS-Step:' trailer for provenance.",
                },
                "name": {
                    "type": "string",
                    "description": "operation='branch'/'tag' — the branch/tag name to create. Omit to LIST branches/tags instead.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "operation='commit'/'diff' — restrict to these inner-repo-relative paths (commit: stage only these; diff: limit the stat).",
                },
                "all_changes": {
                    "type": "boolean",
                    "description": "operation='commit' — stage all changes with 'git add -A' before committing (default true; ignored when paths= is given).",
                },
                "max_count": {
                    "type": "integer",
                    "description": "operation='log' — number of recent commits to return (default 20).",
                },
                "annotated": {
                    "type": "boolean",
                    "description": "operation='tag' — create an annotated tag (default true); false makes a lightweight tag.",
                },
            },
            "required": ["operation"],
        },
    },
    "tool_build": {
        "short": "Run the researcher-declared build/test/lint command in the inner repo. operation=build|test|lint.",
        "description": "Shells the per-operation command declared in researcher_config.yaml#workspace.commands.{build,test,lint}, with cwd = the tool_build inner repo. operation='build' runs the build/compile, 'test' runs the test suite, 'lint' runs the static checks. Returns {passed, exit_code, command, output_tail, log_path}; the full transcript is written to workspace/logs/build_<operation>.log and only the tail rides in the envelope. When the requested command is NOT configured it returns a clear status='error' naming the exact key to set (e.g. 'configure workspace.commands.test') rather than crashing. Path-contained to the inner repo; refuses to run outside the project root. The build/* protocols use this to run tests/build per increment; tool_audit(scope='tool', dimension='tests'|'build') wraps it as a gate.",
        "category": "exec",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["build", "test", "lint"],
                    "description": "Which configured command to run.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Per-run timeout in seconds (default 1800).",
                },
            },
            "required": ["operation"],
        },
    },
}
