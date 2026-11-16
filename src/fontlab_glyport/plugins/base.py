# this_file: src/fontlab_glyport/plugins/base.py
"""The seven Glyphs SDK plugin base classes over a plugin host (R025).

They follow GlyphsSDK ``ObjectWrapper/GlyphsApp/plugins.py``: the same
defaults in ``init``/``loadPlugin``, then the optional script hooks
``settings()`` and ``start()``; titles from ``menuName``/``name``; filters
call ``filter(layer, inEditView, customParameters)``; reporters call
``foreground``/``background``/``inactiveLayerForeground``/
``inactiveLayerBackground`` with ``getScale()`` set from the paint context.
Where the SDK relies on Glyphs' native superclasses, the host does the work:
``FilterWithDialog.process_`` restores each layer from its host snapshot
before filtering (Glyphs copies ``shadowLayers``), and ``loadNib`` decodes the
bundle's NIB/XIB into Qt-backed Cocoa views with this plugin as File's Owner.
Exceptions in protocol methods go to the environment's error sink, as the SDK
sends them to ``LogError``.

``make_plugins_module(env)`` returns the ``GlyphsApp.plugins`` module with
classes bound to ``env``.
"""

from collections.abc import Callable, Mapping, MutableMapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from ..errors import UnsupportedCapability
from ..receipt import ReceiptDiagnostic
from ..ui.cocoa import NSObject
from ..ui.cocoa_menu import NSMenuItem
from ..ui.images import find_image, image_class
from ..ui.nib_loader import find_nib, instantiate, load_graph
from .host import PluginHost

ErrorSink = Callable[[Exception, object], object]


@dataclass
class PluginEnv:
    """What plugin classes need from their host and UI layer."""

    host: PluginHost
    appkit: Mapping[str, Any]
    error_sink: ErrorSink
    log: Callable[[str], object] = print
    defaults: MutableMapping[str, Any] = field(default_factory=dict)
    classes: Mapping[str, type] = field(default_factory=dict)  # NIB custom classes
    paint_scope: Callable[[Any], Any] = nullcontext
    menu: Any = None  # plugins.menus.AppMenu behind Glyphs.menu, if any
    wrap: Callable[[Callable], Callable] | None = None  # e.g. ExecutionContext.wrap
    filters: MutableMapping = field(default_factory=dict)
    diagnostic_sink: Callable[[ReceiptDiagnostic], object] | None = None

    def runner(self, owner: object) -> Callable[[Callable], Callable]:
        """``NSMenuItem._runner`` for items a plugin adds: its guard."""
        return lambda call: lambda: self.guard(owner, call)

    def guard(self, owner: object, function: Callable, *args: Any) -> Any:
        """Run a protocol method (through ``wrap`` when given, so late menu and
        paint callbacks keep the execution context); exceptions go to the sink."""
        menu = self.menu
        scope = menu.owned_by(self.runner(owner)) if menu is not None else nullcontext()
        try:
            with scope:  # Glyphs.menu items added meanwhile belong to ``owner``
                return (self.wrap(function) if self.wrap else function)(*args)
        except Exception as exc:  # noqa: BLE001 - the sink is the error route
            self.error_sink(exc, owner)
            return None


def _resources(path: str | None, cls: type) -> Path | None:
    """The bundle's ``Contents/Resources`` for a plugin file path."""
    if not path:
        return None
    marker = "/Contents/Resources/"
    text = str(path)
    if marker in text:
        return Path(text[: text.find(marker) + len(marker)])
    return Path(text).parent


def plugin_resources(plugin: Any) -> Path | None:
    """The bundle Resources folder of the file defining ``plugin``'s class."""
    for value in vars(type(plugin)).values():
        path = (getattr(value, "__globals__", None) or {}).get("__file__")
        if path:
            return _resources(path, type(plugin))
    return None


def plugin_image(qt: Any, plugin: Any, image: Any) -> Any:
    """An SDK icon (``self.icon``): an ``NSImage`` as is, or a resource name
    resolved in the plugin's bundle (``"ExportIcon"`` -> ``ExportIcon.tiff``)."""
    if callable(getattr(image, "icon", None)):
        return image
    path = (
        find_image(image, plugin_resources(plugin)) if isinstance(image, str) else None
    )
    return (
        None
        if path is None
        else image_class(qt).alloc().initWithContentsOfFile_(str(path))
    )


def _optional(obj: Any, name: str) -> None:
    hook = getattr(obj, name, None)
    if callable(hook):
        hook()


def _parse_arguments(arguments, *, skip_lists: bool) -> dict:
    """SDK custom-parameter parsing: ``key:value`` pairs, else numbered values."""
    parameters, unnamed = {}, 0
    for argument in list(arguments)[1:]:
        if skip_lists and ("include" in argument or "exclude" in argument):
            continue
        if ":" in argument:
            key, value = argument.split(":", 1)
        else:
            key, value = unnamed, argument
            unnamed += 1
        try:
            parameters[key] = float(value)
        except ValueError:
            parameters[key] = value
    return parameters


# ReporterPlugin.drawTextAtPoint's SDK alignment names.
_TEXT_ALIGNMENTS = {
    "bottomleft": 0, "bottomcenter": 1, "bottomright": 2,
    "left": 3, "center": 4, "right": 5,
    "topleft": 6, "topcenter": 7, "topright": 8,
}  # fmt: skip


class _Plugin(NSObject):
    _env: PluginEnv

    def loadPlugin(self) -> None:
        """Called once after ``init`` (General plugins and filters configure here)."""

    def logToConsole(self, message) -> None:
        self._env.log(f"{self.title()}: {message}")

    def logError(self, message) -> None:
        self._env.log(f"Error in Plugin: {type(self).__name__}: {message}")

    def loadNib(self, nibname, path=None) -> None:
        """Decode ``nibname`` from the plugin bundle with ``self`` as File's Owner."""
        resources = _resources(path, type(self))
        nib = find_nib(str(nibname), resources) if resources else None
        if nib is None:
            self.logError(
                f"Error loading nib {nibname} for Class: {type(self).__name__}"
            )
            return
        env = self._env
        instance = instantiate(
            load_graph(nib),
            self,
            env.appkit,
            classes=env.classes,
            resources=[resources],
        )
        self.topLevelObjects = instance.top_level
        for message in instance.diagnostics:
            self.logToConsole(f"{nibname}: {message}")


class GeneralPlugin(_Plugin):
    def loadPlugin(self) -> None:
        _optional(self, "settings")
        _optional(self, "start")

    def title(self) -> str:
        return getattr(self, "name", None) or type(self).__name__


class _Filter(_Plugin):
    @property
    def controller(self):
        if "_controller" in self.__dict__:
            return self._controller
        font = self._env.host.current_font()
        return getattr(font, "currentTab", None) if font is not None else None

    @controller.setter
    def controller(self, value):
        self.setController_(value)

    def setController_(self, controller):
        from ..model.proxies import GSEditViewController

        if controller is not None and not isinstance(controller, GSEditViewController):
            raise TypeError("Expected GSEditViewController or None")
        self._controller = controller


class FilterWithoutDialog(_Filter):
    def loadPlugin(self) -> None:
        self.menuName = "My Filter"
        self.keyboardShortcut = None
        _optional(self, "settings")
        _optional(self, "start")
        self._filter = hasattr(self, "filter")

    def title(self) -> str:
        return self.menuName

    def keyEquivalent(self):
        return self.keyboardShortcut

    def runFilterWithLayers_error_(self, layers, error):
        for layer in layers:
            if self._filter:
                self.filter(layer, False, {})
        return True, None

    def runFilterWithLayer_error_(self, layer, error):
        if self._filter:
            self.filter(layer, True, {})
        return True, None

    def runFilterWithLayer_options_error_(self, layer, options, error):
        return self.runFilterWithLayer_error_(layer, error)

    def processLayer_withArguments_(self, layer, arguments) -> None:
        if self._filter:
            self.filter(layer, False, _parse_arguments(arguments, skip_lists=False))


class FilterWithDialog(_Filter):
    """``layers``/``shadowLayers`` are set by the loader while the dialog is open."""

    layers: tuple = ()
    shadowLayers: tuple = ()

    def loadPlugin(self) -> None:
        self.menuName = "My Filter"
        self.keyboardShortcut = None
        self.actionButtonLabel = "Apply"
        _optional(self, "settings")
        if not hasattr(self, "dialog"):
            self.dialog = None

    def setup(self):
        _optional(self, "start")
        self.process_(None)

    def title(self) -> str:
        return self.menuName

    def actionName(self) -> str:
        return self.actionButtonLabel

    def keyEquivalent(self):
        return self.keyboardShortcut

    def view(self):
        return self.dialog

    def process_(self, sender) -> None:
        """Preview: restore every layer from its snapshot, then filter it."""
        host = self._env.host
        for layer, shadow in zip(self.layers, self.shadowLayers, strict=True):
            host.restore_layer(layer, shadow)
            if hasattr(self, "filter"):
                self.filter(layer, True, {})
        host.redraw()

    def update(self) -> None:
        self.process_(None)

    def customParameterString(self):
        generate = getattr(self, "generateCustomParameter", None)
        return generate() if callable(generate) else None

    def processLayer_withArguments_(self, layer, arguments) -> None:
        if hasattr(self, "filter"):
            self.filter(layer, False, _parse_arguments(arguments, skip_lists=False))


class PalettePlugin(_Plugin):
    def init(self):
        self.name, self.dialog, self.sortId = "My Palette", None, 0
        _optional(self, "settings")
        view = self.theView()
        if view is not None:
            height = view.frame().size.height
            if not hasattr(self, "min"):
                self.min = height
            if not hasattr(self, "max"):
                self.max = height
        _optional(self, "start")
        return self

    def title(self) -> str:
        return self.name

    def sortID(self) -> int:
        return self.sortId

    def theView(self):
        return self.dialog

    def minHeight(self) -> int:
        return round(getattr(self, "min", 0))

    def maxHeight(self) -> int:
        return round(getattr(self, "max", 0))

    def currentHeight(self) -> int:
        return int(self._env.defaults.get(self.name + ".ViewHeight", 0) or 0)

    def setCurrentHeight_(self, height) -> None:
        if self.minHeight() <= height <= self.maxHeight():
            self._env.defaults[self.name + ".ViewHeight"] = int(height)


class ReporterPlugin(_Filter):
    def init(self):
        self.needsExtraMainOutlineDrawingForInactiveLayers = True
        self.needsExtraMainOutlineDrawingForActiveLayer = True
        self.menuName = "New ReporterPlugin"
        self.keyboardShortcut = None
        self.keyboardShortcutModifier = 0
        self.drawDefaultInactiveLayers = True
        self.generalContextMenus = []
        _optional(self, "settings")
        _optional(self, "start")
        self._foreground = hasattr(self, "foreground")
        self._background = hasattr(self, "background")
        self._foregroundInViewCoords = hasattr(self, "foregroundInViewCoords")
        self._backgroundInViewCoords = hasattr(self, "backgroundInViewCoords")
        self._inactiveLayerForeground = hasattr(self, "inactiveLayerForeground")
        self._inactiveLayerBackground = hasattr(self, "inactiveLayerBackground")
        if not self._inactiveLayerBackground and hasattr(self, "inactiveLayers"):
            self.inactiveLayerBackground = self.inactiveLayers
            self._inactiveLayerBackground = True
        self._scale, self.black = 1.0, False
        return self

    def title(self) -> str:
        return self.menuName or type(self).__name__

    def keyEquivalent(self):
        return self.keyboardShortcut

    def modifierMask(self) -> int:
        return self.keyboardShortcutModifier

    def _dispatch_reporter_hook(self, hook: str, layer, options) -> None:
        self._scale = options.get("Scale", 1.0)
        self.black = options.get("Black", False)
        getattr(self, hook)(layer)

    def activeLayer(self):
        if "_paint_layer" in self.__dict__:
            return self._paint_layer
        if self.controller is None:
            return None
        layers = self._env.host.selected_layers()
        return next(iter(layers), None)

    def activePosition(self):
        from ..drawing.context import optional_current
        from ..model.proxies import _GraphicView

        if self.activeLayer() is None:
            return None
        if self.controller is not None:
            return self.controller.graphicView().activePosition()
        context = optional_current()
        return None if context is None else _GraphicView(context).activePosition()

    def _dispatch_view_hook(self, hook, options):
        self._scale = options.get("Scale", 1.0)
        self.black = options.get("Black", False)
        getattr(self, hook)()

    def drawForegroundWithOptions_(self, options):
        if self._foregroundInViewCoords:
            self._dispatch_view_hook("foregroundInViewCoords", options)

    def drawBackgroundWithOptions_(self, options):
        if self._backgroundInViewCoords:
            self._dispatch_view_hook("backgroundInViewCoords", options)

    def drawForegroundForLayer_options_(self, layer, options) -> None:
        if self._foreground:
            ReporterPlugin._dispatch_reporter_hook(self, "foreground", layer, options)

    def drawBackgroundForLayer_options_(self, layer, options) -> None:
        if self._background:
            ReporterPlugin._dispatch_reporter_hook(self, "background", layer, options)

    def drawForegroundForInactiveLayer_options_(self, layer, options) -> None:
        if self._inactiveLayerForeground:
            ReporterPlugin._dispatch_reporter_hook(
                self, "inactiveLayerForeground", layer, options
            )

    def drawBackgroundForInactiveLayer_options_(self, layer, options) -> None:
        if self._inactiveLayerBackground:
            ReporterPlugin._dispatch_reporter_hook(
                self, "inactiveLayerBackground", layer, options
            )

    def getScale(self) -> float:
        return self._scale

    def drawTextAtPoint(
        self, text, textPosition, fontSize=10.0, fontColor=None, align="bottomleft"
    ) -> None:
        """SDK helper: ``fontSize`` screen points at any zoom; errors are logged."""
        if align not in _TEXT_ALIGNMENTS:
            self.logError(f"drawTextAtPoint: unknown align {align!r}, using topleft")
        from ..drawing.cocoa_drawing import (
            NSAttributedString,
            NSColor,
            NSFont,
            NSFontAttributeName,
            NSForegroundColorAttributeName,
        )

        try:
            attributes = {
                NSFontAttributeName: NSFont.labelFontOfSize_(
                    fontSize / self.getScale()
                ),
                NSForegroundColorAttributeName: fontColor or NSColor.textColor(),
            }
            NSAttributedString.alloc().initWithString_attributes_(
                text, attributes
            ).drawAtPoint_alignment_(textPosition, _TEXT_ALIGNMENTS.get(align, 6))
        except UnsupportedCapability:
            raise  # refusals stay reported, not logged away
        except Exception as error:  # noqa: BLE001 - the SDK logs and keeps drawing
            self.logError(f"drawTextAtPoint: {error!r}")

    def getHandleSize(self) -> float:
        return 7.0 / self._scale  # Glyphs' medium handle size, in glyph units


class SelectTool(_Plugin):
    def init(self):
        self.name = "My Select Tool"
        self.toolbarPosition = 100
        self.keyboardShortcut = None
        self.generalContextMenus = []
        if not hasattr(self, "inspectorDialogView"):
            self.inspectorDialogView = None
        _optional(self, "settings")
        _optional(self, "start")
        self._activate = hasattr(self, "activate")
        self._deactivate = hasattr(self, "deactivate")
        self._foreground = hasattr(self, "foreground")
        self._background = hasattr(self, "background")
        return self

    def title(self) -> str:
        return self.name

    def trigger(self):
        return self.keyboardShortcut

    def willActivate(self) -> None:
        if self._activate:
            self.activate()

    def willDeactivate(self) -> None:
        if self._deactivate:
            self.deactivate()

    def drawForegroundForLayer_options_(self, layer, options) -> None:
        if self._foreground:
            self.foreground(layer)

    def drawBackgroundForLayer_options_(self, layer, options) -> None:
        if self._background:
            self.background(layer)

    def editViewController(self):
        """The current canvas: set by the tool bridge during an event, else built
        from the paint context while the tool's foreground/background paints."""
        view = self.__dict__.get("_edit_view")
        if view is not None:
            return view
        context = self.__dict__.get("_paint_context")
        if context is None:
            from ..ui.cocoa import unsupported

            raise unsupported("SelectTool.editViewController outside a tool event")
        from .tool_bridge import CanvasView

        return CanvasView(None, None, getattr(self._env.host, "qt", None), context)

    # Glyphs' own select-tool handling is native and has no FontLab equivalent:
    # ``objc.super(...).mouseDown_(event)`` reaches these no-ops, and the tool
    # bridge leaves events a plugin does not override to FontLab.
    def _no_event(self, event) -> None:
        return None

    _no_event.glyport_default = True  # type: ignore[attr-defined]
    mouseDown_ = mouseDragged_ = mouseUp_ = mouseMoved_ = _no_event
    mouseDoubleDown_ = keyDown_ = keyUp_ = _no_event


class FileFormatPlugin(_Plugin):
    def init(self):
        self.name, self.icon, self.toolbarPosition = "My File Format", "ExportIcon", 100
        _optional(self, "settings")
        if not hasattr(self, "dialog"):
            self.dialog = None
        _optional(self, "start")
        return self

    def title(self) -> str:
        return self.name or type(self).__name__ or "New FileFormat Plugin"

    def exportSettingsView(self):
        return self.dialog

    def exportFont_(self, font) -> None:
        status, message = False, "export() is not implemented in the plugin."
        try:
            if hasattr(self, "export"):
                status, message = self.export(font)
        except Exception:
            import traceback

            self._env.log(traceback.format_exc())
            raise
        title = "Export done" if status else "Export failed"
        self._env.log(f"{self.title()}: {title}: {message}\n")
        self._env.host.notify(f"{self.title()}: {title}", str(message))


PLUGIN_CLASSES = (
    GeneralPlugin,
    FilterWithoutDialog,
    FilterWithDialog,
    PalettePlugin,
    ReporterPlugin,
    SelectTool,
    FileFormatPlugin,
)


def setUpMenuHelper(menu, items, defaultTarget) -> None:
    """SDK helper: add ``{"name", "action", "target", "state", "index"}`` entries."""
    if not isinstance(items, list):
        return
    for entry in items:
        if "menu" in entry:
            item = entry["menu"]
        else:
            if "view" in entry:
                raise TypeError("setUpMenuHelper: menu item views are unsupported")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                entry["name"], entry.get("action"), ""
            )
            if "state" in entry:
                item.setState_(entry["state"])
        item.setTarget_(entry.get("target", defaultTarget))
        index = int(entry.get("index", -1))
        if index >= 0:
            menu.insertItem_atIndex_(item, index)
        else:
            menu.addItem_(item)


def pathForResource(resourceName, extension, path=None):
    """SDK helper: the bundle resource's path, or None when it does not exist."""
    if not path or len(path) <= 10:
        raise ValueError("Please supply path")
    resources = _resources(path, object)
    name = f"{resourceName}.{extension}" if extension else str(resourceName)
    candidate = resources / name
    return str(candidate) if candidate.exists() else None


# Names the Glyphs SDK's ``GlyphsApp.plugins.__all__`` re-exports from
# Foundation/AppKit/GlyphsApp; plugins rely on ``from GlyphsApp.plugins import *``.
SDK_REEXPORTS = (
    "NSBundle", "NSLog", "NSObject", "NSClassFromString", "NSMutableArray",
    "NSMutableOrderedSet", "NSString", "NSAttributedString", "NSNumber",
    "NSUserDefaults", "NSUserNotification", "NSUserNotificationCenter",
    "NSNotificationCenter", "NSError", "NSLocalizedDescriptionKey",
    "NSLocalizedRecoverySuggestionErrorKey", "NSLocalizedString", "NSNotFound",
    "NSPoint", "NSMakePoint", "NSZeroPoint", "NSMakeRect", "NSMakeSize", "NSMinX",
    "NSMinY", "NSMaxX", "NSMaxY", "NSRect", "NSSize", "NSUnarchiver",
    "NSApplication", "NSColor", "NSNib", "NSMenu", "NSMenuItem", "NSView",
    "NSImage", "NSDocumentController", "NSBezierPath", "NSFont",
    "NSFontAttributeName", "NSForegroundColorAttributeName", "NSControlKeyMask",
    "NSCommandKeyMask", "NSShiftKeyMask", "NSAlternateKeyMask", "NSEvent",
    "NSAffineTransform", "Glyphs", "LogToConsole", "LogError", "ONSTATE",
    "OFFSTATE", "MIXEDSTATE", "Message", "distance", "python_method",
)  # fmt: skip


def make_plugins_module(
    env: PluginEnv, extras: Mapping[str, Any] | None = None
) -> ModuleType:
    """``GlyphsApp.plugins``: the seven classes bound to ``env``, SDK helpers and
    the SDK's re-exported Cocoa/GlyphsApp names that glyport provides (``extras``)."""
    module = ModuleType("GlyphsApp.plugins", "glyport Glyphs SDK plugin classes")
    module.__dict__.update(extras or {})
    for cls in PLUGIN_CLASSES:
        bound = type(
            cls.__name__, (cls,), {"_env": env, "__module__": "GlyphsApp.plugins"}
        )
        setattr(module, cls.__name__, bound)
    module.setUpMenuHelper = setUpMenuHelper
    module.pathForResource = pathForResource
    module.__all__ = [cls.__name__ for cls in PLUGIN_CLASSES]
    module.__all__ += ["setUpMenuHelper", "pathForResource", *(extras or {})]
    return module
