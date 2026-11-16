# this_file: tests/test_custom_info_parser.py
"""Independent P01-P27 glyph-token/plist grammar and partial-mutation oracles."""

from copy import deepcopy

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.custom_info_errors import (
    GlyphDataLoadError,
    GlyphDataParseError,
)
from fontlab_glyport.model.custom_info_parser import parse_into, scan_entries
from fontlab_glyport.model.info_records import GlyphInfoIndex


def parse(data):
    index = GlyphInfoIndex()
    parse_into(index, data)
    return index


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"abc",
        b'<Glyph name="Ignored"/>',
        b"<glyph/>",
        b"<glyph>",
        b"trailing<glyph ",
    ],
)
def test_outer_scan_ignores_unrecognized_tokens_or_short_suffix(data):
    assert parse(data).records == []


def test_rootless_and_arbitrary_invalid_surrounding_text_do_not_hide_glyph_tokens():
    data = b'junk<broken><glyph name="OwnedA"/>unclosed<glyph name="OwnedB">'
    index = parse(data)
    assert [r.name for r in index.records] == ["OwnedA", "OwnedB"]


@pytest.mark.parametrize("space", [b"\t", b"\n", b"\v", b"\f", b"\r", b" "])
def test_glyph_entry_requires_exact_ascii_space_set_after_token(space):
    assert (
        parse(b"<glyph" + space + b'name="Owned"/>').raw_name("Owned").name == "Owned"
    )


@pytest.mark.parametrize("after", [b"\xe2\x80\xa8", b"\xe2\x80\xa9", b"/*comment*/"])
def test_unicode_separator_and_comment_immediately_after_glyph_do_not_start_entry(
    after,
):
    assert parse(b"<glyph" + after + b'name="Ignored"/>').records == []


def test_unicode_separators_c_comments_and_no_inter_attribute_space_are_supported_inside_entry():
    data = "<glyph \u2028name/*key*/=//line\n\"OwnedA\"unicode=\u2029'0041'/>".encode()
    index = parse(data)
    assert index.raw_name("OwnedA").unicode == "0041"


def test_outer_xml_comments_skip_fake_glyphs_but_do_not_require_valid_document():
    index = parse(b'<!-- <glyph name="Ignored"/> --><glyph name="Owned"/>')
    assert [r.name for r in index.records] == ["Owned"]


def test_unterminated_outer_comment_after_completed_row_retains_row_without_parse_error():
    assert [r.name for r in parse(b'<glyph name="Owned"/><!-- no end').records] == [
        "Owned"
    ]


def test_duplicate_attributes_last_win_and_absent_name_is_ignored_but_empty_is_present():
    index = parse(
        b'<glyph name="Wrong"name="Owned"/><glyph unicode="0041"/><glyph name=""/>'
    )
    assert [r.name for r in index.records] == ["Owned", ""]
    assert index.raw_name("Wrong") is None


def test_values_keep_literal_entities_and_accept_opposite_quote_and_tag_characters():
    data = b"""<glyph name='Owned' production="&amp;&#65;&#x41;&quot;'/>"/>"""
    record = parse(data).raw_name("Owned")
    assert record._production_state.value == "&amp;&#65;&#x41;&quot;'/>"


@pytest.mark.parametrize(
    "encoded,expected",
    [
        (rb"\a\b\f\n\r\t\v", "\a\b\f\n\r\t\v"),
        (rb"\q\x41\u0041", "qx41u0041"),
        (rb"\101\7774", "A\u00ff4"),
        (rb"\U0041\U03A9\U0100\U1F600", "A\u00a9\x00`0"),
        (b"\\\n", "\n"),
        (rb"\UGGGG", "\x00GGGG"),
    ],
)
def test_plist_escape_values_are_not_standard_xml_or_unicode_escape_decoding(
    encoded, expected
):
    record = parse(b'<glyph name="Owned" production="' + encoded + b'"/>').raw_name(
        "Owned"
    )
    assert record._production_state.value == expected


def test_non_xml_key_characters_and_invalid_slash_close_still_merge_completed_dictionary():
    assert list(scan_entries(b'<glyph name="Owned" a:b="x" strange&key="y" /x')) == [
        {"name": "Owned", "a:b": "x", "strange&key": "y"}
    ]


@pytest.mark.parametrize(
    "bad",
    [
        b'<glyph name "Bad"/>',
        b"<glyph name=Bad/>",
        b'<glyph name="Bad',
        b"<glyph /*unterminated",
        b'<glyph ="Bad"/>',
        b'<glyph name="Bad" <!-- comment -->/>',
    ],
)
def test_later_entry_parse_failure_preserves_completed_rows_and_does_not_merge_bad_entry(
    bad,
):
    index = GlyphInfoIndex()
    with pytest.raises(GlyphDataParseError):
        parse_into(index, b'<glyph name="Owned"/>' + bad)
    assert [r.name for r in index.records] == ["Owned"]


def test_duplicate_production_failure_occurs_after_all_rows_mutate_graph():
    index = GlyphInfoIndex()
    with pytest.raises(GlyphDataLoadError) as caught:
        parse_into(
            index,
            b'<glyph name="A" production="Same"/><glyph name="B" production="Same"/><glyph name="Later"/>',
        )
    assert caught.value.code() == 1 and caught.value.domain() == "GSGlyphsDomain"
    assert [r.name for r in index.records] == ["A", "B", "Later"]
    assert index.raw_name("Same") is index.raw_name("A")


def test_scanner_is_streamed_so_later_parse_failure_does_not_prevent_first_yield():
    rows = scan_entries(b'<glyph name="Owned"/><glyph name=Bad/>')
    assert next(rows) == {"name": "Owned"}
    with pytest.raises(GlyphDataParseError):
        next(rows)


def test_invalid_utf8_key_and_value_are_explicit_qualified_refusals_with_prior_rows_retained():
    for bad in [b'<glyph name="Bad" \xff="x"/>', b'<glyph name="\xff"/>']:
        index = GlyphInfoIndex()
        with pytest.raises(UnsupportedCapability) as caught:
            parse_into(index, b'<glyph name="Owned"/>' + bad)
        assert caught.value.capability == "GSGlyphsInfo.customData.UTF8"
        assert [r.name for r in index.records] == ["Owned"]


def test_custom_merged_rows_preserve_exact_index_rules_and_input_bytes():
    data = b'<glyph name="Owned" unicode="0041" altNames="Old"/><glyph name="Owned" unicode="0042" altNames="New" description="ignored" group="ignored"/>'
    before = deepcopy(data)
    index = parse(data)
    a = index.raw_name("Owned")
    assert index.raw_name("Old") is index.raw_name("New") is a
    assert a.unicodes == ("0041", "0042") and index.raw_unicode("0042") is None
    assert (a.desc, a.group) == (None, None)
    assert data == before


@pytest.mark.parametrize(
    "bad", [b"<glyph unfinished", b"<glyph name   ", b"<glyph name=   "]
)
def test_key_and_equals_eof_are_bounded_failures_after_prior_completed_entry(bad):
    index = GlyphInfoIndex()
    with pytest.raises(GlyphDataParseError) as caught:
        parse_into(index, b'<glyph name="Prior"/>' + bad)
    assert caught.value.offset >= 0
    assert [r.name for r in index.records] == ["Prior"]


def test_outer_scanner_sees_glyph_text_inside_unrelated_quotes_or_cdata():
    for data in [
        b"""<other attr="<glyph name='Owned'/>"/>""",
        b"""<![CDATA[<glyph name="Owned"/>]]>""",
    ]:
        assert [r.name for r in parse(data).records] == ["Owned"]
