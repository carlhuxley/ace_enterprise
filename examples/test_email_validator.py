
import pytest
from email_validator import is_valid_email, get_email_parts, validate_email_domain

class TestBasicEmailValidation:
    def test_empty_email_is_invalid(self):
        assert is_valid_email("") == False

    def test_valid_simple_email(self):
        assert is_valid_email("user@example.com") == True

    def test_email_requires_at_symbol(self):
        assert is_valid_email("userexample.com") == False

    def test_email_requires_domain(self):
        assert is_valid_email("user@") == False

    def test_email_requires_username(self):
        assert is_valid_email("@example.com") == False

class TestEmailFormat:
    def test_email_allows_dots_in_username(self):
        assert is_valid_email("user.name@example.com") == True

    def test_email_allows_plus_in_username(self):
        assert is_valid_email("user+tag@example.com") == True

    def test_email_allows_hyphens_in_domain(self):
        assert is_valid_email("user@my-domain.com") == True

    def test_email_allows_subdomains(self):
        assert is_valid_email("user@mail.example.com") == True

    def test_email_rejects_spaces(self):
        assert is_valid_email("user name@example.com") == False

class TestAdvancedValidation:
    def test_email_requires_valid_tld(self):
        assert is_valid_email("user@example") == False

    def test_email_allows_long_tlds(self):
        assert is_valid_email("user@example.international") == True

    def test_email_rejects_consecutive_dots(self):
        assert is_valid_email("user..name@example.com") == False

    def test_email_rejects_starting_dot(self):
        assert is_valid_email(".user@example.com") == False

    def test_email_rejects_ending_dot(self):
        assert is_valid_email("user.@example.com") == False

class TestEmailParsing:
    def test_get_email_parts_extracts_username(self):
        username, domain = get_email_parts("user@example.com")
        assert username == "user"

    def test_get_email_parts_extracts_domain(self):
        username, domain = get_email_parts("user@example.com")
        assert domain == "example.com"

    def test_get_email_parts_handles_complex_email(self):
        username, domain = get_email_parts("user.name+tag@mail.example.com")
        assert username == "user.name+tag"
        assert domain == "mail.example.com"

class TestDomainValidation:
    def test_validate_domain_checks_format(self):
        assert validate_email_domain("example.com") == True

    def test_validate_domain_rejects_invalid(self):
        assert validate_email_domain("invalid") == False
