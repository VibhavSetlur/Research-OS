#!/usr/bin/env python3
"""Compile every protocol's ``enforcement.gates`` block into one sidecar.

The HYBRID layer (docs/HYBRID_ARCHITECTURE.md): protocols DECLARE their
hard floor gates in machine-readable YAML; this build step collects every
declaration into ``src/research_os/protocols/_gate_meta.json``, which the
engine (server/gate_spec.py + autopilot_gate.py) reads at runtime instead
of parsing YAML on the dispatch hot path. Mirrors how _route_meta.json is
built from the router index.

Usage:
    python scripts/build_gate_meta.py            # write the sidecar
    python scripts/build_gate_meta.py --check     # exit 1 if stale (CI)

Importable: ``build_gate_meta()`` returns the dict (used by preflight to
re-derive and compare without writing).
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
GATE_META_PATH = PROTOCOLS_DIR / "_gate_meta.json"
SCHEMA = 1

_VALID_FLOORS = {"light", "normal", "strict"}


def _iter_core_protocol_files() -> list[tuple[str, Path]]:
    """(protocol_id, yaml_path) for every core protocol (sorted, stable)."""
    out: list[tuple[str, Path]] = []
    for yaml_file in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if "light" in yaml_file.parts:
            continue
        if yaml_file.name.startswith("_"):
            continue
        rel = yaml_file.relative_to(PROTOCOLS_DIR).with_suffix("")
        out.append((str(rel).replace("\\", "/"), yaml_file))
    return out


def _validate_gate(pid: str, gate: dict, errors: list[str]) -> dict | None:
    """Validate one declared gate. Append problems to ``errors``."""
    if not isinstance(gate, dict):
        errors.append(f"{pid}: a gate entry is not a mapping")
        return None
    key = gate.get("key")
    tool = gate.get("tool")
    floor = gate.get("floor")
    when = gate.get("when", {})
    if not isinstance(key, str) or not key:
        errors.append(f"{pid}: gate missing string `key`")
        return None
    if not isinstance(tool, str) or not tool:
        errors.append(f"{pid}: gate {key!r} missing string `tool`")
        return None
    if floor not in _VALID_FLOORS:
        errors.append(
            f"{pid}: gate {key!r} floor {floor!r} not in {sorted(_VALID_FLOORS)}"
        )
        return None
    if when is None:
        when = {}
    if not isinstance(when, dict):
        errors.append(f"{pid}: gate {key!r} `when` must be a mapping (or omitted)")
        return None
    return {
        "key": key,
        "tool": tool,
        "floor": floor,
        "when": when,
        "reason": str(gate.get("reason") or ""),
        "source_protocol": pid,
    }


def build_gate_meta() -> dict:
    """Scan all protocols, collect + validate enforcement.gates, return dict.

    Raises SystemExit(2) with a readable message on any validation error or
    duplicate gate key (a duplicate key across protocols is ambiguous: two
    protocols declaring different floors for the same key would silently
    fight).
    """
    gates: list[dict] = []
    built_from: list[str] = []
    errors: list[str] = []
    seen_keys: dict[str, str] = {}

    for pid, path in _iter_core_protocol_files():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - report which file broke
            errors.append(f"{pid}: YAML parse failed: {exc}")
            continue
        enforcement = data.get("enforcement")
        if not enforcement:
            continue
        if not isinstance(enforcement, dict):
            errors.append(f"{pid}: `enforcement` must be a mapping")
            continue
        decl = enforcement.get("gates") or []
        if not isinstance(decl, list):
            errors.append(f"{pid}: `enforcement.gates` must be a list")
            continue
        had_gate = False
        for g in decl:
            validated = _validate_gate(pid, g, errors)
            if validated is None:
                continue
            k = validated["key"]
            if k in seen_keys:
                errors.append(
                    f"duplicate gate key {k!r}: declared in {seen_keys[k]!r} "
                    f"and {pid!r} — gate keys must be globally unique"
                )
                continue
            seen_keys[k] = pid
            gates.append(validated)
            had_gate = True
        if had_gate:
            built_from.append(pid)

    if errors:
        msg = "gate-meta build failed:\n  " + "\n  ".join(errors)
        raise SystemExit(msg)

    # Deterministic order so the sidecar + source_hash are reproducible.
    gates.sort(key=lambda g: g["key"])
    payload = {
        "schema": SCHEMA,
        "built_from": sorted(built_from),
        "gates": gates,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["source_hash"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the on-disk sidecar is stale (do not write)",
    )
    args = ap.parse_args(argv)

    fresh = build_gate_meta()
    if args.check:
        if not GATE_META_PATH.exists():
            print("MISSING _gate_meta.json — run scripts/build_gate_meta.py")
            return 1
        try:
            on_disk = json.loads(GATE_META_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"could not parse _gate_meta.json: {exc}")
            return 1
        if on_disk.get("source_hash") != fresh.get("source_hash"):
            print(
                "STALE _gate_meta.json — recompile: "
                "python scripts/build_gate_meta.py"
            )
            return 1
        print(
            f"_gate_meta.json fresh: {len(fresh['gates'])} gate(s) "
            f"from {len(fresh['built_from'])} protocol(s)"
        )
        return 0

    GATE_META_PATH.write_text(
        json.dumps(fresh, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {GATE_META_PATH.relative_to(REPO_ROOT)}: "
        f"{len(fresh['gates'])} gate(s) from {len(fresh['built_from'])} protocol(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
