"""Plugin system for Research-OS protocol packs.

Third-party (or first-party out-of-tree) packs register via the
`research_os.protocol_pack` Python entry-point group. Each pack
exposes a `register()` callable that returns a `PackRegistration`
describing the pack's protocols, tools, router entries, and an
optional domain detector. The loader (`research_os.plugins.loader`)
discovers packs at server startup and merges them into the core
registries with namespace prefixing to avoid collisions.

Stable surface:
    PackRegistration   — the namedtuple every pack returns
    register_tool      — decorator capturing (name, schema, handler)
    discover_packs     — entry-point walker (called from server.py)
    installed_packs    — diagnostic snapshot for sys_packs_installed
"""
from research_os.plugins.pack_api import (
    PackRegistration,
    PackTool,
    register_tool,
    captured_tools,
    reset_captured_tools,
    pack_ok,
    pack_err,
)
from research_os.plugins.loader import (
    discover_packs,
    installed_packs,
    load_pack_errors,
    pack_paper_sections,
    PackLoadResult,
)

__all__ = [
    "PackRegistration",
    "PackTool",
    "register_tool",
    "captured_tools",
    "reset_captured_tools",
    "pack_ok",
    "pack_err",
    "discover_packs",
    "installed_packs",
    "load_pack_errors",
    "pack_paper_sections",
    "PackLoadResult",
]
