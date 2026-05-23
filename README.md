# Research OS

**From data to publication-ready manuscript – your MCP-native research operating system.**

Research OS is a Model Context Protocol (MCP) server designed to manage and guide LLM agents (like Cursor, Claude Code, Antigravity, or custom scripts) through rigorous, reproducible academic research workflows.

## Quick Start

1. **Install the OS**
   ```bash
   pip install research-os
   
   # Or install with all optional tools (like MCP and Dev):
   pip install research-os[all]
   ```

2. **Start the MCP Server**
   ```bash
   python -m research_os.server
   ```
   *(Configure this command in your MCP client like Cursor or Claude Code).*

3. **Initialize your Project**
   In your AI IDE, prompt the agent:
   > "Please scaffold my new project using `sys.workspace.scaffold` with the name 'My First Study'."

4. **Add Data and Analyze**
   Then drop your data files into `inputs/raw_data/` and ask:
   > "Analyze my data."

## Architecture

```text
+-------------------+       +-------------------+       +-------------------+       +-------------------+
|                   |       |                   |       |                   |       |                   |
|     AI IDE        | <---> |   MCP Protocol    | <---> |    Research OS    | <---> |     Workspace     |
| (Cursor / Claude / Antigravity) |       |                   |       |                   |       |                   |
+-------------------+       +-------------------+       +-------------------+       +-------------------+
```

## What This Is NOT

- **NOT an autonomous agent**: It does not think, plan, or make decisions on its own.
- **NOT an LLM**: It relies entirely on your AI IDE (e.g., Cursor, Claude) to provide the intelligence.
- **NOT a black box**: Every decision and change is logged for full transparency.

## Workspace File Tree
```text
<user-project>/
├── AGENTS.md                       # AI agent instructions
├── README.md                       # Auto-generated project overview
├── .os_state/                      # INTERNAL — OS state
│   ├── state_ledger.yaml           # Source of truth
│   ├── manifest.json               # Full file inventory with checksums
│   ├── checkpoints/                # Workspace snapshots
│   └── cache/                      # API response cache
├── docs/                           # Human-written research docs
│   ├── research_question.md
│   ├── hypotheses.md
│   └── glossary.md
├── inputs/                         # IMMUTABLE — researcher provided
│   ├── researcher_config.yaml      # Researcher preferences & API keys
│   ├── raw_data/                   # Source data (or symlinks)
│   ├── literature/                 # PDFs
│   ├── context/                    # Notes, past results, text files
│   ├── intake.md                   # Auto-generated research brief
│   └── literature_index.yaml       # Filename → citation key mapping
├── workspace/                      # ACTIVE — iterative experiments
│   ├── methods.md                  # Append-only method log
│   ├── analysis.md                 # Chronological log + Mermaid workflow
│   ├── citations.md                # Running bibliography with verified flags
│   ├── workflow.mermaid            # Auto-updated workflow diagram
│   ├── workflow.png                # Rendered diagram
│   ├── logs/                       # Execution logs
│   │   ├── searches.log            # Every web search logged (JSON lines)
│   │   ├── state_changes.log       # Before/after state diffs
│   │   ├── notifications.log       # Researcher notifications
│   │   ├── data_inventory.json     # Auto-profiled data inventory
│   │   └── 01_baseline.log         # Per-step execution logs
│   ├── 01_experiment_baseline/
│   │   ├── README.md               # Goal, hypotheses, outcomes
│   │   ├── conclusions.md          # Key findings, bugs, routing decisions
│   │   ├── methods_research.md     # AI's research into methods for this step
│   │   ├── data/                   # Derived data
│   │   ├── scripts/                # Versioned (01_load_v1.py, 02_eda_v1.py)
│   │   ├── outputs/
│   │   │   ├── reports/
│   │   │   ├── figures/
│   │   │   ├── tables/
│   │   │   └── dashboards/
│   │   └── environment/            # Pinned dependencies
│   ├── 02_data_preparation/
│   │   └── ... (same structure)
│   └── .os_state/                  # Symlink to root .os_state/
├── synthesis/                      # FINAL — populated on completion
│   ├── abstract.md
│   ├── paper.tex / paper.pdf
│   ├── references.bib
│   ├── workflow_diagram.png
│   └── supplementary/
└── environment/                    # Global environment
    ├── requirements.txt
    └── Dockerfile
```

## Value Proposition

Why use Research OS?
- **Immutability First:** Your raw data (`inputs/raw_data/`) is strictly write-protected. All transformations are safely saved as derived data.
- **Methodological Provenance:** Every critical decision, applied method, and statistical result is atomically logged via strict append-only decision logging.
- **Chronological Experiment Paths:** Experiments run as numbered consecutive steps (`01_experiment_baseline/`, `02_data_preparation/`). Abandoned paths are renamed (e.g., `__DEAD_END__`) rather than deleted, preserving full history.
- **Model-Size Adaptability:** Supports `small`, `medium`, and `large` LLM profiles to optimize token economy and context window limits.

## Documentation
- **Manuals**: [Researcher Guide (Operational Manual)](docs/RESEARCHER_GUIDE.md) - Learn how to run your first project.
- **Tutorials**: [Quickstart](docs/tutorials/QUICKSTART.md), [Example Walkthrough](docs/tutorials/EXAMPLE_WALKTHROUGH.md)
- **Architecture**: [AI Integration](docs/architecture/AI_INTEGRATION.md), [Guidance System](docs/architecture/GUIDANCE_SYSTEM.md)
- **Templates**: [Agents Guide](templates/AGENTS.md) - Strict rules for LLM agents operating in this workspace.
- **Project**: [Contributing](CONTRIBUTING.md) | [Changelog](CHANGELOG.md) | [Code of Conduct](CODE_OF_CONDUCT.md)

## File Index

To help you navigate this repository:
- `src/research_os/server.py` - Core MCP server and tool definitions.
- `src/research_os/protocols/` - The YAML-based methodology guidelines.
- `src/research_os/tools/` - Implementation of all OS actions (search, path creation, literature, etc.).
- `src/research_os/state/` - State ledger and checkpoint logic.
- `templates/` - Default rules and guides to feed to agents.

[![PyPI version](https://badge.fury.io/py/research-os.svg)](https://badge.fury.io/py/research-os)
[![Python versions](https://img.shields.io/pypi/pyversions/research-os.svg)](https://pypi.org/project/research-os/)
[![Tests](https://github.com/VibhavSetlur/Research-OS/actions/workflows/tests.yml/badge.svg)](https://github.com/VibhavSetlur/Research-OS/actions)
