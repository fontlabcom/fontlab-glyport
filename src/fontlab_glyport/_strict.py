# this_file: src/fontlab_glyport/_strict.py
"""Shared rules for strict facades: script locations and probe-safe properties.

Strict facades raise ``UnsupportedAttribute`` (also an AttributeError) for
unknown reads so ``hasattr``/``getattr(obj, name, default)`` probes work. CPython
re-dispatches an AttributeError raised inside a property body to ``__getattr__``
under the property's own name, losing the real cause. ``guard_properties``
rewraps a class's properties so their bodies never leak an AttributeError.
"""

import os
import sys
from pathlib import Path

from ._receipt_records import SourceLocation
from .errors import UnsupportedAttribute, UnsupportedCapability

_PACKAGE = str(Path(__file__).resolve().parent) + os.sep


def caller_location() -> SourceLocation | None:
    """Locate the innermost frame outside this package (the script's own line).

    The column is left unknown: resolving it walks ``co_positions`` and made
    each ``hasattr`` miss in a 300-line script ~50x slower.
    """
    frame = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(_PACKAGE):
        frame = frame.f_back
    if frame is None:
        return None
    return SourceLocation(frame.f_code.co_filename, frame.f_lineno)


class _GuardedProperty(property):
    """A property whose body cannot re-dispatch into ``__getattr__``."""

    def __get__(self, obj, owner=None):
        try:
            return super().__get__(obj, owner)
        except UnsupportedAttribute as error:
            raise UnsupportedCapability(
                str(error),
                location=error.location,
                capability=error.capability,
                recovery_action=error.recovery_action,
            ) from error
        except AttributeError as error:
            name = getattr(self.fget, "__name__", "property")
            capability = f"{type(obj).__name__}.{name}"
            raise UnsupportedCapability(
                f"Unsupported capability: {capability} ({error})",
                location=caller_location(),
                capability=capability,
            ) from error


def guard_properties(cls: type) -> None:
    """Rewrap every plain property defined directly on ``cls`` (fset/doc kept)."""
    for name, value in list(vars(cls).items()):
        if type(value) is property:
            guarded = _GuardedProperty(
                value.fget, value.fset, value.fdel, value.__doc__
            )
            setattr(cls, name, guarded)
