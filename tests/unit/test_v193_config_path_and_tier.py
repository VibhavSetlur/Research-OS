"""v1.9.3 — config-reader path fix (AUDIT-v1.9.2-001) and project_tier
propagation (AUDIT-v1.9.2-011).

These bugs silently neutered the entire v1.5.1 tier/strictness subsystem.
The wizard writes `researcher_config.yaml` to `inputs/`, but three readers
were looking for it at the project root. And `resolve_gate_strictness`
never consulted `project_tier` as a default, so `project_tier: throwaway`
in the config did nothing.
"""

from __future__ import annotations

import yaml


def _scaffold(tmp_path):
    """Bare-bones project root the readers can introspect."""
    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_resolve_gate_strictness_reads_from_inputs_dir(tmp_path):
    """Wizard writes to inputs/; the resolver must read from there too."""
    from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "gate_strictness": "light",
    }))

    res = resolve_gate_strictness(root)
    assert res["resolved"] == "light"
    assert res["source"] == "config"


def test_resolve_gate_strictness_falls_back_to_legacy_root_config(tmp_path):
    """Legacy pre-v1.5.1 projects keep working via root-level fallback."""
    from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness

    root = _scaffold(tmp_path)
    # No inputs/researcher_config.yaml — only the legacy root path.
    (root / "researcher_config.yaml").write_text(yaml.safe_dump({
        "gate_strictness": "strict",
    }))

    res = resolve_gate_strictness(root)
    assert res["resolved"] == "strict"
    assert res["source"] == "config"


def test_project_tier_propagates_to_resolve_gate_strictness(tmp_path):
    """project_tier set in inputs/researcher_config maps to gate_strictness."""
    from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "project_tier": "throwaway",
    }))

    res = resolve_gate_strictness(root)
    assert res["resolved"] == "light"
    assert res["source"] == "project_tier"
    assert res["project_tier"] == "throwaway"


def test_explicit_gate_strictness_overrides_project_tier(tmp_path):
    """If both are set, explicit gate_strictness wins (matches doc invariant)."""
    from research_os.tools.actions.state.rigor_signals import resolve_gate_strictness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "gate_strictness": "strict",
        "project_tier": "throwaway",
    }))

    res = resolve_gate_strictness(root)
    assert res["resolved"] == "strict"
    assert res["source"] == "config"


def test_project_tier_strictness_reads_from_inputs_dir(tmp_path):
    """project_tier_strictness must read inputs/researcher_config.yaml too."""
    from research_os.tools.actions.state.quick_mode import project_tier_strictness

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "project_tier": "sketch",
    }))

    res = project_tier_strictness(root)
    assert res["status"] == "success"
    assert res["project_tier"] == "sketch"
    assert res["default_gate_strictness"] == "normal"


def test_read_model_profile_from_inputs_dir(tmp_path):
    """_read_model_profile reads inputs/researcher_config.yaml model_profile."""
    from research_os.tools.actions.state.reliability import _read_model_profile

    root = _scaffold(tmp_path)
    (root / "inputs" / "researcher_config.yaml").write_text(yaml.safe_dump({
        "model_profile": "large",
    }))

    assert _read_model_profile(root) == "large"


def test_read_model_profile_legacy_fallback(tmp_path):
    """_read_model_profile falls back to root config for legacy projects."""
    from research_os.tools.actions.state.reliability import _read_model_profile

    root = _scaffold(tmp_path)
    (root / "researcher_config.yaml").write_text(yaml.safe_dump({
        "model_profile": "small",
    }))

    assert _read_model_profile(root) == "small"
