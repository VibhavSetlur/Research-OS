"""Structure integrity audit — verify an RO project is structurally sound and
nothing is broken, so the chaos we ordered STAYS ordered.

docs/STRUCTURE_INTEGRITY.md.

``workspace_repair`` heals the *scaffold* (missing dirs, corrupted state
ledger, stale path aliases). This module is the layer above it: it VERIFIES
that the research content is internally consistent — that numbered steps are
well-formed, that what STATE/the ledger claims matches what's on disk, that no
step's recorded outputs vanished, that the lineage isn't dangling. It answers
"is this project actually aligned, or has it silently drifted?".

It is READ-ONLY (it reports findings; healing is workspace_repair's job or an
explicit migrate/repair action). Each finding has a severity:

  * ``block``  — a real integrity break (a step references an output that
                 doesn't exist; a finalized step has no conclusions; the
                 ledger claims a step the workspace doesn't have).
  * ``warn``   — drift that won't break a run but should be fixed (an
                 un-finalized step with output present; an orphaned output
                 dir with no step).
  * ``info``   — structural notes.

The point: after a migration, an iteration, or a long unattended session, the
AI (or the daemon, on a timer) can run this and get a precise, actionable
"here's what's misaligned" list instead of discovering breakage mid-synthesis.

stdlib only. Pure inspection. Never raises.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STEP_RE = re.compile(r"^\d{2,3}_")


def _finding(severity: str, code: str, message: str, **ctx: Any) -> dict[str, Any]:
    f: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if ctx:
        f["context"] = ctx
    return f


def _step_dirs(workspace: Path) -> list[Path]:
    if not workspace.is_dir():
        return []
    return sorted(
        d for d in workspace.iterdir()
        if d.is_dir() and _STEP_RE.match(d.name)
    )


def _has_output(step: Path) -> bool:
    """True if a step has any recorded output (3.2 or legacy layout)."""
    for sub in ("data/next_step_output", "data/output", "outputs"):
        d = step / sub
        if d.is_dir() and any(d.rglob("*")):
            return True
    return False


def audit_structure(root: str | Path) -> dict[str, Any]:
    """Verify the structural integrity of an RO project. Read-only.

    Returns ``{status, findings, counts, ok}`` where ``ok`` is True only when
    there are zero BLOCK findings. Designed to be cheap enough to run on a
    timer (the daemon) and precise enough that each finding is directly
    actionable by the AI.
    """
    root = Path(root)
    findings: list[dict[str, Any]] = []

    if not root.is_dir():
        return {
            "status": "error",
            "message": f"not a directory: {root}",
            "ok": False,
            "findings": [],
        }

    # 1. Core scaffold present? (A missing core dir is a structure break that
    #    workspace_repair fixes — we flag it so the AI knows to run repair.)
    for core in ("inputs", "workspace", ".os_state"):
        if not (root / core).is_dir():
            findings.append(_finding(
                "block", "missing_core_dir",
                f"core directory '{core}/' is missing — run tool_workspace_repair",
                dir=core,
            ))

    workspace = root / "workspace"
    steps = _step_dirs(workspace)

    # 2. Step well-formedness.
    seen_numbers: dict[str, str] = {}
    for step in steps:
        name = step.name
        num = name.split("_", 1)[0]
        if num in seen_numbers:
            findings.append(_finding(
                "block", "duplicate_step_number",
                f"two steps share number {num}: '{seen_numbers[num]}' and '{name}'",
                number=num,
            ))
        else:
            seen_numbers[num] = name

        is_dead_end = name.endswith("__DEAD_END")
        is_incomplete = name.endswith(".incomplete")
        if is_dead_end or is_incomplete:
            continue  # dead-ends / incompletes are intentional, not breaks

        # A finalized step should have conclusions; flag a substantive-output
        # step that has none (it produced data but no recorded reasoning).
        conclusions = step / "conclusions.md"
        has_concl = conclusions.is_file() and conclusions.stat().st_size > 50
        if _has_output(step) and not has_concl:
            findings.append(_finding(
                "warn", "output_without_conclusions",
                f"step '{name}' has output but no conclusions.md — its result "
                "isn't interpreted (a synthesis will have nothing to cite)",
                step=name,
            ))

    # 3. Ledger ⇆ disk alignment. The state ledger records steps; verify each
    #    claimed step actually exists on disk (a claim with no dir is a break).
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
    except Exception:  # noqa: BLE001 - state unreadable is itself a finding
        state = None
        findings.append(_finding(
            "warn", "state_unreadable",
            "could not read the project state ledger (.os_state/state.json)",
        ))

    disk_step_names = {s.name for s in steps}
    if isinstance(state, dict):
        claimed = state.get("completed_steps") or state.get("steps") or []
        if isinstance(claimed, list):
            for entry in claimed:
                sid = entry.get("id") if isinstance(entry, dict) else entry
                if not sid:
                    continue
                # Match by leading number or exact name.
                num = str(sid).split("_", 1)[0]
                if str(sid) not in disk_step_names and num not in seen_numbers:
                    findings.append(_finding(
                        "block", "ledger_step_missing_on_disk",
                        f"state ledger claims step '{sid}' but no matching "
                        "workspace directory exists",
                        step=str(sid),
                    ))

    # 4. Orphaned output dirs: an outputs/ tree directly under workspace/ (not
    #    inside a numbered step) is misplaced.
    if workspace.is_dir():
        for child in workspace.iterdir():
            if child.is_dir() and child.name in ("outputs", "output", "data"):
                findings.append(_finding(
                    "warn", "orphaned_output_dir",
                    f"'{child.name}/' sits directly under workspace/ instead of "
                    "inside a numbered step — its provenance is ambiguous",
                    dir=child.name,
                ))

    # 5. Mode integrity (B5): config mode vs state mode drift, and whether the
    #    active mode's required scaffold surface is actually present. A project
    #    flipped via raw sys_config(workspace.mode=…) before the transition tool
    #    existed (or a hand-edited config) is silently inconsistent — catch it.
    try:
        from research_os.tools.actions.state.config import get_workspace_mode
        from research_os.project_ops import (
            SCAFFOLD_PROFILES, load_state as _ls,
        )
        cfg_mode = get_workspace_mode(root)
        try:
            state_mode = str((_ls(root) or {}).get("workspace_mode") or cfg_mode)
        except Exception:
            state_mode = cfg_mode
        if cfg_mode != state_mode:
            findings.append(_finding(
                "warn", "mode_drift",
                f"config workspace.mode='{cfg_mode}' but state says '{state_mode}' "
                "— a half-applied mode change. Heal with "
                f"sys_workspace_mode(operation='transition', to='{cfg_mode}', confirm=true).",
                config_mode=cfg_mode, state_mode=state_mode,
            ))
        prof = SCAFFOLD_PROFILES.get(cfg_mode)
        if prof:
            missing_surface = [d for d in prof["eager_dirs"] if not (root / d).is_dir()]
            if missing_surface:
                findings.append(_finding(
                    "warn", "missing_mode_surface",
                    f"mode is '{cfg_mode}' but its required surface is missing "
                    f"({', '.join(missing_surface)}) — run "
                    f"sys_workspace_mode(operation='transition', to='{cfg_mode}', confirm=true) "
                    "to create it additively.",
                    mode=cfg_mode, missing=missing_surface,
                ))
    except Exception:
        pass  # mode check is best-effort; never break the structure audit

    # 6. Script naming convention (4.0.3): the daemon WATCHES that analysis
    #    scripts follow <NN>[a-z]_<snake_name>_v<k>.<ext> with <NN> = the step's
    #    number. The AI repeatedly drifts on this; surfacing it here means the
    #    daemon's periodic self-check (health_notes.run_self_check) and sys_boot
    #    both flag it, so it gets caught + fixed early instead of leaving a step
    #    un-navigable. Each violation carries the exact conforming rename.
    try:
        from research_os.tools.actions.audit.script_naming import (
            audit_script_naming,
        )
        naming = audit_script_naming(root)
        for v in naming.get("blockers", []):
            findings.append(_finding(
                "warn", "script_naming",
                f"script does not follow the naming convention: {v} "
                "(convention: workspace/<NN>_<slug>/scripts/"
                "<NN>[a-z]_<snake_name>_v<k>.<ext>).",
            ))
    except Exception:
        pass  # naming check is best-effort; never break the structure audit

    # 7. Provenance integrity (4.1.x): the daemon WATCHES whether recorded
    #    inputs/outputs still match on disk. An output built from an input that
    #    has since changed is STALE — a silent reproducibility break the AI
    #    won't notice. Surfacing it here means the daemon's self-check + sys_boot
    #    flag stale results early instead of a reviewer finding them.
    try:
        from research_os.tools.actions.state.provenance import (
            verify_provenance_integrity,
        )
        prov = verify_provenance_integrity(root)
        for f in prov.get("findings", []):
            sev = "block" if f.get("severity") == "block" else "warn"
            findings.append(_finding(
                sev, f.get("code", "provenance_drift"),
                f.get("message", "provenance integrity issue"),
            ))
    except Exception:
        pass  # provenance check is best-effort; never break the structure audit

    # 8. Mode-aware project health: the daemon stays involved in EVERY workspace
    #    mode, not just analysis. tool_build needs its eval/spec/decisions,
    #    notebook outputs shouldn't be stale vs data, multi_study needs its
    #    shared commons, exploration shouldn't strand promote-worthy probes,
    #    hybrid's tool half needs tests. Same engine feeds the daemon self-check,
    #    sys_boot, and tool_structure_audit, so all three agree.
    try:
        from research_os.tools.actions.state.mode_health import mode_health_findings

        for f in mode_health_findings(root):
            sev = f.get("severity", "info")
            findings.append(_finding(
                sev if sev in ("block", "warn", "info") else "info",
                f.get("code", "mode_health"),
                f.get("message", "mode-specific health issue"),
            ))
    except Exception:
        pass  # mode-health check is best-effort; never break the structure audit

    counts: dict[str, int] = {"block": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "status": "success",
        "root": str(root),
        "step_count": len(steps),
        "findings": findings,
        "counts": counts,
        "ok": counts["block"] == 0,
        "note": (
            "Structure is sound."
            if counts["block"] == 0 and counts["warn"] == 0 else
            f"{counts['block']} integrity break(s), {counts['warn']} drift "
            "warning(s). BLOCK findings should be fixed before building on this "
            "project (tool_workspace_repair heals scaffold/state; content "
            "findings need the AI to act)."
        ),
    }
