import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("research.tools.path")


EXPERIMENT_SUBDIRS = [
    "data",
    "scripts",
    "outputs/reports",
    "outputs/figures",
    "outputs/tables",
    "outputs/dashboards",
    "environment",
]


def _next_experiment_number(root: Path) -> int:
    workspace_dir = root / "workspace"
    max_num = 0
    if workspace_dir.exists():
        for p in workspace_dir.iterdir():
            if p.is_dir() and re.match(r"^\d{2}_", p.name):
                try:
                    num = int(p.name[:2])
                    max_num = max(max_num, num)
                except ValueError:
                    pass
    return max_num + 1


def create_path(name: str, root: Path) -> dict[str, Any]:
    next_num = _next_experiment_number(root)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_") or "experiment"
    path_id = f"{next_num:02d}_{slug}"
    experiment_dir = root / "workspace" / path_id

    if experiment_dir.exists():
        return {"status": "error", "message": f"Path '{path_id}' already exists at {experiment_dir}"}

    experiment_dir.mkdir(parents=True, exist_ok=True)
    for sub in EXPERIMENT_SUBDIRS:
        (experiment_dir / sub).mkdir(parents=True, exist_ok=True)

    readme = experiment_dir / "README.md"
    readme.write_text(
        f"# Experiment: {path_id}\n\n"
        f"*Created:*\n\n"
        "## Goal\n\n"
        f"{name}\n\n"
        "## Input Data\n\n"
        "- *(List input files used)*\n\n"
        "## Methods Used\n\n"
        "- *(List statistical methods, transforms, models)*\n\n"
        "## Expected Output\n\n"
        "- *(Describe expected outputs)*\n\n"
        "## Actual Output\n\n"
        "- *(Describe actual results after execution)*\n\n"
        "## Next-Step Decision\n\n"
        "- *(proceed / abandon)*\n"
    )

    conclusions = experiment_dir / "conclusions.md"
    conclusions.write_text(
        f"# {path_id} — Conclusions\n\n"
        f"*Created:*\n\n"
        "## Summary\n\n"
        "*(Summarize key findings here after analysis.)*\n\n"
        "## Next Steps\n\n"
        "*(Describe what to do next — proceed or abandon.)*\n"
    )

    from research_os.project_ops import _update_workflow_mermaid, _update_manifest
    _update_workflow_mermaid(root)
    _update_manifest(root)

    return {
        "status": "success",
        "path_id": path_id,
        "experiment_dir": str(experiment_dir.absolute()),
        "paths_created": [
            str(experiment_dir / sub) for sub in EXPERIMENT_SUBDIRS
        ] + [str(readme), str(conclusions)],
        "paths_created_count": 2 + len(EXPERIMENT_SUBDIRS),
    }


def abandon_path(path_name: str, rationale: str, root: Path) -> dict[str, Any]:
    workspace_dir = root / "workspace"
    target_dir = workspace_dir / path_name

    if not target_dir.exists() or not target_dir.is_dir():
        return {"status": "error", "message": f"Path '{path_name}' not found in workspace/"}

    if not re.match(r"^\d{2}_", path_name):
        return {"status": "error", "message": f"'{path_name}' is not a numbered experiment path"}

    dead_end_name = f"{path_name}__DEAD_END"
    dead_end_dir = workspace_dir / dead_end_name

    if dead_end_dir.exists():
        shutil.rmtree(dead_end_dir, ignore_errors=True)

    target_dir.rename(dead_end_dir)

    analysis_path = root / "workspace" / "analysis.md"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    with open(analysis_path, "a") as f:
        f.write(f"\n\n## Abandoned: {path_name}\n\n**Rationale:** {rationale}\n\n")

    from research_os.project_ops import _update_workflow_mermaid, _update_manifest
    _update_workflow_mermaid(root)
    _update_manifest(root)

    return {
        "status": "success",
        "original_path": path_name,
        "renamed_to": dead_end_name,
        "rationale": rationale,
        "files_preserved": True,
    }


def list_paths(root: Path) -> dict[str, Any]:
    workspace_dir = root / "workspace"
    paths: list[dict[str, Any]] = []

    if not workspace_dir.exists():
        return {"status": "success", "paths": paths, "paths_count": 0}

    for p in sorted(workspace_dir.iterdir()):
        if not p.is_dir():
            continue
        m = re.match(r"^(\d{2})_(.+?)(__DEAD_END)?$", p.name)
        if not m:
            continue

        number = int(m.group(1))
        name = m.group(2)
        is_dead_end = m.group(3) is not None

        if is_dead_end:
            status = "dead_end"
            display_name = name
        else:
            has_conclusions = (p / "conclusions.md").exists()
            conclusions_text = ""
            if has_conclusions:
                conclusions_text = (p / "conclusions.md").read_text()
            has_next_steps = "Next Steps" in conclusions_text and "proceed" not in conclusions_text.lower()
            status = "completed" if has_conclusions and has_next_steps else "active"
            display_name = name

        paths.append({
            "path_id": p.name,
            "number": number,
            "name": display_name,
            "status": status,
            "experiment_dir": str(p.absolute()),
            "has_readme": (p / "README.md").exists(),
            "has_conclusions": (p / "conclusions.md").exists(),
        })

    return {"status": "success", "paths": paths, "paths_count": len(paths)}
