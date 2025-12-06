"""
Tests for OAuth Client

These existing tests capture the behavior we want to preserve.
"""

import pytest
from oauth import OAuthClient


class TestOAuthClient:
    """Test suite for OAuth client."""

    def test_create_oauth_client(self):
        """Test OAuth client can be created with credentials."""
        client = OAuthClient(
            client_id="test_client_id",
            client_secret="test_secret",
            auth_url="https://auth.example.com/oauth"
        )

        assert client.client_id == "test_client_id"
        assert client.client_secret == "test_secret"
        assert client.auth_url == "https://auth.example.com/oauth"

    def test_generate_authorization_url_with_required_params(self):
        """Test generating authorization URL with required parameters."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        url = client.generate_authorization_url(
            redirect_uri="https://myapp.com/callback",
            scope="read write"
        )

        assert url.startswith("https://auth.example.com/oauth?")
        assert "client_id=app_123" in url
        assert "redirect_uri=https%3A%2F%2Fmyapp.com%2Fcallback" in url
        assert "scope=read+write" in url
        assert "response_type=code" in url

    def test_generate_authorization_url_with_state(self):
        """Test generating authorization URL with CSRF state parameter."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        url = client.generate_authorization_url(
            redirect_uri="https://myapp.com/callback",
            scope="read",
            state="random_csrf_token"
        )

        assert "state=random_csrf_token" in url

    def test_exchange_code_for_token(self):
        """Test exchanging authorization code for access token."""
        client = OAuthClient(
            client_id="app_123",
            client_secret="secret",
            auth_url="https://auth.example.com/oauth"
        )

        token_response = client.exchange_code_for_token(
            authorization_code="auth_code_xyz",
            redirect_uri="https://myapp.com/callback"
        )

        assert token_response["access_token"] is not None
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] > 0
