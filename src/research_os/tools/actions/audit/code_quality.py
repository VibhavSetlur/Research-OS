"""Code-quality audit for analysis scripts.

Tier-1 quality bar for a step's `scripts/` directory:

* **Lint** — `ruff check` when the binary is on PATH (fast, covers
  what flake8 + isort + most of pylint cover).
* **Static type checks** — `mypy --ignore-missing-imports` when
  available. Soft warning rather than blocker by default.
* **Cyclomatic complexity + function length** — AST-based, no
  external deps. Flag any function ≥ 50 lines OR McCabe ≥ 10.
* **Docstring presence** — every module gets a docstring; every
  *public* function gets one. Private (`_underscore`) functions
  exempt.
* **Bare-except / debug-print / TODO-density** — sloppy-code smells
  that show up in AI-authored analysis scripts.

The auditor writes ``workspace/logs/code_quality.md`` and returns the
classification per script + per-file blockers/warnings that
``tool_audit_step_completeness`` can incorporate into its gating
decision.

The bar is calibrated for *analysis code*, not library code:

* `print()` is fine for analysis scripts (researchers read stdout); the
  audit only flags it when the script also writes structured outputs
  (i.e., it's pretending to be a tool, not a notebook export).
* Type hints are *not* mandatory — many analysts work with untyped
  pandas DataFrames. mypy warnings surface in the report but never
  become blockers without explicit opt-in.
* Wide-open `from foo import *` IS a blocker — it hides what the
  analysis depends on, which breaks reproducibility audits.
"""

from __future__ import annotations

import ast
import logging
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from research_os.tools.actions.audit._base import AuditBase, AuditFinding

logger = logging.getLogger("research_os.audit.code_quality")


# ---------------------------------------------------------------------------
# AST-based complexity + docstring + smell checks
# ---------------------------------------------------------------------------


def _module_docstring(tree: ast.AST) -> str | None:
    if isinstance(tree, ast.Module):
        return ast.get_docstring(tree)
    return None


def _function_metrics(tree: ast.AST) -> list[dict[str, Any]]:
    """Per-function complexity, length, docstring presence."""
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # McCabe complexity = number of decision points + 1.
        complexity = 1
        for sub in ast.walk(node):
            if isinstance(sub, (ast.If, ast.For, ast.AsyncFor,
                                 ast.While, ast.ExceptHandler,
                                 ast.With, ast.AsyncWith,
                                 ast.BoolOp, ast.IfExp)):
                complexity += 1
            elif isinstance(sub, ast.comprehension):
                complexity += 1
        first_line = node.lineno
        last_line = max((getattr(n, "lineno", first_line) for n in ast.walk(node)),
                        default=first_line)
        out.append({
            "name": node.name,
            "is_public": not node.name.startswith("_"),
            "lineno": first_line,
            "length_lines": last_line - first_line + 1,
            "complexity": complexity,
            "has_docstring": ast.get_docstring(node) is not None,
        })
    return out


def _detect_smells(src: str, tree: ast.AST) -> list[str]:
    smells: list[str] = []
    # Bare except (BLOCKER — masks failures).
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            smells.append(
                f"L{node.lineno}: bare `except:` clause — name the exception."
            )
    # `from x import *` (BLOCKER — hides dependencies).
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    smells.append(
                        f"L{node.lineno}: `from {node.module} import *` — "
                        "spell out the imports."
                    )
    # eval / exec (BLOCKER — almost always a code-smell in analysis).
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None)
            if name in {"eval", "exec"}:
                smells.append(
                    f"L{node.lineno}: `{name}()` call — re-write without "
                    "dynamic code execution."
                )
    # TODO density (WARNING).
    todos = re.findall(r"#\s*(TODO|XXX|FIXME)\b", src)
    if len(todos) >= 5:
        smells.append(
            f"{len(todos)} TODO/FIXME markers — high WIP density; "
            "spin off into a tracked issue rather than leaving in code."
        )
    # Hardcoded absolute paths (BLOCKER for reproducibility).
    for m in re.finditer(r'["\']/(?:home|users|scratch|data|mnt)/[^"\'\s]+["\']', src):
        smells.append(
            f"Absolute path literal `{m.group(0)[:60]}…` — load from "
            "config or environment so the script runs on other machines."
        )
        break  # report once
    return smells


def audit_script(path: Path) -> dict[str, Any]:
    """Audit a single Python script. Returns a structured report.

    Result schema::

        {
          "path": "scripts/03_fit_v1.py",
          "ok":   bool,
          "blockers": ["L17: bare `except:`", ...],
          "warnings": [...],
          "module_docstring": True | False,
          "functions": [{"name": "fit", "complexity": 7, "length_lines": 38,
                         "has_docstring": True, "is_public": True}, …],
        }
    """
    if path.suffix.lower() != ".py":
        return {
            "path": str(path),
            "ok": True,
            "blockers": [],
            "warnings": [f"non-Python script (.{path.suffix}); audit skipped"],
            "skipped": True,
        }
    try:
        src = path.read_text(errors="replace")
    except OSError as e:
        return {"path": str(path), "ok": False,
                "blockers": [f"cannot read: {e}"],
                "warnings": [], "skipped": False}
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {
            "path": str(path),
            "ok": False,
            "blockers": [f"SyntaxError at L{e.lineno}: {e.msg}"],
            "warnings": [],
            "skipped": False,
        }

    blockers: list[str] = []
    warnings: list[str] = []

    if not _module_docstring(tree):
        warnings.append(
            "Module has no docstring — start the file with a brief triple-"
            "quoted explanation of what the script does + its inputs/outputs."
        )

    fns = _function_metrics(tree)
    long_fns = [f for f in fns if f["length_lines"] > 80]
    if long_fns:
        for f in long_fns:
            warnings.append(
                f"L{f['lineno']}: function `{f['name']}` is "
                f"{f['length_lines']} lines — split into smaller helpers."
            )
    very_long = [f for f in fns if f["length_lines"] > 150]
    if very_long:
        for f in very_long:
            blockers.append(
                f"L{f['lineno']}: function `{f['name']}` is "
                f"{f['length_lines']} lines (>150). Split it."
            )
    complex_fns = [f for f in fns if f["complexity"] > 10]
    for f in complex_fns:
        warnings.append(
            f"L{f['lineno']}: function `{f['name']}` cyclomatic "
            f"complexity {f['complexity']} (>10) — refactor branches."
        )
    very_complex = [f for f in fns if f["complexity"] > 20]
    for f in very_complex:
        blockers.append(
            f"L{f['lineno']}: function `{f['name']}` complexity "
            f"{f['complexity']} (>20). Refactor before merging."
        )

    public_undocumented = [
        f for f in fns
        if f["is_public"] and not f["has_docstring"]
        and f["length_lines"] >= 8
    ]
    for f in public_undocumented[:5]:
        warnings.append(
            f"L{f['lineno']}: public function `{f['name']}` has no "
            "docstring — at least one sentence describing what it does."
        )

    smells = _detect_smells(src, tree)
    for s in smells:
        # Treat the "definitely a blocker" smells as blockers.
        if any(tok in s for tok in
               ["bare `except:`", "import *`", "`exec()`", "`eval()`",
                "Absolute path literal"]):
            blockers.append(s)
        else:
            warnings.append(s)

    return {
        "path": str(path),
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "module_docstring": bool(_module_docstring(tree)),
        "functions": fns,
        "n_functions": len(fns),
        "longest_function_lines": max(
            (f["length_lines"] for f in fns), default=0),
        "max_complexity": max((f["complexity"] for f in fns), default=0),
    }


# ---------------------------------------------------------------------------
# External tool wrappers (ruff / mypy) — opt-in, graceful when absent.
# ---------------------------------------------------------------------------


def _run_ruff(paths: list[Path]) -> dict[str, Any]:
    ruff = shutil.which("ruff")
    if not ruff:
        return {"ran": False, "reason": "ruff not on PATH"}
    try:
        res = subprocess.run(
            [ruff, "check", "--output-format=concise", *[str(p) for p in paths]],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ran": False, "reason": str(e)}
    return {
        "ran": True,
        "exit_code": res.returncode,
        "issue_count": len([
            ln for ln in (res.stdout or "").splitlines() if ":" in ln
        ]),
        "output_tail": (res.stdout or "")[-3000:],
    }


def _run_mypy(paths: list[Path]) -> dict[str, Any]:
    mypy = shutil.which("mypy")
    if not mypy:
        return {"ran": False, "reason": "mypy not on PATH"}
    try:
        res = subprocess.run(
            [mypy, "--ignore-missing-imports", "--no-error-summary",
             *[str(p) for p in paths]],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ran": False, "reason": str(e)}
    out = res.stdout or ""
    n = len([ln for ln in out.splitlines() if ": error:" in ln])
    return {
        "ran": True,
        "exit_code": res.returncode,
        "error_count": n,
        "output_tail": out[-3000:],
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def audit_code_quality(
    root: Path,
    step_id: str | None = None,
    *,
    run_ruff: bool = True,
    run_mypy: bool = False,
) -> dict[str, Any]:
    """Audit scripts under workspace/<step>/scripts/ (or every step).

    Returns a structured report + writes ``workspace/logs/code_quality.md``.
    """
    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    if step_id:
        targets = [workspace / step_id]
    else:
        targets = [
            d for d in sorted(workspace.iterdir())
            if d.is_dir() and re.match(r"^\d{2,3}_", d.name)
            and not d.name.endswith("__DEAD_END")
        ]

    per_step: list[dict[str, Any]] = []
    any_blockers = False

    for step_dir in targets:
        scripts_dir = step_dir / "scripts"
        if not scripts_dir.exists():
            continue
        scripts = sorted(scripts_dir.glob("*.py"))
        per_script = [audit_script(p) for p in scripts]
        step_blockers = sum(len(s["blockers"]) for s in per_script)
        step_warnings = sum(len(s["warnings"]) for s in per_script)
        if step_blockers:
            any_blockers = True

        ruff_res = _run_ruff(scripts) if (run_ruff and scripts) else {"ran": False}
        mypy_res = _run_mypy(scripts) if (run_mypy and scripts) else {"ran": False}
        if ruff_res.get("ran") and ruff_res.get("exit_code") not in (0, 1):
            # Ruff non-zero = issues found; we treat as warnings (not blockers
            # for analysis code).
            step_warnings += ruff_res.get("issue_count", 0)

        per_step.append({
            "step_id": step_dir.name,
            "script_count": len(per_script),
            "blockers": step_blockers,
            "warnings": step_warnings,
            "scripts": per_script,
            "ruff": ruff_res,
            "mypy": mypy_res,
        })

    # Write summary report.
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "code_quality.md"
    lines = ["# Code Quality Audit", ""]
    if not per_step:
        lines.append("_(no script directories found)_")
    for s in per_step:
        icon = "❌" if s["blockers"] else "⚠️" if s["warnings"] else "✅"
        lines.append(
            f"## {icon} `{s['step_id']}` — "
            f"{s['script_count']} script(s), "
            f"{s['blockers']} blocker(s), {s['warnings']} warning(s)"
        )
        for sc in s["scripts"]:
            sub_icon = "❌" if sc["blockers"] else "⚠️" if sc["warnings"] else "✓"
            lines.append("")
            lines.append(f"### {sub_icon} `{sc['path']}`")
            if sc.get("blockers"):
                lines.append("")
                lines.append("**Blockers**")
                for b in sc["blockers"]:
                    lines.append(f"- {b}")
            if sc.get("warnings"):
                lines.append("")
                lines.append("Warnings")
                for w in sc["warnings"]:
                    lines.append(f"- {w}")
        if s["ruff"].get("ran"):
            lines.append("")
            lines.append("**ruff** issue count: "
                         f"{s['ruff'].get('issue_count', 0)}")
        if s["mypy"].get("ran"):
            lines.append("")
            lines.append("**mypy** error count: "
                         f"{s['mypy'].get('error_count', 0)}")
        lines.append("")
    out.write_text("\n".join(lines) + "\n")

    return {
        "status": "error" if any_blockers else "success",
        "per_step": per_step,
        "report_path": str(out.relative_to(root)),
        "advice": (
            "Code quality BLOCKERS found. Fix them before tool_synthesize: "
            "bare except, import *, eval/exec, absolute paths, oversize "
            "functions (>150 lines)."
            if any_blockers
            else "Code quality audit clean."
        ),
    }


# ---------------------------------------------------------------------------
# AuditBase subclass emitting AuditFinding objects
# ---------------------------------------------------------------------------


# Stable UUID namespace for deterministic finding ids. Re-runs against the
# same workspace state produce the same finding ids so downstream consumers
# (dashboards, history queries) can dedupe by id across runs.
_FINDING_UUID_NAMESPACE = uuid.NAMESPACE_DNS


def _finding_uuid(audit_name: str, dimension: str, evidence_paths: list[str],
                  detail: str = "") -> str:
    """Deterministic uuid5 derived from audit_name + dimension + paths + detail.

    Including ``detail`` lets a single (path, dimension) pair distinguish
    multiple findings (e.g. several blockers in the same script) without
    clashing on the id. Re-runs against the same code state still produce
    the same ids — the inputs are pure functions of the source artefacts.
    """
    key = "|".join([
        audit_name,
        dimension,
        ",".join(sorted(evidence_paths)),
        detail,
    ])
    return str(uuid.uuid5(_FINDING_UUID_NAMESPACE, key))


def _smell_dimension(message: str) -> str:
    """Map a smell/blocker/warning message to a stable dimension tag.

    The dimension axis groups findings in the markdown report and in
    downstream dashboards. We bucket by the substantive code-quality
    concern rather than by severity (severity is its own field).
    """
    m = message.lower()
    if "bare `except" in m or "bare except" in m:
        return "error_handling"
    if "import *" in m:
        return "imports"
    if "eval()" in m or "exec()" in m:
        return "dynamic_exec"
    if "absolute path" in m:
        return "reproducibility"
    if "todo" in m or "fixme" in m:
        return "wip"
    if "complexity" in m:
        return "complexity"
    if "lines" in m and "function" in m:
        return "length"
    if "docstring" in m:
        return "docs"
    if "syntaxerror" in m:
        return "syntax"
    if "cannot read" in m:
        return "io"
    return "code_quality"


class CodeQualityAudit(AuditBase):
    """AuditBase subclass for the analysis-script code-quality gate.

    Delegates to :func:`audit_code_quality` for the heavy lifting (which
    preserves the legacy markdown contract at ``workspace/logs/code_quality.md``)
    and converts the per-script blocker/warning lists into structured
    :class:`AuditFinding` objects.
    """

    name = "code_quality"

    def run(
        self,
        root: Path,
        *,
        step_id: str | None = None,
        run_ruff: bool = True,
        run_mypy: bool = False,
        **_: Any,
    ) -> list[AuditFinding]:
        """Run the code-quality audit and return structured findings.

        Side effect: writes the legacy ``workspace/logs/code_quality.md``
        report (preserved byte-for-byte from the pre-AuditBase entry
        point) so callers that relied on the markdown artefact keep
        working.
        """
        report = audit_code_quality(
            root,
            step_id=step_id,
            run_ruff=run_ruff,
            run_mypy=run_mypy,
        )
        findings: list[AuditFinding] = []
        if report.get("status") == "error" and "message" in report:
            # workspace/ missing — single info finding describing the gap.
            findings.append(
                AuditFinding(
                    id=_finding_uuid(self.name, "workspace", [],
                                     report["message"]),
                    audit_name=self.name,
                    severity="info",
                    dimension="workspace",
                    evidence_paths=[],
                    suggested_fix=(
                        "Create workspace/<NN>_<slug>/scripts/ before "
                        "running the code-quality audit."
                    ),
                )
            )
            return findings

        for step in report.get("per_step", []) or []:
            step_id_val = step.get("step_id", "")
            for sc in step.get("scripts", []) or []:
                # Workspace-relative path for evidence (audit_script stores
                # whatever Path it received — typically absolute).
                try:
                    rel_path = str(
                        Path(sc["path"]).resolve().relative_to(root.resolve())
                    )
                except (ValueError, OSError):
                    rel_path = sc["path"]
                evidence = [rel_path]
                for b in sc.get("blockers") or []:
                    dim = _smell_dimension(b)
                    findings.append(
                        AuditFinding(
                            id=_finding_uuid(self.name, dim, evidence, b),
                            audit_name=self.name,
                            severity="block",
                            dimension=dim,
                            evidence_paths=evidence,
                            suggested_fix=b,
                        )
                    )
                for w in sc.get("warnings") or []:
                    dim = _smell_dimension(w)
                    findings.append(
                        AuditFinding(
                            id=_finding_uuid(self.name, dim, evidence, w),
                            audit_name=self.name,
                            severity="warn",
                            dimension=dim,
                            evidence_paths=evidence,
                            suggested_fix=w,
                        )
                    )
            # ruff issues — surfaced as a single info finding per step so
            # the report doesn't explode when the linter is verbose.
            ruff = step.get("ruff") or {}
            if ruff.get("ran") and ruff.get("issue_count", 0) > 0:
                detail = f"{step_id_val}:ruff:{ruff['issue_count']}"
                findings.append(
                    AuditFinding(
                        id=_finding_uuid(self.name, "lint",
                                         [f"workspace/{step_id_val}/scripts"],
                                         detail),
                        audit_name=self.name,
                        severity="info",
                        dimension="lint",
                        evidence_paths=[f"workspace/{step_id_val}/scripts"],
                        suggested_fix=(
                            f"ruff reported {ruff['issue_count']} issue(s) "
                            f"in {step_id_val}/scripts; run `ruff check "
                            f"workspace/{step_id_val}/scripts` for the full "
                            "list."
                        ),
                    )
                )
            mypy = step.get("mypy") or {}
            if mypy.get("ran") and mypy.get("error_count", 0) > 0:
                detail = f"{step_id_val}:mypy:{mypy['error_count']}"
                findings.append(
                    AuditFinding(
                        id=_finding_uuid(self.name, "types",
                                         [f"workspace/{step_id_val}/scripts"],
                                         detail),
                        audit_name=self.name,
                        severity="info",
                        dimension="types",
                        evidence_paths=[f"workspace/{step_id_val}/scripts"],
                        suggested_fix=(
                            f"mypy reported {mypy['error_count']} error(s) "
                            f"in {step_id_val}/scripts; type-hints are "
                            "optional for analysis scripts but help with "
                            "refactors."
                        ),
                    )
                )
        return findings


__all__ = [
    "audit_code_quality",
    "audit_script",
    "CodeQualityAudit",
]
