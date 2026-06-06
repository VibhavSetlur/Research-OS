#!/usr/bin/env python3
"""Lint for historical version commentary in live doctrine surfaces.

Live doctrine (protocol bodies, MCP tool descriptions, code docstrings
and comments) should be timeless: it describes what the system does
now. Version history belongs in CHANGELOG.md, git log, and the
schema_version / last_reviewed fields — every load of a live doc
pays the token cost of any narrative wrapped around the rule.

This linter scans the live surfaces and flags inline references to
specific package versions, "as of vX.Y.Z" framing, narration of
"previously X, now Y" decisions, and references to specific stress
tests / bumps that the reader doesn't need to act on.

Usage:
    python scripts/lint_no_version_chatter.py             # warn-only
    python scripts/lint_no_version_chatter.py --strict    # exit 1 on any hit
    python scripts/lint_no_version_chatter.py --diff      # only fail on hits in files staged or modified in git
    python scripts/lint_no_version_chatter.py --quiet     # summary only
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = [
    REPO_ROOT / "src" / "research_os" / "protocols",
    REPO_ROOT / "src" / "research_os" / "tools" / "actions",
    REPO_ROOT / "src" / "research_os" / "server.py",
    REPO_ROOT / "src" / "research_os" / "project_ops.py",
    REPO_ROOT / "src" / "research_os" / "wizard.py",
]
WHITELIST_NAMES = {
    "CHANGELOG.md",
    "RELEASING.md",
}
WHITELIST_PREFIXES = (
    "CHANGELOG_",
)
ALLOWED_FILES = {
    REPO_ROOT / "src" / "research_os" / "__init__.py",
}


PATTERNS = [
    (re.compile(r"\bv\d+\.\d+(?:\.\d+)?(?!\.\d{2,})"), "version-ref"),
    (re.compile(r"\bas of v(?:ersion)?\b", re.IGNORECASE), "as-of-version"),
    (re.compile(r"\bpreviously this\b", re.IGNORECASE), "previously-this"),
    (re.compile(r"\bwas the bug\b", re.IGNORECASE), "was-the-bug"),
    (re.compile(r"^\s*now we\b", re.IGNORECASE | re.MULTILINE), "now-we-start"),
    (re.compile(r"promoted from WARN to BLOCK"), "warn-to-block"),
    (re.compile(r"\bdeferred to v\d", re.IGNORECASE), "deferred-to-v"),
    (re.compile(r"\bthe v\d+\.\d+(?:\.\d+)? stress test\b", re.IGNORECASE), "stress-test-ref"),
    (re.compile(r"\bbump(?:ed)? to BLOCK in v\d"), "bump-block-in-v"),
    (re.compile(r"\bcarried (?:over )?from v\d"), "carried-from-v"),
]

# False-positive exemptions: substrings that are NOT version chatter
# even though the regex matched them.
LINE_EXEMPT_SUBSTRINGS = (
    "BAAI/bge-small-en-v1.5",
    "_v1.py",  # user-facing script naming convention
    "scripts/NN_<slug>_v",
    "VERSION the dashboard (semver:",  # user example, not internal commentary
    "demo, v1.1 fixed filters",
    # _REMOVED_TOOLS redirect messages and the docstrings naming the
    # removal phase. These are user-facing migration data — the version
    # context is the load-bearing detail callers need to find the new path.
    "renamed to",
    "removed in v",
    "(phase-14a)",
    "phase-14a (v",
    "(phase-14b)",
    "phase-14b (v",
    "pre-dating v1.6.1",
    "across v2.0.0",
)


def _is_whitelisted_file(path: Path) -> bool:
    name = path.name
    if name in WHITELIST_NAMES:
        return True
    if any(name.startswith(p) for p in WHITELIST_PREFIXES):
        return True
    if path.resolve() in {p.resolve() for p in ALLOWED_FILES}:
        return True
    if "_embeddings" in name or name == "_router_index.yaml":
        return True
    return False


def _line_exempt(line: str) -> bool:
    return any(sub in line for sub in LINE_EXEMPT_SUBSTRINGS)


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            if not _is_whitelisted_file(root):
                out.append(root)
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix not in {".yaml", ".py"}:
                continue
            if "__pycache__" in f.parts:
                continue
            if _is_whitelisted_file(f):
                continue
            out.append(f)
    return out


def scan_text(text: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    for pat, label in PATTERNS:
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            line = lines[line_no - 1] if line_no <= len(lines) else ""
            if _line_exempt(line):
                continue
            snippet = line.strip()
            if len(snippet) > 140:
                snippet = snippet[:137] + "..."
            hits.append((line_no, label, snippet))
    return hits


def _changed_files() -> set[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, check=False, cwd=REPO_ROOT,
        )
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, check=False, cwd=REPO_ROOT,
        )
        unt = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=False, cwd=REPO_ROOT,
        )
        names = set()
        for r in (out, staged, unt):
            for line in r.stdout.splitlines():
                if line.strip():
                    names.add((REPO_ROOT / line.strip()).resolve())
        return names
    except Exception:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    files = _iter_files()
    total_hits = 0
    hit_files: list[tuple[Path, list[tuple[int, str, str]]]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = scan_text(text)
        if hits:
            hit_files.append((f, hits))
            total_hits += len(hits)

    if not args.quiet:
        for f, hits in hit_files:
            rel = f.relative_to(REPO_ROOT)
            print(f"\n{rel} — {len(hits)} hit(s):")
            for line_no, label, snippet in hits[:20]:
                print(f"  L{line_no:4d}  [{label}]  {snippet}")
            if len(hits) > 20:
                print(f"  ... and {len(hits) - 20} more")

    print(f"\nTotal: {total_hits} hit(s) across {len(hit_files)} file(s)")

    if args.diff:
        changed = _changed_files()
        bad = [(f, h) for f, h in hit_files if f.resolve() in changed]
        if bad:
            print(f"\nFAIL (--diff): {sum(len(h) for _, h in bad)} hit(s) in {len(bad)} modified file(s)")
            return 1
        return 0

    if args.strict and total_hits:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
