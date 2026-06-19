"""Ship gate — the single server-enforced refusal of "done".

Every other gate in the project is *advisory*: a synthesis step can run,
emit a warning, and proceed anyway. This module is the one place that can
actually REFUSE to ship a deliverable. It aggregates BLOCK-severity
findings from across the project into one verdict and, unless a
verifiable researcher override clears it, returns ``status='blocked'`` —
which the handler turns into a hard ``_error`` envelope.

What it aggregates
------------------
1. **Unresolved audit blockers** — every BLOCK finding currently in the
   cross-audit ledger (``workspace/logs/.audit_findings.jsonl`` via
   :func:`unresolved_block_findings`). These are the findings the audits
   already raised and nobody resolved.
2. **Cited-but-missing / invalid PDFs** — files named ``*.pdf`` in any
   literature folder that are NOT real PDFs (fail the ``%PDF-`` magic
   check). A renamed 403/HTML page named like a paper is a fake citation
   substrate.
3. **Ungrounded numeric claims in the deliverable** — runs the existing
   claim-grounding auditor against the resolved paper; each ungrounded
   number is a ship blocker (it appears in no workspace output).
4. **Stub / placeholder deliverable sections** — the paper still carries
   ``TODO`` / ``TBD`` / ``XXX`` / ``FIXME`` / ``lorem ipsum`` / authoring
   HTML comments / ``<placeholder>`` markers.

The verdict
-----------
* ``operation='check'`` (default) — report-only. Returns the full
  findings list with ``status='blocked'`` if any blocker exists, else
  ``status='clear'``. Never raises; safe to call any time.
* ``operation='finalize'`` — the same aggregation, but a non-empty
  blocker set yields ``status='blocked'`` that the handler escalates to a
  hard error. Pass ``override=true`` + a substantive
  ``override_rationale`` (validated, logged) to ship despite blockers.

This is intentionally the LAST pre-ship step a synthesis/audit protocol
references. It is a scaffold, not a script: it tells the AI exactly what
is unfinished and lets the researcher decide, but it will not let a
deliverable out the door silently while blockers stand.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.audit.ship_gate")


# Placeholder markers that mean a section is unfinished. Word-boundary
# anchored so "TODO" matches but "mastodon" does not.
_STUB_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bTODO\b", "TODO"),
    (r"\bTBD\b", "TBD"),
    (r"\bFIXME\b", "FIXME"),
    (r"\bXXX\b", "XXX"),
    (r"\blorem ipsum\b", "lorem ipsum"),
    (r"<placeholder", "<placeholder>"),
    (r"\[INSERT[^\]]*\]", "[INSERT…]"),
    # NB: the bare word "placeholder" is intentionally NOT a stub marker —
    # legitimate prose ("placeholder imputation", "a placeholder variable")
    # tripped the ship gate. Only the scaffold forms above (``<placeholder``,
    # ``[INSERT…]``) signal an unfinished section.
)
# Authoring HTML comments (Markdown scaffolds leave `<!-- AI: ... -->`).
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _scan_stub_markers(text: str) -> list[str]:
    """Return the distinct stub markers present in ``text``."""
    found: list[str] = []
    for pat, label in _STUB_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            found.append(label)
    if _HTML_COMMENT_RE.search(text):
        found.append("<!-- authoring comment -->")
    return found


def _fake_pdfs(root: Path) -> list[str]:
    """Return relative paths of *.pdf files that are not real PDFs.

    Scans every step literature folder + the project literature folder.
    A file is "fake" when it carries a .pdf name but fails the magic-byte
    check — a cited-but-invalid substrate.
    """
    from research_os.tools.actions.search.literature import is_valid_pdf

    fakes: list[str] = []
    lit_dirs: list[Path] = [root / "inputs" / "literature"]
    workspace = root / "workspace"
    if workspace.is_dir():
        for step_dir in workspace.iterdir():
            if step_dir.is_dir():
                lit_dirs.append(step_dir / "literature")
    for d in lit_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.pdf")):
            if f.is_file() and not is_valid_pdf(f):
                try:
                    fakes.append(str(f.relative_to(root)))
                except ValueError:
                    fakes.append(str(f))
    return fakes


def _collect_blockers(root: Path) -> dict[str, Any]:
    """Aggregate every category of ship blocker. Pure read; never raises."""
    blockers: list[dict[str, Any]] = []

    # 1. Unresolved audit BLOCK findings in the cross-audit ledger.
    try:
        from research_os.tools.actions.audit.findings_query import (
            unresolved_block_findings,
        )
        for f in unresolved_block_findings(root):
            blockers.append({
                "category": "audit_blocker",
                "id": f.get("id"),
                "dimension": f.get("dimension"),
                "audit_name": f.get("audit_name"),
                "detail": (f.get("suggested_fix") or "")[:400],
                "evidence_paths": f.get("evidence_paths") or [],
            })
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("ship_gate: ledger read failed: %s", exc)

    # 2. Cited-but-invalid PDFs (fake substrate).
    for rel in _fake_pdfs(root):
        blockers.append({
            "category": "invalid_pdf",
            "detail": (
                f"{rel} is named like a PDF but is not a valid PDF "
                "(fails %PDF- magic check) — a renamed error/paywall page "
                "cannot ground a citation. Re-download or remove it."
            ),
            "evidence_paths": [rel],
        })

    # 3. Ungrounded numeric claims in the resolved deliverable.
    target_path: str | None = None
    try:
        from research_os.tools.actions.audit._paper import resolve_paper_path
        from research_os.tools.actions.audit.claim_grounding import audit_claims

        target_path = resolve_paper_path(root)
        if (root / target_path).is_file():
            res = audit_claims(root, target_path=target_path)
            for c in res.get("ungrounded_claims") or []:
                blockers.append({
                    "category": "ungrounded_claim",
                    "detail": (
                        f"Claim `{c.get('token')}` on L{c.get('line')} of "
                        f"{target_path} appears in no workspace output."
                    ),
                    "evidence_paths": [target_path],
                    "context": (c.get("context") or "")[:160],
                })
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("ship_gate: claim audit failed: %s", exc)

    # 4. Stub / placeholder sections in the deliverable.
    try:
        if target_path and (root / target_path).is_file():
            body = (root / target_path).read_text(errors="replace")
            markers = _scan_stub_markers(body)
            for mk in markers:
                blockers.append({
                    "category": "stub_section",
                    "detail": (
                        f"Deliverable {target_path} still contains a "
                        f"placeholder marker: {mk}. Finish or remove it "
                        "before shipping."
                    ),
                    "evidence_paths": [target_path],
                })
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("ship_gate: stub scan failed: %s", exc)

    counts: dict[str, int] = {}
    for b in blockers:
        counts[b["category"]] = counts.get(b["category"], 0) + 1

    return {
        "blockers": blockers,
        "n_blockers": len(blockers),
        "by_category": counts,
        "deliverable": target_path,
    }


def _write_report(root: Path, agg: dict[str, Any]) -> str:
    """Write a human-readable ship-readiness report. Returns its rel path."""
    logs = root / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "ship_gate.md"
    lines = [
        "# Ship gate",
        "",
        f"- Deliverable: `{agg.get('deliverable') or '(none resolved)'}`",
        f"- Total ship blockers: **{agg['n_blockers']}**",
        "",
    ]
    if agg["by_category"]:
        lines.append("## By category")
        for cat, n in sorted(agg["by_category"].items()):
            lines.append(f"- {cat}: {n}")
        lines.append("")
    if agg["blockers"]:
        lines.append("## Blockers")
        for b in agg["blockers"][:100]:
            lines.append(f"- **[{b['category']}]** {b['detail']}")
        if len(agg["blockers"]) > 100:
            lines.append(f"… and {len(agg['blockers']) - 100} more.")
        lines.append("")
    else:
        lines.append("No ship blockers detected. Deliverable is clear to ship.")
        lines.append("")
    out.write_text("\n".join(lines) + "\n")
    return str(out.relative_to(root))


_STEP_IN_PATH_RE = re.compile(r"workspace/(?:[^/]+_PATH_\d+/)?(\d{2,3}_[^/]+)")


def write_final_audit(root: Path) -> str:
    """Write the single project-end meta-review at ``workspace/audit.md``.

    This is the one human-facing audit artefact (the per-gate
    ``logs/audits/*`` files are machine detail). It aggregates the
    cross-audit findings ledger into a reviewer's report: per-step
    warnings + concerns, each with its evidence path(s), a content hash
    of the evidence (so a reader can tell if the file changed since the
    finding), and the suggested fix. Written only at project end (when the
    researcher signals the last step / runs the ship gate), so it never
    clutters the workspace mid-run.
    """
    from datetime import datetime, timezone

    from research_os import __version__
    from research_os.project_ops import compute_file_hash
    from research_os.tools.actions.audit.findings_query import (
        _findings_jsonl_path,
        _load_jsonl_lines,
    )

    jsonl = _findings_jsonl_path(root)
    lines = _load_jsonl_lines(jsonl) if jsonl.exists() else []
    # Dedup by stable id, last occurrence wins (ledger is chronological).
    latest: dict[str, dict[str, Any]] = {}
    for f in lines:
        fid = f.get("id")
        if fid:
            latest[fid] = f
    findings = list(latest.values())

    # Group by step (derived from evidence paths); else "project".
    by_step: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        step = "project"
        for ev in (f.get("evidence_paths") or []):
            m = _STEP_IN_PATH_RE.search(str(ev))
            if m:
                step = m.group(1)
                break
        by_step.setdefault(step, []).append(f)

    sev_rank = {"block": 0, "warn": 1, "info": 2}
    n_block = sum(1 for f in findings if f.get("severity") == "block")
    n_warn = sum(1 for f in findings if f.get("severity") == "warn")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out_lines = [
        "# Project audit — meta-review",
        "",
        f"*Generated {stamp} · Research-OS v{__version__}. The single "
        "human-facing audit: per-step concerns with evidence, content "
        "hashes, and suggested fixes. The per-gate machine detail lives in "
        "`workspace/logs/audits/`.*",
        "",
        f"- **Concerns (block):** {n_block}",
        f"- **Warnings:** {n_warn}",
        f"- **Total findings:** {len(findings)}",
        "",
    ]
    if not findings:
        out_lines.append(
            "No outstanding audit findings recorded. Run the per-step / "
            "synthesis audits before relying on this — an empty ledger can "
            "also mean the audits were never run.\n"
        )
    else:
        # Steps first (numeric order), then project-level.
        def _step_key(s: str) -> tuple[int, str]:
            m = re.match(r"^(\d{2,3})_", s)
            return (int(m.group(1)) if m else 9999, s)

        for step in sorted(by_step, key=_step_key):
            fs = sorted(
                by_step[step],
                key=lambda f: sev_rank.get(f.get("severity"), 3),
            )
            out_lines.append(f"## `{step}`")
            out_lines.append("")
            for f in fs:
                sev = f.get("severity", "info").upper()
                dim = f.get("dimension", "?")
                fix = (f.get("suggested_fix") or "").strip()
                out_lines.append(f"- **[{sev}·{dim}]** {fix}")
                for ev in (f.get("evidence_paths") or [])[:4]:
                    h = compute_file_hash(root / ev)
                    short = h[:12] if h != "error" else "missing"
                    out_lines.append(f"    - evidence: `{ev}` · sha256 `{short}`")
            out_lines.append("")

    audit_md = root / "workspace" / "audit.md"
    audit_md.parent.mkdir(parents=True, exist_ok=True)
    audit_md.write_text("\n".join(out_lines) + "\n")
    return str(audit_md.relative_to(root))


def finalize_project(
    root: Path,
    *,
    operation: str = "check",
    override: bool = False,
    override_rationale: str = "",
) -> dict[str, Any]:
    """Aggregate every ship blocker and decide whether the project may ship.

    Parameters
    ----------
    operation:
        ``'check'`` (default) report-only; ``'finalize'`` enforces the gate.
    override:
        Researcher authorization to ship despite blockers. Requires a
        substantive ``override_rationale`` (validated + logged).
    override_rationale:
        Why shipping despite blockers is acceptable. Validated by
        :func:`research_os.project_ops.validate_override_rationale`.

    Returns a dict whose ``status`` is one of:
      * ``'clear'``       — no blockers; safe to ship.
      * ``'blocked'``     — blockers present and not overridden. The
                            handler turns this into a hard error.
      * ``'overridden'``  — blockers present but a verifiable override
                            cleared them (logged).
      * ``'error'``       — a bad override (e.g. flag set, thin rationale).
    """
    op = (operation or "check").lower()
    if op not in ("check", "finalize"):
        return {
            "status": "error",
            "message": (
                f"ship_gate: unknown operation '{operation}'. "
                "Use 'check' (report-only) or 'finalize' (enforce)."
            ),
        }

    agg = _collect_blockers(root)
    report_path = _write_report(root, agg)
    # The project-end meta-review: a single human-facing workspace/audit.md
    # (per-step concerns + evidence hashes + suggested fixes). The ship gate
    # IS the "this is the last step" moment, so generate it here.
    try:
        final_audit_path = write_final_audit(root)
    except Exception:  # pragma: no cover - never let the meta-review break the gate
        logger.exception("write_final_audit failed")
        final_audit_path = None
    base = {
        "operation": op,
        "n_blockers": agg["n_blockers"],
        "by_category": agg["by_category"],
        "blockers": agg["blockers"],
        "deliverable": agg["deliverable"],
        "report_path": report_path,
        "audit_md": final_audit_path,
    }

    if agg["n_blockers"] == 0:
        return {
            "status": "clear",
            **base,
            "message": (
                "Ship gate clear: no unresolved audit blockers, no invalid "
                "PDFs, no ungrounded numeric claims, no stub sections."
            ),
        }

    # Blockers exist. In 'check' mode we report without refusing.
    if op == "check":
        return {
            "status": "blocked",
            **base,
            "advisory": True,
            "message": (
                f"{agg['n_blockers']} ship blocker(s) present (check mode — "
                "advisory). Call tool_finalize_project(operation='finalize') "
                "to enforce, or resolve the blockers listed in "
                f"{report_path}."
            ),
        }

    # operation='finalize': enforce. Honour a verifiable override only.
    if override:
        if not override_rationale or not override_rationale.strip():
            return {
                "status": "error",
                **base,
                "message": (
                    "override=true requires override_rationale — an empty "
                    "rationale would silently ship a blocked deliverable."
                ),
            }
        from research_os.project_ops import (
            log_override,
            validate_override_rationale,
        )
        thin = validate_override_rationale(override_rationale)
        if thin is not None:
            # Surface the structured 'too thin' error verbatim.
            thin_msg = thin.get("error") or "override_rationale too thin"
            return {"status": "error", **base, "message": thin_msg,
                    "override_error": thin}
        try:
            log_override(
                root,
                tool="tool_finalize_project",
                gate="ship_gate",
                rationale=override_rationale,
                extra={
                    "n_blockers": agg["n_blockers"],
                    "by_category": agg["by_category"],
                },
            )
        except Exception as exc:  # pragma: no cover - best-effort log
            logger.debug("ship_gate: override log failed: %s", exc)
        return {
            "status": "overridden",
            **base,
            "override_rationale": override_rationale,
            "message": (
                f"Shipped with {agg['n_blockers']} blocker(s) overridden by "
                "researcher. Logged to workspace/logs/override_log.md."
            ),
        }

    # No override → REFUSE.
    return {
        "status": "blocked",
        **base,
        "message": (
            f"SHIP REFUSED: {agg['n_blockers']} unresolved blocker(s) stand "
            "between this deliverable and 'done'. Resolve them (see "
            f"{report_path}) OR, if the researcher explicitly accepts "
            "shipping anyway, call tool_finalize_project("
            "operation='finalize', override=true, override_rationale='...') "
            "with a substantive rationale (>=20 chars, multi-word)."
        ),
    }


__all__ = ["finalize_project", "write_final_audit"]
