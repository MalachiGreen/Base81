from base81 import ALPHABET_STANDARD, ALPHABET_URL


def test_standard_alphabet_length():
    assert len(ALPHABET_STANDARD) == 81


def test_url_alphabet_length():
    assert len(ALPHABET_URL) == 62


def test_no_header_delimiter():
    assert '^' not in ALPHABET_STANDARD
    assert '^' not in ALPHABET_URL


def test_excluded_ambiguous_chars():
    # Standard excludes I, O, l
    assert 'I' not in ALPHABET_STANDARD
    assert 'O' not in ALPHABET_STANDARD
    assert 'l' not in ALPHABET_STANDARD


def test_url_alphabet_is_alnum():
    assert all(c.isalnum() for c in ALPHABET_URL)


def test_standard_alphabet_contains_specials():
    specials = "!#$%&()*+-./:;=?@_{}[]"
    for ch in specials:
        assert ch in ALPHABET_STANDARD