# this_file: src/fontlab_glyport/plugins/loader.py
"""Load a plugin class into a host and unload it deterministically (R025-R027).

``load_plugin(cls, env)`` creates the instance the SDK way (``alloc().init()``
then ``loadPlugin()``) and registers what its protocol needs:

- FilterWithoutDialog: a FILTER_MENU item running ``filter(layer, True, {})``
  on the selected layers inside one undo group.
- FilterWithDialog: a FILTER_MENU item that snapshots the selected layers,
  opens the plugin's view in a host dialog (``setup()`` previews), keeps the
  result on Apply and restores the snapshots on Cancel, in one undo group.
- PalettePlugin: a host panel with ``theView()``.
- ReporterPlugin: a VIEW_MENU toggle "Show <title>"; while on, painters for
  each hook the plugin defines (foreground/background, active/inactive).
  If the host refuses before-native drawing (FontLab R054), background hooks
  paint in the post-native overlay. REPORTER_BACKGROUND_AS_OVERLAY records
  "background drawn as overlay" in the execution receipt: ink is above the
  native outlines, rather than below them.
- SelectTool: ``register_tool``; its foreground/background paint while it is
  active. FileFormatPlugin: ``register_file_format``.
- GeneralPlugin: nothing; its ``start()`` adds menus through ``Glyphs.menu``.

A ``register_*`` call the host cannot honour (``UnsupportedCapability``)
becomes a diagnostic; the rest of the plugin stays loaded. A failure in
``init``/``loadPlugin`` gives a ``failed`` handle with everything registered
so far removed (R027). ``unload()`` removes tokens newest first, once.
"""

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from ..drawing.fallbacks import BACKGROUND_AS_OVERLAY
from ..errors import UnsupportedCapability
from ..ui.cocoa_menu import NSMenuItem, NSOffState, NSOnState
from . import base
from .base import PluginEnv
from .host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER, PaintContext

# (plugin flag, phase, layer filter, protocol method)
_REPORTER_HOOKS = (
    ("_background", BEFORE_NATIVE_LAYER, "active", "drawBackgroundForLayer_options_"),
    ("_foreground", AFTER_NATIVE_LAYER, "active", "drawForegroundForLayer_options_"),
    (
        "_foregroundInViewCoords",
        AFTER_NATIVE_LAYER,
        "active",
        "drawForegroundWithOptions_",
    ),
    (
        "_backgroundInViewCoords",
        BEFORE_NATIVE_LAYER,
        "active",
        "drawBackgroundWithOptions_",
    ),
    (
        "_inactiveLayerBackground",
        BEFORE_NATIVE_LAYER,
        "inactive",
        "drawBackgroundForInactiveLayer_options_",
    ),
    (
        "_inactiveLayerForeground",
        AFTER_NATIVE_LAYER,
        "inactive",
        "drawForegroundForInactiveLayer_options_",
    ),
)
# SelectTool painters while the tool is active: (plugin flag, phase, method)
_TOOL_HOOKS = (
    ("_background", BEFORE_NATIVE_LAYER, "drawBackgroundForLayer_options_"),
    ("_foreground", AFTER_NATIVE_LAYER, "drawForegroundForLayer_options_"),
)


@dataclass
class PluginHandle:
    """A loaded (or failed) plugin and every host token it holds."""

    plugin: Any
    kind: str
    env: PluginEnv
    status: str = "loaded"
    error: Exception | None = None
    tokens: list[object] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    painters: list[object] = field(default_factory=list)
    dialog: object | None = None  # the open FilterWithDialog session's token
    views: list[Any] = field(default_factory=list)  # plugin views to dispose

    def diagnose(self, message: str) -> None:
        if message not in self.diagnostics:
            self.diagnostics.append(message)

    def _register(self, what: str, call: Callable[[], object]) -> object | None:
        try:
            token = call()
        except UnsupportedCapability as error:
            self.diagnostics.append(f"{what}: {error}")
            return None
        self.tokens.append(token)
        return token

    def unload(self) -> None:
        """Cancel an open dialog, remove painters and registrations newest
        first, dispose the plugin's views. Every step is attempted; the first
        failure is re-raised afterwards. Idempotent."""
        host, failures, menu = self.env.host, [], self.env.menu
        steps: list[Callable[[], None]] = []
        if self.dialog is not None:
            steps.append(lambda token=self.dialog: host.remove(token))
        steps += [lambda t=t: host.remove(t) for t in reversed(self.painters)]
        steps += [lambda t=t: host.remove(t) for t in reversed(self.tokens)]
        steps += [view.dispose for view in self._owned_views()]
        if menu is not None:
            steps += [lambda t=t: menu.forget(t) for t in self.tokens]
        self.painters, self.tokens, self.views, self.dialog = [], [], [], None
        self.env.filters.pop(id(self.plugin), None)
        for step in steps:
            try:
                step()
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if self.status == "loaded":
            self.status = "unloaded"
        if failures:
            raise failures[0]

    def _owned_views(self) -> list[Any]:
        """Cocoa view trees the plugin made (NIB top-level objects, its dialog)."""
        plugin, found = self.plugin, list(self.views)
        if plugin is not None:
            top_level = getattr(plugin, "topLevelObjects", None) or ()
            candidates = [*top_level, getattr(plugin, "dialog", None)]
            found += [v for v in candidates if callable(getattr(v, "dispose", None))]
        unique: dict[int, Any] = {}
        for view in found:
            unique.setdefault(id(view), view)
        return list(unique.values())

    def _remove_painters(self) -> None:
        host, failures = self.env.host, []
        while self.painters:
            try:
                host.remove(self.painters.pop())
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if failures:
            raise failures[0]


def _kind(cls: type) -> str:
    for base_class in base.PLUGIN_CLASSES:
        if issubclass(cls, base_class):
            return base_class.__name__
    raise TypeError(f"{cls.__name__} is not a Glyphs plugin class")


def load_plugin(cls: type, env: PluginEnv) -> PluginHandle:
    """Instantiate ``cls`` (bound to ``env``) and register it with the host."""
    handle = PluginHandle(None, _kind(cls), env)
    collect = env.menu.collect() if env.menu is not None else nullcontext([])
    try:
        with collect as menu_tokens:
            try:
                plugin = cls.alloc()
                handle.plugin = plugin
                owned = (
                    env.menu.owned_by(env.runner(plugin)) if env.menu else nullcontext()
                )
                with owned:  # Glyphs.menu items from init/start run via its guard
                    handle.plugin = plugin.init()
                    handle.plugin.loadPlugin()
                _REGISTER[handle.kind](handle)
                if handle.kind in {"FilterWithoutDialog", "FilterWithDialog"}:
                    env.filters[id(handle.plugin)] = handle.plugin
            finally:  # Glyphs.menu items added by init/start belong to this plugin
                handle.tokens[:0] = menu_tokens
    except Exception as error:  # noqa: BLE001 - a failed receipt, not a crash
        handle.status, handle.error = "failed", error
        try:
            handle.unload()
        except Exception as cleanup:  # noqa: BLE001 - keep the original error
            handle.diagnostics.append(f"cleanup after failed start: {cleanup!r}")
        handle.status = "failed"
    return handle


def _menu_item(handle: PluginHandle, title: str, action: Callable[[Any], None]):
    plugin, env = handle.plugin, handle.env
    item = NSMenuItem(title, lambda sender: env.guard(plugin, action, sender))
    key = getattr(plugin, "keyboardShortcut", None)
    if key:
        item.setKeyEquivalent_(key)
        item.setKeyEquivalentModifierMask_(
            getattr(plugin, "keyboardShortcutModifier", 0)
        )
    return item


def _register_general(handle: PluginHandle) -> None:
    """GeneralPlugin: its own ``start()`` registered whatever it needs."""


def _register_filter_without_dialog(handle: PluginHandle) -> None:
    plugin, host = handle.plugin, handle.env.host

    def run(sender) -> None:
        layers = list(host.selected_layers())
        with host.undo_group(plugin.title()):
            for layer in layers:
                plugin.runFilterWithLayer_error_(layer, None)
        host.redraw()

    item = _menu_item(handle, plugin.title(), run)
    handle._register("FILTER_MENU", lambda: host.register_menu("FILTER_MENU", item))


def _register_filter_with_dialog(handle: PluginHandle) -> None:
    plugin, env = handle.plugin, handle.env
    host = env.host

    def run(sender) -> None:
        if handle.dialog is not None:
            return  # one dialog session per plugin instance
        layers = list(host.selected_layers())
        if not layers:
            return
        plugin.layers = layers
        plugin.shadowLayers = [host.snapshot_layer(layer) for layer in layers]
        group = host.undo_group(plugin.title())
        group.__enter__()

        def closed(applied: bool) -> None:
            try:
                if not applied:
                    for layer, shadow in zip(layers, plugin.shadowLayers, strict=True):
                        host.restore_layer(layer, shadow)
            finally:
                handle.dialog = None
                group.__exit__(None, None, None)
                plugin.layers, plugin.shadowLayers = (), ()
                host.redraw()

        try:
            plugin.setup()
            view = plugin.view()
            if view is None:
                from ..ui.cocoa import unsupported

                error = unsupported("FilterWithDialog.view")
                handle.diagnose(str(error))
                raise error
            handle.dialog = host.run_dialog(
                view, plugin.title(), plugin.actionName(), closed
            )
        except BaseException:
            closed(False)
            raise

    item = _menu_item(handle, plugin.title() + "…", run)
    handle._register("FILTER_MENU", lambda: host.register_menu("FILTER_MENU", item))


def _register_palette(handle: PluginHandle) -> None:
    plugin, host = handle.plugin, handle.env.host
    view = plugin.theView()
    if view is None:
        handle.diagnostics.append("PalettePlugin: no view (dialog is None)")
        return
    if callable(getattr(view, "dispose", None)):
        handle.views.append(view)  # the panel content is disposed on unload
    handle._register(
        "panel",
        lambda: host.register_panel(
            view, plugin.title(), plugin.minHeight(), plugin.maxHeight()
        ),
    )


def _painter(handle: PluginHandle, method: str) -> Callable[[PaintContext], None]:
    plugin, env = handle.plugin, handle.env

    def paint(context: PaintContext) -> None:
        options = {"Scale": context.scale, "Black": False}
        state = plugin.__dict__
        saved = {k: state[k] for k in ("_paint_layer", "_paint_context") if k in state}
        plugin._paint_layer, plugin._paint_context = context.layer, context
        try:
            with env.paint_scope(context):
                if method in (
                    "drawForegroundWithOptions_",
                    "drawBackgroundWithOptions_",
                ):
                    from ..drawing.context import reporter_view_scope

                    with reporter_view_scope(context.scale):
                        env.guard(plugin, getattr(plugin, method), options)
                else:
                    env.guard(plugin, getattr(plugin, method), context.layer, options)
        finally:
            for key in ("_paint_layer", "_paint_context"):
                state.pop(key, None)
            state.update(saved)

    return paint


def _register_reporter(handle: PluginHandle) -> None:
    plugin, host = handle.plugin, handle.env.host
    if getattr(
        host, "reporter_background_phase", BEFORE_NATIVE_LAYER
    ) == AFTER_NATIVE_LAYER and any(
        getattr(plugin, flag, False)
        for flag, phase, _, _ in _REPORTER_HOOKS
        if phase == BEFORE_NATIVE_LAYER
    ):
        _note_background_overlay(handle)

    def toggle(sender) -> None:
        if handle.painters:
            handle._remove_painters()
            sender.setState_(NSOffState)
        else:
            _activate_reporter(handle)
            sender.setState_(NSOnState if handle.painters else NSOffState)
        host.redraw()

    item = _menu_item(handle, f"Show {plugin.title()}", toggle)
    handle._register("VIEW_MENU", lambda: host.register_menu("VIEW_MENU", item))
    _register_reporter_options(handle)


def _register_reporter_options(handle: PluginHandle) -> None:
    """``generalContextMenus`` as VIEW_MENU items after the toggle: FontLab
    offers Python no hook into the glyph editor's context menu. A header
    without action is disabled; an action runs (with ``sender`` only if it
    takes one) and every state is re-read from the list the plugin rebuilds;
    a ``view`` entry toggles that view in a host panel."""
    plugin, host, env = handle.plugin, handle.env.host, handle.env
    entries = list(getattr(plugin, "generalContextMenus", None) or [])
    named: list[tuple[int, NSMenuItem]] = []

    def resync() -> None:
        current = list(getattr(plugin, "generalContextMenus", None) or [])
        for index, menu_item in named:
            if index < len(current) and "state" in current[index]:
                state = NSOnState if current[index]["state"] else NSOffState
                menu_item.setState_(state)

    for index, entry in enumerate(entries):
        if "view" in entry:
            title = f"{plugin.title()} Settings"
            panel: list = []

            def show(sender, view=entry["view"], title=title, panel=panel) -> None:
                if panel:  # open: close it
                    token = panel.pop()
                    handle.tokens.remove(token)
                    host.remove(token)
                else:  # an open panel is removed on unload with the other tokens
                    token = host.register_panel(view, title, 0, 0)
                    panel.append(token)
                    handle.tokens.append(token)

            item = NSMenuItem(
                title + "\u2026", lambda s, f=show: env.guard(plugin, f, s)
            )
            handle._register(
                "VIEW_MENU", lambda i=item: host.register_menu("VIEW_MENU", i)
            )
            continue
        action = entry.get("action")

        def run(sender, action=action) -> None:
            import inspect

            takes_sender = bool(inspect.signature(action).parameters)
            action(sender) if takes_sender else action()
            resync()
            host.redraw()

        item = NSMenuItem(
            str(entry.get("name", "")),
            (lambda s: None)  # a disabled header
            if action is None
            else (lambda s, f=run: env.guard(plugin, f, s)),
        )
        if action is None:
            item.setEnabled_(False)
        if "state" in entry:
            item.setState_(NSOnState if entry["state"] else NSOffState)
            named.append((index, item))
        handle._register("VIEW_MENU", lambda i=item: host.register_menu("VIEW_MENU", i))


def _note_background_overlay(handle: PluginHandle) -> None:
    note = f"{BACKGROUND_AS_OVERLAY.code}: {BACKGROUND_AS_OVERLAY.message}"
    if note not in handle.diagnostics:
        handle.diagnostics.append(note)
        if handle.env.diagnostic_sink is not None:
            handle.env.diagnostic_sink(BACKGROUND_AS_OVERLAY)


def _activate_reporter(handle: PluginHandle) -> None:
    plugin = handle.plugin
    for flag, phase, layers, method in _REPORTER_HOOKS:
        if not getattr(plugin, flag, False):
            continue
        _add_painter(handle, phase, method, layer_filter=layers)


def _add_painter(handle: PluginHandle, phase: str, method: str, **kwargs) -> None:
    """Register one paint hook; a refused background falls back to an overlay
    (with the R054 note), any other refusal becomes a diagnostic."""
    host = handle.env.host
    if phase == BEFORE_NATIVE_LAYER:
        phase = getattr(host, "reporter_background_phase", phase)
        if phase != BEFORE_NATIVE_LAYER:
            _note_background_overlay(handle)
    try:
        token = host.register_painter(phase, _painter(handle, method), **kwargs)
    except UnsupportedCapability as error:
        if phase != BEFORE_NATIVE_LAYER:
            handle.diagnose(f"{method}: {error}")
            return
        try:
            token = host.register_painter(
                AFTER_NATIVE_LAYER, _painter(handle, method), **kwargs
            )
        except UnsupportedCapability as overlay_error:
            handle.diagnose(f"{method}: {error}; overlay: {overlay_error}")
            return
        _note_background_overlay(handle)
    handle.painters.append(token)


def _register_select_tool(handle: PluginHandle) -> None:
    """``register_tool``; while the tool is active its ``foreground`` and
    ``background`` paint on the active layer, like a reporter's."""
    plugin, host = handle.plugin, handle.env.host

    def activate() -> None:
        handle._remove_painters()  # a repeated activate never paints twice
        for flag, phase, method in _TOOL_HOOKS:
            if getattr(plugin, flag, False):
                _add_painter(handle, phase, method)

    handle._register(
        "tool",
        lambda: host.register_tool(
            plugin,
            guard=handle.env.guard,
            activate=activate,
            deactivate=handle._remove_painters,
        ),
    )


def _register_file_format(handle: PluginHandle) -> None:
    host = handle.env.host
    plugin, guard = handle.plugin, handle.env.guard
    handle._register(
        "file format", lambda: host.register_file_format(plugin, guard=guard)
    )


_REGISTER = {
    "GeneralPlugin": _register_general,
    "FilterWithoutDialog": _register_filter_without_dialog,
    "FilterWithDialog": _register_filter_with_dialog,
    "PalettePlugin": _register_palette,
    "ReporterPlugin": _register_reporter,
    "SelectTool": _register_select_tool,
    "FileFormatPlugin": _register_file_format,
}
