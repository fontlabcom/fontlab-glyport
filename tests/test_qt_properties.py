# this_file: tests/test_qt_properties.py
"""Keep the existing foreign reader path, metadata and live App delegation."""

import inspect
from types import SimpleNamespace

from fontlab_glyport.ui import application_windows


def test_qt_value_when_shared_then_old_callable_metadata_and_signature_remain(
    monkeypatch,
):
    import fontlabapp.qt.properties as _qt_properties

    reader = application_windows.qt_value
    assert reader.__name__ == reader.__qualname__ == "qt_value"
    assert reader.__module__ == "fontlab_glyport.ui.application_windows"
    assert tuple(inspect.signature(reader).parameters) == ("obj", "name")
    owner, result, calls = SimpleNamespace(), object(), []

    def value(obj, name):
        calls.append((obj, name))
        return result

    monkeypatch.setattr(_qt_properties, "value", value)
    assert reader(owner, "windowTitle") is result
    assert calls == [(owner, "windowTitle")]
