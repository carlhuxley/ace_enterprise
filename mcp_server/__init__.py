"""
ACE MCP Server - Model Context Protocol server for institutional knowledge.

Exposes ACE's CGR³ knowledge service to Claude Code, Claude Desktop,
and other MCP-compatible clients.

Usage:
    # Run as MCP server (stdio mode)
    python -m mcp_server

    # With specific playbook
    python -m mcp_server --playbook my_project_playbook

    # Query-only mode (no database required)
    python -m mcp_server --playbook-file ./playbook.json
"""

from mcp_server.server import ACEMCPServer, main

__all__ = ["ACEMCPServer", "main"]
