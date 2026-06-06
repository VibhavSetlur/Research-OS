"""Handlers for the meta_workspace sub-domain.

Carved out of handlers/meta.py to stay under the 600-line ceiling.
"""
from __future__ import annotations

from .._handlers_runtime import *  # noqa: F401,F403
# mem_log dispatcher delegates to a methodology handler — pull it into scope.

__all__ = [
    "_handle_sys_workspace_scaffold",
    "_handle_sys_workspace_tree",
    "_handle_sys_state_get",
    "_handle_sys_file_read",
    "_handle_sys_file_write",
    "_handle_sys_file_list",
    "_handle_sys_file_delete",
    "_handle_sys_file_validate_md",
    "_handle_sys_path_create",
    "_handle_sys_path_abandon",
    "_handle_sys_path_list",
    "_handle_tool_path_finalize",
    "_handle_tool_synthesis_curate_figures",
    "_handle_sys_export_share_archive",
    "_handle_sys_checkpoint_create",
    "_handle_sys_checkpoint_rollback",
    "_handle_sys_checkpoint_list",
    "_handle_sys_path",
]

def _handle_sys_workspace_scaffold(name, arguments, root):
    ide = arguments.get("ide", "all")
    valid = [
        "cursor", "claude", "antigravity", "opencode", "vscode",
        "windsurf", "continue", "aider",
    ]
    ide_flags = (
        valid
        if ide == "all"
        else [i.strip() for i in ide.split(",") if i.strip() in valid]
    )
    scaffold_minimal_workspace(
        root,
        arguments.get("project_name", "Research Project"),
        ide_flags=ide_flags,
        copy_agents=True,
    )
    if (root / ".os_state").exists() and (root / "workspace").exists():
        _profile_inputs(root)
    return _text(_success({"scaffolded": True, "ide_flags": ide_flags}))


def _handle_sys_workspace_tree(name, arguments, root):
    depth = arguments.get("depth", 3)
    include_files = arguments.get("include_files", True)
    tree = _build_tree(root / "workspace", depth, include_files)
    return _text(_success({"tree": tree}))


def _handle_sys_state_get(name, arguments, root):
    fmt = (arguments.get("format") or "full").lower()
    state = load_state(root)
    if fmt == "minimal":
        from research_os.state.state_ledger import ResearchLedger

        ledger = ResearchLedger(root / ".os_state" / "state_ledger.json")
        return _text(_success({"minimal_context": ledger.get_project_summary(max_tokens=450)}))
    if fmt == "markdown":
        md_path = root / ".os_state" / "os_state.md"
        if not md_path.exists():
            return _text(_error("os_state.md missing — run a tool that mutates state first."))
        return _text(_success({"markdown": md_path.read_text()}))
    # full (lean projection — strip very large fields)
    paths = state.get("paths", {})
    out: dict[str, Any] = {
        "project_name": state.get("project_name") or state.get("project", ""),
        "pipeline_stage": state.get("pipeline_stage", state.get("phase", "init")),
        "step": state.get("step", 0),
        "current_path": state.get("current_path", "main"),
    }
    # Only include collection-valued fields when they have content —
    # empty list/dict/None on a fresh project just burns tokens.
    paths_summary = {k: v.get("status") for k, v in paths.items()}
    if paths_summary:
        out["paths_summary"] = paths_summary
    hypotheses = state.get("active_hypotheses") or []
    if hypotheses:
        out["active_hypotheses"] = hypotheses
    if state.get("resumable_from"):
        out["resumable_from"] = state["resumable_from"]
    return _text(_success(out))


def _handle_sys_file_read(name, arguments, root):
    p = root / arguments["filepath"]
    if not p.exists() or not p.is_file():
        return _text(_error(f"File not found: {arguments['filepath']}"))
    if p.stat().st_size > 50 * 1024 * 1024:
        return _text(_error("File too large (>50 MB). Use tool_data_sample for tabular data."))
    return _text(_success({"content": p.read_text(errors="replace")}))


def _handle_sys_file_write(name, arguments, root):
    p = root / arguments["filepath"]
    force = arguments.get("force", False)
    rel = str(p.relative_to(root)) if str(p).startswith(str(root)) else str(p)

    if rel.startswith("inputs/raw_data") or rel.startswith("inputs/literature"):
        if not rel.endswith("literature_index.yaml"):
            return _text(_error("WriteProtectedError: inputs/raw_data and inputs/literature are immutable."))
    if rel.startswith("synthesis/") and p.exists() and not force:
        return _text(_error("synthesis/ files exist — pass force=true to overwrite."))

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(arguments["content"])
    if rel.startswith("workspace/"):
        _update_manifest(root)
    return _text(_success({"written": True, "checksum": compute_file_hash(p)}))


def _handle_sys_file_list(name, arguments, root):
    from research_os.project_ops import LAZY_DIRS

    rel = arguments["directory"]
    p = root / rel
    if not p.exists() or not p.is_dir():
        # A lazy directory that hasn't been materialised yet is NOT an
        # error — it just hasn't received its first artefact. Return an
        # empty list with a hint so protocols can detect the empty state
        # without retry loops.
        if rel.strip("/") in LAZY_DIRS:
            return _text(_success({
                "files": [],
                "empty": True,
                "lazy_dir": True,
                "hint": (
                    f"`{rel}` is created on first write. "
                    "Drop files here (or via the wizard) to materialise it."
                ),
            }))
        return _text(_error("Directory not found"))
    files = [str(f.relative_to(root)) for f in p.rglob("*") if f.is_file()]
    return _text(_success({"files": files, "empty": not files}))


def _handle_sys_file_delete(name, arguments, root):
    p = root / arguments["filepath"]
    if not p.exists():
        return _text(_error("File or directory not found"))
    if p.is_file():
        p.unlink()
        return _text(_success({"deleted": True}))
    try:
        p.rmdir()
        return _text(_success({"deleted": True, "type": "directory"}))
    except OSError as e:
        return _text(_error(f"Cannot delete directory: {e}"))


def _handle_sys_file_validate_md(name, arguments, root):
    from research_os.tools.actions.audit.md_audit import validate_md_template

    res = validate_md_template(arguments["filepath"], arguments["protocol_name"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "Validation failed")))


def _handle_sys_path_create(name, arguments, root):
    from research_os.project_ops import create_numbered_experiment

    try:
        # The MCP handler defaults to enforcing
        # previous-step finalization. Researcher can opt out by passing
        # `allow_unfinalized_predecessor=true` (logged to override_log).
        allow_bypass = bool(arguments.get("allow_unfinalized_predecessor", False))
        res = create_numbered_experiment(
            root,
            arguments["name"],
            hypothesis=arguments.get("hypothesis", ""),
            branch_of=arguments.get("branch_of"),
            from_step=arguments.get("from_step"),
            enforce_predecessor_finalized=not allow_bypass,
        )
        if allow_bypass:
            from research_os.project_ops import log_override
            log_override(
                root,
                tool="sys_path_create",
                gate="enforce_predecessor_finalized",
                rationale=arguments.get("override_rationale"),
                extra={"new_step": res.get("path_id")},
            )
        return _text(_success(res))
    except Exception as e:
        return _text(_error(str(e)))


def _handle_sys_path_abandon(name, arguments, root):
    res = abandon_path(arguments["path_name"], arguments["rationale"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "abandon failed")))


def _handle_sys_path_list(name, arguments, root):
    return _text(_success(list_paths(root)))


def _handle_tool_path_finalize(name, arguments, root):
    from research_os.tools.actions.audit.step_literature import (
        audit_step_literature,
    )
    from research_os.tools.actions.state.path import finalize_path

    # First-gate
    # literature-loop check. Closes the gap where
    # literature_per_step was documented as pipeline-mandatory but
    # never enforced (autopilot skipped it). Override via
    # override_literature_gate=true + override_rationale.
    override_lit = bool(arguments.get("override_literature_gate", False))
    override_rationale = str(arguments.get("override_rationale", "")).strip()
    path_name = arguments.get("path_name")
    step_id = path_name if (path_name and path_name != "main") else None
    try:
        lit_audit = audit_step_literature(root, step_id=step_id)
    except Exception as e:
        lit_audit = {"status": "error", "message": str(e), "blockers": []}
    if (
        lit_audit.get("status") == "error"
        and lit_audit.get("blockers")
        and not (override_lit and override_rationale)
    ):
        msg = (
            f"tool_path_finalize blocked by tool_audit_step_literature "
            f"({len(lit_audit['blockers'])} blocker(s)). "
            "Either run research/literature_per_step OR pass "
            "override_literature_gate=true + override_rationale=... to "
            "proceed. See workspace/logs/step_literature_audit.md."
        )
        return _text(_error({
            "message": msg,
            "literature_audit": lit_audit,
        }))

    res = finalize_path(arguments.get("path_name"), root)
    if isinstance(res, dict):
        res.setdefault("literature_audit", lit_audit)
        if override_lit and override_rationale:
            res["literature_override"] = {
                "override_literature_gate": True,
                "override_rationale": override_rationale,
            }
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "finalize failed")))


def _handle_tool_synthesis_curate_figures(name, arguments, root):
    from research_os.tools.actions.synthesis.dashboard import curate_figures

    res = curate_figures(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "curate failed")))


def _handle_sys_export_share_archive(name, arguments, root):
    """Run scripts/export_share_archive.py for the project root."""
    import subprocess as _sp
    import sys as _sys

    script = root / "scripts" / "export_share_archive.py"
    if not script.exists():
        # Lazy-scaffold the script if the project pre-dates the feature.
        try:
            from research_os.project_ops import _write_sharing_scripts, load_state
            project_name = (load_state(root) or {}).get("project_name") or root.name
            _write_sharing_scripts(root, project_name)
        except Exception as e:
            return _text(_error(f"export script missing and could not be scaffolded: {e}"))

    cmd = [_sys.executable, str(script)]
    if arguments.get("out"):
        cmd += ["--out", str(arguments["out"])]
    if arguments.get("include_raw_data"):
        cmd += ["--include-raw-data"]
    try:
        res = _sp.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(root))
        if res.returncode != 0:
            return _text(_error(
                f"export failed (rc={res.returncode}):\n"
                f"stdout:\n{res.stdout[-1000:]}\n"
                f"stderr:\n{res.stderr[-1000:]}"
            ))
        return _text(_success({"status": "success", "stdout": res.stdout.strip()}))
    except _sp.TimeoutExpired:
        return _text(_error("export timed out (>180s)"))
    except Exception as e:
        return _text(_error(f"export failed: {e}"))


def _handle_sys_checkpoint_create(name, arguments, root):
    res = create_checkpoint(arguments.get("description", "manual"), root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "checkpoint failed")))


def _handle_sys_checkpoint_rollback(name, arguments, root):
    res = rollback_checkpoint(arguments["checkpoint_id"], root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "rollback failed")))


def _handle_sys_checkpoint_list(name, arguments, root):
    res = list_checkpoints(root)
    if res.get("status") == "success":
        return _text(_success(res))
    return _text(_error(res.get("message", "checkpoint list failed")))


def _handle_sys_path(name, arguments, root):
    """Unified path dispatcher (create | abandon | list)."""
    legacy = {
        "sys_path_create": "create",
        "sys_path_abandon": "abandon",
        "sys_path_list": "list",
    }
    operation = arguments.get("operation") or legacy.get(name)
    if not operation:
        return _text(_error(
            "sys_path requires operation='create'|'abandon'|'list'"
        ))
    if operation == "create":
        return _handle_sys_path_create(name, arguments, root)
    if operation == "abandon":
        return _handle_sys_path_abandon(name, arguments, root)
    if operation == "list":
        return _handle_sys_path_list(name, arguments, root)
    return _text(_error(f"Unknown sys_path operation '{operation}'"))


HANDLERS = {
    "sys_workspace_scaffold": _handle_sys_workspace_scaffold,
    "sys_workspace_tree": _handle_sys_workspace_tree,
    "sys_state_get": _handle_sys_state_get,
    "sys_file_read": _handle_sys_file_read,
    "sys_file_write": _handle_sys_file_write,
    "sys_file_list": _handle_sys_file_list,
    "sys_file_delete": _handle_sys_file_delete,
    "sys_file_validate_md": _handle_sys_file_validate_md,
    "tool_path_finalize": _handle_tool_path_finalize,
    "tool_synthesis_curate_figures": _handle_tool_synthesis_curate_figures,
    "sys_export_share_archive": _handle_sys_export_share_archive,
    "sys_checkpoint_create": _handle_sys_checkpoint_create,
    "sys_checkpoint_rollback": _handle_sys_checkpoint_rollback,
    "sys_checkpoint_list": _handle_sys_checkpoint_list,
    "sys_path": _handle_sys_path,
}
