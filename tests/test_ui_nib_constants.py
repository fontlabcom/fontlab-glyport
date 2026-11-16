# this_file: tests/test_ui_nib_constants.py
"""The AppKit constants of the NIB classes reach scripts: a session exports the
``NS*`` ints of ``cocoa_views`` (and ``cocoa_menu``) and the kit's names."""

from ui_doubles import make_qt

from fontlab_glyport.ui import cocoa_views
from fontlab_glyport.ui.cocoa_views import make_appkit_classes

CONSTANTS = {
    "NSWindowStyleMaskTitled": 1,
    "NSWindowStyleMaskClosable": 2,
    "NSWindowStyleMaskMiniaturizable": 4,
    "NSWindowStyleMaskResizable": 8,
    "NSWindowStyleMaskUtilityWindow": 16,
    "NSUserInterfaceLayoutOrientationHorizontal": 0,
    "NSUserInterfaceLayoutOrientationVertical": 1,
    "NSImageScaleProportionallyDown": 0,
    "NSImageScaleAxesIndependently": 1,
    "NSImageScaleNone": 2,
    "NSImageScaleProportionallyUpOrDown": 3,
    "NSRadioModeMatrix": 0,
    "NSHighlightModeMatrix": 1,
    "NSListModeMatrix": 2,
    "NSTrackModeMatrix": 3,
}


def test_constants_when_session_collects_cocoa_views_ints_then_present():
    exported = {
        key: value
        for key, value in vars(cocoa_views).items()
        if key.startswith("NS") and isinstance(value, int)
    }
    assert {k: exported.get(k) for k in CONSTANTS} == CONSTANTS


def test_kit_when_built_then_edge_insets_helper_and_url_present():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    assert tuple(kit["NSEdgeInsetsMake"](1, 2, 3, 4)) == (1.0, 2.0, 3.0, 4.0)
    assert kit["NSURL"].fileURLWithPath_("/tmp/").path() == "/tmp"
    kit["close"]()
