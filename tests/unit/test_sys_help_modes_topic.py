"""v3.7.0: sys_help(topic='modes') — workspace-mode discoverability.

Before this slice the workspace MODE axis (analysis / hybrid / tool_build /
exploration / notebook / multi_study) was completely undiscoverable from
sys_help — the AI learned it existed only by reading config.py. The 'modes'
topic returns:
  * what the mode axis is (scaffold + routing + audits)
  * the registered-mode enum (sourced from config, can't drift)
  * a 1-line role per mode
  * how to set it + how routing bias differs per mode
"""

from __future__ import annotations

import json

import pytest

from research_os.server import _handle_tool_call


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / ".os_state").mkdir()
    (tmp_path / "workspace").mkdir()
    return tmp_path


def _payload(result):
    assert isinstance(result, list) and result, f"unexpected: {result!r}"
    env = json.loads(result[0].text)
    assert env["status"] == "success", env
    return env["data"]


def test_modes_topic_listed_in_topics_index(project_root):
    """sys_help with no topic must advertise 'modes' so the AI can find it."""
    res = _handle_tool_call("sys_help", {}, project_root)
    data = _payload(res)
    assert "modes" in data["topics"]


def test_modes_topic_returns_every_registered_mode(project_root):
    """The topic documents every VALID_WORKSPACE_MODE — enum sourced from
    config so the help text can't silently fall behind a new mode."""
    from research_os.tools.actions.state.config import VALID_WORKSPACE_MODES

    res = _handle_tool_call("sys_help", {"topic": "modes"}, project_root)
    data = _payload(res)

    assert set(data["registered_modes"]) == set(VALID_WORKSPACE_MODES)
    # Every registered mode has a non-empty 1-line role.
    for mode in VALID_WORKSPACE_MODES:
        assert mode in data["modes"], f"modes topic missing role for {mode}"
        assert data["modes"][mode].strip(), f"{mode} role is empty"


def test_modes_topic_explains_axis_and_routing(project_root):
    res = _handle_tool_call("sys_help", {"topic": "modes"}, project_root)
    data = _payload(res)
    for key in ("what_mode_is", "how_to_set", "routing_effect", "inspect"):
        assert key in data and data[key].strip(), f"missing {key}"
    # The routing_effect must name the biased modes vs the neutral ones.
    eff = data["routing_effect"]
    for biased in ("tool_build", "exploration", "notebook", "multi_study"):
        assert biased in eff
    assert "analysis" in eff and "hybrid" in eff


def test_modes_topic_aliases_resolve(project_root):
    """'mode' and 'workspace_mode' resolve to the same topic as 'modes'."""
    base = _payload(_handle_tool_call("sys_help", {"topic": "modes"},
                                      project_root))
    for alias in ("mode", "workspace_mode"):
        alt = _payload(_handle_tool_call("sys_help", {"topic": alias},
                                         project_root))
        assert alt["registered_modes"] == base["registered_modes"]
