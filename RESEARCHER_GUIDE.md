# Researcher Guide: Research OS

Welcome to Research OS, the guidance engine designed to supercharge your research workflow while maintaining absolute reproducibility and rigorous provenance.

## Core Concepts

Research OS acts as a mediator between you (the human researcher), your data, and LLM-based agents (like Cursor, Windsurf, or custom scripts). It provides a structured environment that enforces best practices.

### 1. The Workspace Architecture
When you initialize a project using `sys.workspace.scaffold`, Research OS creates a publication-grade directory structure:
- `inputs/`: Immutable raw data and literature.
- `workspace/`: Active experimentation, derived data, and logs.
- `docs/`: Living documents like hypotheses and research questions.
- `synthesis/`: Final outputs like the paper draft.

### 2. Immutability
The `inputs/` directory is strictly write-protected. Agents cannot modify files here. All transformations must be saved to `workspace/data/derived/`. This ensures your raw data is never corrupted.

### 3. Provenance & Logging
Research OS maintains a continuous audit trail:
- **Decision Log**: Major methodological choices are recorded via `tool.log.decision`.
- **Methods Log**: Every technique applied is appended to `workspace/methods.md`.
- **Analysis Log**: Chronological findings are logged in `workspace/analysis.md`.
- **State Checkpoints**: The entire workspace state is snapshotted via `sys.checkpoint.create`.

### 4. Experiment Branching
Want to test a new hypothesis without ruining your main analysis? Use the experiment branching feature (`sys.branch.create`). It creates an isolated workspace state. If the experiment fails, you simply switch back (`sys.branch.switch`). If it succeeds, you can merge the findings (`sys.branch.merge`).

## Getting Started

1. **Initialize Project**: Run the MCP server in an empty directory and call `sys.workspace.scaffold` (with a project name).
2. **Configure**: Update the generated `inputs/researcher_config.yaml` with your API keys (e.g., Firecrawl, OpenAI) and preferred autonomy level.
3. **Upload Data**: Place your raw datasets in `inputs/raw_data/` and literature PDFs in `inputs/literature/`.
4. **Agent Interaction**: Start interacting with your agent (Cursor, etc.). The agent will automatically discover the Research OS tools and begin exploring your data safely.

## Autonomy Levels

You can set the autonomy level in your configuration:
- **Supervised**: The agent will pause and request approval (`sys.checkpoint.pending`) before executing long-running tasks or making major methodology changes.
- **Semi-Autonomous**: The agent will request approval only for critical milestones.
- **Autonomous**: The agent operates fully independently, relying on checkpoints for safety.

## Using Guidance Protocols

Research OS includes built-in methodologies (Protocols) for common research tasks:
- `domain_analysis`
- `literature_search`
- `evidence_synthesis`
- `research_design`
- `methodology_selection`
- `analysis_plan`

Agents can load these protocols via `sys.guidance.get` to follow rigorous, structured steps.

## External MCP Servers

Research OS can integrate with other MCP servers (e.g., a specialized genomic analysis server). Add the server details to your `researcher_config.yaml`, and Research OS will help your agent discover them via `sys.external_mcp.discover`.
