"""Guard: every `scripts/<name>` reference in docs/ must point at a real script.

Catches the SHARING.md class of bug where docs name a script that
was never committed (or got deleted in a refactor) and a new user
hits a 'No such file' wall on their first day.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Match `scripts/<name>` where <name> looks like a filename
# (has an extension or is a known executable). Skip `workspace/.../scripts/`
# style structural references which describe end-user project layout, not
# repo-local scripts.
_SCRIPT_REF = re.compile(r"(?<![\w/])scripts/([A-Za-z0-9_.\-]+)")

# Tokens that are clearly not script filenames even though they match
# the regex (e.g. directory references in prose).
_NOT_A_SCRIPT = {"__pycache__"}


def _iter_doc_files():
    for path in sorted(DOCS_DIR.rglob("*.md")):
        yield path


def _named_scripts_in(text: str) -> set[str]:
    found: set[str] = set()
    for match in _SCRIPT_REF.finditer(text):
        name = match.group(1)
        if name in _NOT_A_SCRIPT:
            continue
        # Must look like a real filename: has a `.` extension OR is a
        # bare token without trailing slash and not a generic word like
        # 'NN_'. We accept anything with a dot extension as a script.
        if "." not in name:
            continue
        found.add(name)
    return found


def test_every_scripts_reference_in_docs_exists():
    missing: list[tuple[str, str]] = []
    for doc in _iter_doc_files():
        text = doc.read_text(encoding="utf-8")
        # Strip auto-generated sections so we don't police generated content
        # that points at protocols/ paths etc.
        for script_name in _named_scripts_in(text):
            target = SCRIPTS_DIR / script_name
            if not target.exists():
                rel = doc.relative_to(REPO_ROOT).as_posix()
                missing.append((rel, script_name))

    assert not missing, (
        "Docs reference scripts/ files that do not exist:\n"
        + "\n".join(f"  {doc}: scripts/{name}" for doc, name in missing)
    )


def test_sharing_doc_has_no_dead_script_references():
    """Pin the specific bug W05 fixed — SHARING.md must not regress."""
    sharing = (DOCS_DIR / "SHARING.md").read_text(encoding="utf-8")
    assert "scripts/export_share_archive.py" not in sharing, (
        "SHARING.md still references the nonexistent "
        "scripts/export_share_archive.py — use sys_export_share_archive instead."
    )
    assert "scripts/init_github.sh" not in sharing, (
        "SHARING.md still references the nonexistent "
        "scripts/init_github.sh — use the inline `gh repo create` snippet instead."
    )
    assert "sys_export_share_archive" in sharing, (
        "SHARING.md must mention the sys_export_share_archive tool that "
        "replaced the dead script."
    )
