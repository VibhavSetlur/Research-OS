"""AUDIT-063: tool_synthesize `auto_proceed` autopilot short-circuit.

Covers:
* ``auto_proceed=True`` + ``autonomy_level=autopilot`` writes every
  per-section file and the full assembly in ONE call.
* ``auto_proceed=True`` + non-autopilot autonomy returns a structured
  error (no files written, multi-turn cadence preserved).
* ``auto_proceed=False`` (default) preserves existing single-section /
  full-assembly behaviour (backwards-compat).
* The kwarg defaults to ``False`` — every existing call site keeps
  working without modification.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import yaml

from research_os.project_ops import scaffold_minimal_workspace
from research_os.tools.actions.synthesis.synthesize import (
    _AUTO_PROCEED_SECTION_ORDER,
    synthesize_workspace,
)


def _scaffold(tmp_path: Path) -> Path:
    scaffold_minimal_workspace(
        tmp_path, "AutoProceed Test", ide_flags=[], copy_agents=False,
    )
    # Seed methods.md so the methods builder produces a real body.
    (tmp_path / "workspace" / "methods.md").write_text(
        "# Methods\n\nWe used method X with parameters Y.\n"
    )
    return tmp_path


def _set_autonomy(root: Path, level: str) -> None:
    cfg_path = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}
    data.setdefault("interaction", {})["autonomy_level"] = level
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))


# ── Signature / default ───────────────────────────────────────────────


def test_auto_proceed_kwarg_default_is_false():
    """auto_proceed defaults to False — every existing caller is safe."""
    sig = inspect.signature(synthesize_workspace)
    assert "auto_proceed" in sig.parameters
    assert sig.parameters["auto_proceed"].default is False


def test_auto_proceed_kwarg_is_keyword_only():
    """auto_proceed must be keyword-only to avoid positional drift."""
    sig = inspect.signature(synthesize_workspace)
    assert sig.parameters["auto_proceed"].kind == inspect.Parameter.KEYWORD_ONLY


# ── auto_proceed=True + autopilot → all sections + assembly in one call ──


def test_auto_proceed_autopilot_writes_every_section(tmp_path):
    root = _scaffold(tmp_path)
    _set_autonomy(root, "autopilot")

    res = synthesize_workspace(root, auto_proceed=True)

    assert res.get("status") == "success", res
    assert res.get("auto_proceed") is True
    assert res.get("autonomy_level") == "autopilot"
    assert res.get("sections_processed") == list(_AUTO_PROCEED_SECTION_ORDER)

    # Every per-section file landed on disk.
    synthesis_dir = root / "synthesis"
    for sec in _AUTO_PROCEED_SECTION_ORDER:
        assert (synthesis_dir / f"{sec}.md").exists(), sec

    # The full assembly also landed — paper.md + references.bib.
    assert (synthesis_dir / "paper.md").exists()
    assert (synthesis_dir / "references.bib").exists()


def test_auto_proceed_autopilot_returns_per_section_paths(tmp_path):
    """Response includes per_section_paths so the caller can audit each file."""
    root = _scaffold(tmp_path)
    _set_autonomy(root, "autopilot")

    res = synthesize_workspace(root, auto_proceed=True)

    paths = res.get("per_section_paths") or []
    assert len(paths) == len(_AUTO_PROCEED_SECTION_ORDER)
    # Each returned path resolves to an actual file under synthesis/.
    for rel in paths:
        assert (root / rel).exists()


# ── auto_proceed=True + non-autopilot → structured error ─────────────


def test_auto_proceed_supervised_returns_error(tmp_path):
    root = _scaffold(tmp_path)
    _set_autonomy(root, "supervised")

    res = synthesize_workspace(root, auto_proceed=True)

    assert res.get("status") == "error"
    assert "autopilot" in res.get("error", "").lower()
    # Multi-turn cadence preserved: no per-section files written.
    for sec in _AUTO_PROCEED_SECTION_ORDER:
        assert not (root / "synthesis" / f"{sec}.md").exists(), sec
    assert not (root / "synthesis" / "paper.md").exists()


def test_auto_proceed_manual_returns_error(tmp_path):
    root = _scaffold(tmp_path)
    _set_autonomy(root, "manual")

    res = synthesize_workspace(root, auto_proceed=True)

    assert res.get("status") == "error"
    assert "autopilot" in res.get("error", "").lower()


def test_auto_proceed_coaching_returns_error(tmp_path):
    """`coaching` aliases to `supervised` for scheduling — same rejection."""
    root = _scaffold(tmp_path)
    _set_autonomy(root, "coaching")

    res = synthesize_workspace(root, auto_proceed=True)

    assert res.get("status") == "error"
    assert "autopilot" in res.get("error", "").lower()


def test_auto_proceed_default_autonomy_returns_error(tmp_path):
    """No interaction block → defaults to supervised → rejection."""
    root = _scaffold(tmp_path)
    # Strip the interaction block entirely.
    cfg_path = root / "inputs" / "researcher_config.yaml"
    data = yaml.safe_load(cfg_path.read_text()) or {}
    data.pop("interaction", None)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))

    res = synthesize_workspace(root, auto_proceed=True)

    assert res.get("status") == "error"


# ── Backwards-compat: auto_proceed=False (default) unchanged ─────────


def test_default_section_call_unchanged(tmp_path):
    """auto_proceed default + section="methods" → single section as before."""
    root = _scaffold(tmp_path)
    # Autopilot autonomy MUST NOT change anything when auto_proceed=False.
    _set_autonomy(root, "autopilot")

    res = synthesize_workspace(root, section="methods")

    assert res.get("status") == "success"
    assert res.get("section") == "methods"
    # Only the methods file was written — other sections stay absent.
    assert (root / "synthesis" / "methods.md").exists()
    for sec in ("results", "discussion", "introduction", "abstract"):
        assert not (root / "synthesis" / f"{sec}.md").exists()
    # No full paper assembly either.
    assert not (root / "synthesis" / "paper.md").exists()


def test_default_full_assembly_unchanged(tmp_path):
    """auto_proceed default + no section → full assembly as before."""
    root = _scaffold(tmp_path)
    _set_autonomy(root, "supervised")

    res = synthesize_workspace(root)

    assert res.get("status") == "success"
    # Full assembly emits paper.md + references.bib, no per-section files.
    assert (root / "synthesis" / "paper.md").exists()
    assert (root / "synthesis" / "references.bib").exists()
    assert "auto_proceed" not in res
    assert "autonomy_level" not in res


def test_explicit_auto_proceed_false_is_a_noop(tmp_path):
    """Passing auto_proceed=False explicitly matches the no-kwarg call."""
    root = _scaffold(tmp_path)
    _set_autonomy(root, "supervised")

    res = synthesize_workspace(root, auto_proceed=False, section="methods")

    assert res.get("status") == "success"
    assert res.get("section") == "methods"
