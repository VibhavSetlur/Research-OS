# Infrastructure adapters

Research-OS adapters are pluggable detectors + provenance extractors
for the tools a project uses *around* its code: HPC schedulers,
workflow engines, analysis platforms, data systems. They mean that a
researcher running, say, a Snakemake pipeline on Slurm gets every
rule + every sbatch directive + every HPC module load captured in
`workspace/<step>/provenance/` and surfaced in `workspace/tools.md`
without ever calling a special tool.

Six adapters ship bundled with the core wheel.

| Adapter | Detects | Extracts |
|---|---|---|
| `slurm` | `#SBATCH` / `#PBS` directives in shell scripts; inline `sbatch` / `qsub` | partition, time, nodes, cpus-per-task, mem, GPU, dependencies, modules |
| `snakemake` | `Snakefile` / `*.smk` files | rule names, inputs, outputs, shell preview, conda envs, containers, threads |
| `nextflow` | `*.nf` / `nextflow.config` / `main.nf` | process blocks, containers, cpus/memory/time directives, executor profiles |
| `cytoscape` | `*.cys` session archives | per-network: nodes, edges, node + edge attribute schema, layout, visual styles |
| `redcap` | REDCap data-dictionary CSVs OR exports with `record_id` + `redcap_event_name` | fields (name, type, validation, required, identifier-flagged), longitudinal vs cross-sectional, events, instruments, sample N, PHI warnings |
| `synapse` | `.synapseConfig` / `synapseclient` imports / `synXXXXXXXX` references | referenced Synapse entity IDs (with source script + line + nearby comment) |

## How adapters integrate

Three core MCP tools drive the surface:

- **`tool_adapters_list`** — walks every installed adapter, calls its
  `detect(root)`, returns the combined status with `detected_in_project`
  per adapter. Detection is filesystem-only and cheap.
- **`tool_adapter_extract`** — runs one adapter's `extract()` and
  persists the result to `workspace/<step>/provenance/<adapter>.yaml`.
- **`tool_adapters_run_all`** — bulk version: runs every detected
  adapter's extract().

A meta tool surfaces installation diagnostics:

- **`sys_adapters_installed`** — returns name, version, tool count,
  pattern count, and any registration errors. Bundled adapters
  (slurm, snakemake, nextflow, cytoscape, redcap, synapse) auto-load;
  third-party adapters register via the
  `research_os.adapter` entry-point group on `pip install`.

## Adapter-contributed tools

Each adapter optionally registers a small handful of opt-in tools.
All are namespaced `tool_<adapter>_*`:

- `tool_slurm_job_status(job_id)` — `squeue --json` or `qstat -f`
- `tool_slurm_estimate_cost(step_id, cost_per_node_hour)`
- `tool_snakemake_dryrun(step_id)`
- `tool_snakemake_dag_render(step_id)`
- `tool_nextflow_validate(step_id)`
- `tool_cytoscape_export_static(step_id, network_name)`
- `tool_redcap_schema_describe(step_id)`
- `tool_synapse_entity_info(entity_id)` — never auto-runs; requires
  `synapseclient` + auth.

External deps (snakemake CLI, Nextflow, synapseclient, etc.) are
optional. Adapters degrade gracefully when they're absent: detection
still works (it's filesystem-only), extraction still works for the
regex-fallback paths, and optional tools return a `status='warning'`
envelope with an install hint instead of failing.

## Tools.md gets multi-language

Alongside the adapters, v1.8.0 ships a new extractor module at
`src/research_os/tools/actions/state/extractors.py`. The
`tools.md` section that previously captured only Python imports + R
`library()` calls now covers:

- Python `import` / `from import` (via `extract_python`)
- R `library()` / `require()` / `p_load()` / `BiocManager::install()`
  (via `extract_r`)
- R `DESCRIPTION` Imports / Depends / Suggests / LinkingTo
  (via `extract_r_description`)
- `renv.lock` pinned versions (via `extract_r_renv_lock`)
- Bash `module load X/Y/Z` + `conda activate <env>` + `source venv`
  (via `extract_bash_modules`)
- Node `package.json` deps + JS / TS `import` / `require`
  (via `extract_node`)
- Rust `Cargo.toml` deps + `.rs` `use` statements (via `extract_rust`)
- Julia `Project.toml` deps + `.jl` `using` / `import`
  (via `extract_julia`)
- Adapter-contributed patterns: every active adapter's
  `tools_md_patterns` regex list is applied on top, so HPC modules,
  Snakemake rules, Nextflow processes, and REDCap / Cytoscape hits
  surface alongside language deps.

A step's `tools.md` entry now reads like a full reproducibility
manifest: "R library: DESeq2", "HPC module: bwa/0.7.17", "Snakemake
rule: align", etc.

## Writing your own adapter

```python
# src/research_os_adapter_myinfra/__init__.py
from pathlib import Path
from research_os.adapters import (
    AdapterRegistration, AdapterTool, register_adapter,
)

__version__ = "0.1.0"


def detect(root: Path) -> bool:
    """Filesystem-only. Fast. No network."""
    return (root / ".myinfra.yaml").exists()


def extract(root: Path, step_id: str | None = None) -> dict:
    """Return a structured dict the runner serialises to YAML."""
    cfg = (root / ".myinfra.yaml").read_text()
    return {"raw_config": cfg, "_notes": "regex-only; lacks YAML parser"}


def describe() -> dict:
    return {"name": "myinfra", "version": __version__}


def register() -> AdapterRegistration:
    return register_adapter(
        name="myinfra",
        version=__version__,
        description="MyInfra workflow-system provenance extractor.",
        detect=detect,
        extract=extract,
        describe=describe,
        tools_md_patterns=(
            (r"^\s*MYINFRA_TASK\s+(\w+)", "MyInfra task: {0}"),
        ),
        tools=(),     # optional tools live here
    )
```

Then in your package's `pyproject.toml`:

```toml
[project.entry-points."research_os.adapter"]
myinfra = "research_os_adapter_myinfra:register"
```

`pip install research-os-adapter-myinfra` and it auto-registers on
the next server start. Bundled adapters (the 6 above) sidestep the
entry-point hop via an in-tree bundled list in `server.py`.

## Namespace + safety rules

- Adapter `name` must be lowercase alphanumeric (underscores ok).
- Tool names must start with `tool_<adapter>_`.
- `tools_md_patterns` regex are compiled at `register_adapter()`
  call so malformed patterns fail loudly at startup instead of
  silently at extract time.
- `detect()` and `extract()` errors are caught per-adapter — a bad
  adapter writes its traceback to `workspace/logs/adapter_errors.log`
  and is skipped without blocking server startup or other adapters.
- Adapters MUST NOT auto-query external services (e.g. Synapse) at
  detect or extract time. Network calls live behind opt-in optional
  tools the user has to explicitly invoke.

## Stress-matrix coverage

Three reference projects under `tests/fixtures/projects/` exercise
the adapters in CI:

- `slurm_snakemake` — RNA-seq pipeline with Snakefile + sbatch
  wrappers (exercises slurm + snakemake adapters)
- `nextflow_chipseq` — ChIP-seq with Nextflow DSL2 process blocks
- `redcap_longitudinal` — longitudinal study with REDCap data
  dictionary + export

The stress matrix now runs 11 reference projects × mock model on
every PR.
