"""
Test suite for password verifier.

This module tests password validation with various security requirements:
- Minimum length
- Character type requirements (uppercase, lowercase, digits, special chars)
- Common password detection
- Strength scoring
"""
import pytest


def test_empty_password_is_invalid():
    """Empty passwords should be rejected."""
    from password_verifier import is_valid_password

    assert is_valid_password("") is False


def test_short_password_is_invalid():
    """Passwords shorter than 8 characters should be rejected."""
    from password_verifier import is_valid_password

    assert is_valid_password("abc") is False
    assert is_valid_password("1234567") is False
    assert is_valid_password("Ab1!") is False


def test_minimum_length_password_is_valid():
    """Passwords with exactly 8 characters meeting requirements should be valid."""
    from password_verifier import is_valid_password

    assert is_valid_password("Abcd123!") is True


def test_password_requires_uppercase():
    """Password must contain at least one uppercase letter."""
    from password_verifier import is_valid_password

    assert is_valid_password("abcdefgh123!") is False  # No uppercase
    assert is_valid_password("Abcdefgh123!") is True   # Has uppercase


def test_password_requires_lowercase():
    """Password must contain at least one lowercase letter."""
    from password_verifier import is_valid_password

    assert is_valid_password("ABCDEFGH123!") is False  # No lowercase
    assert is_valid_password("ABCDEFGh123!") is True   # Has lowercase


def test_password_requires_digit():
    """Password must contain at least one digit."""
    from password_verifier import is_valid_password

    assert is_valid_password("Abcdefgh!") is False    # No digit
    assert is_valid_password("Abcdefgh1!") is True    # Has digit


def test_password_requires_special_character():
    """Password must contain at least one special character."""
    from password_verifier import is_valid_password

    assert is_valid_password("Abcdefgh123") is False   # No special char
    assert is_valid_password("Abcdefgh123!") is True   # Has special char


def test_accepts_various_special_characters():
    """Different special characters should be accepted."""
    from password_verifier import is_valid_password

    assert is_valid_password("Abcdefg1!") is True
    assert is_valid_password("Abcdefg1@") is True
    assert is_valid_password("Abcdefg1#") is True
    assert is_valid_password("Abcdefg1$") is True
    assert is_valid_password("Abcdefg1%") is True
    assert is_valid_password("Abcdefg1^") is True
    assert is_valid_password("Abcdefg1&") is True
    assert is_valid_password("Abcdefg1*") is True


def test_common_passwords_are_rejected():
    """Common/weak passwords should be rejected even if they meet requirements."""
    from password_verifier import is_valid_password

    # These meet technical requirements but are too common
    assert is_valid_password("Password123!") is False
    assert is_valid_password("Qwerty123!") is False
    assert is_valid_password("Admin123!") is False


def test_password_strength_weak():
    """Calculate strength score for weak passwords."""
    from password_verifier import get_password_strength

    # Just meets minimum requirements
    strength = get_password_strength("Abcd123!")
    assert strength == "weak"


def test_password_strength_medium():
    """Calculate strength score for medium passwords."""
    from password_verifier import get_password_strength

    # Longer with good variety
    strength = get_password_strength("MyP@ssw0rd2024")
    assert strength == "medium"


def test_password_strength_strong():
    """Calculate strength score for strong passwords."""
    from password_verifier import get_password_strength

    # Long with excellent variety
    strength = get_password_strength("C0mpl3x!P@ssw0rd#2024")
    assert strength == "strong"


def test_get_password_requirements():
    """Should return which requirements a password fails."""
    from password_verifier import get_password_requirements

    result = get_password_requirements("abc")

    assert result["length"] is False
    assert result["uppercase"] is False
    assert result["lowercase"] is True
    assert result["digit"] is False
    assert result["special"] is False


def test_get_password_requirements_all_met():
    """Should show all requirements met for valid password."""
    from password_verifier import get_password_requirements

    result = get_password_requirements("Abcd123!")

    assert result["length"] is True
    assert result["uppercase"] is True
    assert result["lowercase"] is True
    assert result["digit"] is True
    assert result["special"] is True


def test_validate_with_custom_min_length():
    """Should allow custom minimum length."""
    from password_verifier import is_valid_password

    # Default is 8, let's require 12
    assert is_valid_password("Abcd123!", min_length=12) is False
    assert is_valid_password("Abcd123!xYz4", min_length=12) is True


def test_whitespace_in_password_is_invalid():
    """Passwords with whitespace should be rejected."""
    from password_verifier import is_valid_password

    assert is_valid_password("Abcd 123!") is False
    assert is_valid_password("Abcd\t123!") is False
    assert is_valid_password("Abcd\n123!") is False


def test_very_long_password_is_valid():
    """Very long passwords should be accepted."""
    from password_verifier import is_valid_password

    long_password = "MyV3ry!L0ng@Passw0rd#With$Many%Characters^2024"
    assert is_valid_password(long_password) is True


def test_password_must_not_contain_username():
    """Password should not contain the username."""
    from password_verifier import is_valid_password_with_username

    assert is_valid_password_with_username("Alice", "MyP@ssw0rd123") is True
    assert is_valid_password_with_username("alice", "MyP@ssw0rd123") is True
    assert is_valid_password_with_username("Alice", "Alice123!") is False  # Contains username
    assert is_valid_password_with_username("Alice", "alice123!") is False  # Case insensitive
    assert is_valid_password_with_username("Bob", "BobTheBuilder1!") is False


def test_password_history_check():
    """Password should not match any in password history."""
    from password_verifier import is_password_in_history

    history = ["OldP@ss1", "OldP@ss2", "OldP@ss3"]

    assert is_password_in_history("NewP@ss123", history) is False
    assert is_password_in_history("OldP@ss1", history) is True
    assert is_password_in_history("OldP@ss2", history) is True
