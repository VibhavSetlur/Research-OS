"""v1.11.1 known issue: tool_synthesize must consult the active pack's
preferred paper-section schema instead of always forcing IMRAD.

Spec recap
----------
1. ``PackRegistration`` carries an optional ``paper_sections`` tuple.
2. The plugin loader stashes the declaration in a module-level map
   and exposes it via ``research_os.plugins.pack_paper_sections``.
3. ``synthesize_workspace`` resolves the active pack from
   ``inputs/researcher_config.yaml`` (``pack:`` / ``domain:`` /
   ``packs:``) and reads the declared schema; when absent, falls back
   to the IMRAD default.
4. The bundled ``theory_math`` pack declares
   ``(introduction, preliminaries, main_theorems, proofs, discussion)``
   so a formal-math project's ``synthesis/paper.md`` is no longer
   forced into IMRAD.

These tests pin all four contracts without mocking the database or
calling LLM APIs — they exercise real PackRegistration validation, the
loader, the synthesis pipeline, and the on-disk paper.md.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.synthesis.synthesize import (
    _DEFAULT_PAPER_SECTIONS,
    _active_pack_name,
    _resolve_paper_sections,
    synthesize_workspace,
)


# ── helpers ──────────────────────────────────────────────────────────


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(
        tmp_path, "PackSections Test", ide_flags=[], copy_agents=False,
    )
    # Seed methods.md so the IMRAD-default path produces a non-stub
    # methods section — keeps assertions about IMRAD ordering meaningful.
    (tmp_path / "workspace" / "methods.md").write_text(
        "# Methods\n\nWe used method X with parameters Y.\n"
    )
    return tmp_path


def _set_pack(root: Path, pack: str) -> None:
    cfg_path = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}
    data["pack"] = pack
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))


# ── PackRegistration carries paper_sections ──────────────────────────


def test_pack_registration_accepts_paper_sections(tmp_path):
    """The dataclass admits a paper_sections tuple — default is ()."""
    from research_os.plugins.pack_api import PackRegistration

    pdir = tmp_path / "protocols"
    pdir.mkdir()

    # Empty default — every existing pack stays backwards-compatible.
    reg_default = PackRegistration(
        name="mypack", version="0.0.1", protocols_dir=pdir,
    )
    assert reg_default.paper_sections == ()

    # Custom declaration round-trips.
    declared = ("introduction", "preliminaries", "main_theorems", "discussion")
    reg_custom = PackRegistration(
        name="mypack",
        version="0.0.1",
        protocols_dir=pdir,
        paper_sections=declared,
    )
    assert reg_custom.paper_sections == declared


def test_pack_paper_sections_lookup_returns_empty_for_unknown():
    """Unknown packs return an empty tuple, not None — keeps callers
    using tuple semantics without isinstance checks."""
    from research_os.plugins import pack_paper_sections

    assert pack_paper_sections("definitely_not_a_real_pack_xyz") == ()
    assert pack_paper_sections("") == ()


# ── theory_math pack declares non-IMRAD schema ───────────────────────


def test_theory_math_register_declares_non_imrad_sections():
    """The bundled theory_math pack must declare its proof-shaped
    schema so a fresh discover_packs() call wires it up."""
    from research_os_theory_math import register

    reg = register()
    assert reg.paper_sections, "theory_math must declare paper_sections"
    # The declared schema is explicitly NOT IMRAD: no 'methods', no
    # 'results'. Proof papers don't have those.
    assert "methods" not in reg.paper_sections
    assert "results" not in reg.paper_sections
    # Order matters — preliminaries must come before main_theorems must
    # come before proofs.
    sections = list(reg.paper_sections)
    assert sections.index("introduction") < sections.index("preliminaries")
    assert sections.index("preliminaries") < sections.index("main_theorems")
    assert sections.index("main_theorems") < sections.index("proofs")


# ── resolver: pack-aware schema vs IMRAD fallback ────────────────────


def test_resolve_paper_sections_falls_back_to_imrad(tmp_path):
    """No pack declared → IMRAD default + source_pack=None."""
    root = _scaffold(tmp_path)
    # Strip any pack hint the scaffold may have written.
    cfg_path = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}
    data.pop("pack", None)
    data.pop("domain", None)
    data.pop("packs", None)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))

    sections, source = _resolve_paper_sections(root)
    assert sections == _DEFAULT_PAPER_SECTIONS
    assert source is None


def test_active_pack_name_reads_config(tmp_path):
    root = _scaffold(tmp_path)
    _set_pack(root, "theory_math")
    assert _active_pack_name(root) == "theory_math"


def test_resolve_paper_sections_uses_theory_math_schema(tmp_path):
    """When pack=theory_math is in the config AND theory_math has been
    discovered by the plugin loader, the resolver returns the pack's
    declared schema."""
    # Ensure the bundled pack is registered (server startup normally
    # does this, but tests run in isolation — discover explicitly).
    from research_os.plugins import discover_packs

    discover_packs(bundled=[("theory_math", "research_os_theory_math:register")])

    root = _scaffold(tmp_path)
    _set_pack(root, "theory_math")

    sections, source = _resolve_paper_sections(root)
    assert source == "theory_math"
    # Must NOT be the IMRAD default.
    assert sections != _DEFAULT_PAPER_SECTIONS
    assert "main_theorems" in sections
    assert "proofs" in sections


# ── synthesize_workspace end-to-end with theory_math ─────────────────


def test_synthesize_full_assembly_uses_pack_section_order(tmp_path):
    """paper.md headings come out in the pack-declared order, NOT IMRAD."""
    from research_os.plugins import discover_packs

    discover_packs(bundled=[("theory_math", "research_os_theory_math:register")])

    root = _scaffold(tmp_path)
    _set_pack(root, "theory_math")

    # Seed a couple of theory-flavoured workspace files so the generic
    # builder has real content to emit (otherwise it writes the *No
    # <section> recorded* stub — which is also fine, but exercising the
    # happy path catches regressions in the heading slug logic).
    (root / "workspace" / "preliminaries.md").write_text(
        "We assume a measure space $(X, \\Sigma, \\mu)$.\n"
    )
    (root / "workspace" / "main_theorems.md").write_text(
        "**Theorem 1.** Every Cauchy sequence in $X$ converges.\n"
    )
    (root / "workspace" / "proofs.md").write_text(
        "*Proof of Theorem 1.* Standard $\\epsilon$/3 argument.\n"
    )

    res = synthesize_workspace(root)
    assert res.get("status") == "success", res
    assert res.get("pack_section_schema_source") == "theory_math"

    paper_md = (root / "synthesis" / "paper.md").read_text()

    # The pack-declared sections must appear, in the pack-declared
    # order, and IMRAD-only sections (Methods / Results) must NOT.
    idx_intro = paper_md.find("## Introduction")
    idx_prelim = paper_md.find("## Preliminaries")
    idx_thm = paper_md.find("## Main Theorems")
    idx_proofs = paper_md.find("## Proofs")
    idx_discussion = paper_md.find("## Discussion")

    assert idx_intro != -1, "Introduction heading missing"
    assert idx_prelim != -1, "Preliminaries heading missing"
    assert idx_thm != -1, "Main Theorems heading missing"
    assert idx_proofs != -1, "Proofs heading missing"
    assert idx_discussion != -1, "Discussion heading missing"

    assert idx_intro < idx_prelim < idx_thm < idx_proofs < idx_discussion

    # IMRAD-only sections must NOT be in the body.
    assert "## Methods" not in paper_md
    assert "## Results" not in paper_md

    # References are appended even when not in the declared schema so
    # the bibliography is never silently dropped.
    assert "## References" in paper_md


def test_synthesize_full_assembly_falls_back_to_imrad_without_pack(tmp_path):
    """No pack hint AND no pack-declared schema → IMRAD ordering."""
    root = _scaffold(tmp_path)
    # Make sure no pack is configured.
    cfg_path = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}
    data.pop("pack", None)
    data.pop("domain", None)
    data.pop("packs", None)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))

    res = synthesize_workspace(root)
    assert res.get("status") == "success", res
    assert res.get("pack_section_schema_source") is None

    paper_md = (root / "synthesis" / "paper.md").read_text()
    # Classic IMRAD headings must all appear.
    for heading in ("## Abstract", "## Introduction", "## Methods",
                    "## Results", "## Discussion", "## References"):
        assert heading in paper_md, heading


def test_synthesize_single_section_accepts_pack_declared_id(tmp_path):
    """Calling synthesize_workspace(section='main_theorems') works for a
    theory_math project even though no hardcoded builder exists."""
    from research_os.plugins import discover_packs

    discover_packs(bundled=[("theory_math", "research_os_theory_math:register")])

    root = _scaffold(tmp_path)
    _set_pack(root, "theory_math")
    (root / "workspace" / "main_theorems.md").write_text(
        "**Theorem.** $P = NP$ is undecidable in ZFC.\n"
    )

    res = synthesize_workspace(root, section="main_theorems")
    assert res.get("status") == "success", res
    assert res.get("section") == "main_theorems"

    body = (root / "synthesis" / "main_theorems.md").read_text()
    assert "## Main Theorems" in body
    assert "Theorem" in body


def test_synthesize_single_section_rejects_unknown_id(tmp_path):
    """Section IDs that are neither hardcoded nor pack-declared are
    rejected with a structured error listing what IS allowed."""
    root = _scaffold(tmp_path)
    res = synthesize_workspace(root, section="totally_made_up_section")
    assert res.get("status") == "error"
    assert "Unknown section" in res.get("error", "")
