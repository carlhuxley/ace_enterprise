def reverse_string(s):
    return s[::-1]

def is_palindrome(s):
    return reverse_string(s) == s

def count_vowels(s):
    vowels = {'a', 'e', 'i', 'o', 'u'}
    return sum(1 for c in s if c in vowels)