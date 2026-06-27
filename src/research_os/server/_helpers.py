"""Shared helper functions used by multiple handler modules.

These are NOT MCP tools themselves — they're internal utilities that
several handlers call (e.g. _log_search records a search-query event,
_read_profile fetches the researcher autonomy/expertise config in <100 tokens,
_latest_protocol_for_step resolves a step ID back to its owning protocol).

Lives alongside _handlers_runtime.py and is imported via
``from ._helpers import *`` inside each handlers/*.py module.
"""
from __future__ import annotations

import json
from pathlib import Path

from ._handlers_runtime import get_config, now_iso


__all__ = [
    "_log_search",
    "_read_profile",
    "_recommended_action_for_route",
    "_build_tree",
    "_latest_protocol_for_step",
    "_build_tier_progress",
    "_AUDIT_DISPATCH",
    "_STEP_DISPATCH",
    "_STEP_PIPELINE_DISPATCH",
]


def _build_tier_progress(root) -> dict:
    """Tier-based progress summary for tool_audit_master.

    Reads ``workspace/.os_state/current_tier.json`` and the protocol
    execution log to count how many distinct protocols have fired per
    tier. Returns a compact summary suitable for the audit_master
    response body (the v2 markdown writer is not modified).
    """
    from research_os.protocols._tiers import TIERS, tier_position
    from research_os.tools.actions.protocol import get_protocol_history
    from research_os.tools.actions.router import _resolve_tier
    from research_os.tools.actions.state.tier_state import (
        read_tier_state,
        tier_direction,
    )

    state = read_tier_state(root)
    current = state.get("current_tier")
    history = list(state.get("history") or [])

    # Per-tier protocol-fire counts from the execution log.
    per_tier_protocols: dict[str, set[str]] = {t: set() for t in TIERS}
    try:
        entries = (get_protocol_history(root, limit=500).get("entries") or [])
    except Exception:
        entries = []
    for ent in entries:
        pn = ent.get("protocol") or ent.get("protocol_name")
        if not isinstance(pn, str) or not pn:
            continue
        tier = _resolve_tier(pn)
        if tier and tier in per_tier_protocols:
            per_tier_protocols[tier].add(pn)

    per_tier_summary = []
    for t in TIERS:
        names = sorted(per_tier_protocols[t])
        per_tier_summary.append({
            "tier": t,
            "position": tier_position(t),
            "n_protocols_fired": len(names),
            "protocols": names[:5],  # cap the list — full set is in the log
            "is_current": (t == current),
        })

    last_transition = history[-1] if history else None
    direction = None
    if last_transition:
        direction = tier_direction(last_transition.get("from"), last_transition.get("to"))

    return {
        "current_tier": current,
        "current_tier_position": tier_position(current) if current else None,
        "n_tiers_visited": sum(1 for t in TIERS if per_tier_protocols[t]),
        "per_tier": per_tier_summary,
        "last_transition": last_transition,
        "last_transition_direction": direction,
        "transition_count": len(history),
    }


# ── Audit / dashboard / step / pipeline dispatch tables ────────────
# These map operation/(scope,dimension) tuples to private handler names
# (resolved at call time inside the consolidated tool_audit / tool_dashboard
# / tool_step / tool_step_pipeline dispatchers).
_AUDIT_DISPATCH: dict[tuple[str, str], str] = {
    # scope=step
    ("step", "assumptions"):            "_handle_tool_audit_assumptions",
    ("step", "code_quality"):           "_handle_tool_audit_code_quality",
    ("step", "completeness"):           "_handle_tool_audit_step_completeness",
    ("step", "evalue"):                 "_handle_tool_audit_evalue",
    ("step", "figure"):                 "_handle_tool_audit_figure",
    ("step", "figure_full"):            "_handle_tool_audit_figure_full",
    ("step", "figure_interactivity"):   "_handle_tool_audit_figure_interactivity",
    ("step", "literature"):             "_handle_tool_audit_step_literature",
    ("step", "power"):                  "_handle_tool_audit_power",
    ("step", "reproducibility"):        "_handle_tool_audit_reproducibility",
    ("step", "script_naming"):          "_handle_tool_audit_script_naming",
    ("step", "provenance_integrity"):   "_handle_tool_audit_provenance_integrity",
    # scope=project
    ("project", "citations"):           "_handle_tool_audit_citations",
    ("project", "claims"):              "_handle_tool_audit_claims",
    ("project", "cliches"):             "_handle_tool_audit_cliches",
    ("project", "coherence"):           "_handle_tool_audit_coherence",
    ("project", "cross_deliverable"):   "_handle_tool_audit_cross_deliverable_consistency",
    ("project", "prose"):               "_handle_tool_audit_prose",
    ("project", "version_coherence"):   "_handle_tool_audit_version_coherence",
    # scope=synthesis
    ("synthesis", "all"):               "_handle_tool_audit_synthesis",
    ("synthesis", "dashboard_content"): "_handle_tool_audit_dashboard_content",
    ("synthesis", "figure_coverage"):   "_handle_tool_audit_figure_coverage",
    ("synthesis", "reviewer_responses"): "_handle_tool_audit_reviewer_responses",
    # scope=tool — the tool_build analog of the analysis gates. Mode-aware:
    # a no-op outside workspace.mode='tool_build'.
    ("tool", "tests"):                  "_handle_tool_audit_tool_tests",
    ("tool", "git_hygiene"):            "_handle_tool_audit_tool_git_hygiene",
    ("tool", "build"):                  "_handle_tool_audit_tool_build",
}


# tool_dashboard removed in v2.3.0; the dispatch table is gone with it.
# (Old aliases still resolve via _REMOVED_TOOLS to a redirect message.)


_STEP_DISPATCH: dict[str, str] = {
    "iterate":           "_handle_tool_step_iterate",
    "iterations_list":   "_handle_tool_step_iterations_list",
    "revision_options":  "_handle_tool_step_revision_options",
    "env_lock":          "_handle_tool_step_env_lock",
}


_STEP_PIPELINE_DISPATCH: dict[str, str] = {
    "define":  "_handle_tool_step_pipeline_define",
    "run":     "_handle_tool_step_pipeline_run",
    "status":  "_handle_tool_step_pipeline_status",
    "diagram": "_handle_tool_step_pipeline_diagram",
}


def _log_search(root: Path, tool_name: str, query: str, count: int) -> None:
    log_path = root / "workspace" / "logs" / "searches.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": now_iso(),
                    "tool": tool_name,
                    "query": query,
                    "results_count": count,
                }
            )
            + "\n"
        )


def _read_profile(root: Path) -> dict:
    """Return autonomy_level, expertise_level, model_profile, context_class
    in <100 tokens.

    ``ai.model_profile`` and ``ai.context_class`` (W20) override the legacy
    top-level ``model_profile`` when present, so callers can opt into the
    new ai-side knobs without breaking existing configs.
    """
    cfg = get_config(root)
    if cfg.get("status") != "success":
        return {
            "autonomy_level": "adaptive",
            "expertise_level": "intermediate",
            "model_profile": "medium",
            "context_class": "short",
        }
    config = cfg.get("config", {})
    ai_block = config.get("ai") or {}
    return {
        "autonomy_level": config.get("interaction", {}).get(
            "autonomy_level", "adaptive"
        ),
        "expertise_level": config.get("researcher", {}).get(
            "expertise_level", "intermediate"
        ),
        "model_profile": (
            ai_block.get("model_profile")
            or config.get("model_profile", "medium")
        ),
        "context_class": ai_block.get("context_class", "short"),
    }


def _recommended_action_for_route(res: dict) -> str:
    """Phase-9 cross-cutting: name the exact next tool to call.

    The router already returns method / confidence / primary_protocol /
    shortcut_tool / decomposition / ask_user. The AI then has to reason
    about "what do I call next?" — a hop we can collapse by naming it
    directly in the response.

    Priority:
      1. ask_user set → ask the researcher first.
      2. shortcut_tool present → call the shortcut directly.
      3. primary_protocol resolved → load it summary-first.
      4. No primary, but alternatives exist → call tool_semantic_route to
         eyeball the ranked candidates.
      5. Total dead end → fall back to tool_route again or sys_help.
    """
    if res.get("ask_user"):
        return "ask_user: " + str(res["ask_user"])
    shortcut = res.get("shortcut_tool")
    if shortcut:
        return f"{shortcut}(...)"
    primary = res.get("primary_protocol")
    if primary:
        return (
            f"sys_protocol_get(protocol_name='{primary}', format='summary')"
        )
    alts = res.get("alternatives") or []
    if alts:
        return "tool_semantic_route(prompt=<refined>, top_k=5)"
    return "sys_help(topic=...)"


def _build_tree(path: Path, depth: int, include_files: bool) -> dict:
    # `<= 0` (not `== 0`) so a negative depth that slips past the handler
    # clamp still terminates instead of recursing the whole subtree.
    if depth <= 0:
        return {"_truncated": True}
    result: dict = {}
    try:
        for item in sorted(path.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                result[f"{item.name}/"] = _build_tree(item, depth - 1, include_files)
            elif include_files:
                result[item.name] = None
    except PermissionError:
        return {"_error": "permission_denied"}
    return result


def _latest_protocol_for_step(root, step_id: str) -> str | None:
    """Resolve the protocol most likely "owned" by ``step_id``.

    Heuristics, cheapest first (all best-effort):
      1. ``.os_state/active_plan.json`` — the most recent route's primary.
      2. The latest entry in ``protocol_execution_log.jsonl``.

    Returns the bare protocol name (e.g. ``guidance/analysis_plan``) or
    None when nothing was logged yet.
    """
    import json as _json
    plan_path = root / ".os_state" / "active_plan.json"
    if plan_path.exists():
        try:
            plan = _json.loads(plan_path.read_text())
            pp = plan.get("primary_protocol")
            if isinstance(pp, str) and pp:
                return pp
        except Exception:
            pass
    log_path = root / ".os_state" / "protocol_execution_log.jsonl"
    if log_path.exists():
        try:
            last_proto = None
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = _json.loads(line)
                except Exception:
                    continue
                pn = entry.get("protocol") or entry.get("protocol_name")
                if pn:
                    last_proto = pn
            if last_proto:
                return last_proto
        except Exception:
            pass
    return None
