"""v3.8.0: AUTONOMY GATE blocks use the collapsed proceed/confirm idiom.

Before this slice every AUTONOMY GATE block in the protocol catalogue spelled
out four autonomy modes in full — `adaptive (default) → ...`, `manual /
supervised → ...`, `autopilot → ...` — restating the same proceed-path twice
(adaptive + autopilot almost always said the same thing). That made the
adaptive default visually co-equal with three override modes and bloated every
gate by ~40%.

v3.8.0 collapses each block to two behaviour lines that make adaptive primary:

    AUTONOMY GATE:
      Risk: <dimension> — <why>.
      proceed (adaptive default, autopilot) → <proceed behaviour>.
      confirm first (manual / supervised) → <confirm behaviour>.

Autopilot nuance (the rare case where autopilot bypassed a confirm-floor that
adaptive honours) is preserved inline as a parenthetical "(Under autopilot,
...)" clause rather than a separate mode line.

These tests lock the new idiom catalogue-wide so a future edit can't silently
regress a gate back to the verbose four-mode form.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PROTOCOLS = _REPO / "src" / "research_os" / "protocols"

# The one sanctioned exception: analysis_plan.yaml carries a bulleted
# `AUTONOMY GATE (read interaction.autonomy_level):` variant that lists modes
# as markdown bullets inside a longer reasoning passage. It is intentionally
# not part of the collapsed two-line idiom.
_BULLET_VARIANT_MARKER = "AUTONOMY GATE (read interaction.autonomy_level)"


def _yaml_files() -> list[str]:
    return sorted(glob.glob(str(_PROTOCOLS / "**" / "*.yaml"), recursive=True))


def _collapsed_blocks() -> list[tuple[str, int]]:
    """Return (file, line) for every collapsed `proceed (adaptive default`
    gate line across the catalogue."""
    out: list[tuple[str, int]] = []
    for f in _yaml_files():
        for i, line in enumerate(Path(f).read_text().splitlines(), start=1):
            if "proceed (adaptive default" in line:
                out.append((f, i))
    return out


def test_catalogue_uses_collapsed_proceed_idiom():
    """Every standard AUTONOMY GATE block now leads with the collapsed
    `proceed (adaptive default, autopilot) →` line."""
    blocks = _collapsed_blocks()
    # There are 28 well-formed gate blocks in the catalogue (the count grows
    # as protocols are added — assert a floor, not an exact number, so adding
    # a new gated protocol doesn't fail this test).
    assert len(blocks) >= 28, (
        f"expected >=28 collapsed gate blocks, found {len(blocks)}"
    )


def test_no_verbose_four_mode_gate_lines_remain():
    """The old verbose form (`adaptive (default) →` as a standalone gate line)
    must not survive anywhere except the sanctioned bulleted variant."""
    offenders: list[str] = []
    for f in _yaml_files():
        text = Path(f).read_text()
        has_bullet_variant = _BULLET_VARIANT_MARKER in text
        for i, line in enumerate(text.splitlines(), start=1):
            if re.search(r"adaptive \(default\)\s*→", line):
                # The bulleted variant legitimately keeps `- adaptive (default) →`.
                if has_bullet_variant and line.lstrip().startswith("- adaptive"):
                    continue
                offenders.append(f"{Path(f).name}:{i}: {line.strip()}")
    assert not offenders, (
        "verbose four-mode gate lines must be collapsed:\n" + "\n".join(offenders)
    )


def test_collapsed_blocks_pair_proceed_with_confirm():
    """Each collapsed `proceed (...)` line is followed (within a few lines) by
    a matching `confirm first (manual / supervised) →` line, so no gate loses
    its override path."""
    for f, ln in _collapsed_blocks():
        lines = Path(f).read_text().splitlines()
        window = "\n".join(lines[ln - 1 : ln + 8])
        assert "confirm first (manual / supervised)" in window, (
            f"{Path(f).name}:{ln} proceed-line has no matching confirm-first line"
        )


@pytest.mark.parametrize(
    "rel",
    [
        "build/spec_and_design.yaml",
        "build/test_strategy.yaml",
        "build/release_and_changelog.yaml",
    ],
)
def test_autopilot_nuance_preserved(rel):
    """The three blocks where autopilot deviated from adaptive keep that nuance
    inline as a parenthetical clause — collapsing must not drop a floor."""
    text = (_PROTOCOLS / rel).read_text()
    assert "Under autopilot" in text, (
        f"{rel}: autopilot-specific nuance was dropped during gate collapse"
    )
