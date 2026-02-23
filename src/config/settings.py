"""
ACE Enterprise Configuration Settings
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Environment
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_title: str = "ACE Enterprise API"
    api_version: str = "0.1.0"
    api_description: str = "Agentic Context Engineering for Production LLM Applications"

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://ace_user:ace_password@localhost:5432/ace_enterprise"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = 50

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # LLM Providers
    # Ollama (local - open-source models)
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "qwen3-coder:30b"

    # DeepSeek API (MIT license)
    deepseek_api_key: str | None = None
    deepseek_default_model: str = "deepseek-chat"

    # Together AI (open-source models)
    togetherai_api_key: str | None = None
    togetherai_default_model: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"

    # OpenRouter (access to many models, including free tiers)
    openrouter_api_key: str | None = None
    openrouter_default_model: str = "qwen/qwen3-coder:free"

    # OpenAI
    openai_api_key: str | None = None
    openai_default_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_default_model: str = "claude-sonnet-4-20250514"

    default_llm_provider: Literal["ollama", "vllm", "deepseek", "togetherai", "openrouter", "openai", "anthropic"] = "ollama"

    # Embedding Configuration
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"
    embedding_batch_size: int = 32

    # ACE Core Configuration - Retrieval
    retrieval_top_k: int = 20
    retrieval_similarity_threshold: float = 0.7
    deduplication_similarity_threshold: float = 0.85

    # Cross-Model Learning
    retrieval_mode: Literal["model_specific", "cross_model_hybrid"] = "model_specific"
    cross_model_weight: float = 0.5  # Weight for bullets from other models (0.0 to 1.0)

    # ACE Core Configuration - Reflection
    max_refinement_rounds: int = 3
    enable_iterative_reflection: bool = True

    # ACE Core Configuration - Curation
    token_budget_per_section: int = 10000
    enable_redundancy_checking: bool = True

    # Performance & Reliability
    checkpoint_frequency: int = 50
    regression_threshold: float = 0.05
    enable_auto_rollback: bool = True
    regression_window_recent: int = 20
    regression_window_baseline: int = 50

    # Adaptation Mode
    adaptation_mode: Literal["offline", "online", "hybrid"] = "hybrid"
    max_epochs: int = 5
    batch_size: int = 1

    # Monitoring
    enable_prometheus_metrics: bool = True
    prometheus_port: int = 9090
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Storage & Retention
    experiment_log_retention_days: int = 365
    checkpoint_retention_count: int = 50
    enable_log_compression: bool = True

    # Rate Limiting
    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 20

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    cors_allow_credentials: bool = True

    # Webhooks
    webhook_secret: str = "your-webhook-secret"
    webhook_retry_attempts: int = 3
    webhook_timeout_seconds: int = 10

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: PostgresDsn) -> str:
        """Convert PostgresDsn to string"""
        return str(v)

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: RedisDsn) -> str:
        """Convert RedisDsn to string"""
        return str(v)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Using lru_cache ensures settings are loaded only once.
    """
    return Settings()


# Convenience export
settings = get_settings()
