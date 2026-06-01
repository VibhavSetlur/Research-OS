"""Post-scaffold workspace smoke check.

Verifies that a freshly scaffolded Research OS workspace is structurally
sound — required files exist, MCP configs are valid JSON, state ledger
parses, AGENTS.md was dropped. Cheap (<50 ms) and runs as the final step
of ``research-os init`` so the researcher gets immediate confidence the
workspace is ready for an AI IDE.

Returns a list of ``(check_name, ok, detail)`` tuples so the caller
can pretty-print however it wants.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # noqa


REQUIRED_FILES = [
    "AGENTS.md",
    "GETTING_STARTED.md",
    "inputs/researcher_config.yaml",
    "inputs/intake.md",
    "workspace/methods.md",
    "workspace/analysis.md",
    "workspace/citations.md",
    "workspace/workflow.mermaid",
    "workspace/scratch/README.md",
    ".os_state/state_ledger.json",
    ".os_state/manifest.json",
    ".gitignore",
]

# Directories that MUST exist after `research-os init`. Lazy dirs
# (inputs/{raw_data,literature,context}, synthesis/, environment/) are
# deliberately omitted — they materialise on first write so a fresh
# project surface stays uncluttered.
REQUIRED_DIRS = [
    "inputs",
    "workspace",
    "workspace/logs",
    "workspace/scratch",
    "docs",
    ".os_state",
]


def _file_exists(root: Path, rel: str) -> tuple[bool, str]:
    p = root / rel
    if not p.exists():
        return False, f"missing: {rel}"
    if p.stat().st_size == 0 and not rel.endswith(".gitkeep"):
        return False, f"empty: {rel}"
    return True, ""


def _dir_exists(root: Path, rel: str) -> tuple[bool, str]:
    p = root / rel
    if not p.is_dir():
        return False, f"missing dir: {rel}"
    return True, ""


def _json_parses(path: Path) -> tuple[bool, str]:
    try:
        json.loads(path.read_text())
        return True, ""
    except Exception as e:
        return False, f"{path.name} invalid JSON: {e}"


def _yaml_parses(path: Path) -> tuple[bool, str]:
    if yaml is None:
        return True, "yaml not installed — skipped"
    try:
        yaml.safe_load(path.read_text())
        return True, ""
    except Exception as e:
        return False, f"{path.name} invalid YAML: {e}"


def verify_workspace(root: Path, ides: list[str] | None = None) -> list[tuple[str, bool, str]]:
    """Run the full check suite. Returns one row per check."""
    ides = ides or []
    results: list[tuple[str, bool, str]] = []

    # 1. Required files
    missing = []
    empty = []
    for rel in REQUIRED_FILES:
        ok, detail = _file_exists(root, rel)
        if not ok:
            (empty if "empty" in detail else missing).append(rel)
    if missing or empty:
        problems = []
        if missing:
            problems.append(f"missing {len(missing)}: {missing[:3]}")
        if empty:
            problems.append(f"empty {len(empty)}: {empty[:3]}")
        results.append(("Required files present", False, "; ".join(problems)))
    else:
        results.append(("Required files present", True, f"{len(REQUIRED_FILES)} files"))

    # 2. Required directories
    bad_dirs = [d for d in REQUIRED_DIRS if not (root / d).is_dir()]
    results.append((
        "Required directories",
        not bad_dirs,
        f"{len(REQUIRED_DIRS)} dirs" if not bad_dirs else f"missing: {bad_dirs}",
    ))

    # 3. State ledger parses
    state_path = root / ".os_state" / "state_ledger.json"
    if state_path.exists():
        ok, detail = _json_parses(state_path)
        results.append(("State ledger is valid JSON", ok, detail or "ok"))
    else:
        results.append(("State ledger is valid JSON", False, "state_ledger.json missing"))

    # 4. Manifest parses
    manifest_path = root / ".os_state" / "manifest.json"
    if manifest_path.exists():
        ok, detail = _json_parses(manifest_path)
        results.append(("Manifest is valid JSON", ok, detail or "ok"))
    else:
        results.append(("Manifest is valid JSON", False, "manifest.json missing"))

    # 5. researcher_config.yaml parses
    cfg = root / "inputs" / "researcher_config.yaml"
    if cfg.exists():
        ok, detail = _yaml_parses(cfg)
        results.append(("researcher_config.yaml is valid YAML", ok, detail or "ok"))
    else:
        results.append(("researcher_config.yaml is valid YAML", False, "config missing"))

    # 6. MCP configs (JSON) — one row per IDE the user picked
    mcp_targets = {
        "cursor":      ".cursor/mcp.json",
        "claude":      ".claude/mcp.json",
        "antigravity": ".antigravity/mcp.json",
        "vscode":      ".vscode/mcp.json",
        "opencode":    "opencode.json",
    }
    for ide in ides:
        rel = mcp_targets.get(ide)
        if not rel:
            continue
        p = root / rel
        if not p.exists():
            results.append((f"MCP config: {ide}", False, f"missing: {rel}"))
            continue
        ok, detail = _json_parses(p)
        results.append((f"MCP config: {ide}", ok, detail or "ok"))

    return results


def summarize(results: list[tuple[str, bool, str]]) -> tuple[int, int, str]:
    """Returns (passed, failed, one-line summary)."""
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    summary = f"{passed}/{len(results)} checks passed"
    if failed:
        summary += f" — {failed} failed"
    return passed, failed, summary
