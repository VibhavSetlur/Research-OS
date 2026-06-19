"""Quick mode + promote-to-step.

Throwaway / sanity-check / exploratory-only work bypasses protocols
and lands under ``workspace/scratch/``. Researcher can promote a quick
result to a proper step retroactively if it turns out to matter.

Quick-mode behavior:
- no protocol load
- single shortcut tool
- outputs land in ``workspace/scratch/<slug>/``
- no provenance sidecars required
- no audit gates fire

``researcher_config.project_tier: throwaway | sketch | production``
sets the default audit strictness across the project. ``throwaway``
maps to ``gate_strictness: light``; ``sketch`` is ``normal``;
``production`` is ``strict``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.state.quick_mode")


_QUICK_TRIGGERS = (
    "just make me a plot",
    "sanity check",
    "exploratory only",
    "throwaway viz",
    "quick look",
    "quick plot",
    "quick check",
    "rough draft",
    "scratch",
    "throwaway",
)


def _slugify(s: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip()).strip("_") or "scratch"
    return s[:maxlen].lower()


def detect_quick_intent(prompt: str) -> dict[str, Any]:
    """Return ``{is_quick, matched_trigger}`` for an intent prompt."""
    lower = (prompt or "").lower()
    for t in _QUICK_TRIGGERS:
        if t in lower:
            return {"is_quick": True, "matched_trigger": t}
    return {"is_quick": False, "matched_trigger": None}


def quick_route(root: Path, prompt: str) -> dict[str, Any]:
    """Return a routing decision compatible with ``tool_route``.

    The MCP's ``tool_route`` calls this first; on quick intent it
    short-circuits the protocol load and returns ``complexity: quick``
    plus a shortcut tool name.
    """
    try:
        det = detect_quick_intent(prompt)
        if not det["is_quick"]:
            return {"is_quick": False}
        scratch_dir = root / "workspace" / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        return {
            "is_quick": True,
            "matched_trigger": det["matched_trigger"],
            "complexity": "quick",
            "recommended_tool": "tool_scratch_write",
            "output_dir": "workspace/scratch/",
            "advice": (
                "Quick mode active — no protocol, no audit gates. Write "
                "the result under workspace/scratch/ via tool_scratch_write. "
                "If the result turns out to matter, call "
                "tool_promote_to_step to wrap it in proper provenance."
            ),
        }
    except Exception as e:
        logger.exception("quick_route failed")
        return {"is_quick": False, "error": str(e)}


def promote_to_step(
    root: Path,
    *,
    scratch_path: str,
    step_slug: str,
    rationale: str = "",
) -> dict[str, Any]:
    """Wrap a scratch result in proper provenance retroactively.

    Creates a new numbered step folder, moves the scratch file into it,
    writes a minimal step_summary.yaml + conclusions.md, and emits a
    .prov.json sidecar pointing back to the original scratch source.
    """
    try:
        src = (root / scratch_path).resolve()
        if not src.exists():
            return {"status": "error", "message": f"scratch path not found: {scratch_path}"}
        # Refuse paths that escape the project root via .. or
        # absolute paths.
        try:
            src.relative_to(root.resolve())
        except ValueError:
            return {
                "status": "error",
                "message": (
                    f"scratch path must live under the project root; "
                    f"got {src}"
                ),
            }
        workspace = root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        # Parse leading-digit run with regex, not name[:2], so 100+
        # step projects don't collide on next_num.
        existing_nums = []
        for d in workspace.iterdir():
            if not d.is_dir():
                continue
            m = re.match(r"^(\d+)_", d.name)
            if not m:
                continue
            try:
                existing_nums.append(int(m.group(1)))
            except ValueError:
                continue
        next_num = (max(existing_nums) + 1) if existing_nums else 1
        slug = _slugify(step_slug)
        step_dir = workspace / f"{next_num:02d}_{slug}"
        step_dir.mkdir()
        (step_dir / "scripts").mkdir()
        (step_dir / "outputs" / "figures").mkdir(parents=True)
        (step_dir / "literature").mkdir()
        # Decide destination — images go to outputs/figures/, else step root.
        dest_dir = step_dir / "outputs" / "figures"
        if src.suffix.lower() not in {".png", ".svg", ".pdf", ".jpg"}:
            dest_dir = step_dir
        dest = dest_dir / src.name
        # Copy rather than move so original scratch stays untouched.
        dest.write_bytes(src.read_bytes())
        # Provenance sidecar.
        prov = {
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promoted_from_scratch": str(src.relative_to(root)),
            "rationale": rationale,
            "tool": "tool_promote_to_step",
        }
        import json
        # Provenance sidecar uses the STEM (fig.prov.json), matching what
        # every reader (inventory / audit / RO-Crate) expects — NOT
        # fig.png.prov.json, which left the record invisible.
        prov_path = dest.with_name(dest.stem + ".prov.json")
        prov_path.write_text(json.dumps(prov, indent=2))
        # Minimal conclusions.md.
        # The marker comment makes the step literature-exempt (a promoted
        # scratch probe doesn't owe the per-step literature loop). The
        # step-literature gate reads this marker from conclusions.md;
        # delete the line to opt the step back into the literature loop.
        (step_dir / "conclusions.md").write_text(
            "<!-- research-os: literature_required=false -->\n\n"
            f"## Findings\n\n"
            f"Promoted from scratch artifact `{src.name}`. "
            f"Rationale: {rationale or '(none provided)'}\n\n"
            f"## Decision\n\nPromoted to numbered step "
            f"{next_num:02d}_{slug} for proper audit + synthesis "
            "inclusion.\n"
        )
        return {
            "status": "success",
            "step_id": f"{next_num:02d}_{slug}",
            "step_dir": str(step_dir.relative_to(root)),
            "moved_to": str(dest.relative_to(root)),
            "provenance_file": str(prov_path.relative_to(root)),
            "note": (
                "Step is literature-exempt by default (marker in "
                "conclusions.md); delete the marker line if the promoted "
                "finding needs the per-step literature loop."
            ),
        }
    except Exception as e:
        logger.exception("promote_to_step failed")
        return {"status": "error", "message": str(e)}


def project_tier_strictness(root: Path) -> dict[str, Any]:
    """Map researcher_config.project_tier → gate_strictness default."""
    try:
        cfg_path = root / "inputs" / "researcher_config.yaml"
        if not cfg_path.exists():
            legacy = root / "researcher_config.yaml"
            if legacy.exists():
                cfg_path = legacy
        tier = "production"
        if cfg_path.exists():
            try:
                import yaml  # type: ignore
                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                tier = str(cfg.get("project_tier") or "production")
            except Exception:
                pass
        mapping = {
            "throwaway": "light",
            "sketch": "normal",
            "production": "strict",
        }
        strictness = mapping.get(tier, "normal")
        return {
            "status": "success",
            "project_tier": tier,
            "default_gate_strictness": strictness,
        }
    except Exception as e:
        logger.exception("project_tier_strictness failed")
        return {"status": "error", "message": str(e)}
