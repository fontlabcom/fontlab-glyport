# this_file: tests/test_issue106_round11_adapters.py
"""Geometry helper exports and queued alert answers over adapter doubles."""

import pytest
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedCapability


def test_f51_helpers_are_exported_and_bootstrapped_into_scripts(tmp_path):
    context, _ = make_session(tmp_path)
    context.implicit_imports = ("GlyphsApp",)
    path = tmp_path / "geometry.py"
    path.write_text("result = distance(GSNode((1, 2)), (4, 6))\n")
    try:
        context.run(path)
        assert context.globals["result"] == 5
        with context:
            module = context.import_module("GlyphsApp")
            for name in (
                "distance",
                "addPoints",
                "subtractPoints",
                "scalePoint",
                "divideCurve",
                "pointOnLine",
                "pointOnQuadratic",
            ):
                assert name in module.__all__
            assert module.distance((2, 3), (2, 3)) == 0
            assert module.addPoints(module.GSNode((1, 2)), (4, 6)) == (5, 8)
            assert module.subtractPoints((4, 6), module.GSNode((1, 2))) == (3, 4)
            assert module.scalePoint(module.GSNode((1, 2)), -2) == (-2, -4)
            assert module.pointOnLine((0, 0), (8, 4), 0.25) == (2, 1)
            assert module.pointOnQuadratic((0, 0), (4, 8), (8, 0), 0.5) == (4, 4)
            points = [(0, 0), (0, 8), (8, 8), (8, 0)]
            assert module.divideCurve(*points, 0.5) == (
                points[0],
                (0, 4),
                (2, 6),
                (4, 6),
                (6, 6),
                (8, 4),
                points[3],
            )
            for t in (0, 1, -0.5, 1.5):
                divided = module.divideCurve(*points, t)
                assert divided[0] is points[0] and divided[-1] is points[-1]
                assert len(divided) == 7
            # The Glyphs 4 module exports pointOnLine/pointOnQuadratic, but
            # bezierPoint is a path selector, not a module helper.
            assert "bezierPoint" not in module.__all__
            with pytest.raises(UnsupportedCapability) as caught:
                _ = module.bezierPoint
            assert caught.value.capability == "GlyphsApp.bezierPoint"
    finally:
        context.close()


def test_f43_alerts_queue_sets_accessory_and_returns_matching_button(tmp_path):
    context, session = make_session(tmp_path)
    session.bridge.answers = {"alerts": [["OK", "1"], ["Cancel", "2"], ["OK", "50"]]}
    try:
        with context:
            kit = context.import_module("AppKit")
            for title, text, code in (
                ("OK", "1", 1000),
                ("Cancel", "2", 1001),
                ("OK", "50", 1000),
            ):
                alert = kit.NSAlert.alloc().init()
                alert.addButtonWithTitle_("OK")
                alert.addButtonWithTitle_("Cancel")
                field = kit.NSTextField.alloc().init()
                alert.setAccessoryView_(field)
                assert alert.runModal() == code, title
                assert field.stringValue() == text
            assert session.bridge.answers["alerts"] == []
            with pytest.raises(UnsupportedCapability) as caught:
                alert.runModal()
            assert caught.value.capability == "NSAlert.runModal"
    finally:
        context.close()


def test_f43_alert_queue_rejects_bad_answers_without_consuming_or_opening_modal(
    tmp_path,
):
    context, session = make_session(tmp_path)
    session.bridge.answers = {"alerts": [["Missing", "text"]], "alert": 0}
    try:
        with context:
            kit = context.import_module("AppKit")
            alert = kit.NSAlert.alloc().init()
            alert.addButtonWithTitle_("OK")
            with pytest.raises(ValueError, match="not present"):
                alert.runModal()
            assert session.bridge.answers["alerts"] == [["Missing", "text"]]
            session.bridge.answers["alerts"] = [["OK"]]
            with pytest.raises(ValueError, match="accessory text"):
                alert.runModal()
            session.bridge.answers["alerts"] = []
            with pytest.raises(UnsupportedCapability):
                alert.runModal()  # an exhausted queue does not reuse singular 'alert'
            del session.bridge.answers["alerts"]
            assert alert.runModal() == 1000  # preserve the existing singular answer API
    finally:
        context.close()
