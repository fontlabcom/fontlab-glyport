# this_file: src/fontlab_glyport/adaptation_imports.py
"""Small Python equivalents for Cocoa values and Python-only objc decorators.

Qt widgets, native selectors, bindings and outlets require injected providers.
These adapters never import AppKit/PyObjC or install global aliases.
"""

from collections import namedtuple

from .affine import NSAffineTransformStruct
from .cocoa_logging import NSLog

# One geometry implementation for every context (review R-merge P2): the
# Qt-free value types of ui.cocoa, shared with the session's AppKit names.
from .ui.cocoa import (
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSZeroPoint,
    NSZeroRect,
    NSZeroSize,
)
from .ui.cocoa import NSPoint as Point
from .ui.cocoa import NSRect as Rect
from .ui.cocoa import NSSize as Size

Range = namedtuple("NSRange", "location length", defaults=(0, 0))


def make_rect(x: float, y: float, width: float, height: float) -> Rect:
    return NSMakeRect(x, y, width, height)


def python_method(function):
    """Mark a Python-only method; no native selector registration is performed."""
    return function


def cocoa_adapters(translate=None) -> dict:
    """Return per-context providers; unknown native attributes fail explicitly."""
    from .execution import placeholder

    values = {
        "NSPoint": Point,
        "NSSize": Size,
        "NSRect": Rect,
        "NSRange": Range,
        "NSMakePoint": NSMakePoint,
        "NSMakeSize": NSMakeSize,
        "NSMakeRect": NSMakeRect,
        "NSMakeRange": Range,
        "NSZeroPoint": NSZeroPoint,
        "NSZeroSize": NSZeroSize,
        "NSZeroRect": NSZeroRect,
        "NSAffineTransformStruct": NSAffineTransformStruct,
        "NSLog": NSLog,
    }

    def provider(name):
        module = placeholder(name, translate)
        exports = {"python_method": python_method} if name == "objc" else values
        module.__dict__.update(exports)
        module.__all__ = tuple(exports)
        return module

    return {
        name: lambda name=name: provider(name)
        for name in ("AppKit", "Foundation", "Cocoa", "objc")
    }
