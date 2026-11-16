# this_file: src/fontlab_glyport/fonttools.py
"""Resolve optional fontTools without aliasing FontLab's private package."""

from importlib import import_module
from types import ModuleType

from .errors import UnsupportedCapability


def fonttools_module(name: str, capability: str) -> ModuleType:
    """Prefer a public installation, then FontLab's bundled private module.

    Check the root too: a cached submodule must not defeat an unavailable or
    deliberately blocked package. Never publish private modules under public
    names in sys.modules; FontLab rewrites their internal imports itself.
    """
    errors = []
    for root in ("fontTools", "fontlab_private.fontTools"):
        try:
            import_module(root)
            return import_module(f"{root}.{name}")
        except ImportError as error:
            errors.append(error)
    raise UnsupportedCapability(
        f"{capability} requires fontTools or FontLab's bundled fontlab_private.fontTools",
        capability=capability,
    ) from errors[-1]
