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


def _slugify(text: str, max_words: int = 6) -> str:
    """Derive a filename-safe module name from free-form requirement text."""
    import re
    words = re.findall(r"[A-Za-z0-9]+", text.lower())[:max_words]
    return "_".join(words) or "feature"


def _pod_file_paths(language: str, name: str, src_dir: Path, test_dir: Path) -> tuple[Path, Path]:
    """Return (test_file, implementation_file) in each language's own convention."""
    if language == "python":
        return test_dir / f"test_{name}.py", src_dir / f"{name}.py"
    if language == "typescript":
        return test_dir / f"{name}.test.ts", src_dir / f"{name}.ts"
    if language == "go":
        return test_dir / f"{name}_test.go", src_dir / f"{name}.go"
    raise ValueError(f"Unsupported language: {language!r}")


def _resolve_model_id(llm_client) -> str:
    """Real model/agent identity for audit actor_id -- see tdd_cycle_runner.py."""
    provider = getattr(llm_client, "provider", None)
    model = getattr(llm_client, "model", "unknown")
    return f"{provider}/{model}" if provider else model


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
        """Lazy-load the playbook manager based on storage configuration."""
        if self._playbook_manager is None:
            try:
                from src.config.settings import settings

                if settings.playbook_storage == "postgres":
                    from src.playbook.postgres_adapter import PostgresPlaybookAdapter
                    self._playbook_manager = PostgresPlaybookAdapter()
                    logger.info("Using PostgreSQL playbook storage")
                else:
                    from src.playbook.manager import PlaybookManager
                    self._playbook_manager = PlaybookManager(
                        storage_path=settings.playbook_storage_path
                    )
                    logger.info(f"Using file-based playbook storage: {settings.playbook_storage_path}")
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
                    "Build a feature from a Gherkin spec using Test-Driven Development, "
                    "in Python, TypeScript, or Go. RED/GREEN/REFACTOR all execute inside "
                    "a rootless, network-isolated Podman container (clean-room sandbox) "
                    "with per-language static security scanning (Bandit / eslint-plugin-security "
                    "/ gosec) -- generated code is never run, and never written to your project, "
                    "until it has passed inside the sandbox."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "Gherkin feature description (inline text). Ignored if feature_file is given.",
                        },
                        "feature_file": {
                            "type": "string",
                            "description": "Path to a .feature file to build from. Takes precedence over 'feature'.",
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python", "typescript", "go"],
                            "default": "python",
                            "description": "Target language. Each runs in its own sandboxed container image.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Module/feature name used for generated file names (e.g. 'user_auth' -> user_auth.py / test_user_auth.py). Derived from the feature text if omitted.",
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
                        "max_cycles": {
                            "type": "integer",
                            "description": "Maximum GREEN retry cycles (default: 5)",
                        },
                        "team_id": {
                            "type": "string",
                            "description": "Team producing this pattern -- stamped onto any Playbook bullets learned from this build, so CGR3's team-locality ranking has real data to score against.",
                        },
                        "model": {
                            "type": "string",
                            "description": "LLM model to use (must be open-source). Examples: qwen/qwen3-coder:free, meta-llama/llama-3.3-70b-instruct:free. Omit to use the local Claude Code session (no API key needed).",
                        },
                        "models": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Two or more '<provider>/<model>' candidates to route between via the AdaptiveBroker, which picks the best one for this language from audit history (falls back to the first with no history). Overrides 'model'. The chosen model and the broker verdict are returned under 'routing'.",
                        },
                    },
                    "required": ["project_path"],
                },
            })
            tools.append({
                "name": "build_feature_ensemble",
                "description": (
                    "Build a Python feature with 2+ candidate models, score each "
                    "implementation blind (the evaluator never sees which model wrote "
                    "which), and commit the winner. Every candidate is generated in its "
                    "own throwaway sandbox; nothing reaches your project until it wins. "
                    "Returns per-candidate scores (attribution revealed post-scoring) and "
                    "a consensus report on how far the models' solutions converged."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "Gherkin feature description (inline text). Ignored if feature_file is given.",
                        },
                        "feature_file": {
                            "type": "string",
                            "description": "Path to a .feature file to build from. Takes precedence over 'feature'.",
                        },
                        "models": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "description": "Two or more '<provider>/<model>' candidates (e.g. 'openrouter/qwen/qwen3-coder:free'). Each produces one candidate implementation.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Module/feature name for generated files (e.g. 'user_auth' -> user_auth.py / test_user_auth.py). Derived from the feature text if omitted.",
                        },
                        "project_path": {"type": "string", "description": "Path to the project root"},
                        "src_dir": {"type": "string", "description": "Source directory (default: src/)"},
                        "test_dir": {"type": "string", "description": "Test directory (default: tests/)"},
                        "max_cycles": {"type": "integer", "description": "Maximum GREEN retry cycles per candidate (default: 5)"},
                        "team_id": {
                            "type": "string",
                            "description": "Team producing this pattern -- stamped onto any Playbook bullets learned from this build.",
                        },
                    },
                    "required": ["project_path", "models"],
                },
            })
            tools.append({
                "name": "build_project",
                "description": (
                    "Decompose a project spec into a set of Python modules with build-order "
                    "dependencies, then build each module in topological order (ModuleArchitect "
                    "-> ModuleTDDBuilder), writing src/<module>.py + tests/test_<module>.py and "
                    "running the whole suite as an assembly check. All generated code runs only "
                    "inside the Podman sandbox. Call with plan_only=true first to review the "
                    "module DAG before building."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spec": {"type": "string", "description": "Project spec (inline free text). Ignored if spec_file is given."},
                        "spec_file": {"type": "string", "description": "Path to a spec file. Takes precedence over 'spec'."},
                        "project_path": {"type": "string", "description": "Path to the target project root"},
                        "src_dir": {"type": "string", "description": "Source directory (default: src/)"},
                        "test_dir": {"type": "string", "description": "Test directory (default: tests/)"},
                        "model": {"type": "string", "description": "LLM model (must be open-source). Omit for the local Claude Code session."},
                        "plan_only": {"type": "boolean", "description": "Return the module plan without building (default: false)"},
                        "resume": {"type": "boolean", "description": "Skip modules whose files already exist (default: false)"},
                        "keep_going": {"type": "boolean", "description": "Don't stop at the first module failure (default: false)"},
                    },
                    "required": ["project_path"],
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
            "build_feature_ensemble": self._handle_build_feature_ensemble,
            "build_project": self._handle_build_project,
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
            from src.playbook.content_safety import (
                NEEDS_REVIEW_TAG,
                ContentRejectedError,
                Verdict,
                screen_bullet_content,
            )
            from src.storage.schemas import BulletCreate

            playbook_id = self.playbook_id or "default_playbook"
            content = args["content"]

            # Content safety (ace_enterprise-z51): `learn` is callable by any
            # MCP client, so its content is untrusted the same way external
            # user input is. Screen before persisting.
            screen = screen_bullet_content(content)
            if screen.verdict == Verdict.REJECT:
                self._audit.emit_simple(
                    event_type=AuditEventType.KNOWLEDGE_ADDED,
                    actor_id="mcp-client",
                    actor_type="human",
                    payload={
                        "rejected": True,
                        "reasons": screen.reasons,
                        "content_length": len(content),
                        "team_id": args.get("team_id"),
                    },
                    playbook_id=playbook_id,
                )
                return {
                    "success": False,
                    "error": f"Content rejected by safety screen: {'; '.join(screen.reasons)}",
                }

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

            tags = list(args.get("tags", []))
            if screen.verdict == Verdict.FLAG and NEEDS_REVIEW_TAG not in tags:
                tags.append(NEEDS_REVIEW_TAG)

            bullet_data = BulletCreate(
                content=content,
                section=section_map.get(knowledge_type, "domain_knowledge"),
                tags=tags,
                created_by_type="human",
                created_by_id=args.get("team_id"),
                team_id=args.get("team_id"),
                # Contextual retrieval fields. Always low initial confidence,
                # NOT caller-controlled -- args.get("confidence", ...) used to
                # let any MCP client hand a new bullet an arbitrary starting
                # confidence, which defeated the "low confidence until
                # promoted by real feedback" mitigation entirely.
                confidence_score=0.3,
                applicable_domains=args.get("domains"),
                project_ids=project_ids,
            )

            bullet = manager.add_bullet(playbook_id, bullet_data)

            # Emit audit event
            self._audit.emit_simple(
                event_type=AuditEventType.KNOWLEDGE_ADDED,
                actor_id="mcp-client",
                actor_type="human",
                payload={
                    "bullet_id": bullet.id,
                    "content_length": len(content),
                    "type": knowledge_type,
                    "tags": tags,
                    "team_id": args.get("team_id"),
                    "flagged_for_review": screen.verdict == Verdict.FLAG,
                },
                playbook_id=playbook_id,
            )

            return {
                "success": True,
                "bullet_id": bullet.id,
                "playbook_id": playbook_id,
                "message": "Knowledge added successfully",
                "flagged_for_review": screen.verdict == Verdict.FLAG,
            }
        except ContentRejectedError as e:
            return {"success": False, "error": str(e)}
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

    _LANGUAGES = ("python", "typescript", "go")

    def _handle_build_feature(self, args: dict) -> dict:
        """Handle build_feature tool call: sandboxed TDD in Python/TypeScript/Go.

        RED/GREEN/REFACTOR run inside PodmanOrchestrator-backed language pods
        (rootless, --network none, --cap-drop=all) via PolyglotTDDRunner —
        generated code is committed to the project only after it passes inside
        the container. No generated code is ever executed, or written to disk,
        directly on the host.
        """
        if not self.enable_tdd:
            return {"error": "TDD tools not enabled"}

        try:
            import time
            from pathlib import Path

            from src.agents.gherkin_feature_bridge import GherkinFeatureBridge
            from src.agents.polyglot_pod_builder import build_pod_kwargs
            from src.agents.polyglot_tdd_runner import PodFactory, PolyglotTDDRunner
            from src.agents.redundancy_checker import RedundancyPreChecker

            language = args.get("language", "python")
            if language not in self._LANGUAGES:
                return {
                    "success": False,
                    "error": f"Unsupported language: {language!r} (expected one of {self._LANGUAGES})",
                }

            project_path = Path(args["project_path"]).resolve()
            src_dir = project_path / args.get("src_dir", "src")
            test_dir = project_path / args.get("test_dir", "tests")
            src_dir.mkdir(parents=True, exist_ok=True)
            test_dir.mkdir(parents=True, exist_ok=True)

            if args.get("feature_file"):
                spec = GherkinFeatureBridge.parse(Path(args["feature_file"]))
                requirement = spec.as_requirement()
            elif args.get("feature"):
                requirement = args["feature"]
            else:
                return {"success": False, "error": "Provide either 'feature' or 'feature_file'"}

            name = args.get("name") or _slugify(requirement)
            test_file, implementation_file = _pod_file_paths(language, name, src_dir, test_dir)

            playbook_id = self.playbook_id or "mcp_tdd_playbook"
            routing = self._route_model(args, task_type=language, playbook_id=playbook_id)
            if routing is not None:
                from src.utils.llm_client import LLMClient
                provider, _, model_name = routing.selected_model.partition("/")
                llm_client = LLMClient(provider=provider, model=model_name)
            else:
                llm_client = self._resolve_llm_client(args)
            pod_kwargs = {
                language: build_pod_kwargs(language, project_path, llm_client, src_dir=src_dir)
            }
            # Same pipeline extensions as ace tdd's build_agent(): audit trail,
            # AST redundancy pre-check. (ContextMap injection happens inside
            # build_pod_kwargs, for the python worker only.)
            runner = PolyglotTDDRunner(
                PodFactory,
                max_cycles=args.get("max_cycles", 5),
                pod_kwargs=pod_kwargs,
                audit_client=self._audit,
                redundancy_checker=RedundancyPreChecker(),
                playbook_id=playbook_id,
                team_id=args.get("team_id"),
                model_id=_resolve_model_id(llm_client),
            )

            start = time.monotonic()
            polyglot_result = runner.run(
                feature_requirement=requirement,
                test_file=test_file,
                implementation_file=implementation_file,
                languages=[language],
            )
            elapsed = time.monotonic() - start

            run_result = polyglot_result.language_results[language]
            all_passed = run_result.green.passed and run_result.refactor.passed

            # No separate audit event here -- PolyglotTDDRunner's
            # TDDCycleRunner already emits one CYCLE_COMPLETED per cycle
            # with the real model_id as actor_id and elapsed_seconds/
            # task_type in the payload (see tdd_cycle_runner.py). A second,
            # differently-shaped event under a fake "mcp-client" actor_id
            # used to be emitted here too -- it double-counted every build
            # in PerformanceAggregator.get_all_agent_metrics() (inflating
            # total_tasks 2x) under keys ("total_time_seconds", "language")
            # the aggregator never reads, so it silently contributed
            # nothing but noise and a phantom "agent".

            return {
                "success": all_passed,
                "sandboxed": True,
                "language": language,
                "requirement": requirement,
                "test_file": str(test_file),
                "implementation_file": str(implementation_file),
                "cycles_to_green": run_result.cycles_to_green,
                "red_error": run_result.red.error,
                "green_passed": run_result.green.passed,
                "green_error": run_result.green.error,
                "refactor_passed": run_result.refactor.passed,
                "refactor_error": run_result.refactor.error,
                "total_time_seconds": elapsed,
                "routing": routing.to_payload() if routing is not None else None,
            }

        except Exception as e:
            logger.exception(f"build_feature failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_build_feature_ensemble(self, args: dict) -> dict:
        """Multi-candidate blind build: N models -> N sandboxed candidates ->
        blind scoring -> winner committed. See EnsembleBuildRunner."""
        if not self.enable_tdd:
            return {"error": "TDD tools not enabled"}

        try:
            from pathlib import Path

            from src.agents.ensemble_build import EnsembleBuildRunner
            from src.agents.gherkin_feature_bridge import GherkinFeatureBridge

            models = args.get("models") or []
            if not isinstance(models, list) or len({str(m) for m in models}) < 2:
                return {"success": False, "error": "provide 2+ distinct 'models'"}

            language = args.get("language", "python")

            project_path = Path(args["project_path"]).resolve()
            src_dir = project_path / args.get("src_dir", "src")
            test_dir = project_path / args.get("test_dir", "tests")

            if args.get("feature_file"):
                requirement = GherkinFeatureBridge.parse(Path(args["feature_file"])).as_requirement()
            elif args.get("feature"):
                requirement = args["feature"]
            else:
                return {"success": False, "error": "Provide either 'feature' or 'feature_file'"}

            name = args.get("name") or _slugify(requirement)
            playbook_id = self.playbook_id or "mcp_tdd_playbook"

            runner = EnsembleBuildRunner(
                project_path=project_path,
                language=language,
                src_dir=src_dir,
                test_dir=test_dir,
                playbook_id=playbook_id,
                audit_client=self._audit,
                team_id=args.get("team_id"),
                max_cycles=args.get("max_cycles", 5),
            )
            result = runner.run(requirement, [str(m) for m in models], name)

            payload = result.to_dict()
            payload["success"] = result.committed
            payload["sandboxed"] = True
            return payload

        except Exception as e:
            logger.exception(f"build_feature_ensemble failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_build_project(self, args: dict) -> dict:
        """Decompose a spec into modules and build them in dependency order.

        See src/cli/project_builder.py. plan_only returns just the module DAG.
        """
        if not self.enable_tdd:
            return {"error": "TDD tools not enabled"}

        try:
            from pathlib import Path

            from src.cli.project_builder import ProjectBuilder
            from src.contracts.project_architect import ProjectArchitect

            project_path = Path(args["project_path"]).resolve()
            src_dir = project_path / args.get("src_dir", "src")
            test_dir = project_path / args.get("test_dir", "tests")

            if args.get("spec_file"):
                spec = Path(args["spec_file"]).read_text(encoding="utf-8")
            elif args.get("spec"):
                spec = args["spec"]
            else:
                return {"success": False, "error": "Provide either 'spec' or 'spec_file'"}

            llm = self._resolve_llm_client({"model": args.get("model")})
            model_id = _resolve_model_id(llm)

            architect = ProjectArchitect(llm, audit_client=self._audit, model_id=model_id)
            plan_result = architect.plan(spec)
            if not plan_result.success or plan_result.plan is None:
                return {"success": False, "error": f"planning failed: {plan_result.error}"}
            plan = plan_result.plan

            if args.get("plan_only"):
                return {"success": True, "plan_only": True, "plan": plan.to_payload()}

            builder = ProjectBuilder(llm, audit_client=self._audit, model_id=model_id)
            result = builder.build(
                plan, project_path, src_dir, test_dir,
                resume=bool(args.get("resume", False)),
                stop_on_failure=not bool(args.get("keep_going", False)),
            )
            return {
                "success": result.success,
                "sandboxed": True,
                "plan": plan.to_payload(),
                **result.to_payload(),
            }

        except Exception as e:
            logger.exception(f"build_project failed: {e}")
            return {"success": False, "error": str(e)}

    def _route_model(self, args: dict, task_type: str, playbook_id: str):
        """Route this build among args['models'] via the AdaptiveBroker.

        Returns None (caller uses args['model'] / the local Claude session)
        unless 2+ '<provider>/<model>' candidates are given. Emits a
        ROUTING_DECISION audit event so the choice shows up in the trail.
        """
        candidates = args.get("models") or []
        if not isinstance(candidates, list) or len(candidates) < 2:
            return None

        from src.broker.model_router import route_model

        decision = route_model(
            [str(c) for c in candidates],
            task_type=task_type,
            audit_database_url=self._audit.database_url,
        )
        try:
            self._audit.emit_simple(
                event_type=AuditEventType.ROUTING_DECISION,
                actor_id=decision.selected_model,
                payload=decision.to_payload(),
                playbook_id=playbook_id,
            )
        except Exception:  # noqa: BLE001 -- audit is best-effort
            logger.debug("routing-decision audit emit failed", exc_info=True)
        return decision

    def _resolve_llm_client(self, args: dict):
        """Build the LLM client for code generation.

        Defaults to ClaudeCliClient — no API key needed, uses the local Claude
        Code session that's already running this MCP server. An explicit
        'model' arg opts into a provider-backed LLMClient instead (e.g. for
        other MCP-capable coding harnesses without a local Claude CLI).
        """
        model = args.get("model")
        if not model:
            from src.utils.claude_cli_client import ClaudeCliClient
            return ClaudeCliClient()

        from src.utils.llm_client import LLMClient
        provider = "openrouter" if "/" in model else "ollama"
        return LLMClient(provider=provider, model=model)

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
