"""Workspace scaffolding, state I/O, and shared filesystem helpers.

Conventions
-----------
* Single state file: ``.os_state/state_ledger.json`` (mirrored to
  ``.os_state/state_ledger.yaml`` for human reading).
* Append-only logs: ``workspace/methods.md``, ``analysis.md``, ``citations.md``.
* Immutable: ``inputs/raw_data/``, ``inputs/literature/``.
* All workspace writes go through MCP tools so provenance is captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - yaml is a hard dep
    yaml = None

from research_os.errors import check_write_permitted
from research_os.state.state_ledger import ResearchLedger
from research_os.utils.common import find_project_root, now_iso

EXPERIMENT_SUBDIRS = (
    "data/input",
    "data/output",
    "scripts",
    "literature",        # per-step PDFs; populated by tool_literature_download(step_id=…)
    "context",           # per-step prose notes, methodology rationale, hand-overs
    "outputs/reports",
    "outputs/figures",
    "outputs/tables",
    "environment",
)
# NOTE: no `outputs/dashboards` here on purpose. Dashboards are a *project-level*
# synthesis output (synthesis/dashboard.html), not a per-step artifact.
#
# `context/` is the step's "if a new analyst opened this folder today, what
# narrative would let them act?" — methodology rationale, drafts, screen-grab
# notes from upstream meetings. Distinct from `literature/` (formal sources)
# and `data/` (machine-readable). `finalize_path` rewrites its README to
# summarise whatever was deposited so the dashboard's per-step appendix can
# surface it.

TOP_LEVEL_DIRS = (
    ".os_state",
    "docs",
    "inputs",
    "inputs/raw_data",
    "inputs/literature",
    "inputs/context",
    "workspace",
    "workspace/logs",
    "workspace/scratch",
    "synthesis",
    "environment",
)

# Directories created EAGERLY (always populated, never empty after init).
# inputs/{raw_data,literature,context} are eager from v1.3.0 — GETTING_STARTED
# tells the researcher to drop files there, and the dirs must exist for that
# `cp` to work without `mkdir -p` friction. Each is seeded with a tiny README
# explaining what belongs there so an empty folder isn't a dead end.
EAGER_DIRS = (
    ".os_state",
    "docs",
    "inputs",
    "inputs/raw_data",
    "inputs/literature",
    "inputs/context",
    "workspace",
    "workspace/logs",
    "workspace/scratch",
    "environment",
)

# Directories created LAZILY (only when the first artefact lands in them).
# Tools that write into them MUST call ``ensure_lazy_dir`` first.
LAZY_DIRS = (
    "synthesis",
)


def _has_user_inputs(root: Path) -> bool:
    """True iff the researcher has dropped real files into inputs/.

    Skips scaffold-seeded ``README.md`` files in each input subfolder
    (added in v1.3.0 round-3 so an empty folder isn't a dead end) —
    those don't count as user content.
    """
    for sub in ("raw_data", "literature", "context"):
        d = root / "inputs" / sub
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if p.name.startswith(".") or p.name == ".gitkeep":
                continue
            if p.name == "README.md" and p.parent.name in {
                "raw_data", "literature", "context"
            }:
                continue
            return True
    return False


def ensure_lazy_dir(root: Path, rel: str) -> Path:
    """Create a lazy workspace directory at first write; idempotent.

    Tools call this before dropping the first artefact into a LAZY_DIRS
    path so the project surface stays minimal until real content arrives.
    Passing a path that is not in ``LAZY_DIRS`` raises so writers can't
    silently grow the lazy surface without updating the registry.
    """
    if rel not in LAZY_DIRS:
        raise ValueError(
            f"ensure_lazy_dir('{rel}') is not a registered lazy directory. "
            f"Allowed: {', '.join(LAZY_DIRS)}. Use Path.mkdir for ad-hoc dirs."
        )
    target = root / rel
    target.mkdir(parents=True, exist_ok=True)
    return target


def log_override(
    root: Path,
    *,
    tool: str,
    gate: str,
    rationale: str | None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append a researcher-authorised gate bypass to the override log.

    Every time the AI calls a tool with ``override_completeness_gate=true``
    (or ``override_gate=true`` on ``tool_plan_advance``), we record:

    * which tool was bypassed
    * which gate it was
    * the rationale the researcher supplied (or ``<none provided>`` —
      this surfaces in audits as a soft warning)
    * a UTC timestamp

    The log lives at ``workspace/logs/override_log.md`` so the
    pre-submission audit can list every bypass and ask the researcher
    to confirm before publication.
    """
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / "override_log.md"
    if not log.exists():
        log.write_text(
            "# Quality-gate bypass log\n\n"
            "Every entry here represents a moment the researcher "
            "explicitly authorised the AI to bypass a quality gate. "
            "The pre-submission audit surfaces this list — confirm "
            "each bypass was intentional before submission.\n\n"
        )
    note = (rationale or "").strip() or "<no rationale provided — flag in audit>"
    extras = ""
    if extra:
        try:
            extras = " · " + json.dumps(extra, sort_keys=True, default=str)
        except Exception:
            extras = ""
    with log.open("a") as fh:
        fh.write(f"- {now_iso()} · `{tool}` · gate={gate} · {note}{extras}\n")
    return log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    r = find_project_root()
    if not r:
        raise ValueError("Could not find project root containing .os_state/")
    return r


def slugify(value: str, fallback: str = "path") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def state_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.yaml"


def state_json_path(root: Path) -> Path:
    return root / ".os_state" / "state_ledger.json"


def manifest_path(root: Path) -> Path:
    return root / ".os_state" / "manifest.json"


# ---------------------------------------------------------------------------
# Atomic JSON / YAML I/O
# ---------------------------------------------------------------------------


def read_yaml(path: Path) -> dict | None:
    if not yaml:
        raise RuntimeError("PyYAML is required (pip install pyyaml).")
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return None


def write_yaml(path: Path, data: dict) -> None:
    if not yaml:
        raise RuntimeError("PyYAML is required (pip install pyyaml).")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def compute_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return "error"


# ---------------------------------------------------------------------------
# State (single source of truth — ResearchLedger)
# ---------------------------------------------------------------------------


def default_state() -> dict:
    """Canonical default state — delegates to ResearchLedger's canonical schema.

    Kept as a thin wrapper for callers that import ``default_state`` directly.
    """
    return ResearchLedger._default_state()


def load_state(root: Path | None = None) -> dict:
    root = _resolve_root(root)
    ledger = ResearchLedger(state_json_path(root))
    state = ledger._load()
    if not state or "paths" not in state:
        state = default_state()
        ledger._save(state)
    return state


def save_state(root: Path, state: dict) -> dict:
    """Persist state via ResearchLedger. Migration runs on ``_load``, so any
    legacy keys that re-appear here from callers are normalised on read."""
    root = _resolve_root(root)
    ledger = ResearchLedger(state_json_path(root))
    state["updated_at"] = now_iso()
    # If callers handed us a legacy-shaped dict, normalise before saving so
    # the on-disk view stays canonical from this point forward.
    ResearchLedger._migrate(state)
    ledger._save(state)
    _write_os_state_summary(root)
    return state


def _write_os_state_summary(root: Path) -> None:
    """Render the canonical project status — a researcher- AND AI-readable
    snapshot of what's going on.

    v1.3.0: This file used to be ``.os_state/os_state.md`` (buried). It
    is now ``STATE.md`` at the PROJECT ROOT so a fresh AI session can
    find it without inside knowledge, and so a collaborator opening
    the project sees the status immediately. The contents are richer:
    not just "which paths exist" but the active research question,
    the open hypotheses with status, the most-recent step finalized,
    the next pipeline-recommended protocol, and the key files. A
    plain-English "where to go from here" footer points new sessions
    at AGENTS.md + sys_boot.

    Old ``.os_state/os_state.md`` is removed by the caller (save_state)
    on first save after upgrade so the working tree doesn't end up
    with two copies.
    """
    try:
        state = load_state(root)
    except Exception:
        return

    try:
        from research_os.tools.actions.state.path import list_paths

        paths = list_paths(root).get("paths", []) or []
    except Exception:
        paths = []

    name = state.get("project_name") or "Research Project"
    stage = state.get("pipeline_stage", "init")
    current = state.get("current_path", "main")
    question = (state.get("research_question") or "").strip()
    domain = (state.get("domain") or "").strip()
    hyps = state.get("active_hypotheses") or []

    # Last protocol log entry (so a fresh chat knows what happened most
    # recently without digging through workspace/analysis.md).
    last_protocol = None
    try:
        log = root / ".os_state" / "protocol_execution_log.jsonl"
        if log.exists():
            for line in reversed(log.read_text().splitlines()):
                if line.strip():
                    last_protocol = json.loads(line)
                    break
    except Exception:
        last_protocol = None

    lines = [
        f"# {name}",
        "",
        "*The canonical status file. A new AI session reads this first.*",
        f"*Last updated: {now_iso()}.*",
        "",
        "## What this project is",
        "",
        f"- **Research question:** {question or '_(not yet set — run `tool_intake_autofill` or set in `inputs/researcher_config.yaml`)_'}",
        f"- **Domain:** {domain or '_(unset)_'}",
        f"- **Pipeline phase:** `{stage}`",
        f"- **Active path:** `{current}`",
        "",
        "## Open hypotheses",
        "",
    ]
    if not hyps:
        lines.append("_(none registered yet)_")
    else:
        lines.append("| ID | Status | Statement |")
        lines.append("|---|---|---|")
        for h in hyps:
            hid = h.get("id", "?")
            status = h.get("status", "testing")
            stmt = (h.get("statement") or "")[:140]
            lines.append(f"| {hid} | {status} | {stmt} |")

    lines.extend([
        "",
        "## Analysis steps",
        "",
    ])
    if not paths:
        lines.append("_(no numbered steps yet)_")
    else:
        for p in paths:
            icon = {
                "completed": "✓",
                "active": "→",
                "dead_end": "✗",
            }.get(p.get("status", "active"), "•")
            pid = p.get("path_id", "?")
            hyp = (p.get("hypothesis") or "").strip()[:80]
            extra = f" — {hyp}" if hyp else ""
            lines.append(f"- {icon} `{pid}`{extra}")

    if last_protocol:
        lines.extend([
            "",
            "## Most recent action",
            "",
            f"- Protocol `{last_protocol.get('protocol', '?')}`"
            f" ({last_protocol.get('status', '?')}) at "
            f"{last_protocol.get('timestamp', '?')}",
        ])

    lines.extend([
        "",
        "## Key files (✓ exists / ⚪ not yet)",
        "",
    ])
    for f, label in [
        ("inputs/intake.md", "intake summary"),
        ("inputs/researcher_config.yaml", "config + autonomy"),
        ("docs/research_overview.md", "research question + overview"),
        ("workspace/analysis.md", "narrative log of every step"),
        ("workspace/methods.md", "methods log (assembles into paper)"),
        ("workspace/citations.md", "auto bibliography"),
        ("environment/requirements.txt", "reproducibility env"),
        ("synthesis/paper.md", "draft paper"),
    ]:
        exists = (root / f).exists()
        lines.append(f"- {'✓' if exists else '⚪'} `{f}` — {label}")

    lines.extend([
        "",
        "## How to resume in a fresh chat",
        "",
        "1. Read `AGENTS.md` at project root (the AI's operating rules).",
        "2. Read THIS file (status + open hypotheses + what was last done).",
        "3. On your first turn, call `sys_boot` for the live state +"
        " active plan + pause classification.",
        "4. Then `tool_route(prompt=<the researcher's message>)`.",
    ])

    # Write the canonical version at project root.
    state_md = root / "STATE.md"
    state_md.write_text("\n".join(lines) + "\n")

    # Migration: remove the old buried copy if it exists from a prior
    # version. Best-effort — never raise.
    old = root / ".os_state" / "os_state.md"
    if old.exists():
        try:
            old.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Manifest (workspace tree snapshot)
# ---------------------------------------------------------------------------


def _update_manifest(root: Path) -> None:
    """Sync ``.os_state/manifest.json`` with the current workspace tree."""
    workspace = root / "workspace"
    paths_info: dict[str, Any] = {}
    if workspace.exists():
        for p in sorted(workspace.iterdir()):
            if p.is_dir() and re.match(r"^\d{2,3}_", p.name):
                scripts: list[str] = []
                scripts_dir = p / "scripts"
                if scripts_dir.exists():
                    scripts = [f.name for f in sorted(scripts_dir.iterdir()) if f.is_file()]
                paths_info[p.name] = {
                    "status": "dead_end" if "__DEAD_END" in p.name else "active",
                    "has_readme": (p / "README.md").exists(),
                    "has_conclusions": (p / "conclusions.md").exists(),
                    "scripts": scripts,
                }
    manifest = read_json(manifest_path(root), {})
    manifest["paths"] = paths_info
    manifest["updated_at"] = now_iso()
    write_json(manifest_path(root), manifest)


# ---------------------------------------------------------------------------
# Hashing of input files
# ---------------------------------------------------------------------------


def compute_input_hashes(root: Path | None = None) -> dict[str, str]:
    root = _resolve_root(root)
    hashes: dict[str, str] = {}
    for base in (root / "inputs" / "raw_data", root / "inputs" / "literature", root / "inputs" / "context"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and not path.name.startswith(".")
                and path.name not in {"README.md", ".gitkeep"}
            ):
                hashes[path.relative_to(root).as_posix()] = compute_file_hash(path)
    return hashes


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def write_readme(path: Path, title: str, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {title}\n\n{body.strip()}\n")


def scaffold_minimal_workspace(
    root: Path,
    project_name: str,
    config_overrides: dict | None = None,
    git_init: bool = False,
    ide_flags: list[str] | None = None,
    copy_agents: bool = True,
) -> None:
    """Create the workspace directory tree.

    Philosophy: scaffold creates ONLY the directories + the bare minimum files
    the AI / researcher need before the first session boot. We do NOT
    pre-create synthesis outputs (paper.md, abstract.md), per-experiment
    folders, or pre-filled docs. Those get written by the protocols that own
    them, when (and only when) they're needed.
    """
    config_overrides = config_overrides or {}
    ide_flags = ide_flags or list(("cursor", "claude", "antigravity", "opencode", "vscode"))
    root.mkdir(parents=True, exist_ok=True)

    # 1. Eager skeleton — only the directories that are GUARANTEED to be
    #    populated by the rest of this scaffold. Lazy dirs (synthesis/,
    #    environment/, inputs/raw_data/, inputs/literature/, inputs/context/)
    #    are deferred to first-write via ``ensure_lazy_dir`` so a fresh
    #    project surface has no orphan .gitkeep folders.
    for rel in EAGER_DIRS:
        d = root / rel
        d.mkdir(parents=True, exist_ok=True)

    # 2. docs/glossary.md — empty table (the AI fills it).
    glossary = root / "docs" / "glossary.md"
    if not glossary.exists():
        glossary.write_text(
            "# Glossary\n\n"
            "Domain-specific terms used in this project — definitions and "
            "their source. The AI auto-populates this table when it "
            "encounters new terminology in your data or literature; you "
            "can also add rows by hand.\n\n"
            "| Term | Definition | Source |\n|---|---|---|\n"
        )

    # 3. docs/research_overview.md — created LAZILY by
    #    ``tool_intake_autofill``. Leaving it absent on a cold init avoids
    #    the "what's all this placeholder text?" friction; the researcher
    #    is pointed at it via inputs/intake.md instead.

    # 4. Append-only workspace logs — start EMPTY but with a header so the
    #    AI knows the file is initialised.
    #    v1.3.0: researcher-facing wording. These files are read by
    #    humans (you, your PI, a collaborator on a fresh chat). They
    #    should not name internal tools by their MCP function name —
    #    you don't care that `mem_analysis_log` is what writes here;
    #    you care what the file IS and how to read it.
    for fname, header in [
        ("methods.md",
         "# Methods\n\n"
         "Chronological record of every methodological choice made in "
         "this project — which model, why, with what parameters, citing "
         "what literature. The Methods section of your eventual paper "
         "is assembled from this file. Each analysis step appends a "
         "subsection here when it finalizes.\n"),
        ("analysis.md",
         "# Analysis log\n\n"
         "Running narrative of what was done in each numbered analysis "
         "step (`workspace/01_...`, `02_...`, …) — the headline finding, "
         "the figures and tables it produced, the decision taken at the "
         "end. Read top-to-bottom to retrace the project's reasoning; "
         "a fresh AI session can resume from this file alone.\n"),
        ("citations.md",
         "# Citations\n\n"
         "Auto-generated bibliography across the project + every per-"
         "step `literature/` folder. The Discussion / References of "
         "your paper draws from here. Regenerated whenever a step is "
         "finalized so newly-added PDFs appear automatically.\n"),
        # v1.3.0 round-3: tools.md — append-only log of which Research-OS
        # tools (and which 3rd-party packages, external services, web
        # searches) were used in this project, when, and why. Surfaces
        # the *provenance of the workflow* for reviewers + future
        # collaborators in a single place — methods.md tells WHAT the
        # analysis did; tools.md tells WHICH MACHINERY enabled it.
        ("tools.md",
         "# Tools log\n\n"
         "Chronological record of the tooling stack actually used by "
         "this project — Research-OS MCP calls (route, search, audit, "
         "finalize), 3rd-party packages (statsmodels, scanpy, DESeq2, "
         "Cytoscape, …), external services (Semantic Scholar, PubMed, "
         "GTEx, GEO), and any custom scripts the analyses depend on.\n\n"
         "Format: one bullet per usage, grouped by analysis step + "
         "synthesis stage. The synthesis dashboard surfaces this so a "
         "reviewer can audit reproducibility without re-deriving the "
         "stack from the scripts.\n\n"
         "Each step's `tool_path_finalize` appends a section here from "
         "its `conclusions.md` Methods + the per-step provenance "
         "sidecars; manual additions are welcome.\n"),
    ]:
        p = root / "workspace" / fname
        if not p.exists():
            p.write_text(header)

    # 5. workflow.mermaid — minimal diagram; expanded by _update_workflow_mermaid.
    wf = root / "workspace" / "workflow.mermaid"
    if not wf.exists():
        wf.write_text(
            "graph TD\n"
            "    init[Initialised]:::complete\n"
            "    classDef complete fill:#d4edda,stroke:#28a745\n"
        )

    # 5a. environment/ — project-global env scaffold (v1.3.0).
    #     Previously a LAZY_DIR (empty until sys_env_snapshot wrote into
    #     it). Researchers reported they couldn't tell whether the
    #     workspace had a reproducible env story at all. Now eager: an
    #     empty folder with two header files is enough for a fresh
    #     researcher to know what goes here and how it gets filled.
    env_dir = root / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_req = env_dir / "requirements.txt"
    if not env_req.exists():
        env_req.write_text(
            "# Project-global Python packages.\n"
            "#\n"
            "# Add packages here as you install them, or call\n"
            "# `sys_env_snapshot` from the AI to regenerate this from\n"
            "# the active interpreter. Pin to a major when stability\n"
            "# matters (e.g. `pandas>=2.0,<3`).\n"
            "#\n"
            "# Per-step requirements (when one step needs different\n"
            "# versions) live in `workspace/<NN_slug>/environment/\n"
            "# requirements.txt` — see that step's README.\n"
        )
    env_readme = env_dir / "README.md"
    if not env_readme.exists():
        env_readme.write_text(
            "# Project environment\n\n"
            "Single source of truth for the Python (and other-language)\n"
            "packages this project depends on. Reproducibility starts here.\n\n"
            "* `requirements.txt` — pip-installable package list. Hand-add\n"
            "  or regenerate via `sys_env_snapshot`.\n"
            "* `Dockerfile` — generated on demand by `sys_docker_generate`.\n"
            "* Conda export, R session info, system pkgs — pile in as\n"
            "  needed; `sys_env_snapshot` accepts language hints.\n\n"
            "When a single analysis step needs a bespoke environment\n"
            "different from the project default, snapshot inside that\n"
            "step instead: `sys_env_snapshot step_id=NN_slug`.\n"
        )

    # 5a-b. workspace/logs/ — append-only audit/search/override trail.
    #       Previously eager-scaffolded as an empty folder. v1.3.0:
    #       ships with a README so researchers know what lands here
    #       and can grep across audit reports without first finding
    #       out the folder exists.
    logs_dir = root / "workspace" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logs_readme = logs_dir / "README.md"
    if not logs_readme.exists():
        logs_readme.write_text(
            "# `workspace/logs/` — audit + activity trail\n\n"
            "Aggregated logs that every step (and every audit tool)\n"
            "appends to. Files here are append-only and machine-written;\n"
            "to read across steps, grep here:\n\n"
            "* `audit_report.md` — every `tool_audit_quality_full` run.\n"
            "* `search_log.md` — every literature / web search\n"
            "  (`tool_search_*` and `tool_literature_search_and_save`).\n"
            "* `repair_log.md` — every `tool_workspace_repair` invocation\n"
            "  (file moves, broken-link fixes).\n"
            "* `override_log.md` — every `override_completeness_gate=true`\n"
            "  bypass with the rationale that authorised it. Surfaced at\n"
            "  pre-submission audit time.\n"
            "* `task_*.log` — stdout/stderr of `tool_python_exec` /\n"
            "  `tool_task_run` script invocations.\n"
            "* `notifications.log` — `sys_notify` messages.\n"
            "* `version_coherence.md` — drift between scripts and the\n"
            "  outputs that cite them (from `tool_audit_version_coherence`).\n"
        )

    # 5b. workspace/scratch/ — AI sandbox. Gitignored.
    scratch_dir = root / "workspace" / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_gi = scratch_dir / ".gitignore"
    if not scratch_gi.exists():
        scratch_gi.write_text("*\n!.gitignore\n!README.md\n")
    scratch_readme = scratch_dir / "README.md"
    if not scratch_readme.exists():
        scratch_readme.write_text(
            "# Scratch\n\n"
            "AI sandbox for one-off tests (syntax checks, smoke runs, parameter\n"
            "sweeps, throw-away queries). Contents are gitignored.\n\n"
            "Anything that produces **research** must be moved into a proper\n"
            "numbered experiment folder via `sys_path_create` before it counts.\n\n"
            "Tools: `tool_scratch_write`, `tool_scratch_run`,\n"
            "`tool_scratch_list`, `tool_scratch_clear`.\n"
        )

    # 6. researcher_config.yaml — source of truth for AI behaviour.
    from research_os.tools.actions.state.config import init_config

    init_config(root, overrides=config_overrides)

    # 7. .os_state symlink inside workspace/ for scripts that resolve relative.
    workspace_os_state = root / "workspace" / ".os_state"
    if not workspace_os_state.exists():
        try:
            workspace_os_state.symlink_to(root / ".os_state", target_is_directory=True)
        except OSError:
            pass

    # 8. inputs/intake.md — single-line pointer. Replaced wholesale by
    #    tool_intake_autofill once the researcher drops files + says
    #    "fill out the intake".
    intake = root / "inputs" / "intake.md"
    if not intake.exists():
        intake.write_text(
            "# Research Intake\n\n"
            "Drop data into `inputs/raw_data/`, PDFs into `inputs/literature/`, "
            "notes into `inputs/context/`, then ask the AI to **fill out the "
            "intake** — `tool_intake_autofill` rewrites this file.\n"
        )

    # 8a. Seed each input sub-folder with a one-paragraph README so an
    #     empty folder isn't a dead end for a fresh researcher.
    _SEEDED_INPUT_READMES = {
        "raw_data": (
            "# `inputs/raw_data/`\n\n"
            "Drop datasets here — CSV, Parquet, FASTQ, NIfTI, .h5, .xlsx, "
            "VCF, JSON, whatever your project consumes. The AI reads files "
            "from here but **never modifies them**; derived data lives under "
            "`workspace/<NN_slug>/data/output/`.\n"
        ),
        "literature": (
            "# `inputs/literature/`\n\n"
            "PDFs / EPUBs of papers + theses + protocols. The AI extracts "
            "citations and quotes from here when grounding methodology "
            "(`tool_research_method`) and when assembling the bibliography "
            "(`tool_citations_verify`, `mem_citations_generate`).\n"
        ),
        "context": (
            "# `inputs/context/`\n\n"
            "Free-form context that doesn't fit raw_data or literature: PI "
            "emails, protocols, drafts, prior reports, lab notebook excerpts, "
            "screenshots of Slack threads. The AI reads these for project "
            "framing during `tool_intake_autofill` and step planning.\n"
        ),
    }
    for sub, body in _SEEDED_INPUT_READMES.items():
        rp = root / "inputs" / sub / "README.md"
        if not rp.exists():
            rp.write_text(body)

    # 9. Manifest + state.
    manifest = {
        "schema_version": "2.0",
        "project": {"title": project_name},
        "created_at": now_iso(),
        "top_level_directories": list(TOP_LEVEL_DIRS),
        "active_path": "main",
        "paths": {"main": {"status": "active"}},
    }
    write_json(manifest_path(root), manifest)

    state = default_state()
    state["project_name"] = project_name
    # Persist wizard-captured research metadata to state (it used to live in
    # researcher_config.yaml, but that's now reserved for fields a researcher
    # actively chooses). regenerate_intake reads these on subsequent calls.
    if config_overrides:
        if config_overrides.get("domain"):
            state["domain"] = config_overrides["domain"]
        if config_overrides.get("research_question"):
            state["research_question"] = config_overrides["research_question"]
        questions = config_overrides.get("research_questions") or []
        if questions:
            state["research_questions"] = [q for q in questions if isinstance(q, str) and q.strip()]
    save_state(root, state)

    # Only regenerate intake.md if there's something real to put in it:
    # files the researcher already dropped under inputs/, or explicit
    # overrides (research_question / domain) passed via the wizard or
    # `--config-overrides`. On a cold init with no signal, the short
    # pointer written above is the right surface — tool_intake_autofill
    # rewrites it once the researcher has dropped files in and asked
    # for an intake pass.
    intake_signal = _has_user_inputs(root) or any(
        (config_overrides or {}).get(k) for k in ("research_question", "domain", "keywords")
    )
    if intake_signal:
        regenerate_intake(root, project_name, config_overrides)
    _copy_agents_md(root, copy_agents)
    _setup_mcp_configs(root, ide_flags)
    _setup_gitignore(root)
    _write_getting_started(root, project_name)
    _write_project_root_readme(root, project_name, state)
    _write_sharing_scripts(root, project_name)
    _update_manifest(root)
    _prune_stale_gitkeeps(root)
    if git_init and not (root / ".git").exists():
        try:
            subprocess.run(["git", "init"], cwd=root, capture_output=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sharing — zip + GitHub init scripts written at scaffold time.
# ---------------------------------------------------------------------------


# Files / directories EXCLUDED from the share-safe archive. These are
# either AI-internal (CLAUDE.md, AGENTS.md, MCP configs) or onboarding
# artefacts a downstream researcher does not need (GETTING_STARTED.md).
_SHARE_EXCLUDE_NAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GETTING_STARTED.md",
    ".os_state",
    ".claude",
    ".cursor",
    ".vscode",
    ".antigravity",
    ".opencode",
    "mcp_config.json",
    ".mcp.json",
    "opencode.json",
    "__pycache__",
    ".pytest_cache",
    ".DS_Store",
    "node_modules",
    "venv",
    ".venv",
    "env",
)

# Folders that ARE included by default. Anything else at the project root
# is preserved as-is unless it matches an exclusion above.
_SHARE_INCLUDE_DIRS = (
    "inputs",
    "workspace",
    "synthesis",
    "docs",
    "environment",
)


def _write_sharing_scripts(root: Path, project_name: str) -> None:
    """Scaffold the export-to-zip + GitHub init scripts. Idempotent."""
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    export_py = scripts_dir / "export_share_archive.py"
    if not export_py.exists():
        export_py.write_text(_EXPORT_PY_TEMPLATE)
        try:
            export_py.chmod(0o755)
        except OSError:
            pass

    export_sh = scripts_dir / "export_share_archive.sh"
    if not export_sh.exists():
        export_sh.write_text(
            "#!/usr/bin/env bash\n"
            "# Build a share-safe zip of this project (no AI internals).\n"
            "# Equivalent to `python scripts/export_share_archive.py`.\n"
            "set -euo pipefail\n"
            'HERE="$(cd "$(dirname "$0")/.." && pwd)"\n'
            'python "$HERE/scripts/export_share_archive.py" "$@"\n'
        )
        try:
            export_sh.chmod(0o755)
        except OSError:
            pass

    init_gh = scripts_dir / "init_github.sh"
    if not init_gh.exists():
        slug = slugify(project_name, "research-project").replace("_", "-")
        init_gh.write_text(_INIT_GITHUB_TEMPLATE.replace("__SLUG__", slug))
        try:
            init_gh.chmod(0o755)
        except OSError:
            pass

    sharing_doc = root / "docs" / "SHARING.md"
    if not sharing_doc.exists():
        sharing_doc.write_text(_SHARING_DOC_TEMPLATE)


_EXPORT_PY_TEMPLATE = '''"""Bundle this Research OS project for a collaborator.

Builds a zip that contains a clean, share-safe view of your project —
the inputs you've collected, the analyses you've run, the synthesis
artefacts, and the docs — WITHOUT any AI configuration. The recipient
opens the zip and sees a normal research workspace; they do NOT need
Research OS installed to read it.

What is included:
  inputs/, workspace/, synthesis/, docs/, environment/, README.md (if present)
What is EXCLUDED (always):
  AGENTS.md, CLAUDE.md, GETTING_STARTED.md, CONTRIBUTORS.md,
  .os_state/, .claude/, .cursor/, .vscode/, .antigravity/, .opencode/,
  MCP configs, __pycache__/, .pytest_cache/, .DS_Store, virtualenvs,
  node_modules/.

The zip is written to <project>_share_<YYYY-MM-DD>.zip in the project
root. Use --out PATH to override.

Usage:
    python scripts/export_share_archive.py                    # default zip
    python scripts/export_share_archive.py --out /tmp/x.zip   # custom path
    python scripts/export_share_archive.py --include-raw-data # include raw data
"""
from __future__ import annotations
import argparse
import datetime as _dt
import sys
import zipfile
from pathlib import Path

EXCLUDE_NAMES = {
    "AGENTS.md", "CLAUDE.md", "GETTING_STARTED.md",
    ".os_state", ".claude", ".cursor", ".vscode",
    ".antigravity", ".opencode",
    "mcp_config.json", ".mcp.json", "opencode.json",
    "__pycache__", ".pytest_cache", ".DS_Store",
    "node_modules", "venv", ".venv", "env",
}

INCLUDE_DIRS = ("inputs", "workspace", "synthesis", "docs", "environment")


def _excluded(path: Path) -> bool:
    parts = path.parts
    for part in parts:
        if part in EXCLUDE_NAMES:
            return True
        if part.startswith(".") and part not in {".gitignore", ".gitkeep"}:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None,
                    help="Output zip path. Default: <project>_share_<date>.zip")
    ap.add_argument("--include-raw-data", action="store_true",
                    help="Include inputs/raw_data/ (default: skipped to keep "
                    "the archive small and avoid PII leaks).")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    today = _dt.date.today().isoformat()
    out = args.out or (root / f"{root.name}_share_{today}.zip")
    out = out.resolve()

    files_added = 0
    bytes_added = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Top-level files we DO want shipped to collaborators.
        for top in ("README.md", "CONTRIBUTORS.md"):
            tp = root / top
            if tp.exists():
                zf.write(tp, arcname=f"{root.name}/{top}")
                files_added += 1
                bytes_added += tp.stat().st_size
        for sub in INCLUDE_DIRS:
            base = root / sub
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                if not args.include_raw_data and "raw_data" in p.relative_to(root).parts:
                    continue
                rel = p.relative_to(root)
                if _excluded(rel):
                    continue
                arc = f"{root.name}/{rel.as_posix()}"
                zf.write(p, arcname=arc)
                files_added += 1
                bytes_added += p.stat().st_size

    print(f"[done] {out}")
    print(f"       {files_added} files, {bytes_added / 1024:.1f} KB compressed "
          f"({out.stat().st_size / 1024:.1f} KB on disk)")
    if not args.include_raw_data:
        print("       NOTE: inputs/raw_data/ skipped. Pass --include-raw-data to bundle it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_INIT_GITHUB_TEMPLATE = """#!/usr/bin/env bash
# Initialise a GitHub repo from this project — share-safe by default.
#
# Excludes AI-internal files (AGENTS.md, CLAUDE.md, .os_state/, .claude/,
# MCP configs, GETTING_STARTED.md) and large raw data via .gitignore.
#
# Requires: gh CLI installed and authenticated (`gh auth login`).
#
# Usage:
#   ./scripts/init_github.sh                    # default name from project slug
#   ./scripts/init_github.sh my-repo-name       # custom repo name
#   ./scripts/init_github.sh my-repo --public   # public repo (default private)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

REPO_NAME="${1:-__SLUG__}"
VISIBILITY="--private"
for arg in "$@"; do
  [[ "$arg" == "--public" ]] && VISIBILITY="--public"
  [[ "$arg" == "--internal" ]] && VISIBILITY="--internal"
done

# 1. Make sure git is initialised.
if [ ! -d ".git" ]; then
  git init -b main
fi

# 2. Make sure the share-safe .gitignore additions are present.
GI=".gitignore"
touch "$GI"
add_ignore() {
  grep -qxF "$1" "$GI" 2>/dev/null || echo "$1" >> "$GI"
}
add_ignore "AGENTS.md"
add_ignore "CLAUDE.md"
add_ignore "GETTING_STARTED.md"
add_ignore ".os_state/"
add_ignore ".claude/"
add_ignore ".cursor/"
add_ignore ".vscode/"
add_ignore ".antigravity/"
add_ignore ".opencode/"
add_ignore "mcp_config.json"
add_ignore ".mcp.json"
add_ignore "opencode.json"
add_ignore "inputs/raw_data/"
add_ignore "__pycache__/"
add_ignore "*.pyc"
add_ignore ".DS_Store"

# 3. Stage + commit (idempotent — skips if nothing changed).
git add .
if ! git diff --staged --quiet; then
  git commit -m "Initial commit: Research OS project (share-safe)"
fi

# 4. Create the remote + push.
if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not installed. Skipping remote creation."
  echo "Install: https://cli.github.com/  then re-run."
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

if ! gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" $VISIBILITY --source=. --remote=origin --push
else
  echo "Repo $REPO_NAME already exists. Pushing current branch."
  git push -u origin main
fi

echo "[done] Repo URL:"
gh repo view --json url -q .url
"""


_SHARING_DOC_TEMPLATE = """# Sharing this project

**What this is for.** Two safe ways to send this project to a
collaborator (or your PI / advisor / Argonne team) without leaking
AI-internal config or large raw data. Both excludes `.os_state/`,
the IDE MCP configs, `AGENTS.md`, and `CLAUDE.md` by default — what
your collaborator opens looks like a finished research workspace,
not an in-progress AI session.

Pick the one that matches how you collaborate:

* **Option 1** — bundle a zip you can email or upload anywhere.
  No git knowledge required.
* **Option 2** — push to a private GitHub repo so your team can
  pull, contribute, and see the project's `CONTRIBUTORS.md` history.

---

## Option 1 — Zip archive

```sh
python scripts/export_share_archive.py
# → <project>_share_<YYYY-MM-DD>.zip in the project root
```

What's included: `inputs/` (minus raw data unless you pass
`--include-raw-data`), `workspace/`, `synthesis/`, `docs/`, `environment/`,
and a top-level `README.md` if present.

What's excluded (always): `AGENTS.md`, `CLAUDE.md`, `GETTING_STARTED.md`,
`.os_state/`, `.claude/`, `.cursor/`, `.vscode/`, `.antigravity/`,
`.opencode/`, MCP configs, `__pycache__/`, virtualenvs, `node_modules/`.

Pass `--out PATH` to override the destination, e.g.

```sh
python scripts/export_share_archive.py --out /tmp/myproj.zip
```

## Option 2 — GitHub repo

```sh
./scripts/init_github.sh                  # private repo named after the project
./scripts/init_github.sh my-repo-name     # custom repo name
./scripts/init_github.sh my-repo --public # public repo
```

This script:

1. Initialises `git` if needed.
2. Appends the share-safe exclusions to `.gitignore` (idempotent).
3. Commits if there are any new changes.
4. Creates the GitHub repo via the `gh` CLI and pushes the first commit.

Requires the [GitHub CLI](https://cli.github.com/) authenticated
(`gh auth login`). If `gh` is not installed, the local commit still
happens — push manually afterward.

## What collaborators get

A clean research workspace they can read without any Research-OS context:

* `synthesis/dashboard.html` — the polished single-file dashboard
  (open in any browser; self-contained).
* `synthesis/figures/` — every curated figure with its caption sidecar.
* `synthesis/REPORT.md` / `synthesis/paper.md` — the narrative deliverable.
* `workspace/NN_*/conclusions.md` — the per-step reasoning chain.
* `workspace/NN_*/scripts/` — the actual analysis code (reproducible).
* `workspace/NN_*/data/output/` — derived artefacts each step persisted.
* `docs/` — research question, glossary, workflow diagram.

The AI-side configuration is intentionally excluded, so the share
reads as a finished research project, not an in-progress AI workspace.
"""



def _prune_stale_gitkeeps(root: Path) -> None:
    """Remove .gitkeep from any project directory that now has real content.

    With the eager/lazy split we no longer create .gitkeep on a cold
    scaffold. This helper still runs for safety: pre-1.0 projects (or
    user-created dirs) may carry .gitkeep files alongside real artefacts,
    and we want them gone so casual ``ls`` and dashboard counters stay
    honest. The pass also removes .gitkeep from any empty LAZY_DIR a
    legacy code path may have created — those dirs should not exist at
    all unless populated.
    """
    for rel in TOP_LEVEL_DIRS:
        d = root / rel
        if not d.is_dir():
            continue
        keep = d / ".gitkeep"
        if not keep.exists():
            continue
        siblings = [p for p in d.iterdir() if p.name != ".gitkeep"]
        if siblings:
            try:
                keep.unlink()
            except OSError:
                pass
            continue
        # Empty + .gitkeep'd lazy dir → drop both the marker and the dir.
        if rel in LAZY_DIRS:
            try:
                keep.unlink()
                d.rmdir()
            except OSError:
                pass


def _write_project_root_readme(root: Path, project_name: str, state: dict) -> None:
    """Drop a project-root README.md — the GitHub / repo-browser front page.

    Distinct from GETTING_STARTED.md (which targets the *researcher driving
    this Research OS workspace*); README.md targets anyone who lands on the
    folder cold — a collaborator, a PI, a reviewer cloning from GitHub.
    Researcher-facing AND tooling-neutral: never mentions MCP tool names.
    """
    dest = root / "README.md"
    if dest.exists():
        return
    domain = (state.get("domain") or "").strip()
    question = (state.get("research_question") or "").strip()
    domain_line = f"**Domain:** {domain}\n\n" if domain else ""
    q_line = f"**Research question:** {question}\n\n" if question else ""
    dest.write_text(
        f"""# {project_name}

{q_line}{domain_line}> A research project scaffolded with [Research OS](https://github.com/vsetlur/Research-OS) — a structured AI-collaboration workspace for grounded, reproducible research.

## What's in this folder

| Folder | Purpose |
|---|---|
| `inputs/raw_data/` | Datasets you (or collaborators) provide. Immutable; the AI reads but never writes here. |
| `inputs/literature/` | PDFs / EPUBs of papers, theses, protocols the project draws on. |
| `inputs/context/` | Free-form context: PI emails, lab-notebook entries, prior reports. |
| `workspace/NN_slug/` | Numbered analysis steps. Each has its own scripts, data, outputs, conclusions. |
| `workspace/methods.md` · `analysis.md` · `citations.md` | Append-only project-wide logs (the narrative). |
| `synthesis/` | Final deliverables — paper, poster, dashboard, slides — generated on request. |
| `environment/` | Reproducibility surface — `requirements.txt`, conda exports, optional Dockerfile. |
| `STATE.md` | Canonical project status. A fresh session reads this first to know where things stand. |

## How to read the project

1. Open `STATE.md` for the snapshot: research question, active hypotheses, what's been done.
2. `workspace/analysis.md` gives the chronological narrative.
3. Each `workspace/NN_*/conclusions.md` has the full statistics + decisions for that step.
4. Final outputs (when generated) live in `synthesis/`.

## Reproducing the analysis

```bash
# 1. Install Python + the project's package list
pip install -r environment/requirements.txt

# 2. Run any analysis step end-to-end
cd workspace/01_<slug>
python scripts/01_<slug>_v1.py
```

Each step's `data/input/` is symlinked from the project's `inputs/raw_data/`
or from the previous step's `data/output/`. Outputs land under
`workspace/<step>/outputs/{{figures,tables,reports}}`.

## Working on this project with an AI

* Researcher onboarding: `GETTING_STARTED.md`
* AI operating rules: `AGENTS.md`

## License

_(set by you in this README — the scaffold leaves it blank by default.)_
"""
    )


def _write_getting_started(root: Path, project_name: str) -> None:
    """Drop a friendly GETTING_STARTED.md the researcher reads first."""
    dest = root / "GETTING_STARTED.md"
    if dest.exists():
        return
    dest.write_text(
        f"""# Getting started with **{project_name}**

This is a Research OS workspace. Two files matter most to you:

* `AGENTS.md` — what the AI is told to do (you almost never edit this).
* `inputs/researcher_config.yaml` — how the AI should behave for **you**.
  Every field is optional; defaults work.

## 1. Drop your files

| Where | What goes here |
|---|---|
| `inputs/raw_data/`  | Data files (CSV, Parquet, FASTQ, NIfTI, JSON, Excel, ...) |
| `inputs/literature/`| PDFs of papers you want the AI to know about |
| `inputs/context/`   | Notes, drafts, prior reports — anything text |

`inputs/` is **immutable** — the AI can read it but cannot modify it.
Derived data lives under `workspace/`.

## 2. Open your AI IDE on this folder

The MCP config was already dropped for whichever IDE you use:
Claude Code, OpenCode, Antigravity, Cursor, Claude Desktop, VS Code,
Windsurf, Continue, Aider. Restart your IDE if it doesn't auto-detect.

The MCP server should show as connected. If it doesn't, run
`research-os start` in a terminal at the project root.

## 3. Start a chat. Try any of:

```
fill out the intake               (AI reads inputs/, proposes question + hypotheses)
what should I do next?            (iterative planning — AI assesses + searches + proposes)
run a baseline EDA                (creates workspace/01_baseline_eda/ with figures + report)
fit a logistic regression         (methodology selection → analysis_plan)
find papers about <topic>         (literature search across S2 + Crossref + PubMed + arXiv)
write the methods section
write the paper for a journal     (verified citations only — no hallucinations)
make me an executive dashboard
draft an NIH R01 narrative
check reproducibility
fix my workspace                  (heals missing dirs / corrupted state, never deletes)
wrap up the session
```

The AI loads the right protocol and walks through it. Interrupt anytime;
"keep going" or "switch to autopilot" both work.

## 4. Where outputs end up

| Folder | What's inside |
|---|---|
| `workspace/01_<slug>/`, `02_<slug>/`, ... | Numbered experiment folders. Scripts + data + outputs + per-step conclusions. |
| `workspace/methods.md`, `analysis.md`, `citations.md` | Append-only logs (the project's narrative). |
| `workspace/scratch/`  | AI sandbox for quick tests (gitignored). |
| `synthesis/`          | Final outputs — paper.md, abstract.md, poster.pdf, dashboard.html (only created when you ask). |

## 5. Controls

In `inputs/researcher_config.yaml`:

* `interaction.autonomy_level: manual | supervised | autopilot`
* `model_profile: small | medium | large` (affects how the AI batches work)
* `runtime.shared_server: true` if you're on HPC / a shared box

You can change these mid-session by telling the AI ("switch to autopilot").

## 6. When things go wrong

| Problem | Say to the AI... |
|---|---|
| Something seems broken | "Run `tool_workspace_repair`." |
| Lost work | "Show me checkpoints and roll back to <id>." |
| Conversation too long | "Hand off the session." |
| AI making bad calls | "Switch to manual mode and walk me through each step." |

## 7. Working with collaborators

* `CONTRIBUTORS.md` — opt-in activity log. Created on the first
  `research-os ide add` / `ide remove` / explicit share action so a
  fresh collaborator can see who changed wiring. Fresh projects do not
  ship one until something changes.
* `research-os ide add <name>` — wire a new AI IDE for *you* without
  re-scaffolding the workspace (so nothing your teammate did breaks).
* `research-os ide list` — see which IDE configs are wired.
* `scripts/export_share_archive.py` — bundle this project as a safe
  zip (no AI internals) to email or upload. See `docs/SHARING.md`.
* `scripts/init_github.sh` — push to a private GitHub repo with the
  share-safe `.gitignore` already configured.

## More

* First steps: `docs/START.md` (install + first project + cheatsheet)
* Sharing: `docs/SHARING.md` (zip + GitHub paths)
* Full guide: `docs/RESEARCHER_GUIDE.md`
* Pick a protocol: `docs/USE_CASES.md` (role × goal × output)
* All tools: `docs/TOOLS.md`
* All protocols: `docs/PROTOCOLS.md`
* FAQ: `docs/FAQ.md`
"""
    )


def _copy_agents_md(root: Path, copy: bool) -> None:
    if not copy:
        return
    dest = root / "AGENTS.md"
    if dest.exists():
        return
    src = Path(__file__).resolve().parent.parent.parent / "templates" / "AGENTS.md"
    if src.exists():
        shutil.copy2(src, dest)


def _setup_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    if gi.exists():
        return
    gi.write_text(
        "# Research OS\n"
        "__pycache__/\n*.pyc\n*.pyo\n*.egg-info/\n"
        ".venv/\nvenv/\nenv/\n"
        ".DS_Store\n\n"
        ".os_state/cache/\n.os_state/checkpoints/\n.os_state/handoffs/\n\n"
        "# Secrets / machine-specific\n"
        "inputs/researcher_config.yaml\n"
        "inputs/literature_index.yaml\n"
        "inputs/raw_data/\n"
    )


def _setup_mcp_configs(root: Path, ide_flags: list[str]) -> None:
    """Drop a per-IDE MCP config + rule file so the AI auto-connects.

    The MCP config uses `${workspaceFolder}` so the SAME `research-os`
    binary serves every project the IDE has open — install once,
    scaffold each project with `research-os init`, no rebuild of the
    global install. Editors that don't expand `${workspaceFolder}`
    still work: the server reads `RESEARCH_OS_WORKSPACE` first and
    falls back to walking up from the current working directory for
    `.os_state/` (which the IDE typically launches the server in).
    """
    mcp_entry = {
        "command": "research-os",
        "args": ["start"],
        "env": {"RESEARCH_OS_WORKSPACE": "${workspaceFolder}"},
    }
    templates_dir = Path(__file__).resolve().parent.parent.parent / "templates"

    def _copy_rule(src_rel: str, dest: Path) -> None:
        src = templates_dir / src_rel
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(src, dest)

    if "cursor" in ide_flags:
        d = root / ".cursor"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".cursor/rules/research-os.mdc", d / "rules" / "research-os.mdc")

    if "claude" in ide_flags:
        d = root / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".claude/rules/research-os.md", d / "rules" / "research-os.md")
        _copy_rule(".claude/commands/start-session.md", d / "commands" / "start-session.md")

    if "antigravity" in ide_flags:
        d = root / ".antigravity"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")
        _copy_rule(".antigravity/rules/research-os.md", d / "rules" / "research-os.md")

    if "opencode" in ide_flags:
        f = root / "opencode.json"
        if not f.exists():
            f.write_text(
                json.dumps(
                    {
                        "mcp": {"research-os": mcp_entry},
                        "system_prompt": "Read AGENTS.md at the project root before any research request.",
                    },
                    indent=2,
                )
                + "\n"
            )

    if "vscode" in ide_flags:
        d = root / ".vscode"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "mcp.json"
        if not f.exists():
            f.write_text(json.dumps({"mcpServers": {"research-os": mcp_entry}}, indent=2) + "\n")

    if "windsurf" in ide_flags:
        # Project-level rules file Windsurf reads automatically.
        _copy_rule(".windsurfrules", root / ".windsurfrules")

    if "continue" in ide_flags:
        _copy_rule(".continuerules", root / ".continuerules")

    if "aider" in ide_flags:
        _copy_rule(".aider.conf.yml", root / ".aider.conf.yml")

    if "claude_code" in ide_flags or "claude" in ide_flags:
        # Claude Code reads CLAUDE.md at the project root.
        _copy_rule("CLAUDE.md", root / "CLAUDE.md")


# ---------------------------------------------------------------------------
# Intake + literature index
# ---------------------------------------------------------------------------


def regenerate_intake(
    root: Path, project_name: str | None = None, config_overrides: dict | None = None
) -> str:
    """Rewrite ``inputs/intake.md`` with current file hashes + config."""
    config_overrides = config_overrides or {}
    try:
        state = load_state(root) or {}
    except Exception:
        state = {}
    project_name = project_name or state.get("project_name") or "Research Project"

    # Domain / research_question used to live in researcher_config.yaml; they
    # now live in .os_state/state.json (written by tool_intake_autofill).
    # Overrides win; state is the fallback; finally a placeholder.
    domain = (
        config_overrides.get("domain")
        or state.get("domain")
        or ""
    )
    research_question = (
        config_overrides.get("research_question")
        or state.get("research_question")
        or ""
    )
    keywords: list[str] = list(config_overrides.get("keywords", []) or [])
    if not keywords:
        keywords = [
            h.get("statement", "")
            for h in (state.get("active_hypotheses") or [])
            if isinstance(h, dict) and h.get("statement")
        ][:5]

    input_files: list[dict[str, Any]] = []
    for subdir in ("raw_data", "literature", "context"):
        d = root / "inputs" / subdir
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name.startswith(".") or f.name in {".gitkeep"}:
                continue
            input_files.append(
                {
                    "path": f.relative_to(root).as_posix(),
                    "sha256": compute_file_hash(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                }
            )

    lines = [
        f"# {project_name} — Research Intake",
        f"*Auto-generated: {now_iso()}*",
        "",
        "## Project",
        f"- Title: {project_name}",
        f"- Domain: {domain or '(not yet classified — domain_analysis will set this)'}",
        f"- Research question: {research_question or '(to be confirmed in project_startup)'}",
        f"- Keywords: {', '.join(keywords) if keywords else '(none)'}",
        "",
        "## Input files",
    ]
    if input_files:
        lines.extend(["", "| File | SHA-256 | Size |", "|---|---|---|"])
        for f in input_files:
            lines.append(
                f"| {f['path']} | `{f['sha256'][:12]}…` | {f['size_kb']:.1f} KB |"
            )
    else:
        lines.append("- (no inputs yet — drop files into `inputs/raw_data/` or `inputs/literature/`)")
    lines.append("")

    intake_path = root / "inputs" / "intake.md"
    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text("\n".join(lines) + "\n")
    return str(intake_path.absolute())


def update_literature_index(root: Path) -> dict:
    """Refresh ``inputs/literature_index.yaml`` from PDFs in ``inputs/literature/``."""
    lit_dir = root / "inputs" / "literature"
    index_path = root / "inputs" / "literature_index.yaml"

    index: dict = {"schema_version": "1.0", "last_updated": now_iso(), "entries": {}}
    if index_path.exists() and yaml:
        try:
            existing = yaml.safe_load(index_path.read_text()) or {}
            index["entries"] = existing.get("entries", {})
        except Exception:
            pass

    if lit_dir.exists():
        for f in sorted(lit_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in {".pdf", ".epub", ".ps", ".djvu"}:
                continue
            citation_key = re.sub(r"[\s-]+", "_", f.stem).lower()
            sha = compute_file_hash(f)
            entry = index["entries"].get(f.name, {})
            entry.update(
                {
                    "citation_key": citation_key,
                    "sha256": sha,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "verified": entry.get("verified", False),
                }
            )
            index["entries"][f.name] = entry

    if yaml:
        index_path.write_text(yaml.safe_dump(index, sort_keys=False))
    else:
        index_path.write_text(json.dumps(index, indent=2) + "\n")
    return index


# ---------------------------------------------------------------------------
# Numbered experiment creation
# ---------------------------------------------------------------------------


def _prune_old_checkpoints(root: Path, keep: int = 5) -> None:
    ckpt_dir = root / ".os_state" / "checkpoints"
    if not ckpt_dir.exists():
        return
    meta_files = sorted(ckpt_dir.glob("*.meta.json"), key=lambda f: f.stat().st_mtime)
    for meta in meta_files[: max(0, len(meta_files) - keep)]:
        try:
            data = json.loads(meta.read_text())
            cid = data.get("checkpoint_id")
        except Exception:
            cid = meta.stem
        meta.unlink(missing_ok=True)
        snapshot_dir = ckpt_dir / cid if cid else None
        if snapshot_dir and snapshot_dir.exists():
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def _seed_step_subfolder_readmes(
    exp_dir: Path,
    root: Path,
    branch_id: str,
    next_num: int,
    from_step: str | None,
) -> None:
    """Write informative README.md stubs in every step subfolder so an empty
    folder still tells the researcher what to do — and points at the project-
    global resource (inputs/literature, environment/) when nothing step-
    specific was needed. Idempotent.
    """
    rel_root = root.absolute()

    def _write_if_missing(path: Path, body: str) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)

    upstream_hint = (
        f"data/input → previous step's data/output (step {next_num - 1:02d})."
        if next_num > 1 and not from_step
        else "data/input → inputs/raw_data (this is the ingest step)."
        if next_num == 1
        else f"data/input copied from `{from_step}`."
    )

    # Top-level data/ — explains the symlink + how downstream steps consume it.
    _write_if_missing(
        exp_dir / "data" / "README.md",
        f"# `{branch_id}` — data\n\n"
        "Two subfolders, both managed by the harness:\n\n"
        "- **`input/`** — usually a symlink. Source of truth for this step's "
        f"raw or pre-processed inputs. Default: {upstream_hint}\n"
        "- **`output/`** — write CSV/parquet/pickle artefacts here. "
        "Downstream steps' `data/input/` will symlink to this folder, so "
        "name files for reuse (e.g. `tidy_survey.csv`, `composites.csv`).\n\n"
        "When this step is complete `tool_path_finalize` rewrites this file "
        "with the actual filename → downstream-step consumer mapping derived "
        "from the workflow DAG.\n",
    )
    _write_if_missing(
        exp_dir / "data" / "input" / "README.md"
        if (exp_dir / "data" / "input").is_dir() and not (exp_dir / "data" / "input").is_symlink()
        else exp_dir / "data" / "_input_readme.md",
        f"# `{branch_id}/data/input` — usage\n\n"
        f"Default wiring: {upstream_hint}\n\n"
        "Replace the symlink with a directory only if this step has bespoke "
        "inputs that aren't a clean function of the previous step's outputs. "
        "Document any divergence in `analysis.md` (`mem_decision_log`).\n",
    )
    _write_if_missing(
        exp_dir / "data" / "output" / "README.md",
        f"# `{branch_id}/data/output` — usage\n\n"
        "Persist analytic artefacts (CSV, parquet, pickle, JSON) here so "
        "downstream steps and the synthesis dashboard can consume them.\n\n"
        "Each saved file should be reproducible from `scripts/` alone — no "
        "ad-hoc REPL edits. After `tool_path_finalize` runs, this README is "
        "rewritten to list every persisted artefact with its consumer step.\n",
    )

    # Environment — by default points at global env; only step-specific if the
    # researcher snapshotted with sys_env_snapshot.
    _write_if_missing(
        exp_dir / "environment" / "README.md",
        f"# `{branch_id}` — environment\n\n"
        "**Default:** this step uses the project-global environment at "
        f"`{rel_root.name}/environment/` (see `environment/requirements.txt`).\n\n"
        "Run `sys_env_snapshot` ONLY if this step needs different package "
        "versions than the global env — otherwise this folder stays empty "
        "(intentionally; the global snapshot is sufficient for reproducibility).\n\n"
        "When `tool_path_finalize` runs at step completion it confirms one of "
        "the two states above and updates this note accordingly.\n",
    )

    # Literature — points at global inputs/literature; step-specific only if
    # the step has its own evidence chain (e.g. methodology pick, sensitivity
    # comparison). Seed a structured `key_papers.md` so the analyst has a
    # template, not a blank page.
    _write_if_missing(
        exp_dir / "literature" / "README.md",
        f"# `{branch_id}` — literature\n\n"
        "**Default:** this step uses the project-global literature corpus at "
        "`inputs/literature/` (search via `tool_literature_search` or "
        "`tool_evidence_synthesise`).\n\n"
        "Put a PDF / DOI / sidecar `.notes.md` here ONLY if the citation is "
        "specific to a methodological choice made in *this* step (and not "
        "broadly relevant to the project). For decisions that hang on "
        "literature, also call `mem_decision_log` with the citation key + a "
        "one-line rationale so the reasoning is captured in `analysis.md`.\n\n"
        "For statistical / methodological choices (e.g. 'use Welch ANOVA "
        "because variances unequal'), include a short *Why this method?* "
        "block citing either a textbook reference or the EDA result that "
        "triggered the choice. See `key_papers.md` for the template the "
        "finaliser fills in.\n\n"
        "`tool_path_finalize` will normalise this README to summarise the "
        "actual decisions + sources captured.\n",
    )
    _write_if_missing(
        exp_dir / "literature" / "key_papers.md",
        f"# `{branch_id}` — key papers (template)\n\n"
        "Per-decision evidence list. Fill in only those rows where this step "
        "leans on a specific source; leave the rest blank. The synthesis "
        "tools read this to anchor each methodological claim to a real "
        "citation when they assemble the paper / dashboard.\n\n"
        "| Decision | Citation key | DOI / URL | One-line rationale |\n"
        "|---|---|---|---|\n"
        "| _(e.g. method choice)_ | | | |\n"
        "| _(e.g. parameter pick)_ | | | |\n"
        "| _(e.g. assumption check)_ | | | |\n\n"
        "Tip: `tool_literature_search_and_save query=\"<method>\" step_id="
        f"\"{branch_id}\" limit=5 download_top=2` populates this folder + the "
        "step-level `literature_index.yaml` in one shot.\n",
    )

    # Context — the step's narrative scratchpad. Distinct from literature
    # (formal sources) and data (machine-readable). Holds: methodology
    # rationale prose, prior conversation snippets, hand-overs from
    # upstream collaborators, screenshots the analysis depends on.
    _write_if_missing(
        exp_dir / "context" / "README.md",
        f"# `{branch_id}` — context (narrative scratchpad)\n\n"
        "Drop anything *prose* here that the next analyst would need to act:\n\n"
        "- Methodology rationale that doesn't fit in `conclusions.md`.\n"
        "- Notes from upstream conversations / Slack threads.\n"
        "- Screenshots of source documents the analysis depends on.\n"
        "- Drafts of plain-language explanations for the dashboard.\n"
        "- Hand-overs from a previous chat (auto-written by "
        "  `sys_session_handoff` when relevant).\n\n"
        "What does NOT go here:\n\n"
        "- PDFs / DOIs / formal citations → `literature/`.\n"
        "- CSV / parquet outputs → `data/output/`.\n"
        "- Figures / tables → `outputs/figures/` and `outputs/tables/`.\n\n"
        "Files here are read by the synthesis dashboard's per-step appendix "
        "and surface in the paper's discussion when relevant. Empty is fine "
        "for routine steps; `tool_path_finalize` will note the folder was "
        "intentionally left blank.\n",
    )
    _write_if_missing(
        exp_dir / "context" / "notes.md",
        f"# `{branch_id}` — notes\n\n"
        "*(Free-form. Anything that would help a new reader pick this step up.)*\n\n"
        "## Plain-language summary\n\n"
        "_If you had to explain this step's purpose to a non-statistician in "
        "two sentences, what would you say? This is what the dashboard will "
        "surface for executive / teaching audiences._\n\n"
        "## Decisions made informally (not yet in mem_decision_log)\n\n"
        "_Capture the reasoning as it happens so it doesn't get lost between "
        "the script and the formal log._\n",
    )

    # Outputs — explain what each subfolder is for.
    _write_if_missing(
        exp_dir / "outputs" / "README.md",
        f"# `{branch_id}` — outputs\n\n"
        "- **`reports/`** — Markdown narratives (`*.md`) summarising results "
        "for humans. The synthesis report + dashboard surface these verbatim.\n"
        "- **`figures/`** — PNG / SVG plots. Each figure SHOULD have a "
        "sibling `<name>.caption.md` describing what the reader is looking at "
        "in plain language (the dashboard embeds the caption inline).\n"
        "- **`tables/`** — CSV / TSV tables. Each table SHOULD have a "
        "sibling `<name>.caption.md` for the same reason.\n\n"
        "Follow `figure_guidelines` (DPI ≥150 screen / ≥300 print, colour-blind "
        "safe palette, axis units). Audit with `tool_audit_figure`.\n",
    )

    # Scripts — explain naming + reproducibility expectation.
    _write_if_missing(
        exp_dir / "scripts" / "README.md",
        f"# `{branch_id}` — scripts\n\n"
        f"Place runnable analysis scripts here (preferred name: "
        f"`{branch_id}_v1.py`). Bump the suffix when the analysis materially "
        "changes; the dashboard surfaces the latest version. Each script must "
        "be re-runnable end-to-end with only `data/input/` and the documented "
        "environment as inputs.\n",
    )


_PATH_LINEAGE_RE = re.compile(r"_path_(\d+)(?:__DEAD_END)?$")


def _extract_path_lineage(branch_id: str) -> int | None:
    """Return the branch lineage number embedded in a folder name, or None.

    ``05_glmm_path_2`` → ``2``; ``05_glmm`` → ``None``; ``05_glmm_path_2__DEAD_END`` → ``2``.
    """
    m = _PATH_LINEAGE_RE.search(branch_id)
    return int(m.group(1)) if m else None


def _max_path_lineage(workspace: Path) -> int:
    """Largest existing ``_path_<k>`` lineage tag across the workspace."""
    best = 0
    if not workspace.exists():
        return 0
    for p in workspace.iterdir():
        if not (p.is_dir() and re.match(r"^\d{2,3}_", p.name)):
            continue
        k = _extract_path_lineage(p.name)
        if k is not None and k > best:
            best = k
    return best


def create_numbered_experiment(
    root: Path,
    name: str,
    hypothesis: str = "",
    from_step: str | None = None,
    branch_of: str | None = None,
    *,
    enforce_predecessor_finalized: bool = True,
) -> dict:
    """Create the next numbered experiment folder + wire up its data link.

    Branching
    ---------
    Pass ``branch_of=<existing path_id>`` to fork a new analytical path off
    an existing step. The new folder name carries a ``_path_<k>`` lineage
    suffix (e.g. ``05_glmm_path_1``). Subsequent calls that branch off a
    step ALREADY carrying a lineage tag inherit it — the lineage flows
    through every downstream step on the branch. A brand-new fork
    receives the next free lineage number (max existing + 1).

    Dead-ends keep the existing ``__DEAD_END`` convention and stack with
    branch tags: ``05_glmm_path_1`` → ``05_glmm_path_1__DEAD_END``.

    Root validation
    ---------------
    Raises ``ValueError`` if ``root`` is not a Research-OS project (no
    ``.os_state/`` directory present). Prevents accidental pollution of
    arbitrary cwd when a misconfigured caller passes the wrong root.
    """
    if not (root / ".os_state").is_dir():
        raise ValueError(
            f"{root} is not a Research-OS project (no .os_state/ directory). "
            f"Run `research-os init` here first, or pass the correct project root."
        )
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # v1.3.0 round-3: enforce previous-step finalization. The user
    # surfaced a case where the AI created step 02 with step 01 left in
    # placeholder form (README + conclusions never filled, analysis.md
    # missing step 01 entry). The fix is to refuse to scaffold step N+1
    # while the most-recent main-path step (N) still has placeholder
    # text in its README. The caller can override via
    # ``enforce_predecessor_finalized=False`` — used by tests that
    # exercise multi-step scaffolding without going through the full
    # finalize workflow, and by ``sys_path_create`` when the researcher
    # explicitly authorises bypass (logged to workspace/logs/override_log.md).
    existing_main_steps = sorted(
        p for p in workspace.iterdir()
        if p.is_dir()
        and re.match(r"^\d{2,3}_", p.name)
        and _extract_path_lineage(p.name) is None
        and not p.name.endswith("__DEAD_END")
    )
    if enforce_predecessor_finalized and existing_main_steps and not branch_of:
        prev = existing_main_steps[-1]
        prev_readme = prev / "README.md"
        prev_conc = prev / "conclusions.md"
        if prev_readme.exists() and prev_conc.exists():
            r_txt = prev_readme.read_text()
            c_txt = prev_conc.read_text()
            placeholder_markers_readme = (
                "*(list inputs used)*",
                "*(name the method;",
                "*(the single most important result",
                "*(proceed | branch | dead-end)*",
            )
            placeholder_markers_conc = (
                "*(2-3 sentences",
                "*(method name",
                "*(the single most important",
            )
            unfilled_readme = sum(m in r_txt for m in placeholder_markers_readme)
            unfilled_conc = sum(m in c_txt for m in placeholder_markers_conc)
            if unfilled_readme >= 3 or unfilled_conc >= 2:
                raise ValueError(
                    f"Cannot scaffold the next step: previous step "
                    f"`{prev.name}` is still in placeholder form "
                    f"(README has {unfilled_readme} unfilled stubs, "
                    f"conclusions.md has {unfilled_conc}). Call "
                    f"`tool_path_finalize` on `{prev.name}` first to "
                    "lock its findings into workspace/analysis.md + "
                    "methods.md + tools.md + citations.md. If this is a "
                    "data-plumbing step that legitimately has nothing "
                    "to conclude, the AI should explicitly write 'No "
                    "substantive findings — see step purpose in README' "
                    "into the conclusions stubs before re-trying."
                )

    max_num = 0
    for p in workspace.iterdir():
        if p.is_dir() and re.match(r"^\d{2,3}_", p.name):
            try:
                max_num = max(max_num, int(p.name.split("_", 1)[0]))
            except ValueError:
                pass
    next_num = max_num + 1
    slug = slugify(name, "experiment")

    # Resolve branch lineage. Order of precedence:
    #   1. `branch_of` names an existing step → inherit its lineage if any,
    #      otherwise allocate a fresh lineage number.
    #   2. No `branch_of` → no lineage tag (main path).
    lineage: int | None = None
    parent_id: str | None = None
    if branch_of:
        # Allow callers to pass either the full `NN_slug` or the dead-end
        # variant; we resolve to the real on-disk folder.
        candidates = [branch_of, branch_of.removesuffix("__DEAD_END")]
        parent_dir: Path | None = None
        for cand in candidates:
            cand_dir = workspace / cand
            if cand_dir.is_dir():
                parent_dir = cand_dir
                parent_id = cand
                break
            # Tolerate when only the dead-end variant exists on disk.
            cand_dead = workspace / f"{cand}__DEAD_END"
            if cand_dead.is_dir():
                parent_dir = cand_dead
                parent_id = cand_dead.name
                break
        if parent_dir is None:
            raise ValueError(f"branch_of step '{branch_of}' not found in workspace/")
        inherited = _extract_path_lineage(parent_dir.name)
        lineage = inherited if inherited is not None else _max_path_lineage(workspace) + 1

    if lineage is not None:
        branch_id = f"{next_num:02d}_{slug}_path_{lineage}"
    else:
        branch_id = f"{next_num:02d}_{slug}"
    exp_dir = workspace / branch_id

    if exp_dir.exists():
        raise ValueError(f"Experiment '{branch_id}' already exists at {exp_dir}")

    check_write_permitted(exp_dir)

    # v1.3.0: `from_step` USED to `shutil.copytree` the whole source step
    # into the new step, leaving outputs/figures/tables/reports/scripts
    # all duplicated. That bloated the workspace, broke per-step
    # provenance (the new step's outputs/ contained the previous step's
    # artefacts before any code ran), and confused tool_path_finalize's
    # inventory. The intent of `from_step` is "wire data/input from this
    # step's output instead of the previous numbered step" — and now
    # that's all it does. Everything else is scaffolded fresh.
    exp_dir.mkdir(parents=True, exist_ok=True)
    for sub in EXPERIMENT_SUBDIRS:
        (exp_dir / sub).mkdir(parents=True, exist_ok=True)
    # v1.3.0: ALWAYS expose the project's inputs/raw_data/ via a
    # `data/project_inputs` symlink so an analysis step can reach the
    # original data when its `data/input` (which prefers the upstream
    # step's data/output/) is empty — common pitfall surfaced by the
    # genomics e2e where step 02 inherited step 01's empty data/output.
    raw_inputs = root / "inputs" / "raw_data"
    raw_inputs.mkdir(parents=True, exist_ok=True)
    project_inputs_link = exp_dir / "data" / "project_inputs"
    if not project_inputs_link.exists():
        try:
            project_inputs_link.symlink_to(raw_inputs.absolute())
        except OSError:
            pass
    if from_step:
        src_step_output = workspace / from_step / "data" / "output"
        src_step_output.mkdir(parents=True, exist_ok=True)
        data_input = exp_dir / "data" / "input"
        try:
            data_input.rmdir()
            data_input.symlink_to(src_step_output.absolute())
        except OSError:
            pass
    else:
        # Wire data/input/ — branch steps draw from their parent's output;
        # non-branch steps draw from the prior numbered step's output (or
        # raw_data for step 01).
        data_input = exp_dir / "data" / "input"
        if parent_id:
            parent_output = workspace / parent_id / "data" / "output"
            parent_output.mkdir(parents=True, exist_ok=True)
            try:
                data_input.rmdir()
                data_input.symlink_to(parent_output.absolute())
            except OSError:
                pass
        elif next_num == 1:
            raw_dir = root / "inputs" / "raw_data"
            raw_dir.mkdir(parents=True, exist_ok=True)
            try:
                data_input.rmdir()
                data_input.symlink_to(raw_dir.absolute())
            except OSError:
                pass
        else:
            prev_num = next_num - 1
            # Prefer main-path predecessors over branch siblings when both exist.
            prev_dirs = sorted(
                p for p in workspace.iterdir()
                if p.is_dir() and re.match(rf"^{prev_num:02d}_", p.name)
                and _extract_path_lineage(p.name) is None
            ) or sorted(
                p for p in workspace.iterdir()
                if p.is_dir() and re.match(rf"^{prev_num:02d}_", p.name)
            )
            if prev_dirs:
                prev_output = prev_dirs[0] / "data" / "output"
                prev_output.mkdir(parents=True, exist_ok=True)
                try:
                    data_input.rmdir()
                    data_input.symlink_to(prev_output.absolute())
                except OSError:
                    pass

    # README — the OVERVIEW reader: short, easy to read, no statistical jargon.
    # `conclusions.md` is the thorough version with method details.
    (exp_dir / "README.md").write_text(
        f"# Experiment: {branch_id}\n*Created: {now_iso()}*\n\n"
        "> **What this file is.** A short overview a non-expert reader can "
        "skim in 60 seconds. The detailed methodology, statistics, and "
        "limitations live in [`conclusions.md`](./conclusions.md). "
        "When the step is finished, run `tool_path_finalize` to populate "
        "the sections below from what was actually produced.\n\n"
        f"## Goal\n{hypothesis or name}\n\n"
        "## In plain English\n"
        "*(One paragraph. Imagine you're explaining this step to a colleague "
        "from a different field. What is being asked? Why does it matter? "
        "What did we find?)*\n\n"
        "## Input data\n- *(list inputs used)*\n\n"
        "## Methods (one line each)\n- *(name the method; full justification "
        "lives in `conclusions.md` and `literature/key_papers.md`)*\n\n"
        "## Headline finding\n- *(the single most important result — "
        "researchers should be able to quote this sentence verbatim)*\n\n"
        "## Outputs\n- *(figures / tables / reports produced)*\n\n"
        "## Decision\n- *(proceed | branch | dead-end)*\n\n"
        "## Read next\n"
        "- [`conclusions.md`](./conclusions.md) — full statistical results, "
        "limitations, decisions.\n"
        "- [`outputs/figures/`](./outputs/figures/) — every figure has a "
        "sibling `.caption.md` (technical) and `.summary.md` (plain English).\n"
        "- [`literature/key_papers.md`](./literature/key_papers.md) — the "
        "sources that anchor each decision.\n"
        "- [`context/notes.md`](./context/notes.md) — narrative "
        "rationale + hand-overs.\n"
    )
    # conclusions.md — the THOROUGH reader: full statistical detail, edge
    # cases, sensitivity checks, every limitation. Targets the same audience
    # as a journal Methods + Results + Discussion section.
    (exp_dir / "conclusions.md").write_text(
        f"# {branch_id} — Conclusions\n*Created: {now_iso()}*\n\n"
        "> **What this file is.** The full statistical record of the step. "
        "Method, assumption checks, every effect size, every limitation. "
        "If `README.md` is the elevator pitch, this is the full paper.\n\n"
        "## Plain-language summary\n"
        "*(2-3 sentences. What was tested, what was found, and the strength "
        "of the evidence — in language an undergraduate could follow. The "
        "dashboard's executive/teaching views surface this verbatim.)*\n\n"
        "## Findings\n"
        "*(2-5 quantitative bullets with numbers + units + 95% CI where "
        "applicable. Lead with effect sizes, not p-values. Plain frequencies "
        "preferred over percentages for risk communication — see the "
        "statistical glossary in `synthesis/dashboard.html`.)*\n\n"
        "## Hypothesis evidence\n"
        "*(For each hypothesis touched: H<id> status + one-line evidence + "
        "the figure / table the verdict rests on.)*\n\n"
        "## Methods (full detail)\n"
        "*(Dataset shape, transforms applied, model spec, parameter values, "
        "RNG seed, software versions. Reproducible: a competent reader "
        "should be able to re-run this from `scripts/` alone.)*\n\n"
        "## Methodological notes\n"
        "*(Assumption checks, sensitivity analyses, robustness — use "
        "supportive voice. e.g. \"the analysis would benefit from\" rather "
        "than \"is wrong\".)*\n\n"
        "## Limitations\n"
        "*(What this step cannot conclude, and why — sample size, design "
        "constraints, measurement bias, etc. Honest framing: \"no detectable "
        "difference\" beats \"no effect\" when underpowered.)*\n\n"
        "## Decision\n*(proceed | branch | dead-end)*\n\n"
        "## Next steps\n*(2-3 candidates with rationale)*\n"
    )

    _seed_step_subfolder_readmes(exp_dir, root, branch_id, next_num, from_step)

    # State update
    state = load_state(root)
    path_entry: dict[str, Any] = {
        "path_id": branch_id,
        "experiment_number": next_num,
        "status": "active",
        "hypothesis": hypothesis or name,
        "experiment_dir": f"workspace/{branch_id}",
        "created_at": now_iso(),
    }
    if lineage is not None:
        path_entry["path_lineage"] = lineage
    if parent_id:
        path_entry["branch_of"] = parent_id
    state["paths"][branch_id] = path_entry
    state["current_path"] = branch_id
    state["step"] = next_num
    if state.get("pipeline_stage") in (None, "init", "planned"):
        state["pipeline_stage"] = "execution"
    save_state(root, state)
    _update_manifest(root)
    _update_workflow_mermaid(root)
    _prune_old_checkpoints(root, keep=5)
    # Refresh DAG view best-effort; don't block step creation on failures.
    try:
        from research_os.tools.actions.state.path import workflow_dag

        workflow_dag(root)
    except Exception:
        pass

    return {
        "path_id": branch_id,
        "experiment_number": next_num,
        "experiment_dir": str(exp_dir.absolute()),
        "from_step": from_step,
        "branch_of": parent_id,
        "path_lineage": lineage,
        "paths_created": [str(exp_dir / sub) for sub in EXPERIMENT_SUBDIRS],
    }


# ---------------------------------------------------------------------------
# Workflow diagram + analysis.md helpers
# ---------------------------------------------------------------------------


def log_decision(
    context: str,
    selected: str,
    rationale: str,
    *,
    options_considered: list[str] | None = None,
    linked_literature: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Append a methodological decision to workspace/analysis.md."""
    root = _resolve_root(root)
    analysis_path = root / "workspace" / "analysis.md"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = (
        f"\n\n### Decision · {ts}\n"
        f"- **Context**: {context}\n"
        f"- **Selected**: {selected}\n"
        f"- **Rationale**: {rationale}\n"
    )
    if options_considered:
        entry += f"- **Options considered**: {', '.join(options_considered)}\n"
    if linked_literature:
        entry += f"- **Linked literature**: {', '.join(linked_literature)}\n"
    with open(analysis_path, "a") as f:
        f.write(entry)
    return {"logged": True, "path": "workspace/analysis.md"}


def _update_analysis_mermaid_block(root: Path, mermaid_content: str) -> None:
    analysis_path = root / "workspace" / "analysis.md"
    if not analysis_path.exists():
        return
    content = analysis_path.read_text()
    start = content.find("```mermaid")
    if start == -1:
        return
    end = content.find("```", start + 10)
    if end == -1:
        return
    end += 3
    new_block = f"```mermaid\n{mermaid_content}\n```"
    analysis_path.write_text(content[:start] + new_block + content[end:])


def _update_workflow_mermaid(root: Path) -> None:
    """Regenerate workspace/workflow.mermaid + analysis.md block + (optional) PNG.

    v1.3.1: refuse to write into ``root/workspace/`` unless ``root`` is a
    valid Research-OS project (``.os_state/`` present). The pollution
    surfaced in v1.3.0 e2e: a misconfigured caller wrote
    ``workspace/workflow.mermaid`` into the Research-OS source repo
    because the writer didn't validate root.
    """
    if not (root / ".os_state").is_dir():
        # v1.3.1 guard against the pollution surfaced in v1.3.0 e2e:
        # a misconfigured caller had written workspace/workflow.mermaid
        # into the Research-OS source repo because this writer didn't
        # check for `.os_state/`. Silent return is fine — the
        # consequence of NOT writing the mermaid in a non-project dir
        # is exactly what we want.
        return
    try:
        from research_os.tools.actions.state.path import list_paths

        paths = list_paths(root).get("paths", []) or []
    except Exception:
        paths = []

    lines = ["graph TD", "    init[Initialise Project]:::complete"]
    for p in paths:
        pid = re.sub(r"[^a-zA-Z0-9_]", "_", p["path_id"])
        label = p.get("name") or p["path_id"]
        status = p.get("status", "active")
        css = {"completed": "complete", "active": "running", "dead_end": "failed"}.get(status, "planned")
        lines.append(f"    {pid}[{label}]:::{css}")
        lines.append(f"    init --> {pid}")
    lines.extend(
        [
            "    classDef complete fill:#d4edda,stroke:#28a745",
            "    classDef running  fill:#fff3cd,stroke:#ffc107",
            "    classDef failed   fill:#f8d7da,stroke:#dc3545,stroke-dasharray: 5 5",
            "    classDef planned  fill:#e2e3e5,stroke:#6c757d",
        ]
    )
    text = "\n".join(lines)
    mermaid_path = root / "workspace" / "workflow.mermaid"
    mermaid_path.write_text(text + "\n")
    _update_analysis_mermaid_block(root, text)

    mmdc = shutil.which("mmdc")
    if mmdc:
        try:
            subprocess.run(
                [mmdc, "-i", str(mermaid_path), "-o", str(root / "workspace" / "workflow.png"), "-b", "white"],
                capture_output=True,
                timeout=60,
            )
        except Exception:
            pass


def generate_citations_md(root: Path) -> str:
    """Regenerate workspace/citations.md from project + per-step literature.

    Pulls entries from:
      - inputs/literature_index.yaml                 (project scope)
      - workspace/<step>/literature/literature_index.yaml (each step scope)
      - workspace/<step>/literature/*.meta.{yaml,json}    (sidecars)
    """
    citations_path = root / "workspace" / "citations.md"
    citations_path.parent.mkdir(parents=True, exist_ok=True)

    # citation_key → entry dict
    entries: dict[str, dict] = {}

    # 1. Project-level literature index.
    proj_index = root / "inputs" / "literature_index.yaml"
    if proj_index.exists() and yaml:
        try:
            data = yaml.safe_load(proj_index.read_text()) or {}
            for filename, meta in (data.get("entries") or {}).items():
                key = meta.get("citation_key") or filename
                meta = dict(meta)
                meta.setdefault("citation_key", key)
                meta.setdefault("filename", filename)
                meta.setdefault("scope", "project")
                entries[key] = meta
        except Exception:
            pass

    # 2. Per-step literature indexes + sidecars + conclusions.md
    # "References to ground" sections.
    workspace = root / "workspace"
    if workspace.exists():
        for step_dir in sorted(workspace.iterdir()):
            if not (step_dir.is_dir() and re.match(r"^\d{2,3}_", step_dir.name)):
                continue
            # 2a. v1.3.1: scrape `## References to ground` from each
            # step's conclusions.md so prose-cited refs (the AI's most
            # common pattern) make it into the project bibliography
            # without requiring a per-paper sidecar.
            conc = step_dir / "conclusions.md"
            if conc.exists():
                try:
                    txt = conc.read_text()
                    m = re.search(
                        r"##\s*References?\s+to\s+ground\s*\n(.+?)(?=^##|\Z)",
                        txt, re.MULTILINE | re.DOTALL | re.IGNORECASE,
                    )
                    if m:
                        for line in m.group(1).splitlines():
                            line = line.strip()
                            if not line.startswith(("-", "*", "+")):
                                continue
                            ref_text = re.sub(r"^[-*+]\s*", "", line).strip()
                            if len(ref_text) < 5:
                                continue
                            # Derive a citation key from the first author-year-ish chunk.
                            author_m = re.match(r"([A-Z][a-zA-Z'-]+)", ref_text)
                            year_m = re.search(r"(19|20)\d{2}", ref_text)
                            if author_m and year_m:
                                key = f"{author_m.group(1).lower()}{year_m.group(0)}"
                            else:
                                key = "conc_" + re.sub(r"[^a-z0-9]+", "_", ref_text[:30].lower()).strip("_")
                            entries.setdefault(key, {
                                "citation_key": key,
                                "title": ref_text,
                                "scope": f"step:{step_dir.name}",
                                "verified": False,
                                "source": "conclusions.md/References to ground",
                            })
                except Exception:
                    pass
            lit_dir = step_dir / "literature"
            if not lit_dir.exists():
                continue
            # First read the step's index (if present).
            step_idx = lit_dir / "literature_index.yaml"
            if step_idx.exists() and yaml:
                try:
                    data = yaml.safe_load(step_idx.read_text()) or {}
                    for filename, meta in (data.get("entries") or {}).items():
                        key = meta.get("citation_key") or filename
                        meta = dict(meta)
                        meta.setdefault("citation_key", key)
                        meta.setdefault("filename", filename)
                        meta.setdefault("scope", f"step:{step_dir.name}")
                        # Don't clobber project entries; step entries are
                        # secondary.
                        entries.setdefault(key, meta)
                except Exception:
                    pass
            # Then fall back to sidecar walk for PDFs that have no index entry.
            for pdf in lit_dir.iterdir():
                if not pdf.is_file() or pdf.suffix.lower() not in {".pdf", ".epub"}:
                    continue
                for ext in (".meta.yaml", ".meta.json"):
                    side = pdf.with_suffix(pdf.suffix + ext)
                    if side.exists():
                        try:
                            if ext == ".meta.yaml":
                                meta = (yaml.safe_load(side.read_text()) or {}) if yaml else {}
                            else:
                                meta = json.loads(side.read_text())
                        except Exception:
                            meta = {}
                        key = meta.get("citation_key") or re.sub(r"[\s-]+", "_", pdf.stem).lower()
                        meta["citation_key"] = key
                        meta["filename"] = pdf.name
                        meta.setdefault("scope", f"step:{step_dir.name}")
                        entries.setdefault(key, meta)
                        break

    lines = [
        "# Running Bibliography",
        "",
        "*Auto-generated from project + per-step literature.*",
        "",
    ]
    if entries:
        # Sort by scope (project first), then citation_key.
        ordered = sorted(
            entries.items(),
            key=lambda kv: (0 if kv[1].get("scope") == "project" else 1, kv[0]),
        )
        for key, meta in ordered:
            scope = meta.get("scope", "project")
            verified = meta.get("verified", bool(meta.get("doi") or meta.get("url")))
            sha = (meta.get("sha256") or "")[:12]
            badge = "✅ verified" if verified else "⏳ pending verification"
            lines.append(f"### `{key}`")
            lines.append(f"- Scope: `{scope}`")
            if meta.get("filename"):
                lines.append(f"- File: {meta['filename']}")
            if meta.get("title"):
                lines.append(f"- Title: {meta['title']}")
            if meta.get("authors"):
                authors = meta["authors"]
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                lines.append(f"- Authors: {authors}")
            if meta.get("year"):
                lines.append(f"- Year: {meta['year']}")
            if meta.get("doi"):
                lines.append(f"- DOI: `{meta['doi']}`")
            if meta.get("url"):
                lines.append(f"- URL: {meta['url']}")
            if sha:
                lines.append(f"- SHA-256: `{sha}`")
            lines.append(f"- Status: {badge}")
            lines.append("")
    else:
        lines.append(
            "*(No literature yet — drop PDFs in `inputs/literature/` or call "
            "`tool_literature_download` / `tool_literature_search_and_save`.)*"
        )
        lines.append("")

    citations_path.write_text("\n".join(lines) + "\n")
    return str(citations_path.absolute())


# ---------------------------------------------------------------------------
# Diff log (unused-but-kept hook for future state-diff watchers)
# ---------------------------------------------------------------------------


def state_diff_log_path(root: Path) -> Path:
    return root / "workspace" / "logs" / "state_changes.log"
