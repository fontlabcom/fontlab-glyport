# this_file: tests/test_info_manager_loading.py
"""Public raw-pointer profile, ordered loading and explicit finalization."""

import sys
from types import ModuleType

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.model.info_records import GlyphInfoIndex, add_unicode, new_record
from fontlab_glyport.ui.cocoa_controls import NSURL
from fontlab_glyport.ui.objc_bridge import make_objc_module


def manager(*records, shared=None):
    index = GlyphInfoIndex(shared=shared)
    for record in records:
        index.append(record)
    return GSGlyphsInfo._from_index(index)


def url(path, data=None):
    if data is not None:
        path.write_bytes(data)
    return NSURL.fileURLWithPath_(str(path))


def test_owned_objc_null_is_one_truthy_noninstantiable_sentinel():
    first, second = make_objc_module({}), make_objc_module({})
    assert first.NULL is second.NULL
    assert first.NULL is not None and first.NULL is not False
    assert bool(first.NULL) is True
    assert repr(first.NULL) == str(first.NULL) == "objc.NULL"
    with pytest.raises(TypeError):
        type(first.NULL)()
    with pytest.raises(AttributeError):
        first.NULL.some_state = 1


def test_alloc_init_and_new_return_shared_without_turning_alloc_into_local_init():
    first, second = GSGlyphsInfo.alloc(), GSGlyphsInfo.alloc()
    shared = GSGlyphsInfo.sharedManager()
    assert first is not second and first is not shared and second is not shared
    assert first.init() is second.init() is GSGlyphsInfo.new() is shared
    assert GSGlyphsInfo() is shared
    with pytest.raises(UnsupportedCapability) as caught:
        first.infoFromDataForName_("A")
    assert caught.value.capability == "GSGlyphsInfo.initialization"


def test_init_of_retained_local_object_returns_shared_without_replacing_its_graph():
    owned = new_record("Owned")
    local = manager(owned)
    view = local.infoFromDataForName_("Owned")
    assert local.init() is GSGlyphsInfo.sharedManager()
    assert local.infoFromDataForName_("Owned") is view


@pytest.mark.parametrize("null_kind", ["None", "NULL"])
def test_raw_error_pointer_returns_exact_bool_and_leaves_components_raw(
    tmp_path, null_kind
):
    null = None if null_kind == "None" else make_objc_module({}).NULL
    m = manager()
    source = url(tmp_path / "GlyphData.xml", b'<glyph name="A" decompose="B, B"/>')
    assert m.loadCustomGlyphDataFromURL_error_(source, null) is True
    view = m.infoFromDataForName_("A")
    assert view.components == ["B", "B"], "Low-level loading must not finalize recipes"
    assert (
        m.loadCustomGlyphDataFromURL_error_(url(tmp_path / "absent.xml"), null) is True
    )
    assert (
        m.loadCustomGlyphDataFromURL_error_(url(tmp_path / "short.xml", b"x"), null)
        is False
    )
    assert m.infoFromDataForName_("A") is view


@pytest.mark.parametrize("null_kind", ["None", "NULL"])
def test_ordered_url_loader_stops_at_error_retaining_completed_mutations(
    tmp_path, null_kind
):
    null = None if null_kind == "None" else make_objc_module({}).NULL
    sources = [
        url(tmp_path / "one.xml", b'<glyph name="A"/>'),
        url(tmp_path / "bad.xml", b'<glyph name="Partial"/><glyph name=Bad/>'),
        url(tmp_path / "last.xml", b'<glyph name="Never"/>'),
    ]
    requested = []

    def ordered():
        for source in sources:
            requested.append(source)
            yield source

    m = manager()
    assert m.loadLocalGlyphInfoFiles_error_(ordered(), null) is False
    assert requested == sources[:2]
    assert [r.name for r in m._index.records] == ["A", "Partial"]
    assert m.infoFromDataForName_("Never") is None


def test_empty_or_nil_url_arrays_succeed_without_consulting_a_url():
    m = manager()
    assert m.loadLocalGlyphInfoFiles_error_([], None) is True
    assert m.loadLocalGlyphInfoFiles_error_(None, None) is True
    assert m._index.records == []


@pytest.mark.parametrize("error", [[], {}, False, 0, 1, object()])
@pytest.mark.parametrize("multiple", [False, True])
def test_nonnull_error_arguments_refuse_before_url_access_or_mutation(error, multiple):
    class UnreadURL:
        def path(self):
            pytest.fail("Unsupported error-slot input must fail before URL access")

    m = manager()
    call = (
        m.loadLocalGlyphInfoFiles_error_
        if multiple
        else m.loadCustomGlyphDataFromURL_error_
    )
    with pytest.raises(UnsupportedCapability) as caught:
        call([UnreadURL()] if multiple else UnreadURL(), error)
    assert caught.value.capability == "GSGlyphsInfo.customData.errorPointer"
    assert m._index.records == []


def test_fake_null_repr_is_not_an_error_pointer():
    class FakeNULL:
        def __repr__(self):
            return "objc.NULL"

    with pytest.raises(UnsupportedCapability, match="error pointer"):
        manager().loadLocalGlyphInfoFiles_error_([], FakeNULL())


def test_active_real_bridge_null_identity_is_accepted_without_import(monkeypatch):
    # Owned stand-in proves protocol identity; no native module is imported.
    bridge = ModuleType("objc")
    bridge.NULL = object()
    monkeypatch.setitem(sys.modules, "objc", bridge)
    assert manager().loadLocalGlyphInfoFiles_error_([], bridge.NULL) is True


@pytest.mark.parametrize("bad", [None, "path.xml", object()])
def test_unqualified_urls_refuse_without_inventing_path_coercion(bad):
    with pytest.raises(UnsupportedCapability) as caught:
        manager().loadCustomGlyphDataFromURL_error_(bad, None)
    assert caught.value.capability == "GSGlyphsInfo.customData.URL"


def test_bad_url_path_type_refuses_and_later_url_refusal_keeps_prior_rows(tmp_path):
    class BadURL:
        def path(self):
            return 12

    first = url(tmp_path / "good.xml", b'<glyph name="A"/>')
    m = manager()
    with pytest.raises(UnsupportedCapability) as caught:
        m.loadLocalGlyphInfoFiles_error_([first, BadURL()], None)
    assert caught.value.capability == "GSGlyphsInfo.customData.URL"
    assert [r.name for r in m._index.records] == ["A"]


def test_url_provider_errors_and_unsupported_bytes_are_not_boolean_failures(tmp_path):
    class BrokenURL:
        def path(self):
            raise RuntimeError("owned URL failure")

    m = manager()
    with pytest.raises(RuntimeError, match="owned URL failure"):
        m.loadCustomGlyphDataFromURL_error_(BrokenURL(), None)
    source = url(tmp_path / "bytes.xml", b'<glyph name="Prior"/><glyph name="\xff"/>')
    with pytest.raises(UnsupportedCapability) as caught:
        m.loadCustomGlyphDataFromURL_error_(source, None)
    assert caught.value.capability == "GSGlyphsInfo.customData.UTF8"
    assert m.infoFromDataForName_("Prior") is not None


def test_public_finalizer_uses_selected_manager_and_keeps_retained_raw_view(tmp_path):
    shared_a = new_record("A")
    add_unicode(shared_a, "0053")
    shared = manager(shared_a)
    local_a = new_record("A")
    add_unicode(local_a, "004C")
    local = manager(local_a, shared=shared._index)
    source = url(tmp_path / "GlyphData.xml", b'<glyph name="pair" decompose="A, A"/>')
    assert local.loadCustomGlyphDataFromURL_error_(source, None) is True
    pair = local.infoFromDataForName_("pair")
    child = local.infoFromDataForName_("A")
    assert pair.components == ["A", "A"]
    assert local.updateComponentsInfos() is None
    assert local.infoFromDataForName_("pair") is pair
    assert pair.components[0] is pair.components[1] is child
    assert pair._resolved_record.baseString == "LL"
    assert shared_a.baseString is None and shared_a.unicharString is None
    with pytest.raises(UnsupportedCapability, match="name tokens"):
        local.updateComponentsInfos()


def test_public_finalizer_synthesis_callback_returns_record_and_restores_scope(
    tmp_path,
):
    from fontlab_glyport.model.info_source import current_index, selected_index

    local = manager()
    source = url(
        tmp_path / "GlyphData.xml", b'<glyph name="pair" decompose="uni0041"/>'
    )
    assert local.loadCustomGlyphDataFromURL_error_(source, None) is True
    other = GlyphInfoIndex()
    with selected_index(other):
        local.updateComponentsInfos()
        assert current_index() is other
    pair = local.infoFromDataForName_("pair")
    assert pair.components[0].name == "uni0041"
    assert pair._resolved_record.baseString == "A"


def test_finalizer_suffix_copy_has_known_empty_codes_and_keeps_base_encoding(tmp_path):
    base = new_record("A")
    add_unicode(base, "0041")
    local = manager(base)
    source = url(
        tmp_path / "GlyphData.xml", b'<glyph name="pair" decompose="A.owned"/>'
    )
    assert local.loadCustomGlyphDataFromURL_error_(source, None) is True
    local.updateComponentsInfos()
    pair = local.infoFromDataForName_("pair")
    child = pair.components[0]._resolved_record
    assert child.unicode is None and child.unicodes == ()
    assert base.unicode == "0041" and base.unicodes == ("0041",)
    assert pair._resolved_record.baseString == "A"


def test_ordered_public_loader_dispatches_each_child_on_receiver_and_forwards_null():
    class Receiver(GSGlyphsInfo):
        def loadCustomGlyphDataFromURL_error_(self, url, error):
            self._calls.append((url, error))
            return url != "stop"

    m = Receiver._from_index(GlyphInfoIndex())
    m._calls = []
    null = make_objc_module({}).NULL
    assert m.loadLocalGlyphInfoFiles_error_(["first", "stop", "never"], null) is False
    assert m._calls == [("first", null), ("stop", null)]


def test_public_finalizer_uses_receiver_full_name_dispatch_for_missing_component(
    tmp_path,
):
    class Receiver(GSGlyphsInfo):
        def glyphInfoForName_(self, name):
            self._calls.append(name)
            if name == "owned-callback":
                return self._view(self._owned)
            return None

    m = Receiver._from_index(GlyphInfoIndex())
    m._calls = []
    m._owned = new_record("owned-callback")
    add_unicode(m._owned, "0041")
    source = url(
        tmp_path / "GlyphData.xml", b'<glyph name="pair" decompose="owned-callback"/>'
    )
    assert m.loadCustomGlyphDataFromURL_error_(source, None) is True
    m.updateComponentsInfos()
    pair = m.infoFromDataForName_("pair")
    assert m._calls == ["alef-ar", "owned-callback"]
    assert pair.components[0] is m._view(m._owned)
    assert pair._resolved_record.baseString == "A"


def test_public_finalizer_materializes_all_base_records_in_source_order():
    from copy import deepcopy

    from glyphsLib import glyphdata

    from fontlab_glyport.model.public_info_index import PublicInfoIndex

    a = {"name": "OwnedA", "unicode": "0041", "category": "Letter", "script": "latin"}
    b = {**a, "name": "OwnedB", "unicode": "0042"}
    data = glyphdata.GlyphData(
        {"OwnedA": a, "OwnedB": b}, {}, {}, {"0041": a, "0042": b}
    )
    before = deepcopy(
        (data.names, data.alternative_names, data.production_names, data.unicodes)
    )
    m = GSGlyphsInfo._from_index(PublicInfoIndex(data))
    retained = m.infoFromDataForName_("OwnedB")  # Reverse lazy warm order.
    m.updateComponentsInfos()
    assert [r.name for r in m._index.records] == ["OwnedA", "OwnedB"]
    assert m.infoFromDataForName_("OwnedB") is retained
    assert m.infoFromDataForName_("OwnedA")._resolved_record.baseString == "A"
    with pytest.raises(UnsupportedCapability) as caught:
        _ = retained.group
    assert caught.value.capability == "GSGlyphInfo.group.source"
    assert (
        data.names,
        data.alternative_names,
        data.production_names,
        data.unicodes,
    ) == before
