# AI Integration Guide

Research OS is designed to be the foundational operating system for Autonomous AI Researchers. It works seamlessly as a Model Context Protocol (MCP) server.

## How Agents Should Interact

1. **Initialization**: Agents should use `sys.workspace.scaffold` to establish a new project environment.
2. **Configuration**: Agents should load `sys.config.get` to adapt their autonomy level (Supervised, Semi-Autonomous, Autonomous) based on human preference.
3. **Exploration**: Rather than loading multi-gigabyte datasets, agents must use `sys.workspace.scaffold` (which triggers `_profile_inputs()`) to view `data_inventory.json`, and then use `tool.data.sample` for safe EDA.
4. **Tool Discovery**: Tools are categorized. Use `sys.tool.search` to find relevant capabilities without overloading your context window.
5. **Safeguards**: Never attempt to modify `inputs/raw_data/`. The system will throw a WriteProtectedError.

## Integration Methods

### Cursor / Windsurf
Add `python -m research_os.server` as an MCP connection. Point it to your project directory.

### Custom Scripted Agents
You can wrap the `research_os` module directly in Python or interact over stdio if you are building a custom LangChain or LlamaIndex loop.
