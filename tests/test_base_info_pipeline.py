# this_file: tests/test_base_info_pipeline.py
"""Owned base-parser oracles from retained parser/row/ordered-commit bodies."""

import logging
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.base_info_parser import (
    BaseParseResult,
    commit_base,
    parse_base_bytes,
    parse_base_file,
)
from fontlab_glyport.model.info_records import GlyphInfoIndex


def test_missing_and_short_files_return_false_with_no_error(tmp_path):
    missing = parse_base_file(tmp_path / "missing.xml")
    assert not missing.success and missing.error is None
    for size in range(10):
        path = tmp_path / f"short-{size}.xml"
        path.write_bytes(b"x" * size)
        result = parse_base_file(path)
        assert not result.success and result.error is None, size


def test_ten_bytes_without_rows_succeed_and_adopt_exact_empty_containers():
    result = parse_base_bytes(b"0123456789")
    target, groups = GlyphInfoIndex(), {}
    assert result.success and result.error is None
    assert commit_base(target, groups, result)
    assert target.names is result.index.names
    assert target.unicodes is result.index.unicodes
    assert target.records is result.index.records
    assert groups is not result.groups


@pytest.mark.parametrize("separator", [b"\t", b"\n", b"\r", b"\v", b"\f"])
def test_only_literal_space_after_glyph_starts_row(separator):
    result = parse_base_bytes(b"<glyph" + separator + b'name="ignored"/>')
    assert result.success and result.index.records == []


def test_outer_scanner_does_not_treat_xml_comment_as_exclusion():
    result = parse_base_bytes(b'<!-- <glyph name="inside"/> -->')
    assert result.success and [r.name for r in result.index.records] == ["inside"]


def test_accepted_row_has_independent_parsed_fields_and_locked_state():
    result = parse_base_bytes(
        b'<glyph name="owned" production="afiiOwned" unicode="0041, 0042" '
        b'unicode2="0043" unicodeLegacy="00AA" category="Letter" '
        b'subCategory="Uppercase" script="latin" case="upper" direction="RTL" '
        b'group="Owned group" groupIdx="-3" description="Owned &amp; literal" '
        b'altNames="aliasA, aliasB" anchors="top, bottom" accents="acute" '
        b'marks="grave, dieresis" decompose="partA, partB" sortName="sort" '
        b'sortNameKeep="keep" mirror="other" deprecated="0"/>'
    )
    assert result.success and result.error is None
    row = result.index.records[0]
    expected = {
        'name': "owned",
        'unicode': "0041",
        'unicodes': ("0041", "0042", "0043"),
        'unicodeLegacy': "00AA",
        'category': "Letter",
        'subCategory': "Uppercase",
        'script': "latin",
        'case': 1,
        'direction': 2,
        'group': "Owned group",
        'groupIdx': -3,
        'desc': "Owned &amp; literal",
        'altNames': ["aliasA", "aliasB"],
        'anchors': ["top", "bottom"],
        'marks': ["grave", "dieresis"],
        '_component_names': ["partA", "partB"],
        'sortName': "sort",
        'sortNameKeep': "keep",
        'mirror': "other",
        'deprecated': True,
        '_locked': True,
    }
    assert {key: getattr(row, key) for key in expected} == expected
    assert row._production_state.value == "afiiOwned"
    assert result.groups == {}, "The retained base parser never fills group map"


def test_base_arrays_keep_empty_tokens_and_legacy_is_production_alias():
    result = parse_base_bytes(
        b'<glyph name="owned" legacy="ownedLegacy" altNames="" anchors="" '
        b'decompose="" accents="" unicodes="0041, 0041, " unicodeLegacy="AA"/>'
    )
    row = result.index.records[0]
    assert row.altNames == row.anchors == row.marks == row._component_names == [""]
    assert row.unicodes == ("0041", "0041", "")
    assert row.unicodeLegacy is None
    assert result.index.names["ownedLegacy"] is row
    assert result.index.names[""] is row


def test_direct_unicodes_replacement_and_add_unicode_are_order_sensitive():
    result = parse_base_bytes(
        b'<glyph name="owned" unicode="0041" unicodes="0042, 0042" '
        b'unicode2="0043" unicode="12345678"/>'
    )
    row = result.index.records[0]
    assert row.unicodes == ("0042", "0042", "0043")
    assert row.unicode == "0042"


def test_alias_collisions_log_and_overwrite_without_custom_duplicate_error(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_base_bytes(
            b'<glyph name="A" altNames="aliasX" production="same"/>'
            b'<glyph name="B" altNames="aliasX" production="same"/>'
        )
    a, b = result.index.records
    assert result.success and result.index.names["A"] is a
    assert result.index.names["aliasX"] is result.index.names["same"] is b
    assert "aliasX" in caplog.text and "B" in caplog.text


@pytest.mark.parametrize("production", ["uni", "unicorn", "uni0041"])
def test_literal_uni_prefix_excludes_production_alias(production):
    result = parse_base_bytes(f'<glyph name="A" production="{production}"/>'.encode())
    assert list(result.index.names) == ["A"]


def test_primary_then_legacy_and_later_rows_follow_last_write_order():
    result = parse_base_bytes(
        b'<glyph name="A" unicodes="0041, 0042" unicodeLegacy="0043"/>'
        b'<glyph name="B" unicodes="0043, 0044" unicodeLegacy="0041"/>'
    )
    a, b = result.index.records
    assert list(result.index.unicodes) == ["0041", "0042", "0043", "0044"]
    assert result.index.unicodes == {"0041": b, "0042": a, "0043": b, "0044": b}


@pytest.mark.parametrize("bad_row", [b"<glyph />", b'<glyph name="unterminated'])
def test_private_partial_parse_failure_commits_no_manager_containers(bad_row):
    result = parse_base_bytes(b'<glyph name="A" unicode="0041"/>' + bad_row)
    assert not result.success and [r.name for r in result.index.records] == ["A"]
    target, groups = GlyphInfoIndex(), {"old": "group"}
    target.names["old"] = target.unicodes["old"] = SimpleNamespace(name="old")
    target.records.append(target.names["old"])
    containers = target.names, target.unicodes, target.records
    assert not commit_base(target, groups, result)
    assert (target.names, target.unicodes, target.records) == containers
    assert all(
        a is b
        for a, b in zip(containers, (target.names, target.unicodes, target.records))
    )
    assert groups == {"old": "group"}
    assert (result.error is None) == (bad_row == b"<glyph />")


def test_missing_quote_produces_owned_error_with_offset():
    result = parse_base_bytes(b"<glyph name=/>")
    assert not result.success and result.error is not None
    assert result.error.offset == 12


def test_nonempty_maps_and_rows_retain_identity_and_group_always_merges():
    target, groups = GlyphInfoIndex(), {"old": "old"}
    old = SimpleNamespace(name="old")
    target.names["old"] = target.unicodes["old"] = old
    target.records.append(old)
    containers = target.names, target.unicodes, target.records
    result = parse_base_bytes(b'<glyph name="A" unicode="0041"/>')
    result.groups["new"] = "new"
    assert commit_base(target, groups, result)
    assert all(
        a is b
        for a, b in zip(containers, (target.names, target.unicodes, target.records))
    )
    assert target.records == [old, result.index.records[0]]
    assert groups == {"old": "old", "new": "new"}


def test_mixed_container_identity_and_nil_groups():
    target = GlyphInfoIndex()
    old = SimpleNamespace(name="old")
    target.unicodes["old"] = old
    target.records.append(old)
    codes, rows = target.unicodes, target.records
    result = parse_base_bytes(b'<glyph name="A" unicode="0041"/>')
    assert commit_base(target, None, result)
    assert target.names is result.index.names
    assert target.unicodes is codes and target.records is rows


def test_setter_can_observe_name_commit_before_unicode_and_rows_then_groups():
    events = []

    class Observed(GlyphInfoIndex):
        def __setattr__(self, key, value):
            if key == "names" and hasattr(self, "names"):
                events.append(("names", self.unicodes, self.records))
            elif key in {"unicodes", "records"} and hasattr(self, key):
                events.append((key,))
            super().__setattr__(key, value)

    class Groups(dict):
        def update(self, values):
            events.append(("groups",))
            super().update(values)

    target, result = Observed(), parse_base_bytes(b'<glyph name="A"/>')
    codes, rows = target.unicodes, target.records
    assert commit_base(target, Groups(), result)
    assert events == [("names", codes, rows), ("unicodes",), ("records",), ("groups",)]


@pytest.mark.parametrize(
    "data", [b'<glyph name="\xff"/>', b'<glyph name="\xef\xbb\xbfA"/>']
)
def test_unqualified_foundation_conversion_stays_explicit(data):
    with pytest.raises(UnsupportedCapability):
        parse_base_bytes(data)


def test_result_containers_are_fresh_per_parse():
    a, b = parse_base_bytes(b"0123456789"), parse_base_bytes(b"0123456789")
    assert isinstance(a, BaseParseResult)
    assert a.index is not b.index and a.groups is not b.groups


def test_row_whitespace_c_comments_and_quoted_escapes_reuse_retained_primitives():
    result = parse_base_bytes(
        b'<glyph /* comment */ name="A\\nB" // next\n anchors="top"/>'
    )
    assert result.success and result.index.records[0].name == "A\nB"


@pytest.mark.parametrize(
    "group_idx,expected", [(b"12", 12), (b'"-3"', -3), (b'"65535"', -1), (b'"+7"', 7)]
)
def test_group_index_retains_read_int_and_signed_short_storage(group_idx, expected):
    result = parse_base_bytes(b'<glyph name="A" groupIdx=' + group_idx + b"/>")
    assert result.success and result.index.records[0].groupIdx == expected


@pytest.mark.parametrize("attribute", [b'unicodeExtra="0041"', b'unicode ="0041"'])
def test_unicode_requires_literal_equals_prefix_and_refuses_native_stall_edge(
    attribute,
):
    with pytest.raises(UnsupportedCapability, match="prefix"):
        parse_base_bytes(b'<glyph name="A" ' + attribute + b"/>")


def test_commit_locks_only_names_and_groups_and_nil_group_has_no_monitor(monkeypatch):
    from fontlab_glyport.model import base_info_commit

    events = []
    active = []

    class Lock:
        def __init__(self, label):
            self.label = label

        def __enter__(self):
            assert not active, "Native name/group commit locks never overlap"
            active.append(self.label)
            events.append(("enter", self.label))

        def __exit__(self, *args):
            events.append(("exit", active.pop()))

    class Target(GlyphInfoIndex):
        def __setattr__(self, key, value):
            if key in {"names", "unicodes", "records"} and hasattr(self, key):
                events.append((key, tuple(active)))
            super().__setattr__(key, value)

    class Groups(dict):
        def update(self, values):
            events.append(("groups", tuple(active)))
            super().update(values)

    monkeypatch.setattr(base_info_commit, "_NAME_LOCK", Lock("name"))
    monkeypatch.setattr(base_info_commit, "_GROUP_LOCK", Lock("group"))
    result = parse_base_bytes(b'<glyph name="A"/>')
    assert commit_base(Target(), Groups(), result)
    assert events == [
        ("enter", "name"),
        ("names", ("name",)),
        ("exit", "name"),
        ("unicodes", ()),
        ("records", ()),
        ("enter", "group"),
        ("groups", ("group",)),
        ("exit", "group"),
    ]
    events.clear()
    assert commit_base(Target(), None, result)
    assert ("enter", "group") not in events


def test_incomplete_row_has_no_fabricated_syntax_error():
    result = parse_base_bytes(b'<glyph name="A"')
    assert not result.success and result.error is None


def test_normal_file_success_and_skippable_row_byte(tmp_path):
    path = tmp_path / "owned.xml"
    path.write_bytes(b'<glyph ?name="A" groupIdx= \t-7/>')
    result = parse_base_file(path)
    assert result.success and result.index.records[0].groupIdx == -7


def test_embedded_nul_finishes_row_as_retained_scanner_does():
    result = parse_base_bytes(b'<glyph name="A"\0 trailing text')
    assert result.success and result.index.records[0]._locked


@pytest.mark.parametrize(
    "data", [b"<glyph name=owned/>", b'<glyph name="A" anchors=/>']
)
def test_malformed_attribute_recovery_is_explicitly_unqualified(data):
    with pytest.raises(UnsupportedCapability, match="recovery"):
        parse_base_bytes(data)
