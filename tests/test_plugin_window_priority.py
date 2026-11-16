# this_file: tests/test_plugin_window_priority.py
"""The actual plugin entry points retain Tool priority and deferred ownership."""

import pytest
from host_doubles import VIOLATIONS, QWidget
from test_plugins_fontlab_host import _qt_host


@pytest.mark.parametrize("route", ["panel", "Apply", "Cancel", "titlebar"])
def test_plugin_windows_request_priority_and_keep_caller_content_after_close(route):
    host, qt, errors = _qt_host()
    view, results = QWidget(), []
    if route == "panel":
        token = host.register_panel(view, "Report", 80, 400)
    else:
        token = host.run_dialog(view, "Filter", "Apply", results.append)
    window = view.parent
    assert window.flags == qt.QtCore.Qt.Tool | qt.QtCore.Qt.WindowStaysOnTopHint, (
        "Plugin panels and filters must request the same explicit tool priority"
    )
    if route in {"Apply", "Cancel"}:
        button = next(item for item in window.children if getattr(item, "text", "") == route)
        button.click()
        assert not window.deleted and not VIOLATIONS, "Defer emitter deletion past dispatch"
    elif route == "titlebar":
        window.close()
    else:
        host.remove(token)
    host._reaper.fire()
    assert window.deleted and not view.deleted and view.parent is None
    assert results == ([] if route == "panel" else [route == "Apply"])
    assert not errors and not VIOLATIONS and not host.has_items
