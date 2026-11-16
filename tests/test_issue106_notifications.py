# this_file: tests/test_issue106_notifications.py
"""Synchronous notification contracts with an in-memory bridge only."""

from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedCapability


def test_center_when_posted_then_synchronous_name_object_and_user_info_filters():
    from fontlab_glyport.notifications import notification_center_class

    cls = notification_center_class()
    center = cls.defaultCenter()
    assert cls.defaultCenter() is center
    first, other, calls = object(), object(), []
    center.postNotificationName_object_("Changed", None)
    all_events = SimpleNamespace(receive_=lambda n: calls.append(("all", n)))
    selected = SimpleNamespace(receive_=lambda n: calls.append(("selected", n)))
    center.addObserver_selector_name_object_(all_events, b"receive:", None, None)
    center.addObserver_selector_name_object_(selected, "receive:", "Changed", first)
    center.postNotificationName_object_userInfo_("Changed", first, {"count": 3})
    assert [kind for kind, _ in calls] == ["all", "selected"]
    assert calls[0][1].name() == "Changed" and calls[0][1].object() is first
    assert calls[0][1].userInfo() == {"count": 3}
    calls.clear()
    center.postNotificationName_object_("Changed", other)
    assert [kind for kind, _ in calls] == ["all"]
    assert calls[0][1].userInfo() is None
    center.removeObserver_(all_events)
    center.removeObserver_name_object_(selected, "Changed", first)
    center.postNotificationName_object_("Changed", first)
    assert len(calls) == 1


def test_center_when_observer_changes_registrations_then_reentrant_posts_are_synchronous():
    from fontlab_glyport.notifications import notification_center_class

    center = notification_center_class().defaultCenter()
    calls = []

    def receive(n):
        calls.append(n.name())
        center.removeObserver_(observer)
        center.postNotificationName_object_("Nested", None)

    observer = SimpleNamespace(receive_=receive)
    center.addObserver_selector_name_object_(observer, "receive:", None, None)
    center.postNotificationName_object_("First", None)
    assert calls == ["First"]


@pytest.mark.parametrize(
    "name",
    [
        "GSUpdateInterface",
        "GSDocumentWasOpenedNotification",
        "GSDocumentWillCloseNotification",
        "GlyphsFontDidChangeNotification",
    ],
)
def test_center_when_glyphs_bridge_fires_then_routes_once_and_unsubscribes(name):
    from fontlab_glyport.notifications import notification_center_class

    bridge, calls, closers = FakeGlyphsBridge(), [], []
    center = notification_center_class(bridge, on_close=closers.append).defaultCenter()
    observer = SimpleNamespace(receive_=calls.append)
    center.addObserver_selector_name_object_(observer, "receive:", name, None)
    center.addObserver_selector_name_object_(observer, "receive:", name, None)
    assert len(bridge.subscriptions) == 1
    event = next(iter(bridge.subscriptions.values()))[0]
    obj = object()
    bridge.fire(event, SimpleNamespace(object=lambda: obj))
    assert len(calls) == 2 and calls[0].name() == name and calls[0].object() is obj
    center.removeObserver_(observer)
    assert not bridge.subscriptions
    closers[0]()
    closers[0]()


def test_center_when_bridge_cannot_supply_event_then_registration_fails_explicitly():
    from fontlab_glyport.notifications import notification_center_class

    class Bridge(FakeGlyphsBridge):
        def subscribe(self, event, callback):
            raise UnsupportedCapability("not available", capability="host.event")

    center = notification_center_class(Bridge()).defaultCenter()
    with pytest.raises(UnsupportedCapability, match="not available"):
        center.addObserver_selector_name_object_(
            SimpleNamespace(receive_=print), "receive:", "GSUpdateInterface", None
        )


def test_center_when_context_closes_then_host_delivery_and_observer_references_are_removed(
    tmp_path,
):
    ctx, session = make_session(tmp_path)
    script = tmp_path / "notifications.py"
    script.write_text(
        "from Foundation import NSNotificationCenter, NSLog\n"
        "from AppKit import NSNotificationCenter as Other\n"
        "assert Other is NSNotificationCenter\n"
        "class Observer:\n"
        "    def changed_(self, n): NSLog('%@ %ld', n.name(), 7)\n"
        "observer = Observer()\n"
        "center = NSNotificationCenter.defaultCenter()\n"
        "center.addObserver_selector_name_object_(observer, 'changed:', 'GSUpdateInterface', None)\n"
        "center.postNotificationName_object_('GSUpdateInterface', None)\n"
    )
    ctx.run(script)
    assert "GSUpdateInterface 7" in "".join(ctx.output.strings)
    session.bridge.fire("GSUpdateInterface", SimpleNamespace(object=lambda: None))
    assert "".join(ctx.output.strings).count("GSUpdateInterface 7") == 2
    center = ctx.globals["center"]
    ctx.close()
    assert not session.bridge.subscriptions
    with pytest.raises(RuntimeError, match="closed"):
        center.postNotificationName_object_("Local", None)


def test_nslog_when_script_runs_then_same_route_as_print_and_formatting(tmp_path):
    ctx, _ = make_session(tmp_path)
    script = tmp_path / "logging.py"
    script.write_text(
        "from Foundation import NSLog\n"
        "print('before')\n"
        "NSLog('plain 50%')\n"
        "NSLog('%@ %ld %.2f %%', 'value', 3, 1.25)\n"
    )
    ctx.run(script)
    assert "".join(ctx.output.strings) == "before\nplain 50%\nvalue 3 1.25 %\n"
    ctx.close()


def test_center_when_removal_fails_then_keeps_token_and_observer_for_retry():
    from fontlab_glyport.notifications import notification_center_class

    class Bridge(FakeGlyphsBridge):
        failing = True

        def remove(self, token):
            if self.failing:
                raise RuntimeError("disconnect failed")
            super().remove(token)

    bridge, calls = Bridge(), []
    center = notification_center_class(bridge).defaultCenter()
    observer = SimpleNamespace(receive_=calls.append)
    center.addObserver_selector_name_object_(
        observer, "receive:", "GSUpdateInterface", None
    )
    with pytest.raises(RuntimeError, match="disconnect failed"):
        center.removeObserver_(observer)
    bridge.fire("GSUpdateInterface", SimpleNamespace(object=lambda: None))
    assert len(calls) == 1 and len(bridge.subscriptions) == 1
    bridge.failing = False
    center.removeObserver_(observer)
    assert not bridge.subscriptions
    center.close()


def test_center_when_callback_raises_then_post_propagates_and_removal_still_works():
    from fontlab_glyport.notifications import notification_center_class

    center = notification_center_class().defaultCenter()

    def fail(note):
        raise ValueError("observer failed")

    observer = SimpleNamespace(receive_=fail)
    center.postNotificationName_object_("Local", None)
    center.addObserver_selector_name_object_(observer, "receive:", "Local", None)
    with pytest.raises(ValueError, match="observer failed"):
        center.postNotificationName_object_("Local", None)
    center.removeObserver_(observer)
    center.postNotificationName_object_("Local", None)


def test_center_when_redraw_notification_posted_then_existing_bridge_redraw_called():
    from fontlab_glyport.notifications import notification_center_class

    bridge = FakeGlyphsBridge()
    center = notification_center_class(bridge).defaultCenter()
    center.postNotificationName_object_("GSRedrawEditView", None)
    assert bridge.calls == [("redraw",)]


def test_center_when_name_was_locally_posted_then_later_observers_receive_local_posts():
    from fontlab_glyport.notifications import notification_center_class

    bridge, calls = FakeGlyphsBridge(), []
    center = notification_center_class(bridge).defaultCenter()
    observer = SimpleNamespace(receive_=calls.append)
    center.postNotificationName_object_("TabDidOpenNotification", None)
    center.addObserver_selector_name_object_(
        observer, "receive:", "TabDidOpenNotification", None
    )
    assert not bridge.subscriptions, "No unsupported native tab signal is claimed"
    center.postNotificationName_object_("TabDidOpenNotification", None)
    assert len(calls) == 1 and calls[0].name() == "TabDidOpenNotification"
    center.close()
