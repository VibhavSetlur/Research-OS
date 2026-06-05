"""Protocol loader, pipeline ordering, and execution log.

A protocol is a YAML file under ``src/research_os/protocols/`` describing a
sequence of steps the AI should take. Each protocol has:

* ``id``, ``name``, ``description``     — metadata
* ``trigger``                            — when the AI should run it
* ``prerequisites``                      — what must be true before running
* ``steps``                              — ordered list of {id, name, description}
* ``expected_outputs``                   — file paths the protocol should produce
* ``next_protocol``                      — what runs after (or null for terminal)
* ``on_failure``                         — fallback protocol when expected outputs missing

Light mode (``model_profile=small``) auto-trims verbose blocks
(``examples``, ``rationale``, ``model_adaptations``) inside the loader so that
small models don't drown in tokens. There is no separate ``light/`` folder —
all protocols are single source of truth.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("research_os.tools.protocol")

PROTOCOLS_DIR = Path(__file__).parent.parent.parent / "protocols"
PROTOCOL_LOG_FILE = "protocol_execution_log.jsonl"
DEPRECATIONS_LOG_FILE = "deprecations.log"


def _log_redirect(source: str, target: str, params: dict | None = None) -> None:
    """Append a redirect event to .os_state/deprecations.log (best-effort).

    Resolves project root via RESEARCH_OS_WORKSPACE env var; falls back to
    walking up CWD for `.os_state/`. Silently no-ops if no workspace.
    """
    import os
    root: Path | None = None
    env_root = os.environ.get("RESEARCH_OS_WORKSPACE", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if candidate.exists():
            root = candidate
    if root is None:
        cur = Path.cwd().resolve()
        for p in [cur, *cur.parents]:
            if (p / ".os_state").exists():
                root = p
                break
    if root is None:
        return
    log_dir = root / ".os_state"
    if not log_dir.exists():
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "protocol_redirect",
        "source": source,
        "target": target,
        "params": params or {},
    }
    try:
        with open(log_dir / DEPRECATIONS_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Execution log
# ---------------------------------------------------------------------------


def log_protocol_execution(
    root: Path, protocol_name: str, status: str, details: str = ""
) -> dict:
    """Append a structured entry to the protocol execution log."""
    log_path = root / ".os_state" / PROTOCOL_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol_name,
        "status": status,
        "details": details,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"status": "success", "entry": entry}


def get_protocol_history(root: Path, limit: int = 20) -> dict:
    """Return the last N protocol execution log entries."""
    log_path = root / ".os_state" / PROTOCOL_LOG_FILE
    entries: list[dict] = []
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {"entries": entries[-limit:], "total": len(entries)}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


_LIGHT_DROP_KEYS = {
    "model_adaptations",
    "examples",
    "rationale",
    "rationale_examples",
    "templates",
    "code_templates",
    "long_description",
}

_LEAN_MAX_STEPS = 3
_LEAN_MAX_DESC_CHARS = 200
_LEAN_DROP_KEYS = _LIGHT_DROP_KEYS | {
    "pedagogical_prelude",
    "model_adaptations",
    "alternates",
    "anti_patterns",
}


def _lean_step(step: dict) -> dict:
    """Shrink one step to its load-bearing fields."""
    if not isinstance(step, dict):
        return step
    out: dict = {}
    for key, value in step.items():
        if key in _LEAN_DROP_KEYS:
            continue
        if key == "description" and isinstance(value, str):
            value = value.strip()
            if len(value) > _LEAN_MAX_DESC_CHARS:
                value = value[:_LEAN_MAX_DESC_CHARS].rsplit(" ", 1)[0] + " …"
        if key in {"sub_steps", "optional_sub_steps"}:
            # Drop optional sub-steps; keep mandatory ones if listed under sub_steps.
            if key == "optional_sub_steps":
                continue
        out[key] = value
    return out


def _auto_distill_lean(data: dict) -> dict:
    """Build a lean variant from `full` when no explicit lean_variant block exists."""
    steps = data.get("steps", []) or []
    capped: list[dict] = []
    for step in steps[:_LEAN_MAX_STEPS]:
        if isinstance(step, dict):
            capped.append(_lean_step(step))
        else:
            capped.append(step)
    out = {
        "id": data.get("id"),
        "name": data.get("name", ""),
        "description": (data.get("description") or "").split("\n\n")[0],
        "trigger": data.get("trigger", ""),
        "steps": capped,
        "expected_outputs": data.get("expected_outputs", []),
        "next_protocol": data.get("next_protocol"),
        "_lean_source": "auto-distilled",
        "_dropped_steps": max(0, len(steps) - _LEAN_MAX_STEPS),
        "_path": data.get("_path"),
    }
    return out


def _find_protocol_file(name: str) -> Path | None:
    """Locate ``<protocols>/<category>/<name>.yaml``.

    Accepts ``"guidance/session_boot"`` or bare ``"session_boot"``.
    Registry / index files (prefix ``_``) are NOT addressable as protocols.
    """
    if "/" in name:
        candidate = PROTOCOLS_DIR / f"{name}.yaml"
        return candidate if candidate.exists() else None

    for yaml_file in PROTOCOLS_DIR.rglob("*.yaml"):
        # Skip any legacy light/ folder that might still be on disk.
        if "light" in yaml_file.parts:
            continue
        if yaml_file.name.startswith("_"):
            continue
        if yaml_file.stem == name:
            return yaml_file
    return None


def _trim_for_light(data: dict) -> dict:
    """Drop verbose keys at the top level and within each step."""
    out: dict = {}
    for key, value in data.items():
        if key in _LIGHT_DROP_KEYS:
            continue
        if key == "steps" and isinstance(value, list):
            out["steps"] = []
            for step in value:
                if not isinstance(step, dict):
                    out["steps"].append(step)
                    continue
                out["steps"].append(
                    {k: v for k, v in step.items() if k not in _LIGHT_DROP_KEYS}
                )
        else:
            out[key] = value
    return out


_PROTOCOL_COMPLETION_BLOCK = {
    "id": "protocol_completion",
    "name": "Complete & Log Protocol",
    "description": (
        "Final mandatory step.\n"
        "1. Call sys_protocol_log with status='completed' and a one-line details summary.\n"
        "   If the protocol BLOCKED on a gate, log status='failed' with the blocker count "
        "   (the next session can resume cleanly from the same point).\n"
        "2. Call sys_checkpoint_create with description='<protocol> completed' — a rollback target\n"
        "   the researcher can return to if a downstream step regresses.\n"
        "3. Call sys_protocol_next to find the pipeline-recommended next protocol. If the\n"
        "   researcher's next message redirects, prefer tool_route on their message over\n"
        "   the pipeline pointer.\n"
        "4. Briefly summarise to the researcher in ONE sentence: what changed + what's next.\n"
        "   Skip the summary on shortcut-tool calls (sys_help, sys_protocol_list, etc.) — the\n"
        "   result is already the answer.\n"
        "\n"
        "Grounding check: if this protocol involved methodology or claims, confirm at\n"
        "least one tool_search_* call was made and logged to workspace/logs/searches.log.\n"
        "If grounding is missing AND the protocol commits a methodology decision, run\n"
        "tool_grounding_verify before declaring completion — ungrounded commitments\n"
        "surface in the master audit and slow the eventual synthesis.\n"
        "\n"
        "Override-log check: if the protocol bypassed any quality gate this turn\n"
        "(override_completeness_gate / override_gate), confirm workspace/logs/override_log.md\n"
        "captured the rationale. The pre-submission audit will re-surface every unresolved\n"
        "bypass — silent bypasses become RED at publish time."
    ),
}


def _inject_completion_step(data: dict) -> dict:
    """Append the standard completion step if not already present."""
    steps = data.get("steps", []) or []
    has_completion = any(
        isinstance(s, dict) and s.get("id") == "protocol_completion" for s in steps
    )
    if not has_completion:
        steps = list(steps) + [_PROTOCOL_COMPLETION_BLOCK]
        data["steps"] = steps
    return data


def load_protocol(
    name: str,
    model_profile: str = "medium",
    *,
    format: str = "full",
    step_id: str | None = None,
    _redirect_chain: tuple[str, ...] | None = None,
) -> dict:
    """Load a protocol YAML and post-process it.

    Args:
        name: ``"guidance/project_startup"`` or bare ``"project_startup"``.
        model_profile: ``small`` | ``medium`` | ``large``. ``small`` trims verbose
                       keys (model_adaptations, examples, etc.) to save tokens.
        format: ``full`` (default) | ``summary`` | ``step`` | ``lean`` | ``dryrun``.
                * ``summary`` returns id + name + description + step
                  headings + expected_outputs + next_protocol + quality_bar
                  — roughly 300 tokens vs 2K for the full load.
                * ``step`` requires ``step_id`` and returns just that step
                  body plus its position in the protocol.
                * ``lean`` returns the protocol's explicit ``lean_variant:``
                  block if present, else auto-distills (cap at 3 steps,
                  drop optional sub-steps, trim step descriptions to 200
                  chars). For small / fast models.
                * ``dryrun`` returns the protocol's full tool-call
                  sequence with predicted arg shapes, without executing.
                  For supervised review before commit.
        step_id: which step to load when ``format='step'``.
    """
    file = _find_protocol_file(name)
    if not file:
        raise FileNotFoundError(f"Protocol '{name}' not found in {PROTOCOLS_DIR}")
    with open(file) as f:
        data = yaml.safe_load(f) or {}

    # Redirect-stub support: a stub YAML carries `redirect_to: <target_name>`
    # (and optional
    # `redirect_params: {key: value}`). The stub is reduced to a thin
    # alias: the target is loaded, the source name is recorded on the
    # result for traceability, and any params are injected into the
    # `_redirect_params` field for the caller. Loops are detected via
    # a seen-set; cycles raise. Stubs must NOT carry `steps:`; the
    # preflight check enforces that.
    redirect_target = data.get("redirect_to")
    if isinstance(redirect_target, str) and redirect_target.strip():
        target = redirect_target.strip()
        params = data.get("redirect_params", {}) or {}
        try:
            _log_redirect(name, target, params)
        except Exception:
            pass
        # Cycle detection across the whole redirect chain (not just self).
        chain = (_redirect_chain or ()) + (name, target)
        target_norm = target.split("/")[-1]
        name_norm = name.split("/")[-1]
        chain_norms = {c.split("/")[-1] for c in (_redirect_chain or ())}
        if target_norm in chain_norms or target_norm == name_norm:
            raise ValueError(
                f"Redirect cycle detected: {' -> '.join(chain)}"
            )
        resolved = load_protocol(
            target,
            model_profile=model_profile,
            format=format,
            step_id=step_id,
            _redirect_chain=chain,
        )
        if isinstance(resolved, dict):
            resolved.setdefault("_redirected_from", name)
            if params:
                resolved.setdefault("_redirect_params", params)
        return resolved

    # Inject any per-profile step overrides explicitly attached as
    # ``model_adaptations: {small: {step_id: {key: value}}}``.
    adaptations = data.get("model_adaptations", {})
    if isinstance(adaptations, dict) and model_profile in adaptations:
        overrides = adaptations.get(model_profile) or {}
        if isinstance(overrides, dict):
            for sid, patch in overrides.items():
                if not isinstance(patch, dict):
                    continue
                for step in data.get("steps", []):
                    if isinstance(step, dict) and step.get("id") == sid:
                        step.update(patch)

    if model_profile == "small":
        data = _trim_for_light(data)

    data = _inject_completion_step(data)
    data.setdefault("name", name.split("/")[-1])
    data.setdefault("_path", str(file.relative_to(PROTOCOLS_DIR)))

    if format == "summary":
        steps = data.get("steps", []) or []
        return {
            "id": data.get("id", name.split("/")[-1]),
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "trigger": data.get("trigger", ""),
            "prerequisites": data.get("prerequisites", []),
            "step_summary": [
                {"id": s.get("id", ""), "name": s.get("name", "")}
                for s in steps
                if isinstance(s, dict)
            ],
            "expected_outputs": data.get("expected_outputs", []),
            "quality_bar": data.get("quality_bar", ""),
            "next_protocol": data.get("next_protocol"),
            "on_failure": data.get("on_failure"),
            "_path": data.get("_path"),
            "_load_hint": (
                f"Loaded as summary. For one specific step body call "
                f"sys_protocol_get name='{name}' format='step' step_id='<id>'. "
                f"For the full YAML use format='full'."
            ),
        }

    if format == "lean":
        explicit = data.get("lean_variant")
        if isinstance(explicit, dict) and explicit:
            out = dict(explicit)
            out.setdefault("id", data.get("id"))
            out.setdefault("name", data.get("name", ""))
            out.setdefault("_path", data.get("_path"))
            out["_lean_source"] = "explicit"
            return out
        return _auto_distill_lean(data)

    if format == "dryrun":
        import re
        steps = data.get("steps", []) or []
        tool_call_pat = re.compile(r"\b((?:sys|tool|mem)_[a-z0-9_]+)\b")
        sequence: list[dict] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            desc = step.get("description") or ""
            tool_calls = sorted(set(tool_call_pat.findall(desc)))
            sequence.append({
                "step_id": step.get("id"),
                "name": step.get("name", ""),
                "predicted_tool_calls": tool_calls,
            })
        return {
            "id": data.get("id"),
            "name": data.get("name", ""),
            "format": "dryrun",
            "sequence": sequence,
            "total_steps": len(sequence),
            "total_predicted_tool_calls": sum(len(s["predicted_tool_calls"]) for s in sequence),
            "_load_hint": (
                "dryrun preview — no tool calls were executed. "
                "Use format='full' to load the actual protocol body."
            ),
        }

    if format == "step":
        if not step_id:
            raise ValueError("format='step' requires step_id")
        steps = data.get("steps", []) or []
        match = next(
            (s for s in steps if isinstance(s, dict) and s.get("id") == step_id),
            None,
        )
        if not match:
            raise ValueError(
                f"Step '{step_id}' not in protocol '{name}'. "
                f"Available: {[s.get('id') for s in steps if isinstance(s, dict)]}"
            )
        step_ids = [s.get("id") for s in steps if isinstance(s, dict)]
        idx = step_ids.index(step_id)
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "step": match,
            "position": idx + 1,
            "of": len(step_ids),
            "previous_step_id": step_ids[idx - 1] if idx > 0 else None,
            "next_step_id": step_ids[idx + 1] if idx + 1 < len(step_ids) else None,
        }

    return data


def list_protocols() -> list[dict]:
    """Return every protocol with name and one-line description."""
    out: list[dict] = []
    for yaml_file in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in yaml_file.parts:
            continue
        # Skip registry/index files (e.g. _router_index.yaml).
        if yaml_file.name.startswith("_"):
            continue
        rel = yaml_file.relative_to(PROTOCOLS_DIR).with_suffix("")
        name = str(rel).replace("\\", "/")
        summary = ""
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f) or {}
            summary = (data.get("description") or "").split("\n")[0]
        except Exception:
            pass
        out.append({"name": name, "summary": summary})
    return out


# ---------------------------------------------------------------------------
# Pipeline ordering
# ---------------------------------------------------------------------------

# Each entry: (protocol_name, predicate(root) -> bool) — "done" means the AI
# can move on. Predicates check both the execution log AND key output files,
# so the pipeline survives a workspace migrated from outside Research OS.


def _has(root: Path, *paths: str) -> bool:
    return all((root / p).exists() for p in paths)


def _has_any(root: Path, glob_pattern: str) -> bool:
    return bool(list(root.glob(glob_pattern)))


def _has_experiment(root: Path, marker: str = "conclusions.md") -> bool:
    workspace = root / "workspace"
    if not workspace.exists():
        return False
    for child in workspace.iterdir():
        if child.is_dir() and child.name[:2].isdigit() and "__DEAD_END" not in child.name:
            mfile = child / marker
            if mfile.exists() and len(mfile.read_text()) > 200:
                return True
    return False


def _protocol_completed(root: Path, name: str) -> bool:
    """True if the protocol has logged a 'completed' status."""
    log = root / ".os_state" / PROTOCOL_LOG_FILE
    if not log.exists():
        return False
    try:
        for line in log.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("protocol") == name and entry.get("status") == "completed":
                return True
    except Exception:
        return False
    return False


def _any_protocol_logged(root: Path) -> bool:
    log = root / ".os_state" / PROTOCOL_LOG_FILE
    if not log.exists():
        return False
    try:
        return any(line.strip() for line in log.read_text().splitlines())
    except Exception:
        return False


def _has_real_research_question(root: Path) -> bool:
    """True if docs/research_overview.md has been filled in (placeholder gone)."""
    p = root / "docs" / "research_overview.md"
    if not p.exists():
        return False
    text = p.read_text().lower()
    # Any of these substrings signals an unfilled placeholder.
    placeholder_markers = (
        "(to be",
        "(blank",
        "(to be confirmed",
        "fill out the intake",
        "*(to be determined)*",
    )
    if any(marker in text for marker in placeholder_markers):
        return False
    # Beyond a placeholder, require at least some real prose.
    return len(text.strip()) > 200


# Each step is considered done when EITHER the protocol logged completion OR
# its hallmark on-disk artifact exists with real content.

PIPELINE: list[tuple[str, Any]] = [
    (
        "guidance/session_boot",
        lambda r: _any_protocol_logged(r) or _protocol_completed(r, "guidance/session_boot"),
    ),
    (
        "guidance/project_startup",
        lambda r: _protocol_completed(r, "guidance/project_startup")
        or _has_real_research_question(r),
    ),
    (
        "domain/domain_analysis",
        lambda r: _protocol_completed(r, "domain/domain_analysis")
        or _has(r, "docs/domain_summary.md"),
    ),
    (
        "domain/research_design",
        lambda r: _protocol_completed(r, "domain/research_design")
        or _has(r, "docs/research_design.md"),
    ),
    (
        "methodology/methodology_selection",
        lambda r: _protocol_completed(r, "methodology/methodology_selection")
        or (
            _has(r, "workspace/methods.md")
            and (r / "workspace" / "methods.md").stat().st_size > 400
        ),
    ),
    (
        "literature/literature_search",
        lambda r: _protocol_completed(r, "literature/literature_search")
        or (_has(r, "inputs/literature_index.yaml") and _has(r, "workspace/citations.md") and (r / "workspace" / "citations.md").stat().st_size > 200),
    ),
    (
        "guidance/analysis_plan",
        lambda r: _has_experiment(r, "conclusions.md"),
    ),
    (
        "reproducibility/reproducibility",
        lambda r: _protocol_completed(r, "reproducibility/reproducibility")
        or _has_any(r, "workspace/*/environment/requirements.txt"),
    ),
    (
        "audit/audit_and_validation",
        lambda r: _protocol_completed(r, "audit/audit_and_validation")
        or _has(r, "workspace/logs/audit_report.md"),
    ),
    (
        "synthesis/synthesis_paper",
        lambda r: _has(r, "synthesis/paper.md")
        and (r / "synthesis" / "paper.md").stat().st_size > 1000,
    ),
]


def get_next_protocol(root: Path) -> dict:
    """Return the recommended next protocol based on workspace state."""
    for protocol_name, predicate in PIPELINE:
        try:
            done = predicate(root)
        except Exception:
            done = False
        if not done:
            return {
                "next_protocol": protocol_name,
                "reason": f"Outputs of '{protocol_name}' not yet present.",
                "pipeline_position": [name for name, _ in PIPELINE].index(protocol_name) + 1,
                "pipeline_total": len(PIPELINE),
            }
    return {
        "next_protocol": None,
        "reason": "Pipeline complete — paper, audit, and reproducibility outputs all present.",
        "pipeline_position": len(PIPELINE),
        "pipeline_total": len(PIPELINE),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_protocol(name: str, root: Path | None = None) -> dict:
    """Check each declared expected_output against the filesystem."""
    try:
        data = load_protocol(name)
        expected_outputs = data.get("expected_outputs", []) or []

        checklist: list[dict] = []
        all_passed = True

        if root:
            for item in expected_outputs:
                if isinstance(item, dict):
                    path_str = item.get("path", "")
                elif ":" in item:
                    path_str = item.split(":")[0].strip()
                else:
                    path_str = item.strip()

                if not path_str:
                    continue

                if "*" in path_str or "{" in path_str:
                    # Use glob — drop curly placeholders ({step_name}) since we
                    # only know step folders by pattern.
                    expanded = path_str.replace("{step_number}", "??").replace(
                        "{step_name}", "*"
                    )
                    matches = list(root.glob(expanded.lstrip("/")))
                    status = "pass" if matches else "fail"
                else:
                    status = "pass" if (root / path_str).exists() else "fail"

                checklist.append({"item": path_str, "status": status})
                if status == "fail":
                    all_passed = False

        return {
            "protocol": name,
            "checklist": checklist,
            "all_passed": all_passed,
            "expected_count": len(expected_outputs),
            "next_protocol": data.get("next_protocol"),
        }
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"validate_protocol failed: {e}")
        return {"error": str(e)}
