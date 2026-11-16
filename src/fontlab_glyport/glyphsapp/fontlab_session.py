# this_file: src/fontlab_glyport/glyphsapp/fontlab_session.py
"""One execution context's FontLab services, shared by all its import adapters.

``FontLabSession(ctx, version=...)`` joins the three issue-104 lanes for a script
or plugin run in FontLab:

- L1 model and ``GlyphsApp`` facade (``fontlab_bridge``): ``Glyphs.menu`` is an
  ``AppMenu`` over the plugin host, ``DRAWFOREGROUND`` callbacks become
  after-native-layer editor painters, ``DRAWBACKGROUND`` callbacks paint
  before the native layer on builds with native canvas painters (else as an
  overlay, R054).
- L2 plugin host, editor painters and Cocoa/Vanilla layer: ``GlyphsApp.plugins``
  classes bound to one ``PluginEnv``; ``FontLabPluginHost`` gets a model adapter
  and ``EditorPainters`` a ``layer_resolver``, so reporters receive model layers.
- L3 import adapters: ``AppKit``/``Foundation``/``Cocoa`` keep L3's value types
  and gain L2's Qt-backed classes, menus, drawing and event names; ``objc`` is
  L2's subset with ``lookUpClass`` over those classes.

Native pieces (PythonQt, ``fontlab``) are imported and built on first use, and
everything is closed with the context. ``plugins.register_plugin`` finds the
session as ``ctx.fontlab_session``.
"""

import traceback
from collections.abc import Callable
from contextlib import nullcontext
from types import ModuleType
from typing import Any

from ..errors import UnsupportedCapability
from ..model import GSAnchor, GSPath, Model
from ..model.backend import NodeInfo, PathInfo
from ..model.fontlab_backend import FontLabBackend
from ..model.proxies import GlyphsToolSelect
from ..profile_versions import ProfileVersion
from .defaults import JsonFileStore, default_defaults_path

COCOA_MODULES = ("AppKit", "Foundation", "Cocoa")


class ModelPluginAdapter:
    """``FontLabPluginHost(model=...)`` services over the glyport model."""

    def __init__(self, model: Model):
        self.model = model

    def current_font(self):
        return self.model.font

    def selected_layers(self) -> list:
        font = self.model.font
        return [] if font is None else list(font.selectedLayers)

    def snapshot_layer(self, layer) -> dict:
        """Everything a filter preview may change: width, every path (id,
        nodes with type, smoothness and selection, closedness), anchors,
        components, and the shape order (paths and components interleaved)."""
        return {
            "width": layer.width,
            "paths": [
                (
                    path.id,
                    tuple(
                        NodeInfo("", n.x, n.y, n.type, n.smooth, n.selected)
                        for n in path.nodes
                    ),
                    path.closed,
                )
                for path in layer.paths
            ],
            "anchors": [(a.name, a.x, a.y) for a in layer.anchors],
            "components": [(c.componentName, c.transform) for c in layer.components],
            "order": [
                ("path", s.id) if isinstance(s, GSPath) else ("component", s.id)
                for s in layer.shapes
            ],
        }

    @staticmethod
    def _content(layer) -> dict:
        """The layer as restore compares it: no ids, shape order kept."""
        return {
            "width": layer.width,
            "shapes": [
                (
                    "path",
                    tuple((n.x, n.y, n.type, n.smooth, n.selected) for n in s.nodes),
                    s.closed,
                )
                if isinstance(s, GSPath)
                else ("component", s.componentName, tuple(s.transform))
                for s in layer.shapes
            ],
            "anchors": sorted((a.name, a.x, a.y) for a in layer.anchors),
        }

    @staticmethod
    def _saved_content(snapshot: dict) -> dict:
        paths = {
            path_id: (nodes, closed) for path_id, nodes, closed in snapshot["paths"]
        }
        components = iter(snapshot["components"])
        shapes = []
        for kind, id in snapshot["order"]:
            if kind == "path":
                nodes, closed = paths[id]
                shapes.append(
                    (
                        "path",
                        tuple((n.x, n.y, n.type, n.smooth, n.selected) for n in nodes),
                        closed,
                    )
                )
            else:
                name, transform = next(components)
                shapes.append(("component", name, tuple(transform)))
        return {
            "width": snapshot["width"],
            "shapes": shapes,
            "anchors": sorted(snapshot["anchors"]),
        }

    def restore_layer(self, layer, snapshot: dict) -> None:
        """Put the snapshot back: changed paths are refilled in place, paths
        added since are removed, paths the preview deleted are re-inserted at
        their shape index with their node selection, anchors are restored.
        Components cannot be edited through the model, so a changed component
        list raises; so does any result that differs from the snapshot."""
        backend = self.model._backend
        if [(c.componentName, c.transform) for c in layer.components] != snapshot[
            "components"
        ]:
            raise UnsupportedCapability(
                "Filter preview changed the layer's components; glyport cannot restore them",
                capability="filter:restore-components",
            )
        layer.width = snapshot["width"]
        saved = {
            path_id: (nodes, closed) for path_id, nodes, closed in snapshot["paths"]
        }
        current = {path.id: path for path in layer.paths}
        for path_id, path in current.items():
            if path_id not in saved:
                layer.paths.remove(path)
        for index, (kind, path_id) in enumerate(snapshot["order"]):
            if kind != "path":
                continue
            nodes, closed = saved[path_id]
            path = current.get(path_id)
            if path is None:  # deleted by the preview: back at its shape index
                backend.insert_path(layer._id, index, PathInfo("", nodes, closed))
                continue
            shape = [(n.x, n.y, n.type, n.smooth) for n in path.nodes]
            if (
                shape != [(n.x, n.y, n.type, n.smooth) for n in nodes]
                or path.closed != closed
            ):
                backend.set_path_nodes(path_id, nodes, closed)
            else:
                for node, saved_node in zip(path.nodes, nodes, strict=True):
                    if node.selected != saved_node.selected:
                        node.selected = saved_node.selected
        names = {name for name, _, _ in snapshot["anchors"]}
        for anchor in list(layer.anchors):
            if anchor.name not in names:
                layer.anchors.remove(anchor)
        for name, x, y in snapshot["anchors"]:
            anchor = layer.anchors[name]
            if anchor is None:
                layer.anchors.append(GSAnchor(name, (x, y)))
            elif (anchor.x, anchor.y) != (x, y):
                anchor.position = (x, y)
        if self._content(layer) != self._saved_content(snapshot):
            raise UnsupportedCapability(
                "Filter preview could not be restored exactly",
                capability="filter:restore",
            )

    def undo_group(self, name: str):
        font = self.model.font
        return nullcontext() if font is None else font.undo_group(name)


def layer_resolver(model: Model, backend: FontLabBackend) -> Callable[[Any], Any]:
    """``EditorPainters`` hook: ``flGlyphInfo`` -> the model ``GSLayer`` shown.

    The glyph's active layer if it is a master layer, else the font's current
    master. Returns None (never raises: it runs inside ``paintEvent``) for a
    glyph outside the model's scope or any lookup failure.
    """

    def resolve(info):
        try:
            glyph = info.glyph
            font_id = backend.font_id_for(glyph.package)
            if font_id is None:
                return None
            font = model.fonts[font_id]
            gs_glyph = None if font is None else font.glyphs[glyph.name]
            if gs_glyph is None:
                return None
            masters = {m.name for m in font.masters}
            active = glyph.activeLayer
            name = active.name if active is not None else None
            if name not in masters:  # e.g. a "Sketch" layer: show the current master
                name = glyph.package.master
            return next(
                (layer for layer in gs_glyph.layers if layer.name == name), None
            )
        except Exception:  # noqa: BLE001 - a failed lookup paints without a layer
            return None

    return resolve


class FontLabSession:
    """Create with the execution context; ``adapters()`` goes into ``ctx.adapters``."""

    def __init__(
        self,
        ctx,
        *,
        version: ProfileVersion | tuple[float, float],
        packages=None,
        defaults=None,
        qt: Any = None,
        fontlab: Any = None,
        **bridge_options,
    ):
        from ..plugins.registry import FILTERS
        from .fontlab_bridge import FontLabGlyphsBridge

        self.ctx, self.version = ctx, version
        self._qt, self._fontlab = qt, fontlab
        self.backend = FontLabBackend(packages)
        self.model = Model(self.backend)
        self.defaults = (
            JsonFileStore(default_defaults_path()) if defaults is None else defaults
        )
        self._painters = self._plugin_host = self._menu = self._foundation = None
        self._appkit = self._env = None
        self._filters = FILTERS
        self.bridge = FontLabGlyphsBridge(
            log=ctx.output.write,
            version=version,
            document=self._document,
            painters=lambda: self.painters,
            paint_scope=self._paint_scope,
            diagnostic_sink=ctx.add_diagnostic,
            **bridge_options,
        )
        ctx.fontlab_session = self
        ctx.on_close(self.close)  # older than the facade's hook: runs after it
        ctx.on_run_end(self._finish_run_undo)

    # --- natives and L2 services, built on first use ---------------------------
    @property
    def qt(self) -> Any:
        if self._qt is None:
            import PythonQt

            self._qt = PythonQt
        return self._qt

    @property
    def fontlab(self) -> Any:
        if self._fontlab is None:
            import fontlab

            self._fontlab = fontlab
        return self._fontlab

    def _sink(self, error: Exception, sender: object) -> None:
        detail = "".join(traceback.format_exception(error))
        self.ctx.output.write(f"[GlyphsApp] {sender!r} failed:\n{detail}")

    @property
    def painters(self) -> Any:
        if self._painters is None:
            from ..drawing.native_painters import editor_painters

            self._painters = editor_painters(
                self.qt,
                self.fontlab,
                error_sink=self._sink,
                layer_resolver=layer_resolver(self.model, self.backend),
            )
        return self._painters

    @property
    def plugin_host(self) -> Any:
        if self._plugin_host is None:
            from ..plugins.fontlab_host import FontLabPluginHost

            self._plugin_host = FontLabPluginHost(
                self.qt,
                self.fontlab,
                error_sink=self._sink,
                painters=self.painters,
                model=ModelPluginAdapter(self.model),
            )
        return self._plugin_host

    @property
    def menu(self) -> Any:
        if self._menu is None:
            from ..plugins.menus import AppMenu

            self._menu = _LazyMenu(
                lambda: AppMenu(self.plugin_host, wrap=self.ctx.wrap)
            )
        return self._menu

    @property
    def appkit(self) -> dict:
        if self._appkit is None:
            from ..ui.cocoa_views import make_appkit_classes

            self._appkit = make_appkit_classes(
                self.qt,
                error_sink=self._sink,
                wrap=self.ctx.wrap,
                defaults=self.defaults,
            )
        return self._appkit

    def plugin_env(self) -> Any:
        if self._env is None:
            from ..drawing.context import paint_scope
            from ..plugins.base import PluginEnv

            self._env = PluginEnv(
                self.plugin_host,
                self.appkit,
                self._sink,
                log=self.ctx.output.write,
                defaults=self.defaults,
                paint_scope=paint_scope(self.qt),
                menu=self.menu.target,
                wrap=self.ctx.wrap,
                filters=self._filters,
                diagnostic_sink=self.ctx.add_diagnostic,
            )
        return self._env

    def _paint_scope(self, context) -> Any:
        from ..drawing.context import paint_scope

        return paint_scope(self.qt)(context)

    def _document(self, package):
        font_id = self.backend.font_id_for(package)
        font = None if font_id is None else self.model.fonts[font_id]
        return None if font is None else font.parent  # one document per font

    # --- adapters ---------------------------------------------------------------
    def adapters(self) -> dict[str, Callable[[], ModuleType]]:
        from ..ui.vanilla import test_module
        from . import glyphsapp_provider
        from .legacy_dialogs import legacy_dialog_providers

        ctx = self.ctx
        previous = {name: ctx.adapters.get(name) for name in (*COCOA_MODULES, "objc")}
        providers = {
            "GlyphsApp": glyphsapp_provider(
                self.model,
                self.bridge,
                profile=ctx.profile,
                defaults=self.defaults,
                wrap=ctx.wrap,
                error_sink=lambda error, event: self._sink(error, event),
                on_close=ctx.on_close,
                menu=self.menu,
                filters=self._filters,
            ),
            "GlyphsApp.plugins": self._plugins_module,
            "GlyphsApp.UI": self._ui_module,
            "vanilla": self._vanilla_module,
            "vanilla.dialogs": self._dialogs_module,
            "vanilla.vanillaBase": self._vanilla_base_module,
            "vanilla.test": test_module,
            "vanilla.test.testAll": test_module,
            "objc": self._objc_module,
        }
        for name in COCOA_MODULES:
            providers[name] = lambda name=name: self._cocoa_module(name, previous[name])
        providers.update(legacy_dialog_providers(self.bridge))
        return providers

    def _plugins_module(self) -> ModuleType:
        from ..plugins.base import SDK_REEXPORTS, make_plugins_module

        sources = [
            vars(self.ctx.import_module(name))
            for name in ("Foundation", "AppKit", "GlyphsApp")
        ]
        extras = {"objc": self.ctx.import_module("objc")}
        for name in SDK_REEXPORTS:
            # vars(), not getattr: placeholder modules raise for unknown names.
            found = next((src[name] for src in sources if name in src), None)
            if found is not None:
                extras[name] = found
        return make_plugins_module(self.plugin_env(), extras)

    def _ui_module(self) -> ModuleType:
        from .ui import make_ui_module

        return make_ui_module(self.ctx.import_module("vanilla"))

    def _vanilla_base_module(self):
        vanilla = self.ctx.import_module("vanilla")
        module = ModuleType("vanilla.vanillaBase")
        module.VanillaBaseObject = vanilla.VanillaBaseObject
        module.VanillaBaseControl = vanilla.VanillaBaseObject
        module.__all__ = ["VanillaBaseObject", "VanillaBaseControl"]
        return module

    def _vanilla_module(self) -> ModuleType:
        from ..ui.vanilla import vanilla_provider

        module = vanilla_provider(
            self.qt, self._sink, wrap=self.ctx.wrap, on_close=self.ctx.on_close
        )()
        self.ctx.windows = module.Window._env.open_windows
        return module

    def _dialogs_module(self) -> ModuleType:
        from ..ui.dialogs import dialogs_provider

        return dialogs_provider(
            self.qt, self._sink, wrap=self.ctx.wrap, on_close=self.ctx.on_close
        )()

    def _cocoa_names(self) -> dict[str, Any]:
        from ..drawing import events
        from ..drawing.cocoa_drawing import DRAWING_NAMES
        from ..ui import cocoa, cocoa_menu, cocoa_views
        from ..ui.cocoa_menu import NSMenu, NSMenuItem
        from ..ui.images import cursor_class, image_class

        # NS* constants of the Qt-backed Cocoa layer (button types, states,
        # autoresizing masks, ...), then the env-bound classes.
        names = {
            key: value
            for module in (cocoa_views, cocoa_menu, events)
            for key, value in vars(module).items()
            if key.startswith("NS") and isinstance(value, int)
        }
        names.update({k: v for k, v in self.appkit.items() if k != "close"})
        names.update(DRAWING_NAMES)
        from ..ui.cocoa_alert import alert_class

        dialogs = getattr(self.bridge, "_dialogs", None)
        answers = (
            getattr(dialogs, "_answers", None)
            if dialogs is not None
            else getattr(self.bridge, "answers", {})
        )
        if "_alert_class" not in self.__dict__:
            self._alert_class = alert_class(
                self.qt,
                self.appkit["NSButton"],
                answers=answers if answers is not None else {},
                interactive=bool(getattr(dialogs, "_interactive", False)),
            )
        names["NSAlert"] = self._alert_class
        names.update(NSMenu=NSMenu, NSMenuItem=NSMenuItem)
        root = getattr(self.ctx, "source_root", None)
        names["NSImage"] = image_class(self.qt, [root] if root else [])
        names["NSCursor"] = cursor_class(self.qt)
        for name in (  # one geometry implementation with L3's values (R-merge P2)
            "NSPoint",
            "NSSize",
            "NSRect",
            "NSMakeRect",
            "NSMakePoint",
            "NSMakeSize",
            "NSZeroPoint",
            "NSZeroSize",
            "NSZeroRect",
            "NSObject",
        ):
            names[name] = getattr(cocoa, name)
        names.update(self._foundation_names(names))
        return names

    def _foundation_names(self, names: dict[str, Any]) -> dict[str, Any]:
        """Foundation values (foundation.py): NSUserDefaults over this
        session's Glyphs.defaults store, NSClassFromString over the classes
        provided here, NSPasteboard/NSTimer on Qt (timers stop on close)."""
        from .. import foundation
        from ..bundles import bundle_class
        from ..cocoa_logging import NSLog
        from ..notifications import CONSTANTS as NOTIFICATION_CONSTANTS
        from ..notifications import NSNotification, notification_center_class
        from ..ui.application import application_class

        if self._foundation is None:
            self._foundation = foundation.qt_names(self.qt, self.ctx.on_close)
            self._foundation.update(NOTIFICATION_CONSTANTS)
            self._foundation["NSBundle"] = bundle_class(
                getattr(self.ctx, "source_root", None)
            )
            self._foundation.update(
                NSLog=NSLog,
                NSNotification=NSNotification,
                NSNotificationCenter=notification_center_class(
                    self.bridge,
                    wrap=self.ctx.wrap,
                    on_close=self.ctx.on_close,
                ),
            )
            application = application_class(
                self.qt,
                glyphs=lambda: self.ctx.import_module("GlyphsApp").Glyphs,
                main_window=lambda: self.fontlab.MainWindow(),
                on_close=self.ctx.on_close,
                wrap=self.ctx.wrap,
                error_sink=self._sink,
            )
            self._foundation.update(
                NSApplication=application,
                NSApp=application.sharedApplication(),
                NSAppearanceNameAqua="NSAppearanceNameAqua",
                NSAppearanceNameDarkAqua="NSAppearanceNameDarkAqua",
            )
        extra = dict(foundation.CONSTANTS)
        extra.update(foundation.GEOMETRY)
        extra.update(foundation.COLLECTIONS)
        extra.update(self._foundation)
        extra["NSUserDefaults"] = foundation.user_defaults_class(self.defaults)
        classes = {
            k: v
            for k, v in {**names, **extra}.items()
            if isinstance(v, type) and k not in foundation.STRUCT_NAMES
        }
        classes.setdefault("GlyphsToolSelect", GlyphsToolSelect)
        extra["NSClassFromString"] = foundation.class_from_string(classes)
        for name in foundation.DEFERRED:  # not classes NSClassFromString knows
            if name not in names:  # a real implementation always wins
                extra[name] = foundation.deferred_class("AppKit", name)
        return extra

    def _cocoa_module(self, name: str, previous: Callable | None) -> ModuleType:
        """L3's module (value types; unknown names raise at the script line)
        plus L2's names."""
        from ..execution import placeholder

        module = previous() if previous is not None else placeholder(name)
        names = self._cocoa_names()
        module.__dict__.update(names)
        module.__all__ = tuple(dict.fromkeys((*getattr(module, "__all__", ()), *names)))
        return module

    def _objc_module(self) -> ModuleType:
        from ..foundation import STRUCT_NAMES
        from ..ui.objc_bridge import make_objc_module

        classes = {
            k: v
            for k, v in self._cocoa_names().items()
            if isinstance(v, type) and k not in STRUCT_NAMES
        }
        return make_objc_module(classes)

    # --- teardown ---------------------------------------------------------------
    def _finish_run_undo(self) -> None:
        """A retained UI/callback may deliberately close the group later."""
        if self.ctx.windows or getattr(self.bridge, "has_callbacks", False):
            return
        if getattr(self._plugin_host, "has_callbacks", False):
            return
        if self._appkit is not None:
            window_type = self._appkit.get("NSWindow")
            if window_type is not None and any(
                isinstance(view, window_type)
                and not view.__dict__.get("_disposed")
                and view.isVisible()
                for view in window_type._env.views
            ):
                return
        self._finish_undo()

    def _finish_undo(self) -> None:
        failures = []
        for font in self.model._fonts.values():
            try:
                font._finish_undo(self.ctx.add_diagnostic)
            except BaseException as error:  # noqa: BLE001 - attempt every font
                failures.append(error)
        if failures:
            raise next(
                (e for e in failures if not isinstance(e, Exception)), failures[0]
            )

    def _purge_filters(self) -> None:
        if self._env is not None:
            for key, plugin in list(self._filters.items()):
                if getattr(plugin, "_env", None) is self._env:
                    self._filters.pop(key, None)

    def close(self) -> None:
        """Menus, plugin host, painters, AppKit environment, bridge: every step is
        attempted, the first failure re-raised."""
        steps = [self._finish_undo, self._purge_filters]
        if self._menu is not None and self._menu.built:
            steps.append(self._menu.target.close)
        if self._plugin_host is not None:
            steps.append(self._plugin_host.close)
        if self._painters is not None:
            steps.append(self._painters.close)
        if self._appkit is not None:
            steps.append(self._appkit["close"])
        steps.append(self.bridge.close)
        failures = []
        for step in steps:
            try:
                step()
            except BaseException as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if failures:
            raise next(
                (e for e in failures if not isinstance(e, Exception)), failures[0]
            )


class _LazyMenu:
    """``Glyphs.menu`` that builds the plugin host only when a script uses it."""

    def __init__(self, build: Callable[[], Any]):
        self._build, self._target = build, None

    @property
    def built(self) -> bool:
        return self._target is not None

    @property
    def target(self) -> Any:
        if self._target is None:
            self._target = self._build()
        return self._target

    def __getitem__(self, key):
        return self.target[key]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.target, name)
