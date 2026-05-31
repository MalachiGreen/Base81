from base81 import get_codec, list_codecs
from base81._codecs import CODECS


def test_list_codecs():
    codecs = list_codecs()
    assert ("standard", 3) in codecs
    assert ("standard", 7) in codecs
    assert ("url", 5) in codecs
    assert len(codecs) == 3


def test_get_codec_exists():
    cfg = get_codec("standard", 7)
    assert cfg is not None
    assert cfg["radix"] == 81
    assert cfg["full_n"] == 7
    assert cfg["full_k"] == 9
    assert len(cfg["tail_enc"]) == 6  # r=1..6
    assert len(cfg["tail_dec"]) == len(set(cfg["tail_enc"].values()))


def test_get_codec_missing():
    assert get_codec("standard", 99) is None
    assert get_codec("unknown", 7) is None


def test_codec_tail_bijection():
    for (alpha, bs), cfg in CODECS.items():
        te = cfg["tail_enc"]
        td = cfg["tail_dec"]
        # Every r in 1..fn-1 has a k
        assert set(te.keys()) == set(range(1, cfg["full_n"]))
        # Inverse mapping holds
        for r, k in te.items():
            assert td[k] == r
        # td keys are exactly the set of tail lengths
        assert set(td.keys()) == set(te.values())


def test_headroom():
    """Check N^fk >= 256^fn for each codec."""
    for (alpha, bs), cfg in CODECS.items():
        radix = cfg["radix"]
        fn = cfg["full_n"]
        fk = cfg["full_k"]
        assert radix ** fk >= 256 ** fn


def test_tail_minimality():
    """Verify tails use smallest k such that N^k >= 256^r."""
    for (alpha, bs), cfg in CODECS.items():
        radix = cfg["radix"]
        for r, k in cfg["tail_enc"].items():
            # k is minimal
            assert radix ** (k - 1) < 256 ** r
            assert radix ** k >= 256 ** r