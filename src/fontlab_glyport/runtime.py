# this_file: src/fontlab_glyport/runtime.py
"""Host-independent helpers for generated Python 2 expressions."""

from collections.abc import Callable, Iterable, Iterator
from functools import partial
from types import SimpleNamespace


def _glyport_div(left: object, right: object) -> object:
    """Preserve classic division for integers, including bool and negative values."""
    if isinstance(left, int) and isinstance(right, int):
        return left // right
    return left / right


# Per-execution builtin fallbacks; never installed in Python's global builtins.
LEGACY_BUILTINS = {
    "xrange": range,
    "unichr": chr,
    "unicode": str,
    "basestring": (str, bytes),
    "long": int,
}


def _glyport_legacy_method(target: object, name: str) -> object:
    """Return the real attribute first; emulate only a missing dictionary method.

    Inspect only actual dicts/classes after lookup fails, to distinguish a
    declared descriptor's AttributeError from a missing inherited operation.
    Native and arbitrary custom objects never receive fallback behavior.
    """
    try:
        return getattr(target, name)
    except AttributeError:
        mapping_class = isinstance(target, type) and issubclass(target, dict)
        if not isinstance(target, dict) and not mapping_class:
            raise
        from inspect import getattr_static

        missing = object()
        if getattr_static(target, name, missing) is not missing:
            raise
        if name == "has_key":
            return (
                dict.__contains__
                if mapping_class
                else partial(dict.__contains__, target)
            )
        methods = {
            "iteritems": dict.items,
            "iterkeys": dict.keys,
            "itervalues": dict.values,
        }
        if name not in methods:
            raise
        method = methods[name]
        return (
            partial(_iterate, method)
            if mapping_class
            else partial(_iterate, method, target)
        )


def _iterate(
    method: Callable[..., Iterable[object]],
    target: object,
    *args: object,
    **kwargs: object,
) -> Iterator[object]:
    """Return a live iterator and preserve the native dict argument failures."""
    return iter(method(target, *args, **kwargs))


# Attribute names avoid injecting quote literals into existing f-strings.
_glyport_legacy_attrs = SimpleNamespace(
    **{
        name: partial(_glyport_legacy_method, name=name)
        for name in ("iteritems", "iterkeys", "itervalues", "has_key")
    }
)
