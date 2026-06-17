"""Stale-state detection.

Auto-called by ``sys_boot`` to surface a "stale state — reconfirm?"
prompt when the workspace looks like it has drifted from an interrupted
session. Triggers:

- ``state.json`` mtime older than ``stale_after_days`` (default 30)
- ``workspace/citations.md`` older than the newest
  ``inputs/literature/*.pdf`` (PDFs added after citations were last
  refreshed)
- Per-step ``.prov.json`` provenance sidecars point to scripts that
  no longer exist
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.freshness")


def state_freshness_check(
    root: Path,
    *,
    stale_after_days: int = 30,
) -> dict[str, Any]:
    """Return a 'stale-state' summary the AI surfaces at sys_boot."""
    try:
        signals: list[str] = []
        details: dict[str, Any] = {
            "stale_after_days": stale_after_days,
        }

        now = time.time()
        cutoff = stale_after_days * 86400

        # The live state ledger is .os_state/state_ledger.json — the old
        # workspace/state.json path never existed, so this staleness signal
        # was permanently dead (state_age_days always None).
        from research_os.project_ops import state_json_path

        state_path = state_json_path(root)
        if state_path.exists():
            state_age = now - state_path.stat().st_mtime
            details["state_age_days"] = round(state_age / 86400, 1)
            if state_age > cutoff:
                signals.append(
                    f"state ledger last updated "
                    f"{int(state_age / 86400)} days ago "
                    f"(threshold: {stale_after_days}). Reconfirm the "
                    "current path + autonomy before continuing."
                )
        else:
            details["state_age_days"] = None

        cit_path = root / "workspace" / "citations.md"
        lit_dir = root / "inputs" / "literature"
        newest_pdf_mtime = 0.0
        newest_pdf_name = ""
        if lit_dir.is_dir():
            for pdf in lit_dir.glob("*.pdf"):
                m = pdf.stat().st_mtime
                if m > newest_pdf_mtime:
                    newest_pdf_mtime = m
                    newest_pdf_name = pdf.name
        details["newest_pdf"] = newest_pdf_name or None
        if (
            cit_path.exists()
            and newest_pdf_mtime
            and cit_path.stat().st_mtime < newest_pdf_mtime
        ):
            lag = newest_pdf_mtime - cit_path.stat().st_mtime
            details["citations_lag_days"] = round(lag / 86400, 1)
            signals.append(
                f"workspace/citations.md is older than "
                f"inputs/literature/{newest_pdf_name} by "
                f"{int(lag / 86400)} day(s). New PDFs likely not "
                "indexed — re-run tool_citations_rebuild."
            )

        orphan_provenance: list[dict[str, str]] = []
        workspace = root / "workspace"
        if workspace.is_dir():
            for step_dir in workspace.iterdir():
                if not (step_dir.is_dir() and step_dir.name[:2].isdigit()):
                    continue
                prov_dir = step_dir / "scripts"
                if not prov_dir.is_dir():
                    continue
                for prov in prov_dir.glob("*.prov.json"):
                    try:
                        meta = json.loads(prov.read_text())
                    except Exception:
                        continue
                    target = meta.get("script") or meta.get("script_path")
                    if not target:
                        continue
                    target_path = (
                        root / target if not target.startswith("/")
                        else Path(target)
                    )
                    if not target_path.exists():
                        orphan_provenance.append({
                            "step": step_dir.name,
                            "provenance_file": str(
                                prov.relative_to(root)
                            ),
                            "missing_script": target,
                        })
        details["orphan_provenance_count"] = len(orphan_provenance)
        details["orphan_provenance"] = orphan_provenance[:10]
        if orphan_provenance:
            signals.append(
                f"{len(orphan_provenance)} provenance sidecar(s) point "
                "to scripts that no longer exist. The step's reported "
                "outputs may not be reproducible — re-run or delete."
            )

        is_stale = bool(signals)
        prompt = ""
        if is_stale:
            prompt = (
                "Workspace shows stale-state signals. Surface to the "
                "researcher: 'It looks like this workspace has drifted "
                "since the last active session. Reconfirm the current "
                "path + autonomy + literature freshness before "
                "proceeding?' Then re-run tool_route on the original "
                "intent so the routing reflects current state."
            )

        return {
            "status": "success",
            "is_stale": is_stale,
            "signals": signals,
            "details": details,
            "prompt_for_ai": prompt,
        }
    except Exception as e:
        logger.exception("state_freshness_check failed")
        return {"status": "error", "message": str(e)}
