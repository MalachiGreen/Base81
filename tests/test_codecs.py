"""Tests for codec registry and validation."""

import pytest
from base81._codecs import CODECS, LOOKUPS, get_codec, list_codecs
from base81._exceptions import CodecError


class TestCodecRegistration:
    def test_standard_3_codec(self):
        cfg = get_codec("standard", 3)
        assert cfg is not None
        assert cfg["full_n"] == 3
        assert cfg["full_k"] == 4
        assert cfg["tail_enc"] == {1: 2, 2: 3}
        assert cfg["tail_dec"] == {2: 1, 3: 2}

    def test_standard_7_codec(self):
        cfg = get_codec("standard", 7)
        assert cfg is not None
        assert cfg["full_n"] == 7
        assert cfg["full_k"] == 9
        assert len(cfg["tail_enc"]) == 6  # 1..6 bytes
        assert len(cfg["tail_dec"]) == 6  # matching k values

    def test_url_5_codec(self):
        cfg = get_codec("url", 5)
        assert cfg is not None
        assert cfg["full_n"] == 5
        assert cfg["full_k"] == 7
        assert len(cfg["tail_enc"]) == 4  # 1..4 bytes
        assert len(cfg["tail_dec"]) == 4

    def test_missing_codec(self):
        assert get_codec("standard", 99) is None
        assert get_codec("unknown", 7) is None

    def test_list_codecs(self):
        codecs = list_codecs()
        assert ("standard", 3) in codecs
        assert ("standard", 7) in codecs
        assert ("url", 5) in codecs
        assert len(codecs) == 3


class TestLookups:
    def test_standard_alphabet_mapping(self):
        cfg = LOOKUPS["standard"]
        assert cfg["base"] == 81
        assert len(cfg["to_char"]) == 81
        assert len(cfg["to_idx"]) == 81
        # Check bijection
        for i, ch in enumerate(cfg["to_char"]):
            assert cfg["to_idx"][ch] == i

    def test_url_alphabet_mapping(self):
        cfg = LOOKUPS["url"]
        assert cfg["base"] == 62
        assert len(cfg["to_char"]) == 62
        assert len(cfg["to_idx"]) == 62

    def test_lookup_immutable(self):
        with pytest.raises(TypeError):
            LOOKUPS["standard"]["base"] = 100  # Should be read-only


class TestTailMappingIntegrity:
    @pytest.mark.parametrize("alpha,bs", [("standard", 3), ("standard", 7), ("url", 5)])
    def test_tail_bijection(self, alpha, bs):
        cfg = get_codec(alpha, bs)
        te = cfg["tail_enc"]
        td = cfg["tail_dec"]

        # Every enc tail maps to dec tail
        for r, k in te.items():
            assert td[k] == r

        # Every dec tail maps to enc tail
        for k, r in td.items():
            assert te[r] == k

    @pytest.mark.parametrize("alpha,bs,fn", [
        ("standard", 3, 3),
        ("standard", 7, 7),
        ("url", 5, 5),
    ])
    def test_tail_covers_all_remainders(self, alpha, bs, fn):
        cfg = get_codec(alpha, bs)
        te = cfg["tail_enc"]
        assert set(te.keys()) == set(range(1, fn))

    @pytest.mark.parametrize("alpha,bs,fn,fk", [
        ("standard", 3, 3, 4),
        ("standard", 7, 7, 9),
        ("url", 5, 5, 7),
    ])
    def test_headroom(self, alpha, bs, fn, fk):
        cfg = get_codec(alpha, bs)
        radix = cfg["radix"]
        assert POW[radix][fk] >= POW[256][fn]