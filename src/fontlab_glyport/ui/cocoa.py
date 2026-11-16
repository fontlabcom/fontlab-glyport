# this_file: src/fontlab_glyport/ui/cocoa.py
"""PyObjC-shaped Foundation basics for Qt-backed Cocoa UI (R030).

``NSObject`` is a plain Python class with PyObjC's construction protocol
(``alloc().init()``, ``new()``), key-value coding and key-value observing.
Selectors are strings in Objective-C form (``"setValue:forKey:"``); a Python
method name maps to one by replacing ``_`` with ``:`` (PyObjC's rule), and the
colon count is the argument count. Geometry values are tuples with Cocoa field
names (``NSMakeRect(x, y, w, h).size.width``) in Cocoa's bottom-left origin.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from .._strict import caller_location
from ..errors import UnsupportedCapability

NSKeyValueObservingOptionNew = 0x01
NSKeyValueObservingOptionOld = 0x02
NSKeyValueChangeNewKey = "new"
NSKeyValueChangeOldKey = "old"
NSKeyValueChangeKindKey = "kind"
NSKeyValueChangeSetting = 1


class _Struct(Sequence):
    """PyObjC structs have writable fields and preserve tuple comparisons."""

    def __iter__(self):
        return (getattr(self, item.name) for item in fields(self))

    def __len__(self):
        return len(fields(self))

    def __getitem__(self, index):
        return tuple(self)[index]

    def __eq__(self, other):
        return isinstance(other, Sequence) and tuple(self) == tuple(other)


@dataclass(eq=False)
class NSPoint(_Struct):
    x: float = 0.0
    y: float = 0.0


@dataclass(eq=False)
class NSSize(_Struct):
    width: float = 0.0
    height: float = 0.0


@dataclass(eq=False)
class NSRect(_Struct):
    origin: NSPoint = field(default_factory=NSPoint)
    size: NSSize = field(default_factory=NSSize)


def NSMakePoint(x, y) -> NSPoint:
    return NSPoint(float(x), float(y))


def NSMakeSize(w, h) -> NSSize:
    return NSSize(float(w), float(h))


def NSMakeRect(x, y, w, h) -> NSRect:
    return NSRect(NSMakePoint(x, y), NSMakeSize(w, h))


NSZeroPoint = NSMakePoint(0, 0)
NSZeroSize = NSMakeSize(0, 0)
NSZeroRect = NSMakeRect(0, 0, 0, 0)


def as_rect(value: Any) -> NSRect:
    """Accept an NSRect or the PyObjC tuple forms ``((x, y), (w, h))``/``(x, y, w, h)``."""
    if isinstance(value, NSRect):
        return value
    if len(value) == 2:
        (x, y), (w, h) = value
        return NSMakeRect(x, y, w, h)
    return NSMakeRect(*value)


def python_name(selector: str) -> str:
    """``"setValue:forKey:"`` -> ``"setValue_forKey_"`` (PyObjC's mapping)."""
    return selector.replace(":", "_")


def selector_of(action: Any) -> str:
    """Normalise a ``setAction_`` argument to an Objective-C selector string.

    Accepts a selector string (``"go:"``), bytes, an ``objc.selector`` object or
    a Python method/function (its ``__name__`` mapped by PyObjC's rule).
    """
    if isinstance(action, bytes):
        action = action.decode("ascii")
    if isinstance(action, str):
        return action
    name = getattr(action, "selector", None)
    if isinstance(name, bytes | str):
        return selector_of(name)
    name = getattr(action, "__name__", None)
    if isinstance(name, str):
        return name.replace("_", ":")
    raise TypeError(f"not a selector: {action!r}")


def unsupported(capability: str) -> UnsupportedCapability:
    """An UnsupportedCapability located at the calling script line."""
    return UnsupportedCapability(
        f"Unsupported capability: {capability}",
        capability=capability,
        location=caller_location(),
    )


def perform(target: Any, selector: str, *args: Any) -> Any:
    """Call ``target``'s method for ``selector`` with exactly its colon arity."""
    method = getattr(target, python_name(selector), None)
    if method is None:
        raise unsupported(f"{type(target).__name__}.{selector}")
    arity = selector.count(":")
    if arity != len(args):
        raise TypeError(f"{selector} takes {arity} argument(s), got {len(args)}")
    return method(*args)


class NSObject:
    """PyObjC-style root object: ``alloc()`` gives an uninitialised instance."""

    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    @classmethod
    def new(cls):
        return cls.alloc().init()

    def init(self):
        return self

    def respondsToSelector_(self, selector) -> bool:
        return callable(getattr(self, python_name(selector_of(selector)), None))

    # Key-value coding: a zero-argument method of that name, else the attribute.
    def valueForKey_(self, key: str) -> Any:
        value = getattr(self, key)
        return value() if callable(value) and _accessor(type(self), key) else value

    def setValue_forKey_(self, value: Any, key: str) -> None:
        old = self._kvc_old(key)
        setter = getattr(self, "set" + key[:1].upper() + key[1:] + "_", None)
        if callable(setter):
            setter(value)
        else:
            setattr(self, key, value)
        self._kvo_notify(key, old)

    def valueForKeyPath_(self, path: str) -> Any:
        obj: Any = self
        for key in path.split("."):
            obj = obj.valueForKey_(key) if obj is not None else None
        return obj

    def setValue_forKeyPath_(self, value: Any, path: str) -> None:
        head, _, last = path.rpartition(".")
        owner = self.valueForKeyPath_(head) if head else self
        owner.setValue_forKey_(value, last)

    def _kvc_old(self, key: str) -> Any:
        try:
            return self.valueForKey_(key)
        except AttributeError:
            return None

    # Key-value observing: explicit KVC writes and will/didChange pairs notify.
    def addObserver_forKeyPath_options_context_(
        self, observer, keyPath, options, context
    ) -> None:
        observers = self.__dict__.setdefault("_kvo_observers", [])
        observers.append((observer, str(keyPath), int(options or 0), context))

    def removeObserver_forKeyPath_(self, observer, keyPath) -> None:
        observers = self.__dict__.get("_kvo_observers", [])
        for entry in list(observers):
            if entry[0] is observer and entry[1] == keyPath:
                observers.remove(entry)
                return
        raise ValueError(f"{observer!r} is not observing {keyPath!r}")

    def willChangeValueForKey_(self, key: str) -> None:
        self.__dict__.setdefault("_kvo_pending", {})[key] = self._kvc_old(key)

    def didChangeValueForKey_(self, key: str) -> None:
        old = self.__dict__.get("_kvo_pending", {}).pop(key, None)
        self._kvo_notify(key, old)

    def _kvo_notify(self, key: str, old: Any) -> None:
        for observer, path, options, context in list(
            self.__dict__.get("_kvo_observers", ())
        ):
            if path != key:
                continue
            change = {NSKeyValueChangeKindKey: NSKeyValueChangeSetting}
            if options & NSKeyValueObservingOptionNew:
                change[NSKeyValueChangeNewKey] = self._kvc_old(key)
            if options & NSKeyValueObservingOptionOld:
                change[NSKeyValueChangeOldKey] = old
            observer.observeValueForKeyPath_ofObject_change_context_(
                key, self, change, context
            )


def _accessor(cls: type, key: str) -> bool:
    """True when ``key`` is a method defined on the class (a Cocoa getter)."""
    return any(callable(vars(base).get(key)) for base in cls.__mro__)


class Dispatcher:
    """Runs script callbacks through ``wrap``; exceptions go to ``sink``."""

    def __init__(self, sink: Callable[[Exception, object], object], wrap=None):
        self.sink, self.wrap = sink, wrap

    def call(self, function: Callable, sender: object, *args: Any) -> None:
        try:
            (self.wrap(function) if self.wrap else function)(*args)
        except Exception as exc:  # noqa: BLE001 - the sink is the error route
            self.sink(exc, sender)
