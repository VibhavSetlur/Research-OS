# Research OS (Pre-Release Build)

A Guidance Engine for Autonomous Research Workflows via the Model Context Protocol (MCP).

## Overview
Research OS is an MCP server designed to manage and guide LLM agents (like Cursor, Windsurf, or custom scripts) through rigorous, reproducible academic research workflows.

It enforces:
- **Immutability** of raw data and literature.
- **Methodological provenance** via strict append-only decision logging.
- **Isolated experimentation** via state branching.
- **Reproducible data pipelines** with built-in profiling and sampling.

## Quick Start
1. Install dependencies: `pip install .`
2. Start the MCP server: `python -m research_os.server`
3. In your MCP client (Cursor/Windsurf), scaffold your first project:
   `sys.workspace.scaffold {"project_name": "My Study"}`
4. Consult the `RESEARCHER_GUIDE.md` for full details.

## Development
To run the tests:
```bash
pip install -e ".[dev]"
pytest tests/
```
