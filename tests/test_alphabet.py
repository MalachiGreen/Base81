"""Tests for alphabet definitions and character sets."""

import pytest
from base81._alphabet import ALPHABET_STANDARD, ALPHABET_URL, _WS_REMOVE_TABLE


class TestAlphabetStandard:
    def test_length(self):
        assert len(ALPHABET_STANDARD) == 81

    def test_no_header_delimiter(self):
        assert '^' not in ALPHABET_STANDARD

    def test_ambiguous_chars_excluded(self):
        assert 'I' not in ALPHABET_STANDARD
        assert 'O' not in ALPHABET_STANDARD
        assert 'l' not in ALPHABET_STANDARD

    def test_all_chars_unique(self):
        assert len(set(ALPHABET_STANDARD)) == 81

    def test_special_chars_present(self):
        specials = "!#$%&()*+-./:;=?@_{}[]"
        for ch in specials:
            assert ch in ALPHABET_STANDARD


class TestAlphabetUrl:
    def test_length(self):
        assert len(ALPHABET_URL) == 62

    def test_no_header_delimiter(self):
        assert '^' not in ALPHABET_URL

    def test_alphanumeric_only(self):
        for ch in ALPHABET_URL:
            assert ch.isalnum()

    def test_upper_lower_digits(self):
        digits = set("0123456789")
        upper = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        lower = set("abcdefghijklmnopqrstuvwxyz")
        assert set(ALPHABET_URL) == digits | upper | lower


class TestWhitespaceRemoval:
    def test_whitespace_translation_table(self):
        s = " hello\tworld\n\r "
        cleaned = s.translate(_WS_REMOVE_TABLE)
        assert cleaned == "helloworld"

    def test_no_whitespace_preserved(self):
        s = "abc123"
        cleaned = s.translate(_WS_REMOVE_TABLE)
        assert cleaned == "abc123"

    def test_only_whitespace(self):
        s = " \t\n\r "
        cleaned = s.translate(_WS_REMOVE_TABLE)
        assert cleaned == ""


@pytest.mark.parametrize("alphabet", [ALPHABET_STANDARD, ALPHABET_URL])
def test_alphabet_characters_are_printable(alphabet):
    for ch in alphabet:
        assert ch.isprintable()
