"""Researcher-facing notifications and session handoff."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from research_os.project_ops import load_state, now_iso

logger = logging.getLogger("research_os.tools.interaction")


def notify_researcher(message: str, level: str, root: Path) -> dict[str, Any]:
    """Log a notification under ``workspace/logs/notifications.log``."""
    try:
        log_path = root / "workspace" / "logs" / "notifications.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[{now_iso()}] [{level.upper()}] {message}\n")
        return {"status": "success", "message": "Notification logged."}
    except Exception as e:
        logger.error(f"Notify failed: {e}")
        return {"status": "error", "message": str(e)}


def session_handoff(root: Path) -> dict[str, Any]:
    """Generate a structured markdown handoff document.

    Enriches the basic markdown with: a checkpoint snapshot id (rollback
    safety net), open hypotheses, running background tasks, the tail of
    methods.md, dead-end lessons, and an explicit "Notes for the next AI"
    addendum. A fresh AI with no conversation history can read this file
    plus AGENTS.md and continue the project.
    """
    try:
        from research_os.tools.actions.state.checkpoint import create_checkpoint
        from research_os.tools.actions.state.path import list_paths

        state = load_state(root)
        paths_data = list_paths(root)
        paths = paths_data.get("paths", []) or []
        active_paths = [p for p in paths if p["status"] == "active"]
        completed_paths = [p for p in paths if p["status"] == "completed"]
        dead_paths = [p for p in paths if p["status"] == "dead_end"]
        active_path = active_paths[0] if active_paths else None

        # Tail of narrative logs.
        def _tail(p: Path, n: int = 30) -> str:
            if not p.exists():
                return ""
            try:
                return "\n".join(p.read_text(errors="replace").splitlines()[-n:])
            except OSError:
                return ""

        analysis_tail = _tail(root / "workspace" / "analysis.md", 30)
        methods_tail = _tail(root / "workspace" / "methods.md", 20)

        # Pending work in active path.
        pending: list[str] = []
        if active_path:
            scripts_dir = root / "workspace" / active_path["path_id"] / "scripts"
            if scripts_dir.exists():
                pending = [f.name for f in scripts_dir.iterdir() if f.is_file()]

        from research_os.tools.actions.protocol import get_next_protocol

        next_info = get_next_protocol(root)

        project_name = state.get("project_name") or state.get(
            "project", "Research Project"
        )
        current_path = state.get("current_path", "main")
        pipeline_stage = state.get("pipeline_stage", state.get("phase", "init"))

        # Hypotheses.
        hypotheses = state.get("active_hypotheses", []) or []
        hyp_lines: list[str] = []
        for h in hypotheses:
            if isinstance(h, dict):
                hyp_lines.append(
                    f"- **{h.get('id', '?')}** ({h.get('status', '?')}): "
                    f"{h.get('statement', '')}"
                )

        # Background tasks.
        running_tasks: list[dict[str, Any]] = []
        try:
            from research_os.tools.actions.exec.tasks import task_list

            tasks = task_list(root).get("tasks", []) or []
            running_tasks = [t for t in tasks if t.get("task_status") == "running"]
        except Exception:
            running_tasks = []

        # Take a checkpoint so the handoff is rollback-safe.
        cp = create_checkpoint(f"handoff {now_iso()}", root)
        cp_id = cp.get("checkpoint_id", "(checkpoint failed)")

        # Dead-end lesson tags.
        dead_lessons: list[str] = []
        for d in dead_paths:
            conc = root / "workspace" / d["path_id"] / "conclusions.md"
            if conc.exists():
                head = conc.read_text(errors="replace").splitlines()[:6]
                dead_lessons.append(
                    f"- `{d['path_id']}`: " + " ".join(head)[:200]
                )

        # Surface the researcher_config in the handoff so a fresh AI
        # sees autonomy / quality_gate_policy / ambiguity posture /
        # model_profile / writing prefs / api keys present without
        # separately calling sys_config_get. Mask secrets.
        try:
            from research_os.tools.actions.state.config import get_config
            cfg_res = get_config(root)
            cfg = cfg_res.get("config", {}) if cfg_res.get("status") == "success" else {}
        except Exception:
            cfg = {}
        config_summary_lines = []
        if cfg:
            interaction = cfg.get("interaction", {}) or {}
            rg = cfg.get("research_goal", {}) or {}
            wp = cfg.get("writing_preferences", {}) or {}
            researcher = cfg.get("researcher", {}) or {}
            api_keys = cfg.get("api_keys", {}) or {}
            keys_set = [k for k, v in api_keys.items() if isinstance(v, str) and v.strip()]
            config_summary_lines.extend([
                f"- Autonomy: `{interaction.get('autonomy_level', 'supervised')}` "
                f"· quality_gate: `{interaction.get('quality_gate_policy', 'enforce')}` "
                f"· ambiguity: `{interaction.get('ambiguity_posture', 'ask_when_uncertain')}`",
                f"- Model profile: `{cfg.get('model_profile', 'medium')}` "
                f"· shared_server: `{(cfg.get('runtime') or {}).get('shared_server', False)}`",
                f"- Writing: `{wp.get('citation_style', 'apa')}` / `{wp.get('language', 'en-US')}`",
                f"- Output types requested: {rg.get('output_types') or '(none specified)'}",
                f"- Target venue: `{rg.get('target_venue') or '(unset)'}`",
                f"- Researcher: {researcher.get('name') or '(unset)'}"
                + (f" ({researcher.get('institution')})" if researcher.get('institution') else "")
                + (f" · {researcher.get('orcid')}" if researcher.get('orcid') else ""),
                f"- API keys configured: {', '.join(keys_set) if keys_set else '(none)'}",
            ])

        content_lines = [
            f"# Session Handoff — {project_name}",
            f"Generated: {now_iso()}",
            f"Rollback checkpoint: `{cp_id}` (use `sys_checkpoint_rollback`)",
            "",
            "## Researcher config (consult before acting)",
        ]
        content_lines.extend(config_summary_lines or ["- (no researcher_config loaded)"])
        content_lines.extend([
            "",
            "## State",
            f"- Current path: `{current_path}`",
            f"- Pipeline stage: `{pipeline_stage}`",
            f"- Active paths: {len(active_paths)} "
            f"· completed: {len(completed_paths)} "
            f"· dead-end: {len(dead_paths)}",
            f"- Next protocol per pipeline: "
            f"`{next_info.get('next_protocol') or '(pipeline complete)'}`",
            "",
            "## Open hypotheses",
        ])
        content_lines.extend(hyp_lines or ["- (none registered)"])

        content_lines.extend(["", "## Background tasks still running"])
        if not running_tasks:
            content_lines.append("- (none)")
        for t in running_tasks:
            content_lines.append(
                f"- `{t.get('task_id')}` (pid {t.get('pid')}) — "
                f"{t.get('description') or t.get('command')}"
            )

        content_lines.extend([
            "",
            "## Pending scripts in active path",
        ])
        content_lines.extend(
            [f"- `{f}`" for f in pending] if pending else ["- (none)"]
        )

        content_lines.extend([
            "",
            "## Recent analysis log (tail)",
            "```",
            analysis_tail or "(empty)",
            "```",
            "",
            "## Recent methods (tail)",
            "```",
            methods_tail or "(empty)",
            "```",
            "",
            "## Dead-end lessons to avoid repeating",
        ])
        content_lines.extend(dead_lessons or ["- (none on record)"])

        content_lines.extend([
            "",
            "## Resume recipe (paste into the next chat)",
            "",
            f"> I'm resuming Research OS project **{project_name}**.",
            f"> Active path: `{current_path}` · stage: `{pipeline_stage}`.",
            "> Step 1: `sys_protocol_get(\"guidance/session_boot\")`",
            "> Step 2: `tool_session_resume` — it will read this handoff "
            "and the state ledger.",
            "> Step 3: Confirm with me before any new tool call.",
            "",
            "## Notes for the next AI",
            "- Read `AGENTS.md` and `inputs/researcher_config.yaml` first.",
            "- Critical assumptions still untested are listed under "
            "`active_hypotheses` (status=testing).",
            "- Dead-end folders are kept on disk — do NOT re-try those "
            "methods without a justification logged via `mem_log(kind='decision')`.",
            f"- The rollback checkpoint above (`{cp_id}`) is your safety net.",
        ])
        content = "\n".join(content_lines) + "\n"

        handoff_path = (
            root
            / ".os_state"
            / "handoffs"
            / f"handoff_{now_iso()[:19].replace(':', '-')}.md"
        )
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(content)
        return {
            "status": "success",
            "handoff_path": str(handoff_path.relative_to(root)),
            "checkpoint_id": cp_id,
            "running_tasks": len(running_tasks),
            "active_paths": len(active_paths),
            "content": content,
        }
    except Exception as e:
        logger.exception("session_handoff failed")
        return {"status": "error", "message": str(e)}
