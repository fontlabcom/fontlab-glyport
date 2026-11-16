# this_file: src/fontlab_glyport/plugins/host.py
"""The host contract plugins are registered through (R026).

These are the planned bridge operations of issue 101 R026, not claims about
FontLab: a host that lacks a capability raises ``UnsupportedCapability`` from
the ``register_*`` call, and the loader records that as a diagnostic of the
plugin instead of pretending the registration happened. Tokens are opaque,
unique, and removed once through ``remove``; removing a removed token does
nothing.

Painters receive a :class:`PaintContext`. ``phase`` is
``"before_native_layer"`` or ``"after_native_layer"``; ``layer_filter`` is
``"active"``, ``"inactive"`` or ``"all"`` and selects which native layers the
callback sees, never the paint order. ``painter`` is only valid during the
callback.
"""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol

from fontlabapp.qt.painting.editor import (
    AFTER_NATIVE_LAYER as AFTER_NATIVE_LAYER,  # noqa: PLC0414 - explicit public re-export
)
from fontlabapp.qt.painting.editor import (
    BEFORE_NATIVE_LAYER as BEFORE_NATIVE_LAYER,  # noqa: PLC0414 - explicit public re-export
)
from fontlabapp.qt.painting.editor import (
    LAYER_FILTERS as LAYER_FILTERS,  # noqa: PLC0414 - explicit public re-export
)
from fontlabapp.qt.painting.editor import (
    PaintContext as PaintContext,  # noqa: PLC0414 - explicit public re-export
)

# Glyphs menu names (GlyphsApp constants have these string values).
MENUS = (
    "APP_MENU",
    "FILE_MENU",
    "EDIT_MENU",
    "GLYPH_MENU",
    "PATH_MENU",
    "FILTER_MENU",
    "VIEW_MENU",
    "SCRIPT_MENU",
    "WINDOW_MENU",
    "HELP_MENU",
)


class PluginHost(Protocol):
    """Host services the plugin loader uses."""

    # Optional for older hosts: default is BEFORE_NATIVE_LAYER. FontLab
    # advertises AFTER_NATIVE_LAYER so load-time receipts describe the fallback.
    reporter_background_phase: str

    @property
    def has_callbacks(self) -> bool: ...

    def register_menu(
        self, menu: str, item: Any, index: int | None = None
    ) -> object: ...
    def register_panel(
        self, view: Any, title: str, min_height: int, max_height: int
    ) -> object: ...
    def register_tool(
        self,
        tool: Any,
        *,
        guard: Callable[..., Any] | None = None,
        activate: Callable[[], Any] | None = None,
        deactivate: Callable[[], Any] | None = None,
    ) -> object: ...
    def register_painter(
        self,
        phase: str,
        callback: Callable[[PaintContext], None],
        *,
        document_id: Any = None,
        layer_filter: str = "active",
    ) -> object: ...
    def register_file_format(
        self, file_format: Any, *, guard: Callable[..., Any] | None = None
    ) -> object:
        """``guard(owner, function, *args)`` runs the export in the plugin's
        context (``PluginEnv.guard``); a host calls the export through it."""
        ...

    def remove(self, token: object) -> None: ...
    def selected_layers(self) -> Sequence[Any]: ...
    def current_font(self) -> Any: ...
    def snapshot_layer(self, layer: Any) -> Any: ...
    def restore_layer(self, layer: Any, snapshot: Any) -> None: ...
    def undo_group(self, name: str) -> AbstractContextManager: ...
    def run_dialog(
        self, view: Any, title: str, apply_label: str, on_close: Callable[[bool], None]
    ) -> object: ...
    def redraw(self) -> None: ...
    def notify(self, title: str, message: str) -> None: ...
