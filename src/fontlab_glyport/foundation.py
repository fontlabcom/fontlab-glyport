# this_file: src/fontlab_glyport/foundation.py
"""Foundation/AppKit values that Glyphs scripts import, without PyObjC.

Qt-free: geometry functions, collection classes, constants, and
``NSUserDefaults`` over glyport's ``Glyphs.defaults`` store (Glyphs keeps its
defaults in the same NSUserDefaults domain, so ``Glyphs.defaults[k]`` and
``NSUserDefaults.standardUserDefaults().boolForKey_(k)`` agree). Qt-backed
names (``NSPasteboard``, ``NSTimer``, ``NSScreen``) are built by ``qt_names(qt, on_close)``.
Referenced by glyphsapp/fontlab_session.py (``_cocoa_names``).
"""

from collections.abc import Callable, MutableMapping
from typing import Any

from .affine import NSAffineTransformStruct
from .foundation_predicate import NSPredicate
from .glyphsapp.defaults import as_bool, as_int
from .ui.cocoa import NSMakePoint, NSMakeRect, NSMakeSize, NSObject, unsupported

# AppKit/Foundation enum values (Apple SDK headers).
CONSTANTS = {
    "NSImageColorSyncProfileData": "NSImageColorSyncProfileData",
    "NSMiniControlSize": 2,
    "NSSmallControlSize": 1,
    "NSRegularControlSize": 0,
    "NSEventMaskFlagsChanged": 1 << 12,
    "NSDeviceWhiteColorSpace": "NSDeviceWhiteColorSpace",
    "NSImageLeading": 7,  # NSCellImagePosition
    "NSLineBreakByClipping": 2,  # NSLineBreakMode
    "NSMaxXEdge": 2,  # NSRectEdge
    "NSChangeCleared": 2,  # NSDocumentChangeType
    "NSStringPboardType": "NSStringPboardType",
    "NSPasteboardTypeString": "public.utf8-plain-text",
    "NSEventMaskAny": 0xFFFFFFFFFFFFFFFF,  # NSUIntegerMax
    "NSPNGFileType": 4,  # NSBitmapImageFileType
    "NSCompositingOperationSourceOver": 2,
    "NSBackingStoreBuffered": 2,
    "NSCenterTextAlignment": 2,  # macOS NSTextAlignmentCenter
    "NSModalPanelWindowLevel": 8,
    "NSAlertFirstButtonReturn": 1000,
    "NSAlertSecondButtonReturn": 1001,
    "NSAlertThirdButtonReturn": 1002,
    "NSControlStateValueOff": 0,
    "NSControlStateValueOn": 1,
    "NSRunLoopCommonModes": "kCFRunLoopCommonModes",
    "NSDefaultRunLoopMode": "kCFRunLoopDefaultMode",
    "NSTextAlignmentLeft": 0,
    "NSTextAlignmentRight": 1,
    "NSTextAlignmentCenter": 2,
    "NSTextAlignmentJustified": 3,
    "NSTextAlignmentNatural": 4,
    "NSFontWeightRegular": 0.0,
    "NSAlertStyleWarning": 0,
    "NSAlertStyleInformational": 1,
    "NSAlertStyleCritical": 2,
}


class NSValue(NSObject):
    @classmethod
    def valueWithPoint_(cls, value):
        result = cls.alloc().init()
        result._value, result._kind = NSMakePoint(*value), "point"
        return result

    @classmethod
    def valueWithSize_(cls, value):
        result = cls.alloc().init()
        result._value, result._kind = NSMakeSize(*value), "size"
        return result

    @classmethod
    def valueWithRect_(cls, value):
        result = cls.alloc().init()
        result._value, result._kind = NSMakeRect(*value[0], *value[1]), "rect"
        return result

    def _unbox(self, kind):
        if self.__dict__.get("_kind") != kind:
            raise unsupported("NSValue." + kind + "Value")
        return self._value

    def pointValue(self):
        return self._unbox("point")

    def sizeValue(self):
        return self._unbox("size")

    def rectValue(self):
        return self._unbox("rect")


# --- NSRect accessors (rect = origin, size, as ui.cocoa.NSRect) -------------
def NSWidth(rect) -> float:
    return float(rect[1][0])


def NSHeight(rect) -> float:
    return float(rect[1][1])


def NSMinX(rect) -> float:
    return float(rect[0][0])


def NSMinY(rect) -> float:
    return float(rect[0][1])


def NSMaxX(rect) -> float:
    return NSMinX(rect) + NSWidth(rect)


def NSMaxY(rect) -> float:
    return NSMinY(rect) + NSHeight(rect)


def NSMidX(rect) -> float:
    return NSMinX(rect) + NSWidth(rect) / 2


def NSMidY(rect) -> float:
    return NSMinY(rect) + NSHeight(rect) / 2


def NSUnionRect(a, b):
    """The smallest rect containing both (an empty rect is ignored)."""
    if NSWidth(a) <= 0 or NSHeight(a) <= 0:
        return b
    if NSWidth(b) <= 0 or NSHeight(b) <= 0:
        return a
    x0, y0 = min(NSMinX(a), NSMinX(b)), min(NSMinY(a), NSMinY(b))
    x1, y1 = max(NSMaxX(a), NSMaxX(b)), max(NSMaxY(a), NSMaxY(b))
    return NSMakeRect(x0, y0, x1 - x0, y1 - y0)


def NSInsetRect(rect, dx, dy):
    return NSMakeRect(
        NSMinX(rect) + dx,
        NSMinY(rect) + dy,
        NSWidth(rect) - 2 * dx,
        NSHeight(rect) - 2 * dy,
    )


def NSOffsetRect(rect, dx, dy):
    return NSMakeRect(
        NSMinX(rect) + dx, NSMinY(rect) + dy, NSWidth(rect), NSHeight(rect)
    )


def NSPointInRect(point, rect) -> bool:
    """Cocoa's half-open test, as ``NSMouseInRect(point, rect, flipped=YES)``:
    the max edges are outside."""
    x, y = point[0], point[1]
    return NSMinX(rect) <= x < NSMaxX(rect) and NSMinY(rect) <= y < NSMaxY(rect)


def NSContainsRect(outer, inner) -> bool:
    """Cocoa: a non-empty ``inner`` that does not extend beyond ``outer``."""
    return (
        NSWidth(inner) > 0
        and NSHeight(inner) > 0
        and NSMinX(outer) <= NSMinX(inner)
        and NSMaxX(inner) <= NSMaxX(outer)
        and NSMinY(outer) <= NSMinY(inner)
        and NSMaxY(inner) <= NSMaxY(outer)
    )


class NSDate:
    """A point in time (``time.monotonic`` based: only intervals matter)."""

    def __init__(self, at: float):
        self._at = at

    @classmethod
    def date(cls):
        import time

        return cls(time.monotonic())

    @classmethod
    def dateWithTimeIntervalSinceNow_(cls, seconds):
        import time

        return cls(time.monotonic() + float(seconds))

    @classmethod
    def distantPast(cls):
        return cls(float("-inf"))

    @classmethod
    def distantFuture(cls):
        return cls(float("inf"))

    def timeIntervalSinceNow(self) -> float:
        import time

        return self._at - time.monotonic()


class NSRunLoop:
    """Timers already run on Qt's event loop: adding one is a no-op."""

    @classmethod
    def currentRunLoop(cls):
        return cls()

    mainRunLoop = currentRunLoop

    def addTimer_forMode_(self, timer, mode) -> None:
        return None


GEOMETRY = {
    f.__name__: f
    for f in (
        NSWidth,
        NSHeight,
        NSMinX,
        NSMinY,
        NSMaxX,
        NSMaxY,
        NSMidX,
        NSMidY,
        NSUnionRect,
        NSInsetRect,
        NSOffsetRect,
        NSPointInRect,
        NSContainsRect,
    )
}
GEOMETRY.update(
    NSDate=NSDate, NSRunLoop=NSRunLoop, NSAffineTransformStruct=NSAffineTransformStruct
)


# --- collections -------------------------------------------------------------
class _Alloc:
    """``Cls.alloc().init...()`` and ``Cls.new()`` as Python construction."""

    @classmethod
    def alloc(cls):
        return cls()

    @classmethod
    def new(cls):
        return cls()

    def init(self):
        return self

    def count(self) -> int:
        return len(self)

    def containsObject_(self, item) -> bool:
        return item in self


class NSArray(_Alloc, list):
    @classmethod
    def array(cls):
        return cls()

    @classmethod
    def arrayWithArray_(cls, items):
        return cls(items)

    def initWithArray_(self, items):
        self[:] = list(items)
        return self

    def filteredArrayUsingPredicate_(self, predicate):
        return NSArray(item for item in self if predicate.evaluateWithObject_(item))

    def objectAtIndex_(self, index):
        return self[index]


class NSMutableArray(NSArray):
    def addObject_(self, item):
        self.append(item)

    def removeObject_(self, item):
        while item in self:
            self.remove(item)

    def insertObject_atIndex_(self, item, index):
        self.insert(index, item)


class NSDictionary(_Alloc, dict):
    @classmethod
    def dictionaryWithContentsOfFile_(cls, path):
        import plistlib

        try:
            with open(path, "rb") as source:
                data = plistlib.load(source)
        except (OSError, ValueError, plistlib.InvalidFileException):
            return None
        return cls(data) if isinstance(data, dict) else None

    @classmethod
    def dictionaryWithDictionary_(cls, values):
        return cls(values)

    def objectForKey_(self, key):
        return self.get(key)

    def allKeys(self):
        return NSArray(self)

    def allValues(self):
        return NSArray(self.values())


class NSIndexPath(tuple):
    @classmethod
    def indexPathWithIndexes_length_(cls, indexes, length):
        return cls(tuple(indexes)[:length])

    def length(self):
        return len(self)

    def indexAtPosition_(self, position):
        if position < 0:
            raise IndexError(position)
        return self[position]


class NSMutableSet(_Alloc, set):
    @classmethod
    def set(cls):
        return cls()

    def addObject_(self, item):
        self.add(item)

    def removeObject_(self, item):
        self.discard(item)

    def allObjects(self) -> list:
        return list(self)


class NSMutableOrderedSet(NSMutableArray):
    """Insertion-ordered, without duplicates."""

    @classmethod
    def orderedSet(cls):
        return cls()

    def initWithArray_(self, items):
        self[:] = list(dict.fromkeys(items))
        return self

    def addObject_(self, item):
        if item not in self:
            self.append(item)

    def insertObject_atIndex_(self, item, index):
        if item in self:
            self.remove(item)
        self.insert(index, item)

    def array(self) -> list:
        return list(self)


COLLECTIONS = {
    "NSValue": NSValue,
    "NSPredicate": NSPredicate,
    "NSIndexPath": NSIndexPath,
    **{
        c.__name__: c
        for c in (
            NSArray,
            NSMutableArray,
            NSMutableSet,
            NSMutableOrderedSet,
            NSDictionary,
        )
    },
}

# C value wrappers are Python types, but not Objective-C classes.
STRUCT_NAMES = {"NSPoint", "NSSize", "NSRect", "NSRange", "NSAffineTransformStruct"}


# --- names that resolve on import and fail on use --------------------------------
def deferred_class(module: str, name: str) -> type:
    """A class a script imports at module level but glyport does not provide:
    the import resolves, and the first member use raises
    UnsupportedCapability naming ``module.name.member``."""
    from .errors import UnsupportedCapability

    class _Deferred(type):
        def __getattr__(cls, member):
            if member.startswith("__"):
                raise AttributeError(member)
            raise UnsupportedCapability(
                f"Unsupported capability: {module}.{name}.{member}",
                capability=f"{module}.{name}.{member}",
            )

    return _Deferred(name, (), {"__module__": module})


# NSBitmapImageRep: AIFontGenerator renders glyph images only while generating;
# NSAlert/NSButtonCell: its dialogs (function-level imports).
DEFERRED = ("NSBitmapImageRep", "NSAlert", "NSButtonCell")


# --- user defaults -------------------------------------------------------------
def user_defaults_class(store: MutableMapping[str, Any]) -> type:
    """``NSUserDefaults`` whose standard instance reads and writes ``store``."""

    class NSUserDefaults:
        @classmethod
        def standardUserDefaults(cls):
            return cls()

        def objectForKey_(self, key):
            return store.get(str(key))

        def stringForKey_(self, key):
            value = store.get(str(key))
            return value if isinstance(value, str) else None

        def boolForKey_(self, key) -> bool:
            return as_bool(store.get(str(key)))

        def integerForKey_(self, key) -> int:
            return as_int(store.get(str(key)))

        def doubleForKey_(self, key) -> float:
            value = store.get(str(key))
            if isinstance(value, bool):
                return float(value)
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        floatForKey_ = doubleForKey_

        def setObject_forKey_(self, value, key):
            if value is None:
                store.pop(str(key), None)
            else:
                store[str(key)] = value

        setBool_forKey_ = setInteger_forKey_ = setDouble_forKey_ = setObject_forKey_
        setFloat_forKey_ = setObject_forKey_

        def removeObjectForKey_(self, key):
            store.pop(str(key), None)

        def registerDefaults_(self, values):
            for key, value in dict(values).items():
                store.setdefault(str(key), value)

        def synchronize(self) -> bool:
            return True

    return NSUserDefaults


def class_from_string(classes: dict[str, type]) -> Callable[[str], type | None]:
    """``NSClassFromString``: a class glyport provides, else None (as Cocoa
    returns nil for a class that is not loaded)."""

    def NSClassFromString(name):
        return classes.get(str(name))

    return NSClassFromString


# --- Qt-backed -----------------------------------------------------------------
def qt_names(qt: Any, on_close: Callable[[Callable[[], object]], object]) -> dict:
    """``NSPasteboard`` (the application clipboard, plain text only) and
    ``NSTimer`` (QTimer; every timer is stopped and disconnected on close)."""
    from fontlabapp.qt.properties import (
        value,
    )  # PythonQt: QScreen geometry is a property

    qtgui, qtcore = qt.QtGui, qt.QtCore
    timers: list = []

    class NSPasteboard:
        @classmethod
        def generalPasteboard(cls):
            return cls()

        def clearContents(self) -> int:
            qtgui.QApplication.clipboard().clear()
            return 0

        def declareTypes_owner_(self, types, owner) -> int:
            return 0

        def setString_forType_(self, text, kind) -> bool:
            qtgui.QApplication.clipboard().setText(str(text))
            return True

        def stringForType_(self, kind):
            text = qtgui.QApplication.clipboard().text()
            return text or None

    class NSTimer:
        def __init__(self, interval, callback, repeats):
            self._callback, self._repeats = callback, bool(repeats)
            self._valid = self._connected = True
            self._qt = qtcore.QTimer()
            self._qt.setInterval(int(max(float(interval), 0) * 1000))
            self._qt.setSingleShot(not repeats)
            self._qt.timeout.connect(self._fire)
            timers.append(self)

        def _fire(self):
            if not self._valid:
                return
            if not self._repeats:  # disconnected later: never inside its own dispatch
                self._valid = False
                self._qt.stop()
            self._callback(self)

        @classmethod
        def scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            cls, interval, target, selector, info, repeats
        ):
            name = str(selector).replace(":", "_")
            timer = cls(interval, lambda t: getattr(target, name)(t), repeats)
            timer.info = info
            timer._qt.start()
            return timer

        @classmethod
        def scheduledTimerWithTimeInterval_repeats_block_(
            cls, interval, repeats, block
        ):
            timer = cls(interval, block, repeats)
            timer._qt.start()
            return timer

        def userInfo(self):
            return getattr(self, "info", None)

        def isValid(self) -> bool:
            return self._valid

        def invalidate(self):
            self._valid = False
            self._qt.stop()

        def _disconnect(self):
            self.invalidate()
            if self._connected:
                self._connected = False
                self._qt.timeout.disconnect(self._fire)

    class NSApplication:
        """Only event pumping while a script waits (no exec(), no new
        QApplication): nextEvent... processes pending Qt events, returns None."""

        @classmethod
        def sharedApplication(cls):
            return cls()

        def nextEventMatchingMask_untilDate_inMode_dequeue_(
            self, mask, date, mode, dequeue
        ):
            qtgui.QApplication.processEvents()  # no event object: returns None

        def sendEvent_(self, event) -> None:
            pass

    class NSScreen:
        """Qt screens in Cocoa coordinates: origin at the bottom-left of the
        primary screen, y up."""

        def __init__(self, screen, primary_height):
            self._screen, self._top = screen, primary_height

        def _cocoa(self, rect):
            y = self._top - (rect.y() + rect.height())
            return NSMakeRect(rect.x(), y, rect.width(), rect.height())

        @classmethod
        def screens(cls):
            from fontlabapp.qt.safe import qt_list

            screens = qt_list(qtgui.QApplication.screens)
            top = value(screens[0], "geometry").height() if screens else 0
            return [cls(screen, top) for screen in screens]

        @classmethod
        def mainScreen(cls):
            screens = cls.screens()
            return screens[0] if screens else None

        def frame(self):
            return self._cocoa(value(self._screen, "geometry"))

        def visibleFrame(self):
            return self._cocoa(value(self._screen, "availableGeometry"))

    def stop_all():
        for timer in timers:
            timer._disconnect()
        timers.clear()

    on_close(stop_all)
    return {
        "NSPasteboard": NSPasteboard,
        "NSTimer": NSTimer,
        "NSScreen": NSScreen,
        "NSApplication": NSApplication,
    }
