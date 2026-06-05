"""Per-step literature-loop audit gate.

After a step's findings are written but BEFORE `tool_path_finalize`, the
AI is supposed to run `research/literature_per_step`: search/download
papers per claim, write `workspace/<step>/literature/findings_vs_literature.md`,
and update `step_summary.yaml.literature`. This module gates that work.

Returns blockers/warnings/info; the caller (typically `tool_path_finalize`
or `tool_audit_master`) treats blockers as a hard stop unless the user
passes an explicit override.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_VERDICT_PATTERN = re.compile(
    r"\*\*Verdict:\*\*\s*(AGREES|DISAGREES|EXTENDS|DEFERRED)",
    re.IGNORECASE,
)
_CLAIM_BLOCK_PATTERN = re.compile(r"^##\s+Claim:", re.MULTILINE)
_DISCUSSION_PATTERN = re.compile(
    r"\*\*Discussion implication:\*\*",
    re.IGNORECASE,
)


def _load_step_summary(step_dir: Path) -> dict[str, Any]:
    """Parse step_summary.yaml; return {} on missing/invalid."""
    ss_path = step_dir / "step_summary.yaml"
    if not ss_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(ss_path.read_text()) or {}
    except Exception:
        return {}


def _step_dirs(root: Path) -> list[Path]:
    """Numbered workspace step directories, sorted."""
    workspace = root / "workspace"
    if not workspace.exists():
        return []
    return sorted(
        p for p in workspace.iterdir()
        if p.is_dir() and re.match(r"^\d{2,}_", p.name)
    )


def _audit_one_step(step_dir: Path) -> dict[str, Any]:
    """Audit literature loop for a single step. Returns per-step report."""
    step_id = step_dir.name
    blockers: list[str] = []
    warnings: list[str] = []
    info: dict[str, Any] = {"step_id": step_id}

    summary = _load_step_summary(step_dir)
    if summary.get("literature_required") is False:
        info["skipped"] = "literature_required: false (data-engineering step)"
        return {"blockers": [], "warnings": [], "info": info}

    conc_path = step_dir / "conclusions.md"
    if not conc_path.exists():
        info["skipped"] = "no conclusions.md yet (step not at literature stage)"
        return {"blockers": [], "warnings": [], "info": info}

    findings_section = ""
    try:
        txt = conc_path.read_text()
        m = re.search(
            r"^##\s+Findings\s*\n(.+?)(?=^##\s|\Z)",
            txt,
            flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        if m:
            findings_section = m.group(1).strip()
    except Exception:
        # Best-effort Findings extraction: an unreadable conclusions.md
        # (decode error, transient I/O) falls through to the stub-block
        # below, which is itself a blocker — so the audit fails closed
        # rather than silently skipping the step.
        pass
    if not findings_section or len(findings_section) < 40:
        # A stub Findings section is a REGRESSION, not a free pass.
        # Silently skipping here would let regenerated step summaries
        # with `findings: []` opt out of the literature gate entirely.
        # Instead: if conclusions.md exists at all, the step is in the
        # literature stage, and an empty Findings block is a blocker —
        # the AI must either regenerate the findings or explicitly tag
        # `literature_required: false` in step_summary.yaml.
        blockers.append(
            f"{step_id}: conclusions.md exists but `## Findings` is empty "
            "or stub (< 40 chars). This is a regenerated-summary regression, "
            "not a deferral. Either repopulate the Findings section and "
            "run research/literature_per_step, OR tag the step "
            "`literature_required: false` in step_summary.yaml if it is "
            "pure data engineering with no claims to ground."
        )
        info["findings_section_stub"] = True
        return {"blockers": blockers, "warnings": warnings, "info": info}

    lit_dir = step_dir / "literature"
    fvl_path = lit_dir / "findings_vs_literature.md"
    info["literature_dir"] = str(lit_dir)
    info["findings_vs_literature_exists"] = fvl_path.exists()

    if not fvl_path.exists():
        blockers.append(
            f"{step_id}: missing workspace/{step_id}/literature/"
            f"findings_vs_literature.md. Run research/literature_per_step "
            "before path_finalize, OR pass override_literature_gate=true "
            "with override_rationale."
        )
        return {"blockers": blockers, "warnings": warnings, "info": info}

    try:
        fvl_text = fvl_path.read_text()
    except Exception as exc:
        blockers.append(
            f"{step_id}: findings_vs_literature.md unreadable: {exc}"
        )
        return {"blockers": blockers, "warnings": warnings, "info": info}

    claim_count = len(_CLAIM_BLOCK_PATTERN.findall(fvl_text))
    verdicts = [v.upper() for v in _VERDICT_PATTERN.findall(fvl_text)]
    verdict_counts = {
        "AGREES": verdicts.count("AGREES"),
        "DISAGREES": verdicts.count("DISAGREES"),
        "EXTENDS": verdicts.count("EXTENDS"),
        "DEFERRED": verdicts.count("DEFERRED"),
    }
    info["claim_count"] = claim_count
    info["verdicts"] = verdict_counts

    if claim_count == 0:
        blockers.append(
            f"{step_id}: findings_vs_literature.md exists but has no "
            "`## Claim:` blocks. Add per-claim grounding sections."
        )
    if claim_count > 0 and len(verdicts) < claim_count:
        warnings.append(
            f"{step_id}: {claim_count - len(verdicts)} claim block(s) "
            "missing **Verdict:** line — verdict must be one of "
            "AGREES | DISAGREES | EXTENDS | DEFERRED."
        )

    disagrees_count = verdict_counts["DISAGREES"]
    discussion_count = len(_DISCUSSION_PATTERN.findall(fvl_text))
    if disagrees_count and discussion_count < disagrees_count:
        blockers.append(
            f"{step_id}: {disagrees_count} DISAGREES verdict(s) without "
            "matching **Discussion implication:** block(s). Every "
            "disagreement must address what to do about it."
        )

    pdfs = sorted(lit_dir.glob("*.pdf")) if lit_dir.exists() else []
    info["papers_downloaded"] = len(pdfs)
    if claim_count > 0 and verdict_counts["DEFERRED"] == claim_count and not pdfs:
        blockers.append(
            f"{step_id}: all {claim_count} claim(s) marked DEFERRED and "
            "no PDFs in workspace/{step_id}/literature/. Either download "
            "evidence or document why no literature is reachable in "
            "step_summary.yaml.literature_deferred + override the gate."
        )

    lit_block = summary.get("literature", {}) if isinstance(summary, dict) else {}
    lit_deferred = summary.get("literature_deferred", []) if isinstance(summary, dict) else []
    info["step_summary_literature"] = lit_block
    info["literature_deferred"] = lit_deferred

    if not lit_block:
        warnings.append(
            f"{step_id}: step_summary.yaml has no `literature:` block. "
            "research/literature_per_step writes it; missing block means "
            "synthesis can't roll up grounding stats."
        )
    elif lit_block.get("claims_grounded", 0) == 0 and not lit_deferred:
        warnings.append(
            f"{step_id}: step_summary.yaml.literature.claims_grounded == 0 "
            "but no literature_deferred reasons recorded. Document why no "
            "claim could be grounded."
        )

    grounding_jsonl = step_dir.parent.parent / "workspace" / ".grounding" / "grounding.jsonl"
    if grounding_jsonl.exists():
        try:
            text = grounding_jsonl.read_text()
            decision_count = text.count(f'"{step_id}_claim_')
            info["grounding_records_for_step"] = decision_count
            non_deferred = (
                verdict_counts["AGREES"]
                + verdict_counts["DISAGREES"]
                + verdict_counts["EXTENDS"]
            )
            if non_deferred and decision_count == 0:
                warnings.append(
                    f"{step_id}: {non_deferred} non-deferred claim(s) but "
                    "no grounding records in .grounding/grounding.jsonl. "
                    "Call tool_grounding_register per claim."
                )
        except Exception:
            # Best-effort grounding-record count: a malformed JSONL line or
            # a transient read error must not crash the literature audit —
            # the warnings the rest of the function emits are still useful.
            pass
    else:
        info["grounding_records_for_step"] = 0

    return {"blockers": blockers, "warnings": warnings, "info": info}


def audit_step_literature(
    root: Path,
    *,
    step_id: str | None = None,
) -> dict[str, Any]:
    """Per-step literature-loop gate.

    Parameters
    ----------
    root : Path
        Project root.
    step_id : str, optional
        Numbered step folder name (e.g. "03_run_deseq2"). When None,
        audits every step that has a conclusions.md.

    Returns
    -------
    dict with keys: status, blockers, warnings, steps_audited, per_step,
    summary (verdict roll-up).
    """
    if step_id:
        step_dir = root / "workspace" / step_id
        if not step_dir.exists():
            return {
                "status": "error",
                "message": f"step '{step_id}' not found under workspace/",
                "blockers": [],
                "warnings": [],
            }
        targets = [step_dir]
    else:
        targets = _step_dirs(root)

    per_step: list[dict[str, Any]] = []
    all_blockers: list[str] = []
    all_warnings: list[str] = []
    roll: dict[str, int] = {
        "AGREES": 0, "DISAGREES": 0, "EXTENDS": 0, "DEFERRED": 0
    }
    grounded_steps = 0
    skipped_steps = 0

    for step_dir in targets:
        report = _audit_one_step(step_dir)
        per_step.append(report["info"])
        all_blockers.extend(report["blockers"])
        all_warnings.extend(report["warnings"])
        if report["info"].get("skipped"):
            skipped_steps += 1
            continue
        verdicts = report["info"].get("verdicts", {})
        for k in roll:
            roll[k] += verdicts.get(k, 0)
        if report["info"].get("findings_vs_literature_exists"):
            grounded_steps += 1

    audited = len([s for s in per_step if not s.get("skipped")])
    status = "error" if all_blockers else ("warning" if all_warnings else "success")

    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "step_literature_audit.md"
    lines = [
        "# Per-step literature loop audit",
        "",
        f"- Steps audited (non-skipped): **{audited}**",
        f"- Steps with findings_vs_literature.md: **{grounded_steps}**",
        f"- Steps skipped (no conclusions / data-eng): **{skipped_steps}**",
        f"- Verdict roll-up: AGREES={roll['AGREES']}, "
        f"DISAGREES={roll['DISAGREES']}, EXTENDS={roll['EXTENDS']}, "
        f"DEFERRED={roll['DEFERRED']}",
        "",
        f"## Blockers ({len(all_blockers)})",
        "",
    ]
    if all_blockers:
        lines += [f"- {b}" for b in all_blockers]
    else:
        lines.append("_None_")
    lines += [
        "",
        f"## Warnings ({len(all_warnings)})",
        "",
    ]
    if all_warnings:
        lines += [f"- {w}" for w in all_warnings]
    else:
        lines.append("_None_")
    log_path.write_text("\n".join(lines) + "\n")

    return {
        "status": status,
        "steps_audited": audited,
        "steps_grounded": grounded_steps,
        "steps_skipped": skipped_steps,
        "verdict_roll_up": roll,
        "blockers": all_blockers,
        "warnings": all_warnings,
        "per_step": per_step,
        "log_path": str(log_path.relative_to(root)),
    }
