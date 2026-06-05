"""Preflight check #23 — `figures_for_paper` field is set explicitly.

Walks every fixture project under ``tests/fixtures/projects/*/workspace/<NN_slug>/``
and confirms that for every figure file under ``outputs/figures/`` that has
a sibling ``<name>.caption.md`` sidecar, the ``figures_for_paper`` field is
declared in **exactly one** of two places:

  1. A frontmatter line inside the sidecar (``figures_for_paper: true|false``).
  2. The step-level ``step_summary.yaml`` (``figures_for_paper: true|false``).

The sidecar value, when present, overrides the step-level default; either
location is sufficient to satisfy the check. Figures without a sidecar are
skipped (a separate gate enforces sidecar presence).

The check returns the standard preflight ``(ok: bool, detail: str)`` tuple
so it slots into ``scripts/preflight.py`` next to the other ``check_*``
functions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT_DEFAULT = REPO_ROOT / "tests" / "fixtures" / "projects"

# Figure file extensions audited for the field. Matches the set the existing
# completeness gate treats as "focal figures".
_FIGURE_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".pdf", ".webp"}

# Frontmatter line matcher. Accepts YAML-style `figures_for_paper: true|false`
# anywhere in the caption sidecar (not strictly bounded to `---` blocks so a
# bare top-of-file declaration without delimiters also counts).
_SIDECAR_FIELD_RE = re.compile(
    r"^[ \t]*figures_for_paper[ \t]*:[ \t]*(true|false)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _iter_workspace_step_dirs(fixtures_root: Path) -> Iterable[Path]:
    """Yield every ``<project>/workspace/<NN_slug>/`` directory under fixtures."""
    if not fixtures_root.exists():
        return
    for project in sorted(fixtures_root.iterdir()):
        if not project.is_dir():
            continue
        workspace = project / "workspace"
        if not workspace.is_dir():
            continue
        for step_dir in sorted(workspace.iterdir()):
            if step_dir.is_dir():
                yield step_dir


def _step_summary_has_field(step_dir: Path) -> bool:
    """True when step_summary.yaml declares figures_for_paper explicitly."""
    summary = step_dir / "step_summary.yaml"
    if not summary.is_file():
        return False
    try:
        data = yaml.safe_load(summary.read_text()) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return "figures_for_paper" in data


def _sidecar_has_field(sidecar: Path) -> bool:
    """True when the caption sidecar declares figures_for_paper explicitly."""
    try:
        text = sidecar.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(_SIDECAR_FIELD_RE.search(text))


def _figure_has_caption_sidecar(figure: Path) -> Path | None:
    """Return the sibling ``<name>.caption.md`` if it exists, else None."""
    # The convention is <name_with_ext>.caption.md OR <stem>.caption.md.
    # Audit code in audit/figure_interactivity.py + project_ops.py uses the
    # stem form (`<stem>.caption.md`) — match that here.
    sidecar = figure.with_name(f"{figure.stem}.caption.md")
    return sidecar if sidecar.is_file() else None


def find_missing_figures_for_paper(
    fixtures_root: Path = FIXTURES_ROOT_DEFAULT,
) -> list[str]:
    """Return relative paths of figures missing the figures_for_paper field.

    A figure is "missing" the field when it has a sibling caption sidecar
    but neither the sidecar nor the step-level ``step_summary.yaml`` set
    ``figures_for_paper`` explicitly.
    """
    missing: list[str] = []
    for step_dir in _iter_workspace_step_dirs(fixtures_root):
        figures_dir = step_dir / "outputs" / "figures"
        if not figures_dir.is_dir():
            continue
        step_has = _step_summary_has_field(step_dir)
        for figure in sorted(figures_dir.iterdir()):
            if not figure.is_file():
                continue
            if figure.suffix.lower() not in _FIGURE_EXTS:
                continue
            sidecar = _figure_has_caption_sidecar(figure)
            if sidecar is None:
                # No sidecar = a different gate's problem; skip here.
                continue
            sidecar_has = _sidecar_has_field(sidecar)
            if step_has or sidecar_has:
                continue
            try:
                rel = figure.relative_to(fixtures_root.parent.parent)
            except ValueError:
                rel = figure
            missing.append(str(rel))
    return missing


def check_figures_for_paper_field(
    fixtures_root: Path = FIXTURES_ROOT_DEFAULT,
) -> tuple[bool, str]:
    """Preflight entrypoint — returns (ok, detail) per the preflight contract.

    OK when every captioned figure under tests/fixtures/projects/*/workspace/*/
    has ``figures_for_paper`` declared either on the figure's caption sidecar
    or on the step-level ``step_summary.yaml``. Returns the count of figures
    actually audited in the detail line so a zero-fixture state is visible.
    """
    audited = 0
    for step_dir in _iter_workspace_step_dirs(fixtures_root):
        figures_dir = step_dir / "outputs" / "figures"
        if not figures_dir.is_dir():
            continue
        for figure in figures_dir.iterdir():
            if not figure.is_file():
                continue
            if figure.suffix.lower() not in _FIGURE_EXTS:
                continue
            if _figure_has_caption_sidecar(figure) is None:
                continue
            audited += 1
    missing = find_missing_figures_for_paper(fixtures_root)
    if missing:
        sample = ", ".join(missing[:3])
        more = "..." if len(missing) > 3 else ""
        return False, (
            f"{len(missing)} captioned figure(s) missing `figures_for_paper`: "
            f"{sample}{more}"
        )
    return True, f"{audited} captioned figure(s) declare figures_for_paper"
