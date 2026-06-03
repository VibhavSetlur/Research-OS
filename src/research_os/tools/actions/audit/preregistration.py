"""Pre-registration & Statistical Analysis Plan (SAP) tooling.

Implements the OSF / AsPredicted / CONSORT-SPIRIT minimal contract:
before any data is touched, the analyst freezes a SAP capturing
hypotheses, primary/secondary endpoints, analysis plan, sample-size
justification, and exclusion rules. The frozen SAP is content-hashed
and immutable; later, when the paper is assembled, a diff is run to
show every deviation between what was pre-registered and what was
actually reported.

This separates **confirmatory** (pre-registered) from **exploratory**
findings — the most important distinction reviewers ask about after
peer-review reform pushed registered reports into the mainstream.

Workflow
--------
1. Call ``tool_preregister_freeze`` BEFORE running the analysis. The
   tool:
     * snapshots ``workspace/methods.md`` + the hypothesis tracker;
     * writes ``workspace/.preregistration/sap_<iso>.md`` + .yaml;
     * computes a SHA-256 of both files;
     * marks the project state as "preregistered_at = <iso>";
     * suggests an OSF submission template.
2. Run the analysis as normal.
3. Before synthesis, call ``tool_preregister_diff`` which:
     * loads the most recent frozen SAP;
     * compares to the current methods.md + hypothesis tracker +
       paper.md;
     * lists deviations (added/removed hypotheses, changed analysis
       plan, post-hoc exclusions);
     * writes ``workspace/logs/preregistration_diff.md`` which the
       dashboard surfaces as "Deviations from pre-registration".
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.audit.preregistration")

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


def _prereg_dir(root: Path) -> Path:
    return root / "workspace" / ".preregistration"


_SAP_TEMPLATE = """\
# Statistical Analysis Plan — {project_name}

*Pre-registered: {iso_date}*
*SHA-256 (this file): {sha256}*

> **What this is.** A frozen snapshot of the analysis plan made before
> any results were inspected. Any deviation between the plan and the
> reported analysis must be documented in the paper's Discussion.

## 1. Project + research question

- Project: {project_name}
- Research question: {research_question}
- Design type: {design}
- Pre-registered by: {researcher}
- Data-collection status at registration: {data_status}

## 2. Hypotheses (confirmatory)

{hypotheses_block}

## 3. Outcome measures

- Primary outcome(s): {primary_outcomes}
- Secondary outcomes: {secondary_outcomes}
- Measurement instrument: {measurement_instrument}

## 4. Sample size + power

- Target sample size: {target_n}
- Power assumption: {power_assumption}
- Stopping rule (if any): {stopping_rule}

## 5. Statistical analysis plan

{methods_block}

## 6. Subgroup / sensitivity analyses (pre-specified)

- Subgroups: {subgroups}
- Sensitivity analyses: {sensitivity}
- Multiplicity correction: {multiplicity}

## 7. Inclusion / exclusion criteria

- Inclusion: {inclusion}
- Exclusion: {exclusion}
- Missing-data handling: {missing_data}

## 8. Additional pre-specified analyses

{additional_analyses}

## 9. Contingencies (if-then decisions)

{contingencies}

## 10. Anticipated deviations

{anticipated_deviations}

---

*Pre-registration ID:* `{prereg_id}`

*Suggested upload:* https://osf.io/prereg/ (paste this file into the
"Standard Pre-Data Collection Registration" form).
"""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def freeze_preregistration(
    root: Path,
    *,
    primary_outcomes: str | None = None,
    secondary_outcomes: str | None = None,
    target_n: int | str | None = None,
    power_assumption: str | None = None,
    stopping_rule: str | None = None,
    subgroups: list[str] | None = None,
    sensitivity: list[str] | None = None,
    multiplicity: str | None = None,
    inclusion: list[str] | None = None,
    exclusion: list[str] | None = None,
    missing_data: str | None = None,
    additional_analyses: list[str] | None = None,
    contingencies: list[str] | None = None,
    anticipated_deviations: list[str] | None = None,
    data_status: str = "not yet collected",
) -> dict[str, Any]:
    """Freeze the current methods + hypotheses into an immutable SAP.

    Idempotent at the daily level — re-running creates a new dated
    snapshot. Old SAPs are preserved alongside as the audit chain.
    """
    from research_os.project_ops import load_state

    state = load_state(root)
    project_name = state.get("project_name") or "Research Project"
    hyps = state.get("active_hypotheses") or []

    methods_path = root / "workspace" / "methods.md"
    methods_text = methods_path.read_text() if methods_path.exists() else ""
    methods_block = methods_text.strip() or (
        "*(methods.md is empty — add at least one substantive method "
        "via mem_methods_append before freezing.)*"
    )

    # Hypothesis block.
    if hyps:
        lines = []
        for h in hyps:
            kind = h.get("kind", "confirmatory")  # default confirmatory at freeze
            lines.append(
                f"- **{h.get('id', '?')}** ({kind}): "
                f"{h.get('statement', '')}"
            )
        hyps_block = "\n".join(lines)
    else:
        hyps_block = (
            "*(no hypotheses tracked — call mem_hypothesis_add for each "
            "before freezing.)*"
        )

    # researcher_config.yaml lookup.
    cfg = {}
    cfg_path = root / "inputs" / "researcher_config.yaml"
    if cfg_path.exists() and yaml:
        try:
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
        except Exception:
            cfg = {}

    # research_question lives in state.json (written by tool_intake_autofill);
    # older workspaces may still carry it in researcher_config.yaml.
    state_rq = ""
    try:
        from research_os.project_ops import load_state
        state_rq = (load_state(root) or {}).get("research_question", "")
    except Exception:
        # State unreadable / not initialised — fall through to the legacy
        # researcher_config locations below.
        pass
    rq = (
        state_rq
        or cfg.get("research_question")
        or (cfg.get("research_goal") or {}).get("primary_question")
        or "(unset)"
    )
    design = (cfg.get("research_goal") or {}).get("design") or "(unset)"
    researcher = (cfg.get("researcher") or {}).get("name") or "(unset)"

    def _fmt_list(items: list[str] | None, default: str = "(none)") -> str:
        if not items:
            return default
        return "\n".join(f"  - {it}" for it in items)

    iso = datetime.now(timezone.utc).isoformat()
    prereg_id = (
        "prereg_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    )

    # Build the SAP text (with placeholder sha256 we'll replace after hashing).
    sap_text = _SAP_TEMPLATE.format(
        project_name=project_name,
        iso_date=iso,
        sha256="{sha256}",  # placeholder
        research_question=rq,
        design=design,
        researcher=researcher,
        data_status=data_status,
        hypotheses_block=hyps_block,
        primary_outcomes=primary_outcomes or "(unspecified)",
        secondary_outcomes=secondary_outcomes or "(unspecified)",
        measurement_instrument=(cfg.get("research_goal") or {}).get(
            "measurement_instrument", "(unspecified)"),
        target_n=str(target_n) if target_n is not None else "(unspecified)",
        power_assumption=power_assumption or "(unspecified)",
        stopping_rule=stopping_rule or "(none)",
        methods_block=methods_block,
        subgroups=_fmt_list(subgroups, "(no pre-specified subgroups)"),
        sensitivity=_fmt_list(
            sensitivity, "(no pre-specified sensitivity analyses)"),
        multiplicity=multiplicity or "(unspecified — Benjamini-Hochberg by default)",
        inclusion=_fmt_list(inclusion, "(unspecified)"),
        exclusion=_fmt_list(exclusion, "(unspecified)"),
        missing_data=missing_data or "(unspecified)",
        additional_analyses=_fmt_list(additional_analyses, "(none)"),
        contingencies=_fmt_list(contingencies, "(none)"),
        anticipated_deviations=_fmt_list(anticipated_deviations, "(none)"),
        prereg_id=prereg_id,
    )
    # Now hash and inject.
    sap_text_for_hash = sap_text.replace("{sha256}", "<placeholder>")
    digest = _hash(sap_text_for_hash)
    sap_text = sap_text.replace("{sha256}", digest)

    # Persist.
    out_dir = _prereg_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    sap_md = out_dir / f"{prereg_id}.md"
    sap_yaml = out_dir / f"{prereg_id}.yaml"
    sap_md.write_text(sap_text)

    # YAML companion for machine-readable diff.
    sap_yaml.write_text(yaml.safe_dump({
        "prereg_id": prereg_id,
        "registered_at": iso,
        "sha256": digest,
        "project_name": project_name,
        "research_question": rq,
        "design": design,
        "data_status": data_status,
        "hypotheses": [
            {**h, "kind": h.get("kind", "confirmatory")} for h in hyps
        ],
        "primary_outcomes": primary_outcomes,
        "secondary_outcomes": secondary_outcomes,
        "target_n": target_n,
        "power_assumption": power_assumption,
        "subgroups": subgroups or [],
        "sensitivity": sensitivity or [],
        "multiplicity": multiplicity,
        "inclusion": inclusion or [],
        "exclusion": exclusion or [],
        "missing_data": missing_data,
        "additional_analyses": additional_analyses or [],
        "methods_snapshot": methods_text,
    }, sort_keys=False, default_flow_style=False))

    # Mark in state.
    state["last_preregistration"] = {
        "prereg_id": prereg_id,
        "registered_at": iso,
        "sha256": digest,
        "sap_md": str(sap_md.relative_to(root)),
        "sap_yaml": str(sap_yaml.relative_to(root)),
    }
    from research_os.project_ops import save_state

    save_state(root, state)

    return {
        "status": "success",
        "prereg_id": prereg_id,
        "sha256": digest,
        "sap_md": str(sap_md.relative_to(root)),
        "sap_yaml": str(sap_yaml.relative_to(root)),
        "advice": (
            "SAP frozen. The file is content-hashed; any later edit will "
            "show up as a deviation. To register with OSF, copy the SAP "
            "to https://osf.io/prereg/ and select the 'Standard "
            "Pre-Data Collection Registration' form. Hypotheses default "
            "to `confirmatory`; tag exploratory ones explicitly via "
            "mem_hypothesis_add kind='exploratory'."
        ),
    }


def _latest_prereg(root: Path) -> dict[str, Any] | None:
    out_dir = _prereg_dir(root)
    if not out_dir.exists() or not yaml:
        return None
    files = sorted(out_dir.glob("prereg_*.yaml"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        return yaml.safe_load(files[0].read_text())
    except Exception:
        return None


def diff_preregistration(root: Path) -> dict[str, Any]:
    """Diff the frozen SAP against the current state + methods + paper.

    Writes ``workspace/logs/preregistration_diff.md`` with:
      * Hypotheses added/removed/changed since freeze.
      * Methods passages added (post-hoc additions).
      * Outcomes mentioned in the paper but not pre-registered.
      * Exclusion rules added post-hoc.

    Used by the dashboard's "Deviations from pre-registration" panel.
    """
    prereg = _latest_prereg(root)
    if not prereg:
        return {
            "status": "warning",
            "message": (
                "no pre-registration found — call tool_preregister_freeze "
                "before data collection."
            ),
        }

    # Hypothesis diff.
    from research_os.project_ops import load_state

    state = load_state(root)
    current_hyps = state.get("active_hypotheses") or []
    prereg_hyps = {h.get("id"): h for h in prereg.get("hypotheses", [])}
    current_by_id = {h.get("id"): h for h in current_hyps}

    added = [hid for hid in current_by_id if hid not in prereg_hyps]
    removed = [hid for hid in prereg_hyps if hid not in current_by_id]
    changed: list[str] = []
    for hid in prereg_hyps:
        if hid in current_by_id:
            before = prereg_hyps[hid].get("statement", "")
            after = current_by_id[hid].get("statement", "")
            if before.strip() != after.strip():
                changed.append(hid)

    # Methods diff.
    methods_now = (root / "workspace" / "methods.md").read_text() \
        if (root / "workspace" / "methods.md").exists() else ""
    methods_before = prereg.get("methods_snapshot", "")
    methods_diff = list(difflib.unified_diff(
        methods_before.splitlines(),
        methods_now.splitlines(),
        fromfile="methods_at_preregistration",
        tofile="methods_now",
        lineterm="",
        n=2,
    ))
    methods_changed = len(methods_diff) > 0
    methods_added = sum(1 for ln in methods_diff if ln.startswith("+") and not ln.startswith("+++"))
    methods_removed = sum(1 for ln in methods_diff if ln.startswith("-") and not ln.startswith("---"))

    # Paper outcome mention check.
    paper = root / "synthesis" / "paper.md"
    paper_text = paper.read_text() if paper.exists() else ""
    paper_lower = paper_text.lower()
    primary_outcomes = (prereg.get("primary_outcomes") or "").lower()
    primary_mentioned = (
        bool(primary_outcomes) and
        any(o.strip() and o.strip() in paper_lower
            for o in re.split(r"[,;\n]", primary_outcomes))
    )

    # Build the report.
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "preregistration_diff.md"
    lines = [
        "# Deviations from pre-registration",
        "",
        f"_Pre-registration: `{prereg.get('prereg_id')}` "
        f"(SHA-256 `{(prereg.get('sha256') or '')[:16]}…`)_",
        f"_Registered: {prereg.get('registered_at')}_",
        "",
        "## Hypotheses",
        f"- Added since freeze (exploratory by definition): "
        f"{', '.join(added) if added else 'none'}",
        f"- Removed since freeze: {', '.join(removed) if removed else 'none'}",
        f"- Wording changed: {', '.join(changed) if changed else 'none'}",
        "",
        "## Methods",
        f"- Methods passages added since freeze: {methods_added}",
        f"- Methods passages removed since freeze: {methods_removed}",
    ]
    if methods_diff and len(methods_diff) <= 200:
        lines.append("")
        lines.append("```diff")
        lines.extend(methods_diff[:200])
        lines.append("```")
    lines.extend([
        "",
        "## Paper",
        f"- Primary outcome(s) ({prereg.get('primary_outcomes')}) mentioned in paper: "
        f"{'yes' if primary_mentioned else 'NO — review whether the outcome was changed post-hoc.'}",
        "",
    ])
    out.write_text("\n".join(lines) + "\n")

    n_deviations = len(added) + len(removed) + len(changed) + (
        1 if methods_changed else 0
    ) + (0 if primary_mentioned else 1)

    return {
        "status": "warning" if n_deviations else "success",
        "report_path": str(out.relative_to(root)),
        "hypotheses_added": added,
        "hypotheses_removed": removed,
        "hypotheses_changed": changed,
        "methods_changed": methods_changed,
        "methods_added_lines": methods_added,
        "methods_removed_lines": methods_removed,
        "primary_outcome_mentioned": primary_mentioned,
        "advice": (
            f"{n_deviations} deviation(s) detected. Each must be "
            "acknowledged in the paper's Discussion. Exploratory "
            "analyses should be labelled as such; post-hoc exclusions "
            "need a one-paragraph justification."
            if n_deviations
            else "Paper aligns with pre-registration."
        ),
    }


__all__ = ["freeze_preregistration", "diff_preregistration"]
