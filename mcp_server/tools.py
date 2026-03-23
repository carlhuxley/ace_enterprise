"""
ACE MCP Tools - Tool definitions and handlers.

Defines the tools exposed by the ACE MCP server and implements
their execution logic.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType

logger = logging.getLogger("ace-mcp.tools")


class ACETools:
    """
    Tool definitions and handlers for ACE MCP server.

    Primary tools (CGR³ focused):
        - get_guidance: Context-aware knowledge retrieval
        - learn: Add knowledge to playbook
        - query: Semantic search (uses local embeddings)
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
        self._embedding_service = None
        self._playbook_embeddings = None  # Cached embeddings for file-mode

        # Audit client for tracking MCP tool usage
        self._audit = LocalAuditClient()

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
                    "Use this before writing code to learn team patterns. "
                    "Only returns patterns above the confidence threshold that match your context."
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
                            "description": "Current project identifier. Filters to patterns applicable to this project.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Domain filter (e.g., 'tdd', 'ml', 'architecture'). Filters to patterns applicable to this domain.",
                        },
                        "min_confidence": {
                            "type": "number",
                            "description": "Minimum confidence threshold (0.0-1.0). Default 0.5 filters out unvalidated patterns.",
                            "default": 0.5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "learn",
                "description": (
                    "Add knowledge to the institutional playbook. "
                    "Use this to capture patterns, decisions, or lessons learned. "
                    "New patterns start with low confidence and are surfaced in retrieval "
                    "after validation via feedback."
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
                            "description": "Initial confidence score (0.0-1.0). New patterns should start low (0.3) and build via feedback.",
                            "default": 0.3,
                        },
                        "domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Applicable domains (e.g., ['healthcare', 'python-tdd']). If empty, applies to all domains.",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Project this pattern applies to. If empty, applies to all projects.",
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
            {
                "name": "list_providers",
                "description": (
                    "List available LLM providers and their configuration. "
                    "Returns which providers are configured and available for use."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_models": {
                            "type": "boolean",
                            "description": "Include default model for each provider",
                            "default": True,
                        },
                        "check_availability": {
                            "type": "boolean",
                            "description": "Check if providers are actually reachable (slower)",
                            "default": False,
                        },
                    },
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
                        "model": {
                            "type": "string",
                            "description": "LLM model to use (must be open-source). Examples: qwen/qwen3-coder:free, meta-llama/llama-3.3-70b-instruct:free",
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
            "list_providers": self._handle_list_providers,
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

        # Get guidance with confidence gating and context filtering
        response = service.get_guidance(
            query=args["query"],
            context=context,
            top_k=args.get("top_k", 10),
            min_confidence=args.get("min_confidence", 0.5),
            domain=args.get("domain"),
            project_id=args.get("project_id"),
        )

        # Emit audit event
        self._audit.emit_simple(
            event_type=AuditEventType.RETRIEVAL_QUERY,
            actor_id="mcp-client",
            actor_type="agent",
            payload={
                "query": args["query"],
                "top_k": args.get("top_k", 10),
                "min_confidence": args.get("min_confidence", 0.5),
                "domain": args.get("domain"),
                "results_apply": len(response.apply),
                "results_ask_first": len(response.ask_first),
                "retrieval_time_ms": response.retrieval_time_ms,
            },
            playbook_id=self.playbook_id,
            project_id=args.get("project_id"),
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

            knowledge_type = args.get("type", "pattern")

            # Build project_ids list if project_id provided
            project_ids = None
            if args.get("project_id"):
                project_ids = [args["project_id"]]

            bullet_data = BulletCreate(
                content=args["content"],
                section=section_map.get(knowledge_type, "domain_knowledge"),
                tags=args.get("tags", []),
                created_by_type="human",
                created_by_id=args.get("team_id"),
                team_id=args.get("team_id"),
                # Contextual retrieval fields
                confidence_score=args.get("confidence", 0.3),  # Low initial confidence
                applicable_domains=args.get("domains"),
                project_ids=project_ids,
            )

            playbook_id = self.playbook_id or "default_playbook"
            bullet = manager.add_bullet(playbook_id, bullet_data)

            # Emit audit event
            self._audit.emit_simple(
                event_type=AuditEventType.KNOWLEDGE_ADDED,
                actor_id="mcp-client",
                actor_type="human",
                payload={
                    "bullet_id": bullet.id,
                    "content_length": len(args["content"]),
                    "type": knowledge_type,
                    "tags": args.get("tags", []),
                    "team_id": args.get("team_id"),
                },
                playbook_id=playbook_id,
            )

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
        # Use file-based playbook if available (fast, no embedding needed)
        if self._playbook_data:
            result = self._query_file_playbook(args)
            # Emit audit event for file-based query
            self._audit.emit_simple(
                event_type=AuditEventType.RETRIEVAL_QUERY,
                actor_id="mcp-client",
                actor_type="agent",
                payload={
                    "query": args["query"],
                    "top_k": args.get("top_k", 5),
                    "results_count": result.get("count", 0),
                    "source": "file",
                },
                playbook_id=str(self.playbook_file) if self.playbook_file else None,
            )
            return result

        # Fall back to knowledge service (requires embeddings)
        service = self._get_knowledge_service()
        if service is None:
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

        # Emit audit event
        self._audit.emit_simple(
            event_type=AuditEventType.RETRIEVAL_QUERY,
            actor_id="mcp-client",
            actor_type="agent",
            payload={
                "query": args["query"],
                "top_k": args.get("top_k", 5),
                "results_count": len(all_results),
                "source": "knowledge_service",
            },
            playbook_id=self.playbook_id,
        )

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

            # Emit audit event
            self._audit.emit_simple(
                event_type=AuditEventType.PATTERN_FEEDBACK,
                actor_id="mcp-client",
                actor_type="human",
                payload={
                    "bullet_id": bullet_id,
                    "feedback": feedback,
                    "context": args.get("context"),
                },
                playbook_id=playbook_id,
            )

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

            from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
            from src.agents.test_review_agent import TestReviewAgent
            from src.config.settings import settings
            from src.ensemble.learner import EnsembleLearner

            # Parse paths
            project_path = Path(args["project_path"]).resolve()
            src_dir = project_path / args.get("src_dir", "src")
            test_dir = project_path / args.get("test_dir", "tests")

            # Ensure directories exist
            src_dir.mkdir(parents=True, exist_ok=True)
            test_dir.mkdir(parents=True, exist_ok=True)

            # Get model configuration - use provided model or fall back to settings
            if args.get("model"):
                # Model specified - assume openrouter for model paths like "qwen/qwen3-coder:free"
                model = args["model"]
                if "/" in model:
                    provider = "openrouter"
                else:
                    provider = settings.default_llm_provider
            else:
                # Use default from settings
                provider = settings.default_llm_provider
                if provider == "openai":
                    model = settings.openai_default_model
                elif provider == "anthropic":
                    model = settings.anthropic_default_model
                elif provider == "openrouter":
                    model = settings.openrouter_default_model
                elif provider == "deepseek":
                    model = settings.deepseek_default_model
                elif provider == "togetherai":
                    model = settings.togetherai_default_model
                else:
                    model = settings.ollama_default_model

            # Create ensemble learner with configured model
            # Use a dummy playbook_id for file mode - learning will be skipped
            playbook_id = self.playbook_id or "mcp_tdd_playbook"

            # Check if we're in file mode (no database)
            file_mode = self.playbook_file is not None and self.playbook_id is None

            ensemble = EnsembleLearner(
                models=[(provider, model)],
                playbook_id=playbook_id,
                enable_deliberation=False,  # Single model, no deliberation needed
            )

            # In file mode, replace the playbook manager with a no-op to avoid DB errors
            if file_mode:
                ensemble.playbook_manager = None

            # Create test reviewer
            test_reviewer = TestReviewAgent(use_llm_analysis=False)

            # Instantiate TDD agent
            tdd_agent = AutonomousTDDAgent(
                ensemble_learner=ensemble,
                test_reviewer=test_reviewer,
                project_root=project_path,
                test_dir=test_dir,
                src_dir=src_dir,
                max_iterations=args.get("max_iterations", 10),
                review_threshold=args.get("review_threshold", 0.7),
            )

            # Handle Gherkin directory if provided
            gherkin_dir = None
            if args.get("gherkin_dir"):
                gherkin_dir = Path(args["gherkin_dir"])

            # Build the feature
            result = tdd_agent.build_feature(
                requirement=args["feature"],
                gherkin_dir=gherkin_dir,
                project_root=project_path,
                source_dir=src_dir,
                test_dir=test_dir,
            )

            # Emit audit event
            self._audit.emit_simple(
                event_type=AuditEventType.CYCLE_COMPLETED,
                actor_id="mcp-client",
                actor_type="agent",
                payload={
                    "feature": args["feature"][:200],
                    "cycles_executed": result.cycles_executed,
                    "all_tests_passed": result.all_tests_passed,
                    "bullets_learned": result.playbook_bullets_added,
                    "total_time_seconds": result.total_time_seconds,
                },
                playbook_id=playbook_id,
                project_id=str(project_path),
            )

            # Return serializable result
            return {
                "success": True,
                "requirement": result.requirement,
                "test_files": [str(f) for f in result.test_files],
                "implementation_files": [str(f) for f in result.implementation_files],
                "cycles_executed": result.cycles_executed,
                "all_tests_passed": result.all_tests_passed,
                "playbook_bullets_added": result.playbook_bullets_added,
                "total_time_seconds": result.total_time_seconds,
            }

        except Exception as e:
            logger.exception(f"build_feature failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_list_providers(self, args: dict) -> dict:
        """Handle list_providers tool call."""
        from src.config.settings import settings
        from src.utils.llm_client import LLMClient

        include_models = args.get("include_models", True)
        check_availability = args.get("check_availability", False)

        # Define all supported providers and their config
        providers_config = {
            "ollama": {
                "type": "local",
                "description": "Local LLM inference via Ollama",
                "configured": True,  # Always available locally
                "default_model": settings.ollama_default_model if include_models else None,
                "base_url": settings.ollama_base_url,
            },
            "openai": {
                "type": "api",
                "description": "OpenAI API (GPT models)",
                "configured": bool(settings.openai_api_key),
                "default_model": settings.openai_default_model if include_models else None,
            },
            "anthropic": {
                "type": "api",
                "description": "Anthropic API (Claude models)",
                "configured": bool(settings.anthropic_api_key),
                "default_model": settings.anthropic_default_model if include_models else None,
            },
            "deepseek": {
                "type": "api",
                "description": "DeepSeek API (MIT licensed models)",
                "configured": bool(settings.deepseek_api_key),
                "default_model": settings.deepseek_default_model if include_models else None,
            },
            "togetherai": {
                "type": "api",
                "description": "Together AI (open-source model hosting)",
                "configured": bool(settings.togetherai_api_key),
                "default_model": settings.togetherai_default_model if include_models else None,
            },
            "openrouter": {
                "type": "api",
                "description": "OpenRouter (unified API for many models, includes free tiers)",
                "configured": bool(settings.openrouter_api_key),
                "default_model": settings.openrouter_default_model if include_models else None,
            },
        }

        # Check actual availability if requested
        if check_availability:
            for provider_name, config in providers_config.items():
                if config["configured"]:
                    try:
                        client = LLMClient(provider=provider_name)
                        config["available"] = client.check_availability()
                    except Exception as e:
                        config["available"] = False
                        config["error"] = str(e)
                else:
                    config["available"] = False

        # Get current default provider
        default_provider = settings.default_llm_provider

        return {
            "default_provider": default_provider,
            "providers": providers_config,
            "configured_count": sum(1 for p in providers_config.values() if p["configured"]),
            "total_count": len(providers_config),
        }
