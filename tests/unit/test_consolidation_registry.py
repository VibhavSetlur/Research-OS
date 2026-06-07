"""Unit tests for ``research_os.consolidation_registry``.

Phase 9a covers the registry mechanics — registration, alias resolution,
arg transformation, removed-tool tracking, and the late-binding /
overwrite guards. Phase 9b cluster agents add cluster-specific tests
once their consolidations land.

The registry is module-level state, so every test snapshots and
restores it via the ``_clean_registry`` fixture. Don't share state
between tests.
"""

from __future__ import annotations

from typing import Any

import pytest

from research_os import consolidation_registry as cr


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot + restore the module-level registry around every test.

    The registry is intentionally global (server.py imports it once at
    startup) so tests must take care not to leak state into each other.
    """
    saved_consolidated = dict(cr.CONSOLIDATED_TOOLS)
    saved_removed = dict(cr.REMOVED_TOOLS)
    cr.CONSOLIDATED_TOOLS.clear()
    cr.REMOVED_TOOLS.clear()
    yield
    cr.CONSOLIDATED_TOOLS.clear()
    cr.CONSOLIDATED_TOOLS.update(saved_consolidated)
    cr.REMOVED_TOOLS.clear()
    cr.REMOVED_TOOLS.update(saved_removed)


def _audit_transform(old_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Sample arg_transform — injects scope+dimension for tool_audit_* aliases.

    Mirrors the shape Phase 9b cluster 1 will use. setdefault semantics
    so caller-supplied kwargs win.
    """
    table = {
        "tool_audit_evalue": ("step", "evalue"),
        "tool_audit_power": ("step", "power"),
        "tool_audit_prose": ("project", "prose"),
    }
    if old_name in table:
        scope, dimension = table[old_name]
        args.setdefault("scope", scope)
        args.setdefault("dimension", dimension)
    return args


def _stub_handler(arguments: dict[str, Any], root: Any = None) -> dict[str, Any]:
    return {"ok": True, "args": arguments}


# ---------------------------------------------------------------------------
# register_consolidated — happy path.
# ---------------------------------------------------------------------------


def test_register_basic_roundtrip():
    cr.register_consolidated(
        new_name="tool_audit",
        old_names=["tool_audit_evalue", "tool_audit_power"],
        arg_transform=_audit_transform,
        schema={"type": "object"},
        handler=_stub_handler,
    )
    assert "tool_audit" in cr.CONSOLIDATED_TOOLS
    spec = cr.CONSOLIDATED_TOOLS["tool_audit"]
    assert spec["old_names"] == ["tool_audit_evalue", "tool_audit_power"]
    assert spec["arg_transform"] is _audit_transform
    assert spec["schema"] == {"type": "object"}
    assert spec["handler"] is _stub_handler


def test_register_handler_optional():
    """Handler can be omitted at registration and bound later."""
    cr.register_consolidated(
        new_name="tool_x",
        old_names=[],
        arg_transform=lambda n, a: a,
        schema={"type": "object"},
    )
    assert cr.CONSOLIDATED_TOOLS["tool_x"]["handler"] is None
    cr.bind_handler("tool_x", _stub_handler)
    assert cr.CONSOLIDATED_TOOLS["tool_x"]["handler"] is _stub_handler


def test_consolidated_names_lists_registered_tools():
    cr.register_consolidated("a", [], lambda n, x: x, {})
    cr.register_consolidated("b", [], lambda n, x: x, {})
    assert set(cr.consolidated_names()) == {"a", "b"}


# ---------------------------------------------------------------------------
# register_consolidated — validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_name", ["", None, 42, [], {}])
def test_register_rejects_bad_new_name(bad_name):
    with pytest.raises(ValueError, match="new_name"):
        cr.register_consolidated(bad_name, [], lambda n, a: a, {})


def test_register_rejects_non_list_old_names():
    with pytest.raises(ValueError, match="old_names"):
        cr.register_consolidated("t", "tool_foo", lambda n, a: a, {})


def test_register_rejects_non_callable_transform():
    with pytest.raises(ValueError, match="arg_transform"):
        cr.register_consolidated("t", [], "not callable", {})


def test_register_rejects_non_dict_schema():
    with pytest.raises(ValueError, match="schema"):
        cr.register_consolidated("t", [], lambda n, a: a, "not a dict")


def test_register_rejects_non_callable_handler():
    with pytest.raises(ValueError, match="handler"):
        cr.register_consolidated("t", [], lambda n, a: a, {}, handler="not callable")


def test_register_duplicate_raises_without_overwrite():
    cr.register_consolidated("t", [], lambda n, a: a, {})
    with pytest.raises(ValueError, match="already registered"):
        cr.register_consolidated("t", [], lambda n, a: a, {})


def test_register_duplicate_allowed_with_overwrite():
    cr.register_consolidated("t", ["old_a"], lambda n, a: a, {"v": 1})
    cr.register_consolidated("t", ["old_b"], lambda n, a: a, {"v": 2}, overwrite=True)
    assert cr.CONSOLIDATED_TOOLS["t"]["schema"] == {"v": 2}
    assert cr.CONSOLIDATED_TOOLS["t"]["old_names"] == ["old_b"]


def test_register_alias_collision_across_tools_raises():
    """Same alias claimed by two different new_names is a bug."""
    cr.register_consolidated("tool_a", ["shared_alias"], lambda n, a: a, {})
    with pytest.raises(ValueError, match="already routes to"):
        cr.register_consolidated("tool_b", ["shared_alias"], lambda n, a: a, {})


def test_register_same_alias_under_overwrite_is_fine():
    """Overwriting the SAME tool can reuse aliases (replacing the spec)."""
    cr.register_consolidated("tool_a", ["alias_1"], lambda n, a: a, {})
    # Overwriting tool_a with the same alias must not collide-check against itself.
    cr.register_consolidated("tool_a", ["alias_1"], lambda n, a: a, {"v": 2}, overwrite=True)
    assert cr.CONSOLIDATED_TOOLS["tool_a"]["schema"] == {"v": 2}


# ---------------------------------------------------------------------------
# resolve_alias + apply_transform — the dispatch path.
# ---------------------------------------------------------------------------


def test_resolve_alias_returns_new_name():
    cr.register_consolidated(
        "tool_audit",
        ["tool_audit_evalue", "tool_audit_power"],
        _audit_transform,
        {},
    )
    assert cr.resolve_alias("tool_audit_evalue") == "tool_audit"
    assert cr.resolve_alias("tool_audit_power") == "tool_audit"


def test_resolve_alias_returns_none_for_unknown():
    assert cr.resolve_alias("does_not_exist") is None


def test_resolve_alias_returns_none_for_consolidated_name_itself():
    """Calling the canonical new name directly should NOT resolve through aliases."""
    cr.register_consolidated("tool_audit", ["tool_audit_evalue"], _audit_transform, {})
    assert cr.resolve_alias("tool_audit") is None


def test_apply_transform_injects_kwargs_for_legacy_alias():
    cr.register_consolidated(
        "tool_audit",
        ["tool_audit_evalue", "tool_audit_power"],
        _audit_transform,
        {},
    )
    out = cr.apply_transform("tool_audit_evalue", {"step_id": "S1"})
    assert out == {"step_id": "S1", "scope": "step", "dimension": "evalue"}


def test_apply_transform_caller_wins_setdefault():
    """If the caller passed scope=, we must NOT clobber it."""
    cr.register_consolidated(
        "tool_audit",
        ["tool_audit_evalue"],
        _audit_transform,
        {},
    )
    out = cr.apply_transform(
        "tool_audit_evalue",
        {"step_id": "S1", "scope": "project", "dimension": "claims"},
    )
    # Caller-supplied values win — alias's defaults must not override.
    assert out["scope"] == "project"
    assert out["dimension"] == "claims"


def test_apply_transform_noop_for_non_alias():
    cr.register_consolidated("tool_audit", [], _audit_transform, {})
    args = {"foo": "bar"}
    assert cr.apply_transform("tool_unrelated", args) is args


# ---------------------------------------------------------------------------
# all_aliases — flatten for server.py consumption.
# ---------------------------------------------------------------------------


def test_all_aliases_flattens_registry():
    cr.register_consolidated("tool_audit", ["a1", "a2"], _audit_transform, {})
    cr.register_consolidated("tool_viz", ["v1"], lambda n, a: a, {})
    flat = cr.all_aliases()
    assert flat == {"a1": "tool_audit", "a2": "tool_audit", "v1": "tool_viz"}


def test_all_aliases_returns_fresh_copy():
    cr.register_consolidated("tool_audit", ["a1"], _audit_transform, {})
    flat = cr.all_aliases()
    flat["mutated"] = "tool_x"
    # Mutating the returned dict must NOT affect a subsequent call.
    assert "mutated" not in cr.all_aliases()


def test_all_aliases_empty_registry():
    assert cr.all_aliases() == {}


# ---------------------------------------------------------------------------
# REMOVED_TOOLS — hard-removed surface.
# ---------------------------------------------------------------------------


def test_register_removed_basic():
    cr.register_removed(
        "tool_figure_create",
        "tool_figure_create was removed. Use tool_viz_figure instead.",
    )
    assert "tool_figure_create" in cr.REMOVED_TOOLS
    assert "tool_viz_figure" in cr.REMOVED_TOOLS["tool_figure_create"]
    assert cr.removed_names() == ["tool_figure_create"]


@pytest.mark.parametrize("bad", ["", None, 42])
def test_register_removed_rejects_bad_name(bad):
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="tool_name"):
        cr.register_removed(bad, "msg")


@pytest.mark.parametrize("bad_msg", ["", None, 42])
def test_register_removed_rejects_bad_message(bad_msg):
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="message"):
        cr.register_removed("tool_x", bad_msg)


# ---------------------------------------------------------------------------
# bind_handler.
# ---------------------------------------------------------------------------


def test_bind_handler_rebinds_existing_tool():
    cr.register_consolidated("tool_a", [], lambda n, a: a, {})
    cr.bind_handler("tool_a", _stub_handler)
    assert cr.CONSOLIDATED_TOOLS["tool_a"]["handler"] is _stub_handler


def test_bind_handler_unknown_tool_raises():
    from research_os.server.errors import RoError
    with pytest.raises((RoError, ValueError), match="not registered"):
        cr.bind_handler("tool_never_registered", _stub_handler)


def test_bind_handler_non_callable_raises():
    from research_os.server.errors import RoError
    cr.register_consolidated("tool_a", [], lambda n, a: a, {})
    with pytest.raises((RoError, ValueError), match="callable"):
        cr.bind_handler("tool_a", "not callable")


# ---------------------------------------------------------------------------
# End-to-end smoke — alias dispatch sequence.
# ---------------------------------------------------------------------------


def test_alias_dispatch_end_to_end():
    """Simulate the full server.py dispatch sequence:

    1. resolve_alias maps legacy name to canonical.
    2. apply_transform injects the dispatch kwargs.
    3. handler runs on the transformed args.
    """
    captured: dict[str, Any] = {}

    def handler(arguments: dict[str, Any], root: Any = None) -> dict[str, Any]:
        captured.update(arguments)
        return {"result": "ok"}

    cr.register_consolidated(
        "tool_audit",
        ["tool_audit_evalue"],
        _audit_transform,
        {"type": "object"},
        handler=handler,
    )

    legacy_name = "tool_audit_evalue"
    incoming_args = {"step_id": "S1"}

    new_name = cr.resolve_alias(legacy_name)
    assert new_name == "tool_audit"

    transformed = cr.apply_transform(legacy_name, dict(incoming_args))
    assert transformed == {"step_id": "S1", "scope": "step", "dimension": "evalue"}

    result = cr.CONSOLIDATED_TOOLS[new_name]["handler"](transformed, None)
    assert result == {"result": "ok"}
    assert captured == {"step_id": "S1", "scope": "step", "dimension": "evalue"}


def test_phase_9a_registry_starts_empty():
    """Phase 9a leaves the registry empty for Phase 9b agents to populate.

    Snapshot semantics: we cleared the registry in the fixture, so this
    is a sanity check that the fixture truly resets state.
    """
    assert cr.CONSOLIDATED_TOOLS == {}
    assert cr.REMOVED_TOOLS == {}
