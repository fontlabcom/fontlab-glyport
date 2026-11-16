# this_file: src/fontlab_glyport/ui/objc_bridge.py
"""The ``objc`` names Glyphs UI code uses, for an import adapter (R030).

Corpus counts (literal grep of the Glyphs corpus ``.py`` files):
``python_method`` 2077, ``IBOutlet`` 342, ``IBAction`` 199, ``super`` 79,
``lookUpClass`` 49, ``selector`` 18, ``error``/``nosuchclass_error`` 14,
``nil`` 7. ``make_objc_module(classes)`` returns a module with exactly these;
any other name raises ``UnsupportedCapability`` at the script line.
``lookUpClass`` resolves only the classes passed in (the Qt-backed Cocoa
classes); any other name raises ``nosuchclass_error``, which is both PyObjC's
catchable error and an ``UnsupportedCapability`` naming the class.
"""

import builtins
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

from .._strict import caller_location
from ..errors import UnsupportedCapability
from .cocoa import selector_of


class ObjCError(UnsupportedCapability):
    """``objc.error``: base of PyObjC's bridge errors."""


class NoSuchClassError(ObjCError):
    """``objc.nosuchclass_error``: the host has no class of that name."""


class _NULLType:
    """Owned subset of PyObjC's identity-based, truthy NULL singleton."""

    __slots__ = ()

    def __new__(cls):
        raise TypeError("Cannot instantiate objc.NULL's type")

    def __repr__(self):
        return "objc.NULL"


NULL = object.__new__(_NULLType)


class IBOutlet:
    """Outlet attribute: ``None`` until a NIB connection (or code) sets it."""

    def __init__(self, name: str | None = None):
        self.name = name

    def __set_name__(self, owner: type, name: str) -> None:
        if self.name is None:
            self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name)

    def __set__(self, obj, value) -> None:
        obj.__dict__[self.name] = value


def IBAction(function: Callable) -> Callable:
    """Mark an action method; the NIB loader connects only marked or named actions."""
    function.__glyport_ibaction__ = True
    return function


def python_method(function: Callable) -> Callable:
    """Identity marker: a Python-only method, never a selector."""
    function.__glyport_python_method__ = True
    return function


class selector:
    """``objc.selector(func, selector=b"name:", signature=...)`` as a method."""

    def __init__(self, function: Callable, selector=None, signature=None, **_):
        self.function = function
        self.selector = selector_of(selector if selector is not None else function)
        self.signature = signature

    def __get__(self, obj, owner=None):
        return self.function.__get__(obj, owner) if obj is not None else self

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)


def signature(types):
    """PyObjC's signature decorator expressed through the existing selector."""
    if not isinstance(types, bytes):
        raise TypeError("Objective-C signature must be bytes")
    return lambda function: selector(function, signature=types)


def _missing_class(name: str) -> NoSuchClassError:
    capability = f"objc.lookUpClass.{name}"
    return NoSuchClassError(
        f"Unsupported capability: {capability} (no such class in FontLab)",
        capability=capability,
        location=caller_location(),
    )


def _module_getattr(name: str) -> Any:
    if name.startswith("__"):
        raise AttributeError(name)
    capability = f"objc.{name}"
    raise UnsupportedCapability(
        f"Unsupported capability: {capability}",
        capability=capability,
        location=caller_location(),
    )


def make_objc_module(classes: Mapping[str, type]) -> ModuleType:
    """Return an ``objc`` module whose ``lookUpClass`` knows ``classes``."""

    def lookUpClass(name):
        name = name.decode() if isinstance(name, bytes) else str(name)
        if name not in classes:
            raise _missing_class(name)
        return classes[name]

    module = ModuleType("objc", "glyport objc subset over Qt-backed Cocoa classes")
    module.__dict__.update(
        python_method=python_method,
        IBOutlet=IBOutlet,
        IBAction=IBAction,
        super=builtins.super,
        lookUpClass=lookUpClass,
        selector=selector,
        signature=signature,
        error=ObjCError,
        nosuchclass_error=NoSuchClassError,
        nil=None,
        NULL=NULL,
        YES=True,
        NO=False,
    )
    module.__all__ = [k for k in module.__dict__ if not k.startswith("__")]
    module.__getattr__ = _module_getattr
    return module
