# Contributing to Research OS

Thank you for your interest in improving Research OS! This guide will help you get started with contributing.

## How to Contribute

1. **Fork the Repository**: Create a fork of this repository to your own GitHub account.
2. **Clone your Fork**: Clone the repository to your local machine.
3. **Create a Branch**: Create a new branch for your feature or bugfix (`git checkout -b feature/your-feature-name`).
4. **Make Changes**: Implement your changes. Ensure you adhere to the code style and formatting guidelines.
5. **Run Tests**: Ensure all existing and new tests pass by running `pytest`.
6. **Commit Changes**: Commit your changes with descriptive messages (`git commit -m "Add new feature"`).
7. **Push to Fork**: Push your branch to your forked repository (`git push origin feature/your-feature-name`).
8. **Submit a Pull Request**: Open a pull request from your fork's branch to the main repository.

## Architecture Overview

Research OS is as a **MCP-Native Research OS**. This means:
- **The AI IDE is the brain**: Tools like Cursor, Claude Code, or Antigravity perform the "thinking," planning, and routing.
- **This repository is the body**: It provides Hands (tools), Eyes (observability), and Memory (state).
- **Stateless Execution**: The OS itself does not make autonomous decisions; it relies entirely on the IDE driving the feedback loop via Model Context Protocol (MCP) tool calls.

The workspace is strictly partitioned into `inputs/` (immutable data), `workspace/` (active research branches with state management), and `synthesis/` (compiled final outputs).

## Development Setup

We recommend using `uv` or `poetry` for dependency management. To set up the environment:

```bash
pip install -e .[dev,all]
```

## Code Style and Formatting

We enforce strict code formatting using `ruff` and type checking using `mypy`.

Before committing, run:
```bash
ruff check .
ruff format .
# Run mypy against the codebase. The project currently uses `research_os`
# as the package name; an alias package `research_os` is provided for compatibility.
mypy src/research_os/  # or: mypy src/research_os/
```

## Writing Tests

We use `pytest` for testing. Place your tests in the `tests/` directory. If your code calls the LLM, use `pytest-mock` or `responses` to mock the API responses so tests run quickly and don't cost tokens.

## Bug Reports and Feature Requests

Please use the provided GitHub Issue templates to report bugs or request features. Ensure you provide as much detail as possible to help us understand and resolve the issue quickly.

## Adding New Protocols

Protocols are YAML files located in `src/research_os/protocols/`.
To add a new protocol:
1. Create a `your_protocol.yaml` file in the directory.
2. Define `name`, `version`, `description`, `expected_outputs`, and a list of `steps`.
3. Generate `light/` variants for small models.

## Adding New Tools

To add a new MCP tool:
1. Define the tool logic in the appropriate file inside `src/research_os/tools/actions/`.
2. Register the tool's JSON schema in `src/research_os/server.py` inside the `TOOL_DEFINITIONS` dictionary.
3. Add an `if name == "your_tool_name":` routing block in the `_handle_tool_call` function in `server.py` to map the MCP invocation to your action logic.
