"""Handlers — synthesis_reviewer sub-domain.

Carved out of handlers/synthesis.py to stay under the 600-line ceiling.
"""
from __future__ import annotations

from .._handlers_runtime import *  # noqa: F401,F403

__all__ = [
    "_handle_tool_reviewer_simulate",
    "_handle_tool_rebuttal_draft",
    "_handle_tool_reviewer_response_compile",
    "_handle_tool_reviewer",
    "_handle_tool_response_to_reviewers",
]

def _handle_tool_reviewer_simulate(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import reviewer_simulate
    res = reviewer_simulate(root, personas=arguments.get("personas"))
    if res.get("status") == "error":
        return _text(_error(res.get("message", "reviewer_simulate failed")))
    return _text(_success(res))


def _handle_tool_rebuttal_draft(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import rebuttal_draft
    res = rebuttal_draft(
        root,
        comment=arguments["comment"],
        persona=arguments["persona"],
        evidence_paths=arguments.get("evidence_paths"),
    )
    if res.get("status") == "error":
        return _text(_error(res.get("message", "rebuttal_draft failed")))
    return _text(_success(res))


def _handle_tool_reviewer_response_compile(name, arguments, root):
    from research_os.tools.actions.synthesis.reviewer import (
        reviewer_response_compile,
    )
    res = reviewer_response_compile(root)
    if res.get("status") == "error":
        return _text(_error(res.get("message", "compile failed")))
    return _text(_success(res))


def _handle_tool_reviewer(name, arguments, root):
    """Unified reviewer-response dispatcher.

    Operations:
      simulate → tool_reviewer_simulate         (build 7-persona pre-submission brief)
      response → tool_response_to_reviewers     (write synthesis/response_to_reviewers.md template)
      rebuttal → tool_rebuttal_draft            (scaffold one rebuttal .md w/ evidence inventory)
      compile  → tool_reviewer_response_compile (assemble rebuttals into response_to_reviewers.md +PDF)

    Every legacy ``tool_reviewer_simulate`` / ``tool_response_to_reviewers``
    / ``tool_rebuttal_draft`` / ``tool_reviewer_response_compile`` name is
    aliased to this entry point and has its operation injected via
    ``_ALIAS_PARAM_INJECTION`` so callers (researchers, scripts, protocols)
    using the older per-operation names keep working unchanged.
    """
    op = arguments.get("operation")
    if not op:
        return _text(_error(
            "tool_reviewer requires operation='simulate'|'response'|'rebuttal'|'compile'."
        ))
    if op == "simulate":
        return _handle_tool_reviewer_simulate(name, arguments, root)
    if op == "response":
        return _handle_tool_response_to_reviewers(name, arguments, root)
    if op == "rebuttal":
        return _handle_tool_rebuttal_draft(name, arguments, root)
    if op == "compile":
        return _handle_tool_reviewer_response_compile(name, arguments, root)
    return _text(_error(
        f"tool_reviewer: unknown operation '{op}'. "
        "Valid operations: simulate, response, rebuttal, compile."
    ))


def _handle_tool_response_to_reviewers(name, arguments, root):
    from research_os.tools.actions.audit.redteam import write_response_template

    res = write_response_template(root, review_path=arguments.get("review_path"))
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "response_to_reviewers failed")))


HANDLERS = {
    "tool_reviewer": _handle_tool_reviewer,
}
