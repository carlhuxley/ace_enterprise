"""
Legacy OAuth Client Implementation

This is an existing codebase that we want to refactor or migrate to another language.
"""

from urllib.parse import urlencode
from typing import Optional


class OAuthClient:
    """OAuth 2.0 client for authorization code flow."""

    def __init__(self, client_id: str, client_secret: str, auth_url: str):
        """
        Initialize OAuth client.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            auth_url: Authorization server URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url

    def generate_authorization_url(
        self,
        redirect_uri: str,
        scope: str,
        state: Optional[str] = None
    ) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: Callback URL for your application
            scope: Requested permissions
            state: CSRF protection token

        Returns:
            Authorization URL for user to visit
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "response_type": "code"
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(
        self,
        authorization_code: str,
        redirect_uri: str
    ) -> dict:
        """
        Exchange authorization code for access token.

        Args:
            authorization_code: Code received from authorization
            redirect_uri: Same redirect URI used in authorization

        Returns:
            Token response with access_token, token_type, expires_in
        """
        # Simplified: In reality would make HTTP request
        return {
            "access_token": "mock_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
