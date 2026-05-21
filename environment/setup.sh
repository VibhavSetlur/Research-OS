#!/usr/bin/env bash
# Research Copilot — Environment Setup (venv)
# Creates a reproducible Python environment and installs standard MCP servers.
#
# Usage:
#   bash environment/setup.sh          # Create venv, install deps, probe MCP
#   bash environment/setup.sh --clean  # Remove and recreate everything
#   source environment/venv/bin/activate  # Activate manually

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="$PROJECT_ROOT/environment/venv"
REQUIREMENTS="$PROJECT_ROOT/environment/requirements.txt"

echo "============================================"
echo "  Research Copilot — Environment Setup"
echo "============================================"
echo ""

# ── Clean flag ────────────────────────────────────────────────────────────────
if [ "$1" = "--clean" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$ENV_DIR"
    echo "Done."
    echo ""
fi

# ── Python venv ───────────────────────────────────────────────────────────────
if [ -d "$ENV_DIR" ]; then
    echo "Virtual environment already exists at: $ENV_DIR"
    echo "To recreate, run: bash environment/setup.sh --clean"
    echo ""
    echo "To activate:"
    echo "  source $ENV_DIR/bin/activate"
    echo ""
else
    echo "Creating virtual environment..."
    python3 -m venv "$ENV_DIR"
    echo "Done."
    echo ""
fi

echo "Activating environment and installing Python dependencies..."
source "$ENV_DIR/bin/activate"
pip install --upgrade pip -q

if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
    echo "Found pyproject.toml — installing in editable mode..."
    pip install -e "$PROJECT_ROOT[all]" -q
else
    echo "Installing research-copilot from PyPI..."
    pip install "research-copilot[all]" -q
    if [ -f "$REQUIREMENTS" ]; then
        pip install -r "$REQUIREMENTS" -q
    fi
fi
echo "Python dependencies installed."
echo ""

# ── MCP Server Installation ───────────────────────────────────────────────────
echo "============================================"
echo "  MCP Server Setup"
echo "============================================"
echo ""

install_mcp_server() {
    local package="$1"
    local label="$2"

    if command -v node >/dev/null 2>&1 && command -v npx >/dev/null 2>&1; then
        echo -n "  Probing $label ($package) ... "
        # Use --yes and a dry-run to verify the package resolves without
        # permanently installing it globally (npx caches it locally).
        if npx --yes "$package" --version >/dev/null 2>&1; then
            echo "OK (available via npx)"
        else
            echo "WARN: package resolved but version check failed (may still work)"
        fi
    else
        echo "  SKIP: Node.js / npx not found — $label unavailable."
        echo "        Install Node.js >= 18 from https://nodejs.org to enable MCP servers."
    fi
}

install_mcp_server "@modelcontextprotocol/server-sqlite"     "SQLite MCP server"
install_mcp_server "@modelcontextprotocol/server-filesystem" "Filesystem MCP server"

echo ""

# ── Preflight check ───────────────────────────────────────────────────────────
echo "============================================"
echo "  Preflight Check"
echo "============================================"
echo ""
if [ -f "$PROJECT_ROOT/environment/preflight_check.py" ]; then
    python "$PROJECT_ROOT/environment/preflight_check.py" || true
fi

echo ""
echo "============================================"
echo "  Setup Complete"
echo "============================================"
echo ""
echo "To activate the environment:"
echo "  source $ENV_DIR/bin/activate"
echo ""
echo "To run the research CLI:"
echo "  rcp status"
echo ""
echo "To start MCP servers for AI IDEs:"
echo "  research-copilot-mcp"
echo ""
echo "To compress state with a local LLM after long runs:"
echo "  rcp compress --model=ollama/llama3"
echo ""
