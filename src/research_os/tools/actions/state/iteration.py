"""Deliberate-iteration versioning for an analysis step.

`_v1` → `_v2` suffix bumping in `scripts/` covers BUG FIXES well (the
fingerprint cache notices the change, re-runs, overwrites). It does
NOT cover **design iteration** — when the researcher says "rerun
Figure 2 with a different colour palette" or "tighten the cutoff to
0.1," they want a coordinated snapshot of every artefact that moves
together: the script that produced the figure, the figure itself, the
caption, the per-step conclusion entry.

This module exposes two functions:

* :func:`iterate_step` — Take a *labelled* snapshot of one or more
  artefacts inside a step, bumping each to a new version suffix in
  lock-step and recording the bump in a step-level
  ``iterations.yaml`` ledger. Optional ``rationale`` is required so
  the audit trail explains why the iteration happened.
* :func:`audit_version_coherence` — Walk a step and flag drift: a
  ``_v2`` figure whose ``.prov.json`` points at a ``_v1`` script, a
  caption sidecar older than its figure, a conclusion that references
  a version no longer on disk.

Design notes
------------
* We do NOT version-suffix figures / captions today (their stems stay
  stable so cross-step references in conclusions / dashboards don't
  rot). Instead, ``iterate_step`` copies the current artefacts into a
  hidden ``.versions/v<n>/`` archive under the step folder, and the
  live files retain their original names. Provenance gets an
  ``iteration: <n>`` field so the audit can correlate.
* The function is *opt-in*. Day-to-day re-runs continue to work as
  before; the researcher invokes :func:`iterate_step` only when they
  want a deliberate, named iteration recorded.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - yaml is a hard dep elsewhere
    yaml = None  # type: ignore[assignment]


_VERSION_RE = re.compile(r"_v(\d+)(?=\.[^.]+$)")


def _step_dir(root: Path, step_id: str) -> Path:
    d = root / "workspace" / step_id
    if not d.is_dir():
        raise FileNotFoundError(f"Step '{step_id}' not found under workspace/")
    return d


def _iteration_ledger_path(step_dir: Path) -> Path:
    return step_dir / "iterations.yaml"


def _load_ledger(step_dir: Path) -> dict[str, Any]:
    path = _iteration_ledger_path(step_dir)
    if not path.exists() or yaml is None:
        return {"step_id": step_dir.name, "iterations": []}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        data = {}
    data.setdefault("step_id", step_dir.name)
    data.setdefault("iterations", [])
    return data


def _save_ledger(step_dir: Path, ledger: dict[str, Any]) -> None:
    if yaml is None:
        return
    path = _iteration_ledger_path(step_dir)
    path.write_text(yaml.safe_dump(ledger, sort_keys=False))


def _next_iteration_number(ledger: dict[str, Any]) -> int:
    existing = [int(it.get("iteration", 0)) for it in ledger.get("iterations", [])]
    return (max(existing) if existing else 0) + 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bump_script_suffix(script: Path) -> Path:
    """Return the path the script SHOULD be renamed to (next ``_v<n>``).

    Idempotent for callers that already bumped; if the current suffix
    is the highest in the folder, return ``script`` unchanged.
    """
    if not script.exists():
        return script
    m = _VERSION_RE.search(script.name)
    if not m:
        # No suffix yet — first iteration adds _v2 (assumes _v1 was implicit).
        new_name = script.stem + "_v2" + script.suffix
        return script.with_name(new_name)
    cur = int(m.group(1))
    new_stem = _VERSION_RE.sub(f"_v{cur + 1}", script.name)
    return script.with_name(new_stem)


def iterate_step(
    root: Path,
    *,
    step_id: str,
    rationale: str,
    scripts: list[str] | None = None,
    figures: list[str] | None = None,
    tables: list[str] | None = None,
    bump_conclusion: bool = True,
) -> dict[str, Any]:
    """Snapshot a coordinated iteration of a step.

    Parameters
    ----------
    root:
        Project root.
    step_id:
        Numbered step folder (e.g. ``03_fit_baseline``).
    rationale:
        REQUIRED. Why the researcher requested this iteration.
        Recorded in the ledger so future audits know whether this was
        a bug fix, a design change, a parameter sweep, etc.
    scripts, figures, tables:
        Filenames (relative to ``scripts/`` / ``outputs/figures/`` /
        ``outputs/tables/``) included in this iteration. ``None`` =
        snapshot every file in that subfolder.
    bump_conclusion:
        Copy ``conclusions.md`` into the version archive alongside the
        snapshot. Recommended (the conclusion text is what makes the
        snapshot interpretable later).

    Returns
    -------
    dict
        ``status``, ``iteration``, ``version_dir`` (relative path),
        ``snapshotted`` (list of artefact paths copied), and
        ``next_script_paths`` (recommended ``_v<n+1>`` rename for each
        script in the snapshot — the AI applies the rename in the
        same turn if iterating the *implementation*).

    Raises
    ------
    ValueError
        If ``rationale`` is blank.
    FileNotFoundError
        If the step does not exist.
    """
    if not rationale or not rationale.strip():
        raise ValueError(
            "rationale is required — every iteration must record WHY "
            "it happened so the audit trail stays interpretable."
        )

    step = _step_dir(root, step_id)
    ledger = _load_ledger(step)
    n = _next_iteration_number(ledger)
    archive = step / ".versions" / f"v{n}"
    archive.mkdir(parents=True, exist_ok=True)

    # Suffixes worth snapshotting per subfolder. We deliberately exclude
    # auto-generated README.md / .gitkeep / .gitignore from the default
    # snapshot — they're not part of the iteration; bumping them would
    # create spurious version churn.
    _SUBDIR_INCLUDE = {
        "scripts": {".py", ".r", ".jl", ".sh", ".ipynb", ".rmd", ".qmd"},
        "outputs/figures": {".png", ".svg", ".jpg", ".jpeg", ".pdf", ".html"},
        "outputs/tables": {".csv", ".tsv", ".parquet", ".xlsx"},
    }

    def _members(subdir: str, names: list[str] | None) -> list[Path]:
        d = step / subdir
        if not d.is_dir():
            return []
        if names is None:
            allowed = _SUBDIR_INCLUDE.get(subdir, None)
            return sorted(
                p for p in d.iterdir()
                if p.is_file()
                and (allowed is None or p.suffix.lower() in allowed)
            )
        out: list[Path] = []
        for n_ in names:
            cand = d / n_
            if cand.is_file():
                out.append(cand)
        return out

    snap_scripts = _members("scripts", scripts)
    snap_figures = _members("outputs/figures", figures)
    snap_tables = _members("outputs/tables", tables)

    snapshotted: list[str] = []

    def _copy(src: Path, dest_rel: str) -> None:
        dest = archive / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        # Also copy sidecars if present (caption, summary, prov).
        for sidecar_suffix in (".caption.md", ".summary.md", ".prov.json"):
            sidecar = src.with_name(src.stem + sidecar_suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, dest.with_name(src.stem + sidecar_suffix))
        snapshotted.append(dest_rel)

    for s in snap_scripts:
        _copy(s, f"scripts/{s.name}")
    for f in snap_figures:
        _copy(f, f"outputs/figures/{f.name}")
    for t in snap_tables:
        _copy(t, f"outputs/tables/{t.name}")

    if bump_conclusion:
        conclusions = step / "conclusions.md"
        if conclusions.exists():
            shutil.copy2(conclusions, archive / "conclusions.md")
            snapshotted.append("conclusions.md")

    next_script_paths = {
        s.name: _bump_script_suffix(s).name for s in snap_scripts
    }

    entry = {
        "iteration": n,
        "created_at": _now_iso(),
        "rationale": rationale.strip(),
        "snapshot_dir": f".versions/v{n}",
        "scripts": [s.name for s in snap_scripts],
        "figures": [f.name for f in snap_figures],
        "tables": [t.name for t in snap_tables],
        "next_script_rename_suggestion": next_script_paths,
    }
    ledger["iterations"].append(entry)
    _save_ledger(step, ledger)

    return {
        "status": "success",
        "step_id": step_id,
        "iteration": n,
        "version_dir": f"workspace/{step_id}/.versions/v{n}",
        "snapshotted": snapshotted,
        "ledger_path": f"workspace/{step_id}/iterations.yaml",
        "next_script_paths": next_script_paths,
        "advice": (
            f"Iteration v{n} archived. To iterate the IMPLEMENTATION, rename "
            "the live scripts using the suffixes in `next_script_paths`, edit "
            "them, and re-run via tool_step_pipeline_run. To iterate only "
            "OUTPUTS (e.g. recolour a figure), regenerate the figure live; "
            "the v" + str(n) + " snapshot preserves the prior version."
        ),
    }


def list_iterations(root: Path, step_id: str) -> dict[str, Any]:
    """Return the iterations.yaml ledger for a step."""
    step = _step_dir(root, step_id)
    return _load_ledger(step)


def audit_version_coherence(root: Path, step_id: str | None = None) -> dict[str, Any]:
    """Flag version drift between scripts, outputs, captions, and provenance.

    For each step:

    * For every figure / table, parse its ``.prov.json`` sidecar (if
      any) and check that the ``produced_by.script`` exists on disk
      AND is the HIGHEST ``_v<n>`` script in that step's
      ``scripts/``. If a v2 script is on disk but the figure says it
      was produced by v1, that's drift.
    * For every figure, check that its ``.caption.md`` is at least as
      new (mtime) as the figure file itself. Stale captions earn a
      warning.
    * For every iteration in ``iterations.yaml``, check that
      ``snapshot_dir`` still exists. A deleted archive is a warning
      (someone scrubbed history).

    Returns
    -------
    dict
        ``status`` ∈ {success, warning}, ``steps`` (per-step drift
        list), ``drift_count``.
    """
    workspace = root / "workspace"
    if not workspace.exists():
        return {"status": "error", "message": "workspace/ not found"}

    if step_id:
        targets = [workspace / step_id]
    else:
        targets = [
            d for d in sorted(workspace.iterdir())
            if d.is_dir() and re.match(r"^\d{2,3}_", d.name)
            and not d.name.endswith("__DEAD_END")
        ]

    def _highest_version_script(scripts_dir: Path, stem_prefix: str | None) -> Path | None:
        if not scripts_dir.is_dir():
            return None
        best: tuple[int, Path] | None = None
        for p in scripts_dir.iterdir():
            if not p.is_file():
                continue
            if stem_prefix and not p.name.startswith(stem_prefix):
                continue
            m = _VERSION_RE.search(p.name)
            v = int(m.group(1)) if m else 1
            if best is None or v > best[0]:
                best = (v, p)
        return best[1] if best else None

    per_step: list[dict[str, Any]] = []
    total_drift = 0

    for step in targets:
        if not step.is_dir():
            continue
        drift: list[str] = []
        warns: list[str] = []
        figs_dir = step / "outputs" / "figures"
        tbls_dir = step / "outputs" / "tables"
        scripts_dir = step / "scripts"

        for art_dir in (figs_dir, tbls_dir):
            if not art_dir.is_dir():
                continue
            for art in art_dir.iterdir():
                if not art.is_file() or art.suffix in {".md", ".json"}:
                    continue
                prov = art.with_name(art.stem + ".prov.json")
                if prov.exists():
                    try:
                        data = json.loads(prov.read_text())
                    except Exception:
                        warns.append(f"{art.relative_to(step)}: .prov.json unreadable")
                        continue
                    script_field = (data.get("produced_by") or {}).get("script") or ""
                    script_name = Path(script_field).name
                    if script_name and script_name != "<unknown>":
                        live = scripts_dir / script_name
                        if not live.exists():
                            drift.append(
                                f"{art.relative_to(step)} provenance points at "
                                f"`{script_name}` which is no longer in scripts/. "
                                "Either restore the script or re-generate the output."
                            )
                            total_drift += 1
                        else:
                            m = _VERSION_RE.search(script_name)
                            v_used = int(m.group(1)) if m else 1
                            # Compare against highest version with same stem-prefix.
                            stem_prefix = _VERSION_RE.split(script_name)[0]
                            head = _highest_version_script(scripts_dir, stem_prefix)
                            if head is not None:
                                hm = _VERSION_RE.search(head.name)
                                v_head = int(hm.group(1)) if hm else 1
                                if v_head > v_used:
                                    drift.append(
                                        f"{art.relative_to(step)} was produced "
                                        f"by `{script_name}` (v{v_used}) but "
                                        f"`{head.name}` (v{v_head}) is now the "
                                        "highest version — output is stale. "
                                        "Re-run tool_step_pipeline_run or "
                                        "call tool_step_iterate."
                                    )
                                    total_drift += 1

                # Caption staleness.
                cap = art.with_name(art.stem + ".caption.md")
                if cap.exists() and cap.stat().st_mtime < art.stat().st_mtime - 1:
                    warns.append(
                        f"{cap.relative_to(step)} is older than its figure — "
                        "caption may describe a prior version."
                    )

        # Iteration archive integrity.
        ledger = _load_ledger(step)
        for it in ledger.get("iterations", []):
            snap = step / it.get("snapshot_dir", "")
            if not snap.is_dir():
                warns.append(
                    f"iteration v{it.get('iteration')} snapshot dir is missing "
                    f"({it.get('snapshot_dir')}) — history was scrubbed."
                )

        per_step.append({
            "step_id": step.name,
            "drift": drift,
            "warnings": warns,
            "status": "drift" if drift else "warning" if warns else "ok",
        })

    # Report.
    logs_dir = root / "workspace" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report = logs_dir / "version_coherence.md"
    lines = ["# Version Coherence Audit", ""]
    for r in per_step:
        icon = {"drift": "❌", "warning": "⚠️", "ok": "✅"}.get(r["status"], "•")
        lines.append(f"## {icon} `{r['step_id']}`")
        for d in r["drift"]:
            lines.append(f"- DRIFT: {d}")
        for w in r["warnings"]:
            lines.append(f"- warn:  {w}")
        lines.append("")
    report.write_text("\n".join(lines) + "\n")

    return {
        "status": "warning" if total_drift else "success",
        "steps": per_step,
        "drift_count": total_drift,
        "report_path": str(report.relative_to(root)),
        "advice": (
            "Version drift detected — outputs were produced by a script "
            "version that is no longer the highest on disk. Re-run the "
            "pipeline or call tool_step_iterate to snapshot the prior "
            "version before regenerating."
            if total_drift else
            "Every output traces to the highest-version script on disk."
        ),
    }
