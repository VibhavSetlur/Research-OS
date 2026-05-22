# Research Copilot — GitHub Copilot Instructions

You are assisting a researcher using Research Copilot, an AI-driven research engine.

## System Configuration
- Installed as a Python package (`research_copilot`).
- CLI Tool: `rcp <command>`
- Project configuration: `.research/config.yaml`
- Project structure: `00_inputs/`, `01_workspace/`, `02_experiments/`, `03_synthesis/`

## Recommended Workflow
1. Run `rcp status` to check pipeline state.
2. Run `rcp scan` to analyze input data.
3. Read `00_inputs/intake.md` to understand the research question.
4. Run `rcp agent research_init` to load the first phase instructions.
5. Execute the pipeline sequentially: init → literature → method → analysis → compile → audit.

## Critical Guidelines
- NEVER modify raw data in `00_inputs/raw_data/` (it is immutable).
- ALWAYS compute a SHA-256 hash of raw data files before using them.
- NEVER invent or guess citations, p-values, or effect sizes.
- Scripts must be numbered sequentially (e.g., `01_load.py`, `02_process.py`) inside the experiment `scripts/` directory.
- Every generated output requires a sibling `.meta.yaml` containing metadata and provenance.
- Every figure generated requires an accompanying `.interpret.md` explanation file.
- For files >1GB, use polars lazy frames (`pl.scan_csv()`). NEVER load large datasets eagerly.
- Use causal language only if the study design is an RCT or contains a valid identification strategy.

## Key CLI Commands
- `rcp status` - Get current project state.
- `rcp scan` - Scan input datasets.
- `rcp agent <name>` - Show specific agent instructions.
- `rcp skill <name>` - Show specific skill methodology.
- `rcp intent <query>` - Route user request through the intent router.
- `rcp branch <name>` - Create a research branch.
- `research-copilot-mcp` - Start Model Context Protocol server.

Refer to `AGENTS.md` for full agent instructions and skill manuals.
