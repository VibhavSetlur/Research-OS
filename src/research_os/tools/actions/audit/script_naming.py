"""Analysis-step script naming + within-step organization validator (4.0.3).

The convention (guidance/analysis_plan.yaml): scripts in a numbered step live in
``workspace/<NN>_<slug>/scripts/`` and are named one of two equivalent ways:

  A) chronological:  <NN>[a-z]_<short_name>_v<k>.<ext>   e.g. 01a_load_counts_v1.py
  B) descriptive:    <NN>_<descriptive>_v<k>.<ext>        e.g. 01_fit_baseline_v1.py

where <NN> is the step's OWN zero-padded number, [a-z] is an optional ordering
letter, <name> is snake_case, _v<k> is the iteration suffix (k = 1..), and <ext>
is one of the supported analysis languages.

The AI repeatedly fails to follow this and, before 4.0.3, NOTHING validated it —
the completeness audit only checked that scripts/ was non-empty. This module is
the single source of truth so the step-completeness gate AND the daemon's
structure watch enforce the SAME rule.

Public surface:
  * SUPPORTED_SCRIPT_EXTS  - frozenset of analysis-script extensions
  * is_helper_module(name) - True for legit non-numbered helpers (utils.py, …)
  * validate_script_name(name, step_number) -> str | None  (None == OK; else why)
  * suggest_script_name(name, step_number) -> str          (a conforming rename)
  * audit_step_script_naming(step_dir) -> dict             (per-step verdict)
  * audit_script_naming(root, step_id=None) -> dict        (project / one step)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Extensions that ARE analysis scripts and therefore must follow the convention.
SUPPORTED_SCRIPT_EXTS = frozenset(
    {".py", ".r", ".jl", ".sh", ".ipynb", ".rmd", ".qmd"}
)

# Helper / infra files that legitimately live in scripts/ but are NOT numbered
# analysis steps — they are imported BY the numbered scripts, not run as a
# sub-task. These are exempt from the <NN>_..._v<k> rule.
_HELPER_EXACT = frozenset(
    {
        "__init__.py",
        "utils.py",
        "helpers.py",
        "common.py",
        "config.py",
        "constants.py",
        "conftest.py",
        "setup.py",
        "requirements.txt",
        "environment.yml",
        "renv.lock",
        "makefile",
        "readme.md",
    }
)
# Helper by shape: lib-prefixed, test_ files, dotfiles.
_HELPER_PREFIXES = ("lib_", "lib/", "_", "test_", ".")

# The canonical name regex. Captures:
#   group 'nn'     -> the leading number (must equal the step number)
#   group 'letter' -> optional single ordering letter (style A)
#   group 'name'   -> snake_case short name (>= 1 char)
#   group 'ver'    -> iteration suffix k (>= 1)
_NAME_RE = re.compile(
    r"^(?P<nn>\d{1,3})(?P<letter>[a-z])?_(?P<name>[a-z0-9]+(?:_[a-z0-9]+)*)_v(?P<ver>\d+)$"
)


def is_helper_module(name: str) -> bool:
    """True if ``name`` is a legitimate helper/infra file (exempt from the rule)."""
    low = name.lower()
    if low in _HELPER_EXACT:
        return True
    return any(low.startswith(p) for p in _HELPER_PREFIXES)


def _step_number(step_dir_name: str) -> str | None:
    """Extract the zero-padded number prefix of a step folder (``01_foo`` -> ``01``)."""
    m = re.match(r"^(\d{1,3})_", step_dir_name)
    return m.group(1) if m else None


def validate_script_name(name: str, step_number: str | None) -> str | None:
    """Return ``None`` if ``name`` conforms, else a one-line reason it doesn't.

    ``step_number`` is the step folder's number (``"01"``). When provided, the
    script's <NN> prefix must match it (a 01_ script under step 02 is a bug).
    Helper modules are always OK.
    """
    if is_helper_module(name):
        return None
    stem, dot, ext = name.rpartition(".")
    if not dot or f".{ext.lower()}" not in SUPPORTED_SCRIPT_EXTS:
        # Not a recognised analysis-script extension — not our concern.
        return None
    m = _NAME_RE.match(stem)
    if not m:
        return (
            "does not match <NN>[a-z]_<snake_name>_v<k> "
            "(e.g. 01a_load_counts_v1 or 01_fit_baseline_v1)"
        )
    if step_number is not None:
        nn = m.group("nn")
        # Compare numerically so 1 == 01.
        if int(nn) != int(step_number):
            return (
                f"number prefix '{nn}' does not match this step's number "
                f"'{step_number}' (a script's <NN> must be its own step's number)"
            )
    return None


def suggest_script_name(name: str, step_number: str | None) -> str:
    """Best-effort conforming rename for a non-conforming script name."""
    stem, dot, ext = name.rpartition(".")
    ext = (ext if dot else "py").lower()
    nn = (step_number or "01")
    try:
        nn = f"{int(nn):02d}"
    except (TypeError, ValueError):
        nn = "01"
    # Strip any leading number/letter the AI already put, and any _v<k>.
    body = re.sub(r"^\d{1,3}[a-z]?_?", "", stem)
    body = re.sub(r"_v\d+$", "", body)
    body = re.sub(r"[^a-zA-Z0-9]+", "_", body).strip("_").lower() or "step"
    return f"{nn}_{body}_v1.{ext}"


def audit_step_script_naming(step_dir: Path) -> dict[str, Any]:
    """Validate every script under ``step_dir/scripts/`` against the convention."""
    step_dir = Path(step_dir)
    step_number = _step_number(step_dir.name)
    scripts_dir = step_dir / "scripts"
    violations: list[dict[str, str]] = []
    checked = 0
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.iterdir()):
            if not f.is_file():
                continue
            if f.suffix.lower() not in SUPPORTED_SCRIPT_EXTS:
                continue
            checked += 1
            why = validate_script_name(f.name, step_number)
            if why is not None:
                violations.append({
                    "script": f"scripts/{f.name}",
                    "why": why,
                    "suggest": suggest_script_name(f.name, step_number),
                })
    status = "error" if violations else "success"
    return {
        "status": status,
        "step": step_dir.name,
        "scripts_checked": checked,
        "violations": violations,
        "blockers": [
            f"{v['script']}: {v['why']} -> rename to {v['suggest']}"
            for v in violations
        ],
        "convention": (
            "scripts/<NN>[a-z]_<snake_name>_v<k>.<ext> where <NN> is this step's "
            "number; see guidance/analysis_plan.yaml. Helper modules "
            "(utils.py, __init__.py, lib_*, _*) are exempt."
        ),
    }


def audit_script_naming(root: Path, step_id: str | None = None) -> dict[str, Any]:
    """Validate script naming across one step or every numbered step."""
    root = Path(root)
    workspace = root / "workspace"
    per_step: list[dict[str, Any]] = []
    if not workspace.is_dir():
        return {"status": "success", "steps_audited": 0, "per_step": [],
                "blockers": [], "message": "no workspace/ to audit"}
    if step_id:
        targets = [workspace / step_id] if (workspace / step_id).is_dir() else []
    else:
        targets = [
            d for d in sorted(workspace.iterdir())
            if d.is_dir() and re.match(r"^\d{1,3}_", d.name)
        ]
    blockers: list[str] = []
    for sd in targets:
        v = audit_step_script_naming(sd)
        per_step.append(v)
        blockers.extend(f"{sd.name}/{b}" for b in v["blockers"])
    return {
        "status": "error" if blockers else "success",
        "steps_audited": len(targets),
        "per_step": per_step,
        "blockers": blockers,
    }
