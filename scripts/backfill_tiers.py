"""Backfill ``tier:`` annotations into every protocol YAML.

Phase 8 of the v2.0.0 release. The tier taxonomy lives at
``src/research_os/protocols/_tiers.py``; this script reads the router
index, pairs each protocol YAML with its ``(intent_class, sub_intent,
category)`` metadata, infers a tier via ``infer_tier``, and inserts a
top-level ``tier:`` field if one isn't already present.

Idempotent — running twice is a no-op. The script reports counts:
annotated, already-present, parse-failed.

Usage:
    python scripts/backfill_tiers.py             # write changes
    python scripts/backfill_tiers.py --dry-run   # report only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Allow `import research_os.protocols._tiers` from inside src/.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from research_os.protocols._tiers import (  # noqa: E402
    TIER_INDEX,
    infer_tier,
)

PROTOCOLS_DIR = SRC / "research_os" / "protocols"
INDEX_PATH = PROTOCOLS_DIR / "_router_index.yaml"


def _load_index_metadata() -> dict[str, dict]:
    """Map protocol_id (e.g. ``writing/writing_methods``) → router-index dict."""
    with open(INDEX_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("protocols", {}) or {}


def _protocol_files() -> list[Path]:
    out: list[Path] = []
    for p in sorted(PROTOCOLS_DIR.rglob("*.yaml")):
        if p.name.startswith("_"):
            continue
        out.append(p)
    return out


def _relpath_id(path: Path) -> str:
    rel = path.relative_to(PROTOCOLS_DIR)
    return str(rel.with_suffix("")).replace("\\", "/")


def _insert_tier_field(text: str, tier: str) -> str:
    """Insert ``tier: <tier>`` right after the ``id:`` line (or top of file).

    Preserves comments, blank lines, and key ordering. Single-quoted to
    mirror the YAML style the rest of the file uses for short string
    values (matches ``version: '2.0.0'``).
    """
    line = f"tier: '{tier}'"
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    # Look for the first line that begins with `id:` at column 0. Most
    # protocol YAMLs start with `id:` as the very first non-comment line;
    # for the handful that don't (e.g. redirect stubs starting with
    # `redirect_to:`), insert after the first non-comment line instead.
    id_pat = re.compile(r"^id:\s")
    first_meaningful = None
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        first_meaningful = i
        break
    for i, ln in enumerate(lines):
        out.append(ln)
        if inserted:
            continue
        if id_pat.match(ln):
            # Insert tier on the line AFTER id:.
            out.append(line + "\n")
            inserted = True
            continue
        if first_meaningful is not None and i == first_meaningful and not id_pat.match(ln):
            # No `id:` line — insert before this first meaningful line.
            out.insert(-1, line + "\n")
            inserted = True
    if not inserted:
        # Totally empty or comment-only file. Append.
        out.append(line + "\n")
    return "".join(out)


def backfill(*, dry_run: bool = False) -> dict[str, int]:
    metadata = _load_index_metadata()
    counts = {
        "total": 0,
        "annotated": 0,
        "already_present": 0,
        "parse_failed": 0,
        "missing_metadata": 0,
    }
    inferred_by_tier: dict[str, int] = {}
    for f in _protocol_files():
        counts["total"] += 1
        pid = _relpath_id(f)
        category = pid.split("/")[0] if "/" in pid else None
        try:
            text = f.read_text()
            data = yaml.safe_load(text) or {}
        except Exception as exc:
            counts["parse_failed"] += 1
            print(f"  PARSE FAIL  {pid}: {exc}", file=sys.stderr)
            continue
        existing = data.get("tier")
        if isinstance(existing, str) and existing in TIER_INDEX:
            counts["already_present"] += 1
            inferred_by_tier[existing] = inferred_by_tier.get(existing, 0) + 1
            continue
        meta = metadata.get(pid, {}) or {}
        if not meta:
            counts["missing_metadata"] += 1
        tier = infer_tier(
            intent_class=meta.get("intent_class"),
            sub_intent=meta.get("sub_intent"),
            category=category,
            protocol_id=pid,
        )
        new_text = _insert_tier_field(text, tier)
        # Verify the rewritten text still parses + carries the tier.
        try:
            parsed = yaml.safe_load(new_text) or {}
            assert parsed.get("tier") == tier
        except Exception as exc:
            counts["parse_failed"] += 1
            print(
                f"  REWRITE FAIL  {pid}: {exc}\n--- new text ---\n{new_text[:500]}",
                file=sys.stderr,
            )
            continue
        if not dry_run:
            f.write_text(new_text)
        counts["annotated"] += 1
        inferred_by_tier[tier] = inferred_by_tier.get(tier, 0) + 1
        print(f"  {tier:10} {pid}")
    # Tail report.
    print(
        f"\nTotal protocols : {counts['total']}"
        f"\n  Annotated     : {counts['annotated']}"
        f"\n  Already present: {counts['already_present']}"
        f"\n  Missing metadata (fell back on category): {counts['missing_metadata']}"
        f"\n  Parse failed  : {counts['parse_failed']}"
        f"\nBy tier        :",
    )
    for t, n in sorted(
        inferred_by_tier.items(), key=lambda kv: TIER_INDEX.get(kv[0], 99)
    ):
        print(f"  {t:10} {n}")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Report only; no writes.")
    args = ap.parse_args()
    counts = backfill(dry_run=args.dry_run)
    return 1 if counts["parse_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
