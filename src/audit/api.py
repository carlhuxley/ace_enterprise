"""
Audit query API service.

This is the read-only API for querying audit events.
Used by compliance officers, administrators, and debugging tools.

This service runs separately from the collector and provides
query access to the audit log without write capabilities.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from src.audit.schemas import (
    AuditEventType,
    AuditQuery,
    AuditResult,
)
from src.audit.store import AuditStore

logger = logging.getLogger(__name__)


def create_api_app(audit_store: AuditStore) -> FastAPI:
    """
    Create the audit API FastAPI application.

    Args:
        audit_store: The audit store instance for querying events

    Returns:
        FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Log startup/shutdown."""
        logger.info("Audit API started")
        yield
        logger.info("Audit API stopped")

    app = FastAPI(
        title="ACE Audit API",
        description="Read-only audit event query API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_methods=["GET"],  # Read-only
        allow_headers=["*"],
    )

    @app.get(
        "/events",
        response_model=AuditResult,
        summary="Query audit events",
        description="Search and retrieve audit events with filtering and pagination.",
    )
    async def query_events(
        start_time: datetime | None = Query(None, description="Filter events after this time"),
        end_time: datetime | None = Query(None, description="Filter events before this time"),
        event_types: str | None = Query(None, description="Comma-separated event types"),
        actor_type: str | None = Query(None, description="Filter by actor type"),
        actor_id: str | None = Query(None, description="Filter by actor ID"),
        session_id: str | None = Query(None, description="Filter by session ID"),
        playbook_id: str | None = Query(None, description="Filter by playbook ID"),
        project_id: str | None = Query(None, description="Filter by project ID"),
        limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        order_by: str = Query("timestamp", description="Field to order by"),
        order_desc: bool = Query(True, description="Order descending"),
    ) -> AuditResult:
        """Query audit events with filters."""
        # Parse event types
        parsed_event_types = None
        if event_types:
            try:
                parsed_event_types = [
                    AuditEventType(t.strip())
                    for t in event_types.split(",")
                ]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {e}",
                )

        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=parsed_event_types,
            actor_type=actor_type,
            actor_id=actor_id,
            session_id=session_id,
            playbook_id=playbook_id,
            project_id=project_id,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc,
        )

        return audit_store.query(query)

    @app.get(
        "/events/{event_id}",
        summary="Get a specific event",
        description="Retrieve a single audit event by its ID.",
    )
    async def get_event(event_id: str):
        """Get a specific audit event by ID."""
        query = AuditQuery(limit=1, offset=0)
        # We need to filter by event_id - extend query for this
        result = audit_store.query(query)

        # Find the specific event (inefficient, but simple for now)
        # TODO: Add event_id filter to AuditQuery
        for event in result.events:
            if event.event_id == event_id:
                return event

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found",
        )

    @app.get(
        "/stats",
        summary="Get audit statistics",
        description="Get summary statistics about the audit log.",
    )
    async def get_stats() -> dict:
        """Get audit log statistics."""
        return audit_store.get_stats()

    @app.get(
        "/verify",
        summary="Verify hash chain integrity",
        description="Verify the entire audit log hash chain.",
    )
    async def verify_chain() -> dict:
        """Verify the audit log hash chain integrity."""
        is_valid, invalid_id = audit_store.verify_full_chain()
        return {
            "chain_valid": is_valid,
            "first_invalid_event": invalid_id,
            "verified_at": datetime.utcnow().isoformat(),
        }

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "service": "audit-api"}

    # No POST/PUT/DELETE endpoints - this API is read-only

    return app


def create_app() -> FastAPI:
    """
    Create the API app with default configuration.

    Reads database URL from AUDIT_DATABASE_URL environment variable.
    """
    database_url = os.getenv(
        "AUDIT_DATABASE_URL",
        "postgresql://audit:audit@localhost:5433/ace_audit"
    )
    store = AuditStore(database_url)
    return create_api_app(store)


# Application instance for uvicorn
app = create_app()
