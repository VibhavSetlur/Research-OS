"""B5 — cited keys are resolved against the actual bibliography file.

A citation key with no matching entry in synthesis/biblio.yml (or
references.bib) is a dangling / hallucinated / typo'd reference that points
at nothing. ``audit_bibliography_resolution`` catches it at WARN severity,
without false-flagging markdown-inline projects (no external biblio file).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def _root() -> Path:
    return Path(tempfile.mkdtemp())


def test_dangling_cite_key_warns_only_on_undefined():
    pytest.importorskip("yaml")
    import yaml

    from research_os.tools.actions.audit.content_depth import (
        audit_bibliography_resolution,
    )
    root = _root()
    syn = root / "synthesis"
    syn.mkdir(parents=True)
    (syn / "biblio.yml").write_text(yaml.safe_dump({"real2024": {"title": "T"}}))
    # Paper cites a real key and a ghost key.
    text = "We build on @real2024 and also @ghost2024 in this work."
    out = audit_bibliography_resolution(text, root, "synthesis/paper.md")
    warns = " ".join(out["warnings"])
    assert "ghost2024" in warns, out
    assert "real2024" not in warns, out  # the defined key is not flagged
    assert not out["blockers"], out  # WARN only — never blocks


def test_typst_cite_form_resolved():
    pytest.importorskip("yaml")
    import yaml

    from research_os.tools.actions.audit.content_depth import (
        audit_bibliography_resolution,
    )
    root = _root()
    syn = root / "synthesis"
    syn.mkdir(parents=True)
    (syn / "biblio.yml").write_text(yaml.safe_dump({"real2024": {"title": "T"}}))
    text = "See #cite(<real2024>) and #cite(<ghost2024>)."
    out = audit_bibliography_resolution(text, root, "synthesis/paper.typ")
    assert any("ghost2024" in w for w in out["warnings"]), out


def test_no_biblio_file_no_spurious_warning():
    from research_os.tools.actions.audit.content_depth import (
        audit_bibliography_resolution,
    )
    root = _root()
    (root / "synthesis").mkdir(parents=True)
    # No biblio.yml / references.bib present → defer to inline reconciliation,
    # emit nothing (markdown-inline projects must not be regressed).
    text = "We cite @anything2024 here."
    out = audit_bibliography_resolution(text, root, "synthesis/paper.md")
    assert out["warnings"] == [] and out["blockers"] == [], out


def test_unused_entry_reported_as_info_warning():
    pytest.importorskip("yaml")
    import yaml

    from research_os.tools.actions.audit.content_depth import (
        audit_bibliography_resolution,
    )
    root = _root()
    syn = root / "synthesis"
    syn.mkdir(parents=True)
    (syn / "biblio.yml").write_text(
        yaml.safe_dump({"a2024": {}, "b2024": {}, "c2024": {}, "d2024": {}})
    )
    text = "Only @a2024 is cited."
    out = audit_bibliography_resolution(text, root, "synthesis/paper.md")
    assert any("never cited" in w for w in out["warnings"]), out
