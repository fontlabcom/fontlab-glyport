# this_file: tests/test_info_manager_discovery.py
"""Actual public discovery methods feeding the existing file loader graph."""

from contextlib import contextmanager
from typing import ClassVar

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.model.info_records import GlyphInfoIndex


def test_public_candidates_keep_project_file_and_exact_home_boundary(monkeypatch):
    import os.path

    monkeypatch.setattr(os.path, "expanduser", lambda path: "/owned/home")
    assert GSGlyphsInfo.foldersForCustomInfoForFolder_("/owned/home/project") == [
        "/owned/home/project",
        "/owned/home/project/Info",
    ]
    assert GSGlyphsInfo.foldersForCustomInfoForFolder_(
        "/owned/project/file.glyphsproject"
    ) == [
        "/owned/project/file.glyphsproject",
        "/owned/project/file.glyphsproject/Info",
        "/owned/project",
        "/owned/project/Info",
    ]


def test_public_local_search_dispatches_receiver_for_supplied_array_and_keeps_duplicates():
    class Receiver(GSGlyphsInfo):
        _calls: ClassVar[list] = []

        @classmethod
        def findCustomGlyphDataInFolder_(cls, folder):
            cls._calls.append(folder)
            return None if folder == "/missing" else [folder]

    assert Receiver.findLocalGlyphInfoFolders_(["/z", "/missing", "/z"]) == ["/z", "/z"]
    assert Receiver._calls == ["/z", "/missing", "/z"]
    assert Receiver.findLocalGlyphInfoFolders_(None) == []
    with pytest.raises(UnsupportedCapability):
        Receiver.findLocalGlyphInfoFolders_("/z")


def test_public_folder_provider_order_filter_and_resolved_duplicate_urls(monkeypatch):
    from fontlab_glyport.model import custom_info_filesystem as fs

    seen = []

    @contextmanager
    def entries(folder):
        seen.append(folder)
        yield ["/owned/GlyphData_z.xml", "/owned/ignored.xml", "/owned/GlyphData.xml"]

    monkeypatch.setattr(fs, "directory_entries", entries)
    monkeypatch.setattr(fs, "resolve_symlinks", lambda path: "/owned/target.txt")
    urls = GSGlyphsInfo.findCustomGlyphDataInFolder_("/owned")
    assert [url.path() for url in urls] == ["/owned/target.txt", "/owned/target.txt"]
    assert seen == ["/owned"]


def test_owned_folder_and_info_files_feed_ordered_raw_then_finalized_local_graph(
    tmp_path,
):
    info = tmp_path / "Info"
    info.mkdir()
    (tmp_path / "GlyphData.xml").write_bytes(b'<glyph name="A" unicode="0041"/>')
    (info / "GlyphData_custom.xml").write_bytes(
        b'<glyph name="pair" decompose="A, A"/>'
    )
    (tmp_path / "glyphdata_ignored.xml").write_bytes(b'<glyph name="Never"/>')
    urls = GSGlyphsInfo.findLocalGlyphInfoFolders_([str(tmp_path), str(info)])
    assert [url.path() for url in urls] == [
        str(tmp_path / "GlyphData.xml"),
        str(info / "GlyphData_custom.xml"),
    ]
    m = GSGlyphsInfo._from_index(GlyphInfoIndex())
    assert m.loadLocalGlyphInfoFiles_error_(urls, None) is True
    pair, child = m.infoFromDataForName_("pair"), m.infoFromDataForName_("A")
    assert pair.components == ["A", "A"]
    m.updateComponentsInfos()
    assert pair.components[0] is pair.components[1] is child
    assert pair._resolved_record.baseString == "AA"
    assert m.infoFromDataForName_("Never") is None


def test_public_file_candidate_is_empty_but_parent_discovers_all_matching_files(
    tmp_path,
):
    project = tmp_path / "project.glyphsproject"
    project.touch()
    match = tmp_path / "GlyphData_other.xml"
    match.touch()
    assert GSGlyphsInfo.findCustomGlyphDataInFolder_(str(project)) == []
    assert GSGlyphsInfo.findCustomGlyphDataInFolder_(str(tmp_path / "missing")) is None
    urls = GSGlyphsInfo.findLocalGlyphInfoFolders_(
        [str(project), str(project) + "/Info", str(tmp_path)]
    )
    assert [url.path() for url in urls] == [str(match)]


def test_matching_directory_is_preserved_for_explicit_low_level_file_kind_refusal(
    tmp_path,
):
    matched = tmp_path / "GlyphData_directory.xml"
    matched.mkdir()
    urls = GSGlyphsInfo.findCustomGlyphDataInFolder_(str(tmp_path))
    assert [url.path() for url in urls] == [str(matched)]
    m = GSGlyphsInfo._from_index(GlyphInfoIndex())
    with pytest.raises(UnsupportedCapability) as caught:
        m.loadLocalGlyphInfoFiles_error_(urls, None)
    assert caught.value.capability == "GSGlyphsInfo.customData.fileType"


def test_public_discovery_closes_enumerator_when_resolution_refuses(monkeypatch):
    from fontlab_glyport.model import custom_info_filesystem as fs

    closed = []

    @contextmanager
    def entries(folder):
        try:
            yield ["/owned/GlyphData.xml"]
        finally:
            closed.append(True)

    def refuse(path):
        raise UnsupportedCapability("owned alias refusal", capability="owned.alias")

    monkeypatch.setattr(fs, "directory_entries", entries)
    monkeypatch.setattr(fs, "resolve_symlinks", refuse)
    with pytest.raises(UnsupportedCapability):
        GSGlyphsInfo.findCustomGlyphDataInFolder_("/owned")
    assert closed == [True]


def test_bsd_hidden_matching_file_never_reaches_public_loader(tmp_path):
    import os
    import stat

    visible, hidden = tmp_path / "GlyphData.xml", tmp_path / "GlyphData_hidden.xml"
    visible.write_bytes(b'<glyph name="Visible"/>')
    hidden.write_bytes(b'<glyph name="Hidden"/>')
    os.chflags(hidden, stat.UF_HIDDEN)
    urls = GSGlyphsInfo.findCustomGlyphDataInFolder_(str(tmp_path))
    assert [url.path() for url in urls] == [str(visible)]
    m = GSGlyphsInfo._from_index(GlyphInfoIndex())
    assert m.loadLocalGlyphInfoFiles_error_(urls, None) is True
    assert m.infoFromDataForName_("Visible") is not None
    assert m.infoFromDataForName_("Hidden") is None
