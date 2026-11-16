# this_file: src/fontlab_glyport/notifications.py
"""Synchronous Cocoa notifications, with optional GlyphsBridge subscriptions.

One default center belongs to each session. Local posts run in the caller's
scope; host callbacks re-enter the owning execution context once per observer.
Custom script names can register before their first post. Unbridged names
from the Cocoa/Glyphs host namespaces require an earlier local post, except
for the small script-only allowlist below. Wildcard observers receive local posts
and supported bridge events only. Observers are retained until removal/close.
"""

from collections.abc import Mapping
from typing import Any

from .glyphsapp.application import EVENT_NAMES
from .ui.cocoa import NSObject, perform, python_name, selector_of, unsupported

_WILDCARD_EVENTS = tuple(
    EVENT_NAMES[k]
    for k in (
        "UPDATEINTERFACE",
        "DOCUMENTOPENED",
        "DOCUMENTACTIVATED",
        "DOCUMENTCLOSED",
    )
)
# Only these notification callbacks currently exist in FontLabGlyphsBridge.
_EVENTS = {event: event for event in _WILDCARD_EVENTS}
_EVENTS.update(
    # Font changes, not glyph/selection updates: the bridge compares package ids.
    # This does not report edits to the current font's contents.
    GlyphsFontDidChangeNotification=EVENT_NAMES["DOCUMENTACTIVATED"],
    GSDocumentCloseNotification=EVENT_NAMES["DOCUMENTCLOSED"],
)
_LOCAL_NAMES = frozenset({"GSRedrawEditView", "drawBotUserDefaultChanged"})


def _host_name(name):
    return (
        name in EVENT_NAMES.values()
        or name.startswith(("NS", "GS", "Glyphs"))
        or (name.startswith(("Tab", "mouse")) and name.endswith("Notification"))
    )


# Cocoa strings imported by the corpus; export does not imply host delivery.
CONSTANTS = {
    name: name
    for name in (
        "NSApplicationDidBecomeActiveNotification",
        "NSApplicationWillResignActiveNotification",
        "NSApplicationWillTerminateNotification",
        "NSControlTextDidBeginEditingNotification",
        "NSControlTextDidChangeNotification",
        "NSFontChangedNotification",
        "NSTextDidChangeNotification",
        "NSTextStorageDidProcessEditingNotification",
        "NSTextViewDidChangeSelectionNotification",
        "NSUserDefaultsDidChangeNotification",
        "NSViewBoundsDidChangeNotification",
        "NSWindowDidBecomeKeyNotification",
        "NSWindowDidBecomeMainNotification",
        "NSWindowDidMoveNotification",
        "NSWindowDidResignMainNotification",
        "NSWindowDidResizeNotification",
        "NSWindowWillCloseNotification",
    )
}


class NSNotification(NSObject):
    def __init__(self, name: str, obj: Any = None, info: Mapping | None = None):
        if not isinstance(name, str) or not name:
            raise TypeError("Notification name must be a nonempty string")
        if info is not None and not isinstance(info, Mapping):
            raise TypeError("Notification userInfo must be a mapping or None")
        self._name, self._object = name, obj
        self._info = None if info is None else dict(info)

    def initWithName_object_userInfo_(self, name, obj, info):
        self.__init__(name, obj, info)
        return self

    @classmethod
    def notificationWithName_object_(cls, name, obj):
        return cls(name, obj)

    @classmethod
    def notificationWithName_object_userInfo_(cls, name, obj, info):
        return cls(name, obj, info)

    def name(self) -> str:
        return self._name

    def object(self) -> Any:
        return self._object

    def userInfo(self) -> dict | None:
        return self._info


def notification_center_class(bridge=None, *, wrap=None, on_close=None) -> type:
    """Create a context-owned class; supplied bridge events keep their limits."""
    default = []

    class NSNotificationCenter(NSObject):
        def init(self):
            self._entries, self._tokens, self._closed = [], {}, False
            self._posted_names = set()
            if on_close is not None:
                on_close(self.close)
            return self

        @classmethod
        def defaultCenter(cls):
            if not default:
                default.append(cls.alloc().init())
            return default[0]

        def _check(self) -> None:
            if self._closed:
                raise RuntimeError("Notification center is closed")

        def _subscribe(self, event: str) -> None:
            if bridge is None or event in self._tokens:
                return
            callback = lambda note: self._receive(event, note)
            self._tokens[event] = bridge.subscribe(event, callback)

        def addObserver_selector_name_object_(self, observer, selector, name, obj):
            self._check()
            selector = selector_of(selector)
            if selector.count(":") != 1 or not callable(
                getattr(observer, python_name(selector), None)
            ):
                raise TypeError("Notification selectors must accept one notification")
            if name is not None and not isinstance(name, str):
                raise TypeError("Notification name must be a string or None")
            local = name in _LOCAL_NAMES or name in self._posted_names
            if (
                name is not None
                and not local
                and (_host_name(name) or name in _EVENTS)
                and (name not in _EVENTS or bridge is None)
            ):
                raise unsupported(f"NSNotificationCenter.{name}")
            events = _WILDCARD_EVENTS if name is None else (_EVENTS.get(name),)
            before = set(self._tokens)
            try:
                for event in events:
                    if event is not None:
                        self._subscribe(event)
            except BaseException:
                for event in set(self._tokens) - before:
                    bridge.remove(self._tokens[event])
                    del self._tokens[event]
                raise
            self._entries.append((observer, selector, name, obj))

        def removeObserver_(self, observer) -> None:
            self.removeObserver_name_object_(observer, None, None)

        def removeObserver_name_object_(self, observer, name, obj) -> None:
            kept = [
                entry
                for entry in self._entries
                if not (
                    entry[0] is observer
                    and (name is None or entry[2] == name)
                    and (obj is None or entry[3] is obj)
                )
            ]
            for event, token in list(self._tokens.items()):
                if not any(e[2] is None or _EVENTS.get(e[2]) == event for e in kept):
                    bridge.remove(token)
                    del self._tokens[event]
            self._entries = kept

        def _receive(self, event: str, note) -> None:
            obj = note.object()
            info = getattr(note, "userInfo", lambda: None)()
            for entry in list(self._entries):
                if entry[2] is None or _EVENTS.get(entry[2]) == event:
                    self._deliver(entry, NSNotification(entry[2] or event, obj, info))

        def _deliver(self, entry, note: NSNotification) -> None:
            if any(e is entry for e in self._entries) and (
                entry[3] is None or entry[3] is note.object()
            ):
                call = lambda: perform(entry[0], entry[1], note)
                (wrap(call) if wrap is not None else call)()

        def postNotificationName_object_(self, name, obj) -> None:
            self.postNotificationName_object_userInfo_(name, obj, None)

        def postNotificationName_object_userInfo_(self, name, obj, info) -> None:
            self._check()
            if not isinstance(name, str) or not name:
                raise TypeError("Posted notification name must be a nonempty string")
            if info is not None and not isinstance(info, Mapping):
                raise TypeError("Notification userInfo must be a mapping or None")
            if name == "GSRedrawEditView" and bridge is not None:
                bridge.redraw()
            self._posted_names.add(name)
            note = NSNotification(name, obj, info)
            for entry in list(self._entries):
                if entry[2] is None or entry[2] == name:
                    self._deliver(entry, note)

        def close(self) -> None:
            errors = []
            for event, token in list(self._tokens.items()):
                try:
                    bridge.remove(token)
                    del self._tokens[event]
                except BaseException as error:  # noqa: BLE001 - finish all teardown before re-raising
                    errors.append(error)
            if errors:
                raise errors[0]
            self._entries.clear()
            self._posted_names.clear()
            self._closed = True

    return NSNotificationCenter
