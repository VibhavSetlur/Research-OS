"""Compare two runs — the experiment-diff (Phase 1.12).

A researcher's core loop is *comparison*: run the experiment, change one
thing, run it again, ask "what changed?". The run journal records every
run's command, provenance (git commit, environment, inputs) and artifacts
(path + sha256) — so the daemon can answer that question precisely instead
of the researcher eyeballing two terminals.

``compare_runs`` diffs two recorded manifests across three planes:

  command   what was executed (cmd, cwd, scheduler, env-overrides)
  context   git commit + branch + dirty, conda env + python, input hashes
  outputs   artifacts by path + sha256 (reusing the reproduce comparator)

It is pure and stdlib-only — it reads manifests already loaded by the
caller, never touches the filesystem, and never raises on well-formed
input. The daemon/CLI loads the two manifests and renders the report.
"""
from __future__ import annotations

from typing import Any

from .reproduce import compare_artifacts


def _spec_of(manifest: dict) -> dict:
    return manifest.get("spec") or {}


def _prov_of(manifest: dict) -> dict:
    return manifest.get("provenance") or {}


def _cmd_str(spec: dict) -> str:
    cmd = spec.get("cmd")
    if isinstance(cmd, list):
        return " ".join(str(c) for c in cmd)
    return str(cmd) if cmd is not None else ""


def compare_runs(manifest_a: dict, manifest_b: dict) -> dict[str, Any]:
    """Diff two recorded run manifests. ``a`` is the baseline, ``b`` the new.

    Returns a structured report:

        {
          "same": bool,                 # identical command + context + outputs
          "command": {changed: bool, fields: {field: {a, b}}},
          "context": {changed: bool, fields: {field: {a, b}}},
          "outputs": <compare_artifacts report a->b>,
          "ids": {a, b},
          "status": {a, b},
        }

    Pure: no I/O, never raises on well-formed input.
    """
    spec_a, spec_b = _spec_of(manifest_a), _spec_of(manifest_b)
    prov_a, prov_b = _prov_of(manifest_a), _prov_of(manifest_b)

    # ── command plane ────────────────────────────────────────────────
    cmd_fields: dict[str, dict] = {}

    def _cmp(name: str, va: Any, vb: Any, into: dict) -> None:
        if va != vb:
            into[name] = {"a": va, "b": vb}

    _cmp("cmd", _cmd_str(spec_a), _cmd_str(spec_b), cmd_fields)
    _cmp("cwd", spec_a.get("cwd"), spec_b.get("cwd"), cmd_fields)
    _cmp("scheduler", spec_a.get("scheduler"), spec_b.get("scheduler"), cmd_fields)
    _cmp("shell", spec_a.get("shell"), spec_b.get("shell"), cmd_fields)
    _cmp(
        "env_overrides",
        spec_a.get("env_overrides") or [],
        spec_b.get("env_overrides") or [],
        cmd_fields,
    )

    # ── context plane ────────────────────────────────────────────────
    ctx_fields: dict[str, dict] = {}
    git_a = prov_a.get("git") or {}
    git_b = prov_b.get("git") or {}
    _cmp("git_commit", git_a.get("commit"), git_b.get("commit"), ctx_fields)
    _cmp("git_branch", git_a.get("branch"), git_b.get("branch"), ctx_fields)
    _cmp("git_dirty", git_a.get("dirty"), git_b.get("dirty"), ctx_fields)

    env_a = prov_a.get("env") or {}
    env_b = prov_b.get("env") or {}
    _cmp("conda_env", env_a.get("conda_env"), env_b.get("conda_env"), ctx_fields)
    _cmp("python_version", env_a.get("python_version"),
         env_b.get("python_version"), ctx_fields)
    _cmp("platform", env_a.get("platform"), env_b.get("platform"), ctx_fields)

    # Inputs: compare by name -> hash if present.
    in_a = _index_inputs(prov_a.get("inputs"))
    in_b = _index_inputs(prov_b.get("inputs"))
    input_changes: dict[str, dict] = {}
    for name in sorted(set(in_a) | set(in_b)):
        ha, hb = in_a.get(name), in_b.get(name)
        if ha != hb:
            input_changes[name] = {"a": ha, "b": hb}
    if input_changes:
        ctx_fields["inputs"] = input_changes

    # Packages: compare by name -> version if present.
    pkg_changes = _diff_packages(prov_a.get("packages"), prov_b.get("packages"))
    if pkg_changes:
        ctx_fields["packages"] = pkg_changes

    # ── outputs plane ────────────────────────────────────────────────
    outputs = compare_artifacts(
        manifest_a.get("artifacts"), manifest_b.get("artifacts")
    )

    command_changed = bool(cmd_fields)
    context_changed = bool(ctx_fields)
    outputs_changed = bool(
        outputs["changed"] or outputs["missing"] or outputs["added"]
    )

    return {
        "same": not (command_changed or context_changed or outputs_changed),
        "command": {"changed": command_changed, "fields": cmd_fields},
        "context": {"changed": context_changed, "fields": ctx_fields},
        "outputs": outputs,
        "ids": {"a": manifest_a.get("id"), "b": manifest_b.get("id")},
        "status": {"a": manifest_a.get("status"), "b": manifest_b.get("status")},
    }


def _index_inputs(inputs: Any) -> dict[str, Any]:
    """Index input records (list of {path/name, sha256}) by name -> hash."""
    out: dict[str, Any] = {}
    if isinstance(inputs, dict):
        # Already a name->hash map.
        return {str(k): v for k, v in inputs.items()}
    for item in inputs or []:
        if isinstance(item, dict):
            key = item.get("path") or item.get("name")
            if key:
                out[str(key)] = item.get("sha256") or item.get("hash")
    return out


def _diff_packages(pa: Any, pb: Any) -> dict[str, dict]:
    """Diff package version maps. Accepts dict name->ver or list of dicts."""
    def _norm(p: Any) -> dict[str, Any]:
        if isinstance(p, dict):
            return {str(k): v for k, v in p.items()}
        out: dict[str, Any] = {}
        for item in p or []:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    out[str(name)] = item.get("version")
        return out

    na, nb = _norm(pa), _norm(pb)
    changes: dict[str, dict] = {}
    for name in sorted(set(na) | set(nb)):
        if na.get(name) != nb.get(name):
            changes[name] = {"a": na.get(name), "b": nb.get(name)}
    return changes
