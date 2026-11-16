# this_file: tests/test_fontlab_backend_r020.py
"""R020 font-level writes in FontLabBackend against native doubles: the native
calls, the undo notifications and refusals. Native proof: the evidence drivers
in verification/issue-101-ecosystem/evidence/glyport-r020/."""

from types import SimpleNamespace

import pytest
from history_scene import install_font_window
from test_fontlab_backend_lazy import CountingPackage, native  # noqa: F401

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class Layout:
    """fgOTLayout double: keys(), get/set/remove feature, get/set prefix."""

    def __init__(self):
        self.prefix, self.features = "", {}

    def keys(self):
        return list(self.features)

    def get_feature(self, tag):
        return self.features[tag]

    def set_feature(self, tag, code):
        self.features[tag] = code

    def remove(self, tag):
        return self.features.pop(tag, None) is not None

    def get_prefix(self):
        return self.prefix

    def set_prefix(self, code):
        self.prefix = code


@pytest.fixture
def font(native, monkeypatch):  # noqa: F811
    module, calls, _, _ = native
    package = CountingPackage(40, calls, glyph_count=1, master_count=1)
    package.features = Layout()
    sent = []
    module.flItems = lambda: SimpleNamespace(
        notifyChangesApplied=lambda name, items, recursive=False: sent.append((name, list(items)))
    )
    module.flWorkspace = None
    install_font_window(monkeypatch, module, package)
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    return backend, fid, package, sent


def test_set_feature_when_written_then_native_text_and_package_notified(font):
    backend, fid, package, sent = font
    backend.set_feature(fid, "liga", "feature liga {\nx;\n} liga;\n")
    assert package.features.features == {"liga": "feature liga {\nx;\n} liga;\n"}
    assert sent == [("Glyport edit", [package]), ("Glyport edit", [package])]
    sent.clear()
    backend.set_feature(fid, "liga", None)
    assert package.features.features == {}
    assert len(sent) == 2


def test_set_feature_when_undo_group_then_one_pre_and_one_post_notification(font):
    backend, fid, package, sent = font
    backend.begin_undo("features")
    backend.set_feature(fid, "liga", "a")
    backend.set_feature(fid, "kern", "b")
    backend.set_feature_prefix(fid, "languagesystem DFLT dflt;")
    backend.end_undo()
    assert sent == [("features", [package]), ("features", [package])]
    assert package.features.prefix == "languagesystem DFLT dflt;"


def test_set_feature_when_bad_arguments_then_refused_before_native(font):
    backend, fid, package, sent = font
    with pytest.raises(ValueError):
        backend.set_feature(fid, "", "x")
    with pytest.raises(TypeError):
        backend.set_feature(fid, "liga", 3)
    with pytest.raises(TypeError):
        backend.set_feature_prefix(fid, None)
    assert sent == [] and package.features.features == {}


def test_font_writes_when_owned_unregistered_package_then_unsupported(native):  # noqa: F811
    from fontlab_glyport.model.fontlab_backend import OwnedPackage

    module, _, _, _ = native
    module.flWorkspace = None

    class Unregistered:
        id, isValid, masters, upm = 77, True, ["Regular"], 1000

        @property
        def fgPackage(self):
            raise AssertionError("must not read fgPackage of an owned package")

    source = SimpleNamespace(features=Layout(), info=SimpleNamespace(familyName="x"))
    backend = FontLabBackend(packages=[OwnedPackage(Unregistered(), source)])
    (fid,) = backend.list_fonts()
    with pytest.raises(UnsupportedCapability):
        backend.set_feature(fid, "liga", "x")


class Group(list):
    """fgGroup double: a list of names with a mode."""

    def __init__(self, name, members, mode, main):
        super().__init__(members)
        self.name, self.mode, self.main = name, mode, main

    def isFeaGroup(self):
        return self.mode == "FeaClassGroupMode"


class Groups:
    """fgGroups double: no item assignment (native fact); fromDict replaces all."""

    def __init__(self, **groups):
        self._groups = dict(groups)
        self.from_dict_calls = 0

    def has_key(self, name):
        return name in self._groups

    def __getitem__(self, name):
        return self._groups[name]

    def asDict(self):
        return dict(self._groups)

    def items(self):
        return self._groups.items()

    def fromDict(self, groups):
        self.from_dict_calls += 1
        self._groups = dict(groups)

    def remove(self, name):
        return self._groups.pop(name, None) is not None

    def rename(self, name, new_name):
        self._groups[new_name] = self._groups.pop(name)


@pytest.fixture
def groups_font(font, monkeypatch):
    backend, fid, package, sent = font
    package.groups = Groups(
        kT=Group("kT", ["T"], "KernLeftGroupMode", "T"),
    )
    monkeypatch.setattr(
        FontLabBackend,
        "_fontgate",
        staticmethod(lambda: SimpleNamespace(fgGroup=Group)),
    )
    return backend, fid, package, sent


def test_set_class_when_added_then_other_groups_kept_and_notified(groups_font):
    backend, fid, package, sent = groups_font
    backend.set_class(fid, "uc", ("A", "B"))
    stored = package.groups.asDict()
    assert list(stored["uc"]) == ["A", "B"] and stored["uc"].mode == "FeaClassGroupMode"
    assert "kT" in stored
    assert [c.name for c in backend.classes(fid)] == ["uc"]
    assert sent == [("Glyport edit", [package]), ("Glyport edit", [package])]


def test_set_class_when_removed_or_renamed_then_native_group_changed(groups_font):
    backend, fid, _, _ = groups_font
    backend.set_class(fid, "uc", ("A",))
    backend.rename_class(fid, "uc", "caps")
    assert [c.name for c in backend.classes(fid)] == ["caps"]
    backend.set_class(fid, "caps", None)
    assert backend.classes(fid) == ()


def test_set_class_when_name_is_a_kerning_group_or_bad_then_refused(groups_font):
    backend, fid, package, _ = groups_font
    with pytest.raises(UnsupportedCapability):
        backend.set_class(fid, "kT", ("A",))
    with pytest.raises(UnsupportedCapability):
        backend.rename_class(fid, "kT", "x")
    with pytest.raises(ValueError):
        backend.set_class(fid, "", ("A",))
    with pytest.raises(TypeError):
        backend.set_class(fid, "uc", ("A", ""))
    backend.set_class(fid, "uc", ("A",))
    with pytest.raises(UnsupportedCapability):
        backend.rename_class(fid, "uc", "kT")
    assert package.groups.from_dict_calls == 1


def test_hint_writes_when_called_then_edit_layer_hints_operations(native):  # noqa: F811
    from test_fontlab_backend_lazy import FontPr

    from fontlab_glyport.model.backend import HintInfo

    module, calls, _, _ = native
    edits = []

    class Tools(FontPr):
        def edit_layer_hints(self, **arguments):
            edits.append(arguments)
            return {"status": "ok"}

    tools = Tools()
    package = CountingPackage(41, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    backend._fontpr = lambda: tools
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    before = calls["notify"]
    backend.add_hint(layer.id, HintInfo(True, 100, 80, "h1"))
    # The tool makes no Undo step from Python: the layer is notified around it.
    assert calls["notify"] - before == 2
    backend.set_hint(
        layer.id, 0, {"horizontal": False, "position": 50, "width": 60, "name": "v"}
    )
    backend.set_hint(layer.id, 1, {"position": 700})
    backend.remove_hint(layer.id, 0)
    where = {"font_id": package.fgId, "glyph_name": "glyph0", "layer_name": "Master 0"}
    assert [{k: e[k] for k in where} for e in edits] == [where] * 4
    assert [e["operations"] for e in edits] == [
        [
            {
                "op": "add",
                "orientation": "horizontal",
                "position": 100,
                "width": 80,
                "name": "h1",
                "ghost": False,
            }
        ],
        [
            {
                "op": "set",
                "hint_index": 0,
                "orientation": "vertical",
                "position": 50,
                "width": 60,
                "name": "v",
            }
        ],
        [{"op": "set", "hint_index": 1, "position": 700}],
        [{"op": "delete", "hint_index": 0}],
    ]
    with pytest.raises(TypeError):
        backend.add_hint(layer.id, {"position": 1})


@pytest.fixture
def axes_font(font):
    from test_fontlab_backend_lazy import Axis

    backend, fid, package, sent = font
    module = FontLabBackend._native()
    module.flAxis = lambda name, tag, short: Axis(name, tag, short)
    from test_fontlab_backend_r020_review import Location

    module.flLocation = Location
    package.axes = []
    locations = {name: Location() for name in package.masters}
    package.location = lambda name: locations[name]
    package.setLocation = lambda location, name: locations.__setitem__(name, location)

    def add_axis(axis):
        package.axes = [*package.axes, axis]
        return axis.name

    package.addAxis = add_axis
    return backend, fid, package, sent


def test_add_axis_when_registered_tag_then_fontlab_short_name_and_id(axes_font):
    from fontlab_glyport.model.backend import AxisInfo

    backend, fid, package, sent = axes_font
    assert backend.add_axis(fid, AxisInfo("", "Weight", "wght", True)) == "wght"
    assert backend.add_axis(fid, AxisInfo("", "Grade", "GRAD")) == "GRAD"
    assert [(a.name, a.tag, a.shortName, a.hidden) for a in package.axes] == [
        ("Weight", "wght", "wt", True),
        ("Grade", "GRAD", "GRAD", False),
    ]
    assert [a.id for a in backend.font_info(fid).axes] == ["wght", "GRAD"]
    assert len(sent) == 4


def test_master_axes_when_set_then_location_by_short_name(axes_font):
    from fontlab_glyport.model.backend import AxisInfo

    backend, fid, package, _ = axes_font
    backend.add_axis(fid, AxisInfo("", "Weight", "wght"))
    backend.add_axis(fid, AxisInfo("", "Width", "wdth"))
    master = backend.font_info(fid).masters[0]
    backend.set_master_axes(master.id, (700.0, 100.0))
    location = package.location(master.name)
    assert (location["wt"], location["wd"], len(location)) == (700.0, 100.0, 2)
    assert backend.font_info(fid).masters[0].axes == (700.0, 100.0)
    with pytest.raises(ValueError):
        backend.set_master_axes(master.id, (700.0,))


def test_remove_and_set_axis_when_attached_then_axes_list_reassigned(axes_font):
    from fontlab_glyport.errors import StaleNativeObject
    from fontlab_glyport.model.backend import AxisInfo

    backend, fid, package, _ = axes_font
    backend.add_axis(fid, AxisInfo("", "Weight", "wght"))
    backend.add_axis(fid, AxisInfo("", "Width", "wdth"))
    backend.set_axis(fid, 1, AxisInfo("", "Breite", "wdth", True))
    assert [(a.name, a.hidden) for a in package.axes] == [
        ("Weight", False),
        ("Breite", True),
    ]
    backend.remove_axis(fid, 0)
    assert [a.tag for a in package.axes] == ["wdth"]
    with pytest.raises(StaleNativeObject):
        backend.remove_axis(fid, 1)


def test_coordinates_when_two_axes_then_read_by_key_not_value_weight(axes_font):
    """Native fact (probe-location-read-run1): valueWeight returns the weight
    for every axis; coordinates are read by short name, name or tag."""
    from test_fontlab_backend_lazy import Axis

    class WeightOnly(Axis):
        def valueWeight(self, location, default):
            raise AssertionError("valueWeight reads the weight for every axis")

    backend, fid, package, _ = axes_font
    package.axes = [
        WeightOnly("Weight", "wght", "wt"),
        WeightOnly("Width", "wdth", "wd"),
    ]
    package.location = lambda name: {"wt": 400.0, "wd": 100.0, "Weight": None}
    assert backend.font_info(fid).masters[0].axes == (400.0, 100.0)
    package.location = lambda name: {"Width": 80.0}
    assert backend.font_info(fid).masters[0].axes == (0.0, 80.0)
