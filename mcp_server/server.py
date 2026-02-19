#!/usr/bin/env python3
"""
ACE MCP Server - Main server implementation.

Implements the Model Context Protocol (MCP) over stdio,
exposing ACE's institutional knowledge service.

Protocol: JSON-RPC 2.0 over stdio
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import ACETools

# Configure logging to stderr (stdout reserved for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("ace-mcp")


class ACEMCPServer:
    """
    MCP Server for ACE Institutional Knowledge Service.

    Exposes CGR³ knowledge retrieval and learning tools via
    the Model Context Protocol.

    Tools:
        - get_guidance: Context-aware knowledge retrieval (CGR³)
        - learn: Add knowledge to playbook
        - query: Simple semantic search
        - feedback: Mark patterns as helpful/harmful
        - build_feature: TDD feature development (optional)
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "ace-knowledge"
    SERVER_VERSION = "1.0.0"

    def __init__(
        self,
        playbook_id: Optional[str] = None,
        playbook_file: Optional[Path] = None,
        enable_tdd: bool = True,
    ):
        """
        Initialize the MCP server.

        Args:
            playbook_id: Playbook ID for database mode
            playbook_file: Path to JSON playbook for file mode
            enable_tdd: Whether to expose TDD tools
        """
        self.playbook_id = playbook_id
        self.playbook_file = playbook_file
        self.enable_tdd = enable_tdd

        # Initialize tools handler
        self.tools = ACETools(
            playbook_id=playbook_id,
            playbook_file=playbook_file,
            enable_tdd=enable_tdd,
        )

        self._log(f"ACE MCP Server initialized")
        self._log(f"Playbook: {playbook_id or playbook_file or 'default'}")

    def _log(self, message: str, level: str = "info"):
        """Log to stderr (stdout is reserved for MCP protocol)."""
        getattr(logger, level)(message)

    def run(self):
        """Run the MCP server (stdio mode)."""
        self._log("Starting MCP server (stdio mode)")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = self._handle_request(request)
                if response is not None:
                    self._send_response(response)
            except json.JSONDecodeError as e:
                self._log(f"Invalid JSON: {e}", "error")
                self._send_error(-32700, "Parse error", None)
            except Exception as e:
                self._log(f"Error handling request: {e}", "error")
                self._send_error(-32603, str(e), None)

    def _handle_request(self, request: dict) -> Optional[dict]:
        """Handle a JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        self._log(f"Request: {method}")

        # Handle MCP protocol methods
        if method == "initialize":
            return self._handle_initialize(params, request_id)
        elif method == "initialized":
            # Notification, no response needed
            return None
        elif method == "tools/list":
            return self._handle_tools_list(request_id)
        elif method == "tools/call":
            return self._handle_tools_call(params, request_id)
        elif method == "shutdown":
            self._log("Shutdown requested")
            sys.exit(0)
        else:
            return self._make_error(-32601, f"Method not found: {method}", request_id)

    def _handle_initialize(self, params: dict, request_id: Any) -> dict:
        """Handle initialize request."""
        return self._make_response({
            "protocolVersion": self.PROTOCOL_VERSION,
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": self.SERVER_VERSION,
            },
            "capabilities": {
                "tools": {},
            },
        }, request_id)

    def _handle_tools_list(self, request_id: Any) -> dict:
        """Handle tools/list request."""
        tools = self.tools.get_tool_definitions()
        return self._make_response({"tools": tools}, request_id)

    def _handle_tools_call(self, params: dict, request_id: Any) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        self._log(f"Calling tool: {tool_name}")

        try:
            result = self.tools.call_tool(tool_name, tool_args)
            return self._make_response({
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, indent=2, default=str),
                }],
            }, request_id)
        except ValueError as e:
            return self._make_error(-32602, str(e), request_id)
        except Exception as e:
            self._log(f"Tool error: {e}", "error")
            return self._make_error(-32603, str(e), request_id)

    def _make_response(self, result: Any, request_id: Any) -> dict:
        """Create a JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    def _make_error(self, code: int, message: str, request_id: Any) -> dict:
        """Create a JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    def _send_response(self, response: dict):
        """Send a response to stdout."""
        print(json.dumps(response), flush=True)

    def _send_error(self, code: int, message: str, request_id: Any):
        """Send an error response."""
        self._send_response(self._make_error(code, message, request_id))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ACE MCP Server - Institutional Knowledge for Claude Code"
    )
    parser.add_argument(
        "--playbook", "-p",
        help="Playbook ID (requires database)",
    )
    parser.add_argument(
        "--playbook-file", "-f",
        type=Path,
        help="Path to JSON playbook file (no database required)",
    )
    parser.add_argument(
        "--no-tdd",
        action="store_true",
        help="Disable TDD tools (knowledge-only mode)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    server = ACEMCPServer(
        playbook_id=args.playbook,
        playbook_file=args.playbook_file,
        enable_tdd=not args.no_tdd,
    )
    server.run()


if __name__ == "__main__":
    main()
