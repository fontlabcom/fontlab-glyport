# this_file: src/fontlab_glyport/glyphsapp/info_runtime.py
"""Explicit lawful dependencies for source-qualified Glyph Info lifecycles.

This internal context is not a native provider installer or a public Glyphs API.
No provider is assumed for proprietary resources, images, localization or queues.
An owned scheduler qualifies its chosen schedule, not NSOperationQueue parity.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock

from ..errors import UnsupportedCapability
from ..model.info_records import GlyphInfoIndex

_provider = ContextVar("glyport_info_provider", default=None)


class InfoNativeException(Exception):
    """Deliberately marked source-NSException analogue; never a catch-all."""


class InfoError(Exception):
    """Owned error fields, without claiming native NSError identity or wording."""

    def __init__(self, domain: str, code: int, message: str) -> None:
        super().__init__(message)
        self._domain, self._code = domain, code

    def domain(self) -> str:
        return self._domain

    def code(self) -> int:
        return self._code

    def localizedDescription(self) -> str:
        return str(self)


@dataclass
class InfoErrorSlot:
    """Internal owned slot; not an arbitrary PyObjC ^@ pointer wrapper."""

    value: object = None


@dataclass
class InfoState:
    """Persistent fields separate from each load's fresh row/category arrays."""

    provider: object
    localURL: object
    shared: bool = False
    index: GlyphInfoIndex = field(default_factory=GlyphInfoIndex)
    queue: object = None
    scriptIDs: list | None = None
    categories: list | None = None
    subCategories: list | None = None
    name2Group: dict | None = None
    sidebarCategories: list | None = None
    subCategoryOrder: dict | None = None
    categoriesGroup: object = None
    languagesGroup: object = None
    allItem: object = None
    filterGroups: object = None
    iMatraCombinations: object = None
    categoryOrder: object = None
    scriptOrder: object = None
    observer_flag: int = 0
    monitor: object = field(default_factory=RLock, repr=False, compare=False)


@contextmanager
def using_info_provider(provider):
    """Scope explicit owned dependencies; constructed managers retain them."""
    token = _provider.set(provider)
    try:
        yield provider
    finally:
        _provider.reset(token)


def current_provider():
    """Return an optional provider without enabling unsupported dependencies."""
    return _provider.get()


def require_provider():
    provider = current_provider()
    if provider is None:
        raise UnsupportedCapability(
            "Local Glyph Info initialization requires an explicit lawful provider",
            capability="GSGlyphsInfo.initialization.provider",
        )
    return provider


def state_for(manager):
    state = vars(manager).get("_lifecycle")
    if state is None:
        raise UnsupportedCapability(
            "Complete Glyph Info lifecycle resources are not initialized",
            capability="GSGlyphsInfo.initialization.resources",
        )
    return state


def error_slot(value):
    """Keep the public NULL-only ABI separate from an explicit internal slot."""
    if isinstance(value, InfoErrorSlot):
        return value
    from .info_loading import _require_null_error

    _require_null_error(value)
    return None


def provider_method(provider, name):
    """An absent dependency is a capability gap, never successful no-op work."""
    method = getattr(provider, name, None)
    if not callable(method):
        raise UnsupportedCapability(
            f"Glyph Info provider capability {name} is unavailable",
            capability=f"GSGlyphsInfo.provider.{name}",
        )
    return method
