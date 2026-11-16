# this_file: tests/test_foundation.py
"""Foundation/AppKit values for Glyphs scripts (matrix plain-model,
external-process, private-selectors, custom-nsview, remote-plugin)."""

from types import SimpleNamespace

from host_doubles import LOG, VIOLATIONS, make_host_qt

from fontlab_glyport.foundation import (
    NSHeight,
    NSMaxX,
    NSMidY,
    NSMutableArray,
    NSMutableOrderedSet,
    NSMutableSet,
    class_from_string,
    qt_names,
    user_defaults_class,
)
from fontlab_glyport.ui.cocoa import NSMakeRect


def test_rect_accessors_when_rect_then_cocoa_geometry():
    rect = NSMakeRect(10, 20, 30, 40)
    assert (NSHeight(rect), NSMaxX(rect), NSMidY(rect)) == (40.0, 40.0, 40.0)


def test_collections_when_alloc_init_then_python_containers():
    ordered = NSMutableOrderedSet.alloc().initWithArray_(["b", "a", "b"])
    ordered.addObject_("a")
    ordered.insertObject_atIndex_("c", 0)
    assert ordered.array() == ["c", "b", "a"] and ordered.count() == 3
    items = NSMutableArray.new()
    items.addObject_(1)
    assert items.objectAtIndex_(0) == 1 and items.containsObject_(1)
    seen = NSMutableSet.alloc().init()
    seen.addObject_("x")
    seen.addObject_("x")
    assert seen.allObjects() == ["x"]


def test_user_defaults_when_glyphs_defaults_store_then_same_values_and_coercion():
    """mekkablue's prefBool/prefInt/prefFloat read NSUserDefaults for keys
    written through Glyphs.defaults: one store."""
    store = {"k.flag": "YES", "k.int": "3.7", "k.float": "2.5"}
    defaults = user_defaults_class(store).standardUserDefaults()
    assert defaults.boolForKey_("k.flag") is True
    assert defaults.integerForKey_("k.int") == 3
    assert defaults.doubleForKey_("k.float") == 2.5
    assert defaults.doubleForKey_("missing") == 0.0
    defaults.setObject_forKey_(True, "k.new")
    defaults.registerDefaults_({"k.new": False, "k.reg": 1})
    assert store["k.new"] is True and store["k.reg"] == 1
    defaults.setObject_forKey_(None, "k.new")
    assert "k.new" not in store and defaults.objectForKey_("k.new") is None


def test_class_from_string_when_unknown_then_none():
    lookup = class_from_string({"NSView": object})
    assert lookup("NSView") is object and lookup("GSAddParameterViewController") is None


def test_qt_names_when_timer_fires_and_closes_then_disconnected_outside_dispatch():
    LOG.clear()
    VIOLATIONS.clear()
    qt = make_host_qt()
    closers = []
    names = qt_names(qt, closers.append)
    fired = []
    target = SimpleNamespace(tick_=lambda timer: fired.append(timer.userInfo()))
    once = names[
        "NSTimer"
    ].scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.5, target, "tick:", "info", False
    )
    assert once._qt.interval == 500 and once._qt.active
    once._qt.fire()
    assert fired == ["info"] and not once.isValid()
    repeat = names["NSTimer"].scheduledTimerWithTimeInterval_repeats_block_(
        0.1, True, fired.append
    )
    repeat._qt.active = True
    repeat._qt.fire()
    assert fired[-1] is repeat and repeat.isValid()
    closers[0]()  # the context closes: every timer stopped and disconnected
    assert not repeat.isValid() and repeat._qt.timeout.slots == []
    assert once._qt.timeout.slots == [] and VIOLATIONS == []


def test_qt_names_when_pasteboard_then_application_clipboard_text():
    clip = SimpleNamespace(text="", setText=None, clear=None)
    clip.setText = lambda t: setattr(clip, "text", t)
    clip.clear = lambda: setattr(clip, "text", "")
    qt = make_host_qt()
    qt.QtGui.QApplication = SimpleNamespace(
        clipboard=lambda: SimpleNamespace(
            setText=clip.setText, clear=clip.clear, text=lambda: clip.text
        )
    )
    board = qt_names(qt, lambda f: None)["NSPasteboard"].generalPasteboard()
    board.clearContents()
    board.declareTypes_owner_(["NSStringPboardType"], None)
    assert board.setString_forType_("abc", "NSStringPboardType")
    assert board.stringForType_("NSStringPboardType") == "abc"
    board.clearContents()
    assert board.stringForType_("NSStringPboardType") is None


def test_qt_names_when_screens_then_cocoa_frames_flipped_to_bottom_left():
    """NSScreen frames use Cocoa coordinates: origin at the bottom-left of the
    primary screen, y up (Cape Weightor centres its window in visibleFrame)."""

    def rect(x, y, w, h):
        return SimpleNamespace(
            x=lambda: x, y=lambda: y, width=lambda: w, height=lambda: h
        )

    primary = SimpleNamespace(
        geometry=lambda: rect(0, 0, 1440, 900),
        availableGeometry=lambda: rect(0, 25, 1440, 875),
    )
    second = SimpleNamespace(
        geometry=lambda: rect(1440, -300, 1920, 1200),
        availableGeometry=lambda: rect(1440, -300, 1920, 1200),
    )
    qt = make_host_qt()
    qt.QtGui.QApplication = SimpleNamespace(screens=lambda: [primary, second])
    screen = qt_names(qt, lambda f: None)["NSScreen"]
    main = screen.mainScreen()
    assert main.frame() == ((0, 0), (1440, 900))
    assert main.visibleFrame() == ((0, 0), (1440, 875))  # menu bar removed at the top
    assert [s.frame() for s in screen.screens()][1] == ((1440, 0), (1920, 1200))


def test_date_union_and_run_loop_values():
    """remote-plugin (AIFontGenerator): NSDate deadlines, NSUnionRect, timers
    added to the current run loop (already scheduled on Qt's loop)."""
    from fontlab_glyport.foundation import NSDate, NSRunLoop, NSUnionRect
    from fontlab_glyport.ui.cocoa import NSMakeRect

    later = NSDate.dateWithTimeIntervalSinceNow_(2.0)
    assert 1.5 < later.timeIntervalSinceNow() <= 2.0
    assert NSDate.distantPast().timeIntervalSinceNow() < 0
    union = NSUnionRect(NSMakeRect(0, 0, 10, 10), NSMakeRect(5, -5, 10, 10))
    assert union == ((0, -5), (15, 15))
    assert (
        NSRunLoop.currentRunLoop().addTimer_forMode_(object(), "kCFRunLoopCommonModes")
        is None
    )


def test_application_when_next_event_then_qt_events_processed_and_none():
    """plugin.py:91-115 pumps events while waiting: processEvents, no exec()."""
    calls = []
    qt = make_host_qt()
    qt.QtGui.QApplication = SimpleNamespace(processEvents=lambda: calls.append(1))
    app = qt_names(qt, lambda f: None)["NSApplication"].sharedApplication()
    assert (
        app.nextEventMatchingMask_untilDate_inMode_dequeue_(0, None, "mode", True)
        is None
    )
    assert calls == [1]


def test_deferred_classes_when_imported_then_resolve_and_fail_only_on_use():
    """remote-plugin (AIFontGenerator) imports NSBitmapImageRep at module
    level but renders only when generating: the import resolves, the first use
    raises UnsupportedCapability naming the member."""
    import pytest

    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.foundation import CONSTANTS, deferred_class

    rep = deferred_class("AppKit", "NSBitmapImageRep")
    assert rep.__name__ == "NSBitmapImageRep"
    with pytest.raises(UnsupportedCapability) as caught:
        rep.alloc()
    assert caught.value.capability == "AppKit.NSBitmapImageRep.alloc"
    assert (CONSTANTS["NSPNGFileType"], CONSTANTS["NSCenterTextAlignment"]) == (4, 2)
    assert CONSTANTS["NSAlertFirstButtonReturn"] == 1000
