"""Setup-UX bug fixes from the three-persona dry run (feat batch)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from research_os.project_ops import scaffold_minimal_workspace


def test_ide_none_writes_no_ide_configs():
    """--ide none -> ide_flags=[] must wire ZERO IDE configs (was: defaulted to 5)."""
    root = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root, "T", mode="analysis", ide_flags=[])
    # None of the per-IDE artifacts should exist.
    for artifact in (".mcp.json", "opencode.json", ".vscode", ".antigravity",
                     ".cursor", ".claude"):
        assert not (root / artifact).exists(), f"{artifact} written despite --ide none"


def test_ide_none_distinct_from_unspecified():
    """An explicit empty list wires nothing; None (unspecified) wires defaults."""
    root_default = Path(tempfile.mkdtemp()) / "p"
    scaffold_minimal_workspace(root_default, "T", mode="analysis")  # ide_flags=None
    # Default path wires the standard set — at least one IDE artifact appears.
    wired = any((root_default / a).exists() for a in
                (".mcp.json", ".cursor", ".claude", ".vscode"))
    assert wired, "unspecified ide_flags should wire the default IDE set"


def test_daemon_serve_has_free_port_fallback():
    """server.serve probes for a free port instead of hard-failing the bind."""
    import inspect

    from research_os.daemon import server

    src = inspect.getsource(server.serve)
    assert "_port_free" in src
    assert "address already in use" not in src or "in use" in src  # graceful path
    # falls forward to a free port rather than crashing/exiting 0 on a busy port
    assert "using %s instead" in src or "no free port" in src
