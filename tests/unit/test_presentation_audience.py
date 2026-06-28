"""Two-path presentation STRUCTURE (technical vs public) — structure, not design."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.synthesis.scaffold import synthesis_scaffold


def _proj() -> Path:
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis")
    return root


def test_technical_and_public_produce_distinct_structures():
    root = _proj()
    rt = synthesis_scaffold(root, kind="slides", audience="technical", confirmed=True)
    rp = synthesis_scaffold(root, kind="slides", audience="public", confirmed=True)
    assert rt["status"] == "success" and rt["audience"] == "technical"
    assert rp["status"] == "success" and rp["audience"] == "public"
    tech = (root / "synthesis" / "presentation_technical.md").read_text()
    pub = (root / "synthesis" / "presentation_public.md").read_text()
    # technical leads with design/methods; public leads with hook/big-theme
    assert "Methods that matter" in tech and "Design / approach" in tech
    assert "The hook" in pub and "The big idea" in pub
    assert "Reproducibility" in tech or "reproducibility" in tech
    assert tech != pub


def test_presentation_structure_is_markdown_not_typst():
    # Structure, not design: the output is a .md outline, not a rendered .typ.
    root = _proj()
    r = synthesis_scaffold(root, kind="slides", audience="public", confirmed=True)
    assert r["path"].endswith(".md")
    body = (root / "synthesis" / "presentation_public.md").read_text()
    assert "#import" not in body  # no Touying/typst machinery
    assert "touying" not in body.lower()


def test_unknown_audience_errors():
    root = _proj()
    r = synthesis_scaffold(root, kind="slides", audience="nonsense", confirmed=True)
    assert r["status"] == "error"
    assert "technical" in r["message"] and "public" in r["message"]


def test_audience_ignored_for_non_slides():
    # audience only applies to slides; a paper still scaffolds normally.
    root = _proj()
    r = synthesis_scaffold(root, kind="paper", confirmed=True)
    assert r["status"] in ("success", "exists")
    assert r.get("audience") is None
