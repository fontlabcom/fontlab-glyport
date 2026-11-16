# this_file: src/fontlab_glyport/drawing/native_painters.py
"""Glyph-editor painters on FontLab's native canvas hooks (resolves R054).

Builds with ``flCanvas.appendPythonPainter(callback, order)`` call Python
inside the canvas paint: ``UnderOwner`` before the glyphs are drawn,
``OverOwner`` after them. ``callback(painter, canvas)`` gets a painter that
FontLab has saved and reset to viewport pixels; it is valid only during the
call, so this module never creates or ends one.

``NativeEditorPainters`` keeps App's registry, window poll, layer resolver and
per-glyph ``PaintContext`` maths, and replaces App's transparent overlay
widget with two native painters per canvas. Both phases work, so a Reporter
background is really drawn under the outlines. When a canvas dies, FontLab
drops its native painters itself; the ``destroyed`` slot only forgets the
Python entry.

``editor_painters(qt, fontlab, ...)`` picks this class when the build has the
hook, else Glyport's overlay ``EditorPainters`` (background as overlay, R054).
"""

import traceback
from contextvars import ContextVar
from dataclasses import replace
from typing import Any

from fontlabapp.qt.painting.editor import (
    AFTER_NATIVE_LAYER,
    BEFORE_NATIVE_LAYER,
    LAYER_FILTERS,
    OverlayEntry,
    PaintContext,
    PainterEntry,
)

from .editor import EditorPainters

# The canvas viewport widget while a native painter runs: FontLab's painter
# device is typed as a bare QPaintDevice, so cursor mapping needs the widget.
_PAINT_WIDGET: ContextVar[Any] = ContextVar("glyport_paint_widget", default=None)


def paint_widget() -> Any:
    """The viewport being painted by a native painter, else None."""
    return _PAINT_WIDGET.get()


PHASES = (BEFORE_NATIVE_LAYER, AFTER_NATIVE_LAYER)


def has_native_painters(fontlab: Any) -> bool:
    """True when this FontLab build has ``flCanvas.appendPythonPainter``."""
    return hasattr(getattr(fontlab, "flCanvas", None), "appendPythonPainter")


def editor_painters(qt: Any, fontlab: Any, **kwargs: Any) -> EditorPainters:
    """Native canvas painters when the build has them, else the overlay."""
    cls = NativeEditorPainters if has_native_painters(fontlab) else EditorPainters
    return cls(qt, fontlab, **kwargs)


class NativeEditorPainters(EditorPainters):
    """``EditorPainters`` drawing through native Under/Over canvas painters.

    ``overlays`` holds ``OverlayEntry(((under, over), (under_cb, over_cb)),
    viewport, canvas, destroyed)``: the native painter tokens and the Python
    callbacks, kept alive while FontLab holds them.
    """

    supports_before_native = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._phases: dict[int, str] = {}

    def register(
        self, phase, callback, layer_filter="active", *, document_id=None
    ) -> int:
        """Add a painter for either phase; return its token."""
        if phase not in PHASES or layer_filter not in LAYER_FILTERS:
            raise ValueError(f"bad painter phase/filter: {phase!r}, {layer_filter!r}")
        token = next(self._ids)
        self.painters[token] = PainterEntry(callback, layer_filter, document_id)
        self._phases[token] = phase  # before the first paint can run
        self._start()
        self._update_all()
        return token

    def remove(self, token: int) -> None:
        self._phases.pop(token, None)
        super().remove(token)

    def _attach(self, canvas: Any, viewport: Any) -> None:
        """Add one native painter per phase to ``canvas``."""
        flcanvas, key = self.fl.flCanvas, id(viewport)

        def under(painter: Any, native: Any) -> None:
            self._paint_native(painter, native, viewport, BEFORE_NATIVE_LAYER)

        def over(painter: Any, native: Any) -> None:
            self._paint_native(painter, native, viewport, AFTER_NATIVE_LAYER)

        first = canvas.appendPythonPainter(under, flcanvas.UnderOwner)
        try:
            second = canvas.appendPythonPainter(over, flcanvas.OverOwner)
        except BaseException:
            canvas.removePythonPainter(first)
            raise

        def destroyed(*args: Any) -> None:  # FontLab already dropped the painters
            self.overlays.pop(key, None)

        # Recorded first: a failed connect must not leak the pair on every poll.
        # The callbacks are kept too, so Python owns them while FontLab calls them.
        self.overlays[key] = OverlayEntry(
            ((first, second), (under, over)), viewport, canvas, destroyed
        )
        viewport.destroyed.connect(destroyed)

    def _detach(self, key: int) -> None:
        """Remove one canvas's native painters; every step is attempted."""
        (tokens, _), viewport, canvas, destroyed = self.overlays.pop(key)
        steps = [lambda: viewport.destroyed.disconnect(destroyed)]
        steps += [lambda t=token: canvas.removePythonPainter(t) for token in tokens]
        failure = None
        for step in steps:
            try:
                step()
            except Exception as exc:  # noqa: BLE001 - finish teardown, then report
                failure = failure or exc
        if failure is not None:
            raise failure

    def _update_all(self) -> None:
        for entry in self.overlays.values():
            entry.viewport.update()

    def _paint_native(
        self, painter: Any, canvas: Any, viewport: Any, phase: str
    ) -> None:
        """Native callback: run this phase's painters. Never raises."""
        if not self.painters:
            return
        token = _PAINT_WIDGET.set(viewport)
        try:
            for context in self._contexts(canvas, viewport, painter, None):
                self._dispatch(replace(context, phase=phase))
        except Exception as exc:  # noqa: BLE001 - never raise into the canvas paint
            self._report(exc, self)
        finally:
            _PAINT_WIDGET.reset(token)

    def _report(self, error: Exception, owner: Any) -> None:
        """The sink, which must not raise into the canvas paint either: if it
        fails, both errors are printed (as the tool bridge does)."""
        try:
            self.sink(error, owner)
        except Exception as sink_error:  # noqa: BLE001 - never raise into FontLab
            traceback.print_exception(error)
            traceback.print_exception(sink_error)

    def _dispatch(self, context: PaintContext) -> None:
        """App's dispatch, limited to painters of ``context.phase``."""
        wanted = "active" if context.is_active_layer else "inactive"
        for token, entry in list(self.painters.items()):
            if self._phases.get(token) != context.phase:
                continue
            if entry.layer_filter not in (wanted, "all"):
                continue
            if (
                entry.document_id is not None
                and entry.document_id != context.document_id
            ):
                continue
            context.painter.save()
            try:
                entry.callback(context)
            except Exception as exc:  # noqa: BLE001 - plugin failure is data
                self._report(exc, entry.callback)
            finally:
                context.painter.restore()
