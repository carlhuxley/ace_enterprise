"""
Domain-Aware Distillation Router for Prompt-Level Distillation.

Routes tasks to domain-specific distillation playbooks, generating
optimized system prompts for weak models based on accumulated
strong model knowledge.

Usage:
    router = DistillationRouter(playbook_manager, model_weights)

    # Get PLD context for a task
    result = router.route("Implement OAuth2 refresh token flow")

    if result.use_teacher:
        # Unknown domain - use strong model
        response = teacher_model.generate(task)
    else:
        # Use weak model with distillation context
        response = weak_model.generate(task, system=result.system_prompt)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.playbook.clustering import (
    BulletClusterer,
    ClusteringResult,
    RepresentativeStrategy,
    build_distillation_playbook,
)
from src.playbook.manager import PlaybookManager
from src.storage.schemas import Bullet, Playbook
from src.utils.embedding import get_embedding_service

logger = logging.getLogger(__name__)


class RoutingVerdict(str, Enum):
    """Verdict for routing decision."""

    USE_DISTILLATION = "use_distillation"  # Use weak model + PLD context
    USE_TEACHER = "use_teacher"  # Fall back to strong model
    ASK_FIRST = "ask_first"  # Low confidence, confirm with user


class LicenseCategory(str, Enum):
    """License category for provenance tracking."""

    OPEN_SOURCE = "open_source"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class Supplier(str, Enum):
    """Model supplier/owner for provenance matching.

    Same supplier can mix proprietary teachers with open students
    (e.g., Google: Gemini → Gemma, OpenAI: GPT-4 → future open model).
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    META = "meta"
    ALIBABA = "alibaba"  # Qwen
    MISTRAL = "mistral"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    MICROSOFT = "microsoft"  # Phi
    OTHER = "other"
    UNKNOWN = "unknown"


# Supplier detection patterns (model name / provider → supplier)
SUPPLIER_PATTERNS: dict[Supplier, frozenset[str]] = {
    Supplier.OPENAI: frozenset({
        "openai", "gpt", "gpt-3.5", "gpt-4", "gpt-4o", "gpt-4-turbo",
        "o1", "o1-mini", "o1-preview", "davinci", "curie", "babbage", "ada",
    }),
    Supplier.ANTHROPIC: frozenset({
        "anthropic", "claude", "claude-2", "claude-3",
        "claude-opus", "claude-sonnet", "claude-haiku",
        "opus", "sonnet", "haiku",
    }),
    Supplier.GOOGLE: frozenset({
        "google", "gemini", "gemini-pro", "gemini-ultra", "gemini-flash",
        "gemma", "gemma2", "palm", "palm-2", "bard",
    }),
    Supplier.META: frozenset({
        "meta", "llama", "llama2", "llama3", "llama-3", "codellama",
    }),
    Supplier.ALIBABA: frozenset({
        "alibaba", "qwen", "qwen2", "qwen2.5", "qwen-", "tongyi",
    }),
    Supplier.MISTRAL: frozenset({
        "mistral", "mixtral", "mistral-", "pixtral",
    }),
    Supplier.COHERE: frozenset({
        "cohere", "command", "command-r",
    }),
    Supplier.DEEPSEEK: frozenset({
        "deepseek", "deepseek-v2", "deepseek-coder",
    }),
    Supplier.MICROSOFT: frozenset({
        "microsoft", "phi", "phi-2", "phi-3", "phi-4",
    }),
}

# Open source licenses
OPEN_SOURCE_LICENSES = frozenset({
    "apache-2.0", "apache", "apache2", "mit",
    "gpl", "gpl-2.0", "gpl-3.0", "agpl", "agpl-3.0",
    "lgpl", "lgpl-2.1", "lgpl-3.0",
    "bsd", "bsd-2-clause", "bsd-3-clause",
    "cc-by", "cc-by-4.0", "cc-by-sa", "cc-by-sa-4.0",
    "cc0", "public-domain", "mpl", "mpl-2.0", "unlicense",
})

# Models that are open source (regardless of supplier)
OPEN_SOURCE_MODELS = frozenset({
    "gemma", "gemma2",  # Google open
    "llama", "llama2", "llama3", "codellama",  # Meta open
    "qwen", "qwen2", "qwen2.5",  # Alibaba open
    "mistral", "mixtral",  # Mistral open
    "phi", "phi-2", "phi-3", "phi-4",  # Microsoft open
    "deepseek", "deepseek-coder",  # DeepSeek open
    "falcon", "starcoder", "starcoder2", "yi",
})

# Models that are proprietary
PROPRIETARY_MODELS = frozenset({
    "gpt-3.5", "gpt-4", "gpt-4o", "gpt-4-turbo", "o1", "o1-mini",  # OpenAI
    "claude", "claude-2", "claude-3", "opus", "sonnet", "haiku",  # Anthropic
    "gemini", "gemini-pro", "gemini-ultra", "gemini-flash", "palm", "bard",  # Google
    "command", "command-r",  # Cohere
})


def detect_supplier(model_name: str | None, provider: str | None = None) -> Supplier:
    """Detect the supplier/owner of a model.

    Checks model name first (more specific), then provider.
    Note: "ollama" is a runtime, not a supplier - it hosts various models.
    """
    # Check model name first (more specific signal)
    if model_name:
        model_lower = model_name.lower().strip()
        for supplier, patterns in SUPPLIER_PATTERNS.items():
            for pattern in patterns:
                if pattern in model_lower or model_lower.startswith(pattern):
                    return supplier

    # Check provider (but skip generic runtimes like ollama)
    if provider:
        provider_lower = provider.lower().strip()
        # Ollama is a runtime that hosts various suppliers' models
        if provider_lower in {"ollama", "lmstudio", "localai", "vllm", "text-generation-inference"}:
            return Supplier.UNKNOWN
        for supplier, patterns in SUPPLIER_PATTERNS.items():
            for pattern in patterns:
                if pattern in provider_lower or provider_lower.startswith(pattern):
                    return supplier

    return Supplier.UNKNOWN


def classify_license(
    model_name: str | None = None,
    provider: str | None = None,
    license_type: str | None = None,
) -> LicenseCategory:
    """Classify the license category of a model."""
    # Explicit license type takes precedence
    if license_type:
        normalized = license_type.lower().strip().replace(" ", "-").replace("_", "-")
        if normalized in OPEN_SOURCE_LICENSES:
            return LicenseCategory.OPEN_SOURCE
        if normalized in {"proprietary", "commercial", "closed"}:
            return LicenseCategory.PROPRIETARY

    # Check model name against known lists
    if model_name:
        model_lower = model_name.lower().strip()
        for open_model in OPEN_SOURCE_MODELS:
            if open_model in model_lower:
                return LicenseCategory.OPEN_SOURCE
        for prop_model in PROPRIETARY_MODELS:
            if prop_model in model_lower:
                return LicenseCategory.PROPRIETARY

    # Provider hints
    if provider:
        provider_lower = provider.lower()
        if provider_lower == "ollama":
            return LicenseCategory.OPEN_SOURCE  # Ollama serves open models

    return LicenseCategory.UNKNOWN


@dataclass
class Provenance:
    """Model/bullet provenance for ownership-aware matching."""

    supplier: Supplier
    license_category: LicenseCategory

    @classmethod
    def from_model(
        cls,
        model_name: str | None = None,
        provider: str | None = None,
        license_type: str | None = None,
    ) -> "Provenance":
        """Create provenance from model details."""
        return cls(
            supplier=detect_supplier(model_name, provider),
            license_category=classify_license(model_name, provider, license_type),
        )

    @classmethod
    def from_bullet(cls, bullet: Bullet) -> "Provenance":
        """Create provenance from bullet metadata."""
        return cls.from_model(
            model_name=bullet.created_by_model,
            provider=bullet.model_provider,
            license_type=bullet.license_type,
        )

    def can_teach(
        self,
        student: "Provenance",
        allow_cross_supplier_proprietary: bool = False,
    ) -> bool:
        """
        Check if this provenance (teacher/bullet) can teach a student.

        Rules:
        1. Same supplier → always allowed (owner can mix their models)
        2. Cross-supplier + open source teacher → allowed
        3. Cross-supplier + proprietary teacher → configurable

        Args:
            student: Student model provenance
            allow_cross_supplier_proprietary: Allow proprietary teacher
                to teach cross-supplier students (ToS risk)

        Returns:
            True if teaching is allowed
        """
        # Same supplier: always OK (Google Gemini → Google Gemma, etc.)
        if self.supplier == student.supplier and self.supplier != Supplier.UNKNOWN:
            return True

        # Unknown supplier: be permissive
        if self.supplier == Supplier.UNKNOWN or student.supplier == Supplier.UNKNOWN:
            return True

        # Cross-supplier: check license
        if self.license_category == LicenseCategory.OPEN_SOURCE:
            # Open source teacher can teach anyone
            return True

        if self.license_category == LicenseCategory.PROPRIETARY:
            # Proprietary teacher teaching cross-supplier: configurable
            return allow_cross_supplier_proprietary

        # Unknown license: be permissive
        return True


def filter_bullets_by_provenance(
    bullets: list[Bullet],
    student_provenance: Provenance,
    allow_cross_supplier_proprietary: bool = False,
) -> list[Bullet]:
    """
    Filter bullets to those that can teach the student model.

    Args:
        bullets: Bullets to filter
        student_provenance: Provenance of the student model
        allow_cross_supplier_proprietary: Allow cross-supplier proprietary

    Returns:
        Bullets with compatible provenance
    """
    return [
        bullet for bullet in bullets
        if Provenance.from_bullet(bullet).can_teach(
            student_provenance,
            allow_cross_supplier_proprietary,
        )
    ]


@dataclass
class DomainMatch:
    """Result of domain classification."""

    domain: str
    confidence: float
    playbook_ids: list[str]
    bullet_count: int


@dataclass
class RoutingResult:
    """Result of distillation routing."""

    verdict: RoutingVerdict
    domain: str | None
    confidence: float
    system_prompt: str | None
    distillation_bullets: list[Bullet]
    cluster_count: int
    outlier_count: int

    # Provenance info
    student_provenance: Provenance | None = None
    bullets_filtered_by_provenance: int = 0  # How many bullets were filtered out

    # Teacher fallback info (when use_teacher=True)
    recommended_teacher_supplier: Supplier | None = None

    # For debugging/auditing
    domain_matches: list[DomainMatch] = field(default_factory=list)
    use_teacher: bool = False

    def __post_init__(self):
        self.use_teacher = self.verdict == RoutingVerdict.USE_TEACHER


@dataclass
class RouterConfig:
    """Configuration for DistillationRouter."""

    # Domain classification thresholds
    high_confidence_threshold: float = 0.7
    low_confidence_threshold: float = 0.4

    # Clustering parameters
    eps: float = 0.3
    min_samples: int = 2
    representative_strategy: RepresentativeStrategy = RepresentativeStrategy.HIGHEST_HELPFUL

    # Model filtering
    min_model_weight: float = 1.0

    # Provenance matching
    # If False (default), proprietary bullets from one supplier (e.g., OpenAI)
    # cannot teach students from another supplier (e.g., Anthropic).
    # Same-supplier is always allowed (Google Gemini → Google Gemma is OK).
    allow_cross_supplier_proprietary: bool = False

    # Prompt generation
    max_bullets_in_prompt: int = 20
    include_section_headers: bool = True


class DomainRegistry:
    """
    Registry of available domains and their playbook signatures.

    Maintains domain centroids for fast classification and tracks
    playbook coverage per domain.
    """

    def __init__(self, playbook_manager: PlaybookManager):
        self._manager = playbook_manager
        self._domain_centroids: dict[str, np.ndarray] = {}
        self._domain_playbooks: dict[str, list[str]] = {}
        self._domain_bullet_counts: dict[str, int] = {}

    def refresh(self) -> None:
        """Rebuild domain registry from current playbooks."""
        self._domain_centroids.clear()
        self._domain_playbooks.clear()
        self._domain_bullet_counts.clear()

        # Group playbooks by domain
        for playbook in self._manager._playbooks.values():
            domain = playbook.metadata.domain
            if not domain:
                continue

            if domain not in self._domain_playbooks:
                self._domain_playbooks[domain] = []
            self._domain_playbooks[domain].append(playbook.playbook_id)

            # Collect embeddings for centroid calculation
            bullets = self._manager.get_all_bullets(playbook.playbook_id)
            embeddings = [b.embedding for b in bullets if b.embedding is not None]

            if embeddings:
                # Update or create domain centroid
                domain_embeddings = np.array(embeddings)
                if domain in self._domain_centroids:
                    # Weighted average with existing centroid
                    existing = self._domain_centroids[domain]
                    existing_count = self._domain_bullet_counts.get(domain, 0)
                    new_count = len(embeddings)
                    total = existing_count + new_count
                    self._domain_centroids[domain] = (
                        existing * existing_count + domain_embeddings.mean(axis=0) * new_count
                    ) / total
                else:
                    self._domain_centroids[domain] = domain_embeddings.mean(axis=0)

                self._domain_bullet_counts[domain] = (
                    self._domain_bullet_counts.get(domain, 0) + len(embeddings)
                )

        logger.info(
            f"Domain registry refreshed: {len(self._domain_centroids)} domains, "
            f"{sum(self._domain_bullet_counts.values())} total bullets"
        )

    def get_domains(self) -> list[str]:
        """Get list of all registered domains."""
        return list(self._domain_centroids.keys())

    def get_domain_playbooks(self, domain: str) -> list[str]:
        """Get playbook IDs for a domain."""
        return self._domain_playbooks.get(domain, [])

    def classify(self, query_embedding: np.ndarray) -> list[DomainMatch]:
        """
        Classify a query to domains by similarity to domain centroids.

        Args:
            query_embedding: Embedding vector for the query

        Returns:
            List of DomainMatch sorted by confidence (descending)
        """
        if not self._domain_centroids:
            return []

        matches = []
        query = query_embedding.reshape(1, -1)

        for domain, centroid in self._domain_centroids.items():
            similarity = cosine_similarity(query, centroid.reshape(1, -1))[0][0]
            matches.append(
                DomainMatch(
                    domain=domain,
                    confidence=float(similarity),
                    playbook_ids=self._domain_playbooks.get(domain, []),
                    bullet_count=self._domain_bullet_counts.get(domain, 0),
                )
            )

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches


class DistillationRouter:
    """
    Routes tasks to domain-specific distillation playbooks.

    Main entry point for PLD system prompt generation.
    """

    def __init__(
        self,
        playbook_manager: PlaybookManager,
        model_weights: dict[str, float] | None = None,
        config: RouterConfig | None = None,
    ):
        self._manager = playbook_manager
        self._model_weights = model_weights or {}
        self._config = config or RouterConfig()

        # Initialize domain registry
        self._registry = DomainRegistry(playbook_manager)
        self._registry.refresh()

        # Initialize clusterer
        self._clusterer = BulletClusterer(
            eps=self._config.eps,
            min_samples=self._config.min_samples,
            representative_strategy=self._config.representative_strategy,
        )

        # Cache for domain distillation sets
        self._distillation_cache: dict[str, tuple[list[Bullet], ClusteringResult]] = {}
        self._cache_playbook_versions: dict[str, dict[str, str]] = {}

    def route(
        self,
        query: str,
        student_model: str | None = None,
        student_provider: str | None = None,
    ) -> RoutingResult:
        """
        Route a task query to appropriate distillation context.

        Args:
            query: The task description or query
            student_model: Name of the student model (for provenance matching)
            student_provider: Provider of the student model (e.g., "ollama", "openai")

        Returns:
            RoutingResult with verdict, context, and system prompt
        """
        # Determine student provenance for filtering
        student_provenance = Provenance.from_model(student_model, student_provider)

        # Get query embedding
        try:
            embedding_service = get_embedding_service()
            query_embedding = np.array(embedding_service.embed_text(query))
        except Exception as e:
            logger.warning(f"Failed to embed query, falling back to teacher: {e}")
            return self._teacher_fallback(
                "embedding_failed",
                student_provenance=student_provenance,
            )

        # Classify to domain
        domain_matches = self._registry.classify(query_embedding)

        if not domain_matches:
            logger.info("No domains available, using teacher model")
            return self._teacher_fallback(
                "no_domains",
                student_provenance=student_provenance,
            )

        best_match = domain_matches[0]

        # Determine verdict based on confidence
        if best_match.confidence >= self._config.high_confidence_threshold:
            verdict = RoutingVerdict.USE_DISTILLATION
        elif best_match.confidence >= self._config.low_confidence_threshold:
            verdict = RoutingVerdict.ASK_FIRST
        else:
            verdict = RoutingVerdict.USE_TEACHER

        if verdict == RoutingVerdict.USE_TEACHER:
            logger.info(
                f"Low domain confidence ({best_match.confidence:.2f}), using teacher model"
            )
            return self._teacher_fallback(
                "low_confidence",
                domain_matches,
                student_provenance=student_provenance,
            )

        # Get distillation set for domain
        distillation_bullets, clustering_result = self._get_domain_distillation(
            best_match.domain
        )

        # Filter by provenance (teacher → student compatibility)
        original_count = len(distillation_bullets)
        distillation_bullets = filter_bullets_by_provenance(
            distillation_bullets,
            student_provenance,
            self._config.allow_cross_supplier_proprietary,
        )
        filtered_count = original_count - len(distillation_bullets)

        if filtered_count > 0:
            logger.info(
                f"Filtered {filtered_count}/{original_count} bullets by provenance "
                f"(student: {student_provenance.supplier.value}/{student_provenance.license_category.value})"
            )

        if not distillation_bullets:
            logger.info(f"No compatible bullets for domain '{best_match.domain}'")
            return self._teacher_fallback(
                "no_compatible_bullets",
                domain_matches,
                student_provenance=student_provenance,
            )

        # Generate system prompt
        system_prompt = self._generate_system_prompt(
            domain=best_match.domain,
            bullets=distillation_bullets,
            query=query,
        )

        logger.info(
            f"Routed to domain '{best_match.domain}' (confidence={best_match.confidence:.2f}, "
            f"bullets={len(distillation_bullets)}, clusters={clustering_result.n_clusters})"
        )

        return RoutingResult(
            verdict=verdict,
            domain=best_match.domain,
            confidence=best_match.confidence,
            system_prompt=system_prompt,
            distillation_bullets=distillation_bullets,
            cluster_count=clustering_result.n_clusters,
            outlier_count=clustering_result.n_outliers,
            student_provenance=student_provenance,
            bullets_filtered_by_provenance=filtered_count,
            domain_matches=domain_matches,
        )

    def route_to_domain(
        self,
        domain: str,
        query: str | None = None,
        student_model: str | None = None,
        student_provider: str | None = None,
    ) -> RoutingResult:
        """
        Route directly to a specific domain (skip classification).

        Useful when domain is already known.

        Args:
            domain: Target domain name
            query: Optional query for prompt customization
            student_model: Name of the student model (for provenance matching)
            student_provider: Provider of the student model

        Returns:
            RoutingResult for the specified domain
        """
        student_provenance = Provenance.from_model(student_model, student_provider)

        if domain not in self._registry.get_domains():
            return self._teacher_fallback(
                f"unknown_domain:{domain}",
                student_provenance=student_provenance,
            )

        distillation_bullets, clustering_result = self._get_domain_distillation(domain)

        # Filter by provenance
        original_count = len(distillation_bullets)
        distillation_bullets = filter_bullets_by_provenance(
            distillation_bullets,
            student_provenance,
            self._config.allow_cross_supplier_proprietary,
        )
        filtered_count = original_count - len(distillation_bullets)

        if not distillation_bullets:
            return self._teacher_fallback(
                f"no_compatible_bullets:{domain}",
                student_provenance=student_provenance,
            )

        system_prompt = self._generate_system_prompt(
            domain=domain,
            bullets=distillation_bullets,
            query=query,
        )

        return RoutingResult(
            verdict=RoutingVerdict.USE_DISTILLATION,
            domain=domain,
            confidence=1.0,  # Direct routing = full confidence
            system_prompt=system_prompt,
            distillation_bullets=distillation_bullets,
            cluster_count=clustering_result.n_clusters,
            outlier_count=clustering_result.n_outliers,
            student_provenance=student_provenance,
            bullets_filtered_by_provenance=filtered_count,
        )

    def get_all_domains(self) -> list[str]:
        """Get list of all available domains."""
        return self._registry.get_domains()

    def refresh(self) -> None:
        """Refresh domain registry and clear caches."""
        self._registry.refresh()
        self._distillation_cache.clear()
        self._cache_playbook_versions.clear()
        logger.info("Distillation router refreshed")

    def _get_domain_distillation(
        self, domain: str
    ) -> tuple[list[Bullet], ClusteringResult]:
        """Get or compute distillation set for a domain."""
        # Check if cache is valid
        if domain in self._distillation_cache:
            if self._is_cache_valid(domain):
                return self._distillation_cache[domain]

        # Collect all bullets from domain playbooks
        all_bullets: list[Bullet] = []
        current_versions: dict[str, str] = {}

        for playbook_id in self._registry.get_domain_playbooks(domain):
            playbook = self._manager.get_playbook(playbook_id)
            if playbook:
                bullets = self._manager.get_all_bullets(playbook_id)
                all_bullets.extend(bullets)
                current_versions[playbook_id] = playbook.version

        if not all_bullets:
            empty_result = ClusteringResult(
                clusters=[],
                outliers=[],
                n_clusters=0,
                n_outliers=0,
                eps=self._config.eps,
                min_samples=self._config.min_samples,
            )
            return [], empty_result

        # Build distillation set
        if self._model_weights:
            distillation_bullets, result = build_distillation_playbook(
                bullets=all_bullets,
                model_weights=self._model_weights,
                min_model_weight=self._config.min_model_weight,
                eps=self._config.eps,
                min_samples=self._config.min_samples,
                strategy=self._config.representative_strategy,
            )
        else:
            distillation_bullets, result = build_distillation_playbook(
                bullets=all_bullets,
                eps=self._config.eps,
                min_samples=self._config.min_samples,
                strategy=self._config.representative_strategy,
            )

        # Cache results
        self._distillation_cache[domain] = (distillation_bullets, result)
        self._cache_playbook_versions[domain] = current_versions

        logger.debug(
            f"Built distillation set for domain '{domain}': "
            f"{len(distillation_bullets)} bullets from {result.n_clusters} clusters"
        )

        return distillation_bullets, result

    def _is_cache_valid(self, domain: str) -> bool:
        """Check if cached distillation is still valid."""
        if domain not in self._cache_playbook_versions:
            return False

        cached_versions = self._cache_playbook_versions[domain]

        for playbook_id, cached_version in cached_versions.items():
            playbook = self._manager.get_playbook(playbook_id)
            if not playbook or playbook.version != cached_version:
                return False

        return True

    def _generate_system_prompt(
        self,
        domain: str,
        bullets: list[Bullet],
        query: str | None = None,
    ) -> str:
        """Generate PLD system prompt from distillation bullets."""
        config = self._config

        # Limit bullets if needed
        if len(bullets) > config.max_bullets_in_prompt:
            # If we have a query, prioritize relevant bullets
            if query:
                bullets = self._prioritize_by_relevance(bullets, query)
            bullets = bullets[: config.max_bullets_in_prompt]

        # Group by section
        sections: dict[str, list[Bullet]] = {}
        for bullet in bullets:
            section = bullet.section
            if section not in sections:
                sections[section] = []
            sections[section].append(bullet)

        # Build prompt
        lines = [
            f"# Domain Knowledge: {domain}",
            "",
            "You have access to the following curated knowledge from experienced practitioners.",
            "Apply these patterns and principles when relevant to the task.",
            "",
        ]

        section_names = {
            "strategies_and_hard_rules": "Strategies & Rules",
            "code_snippets": "Code Patterns",
            "troubleshooting": "Troubleshooting",
            "domain_knowledge": "Domain Knowledge",
        }

        for section_key in ["strategies_and_hard_rules", "code_snippets", "troubleshooting", "domain_knowledge"]:
            if section_key not in sections:
                continue

            section_bullets = sections[section_key]
            if not section_bullets:
                continue

            if config.include_section_headers:
                section_name = section_names.get(section_key, section_key)
                lines.append(f"## {section_name}")
                lines.append("")

            for bullet in section_bullets:
                # Add helpful indicator for high-value bullets
                helpful_indicator = ""
                if bullet.helpful_count >= 5:
                    helpful_indicator = " [highly validated]"

                lines.append(f"- {bullet.content}{helpful_indicator}")

            lines.append("")

        return "\n".join(lines)

    def _prioritize_by_relevance(
        self, bullets: list[Bullet], query: str
    ) -> list[Bullet]:
        """Sort bullets by relevance to query."""
        try:
            embedding_service = get_embedding_service()
            query_embedding = np.array(embedding_service.embed_text(query)).reshape(1, -1)
        except Exception:
            return bullets  # Can't prioritize without embedding

        scored_bullets = []
        for bullet in bullets:
            if bullet.embedding:
                bullet_embedding = np.array(bullet.embedding).reshape(1, -1)
                similarity = cosine_similarity(query_embedding, bullet_embedding)[0][0]
            else:
                similarity = 0.0
            scored_bullets.append((bullet, similarity))

        scored_bullets.sort(key=lambda x: x[1], reverse=True)
        return [b for b, _ in scored_bullets]

    def _teacher_fallback(
        self,
        reason: str,
        domain_matches: list[DomainMatch] | None = None,
        student_provenance: Provenance | None = None,
    ) -> RoutingResult:
        """
        Create teacher fallback result.

        Recommends a teacher supplier that matches the student's provenance
        to maintain provenance chain integrity.
        """
        # Recommend teacher supplier based on student provenance
        recommended_teacher = None
        if student_provenance:
            if student_provenance.supplier != Supplier.UNKNOWN:
                # Same supplier teacher preferred (Google student → Google teacher)
                recommended_teacher = student_provenance.supplier
            elif student_provenance.license_category == LicenseCategory.OPEN_SOURCE:
                # Open source student can use any open source teacher
                # No specific supplier recommended
                recommended_teacher = None
            # Proprietary student with unknown supplier: no recommendation

        logger.debug(f"Teacher fallback: {reason}, recommended_teacher={recommended_teacher}")

        return RoutingResult(
            verdict=RoutingVerdict.USE_TEACHER,
            domain=None,
            confidence=0.0,
            system_prompt=None,
            distillation_bullets=[],
            cluster_count=0,
            outlier_count=0,
            student_provenance=student_provenance,
            recommended_teacher_supplier=recommended_teacher,
            domain_matches=domain_matches or [],
        )


def create_router(
    playbook_manager: PlaybookManager,
    model_weights: dict[str, float] | None = None,
    high_confidence_threshold: float = 0.7,
    low_confidence_threshold: float = 0.4,
) -> DistillationRouter:
    """
    Factory function to create a configured DistillationRouter.

    Args:
        playbook_manager: PlaybookManager instance
        model_weights: Optional model strength weights
        high_confidence_threshold: Threshold for auto-routing
        low_confidence_threshold: Threshold below which to use teacher

    Returns:
        Configured DistillationRouter
    """
    config = RouterConfig(
        high_confidence_threshold=high_confidence_threshold,
        low_confidence_threshold=low_confidence_threshold,
    )
    return DistillationRouter(
        playbook_manager=playbook_manager,
        model_weights=model_weights,
        config=config,
    )
