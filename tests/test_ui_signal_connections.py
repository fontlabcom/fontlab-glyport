# this_file: tests/test_ui_signal_connections.py
"""Shared App primitives keep each foreign owner's teardown and error policy."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.ui import cocoa_views, vanilla


@pytest.fixture(params=["cocoa", "vanilla"])
def owner(request):
    module = cocoa_views if request.param == "cocoa" else vanilla
    cls = module.NSView if request.param == "cocoa" else module._Control
    instance = object.__new__(cls)
    instance._slots = []
    errors = []
    sink = lambda error, sender: errors.append((error, sender))
    instance._env = SimpleNamespace(sink=sink, dispatch=SimpleNamespace(sink=sink))
    instance._container = False
    return module, instance, errors


def test_track_when_either_adapter_then_uses_shared_exact_pair_primitive(
    owner, monkeypatch
):
    module, instance, _ = owner
    pairs = []
    monkeypatch.setattr(module, "track_connection", lambda *args: pairs.append(args))
    signal, slot = object(), lambda: None
    instance._track(signal, slot)
    assert pairs == [(instance._slots, signal, slot)]


def test_disconnect_when_either_adapter_then_passes_same_owner_to_its_sink(
    owner, monkeypatch
):
    module, instance, errors = owner
    failure = RuntimeError("disconnect failed")
    seen = []

    def drain(slots, report):
        seen.append(slots)
        report(failure)

    monkeypatch.setattr(module, "disconnect_connections", drain)
    instance._disconnect()
    assert seen == [instance._slots] and errors == [(failure, instance)]


def test_disconnect_when_shared_drain_returns_then_owner_cleanup_follows(
    owner, monkeypatch
):
    module, instance, _ = owner
    order = []
    monkeypatch.setattr(
        module, "disconnect_connections", lambda *args: order.append("slots")
    )
    if module is cocoa_views:
        instance._container = True

        class Widget:
            def __setattr__(self, name, value):
                assert name == "_owner" and value is None
                order.append("owner")

        instance._qt = Widget()
    else:
        instance._ns = SimpleNamespace(_teardown=lambda: order.append("owner"))
    instance._disconnect()
    assert order == ["slots", "owner"]


@pytest.mark.parametrize("error", [RuntimeError("sink"), KeyboardInterrupt()])
def test_disconnect_when_shared_drain_raises_then_owner_cleanup_stays_unattempted(
    owner, monkeypatch, error
):
    module, instance, _ = owner

    def fail(*args):
        raise error

    monkeypatch.setattr(module, "disconnect_connections", fail)
    instance._container = True
    widget = SimpleNamespace(_owner=instance)
    instance._qt = widget
    instance._ns = SimpleNamespace(_teardown=pytest.fail)
    with pytest.raises(type(error)) as caught:
        instance._disconnect()
    assert caught.value is error and widget._owner is instance
