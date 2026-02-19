"""
ACE MCP Tools - Tool definitions and handlers.

Defines the tools exposed by the ACE MCP server and implements
their execution logic.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ace-mcp.tools")


class ACETools:
    """
    Tool definitions and handlers for ACE MCP server.

    Primary tools (CGR³ focused):
        - get_guidance: Context-aware knowledge retrieval
        - learn: Add knowledge to playbook
        - query: Simple semantic search
        - feedback: Mark patterns helpful/harmful

    Secondary tools:
        - build_feature: TDD feature development
        - get_playbook_info: Playbook status
    """

    def __init__(
        self,
        playbook_id: str | None = None,
        playbook_file: Path | None = None,
        enable_tdd: bool = True,
    ):
        self.playbook_id = playbook_id
        self.playbook_file = playbook_file
        self.enable_tdd = enable_tdd

        # Lazy-loaded services
        self._knowledge_service = None
        self._playbook_manager = None
        self._playbook_data = None

        # Load playbook from file if specified
        if playbook_file and playbook_file.exists():
            self._load_playbook_file(playbook_file)

    def _load_playbook_file(self, path: Path):
        """Load playbook from JSON file."""
        try:
            with open(path) as f:
                self._playbook_data = json.load(f)
            logger.info(f"Loaded playbook from {path}")
        except Exception as e:
            logger.error(f"Failed to load playbook: {e}")

    def _get_knowledge_service(self):
        """Lazy-load the knowledge service."""
        if self._knowledge_service is None:
            try:
                from src.retrieval import InstitutionalKnowledgeService
                self._knowledge_service = InstitutionalKnowledgeService(
                    playbook_manager=self._get_playbook_manager(),
                    default_playbook_id=self.playbook_id,
                )
            except ImportError as e:
                logger.warning(f"Knowledge service not available: {e}")
        return self._knowledge_service

    def _get_playbook_manager(self):
        """Lazy-load the playbook manager."""
        if self._playbook_manager is None:
            try:
                from src.playbook.manager import PlaybookManager
                self._playbook_manager = PlaybookManager()
            except ImportError as e:
                logger.warning(f"Playbook manager not available: {e}")
        return self._playbook_manager

    def get_tool_definitions(self) -> list[dict]:
        """Get MCP tool definitions."""
        tools = [
            {
                "name": "get_guidance",
                "description": (
                    "Get institutional knowledge guidance for a coding task. "
                    "Returns patterns with verdicts: APPLY (safe to use), "
                    "ASK_FIRST (needs clarification), or SKIP (don't use). "
                    "Use this before writing code to learn team patterns."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What you're trying to do (e.g., 'handle database timeout')",
                        },
                        "team_id": {
                            "type": "string",
                            "description": "Your team ID for locality matching",
                        },
                        "tech_stack": {
                            "type": "object",
                            "description": "Tech stack info (e.g., {'python': '3.11', 'framework': 'fastapi'})",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Current project identifier",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Domain filter (e.g., 'tdd', 'ml', 'architecture')",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "learn",
                "description": (
                    "Add knowledge to the institutional playbook. "
                    "Use this to capture patterns, decisions, or lessons learned."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The knowledge content to add",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["decision", "pattern", "snippet", "troubleshooting", "domain"],
                            "description": "Type of knowledge",
                            "default": "pattern",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization",
                        },
                        "team_id": {
                            "type": "string",
                            "description": "Team that owns this knowledge",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score (0.0-1.0)",
                            "default": 0.7,
                        },
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "query",
                "description": (
                    "Simple semantic search for patterns. "
                    "Use get_guidance for context-aware retrieval with verdicts."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results",
                            "default": 5,
                        },
                        "section": {
                            "type": "string",
                            "enum": ["strategies_and_hard_rules", "code_snippets", "troubleshooting", "domain_knowledge"],
                            "description": "Filter by section",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "feedback",
                "description": "Mark a pattern as helpful or harmful to improve future retrieval.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "bullet_id": {
                            "type": "string",
                            "description": "ID of the pattern (e.g., 'ctx-00042')",
                        },
                        "feedback": {
                            "type": "string",
                            "enum": ["helpful", "harmful"],
                            "description": "Was the pattern helpful or harmful?",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional context about why",
                        },
                    },
                    "required": ["bullet_id", "feedback"],
                },
            },
            {
                "name": "get_playbook_info",
                "description": "Get information about the current playbook.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

        # Add TDD tools if enabled
        if self.enable_tdd:
            tools.append({
                "name": "build_feature",
                "description": (
                    "Build a feature using Test-Driven Development. "
                    "Provide a Gherkin feature description and ACE will: "
                    "1) Write failing tests, 2) Write implementation, "
                    "3) Refactor, 4) Learn patterns."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "Gherkin feature description",
                        },
                        "project_path": {
                            "type": "string",
                            "description": "Path to the project root",
                        },
                        "src_dir": {
                            "type": "string",
                            "description": "Source directory (default: src/)",
                        },
                        "test_dir": {
                            "type": "string",
                            "description": "Test directory (default: tests/)",
                        },
                    },
                    "required": ["feature", "project_path"],
                },
            })

        return tools

    def call_tool(self, name: str, arguments: dict) -> Any:
        """
        Call a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        handlers = {
            "get_guidance": self._handle_get_guidance,
            "learn": self._handle_learn,
            "query": self._handle_query,
            "feedback": self._handle_feedback,
            "get_playbook_info": self._handle_get_playbook_info,
            "build_feature": self._handle_build_feature,
        }

        handler = handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")

        return handler(arguments)

    def _handle_get_guidance(self, args: dict) -> dict:
        """Handle get_guidance tool call."""
        from src.retrieval import RetrievalContext

        service = self._get_knowledge_service()
        if service is None:
            return {"error": "Knowledge service not available"}

        # Build context from args
        context = RetrievalContext(
            team_id=args.get("team_id"),
            project_id=args.get("project_id"),
            tech_stack=args.get("tech_stack", {}),
            domain=args.get("domain"),
        )

        # Get guidance
        response = service.get_guidance(
            query=args["query"],
            context=context,
            top_k=args.get("top_k", 10),
        )

        # Format response
        return {
            "apply": [
                {
                    "content": rb.bullet.content,
                    "id": rb.bullet.id,
                    "score": rb.combined_score,
                    "reasoning": rb.reasoning,
                }
                for rb in response.apply
            ],
            "ask_first": [
                {
                    "content": rb.bullet.content,
                    "id": rb.bullet.id,
                    "score": rb.combined_score,
                    "gaps": [g.description for g in rb.context_gaps],
                    "reasoning": rb.reasoning,
                }
                for rb in response.ask_first
            ],
            "questions": response.questions,
            "total_candidates": response.total_candidates,
            "retrieval_time_ms": response.retrieval_time_ms,
        }

    def _handle_learn(self, args: dict) -> dict:
        """Handle learn tool call."""
        manager = self._get_playbook_manager()
        if manager is None:
            return {"error": "Playbook manager not available"}

        try:
            from src.storage.schemas import BulletCreate

            # Map type to section
            section_map = {
                "decision": "strategies_and_hard_rules",
                "pattern": "strategies_and_hard_rules",
                "snippet": "code_snippets",
                "troubleshooting": "troubleshooting",
                "domain": "domain_knowledge",
            }

            bullet_data = BulletCreate(
                content=args["content"],
                section=section_map.get(args.get("type", "pattern"), "domain_knowledge"),
                tags=args.get("tags", []),
                created_by_type="human",
                created_by_id=args.get("team_id"),
                confidence_score=args.get("confidence", 0.7),
            )

            playbook_id = self.playbook_id or "default_playbook"
            bullet = manager.add_bullet(playbook_id, bullet_data)

            return {
                "success": True,
                "bullet_id": bullet.id,
                "playbook_id": playbook_id,
                "message": "Knowledge added successfully",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_query(self, args: dict) -> dict:
        """Handle query tool call."""
        service = self._get_knowledge_service()
        if service is None:
            # Fallback to file-based playbook
            if self._playbook_data:
                return self._query_file_playbook(args)
            return {"error": "No knowledge source available"}

        # Use simple retrieval without CGR³ reasoning
        from src.retrieval import RetrievalContext

        response = service.get_guidance(
            query=args["query"],
            context=RetrievalContext(),  # Empty context = no filtering
            top_k=args.get("top_k", 5),
        )

        # Return all results without verdict filtering
        all_results = response.apply + response.ask_first
        return {
            "results": [
                {
                    "content": rb.bullet.content,
                    "id": rb.bullet.id,
                    "score": rb.semantic_score,
                    "section": rb.bullet.section,
                    "tags": rb.bullet.tags,
                }
                for rb in all_results
            ],
            "count": len(all_results),
        }

    def _query_file_playbook(self, args: dict) -> dict:
        """Query the file-based playbook (simple keyword match)."""
        if not self._playbook_data:
            return {"results": [], "count": 0}

        query_lower = args["query"].lower()
        results = []

        sections = self._playbook_data.get("sections", {})
        for section_name, bullets in sections.items():
            for bullet in bullets:
                content = bullet.get("content", "")
                if query_lower in content.lower():
                    results.append({
                        "content": content,
                        "id": bullet.get("id", "unknown"),
                        "section": section_name,
                        "tags": bullet.get("tags", []),
                    })

        # Limit results
        top_k = args.get("top_k", 5)
        return {
            "results": results[:top_k],
            "count": len(results),
        }

    def _handle_feedback(self, args: dict) -> dict:
        """Handle feedback tool call."""
        manager = self._get_playbook_manager()
        if manager is None:
            return {"error": "Playbook manager not available"}

        try:
            bullet_id = args["bullet_id"]
            feedback = args["feedback"]

            # Find playbook containing this bullet
            playbook_id = None
            for pb_id, playbook in manager._playbooks.items():
                for bullets in playbook.sections.values():
                    for bullet in bullets:
                        if bullet.id == bullet_id:
                            playbook_id = pb_id
                            break
                    if playbook_id:
                        break
                if playbook_id:
                    break

            if not playbook_id:
                return {"success": False, "error": f"Bullet {bullet_id} not found"}

            # Update feedback
            manager.update_bullet_feedback(playbook_id, bullet_id, feedback)

            return {
                "success": True,
                "message": f"Marked {bullet_id} as {feedback}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_playbook_info(self, _args: dict) -> dict:
        """Handle get_playbook_info tool call."""
        if self._playbook_data:
            # File-based playbook
            sections = self._playbook_data.get("sections", {})
            return {
                "source": "file",
                "playbook_id": str(self.playbook_file),
                "sections": {
                    name: len(bullets)
                    for name, bullets in sections.items()
                },
                "total_bullets": sum(len(b) for b in sections.values()),
            }

        manager = self._get_playbook_manager()
        if manager is None:
            return {"error": "No playbook available"}

        playbook_id = self.playbook_id or "default_playbook"
        playbook = manager.get_playbook(playbook_id)

        if playbook is None:
            return {"error": f"Playbook {playbook_id} not found"}

        return {
            "source": "database",
            "playbook_id": playbook_id,
            "version": playbook.version,
            "domain": playbook.metadata.domain,
            "sections": {
                name: len(bullets)
                for name, bullets in playbook.sections.items()
            },
            "total_bullets": playbook.metadata.total_bullets,
        }

    def _handle_build_feature(self, args: dict) -> dict:
        """Handle build_feature tool call (TDD)."""
        if not self.enable_tdd:
            return {"error": "TDD tools not enabled"}

        try:
            from pathlib import Path

            from src.agents.autonomous_tdd_agent import AutonomousTDDAgent  # noqa: F401

            project_path = Path(args["project_path"])
            _src_dir = project_path / args.get("src_dir", "src")
            _test_dir = project_path / args.get("test_dir", "tests")

            # This is a simplified version - full implementation would
            # set up the TDD agent properly
            return {
                "status": "not_implemented",
                "message": "TDD integration requires additional setup. Use 'ace build-feature' CLI instead.",
                "feature": args["feature"][:100] + "...",
            }
        except Exception as e:
            return {"error": str(e)}
