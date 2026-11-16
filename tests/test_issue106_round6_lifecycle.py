# this_file: tests/test_issue106_round6_lifecycle.py
"""Deferred callbacks and stale packages must never trigger unsafe undo publication."""

from types import SimpleNamespace

import pytest
from ui_doubles_session import make_session

from fontlab_glyport.errors import StaleNativeObject
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import GlyphInfo, LayerInfo
from fontlab_glyport.model.fontlab_backend import FontLabBackend


def test_q1_close_when_font_already_closed_then_drop_group_without_publishing(
    tmp_path, monkeypatch
):
    ctx, session = make_session(tmp_path)
    glyph = session.model.font.glyphs[0]
    glyph.beginUndo()
    glyph.layers[0].width = 777
    session.backend.close_font("font")

    def unsafe():
        raise AssertionError("must not publish a closed font")

    monkeypatch.setattr(session.backend, "end_undo", unsafe)
    ctx.close()
    assert glyph._font._undo_depth == glyph._undo_count == 0
    assert not glyph._font._undo_pending and not session.backend._undo
    note = next(d for d in ctx.diagnostics if d.code == "UNBALANCED_UNDO_DISCARDED")
    assert "A" in note.message


def test_q1_close_when_validity_check_fails_then_discard_and_surface_error(
    tmp_path, monkeypatch
):
    from fontlab_glyport.errors import PartialFailure

    ctx, session = make_session(tmp_path)
    glyph = session.model.font.glyphs[0]
    glyph.beginUndo()

    def fail(font_id):
        raise RuntimeError("validity check failed")

    monkeypatch.setattr(session.backend, "can_publish_undo", fail)
    with pytest.raises(PartialFailure, match="validity check failed"):
        ctx.close()
    assert not session.backend._undo and not glyph._font._undo_pending
    assert {d.code for d in ctx.diagnostics} == {
        "UNBALANCED_UNDO_DISCARDED",
        "UNDO_CLOSE_FAILED",
    }


@pytest.mark.parametrize("state", ["valid", "closed", "unregistered", "stale_layer"])
def test_q1_native_batch_when_package_or_layer_stale_then_no_native_notification(
    monkeypatch, state
):
    package = SimpleNamespace(id=10, isValid=True)
    glyph = SimpleNamespace(id=20, isValid=True)

    class Layer:
        id = 30

        @property
        def isValid(self):
            assert package.isValid and packages, (
                "read child only after package is confirmed registered"
            )
            return state != "stale_layer"

    layer, sent, packages = Layer(), [], [package]
    native = SimpleNamespace(
        flGlyph=SimpleNamespace(updatedFgGlyphs=lambda: ()),
        flWorkspace=SimpleNamespace(
            instance=lambda: SimpleNamespace(packages=lambda: packages)
        ),
        flPackage=lambda item: item,
        flItems=lambda: SimpleNamespace(
            notifyChangesApplied=lambda *args: sent.append(args)
        ),
    )
    backend = FontLabBackend(packages=[package])
    monkeypatch.setattr(backend, "_native", lambda: native)
    fid = backend._font_id(package)
    gid = backend._register((10, "glyph", 20), glyph, fid)
    backend._register((10, "layer", 30), layer, gid)
    font = Model(backend)._font(fid)
    font._begin_undo("Edit A")
    backend._changed = {("layer", 30): layer, ("glyph", 20): glyph}
    backend._prepared = dict(backend._changed)
    if state == "closed":
        package.isValid = False
    elif state == "unregistered":
        packages.clear()
    notes = []
    font._finish_undo(notes.append)
    assert font._undo_depth == 0 and not font._undo_pending
    assert backend._undo_name is None and backend._changed == backend._prepared == {}
    if state == "valid":
        assert sent == [("Edit A", [layer, glyph], True)]
        assert notes[0].code == "UNBALANCED_UNDO_CLOSED"
    else:
        assert not sent and notes[0].code == "UNBALANCED_UNDO_DISCARDED"


@pytest.mark.parametrize("kind", ["vanilla", "callback", "AppKit", "menu"])
@pytest.mark.parametrize("invoke", [False, True])
def test_q2_run_when_window_or_callback_retained_then_group_closes_later(
    tmp_path, kind, invoke
):
    ctx, session = make_session(tmp_path)
    if kind == "menu":
        from plugin_doubles import FakeHost

        class Host(FakeHost):
            def close(self):
                for token in list(self.registered):
                    self.remove(token)

        session._plugin_host = Host()
    prefix = "from GlyphsApp import Glyphs, UPDATEINTERFACE\ng = Glyphs.font.glyphs[0]\ng.beginUndo()\ng.layers[0].width = 777\n"
    finish = "def finish(sender):\n    g.layers[0].width = 888\n    g.endUndo()\n"
    if kind == "vanilla":
        retained = "from vanilla import Window, Button\nw = Window((200, 100))\nw.button = Button((10,10,80,20), 'Apply', callback=finish)\nw.open()\n"
    elif kind == "AppKit":
        retained = "from AppKit import NSWindow\nw = NSWindow.alloc().init()\nw.orderFront_(None)\n"
    elif kind == "menu":
        retained = "from GlyphsApp import NSMenuItem\nGlyphs.menu['EDIT_MENU'].append(NSMenuItem('Finish', finish))\n"
    else:
        retained = "Glyphs.addCallback(finish, UPDATEINTERFACE)\n"
    script = tmp_path / "later.py"
    script.write_text(prefix + finish + retained)
    try:
        ctx.run(script)
        assert session.model.font._undo_depth == 1
        assert session.backend.undo_events == [("begin", "Edit A")]
        assert not any(d.code == "UNBALANCED_UNDO_CLOSED" for d in ctx.diagnostics)
        if invoke:
            if kind == "callback":
                session.bridge.fire(ctx.globals["UPDATEINTERFACE"], None)
            else:
                ctx.wrap(ctx.globals["finish"])(None)
            assert session.model.font._undo_depth == 0
            assert session.model.font.glyphs[0].layers[0].width == 888
    finally:
        ctx.close()
    assert session.backend.undo_events == [("begin", "Edit A"), ("end", None)]


def test_l1_diagnostic_when_one_glyph_balanced_then_only_unbalanced_glyph_named(
    tmp_path,
):
    ctx, session = make_session(tmp_path)
    backend = session.backend
    backend.glyph_lists["font"] += (GlyphInfo("other", "B", ()),)
    backend.layers["other", "master"] = LayerInfo("other-layer", "master", 400)
    first, second = session.model.font.glyphs["A"], session.model.font.glyphs["B"]
    first.beginUndo()
    second.beginUndo()
    first.endUndo()
    ctx.close()
    note = next(d for d in ctx.diagnostics if d.code == "UNBALANCED_UNDO_CLOSED")
    assert "glyph B" in note.message and "glyph A" not in note.message


@pytest.mark.parametrize("font_failure", [False, True])
def test_l2_l3_lazy_globals_when_class_body_or_stale_font_then_resolve_at_use(
    tmp_path, monkeypatch, font_failure
):
    ctx, session = make_session(tmp_path)
    ctx.implicit_imports = ("GlyphsApp",)
    session.backend.current_layer_data["font"] = (("A", "Regular"),)
    calls = []
    original = session.backend.current_font_id

    def read():
        calls.append(True)
        if font_failure:
            raise StaleNativeObject("font")
        return original()

    monkeypatch.setattr(session.backend, "current_font_id", read)
    script = tmp_path / "globals.py"
    script.write_text(
        "print('line one')\nassert 'Font' in globals() and 'Layer' in globals()\n"
        "def later():\n    class Tool:\n        font = Font\n        layer = Layer\n    return Tool\n"
    )
    try:
        ctx.run(script)
        assert "line one" in "".join(ctx.output.strings) and not calls
        if font_failure:
            with pytest.raises(StaleNativeObject):
                ctx.wrap(ctx.globals["later"])()
        else:
            tool = ctx.wrap(ctx.globals["later"])()
            assert tool.font is session.model.font
            assert tool.layer is session.model.font.selectedLayers[0]
    finally:
        ctx.close()
