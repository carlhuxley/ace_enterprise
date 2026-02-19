"""
Audit event collector service.

This is the HTTP endpoint that receives audit events from ACE agents.
It validates events and appends them to the audit store.

The collector only accepts POST requests to /events.
No other operations are exposed to event producers.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from src.audit.schemas import AuditEvent
from src.audit.store import AuditStore

logger = logging.getLogger(__name__)


def create_collector_app(audit_store: AuditStore) -> FastAPI:
    """
    Create the audit collector FastAPI application.

    Args:
        audit_store: The audit store instance for persisting events

    Returns:
        FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Initialize audit store on startup."""
        audit_store.create_tables()
        logger.info("Audit collector started")
        yield
        logger.info("Audit collector stopped")

    app = FastAPI(
        title="ACE Audit Collector",
        description="Write-only audit event collector",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS - allow ACE services to send events
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_methods=["POST"],  # Only POST allowed
        allow_headers=["*"],
    )

    @app.post(
        "/events",
        status_code=status.HTTP_202_ACCEPTED,
        summary="Submit an audit event",
        description="Append an audit event to the immutable audit log. This is the only write operation available.",
    )
    async def receive_event(event: AuditEvent) -> dict:
        """
        Receive and store an audit event.

        This endpoint only accepts events - it does not return the stored
        event or any other data. The response is minimal to prevent
        information leakage to event producers.
        """
        try:
            stored_event = audit_store.append(event)
            return {
                "status": "accepted",
                "event_id": stored_event.event_id,
            }
        except Exception as e:
            logger.error(f"Failed to store audit event: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store audit event",
            )

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "service": "audit-collector"}

    # Explicitly disable any read/query endpoints on the collector
    # The collector is write-only by design

    return app


def create_app() -> FastAPI:
    """
    Create the collector app with default configuration.

    Reads database URL from AUDIT_DATABASE_URL environment variable.
    """
    database_url = os.getenv(
        "AUDIT_DATABASE_URL",
        "postgresql://audit:audit@localhost:5433/ace_audit"
    )
    store = AuditStore(database_url)
    return create_collector_app(store)


# Application instance for uvicorn
app = create_app()
