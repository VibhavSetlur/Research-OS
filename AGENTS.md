# Research Copilot — Development Guide

This is the development AGENTS.md for Research Copilot contributors. For researcher-facing AI instructions, see `src/research_copilot/assets/AGENTS.md`.

## Architecture

Research Copilot is a Python package (`research_copilot`) with bundled assets. All agents, skills, workflows, and domains are in `src/research_copilot/assets/`. The `.research/` directory contains only `config.yaml` and runtime cache.

## Key Directories

| Path | Purpose |
|------|---------|
| `src/research_copilot/` | Python package — CLI, engine, MCP server, core modules |
| `src/research_copilot/assets/` | Bundled assets — agents, skills, workflows, domains, schemas |
| `src/research_copilot/assets/AGENTS.md` | Researcher-facing AI instructions (copied to project on `rcp init`) |
| `src/research_copilot/assets/.cursorrules` | Cursor IDE rules (copied to project on `rcp init`) |
| `src/research_copilot/assets/.clinerules` | Cline/Roo Code rules (copied to project on `rcp init`) |

## Development Rules

1. All asset `.md` files must stay under ~120 lines
2. Replace code implementations with AI-readable protocols, decision rules, validation checklists
3. Never break `rcp init` — it must create a working project with AI rules
4. Test changes with `python -m pytest tests/`
5. Lint with `ruff check src/` and `ruff format src/`

## Release Checklist

1. Update version in `pyproject.toml`
2. Run full test suite: `python -m pytest tests/`
3. Build package: `python -m build`
4. Test install: `pip install dist/research_copilot-*.whl`
5. Test `rcp init` creates project with AI rules
6. Publish to PyPI
