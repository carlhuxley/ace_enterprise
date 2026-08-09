"""Tests for the Settings CORS safety check (ace_enterprise-3ig)."""
import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_wildcard_origin_with_credentials_rejected():
    with pytest.raises(ValidationError, match="cors_allow_credentials"):
        Settings(cors_origins=["*"], cors_allow_credentials=True)


def test_wildcard_origin_without_credentials_allowed():
    s = Settings(cors_origins=["*"], cors_allow_credentials=False)
    assert s.cors_origins == ["*"]


def test_explicit_origins_with_credentials_allowed():
    s = Settings(cors_origins=["https://app.example.com"], cors_allow_credentials=True)
    assert s.cors_allow_credentials is True


def test_mixed_wildcard_and_explicit_origins_rejected():
    with pytest.raises(ValidationError, match="cors_allow_credentials"):
        Settings(cors_origins=["https://app.example.com", "*"], cors_allow_credentials=True)


def test_default_settings_are_valid():
    """The shipped defaults must not trip the check they enforce."""
    Settings()
