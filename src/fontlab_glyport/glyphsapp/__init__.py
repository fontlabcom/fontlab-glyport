# this_file: src/fontlab_glyport/glyphsapp/__init__.py
"""Opt-in ``GlyphsApp`` module: the ``Glyphs`` host-services facade (R026 slice).

``make_glyphsapp_module(model, bridge, error_sink=...)`` returns a fresh
``GlyphsApp`` module exporting ``Glyphs``, the callback event constants, the
dialog functions and the model classes. Host effects go through the injected
``GlyphsBridge``; nothing here imports FontLab, fontgate or Qt. Register it with
``ctx.adapters["GlyphsApp"] = glyphsapp_provider(model, bridge, wrap=ctx.wrap,
error_sink=sink, on_close=ctx.on_close)``; ExecutionContext defaults stay
unsupported placeholders.
"""

import posixpath
from collections.abc import Callable, MutableMapping, Sequence
from types import ModuleType
from typing import Any

from .. import model as _model
from ..glyphs_constants import SDK_CONSTANTS
from ..plugins.host import MENUS
from ..ui.cocoa_menu import NSMenuItem
from . import geometry
from .application import (
    EVENT_NAMES,
    EVENTS,
    ErrorSink,
    GSApplication,
    GSDocument,
    OnClose,
    Wrap,
    unsupported,
)
from .application_profiles import application_class
from .bridge import GlyphsBridge
from .defaults import Store
from .glyph_info import GSGlyphInfo
from .info_manager import GSGlyphsInfo
from .proxy import Proxy

__all__ = [
    "EVENTS",
    "EVENT_NAMES",
    "GSApplication",
    "GSDocument",
    "GlyphsBridge",
    "glyphsapp_provider",
    "make_glyphsapp_module",
]

# Process-wide in-memory defaults shared by modules made without ``defaults=``,
# like Glyphs' application-wide user defaults. Never FontLab preferences/files.
_DEFAULT_STORE: dict[str, Any] = {}
_MODEL_CLASSES = (
    "GSFont",
    "GSFontMaster",
    "GSGlyph",
    "GSLayer",
    "GSPath",
    "GSNode",
    "GSAnchor",
    "GSComponent",
    "GSAxis",
    "GSInstance",
    "GSGuide",
    "GSHint",
    "GSCustomParameter",
    "GSClass",
    "GSFeature",
    "GSFeaturePrefix",
)
# Glyphs constants the model uses (GlyphsApp/__init__.py values).
_MODEL_CONSTANTS = (
    "TOPGHOST",
    "STEM",
    "BOTTOMGHOST",
    "GSLTR",
    "GSSHARP",
    "GSSMOOTH",
    "CORNER",
    "CAP",
)


def _types(filetypes: str | Sequence[str] | None) -> list[str] | None:
    if filetypes is None:
        return None
    return [filetypes] if isinstance(filetypes, str) else list(filetypes)


def _message_dialogs(bridge: GlyphsBridge) -> dict[str, Callable]:
    def Message(message, title="Alert", OKButton=None):
        return bridge.message(message, title, OKButton)

    def AskString(message, value=None, title="Glyphs", OKButton=None, placeholder=None):
        return bridge.ask_string(message, value, title, OKButton, placeholder)

    return {"Message": Message, "AskString": AskString}


class NSPath(str):
    """A dialog's path with the NSString path methods (and Glyphs'
    ``dotSuffix`` helpers) scripts call on it."""

    def lastPathComponent(self) -> str:
        return NSPath(posixpath.basename(self))

    def stringByDeletingLastPathComponent(self) -> str:
        return NSPath(posixpath.dirname(self))

    def pathExtension(self) -> str:
        return NSPath(posixpath.splitext(self)[1].lstrip("."))

    def stringByDeletingPathExtension(self) -> str:
        return NSPath(posixpath.splitext(self)[0])

    def dotSuffix(self) -> str:  # Glyphs: ".csv"
        return NSPath(posixpath.splitext(self)[1])

    def stringByDeletingDotSuffix(self) -> str:  # Glyphs
        return self.stringByDeletingPathExtension()

    def stringByAppendingPathComponent_(self, part) -> str:
        return NSPath(posixpath.join(self, str(part)))

    def stringByAppendingString_(self, text) -> str:
        return NSPath(self + str(text))


def _paths(value):
    """Dialog results as ``NSPath`` (a list stays a list; None stays None)."""
    if isinstance(value, str):
        return NSPath(value)
    if isinstance(value, (list, tuple)):
        return [NSPath(v) if isinstance(v, str) else v for v in value]
    return value


def _open_dialogs(bridge: GlyphsBridge) -> dict[str, Callable]:
    def GetFolder(message=None, allowsMultipleSelection=False, path=None):
        return _paths(bridge.get_folder(message, allowsMultipleSelection, path))

    def GetOpenFile(
        message=None,
        title=None,
        allowsMultipleSelection=False,
        filetypes=None,
        path=None,
    ):
        types = _types(filetypes)
        return _paths(
            bridge.get_open_file(message, title, allowsMultipleSelection, types, path)
        )

    def GetFile(
        message=None, title=None, allowsMultipleSelection=False, filetypes=None
    ):
        return GetOpenFile(message, title, allowsMultipleSelection, filetypes)

    return {"GetFolder": GetFolder, "GetOpenFile": GetOpenFile, "GetFile": GetFile}


def _save_dialog(bridge: GlyphsBridge) -> dict[str, Callable]:
    def GetSaveFile(
        message=None,
        ProposedFileName=None,
        filetypes=None,
        filetype=None,
        *,
        proposedFileName=None,
    ):
        if ProposedFileName is not None and proposedFileName is not None:
            raise TypeError("pass ProposedFileName or proposedFileName, not both")
        name = proposedFileName if ProposedFileName is None else ProposedFileName
        types = _types(filetypes if filetypes is not None else filetype)
        return _paths(bridge.get_save_file(message, name, types))

    return {"GetSaveFile": GetSaveFile}


def _missing(name: str) -> Any:
    """Module __getattr__: dunders stay AttributeError, the rest is unsupported."""
    if name.startswith("__"):
        raise AttributeError(name)
    raise unsupported(f"GlyphsApp.{name}")


class GSControlLayer:
    """A tab control layer; only the newline (character 10) is modelled."""

    def __init__(self, char=10):
        self.char = int(char)

    @classmethod
    def newline(cls):
        return cls(10)

    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    def initWithChar_(self, char):
        self.char = int(char)
        return self


class GSScriptingHandler:
    """``sharedHandler().currentPythonPath()``: the host Python's prefix."""

    @classmethod
    def sharedHandler(cls):
        return cls()

    def currentPythonPath(self) -> str:
        import sys

        return sys.base_prefix


def NSStr(string):
    """GlyphsApp's ``NSStr``: an ``NSString`` of a truthy value, else None
    (Python ``str`` is what PyObjC hands scripts for NSString)."""
    return str(string) if string else None


def make_glyphsapp_module(
    model: Any,
    bridge: GlyphsBridge,
    *,
    profile: str = "glyphs4",
    defaults: Store | None = None,
    wrap: Wrap | None = None,
    error_sink: ErrorSink,
    on_close: OnClose | None = None,
    menu: Any = None,
    filters: MutableMapping | None = None,
) -> ModuleType:
    """Return a fresh ``GlyphsApp`` module bound to ``model`` and ``bridge``.

    ``defaults`` is the mapping behind ``Glyphs.defaults`` (default: the
    process-wide in-memory ``_DEFAULT_STORE``). ``wrap`` (e.g.
    ``ExecutionContext.wrap``) runs every callback; callback exceptions go to
    ``error_sink(exc, event)``. ``on_close`` (e.g. ``ExecutionContext.on_close``)
    receives, on the first ``addCallback``, a hook removing every callback.
    ``profile`` selects the exact Glyphs 2/3/4 info wrapper, defaulting to 4;
    the execution layer must resolve ``auto`` before calling this factory.
    """
    application = application_class(profile)
    store = _DEFAULT_STORE if defaults is None else defaults
    module = ModuleType("GlyphsApp", "glyport GlyphsApp host-services facade")
    module.__path__ = []  # a package, so GlyphsApp.plugins/UI still resolve
    names: dict[str, Any] = {
        "Glyphs": application(
            model, bridge, store, wrap, error_sink, on_close, menu=menu, filters=filters
        )
    }
    names.update({name: name for name in MENUS})  # GlyphsApp *_MENU constants
    names.update(EVENT_NAMES)
    names.update(_message_dialogs(bridge))
    names.update(_open_dialogs(bridge))
    names.update(_save_dialog(bridge))
    names.update({name: getattr(_model, name) for name in _MODEL_CLASSES})
    names.update({name: getattr(_model.proxies, name) for name in _MODEL_CONSTANTS})
    names.update(SDK_CONSTANTS)
    names["GSGuideLine"] = names["GSGuide"]
    names.update({name: getattr(geometry, name) for name in geometry.__all__})

    names.update(
        GSGlyphsInfo=GSGlyphsInfo,
        GSScriptingHandler=GSScriptingHandler,
        GSControlLayer=GSControlLayer,
        NSMenuItem=NSMenuItem,
        PLAIN="plain",
        TTF="TTF",
        OTF="OTF",
        WOFF="WOFF",
        WOFF2="WOFF2",
        ONSTATE=1,
        OFFSTATE=0,
        MIXEDSTATE=-1,
        SEGMENT=19,
        INSTANCETYPESINGLE=0,
        INSTANCETYPEVARIABLE=1,
        Proxy=Proxy,
        GSGlyphInfo=GSGlyphInfo,
        NSStr=NSStr,
    )
    from .callbacks import callback_handler

    names["GSCallbackHandler"] = callback_handler(names["Glyphs"])
    from ..drawing.cocoa_drawing import NSAffineTransform
    from ..model.background import GSBackgroundImage, GSBackgroundLayer
    from ..model.proxies import GSEditViewController
    from ..model.zones import GSAlignmentZone

    names.update(
        NSAffineTransform=NSAffineTransform,
        GSBackgroundImage=GSBackgroundImage,
        GSBackgroundLayer=GSBackgroundLayer,
        GSEditViewController=GSEditViewController,
        GSAlignmentZone=GSAlignmentZone,
    )
    for name, value in names.items():
        setattr(module, name, value)
    module.__all__ = sorted(names)
    module.__getattr__ = _missing
    return module


def glyphsapp_provider(
    model: Any,
    bridge: GlyphsBridge,
    *,
    profile: str = "glyphs4",
    defaults: Store | None = None,
    wrap: Wrap | None = None,
    error_sink: ErrorSink,
    on_close: OnClose | None = None,
    menu: Any = None,
    filters: MutableMapping | None = None,
) -> Callable[[], ModuleType]:
    """Zero-argument provider for an ExecutionContext ``GlyphsApp`` adapter.

    Pass ``on_close=ctx.on_close`` so ``ctx.close()`` removes every callback
    each provided module registered, and ``profile=ctx.profile`` for its wrapper.
    """

    application_class(profile)

    def provide() -> ModuleType:
        return make_glyphsapp_module(
            model,
            bridge,
            profile=profile,
            defaults=defaults,
            wrap=wrap,
            error_sink=error_sink,
            on_close=on_close,
            menu=menu,
            filters=filters,
        )

    return provide
