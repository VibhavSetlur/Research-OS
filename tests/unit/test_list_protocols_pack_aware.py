"""v1.11.1 regression — `list_protocols()` must walk pack-registered dirs.

Before the fix, `sys_protocol_list` (and the underlying `list_protocols`)
only scanned the in-tree core ``PROTOCOLS_DIR``. Pack-contributed protocols
(humanities, qualitative, theory_math, wet_lab, engineering) silently
disappeared from the catalog, which broke the "browse what's available"
maintainer flow for any project actually using a pack.

These tests pin the fix:

  * Pack protocols appear in the unfiltered listing.
  * Each entry carries a ``pack_or_core`` source tag.
  * ``category=<pack_name>`` narrows to that pack's contributions only.
  * ``category=<core_segment>`` still works (no regression in the existing
    core-only path).
  * The ``sys_protocol_list`` MCP handler accepts and threads ``category``.
"""

from __future__ import annotations

import json

import pytest


# Importing the server module triggers the bundled-pack discovery side
# effect that populates ``_PACK_PROTOCOL_DIRS``. We do this at module level
# so every test in this file sees a consistent post-discovery snapshot.
import research_os.server as server_module  # noqa: F401  (side-effect import)
from research_os.plugins.loader import pack_protocol_dirs
from research_os.tools.actions.protocol import list_protocols


# Bundled in-tree pack names the core wheel always discovers. If the pack
# discovery story changes (e.g. unbundling), this list moves with it.
BUNDLED_PACK_NAMES = {
    "humanities",
    "qualitative",
    "theory_math",
    "wet_lab",
    "engineering",
}


@pytest.fixture(scope="module")
def discovered_pack_dirs() -> dict:
    """Snapshot of pack-registered protocol dirs after server discovery."""
    dirs = pack_protocol_dirs()
    assert dirs, (
        "Bundled packs failed to register — discovery side effect from "
        "importing research_os.server did not run."
    )
    return dirs


class TestPackProtocolsVisibleInListing:
    def test_listing_includes_pack_entries(self, discovered_pack_dirs):
        names_by_source: dict[str, set] = {}
        for entry in list_protocols():
            names_by_source.setdefault(entry["pack_or_core"], set()).add(
                entry["name"]
            )
        # Every bundled pack that registered a non-empty protocols_dir on
        # disk must contribute at least one entry.
        for pack_name in BUNDLED_PACK_NAMES:
            pdir = discovered_pack_dirs.get(pack_name)
            if pdir is None or not pdir.exists():
                continue
            yamls = [
                f for f in pdir.rglob("*.yaml") if not f.name.startswith("_")
            ]
            if not yamls:
                continue
            assert pack_name in names_by_source, (
                f"pack '{pack_name}' has {len(yamls)} protocol(s) on disk "
                f"but none surfaced in list_protocols()"
            )
            assert names_by_source[pack_name], (
                f"pack '{pack_name}' surfaced 0 protocols (expected >=1)"
            )

    def test_every_entry_carries_pack_or_core_tag(self):
        for entry in list_protocols():
            assert "pack_or_core" in entry, (
                f"entry {entry!r} is missing the pack_or_core source tag"
            )
            assert isinstance(entry["pack_or_core"], str)
            assert entry["pack_or_core"], "pack_or_core tag must be non-empty"

    def test_core_protocols_still_present(self):
        sources = {entry["pack_or_core"] for entry in list_protocols()}
        assert "core" in sources, (
            "core protocols disappeared from the listing — the pack walk "
            "should additively extend the catalog, not replace it"
        )


class TestCategoryFilter:
    def test_filter_to_theory_math_pack(self, discovered_pack_dirs):
        if "theory_math" not in discovered_pack_dirs:
            pytest.skip("theory_math pack not registered in this environment")
        entries = list_protocols(category="theory_math")
        assert entries, (
            "list_protocols(category='theory_math') returned nothing — the "
            "v1.11.1 bug regressed (pack protocols not walked)"
        )
        for entry in entries:
            assert entry["pack_or_core"] == "theory_math", (
                f"unexpected non-theory_math entry leaked through the filter: "
                f"{entry!r}"
            )
        # Sanity: at least one well-known theory_math protocol surfaces.
        names = {e["name"] for e in entries}
        assert any(
            n.startswith("theory_math/") for n in names
        ), f"theory_math entries should be namespaced under the pack: {names}"

    def test_filter_to_core_category(self):
        entries = list_protocols(category="guidance")
        assert entries, "core 'guidance' category should not be empty"
        # All matches must be either core protocols with first segment
        # 'guidance' or pack protocols whose inner category is 'guidance'.
        for entry in entries:
            head = entry["name"].split("/", 1)[0]
            if entry["pack_or_core"] == "core":
                assert head == "guidance", (
                    f"core entry {entry['name']!r} leaked into guidance filter"
                )

    def test_unknown_category_returns_empty(self):
        entries = list_protocols(category="definitely_not_a_real_category_xyz")
        assert entries == []


class TestSysProtocolListHandler:
    """The MCP-facing handler must accept and thread the category argument."""

    @staticmethod
    def _parse(result):
        # The handler returns a list[TextContent]; pull the JSON envelope
        # out of the first element and dig past the {status, data} wrap.
        assert isinstance(result, list) and result, result
        envelope = json.loads(result[0].text)
        assert envelope["status"] == "success", envelope
        return envelope["data"]

    def test_handler_passes_category_through(self):
        from research_os.server import _handle_sys_protocol_list

        result = _handle_sys_protocol_list(
            "sys_protocol_list",
            {"category": "theory_math"},
            root=None,
        )
        data = self._parse(result)
        assert data["category"] == "theory_math"
        protocols = data["protocols"]
        assert protocols, (
            "Expected at least one theory_math protocol when the pack is "
            "registered; got an empty list. Pack discovery may have failed."
        )
        for entry in protocols:
            assert entry["pack_or_core"] == "theory_math", entry

    def test_handler_without_category_returns_full_catalog(self):
        from research_os.server import _handle_sys_protocol_list

        result = _handle_sys_protocol_list(
            "sys_protocol_list", {}, root=None
        )
        data = self._parse(result)
        assert data["category"] is None
        sources = {p["pack_or_core"] for p in data["protocols"]}
        # Core is always present; at least one pack should be too in the
        # bundled configuration.
        assert "core" in sources
        assert sources & BUNDLED_PACK_NAMES, (
            f"no bundled pack surfaced in full catalog: {sources}"
        )
