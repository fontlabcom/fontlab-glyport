# this_file: tests/test_custom_info_discovery.py
"""Owned provider contracts; no Foundation or filesystem enumeration runs."""

from pathlib import PurePosixPath

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.custom_info_discovery import (
    candidate_folders,
    discover_folder,
    discover_local,
    is_glyph_data_name,
)


@pytest.mark.parametrize("path", ["/work/font", "/work/font.glyphsproject"])
def test_candidates_preserve_file_or_directory_input_and_stop_after_parent(path):
    assert candidate_folders(path, home="/Users/owned") == [
        path,
        path + "/Info",
        "/work",
        "/work/Info",
    ]


def test_candidates_suppress_parent_only_for_exact_home_equality():
    assert candidate_folders("/Users/owned/font", home="/Users/owned") == [
        "/Users/owned/font",
        "/Users/owned/font/Info",
    ]
    assert len(candidate_folders("/Users/owned/font", home="/Users/Owned")) == 4
    assert len(candidate_folders("/Users/owned/sub/font", home="/Users/owned")) == 4


def test_root_candidates_keep_duplicate_searches_and_home_root_suppression():
    assert candidate_folders("/", home="/Users/owned") == ["/", "/Info", "/", "/Info"]
    assert candidate_folders("/", home="/") == ["/", "/Info"]
    assert candidate_folders("/font", home="/") == ["/font", "/font/Info"]
    assert candidate_folders("/Info", home="/Users/owned") == [
        "/Info",
        "/Info/Info",
        "/",
        "/Info",
    ]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("GlyphData.xml", True),
        ("GlyphData_.xml", True),
        ("GlyphData_z.xml", True),
        ("GlyphData_x.xml.xml", True),
        ("GlyphData_Ω.xml", True),
        ("GlyphData.xml.bak", False),
        ("GlyphData_.XML", False),
        ("glyphData_x.xml", False),
        ("GlyphDatax.xml", False),
        ("GlyphData_", False),
        ("", False),
    ],
)
def test_name_predicate_uses_exact_case_sensitive_source_prefix_and_suffix(
    name, expected
):
    assert is_glyph_data_name(name) is expected


@pytest.mark.parametrize("name", [None, 7, b"GlyphData.xml"])
def test_non_string_names_refuse_without_implicit_conversion(name):
    with pytest.raises(UnsupportedCapability):
        is_glyph_data_name(name)


def test_folder_filters_before_resolution_preserving_order_and_duplicate_urls():
    calls = []
    paths = [
        "/work/GlyphData_z.xml",
        "/work/ignored.xml",
        "/work/GlyphData.xml",
        "/work/GlyphData_missing.xml",
        "/work/GlyphData_noURL.xml",
        "/work/GlyphData_z.xml",
    ]
    first, last = object(), object()
    urls = iter([first, last, None, first])

    def entries(folder):
        calls.append(("entries", folder))
        return iter(paths)

    def resolve(path):
        calls.append(("resolve", path))
        return None if path.endswith("_missing.xml") else "/target/GlyphData.xml"

    def make_url(path):
        calls.append(("url", path))
        return next(urls)

    assert discover_folder(
        "/work", entries=entries, resolve=resolve, make_url=make_url
    ) == [first, last, first]
    assert calls == [
        ("entries", "/work"),
        ("resolve", paths[0]),
        ("url", "/target/GlyphData.xml"),
        ("resolve", paths[2]),
        ("url", "/target/GlyphData.xml"),
        ("resolve", paths[3]),
        ("resolve", paths[4]),
        ("url", "/target/GlyphData.xml"),
        ("resolve", paths[5]),
        ("url", "/target/GlyphData.xml"),
    ]


@pytest.mark.parametrize("enumerated,expected", [(None, None), ([], [])])
def test_absent_enumerator_and_empty_enumerator_are_distinct(enumerated, expected):
    def unexpected(path):
        pytest.fail(f"unexpected resolution or URL conversion: {path}")

    assert (
        discover_folder(
            "/font.glyphsproject",
            entries=lambda path: enumerated,
            resolve=unexpected,
            make_url=unexpected,
        )
        == expected
    )


def test_url_provider_may_return_false_value_distinct_from_nil():
    assert discover_folder(
        "/work",
        entries=lambda path: ["/work/GlyphData.xml"],
        resolve=lambda path: path,
        make_url=lambda path: False,
    ) == [False]


def test_resolved_path_reaches_url_provider_exactly_without_name_refiltering():
    received = []

    def make_url(path):
        received.append(path)
        return path

    assert discover_folder(
        "/work",
        entries=lambda path: ["/work/GlyphData_alias.xml"],
        resolve=lambda path: "/target/SomeOtherName",
        make_url=make_url,
    ) == ["/target/SomeOtherName"]
    assert received == ["/target/SomeOtherName"]


def test_local_search_calls_each_candidate_in_order_and_keeps_duplicates():
    calls = []
    shared = object()
    responses = iter([None, [], [shared, shared], [shared]])

    def find(folder):
        calls.append(folder)
        return next(responses)

    assert discover_local(
        ["/work/font", "/work/font/Info", "/work", "/work/Info"], find_in_folder=find
    ) == [shared, shared, shared]
    assert calls == ["/work/font", "/work/font/Info", "/work", "/work/Info"]


def test_local_root_search_repeats_provider_calls_instead_of_deduplicating():
    calls = []

    def find(folder):
        calls.append(folder)
        return [folder]

    assert discover_local(["/", "/Info", "/", "/Info"], find_in_folder=find) == [
        "/",
        "/Info",
        "/",
        "/Info",
    ]
    assert calls == ["/", "/Info", "/", "/Info"]


@pytest.mark.parametrize("stage", ["entries", "iterate", "resolve", "url"])
def test_provider_failure_propagates_with_prior_side_effects_and_no_later_work(stage):
    calls = []
    failure = RuntimeError("owned failure")

    def items():
        calls.append("first")
        yield "/work/GlyphData_first.xml"
        calls.append("second")
        if stage == "iterate":
            raise failure
        yield "/work/GlyphData_second.xml"
        pytest.fail("enumeration continued after failure")

    def entries(folder):
        calls.append("entries")
        if stage == "entries":
            raise failure
        return items()

    def resolve(path):
        calls.append("resolve")
        if stage == "resolve" and path.endswith("second.xml"):
            raise failure
        return path

    def make_url(path):
        calls.append("url")
        if stage == "url" and path.endswith("second.xml"):
            raise failure
        return path

    with pytest.raises(RuntimeError) as caught:
        discover_folder("/work", entries=entries, resolve=resolve, make_url=make_url)
    assert caught.value is failure
    expected = ["entries"]
    if stage != "entries":
        expected += ["first", "resolve", "url", "second"]
    if stage in {"resolve", "url"}:
        expected += ["resolve"]
    if stage == "url":
        expected += ["url"]
    assert calls == expected


def test_local_failure_propagates_after_prior_folder_side_effects():
    calls = []
    failure = OSError("owned provider failure")

    def find(folder):
        calls.append(folder)
        if len(calls) == 2:
            raise failure
        return [object()]

    with pytest.raises(OSError) as caught:
        discover_local(
            ["/work/font", "/work/font/Info", "/work", "/work/Info"],
            find_in_folder=find,
        )
    assert caught.value is failure
    assert calls == ["/work/font", "/work/font/Info"]


@pytest.mark.parametrize(
    "path",
    [
        None,
        1,
        PurePosixPath("/work"),
        "",
        "work",
        "~/work",
        "//work",
        "/work/",
        "/work//font",
        "/work/./font",
        "/work/../font",
        "/bad\0path",
        "/bad\ud800path",
    ],
)
def test_unqualified_path_refuses_before_any_provider_call(path):
    def unexpected(*args):
        pytest.fail("provider called for an unqualified path")

    with pytest.raises(UnsupportedCapability):
        candidate_folders(path, home="/Users/owned")
    with pytest.raises(UnsupportedCapability):
        discover_folder(
            path, entries=unexpected, resolve=unexpected, make_url=unexpected
        )
    with pytest.raises(UnsupportedCapability):
        discover_local([path], find_in_folder=unexpected)


@pytest.mark.parametrize("home", [None, "/Users/owned/", "~", "Users/owned"])
def test_unqualified_home_refuses_before_search(home):
    def unexpected(folder):
        pytest.fail("provider called with an unqualified home")

    with pytest.raises(UnsupportedCapability):
        candidate_folders("/work/font", home=home)
    with pytest.raises(UnsupportedCapability):
        discover_local(
            candidate_folders("/work/font", home=home), find_in_folder=unexpected
        )


@pytest.mark.parametrize("entry", ["GlyphData.xml", "/work/../GlyphData.xml", None])
def test_provider_entry_paths_also_require_qualified_full_paths(entry):
    def unexpected(path):
        pytest.fail("resolution reached an unqualified entry")

    with pytest.raises(UnsupportedCapability):
        discover_folder(
            "/work",
            entries=lambda path: [entry],
            resolve=unexpected,
            make_url=unexpected,
        )


@pytest.mark.parametrize("resolved", ["GlyphData.xml", "/work/../GlyphData.xml", 7])
def test_unqualified_resolved_paths_refuse_before_url_wrapping(resolved):
    def unexpected(path):
        pytest.fail("URL provider received an unqualified path")

    with pytest.raises(UnsupportedCapability):
        discover_folder(
            "/work",
            entries=lambda path: ["/work/GlyphData.xml"],
            resolve=lambda path: resolved,
            make_url=unexpected,
        )


@pytest.mark.parametrize("folders", [None, [], ()])
def test_local_nil_or_empty_folder_array_returns_empty_without_search(folders):
    def unexpected(folder):
        pytest.fail("search called for nil/empty folder array")

    assert discover_local(folders, find_in_folder=unexpected) == []


@pytest.mark.parametrize("folders", ["/work/font", 42, PurePosixPath("/work")])
def test_local_refuses_non_array_input_without_implicit_candidate_expansion(folders):
    def unexpected(folder):
        pytest.fail("non-array input reached provider")

    with pytest.raises(UnsupportedCapability):
        discover_local(folders, find_in_folder=unexpected)


def test_local_invalid_later_path_preserves_prior_provider_effects():
    calls = []

    def find(folder):
        calls.append(folder)
        return [object()]

    with pytest.raises(UnsupportedCapability):
        discover_local(["/work", "relative", "/later"], find_in_folder=find)
    assert calls == ["/work"]
