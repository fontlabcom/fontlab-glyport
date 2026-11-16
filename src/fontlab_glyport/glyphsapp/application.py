# this_file: src/fontlab_glyport/glyphsapp/application.py
"""The ``Glyphs`` object: model access, defaults, output, callbacks, localize.

Every host effect goes through the injected ``GlyphsBridge``. Unknown members
raise ``UnsupportedCapability`` at the script's own call location; nothing is
forwarded to a native object.
"""

import traceback
from collections.abc import Callable, Mapping
from threading import RLock

from .._strict import guard_properties
from ..errors import UnsupportedAttribute, UnsupportedCapability
from ..plugins.registry import FILTERS
from ..receipt import SourceLocation
from .bridge import GlyphsBridge
from .defaults import (
    BoolDefaults,
    ColorDefaults,
    Defaults,
    IntDefaults,
    Store,
    register_default,
)

ErrorSink = Callable[[Exception, object], object]
Wrap = Callable[[Callable], Callable]
# Close-hook registrar such as ``ExecutionContext.on_close``.
OnClose = Callable[[Callable[[], object]], object]

# Glyphs SDK callback constants (GlyphsApp/__init__.py "Callbacks" section).
EVENT_NAMES = {
    "UPDATEINTERFACE": "GSUpdateInterface",
    "DRAWBACKGROUND": "DrawBackground",
    "DRAWFOREGROUND": "DrawForeground",
    "DRAWINACTIVE": "DrawInactive",
    "MOUSEMOVED": "mouseMovedNotification",
    "MOUSEDRAGGED": "mouseDraggedNotification",
    "MOUSEDOWN": "mouseDownNotification",
    "MOUSEUP": "mouseUpNotification",
    "DOCUMENTOPENED": "GSDocumentWasOpenedNotification",
    "DOCUMENTACTIVATED": "GSDocumentActivateNotification",
    "DOCUMENTWASSAVED": "GSDocumentWasSavedSuccessfully",
    "DOCUMENTCLOSED": "GSDocumentWillCloseNotification",
    "TABDIDOPEN": "TabDidOpenNotification",
    "TABWILLCLOSE": "TabWillCloseNotification",
}
EVENTS = frozenset(EVENT_NAMES.values())


def unsupported(
    capability: str, error: type[UnsupportedCapability] = UnsupportedCapability
) -> UnsupportedCapability:
    """Build the error located at the frame that called our caller."""
    frame = traceback.extract_stack()[-3]
    location = SourceLocation(frame.filename, frame.lineno, (frame.colno or 0) + 1)
    return error(
        f"Unsupported capability: {capability}",
        capability=capability,
        location=location,
    )


class _Strict:
    """Unknown public reads and every public write fail as unsupported.

    Reads raise ``UnsupportedAttribute`` (also an AttributeError) so feature
    probes such as ``hasattr(Glyphs, "x")`` return False. Subclass properties
    are guarded (``guard_properties``): an AttributeError inside a body, such
    as an unknown model read, surfaces as ``UnsupportedCapability`` with the
    inner capability instead of being re-dispatched here under the property's
    name.
    """

    _prefix = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        guard_properties(cls)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        raise unsupported(f"{self._prefix}.{name}", UnsupportedAttribute)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise unsupported(f"{self._prefix}.{name}")


class GSDocument(_Strict):
    """Document selection and source-qualified local Glyph Info lifecycle.

    File URL/type/superclass writes require explicit ``_file_primitives``;
    FontLab file observation and native NSDocument behavior remain unqualified.
    """

    _prefix = "GSDocument"

    def __init__(self, font) -> None:
        self._font = font
        self._glyph_info_lock = RLock()

    def __getattr__(self, name):
        # Keep unqualified fileURL feature probes absent. It is an inherited
        # NSDocument primitive, not a manufactured FontLab URL property.
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "fileURL":
            provider = self.__dict__.get("_file_primitives")
            read = getattr(provider, "file_url", None)
            if callable(read):
                return lambda: read(self)
        raise unsupported(f"{self._prefix}.{name}", UnsupportedAttribute)

    def glyphsInfo(self):
        self._font._check()
        from .info_manager import GSGlyphsInfo

        with self._glyph_info_lock:
            manager = self.__dict__.get("_local_glyph_info")
        return GSGlyphsInfo.sharedManager() if manager is None else manager

    def fileType(self):
        from .info_document import primitive

        return primitive(self, "file_type")

    def setFileURL_(self, url):
        from .info_document import set_file_url

        return set_file_url(self, url)

    def shouldMonitorFile_(self, file_type):
        from .info_document import should_monitor

        return should_monitor(file_type)

    def startObservingFileIfSupported(self):
        from .info_document import optional_selector

        optional_selector(self, "startObservingFile")

    def loadCustomGlyphsData(self):
        from .info_document import load_custom

        return load_custom(self)

    def valueForKey_(self, key):
        if key != "glyphsInfo":
            raise unsupported(f"GSDocument.valueForKey.{key}")
        return self.glyphsInfo()

    @property
    def font(self):
        return self._font

    def selectedLayers(self) -> list:
        """The font's selected layers (Glyphs: a method on the document)."""
        return list(self._font.selectedLayers)


def _info_manager(font):
    """The shared Glyph Info manager, else the font's own (``font.glyphsInfo()``)."""
    from .info_manager import GSGlyphsInfo

    if font is None:
        return GSGlyphsInfo.sharedManager()
    glyphs_info = getattr(font, "glyphsInfo", None)
    if not callable(glyphs_info):
        raise TypeError(f"font must be a GSFont or None, not {type(font).__name__}")
    return glyphs_info()


class GSApplication(_Strict):
    """Glyphs 4 facade; explicit factories select legacy wrapper subclasses."""

    def delegate(self):
        raise UnsupportedCapability(
            "FontLab has no Glyphs Cocoa application/controller delegate",
            capability="Glyphs.delegate",
        )

    _prefix = "Glyphs"

    def __init__(
        self,
        model,
        bridge: GlyphsBridge,
        store: Store,
        wrap,
        sink,
        on_close=None,
        menu=None,
        filters=None,
    ) -> None:
        self._model, self._bridge, self._store = model, bridge, store
        if menu is not None:
            # Glyphs.menu: plugins.menus.AppMenu over a plugin host. Without one
            # the name stays an unsupported probe (hasattr is False).
            object.__setattr__(self, "menu", menu)
        self._wrap: Wrap | None = wrap
        self._sink: ErrorSink = sink
        self._on_close: OnClose | None = on_close
        self._close_hooked = False
        self._tokens: dict[tuple[Callable, str], object] = {}
        self._defaults = Defaults(store)
        self._bool_defaults = BoolDefaults(store)
        self._int_defaults = IntDefaults(store)
        self._color_defaults = ColorDefaults(store)
        self._filters = FILTERS if filters is None else filters

    @property
    def handleSize(self) -> int:
        """Glyphs' 0–2 handle-size preference, scoped to glyport defaults."""
        return self._int_defaults["GSHandleSize"]

    # Model -------------------------------------------------------------
    @property
    def font(self):
        return self._model.font

    currentFont = font

    @property
    def filters(self):
        return list(self._filters.values())

    def glyphInfoForName(self, name, font=None):
        """Select the explicit font's manager, otherwise the shared manager."""
        if isinstance(name, int):
            return self.glyphInfoForUnicode(name, font=font)
        return _info_manager(font).glyphInfoForName_(name)

    def glyphInfoForUnicode(self, string_or_int, font=None):
        """Preserve integer spelling and the selected manager through dispatch."""
        if isinstance(string_or_int, int):
            string_or_int = f"{string_or_int:04X}"
        return _info_manager(font).glyphInfoForUnicode_(string_or_int)

    @property
    def fonts(self):
        return self._model.fonts

    @property
    def currentDocument(self) -> GSDocument | None:
        font = self._model.font
        return None if font is None else font.parent

    # Defaults ----------------------------------------------------------
    @property
    def defaults(self) -> Defaults:
        return self._defaults

    @property
    def boolDefaults(self) -> BoolDefaults:
        return self._bool_defaults

    @property
    def intDefaults(self) -> IntDefaults:
        return self._int_defaults

    @property
    def colorDefaults(self) -> ColorDefaults:
        return self._color_defaults

    def registerDefault(self, key: str, value) -> None:
        register_default(self._store, key, value)

    def registerDefaults(self, values: Mapping) -> None:
        if not isinstance(values, Mapping):
            raise TypeError("registerDefaults expects a mapping")
        validated = {}
        for key, value in values.items():
            register_default(validated, key, value)
        for key, value in validated.items():
            register_default(self._store, key, value)

    # Host services -----------------------------------------------------
    @property
    def versionNumber(self) -> float:
        """Compatibility value reported by the bridge, not FontLab's version."""
        return self._bridge.version_number()

    @property
    def versionString(self) -> str:
        """The emulated Glyphs version, consistent with ``versionNumber``."""
        return self._bridge.version_string()

    @property
    def buildNumber(self) -> float:
        """Compatibility value reported by the bridge, not FontLab's build."""
        return self._bridge.build_number()

    def showMacroWindow(self) -> None:
        self._bridge.show_macro_window()

    def clearLog(self) -> None:
        self._bridge.clear_log()

    def showNotification(self, title: str, message: str) -> None:
        self._bridge.show_notification(title, message)

    def redraw(self) -> None:
        self._bridge.redraw()

    def currentEvent(self):
        """The tool event being handled, else a synthetic one (FontLab exposes
        no Cocoa event): live ``modifierFlags()`` during reporter paints."""
        from ..drawing.events import NSEvent, current_event

        event = current_event()
        return event if event is not None else NSEvent.synthetic()

    def localize(self, localization):
        """Pick the bridge UI language, its primary subtag, "en", then the first.

        Neither str nor dict: ``str(value)``, as the Glyphs SDK wrapper does.
        """
        if isinstance(localization, str):
            return localization
        if not isinstance(localization, dict):
            return str(localization)
        language = self._bridge.ui_language()
        for key in (language, language.split("-")[0], "en"):
            if key in localization:
                return localization[key]
        return next(iter(localization.values()), "")

    # Callbacks ---------------------------------------------------------
    def addCallback(self, target: Callable, operation: str) -> None:
        """Register through the bridge; a repeated (target, event) replaces."""
        if not callable(target):
            raise TypeError(
                f"callback target must be callable, not {type(target).__name__}"
            )
        if operation not in EVENTS:
            raise unsupported(f"Glyphs.addCallback.{operation}")
        self._hook_close()
        self.removeCallback(target, operation)
        token = self._bridge.subscribe(operation, self._dispatcher(target, operation))
        self._tokens[(target, operation)] = token

    def removeCallback(self, target: Callable, operation: str | None = None) -> None:
        """Remove matching registrations; unknown targets are a no-op."""
        for key in [k for k in self._tokens if k[0] == target]:
            if operation is None or key[1] == operation:
                self._bridge.remove(self._tokens[key])  # keep the token on failure
                del self._tokens[key]

    def _hook_close(self) -> None:
        """Register teardown on first use, after import-time hooks (R027 order).

        Hooks run newest first, so callbacks are removed before windows that a
        ``vanilla`` hook registered at import time are closed.
        """
        if self._on_close is not None and not self._close_hooked:
            self._on_close(self._remove_all_callbacks)
            self._close_hooked = True

    def _remove_all_callbacks(self) -> None:
        """Host teardown hook (R027): try every registration; failures stay.

        The hook is consumed: the next ``addCallback`` registers it again, so
        a closed context's registrar rejects late callbacks. Every token is
        attempted; afterwards the first process exit/interrupt is re-raised,
        else the first error. Failed tokens are kept for a later retry.
        """
        self._close_hooked = False
        failures = []
        for key, token in list(self._tokens.items()):
            try:
                self._bridge.remove(token)
            except BaseException as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
                continue
            del self._tokens[key]
        if failures:
            exits = [e for e in failures if not isinstance(e, Exception)]
            raise (exits or failures)[0]

    def _dispatcher(self, target: Callable, event: str) -> Callable[..., None]:
        def dispatch(*args, **kwargs) -> None:
            try:
                call = self._wrap(target) if self._wrap else target
                call(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - the sink is the error route
                self._sink(exc, event)

        return dispatch
