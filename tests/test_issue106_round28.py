# this_file: tests/test_issue106_round28.py
"""Measured MCP restoration of default-recipe auto layers after creation."""

from copy import deepcopy
from types import SimpleNamespace as NS
from weakref import WeakSet

import pytest
from history_scene import register_history_owner
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.errors import PartialFailure, UnsupportedCapability
from fontlab_glyport.model import GSComponent, GSGlyph


def native_json_arrays(value):
    """Measured fontpr shape: mappings with tuple-valued JSON arrays."""
    if isinstance(value, dict):
        return {key: native_json_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(native_json_arrays(item) for item in value)
    return value


@pytest.fixture
def native(monkeypatch):
    # Each fixture is a different host; their synthetic package IDs are reused.
    # Peers constructed within this host still share its registry normally.
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._LIVE_BACKENDS", WeakSet()
    )
    n = native_fixture.__wrapped__(monkeypatch)
    names = {"A": n.glyph}
    n.package.findName = names.get
    n.package.findNewName = lambda name: "_scratch"
    n.package.deleteGlyph = lambda glyph: bool(names.pop(glyph.name, None))
    n.layer.name = "Regular"

    class AutoLayer:
        id, name, isValid = 900, "Regular", True

        def __init__(self, glyph_name):
            self.glyph_name = glyph_name
            self.cheap_reads = 0

        @property
        def data(self):
            return n.data[self.glyph_name]["layers"][0]

        @property
        def autoLayer(self):
            return bool(self.data.get("flags", 0) & 16)

        @property
        def recipe(self):
            return self.data.get("autoRecipe", "")

        @property
        def advanceWidth(self):
            return self.data.get("advanceWidth", 0)

        @property
        def shapes(self):
            self.cheap_reads += 1
            result = []
            for element in self.data.get("elements", []):
                if "component" not in element:
                    continue
                t = element.get("transform", {})
                result.append(
                    NS(
                        isComponent=True,
                        isComposite=True,
                        shapeData=NS(componentGlyph=element["component"]["glyphName"]),
                        transform=NS(
                            m11=lambda t=t: t.get("xScale", 1),
                            m12=lambda: 0,
                            m21=lambda: 0,
                            m22=lambda t=t: t.get("yScale", 1),
                            dx=lambda t=t: t.get("xOffset", 0),
                            dy=lambda t=t: t.get("yOffset", 0),
                        ),
                    )
                )
            return result

        @property
        def anchors(self):
            result = []
            for anchor in self.data.get("anchors", []):
                x, y = map(float, anchor["point"].split())
                result.append(
                    NS(name=anchor["name"], point=NS(x=lambda x=x: x, y=lambda y=y: y))
                )
            return result

    n.make_auto = AutoLayer
    auto = AutoLayer("Aacute")
    composite = NS(id=901, name="Aacute", layers=[auto])
    names["Aacute"] = composite
    n.package.fgPackage["Aacute"] = NS(name="Aacute", id=901, unicodes=[])
    original = {
        "name": "Aacute",
        "layers": [
            {
                "name": "Regular",
                "flags": 16,
                "advanceWidth": 610,
                "elements": [
                    {"component": {"glyphName": "A"}, "locked": True},
                    {
                        "component": {"glyphName": "acute"},
                        "transform": {"xOffset": 17, "yOffset": 23},
                        "locked": True,
                    },
                ],
                "anchors": [{"name": "top", "point": "42 730"}],
            }
        ],
    }
    n.data = {"Aacute": deepcopy(original)}
    n.original, n.names, n.reads, n.restores = original, names, [], []
    n.rebuild_on_restore = False
    n.restore_error = None
    n.lock_only = False

    def rebuild():
        layer = n.data["Aacute"]["layers"][0]
        if not layer["flags"] & 16 or layer.get("autoRecipe"):
            return
        for element in layer["elements"]:
            element.pop("locked", None)
        layer["anchors"] = []
        if not n.lock_only:
            layer["elements"][1] = {"component": {"glyphName": "acutecomb"}}
            layer["advanceWidth"] = 999

    def get_glyph(**kw):
        n.reads.append(kw["glyph_name"])
        return native_json_arrays(n.data[kw["glyph_name"]])

    def set_glyph(**kw):
        name = kw["glyph_name"]
        if kw.get("create", False):
            names[name] = NS(
                id=902,
                fgGlyphId=903,
                name=name,
                isValid=True,
                findLayer=lambda name: NS(shapes=[n.layer.shapes[0]]),
            )
            rebuild()
        else:
            assert isinstance(kw["glyph_data"]["layers"], list)
            assert all(
                isinstance(layer.get("elements", []), list)
                and isinstance(layer.get("anchors", []), list)
                for layer in kw["glyph_data"]["layers"]
            )
            n.restores.append(kw)
            if n.restore_error:
                raise n.restore_error
            n.data[name] = deepcopy(kw["glyph_data"])
            if n.rebuild_on_restore and ("acutecomb" in names or "_scratch" in names):
                rebuild()

    def resolve(name, capability):
        return {"get_glyph": get_glyph, "set_glyph": set_glyph}[name]

    monkeypatch.setattr(n.backend, "_resolve_tool", resolve)
    return n


@pytest.mark.parametrize("scratch", [False, True])
def test_creation_restores_through_existing_glyph_mcp_and_verifies(native, scratch):
    if scratch:
        native.font.glyphs[0].layers[0].components.append(GSComponent("A"))
        assert "_scratch" not in native.names
    else:
        native.font.glyphs.append(GSGlyph("acutecomb"))
        assert "acutecomb" in native.names
    assert native.data["Aacute"] == native.original
    assert len(native.restores) == 1
    assert native.restores[0]["create"] is False
    assert native.restores[0]["glyph_data"] == native.original
    assert native.reads == ["Aacute", "Aacute", "Aacute"]
    assert all(
        not any(getattr(obj, "id", None) in {900, 901} for obj in call[1])
        for call in native.calls
    )


@pytest.mark.parametrize("scratch", [False, True])
def test_restore_retriggering_rebuild_rolls_back_creation_and_refuses(native, scratch):
    native.rebuild_on_restore = True
    with pytest.raises(UnsupportedCapability, match="Aacute"):
        if scratch:
            native.font.glyphs[0].layers[0].components.append(GSComponent("A"))
        else:
            native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" not in native.names and "_scratch" not in native.names
    assert native.data["Aacute"] == native.original
    assert native.calls == []


def test_permanent_mcp_restore_failure_is_loud_and_creation_removed(native):
    native.restore_error = RuntimeError("MCP restore refused")
    with pytest.raises(PartialFailure, match="Aacute"):
        native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" not in native.names
    assert native.calls == []


@pytest.mark.parametrize("flags,recipe", [(0, None), (16, "A+acute")])
def test_explicit_recipe_or_non_auto_layer_not_restored(native, flags, recipe):
    layer = native.data["Aacute"]["layers"][0]
    layer["flags"] = flags
    if recipe:
        layer["autoRecipe"] = recipe
    native.backend.append_glyph(native.fid, "acutecomb")
    assert native.restores == []
    assert native.reads == []


def test_lock_and_anchor_only_host_defect_does_not_trigger_restore_or_refusal(native):
    native.lock_only = True
    native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" in native.names
    assert native.restores == []
    assert native.data["Aacute"]["layers"][0]["anchors"] == []


def test_unchanged_glyph_has_no_restore_writes(native):
    native.lock_only = True
    native.original["layers"][0]["anchors"] = []
    for element in native.original["layers"][0]["elements"]:
        element.pop("locked", None)
    native.data["Aacute"] = deepcopy(native.original)
    native.backend.append_glyph(native.fid, "acutecomb")
    assert native.data["Aacute"] == native.original
    assert native.restores == []


def test_missing_get_glyph_refuses_before_creation(native, monkeypatch):
    resolve = native.backend._resolve_tool

    def tools(name, capability):
        if name == "get_glyph":
            raise UnsupportedCapability("get_glyph unavailable", capability=capability)
        return resolve(name, capability)

    monkeypatch.setattr(native.backend, "_resolve_tool", tools)
    with pytest.raises(UnsupportedCapability, match="get_glyph"):
        native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" not in native.names
    assert native.data["Aacute"] == native.original
    assert native.calls == []


def test_native_candidate_members_are_bound():
    import ast
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[3]
        / "fontlab-echopy/src/fontlab_echopy/fontlab.pyi"
    )
    if not path.exists():
        pytest.skip("Sibling stub checkout required for API audit")
    classes = {
        node.name: node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.ClassDef)
    }
    for name, needed in {
        "flGlyph": {"name", "layers"},
        "flLayer": {
            "autoLayer",
            "recipe",
            "shapes",
            "anchors",
            "advanceWidth",
            "id",
            "name",
        },
        "flPackage": {"findName", "deleteGlyph"},
    }.items():
        members = {
            node.name
            for node in classes[name].body
            if isinstance(node, ast.FunctionDef)
        } | {
            node.target.id
            for node in classes[name].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert needed <= members
    assert "autoRecipe" not in {
        node.target.id
        for node in classes["flLayer"].body
        if isinstance(node, ast.AnnAssign)
    }


def test_pending_auto_layer_notification_refuses_before_creation(native):
    native.backend.begin_undo("Earlier edits")
    auto = native.names["Aacute"].layers[0]
    register_history_owner(native.backend, native.package, native.names["Aacute"], [auto])
    native.backend._changed["layer", auto.id] = auto
    with pytest.raises(UnsupportedCapability, match="Aacute"):
        native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" not in native.names
    assert native.restores == []
    assert native.calls == []


def test_native_fixture_does_not_reuse_a_previous_fake_hosts_pending_edits(monkeypatch):
    previous = native.__wrapped__(monkeypatch)
    previous.backend.begin_undo("Previous fake host")
    auto = previous.names["Aacute"].layers[0]
    previous.backend._changed["layer", auto.id] = auto
    current = native.__wrapped__(monkeypatch)

    current.font.glyphs.append(GSGlyph("acutecomb"))

    assert "acutecomb" in current.names, "Separate fake hosts reuse numeric IDs"
    assert previous.backend._changed, "Do not discard the previous host's edits"
