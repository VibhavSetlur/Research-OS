#!/usr/bin/env python3
"""Persistent Conversational Control Plane for Research Copilot.

Provides a lightweight REPL that acts as a client to the MCP server.
"""

import asyncio
import sys

try:
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

async def start_chat_loop():
    print("=" * 60)
    print("Research Copilot - Conversational Control Plane (MCP Client)")
    print("=" * 60)
    
    if not HAS_MCP:
        print("ERROR: mcp package is required for the client REPL. Install with `pip install mcp`.")
        sys.exit(1)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "research_copilot.server"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected to MCP Server. Type your request (or 'exit' / 'quit' to stop).")

            while True:
                # Use synchronous input in an executor to avoid blocking the event loop
                user_msg = await asyncio.get_event_loop().run_in_executor(None, input, "\n> ")
                user_msg = user_msg.strip()
                
                if not user_msg:
                    continue
                if user_msg.lower() in ("exit", "quit"):
                    break

                try:
                    print("Routing intent via MCP server...")
                    result = await session.call_tool("route_intent", arguments={"query": user_msg})
                    for content in result.content:
                        if content.type == "text":
                            print(content.text)
                except Exception as e:
                    print(f"Error calling MCP tool: {e}")

def main():
    try:
        asyncio.run(start_chat_loop())
    except KeyboardInterrupt:
        print("\nExiting.")

if __name__ == "__main__":
    main()
