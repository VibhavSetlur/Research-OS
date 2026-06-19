"""Protocol-pack and infrastructure-adapter discovery.

`_discover_packs_once()` is called at import time so list_tools / the
dispatcher see pack-contributed tools.

Both pack and adapter discovery merge entries into the live TOOL_DEFINITIONS
and _HANDLERS dicts from the registry.
"""
from __future__ import annotations

import logging


logger = logging.getLogger("research-os.server")


def _discover_packs_once() -> None:
    """Discover installed protocol packs and merge them into core registries.

    Idempotent — safe to call multiple times; subsequent calls reset
    the plugin loader's state and rediscover. The bundled in-tree packs
    in the list below (humanities, qualitative, theory_math, wet_lab,
    engineering) ship in this wheel and are loaded unconditionally;
    external packs come from the `research_os.protocol_pack`
    entry-point group.
    """
    try:
        from research_os.plugins import discover_packs
    except Exception as exc:
        logger.debug("plugin loader import failed: %s", exc)
        return
    # In-tree packs bundled with the core wheel. They register the
    # same way external packs would but skip the entry-point hop.
    bundled = [
        ("humanities", "research_os_humanities:register"),
        ("qualitative", "research_os_qualitative:register"),
        ("theory_math", "research_os_theory_math:register"),
        ("wet_lab", "research_os_wet_lab:register"),
        ("engineering", "research_os_engineering:register"),
    ]
    try:
        from .registry import TOOL_DEFINITIONS, _HANDLERS
        discover_packs(
            tool_definitions=TOOL_DEFINITIONS,
            handlers=_HANDLERS,
            bundled=bundled,
        )
    except Exception as exc:
        logger.warning("pack discovery raised unexpectedly: %s", exc)


def _discover_adapters_once() -> None:
    """Discover installed infrastructure adapters and merge their tools.

    Mirrors `_discover_packs_once()` but operates over the
    `research_os.adapter` entry-point group + the in-tree bundled
    adapter list. Idempotent; safe to call again from a test.
    """
    try:
        from research_os.adapters import discover_adapters
    except Exception as exc:
        logger.debug("adapter loader import failed: %s", exc)
        return
    bundled = [
        ("slurm", "research_os_adapter_slurm:register"),
        ("snakemake", "research_os_adapter_snakemake:register"),
        ("nextflow", "research_os_adapter_nextflow:register"),
        ("cytoscape", "research_os_adapter_cytoscape:register"),
        ("redcap", "research_os_adapter_redcap:register"),
        ("synapse", "research_os_adapter_synapse:register"),
        ("mlflow", "research_os_adapter_mlflow:register"),
        ("zenodo", "research_os_adapter_zenodo:register"),
    ]
    try:
        from .registry import TOOL_DEFINITIONS, _HANDLERS
        discover_adapters(
            tool_definitions=TOOL_DEFINITIONS,
            handlers=_HANDLERS,
            bundled=bundled,
        )
    except Exception as exc:
        logger.warning("adapter discovery raised unexpectedly: %s", exc)
