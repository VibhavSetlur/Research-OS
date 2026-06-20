"""Per-output-file provenance sidecars (PROV-O / RO-Crate compatible).

Every artefact a research step persists — a figure, a table, a model
pickle, a derived CSV — must carry an immutable record of how it was
produced so a reviewer five years from now can rebuild the same file
byte-for-byte. The pattern follows W3C PROV-O at the sidecar level and
maps cleanly to RO-Crate at the project level.

Layout
------
For an output file at ``workspace/<step>/outputs/figures/03_curve.png``
this module writes ``workspace/<step>/outputs/figures/03_curve.prov.json``
with the following structure::

    {
      "@context": {"prov": "http://www.w3.org/ns/prov#"},
      "@type": "prov:Entity",
      "@id": "workspace/03_baseline/outputs/figures/03_curve.png",
      "produced_by": {
        "script": "scripts/03_baseline_v1.py",
        "tool":   "ai_authored_script",
        "git_sha": "a1b2c3d…" | null,
        "wf_node": "fit"               // sub-task DAG node, if available
      },
      "inputs":  { "data/input/clean.csv": "sha256:…", … },
      "params":  { "alpha": 0.05, "model": "logit", … },
      "rng_seed": 42,
      "software": {
        "python":  "3.11.7",
        "platform": "Linux-6.17.0-29-generic-x86_64-with-glibc2.39",
        "packages": { "numpy": "1.26.4", "pandas": "2.1.4", … }
      },
      "runtime": {
        "started_at": "2026-05-28T14:30:01Z",
        "ended_at":   "2026-05-28T14:30:08Z",
        "wall_seconds": 7.12,
        "host": "node07"
      },
      "output": {
        "sha256": "ec3a…",
        "size_bytes": 23104
      },
      "step_id": "03_baseline"
    }

That structure is enough to power: claim-grounding (each number cited
in the paper can be traced to the file it came from), reproducibility
audits (re-run the script with the same inputs + params + seed → expect
the same output sha256), and journal-grade RO-Crate publication
(every Entity already carries the required PROV-O properties).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("research_os.provenance")


# Library versions we consider "load-bearing" for analysis output. The list
# is intentionally short — too many entries slows down every save and adds
# noise; this is the set whose version changes most commonly invalidate a
# downstream analysis.
_KEY_PACKAGES = (
    "numpy", "pandas", "scipy", "scikit-learn", "statsmodels",
    "matplotlib", "seaborn", "plotnine", "plotly",
    "torch", "tensorflow", "jax", "transformers",
    "pyarrow", "openpyxl", "xlrd",
    "lifelines", "shap", "xgboost", "lightgbm",
)


def _package_versions(extra: Iterable[str] | None = None) -> dict[str, str]:
    """Snapshot the installed versions of every package this analysis is
    likely to depend on. Silently skips packages that aren't installed."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover — Python < 3.8
        return {}
    out: dict[str, str] = {}
    names = set(_KEY_PACKAGES) | set(extra or ())
    for name in sorted(names):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            continue
        except Exception as e:
            logger.debug("version lookup failed for %s: %s", name, e)
    return out


def _runtime_version(language: str) -> str | None:
    """Best-effort interpreter version for a non-Python runtime.

    Shells out to ``R --version`` / ``julia --version`` (mirroring
    ``exec/environment.py``). Returns the first informative line, or
    ``None`` when the interpreter is absent or the call fails. Never
    raises — provenance writing must not crash on a missing toolchain.
    """
    lang = (language or "").lower()
    if lang in ("r", "rmarkdown", "rmd"):
        cmd = ["R", "--version"]
    elif lang == "julia":
        cmd = ["julia", "--version"]
    else:
        return None
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5,
        )
        out = (res.stdout or "").strip()
        if out:
            return out.splitlines()[0].strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as e:
        logger.debug("%s version lookup failed: %s", lang, e)
    return None


def _foreign_packages(language: str, root: Path) -> dict[str, str]:
    """Best-effort package versions for an R / Julia analysis.

    Parses ``renv.lock`` (R) or ``Manifest.toml`` (Julia) at the project
    root. Returns ``{}`` when no lockfile is present or parsing fails —
    this is a best-effort enrichment, never a hard requirement.
    """
    lang = (language or "").lower()
    out: dict[str, str] = {}
    try:
        if lang in ("r", "rmarkdown", "rmd"):
            lock = root / "renv.lock"
            if not lock.exists():
                return out
            data = json.loads(lock.read_text())
            pkgs = data.get("Packages") or {}
            for name, meta in pkgs.items():
                if isinstance(meta, dict) and meta.get("Version"):
                    out[str(name)] = str(meta["Version"])
        elif lang == "julia":
            manifest = root / "Manifest.toml"
            if not manifest.exists():
                return out
            try:
                import tomllib  # type: ignore[import-not-found]
            except ImportError:  # pragma: no cover — Python < 3.11
                return out
            data = tomllib.loads(manifest.read_text())
            # Manifest.toml v2 nests deps under a top-level "deps" table;
            # v1 lists them at the top level. Handle both.
            deps = data.get("deps", data)
            if isinstance(deps, dict):
                for name, entries in deps.items():
                    if name in ("julia_version", "manifest_format", "project_hash"):
                        continue
                    if isinstance(entries, list) and entries:
                        ver = entries[0].get("version") if isinstance(entries[0], dict) else None
                        if ver:
                            out[str(name)] = str(ver)
    except Exception as e:  # noqa: BLE001 — best-effort; never crash provenance
        logger.debug("foreign package lookup failed for %s: %s", lang, e)
    return out


def _git_sha(repo_root: Path) -> str | None:
    """Best-effort short commit SHA for the project's repo."""
    if not (repo_root / ".git").exists():
        return None
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        sha = res.stdout.strip()
        if sha:
            # Also note whether the worktree is dirty.
            try:
                dirty = subprocess.run(
                    ["git", "-C", str(repo_root), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=2,
                )
                if dirty.stdout.strip():
                    sha += "-dirty"
            except Exception:
                pass
            return sha
    except Exception:
        pass
    return None


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    except (FileNotFoundError, PermissionError, OSError):
        return "sha256:unavailable"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _input_hashes(
    inputs: dict[str, Path] | list[Path] | list[str] | None, root: Path,
) -> dict[str, str]:
    """Normalise an inputs spec to {rel_path: sha256}.

    Accepts a dict of label→path, a list of Paths, or a list of path strings.
    Files that don't exist are recorded as 'missing' so a re-run can flag the
    gap immediately.
    """
    out: dict[str, str] = {}
    if inputs is None:
        return out
    if isinstance(inputs, dict):
        items = inputs.items()
    else:
        items = [(str(p), Path(p) if not isinstance(p, Path) else p) for p in inputs]
    for label, raw in items:
        p = Path(raw) if not isinstance(raw, Path) else raw
        if not p.is_absolute():
            p = root / p
        rel = _relative(p, root)
        if not p.exists():
            out[rel if isinstance(label, str) and label == rel else str(label)] = "missing"
            continue
        out[rel] = _file_sha256(p)
    return out


def write_output_provenance(
    *,
    output_path: Path | str,
    root: Path,
    produced_by: dict[str, Any] | None = None,
    inputs: dict[str, Any] | list[Any] | None = None,
    params: dict[str, Any] | None = None,
    rng_seed: int | None = None,
    step_id: str | None = None,
    started_at: str | None = None,
    wall_seconds: float | None = None,
    extra_packages: Iterable[str] | None = None,
    extra: dict[str, Any] | None = None,
    language: str = "python",
) -> Path:
    """Write a ``<output>.prov.json`` sidecar describing one produced artefact.

    Parameters
    ----------
    output_path:
        The artefact that was just written. Path on disk; the sidecar is
        written alongside.
    root:
        Project root (used to relativise paths in the manifest).
    produced_by:
        Dict with any of: ``script``, ``tool``, ``wf_node``. ``git_sha``
        is filled in automatically. If omitted, a best-effort
        ``{"script": "<unknown>"}`` is recorded.
    inputs:
        Either {label: path-or-Path} or a sequence of paths. Each is
        hashed and recorded.
    params:
        The parameter dict the analysis ran with. Should be JSON-safe.
    rng_seed:
        The random seed. Recorded explicitly because it is the single
        most common reason a re-run produces a different byte sequence.
    step_id:
        Numbered step folder (e.g. ``03_baseline``) — auto-derived from
        the output path when omitted.
    started_at, wall_seconds:
        Set by the ``track_runtime`` context manager. Pass through here.
    extra_packages:
        Extra package names whose versions should be captured beyond
        ``_KEY_PACKAGES``.
    extra:
        Arbitrary additional metadata merged into the sidecar.
    language:
        The runtime that produced the artefact (``"python"`` by default,
        or ``"r"`` / ``"julia"`` / ``"shell"``). When non-Python, the
        ``software`` block records the foreign interpreter version (best
        effort) and foreign package versions from ``renv.lock`` /
        ``Manifest.toml`` instead of falsely claiming a Python stack; the
        MCP server's own Python is still recorded under
        ``mcp_server_python`` for traceability.
    """
    output_path = Path(output_path)
    root = Path(root)
    if not output_path.is_absolute():
        output_path = root / output_path
    rel_out = _relative(output_path, root)
    sidecar = output_path.with_suffix(output_path.suffix + ".prov.json") \
        if output_path.suffix else output_path.with_suffix(".prov.json")
    # For files like figures/foo.png we want foo.prov.json next to it, not
    # foo.png.prov.json. Use a flat ".prov.json" convention on the stem.
    sidecar = output_path.with_name(output_path.stem + ".prov.json")

    # Derive step_id from path if not given.
    if step_id is None:
        try:
            parts = output_path.resolve().relative_to(root.resolve()).parts
            if len(parts) >= 2 and parts[0] == "workspace":
                step_id = parts[1]
        except Exception:
            pass

    producer = dict(produced_by or {})
    producer.setdefault("script", "<unknown>")
    if "git_sha" not in producer:
        sha = _git_sha(root)
        if sha:
            producer["git_sha"] = sha

    # Build the software block language-aware. A Python-only block on an
    # R / Julia artefact is actively misleading — it claims a runtime and
    # packages that had nothing to do with producing the file.
    lang = (language or "python").lower()
    if lang == "python":
        software: dict[str, Any] = {
            "runtime_language": "python",
            "python": ".".join(map(str, sys.version_info[:3])),
            "platform": platform.platform(),
            "packages": _package_versions(extra_packages),
        }
    else:
        software = {
            "runtime_language": lang,
            "platform": platform.platform(),
            # The MCP server's interpreter, labelled so it is never
            # mistaken for the analysis runtime.
            "mcp_server_python": ".".join(map(str, sys.version_info[:3])),
            "interpreter_version": _runtime_version(lang),
            "packages": _foreign_packages(lang, root),
        }

    record: dict[str, Any] = {
        "@context": {"prov": "http://www.w3.org/ns/prov#"},
        "@type": "prov:Entity",
        "@id": rel_out,
        "step_id": step_id,
        "produced_by": producer,
        "inputs": _input_hashes(inputs, root),
        "params": params or {},
        "rng_seed": rng_seed,
        "software": software,
        "runtime": {
            "started_at": started_at or datetime.now(timezone.utc).isoformat(),
            "ended_at":   datetime.now(timezone.utc).isoformat(),
            "wall_seconds": float(wall_seconds) if wall_seconds is not None else None,
            "host": socket.gethostname(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME"),
        },
        "output": {
            "sha256": _file_sha256(output_path),
            "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        },
    }
    if extra:
        record.update(extra)

    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return sidecar


@contextmanager
def track_runtime():
    """Context manager that yields a dict you pass to ``write_output_provenance``.

    Usage::

        with track_runtime() as rt:
            ... do the analysis ...
        write_output_provenance(
            output_path=out,
            root=root,
            wall_seconds=rt["wall_seconds"],
            started_at=rt["started_at"],
            ...
        )
    """
    start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {"started_at": started_at, "wall_seconds": None}
    try:
        yield payload
    finally:
        payload["wall_seconds"] = round(time.time() - start, 4)


def load_provenance(output_path: Path | str, root: Path) -> dict[str, Any] | None:
    """Read the sidecar for an output file, or None if absent."""
    output_path = Path(output_path)
    root = Path(root)
    if not output_path.is_absolute():
        output_path = root / output_path
    sidecar = output_path.with_name(output_path.stem + ".prov.json")
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text())
    except Exception:
        return None


def step_provenance_inventory(step_dir: Path, root: Path) -> dict[str, Any]:
    """Walk a step's outputs/ tree and report sidecar coverage.

    Returns a dict::

        {
          "total_outputs": 12,
          "with_provenance": 9,
          "missing_provenance": ["outputs/figures/03_hist.png", …],
          "newest_sidecar": "outputs/figures/03_calibration.prov.json",
        }

    Used by ``tool_audit_step_completeness`` to gate synthesis on
    provenance coverage.
    """
    from research_os.project_ops import step_output_dir
    out_dir = step_dir / "outputs"
    data_out = step_output_dir(step_dir)
    targets = []
    sidecar_suffixes = (".prov.json", ".caption.md", ".summary.md")
    for base in (out_dir, data_out):
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            # Skip auxiliary sidecars themselves. `.suffix` only returns
            # the LAST extension; check the full name.
            if any(f.name.endswith(s) for s in sidecar_suffixes):
                continue
            if f.name in {"README.md", ".gitkeep"}:
                continue
            if f.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg", ".pdf",
                                     ".csv", ".tsv", ".json", ".parquet",
                                     ".feather", ".pkl", ".joblib", ".npz",
                                     ".h5", ".hdf5", ".md"}:
                targets.append(f)
    have: list[str] = []
    missing: list[str] = []
    for f in targets:
        sidecar = f.with_name(f.stem + ".prov.json")
        if sidecar.exists():
            have.append(_relative(f, root))
        else:
            missing.append(_relative(f, root))
    newest = None
    if have:
        try:
            sidecars = [
                step_dir / f.replace(_relative(step_dir, root) + "/", "", 1)
                for f in have
            ]
            newest_path = max(
                (s.with_name(Path(s).stem + ".prov.json") for s in sidecars),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
            )
            newest = _relative(newest_path, root)
        except Exception:
            pass
    return {
        "step_id": step_dir.name,
        "total_outputs": len(targets),
        "with_provenance": len(have),
        "missing_provenance": missing,
        "coverage_pct": round(
            100 * len(have) / max(1, len(targets)), 1,
        ),
        "newest_sidecar": newest,
    }


__all__ = [
    "load_provenance",
    "step_provenance_inventory",
    "track_runtime",
    "write_output_provenance",
]
