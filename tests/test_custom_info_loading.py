# this_file: tests/test_custom_info_loading.py
"""Owned filesystem/error core; native NSError/URL/out ABI remains held."""

from copy import copy, deepcopy
from pathlib import Path

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.model.custom_info_errors import GlyphDataLoadError
from fontlab_glyport.model.custom_info_loading import (
    load_custom_file,
    load_custom_files,
)
from fontlab_glyport.model.info_records import GlyphInfoIndex
from fontlab_glyport.model.public_info_index import PublicInfoIndex


def write(path, data):
    path.write_bytes(data)
    return path


def test_missing_file_succeeds_and_existing_zero_one_two_bytes_fail_without_rows(
    tmp_path,
):
    index = GlyphInfoIndex()
    assert load_custom_file(index, tmp_path / "missing.xml") is None
    for data in [b"", b"x", b"xy"]:
        error = load_custom_file(index, write(tmp_path / "short.xml", data))
        assert isinstance(error, GlyphDataLoadError)
        assert error.domain() == "GSGlyphsDomain" and error.code() == 0x2AE2
        assert error.offset == 0 and error.path == str(tmp_path / "short.xml")
        assert isinstance(error.localizedDescription(), str)
    assert index.records == []
    assert load_custom_file(index, write(tmp_path / "text.xml", b"abc")) is None


def test_completed_file_mutations_survive_later_file_error_and_stop_before_next_file(
    tmp_path,
):
    a = write(tmp_path / "a.xml", b'<glyph name="A"/>')
    bad = write(tmp_path / "bad.xml", b'<glyph name="Partial"/><glyph name=Bad/>')
    b = write(tmp_path / "b.xml", b'<glyph name="B"/>')
    index = GlyphInfoIndex()
    requested = []

    def paths():
        for path in [a, bad, b]:
            requested.append(path)
            yield path

    error = load_custom_files(index, paths())
    assert isinstance(error, GlyphDataLoadError) and error.code() == 0x2AE2
    assert error.path == str(bad) and error.offset is not None
    assert requested == [a, bad]
    assert [r.name for r in index.records] == ["A", "Partial"]


def test_ordered_missing_files_continue_and_duplicate_tracking_is_per_file(tmp_path):
    a = write(tmp_path / "a.xml", b'<glyph name="A" production="Same"/>')
    b = write(tmp_path / "b.xml", b'<glyph name="B" production="Same"/>')
    index = GlyphInfoIndex()
    assert load_custom_files(index, [a, tmp_path / "missing.xml", b]) is None
    assert [r.name for r in index.records] == ["A", "B"]
    assert index.raw_name("Same") is index.raw_name("A")
    assert load_custom_files(index, []) is None


def test_per_file_duplicate_failure_retains_all_that_files_completed_rows(tmp_path):
    p = write(
        tmp_path / "dup.xml",
        b'<glyph name="A" production="Same"/><glyph name="B" production="Same"/><glyph name="C"/>',
    )
    index = GlyphInfoIndex()
    error = load_custom_file(index, p)
    assert error.code() == 1 and error.path == str(p)
    assert [r.name for r in index.records] == ["A", "B", "C"]
    assert index.raw_name("Same") is index.raw_name("A")


def test_read_failure_after_existence_check_is_failure_not_missing_success(
    tmp_path, monkeypatch
):
    p = write(tmp_path / "gone.xml", b'<glyph name="Owned"/>')

    def disappeared(path, *args, **kwargs):
        raise FileNotFoundError("owned disappearance after stat")

    monkeypatch.setattr(Path, "open", disappeared)
    index = GlyphInfoIndex()
    error = load_custom_file(index, p)
    assert isinstance(error, GlyphDataLoadError) and isinstance(
        error.cause, FileNotFoundError
    )
    assert index.records == []


def test_stat_failure_is_explicit_and_never_becomes_empty_success(
    tmp_path, monkeypatch
):
    def denied(path):
        raise PermissionError("owned stat denial")

    monkeypatch.setattr(Path, "stat", denied)
    error = load_custom_file(GlyphInfoIndex(), tmp_path / "denied.xml")
    assert isinstance(error, GlyphDataLoadError) and isinstance(
        error.cause, PermissionError
    )


def test_unqualified_utf8_failure_retains_earlier_rows_and_does_not_become_parse_success(
    tmp_path,
):
    p = write(tmp_path / "utf8.xml", b'<glyph name="Owned"/><glyph name="\xff"/>')
    index = GlyphInfoIndex()
    with pytest.raises(UnsupportedCapability):
        load_custom_file(index, p)
    assert [r.name for r in index.records] == ["Owned"]


def public_index():
    a = {
        "name": "OwnedA",
        "unicode": "0041",
        "unicodeLegacy": "0043",
        "category": "Letter",
        "script": "latin",
        "altNames": "OldAlias",
    }
    b = {
        "name": "OwnedB",
        "unicode": "0042",
        "category": "Letter",
        "script": "latin",
        "production": "PriorProduction",
    }
    data = glyphdata.GlyphData(
        {"OwnedA": a, "OwnedB": b}, {}, {}, {"0041": a, "0042": b}
    )
    return PublicInfoIndex(data), data


def test_materialization_retains_raw_views_cells_order_and_input_dictionaries(tmp_path):
    index, data = public_index()
    before = deepcopy(
        (data.names, data.alternative_names, data.production_names, data.unicodes)
    )
    manager = GSGlyphsInfo._from_index(index)
    manager.infoFromDataForName_(
        "OwnedB"
    )  # Reverse warm order must not become base record order.
    raw = manager.infoFromDataForName_("OldAlias")
    frozen = copy(raw)
    # Rename by code so the old PRIMARY key must stay deleted after lazy lookup.
    p = write(
        tmp_path / "custom.xml",
        b'<glyph name="Renamed" unicode="0041" production="NewProduction"/>',
    )
    assert load_custom_file(index, p) is None
    assert manager.infoFromDataForName_("OwnedA") is None
    assert manager.infoFromDataForName_("Renamed") is raw
    assert manager.infoFromDataForName_("OldAlias") is raw
    assert manager.infoFromDataForUnicode_("0043") is raw
    assert raw.name == "Renamed" and raw.productionName == "NewProduction"
    assert frozen.name == "OwnedA" and frozen.productionName is None
    assert [r.name for r in index.records] == ["Renamed", "OwnedB"]
    assert (
        data.names,
        data.alternative_names,
        data.production_names,
        data.unicodes,
    ) == before


def test_materialization_prevents_removed_secondary_code_resurrection(tmp_path):
    index, _data = public_index()
    manager = GSGlyphsInfo._from_index(index)
    b = manager.infoFromDataForName_("OwnedB")
    # Give B a second ordered code via first custom merge; second merge removes
    # its old code keys but retains the ordered encodings, indexing first only.
    p = write(
        tmp_path / "custom.xml",
        b'<glyph name="OwnedB" unicode="0044"/><glyph name="OwnedB" unicode="0045"/>',
    )
    assert load_custom_file(index, p) is None
    assert b._resolved_record.unicodes == ("0042", "0044", "0045")
    assert manager.infoFromDataForUnicode_("0044") is None
    assert manager.infoFromDataForUnicode_("0045") is None
    assert manager.infoFromDataForUnicode_("0042") is b
    assert manager.infoFromDataForName_("PriorProduction") is b


def test_custom_known_fields_clear_only_their_own_unknown_markers_and_components_stay_raw_names(
    tmp_path,
):
    index, _ = public_index()
    manager = GSGlyphsInfo._from_index(index)
    p = write(
        tmp_path / "custom.xml",
        b'<glyph name="OwnedA" decompose="OwnedB, Missing" anchors="top" sortName="Known" group="ignored"/>',
    )
    assert load_custom_file(index, p) is None
    info = manager.infoFromDataForName_("OwnedA")
    assert info.components == ["OwnedB", "Missing"], (
        "Low-level loader has not finalized native component info"
    )
    record = info._resolved_record
    assert record.anchors == ["top"] and record.sortName == "Known"
    assert not {"components", "anchors", "sortName"} & record._unavailable_fields
    assert {"group", "groupIdx", "marks"} <= record._unavailable_fields
    with pytest.raises(UnsupportedCapability):
        _ = info.group


def test_explicit_empty_recipe_is_known_nil_after_raw_custom_merge(tmp_path):
    index, _ = public_index()
    manager = GSGlyphsInfo._from_index(index)
    p = write(tmp_path / "custom.xml", b'<glyph name="OwnedA" decompose=""/>')
    assert load_custom_file(index, p) is None
    assert manager.infoFromDataForName_("OwnedA").components is None


def test_nonregular_file_type_refuses_before_any_read(tmp_path, monkeypatch):
    from stat import S_IFCHR, S_IFIFO
    from types import SimpleNamespace

    for kind in [S_IFIFO, S_IFCHR]:
        monkeypatch.setattr(
            Path, "stat", lambda path, kind=kind: SimpleNamespace(st_mode=kind, st_size=0)
        )

        def never_read(*args, **kwargs):
            raise AssertionError("Nonregular source must not be opened/read")

        monkeypatch.setattr(Path, "open", never_read)
        with pytest.raises(UnsupportedCapability) as caught:
            load_custom_file(GlyphInfoIndex(), tmp_path / "owned-special")
        assert caught.value.capability == "GSGlyphsInfo.customData.fileType"


def test_short_regular_file_fails_before_read_and_read_is_bounded_to_measured_size(
    tmp_path, monkeypatch
):
    import io
    from stat import S_IFREG
    from types import SimpleNamespace

    requested = []

    class OwnedStream(io.BytesIO):
        def read(self, count=-1):
            requested.append(count)
            return super().read(count)

    monkeypatch.setattr(
        Path, "stat", lambda path: SimpleNamespace(st_mode=S_IFREG, st_size=2)
    )

    def open_stream(*args, **kwargs):
        return OwnedStream(b'abc<glyph name="NotMapped"/>')

    monkeypatch.setattr(Path, "open", open_stream)
    assert load_custom_file(GlyphInfoIndex(), tmp_path / "short") is not None
    assert requested == []
    monkeypatch.setattr(
        Path, "stat", lambda path: SimpleNamespace(st_mode=S_IFREG, st_size=3)
    )
    index = GlyphInfoIndex()
    assert load_custom_file(index, tmp_path / "bounded") is None
    assert requested == [3] and index.records == []


def test_truncated_after_stat_is_retained_read_failure_not_missing_success(
    tmp_path, monkeypatch
):
    import io
    from stat import S_IFREG
    from types import SimpleNamespace

    monkeypatch.setattr(
        Path, "stat", lambda path: SimpleNamespace(st_mode=S_IFREG, st_size=100)
    )
    monkeypatch.setattr(Path, "open", lambda *a, **kw: io.BytesIO(b"x"))
    error = load_custom_file(GlyphInfoIndex(), tmp_path / "shortened")
    assert isinstance(error, GlyphDataLoadError) and error.code() == 0x2AE2


def test_second_file_does_not_rebuild_removed_base_keys_after_materialization(tmp_path):
    index, _ = public_index()
    manager = GSGlyphsInfo._from_index(index)
    raw = manager.infoFromDataForName_("OwnedA")
    first = write(tmp_path / "first.xml", b'<glyph name="Renamed" unicode="0041"/>')
    second = write(tmp_path / "second.xml", b'<glyph name="Other" unicode="0050"/>')
    assert load_custom_files(index, [first, second]) is None
    assert manager.infoFromDataForName_("OwnedA") is None
    assert (
        manager.infoFromDataForName_("Renamed")
        is manager.infoFromDataForName_("OldAlias")
        is raw
    )
    assert [r.name for r in index.records] == ["Renamed", "OwnedB", "Other"]


def test_materialized_collision_winner_and_older_named_code_removal_follow_source_order(
    tmp_path,
):
    a = {
        "name": "Old",
        "unicode": "0041",
        "unicodeLegacy": "0043",
        "category": "Letter",
        "altNames": "Collision",
    }
    b = {
        "name": "New",
        "unicode": "0041",
        "category": "Letter",
        "altNames": "Collision, Old",
    }
    # Avoid aliasing Old itself for the older named update below; another key
    # still proves alias last-write order after reverse lazy warmup.
    b["altNames"] = "Collision"
    data = glyphdata.GlyphData({"Old": a, "New": b}, {}, {}, {"0041": b})
    index = PublicInfoIndex(data)
    manager = GSGlyphsInfo._from_index(index)
    winner = manager.infoFromDataForName_("New")
    older = manager.infoFromDataForName_("Old")
    assert manager.infoFromDataForUnicode_("0041") is winner
    p = write(tmp_path / "named.xml", b'<glyph name="Old"/>')
    assert load_custom_file(index, p) is None
    assert manager.infoFromDataForUnicode_("0041") is older
    assert manager.infoFromDataForUnicode_("0043") is older
    assert manager.infoFromDataForName_("Collision") is winner
    assert [r.name for r in index.records] == ["Old", "New"]


def test_loaded_fresh_local_record_reaches_real_parent_property_and_full_refresh_without_guessing_shared_group(
    tmp_path,
):
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    shared = GSGlyphsInfo.sharedManager()
    with pytest.raises(UnsupportedCapability):
        _ = shared.infoFromDataForName_("A").group
    index = GlyphInfoIndex(shared=shared._index)
    path = write(
        tmp_path / "local.xml",
        b'<glyph name="A" unicode="0041" category="Letter" script="latin" case="upper" direction="VTR" production="OwnedProduction"/>',
    )
    assert load_custom_file(index, path) is None
    local = GSGlyphsInfo._from_index(index)
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = local
    glyph = font.glyphs["A"]
    info = glyph.glyphInfo
    assert info.productionName == "OwnedProduction" and info.direction == 12
    assert info.group is None and info.groupIdx == 0, (
        "Explicit fresh local parser defaults are known, unlike unknown shared records"
    )
    glyph.updateGlyphInfo(False)
    assert (glyph.group, glyph.groupIdx, glyph.direction) == (None, 0, 12)
    assert local.infoFromDataForName_("A") is not shared.infoFromDataForName_("A")
    assert local.infoFromDataForName_("B") is shared.infoFromDataForName_("B")
    with pytest.raises(UnsupportedCapability):
        _ = shared.infoFromDataForName_("A").group


def test_reverse_warm_colliding_base_name_production_alias_and_legacy_indexes_materialize_exactly(
    tmp_path,
):
    a = {
        "name": "OwnedA",
        "unicode": "0041",
        "unicodeLegacy": "0043",
        "category": "Letter",
        "production": "SharedProd",
        "altNames": "AliasA, Collision",
    }
    b = {
        "name": "OwnedB",
        "unicode": "0043",
        "unicodeLegacy": "0041",
        "category": "Letter",
        "production": "SharedProd",
        "altNames": "OwnedA, Collision",
    }
    data = glyphdata.GlyphData(
        {"OwnedA": a, "OwnedB": b}, {}, {}, {"0041": a, "0043": b}
    )
    before = deepcopy(
        (data.names, data.alternative_names, data.production_names, data.unicodes)
    )
    index = PublicInfoIndex(data)
    manager = GSGlyphsInfo._from_index(index)
    raw_b = manager.infoFromDataForName_("OwnedB")
    raw_a = manager.infoFromDataForName_("AliasA")
    assert raw_a is not raw_b
    assert index.records == [raw_b._resolved_record, raw_a._resolved_record]
    p = write(tmp_path / "ignored.xml", b'<glyph production="IgnoredNoName"/>')
    assert load_custom_file(index, p) is None
    assert index.records == [raw_a._resolved_record, raw_b._resolved_record]
    assert manager.infoFromDataForName_("AliasA") is raw_a
    for name in ["OwnedA", "OwnedB", "Collision", "SharedProd"]:
        assert manager.infoFromDataForName_(name) is raw_b
    assert manager.infoFromDataForUnicode_("0041") is raw_b
    assert manager.infoFromDataForUnicode_("0043") is raw_b
    assert (
        data.names,
        data.alternative_names,
        data.production_names,
        data.unicodes,
    ) == before


def test_second_file_named_update_removes_competing_winner_for_older_secondary_code(
    tmp_path,
):
    index, _ = public_index()
    manager = GSGlyphsInfo._from_index(index)
    older = manager.infoFromDataForName_("OwnedA")
    first = write(
        tmp_path / "first.xml",
        b'<glyph name="OwnedA" unicode="0044"/><glyph name="Competing" unicode="0044"/>',
    )
    assert load_custom_file(index, first) is None
    winner = manager.infoFromDataForName_("Competing")
    assert manager.infoFromDataForUnicode_("0044") is winner
    second = write(tmp_path / "second.xml", b'<glyph name="OwnedA"/>')
    assert load_custom_file(index, second) is None
    assert manager.infoFromDataForUnicode_("0044") is None
    assert manager.infoFromDataForUnicode_("0041") is older
    assert manager.infoFromDataForName_("Competing") is winner
    assert older._resolved_record.unicodes == ("0041", "0044")
    assert winner._resolved_record.unicodes == ("0044",)
    assert [r.name for r in index.records] == ["OwnedA", "OwnedB", "Competing"]
