# this_file: tests/test_issue106_round3.py
"""Review and real-use regressions, with handwritten inputs and no native host."""

from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from ui_doubles_session import make_session

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import GSGlyph, GSNode, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend
from fontlab_glyport.notifications import NSNotification, notification_center_class


@pytest.mark.parametrize(
    "name",
    [
        "NSWindowWillCloseNotification",
        "NSApplicationDidBecomeActiveNotification",
        "NSControlTextDidChangeNotification",
        "TabDidOpenNotification",
        "GSTabChangedNotification",
        "mouseMovedNotification",
        "NSUnknownHostNotification",
    ],
)
def test_observer_when_host_name_has_no_bridge_then_registration_raises_precisely(name):
    bridge = FakeGlyphsBridge()
    center = notification_center_class(bridge).defaultCenter()
    with pytest.raises(UnsupportedCapability) as error:
        center.addObserver_selector_name_object_(
            SimpleNamespace(receive_=print), "receive:", name, None
        )
    assert error.value.capability == f"NSNotificationCenter.{name}"
    assert not bridge.subscriptions and not center._entries


def test_observer_when_unsupported_in_script_then_diagnostic_points_to_registration(
    tmp_path,
):
    ctx, _ = make_session(tmp_path)
    script = tmp_path / "observer.py"
    script.write_text(
        "from Foundation import NSNotificationCenter, NSWindowWillCloseNotification\n"
        "class Observer:\n    def receive_(self, n): pass\n"
        "NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(\n"
        "    Observer(), 'receive:', NSWindowWillCloseNotification, None)\n"
    )
    with pytest.raises(UnsupportedCapability) as error:
        ctx.run(script)
    assert (
        error.value.capability == "NSNotificationCenter.NSWindowWillCloseNotification"
    )
    assert error.value.location.path == str(script)
    assert error.value.location.line == 4
    ctx.close()


@pytest.mark.parametrize("name", ["GSRedrawEditView", "drawBotUserDefaultChanged"])
def test_observer_when_wildcard_or_known_script_only_name_then_local_posts_fire(name):
    bridge, calls = FakeGlyphsBridge(), []
    center = notification_center_class(bridge).defaultCenter()
    observer = SimpleNamespace(receive_=calls.append)
    center.addObserver_selector_name_object_(observer, "receive:", None, None)
    center.addObserver_selector_name_object_(observer, "receive:", name, None)
    center.postNotificationName_object_(name, None)
    assert len(calls) == 2
    assert bridge.calls == ([("redraw",)] if name == "GSRedrawEditView" else [])


def test_observer_when_no_bridge_injected_then_host_names_fail_without_silent_registration():
    center = notification_center_class().defaultCenter()
    with pytest.raises(UnsupportedCapability) as error:
        center.addObserver_selector_name_object_(
            SimpleNamespace(receive_=print), "receive:", "GSUpdateInterface", None
        )
    assert error.value.capability == "NSNotificationCenter.GSUpdateInterface"


def test_observer_when_host_or_local_delivery_then_context_is_entered_once():
    bridge, calls, entered = FakeGlyphsBridge(), [], []

    def wrap(callback):
        def invoke(*args):
            entered.append(True)
            return callback(*args)

        return invoke

    center = notification_center_class(bridge, wrap=wrap).defaultCenter()
    center.addObserver_selector_name_object_(
        SimpleNamespace(receive_=calls.append), "receive:", "GSUpdateInterface", None
    )
    bridge.fire("GSUpdateInterface", SimpleNamespace(object=lambda: None))
    center.postNotificationName_object_("GSUpdateInterface", None)
    assert len(calls) == len(entered) == 2


def test_font_change_when_only_interface_updates_then_no_font_change_notification():
    bridge, calls = FakeGlyphsBridge(), []
    center = notification_center_class(bridge).defaultCenter()
    center.addObserver_selector_name_object_(
        SimpleNamespace(receive_=calls.append),
        "receive:",
        "GlyphsFontDidChangeNotification",
        None,
    )
    bridge.fire("GSUpdateInterface", SimpleNamespace(object=lambda: None))
    assert not calls
    document = object()
    bridge.fire(
        "GSDocumentActivateNotification", SimpleNamespace(object=lambda: document)
    )
    assert len(calls) == 1 and calls[0].object() is document
    assert calls[0].name() == "GlyphsFontDidChangeNotification"


def test_notification_when_cocoa_constructors_used_then_name_sender_and_info_preserved():
    obj, info = object(), {"change": 2}
    notes = [
        NSNotification.alloc().initWithName_object_userInfo_("Local", obj, info),
        NSNotification.notificationWithName_object_("Local", obj),
        NSNotification.notificationWithName_object_userInfo_("Local", obj, info),
    ]
    assert all(n.name() == "Local" and n.object() is obj for n in notes)
    info["change"] = 3
    assert [n.userInfo() for n in notes] == [{"change": 2}, None, {"change": 2}]


def test_notification_constants_when_imported_then_same_strings_in_foundation_and_appkit(
    tmp_path,
):
    from fontlab_glyport.notifications import CONSTANTS

    ctx, _ = make_session(tmp_path)
    with ctx:
        for module in (ctx.import_module("Foundation"), ctx.import_module("AppKit")):
            for name in CONSTANTS:
                assert getattr(module, name) == name
    ctx.close()


@pytest.mark.parametrize(
    ("format", "args", "expected"),
    [
        ("100%%", (), "100%"),
        ("%%@ %@", ("value", "ignored"), "%@ value"),
        ("plain", (1, 2), "plain"),
        ("%@ %lld %.2f", (None, 7, 1.25), "(null) 7 1.25"),
        ("%*.*f", (6, 2, 1.25), "  1.25"),
        ("%2$@ %1$ld", (7, "value", "ignored"), "value 7"),
    ],
)
def test_nslog_when_printf_formatting_then_escapes_and_only_needed_arguments_used(
    format, args, expected, capsys
):
    from fontlab_glyport.cocoa_logging import NSLog

    NSLog(format, *args)
    assert capsys.readouterr().out == expected + "\n"


def test_nslog_when_missing_operand_or_unsupported_format_then_fails_precisely():
    from fontlab_glyport.cocoa_logging import NSLog

    with pytest.raises(TypeError, match="Not enough arguments"):
        NSLog("%@ %@", "only one")
    with pytest.raises(UnsupportedCapability) as error:
        NSLog("%p", object())
    assert error.value.capability == "NSLog.format.%p"


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("/", ((),)),
        ("/ /", ((),)),
        ("/\n/", ((), ())),
        ("/A//B", (("A", "B"),)),
        ("//A/ /B/", (("A", "B"),)),
        ("A/", (("A",),)),
    ],
)
def test_new_tab_when_empty_slash_tokens_then_skipped_without_unknown_glyph_error(
    text, lines
):
    backend = FakeBackend()
    font = Model(backend).font
    font.glyphs.append(GSGlyph("B"))
    font.newTab(text)
    assert backend.edit_texts[-1] == (font.id, lines)
    with pytest.raises(ValueError, match="No glyph named 'missing'"):
        font.newTab("/missing")


def test_node_when_connection_or_smooth_changes_then_constants_and_live_state_agree():
    backend = FakeBackend()
    model = Model(backend)
    module = make_glyphsapp_module(
        model, FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    assert module.GSSHARP == 0 and module.GSSMOOTH == 100
    live = model.font.glyphs[0].layers[0].paths[0].nodes[0]
    position, type = live.position, live.type
    for node in (GSNode(), live):
        assert node.connection == module.GSSHARP and not node.smooth
        node.connection = module.GSSMOOTH
        assert node.smooth and node.connection == module.GSSMOOTH
        node.smooth = False
        assert node.connection == module.GSSHARP
        node.smooth = True
        assert node.connection == module.GSSMOOTH
        node.connection = module.GSSHARP
        assert not node.smooth
        node.connection = 1
        assert node.connection == 1 and node.smooth is False
        node.smooth = module.GSSMOOTH
        assert node.connection == module.GSSHARP and node.smooth is False
    assert live.position == position and live.type == type
    backend.close_font(model.font.id)
    with pytest.raises(StaleNativeObject):
        live.connection = module.GSSMOOTH


def test_native_node_when_smooth_written_then_shape_owned_before_writing_clone(
    monkeypatch,
):
    backend = FontLabBackend(packages=[])
    from test_fontlab_backend_lazy import NodeFlags

    class Node(NodeFlags):
        def isOff(self):
            return False

        isCurve = isOff

    original, clone, shape, calls = (
        Node(),
        Node(),
        object(),
        [],
    )
    current = [original]
    backend._node_shapes["node"] = (shape, "layer")
    monkeypatch.setattr(backend, "_object", lambda token: current[0])
    monkeypatch.setattr(
        backend, "_prepare_layer", lambda lid: calls.append(("prepare", lid))
    )

    def own(lid, native):
        assert not original.smooth and native is shape
        # _own_shape now constructs first, then checkpoints and attaches.
        backend._prepare_layer(lid)
        calls.append(("own", lid))
        current[0] = clone

    monkeypatch.setattr(backend, "_own_shape", own)
    monkeypatch.setattr(
        backend,
        "_touch_layer",
        lambda lid: calls.append(("touch", lid, bool(clone.nodeState & 8))),
    )
    monkeypatch.setattr(
        backend,
        "_native",
        lambda: SimpleNamespace(flNode=Node),
    )
    backend.set_node_smooth("node", True)
    assert original.nodeState == 1 and clone.nodeState == 9
    assert calls == [("prepare", "layer"), ("own", "layer"), ("touch", "layer", True)]
