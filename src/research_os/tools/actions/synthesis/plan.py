"""Synthesis planner — inspect workspace, return what's ready to draft.

Read-only: does not write files, does not call the AI. Returns a JSON
skeleton of available sources so the AI knows what's in the workspace
before authoring synthesis/paper.typ (or slides.typ / poster.typ /
dashboard.html) directly.

Public surface: synthesize_plan(root) -> dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def synthesize_plan(root: Path) -> dict[str, Any]:
    """Inspect available sources and recommend section ordering."""
    methods_path = root / "workspace" / "methods.md"
    citations_path = root / "workspace" / "citations.md"
    analysis_path = root / "workspace" / "analysis.md"

    from research_os.project_ops import discover_step_dirs
    conclusions: list[str] = []
    workspace_dir = root / "workspace"
    if workspace_dir.exists():
        for exp_dir in discover_step_dirs(workspace_dir, include_dead=False):
            conc = exp_dir / "conclusions.md"
            if conc.exists() and len(conc.read_text()) > 100:
                conclusions.append(exp_dir.name)

    citations_present = (
        citations_path.exists() and citations_path.stat().st_size > 100
    )

    sections = [
        {
            "id": "methods",
            "source": "workspace/methods.md",
            "status": "ready"
            if methods_path.exists() and methods_path.stat().st_size > 100
            else "missing",
        },
        {
            "id": "results",
            "source": "workspace/*/conclusions.md + outputs/reports/",
            "status": "ready" if conclusions else "missing",
            "experiments": conclusions,
        },
        {
            "id": "discussion",
            "source": "workspace/analysis.md + citations.md",
            "status": "ready"
            if analysis_path.exists() and citations_present
            else "partial",
        },
        {
            "id": "introduction",
            "source": "citations.md + research_overview.md",
            "status": "ready"
            if citations_present
            else "missing (run literature_search first)",
        },
        {
            "id": "abstract",
            "source": "synthesis of all sections (write AFTER methods/results/discussion)",
            "status": "pending",
        },
    ]
    return {
        "sections": sections,
        "recommended_order": [
            "methods",
            "results",
            "discussion",
            "introduction",
            "abstract",
        ],
        "note": (
            "Author synthesis/paper.typ section by section in the recommended "
            "order, then call tool_synthesis_check to validate and "
            "tool_typst_compile to render the PDF."
        ),
    }
