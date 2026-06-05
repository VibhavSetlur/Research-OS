"""Snakemake workflow adapter.

Detects:
    * `Snakefile` (canonical entry point) in workspace/<step>/, workspace/<step>/scripts/, or project root
    * `*.smk` files (modular Snakemake includes) anywhere under workspace/ or root

Extracts per-rule: name, inputs, outputs, shell command preview (first 200 chars),
conda env file, container directive, threads count, resources block. Renders a
best-effort Mermaid DAG from rule input/output edges so reviewers can see workflow
topology without launching Snakemake.

When the `snakemake` Python package is importable, its public Python API is used
for richer parsing (resolves wildcards, expand() calls, include directives,
config dependencies). When absent, falls back to a regex parser that handles
the common `rule NAME: input: ... output: ... shell: ...` block layout but
silently skips Jinja-style expressions and module imports.

Optional tools:
    * tool_snakemake_dryrun(snakefile)     — runs `snakemake --dry-run -s <path>`
    * tool_snakemake_dag_render(snakefile) — runs `snakemake --dag | dot -Tpng`,
                                             falls back to the regex Mermaid DAG

Limitations:
    * Regex fallback does not resolve `include:` directives across files; each
      *.smk is parsed independently.
    * `expand(...)` wildcard expansion is preserved as a string token, not
      flattened.
    * Modules (`module X: snakefile=...`) are detected but not recursively
      walked.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_os.adapters import (
    AdapterRegistration,
    AdapterTool,
    register_adapter,
)


__version__ = "1.8.0"


# ── detection ─────────────────────────────────────────────────────────


_RULE_RE = re.compile(r"^\s*rule\s+(\w+)\s*:", re.MULTILINE)


def _candidate_snakefiles(root: Path) -> list[Path]:
    """Locate Snakefile + *.smk files in workspace/, workspace/<step>/scripts/, and root."""
    files: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path) -> None:
        try:
            rp = p.resolve()
        except Exception:
            return
        if rp in seen or not p.is_file():
            return
        seen.add(rp)
        files.append(p)

    # Root-level Snakefile / .smk
    for name in ("Snakefile", "snakefile"):
        candidate = root / name
        if candidate.exists():
            _add(candidate)
    for p in root.glob("*.smk"):
        _add(p)

    # workspace/ tree (any depth)
    workspace = root / "workspace"
    if workspace.exists():
        for p in workspace.rglob("Snakefile"):
            _add(p)
        for p in workspace.rglob("snakefile"):
            _add(p)
        for p in workspace.rglob("*.smk"):
            _add(p)

    return files


def detect(root: Path) -> bool:
    for path in _candidate_snakefiles(root):
        try:
            head = path.read_text(errors="ignore")[:8192]
        except Exception:
            continue
        # Either the filename matched and we trust it, or we sniff a rule directive.
        if path.name in {"Snakefile", "snakefile"} or path.suffix.lower() == ".smk":
            return True
        if _RULE_RE.search(head):
            return True
    return False


# ── extraction ────────────────────────────────────────────────────────


_RULE_BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)rule\s+(?P<name>\w+)\s*:\s*\n"
    r"(?P<body>(?:(?:[ \t]+[^\n]*|\s*)\n)+)",
    re.MULTILINE,
)
_DIRECTIVE_RE = re.compile(
    r"^[ \t]+(?P<key>input|output|shell|conda|container|threads|resources|params|log|benchmark|wildcard_constraints|priority|message|wrapper|script|run|notebook|envmodules):"
    r"(?P<rest>.*?)(?=^[ \t]+\w+:|^\S|\Z)",
    re.MULTILINE | re.DOTALL,
)
_QUOTED_RE = re.compile(r"""['"]([^'"]+)['"]""")
_INT_RE = re.compile(r"\b(\d+)\b")
_INCLUDE_RE = re.compile(r"""^\s*include:\s*['"]([^'"]+)['"]""", re.MULTILINE)
_MODULE_RE = re.compile(r"""^\s*module\s+(\w+)\s*:""", re.MULTILINE)


def _clean(text: str) -> str:
    return text.strip().strip(",").strip()


def _parse_string_list(rest: str) -> list[str]:
    """Pull quoted strings out of an `input:` / `output:` block body."""
    items = [m.group(1) for m in _QUOTED_RE.finditer(rest)]
    # Preserve expand(...) blobs as raw tokens when no quotes were captured.
    if not items:
        cleaned = _clean(rest)
        if cleaned:
            items = [cleaned[:200]]
    return items


def _parse_resources(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in rest.splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = _clean(v)
    return out


def _parse_threads(rest: str) -> int | None:
    m = _INT_RE.search(rest)
    return int(m.group(1)) if m else None


def _parse_shell(rest: str) -> str:
    # Snakemake shell commands are quoted; preserve the first quoted block,
    # otherwise truncate the raw body.
    m = re.search(r"""(?:r?["']{3}|["'])(.+?)(?:["']{3}|["'])""", rest, re.DOTALL)
    snippet = m.group(1) if m else _clean(rest)
    snippet = snippet.replace("\n", " ").strip()
    return snippet[:200]


def _parse_rule_body(body: str) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "inputs": [],
        "outputs": [],
        "shell_preview": None,
        "conda": None,
        "container": None,
        "threads": None,
        "resources": {},
        "params": [],
        "log": [],
        "benchmark": None,
        "wrapper": None,
        "script": None,
    }
    for m in _DIRECTIVE_RE.finditer(body):
        key = m.group("key")
        rest = m.group("rest") or ""
        try:
            if key == "input":
                rule["inputs"] = _parse_string_list(rest)
            elif key == "output":
                rule["outputs"] = _parse_string_list(rest)
            elif key == "shell":
                rule["shell_preview"] = _parse_shell(rest)
            elif key == "conda":
                quoted = _QUOTED_RE.search(rest)
                rule["conda"] = quoted.group(1) if quoted else _clean(rest)[:200]
            elif key == "container":
                quoted = _QUOTED_RE.search(rest)
                rule["container"] = quoted.group(1) if quoted else _clean(rest)[:200]
            elif key == "threads":
                rule["threads"] = _parse_threads(rest)
            elif key == "resources":
                rule["resources"] = _parse_resources(rest)
            elif key == "params":
                rule["params"] = _parse_string_list(rest)
            elif key == "log":
                rule["log"] = _parse_string_list(rest)
            elif key == "benchmark":
                quoted = _QUOTED_RE.search(rest)
                rule["benchmark"] = quoted.group(1) if quoted else None
            elif key == "wrapper":
                quoted = _QUOTED_RE.search(rest)
                rule["wrapper"] = quoted.group(1) if quoted else None
            elif key == "script":
                quoted = _QUOTED_RE.search(rest)
                rule["script"] = quoted.group(1) if quoted else None
        except Exception:
            # Lenient: one busted directive doesn't kill the whole rule.
            continue
    return rule


def _parse_snakefile_regex(path: Path) -> tuple[list[dict], list[str], list[str]]:
    """Return (rules, includes, modules) from a Snakefile via regex."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return [], [], []
    rules: list[dict] = []
    for m in _RULE_BLOCK_RE.finditer(text):
        name = m.group("name")
        body = m.group("body")
        parsed = _parse_rule_body(body)
        parsed["name"] = name
        rules.append(parsed)
    includes = [m.group(1) for m in _INCLUDE_RE.finditer(text)]
    modules = [m.group(1) for m in _MODULE_RE.finditer(text)]
    return rules, includes, modules


def _parse_snakefile_api(path: Path) -> tuple[list[dict], list[str], list[str]] | None:
    """Use the Snakemake Python API for richer parsing when available.

    Returns None if snakemake isn't installed or the API path fails (signals
    the caller to fall back to regex parsing).
    """
    try:
        from snakemake.workflow import Workflow  # type: ignore
    except Exception:
        return None
    try:
        wf = Workflow(snakefile=str(path), overwrite_configfiles=[])
        wf.include(str(path), overwrite_default_target=True)
        rules: list[dict] = []
        for r in wf.rules:
            try:
                shell_preview = None
                if getattr(r, "shellcmd", None):
                    shell_preview = str(r.shellcmd).replace("\n", " ").strip()[:200]
                rules.append({
                    "name": r.name,
                    "inputs": [str(x) for x in getattr(r, "input", [])],
                    "outputs": [str(x) for x in getattr(r, "output", [])],
                    "shell_preview": shell_preview,
                    "conda": str(getattr(r, "conda_env", None)) if getattr(r, "conda_env", None) else None,
                    "container": getattr(r, "container_img", None),
                    "threads": getattr(r, "resources", {}).get("_cores") if hasattr(r, "resources") else None,
                    "resources": {k: v for k, v in (getattr(r, "resources", {}) or {}).items() if not k.startswith("_")},
                    "params": [str(x) for x in getattr(r, "params", [])],
                    "log": [str(x) for x in getattr(r, "log", [])],
                    "benchmark": str(getattr(r, "benchmark", None)) if getattr(r, "benchmark", None) else None,
                    "wrapper": getattr(r, "wrapper", None),
                    "script": getattr(r, "script", None),
                })
            except Exception:
                continue
        includes = [str(p) for p in getattr(wf, "included", [])]
        return rules, includes, []
    except Exception:
        return None


def _render_mermaid_dag(rules: list[dict]) -> str:
    """Best-effort DAG: each rule is a node, edges go output→consumer-input."""
    if not rules:
        return "graph TD\n  empty[No rules detected]"
    producers: dict[str, str] = {}
    for r in rules:
        for out in r.get("outputs", []) or []:
            producers[out] = r["name"]
    lines = ["graph TD"]
    for r in rules:
        lines.append(f'  {r["name"]}["{r["name"]}"]')
    edges_seen: set[tuple[str, str]] = set()
    for r in rules:
        consumer = r["name"]
        for inp in r.get("inputs", []) or []:
            src = producers.get(inp)
            if src and src != consumer and (src, consumer) not in edges_seen:
                edges_seen.add((src, consumer))
                lines.append(f"  {src} --> {consumer}")
    return "\n".join(lines)


def _write_dag(root: Path, step_id: str | None, mermaid: str) -> str | None:
    """Write the Mermaid DAG under workspace/<step>/snakemake_dag.mmd."""
    if step_id:
        target_dir = root / "workspace" / step_id
    else:
        target_dir = root / "workspace"
    if not target_dir.exists():
        return None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dag_path = target_dir / "snakemake_dag.mmd"
        dag_path.write_text(mermaid)
        return str(dag_path.relative_to(root))
    except Exception:
        return None


def extract(root: Path, step_id: str | None = None) -> dict:
    snakefiles = _candidate_snakefiles(root)
    if step_id:
        step_prefix = (root / "workspace" / step_id).resolve()
        snakefiles = [
            s for s in snakefiles
            if str(s.resolve()).startswith(str(step_prefix))
        ]
    if not snakefiles:
        return {
            "files_scanned": 0,
            "rules": [],
            "snakefile_path": None,
            "dag_path": None,
            "_notes": [
                "No Snakefile or *.smk files found within scope.",
            ],
        }

    all_rules: list[dict] = []
    all_includes: list[str] = []
    all_modules: list[str] = []
    parser_used = "regex"
    primary_snakefile: Path | None = None
    notes: list[str] = []

    for path in snakefiles:
        api_result = _parse_snakefile_api(path)
        if api_result is not None:
            rules, includes, modules = api_result
            parser_used = "snakemake_api"
        else:
            rules, includes, modules = _parse_snakefile_regex(path)
        for r in rules:
            r["_source"] = str(path.relative_to(root))
            all_rules.append(r)
        all_includes.extend(includes)
        all_modules.extend(modules)
        if primary_snakefile is None and path.name in {"Snakefile", "snakefile"}:
            primary_snakefile = path
    if primary_snakefile is None and snakefiles:
        primary_snakefile = snakefiles[0]

    if parser_used == "regex":
        notes.append(
            "snakemake Python API unavailable; rules parsed via regex (include: "
            "directives and expand() wildcards may be incomplete)."
        )
    if all_modules:
        notes.append(
            f"Detected {len(all_modules)} module(s) ({', '.join(all_modules[:5])}); "
            "module bodies are not recursively walked."
        )

    mermaid = _render_mermaid_dag(all_rules)
    dag_rel = _write_dag(root, step_id, mermaid)

    return {
        "files_scanned": len(snakefiles),
        "parser": parser_used,
        "snakefile_path": str(primary_snakefile.relative_to(root)) if primary_snakefile else None,
        "rules": all_rules,
        "includes": all_includes,
        "modules": all_modules,
        "dag_path": dag_rel,
        "dag_mermaid": mermaid,
        "_notes": notes,
    }


def describe() -> dict:
    return {
        "name": "snakemake",
        "version": __version__,
        "parsers": ["snakemake_api", "regex"],
        "outputs": ["rules", "mermaid_dag"],
    }


# ── optional tools ────────────────────────────────────────────────────


def _ok(data: dict) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "success", "data": data}, indent=2, default=str
        ))]


def _err(message: str) -> list:
    try:
        from mcp.types import TextContent
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]
    except ImportError:  # pragma: no cover
        class _Stub:
            def __init__(self, text): self.type, self.text = "text", text
        return [_Stub(json.dumps(
            {"status": "error", "error": message}, indent=2, default=str
        ))]


def _resolve_snakefile(root: Path, arguments: dict) -> Path | None:
    explicit = arguments.get("snakefile")
    if explicit:
        candidate = (root / explicit).resolve() if not Path(explicit).is_absolute() else Path(explicit)
        if candidate.exists():
            return candidate
        return None
    candidates = _candidate_snakefiles(root)
    for c in candidates:
        if c.name in {"Snakefile", "snakefile"}:
            return c
    return candidates[0] if candidates else None


def _handle_snakemake_dryrun(name: str, arguments: dict, root: Path) -> Any:
    try:
        import snakemake  # type: ignore  # noqa: F401
        has_snakemake = True
    except Exception:
        has_snakemake = False

    snakefile = _resolve_snakefile(root, arguments)
    if snakefile is None:
        return _err("No Snakefile or *.smk file found; pass `snakefile` explicitly.")

    binary = shutil.which("snakemake")
    if not (has_snakemake or binary):
        return _ok({
            "status": "warning",
            "message": "snakemake not installed; install via `pip install snakemake` or `conda install -c bioconda snakemake` to enable dry-run.",
            "snakefile": str(snakefile.relative_to(root)) if snakefile.is_relative_to(root) else str(snakefile),
        })

    cmd = [binary or "snakemake", "--dry-run", "-s", str(snakefile)]
    cores = arguments.get("cores")
    if cores:
        cmd.extend(["--cores", str(cores)])
    else:
        cmd.extend(["--cores", "1"])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(root))
    except subprocess.TimeoutExpired:
        return _err("snakemake --dry-run timed out after 60s")
    except FileNotFoundError:
        return _ok({
            "status": "warning",
            "message": "snakemake binary not on PATH despite import succeeding; check your environment.",
        })
    return _ok({
        "snakefile": str(snakefile.relative_to(root)) if snakefile.is_relative_to(root) else str(snakefile),
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    })


def _handle_snakemake_dag_render(name: str, arguments: dict, root: Path) -> Any:
    snakefile = _resolve_snakefile(root, arguments)
    if snakefile is None:
        return _err("No Snakefile or *.smk file found; pass `snakefile` explicitly.")

    snakemake_bin = shutil.which("snakemake")
    dot_bin = shutil.which("dot")
    step_id = arguments.get("step_id")

    if snakemake_bin and dot_bin:
        # Real render: snakemake --dag | dot -Tpng → workspace/<step>/snakemake_dag.png
        if step_id:
            target_dir = root / "workspace" / step_id
        else:
            target_dir = root / "workspace"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            target_dir = root
        png_path = target_dir / "snakemake_dag.png"
        try:
            dag_proc = subprocess.run(
                [snakemake_bin, "--dag", "-s", str(snakefile)],
                capture_output=True, text=True, timeout=60, cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return _err("snakemake --dag timed out after 60s")
        if dag_proc.returncode != 0:
            return _err(
                f"snakemake --dag failed (rc={dag_proc.returncode}): "
                f"{dag_proc.stderr[-500:]}"
            )
        try:
            dot_proc = subprocess.run(
                [dot_bin, "-Tpng", "-o", str(png_path)],
                input=dag_proc.stdout, capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return _err("dot -Tpng timed out after 30s")
        if dot_proc.returncode != 0:
            return _err(
                f"dot -Tpng failed (rc={dot_proc.returncode}): "
                f"{dot_proc.stderr[-500:]}"
            )
        return _ok({
            "renderer": "graphviz",
            "snakefile": str(snakefile.relative_to(root)) if snakefile.is_relative_to(root) else str(snakefile),
            "dag_path": str(png_path.relative_to(root)) if png_path.is_relative_to(root) else str(png_path),
        })

    # Fallback: regenerate the regex-derived Mermaid DAG.
    payload = extract(root, step_id=step_id)
    missing = []
    if not snakemake_bin:
        missing.append("snakemake")
    if not dot_bin:
        missing.append("graphviz `dot`")
    return _ok({
        "status": "warning",
        "renderer": "mermaid_fallback",
        "message": (
            f"{' and '.join(missing)} not installed; returning regex-derived "
            "Mermaid DAG instead of rendered PNG."
        ),
        "snakefile": payload.get("snakefile_path"),
        "dag_path": payload.get("dag_path"),
        "dag_mermaid": payload.get("dag_mermaid"),
    })


# ── adapter registration ──────────────────────────────────────────────


_TOOLS_MD_PATTERNS = (
    (r"rule\s+(\w+):", "Snakemake rule: {0}"),
    (r"^\s*conda:\s+[\"']?([^\"'\n]+)", "Snakemake conda env: {0}"),
    (r"^\s*container:\s+[\"']?([^\"'\n]+)", "Snakemake container: {0}"),
)


def register() -> AdapterRegistration:
    return register_adapter(
        name="snakemake",
        version=__version__,
        description="Snakemake workflow provenance extractor (rules, I/O, conda, container, threads) + Mermaid DAG.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=_TOOLS_MD_PATTERNS,
        tools=(
            AdapterTool(
                name="tool_snakemake_dryrun",
                handler=_handle_snakemake_dryrun,
                schema={
                    "type": "object",
                    "properties": {
                        "snakefile": {"type": "string"},
                        "cores": {"type": "integer"},
                    },
                    "description": "Run `snakemake --dry-run -s <snakefile>` (defaults to auto-detected Snakefile) and return stdout/stderr tails. Returns status=warning with install hint if snakemake is not installed. Uses --cores 1 unless `cores` is supplied.",
                },
            ),
            AdapterTool(
                name="tool_snakemake_dag_render",
                handler=_handle_snakemake_dag_render,
                schema={
                    "type": "object",
                    "properties": {
                        "snakefile": {"type": "string"},
                        "step_id": {"type": "string"},
                    },
                    "description": "Render the workflow DAG to PNG via `snakemake --dag | dot -Tpng` when both snakemake and graphviz are on PATH. Falls back to the regex-derived Mermaid DAG (written by extract()) when either is missing.",
                },
            ),
        ),
    )
