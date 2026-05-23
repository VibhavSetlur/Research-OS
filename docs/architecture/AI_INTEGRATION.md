# AI Integration Guide

Research OS is an MCP-native operating system for AI-assisted research. It provides the Hands, Eyes, and Memory — the AI IDE (Cursor, Claude, Antigravity) provides the intelligence.

## How Agents Should Interact

1. **Initialization**: Agents should use `sys.workspace.scaffold` to establish a new project environment.
2. **Configuration**: Agents should load `sys.config.get` to adapt their autonomy level (Supervised, Semi-Autonomous, Autonomous) based on human preference.
3. **Exploration**: Rather than loading multi-gigabyte datasets, agents must use `sys.workspace.scaffold` (which triggers `_profile_inputs()`) to view `data_inventory.json`, and then use `tool.data.sample` for safe EDA.
4. **Tool Discovery**: Tools are categorized. Use `sys.tool.search` to find relevant capabilities without overloading your context window.
5. **Safeguards**: Never attempt to modify `inputs/raw_data/`. The system will throw a WriteProtectedError.

## Connection Configuration

### Cursor
Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "research-os": {
      "command": "python",
      "args": ["-m", "research_os.server", "--transport", "stdio"]
    }
  }
}
```
Point it to your project directory by running the server from there, or use the `--workspace` flag:
```json
{
  "mcpServers": {
    "research-os": {
      "command": "python",
      "args": ["-m", "research_os.server", "--transport", "stdio", "--workspace", "/path/to/project"]
    }
  }
}
```

### Claude Desktop (Claude Code)
Add to `~/.claude/mcp.json`:
```json
{
  "mcpServers": {
    "research-os": {
      "command": "python",
      "args": ["-m", "research_os.server", "--transport", "stdio"]
    }
  }
}
```



### Antigravity
Antigravity auto-discovers MCP servers from the project directory. No manual configuration needed.

### VS Code (via VS Code MCP extension)
Add to `.vscode/mcp.json`:
```json
{
  "mcpServers": {
    "research-os": {
      "command": "python",
      "args": ["-m", "research_os.server", "--transport", "stdio"]
    }
  }
}
```

### Custom Scripted Agents
You can wrap the `research_os` module directly in Python or interact over stdio if you are building a custom LangChain or LlamaIndex loop.

## Tool Discovery Pattern

All tools follow a consistent naming convention:

| Prefix | Category | Examples |
|--------|----------|---------|
| `sys.workspace.*` | Project setup and file operations | `sys.workspace.scaffold`, `sys.file.read` |
| `sys.guidance.*` | Research protocol loading | `sys.guidance.get`, `sys.guidance.list` |
| `sys.state.*` | State introspection | `sys.state.get`, `sys.state.summary` |
| `sys.checkpoint.*` | Snapshot and rollback | `sys.checkpoint.create`, `sys.checkpoint.rollback` |
| `sys.path.*` | Experiment path management | `sys.path.create`, `sys.path.abandon`, `sys.path.list` |
| `sys.config.*` | Researcher configuration | `sys.config.get`, `sys.config.set`, `sys.config.init` |
| `tool.search.*` | Literature and web search | `tool.search.semantic_scholar`, `tool.search.web` |
| `tool.package.*` | Environment management | `tool.package.install`, `tool.env.freeze` |
| `mem.*` | Memory logging | `mem.analysis.log`, `mem.methods.append` |

Use `sys.tool.search` with a keyword (e.g., `"search"`, `"checkpoint"`) to find relevant tools without enumerating all of them.

## Protocol Loading

Research protocols (guidance workflows) are loaded via `sys.guidance.get`:
- `sys.guidance.list` — shows all available protocols with descriptions
- `sys.guidance.get` — returns the full YAML protocol with steps and expected outputs
- `sys.guidance.validate` — checks if expected outputs exist in the workspace

Each protocol encodes a complete research workflow as structured YAML with typed steps. Protocols auto-adjust to the model profile (`small`, `medium`, `large`) via the researcher config.

## Error Handling

Research OS returns structured error envelopes:

```json
{
  "status": "error",
  "data": {
    "error": "WriteProtectedError: Cannot modify raw inputs."
  }
}
```

Common errors and how to handle them:

| Error | Cause | Recovery |
|-------|-------|----------|
| `WriteProtectedError` | Attempt to write to `inputs/` or overwrite `synthesis/` without `force=true` | Save output to `workspace/<step>/` instead |
| `Rate limit exceeded` | Too many tool calls in 60s window | Wait and retry |
| `File not found` | Requested path does not exist | Check path with `sys.file.list` |
| `File too large (>50MB)` | Read exceeds size limit | Use `tool.data.sample` instead |

Always check `status` before processing `data`. Wrap tool calls in try-except and handle `"error"` status gracefully.
