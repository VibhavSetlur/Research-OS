"""Theory + Math pack tools.

Three tools — all best-effort: heavy work (actual Lean / Coq build,
graph rendering) is deferred to the researcher's scripts or to
optional system runtimes if available.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_os.plugins import (
    PackPathError,
    pack_err as _err,
    pack_ok as _ok,
    register_tool,
    resolve_in_root,
)


@register_tool(
    "tool_theory_math_lean_check",
    schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "filepath": {"type": "string", "description": "Alias for file_path (core file tools use 'filepath')."},
            "timeout_seconds": {"type": "integer"},
        },
        "required": ["file_path"],
    },
    description=(
        "Runs `lean --make` on a .lean file and parses the output. "
        "Returns success / failure + structured error messages "
        "(line, column, message). If Lean isn't installed locally, "
        "writes a stub plan to workspace/proof/lean_install_hint.md and "
        "returns a success envelope with lean_available=false + a warning "
        "note so the researcher knows to install Lean 4 + Mathlib first."
    ),
)
def lean_check(name: str, arguments: dict, root: Path) -> Any:
    file_path = (arguments.get("file_path") or arguments.get("filepath") or "").strip()
    timeout = int(arguments.get("timeout_seconds") or 120)
    try:
        target = resolve_in_root(root, file_path)
    except PackPathError as exc:
        return _err(str(exc))
    if not target.exists():
        return _err(f"file_path '{file_path}' not found")
    lean_bin = shutil.which("lean")
    if not lean_bin:
        hint_dir = root / "workspace" / "proof"
        hint_dir.mkdir(parents=True, exist_ok=True)
        hint = hint_dir / "lean_install_hint.md"
        hint.write_text(
            "# Lean 4 not detected\n\n"
            "Install via elan: https://leanprover-community.github.io/get_started.html\n"
            "Then re-run tool_theory_math_lean_check.\n"
        )
        # Soft state: surface as data fields, not a nested status key the
        # dispatcher/clients never read (the outer envelope is success).
        return _ok({
            "lean_available": False,
            "warning": "Lean 4 not installed; wrote install hint.",
            "hint_path": str(hint.relative_to(root)),
        })
    try:
        proc = subprocess.run(
            [lean_bin, "--make", str(target)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _err(f"lean --make timed out after {timeout}s")
    err_pat = re.compile(
        r"^([^:]+):(\d+):(\d+):\s+(error|warning):\s*(.+)$", re.MULTILINE
    )
    errors = [
        {"file": m.group(1), "line": int(m.group(2)),
         "column": int(m.group(3)), "level": m.group(4),
         "message": m.group(5)}
        for m in err_pat.finditer(proc.stderr + "\n" + proc.stdout)
    ]
    return _ok({
        "returncode": proc.returncode,
        "succeeded": proc.returncode == 0,
        "errors": errors,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    })


@register_tool(
    "tool_theory_math_coq_check",
    schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "filepath": {"type": "string", "description": "Alias for file_path (core file tools use 'filepath')."},
            "timeout_seconds": {"type": "integer"},
        },
        "required": ["file_path"],
    },
    description=(
        "Runs `coqc` on a .v file. Same install-detection behaviour "
        "as tool_theory_math_lean_check: writes a hint if Coq is missing, "
        "parses output otherwise. Coq error lines have a different "
        "format from Lean (File \"...\", line N, characters A-B:)."
    ),
)
def coq_check(name: str, arguments: dict, root: Path) -> Any:
    file_path = (arguments.get("file_path") or arguments.get("filepath") or "").strip()
    timeout = int(arguments.get("timeout_seconds") or 120)
    try:
        target = resolve_in_root(root, file_path)
    except PackPathError as exc:
        return _err(str(exc))
    if not target.exists():
        return _err(f"file_path '{file_path}' not found")
    coq_bin = shutil.which("coqc")
    if not coq_bin:
        hint_dir = root / "workspace" / "proof"
        hint_dir.mkdir(parents=True, exist_ok=True)
        hint = hint_dir / "coq_install_hint.md"
        hint.write_text(
            "# Coq not detected\n\n"
            "Install via opam: https://coq.inria.fr/opam-using.html\n"
            "Then re-run tool_theory_math_coq_check.\n"
        )
        return _ok({
            "coq_available": False,
            "warning": "Coq not installed; wrote install hint.",
            "hint_path": str(hint.relative_to(root)),
        })
    try:
        proc = subprocess.run(
            [coq_bin, str(target)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _err(f"coqc timed out after {timeout}s")
    err_pat = re.compile(
        r'^File "([^"]+)", line (\d+), characters (\d+)-(\d+):\s*(.*)$',
        re.MULTILINE,
    )
    errors = [
        {"file": m.group(1), "line": int(m.group(2)),
         "start_char": int(m.group(3)), "end_char": int(m.group(4)),
         "message": m.group(5).strip()}
        for m in err_pat.finditer(proc.stderr + "\n" + proc.stdout)
    ]
    return _ok({
        "returncode": proc.returncode,
        "succeeded": proc.returncode == 0,
        "errors": errors,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    })


_LEAN_THM_PAT = re.compile(
    r"^\s*(?:theorem|lemma|def|example)\s+([A-Za-z_][A-Za-z0-9_.]*)",
    re.MULTILINE,
)
_LEAN_IMPORT_PAT = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)
_COQ_THM_PAT = re.compile(
    r"^\s*(?:Theorem|Lemma|Definition|Fact|Corollary|Proposition)\s+([A-Za-z_][A-Za-z0-9_']*)",
    re.MULTILINE,
)
_COQ_IMPORT_PAT = re.compile(r"^\s*(?:From\s+\S+\s+)?Require(?:\s+Import)?\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)


@register_tool(
    "tool_theory_math_dep_graph",
    schema={
        "type": "object",
        "properties": {
            "source_dir": {
                "type": "string",
                "description": "Directory under root that holds .lean / .v files.",
            },
        },
        "required": ["source_dir"],
    },
    description=(
        "Parses every .lean and .v file under source_dir, extracts the "
        "named theorems / lemmas / definitions + the modules they import, "
        "and writes a mermaid + JSON dependency graph to "
        "workspace/docs/proof_dependencies.mermaid + .json. The graph is "
        "approximate (lexical, not type-checked) but accurate enough to "
        "spot which lemmas a result transitively depends on."
    ),
)
def dep_graph(name: str, arguments: dict, root: Path) -> Any:
    try:
        src_dir = resolve_in_root(root, arguments["source_dir"])
    except PackPathError as exc:
        return _err(str(exc))
    if not src_dir.exists() or not src_dir.is_dir():
        return _err(f"source_dir '{arguments['source_dir']}' not a directory")
    files: list[dict] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".lean", ".v"}:
            continue
        text = path.read_text(errors="ignore")
        if path.suffix == ".lean":
            thms = _LEAN_THM_PAT.findall(text)
            imps = _LEAN_IMPORT_PAT.findall(text)
        else:
            thms = _COQ_THM_PAT.findall(text)
            imps = _COQ_IMPORT_PAT.findall(text)
        files.append({
            "path": str(path.relative_to(root)),
            "theorems": thms,
            "imports": imps,
        })
    docs_dir = root / "workspace" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    json_out = docs_dir / "proof_dependencies.json"
    json_out.write_text(json.dumps({"files": files}, indent=2))

    lines = ["graph TD"]
    for f in files:
        node = f["path"].replace("/", "_").replace(".", "_")
        label = Path(f["path"]).name
        lines.append(f'    {node}["{label}"]')
        for imp in f["imports"]:
            imp_node = imp.replace(".", "_")
            lines.append(f'    {node} --> {imp_node}')
    mermaid_out = docs_dir / "proof_dependencies.mermaid"
    mermaid_out.write_text("\n".join(lines) + "\n")
    return _ok({
        "json_path": str(json_out.relative_to(root)),
        "mermaid_path": str(mermaid_out.relative_to(root)),
        "n_files": len(files),
        "n_theorems": sum(len(f["theorems"]) for f in files),
        "n_imports": sum(len(f["imports"]) for f in files),
    })
