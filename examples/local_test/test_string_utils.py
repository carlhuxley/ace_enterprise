
import pytest

def test_reverse_string():
    from string_utils import reverse_string
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""
    assert reverse_string("a") == "a"

def test_is_palindrome():
    from string_utils import is_palindrome
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False
    assert is_palindrome("") is True
    assert is_palindrome("A") is True

def test_count_vowels():
    from string_utils import count_vowels
    assert count_vowels("hello") == 2
    assert count_vowels("AEIOU") == 5
    assert count_vowels("xyz") == 0
    assert count_vowels("") == 0
