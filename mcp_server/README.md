# ACE MCP Server

Model Context Protocol (MCP) server exposing ACE's institutional knowledge service to Claude Code, Claude Desktop, and other MCP-compatible clients.

**This is a local development tool, not a deployable service.** It communicates over stdio (see [Protocol](#protocol) below) and is spawned as a subprocess by your MCP client on your own machine — there's no network listener, authentication, or remote-access story here, unlike `services/ace-audit/` which is a real deployable service.

## Overview

The ACE MCP Server provides context-aware knowledge retrieval using CGR³ (Context Graph Retrieve-Rank-Reason). It enables AI assistants to:

- **Get Guidance**: Retrieve institutional patterns with verdicts (APPLY, ASK_FIRST, SKIP)
- **Learn**: Add knowledge to the playbook
- **Query**: Simple semantic search
- **Feedback**: Mark patterns as helpful/harmful

## Installation

```bash
# From the ace_enterprise root
pip install -e .
```

## Usage

### Standalone (stdio mode)

```bash
# Basic usage
python -m mcp_server

# With specific playbook
python -m mcp_server --playbook my_project_playbook

# With JSON playbook file (no database required)
python -m mcp_server --playbook-file ./playbook.json

# Knowledge-only mode (disable TDD tools)
python -m mcp_server --no-tdd

# Debug logging
python -m mcp_server --debug
```

### Claude Desktop Integration

Add to your Claude Desktop config (`~/.config/claude/claude_desktop_config.json` on Linux, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "ace-knowledge": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/ace_enterprise"
    }
  }
}
```

With a specific playbook:

```json
{
  "mcpServers": {
    "ace-knowledge": {
      "command": "python",
      "args": ["-m", "mcp_server", "--playbook", "my_project"],
      "cwd": "/path/to/ace_enterprise"
    }
  }
}
```

### Claude Code Integration

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "ace-knowledge": {
      "command": "python",
      "args": ["-m", "mcp_server", "--playbook-file", "./playbook.json"]
    }
  }
}
```

## Tools

### get_guidance

Context-aware knowledge retrieval using CGR³. Returns patterns categorized by verdict:

- **APPLY**: Safe to use, context matches well
- **ASK_FIRST**: May apply but needs clarification
- **SKIP**: Don't use (excluded from response)

```json
{
  "name": "get_guidance",
  "arguments": {
    "query": "handle database timeout",
    "team_id": "backend",
    "tech_stack": {"python": "3.11", "database": "postgresql"},
    "domain": "error-handling"
  }
}
```

### learn

Add knowledge to the institutional playbook.

```json
{
  "name": "learn",
  "arguments": {
    "content": "Always use connection pooling for database connections",
    "type": "pattern",
    "tags": ["database", "performance"],
    "confidence": 0.8
  }
}
```

### query

Simple semantic search without CGR³ reasoning.

```json
{
  "name": "query",
  "arguments": {
    "query": "error handling",
    "top_k": 5,
    "section": "troubleshooting"
  }
}
```

### feedback

Mark patterns as helpful or harmful to improve future retrieval.

```json
{
  "name": "feedback",
  "arguments": {
    "bullet_id": "ctx-00042",
    "feedback": "helpful",
    "context": "Worked great for FastAPI timeout handling"
  }
}
```

### get_playbook_info

Get information about the current playbook.

```json
{
  "name": "get_playbook_info",
  "arguments": {}
}
```

### build_feature (TDD)

Build a feature using Test-Driven Development. Requires TDD tools to be enabled.

```json
{
  "name": "build_feature",
  "arguments": {
    "feature": "Feature: User authentication\n  Scenario: Login with valid credentials\n    Given a registered user\n    When they submit valid credentials\n    Then they should be logged in",
    "project_path": "/path/to/project"
  }
}
```

## File-based Playbook

For quick setup without a database, use a JSON playbook file:

```json
{
  "metadata": {
    "name": "My Project Playbook",
    "version": "1.0.0"
  },
  "sections": {
    "strategies_and_hard_rules": [
      {
        "id": "rule-001",
        "content": "Always validate user input at API boundaries",
        "tags": ["security", "validation"]
      }
    ],
    "code_snippets": [],
    "troubleshooting": [],
    "domain_knowledge": []
  }
}
```

## Protocol

The server implements MCP over stdio using JSON-RPC 2.0:

- All communication is via stdin/stdout
- Logging goes to stderr
- Protocol version: 2024-11-05

## Environment Variables

- `ACE_PLAYBOOK_ID`: Default playbook ID
- `ACE_DATABASE_URL`: PostgreSQL connection string (for database mode)
