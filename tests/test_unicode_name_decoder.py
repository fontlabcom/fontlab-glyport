# this_file: tests/test_unicode_name_decoder.py
"""Raw decoder controls from the retained Glyphs4 decoder contract."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fontlab_glyport.model import unicode_name
from fontlab_glyport.model.unicode_name import decode_unicode_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("uni", []),
        ("uni0041", ["0041"]),
        ("uni004A0301", ["004A", "0301"]),
        ("uni004103010327", ["0041", "0301", "0327"]),
        ("uni0041030103270308", ["0041", "0301", "0327", "0308"]),
        ("uniD83DDE00", ["D83D", "DE00"]),
        ("uni0378FFFF", ["0378", "FFFF"]),
        ("u0041", ["0041"]),
        ("u00041", ["0041"]),
        ("u1F600", ["1F600"]),
        ("u1F6001F601", ["1F600", "1F601"]),
        ("u1F60000041", ["1F600", "00041"]),
        ("u0004100042", ["0041", "0004"]),
        ("u000410004200043", ["0041", "0004", "2000"]),
        ("u00041000420004300044", ["0041", "0004", "2000", "4300"]),
        (
            "u0004100042000430004400045",
            ["0041", "0004", "2000", "4300", "0440", "0045"],
        ),
        ("u100000", ["100000"]),
        ("u10FFFE", ["10FFFE"]),
        ("u10FFFF", ["10FFFF"]),
        ("u110000", ["110000"]),
        ("u1FFFFF", ["1FFFFF"]),
    ],
)
def test_contract_chunk_spelling_and_order(name, expected):
    calls = []

    def lookup(code):
        calls.append(code)
        return SimpleNamespace(unicode=code)

    result = decode_unicode_name(name, lookup, lambda code: pytest.fail(code))
    assert result is not None, f"Accepted contract spelling rejected: {name}"
    assert [record.unicode for record in result] == expected
    assert calls == expected, "Each complete chunk must reach lookup once, in order"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "UNI0041",
        "U0041",
        "Uni0041",
        "uni004a0301",
        "u1f600",
        "uni0041030G",
        "uni0041_0301",
        "uni0041.0301",
        "uni004A0301.sc",
        "u000410004G",
        "u000041",
        "u200000",
        "uni0041004",
        "uni00410",
        "u000",
        "u0000000",
        "u+041",
        "u-041",
        "u 041",
        "u\x00041",
        "u００４１",
        "u004\U0001f600",
        "uni0041\ud800000",
        "u\ud800041",
        "u004\uff26",
        "uni0x410301",
        "uni0041030\n",
    ],
)
def test_rejected_grammar_never_calls_callbacks(name):
    def forbidden(code):
        pytest.fail(f"Rejected spelling reached a callback: {code!r}")

    assert decode_unicode_name(name, forbidden, forbidden) is None


def test_direct_bare_u_keeps_helper_out_of_bounds():
    with pytest.raises(IndexError):
        decode_unicode_name(
            "u", lambda code: pytest.fail(code), lambda code: pytest.fail(code)
        )


@pytest.mark.parametrize("production", [None, "", "A", "uni0041"])
def test_indexed_repetitions_keep_raw_identity_and_later_mutation(production):
    record = SimpleNamespace(name="A", production=production, unicode="0041")
    index = {"0041": record}
    before = dict(vars(record))
    result = decode_unicode_name(
        "uni00410041", index.get, lambda code: pytest.fail(code)
    )
    assert result is not None and len(result) == 2
    assert result[0] is record and result[1] is record, (
        "Indexed records must not be copied"
    )
    assert vars(record) == before and index == {"0041": record}
    record.production = "later-fill"
    assert result[0].production == result[1].production == "later-fill"


def test_primary_legacy_alias_keys_preserve_same_record_in_both_positions():
    record = SimpleNamespace(name="alias", production=None)
    index = {"0041": record, "FE8D": record}
    result = decode_unicode_name(
        "uni0041FE8D", index.get, lambda code: pytest.fail(code)
    )
    assert result is not None and len(result) == 2
    assert result[0] is record and result[1] is record
    assert vars(record) == {"name": "alias", "production": None}


def test_misses_call_fallback_each_time_without_caching_or_filling():
    events = []

    def lookup(code):
        events.append(("lookup", code))

    def fallback(code):
        events.append(("fallback", code))
        return SimpleNamespace(name=code, production=None)

    result = decode_unicode_name("uni00410041", lookup, fallback)
    assert result is not None and len(result) == 2
    assert result[0] is not result[1], "Every uncached miss needs its own fallback call"
    assert [vars(record) for record in result] == [
        {"name": "0041", "production": None}
    ] * 2
    assert events == [("lookup", "0041"), ("fallback", "0041")] * 2


def test_index_hit_outranks_rejected_numeric_value_and_fallback_is_raw():
    indexed = SimpleNamespace(name="indexed-out-of-range", production="")
    fallback_record = SimpleNamespace(name="u110000", production=None)
    calls = []

    def fallback(code):
        calls.append(code)
        return fallback_record

    hit = decode_unicode_name("u10FFFF", {"10FFFF": indexed}.get, fallback)
    miss = decode_unicode_name("u110000", {}.get, fallback)
    assert hit is not None and hit[0] is indexed
    assert miss is not None and miss[0] is fallback_record
    assert indexed.production == "" and fallback_record.production is None
    assert calls == ["110000"]


@pytest.mark.parametrize(("prefix", "chunk"), [("uni", "FFFF"), ("u", "1F600")])
def test_long_names_preserve_all_chunks_without_whole_integer_parsing(prefix, chunk):
    record = SimpleNamespace(name="shared")
    result = decode_unicode_name(
        prefix + chunk * 4096, {chunk: record}.get, lambda code: pytest.fail(code)
    )
    assert result is not None and len(result) == 4096
    assert all(item is record for item in result)


def test_source_origin_is_this_worktree():
    """Source runs import this tree; GLYPORT_TEST_INSTALLED=1 runs (shipped tests
    against an installed wheel) must import the installed copy instead."""
    root = Path(__file__).resolve().parents[1]
    origin = Path(unicode_name.__file__).resolve()
    if os.environ.get("GLYPORT_TEST_INSTALLED") == "1":
        assert "site-packages" in origin.parts, origin
        assert root not in origin.parents, "Installed run imported the source tree"
        return
    assert origin == root / "src/fontlab_glyport/model/unicode_name.py"
