"""Tests for API-key auth on the audit collector and query API (ace_enterprise-3ig).

Both services are deployed standalone with host-published ports
(services/ace-audit/docker-compose.yml) and handle real audit data, unlike
src/main.py which has no sensitive routes wired in yet.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.audit.api import create_api_app
from src.audit.collector import create_collector_app
from src.audit.schemas import AuditResult

_VALID_KEY = "test-secret-key"


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.query.return_value = AuditResult(events=[], total_count=0, has_more=False)
    store.get_stats.return_value = {"total_events": 0}
    store.verify_full_chain.return_value = (True, None)
    return store


@pytest.fixture
def api_client(mock_store, monkeypatch):
    monkeypatch.setenv("AUDIT_API_KEY", _VALID_KEY)
    return TestClient(create_api_app(mock_store))


@pytest.fixture
def collector_client(mock_store, monkeypatch):
    monkeypatch.setenv("AUDIT_API_KEY", _VALID_KEY)
    return TestClient(create_collector_app(mock_store))


def _auth_headers(key=_VALID_KEY):
    return {"X-API-Key": key}


# ---------------------------------------------------------------------------
# Query API (src/audit/api.py) — read side
# ---------------------------------------------------------------------------

class TestQueryApiAuth:
    @pytest.mark.parametrize("path", ["/events", "/events/some-id", "/stats", "/verify"])
    def test_rejects_missing_key(self, api_client, path):
        resp = api_client.get(path)
        assert resp.status_code == 401

    @pytest.mark.parametrize("path", ["/events", "/events/some-id", "/stats", "/verify"])
    def test_rejects_wrong_key(self, api_client, path):
        resp = api_client.get(path, headers=_auth_headers("wrong-key"))
        assert resp.status_code == 401

    def test_accepts_valid_key(self, api_client):
        resp = api_client.get("/events", headers=_auth_headers())
        assert resp.status_code == 200

    def test_health_does_not_require_key(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200

    def test_fails_closed_when_server_has_no_key_configured(self, mock_store, monkeypatch):
        monkeypatch.delenv("AUDIT_API_KEY", raising=False)
        client = TestClient(create_api_app(mock_store))
        # Even a "correct-looking" key can't work if the server has none configured.
        resp = client.get("/events", headers=_auth_headers("anything"))
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Collector (src/audit/collector.py) — write side
# ---------------------------------------------------------------------------

_EVENT_PAYLOAD = {
    "event_id": "11111111-1111-1111-1111-111111111111",
    "event_type": "agent_started",
    "actor_type": "agent",
    "actor_id": "test-agent",
}


class TestCollectorAuth:
    def test_rejects_missing_key(self, collector_client):
        resp = collector_client.post("/events", json=_EVENT_PAYLOAD)
        assert resp.status_code == 401

    def test_rejects_wrong_key(self, collector_client):
        resp = collector_client.post("/events", json=_EVENT_PAYLOAD, headers=_auth_headers("wrong-key"))
        assert resp.status_code == 401

    def test_accepts_valid_key(self, collector_client, mock_store):
        mock_store.append.return_value = MagicMock(event_id=_EVENT_PAYLOAD["event_id"])
        resp = collector_client.post("/events", json=_EVENT_PAYLOAD, headers=_auth_headers())
        assert resp.status_code == 202

    def test_health_does_not_require_key(self, collector_client):
        resp = collector_client.get("/health")
        assert resp.status_code == 200

    def test_fails_closed_when_server_has_no_key_configured(self, mock_store, monkeypatch):
        monkeypatch.delenv("AUDIT_API_KEY", raising=False)
        client = TestClient(create_collector_app(mock_store))
        resp = client.post("/events", json=_EVENT_PAYLOAD, headers=_auth_headers("anything"))
        assert resp.status_code == 503

    def test_unauthenticated_request_never_reaches_the_store(self, collector_client, mock_store):
        """A rejected request must not append a forged event to the audit log."""
        collector_client.post("/events", json=_EVENT_PAYLOAD)
        mock_store.append.assert_not_called()
