"""Environment snapshotting and Docker generation.

Snapshots are written into the *active experiment*'s ``environment/`` so that
each experiment can be reproduced independently. A root-level ``environment/``
is used as a fallback when no experiment is active.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("research_os.tools.environment")


def package_install(packages: list[str]) -> dict[str, Any]:
    """``pip install`` the requested packages."""
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", *packages],
            capture_output=True,
            text=True,
        )
        status = "success" if res.returncode == 0 else "error"
        return {
            "status": status,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "code": res.returncode,
        }
    except Exception as e:
        logger.exception("package_install failed")
        return {"status": "error", "error": str(e), "code": 1}


def _detect_languages_in_use(root: Path) -> set[str]:
    """Scan workspace + project root for evidence of each language.

    v1.3.0: env_snapshot used to capture Python unconditionally and
    only capture R/Julia/conda when their lock files existed at
    project root. Researchers running an R-only or Julia-only project
    saw a meaningless Python pip-freeze in their environment/ folder
    and no R/Julia capture. This helper looks at what scripts actually
    EXIST under workspace/ to decide which captures matter.

    Returns the set of detected language tags:
      {"python", "r", "julia", "quarto", "rmarkdown", "shell", "node"}
    """
    detected: set[str] = set()
    ext_to_lang = {
        ".py": "python", ".ipynb": "python",
        ".r": "r", ".R": "r", ".Rmd": "rmarkdown",
        ".jl": "julia",
        ".qmd": "quarto",
        ".sh": "shell", ".bash": "shell",
        ".js": "node", ".ts": "node", ".mjs": "node",
    }
    ws = root / "workspace"
    if ws.exists():
        for p in ws.rglob("*"):
            if not p.is_file():
                continue
            suffix = p.suffix
            if suffix in ext_to_lang:
                detected.add(ext_to_lang[suffix])
            # Also check the lowercased suffix for ".R" vs ".r".
            elif suffix.lower() in ext_to_lang:
                detected.add(ext_to_lang[suffix.lower()])
    # Project-root lock files are also signal.
    if (root / "renv.lock").exists() or (root / "DESCRIPTION").exists():
        detected.add("r")
    if (root / "Project.toml").exists():
        detected.add("julia")
    if (root / "environment.yml").exists() or (root / "environment.yaml").exists():
        detected.add("conda")
    # Default fallback: if nothing detected (fresh project), assume the
    # researcher will use python — it remains the most common.
    if not detected:
        detected = {"python"}
    return detected


def _active_experiment_dir(root: Path) -> Path | None:
    ws = root / "workspace"
    if not ws.exists():
        return None
    active = [
        p
        for p in ws.iterdir()
        if p.is_dir()
        and p.name[:2].isdigit()
        and "_" in p.name
        and not p.name.endswith("__DEAD_END")
    ]
    return sorted(active)[-1] if active else None


def env_snapshot(
    root: Path, *, step_id: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """Snapshot Python (always) and any detected R/Julia/Conda configs.

    Target directory rules (v1.3.0):
      * If ``step_id`` is given, snapshot into
        ``workspace/<step_id>/environment/``.
      * Else if ``scope='project'``, snapshot into the project-global
        ``environment/`` (the eager-scaffolded folder created at init).
      * Else (legacy default), snapshot into the most-recent active
        numbered step's environment, or the project-global folder if
        there are no numbered steps yet.
    """
    try:
        if step_id:
            target = root / "workspace" / step_id
            if not target.is_dir():
                return {
                    "status": "error",
                    "message": f"step_id '{step_id}' not found under workspace/",
                }
            env_dir = target / "environment"
        elif scope == "project":
            env_dir = root / "environment"
        else:
            active = _active_experiment_dir(root)
            env_dir = (active or root) / "environment"
        env_dir.mkdir(parents=True, exist_ok=True)
        session: dict[str, Any] = {"languages": []}

        # v1.3.0: detect which languages this project actually uses by
        # scanning workspace scripts. Capture all of them — not just
        # Python — so R-only and Julia-only projects don't end up with
        # a meaningless pip-freeze.
        in_use = _detect_languages_in_use(root)
        session["detected_languages"] = sorted(in_use)

        # ── Python ────────────────────────────────────────────────
        if "python" in in_use:
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "pip", "freeze"],
                    capture_output=True, text=True, timeout=60,
                )
                if res.returncode == 0:
                    (env_dir / "requirements.txt").write_text(res.stdout)
                    session["languages"].append({
                        "name": "python",
                        "version": sys.version.split()[0],
                        "manager": "pip",
                        "file": "requirements.txt",
                    })
            except Exception as e:
                logger.warning(f"Python snapshot failed: {e}")

        # ── R ─────────────────────────────────────────────────────
        if "r" in in_use or "rmarkdown" in in_use:
            captured = []
            # renv.lock at project root → copy it.
            r_lock = root / "renv.lock"
            if r_lock.exists():
                shutil.copy(r_lock, env_dir / "renv.lock")
                captured.append("renv.lock")
            # DESCRIPTION file (R package manifest) → copy it.
            desc = root / "DESCRIPTION"
            if desc.exists():
                shutil.copy(desc, env_dir / "DESCRIPTION")
                captured.append("DESCRIPTION")
            # Try `R --version` for record-keeping (best-effort).
            r_version = None
            try:
                r_v = subprocess.run(
                    ["R", "--version"], capture_output=True, text=True, timeout=10,
                )
                if r_v.returncode == 0:
                    r_version = r_v.stdout.splitlines()[0]
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            session["languages"].append({
                "name": "R",
                "version": r_version,
                "manager": "renv" if "renv.lock" in captured else "(no lock file)",
                "files": captured or ["(none — add renv.lock or DESCRIPTION)"],
            })

        # ── Julia ─────────────────────────────────────────────────
        if "julia" in in_use:
            captured = []
            for fname in ("Project.toml", "Manifest.toml"):
                p = root / fname
                if p.exists():
                    shutil.copy(p, env_dir / fname)
                    captured.append(fname)
            julia_version = None
            try:
                jv = subprocess.run(
                    ["julia", "--version"], capture_output=True, text=True,
                    timeout=10,
                )
                if jv.returncode == 0:
                    julia_version = jv.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            session["languages"].append({
                "name": "julia",
                "version": julia_version,
                "manager": "Pkg",
                "files": captured or ["(none — run Pkg.activate(); Pkg.instantiate() then commit Project.toml + Manifest.toml)"],
            })

        # ── Quarto ────────────────────────────────────────────────
        if "quarto" in in_use:
            q_yml = root / "_quarto.yml"
            if q_yml.exists():
                shutil.copy(q_yml, env_dir / "_quarto.yml")
            qv = None
            try:
                qr = subprocess.run(
                    ["quarto", "--version"], capture_output=True, text=True,
                    timeout=10,
                )
                if qr.returncode == 0:
                    qv = qr.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            session["languages"].append({
                "name": "quarto",
                "version": qv,
                "manager": "quarto",
                "files": ["_quarto.yml"] if q_yml.exists() else [],
            })

        # ── Shell / Bash ──────────────────────────────────────────
        if "shell" in in_use:
            session["languages"].append({
                "name": "shell",
                "manager": "system",
                "files": [],
                "note": "Shell scripts captured by version control; "
                        "list system-package dependencies (apt/brew/yum) "
                        "in a Dockerfile or environment/README.md.",
            })

        # ── Node ──────────────────────────────────────────────────
        if "node" in in_use:
            captured = []
            for fname in ("package.json", "package-lock.json", "yarn.lock"):
                p = root / fname
                if p.exists():
                    shutil.copy(p, env_dir / fname)
                    captured.append(fname)
            session["languages"].append({
                "name": "node",
                "manager": "npm / yarn",
                "files": captured,
            })

        # ── Conda (project-level) ─────────────────────────────────
        for fname in ("environment.yml", "environment.yaml"):
            conda_env = root / fname
            if conda_env.exists():
                shutil.copy(conda_env, env_dir / fname)
                session["languages"].append({
                    "name": "conda",
                    "manager": "conda",
                    "files": [fname],
                })
                break

        (env_dir / "session.yaml").write_text(yaml.dump(session, sort_keys=False))
        return {
            "status": "success",
            "session": session,
            "snapshot_dir": str(env_dir.relative_to(root)),
            "languages_captured": [lang["name"] for lang in session["languages"]],
            "message": "Environment snapshotted.",
        }
    except Exception as e:
        logger.exception("env_snapshot failed")
        return {"status": "error", "message": str(e)}


def step_env_lock(
    root: Path,
    *,
    step_id: str | None = None,
    write_conda_yaml: bool = False,
    write_dockerfile: bool = False,
    write_apptainer: bool = False,
    write_entrypoint: bool = True,
) -> dict[str, Any]:
    """Lock the current Python (+ optional R/Julia/conda) env into a SPECIFIC step.

    Writes:
      workspace/<step>/environment/requirements.txt   (pip freeze)
      workspace/<step>/environment/python_version.txt
      workspace/<step>/environment/session.yaml       (manifest of languages)
      workspace/<step>/environment/conda.yaml         (if write_conda_yaml)
      workspace/<step>/environment/Dockerfile         (if write_dockerfile)

    Unlike env_snapshot (which auto-targets the most-recent numbered step),
    this tool requires an explicit step_id so years-later reproduction is
    deterministic. If step_id is omitted, falls back to the active step
    with a clear warning in the response.
    """
    try:
        if step_id:
            step_dir = root / "workspace" / step_id
            if not step_dir.is_dir():
                return {
                    "status": "error",
                    "message": (
                        f"Step `{step_id}` not found under workspace/. "
                        "Check the numbered slug or call sys_path_list first."
                    ),
                }
            warning = None
        else:
            active = _active_experiment_dir(root)
            if not active:
                return {
                    "status": "error",
                    "message": "No step_id given and no active numbered step found.",
                }
            step_dir = active
            warning = (
                f"step_id omitted — defaulted to most-recent active step "
                f"`{active.name}`. Pass step_id explicitly for deterministic "
                "long-term reproduction."
            )

        env_dir = step_dir / "environment"
        env_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[str] = []

        # Pin the interpreter version explicitly — pip freeze doesn't.
        py_version = sys.version.split()[0]
        (env_dir / "python_version.txt").write_text(py_version + "\n")
        artifacts.append("python_version.txt")

        # pip freeze
        res = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode == 0:
            (env_dir / "requirements.txt").write_text(res.stdout)
            artifacts.append("requirements.txt")
        else:
            return {
                "status": "error",
                "message": f"pip freeze failed: {res.stderr.strip()}",
            }

        session: dict[str, Any] = {
            "step_id": step_dir.name,
            "locked_at": _now_iso(),
            "languages": [
                {"name": "python", "version": py_version, "manager": "pip"}
            ],
        }

        # R / Julia / conda passthroughs — only if a project-level lockfile
        # exists. Step-local copies make the step self-contained.
        for lock_name, lang, manager in [
            ("renv.lock", "R", "renv"),
            ("Project.toml", "julia", "Pkg"),
            ("environment.yml", "conda", "conda"),
        ]:
            src = root / lock_name
            if src.exists():
                shutil.copy(src, env_dir / lock_name)
                session["languages"].append({"name": lang, "manager": manager})
                artifacts.append(lock_name)
                # Julia: also copy Manifest.toml if present.
                if lock_name == "Project.toml":
                    man = root / "Manifest.toml"
                    if man.exists():
                        shutil.copy(man, env_dir / "Manifest.toml")
                        artifacts.append("Manifest.toml")

        (env_dir / "session.yaml").write_text(
            yaml.dump(session, sort_keys=False)
        )
        artifacts.append("session.yaml")

        if write_conda_yaml:
            # Synthesize a conda.yaml that pins python + lists pip deps.
            conda_doc = {
                "name": f"research-os-{step_dir.name}",
                "channels": ["defaults"],
                "dependencies": [
                    f"python={py_version}",
                    "pip",
                    {
                        "pip": [
                            ln.strip()
                            for ln in (env_dir / "requirements.txt").read_text().splitlines()
                            if ln.strip() and not ln.startswith("#")
                        ]
                    },
                ],
            }
            (env_dir / "conda.yaml").write_text(yaml.dump(conda_doc, sort_keys=False))
            artifacts.append("conda.yaml")

        if write_dockerfile:
            lines = [
                f"# Auto-generated per-step Dockerfile for {step_dir.name}",
                "# Reproduces every output via the per-step entrypoint.sh.",
                f"FROM python:{py_version.rsplit('.', 1)[0]}-slim",
                "ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 \\",
                "    PYTHONUNBUFFERED=1 LC_ALL=C.UTF-8 LANG=C.UTF-8",
                "RUN apt-get update && apt-get install -y --no-install-recommends \\",
                "      build-essential git ca-certificates && \\",
                "    rm -rf /var/lib/apt/lists/*",
                "WORKDIR /step",
                "COPY environment/requirements.txt /step/environment/requirements.txt",
                "RUN pip install --no-cache-dir -r environment/requirements.txt",
                "COPY . /step",
                "ENTRYPOINT [\"bash\", \"environment/entrypoint.sh\"]",
            ]
            (env_dir / "Dockerfile").write_text("\n".join(lines) + "\n")
            artifacts.append("Dockerfile")

        if write_apptainer:
            # HPC-friendly Apptainer definition file. Builds on top of the
            # Dockerfile when present, or directly off python:slim.
            lines = [
                f"# Auto-generated per-step Apptainer definition for {step_dir.name}",
                "BootStrap: docker",
                f"From: python:{py_version.rsplit('.', 1)[0]}-slim",
                "",
                "%files",
                "    environment/requirements.txt /opt/req.txt",
                "",
                "%post",
                "    apt-get update && apt-get install -y --no-install-recommends \\",
                "        build-essential git ca-certificates",
                "    pip install --no-cache-dir -r /opt/req.txt",
                "    rm -rf /var/lib/apt/lists/*",
                "",
                "%environment",
                "    export LC_ALL=C.UTF-8",
                "    export LANG=C.UTF-8",
                "",
                "%runscript",
                "    cd /step && exec bash environment/entrypoint.sh \"$@\"",
                "",
                "%labels",
                f"    StepID {step_dir.name}",
                f"    Python {py_version}",
                f"    BuiltAt {_now_iso()}",
            ]
            (env_dir / "step.def").write_text("\n".join(lines) + "\n")
            artifacts.append("step.def")

        if write_entrypoint:
            # entrypoint.sh — single command that reproduces every output
            # by walking the step's sub-task DAG (pipeline.yaml). When no
            # pipeline.yaml exists, falls back to running every script in
            # scripts/ in alphabetical order.
            pipe_path = step_dir / "pipeline.yaml"
            if pipe_path.exists():
                cmd_block = (
                    "# Sub-task DAG present — walk it via the runner.\n"
                    "python -m research_os.tools.actions.exec.step_pipeline "
                    f"--step-id \"{step_dir.name}\" --root \"$(pwd)/../..\" "
                    "|| python -c \"from research_os.tools.actions.exec.step_pipeline "
                    f"import run_pipeline; from pathlib import Path; "
                    f"print(run_pipeline('{step_dir.name}', Path('$(pwd)/../..')))\""
                )
            else:
                cmd_block = (
                    "# No pipeline.yaml — run every script in scripts/ in order.\n"
                    "for script in scripts/*.py; do\n"
                    "    echo \"--- $script ---\"\n"
                    "    python \"$script\"\n"
                    "done"
                )
            entry = (
                "#!/usr/bin/env bash\n"
                f"# Auto-generated reproducer for {step_dir.name}.\n"
                "# Re-creates every output the step produced; meant to be the\n"
                "# single command that a reviewer / future-you runs.\n"
                "set -euo pipefail\n"
                "echo \"# entrypoint started $(date -u +%Y-%m-%dT%H:%M:%SZ) "
                "on $(hostname)\"\n"
                "\n"
                f"{cmd_block}\n"
                "\n"
                "echo \"# entrypoint finished $(date -u +%Y-%m-%dT%H:%M:%SZ)\"\n"
            )
            ep_path = env_dir / "entrypoint.sh"
            ep_path.write_text(entry)
            try:
                ep_path.chmod(0o755)
            except OSError:
                pass
            artifacts.append("entrypoint.sh")

        result = {
            "status": "success",
            "step_id": step_dir.name,
            "env_dir": str(env_dir.relative_to(root)),
            "artifacts": artifacts,
            "python_version": py_version,
            "package_count": len(
                [ln for ln in (env_dir / "requirements.txt").read_text().splitlines() if ln.strip()]
            ),
        }
        if warning:
            result["warning"] = warning
        return result
    except Exception as e:
        logger.exception("step_env_lock failed")
        return {"status": "error", "message": str(e)}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def env_docker_generate(root: Path) -> dict[str, Any]:
    """Generate a Dockerfile from the latest environment snapshot."""
    try:
        env_dir = root / "environment"
        session_file = env_dir / "session.yaml"

        langs: set[str] = set()
        if session_file.exists():
            data = yaml.safe_load(session_file.read_text()) or {}
            langs = {lang.get("name") for lang in data.get("languages", []) if lang.get("name")}

        lines = [
            "FROM python:3.11-slim",
            "ENV DEBIAN_FRONTEND=noninteractive",
            "RUN apt-get update && apt-get install -y --no-install-recommends \\",
            "    git build-essential curl wget ca-certificates && rm -rf /var/lib/apt/lists/*",
        ]

        if "R" in langs:
            lines.extend(
                [
                    "RUN apt-get update && apt-get install -y --no-install-recommends r-base \\",
                    "    && rm -rf /var/lib/apt/lists/*",
                ]
            )
        if "julia" in langs:
            # Pin via $JULIA_VERSION env, easy to bump.
            lines.extend(
                [
                    "ENV JULIA_VERSION=1.10.0",
                    "RUN curl -fsSL https://julialang-s3.julialang.org/bin/linux/x64/${JULIA_VERSION%.*}/julia-${JULIA_VERSION}-linux-x86_64.tar.gz \\",
                    "    | tar -xz -C /opt/ && ln -s /opt/julia-${JULIA_VERSION}/bin/julia /usr/local/bin/julia",
                ]
            )

        lines.extend(
            [
                "WORKDIR /app",
                "COPY . /app",
            ]
        )

        if (env_dir / "requirements.txt").exists():
            lines.append(
                "RUN pip install --no-cache-dir -r environment/requirements.txt"
            )

        if (env_dir / "renv.lock").exists():
            lines.append(
                "RUN R -e 'install.packages(\"renv\", repos=\"https://cloud.r-project.org\"); "
                "renv::restore(lockfile=\"environment/renv.lock\")'"
            )

        if (env_dir / "Project.toml").exists():
            lines.append(
                "RUN julia --project=environment -e 'using Pkg; Pkg.instantiate()'"
            )

        lines.append('CMD ["/bin/bash"]')
        df_path = env_dir / "Dockerfile"
        df_path.parent.mkdir(parents=True, exist_ok=True)
        df_path.write_text("\n".join(lines) + "\n")
        return {
            "status": "success",
            "dockerfile_path": str(df_path.relative_to(root)),
            "message": "Dockerfile generated.",
        }
    except Exception as e:
        logger.exception("env_docker_generate failed")
        return {"status": "error", "message": str(e)}
