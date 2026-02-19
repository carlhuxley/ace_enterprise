"""
Entry point for running ACE MCP server as a module.

Usage:
    python -m mcp_server
    python -m mcp_server --playbook my_playbook
    python -m mcp_server --playbook-file ./playbook.json
"""

from mcp_server.server import main

if __name__ == "__main__":
    main()
