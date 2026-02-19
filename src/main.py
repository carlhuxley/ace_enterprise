"""
ACE Enterprise - Main Application Entry Point
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from src.config.settings import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting ACE Enterprise...")
    logger.info(f"Environment: {settings.env}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"LLM Provider: {settings.default_llm_provider}")
    if settings.default_llm_provider == "ollama":
        logger.info(f"Ollama Model: {settings.ollama_default_model}")
        logger.info(f"Ollama URL: {settings.ollama_base_url}")

    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Load embedding model
    # TODO: Initialize playbook manager

    logger.info("ACE Enterprise started successfully")

    yield

    # Shutdown
    logger.info("Shutting down ACE Enterprise...")
    # TODO: Close database connections
    # TODO: Close Redis connections
    # TODO: Cleanup resources
    logger.info("ACE Enterprise shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
if settings.enable_prometheus_metrics:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring and load balancers.
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.env,
            "llm_provider": settings.default_llm_provider,
        }
    )


# Root endpoint
@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "description": settings.api_description,
        "docs": "/docs" if settings.is_development else "Documentation disabled in production",
    }


# TODO: Register API routes
# from src.api.routes import tasks, playbooks, checkpoints, logs
# app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
# app.include_router(playbooks.router, prefix="/api/v1/playbooks", tags=["Playbooks"])
# app.include_router(checkpoints.router, prefix="/api/v1/checkpoints", tags=["Checkpoints"])
# app.include_router(logs.router, prefix="/api/v1/logs", tags=["Logs"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        workers=1 if settings.is_development else settings.api_workers,
        log_level=settings.log_level.lower(),
    )
