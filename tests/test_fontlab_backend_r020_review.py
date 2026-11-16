# this_file: tests/test_fontlab_backend_r020_review.py
"""R020 review fixes in FontLabBackend against native doubles that follow the
probed behaviour (glyport-r020/probe-review-fixes-run1): flLocation keys are
case-insensitive, unknown keys read None, repr lists lowercased keys, values
may be (x, y) tuples, and flPackage.instances hands out copies but accepts
list assignment."""

from types import SimpleNamespace

import pytest
from history_scene import install_font_window
from test_fontlab_backend_lazy import Axis, CountingPackage, native  # noqa: F401

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.backend import AxisInfo, InstanceInfo
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class Location:
    """flLocation double (probe-location-keys-run1): case-sensitive lookups that
    read None for unknown keys; repr lowercases keys and rounds values."""

    def __init__(self, entries=None):
        self._entries = dict(entries or {})

    def __len__(self):
        return len(self._entries)

    def __getitem__(self, key):
        return self._entries.get(key)

    def __repr__(self):
        def text(v):
            return f"({v[0]:g},{v[1]:g})" if isinstance(v, tuple) else f"{v:g}"

        body = ",".join(f"{k.lower()}={text(v)}" for k, v in self._entries.items())
        return f"<flLocation {body}>"


class Instance:
    def __init__(self, name="", tsn="", location=None):
        self.name, self.tsn = name, tsn
        self.location = location if location is not None else Location()
        self.exportable, self.sgn = True, "kept"

    def copy(self):
        twin = Instance(self.name, self.tsn, self.location)
        twin.exportable, twin.sgn = self.exportable, self.sgn
        return twin


class Package(CountingPackage):
    @property
    def instances(self):
        return [i.copy() for i in self._store]

    @instances.setter
    def instances(self, value):
        self.assignments = getattr(self, "assignments", -1) + 1
        if getattr(self, "fail_assignment", False):
            self.fail_assignment = False
            self._store = list(value)[:1]
            raise RuntimeError("native assignment failed")
        self._store = [i.copy() for i in value]


@pytest.fixture
def font(native, monkeypatch):  # noqa: F811
    module, calls, _, _ = native
    package = Package(50, calls, glyph_count=1, master_count=1)
    package._store, package.assignments, package.fail_assignment = [], 0, False
    package.axes = [Axis("Weight", "wght", "wt")]
    locations = {name: Location({"wt": 400.0}) for name in package.masters}
    package.location = lambda name: locations[name]
    package.setLocation = lambda location, name: locations.__setitem__(name, location)
    package.clearInstances = lambda: (_ for _ in ()).throw(
        AssertionError("instances are assigned, not cleared and re-added")
    )
    module.flLocation = Location
    module.flInstance = Instance
    sent = []
    module.flItems = lambda: SimpleNamespace(
        notifyChangesApplied=lambda name, items, recursive=False: sent.append(name)
    )
    module.flWorkspace = None
    install_font_window(monkeypatch, module, package)
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    return backend, fid, package, sent


def test_set_instance_when_exports_only_then_location_untouched(font):
    backend, fid, package, _ = font
    location = Location({"wt": 700.0, "GRAD": -50.0})
    package._store = [Instance("Bold", "Bold", location)]
    backend.set_instance(fid, 0, {"exports": False})
    (stored,) = package._store
    assert stored.location is location and stored.exportable is False
    assert stored.sgn == "kept" and package.assignments == 1


def test_set_instance_when_axes_then_unrepresented_entries_kept(font):
    backend, fid, package, _ = font
    package._store = [Instance("Bold", "Bold", Location({"wt": 700.0, "GRAD": -50.0}))]
    backend.set_instance(fid, 0, {"axes": (900.0,)})
    location = package._store[0].location
    assert (location["wt"], location["GRAD"], len(location)) == (900.0, -50.0, 2)


def test_set_instance_when_location_keys_unreadable_then_refused(font):
    backend, fid, package, sent = font

    class Opaque(Location):
        def __repr__(self):
            return "<flLocation ?>"

    package._store = [Instance("Bold", "Bold", Opaque({"wt": 700.0, "x": 1.0}))]
    with pytest.raises(UnsupportedCapability):
        backend.set_instance(fid, 0, {"axes": (900.0,)})
    # A removed axis stored under an unusual spelling cannot be found again.
    package._store = [Instance("Bold", "Bold", Location({"wt": 700.0, "opSz": 9.0}))]
    with pytest.raises(UnsupportedCapability):
        backend.set_instance(fid, 0, {"axes": (900.0,)})
    assert package.assignments == 0 and sent == []


def test_instances_when_assignment_fails_then_original_restored_and_notified(font):
    backend, fid, package, sent = font
    package._store = [Instance("A"), Instance("B")]
    package.fail_assignment = True
    with pytest.raises(RuntimeError):
        backend.add_instance(fid, InstanceInfo("", "C", (400.0,)))
    assert [i.name for i in package._store] == ["A", "B"]
    assert sent == ["Glyport edit", "Glyport edit"]


def test_coordinates_when_anisotropic_then_xy_tuple_and_kept_on_write(font):
    backend, fid, package, _ = font
    package.axes = [Axis("Weight", "wght", "wt"), Axis("Width", "wdth", "wd")]
    locations = {"Master 0": Location({"wt": (300.0, 400.0), "wd": 100.0})}
    package.location = lambda name: locations[name]
    package.setLocation = lambda location, name: locations.__setitem__(name, location)
    master = backend.font_info(fid).masters[0]
    assert master.axes == ((300.0, 400.0), 100.0)
    backend.set_master_axes(master.id, (500.0, 120.0))
    assert locations["Master 0"]["wt"] == 500.0 and locations["Master 0"]["wd"] == 120.0


def test_set_axis_when_index_and_duplicate_then_refused_before_change(font):
    backend, fid, package, sent = font
    package.axes = [Axis("Weight", "wght", "wt"), Axis("Width", "wdth", "wd")]
    with pytest.raises(UnsupportedCapability):
        backend.set_axis(fid, 1, AxisInfo("", "Width", "wght"))
    with pytest.raises(UnsupportedCapability):
        backend.set_axis(fid, 1, AxisInfo("", "Weight", "wdth"))
    assert [(a.name, a.tag) for a in package.axes] == [
        ("Weight", "wght"),
        ("Width", "wdth"),
    ]
    assert sent == []
    backend.set_axis(fid, 1, AxisInfo("", "Breite", "wdth", True))
    assert (package.axes[1].name, package.axes[1].hidden) == ("Breite", True)
    backend.remove_axis(fid, 0)
    assert [a.tag for a in package.axes] == ["wdth"]


def test_set_hint_when_one_field_then_only_that_field_patched(native):  # noqa: F811
    from test_fontlab_backend_lazy import FontPr

    module, calls, _, _ = native
    edits = []

    class Tools(FontPr):
        def edit_layer_hints(self, **arguments):
            edits.append(arguments["operations"])

    package = CountingPackage(51, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    tools = Tools()
    backend._fontpr = lambda: tools
    (fid,) = backend.list_fonts()
    layer = backend.layer(
        backend.glyphs(fid)[0].id, backend.font_info(fid).masters[0].id
    )
    backend.set_hint(layer.id, 0, {"name": "bar"})
    backend.set_hint(layer.id, 1, {"horizontal": False})
    backend.set_hint(layer.id, 2, {"position": 10.0})
    assert edits == [
        [{"op": "set", "hint_index": 0, "name": "bar"}],
        [{"op": "set", "hint_index": 1, "orientation": "vertical"}],
        [{"op": "set", "hint_index": 2, "position": 10.0}],
    ]
    with pytest.raises(ValueError):
        backend.set_hint(layer.id, 0, {"ghost": True})


def test_instances_when_added_renamed_removed_then_list_assigned(font):
    backend, fid, package, sent = font
    backend.add_instance(fid, InstanceInfo("", "Bold", (700.0,), False))
    backend.add_instance(fid, InstanceInfo("", "Light", (300.0,)))
    assert [
        (i.name, i.tsn, i.location["wt"], i.exportable) for i in package._store
    ] == [
        ("Bold", "Bold", 700.0, False),
        ("Light", "Light", 300.0, True),
    ]
    backend.set_instance(fid, 0, {"name": "Black"})
    assert (package._store[0].name, package._store[0].tsn) == ("Black", "Black")
    package._store[0].tsn = "Heavy"
    backend.set_instance(fid, 0, {"name": "Ultra"})
    assert (package._store[0].name, package._store[0].tsn) == ("Ultra", "Heavy")
    backend.remove_instance(fid, 1)
    assert [i.name for i in package._store] == ["Ultra"]
    assert len(sent) == 10
    with pytest.raises(ValueError):
        backend.add_instance(fid, InstanceInfo("", "X", (1.0, 2.0)))
    with pytest.raises(ValueError):
        backend.set_instance(fid, 0, {"weight": 700})


def test_set_instance_when_case_distinct_keys_then_kept_exactly(font):
    backend, fid, package, _ = font
    location = Location({"wt": 700.0, "GRAD": -50.0, "Grad": 25.0})
    package._store = [Instance("Bold", "Bold", location)]
    backend.set_instance(fid, 0, {"axes": (900.0,)})
    stored = package._store[0].location
    assert (len(stored), stored["wt"], stored["GRAD"], stored["Grad"]) == (
        3,
        900.0,
        -50.0,
        25.0,
    )


def test_set_instance_when_spelling_ambiguous_or_unfound_then_refused(font):
    backend, fid, package, sent = font
    for entries in (
        {"wt": 700.0, "gRaD": 1.0},
        {"wt": 700.0, "GRAD": 1.0, "gRAD": 2.0},
    ):
        package._store = [Instance("Bold", "Bold", Location(entries))]
        with pytest.raises(UnsupportedCapability):
            backend.set_instance(fid, 0, {"axes": (900.0,)})
    assert package.assignments == 0 and sent == []
