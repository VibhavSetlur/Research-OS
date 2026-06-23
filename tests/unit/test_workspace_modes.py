"""Workspace-mode foundation: config getter, scaffold profiles, state field.

A single ``workspace.mode`` axis drives the scaffold (and, in later
slices, routing + audits). Three modes:

* ``analysis``    — the classic linear numbered-step workspace (default).
* ``tool_build``  — Research OS governs a software build from above (spec
                    + decisions + eval + milestones); the tool lives in an
                    inner git repo.
* ``exploration`` — scratch-first quick probes with light gates.

The HARD invariant these tests protect: when the mode is unset / old /
``analysis``, the scaffold surface is BYTE-IDENTICAL to every prior
release (same TOP_LEVEL_DIRS / EAGER_DIRS / LAZY_DIRS contract).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import (
    EAGER_DIRS,
    LAZY_DIRS,
    SCAFFOLD_PROFILES,
    TOP_LEVEL_DIRS,
    scaffold_minimal_workspace,
)
from research_os.tools.actions.state.config import (
    get_inner_repo_dir,
    get_workspace_mode,
    init_config,
)


# ---------------------------------------------------------------------------
# Config getter
# ---------------------------------------------------------------------------


def test_get_workspace_mode_defaults_analysis_when_config_absent():
    """No config file → analysis (the back-compat default)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        assert get_workspace_mode(root) == "analysis"


def test_get_workspace_mode_defaults_analysis_for_old_config():
    """A config with no ``workspace:`` block reads as analysis."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = root / "inputs" / "researcher_config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("project_name: legacy\nmodel_profile: medium\n")
        assert get_workspace_mode(root) == "analysis"


def test_get_workspace_mode_defaults_analysis_for_malformed_config():
    """Unparseable / odd config falls back to analysis, never raises."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = root / "inputs" / "researcher_config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("workspace: 'not-a-dict'\n")
        assert get_workspace_mode(root) == "analysis"


def test_get_workspace_mode_reads_written_mode():
    """A written tool_build / exploration mode round-trips through the getter."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init_config(root, overrides={
            "project_name": "T",
            "workspace": {"mode": "tool_build", "inner_repo": "engine"},
        })
        assert get_workspace_mode(root) == "tool_build"
        assert get_inner_repo_dir(root) == "engine"


def test_get_workspace_mode_unknown_value_is_analysis():
    """An off-enum mode string degrades to analysis."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = root / "inputs" / "researcher_config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("workspace:\n  mode: nonsense\n")
        assert get_workspace_mode(root) == "analysis"


def test_get_inner_repo_dir_defaults_project():
    """Blank / absent inner_repo → 'project'."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        assert get_inner_repo_dir(root) == "project"
        init_config(root, overrides={
            "project_name": "T", "workspace": {"mode": "tool_build"},
        })
        assert get_inner_repo_dir(root) == "project"


# ---------------------------------------------------------------------------
# Scaffold profiles — analysis is byte-identical to today
# ---------------------------------------------------------------------------


def test_analysis_profile_reproduces_legacy_constants():
    """The analysis profile IS the legacy contract — exact set equality."""
    prof = SCAFFOLD_PROFILES["analysis"]
    assert prof["top_level_dirs"] == TOP_LEVEL_DIRS
    assert prof["eager_dirs"] == EAGER_DIRS
    assert prof["lazy_dirs"] == LAZY_DIRS


def _top_level_dirs_on_disk(root: Path) -> set[str]:
    """The directory contract the scaffold actually built, as a flat set
    matching the relative paths in TOP_LEVEL_DIRS (incl. nested inputs/*)."""
    found: set[str] = set()
    for rel in TOP_LEVEL_DIRS:
        if (root / rel).is_dir():
            found.add(rel)
    return found


def test_scaffold_unset_mode_creates_exactly_legacy_top_level_dirs():
    """Mode unset == analysis: every eager TOP_LEVEL_DIR exists; the lone
    lazy dir (synthesis/) does not — byte-identical to the classic surface."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(root, "Legacy", ide_flags=[], copy_agents=False)
        # Every eager dir present.
        for rel in EAGER_DIRS:
            assert (root / rel).is_dir(), f"missing eager dir {rel}"
        # Lazy dirs absent on a cold init.
        for rel in LAZY_DIRS:
            assert not (root / rel).exists(), f"lazy dir {rel} should not exist"
        # No governance surface from other modes leaked in.
        for leaked in ("spec", "decisions", "eval", "governance.md",
                       "milestones.md"):
            assert not (root / leaked).exists(), f"analysis leaked {leaked}"


def test_scaffold_explicit_analysis_matches_unset():
    """Passing mode='analysis' explicitly builds the same dir set as unset."""
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        a, b = Path(d1), Path(d2)
        scaffold_minimal_workspace(a, "A", ide_flags=[], copy_agents=False)
        scaffold_minimal_workspace(b, "B", ide_flags=[], copy_agents=False,
                                   mode="analysis")
        assert _top_level_dirs_on_disk(a) == _top_level_dirs_on_disk(b)


# ---------------------------------------------------------------------------
# tool_build profile
# ---------------------------------------------------------------------------


def test_tool_build_scaffold_creates_governance_surface():
    """tool_build seeds spec/, decisions/, eval/, milestones.md, governance.md,
    CHANGELOG.md, and an inner repo dir with its own .git — and does NOT
    pre-create analysis numbered-step plumbing."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Builder", ide_flags=[], copy_agents=False,
            mode="tool_build",
            config_overrides={"project_name": "Builder",
                              "workspace": {"mode": "tool_build"}},
        )
        # Governance layer.
        for rel in ("spec", "decisions", "eval"):
            assert (root / rel).is_dir(), f"missing governance dir {rel}"
        for f in ("spec/requirements.md", "spec/design.md",
                  "decisions/README.md", "eval/README.md",
                  "milestones.md", "governance.md", "CHANGELOG.md"):
            assert (root / f).is_file(), f"missing governance file {f}"

        # Inner repo with its own .git.
        inner = root / "project"   # default inner_repo name
        assert inner.is_dir(), "inner repo dir not created"
        assert (inner / ".git").exists(), "inner repo not git-init'd"
        assert (inner / "README.md").is_file()

        # Mode-agnostic safety surface preserved.
        for rel in ("inputs/raw_data", "inputs/literature", "inputs/context",
                    ".os_state", "environment", "workspace/scratch", "docs"):
            assert (root / rel).is_dir(), f"missing safety dir {rel}"

        # Config + state both record the mode.
        assert get_workspace_mode(root) == "tool_build"
        from research_os.project_ops import load_state
        assert load_state(root).get("workspace_mode") == "tool_build"


def test_tool_build_does_not_create_analysis_step_dirs():
    """tool_build must NOT seed the classic synthesis/ output dir or any
    numbered analysis step folder."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Builder", ide_flags=[], copy_agents=False,
            mode="tool_build",
        )
        assert not (root / "synthesis").exists()
        # No NN_* step dirs pre-created.
        ws = root / "workspace"
        step_dirs = [p for p in ws.iterdir()
                     if p.is_dir() and p.name[:2].isdigit()]
        assert step_dirs == [], f"unexpected step dirs: {step_dirs}"


def test_tool_build_custom_inner_repo_name():
    """A configured inner_repo name is used for the inner git repo."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Builder", ide_flags=[], copy_agents=False,
            mode="tool_build",
            config_overrides={"workspace": {"mode": "tool_build",
                                            "inner_repo": "engine"}},
        )
        assert (root / "engine" / ".git").exists()
        assert not (root / "project").exists()


# ---------------------------------------------------------------------------
# exploration profile
# ---------------------------------------------------------------------------


def test_exploration_scaffold_is_scratch_first():
    """exploration: workspace/scratch is eager; synthesis stays lazy;
    workspace/logs deferred. The classic numbered-step plumbing is minimal."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Probe", ide_flags=[], copy_agents=False,
            mode="exploration",
        )
        # Scratch home base eager.
        assert (root / "workspace" / "scratch").is_dir()
        # Safety surface present.
        for rel in ("inputs/raw_data", "inputs/literature", "inputs/context",
                    ".os_state", "environment", "docs"):
            assert (root / rel).is_dir(), f"missing safety dir {rel}"
        # Synthesis is lazy → absent on cold init.
        assert not (root / "synthesis").exists()
        # workspace/logs is lazy in exploration → absent on cold init.
        assert not (root / "workspace" / "logs").exists()
        # No tool_build governance surface leaked in.
        for leaked in ("spec", "decisions", "eval", "governance.md"):
            assert not (root / leaked).exists()
        assert get_workspace_mode(root) == "exploration"


# ---------------------------------------------------------------------------
# notebook profile
# ---------------------------------------------------------------------------


def test_notebook_scaffold_is_jupyter_first():
    """notebook: notebooks/ + data/ + outputs/ are eager; synthesis stays
    lazy; the mode-agnostic safety dirs hold. No analysis/tool_build/program
    surface leaks in."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Nb", ide_flags=[], copy_agents=False,
            mode="notebook",
        )
        # Jupyter-first work surface, eager.
        for rel in ("notebooks", "data", "outputs"):
            assert (root / rel).is_dir(), f"missing notebook dir {rel}"
        for f in ("notebooks/README.md", "data/README.md", "outputs/README.md"):
            assert (root / f).is_file(), f"missing notebook seed {f}"
        # Mode-agnostic safety surface present.
        for rel in ("inputs/raw_data", "inputs/literature", "inputs/context",
                    ".os_state", "environment", "workspace/scratch",
                    "workspace/logs", "docs"):
            assert (root / rel).is_dir(), f"missing safety dir {rel}"
        # synthesis is lazy → absent on cold init.
        assert not (root / "synthesis").exists()
        # No other mode's surface leaked in.
        for leaked in ("spec", "decisions", "eval", "governance.md",
                       "studies", "shared", "roll_up"):
            assert not (root / leaked).exists(), f"notebook leaked {leaked}"
        assert get_workspace_mode(root) == "notebook"
        from research_os.project_ops import load_state
        assert load_state(root).get("workspace_mode") == "notebook"


# ---------------------------------------------------------------------------
# multi_study (program) profile
# ---------------------------------------------------------------------------


def test_multi_study_scaffold_creates_program_surface():
    """multi_study: studies/ + shared/ + roll_up/ are eager and seeded with
    the program commons (codebook, prereg, governance). The mode-agnostic
    safety dirs hold; no tool_build/notebook surface leaks in."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        scaffold_minimal_workspace(
            root, "Program", ide_flags=[], copy_agents=False,
            mode="multi_study",
            config_overrides={"project_name": "Program",
                              "workspace": {"mode": "multi_study"}},
        )
        # Program portfolio surface.
        for rel in ("studies", "shared", "roll_up"):
            assert (root / rel).is_dir(), f"missing program dir {rel}"
        for f in ("studies/README.md", "shared/README.md",
                  "shared/codebook.md", "shared/preregistration.md",
                  "roll_up/README.md", "governance.md"):
            assert (root / f).is_file(), f"missing program seed {f}"
        # Mode-agnostic safety surface present.
        for rel in ("inputs/raw_data", "inputs/literature", "inputs/context",
                    ".os_state", "environment", "workspace/scratch",
                    "workspace/logs", "docs"):
            assert (root / rel).is_dir(), f"missing safety dir {rel}"
        # synthesis is lazy → absent on cold init.
        assert not (root / "synthesis").exists()
        # No other mode's surface leaked in.
        for leaked in ("spec", "decisions", "eval", "notebooks", "data",
                       "outputs"):
            assert not (root / leaked).exists(), f"multi_study leaked {leaked}"
        # Config + state both record the mode.
        assert get_workspace_mode(root) == "multi_study"
        from research_os.project_ops import load_state
        assert load_state(root).get("workspace_mode") == "multi_study"


def test_new_modes_in_valid_workspace_modes():
    """notebook + multi_study are registered enum values + scaffold profiles."""
    from research_os.tools.actions.state.config import VALID_WORKSPACE_MODES
    for m in ("analysis", "tool_build", "exploration", "notebook",
              "multi_study"):
        assert m in VALID_WORKSPACE_MODES
        assert m in SCAFFOLD_PROFILES


def test_unknown_mode_still_falls_back_to_analysis_byte_identical():
    """A nonsense mode collapses to the analysis profile (the fallback the
    new modes must NOT disturb) — same dir set as an explicit analysis build."""
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        a, b = Path(d1), Path(d2)
        scaffold_minimal_workspace(a, "A", ide_flags=[], copy_agents=False,
                                   mode="analysis")
        scaffold_minimal_workspace(b, "B", ide_flags=[], copy_agents=False,
                                   mode="totally-bogus-mode")
        assert _top_level_dirs_on_disk(a) == _top_level_dirs_on_disk(b)
        # The unknown-mode build must not have grown any new-mode surface.
        for leaked in ("notebooks", "studies", "shared", "roll_up", "spec",
                       "data", "outputs"):
            assert not (b / leaked).exists(), f"fallback leaked {leaked}"


# ---------------------------------------------------------------------------
# Mode routing registry — the single source of truth that biases routing.
# Every mode-aware code path reads from MODE_ROUTING; these tests lock the
# contract so notebook / multi_study / hybrid stay first-class and analysis
# stays the neutral baseline.
# ---------------------------------------------------------------------------


def test_mode_routing_registry_covers_every_biased_mode():
    """Every non-baseline mode (all VALID modes except analysis, which is the
    universal baseline routing surface) has a registry entry. This is what
    makes notebook + multi_study + hybrid first-class instead of relying only
    on the indirect workflow-shape tiebreak."""
    from research_os.tools.actions.router import MODE_ROUTING
    from research_os.tools.actions.state.config import VALID_WORKSPACE_MODES
    baseline = {"analysis"}
    biased = set(VALID_WORKSPACE_MODES) - baseline
    assert biased == set(MODE_ROUTING), (
        f"registry/enum drift: enum-biased={biased} registry={set(MODE_ROUTING)}"
    )


def test_mode_boost_is_registry_driven_for_every_native_sub_intent():
    """Each registry mode boosts EVERY one of its own native sub-intents by
    exactly its declared boost, and zero for a sub-intent it doesn't own."""
    from research_os.tools.actions.router import MODE_ROUTING, _mode_boost_for
    for mode, entry in MODE_ROUTING.items():
        for sub in entry.sub_intents:
            assert _mode_boost_for(mode, sub) == entry.boost, (
                f"{mode}/{sub} boost != {entry.boost}"
            )
        # A sub-intent guaranteed not to be native to this mode.
        assert _mode_boost_for(mode, "__not_a_real_sub_intent__") == 0


def test_notebook_and_multi_study_are_first_class():
    """notebook + multi_study + hybrid carry a real routing boost on their
    native sub-intents (not just the indirect shape tiebreak)."""
    from research_os.tools.actions.router import _mode_boost_for
    assert _mode_boost_for("notebook", "notebook_run") > 0
    assert _mode_boost_for("multi_study", "program_setup") > 0
    assert _mode_boost_for("hybrid", "hybrid_run") > 0


def test_analysis_gets_no_mode_boost():
    """analysis is the universal baseline; it may not boost ANY sub-intent —
    that would silently re-rank the default workspace."""
    from research_os.tools.actions.router import MODE_ROUTING, _mode_boost_for
    every_sub = {s for e in MODE_ROUTING.values() for s in e.sub_intents}
    for sub in every_sub | {"eda", "casual", "notebook_run"}:
        assert _mode_boost_for("analysis", sub) == 0, f"analysis boosted {sub}"


def test_tool_build_is_the_only_override_mode():
    """Only tool_build defers the semantic guess on a strong native trigger
    (build vocabulary collides with analysis). The lighter modes nudge but
    never override — guards against an over-steering regression."""
    from research_os.tools.actions.router import MODE_ROUTING
    overriding = {m for m, e in MODE_ROUTING.items() if e.override}
    assert overriding == {"tool_build"}


def test_mode_to_shape_derives_from_registry():
    """The mode→workflow_shape fallback map is derived from the registry, so
    a mode can't declare a shape in one place and a boost in another and
    drift. Every biased mode with a shape appears in the derived map."""
    from research_os.tools.actions.router import MODE_ROUTING, _MODE_TO_SHAPE
    expected = {m: e.shape for m, e in MODE_ROUTING.items() if e.shape}
    assert _MODE_TO_SHAPE == expected


# ── canonical directory layout (single source of truth) ───────────
# The layout is now declared once in LAYOUT_SPEC and composed; SCAFFOLD_PROFILES
# is derived. These lock the canonical contract so a future edit can't silently
# break the safety backbone or let a profile drift out of the spec.

# The mode-agnostic safety backbone that MUST appear in every profile.
_BACKBONE = (
    ".os_state",
    "docs",
    "inputs",
    "inputs/raw_data",
    "inputs/literature",
    "inputs/context",
    "workspace",
    "workspace/logs",
    "workspace/scratch",
    "environment",
)


def test_scaffold_profiles_is_derived_from_layout_spec():
    """SCAFFOLD_PROFILES must be the composition of LAYOUT_SPEC — no hand-
    written tuple may sneak back in and drift from the declarative source."""
    from research_os.project_ops import (
        LAYOUT_SPEC,
        SCAFFOLD_PROFILES,
        _compose_layout,
    )
    assert set(SCAFFOLD_PROFILES) == set(LAYOUT_SPEC)
    for mode, spec in LAYOUT_SPEC.items():
        assert SCAFFOLD_PROFILES[mode] == _compose_layout(spec)


def test_safety_backbone_present_in_every_mode():
    """Every workspace mode carries the full safety backbone in its
    top_level_dirs — the contract that .os_state/inputs/workspace/environment
    mean the same thing everywhere."""
    for mode, prof in SCAFFOLD_PROFILES.items():
        top = prof["top_level_dirs"]
        for d in _BACKBONE:
            assert d in top, f"{mode} missing backbone dir {d!r}"


def test_eager_plus_lazy_partition_top_level():
    """eager_dirs and lazy_dirs partition top_level_dirs exactly — nothing
    created twice, nothing forgotten. Guards the composer's set logic."""
    for mode, prof in SCAFFOLD_PROFILES.items():
        top = set(prof["top_level_dirs"])
        eager = set(prof["eager_dirs"])
        lazy = set(prof["lazy_dirs"])
        assert eager.isdisjoint(lazy), f"{mode}: dir is both eager and lazy"
        assert eager | lazy == top, f"{mode}: eager+lazy != top_level"


def test_describe_layout_covers_every_mode():
    """describe_layout renders for every mode and names the mode + its
    eager/lazy split — the single doc/sys_boot rendering path can't break
    silently for a mode."""
    from research_os.project_ops import LAYOUT_SPEC, describe_layout
    for mode in LAYOUT_SPEC:
        text = describe_layout(mode)
        assert text.startswith(f"{mode}:")
        assert "created at init (eager):" in text
        assert "created on first use (lazy):" in text


def test_describe_layout_rejects_unknown_mode():
    from research_os.project_ops import describe_layout
    import pytest
    with pytest.raises(KeyError):
        describe_layout("nope_not_a_mode")

