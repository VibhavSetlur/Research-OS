"""Infrastructure-adapter framework for Research-OS.

Adapters are pluggable detectors + provenance-extractors for tools
the research project uses *around* its code: HPC schedulers (Slurm,
PBS), workflow engines (Snakemake, Nextflow), analysis platforms
(Cytoscape), data systems (REDCap, Synapse), and so on.

Each adapter:
    * declares a `detect(root)` callable that returns True when the
      project uses the infra,
    * declares an `extract(root, step_id=None)` callable that reads
      the project filesystem and writes a structured provenance YAML
      under `workspace/<step>/provenance/<adapter>.yaml`,
    * contributes regex patterns to the multi-language tools.md
      extractor (so HPC modules / Snakemake rules / Nextflow processes
      surface alongside Python imports),
    * optionally registers a small handful of opt-in tools the AI can
      call (e.g. `tool_slurm_job_status`).

Discovery is via the `research_os.adapter` Python entry-point group —
mirrors the protocol-pack plugin loader from v1.7.0 but with a
distinct group name so the two registries don't cross-contaminate.

Stable surface:
    AdapterRegistration   — the namedtuple every adapter returns
    register_adapter      — convenience constructor with validation
    discover_adapters     — entry-point walker (called from server.py)
    installed_adapters    — diagnostic snapshot for sys_adapters_installed
"""
from research_os.adapters.base import (
    AdapterRegistration,
    AdapterTool,
    register_adapter,
    ok_envelope,
    err_envelope,
)
from research_os.adapters.loader import (
    AdapterLoadResult,
    discover_adapters,
    installed_adapters,
    load_adapter_errors,
    active_adapter_extractors,
    write_adapter_errors_log,
)

__all__ = [
    "AdapterRegistration",
    "AdapterTool",
    "register_adapter",
    "ok_envelope",
    "err_envelope",
    "AdapterLoadResult",
    "discover_adapters",
    "installed_adapters",
    "load_adapter_errors",
    "active_adapter_extractors",
    "write_adapter_errors_log",
]
