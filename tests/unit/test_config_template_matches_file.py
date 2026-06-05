"""AUDIT-v1.9.2-068 — keep CONFIG_TEMPLATE in sync with templates/researcher_config.yaml.

The schema for ``inputs/researcher_config.yaml`` has historically lived in three
places: the in-code ``CONFIG_TEMPLATE`` constant (used by the wizard at init
time), ``templates/researcher_config.yaml`` (used as documentation + the
canonical reference for human authors), and ``docs/RESEARCHER_GUIDE.md`` §8.
The audit flagged drift across these three. This test pins the in-code copy
to the file copy so the source of truth is a single editable artifact —
``templates/researcher_config.yaml`` — and the in-code copy is mechanically
kept up to date.

The only allowed difference is the ``project_name:`` line, where the in-code
copy carries a ``"{project_name}"`` substitution placeholder so init_config
can stamp the directory name on first write.
"""
from __future__ import annotations

from pathlib import Path

from research_os.tools.actions.state.config import CONFIG_TEMPLATE


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalise(text: str) -> str:
    """Strip the project_name substitution + trim trailing whitespace."""
    out = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("project_name:"):
            # Both files declare project_name; normalise both forms so the
            # placeholder vs blank-default difference doesn't trip the diff.
            out.append("project_name: __NORMALISED__")
        else:
            out.append(stripped)
    return "\n".join(out).rstrip("\n")


def test_config_template_matches_template_file():
    """In-code CONFIG_TEMPLATE must match templates/researcher_config.yaml."""
    template_file = _repo_root() / "templates" / "researcher_config.yaml"
    assert template_file.exists(), (
        f"missing source-of-truth file: {template_file}"
    )
    on_disk = template_file.read_text()

    # Strip the "SOURCE OF TRUTH" preamble from the disk copy — the in-code
    # constant doesn't carry it (it's a documentation aid for human editors,
    # not part of the per-project file the wizard writes).
    on_disk_lines = on_disk.splitlines()
    if on_disk_lines and "SOURCE OF TRUTH" in (on_disk_lines[2] if len(on_disk_lines) > 2 else ""):
        # Drop the 8-line preamble block (lines 3-10 inclusive in the file
        # header) so the rest matches the in-code copy.
        kept = [on_disk_lines[0], on_disk_lines[1]]
        i = 2
        while i < len(on_disk_lines):
            line = on_disk_lines[i]
            if line.startswith("# Tells the AI"):
                kept.extend(on_disk_lines[i:])
                break
            i += 1
        on_disk = "\n".join(kept)

    in_code = CONFIG_TEMPLATE
    a = _normalise(on_disk)
    b = _normalise(in_code)
    assert a == b, (
        "templates/researcher_config.yaml drifted from CONFIG_TEMPLATE.\n"
        "Edit templates/researcher_config.yaml first, then mirror into\n"
        "src/research_os/tools/actions/state/config.py::CONFIG_TEMPLATE.\n"
        f"--- on-disk\n{a}\n--- in-code\n{b}\n"
    )
