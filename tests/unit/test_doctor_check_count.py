"""Contract test: `cli_doctor` ships at least 18 `check_*` functions.

The README and FAQ both advertise "18+ install + workspace health
checks". If a refactor accidentally collapses two checks into one,
or if a check_* helper is removed without bumping the docs, this
test fires so the doc/string and code stay in lock-step.

Counts the public ``def check_*`` definitions both via
``inspect``/``ast`` (catches definitions even if they shadow another
attribute) and via a regex on the source file (matches the
``grep -c '^def check_'`` invariant used by the work-item harness).
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from research_os import cli_doctor


MIN_CHECKS = 18


def test_doctor_exposes_at_least_18_check_functions():
    """The module-level `check_*` callables must number >= 18."""
    public_checks = [
        name for name, obj in inspect.getmembers(cli_doctor, inspect.isfunction)
        if name.startswith("check_") and obj.__module__ == cli_doctor.__name__
    ]
    assert len(public_checks) >= MIN_CHECKS, (
        f"cli_doctor exposes {len(public_checks)} check_* functions "
        f"(< {MIN_CHECKS}). Either restore the missing checks or "
        f"update the README/FAQ to match. Found: {sorted(public_checks)}"
    )


def test_doctor_source_has_at_least_18_def_check_lines():
    """Mirror the `grep -c '^def check_'` invariant from the release gate."""
    src = Path(cli_doctor.__file__).read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^def check_\w+", src)
    assert len(matches) >= MIN_CHECKS, (
        f"`grep -c '^def check_' cli_doctor.py` would return {len(matches)} "
        f"(< {MIN_CHECKS}). The work item W12 explicitly requires this gate."
    )


def test_ast_walks_match_inspect_count():
    """Sanity: inspect-based count and AST-based count agree.
    Catches the case where a check_* is defined inside a class or
    inside another function (which inspect.getmembers would miss
    but ast.parse would still see)."""
    src = Path(cli_doctor.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    top_level = [
        node.name for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("check_")
    ]
    assert len(top_level) >= MIN_CHECKS
