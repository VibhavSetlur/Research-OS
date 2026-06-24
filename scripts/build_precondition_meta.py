#!/usr/bin/env python3
"""Compile every protocol's ``requires.checks`` into one sidecar.

docs/v4/PRECONDITION_GATE.md. Protocols DECLARE their mechanically
checkable preconditions; this collects them into
``src/research_os/protocols/_precondition_meta.json`` which
server/preconditions.py reads at runtime. Mirrors build_gate_meta.py.

Usage:
    python scripts/build_precondition_meta.py            # write the sidecar
    python scripts/build_precondition_meta.py --check    # exit 1 if stale
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOLS_DIR = REPO_ROOT / "src" / "research_os" / "protocols"
META_PATH = PROTOCOLS_DIR / "_precondition_meta.json"
SCHEMA = 1

_VALID_KINDS = {"file_exists", "glob_min", "protocol_completed", "state_field"}
# Required field per kind (besides 'kind').
_REQUIRED_FIELD = {
    "file_exists": "path",
    "glob_min": "pattern",
    "protocol_completed": "protocol",
    "state_field": "field",
}


def _iter_core_protocol_files() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for yaml_file in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in yaml_file.parts or yaml_file.name.startswith("_"):
            continue
        rel = yaml_file.relative_to(PROTOCOLS_DIR).with_suffix("")
        out.append((str(rel).replace("\\", "/"), yaml_file))
    return out


def _validate_check(pid: str, check: dict, errors: list[str]) -> dict | None:
    if not isinstance(check, dict):
        errors.append(f"{pid}: a requires.check is not a mapping")
        return None
    kind = check.get("kind")
    if kind not in _VALID_KINDS:
        errors.append(f"{pid}: check kind {kind!r} not in {sorted(_VALID_KINDS)}")
        return None
    req = _REQUIRED_FIELD[kind]
    if not check.get(req):
        errors.append(f"{pid}: {kind} check missing required field {req!r}")
        return None
    out = {"kind": kind, req: check[req], "because": str(check.get("because") or "")}
    if kind == "file_exists" and check.get("non_empty"):
        out["non_empty"] = True
    if kind == "glob_min":
        try:
            out["min"] = int(check.get("min", 1))
        except (TypeError, ValueError):
            out["min"] = 1
    return out


def build_precondition_meta() -> dict:
    """Scan all protocols, collect + validate requires.checks. Raises on error.

    Also validates that every ``protocol_completed`` target names a real
    protocol (no dangling references), so a renamed protocol can't leave a
    silently-unsatisfiable precondition.
    """
    all_ids = {pid for pid, _ in _iter_core_protocol_files()}
    protocols: dict[str, list[dict]] = {}
    errors: list[str] = []

    for pid, path in _iter_core_protocol_files():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{pid}: YAML parse failed: {exc}")
            continue
        req = data.get("requires")
        if not req:
            continue
        if not isinstance(req, dict):
            errors.append(f"{pid}: `requires` must be a mapping")
            continue
        checks = req.get("checks") or []
        if not isinstance(checks, list):
            errors.append(f"{pid}: `requires.checks` must be a list")
            continue
        validated: list[dict] = []
        for c in checks:
            v = _validate_check(pid, c, errors)
            if v is None:
                continue
            if v["kind"] == "protocol_completed" and v["protocol"] not in all_ids:
                errors.append(
                    f"{pid}: protocol_completed references unknown protocol "
                    f"{v['protocol']!r}"
                )
                continue
            validated.append(v)
        if validated:
            protocols[pid] = validated

    if errors:
        raise SystemExit("precondition-meta build failed:\n  " + "\n  ".join(errors))

    payload = {"schema": SCHEMA, "protocols": dict(sorted(protocols.items()))}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["source_hash"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the on-disk sidecar is stale")
    args = ap.parse_args(argv)

    fresh = build_precondition_meta()
    n_checks = sum(len(v) for v in fresh["protocols"].values())
    if args.check:
        if not META_PATH.exists():
            print("MISSING _precondition_meta.json — run scripts/build_precondition_meta.py")
            return 1
        try:
            on_disk = json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"could not parse _precondition_meta.json: {exc}")
            return 1
        if on_disk.get("source_hash") != fresh.get("source_hash"):
            print("STALE _precondition_meta.json — recompile: "
                  "python scripts/build_precondition_meta.py")
            return 1
        print(f"_precondition_meta.json fresh: {n_checks} check(s) "
              f"across {len(fresh['protocols'])} protocol(s)")
        return 0

    META_PATH.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    print(f"wrote {META_PATH.relative_to(REPO_ROOT)}: {n_checks} check(s) "
          f"across {len(fresh['protocols'])} protocol(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
