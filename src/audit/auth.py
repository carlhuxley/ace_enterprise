"""Shared API-key authentication for the audit services.

The audit collector (write) and audit query API (read) are deployed as
standalone services with host-published ports (services/ace-audit/docker-
compose.yml) — unlike src/main.py, which has no sensitive routes wired in
yet, these two handle real audit data today and are real attack surface
once reachable beyond localhost (ace_enterprise-3ig).

Fails closed: a request without a valid key is rejected, and if the server
itself has no AUDIT_API_KEY configured, every request is rejected too
(503) rather than silently running unauthenticated.
"""
import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    expected = os.environ.get("AUDIT_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUDIT_API_KEY is not configured on the server — refusing all "
            "requests rather than running unauthenticated.",
        )
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
