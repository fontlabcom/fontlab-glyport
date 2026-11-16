# this_file: src/fontlab_glyport/plugins/fontlab_host.py
"""The plugin host contract on FontLab 9 (R025-R027).

What this module keeps (Glyphs-specific):

- Menus: Glyphs menu names map to FontLab's main-window menus by title
  (FILE "File", EDIT "Edit", VIEW "View", GLYPH "Glyph", PATH "Contour",
  WINDOW "Window", SCRIPT "Script", HELP "Help"); FILTER_MENU and APP_MENU
  have no FontLab counterpart and go to an owned "Glyphs Plugins" menu. Each
  NSMenuItem becomes an owned QAction; its ``triggered`` runs ``item.fire()``
  through the error sink, and item changes (title, state, enabled) update it.
- Panels and filter dialogs are owned tool windows (FontLab's own panel
  registry is not scriptable here); a dialog closes with Apply or Cancel.
- Painters go to the session's editor painters: native canvas painters
  (``drawing.native_painters``) when the build has them, else the overlay
  :class:`~fontlab_glyport.drawing.editor.EditorPainters`.
- Tools: ``flWorkspace.registerPythonTool`` with a
  :class:`~fontlab_glyport.plugins.tool_bridge.ToolBridge`; builds without
  it raise ``UnsupportedCapability``. Tools have no icon yet (SDK icons are
  PDF resources).
- File formats: a File-menu action "Export with <title>…" calls
  ``exportFont_`` with the current font.
- Layers, fonts, snapshots and undo come from an injected ``model`` adapter
  (the GlyphsApp model of lane L1); without one those calls raise.

What App provides (generic): ``FontLabPluginHost`` is a
:class:`fontlabapp.qt.menus.OwnedMenus`. That class adds the QActions,
shows the tool windows, hands out the tokens and tears everything down. Its
rules hold here unchanged: every token removes its widgets and connections
exactly once; ``close()`` removes everything newest first, tries each item and
re-raises the first failure. Nothing is disconnected or deleted while a signal
of the host's own widgets dispatches (the PythonQtSignalReceiver crash pattern
in AGENTS.md). Teardown, and any ``remove``/``close`` called from a host slot
(menu action, Apply/Cancel, title-bar close, ``on_close`` callback), wait for
App's shared zero-delay timer.

Why a subclass: ``OwnedMenus`` already has the seams this host needs
(``_token``, ``_menu``, ``_defer(first=True)``, ``_guarded``), so the subclass
adds only Glyphs mapping, NSMenuItem sync and the Apply/Cancel dialog. It never
edits App's private queue. A missing main window is App's
``qtsafe.MainWindowNotFound``; the host reports it as ``HostUnavailable``.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from fontlabapp.qt.menus import OwnedMenus
from fontlabapp.qt.safe import MainWindowNotFound

from ..errors import HostUnavailable, UnsupportedCapability
from ..ui.cocoa_menu import NSOnState
from .host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER

MENU_TITLES = {
    "FILE_MENU": "File",
    "EDIT_MENU": "Edit",
    "VIEW_MENU": "View",
    "GLYPH_MENU": "Glyph",
    "PATH_MENU": "Contour",
    "WINDOW_MENU": "Window",
    "SCRIPT_MENU": "Script",
    "HELP_MENU": "Help",
}
OWNED_MENU = "Glyphs Plugins"
# Space under the plugin's view for the Cancel and Apply buttons, in pixels.
_BUTTON_ROW = 44


def qt_widget(view: Any) -> Any:
    """A Cocoa view wrapper's Qt widget, or the widget itself (vanilla handles)."""
    return getattr(view, "_qt", view)


class FontLabPluginHost(OwnedMenus):
    @property
    def reporter_background_phase(self) -> str:
        """Known at load, before any painter is enabled: native canvas painters
        draw backgrounds before the outlines; the overlay fallback after (R054)."""
        painters = getattr(self, "painters", None)
        if getattr(painters, "supports_before_native", False):
            return BEFORE_NATIVE_LAYER
        return AFTER_NATIVE_LAYER

    @property
    def has_callbacks(self) -> bool:
        return self.has_items

    def __init__(
        self,
        qt: Any,
        fontlab: Any,
        *,
        error_sink: Callable[[Exception, object], object],
        painters: Any = None,
        model: Any = None,
        main_window: Any = None,
    ):
        super().__init__(
            qt,
            fontlab,
            error_sink=error_sink,
            owned_title=OWNED_MENU,
            main_window=main_window,
        )
        self.painters, self.model = painters, model
        # token -> extra undo that App does not know (NSMenuItem observer)
        self._cleanups: dict[int, Callable[[], None]] = {}

    # --- App seams ------------------------------------------------------------------
    def main_window(self) -> Any:
        """FontLab's main window; a missing one raises ``HostUnavailable``.

        Only App's ``qtsafe.MainWindowNotFound`` means "no window". A plain
        ``RuntimeError`` (the off-GUI-thread refusal) propagates, whatever its
        text says.
        """
        try:
            return super().main_window()
        except MainWindowNotFound as error:
            raise HostUnavailable(str(error)) from error

    def _menu(self, name: str) -> Any:
        """The QMenu of a Glyphs menu name; every other name gets the owned menu.

        Only the ``*_MENU`` keys of ``MENU_TITLES`` reach a FontLab menu. An
        unmapped Glyphs name (FILTER_MENU, APP_MENU) or a literal title such
        as "Edit" is not a mapped Glyphs menu name, so it lands in this host's
        own menu (never in another host's menu of the same title).
        """
        title = MENU_TITLES.get(name)
        if title is not None:
            return super()._menu(title)
        return self.own_menu()

    def remove(self, token: object) -> None:
        """Undo one item, including its NSMenuItem observer (see App ``remove``)."""
        cleanup = None if self.dispatching else self._cleanups.pop(token, None)  # type: ignore[arg-type]
        try:
            if cleanup is not None:
                cleanup()
        finally:
            super().remove(token)

    # --- menus ------------------------------------------------------------------
    def register_menu(self, menu: str, item: Any, index: int | None = None) -> int:
        """Add ``item`` as an owned QAction in ``menu``; return its token.

        Atomic: if the first sync fails (for example a bad icon), the token
        and its QAction are removed before the error re-raises (inside a
        host slot App defers that removal to the end of the dispatch).
        """

        def fire() -> None:
            self._guarded(item, item.fire)  # the sink gets the item, not the action

        token = self.add_action(menu, item.title(), fire, index=index)

        def changed(changed_item: Any) -> None:
            self._sync(self.action(token), changed_item)

        try:
            self._sync(self.action(token), item)
        except BaseException:
            self.remove(token)
            raise
        item._observers.append(changed)
        self._cleanups[token] = lambda: item._observers.remove(changed)
        return token

    def _sync(self, action: Any, item: Any) -> None:
        action.setText(item.title())
        action.setEnabled(item.isEnabled())
        image = getattr(item, "image", lambda: None)()
        if image is not None:
            action.setIcon(image.icon())
        if item.state() == NSOnState or action.isCheckable():
            action.setCheckable(True)
            action.setChecked(item.state() == NSOnState)

    # --- windows ---------------------------------------------------------------
    @staticmethod
    def _view_widget(view: Any) -> Any:
        """The Qt widget of a plugin view; a missing view is a located error."""
        if view is None:
            from ..ui.cocoa import unsupported

            raise unsupported("FilterWithDialog.view")
        return qt_widget(view)

    def register_panel(
        self, view: Any, title: str, min_height: int, max_height: int
    ) -> int:
        widget = self._view_widget(view)
        token, window = self.tool_window(widget, title)
        width = widget.geometry.width()
        window.resize(width, max(min_height, 1))
        window.setMinimumHeight(max(int(min_height), 1))
        window.setMaximumHeight(max(int(max_height), int(min_height), 1))
        return token

    def run_dialog(
        self, view: Any, title: str, apply_label: str, on_close: Callable[[bool], None]
    ) -> int:
        """Show ``view`` with Cancel/Apply; ``on_close(applied)`` runs once.

        Apply, Cancel, the title-bar close and removing the token all end the
        session through App's tool-window close. A button only records the
        outcome and closes the window. The button connections are dropped from
        the shared timer, after the dispatch that ended the session and before
        the window is closed and deleted.
        """
        gui = self.qt.QtGui
        widget = self._view_widget(view)
        outcome = [False]  # True only when Apply ended the session

        def release() -> None:
            cancel.clicked.disconnect(cancelled)
            apply.clicked.disconnect(applied)

        def ended() -> None:
            # App queued its teardown (close, deleteLater) just before this call.
            # The connections must go first: ``first=True`` puts ``release`` at
            # the queue front. The plugin view, not the window, owns errors.
            self._defer(release, first=True)
            self._guarded(view, on_close, outcome[0])

        token, window = self.tool_window(widget, title, on_close=ended)
        rect = widget.geometry
        width, height = rect.width(), rect.height()
        cancel, apply = gui.QPushButton(window), gui.QPushButton(window)
        cancel.setText("Cancel")
        apply.setText(str(apply_label or "Apply"))
        cancel.setGeometry(max(width - 190, 0), height + 8, 90, 28)
        apply.setGeometry(max(width - 95, 0), height + 8, 90, 28)
        window.resize(width, height + _BUTTON_ROW)

        @self._slot
        def cancelled(*args: Any) -> None:
            window.close()

        @self._slot
        def applied(*args: Any) -> None:
            outcome[0] = True
            window.close()

        cancel.clicked.connect(cancelled)
        apply.clicked.connect(applied)
        cancel.show()  # children added to a shown window stay hidden otherwise
        apply.show()
        return token

    # --- painters, tools, formats -------------------------------------------------
    def register_painter(
        self, phase, callback, *, document_id=None, layer_filter="active"
    ):
        if self.painters is None:
            raise HostUnavailable("no editor painters configured")
        inner = self.painters.register(
            phase, callback, layer_filter, document_id=document_id
        )
        return self._token(lambda: self.painters.remove(inner))

    def register_tool(
        self,
        tool: Any,
        *,
        guard: Callable | None = None,
        activate: Callable[[], Any] | None = None,
        deactivate: Callable[[], Any] | None = None,
    ) -> int:
        """Add ``tool`` to FontLab's tools; ``activate``/``deactivate`` run
        when FontLab switches to and away from it (see ``ToolBridge``)."""
        workspace_class = getattr(self.fl, "flWorkspace", None)
        if not hasattr(workspace_class, "registerPythonTool"):
            capability = "FontLab.register_tool"
            raise UnsupportedCapability(
                f"Unsupported capability: {capability} "
                "(this FontLab build has no flWorkspace.registerPythonTool)",
                capability=capability,
            )
        from .tool_bridge import ToolBridge

        bridge = ToolBridge(
            self.qt,
            tool,
            self.painters,
            guard=guard,
            activate=activate,
            deactivate=deactivate,
            sink=self.sink,
        )
        workspace = workspace_class.instance()
        # shortcut: no icon (SDK toolbar icons are PDF); add one when images load PDF
        native = workspace.registerPythonTool(tool.title(), None, bridge)
        # the token keeps the bridge alive for as long as FontLab may call it
        return self._token(
            lambda _bridge=bridge: workspace.unregisterPythonTool(native)
        )

    def register_file_format(
        self, file_format: Any, *, guard: Callable | None = None
    ) -> int:
        """File > "Export with <title>…"; ``guard(owner, function, *args)``
        (``PluginEnv.guard``) runs the plugin's export in its context."""
        from ..ui.cocoa_menu import NSMenuItem

        def export(sender):
            font = self.current_font()
            if guard is None:
                file_format.exportFont_(font)
            else:
                guard(file_format, file_format.exportFont_, font)

        from .base import plugin_image

        item = NSMenuItem(f"Export with {file_format.title()}…", export)
        image = plugin_image(self.qt, file_format, getattr(file_format, "icon", None))
        if image is not None:
            item.setImage_(image)
        return self.register_menu("FILE_MENU", item)

    # --- model and services ---------------------------------------------------------
    def _model(self) -> Any:
        if self.model is None:
            raise HostUnavailable("no GlyphsApp model adapter configured")
        return self.model

    def selected_layers(self):
        return self._model().selected_layers()

    def current_font(self):
        return self._model().current_font()

    def snapshot_layer(self, layer):
        return self._model().snapshot_layer(layer)

    def restore_layer(self, layer, snapshot) -> None:
        self._model().restore_layer(layer, snapshot)

    def undo_group(self, name: str) -> AbstractContextManager:
        return self._model().undo_group(name)

    def redraw(self) -> None:
        update = getattr(self.fl, "UpdateActiveCanvas", None)
        if callable(update):
            update()

    def notify(self, title: str, message: str) -> None:
        bar = self.main_window().statusBar()
        bar.showMessage(f"{title}: {message}", 5000)
